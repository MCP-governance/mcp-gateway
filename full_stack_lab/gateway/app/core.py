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
from urllib.parse import urlsplit

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

from . import db, endpoint_plane, privacy

OPA_URL = os.getenv("OPA_URL", "http://opa:8181/v1/data/mcp/authz/decision")
# 정책 관리대장(§11.8 / §12.5)은 정책 코드와 함께 배포되고 OPA가 그 정본이다.
# Gateway가 별도 사본을 들면 "승인된 정책"이 둘이 된다.
POLICY_LEDGER_URL = os.getenv("POLICY_LEDGER_URL", "http://opa:8181/v1/data/policy_ledger")
GATEWAY_ENVIRONMENT = os.getenv("GATEWAY_ENVIRONMENT", "prod")
HTTP_MCP_URL = os.getenv("HTTP_MCP_URL", "http://mock-http-mcp:9000/mcp/")
GITHUB_MCP_URL = os.getenv("GITHUB_MCP_URL", "https://api.githubcopilot.com/mcp/")
GITHUB_TOKEN = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN", "")
EFFECT_LOG = Path(os.getenv("EFFECT_LOG", "/runtime/upstream-effects.jsonl"))
REPORT_DIR = Path(os.getenv("REPORT_DIR", "/reports"))
POLICY_PATH = Path(os.getenv("POLICY_PATH", "/policy/policy.rego"))
TIME_MCP_PYTHON = os.getenv("TIME_MCP_PYTHON", "/opt/time-mcp/bin/python")
# 승인 계약 기준선을 재현 가능하게 만드는 고정값. 아래 _client() 주석 참고.
STDIO_TIME_TZ = os.getenv("STDIO_TIME_TZ", "UTC")
APPROVAL_TTL_MINUTES = 10

# External names normally match the registered MCP tool. Only this user-facing
# GitHub name differs; r/w/x always comes from mcp_tools, the Registry source of truth.
TOOL_ALIASES = {"github_get_file": ("github", "get_file_contents")}
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
ALWAYS_ENFORCED = ("MCP-", "P-CONTROL-", "P-INPUT-", "P-RATE-", "P-CHAIN-")
RATE_LIMIT_CALLS = int(os.getenv("RATE_LIMIT_CALLS", "60"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
IMPORTANT_BURST_LIMIT = int(os.getenv("IMPORTANT_BURST_LIMIT", "10"))
IMPORTANT_BURST_MINUTES = int(os.getenv("IMPORTANT_BURST_MINUTES", "5"))
BLOCK_STREAK_LIMIT = int(os.getenv("BLOCK_STREAK_LIMIT", "5"))
BLOCK_STREAK_MINUTES = int(os.getenv("BLOCK_STREAK_MINUTES", "10"))
# CTL-28이 보라는 "반복 실패"는 이 사람이 권한 경계를 더듬고 있다는 신호다.
# 모든 차단을 세면 그 신호가 환경 상태에 묻힌다 - 서버 하나가 드리프트 상태면
# MCP-CATALOG-001이 모든 사용자에게 걸리고, 그러면 아무 잘못 없는 사람들의 다음
# 호출이 전부 경보가 된다. 주체에게 귀속되는 인가 거부만 센다.
DENIAL_POLICIES = ("P-AUTHZ-DENY-001", "MCP-REPOSITORY-001", "MCP-EGRESS-001",
                   "P-CLASSIFICATION-001", "P-APPROVAL-EXPIRY-001")

# OPA is a trust boundary too. Only policy fields may enter the execution event;
# a malformed result must never become Allow through monitor mode.
POLICY_RESULT = Draft202012Validator({
    "type": "object", "additionalProperties": False,
    "required": ["decision", "policy_id", "reason", "restrictions"],
    "properties": {
        "decision": {"enum": ["Allow", "Alert", "Restrict", "Approval", "Block"]},
        "policy_id": {"type": "string", "minLength": 1},
        "reason": {"type": "string", "minLength": 1},
        "restrictions": {
            "type": "object", "additionalProperties": False,
            "properties": {"destination": {"type": "string", "minLength": 1, "maxLength": 200},
                           "max_chars": {"type": "integer", "minimum": 0, "maximum": 2000}},
        },
        **{key: {"type": "string"} for key in (
            "policy_name", "policy_version", "policy_status", "policy_set_version", "environment")},
        **{key: {"type": "array", "items": {"type": "string"}} for key in (
            "risk_ids", "control_ids", "requirement_ids", "obligations")},
        "priority": {"type": ["integer", "null"]},
        "conditions": {"type": "object"},
        "exception": {"type": ["object", "null"], "required": ["id"],
                      "properties": {"id": {"type": "string", "minLength": 1}}},
        "conflicts": {"type": "array", "items": {"type": "object"}},
    },
})


class ResultRejected(RuntimeError):
    """Upstream answered, but its output failed the gateway's output control."""


class DispatchRejected(RuntimeError):
    """The final checks failed before tools/call was sent."""


def _configure_tracing() -> Any:
    # 수집기가 없는 배치(네이티브 실행, 단일 호스트 검증)에서는 매 스팬마다 연결
    # 실패가 쌓여 실제 오류를 덮는다. OTEL 표준 스위치를 그대로 따른다.
    if os.getenv("OTEL_SDK_DISABLED", "").strip().lower() in {"1", "true", "yes"}:
        return trace.get_tracer("mcp-governance.gateway")
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


async def _tool_spec(tool_name: str) -> dict:
    """Resolve action from the approved Registry, not a duplicate Python table."""
    alias = TOOL_ALIASES.get(tool_name)
    if alias:
        row = await db.fetch_one(
            "SELECT server_id,name,action FROM mcp_tools WHERE server_id=%s AND name=%s", alias,
        )
    else:
        rows = await db.fetch_all("SELECT server_id,name,action FROM mcp_tools WHERE name=%s", (tool_name,))
        row = rows[0] if len(rows) == 1 else None
    if not row:
        # Keep unknown requests on the existing fail-closed MCP-REGISTRY path.
        return {"server_id": "mock-http", "registry_name": tool_name, "action": "x"}
    return {"server_id": row["server_id"], "registry_name": row["name"], "action": row["action"]}


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
        # --local-timezone을 고정한다. mcp-server-time은 도구 설명·Schema 안에
        # 호스트의 지역 시간대를 문자열로 박아 넣는다. 고정하지 않으면 같은 버전의
        # 같은 서버가 호스트마다 다른 schema_hash를 내고, MCP-CATALOG-001이 실제
        # 변조가 아니라 "이 컨테이너가 어느 시간대에서 돌았는가"를 탐지하게 된다.
        # 승인 계약의 기준선은 재현 가능해야 한다.
        client_source = StdioServerParameters(
            command=TIME_MCP_PYTHON,
            args=["-m", "mcp_server_time", "--local-timezone", STDIO_TIME_TZ],
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
            # 서버가 initialize에서 스스로 말하는 이름. 망 관측이 손에 넣는 것은
            # 사람이 적은 라벨이 아니라 이 값이라, Registry가 이것을 알고 있어야
            # 등록된 서버가 섀도로 분류되지 않는다.
            "advertised_name": (info.name if info else "") or "",
            "version": info.version if info else "unknown",
            "protocol_version": str(client.protocol_version),
            "tools": [_tool_view(tool) for tool in listed.tools],
        }


async def refresh_catalog(server_id: str) -> dict:
    server = await db.fetch_one("SELECT * FROM mcp_servers WHERE id=%s", (server_id,))
    if not server:
        raise RuntimeError(f"unregistered server: {server_id}")
    if server["status"] in {"DISABLED", "BLOCKED_SUPPLY_CHAIN"}:
        # Catalog discovery proves only that a service answers; it must never undo
        # an operator's supply-chain containment or reconnect to the blocked target.
        return {"server_id": server_id, "status": server["status"], "reason": server["status_reason"]}
    if server["lifecycle"] in {"TERMINATING", "RETIRED"}:
        # 폐기 절차에 들어간 서버에 다시 붙어 catalog를 읽는 것은 종료 조치와
        # 반대 방향의 행동이다. 계약을 갱신할 이유가 없고, 연결 자체가 "아직
        # 연결되어 있다"는 사실을 만든다.
        return {"server_id": server_id, "status": server["status"],
                "lifecycle": server["lifecycle"], "reason": "폐기 절차 중이므로 catalog를 다시 읽지 않습니다."}

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
        """UPDATE mcp_servers SET status=%s, status_reason=%s, last_seen_at=now(),
               advertised_name=%s WHERE id=%s""",
        (
            "READY" if exact_match else "DRIFT",
            "승인 계약과 일치" if exact_match else "도구 계약 변화가 탐지됨",
            discovered.get("advertised_name") or None,
            server_id,
        ),
    )
    # T4. 계약이 바뀌면 심사한 코드와 지금 도는 코드가 갈라졌다는 뜻이므로 AI 코드
    # 감사도 다시 돌아야 한다. v1.5는 scan_jobs.trigger에 'drift' 값만 예약해 두고
    # 이 시각을 남기지 않아서, 워커가 "마지막 감사 이후 드리프트가 있었는가"를
    # 물어볼 수 없었다. 큐잉은 워커가 하고, 여기서는 사실만 기록한다.
    if not exact_match:
        await db.execute(
            "UPDATE mcp_servers SET drift_observed_at=now() WHERE id=%s", (server_id,)
        )
    return {
        "server_id": server_id,
        "status": "READY" if exact_match else "DRIFT",
        "protocol_version": discovered["protocol_version"],
        "version": discovered["version"],
        "tool_count": len(observed),
        "findings": findings,
    }




async def approve_contract(server_id: str, actor: str, note: str) -> dict:
    """관측된 도구 계약을 승인본으로 올린다 (CTL-30 변경 식별과 재평가).

    이 기능이 없던 v1.5까지, 정당한 변경 뒤에 계약을 다시 승인하는 방법은 SQL을
    직접 고치는 것뿐이었다. 그러면 재승인이 기록되지 않고, "누가 언제 무엇을
    승인했는가"가 남지 않는다. 승인 절차가 없는 통제는 우회로 유지된다.

    승인 대상은 **지금 관측된 값**이다. 그래서 호출 순서가 중요하다 - 먼저
    catalog를 다시 읽고, 그 결과를 승인한다. 관리자가 보고 있던 화면의 값이
    아니라 이 순간 서버가 말하는 값을 승인해야, 화면과 실제가 갈라진 사이에
    끼어든 변경이 함께 승인되지 않는다.

    막는 것: 공급망 차단·비활성·폐기 절차 중인 서버는 재승인하지 않는다. 그
    상태들은 "계약이 바뀌었다"가 아니라 "이 서버를 쓰지 않기로 했다"이고,
    되돌리는 절차가 다르다.
    """
    server = await db.fetch_one("SELECT * FROM mcp_servers WHERE id=%s", (server_id,))
    if not server:
        raise ValueError(f"등록되지 않은 서버입니다: {server_id}")
    if server["status"] in {"DISABLED", "BLOCKED_SUPPLY_CHAIN"}:
        raise ValueError("비활성 또는 공급망 차단 상태의 서버는 재승인할 수 없습니다.")
    if (server.get("lifecycle") or "OPERATING") in {"TERMINATING", "RETIRED"}:
        raise ValueError("종료 절차에 들어간 서버는 재승인할 수 없습니다.")

    await refresh_catalog(server_id)
    rows = await db.fetch_all(
        "SELECT * FROM mcp_tools WHERE server_id=%s ORDER BY name", (server_id,))
    changes = []
    for row in rows:
        fields = []
        if row["approved_description_hash"] != row["observed_description_hash"]:
            fields.append("description")
        if row["approved_schema_hash"] != row["observed_schema_hash"]:
            fields.append("schema")
        if row["approved_server_version"] != row["observed_server_version"]:
            fields.append("version")
        if not fields:
            continue
        changes.append({
            "tool": row["name"], "fields": fields,
            "from": {"description": row["approved_description_hash"],
                     "schema": row["approved_schema_hash"],
                     "version": row["approved_server_version"]},
            "to": {"description": row["observed_description_hash"],
                   "schema": row["observed_schema_hash"],
                   "version": row["observed_server_version"]},
        })
    if not changes:
        return {"server_id": server_id, "changed": [], "status": server["status"],
                "note": "승인본과 관측값이 이미 같습니다."}

    await db.execute(
        """UPDATE mcp_tools SET
             approved_description_hash = COALESCE(observed_description_hash, approved_description_hash),
             approved_schema_hash = COALESCE(observed_schema_hash, approved_schema_hash),
             approved_server_version = COALESCE(observed_server_version, approved_server_version)
           WHERE server_id=%s""", (server_id,))
    # 재승인 자체가 기록이다. 무엇을 무엇으로 바꿨는지가 없으면 나중에 "그때
    # 승인한 것이 지금 도는 것과 같은가"에 답할 수 없다.
    await db.execute(
        """INSERT INTO catalog_snapshots(server_id, server_version, catalog_hash, tool_count,
                                         exact_match, findings)
           VALUES (%s,%s,%s,%s,true,%s)""",
        (server_id, rows[0]["observed_server_version"] if rows else None,
         canonical_hash(changes), len(rows),
         Jsonb([{"type": "contract-reapproved", "actor": actor, "note": note,
                 "changes": changes}])),
    )
    # 재대조해서 상태를 READY로 되돌린다. 승인만 하고 status가 DRIFT로 남으면
    # 화면은 여전히 변조를 말하고 정책은 통과시킨다 - 둘 중 하나가 거짓말이다.
    refreshed = await refresh_catalog(server_id)
    return {"server_id": server_id, "changed": changes, "status": refreshed["status"],
            "actor": actor, "note": note}


async def bootstrap() -> None:
    await db.wait_until_ready()
    await db.execute((Path(__file__).parent / "agent_tables.sql").read_text())
    await db.execute((Path(__file__).parent / "lifecycle_tables.sql").read_text())
    await policy_ledger(refresh=True)
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
            "approval_valid_until": None,
            "lifecycle": "UNKNOWN",
        }

    latest = await db.fetch_one(
        "SELECT * FROM catalog_snapshots WHERE server_id=%s ORDER BY id DESC LIMIT 1", (server_id,)
    )
    critical = await db.fetch_one(
        """SELECT COALESCE(sum(critical_count),0) AS critical_count FROM
           (SELECT DISTINCT ON (scanner, COALESCE(summary->>'evidence_mode', 'live'))
                   critical_count FROM supply_chain_reports
            WHERE source_ref=%s
            ORDER BY scanner, COALESCE(summary->>'evidence_mode', 'live'), id DESC) latest_per_scanner""",
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
        # 승인은 영구가 아니다(§11.4.1). 기한은 Registry가 들고, 만료 판단은 정책이 한다.
        "approval_valid_until": tool["approval_valid_until"].isoformat()
        if tool.get("approval_valid_until")
        else None,
        # 전주기의 마지막 단계. status와 따로 두는 이유는 "공급망 문제로 잠깐 막힘"과
        # "이 이용 관계를 끝내는 중"이 되돌리는 절차가 전혀 다르기 때문이다.
        "lifecycle": server.get("lifecycle") or "OPERATING",
        # CTL-24·CTL-25. 등록되어 있다는 사실이 "안전한 경로로 붙는다"를 뜻하지는
        # 않는다. 전송 보호와 목적지 허용 여부는 계약의 일부이지 배포 설정이 아니다.
        "transport_secure": transport_secure(server.get("endpoint")),
        "endpoint_allowed": await egress_allowed(server.get("endpoint")),
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


# CTL-13 / RSK-12. 도구 설명만 검사하면 "설명은 깨끗한데 인자로 들어온 문서 본문에
# 지시가 박혀 있는" 경로가 그대로 남는다. 간접 프롬프트 인젝션은 대부분 그 경로다.
# 여기서는 세기만 하고 판단은 정책이 한다.
def untrusted_markers(payload: dict) -> list[str]:
    found: list[str] = []
    for key in ("content", "destination", "path", "timezone", "owner", "repo"):
        value = payload.get(key)
        if not isinstance(value, str):
            continue
        for match in UNSAFE_METADATA.findall(value):
            found.append(key)
            break
    return sorted(set(found))


# CTL-24 / RSK-24. 원격 endpoint가 평문이면 요청·응답이 경로 위에서 읽히고 바뀐다.
# 루프백과 컨테이너 내부 망은 이 판단에서 제외한다 - 거기까지 TLS를 요구하면
# 아무도 지키지 않는 규칙이 하나 더 생긴다.
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _endpoint_host(endpoint: str | None) -> str:
    value = (endpoint or "").strip()
    if not value:
        return ""
    if not value.startswith(("http://", "https://")):
        return ""
    return (urlsplit(value).hostname or "").lower()


def _destination_host(destination: str | None) -> str:
    value = (destination or "").strip()
    if not value or any(char.isspace() for char in value):
        return ""
    try:
        if value.startswith(("http://", "https://")):
            parsed = urlsplit(value)
            if parsed.username or parsed.password:
                return ""
            host = parsed.hostname or ""
        elif "@" in value:
            host = value.rsplit("@", 1)[1] if value.count("@") == 1 else ""
        else:
            host = value
    except ValueError:
        return ""
    host = host.lower()
    label = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
    return host if len(host) <= 253 and all(label.fullmatch(part) for part in host.split(".")) else ""


def transport_secure(endpoint: str | None) -> bool:
    value = (endpoint or "").strip().lower()
    if not value.startswith(("http://", "https://")):
        return True  # stdio 등 네트워크를 타지 않는 전송
    if value.startswith("https://"):
        return True
    host = _endpoint_host(value)
    # 도커 내부 서비스 이름과 루프백은 이 호스트 밖으로 나가지 않는다.
    return host in LOCAL_HOSTS or "." not in host


async def egress_allowed(endpoint: str | None) -> bool:
    """CTL-25 / RSK-25. 등록 서버의 목적지가 허용 목록 안인가.

    허용 목록이 비어 있으면 통제가 없는 것이지 전부 허용인 것이 아니다. 그래서
    비어 있을 때는 참을 돌려주고, 그 사실을 관리대장(data.json)이 드러낸다.
    """
    host = _endpoint_host(endpoint)
    if not host:
        return True  # stdio: 네트워크 목적지가 없다
    allowed = await opa_document("egress")
    entries = (allowed or {}).get("allowed_hosts") if isinstance(allowed, dict) else None
    if not entries:
        return True
    for item in entries:
        item = str(item).strip().lower()
        if not item:
            continue
        if item.startswith("*."):
            if host == item[2:] or host.endswith(item[1:]):
                return True
        elif host == item:
            return True
    return False


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
                                     AND created_at > now() - make_interval(mins => %s)) AS recent_important,
                  count(*) FILTER (WHERE decision = 'Block'
                                     AND policy_id = ANY(%s::text[])
                                     AND created_at > now() - make_interval(mins => %s)) AS recent_blocks
           FROM decisions WHERE user_token = %s AND created_at > now() - interval '1 hour'""",
        (RATE_LIMIT_WINDOW_SECONDS, IMPORTANT_BURST_MINUTES,
         list(DENIAL_POLICIES), BLOCK_STREAK_MINUTES, user_token),
    )
    return {
        "recent_calls": int(row["recent_calls"]) if row else 0,
        "call_limit": RATE_LIMIT_CALLS,
        "recent_important": int(row["recent_important"]) if row else 0,
        "important_limit": IMPORTANT_BURST_LIMIT,
        # CTL-28 / RSK-27. 한 건의 인가 거부는 오조작이지만 짧은 시간에 쌓인 거부는
        # 권한 경계를 더듬고 있다는 뜻이다. 막지는 않는다 - 막으면 정상 사용자의
        # 오타가 계정 정지가 된다. 증적을 올리고 사람이 본다.
        "recent_blocks": int(row["recent_blocks"]) if row else 0,
        "block_limit": BLOCK_STREAK_LIMIT,
    }


async def _sequence_flags(payload: dict, tool_name: str) -> list[str]:
    """Only signed Agent sessions can link a sensitive read to a later send."""
    session_id = str(payload.get("_agent_context", {}).get("session_id") or "")
    if tool_name != "send_external" or not session_id:
        return []
    row = await db.fetch_one(
        """SELECT 1 FROM decisions
           WHERE user_token=%s AND request_payload #>> '{_agent_context,session_id}'=%s
             AND tool_name='read_document' AND data_class='important'
             AND upstream_executed=true AND created_at > now() - interval '10 minutes'
           LIMIT 1""",
        (payload["user_token"], session_id),
    )
    return ["sensitive_read_then_send"] if row else []


def _risk_score(data_class: str, action: str, external: bool,
                privacy_types: list[str], sequence_flags: list[str]) -> int:
    return min(100, (30 if data_class == "important" else 10 if data_class == "nonimportant" else 0)
               + (20 if action == "x" else 10 if action == "w" else 0)
               + (15 if external else 0) + (25 if privacy_types else 0)
               + (30 if sequence_flags else 0))


_ledger_cache: dict[str, dict] = {}
OPA_DATA_ROOT = OPA_URL.split("/v1/data/")[0] + "/v1/data"


async def opa_document(name: str) -> Any:
    """읽기 전용 data 문서 조회. 정책이 실제로 들고 있는 값을 화면에 그대로 보인다."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{OPA_DATA_ROOT}/{name}")
            response.raise_for_status()
            return response.json().get("result")
    except (httpx.HTTPError, ValueError):
        return None


async def policy_ledger(refresh: bool = False) -> dict:
    """§12.5 PaC 정책 관리대장. 없으면 판정이 관리정보 없이 나가지만 차단하지는 않는다.

    관리정보를 못 읽은 것과 정책을 못 읽은 것은 다른 사건이다. 후자는 이미
    P-CONTROL-FAIL-CLOSED가 차단하고, 전자까지 차단하면 대시보드 장애가 업무
    중단이 된다.
    """
    if _ledger_cache and not refresh:
        return _ledger_cache
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(POLICY_LEDGER_URL)
            response.raise_for_status()
            entries = response.json().get("result")
    except (httpx.HTTPError, ValueError):
        return _ledger_cache
    if isinstance(entries, dict):
        _ledger_cache.clear()
        _ledger_cache.update(entries)
    return _ledger_cache


def local_verdict(policy_id: str, decision: str, reason: str, **extra: Any) -> dict:
    """Gateway가 직접 내리는 판정도 OPA 판정과 같은 관리정보를 달고 나가야 한다.

    §11.7은 판단 결과에 적용 정책과 정책 버전을 포함하라고 하지, 그 판단을 누가
    내렸는지로 예외를 두지 않는다. PEP가 PDP보다 앞에서 거부한 요청만 증적 형식이
    다르면 감사에서 두 종류의 기록을 대조해야 한다.
    """
    entry = _ledger_cache.get(policy_id, {})
    return {
        "decision": decision,
        "policy_id": policy_id,
        "reason": reason,
        "restrictions": {},
        "policy_name": entry.get("name", ""),
        "policy_version": entry.get("version", "unknown"),
        "policy_status": entry.get("status", "unknown"),
        "priority": entry.get("priority"),
        "risk_ids": entry.get("risk_ids", []),
        "control_ids": entry.get("control_ids", []),
        "requirement_ids": entry.get("requirement_ids", []),
        "obligations": entry.get("obligations", []),
        "exception": None,
        "conflicts": [],
        "environment": GATEWAY_ENVIRONMENT,
        **extra,
    }


async def _policy(input_document: dict) -> dict:
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.post(OPA_URL, json={"input": input_document})
        response.raise_for_status()
        result = response.json().get("result")
        # Do not include an invalid policy response in the audit error verbatim.
        if not POLICY_RESULT.is_valid(result):
            raise RuntimeError("OPA returned an invalid decision contract")
        restrictions = result["restrictions"]
        if ((result["decision"] == "Restrict" or restrictions)
                and (input_document.get("tool", {}).get("name") != "send_external"
                     or set(restrictions) != {"destination", "max_chars"})):
            raise RuntimeError("OPA returned unenforceable restrictions")
        return result


async def _call_upstream(spec: dict, arguments: dict, approval_id: str | None = None) -> dict:
    try:
        async with _client(spec["server_id"]) as client:
            # Recheck the approved contract on the SAME connection that will execute.
            listed = await client.list_tools()
            registered = await db.fetch_all("SELECT * FROM mcp_tools WHERE server_id=%s", (spec["server_id"],))
            observed = {t.name: _tool_view(t) for t in listed.tools}
            if set(observed) != {t["name"] for t in registered}:
                raise DispatchRejected("MCP catalog changed before execution")
            for row in registered:
                tool = observed[row["name"]]
                if (canonical_hash(tool["description"]) != row["approved_description_hash"]
                        or canonical_hash(tool["input_schema"]) != row["approved_schema_hash"]
                        or client.server_info.version != row["approved_server_version"]):
                    raise DispatchRejected("MCP contract changed before execution")
            if not Draft202012Validator(observed[spec["registry_name"]]["input_schema"]).is_valid(arguments):
                raise DispatchRejected("Arguments do not match the approved input schema")
            if approval_id is not None:
                # Discovery may take longer than the remaining approval lifetime.
                approval = await db.fetch_one(
                    "SELECT status, expires_at FROM approvals WHERE id=%s", (approval_id,),
                )
                if (not approval or approval["status"] != "APPROVED"
                        or approval["expires_at"] <= datetime.now(UTC)):
                    raise DispatchRejected("Approval expired or was withdrawn before execution")
            result = await client.call_tool(spec["registry_name"], arguments)
            if result.is_error:
                messages = [getattr(item, "text", str(item)) for item in result.content]
                raise RuntimeError("; ".join(messages))
            if result.structured_content is not None:
                return _guarded_result(result.structured_content)
            return _guarded_result({"content": [getattr(item, "text", str(item)) for item in result.content]})
    except* DispatchRejected as exc:
        # MCP Client task groups wrap exceptions raised inside their context.
        raise DispatchRejected("Pre-execution contract or approval check failed") from exc
    except* ResultRejected as exc:
        raise ResultRejected("Upstream result failed output controls") from exc


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
        if "max_chars" in restrictions:
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
    """Keep structural evidence while excluding body, address and file path values."""
    safe = dict(payload)
    for key in ("content", "destination", "path"):
        if key in safe:
            value = str(safe.pop(key) or "")
            safe[key + "_sha256"] = canonical_hash(value)
            safe[key + "_chars"] = len(value)
    return safe


def _audit_result(result: Any) -> dict:
    """Enough to prove what came back and to compare it later, not a copy of it."""
    body = json.dumps(result, ensure_ascii=False)
    return {"sha256": canonical_hash(result), "chars": len(body)}


def _public_event(event: dict) -> dict:
    safe = {**event, "request_payload": _audit_payload(event.get("request_payload") or {})}
    if "effective_arguments" in safe:
        safe["effective_arguments"] = _audit_payload(safe["effective_arguments"])
    return safe


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
    3: (
        "request_id", "trace_id", "user_token", "role", "tool_name", "data_class", "action",
        "decision", "policy_id", "reason", "upstream_executed", "restrictions", "approval_id",
        "request_payload", "result_preview", "error",
        "enforcement", "would_decision", "would_policy_id",
        # §11.17 정책 판단 및 집행 증적
        "policy_version", "obligations", "exception_id", "conflicts", "environment",
    ),
}
AUDIT_COLUMN_SETS[4] = (*AUDIT_COLUMN_SETS[3], "upstream_attempted")
AUDIT_COLUMN_SETS[5] = (*AUDIT_COLUMN_SETS[4], "policy_input", "risk_score",
                        "privacy_types", "sequence_flags")
CHAIN_VERSION = 5
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
        if column in {"upstream_executed", "upstream_attempted"}:
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
        "upstream_attempted": bool(event.get("upstream_attempted", event["upstream_executed"])),
        "restrictions": event.get("restrictions") or {},
        "approval_id": event.get("approval_id"),
        "request_payload": _audit_payload(event.get("request_payload") or {}),
        "result_preview": _audit_result(event["result"]) if event.get("result") is not None else None,
        "error": event.get("error"),
        "enforcement": event.get("enforcement") or "enforce",
        "would_decision": event.get("would_decision"),
        "would_policy_id": event.get("would_policy_id"),
        "policy_version": event.get("policy_version") or "unknown",
        "obligations": event.get("obligations") or [],
        "exception_id": (event.get("exception") or {}).get("id"),
        "conflicts": event.get("conflicts") or [],
        "environment": event.get("environment") or GATEWAY_ENVIRONMENT,
        "policy_input": event.get("policy_input"),
        "risk_score": int(event.get("risk_score") or 0),
        "privacy_types": event.get("privacy_types") or [],
        "sequence_flags": event.get("sequence_flags") or [],
    }
    async with db.transaction() as connection:
        cursor = await connection.execute("SELECT head_sha256 FROM audit_chain WHERE id=1 FOR UPDATE")
        head = await cursor.fetchone()
        previous = head["head_sha256"] if head else GENESIS
        entry = hashlib.sha256((previous + _audit_fingerprint(record)).encode()).hexdigest()
        values = {**record, "prev_sha256": previous, "entry_sha256": entry,
                  "chain_version": CHAIN_VERSION}
        json_columns = {"restrictions", "request_payload", "result_preview", "obligations",
                        "conflicts", "policy_input", "privacy_types", "sequence_flags"}
        cursor = await connection.execute(
            f"INSERT INTO decisions ({', '.join(values)}) VALUES "
            f"({', '.join(['%s'] * len(values))}) RETURNING id",
            tuple(Jsonb(value) if key in json_columns and value is not None else value
                  for key, value in values.items()),
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
        spec = await _tool_spec(tool_name)
        principal = await db.fetch_one("SELECT * FROM principals WHERE token=%s", (payload.get("user_token", ""),))
        document = None
        classification = {"required": False}
        if tool_name == "get_current_time":
            data_class = "public"
        elif tool_name == "github_get_file":
            # An external repository is important unless an operator classifies it otherwise.
            data_class = "important"
            classification = {"required": True, "source": "github-allowlist", "version": "v1"}
        else:
            document = await db.fetch_one("SELECT * FROM documents WHERE id=%s", (payload.get("document_id", ""),))
            data_class = document["data_class"] if document else "important"
            if document:
                classification = {
                    "required": True,
                    "source": document.get("classification_source"),
                    "version": document.get("classification_version"),
                }
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
            "upstream_attempted": False,
            "enforcement": "enforce",
            "would_decision": None,
            "would_policy_id": None,
            "approval_id": approval_id,
            "request_payload": payload,
            "result": None,
            "error": None,
            "policy_input": None,
            "risk_score": 0,
            "privacy_types": [],
            "sequence_flags": [],
        }

        await policy_ledger()
        if (not principal or principal["status"] != "active"
                or (spec["server_id"] == "mock-http" and not document)):
            base_event.update(local_verdict(
                "P-INPUT-001", "Block", "활성 상태의 등록 계정과 유효한 문서 ID가 필요합니다.",
            ))
            decision_id = await _record_decision(base_event)
            return {**_public_event(base_event), "decision_id": decision_id, "effect_before": before, "effect_after": effect_count()}

        from .agent_contract import SCHEMAS
        if tool_name in SCHEMAS:
            try:
                Draft202012Validator(SCHEMAS[tool_name]).validate(_upstream_arguments(tool_name, payload, {}))
            except Exception:
                base_event.update(local_verdict(
                    "P-INPUT-SCHEMA-001", "Block", "도구 인자가 승인된 입력 형식과 다릅니다.",
                ))
                decision_id = await _record_decision(base_event)
                return {**_public_event(base_event), "decision_id": decision_id, "effect_before": before, "effect_after": effect_count()}

        destination_host = _destination_host(payload.get("destination")) if tool_name == "send_external" else ""
        if tool_name == "send_external" and not destination_host:
            base_event.update(local_verdict(
                "P-INPUT-SCHEMA-001", "Block", "외부 목적지를 도메인으로 해석할 수 없습니다.",
            ))
            decision_id = await _record_decision(base_event)
            return {**_public_event(base_event), "decision_id": decision_id, "effect_before": before, "effect_after": effect_count()}

        try:
            findings = await privacy.analyze(str(payload.get("content") or "")) if tool_name in {"write_document", "send_external"} else []
        except privacy.InspectionUnavailable as exc:
            base_event.update(local_verdict(
                "P-DATA-INSPECTION-001", "Block", "민감정보 검사를 완료하지 못해 실행을 차단했습니다.",
                error=str(exc),
            ))
            decision_id = await _record_decision(base_event)
            return {**_public_event(base_event), "decision_id": decision_id, "effect_before": before, "effect_after": effect_count()}
        privacy_types = sorted({item["entity_type"] for item in findings})
        sequence_flags = await _sequence_flags(payload, tool_name)
        base_event["privacy_types"] = privacy_types
        base_event["sequence_flags"] = sequence_flags
        base_event["risk_score"] = _risk_score(data_class, spec["action"],
                                               tool_name == "send_external", privacy_types, sequence_flags)

        if tool_name == "github_get_file":
            allowed_repos = {item.strip().lower() for item in os.getenv("GITHUB_ALLOWED_REPOS", "MCP-governance/mcp-gateway").split(",") if item.strip()}
            if f"{payload.get('owner', '')}/{payload.get('repo', '')}".lower() not in allowed_repos:
                base_event.update(local_verdict(
                    "MCP-REPOSITORY-001", "Block", "허용 목록에 없는 GitHub 저장소입니다.",
                ))
                decision_id = await _record_decision(base_event)
                return {**_public_event(base_event), "decision_id": decision_id, "effect_before": before, "effect_after": effect_count()}

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
            # §11.6 환경정보와 상황정보. 시각을 정책이 스스로 읽으면 만료 판단이
            # 판단 시점마다 달라지고 시험으로 재현할 수 없다. Gateway가 재고, 정책이 판단한다.
            "environment": GATEWAY_ENVIRONMENT,
            "now": datetime.now(UTC).isoformat(),
            "principal": {"role": role, "synthetic": bool(principal["synthetic"]),
                          "department": principal.get("department"),
                          # 이 사람의 엔드포인트에 게이트웨이를 통과하지 않는 MCP
                          # 설정이 몇 건 보고됐는가. 강제 경로 밖의 경로를 가진
                          # 사람의 호출은 같은 권한이어도 같은 위험이 아니다.
                          "shadow_endpoints": await endpoint_plane.shadow_count_for(
                              str(payload.get("user_token", ""))),
                          # 설정 파일과 다른 증거. 설정에 적지 않고 띄운 서버는
                          # 설정 대조로는 보이지 않고, 망 관측만 답할 수 있다.
                          "shadow_listeners": await endpoint_plane.shadow_listener_count_for(
                              str(payload.get("user_token", ""))),
                          },
            "resource": {"id": payload.get("document_id", "time"), "data_class": data_class,
                         "owner_department": document.get("owner_department") if document else None,
                         "classification": classification},
            "tool": {"name": spec["registry_name"], "action": spec["action"]},
            # 이 호출의 인자 자체가 신뢰할 수 없는 콘텐츠인가. 도구 설명 검사(계약)와
            # 다른 축이라 따로 싣는다 - 같은 서버의 같은 도구라도 인자는 매 호출 다르다.
            "request": {"untrusted_markers": untrusted_markers(payload),
                        "destination_host": destination_host,
                        "pii_types": privacy_types,
                        "sequence_flags": sequence_flags},
            "approval": {"granted": approval_granted, "id": approval_id},
            "contract": contract,
            "context": await _recent_activity(str(payload.get("user_token", ""))),
        }
        base_event["policy_input"] = policy_input
        try:
            result = await _policy(policy_input)
        except Exception as exc:
            result = local_verdict(
                "P-CONTROL-FAIL-CLOSED", "Block", "OPA 정책 결정에 실패하여 기본 차단했습니다.",
            )
            base_event["error"] = str(exc)[:500]

        mode = await enforcement_mode()
        base_event["enforcement"] = mode
        if (mode == "monitor" and result["decision"] != "Allow"
                and not result["policy_id"].startswith(ALWAYS_ENFORCED)):
            base_event["would_decision"] = result["decision"]
            base_event["would_policy_id"] = result["policy_id"]
            span.set_attribute("mcp.would_decision", result["decision"])
            result = local_verdict(
                "P-MONITOR-001", "Allow",
                f"관찰 모드입니다. 집행 모드였다면 {base_event['would_decision']}"
                f"({base_event['would_policy_id']})로 처리됐습니다.",
                conflicts=result.get("conflicts") or [],
            )
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
                    raw_result = await _call_upstream(spec, effective, approval_id)
                base_event["upstream_executed"] = True
                try:
                    base_event["result"], output_types = await privacy.mask_payload(raw_result)
                except privacy.InspectionUnavailable as exc:
                    raise ResultRejected(str(exc)) from exc
                base_event["privacy_types"] = sorted(set(privacy_types) | set(output_types))
                base_event["effective_arguments"] = effective
            except DispatchRejected as exc:
                base_event.update(local_verdict(
                    "P-CONTROL-FAIL-CLOSED", "Block",
                    "실행 직전 계약 또는 승인 재검증에 실패하여 도구 호출을 전달하지 않았습니다.",
                    upstream_attempted=False, error=str(exc),
                ))
                span.record_exception(exc)
            except ResultRejected as exc:
                # The call did run upstream; only the answer is withheld. Recording it
                # as "not executed" would make the effect log and the audit disagree.
                # 이 호출을 통과시킨 제한조건과 예외는 남긴다. 나중에 "무엇을 허용한
                # 판정이 결국 결과를 반환하지 않았는가"를 재구성해야 한다.
                base_event.update(local_verdict(
                    "MCP-OUTPUT-001", "Block",
                    "upstream 결과가 출력 통제에 걸려 반환하지 않았습니다. 호출 자체는 실행됐습니다.",
                    restrictions=base_event.get("restrictions") or {},
                    exception=base_event.get("exception"),
                    upstream_executed=True, result=None, error=str(exc)[:500],
                ))
                span.record_exception(exc)
            except Exception as exc:
                base_event.update(local_verdict(
                    "MCP-UPSTREAM-001", "Block",
                    "허용 후 MCP 통신이 실패했습니다. 실제 실행 여부는 독립 증적을 확인하세요.",
                    restrictions=base_event.get("restrictions") or {},
                    exception=base_event.get("exception"),
                    error=str(exc)[:500],
                ))
                span.record_exception(exc)

        decision_id = await _record_decision(base_event)
        after = effect_count()
        return {**_public_event(base_event), "decision_id": decision_id, "effect_before": before, "effect_after": after}


async def approve_request(approval_id: str, reviewer_token: str) -> dict:
    reviewer = await db.fetch_one("SELECT * FROM principals WHERE token=%s", (reviewer_token,))
    if not reviewer or reviewer["role"] != "admin" or reviewer["status"] != "active":
        raise ValueError("합성 관리자만 승인할 수 있습니다.")
    row = await db.fetch_one("SELECT * FROM approvals WHERE id=%s", (approval_id,))
    if not row or row["status"] != "PENDING":
        raise ValueError("대기 중인 승인 요청이 아닙니다.")
    if row["expires_at"] <= datetime.now(UTC):
        await db.execute("UPDATE approvals SET status='EXPIRED' WHERE id=%s AND status='PENDING'", (approval_id,))
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


def _trivy_summary(data: dict) -> tuple[dict, dict]:
    counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0}
    categories = {key: {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0} for key in ("Vulnerabilities", "Misconfigurations", "Secrets")}
    findings: list[dict] = []
    for result in data.get("Results") or []:
        for category in categories:
            for finding in result.get(category) or []:
                if category == "Misconfigurations" and finding.get("Status") == "PASS":
                    continue
                severity = finding.get("Severity", "")
                if severity in counts:
                    counts[severity] += 1
                    categories[category][severity] += 1
                    if len(findings) < 50:
                        findings.append({
                            "kind": category,
                            "severity": severity,
                            "id": finding.get("VulnerabilityID") or finding.get("ID") or "unclassified",
                            "title": finding.get("Title") or finding.get("RuleID") or "세부 정보 없음",
                            "target": result.get("Target", ""),
                        })
    return {"targets": len(data.get("Results") or []), "counts": counts, "categories": categories, "findings": findings}, counts


async def _store_trivy(report: Path, source_ref: str, summary: dict, counts: dict) -> None:
    await db.execute("DELETE FROM supply_chain_reports WHERE scanner='Trivy' AND report_path=%s", (str(report),))
    await db.execute(
        """INSERT INTO supply_chain_reports(scanner, scanner_version, source_ref, report_path, status,
           critical_count, high_count, medium_count, summary)
           VALUES ('Trivy','0.74.0',%s,%s,'IMPORTED',%s,%s,%s,%s)""",
        (source_ref, str(report), counts["CRITICAL"], counts["HIGH"], counts["MEDIUM"], Jsonb(summary)),
    )


async def supply_chain_coverage() -> list[dict]:
    """Which servers actually have scan output wired to the MCP-SUPPLY-001 gate.

    A dashboard that shows scan numbers without saying whether they gate anything
    invites exactly the wrong conclusion in a review.
    """
    return await db.fetch_all(
        """SELECT s.id AS server_id, s.source_ref, s.scan_path,
                  count(r.id) AS reports,
                  COALESCE(sum(r.critical_count), 0) AS critical_count,
                  max(r.imported_at) AS last_scanned_at
           FROM mcp_servers s
           LEFT JOIN supply_chain_reports r ON r.source_ref = s.source_ref
           GROUP BY s.id, s.source_ref, s.scan_path ORDER BY s.id"""
    )


async def reject_request(approval_id: str, reviewer_token: str, note: str) -> dict:
    """The other half of an approval.

    Without it a reviewer's only options are "approve" or "let it expire", and the
    audit cannot tell a considered refusal apart from someone going to lunch.
    """
    reviewer = await db.fetch_one("SELECT * FROM principals WHERE token=%s", (reviewer_token,))
    if not reviewer or reviewer["role"] != "admin" or reviewer["status"] != "active":
        raise ValueError("합성 관리자만 승인 요청을 처리할 수 있습니다.")
    if not note.strip():
        raise ValueError("거부 사유는 비워둘 수 없습니다.")
    claimed = await db.fetch_one(
        """UPDATE approvals SET status='REJECTED', reviewed_by=%s, reviewed_at=now(), review_note=%s
           WHERE id=%s AND status='PENDING' RETURNING id, requested_by, review_note""",
        (reviewer_token, note.strip(), approval_id),
    )
    if not claimed:
        raise ValueError("대기 중인 승인 요청이 아닙니다.")
    return {"approval_id": approval_id, "status": "REJECTED", "reviewed_by": reviewer_token,
            "review_note": claimed["review_note"], "upstream_executed": False}


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
        summary, counts = _trivy_summary(json.loads(trivy.read_text(encoding="utf-8")))
        await _store_trivy(trivy, "workspace", summary, counts)
        imported.append({"scanner": "Trivy", "source_ref": "workspace", **summary})

    semgrep = REPORT_DIR / "semgrep.json"
    if semgrep.exists():
        data = json.loads(semgrep.read_text(encoding="utf-8"))
        levels = {"ERROR": 0, "WARNING": 0, "INFO": 0}
        findings = []
        for item in data.get("results") or []:
            severity = str(item.get("extra", {}).get("severity", "INFO")).upper()
            severity = severity if severity in levels else "INFO"
            levels[severity] += 1
            if len(findings) < 50:
                findings.append({
                    "rule": item.get("check_id", "unclassified"),
                    "severity": severity,
                    "message": item.get("extra", {}).get("message", "세부 정보 없음"),
                    "path": item.get("path", ""),
                    "line": item.get("start", {}).get("line"),
                })
        summary = {"findings": findings, "total": len(data.get("results") or []), "levels": levels}
        await db.execute("DELETE FROM supply_chain_reports WHERE scanner='Semgrep' AND report_path=%s", (str(semgrep),))
        await db.execute(
            """INSERT INTO supply_chain_reports(scanner, scanner_version, source_ref, report_path, status,
               critical_count, high_count, medium_count, summary)
               VALUES ('Semgrep',%s,'workspace',%s,'IMPORTED',%s,%s,%s,%s)""",
            (str(data.get("version", "1.172.0")), str(semgrep), levels["ERROR"], levels["WARNING"], levels["INFO"], Jsonb(summary)),
        )
        imported.append({"scanner": "Semgrep", **summary})

    # A report named for a server is attributed to that server's pinned source_ref,
    # which is the value _contract() counts criticals against. Without this the
    # dashboard's scan numbers and the MCP-SUPPLY-001 gate never referred to the same
    # thing: one scanned the workspace, the other looked up a server.
    servers = {row["id"]: row["source_ref"] for row in await db.fetch_all("SELECT id, source_ref FROM mcp_servers")}
    for report in sorted(REPORT_DIR.glob("trivy-*.json")):
        server_id = report.stem[len("trivy-"):]
        source_ref = servers.get(server_id)
        if not source_ref:
            imported.append({"scanner": "Trivy", "report": report.name, "status": "SKIPPED",
                             "reason": f"등록되지 않은 서버 {server_id}"})
            continue
        summary, counts = _trivy_summary(json.loads(report.read_text(encoding="utf-8")))
        await _store_trivy(report, source_ref, summary, counts)
        imported.append({"scanner": "Trivy", "server_id": server_id, "source_ref": source_ref, **summary})

    sarif = REPORT_DIR / "mcp-scan.sarif.json"
    if sarif.exists():
        data = json.loads(sarif.read_text(encoding="utf-8"))
        results = [item for run in data.get("runs", []) for item in run.get("results", [])]
        levels = {"error": 0, "warning": 0, "note": 0}
        findings = []
        for item in results:
            level = item.get("level", "warning")
            levels[level] = levels.get(level, 0) + 1
            location = (item.get("locations") or [{}])[0].get("physicalLocation", {})
            if len(findings) < 50:
                findings.append({
                    "rule": item.get("ruleId", "unclassified"),
                    "severity": level,
                    "message": item.get("message", {}).get("text", "세부 정보 없음"),
                    "path": location.get("artifactLocation", {}).get("uri", ""),
                    "line": location.get("region", {}).get("startLine"),
                })
        summary = {"findings": findings, "total": len(results), "levels": levels}
        await db.execute("DELETE FROM supply_chain_reports WHERE scanner='AI-Infra-Guard mcp-scan' AND report_path=%s", (str(sarif),))
        await db.execute(
            """INSERT INTO supply_chain_reports(scanner, scanner_version, source_ref, report_path, status,
               critical_count, high_count, medium_count, summary)
               VALUES ('AI-Infra-Guard mcp-scan','036c39bd03b3','workspace',%s,'IMPORTED',%s,%s,%s,%s)""",
            (str(sarif), levels["error"], levels["warning"], levels["note"], Jsonb(summary)),
        )
        imported.append({"scanner": "AI-Infra-Guard mcp-scan", **summary})
    return imported
