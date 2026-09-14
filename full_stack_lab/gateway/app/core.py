from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import httpx2
from mcp import Client, StdioServerParameters
from mcp.client.streamable_http import streamable_http_client
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from psycopg.types.json import Jsonb
from jsonschema import Draft202012Validator

from . import db

OPA_URL = os.getenv("OPA_URL", "http://opa:8181/v1/data/mcp/authz/decision")
HTTP_MCP_URL = os.getenv("HTTP_MCP_URL", "http://mock-http-mcp:9000/mcp/")
GITHUB_MCP_URL = os.getenv("GITHUB_MCP_URL", "https://api.githubcopilot.com/mcp/")
GITHUB_TOKEN = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN", "")
EFFECT_LOG = Path(os.getenv("EFFECT_LOG", "/runtime/upstream-effects.jsonl"))
REPORT_DIR = Path(os.getenv("REPORT_DIR", "/reports"))
POLICY_PATH = Path(os.getenv("POLICY_PATH", "/policy/policy.rego"))
TIME_MCP_PYTHON = os.getenv("TIME_MCP_PYTHON", "/opt/time-mcp/bin/python")
APPROVAL_TTL_MINUTES = 10

TOOL_SPECS = {
    "read_document": {"server_id": "mock-http", "registry_name": "read_document", "action": "r"},
    "write_document": {"server_id": "mock-http", "registry_name": "write_document", "action": "w"},
    "send_external": {"server_id": "mock-http", "registry_name": "send_external", "action": "x"},
    "get_current_time": {"server_id": "mock-stdio", "registry_name": "get_current_time", "action": "r"},
    "github_get_file": {"server_id": "github", "registry_name": "get_file_contents", "action": "r"},
}
UNSAFE_METADATA = re.compile(
    r"ignore\s+(all\s+)?previous|system\s+prompt|credential|secret\s+key|bypass\s+policy",
    re.IGNORECASE,
)
MAX_RESULT_BYTES = int(os.getenv("MAX_RESULT_BYTES", "262144"))
DEFAULT_ENFORCEMENT = os.getenv("GATEWAY_ENFORCEMENT", "enforce")
# Integrity failures are not opinions. A drifted catalog, an unregistered tool, a
# critical supply-chain finding or an unavailable policy engine stay enforced even
# while the gateway is only observing the permission model, because "observe" cannot
# mean "call a server we can no longer vouch for".
# P-RATE- is here because a call-rate ceiling protects the gateway and the upstream,
# not a permission opinion about who may read what. Observing it would mean having no
# ceiling at all for as long as observation lasts.
ALWAYS_ENFORCED = ("MCP-", "P-CONTROL-", "P-INPUT-", "P-RATE-")
RATE_LIMIT_CALLS = int(os.getenv("RATE_LIMIT_CALLS", "60"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
IMPORTANT_BURST_LIMIT = int(os.getenv("IMPORTANT_BURST_LIMIT", "10"))
IMPORTANT_BURST_MINUTES = int(os.getenv("IMPORTANT_BURST_MINUTES", "5"))


class ResultRejected(RuntimeError):
    """Upstream answered, but its output failed the gateway's output control."""


def _configure_tracing() -> Any:
    provider = TracerProvider(resource=Resource.create({"service.name": os.getenv("OTEL_SERVICE_NAME", "mcp-security-gateway")}))
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4318").rstrip("/") + "/v1/traces"
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    try:
        trace.set_tracer_provider(provider)
    except Exception:
        pass
    return trace.get_tracer("mcp-governance.gateway")


tracer = _configure_tracing()


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def effect_count() -> int:
    if not EFFECT_LOG.exists():
        return 0
    with EFFECT_LOG.open(encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def _tool_view(tool: Any) -> dict:
    return {
        "name": tool.name,
        "description": tool.description or "",
        "input_schema": tool.input_schema,
    }


@asynccontextmanager
async def _client(server_id: str):
    if server_id == "github":
        if not GITHUB_TOKEN:
            raise RuntimeError("GitHub token is not configured")
        headers = {"Authorization": "Bearer " + GITHUB_TOKEN, "X-MCP-Tools": "get_file_contents", "X-MCP-Readonly": "true"}
        async with httpx2.AsyncClient(headers=headers, timeout=20, trust_env=False) as http_client:
            async with Client(streamable_http_client(GITHUB_MCP_URL, http_client=http_client)) as client:
                yield client
        return
    if server_id == "mock-http":
        client_source: Any = HTTP_MCP_URL
    elif server_id == "mock-stdio":
        client_source = StdioServerParameters(
            command=TIME_MCP_PYTHON,
            args=["-m", "mcp_server_time"],
        )
    else:
        raise RuntimeError(f"discovery is disabled for {server_id}")

    async with Client(client_source) as client:
        yield client


async def _discover(server_id: str) -> dict:
    async with _client(server_id) as client:
        listed = await client.list_tools()
        info = client.server_info
        return {
            "version": info.version if info else "unknown",
            "protocol_version": str(client.protocol_version),
            "tools": [_tool_view(tool) for tool in listed.tools],
        }


async def refresh_catalog(server_id: str) -> dict:
    server = await db.fetch_one("SELECT * FROM mcp_servers WHERE id=%s", (server_id,))
    if not server:
        raise RuntimeError(f"unregistered server: {server_id}")
    if server["status"] == "DISABLED":
        return {"server_id": server_id, "status": "DISABLED", "reason": server["status_reason"]}

    discovered = await _discover(server_id)
    observed = {tool["name"]: tool for tool in discovered["tools"]}
    registered_rows = await db.fetch_all("SELECT * FROM mcp_tools WHERE server_id=%s ORDER BY name", (server_id,))
    registered = {row["name"]: row for row in registered_rows}

    for name, tool in observed.items():
        if name not in registered:
            continue
        description_hash = canonical_hash(tool["description"])
        schema_hash = canonical_hash(tool["input_schema"])
        await db.execute(
            """UPDATE mcp_tools SET observed_description_hash=%s, observed_schema_hash=%s,
               observed_server_version=%s, observed_at=now() WHERE server_id=%s AND name=%s""",
            (description_hash, schema_hash, discovered["version"], server_id, name),
        )
    registered_rows = await db.fetch_all("SELECT * FROM mcp_tools WHERE server_id=%s ORDER BY name", (server_id,))
    registered = {row["name"]: row for row in registered_rows}
    names_match = set(observed) == set(registered)
    metadata_safe = all(not UNSAFE_METADATA.search(tool["description"]) for tool in observed.values())
    findings: list[dict] = []
    if not names_match:
        findings.append({
            "type": "tool-set-drift",
            "added": sorted(set(observed) - set(registered)),
            "missing": sorted(set(registered) - set(observed)),
        })
    if not metadata_safe:
        findings.append({"type": "unsafe-description", "tools": [name for name, tool in observed.items() if UNSAFE_METADATA.search(tool["description"])]})

    hashes_match = True
    for name in set(observed) & set(registered):
        row = registered[name]
        tool = observed[name]
        mismatches = []
        if row["approved_description_hash"] != canonical_hash(tool["description"]):
            mismatches.append("description")
        if row["approved_schema_hash"] != canonical_hash(tool["input_schema"]):
            mismatches.append("schema")
        if row["approved_server_version"] != discovered["version"]:
            mismatches.append("version")
        if mismatches:
            hashes_match = False
            findings.append({"type": "contract-drift", "tool": name, "fields": mismatches})

    exact_match = names_match and metadata_safe and hashes_match
    catalog_hash = canonical_hash(discovered["tools"])
    previous = await db.fetch_one(
        "SELECT catalog_hash, exact_match FROM catalog_snapshots WHERE server_id=%s ORDER BY id DESC LIMIT 1",
        (server_id,),
    )
    # The snapshot table is change evidence, not a call counter: the catalog is
    # re-read before every call, so writing a row per call grows it without adding
    # anything a reviewer can read.
    if not previous or previous["catalog_hash"] != catalog_hash or previous["exact_match"] != exact_match:
        await db.fetch_one(
            """INSERT INTO catalog_snapshots(server_id, server_version, catalog_hash, tool_count, exact_match, findings)
               VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
            (server_id, discovered["version"], catalog_hash, len(observed), exact_match, Jsonb(findings)),
        )
    await db.execute(
        "UPDATE mcp_servers SET status=%s, status_reason=%s, last_seen_at=now() WHERE id=%s",
        (
            "READY" if exact_match else "DRIFT",
            "승인 계약과 일치" if exact_match else "도구 계약 변화가 탐지됨",
            server_id,
        ),
    )
    return {
        "server_id": server_id,
        "status": "READY" if exact_match else "DRIFT",
        "protocol_version": discovered["protocol_version"],
        "version": discovered["version"],
        "tool_count": len(observed),
        "findings": findings,
    }


async def bootstrap() -> None:
    await db.wait_until_ready()
    await db.execute((Path(__file__).parent / "agent_tables.sql").read_text())
    if POLICY_PATH.exists():
        digest = hashlib.sha256(POLICY_PATH.read_bytes()).hexdigest()
        await db.execute("UPDATE policy_versions SET status='SUPERSEDED' WHERE status='ACTIVE' AND source_sha256<>%s", (digest,))
        await db.execute(
            """INSERT INTO policy_versions(id, source_path, source_sha256, status)
               VALUES (%s,%s,%s,'ACTIVE') ON CONFLICT (id) DO UPDATE SET status='ACTIVE'""",
            (f"rego-{digest[:12]}", str(POLICY_PATH), digest),
        )

    for server_id in ("mock-http", "mock-stdio"):
        for attempt in range(20):
            try:
                await refresh_catalog(server_id)
                break
            except Exception as exc:
                if attempt == 19:
                    await db.execute(
                        "UPDATE mcp_servers SET status='ERROR', status_reason=%s WHERE id=%s",
                        (str(exc)[:240], server_id),
                    )
                await asyncio.sleep(1)


async def _contract(server_id: str, tool_name: str) -> dict:
    server = await db.fetch_one("SELECT * FROM mcp_servers WHERE id=%s", (server_id,))
    tool = await db.fetch_one(
        "SELECT * FROM mcp_tools WHERE server_id=%s AND name=%s", (server_id, tool_name)
    )
    if not server or not tool:
        return {
            "registered": False,
            "enabled": False,
            "schema_hash_match": False,
            "description_hash_match": False,
            "version_match": False,
            "known_tools_only": False,
            "metadata_safe": False,
            "supplier_approved": False,
            "critical_vulnerabilities": 0,
        }

    latest = await db.fetch_one(
        "SELECT * FROM catalog_snapshots WHERE server_id=%s ORDER BY id DESC LIMIT 1", (server_id,)
    )
    critical = await db.fetch_one(
        """SELECT COALESCE(sum(critical_count),0) AS critical_count FROM
           (SELECT DISTINCT ON (scanner) critical_count FROM supply_chain_reports
            WHERE source_ref=%s ORDER BY scanner,id DESC) latest_per_scanner""",
        (server["source_ref"],),
    )
    return {
        "registered": True,
        "enabled": bool(tool["enabled"] and server["status"] != "DISABLED"),
        "schema_hash_match": bool(tool["approved_schema_hash"] and tool["approved_schema_hash"] == tool["observed_schema_hash"]),
        "description_hash_match": bool(tool["approved_description_hash"] and tool["approved_description_hash"] == tool["observed_description_hash"]),
        "version_match": bool(tool["approved_server_version"] and tool["approved_server_version"] == tool["observed_server_version"]),
        "known_tools_only": bool(latest and latest["exact_match"]),
        "metadata_safe": not bool(latest and any(item.get("type") == "unsafe-description" for item in latest["findings"])),
        "supplier_approved": server["status"] != "BLOCKED_SUPPLY_CHAIN",
        "critical_vulnerabilities": int(critical["critical_count"]) if critical else 0,
    }


async def enforcement_mode() -> str:
    """'enforce' applies decisions; 'monitor' records what enforcement would have done.

    Stored in the database rather than the environment so an operator can turn
    enforcement on without a restart - and so the switch itself is auditable.
    """
    row = await db.fetch_one("SELECT value FROM gateway_settings WHERE key='enforcement'")
    value = row["value"] if row else DEFAULT_ENFORCEMENT
    return value if value in {"enforce", "monitor"} else "enforce"


async def set_enforcement_mode(mode: str, actor: str) -> dict:
    if mode not in {"enforce", "monitor"}:
        raise ValueError("enforce 또는 monitor만 사용할 수 있습니다.")
    await db.execute(
        """INSERT INTO gateway_settings(key, value, updated_by) VALUES ('enforcement',%s,%s)
           ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_by=EXCLUDED.updated_by, updated_at=now()""",
        (mode, actor),
    )
    return {"enforcement": mode, "updated_by": actor}


async def monitor_summary(hours: int = 168) -> dict:
    """What enforcement would have stopped, so a team can turn it on with numbers."""
    rows = await db.fetch_all(
        """SELECT would_decision, would_policy_id, role, tool_name, data_class, count(*) AS calls
           FROM decisions
           WHERE would_decision IS NOT NULL AND created_at > now() - make_interval(hours => %s)
           GROUP BY 1,2,3,4,5 ORDER BY calls DESC LIMIT 50""",
        (hours,),
    )
    users = await db.fetch_one(
        """SELECT count(DISTINCT user_token) AS affected FROM decisions
           WHERE would_decision IS NOT NULL AND created_at > now() - make_interval(hours => %s)""",
        (hours,),
    )
    return {
        "enforcement": await enforcement_mode(),
        "window_hours": hours,
        "would_have_stopped": sum(int(row["calls"]) for row in rows),
        "affected_principals": int(users["affected"]) if users else 0,
        "breakdown": rows,
    }


async def _recent_activity(user_token: str) -> dict:
    """Both volume signals in one query.

    Counted from the audit table rather than from in-process state, so the ceilings
    still hold when more than one gateway replica is serving. Blocked calls count
    too: a flood of denied calls is still a flood.

    The gateway measures and the policy decides, so the limits travel as part of the
    input rather than as a branch in this function.
    """
    row = await db.fetch_one(
        """SELECT count(*) FILTER (WHERE created_at > now() - make_interval(secs => %s)) AS recent_calls,
                  count(*) FILTER (WHERE data_class = 'important'
                                     AND created_at > now() - make_interval(mins => %s)) AS recent_important
           FROM decisions WHERE user_token = %s AND created_at > now() - interval '1 hour'""",
        (RATE_LIMIT_WINDOW_SECONDS, IMPORTANT_BURST_MINUTES, user_token),
    )
    return {
        "recent_calls": int(row["recent_calls"]) if row else 0,
        "call_limit": RATE_LIMIT_CALLS,
        "recent_important": int(row["recent_important"]) if row else 0,
        "important_limit": IMPORTANT_BURST_LIMIT,
    }


async def _policy(input_document: dict) -> dict:
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.post(OPA_URL, json={"input": input_document})
        response.raise_for_status()
        result = response.json().get("result")
        if not isinstance(result, dict) or "decision" not in result:
            raise RuntimeError("OPA returned no decision")
        return result


async def _call_upstream(spec: dict, arguments: dict) -> dict:
    async with _client(spec["server_id"]) as client:
        # Recheck the approved contract on the SAME connection that will execute.
        listed = await client.list_tools()
        registered = await db.fetch_all("SELECT * FROM mcp_tools WHERE server_id=%s", (spec["server_id"],))
        observed = {t.name: _tool_view(t) for t in listed.tools}
        if set(observed) != {t["name"] for t in registered}:
            raise RuntimeError("MCP catalog changed before execution")
        for row in registered:
            tool = observed[row["name"]]
            if (canonical_hash(tool["description"]) != row["approved_description_hash"]
                    or canonical_hash(tool["input_schema"]) != row["approved_schema_hash"]
                    or client.server_info.version != row["approved_server_version"]):
                raise RuntimeError("MCP contract changed before execution")
        Draft202012Validator(observed[spec["registry_name"]]["input_schema"]).validate(arguments)
        result = await client.call_tool(spec["registry_name"], arguments)
        if result.is_error:
            messages = [getattr(item, "text", str(item)) for item in result.content]
            raise RuntimeError("; ".join(messages))
        if result.structured_content is not None:
            return _guarded_result(result.structured_content)
        return _guarded_result({"content": [getattr(item, "text", str(item)) for item in result.content]})


def _guarded_result(payload: dict) -> dict:
    """Upstream output is untrusted input too.

    A pinned description and schema say nothing about what a server returns at
    runtime, and that is where an injected instruction or an oversized blob arrives.
    """
    body = json.dumps(payload, ensure_ascii=False)
    if len(body.encode()) > MAX_RESULT_BYTES:
        raise ResultRejected(f"도구 결과가 {MAX_RESULT_BYTES} byte 상한을 넘었습니다.")
    if UNSAFE_METADATA.search(body):
        raise ResultRejected("도구 결과에 정책 우회 지시 패턴이 포함되어 있습니다.")
    return payload


def _upstream_arguments(tool_name: str, payload: dict, restrictions: dict) -> dict:
    if tool_name == "read_document":
        return {"document_id": payload["document_id"]}
    if tool_name == "write_document":
        return {"document_id": payload["document_id"], "content": payload.get("content", "")}
    if tool_name == "send_external":
        content = payload.get("content", "")
        if restrictions.get("max_chars"):
            content = content[: int(restrictions["max_chars"])]
        return {
            "document_id": payload["document_id"],
            "destination": restrictions.get("destination", payload.get("destination", "")),
            "content": content,
        }
    if tool_name == "get_current_time":
        return {"timezone": payload.get("timezone", "Asia/Seoul")}
    if tool_name == "github_get_file":
        return {key: payload[key] for key in ("owner", "repo", "path") if key in payload}
    return {}


def _audit_payload(payload: dict) -> dict:
    """Structural evidence stays readable; the document body becomes a digest."""
    if "content" not in payload:
        return payload
    content = str(payload.get("content") or "")
    return {**{k: v for k, v in payload.items() if k != "content"},
            "content_sha256": canonical_hash(content), "content_chars": len(content)}


def _audit_result(result: Any) -> dict:
    """Enough to prove what came back and to compare it later, not a copy of it."""
    body = json.dumps(result, ensure_ascii=False)
    return {"sha256": canonical_hash(result), "chars": len(body), "head": body[:200]}


AUDIT_COLUMN_SETS = {
    1: (
        "request_id", "trace_id", "user_token", "role", "tool_name", "data_class", "action",
        "decision", "policy_id", "reason", "upstream_executed", "restrictions", "approval_id",
        "request_payload", "result_preview", "error",
    ),
    2: (
        "request_id", "trace_id", "user_token", "role", "tool_name", "data_class", "action",
        "decision", "policy_id", "reason", "upstream_executed", "restrictions", "approval_id",
        "request_payload", "result_preview", "error",
        "enforcement", "would_decision", "would_policy_id",
    ),
}
CHAIN_VERSION = 2
AUDIT_COLUMNS = AUDIT_COLUMN_SETS[CHAIN_VERSION]
GENESIS = "0" * 64


def _audit_fingerprint(record: dict, version: int = CHAIN_VERSION) -> str:
    """One canonical form for both the append and the later verification.

    Values are normalised to str / bool / None / JSON documents so that the hash of a
    row read back from PostgreSQL matches the hash computed when it was written.
    """
    normalised = {}
    for column in AUDIT_COLUMN_SETS[version]:
        value = record.get(column)
        if column == "upstream_executed":
            normalised[column] = bool(value)
        elif isinstance(value, (dict, list)) or value is None:
            normalised[column] = value
        else:
            normalised[column] = str(value)
    return canonical_hash(normalised)


# The chain is appended under a row lock, so decision writes serialise on one row.
# That is the right trade for a single gateway; a multi-replica deployment wants one
# chain per instance, anchored together.
async def _record_decision(event: dict) -> int:
    record = {
        "request_id": event["request_id"], "trace_id": event["trace_id"],
        "user_token": event["user_token"], "role": event["role"],
        "tool_name": event["tool_name"], "data_class": event["data_class"],
        "action": event["action"], "decision": event["decision"],
        "policy_id": event["policy_id"], "reason": event["reason"],
        "upstream_executed": bool(event["upstream_executed"]),
        "restrictions": event.get("restrictions") or {},
        "approval_id": event.get("approval_id"),
        "request_payload": _audit_payload(event.get("request_payload") or {}),
        "result_preview": _audit_result(event["result"]) if event.get("result") is not None else None,
        "error": event.get("error"),
        "enforcement": event.get("enforcement") or "enforce",
        "would_decision": event.get("would_decision"),
        "would_policy_id": event.get("would_policy_id"),
    }
    async with db.transaction() as connection:
        cursor = await connection.execute("SELECT head_sha256 FROM audit_chain WHERE id=1 FOR UPDATE")
        head = await cursor.fetchone()
        previous = head["head_sha256"] if head else GENESIS
        entry = hashlib.sha256((previous + _audit_fingerprint(record)).encode()).hexdigest()
        cursor = await connection.execute(
            """INSERT INTO decisions(
                 request_id, trace_id, user_token, role, tool_name, data_class, action,
                 decision, policy_id, reason, upstream_executed, restrictions,
                 approval_id, request_payload, result_preview, error,
                 enforcement, would_decision, would_policy_id,
                 prev_sha256, entry_sha256, chain_version)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING id""",
            (
                record["request_id"], record["trace_id"], record["user_token"], record["role"],
                record["tool_name"], record["data_class"], record["action"], record["decision"],
                record["policy_id"], record["reason"], record["upstream_executed"],
                Jsonb(record["restrictions"]), record["approval_id"],
                Jsonb(record["request_payload"]),
                Jsonb(record["result_preview"]) if record["result_preview"] is not None else None,
                record["error"], record["enforcement"], record["would_decision"],
                record["would_policy_id"], previous, entry, CHAIN_VERSION,
            ),
        )
        row = await cursor.fetchone()
        await connection.execute(
            "UPDATE audit_chain SET head_sha256=%s, entries=entries+1, updated_at=now() WHERE id=1",
            (entry,),
        )
    return int(row["id"])


async def verify_audit_chain() -> dict:
    """Walk the chain and name the first row that does not follow from the previous.

    An edited or deleted row cannot be made to fit again without rewriting every row
    after it, so this answers "was the audit log tampered with" with a row id rather
    than with an assurance.
    """
    rows = await db.fetch_all(
        "SELECT id, " + ", ".join(AUDIT_COLUMNS) + ", prev_sha256, entry_sha256, chain_version"
        " FROM decisions ORDER BY id"
    )
    previous = GENESIS
    chained = 0
    for row in rows:
        if row["entry_sha256"] is None:
            # Written before the chain existed. It anchors nothing and claims nothing.
            continue
        version = int(row["chain_version"] or 1)
        if version not in AUDIT_COLUMN_SETS:
            return {"intact": False, "checked": chained, "broken_at": row["id"],
                    "reason": f"알 수 없는 체인 버전 {version}입니다."}
        expected = hashlib.sha256((previous + _audit_fingerprint(row, version)).encode()).hexdigest()
        if row["prev_sha256"] != previous:
            return {"intact": False, "checked": chained, "broken_at": row["id"],
                    "reason": "이전 항목과 연결되지 않습니다. 앞의 행이 지워졌을 수 있습니다."}
        if row["entry_sha256"] != expected:
            return {"intact": False, "checked": chained, "broken_at": row["id"],
                    "reason": "항목 내용이 기록된 해시와 다릅니다."}
        previous = row["entry_sha256"]
        chained += 1
    head = await db.fetch_one("SELECT head_sha256, entries FROM audit_chain WHERE id=1")
    if head and head["head_sha256"] != previous:
        return {"intact": False, "checked": chained, "broken_at": None,
                "reason": "마지막 항목이 체인 head와 다릅니다. 끝부분이 잘렸을 수 있습니다."}
    return {"intact": True, "checked": chained, "head": previous,
            "entries_recorded": int(head["entries"]) if head else None}


async def execute_call(payload: dict, approval_granted: bool = False, approval_id: str | None = None) -> dict:
    request_id = str(payload.get("_agent_context", {}).get("request_id") or uuid.uuid4())
    before = effect_count()
    with tracer.start_as_current_span("mcp.gateway.call") as span:
        trace_id = f"{span.get_span_context().trace_id:032x}"
        tool_name = str(payload.get("tool_name", "unknown"))
        spec = TOOL_SPECS.get(tool_name, {"server_id": "mock-http", "registry_name": tool_name, "action": "x"})
        principal = await db.fetch_one("SELECT * FROM principals WHERE token=%s", (payload.get("user_token", ""),))
        document = None
        if tool_name == "get_current_time":
            data_class = "public"
        elif tool_name == "github_get_file":
            # An external repository is important unless an operator classifies it otherwise.
            data_class = "important"
        else:
            document = await db.fetch_one("SELECT * FROM documents WHERE id=%s", (payload.get("document_id", ""),))
            data_class = document["data_class"] if document else "important"
        role = principal["role"] if principal else "unknown"
        span.set_attribute("mcp.tool", tool_name)
        span.set_attribute("mcp.role", role)
        span.set_attribute("mcp.data_class", data_class)

        base_event = {
            "request_id": request_id,
            "trace_id": trace_id,
            "user_token": str(payload.get("user_token", "unknown")),
            "role": role,
            "tool_name": tool_name,
            "data_class": data_class,
            "action": spec["action"],
            "upstream_executed": False,
            "enforcement": "enforce",
            "would_decision": None,
            "would_policy_id": None,
            "approval_id": approval_id,
            "request_payload": payload,
            "result": None,
            "error": None,
        }

        if not principal or (spec["server_id"] == "mock-http" and not document):
            base_event.update({
                "decision": "Block",
                "policy_id": "P-INPUT-001",
                "reason": "합성 사용자 토큰 또는 문서 ID가 유효하지 않습니다.",
                "restrictions": {},
            })
            decision_id = await _record_decision(base_event)
            return {**base_event, "decision_id": decision_id, "effect_before": before, "effect_after": effect_count()}

        from .agent_contract import SCHEMAS
        if tool_name in SCHEMAS:
            try:
                Draft202012Validator(SCHEMAS[tool_name]).validate(_upstream_arguments(tool_name, payload, {}))
            except Exception:
                base_event.update(decision="Block", policy_id="P-INPUT-SCHEMA-001", reason="도구 인자가 승인된 입력 형식과 다릅니다.", restrictions={})
                decision_id = await _record_decision(base_event)
                return {**base_event, "decision_id": decision_id, "effect_before": before, "effect_after": effect_count()}

        if tool_name == "github_get_file":
            allowed_repos = {item.strip().lower() for item in os.getenv("GITHUB_ALLOWED_REPOS", "MCP-governance/mcp-gateway").split(",") if item.strip()}
            if f"{payload.get('owner', '')}/{payload.get('repo', '')}".lower() not in allowed_repos:
                base_event.update(decision="Block", policy_id="MCP-REPOSITORY-001", reason="허용 목록에 없는 GitHub 저장소입니다.", restrictions={})
                decision_id = await _record_decision(base_event)
                return {**base_event, "decision_id": decision_id, "effect_before": before, "effect_after": effect_count()}

        catalog_fresh = True
        if spec["server_id"] != "github" or GITHUB_TOKEN:
            try:
                await refresh_catalog(spec["server_id"])
            except Exception as exc:
                span.record_exception(exc)
                catalog_fresh = False

        contract = await _contract(spec["server_id"], spec["registry_name"])
        if not catalog_fresh:
            contract["known_tools_only"] = False
        policy_input = {
            "principal": {"role": role, "synthetic": bool(principal["synthetic"])},
            "resource": {"id": payload.get("document_id", "time"), "data_class": data_class},
            "tool": {"name": spec["registry_name"], "action": spec["action"]},
            "approval": {"granted": approval_granted, "id": approval_id},
            "contract": contract,
            "context": await _recent_activity(str(payload.get("user_token", ""))),
        }
        try:
            result = await _policy(policy_input)
        except Exception as exc:
            result = {
                "decision": "Block",
                "policy_id": "P-CONTROL-FAIL-CLOSED",
                "reason": "OPA 정책 결정에 실패하여 기본 차단했습니다.",
                "restrictions": {},
            }
            base_event["error"] = str(exc)[:500]

        mode = await enforcement_mode()
        base_event["enforcement"] = mode
        if (mode == "monitor" and result["decision"] != "Allow"
                and not result["policy_id"].startswith(ALWAYS_ENFORCED)):
            base_event["would_decision"] = result["decision"]
            base_event["would_policy_id"] = result["policy_id"]
            span.set_attribute("mcp.would_decision", result["decision"])
            result = {
                "decision": "Allow",
                "policy_id": "P-MONITOR-001",
                "reason": f"관찰 모드입니다. 집행 모드였다면 {base_event['would_decision']}"
                          f"({base_event['would_policy_id']})로 처리됐습니다.",
                "restrictions": {},
            }
        base_event.update(result)
        span.set_attribute("mcp.enforcement", mode)
        span.set_attribute("mcp.decision", result["decision"])
        span.set_attribute("mcp.policy_id", result["policy_id"])

        if result["decision"] == "Approval":
            new_approval_id = str(uuid.uuid4())
            fingerprint = canonical_hash(payload)
            await db.execute(
                """INSERT INTO approvals(id, request_fingerprint, request_payload, status, requested_by, expires_at)
                   VALUES (%s,%s,%s,'PENDING',%s,%s)""",
                (
                    new_approval_id, fingerprint, Jsonb(payload), payload["user_token"],
                    datetime.now(UTC) + timedelta(minutes=APPROVAL_TTL_MINUTES),
                ),
            )
            base_event["approval_id"] = new_approval_id
        elif result["decision"] in {"Allow", "Alert", "Restrict"}:
            effective = _upstream_arguments(tool_name, payload, result.get("restrictions") or {})
            base_event["upstream_attempted"] = True
            try:
                with tracer.start_as_current_span("mcp.upstream.call") as upstream_span:
                    upstream_span.set_attribute("mcp.server", spec["server_id"])
                    upstream_span.set_attribute("mcp.transport", "stdio" if spec["server_id"] == "mock-stdio" else "streamable-http")
                    base_event["result"] = await _call_upstream(spec, effective)
                base_event["upstream_executed"] = True
                base_event["effective_arguments"] = effective
            except ResultRejected as exc:
                # The call did run upstream; only the answer is withheld. Recording it
                # as "not executed" would make the effect log and the audit disagree.
                base_event.update({
                    "decision": "Block",
                    "policy_id": "MCP-OUTPUT-001",
                    "reason": "upstream 결과가 출력 통제에 걸려 반환하지 않았습니다. 호출 자체는 실행됐습니다.",
                    "upstream_executed": True,
                    "result": None,
                    "error": str(exc)[:500],
                })
                span.record_exception(exc)
            except Exception as exc:
                base_event.update({
                    "decision": "Block",
                    "policy_id": "MCP-UPSTREAM-001",
                    "reason": "허용 후 MCP 통신이 실패했습니다. 실제 실행 여부는 독립 증적을 확인하세요.",
                    "error": str(exc)[:500],
                })
                span.record_exception(exc)

        decision_id = await _record_decision(base_event)
        after = effect_count()
        return {**base_event, "decision_id": decision_id, "effect_before": before, "effect_after": after}


async def approve_request(approval_id: str, reviewer_token: str) -> dict:
    reviewer = await db.fetch_one("SELECT * FROM principals WHERE token=%s", (reviewer_token,))
    if not reviewer or reviewer["role"] != "admin":
        raise ValueError("합성 관리자만 승인할 수 있습니다.")
    row = await db.fetch_one("SELECT * FROM approvals WHERE id=%s", (approval_id,))
    if not row or row["status"] != "PENDING":
        raise ValueError("대기 중인 승인 요청이 아닙니다.")
    if row["expires_at"] <= datetime.now(UTC):
        await db.execute("UPDATE approvals SET status='EXPIRED' WHERE id=%s", (approval_id,))
        raise ValueError("승인 요청의 10분 유효시간이 지났습니다.")

    claimed = await db.fetch_one(
        """UPDATE approvals SET status='APPROVED', reviewed_by=%s, reviewed_at=now()
           WHERE id=%s AND status='PENDING' AND expires_at>now() RETURNING *""",
        (reviewer_token, approval_id),
    )
    if not claimed:
        raise ValueError("다른 승인자가 먼저 처리했습니다.")
    payload = claimed["request_payload"]
    if canonical_hash(payload) != claimed["request_fingerprint"]:
        await db.execute("UPDATE approvals SET status='REJECTED' WHERE id=%s", (approval_id,))
        raise ValueError("승인 요청 내용의 무결성 검증에 실패했습니다.")

    result = await execute_call(payload, approval_granted=True, approval_id=approval_id)
    final_status = "EXECUTED" if result["upstream_executed"] else "REJECTED"
    await db.execute(
        "UPDATE approvals SET status=%s, executed_decision_id=%s WHERE id=%s",
        (final_status, result["decision_id"], approval_id),
    )
    return result


async def import_supply_chain_reports() -> list[dict]:
    imported: list[dict] = []
    sbom = REPORT_DIR / "sbom.cdx.json"
    if sbom.exists():
        data = json.loads(sbom.read_text(encoding="utf-8"))
        summary = {"components": len(data.get("components", [])), "format": data.get("bomFormat")}
        await db.execute("DELETE FROM supply_chain_reports WHERE scanner='Syft' AND report_path=%s", (str(sbom),))
        await db.execute(
            """INSERT INTO supply_chain_reports(scanner, scanner_version, source_ref, report_path, status, summary)
               VALUES ('Syft','1.51.1','workspace',%s,'IMPORTED',%s)""",
            (str(sbom), Jsonb(summary)),
        )
        imported.append({"scanner": "Syft", **summary})

    trivy = REPORT_DIR / "trivy.json"
    if trivy.exists():
        data = json.loads(trivy.read_text(encoding="utf-8"))
        counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0}
        categories = {key: {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0} for key in ("Vulnerabilities", "Misconfigurations", "Secrets")}
        for result in data.get("Results") or []:
            for category in categories:
                for finding in result.get(category) or []:
                    if category == "Misconfigurations" and finding.get("Status") == "PASS":
                        continue
                    severity = finding.get("Severity", "")
                    if severity in counts:
                        counts[severity] += 1
                        categories[category][severity] += 1
        summary = {"targets": len(data.get("Results") or []), "counts": counts, "categories": categories}
        await db.execute("DELETE FROM supply_chain_reports WHERE scanner='Trivy' AND report_path=%s", (str(trivy),))
        await db.execute(
            """INSERT INTO supply_chain_reports(scanner, scanner_version, source_ref, report_path, status,
               critical_count, high_count, medium_count, summary)
               VALUES ('Trivy','0.74.0','workspace',%s,'IMPORTED',%s,%s,%s,%s)""",
            (str(trivy), counts["CRITICAL"], counts["HIGH"], counts["MEDIUM"], Jsonb(summary)),
        )
        imported.append({"scanner": "Trivy", **summary})

    sarif = REPORT_DIR / "mcp-scan.sarif.json"
    if sarif.exists():
        data = json.loads(sarif.read_text(encoding="utf-8"))
        results = [item for run in data.get("runs", []) for item in run.get("results", [])]
        levels = {"error": 0, "warning": 0, "note": 0}
        for item in results:
            level = item.get("level", "warning")
            levels[level] = levels.get(level, 0) + 1
        summary = {"findings": len(results), "levels": levels}
        await db.execute("DELETE FROM supply_chain_reports WHERE scanner='AI-Infra-Guard mcp-scan' AND report_path=%s", (str(sarif),))
        await db.execute(
            """INSERT INTO supply_chain_reports(scanner, scanner_version, source_ref, report_path, status,
               critical_count, high_count, medium_count, summary)
               VALUES ('AI-Infra-Guard mcp-scan','036c39bd03b3','workspace',%s,'IMPORTED',%s,%s,%s,%s)""",
            (str(sarif), levels["error"], levels["warning"], levels["note"], Jsonb(summary)),
        )
        imported.append({"scanner": "AI-Infra-Guard mcp-scan", **summary})
    return imported
