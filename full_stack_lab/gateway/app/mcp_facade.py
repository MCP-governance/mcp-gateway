"""The Gateway as an MCP server: what employee harnesses connect to instead of the real servers.

Two shapes of the same policy path (D-30):
- `/mcp/<server>/` - one registered server, tools under their own names. The managed
  config of Claude Code, Codex, Gemini CLI and OpenCode lists these, so a harness sees
  `filesystem`, `git`, ... exactly as if it had connected to them directly.
- `/mcp/` - every operating server at once as `<server>__<tool>` (clients that take one URL).

tools/list returns the approved schema, not whatever the server says today.
tools/call runs through execute_call(). Identity comes from the transport (Bearer token
on HTTP/SSE, the spawn-time principal on stdio) and never from tool arguments.

Only initialize/ping/tools/list/tools/call are handled; resources, prompts,
sampling and the rest are not mediated, so the server does not register them and
the SDK answers "method not found" (MCP-METHOD-001 in the audit narrative).
"""
from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.parse import urlsplit

from mcp import types
from mcp.server.lowlevel.server import Server
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types.version import HANDSHAKE_PROTOCOL_VERSIONS
from pydantic import model_serializer

from . import db, output_contract, pac, registry, upstream_sessions
from .agent_contract import authenticated_user
from .core import execute_call, response_disposition

SEPARATOR = "__"
STDIO_PRINCIPAL = os.getenv("GATEWAY_STDIO_PRINCIPAL", "")
DECISION_LABEL = {"Allow": "허용", "Alert": "허용·경보", "Restrict": "제한 실행", "Approval": "승인 대기", "Block": "차단"}


def _headers(ctx: Any) -> Any:
    return getattr(getattr(ctx, "request", None), "headers", None)


async def _caller(ctx: Any) -> dict:
    """Verified principal for this request. stdio has no headers and uses the
    principal bound when the process was spawned; unset fails closed."""
    headers = _headers(ctx)
    if headers is None:
        if not STDIO_PRINCIPAL:
            raise ValueError("stdio ingress에 신원이 바인딩되지 않았습니다. GATEWAY_STDIO_PRINCIPAL을 설정하세요.")
        row = await db.fetch_one("SELECT token, role FROM principals WHERE token=%s", (STDIO_PRINCIPAL,))
        return {"principal": STDIO_PRINCIPAL, "roles": [row["role"] if row else "unknown"], "claims": {}}
    user = await authenticated_user(headers.get("authorization"), require_mcp=True)
    return user


def _conversation(ctx: Any, user: dict) -> tuple[str, str] | None:
    headers = _headers(ctx) or {}
    session_id = headers.get("mcp-session-id")
    jti = (user.get("claims") or {}).get("jti")
    # The SDK admitted this legacy session before invoking the handler; a body/task id cannot bind it.
    if getattr(ctx, "protocol_version", "") in HANDSHAKE_PROTOCOL_VERSIONS and session_id and jti:
        return session_id, jti
    return None


def _scope(ctx: Any) -> str | None:
    """The registered server this connection was opened for (`/mcp/<server>/`), or
    None on the aggregate endpoint. Set by main.ServerPath from the URL, never the body."""
    request = getattr(ctx, "request", None)
    return getattr(request, "scope", {}).get("mcp_server") if request is not None else None


def _harness(ctx: Any, headers: Any) -> dict:
    """Which MCP client is calling: the initialize clientInfo (claude-code,
    codex-mcp-client, gemini-cli-mcp-client, opencode, ...) and the User-Agent.
    Client-reported, so it describes the call and never decides it."""
    params = getattr(getattr(ctx, "session", None), "client_params", None)
    info = getattr(params, "client_info", None)
    return {
        "name": (getattr(info, "name", None) or "")[:60] or None,
        "version": (getattr(info, "version", None) or "")[:30] or None,
        "user_agent": (headers.get("user-agent") or "")[:120] or None,
    }


TRACEPARENT = re.compile(r"00-(?!0{32})[0-9a-f]{32}-(?!0{16})[0-9a-f]{16}-[0-9a-f]{2}")


def _traceparent(headers: Any) -> str | None:
    """W3C trace context the harness sent, kept for correlation only. It never decides a call."""
    value = (headers.get("traceparent") or "").strip().lower()
    return value if TRACEPARENT.fullmatch(value) else None


def _client_context(ctx: Any, user: dict) -> dict:
    """What the workstation says about itself. Client-reported, recorded as such.
    The OAuth client of the token is the workstation that signed in (password grant
    with client_id = workstation id), so harnesses that send no custom header still
    land on the right PC."""
    headers = _headers(ctx) or {}
    claims = user.get("claims") or {}
    harness = _harness(ctx, headers)
    return {
        "workstation": (headers.get("x-workstation-id") or claims.get("client_id") or "")[:64] or None,
        "agent": (headers.get("x-agent-name") or harness["name"] or harness["user_agent"] or "")[:80] or None,
        "harness": harness,
        "protocol_version": getattr(ctx, "protocol_version", None),
        "endpoint": _scope(ctx) or "aggregate",
        "task_id": (headers.get("x-agent-task-id") or "")[:64] or None,
        "token_jti": claims.get("jti"),
        "oauth_client": claims.get("client_id"),
        "device_id": claims.get("device_id"),
        "traceparent": _traceparent(headers),
        "delegation_headers": [name for name in pac.DELEGATION_HEADERS if name in headers],
    }


async def _approved_tools(role: str, server: str | None = None, principal: str = "",
                          protocol_version: str | None = None) -> list[types.Tool]:
    rows = await db.fetch_all(
        """SELECT t.server_id, t.name, t.action, t.description, t.input_schema,
               CASE WHEN t.approved_output_schema_hash IS NULL THEN NULL ELSE t.output_schema END AS output_schema, s.display_name
             FROM mcp_tools t JOIN mcp_servers s ON s.id = t.server_id
            WHERE t.enabled AND t.input_schema IS NOT NULL
              AND t.approved_schema_hash=t.observed_schema_hash
               AND (t.approved_output_schema_hash IS NULL OR t.approved_output_schema_hash=t.observed_output_schema_hash)
              AND t.approved_description_hash=t.observed_description_hash
              AND EXISTS (SELECT 1 FROM (SELECT exact_match,restricted_tools FROM catalog_snapshots
                          WHERE server_id=s.id ORDER BY id DESC LIMIT 1) c
                          WHERE c.exact_match OR (c.restricted_tools IS NOT NULL AND NOT t.name=ANY(c.restricted_tools)))
              AND COALESCE(s.lifecycle, 'OPERATING') = 'OPERATING'
              AND s.status NOT IN ('DISABLED', 'BLOCKED_SUPPLY_CHAIN')
              AND (%s::text IS NULL OR t.server_id = %s)
            ORDER BY t.server_id, t.name""", (server, server))
    person = await db.fetch_one("SELECT * FROM principals WHERE token=%s", (principal,))
    tools = []
    for row in rows:
        allowed = registry.allowed_principals(row["server_id"])
        if allowed is not None and principal not in allowed:
            continue
        if row["name"] not in registry.reviewed_tools(row["server_id"]):
            continue  # a tool nobody scoped is neither listed here nor callable (D-91)
        if not person or not pac.visible(person, row["server_id"], row["name"], row["action"]):
            continue
        if server:
            # A per-server endpoint is the server as the harness would see it directly:
            # its own tool names and descriptions.
            name, description = row["name"], row["description"] or ""
        else:
            name = f"{row['server_id']}{SEPARATOR}{row['name']}"
            description = f"[{row['display_name']} · {row['action']}] {row['description'] or ''}"
        schema = row.get("output_schema")
        if protocol_version not in output_contract.JSON_PROTOCOLS:
            # An array/scalar output contract cannot be advertised to object-era clients.
            if protocol_version not in output_contract.OBJECT_PROTOCOLS or (schema is not None and schema.get("type") != "object"):
                schema = None
        tools.append(types.Tool(name=name, description=description[:1500], inputSchema=row["input_schema"],
                                outputSchema=schema))
    return tools


class _NullStructuredResult(types.CallToolResult):
    @model_serializer(mode="wrap")
    def _with_explicit_null(self, handler, info):
        # SDK runner uses exclude_none=True, which otherwise loses a valid JSON null.
        data = handler(self)
        data["structuredContent" if info.by_alias else "structured_content"] = None
        return data


def _render(outcome: dict, protocol_version: str | None = None) -> types.CallToolResult:
    decision = outcome.get("decision", "Block")
    gateway = {
        "decision": decision, "policy_id": outcome.get("policy_id"), "decision_id": outcome.get("decision_id"),
        "trace_id": outcome.get("trace_id"), "approval_id": outcome.get("approval_id"),
        "data_class": outcome.get("data_class"), "action": outcome.get("action"),
        "upstream_attempted": bool(outcome.get("upstream_attempted")),
        "upstream_executed": bool(outcome.get("upstream_executed")),
        "execution_status": ("executed" if outcome.get("upstream_executed") else
                             "unconfirmed" if outcome.get("upstream_attempted") else "not_dispatched"),
        "response_disposition": response_disposition(outcome),
        "response_withheld": response_disposition(outcome) == "withheld",
        "restrictions_applied": outcome.get("restrictions_applied") or [],
    }
    header = f"[MCP Gateway · {DECISION_LABEL.get(decision, decision)} · {outcome.get('policy_id')}] {outcome.get('reason', '')}"
    result = outcome.get("result")
    if (outcome.get("upstream_executed") and result and decision in {"Allow", "Alert", "Restrict"}
            and gateway["response_disposition"] in {"returned", "masked"}):
        result = output_contract.for_protocol(result, protocol_version)
        # The tool's own output comes first. A notice at the top of an allowed result
        # ("허용·경보 ...") reads like a refusal to small models; they then tell the
        # user the call was blocked when it ran. The note goes last, phrased as done.
        # core._guarded_result passes only text items; anything else was withheld there.
        content = [types.TextContent(type="text", text=item["text"]) for item in result.get("content") or []]
        structured = result.get("structured")
        # Both representations use core's inspected payload, including privacy masking.
        if not content and "structured" in result:
            content = [types.TextContent(type="text", text=json.dumps(structured, ensure_ascii=False, allow_nan=False))]
        if decision != "Allow":
            applied = outcome.get("restrictions_applied") or []
            note = {"Alert": "실행되었으며 보안 경보로 기록되었습니다",
                    "Restrict": "제한을 적용해 실행되었습니다" + (f"({', '.join(applied)})" if applied else "")}.get(decision, "실행되었습니다")
            content.append(types.TextContent(type="text", text=f"\n(MCP Gateway: {note} · {outcome.get('policy_id')})"))
        result_type = _NullStructuredResult if "structured" in result and structured is None else types.CallToolResult
        return result_type(content=content or [types.TextContent(type="text", text="(빈 결과)")],
                                    structuredContent=structured, isError=bool(result.get("is_error")),
                                    _meta={"gateway": gateway})
    if decision == "Approval":
        text = (f"{header}\n관리자 승인이 필요합니다. 승인 ID {outcome.get('approval_id')} "
                "(Console → 승인 대기). 승인되면 Gateway가 이 요청을 그대로 실행합니다.")
    elif gateway["response_withheld"]:
        text = (f"{header}\n도구는 공급자에서 이미 실행됐고 결과만 반환하지 않았습니다. "
                "쓰기·전송 효과는 이 보류로 되돌려지지 않습니다.")
    else:
        text = header + (f"\n오류: {outcome['error']}" if outcome.get("error") else "")
    return types.CallToolResult(content=[types.TextContent(type="text", text=text)], isError=True,
                                _meta={"gateway": gateway})


def build_mcp() -> Server:
    async def list_tools(ctx: Any, params: Any) -> types.ListToolsResult:
        try:
            user = await _caller(ctx)
            return types.ListToolsResult(tools=await _approved_tools(
                user["roles"][0], _scope(ctx), user["principal"], getattr(ctx, "protocol_version", None)))
        except Exception:
            raise ValueError("도구 목록 요청을 완료하지 못했습니다.") from None

    async def call_tool(ctx: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
        try:
            user = await _caller(ctx)
            name = params.name or ""
            server_id = _scope(ctx)
            if server_id:
                tool = name
            else:
                server_id, _, tool = name.partition(SEPARATOR)
            token = upstream_sessions.downstream.set(_conversation(ctx, user))
            try:
                outcome = await execute_call({
                    "server_id": server_id, "tool": tool, "arguments": dict(params.arguments or {}),
                    "_response_protocol": getattr(ctx, "protocol_version", None),
                    "user_token": user["principal"], "client": _client_context(ctx, user), "transport_claims": user.get("claims") or {},
                })
            finally:
                upstream_sessions.downstream.reset(token)
        except Exception:
            raise ValueError("도구 호출을 완료하지 못했습니다.") from None
        return _render(outcome, getattr(ctx, "protocol_version", None))

    return Server(
        "mcp-governance-security-gateway",
        version="3.0.0",
        instructions=("BoB Corp MCP Gateway. 모든 도구 호출은 신원·계약·자원 분류·OPA 정책으로 판정됩니다. "
                      "차단·승인 대기 응답의 사유를 사용자에게 그대로 알려 주세요."),
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


def transport_security() -> TransportSecuritySettings:
    hosts = ["gateway:*", "gateway-sse:*", "localhost:*", "127.0.0.1:*"]
    # 실기기 배치(compose.field.yaml): PC의 하네스는 공개 주소로 부르고 Caddy가 그 Host를 그대로 넘긴다.
    # DNS 리바인딩 방어는 유지하되, 배포자가 정한 그 이름 하나만 더한다(포트 없는 Host도 오므로 둘 다).
    public = urlsplit(os.getenv("GATEWAY_PUBLIC_MCP_URL", "")).hostname
    if public and f"{public}:*" not in hosts:
        hosts += [public, f"{public}:*"]
    name = os.getenv("FIELD_PUBLIC_NAME", "")
    if name:
        hosts += [name, f"{name}:*"]
    return TransportSecuritySettings(
        allowed_hosts=hosts,
        allowed_origins=["http://localhost:*", "http://127.0.0.1:*"],
    )
