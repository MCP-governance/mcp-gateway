from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

import httpx
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from psycopg.types.json import Jsonb
from jsonschema import Draft202012Validator
from jsonschema.validators import validator_for
from referencing import Registry

from . import classify, connections, consent, db, dispatch, disposal, endpoint_plane, local_jobs, ops_response, pac, poisoning, privacy, registry, retention, risk_tier, secret_scan, supplier_assurance, upstream, user_suspend
from .destination import DestinationBlocked
from .outcomes import outcome_axes
from . import flow_fingerprint, high_impact, output_contract, residency, selective, tool_sunset
from .contract import (  # re-exported: older callers import these from core
    AUDIT_COLUMNS, CHAIN_VERSION, GENESIS, POLICY_RESULT, canonical_hash,
    audit_fingerprint as _audit_fingerprint, walk_chain,
)

from . import intake_proposal, review  # noqa: E402  (approval records, intake gate; see review.py)

OPA_URL = os.getenv("OPA_URL", "http://opa:8181/v1/data/mcp/authz/decision")
# 정책 관리대장(§11.8 / §12.5)은 정책 코드와 함께 배포되고 OPA가 그 정본이다.
# Gateway가 별도 사본을 들면 "승인된 정책"이 둘이 된다.
POLICY_LEDGER_URL = os.getenv("POLICY_LEDGER_URL", "http://opa:8181/v1/data/policy_ledger")
GATEWAY_ENVIRONMENT = os.getenv("GATEWAY_ENVIRONMENT", "prod")
REPORT_DIR = Path(os.getenv("REPORT_DIR", "/reports"))
POLICY_PATH = Path(os.getenv("POLICY_PATH", "/policy/policy.rego"))
# What OPA serves from /policy, including the integrated PAC pack and its decision contract.
POLICY_BUNDLE = ("policy.rego", "pac15.rego", "decision.rego", "data.json", "policy_ledger.json", "residency.json")
APPROVAL_TTL_MINUTES = 10
CATALOG_REFRESH_SECONDS = int(os.getenv("CATALOG_REFRESH_SECONDS", "60"))
# A server check only negotiates a session; a slow answer is itself the finding.
SERVER_CHECK_TIMEOUT_SECONDS = float(os.getenv("SERVER_CHECK_TIMEOUT_SECONDS", "5"))

# Instruction-shaped text aimed at the model lives in one ruleset (app/poisoning.py),
# which every door uses: contracts at registration and catalog refresh, arguments on
# the way out, results on the way back. The gateway used to keep a shorter pattern of
# its own here, so the weakest check ran on the least trusted content.
MAX_RESULT_BYTES = int(os.getenv("MAX_RESULT_BYTES", "262144"))
MAX_RESULT_ITEMS = int(os.getenv("MAX_RESULT_ITEMS", "1000"))
if MAX_RESULT_BYTES <= 0 or MAX_RESULT_ITEMS <= 0:
    raise ValueError("Result limits must be positive")
OUTPUT_INSPECTION_TIMEOUT_SECONDS = float(os.getenv("OUTPUT_INSPECTION_TIMEOUT_SECONDS", "30"))
if not math.isfinite(OUTPUT_INSPECTION_TIMEOUT_SECONDS) or OUTPUT_INSPECTION_TIMEOUT_SECONDS <= 0:
    raise ValueError("OUTPUT_INSPECTION_TIMEOUT_SECONDS must be finite and positive")
DEFAULT_ENFORCEMENT = os.getenv("GATEWAY_ENFORCEMENT", "enforce")
# Integrity failures are not opinions. A drifted catalog, an unregistered tool, a
# critical supply-chain finding or an unavailable policy engine stay enforced even
# while the gateway is only observing the permission model, because "observe" cannot
# mean "call a server we can no longer vouch for".
# P-RATE- is here because a call-rate ceiling protects the gateway and the upstream,
# not a permission opinion about who may read what. Observing it would mean having no
# ceiling at all for as long as observation lasts.
# P-CHAIN- (PDF integration): a read-then-export chain is a disclosure, not a permission
# opinion; observing it would let the export through while "measuring".
ALWAYS_ENFORCED = ("MCP-", "PAC-", "INPUT_CONTRACT", "POLICY_BUNDLE", "P-CONTROL-", "P-INPUT-", "P-RATE-", "P-CHAIN-", "P-FLOW-", "P-HIGH-IMPACT-", "P-RESIDENCY-")
CHAIN_WINDOW_MINUTES = int(os.getenv("CHAIN_WINDOW_MINUTES", "10"))


def _flow_match_mode(value: str | None) -> str:
    """D-142: "content" narrows P-FLOW-001 to calls whose text matches what was read; anything else,
    a misspelling included, is "coarse": every call after a read from another server."""
    return "content" if (value or "").strip().lower() == "content" else "coarse"


FLOW_MATCH_MODE = _flow_match_mode(os.getenv("FLOW_MATCH_MODE"))
RATE_LIMIT_CALLS = int(os.getenv("RATE_LIMIT_CALLS", "60"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
IMPORTANT_BURST_LIMIT = int(os.getenv("IMPORTANT_BURST_LIMIT", "10"))
IMPORTANT_BURST_MINUTES = int(os.getenv("IMPORTANT_BURST_MINUTES", "5"))
BLOCK_STREAK_LIMIT = int(os.getenv("BLOCK_STREAK_LIMIT", "5"))
BLOCK_STREAK_MINUTES = int(os.getenv("BLOCK_STREAK_MINUTES", "10"))
AUTO_SUSPEND_THRESHOLD = int(os.getenv("AUTO_SUSPEND_THRESHOLD", "5"))
AUTO_SUSPEND_WINDOW_SECONDS = int(os.getenv("AUTO_SUSPEND_WINDOW_SECONDS", "600"))
AUTO_SUSPEND_DURATION_SECONDS = int(os.getenv("AUTO_SUSPEND_DURATION_SECONDS", "900"))
# How many calls one principal may have in flight at once, and how long a reservation
# survives if the gateway dies mid-call. The TTL is the upstream timeout plus a margin:
# shorter and a slow tool frees its own place while still running.
CONCURRENCY_LIMIT = int(os.getenv("CONCURRENCY_LIMIT", "4"))
RESERVATION_TTL_SECONDS = int(os.getenv("RESERVATION_TTL_SECONDS", "120"))
MAX_ARGUMENT_BYTES = int(os.getenv("MAX_ARGUMENT_BYTES", "65536"))
# D-176: count only repeated, request-attributable security violations. State,
# approval, consent, catalog, classification, rate, and fail-closed refusals are
# deliberately absent because they can be normal workflow or service conditions.
AUTO_SUSPEND_POLICIES = (
    "MCP-EGRESS-002", "MCP-DATA-EGRESS-001",
    "P-DLP-001", "P-CHAIN-001", "P-FLOW-001",
)
DENIAL_POLICIES = AUTO_SUSPEND_POLICIES


def check_auto_suspend_settings(threshold: int, window_seconds: int, duration_seconds: int,
                                policies: tuple[str, ...]) -> None:
    """D-176: a wrong setting stops the gateway at start. Quietly disabling the control would be worse."""
    for name, value in (("AUTO_SUSPEND_THRESHOLD", threshold), ("AUTO_SUSPEND_WINDOW_SECONDS", window_seconds),
                        ("AUTO_SUSPEND_DURATION_SECONDS", duration_seconds)):
        if value < 1:
            raise RuntimeError(f"{name}은(는) 1 이상이어야 합니다(현재 {value}). 게이트웨이를 시작하지 않습니다.")
    if not policies:
        raise RuntimeError("자동 중지 대상 정책 목록이 비어 있습니다. 게이트웨이를 시작하지 않습니다.")


check_auto_suspend_settings(AUTO_SUSPEND_THRESHOLD, AUTO_SUSPEND_WINDOW_SECONDS,
                            AUTO_SUSPEND_DURATION_SECONDS, AUTO_SUSPEND_POLICIES)


class ResultRejected(RuntimeError):
    """Upstream answered, but its output failed the gateway's output control."""

    def __init__(self, message: str, payload: Any = None):
        super().__init__(message)
        # No digest of the withheld text: a short unmasked answer could be confirmed by
        # hashing guesses. Size and shape are enough to tell what was kept back.
        self.evidence = ({**response_evidence(payload, "withheld"), "sha256": None}
                         if payload is not None else None)


# What a client receives as tool output. Images, audio, embedded resources and
# resource links carry bytes or URIs the output checks cannot read; they used to reach
# the client flattened into truncated JSON text. They are withheld instead.
RESULT_CONTENT_TYPES = {"text"}


def response_evidence(payload: Any, disposition: str, masked_types: list[str] | None = None) -> dict:
    """What the audit keeps of a response: digest, size and shape, never the text."""
    content = payload.get("content") if isinstance(payload, dict) else None
    return {"disposition": disposition, "sha256": canonical_hash(payload),
            "bytes": len(json.dumps(payload, ensure_ascii=False).encode()),
            "content_types": sorted({item.get("type") if item.get("type") in
                                     {"text", "image", "audio", "resource", "resource_link"} else "unsupported"
                                     for item in content or [] if isinstance(item, dict) and isinstance(item.get("type"), str)}),
            "structured": bool(isinstance(payload, dict) and "structured" in payload),
            **({"structured_dropped": payload["structured_dropped"]}
               if isinstance(payload, dict) and payload.get("structured_dropped") else {}),
            "masked_types": masked_types or []}


def response_disposition(event: dict) -> str:
    """returned · masked · withheld (executed, answer kept back) · unknown · not_executed."""
    if (event.get("result_evidence") or {}).get("disposition"):
        return event["result_evidence"]["disposition"]
    if event.get("upstream_executed"):
        return "withheld" if event.get("result") is None else "returned"
    return "unknown" if event.get("upstream_attempted") else "not_executed"


class _Laps:
    """Wall time per stage of one tools/call, in milliseconds, kept with its decision.

    A stage is the time since the previous lap, so stages add up to the total; a stage
    that runs twice (output inspection) accumulates.
    """

    def __init__(self) -> None:
        self.started = self.mark = time.perf_counter()
        self.stages: dict[str, float] = {}

    def lap(self, stage: str) -> None:
        now = time.perf_counter()
        self.stages[stage] = round(self.stages.get(stage, 0.0) + (now - self.mark) * 1000, 2)
        self.mark = now

    def view(self) -> dict:
        return {**self.stages, "total": round((time.perf_counter() - self.started) * 1000, 2)}


class DispatchRejected(RuntimeError):
    """The final checks failed before tools/call was sent."""

    def __init__(self, message: str, verdict: dict | None = None):
        super().__init__(message)
        self.verdict = verdict


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


async def _discover(server_id: str) -> dict:
    spec = registry.server(server_id)
    if not spec:
        raise RuntimeError(f"catalog has no server {server_id}")
    return await upstream.discover(spec["endpoint"])


async def refresh_catalog(server_id: str) -> dict:
    server = await db.fetch_one(
        """SELECT s.*, (SELECT reason FROM ops_suspensions x WHERE x.server_id=s.id AND x.resumed_at IS NULL)
                         AS automatic_stop_reason FROM mcp_servers s WHERE s.id=%s""", (server_id,))
    if not server:
        raise RuntimeError(f"unregistered server: {server_id}")
    if server.get("automatic_stop_reason") and server["status"] != "DISABLED":
        await db.execute("UPDATE mcp_servers SET status='DISABLED',status_reason=%s WHERE id=%s",
                         (server["automatic_stop_reason"], server_id))
        server = {**server, "status": "DISABLED", "status_reason": server["automatic_stop_reason"]}
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
    catalog_hash = canonical_hash(discovered["tools"])
    registered_rows = await db.fetch_all("SELECT * FROM mcp_tools WHERE server_id=%s ORDER BY name", (server_id,))
    registered = {row["name"]: row for row in registered_rows}
    # Per-tool observed columns change only when the catalog changes; writing them on
    # every refresh would cost one UPDATE per tool (gitea has 55) for no new fact.
    latest = await db.fetch_one(
        "SELECT catalog_hash FROM catalog_snapshots WHERE server_id=%s ORDER BY id DESC LIMIT 1",
        (server_id,))
    if (not latest or latest["catalog_hash"] != catalog_hash
            or any(row["observed_schema_hash"] is None or row.get("observed_output_schema_hash") is None
                   for row in registered_rows)):
        for name, tool in observed.items():
            if name not in registered:
                continue
            await db.execute(
                """UPDATE mcp_tools SET observed_description_hash=%s, observed_schema_hash=%s,
                   observed_server_version=%s, observed_at=now(), description=%s, input_schema=%s,
                   annotations=%s WHERE server_id=%s AND name=%s""",
                (canonical_hash(tool["description"]), canonical_hash(tool["input_schema"]),
                 discovered["version"], tool["description"], Jsonb(tool["input_schema"]),
                 Jsonb(tool.get("annotations")), server_id, name),
            )
            await db.execute(
                """UPDATE mcp_tools SET output_schema=%s, observed_output_schema_hash=%s
                   WHERE server_id=%s AND name=%s""",
                (Jsonb(tool.get("output_schema")), canonical_hash(tool.get("output_schema")), server_id, name))
    registered_rows = await db.fetch_all("SELECT * FROM mcp_tools WHERE server_id=%s ORDER BY name", (server_id,))
    registered = {row["name"]: row for row in registered_rows}
    names_match = set(observed) == set(registered)
    # Only enabled tools reach a client. Unexposed provider helpers cannot inject
    # their descriptions into that client, but the entire catalog remains pinned.
    reviewed = (registry.server(server_id) or {}).get("poisoning_review") or {}
    metadata_findings = {name: reasons for name, tool in observed.items()
                         if name in registered and registered[name]["enabled"]
                         and not registry.review_matches(reviewed.get(name), tool)
                         and (reasons := poisoning.findings(tool))}
    metadata_safe = not metadata_findings
    findings: list[dict] = []
    if not names_match:
        findings.append({
            "type": "tool-set-drift",
            "added": sorted(set(observed) - set(registered)),
            "missing": sorted(set(registered) - set(observed)),
        })
    if not metadata_safe:
        findings.append({"type": "unsafe-description",
                         "tools": metadata_findings})

    # What gates the server (D-69) is the contract a client can actually reach: the enabled tools'
    # descriptions and schemas. Hosted servers report a build id as their version (GitHub: one per
    # deploy) and change helpers nobody enabled; pinning those took figma and github down every few
    # days with no reviewed tool changed. Those changes are still recorded below as findings.
    enabled = {name for name, row in registered.items() if row["enabled"]}
    enabled_missing = sorted(enabled - set(observed))
    hashes_match = not enabled_missing
    version_only = []
    for name in set(observed) & set(registered):
        row = registered[name]
        tool = observed[name]
        mismatches = []
        if row["approved_description_hash"] != canonical_hash(tool["description"]):
            mismatches.append("description")
        if row["approved_schema_hash"] != canonical_hash(tool["input_schema"]):
            mismatches.append("schema")
        if not output_contract.matches(row, tool.get("output_schema")):
            mismatches.append("output_schema")
        if row["approved_server_version"] != discovered["version"]:
            mismatches.append("version")
        if mismatches:
            findings.append({"type": "contract-drift", "tool": name, "fields": mismatches, "enabled": name in enabled})
            if name in enabled and mismatches != ["version"]:
                hashes_match = False
            elif mismatches == ["version"]:
                version_only.append(name)
    if enabled_missing:
        findings.append({"type": "enabled-tool-missing", "tools": enabled_missing})
    # Same reviewed description and schema under whatever build id answered: the approval carries
    # over. Both columns, every refresh: the observed ones are otherwise rewritten only when the
    # tool list changes, and the per-call contract compares the two (version_match).
    await db.execute(
        """UPDATE mcp_tools SET approved_server_version=%s, observed_server_version=%s WHERE server_id=%s
             AND (approved_server_version IS DISTINCT FROM %s OR observed_server_version IS DISTINCT FROM %s)
             AND approved_description_hash=observed_description_hash AND approved_schema_hash=observed_schema_hash
             AND (approved_output_schema_hash IS NULL OR approved_output_schema_hash=observed_output_schema_hash)""",
        (discovered["version"], discovered["version"], server_id, discovered["version"], discovered["version"]))
    if version_only:
        findings.append({"type": "version-carried", "to": discovered["version"], "tools": sorted(version_only)})

    # Exactness describes the whole catalog; only a proven affected tool is restricted.
    exact_match = metadata_safe and hashes_match
    restricted = selective.restricted_tools(findings)
    previous = await db.fetch_one(
        "SELECT catalog_hash, exact_match, restricted_tools, server_version FROM catalog_snapshots WHERE server_id=%s ORDER BY id DESC LIMIT 1",
        (server_id,),
    )
    # The snapshot table is change evidence, not a call counter: the catalog is
    # re-read before every call, so writing a row per call grows it without adding
    # anything a reviewer can read.
    async with db.transaction() as connection:
        await connection.execute("SELECT id FROM mcp_servers WHERE id=%s FOR UPDATE", (server_id,))
        if (not previous or previous["catalog_hash"] != catalog_hash or previous["exact_match"] != exact_match
                or previous.get("restricted_tools") != restricted or previous.get("server_version") != discovered["version"]):
            snapshot = await (await connection.execute(
                """INSERT INTO catalog_snapshots(server_id, server_version, catalog_hash, tool_count, exact_match, findings, restricted_tools)
                   VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (server_id, discovered["version"], catalog_hash, len(observed), exact_match, Jsonb(findings), restricted),
            )).fetchone()
        else:
            snapshot = None
        await connection.execute(
            """UPDATE mcp_servers SET status=%s, status_reason=%s, last_seen_at=now(),
               advertised_name=%s WHERE id=%s AND status NOT IN ('DISABLED','BLOCKED_SUPPLY_CHAIN')
               AND lifecycle NOT IN ('TERMINATING','RETIRED')""",
            (
                "READY" if exact_match else "DRIFT",
                "승인 계약과 일치" if exact_match else "도구 계약 변화가 탐지됨",
                discovered.get("advertised_name") or None,
                server_id,
            ),
        )
    if snapshot:
        await ops_response.catalog_alerts(server_id, findings, snapshot["id"])
    # T4. 계약이 바뀌면 심사한 코드와 지금 도는 코드가 갈라졌다는 뜻이므로 AI 코드
    # 감사도 다시 돌아야 한다. v1.5는 scan_jobs.trigger에 'drift' 값만 예약해 두고
    # 이 시각을 남기지 않아서, 워커가 "마지막 감사 이후 드리프트가 있었는가"를
    # 물어볼 수 없었다. 큐잉은 워커가 하고, 여기서는 사실만 기록한다.
    if not exact_match:
        await upstream.release_pool(server["endpoint"], None, "contract-drift")
        await db.execute(
            "UPDATE mcp_servers SET drift_observed_at=now() WHERE id=%s", (server_id,)
        )
        await ops_response.contain_drift(server_id, findings)
    current_status = await db.fetch_one("SELECT status FROM mcp_servers WHERE id=%s", (server_id,))
    return {
        "server_id": server_id,
        "status": current_status["status"],
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
    if registry.is_console_registration(server_id):
        raise ValueError("Console 등록 서버의 계약 변경은 새 도입 신청에서 재검토해야 합니다.")
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
        # An unpinned legacy approval is pinned by this person's review (D-149).
        if not output_contract.observed_matches(row) or row.get("approved_output_schema_hash") is None:
            fields.append("output_schema")
        if row["approved_server_version"] != row["observed_server_version"]:
            fields.append("version")
        if not fields:
            continue
        changes.append({
            "tool": row["name"], "fields": fields,
            "from": {"description": row["approved_description_hash"],
                     "schema": row["approved_schema_hash"], "output_schema": row.get("approved_output_schema_hash"),
                     "version": row["approved_server_version"]},
            "to": {"description": row["observed_description_hash"],
                   "schema": row["observed_schema_hash"], "output_schema": row.get("observed_output_schema_hash"),
                   "version": row["observed_server_version"]},
        })
    if not changes:
        return {"server_id": server_id, "changed": [], "status": server["status"],
                "note": "승인본과 관측값이 이미 같습니다."}

    async with db.transaction() as connection:
        await connection.execute(
            """UPDATE mcp_tools SET
                 approved_description_hash = COALESCE(observed_description_hash, approved_description_hash),
                 approved_schema_hash = COALESCE(observed_schema_hash, approved_schema_hash),
                 approved_output_schema_hash = COALESCE(observed_output_schema_hash, approved_output_schema_hash),
                 approved_server_version = COALESCE(observed_server_version, approved_server_version)
               WHERE server_id=%s""", (server_id,))
        # 재승인 자체가 기록이다. 무엇을 무엇으로 바꿨는지가 없으면 나중에 "그때
        # 승인한 것이 지금 도는 것과 같은가"에 답할 수 없다.
        await connection.execute(
            """INSERT INTO catalog_snapshots(server_id, server_version, catalog_hash, tool_count,
                                             exact_match, findings)
               VALUES (%s,%s,%s,%s,true,%s)""",
            (server_id, rows[0]["observed_server_version"] if rows else None,
             canonical_hash(changes), len(rows),
             Jsonb([{"type": "contract-reapproved", "actor": actor, "note": note,
                     "changes": changes}])),
        )
        await review.record_event("contract-reapprove", "approved", "server", server_id, actor, reason=note,
                                  scope={"tools": [change["tool"] for change in changes]}, connection=connection)
    # 재대조해서 상태를 READY로 되돌린다. 승인만 하고 status가 DRIFT로 남으면
    # 화면은 여전히 변조를 말하고 정책은 통과시킨다 - 둘 중 하나가 거짓말이다.
    refreshed = await refresh_catalog(server_id)
    await upstream.release_pool(server["endpoint"], None, "contract-reapproved")
    return {"server_id": server_id, "changed": changes, "status": refreshed["status"],
            "actor": actor, "note": note}


async def bootstrap() -> None:
    await db.wait_until_ready()
    await db.execute((Path(__file__).parent / "agent_tables.sql").read_text())
    await db.execute((Path(__file__).parent / "lifecycle_tables.sql").read_text())
    await db.execute((Path(__file__).parent / "v2_tables.sql").read_text())
    await db.execute((Path(__file__).parent / "oidc_tables.sql").read_text())
    await db.execute((Path(__file__).parent / "ops_tables.sql").read_text())
    await db.execute((Path(__file__).parent / "local_run_tables.sql").read_text())
    await db.execute((Path(__file__).parent / "siem_tables.sql").read_text())
    await registry.sync()
    await disposal.capture_existing()
    await disposal.reconcile()
    await policy_ledger(refresh=True)
    if POLICY_PATH.exists():
        files = [path for path in (POLICY_PATH.parent / name for name in POLICY_BUNDLE) if path.exists()]
        bundle = hashlib.sha256()
        for path in files:
            bundle.update(path.name.encode() + b"\0" + path.read_bytes() + b"\0")
        digest = bundle.hexdigest()
        await db.execute("UPDATE policy_versions SET status='SUPERSEDED' WHERE status='ACTIVE' AND source_sha256<>%s", (digest,))
        await db.execute(
            """INSERT INTO policy_versions(id, source_path, source_sha256, status)
               VALUES (%s,%s,%s,'ACTIVE') ON CONFLICT (id) DO UPDATE SET status='ACTIVE'""",
            (f"bundle-{digest[:12]}", ", ".join(str(path) for path in files), digest),
        )


async def refresh_all_catalogs() -> dict:
    """One pass over every catalog server. A server that does not answer is ERROR,
    which the policy path reads as an unverifiable contract (MCP-CATALOG-001)."""
    results = {}
    for server_id in registry.servers():
        if (registry.server(server_id) or {}).get("deployment") == "local":
            # 로컬 실행 서버는 호출하는 직원 PC의 실행기가 승인 계약을 호출마다 대조한다(local-runner control contracts).
            # 관찰 PC 한 대가 정책 갱신 중이라 거절한 것을 서버 전체 ERROR로 내리면, ERROR는 로컬 실행 허가에서 빠져
            # 스스로 복구하지 못하고 모든 직원 하네스 설정에서 사라졌다(10-23 실측).
            results[server_id] = "LOCAL"
            continue
        try:
            results[server_id] = (await refresh_catalog(server_id))["status"]
        except Exception as exc:
            await db.execute(
                "UPDATE mcp_servers SET status='ERROR', status_reason=%s WHERE id=%s AND status NOT IN ('DISABLED','BLOCKED_SUPPLY_CHAIN')",
                (f"연결 실패: {_root_cause(exc)}", server_id))
            results[server_id] = "ERROR"
    return results


async def check_server(server_id: str) -> dict:
    """D-40: can the Gateway open an MCP session with this server right now?

    LiteLLM keeps the same split (health_check_server beside its tool discovery). The
    catalog refresh reads tools/list and rewrites contract state, so it is the wrong
    tool for "is it up": this one only negotiates a session, and records nothing.
    A retired server is not contacted - its endpoint is the termination case's evidence.
    """
    spec = registry.server(server_id)
    if not spec:
        raise LookupError(server_id)
    row = await db.fetch_one("SELECT lifecycle FROM mcp_servers WHERE id=%s", (server_id,))
    checked_at = datetime.now(UTC).isoformat()
    if row and row["lifecycle"] == "RETIRED":
        return {"server_id": server_id, "state": "retired", "checked_at": checked_at}
    loop = asyncio.get_running_loop()
    started = loop.time()
    try:
        info = await asyncio.wait_for(upstream.handshake(spec["endpoint"]), SERVER_CHECK_TIMEOUT_SECONDS)
        result = {"state": "healthy", **info}
    except Exception as exc:
        result = {"state": "unhealthy", "error": _root_cause(exc)}
    return {"server_id": server_id, **result, "latency_ms": round((loop.time() - started) * 1000, 1),
            "checked_at": checked_at}


# ── Console registration of an approved server (D-49) ────────────────────────────
# LiteLLM keeps config servers and runtime (DB) servers side by side; here the runtime
# half is REGISTRY_RUNTIME_DIR/servers.json. What LiteLLM does not do, and this must:
# pin the contract the admin reviewed (no trust-on-first-use), and give the approval an
# end date - the BeyondTrust shape "request → approve → use → expire → audit", where the
# expiry is enforced by the existing P-APPROVAL-EXPIRY-001.
REGISTER_LOCK = asyncio.Lock()


def registration_endpoint(value: str) -> str:
    endpoint = value.strip()
    parts = urlsplit(endpoint)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password or parts.fragment:
        raise ValueError("http(s)://호스트/경로 형식의 MCP 엔드포인트여야 합니다. 자격 정보는 URL에 넣지 않습니다.")
    if not transport_secure(endpoint):
        raise ValueError("사내 서비스가 아니면 HTTPS 엔드포인트만 등록할 수 있습니다.")
    return endpoint


def suggested_action(annotations: dict | None) -> str:
    # upstream.tool_view stores the SDK's field names (read_only_hint); the wire form is readOnlyHint.
    hints = {key.replace("_", "").lower(): value for key, value in (annotations or {}).items()}
    return "r" if hints.get("readonlyhint") else "x" if hints.get("destructivehint") or hints.get("openworldhint") else "w"


async def discover_for_registration(endpoint: str, local: dict | None = None, intake_id: str = "",
                                    principal: str | None = None) -> dict:
    if local:
        server_id = local_jobs.server_of(endpoint) or ""
        try:
            # 원클릭 승인은 승인 전에 신청자 PC에서 계약을 관찰한다. 관찰은 관리자만 부르고(admin_caller), 등록은 여전히 승인 뒤다.
            intake = await db.fetch_one("SELECT submitted_by FROM mcp_intake_requests WHERE id=%s AND status IN ('HOLD','VALIDATED','APPROVED')", (uuid.UUID(intake_id),))
        except ValueError:
            intake = None
        if not intake:
            raise ValueError("로컬 실행 계약은 도입 신청자의 PC에서 확인합니다. 신청을 지정하세요.")
        local = local_jobs.local_block(local["manifest"], local["signature"],
                                       await local_jobs.applicant_device(intake["submitted_by"], intake_id), server_id)
        observer = await local_jobs._device(local['observer_device'])
        token = local_jobs.registering.set(local)
        try:
            await local_jobs.approve_manifest(local_jobs.registering.get(), intake_id)
            found = await upstream.discover(endpoint)
        finally:
            local_jobs.registering.reset(token)
    else:
        found = (await upstream.discover(registration_endpoint(endpoint), principal=principal) if principal
                 else await upstream.discover(registration_endpoint(endpoint)))
    local_view = {}
    if local:
        # 격리 구성은 기기 설정이 아니라 관찰 PC 실행기가 측정해 보고한 값(엔진·판본·사용자 매핑)이다.
        measurement = await db.fetch_one(
            """SELECT evidence->'isolation' AS isolation FROM local_job_events
               WHERE server_id=%s AND device_id=%s AND evidence ? 'isolation'
               ORDER BY created_at DESC,id DESC LIMIT 1""",
            (local["manifest"]["server_id"], local["observer_device"]))
        isolation = (measurement or {}).get("isolation") or {}
        namespace = isolation.get("namespace")
        engine_name = {"podman": "Podman", "docker": "Docker"}.get(
            isolation.get("engine") or ("podman" if str(namespace).startswith("podman") else "docker"))
        namespace_name = {"podman-auto": "자동 사용자 공간", "docker-remap": "사용자 재매핑"}.get(namespace)
        if namespace == "host":
            isolation_scope = "탈출 시 호스트 root"
        elif namespace_name:
            isolation_scope = f"{engine_name} {isolation.get('engine_version') or '—'} · {namespace_name} · {isolation.get('scope') or '확인 안 됨'}"
        else:
            isolation_scope = "확인 안 됨"
        local_view = {"observer_device": local["observer_device"], "observer_uid": observer["local_uid"],
                      "image_signature": "확인 안 됨", "isolation_scope": isolation_scope,
                      "user_mapping": isolation.get("uid_map") or "확인 안 됨"}
    return {**local_view,
            "endpoint": endpoint.strip(), "server_name": found["advertised_name"], "version": found["version"],
            "protocol_version": found["protocol_version"], "catalog_hash": canonical_hash(found["tools"]),
            "tools": [{**tool, "suggested": suggested_action(tool.get("annotations")), "warnings": poisoning.findings(tool)}
                      for tool in found["tools"]]}


async def register_server(request: dict, actor: str) -> dict:
    server_id = request["server_id"]
    server_location = residency.normalize(request.get("residency"))
    local = request.get("local")
    if local:
        # DEV-73: the server runs on each caller's own device under a signed manifest.
        if request["endpoint"] != local_jobs.PREFIX + server_id:
            raise ValueError(f"로컬 실행 서버는 {local_jobs.PREFIX}{server_id} 주소로 등록합니다.")
        endpoint = request["endpoint"]
    else:
        endpoint = registration_endpoint(request["endpoint"])
    residency.require_location(server_location, request["data_class"], registry.catalog().get("organization", {}))
    if not local:
        endpoint = registration_endpoint(request["endpoint"])
    try:
        intake_id = uuid.UUID(request.get("intake_id") or "")
    except ValueError as exc:
        raise ValueError("승인된 도입 신청 id가 필요합니다. 관리자 직접 등록으로 신청을 우회할 수 없습니다.") from exc
    intake = await db.fetch_one("SELECT * FROM mcp_intake_requests WHERE id=%s", (intake_id,))
    if not intake or intake["status"] != "APPROVED" or not intake.get("reviewed_by"):
        raise ValueError("승인된 도입 신청만 등록할 수 있습니다.")
    if await review.same_person(intake["submitted_by"], intake["reviewed_by"]):
        raise ValueError("신청자와 승인자가 같아 등록할 수 없습니다.")
    evidence = intake.get("evidence") or {}
    proposal = evidence.get("approval_proposal")
    if proposal:
        scope = evidence.get("one_click_scope") or {}
        selected = scope.get("tools") or []
        # 승인자가 낮춘 도구 분류만 반영한다. 올린 값은 위험 등급 산정과 어긋나므로 받지 않는다.
        actions = scope.get("actions") or {}
        lowered = set(actions) <= set(selected) and all(
            a in {"r", "w", "x"} and "rwx".index(a) <= "rwx".index(proposal["tools"][n]) for n, a in actions.items())
        expected = {"server_id": proposal["server_id"], "endpoint": proposal["endpoint"],
                    "catalog_hash": (proposal.get("catalog") or {}).get("catalog_hash"),
                    "tools": {n: actions.get(n, proposal["tools"][n]) for n in selected}, "data_class": proposal["data_class"],
                    "valid_days": scope.get("valid_days"), "supplier_assurance": scope.get("supplier_assurance"),
                    "residency": scope.get("residency")}
        if (scope.get("proposal_sha256") != intake_proposal.digest(proposal) or not selected or not lowered
                or intake_proposal.basis(intake) != proposal["basis"]
                or intake.get("risk_input") != proposal["risk_input"]
                or any(request.get(k) != v for k, v in expected.items())
                or {n: review.scope_terms(item) for n, item in review.normalize_tool_reviews(
                    request["tools"], request.get("tool_reviews"), actor).items()} != {
                    n: review.scope_terms(item) for n, item in review.normalize_tool_reviews(
                        expected["tools"], {n: proposal["tool_reviews"][n] for n in selected}, actor).items()}):
            raise ValueError("화면에서 승인한 범위와 다릅니다. 도입 검토를 다시 열어 확인하세요.")
    # Registration repeats the checks approval made: provenance recorded and compared with the copy in
    # use, every scan finished and fresh, no critical finding without a live acceptance (D-90).
    gate = await review.intake_gate(intake, verified=True)
    if gate["blockers"]:
        raise ValueError("등록할 수 없습니다: " + " / ".join(item["message"] for item in gate["blockers"]))
    remote_review = None
    if intake["intake_kind"] == "remote-endpoint":
        remote_review = (intake.get("evidence") or {}).get("remote_contract") or {}
        approval = (intake.get("evidence") or {}).get("remote_approval") or {}
        if (approval.get("review_digest") != canonical_hash(remote_review)
                or approval.get("actor") != intake["reviewed_by"]
                or not remote_review.get("allowed_principals")):
            raise ValueError("검토한 계약과 도입 승인 근거가 일치하지 않습니다.")
        selected = {key: request.get(key) for key in remote_review["registration"]}
        if selected != remote_review["registration"] or endpoint != intake["endpoint_url"]:
            raise ValueError("승인된 endpoint·도구·등급·기한과 다른 등록은 거부합니다.")
        if request.get("source_url") != endpoint or request.get("commit_sha"):
            raise ValueError("원격 서비스 등록을 검증한 구현 소스인 것처럼 표시할 수 없습니다.")
        if datetime.fromisoformat(remote_review["valid_until"]) <= datetime.now(UTC):
            raise ValueError("도입 승인 사용 기한이 지났습니다.")
    elif (not intake.get("commit_sha") or request.get("source_url") != intake["repository_url"]
          or request.get("commit_sha") != intake["commit_sha"]):
        raise ValueError("검증·승인된 구현 저장소와 커밋이 일치하지 않습니다.")
    if server_id in registry.reviewed_servers():
        raise ValueError(f"검토된 카탈로그(catalog.toml)에 같은 id가 있습니다: {server_id}")
    # One approval is one registration, and it never replaces a server another approval runs.
    if intake.get("registered_server_id") not in (None, "", server_id):
        raise ValueError(f"이 도입 승인은 이미 {intake['registered_server_id']}로 등록했습니다. 새 서버는 새 신청이 필요합니다.")
    active = registry.runtime()["servers"].get(server_id)
    if active and active.get("intake_id") != str(intake_id):
        raise ValueError(f"운영 중인 서버 id입니다: {server_id}. 기존 등록을 해제한 뒤 등록하세요.")
    if active and residency.normalize(active.get("residency")) != server_location:
        raise ValueError("처리·저장 위치 변경은 새 도입 신청과 승인이 필요합니다.")
    row = await db.fetch_one("SELECT lifecycle FROM mcp_servers WHERE id=%s", (server_id,))
    if row and (row["lifecycle"] or "OPERATING") in {"TERMINATING", "RETIRED"}:
        raise ValueError("종료 절차를 거친 서버 id는 다시 쓸 수 없습니다. 새 id로 등록하세요.")
    runtime = None
    if local and intake["intake_kind"] != "repository":
        raise ValueError("로컬 실행은 검증한 구현 저장소 신청으로만 등록합니다.")
    if local:
        local = local_jobs.local_block(local["manifest"], local["signature"],
                                       await local_jobs.applicant_device(intake["submitted_by"], intake_id), server_id)
    if intake["intake_kind"] == "repository" and not local:
        # A source the solution runs itself is registered at the address of that run, so the
        # registration names the image built from the approved commit (DEV-38).
        runtime = await db.fetch_one(
            """SELECT id, generation, image_id, source_commit, source_archive_sha256, recipe_id, recipe_sha256, endpoint
               FROM mcp_runtimes WHERE intake_id=%s AND status='ACTIVE'""", (intake_id,))
        if runtime and endpoint != runtime["endpoint"]:
            raise ValueError(f"이 신청은 솔루션이 실행하고 있습니다. 실행 주소로 등록하세요: {runtime['endpoint']}")
    if local:
        await local_jobs.approve_manifest(local, str(intake_id))
        token = local_jobs.registering.set(local)
        try:
            found = await upstream.discover(endpoint)
        finally:
            local_jobs.registering.reset(token)
    else:
        found = await upstream.discover(endpoint)
    if remote_review and (found["version"] != remote_review["version"]
            or found["advertised_name"] != remote_review["advertised_name"]
            or found["protocol_version"] != remote_review["protocol_version"]):
        raise ValueError("검토한 공급자 신원·버전·프로토콜과 다릅니다.")
    # The admin approves what they saw. A contract that moved between review and this call
    # is not what they approved, so they review again (the same rule as approve_contract).
    if canonical_hash(found["tools"]) != request["catalog_hash"]:
        raise ValueError("검토한 뒤 서버의 도구 계약이 바뀌었습니다. 도구를 다시 불러와 검토하세요.")
    advertised = {tool["name"]: tool for tool in found["tools"]}
    unknown = sorted(set(request["tools"]) - set(advertised))
    if unknown:
        raise ValueError(f"서버가 제공하지 않는 도구: {', '.join(unknown)}")
    # D-52: a selected tool whose text reads like an instruction to the model is approved only on purpose.
    flagged = {name: poisoning.findings(advertised[name]) for name in request["tools"]}
    flagged = {name: reasons for name, reasons in flagged.items() if reasons}
    if flagged and not request.get("poisoning_ack"):
        raise ValueError("도구 설명에 모델을 조종하는 문구로 보이는 부분이 있습니다: "
                         + ", ".join(f"{name}({'·'.join(reasons)})" for name, reasons in sorted(flagged.items()))
                         + ". 내용을 읽고 확인했다고 표시해야 등록할 수 있습니다.")
    # What a person scoped, tool by tool; a tool without it is registered but not enabled (D-91).
    tool_reviews = review.normalize_tool_reviews(request["tools"], request.get("tool_reviews"), actor)
    for name, item in tool_reviews.items():
        if item["inputs"] is not None:
            review.check_inputs(name, advertised[name].get("input_schema") or {}, item["inputs"])
    host = urlsplit(endpoint).hostname or ""
    source_url = request.get("source_url") or ""
    commit = request.get("commit_sha") or ""
    github = source_url.startswith("https://github.com/")
    package = source_url.removeprefix("https://") if github else host
    # For a GitHub source the version is the validated commit, which is also what the
    # A.I.G worker checks out for a static audit of this server (source_ref = package@commit).
    version = commit if github and commit else found["version"]
    assurance = request.get("supplier_assurance") or {}
    assurance_errors = supplier_assurance.validate(assurance, required=False)
    if assurance_errors:
        raise ValueError("등록할 수 없습니다: " + " / ".join(assurance_errors))
    # DEV-71: the tier is read again from the stated input the approval was made on, and the approval
    # must have recorded that same input. A data grade above what the applicant stated understates the tier.
    stated = risk_tier.assess(intake.get("risk_input"))
    approved_risk = (intake.get("evidence") or {}).get("risk_assessment") or {}
    if stated["status"] != "ok" or approved_risk.get("input_sha256") != stated["input_sha256"]:
        raise ValueError("등록할 수 없습니다: 승인 때 확인한 영향평가 입력이 없거나 바뀌었습니다. 다시 신청하세요.")
    rule = risk_tier.APPROVAL[stated["tier"]]
    if rule["approvers"] > 1:
        approvers = []
        for person in approved_risk.get("approvers") or []:
            if await review.same_person(person, intake["submitted_by"]):
                raise ValueError("신청자는 승인자로 셀 수 없습니다.")
            if not any([await review.same_person(person, other) for other in approvers]):
                approvers.append(person)
        if len(approvers) < rule["approvers"]:
            raise ValueError("높은 위험 등급은 서로 다른 관리자 두 명이 승인해야 등록할 수 있습니다.")
    if rule["reason"] == "required" and not approved_risk.get("written_reason"):
        raise ValueError("매우 높은 위험 등급은 승인 때 기록한 위험 수용 사유가 필요합니다.")
    ranks = list(risk_tier.CHOICES["data_class"])
    if ranks.index(request["data_class"]) > ranks.index(intake["risk_input"]["data_class"]):
        raise ValueError("등록할 수 없습니다: 신청에 적은 데이터 등급보다 높은 등급입니다. 영향평가 입력을 고쳐 다시 승인하세요.")
    approval_until = datetime.now(UTC) + timedelta(days=int(request["valid_days"]))
    if proposal:
        approval_until = datetime.fromisoformat(evidence["one_click_scope"]["valid_until"])
        if approval_until <= datetime.now(UTC):
            raise ValueError("승인 기한이 지났습니다. 새 도입 신청이 필요합니다.")
    if remote_review:
        approval_until = datetime.fromisoformat(remote_review["valid_until"])
    valid_until = (min(approval_until, supplier_assurance.support_expiry(assurance["support_end"]))
                   if assurance.get("support_end") else approval_until).isoformat(timespec="seconds")
    spec = {
        "display_name": request["display_name"], "package": package, "version": version,
        "source_url": source_url or endpoint, "supplier": request.get("supplier") or host,
        "license": ((intake.get("provenance") or {}).get("license") or {}).get("spdx"), "endpoint": endpoint,
        # Only an active managed runtime proves that the solution runs this registration.
        "deployment": "internal" if runtime else "provider",
        "residency": server_location,
        "downstream": request.get("downstream") or None, "data_class": request["data_class"],
        "tools": dict(sorted(request["tools"].items())), "exit_terms": request.get("exit_terms") or {},
        "valid_until": valid_until, "registered_by": actor,
        "registered_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "intake_id": request.get("intake_id") or None,
        # A remote service is scoped to the principals its contract review named. A source-validated
        # server is scoped to the person who asked for it, with arguments derived from its pinned contract
        # and the reviewed destinations: an administrator enters an address, not JSON Schema (10-15).
        "allowed_principals": remote_review["allowed_principals"] if remote_review else [intake["submitted_by"]],
        "parameter_constraints": (remote_review.get("parameter_constraints", {}) if remote_review
                                  else review.derived_constraints(advertised, tool_reviews)),
        "constraints_derived": not remote_review,
        "poisoning_review": {name: registry.tool_hashes(advertised[name]) for name in flagged}
                            if request.get("poisoning_ack") else {},
        "tool_reviews": tool_reviews, "provenance": intake.get("provenance") or {},
        "supplier_assurance": assurance, "supplier_assurance_unconfirmed": supplier_assurance.unconfirmed(assurance),
        "risk_assessment": {"tier": stated["tier"], "score": stated["score"], "floors": stated["floors"],
                            "input": intake["risk_input"], "input_sha256": stated["input_sha256"],
                            "approvers": approved_risk.get("approvers") or [],
                            "solo_mode": approved_risk.get("solo_mode"),
                            "solo_operator": approved_risk.get("solo_operator"), "version": stated["version"]},
        "runtime": {key: str(value) for key, value in runtime.items()} if runtime else None,
    }
    if local:
        spec.update(local=local, deployment="local")
    contract = {"package": f"{package}@{version}", "server_name": found["advertised_name"],
                "server_version": found["version"], "protocol_version": found["protocol_version"],
                "tools": {name: registry.tool_hashes(tool) for name, tool in sorted(advertised.items())}}
    relationship = {"id": f"UR-{server_id.upper()}", "server": server_id,
                    "purpose": request.get("purpose") or request["display_name"],
                    "provider": spec["supplier"], "owner_department": request.get("owner_department") or None,
                    "allowed_resources": []}
    async with REGISTER_LOCK:
        doc = registry.runtime()
        doc["servers"][server_id] = spec
        doc["contracts"][server_id] = contract
        doc["usage_relationships"] = [r for r in doc["usage_relationships"] if r["id"] != relationship["id"]] + [relationship]
        doc["history"].append({"type": "registered", "server_id": server_id, "actor": actor,
                               "at": spec["registered_at"], "valid_until": valid_until, "residency": server_location})
        registry.save_runtime(doc)
        await registry.sync()
    if intake["intake_kind"] == "repository":
        # The scan evidence follows the release it approved: the Gateway reads criticals under the
        # server's own source_ref, and an accepted risk that lapses must bite there (D-90).
        linked, pattern = registry.source_ref(spec), f"%/intake-{intake_id}-%"
        await db.execute("DELETE FROM supply_chain_reports WHERE source_ref=%s AND report_path LIKE %s", (linked, pattern))
        await db.execute(
            """INSERT INTO supply_chain_reports(scanner, scanner_version, source_ref, report_path, status, critical_count,
                                                high_count, medium_count, vuln_db_updated_at, summary)
               SELECT scanner, scanner_version, %s, report_path, status, critical_count, high_count, medium_count,
                      vuln_db_updated_at, summary
                 FROM supply_chain_reports WHERE source_ref=%s AND report_path LIKE %s""",
            (linked, intake["source_ref"], pattern))
    # Re-registering an id (after a deregistration) starts from what was approved now.
    for name, hashes in contract["tools"].items():
        await db.execute(
            """UPDATE mcp_tools SET approved_description_hash=%s, approved_schema_hash=%s, approved_server_version=%s,
                      approved_output_schema_hash=%s
               WHERE server_id=%s AND name=%s""",
            (hashes["description_sha256"], hashes["schema_sha256"], found["version"],
             hashes["output_schema_sha256"], server_id, name))
    await db.execute(
        "UPDATE mcp_servers SET status='PENDING', status_reason='Console 등록, 계약 확인 전', lifecycle='OPERATING' WHERE id=%s",
        (server_id,))
    await db.execute("UPDATE usage_relationships SET status='ACTIVE' WHERE id=%s", (relationship["id"],))
    await db.execute(
        """INSERT INTO catalog_snapshots(server_id, server_version, catalog_hash, tool_count, exact_match, findings)
           VALUES (%s,%s,%s,%s,true,%s)""",
        (server_id, found["version"], request["catalog_hash"], len(advertised),
         Jsonb([{"type": "console-registered", "actor": actor, "endpoint": endpoint, "intake_id": spec["intake_id"],
                 "approved_tools": spec["tools"], "valid_until": valid_until,
                 "poisoning_review": spec["poisoning_review"]}])))
    await review.record_event(
        "server-register", "approved", "server", server_id, actor, applicant=intake["submitted_by"],
        reason=request.get("purpose") or request["display_name"],
        scope={"intake": str(intake_id), "tools": spec["tools"], "valid_until": valid_until, "data_class": request["data_class"],
               "residency": server_location,
               "artifact_sha256": ((spec["provenance"].get("artifact") or {}).get("sha256")), "version": spec["provenance"].get("version"),
               "impact": {name: high_impact.normalize(item) for name, item in tool_reviews.items()},
               **({'local':{'observer_device':local['observer_device'],
                            'observer_uid':(await local_jobs._device(local['observer_device']))['local_uid'],
                            'manifest_sha256':local['manifest_sha256'],
                            'signature_generation':local['manifest']['approval']['generation']}} if local else {})})
    refreshed = await refresh_catalog(server_id)
    await upstream.release_pool(endpoint, None, "registration")
    if local:
        await local_jobs.approve_manifest(local, str(intake_id), observed=True)
    return {"server_id": server_id, "status": refreshed["status"], "valid_until": valid_until,
            "tools": spec["tools"], "relationship_id": relationship["id"], "gateway_path": f"/mcp/{server_id}/"}


async def deregister_server(server_id: str, actor: str, reason: str | None = None) -> dict:
    """Takes a Console registration back out. The rows stay (DISABLED) for the audit trail."""
    await local_jobs.quiesce(server_id=server_id)
    async with REGISTER_LOCK:
        doc = registry.runtime()
        if server_id not in doc["servers"]:
            raise LookupError(server_id)
        endpoint = doc["servers"][server_id]["endpoint"]
        del doc["servers"][server_id]
        doc["contracts"].pop(server_id, None)
        doc["usage_relationships"] = [r for r in doc["usage_relationships"] if r["server"] != server_id]
        doc["history"].append({"type": "deregistered", "server_id": server_id, "actor": actor,
                               "at": datetime.now(UTC).isoformat(timespec="seconds")})
        registry.save_runtime(doc)
        await registry.sync()
    await upstream.release_pool(endpoint, None, "deregister")
    await review.record_event("server-deregister", "recorded", "server", server_id, actor, reason=reason)
    # Last: ServerPath already refuses the removed path, so a failure here costs no access
    # but must not cost the audit record above.
    from . import mcp_sessions
    await mcp_sessions.terminate(reason="deregister", server_id=server_id)
    return {"server_id": server_id, "status": "DISABLED"}


async def review_tool_scopes(server_id: str, reviews: dict, actor: str) -> dict:
    """Adds scope reviews (purpose, asset, external destinations) to tools of an existing Console
    registration, for registrations made before every tool carried one. The action is the one the
    registration already approved; the reviewer is never the person who asked for the server (D-91)."""
    async with REGISTER_LOCK:
        doc = registry.runtime()
        spec = doc["servers"].get(server_id)
        if not spec or not spec.get("intake_id"):
            raise LookupError(server_id)
        unknown = sorted(set(reviews) - set(spec["tools"]))
        if unknown:
            raise ValueError("등록에서 승인하지 않은 도구입니다: " + ", ".join(unknown))
        intake = await db.fetch_one("SELECT submitted_by FROM mcp_intake_requests WHERE id=%s::uuid", (spec["intake_id"],))
        applicant = intake["submitted_by"] if intake else None
        await review.require_independent("tool-scope-review", "server", server_id, actor, applicant)
        normalized = review.normalize_tool_reviews({name: spec["tools"][name] for name in reviews}, reviews, actor)
        # The argument set is cut from the pinned contract, so a reviewer can widen the inputs a previous
        # review narrowed, and a remote registration's own schema gets the same check (POL-31).
        pinned = {row["name"]: row["input_schema"] for row in await db.fetch_all(
            "SELECT name, input_schema FROM mcp_tools WHERE server_id=%s", (server_id,)) if row["input_schema"]}
        for name, item in normalized.items():
            if item["inputs"] is not None:
                review.check_inputs(name, pinned.get(name) or spec["parameter_constraints"].get(name) or {}, item["inputs"])
        if spec.get('local'):
            await local_jobs.quiesce(server_id=server_id)
        spec["tool_reviews"] = {**(spec.get("tool_reviews") or {}), **normalized}
        if spec.get("constraints_derived"):
            # New destinations move the address patterns with them.
            spec["parameter_constraints"].update(review.derived_constraints(
                {name: {"input_schema": pinned.get(name) or spec["parameter_constraints"][name]} for name in normalized},
                normalized))
        doc["history"].append({"type": "tool-scope-reviewed", "server_id": server_id, "actor": actor,
                               "at": datetime.now(UTC).isoformat(timespec="seconds"), "tools": sorted(normalized)})
        registry.save_runtime(doc)
        await registry.sync()
    await review.record_event("tool-scope-review", "approved", "server", server_id, actor, applicant=applicant,
                              scope={"tools": {name: item["action"] for name, item in normalized.items()},
                                     "destinations": {name: item["destinations"] for name, item in normalized.items()},
                                     "impact": {name: high_impact.normalize(item) for name, item in normalized.items()}})
    await tool_sunset.approve_review(server_id, sorted(normalized), actor)
    if spec.get('local'):
        await local_jobs.resume(server_id=server_id)
    return {"server_id": server_id, "reviewed": sorted(normalized),
            "unreviewed": sorted(set(spec["tools"]) - set(spec["tool_reviews"]))}


async def review_server_residency(server_id: str, location: dict, actor: str) -> dict:
    """Re-review the declared location without changing the approved remote contract (D-138)."""
    normalized = residency.normalize(location)
    async with REGISTER_LOCK:
        doc = registry.runtime()
        spec = doc["servers"].get(server_id)
        if not spec or not spec.get("intake_id"):
            raise LookupError(server_id)
        if spec.get("deployment") != "provider":
            raise ValueError("사내 실행 위치는 조직 기기 위치 설정에서 관리해야 합니다.")
        intake = await db.fetch_one("SELECT submitted_by FROM mcp_intake_requests WHERE id=%s::uuid",
                                    (spec["intake_id"],))
        if not intake:
            raise ValueError("도입 신청자를 확인할 수 없어 위치를 심사할 수 없습니다.")
        applicant = intake["submitted_by"] if intake else None
        previous = residency.normalize(spec.get("residency"))
        reviewed_at = datetime.now(UTC).isoformat(timespec="seconds")
        await review.require_independent("residency-review", "server", server_id, actor, applicant,
                                         {"residency": normalized, "previous_sha256": residency.sha256(previous)})
        binding = residency.transfer_review_digest(server_id, spec, normalized, residency.load_pack())
        # This decision must be durable before a file-backed grant can take effect.
        # A later registry failure may delay activation, never create an unaudited grant.
        await review.record_event("residency-review", "approved", "server", server_id, actor, applicant=applicant,
                                  scope={"residency": normalized, "previous_sha256": residency.sha256(previous),
                                         "approval_sha256": binding})
        spec["residency"] = normalized
        spec["residency_review"] = {"reviewed_by": actor, "reviewed_at": reviewed_at,
                                    "previous_sha256": residency.sha256(previous),
                                    "approval_sha256": binding}
        doc["history"].append({"type": "residency-reviewed", "server_id": server_id, "actor": actor,
                               "at": reviewed_at, "residency": normalized,
                               "previous_sha256": residency.sha256(previous),
                               "approval_sha256": spec["residency_review"]["approval_sha256"]})
        registry.save_runtime(doc)
        await registry.sync()
    return {"server_id": server_id, "residency": normalized, "reviewed_by": actor, "reviewed_at": reviewed_at}


RENEW_WINDOW_DAYS = int(os.getenv("APPROVAL_RENEW_WINDOW_DAYS", "7"))
RENEW_CONTRACT = ("registered", "enabled", "schema_hash_match", "description_hash_match", "known_tools_only",
                  "metadata_safe", "supplier_approved", "transport_secure", "endpoint_allowed")


async def renew_approvals(now: datetime | None = None) -> list[dict]:
    """Extend a Console registration's use approval by its original period when it is about to
    lapse and nothing it was approved on has changed (D-70): every enabled tool still matches its
    reviewed description and schema, the server is READY and operating, the supply chain shows no
    critical finding, the endpoint is still allowed. Anything else lapses as before and needs a new
    intake. An approval that has already lapsed is not revived."""
    now = now or datetime.now(UTC)
    renewed = []
    async with REGISTER_LOCK:
        doc = registry.runtime()
        for server_id, spec in doc["servers"].items():
            if not spec.get("valid_until") or not spec.get("registered_at"):
                continue
            until = datetime.fromisoformat(spec["valid_until"])
            if not now < until <= now + timedelta(days=RENEW_WINDOW_DAYS):
                continue
            server = await db.fetch_one("SELECT status, lifecycle FROM mcp_servers WHERE id=%s", (server_id,))
            if not server or server["status"] != "READY" or (server["lifecycle"] or "OPERATING") != "OPERATING":
                continue
            tools = await db.fetch_all("SELECT name FROM mcp_tools WHERE server_id=%s AND enabled", (server_id,))
            used = await tool_sunset.recently_used(server_id, [row["name"] for row in tools], now)
            if not used:
                continue
            contracts = [await _contract(server_id, row["name"]) for row in tools]
            if not contracts or not all(c.get(key) is True for c in contracts for key in RENEW_CONTRACT) \
                    or any(c.get("critical_vulnerabilities") for c in contracts):
                continue
            # The approval also rests on the intake still standing and on every served tool keeping its
            # scope review: a request sent back to hold (a lapsed risk acceptance) or a tool whose scope
            # was withdrawn needs a person again, not a quiet extension (D-94).
            intake = await db.fetch_one("SELECT status FROM mcp_intake_requests WHERE id=%s::uuid", (spec.get("intake_id"),))
            if not intake or intake["status"] != "APPROVED" or set(spec.get("tools", {})) - registry.reviewed_tools(server_id):
                continue
            days = int(spec.get("approval_days")
                       or max(1, round((until - datetime.fromisoformat(spec["registered_at"])).total_seconds() / 86400)))
            support_end = (spec.get("supplier_assurance") or {}).get("support_end")
            proposed_until = risk_tier.cap_until(supplier_assurance.renewal_until(until, days, support_end), spec,
                                                 doc.get("risk_tier_grace_started_at"))
            if proposed_until <= until:
                continue
            spec.update(valid_until=proposed_until.isoformat(timespec="seconds"), approval_days=days)
            event = {"type": "approval-renewed", "server_id": server_id, "actor": "automatic",
                     "at": now.isoformat(timespec="seconds"), "from": until.isoformat(timespec="seconds"),
                     "valid_until": spec["valid_until"], "tools": sorted(row["tool_name"] for row in used),
                     "last_use": {row["tool_name"]: row["last_use"].isoformat() for row in used}}
            doc["history"].append(event)
            renewed.append(event)
        if renewed:
            registry.save_runtime(doc)
            await registry.sync()
            for event in renewed:
                await review.record_event(
                    "tool-approval-extension", "approved", "server", event["server_id"], "automatic",
                    reason="관측 기간 안에 도구 이용 이력이 있습니다.",
                    scope={"server": event["server_id"], "tools": event["tools"], "last_use": event["last_use"],
                           "observation_days": tool_sunset.OBSERVATION_DAYS,
                           "window_start": (now - timedelta(days=tool_sunset.OBSERVATION_DAYS)).isoformat(),
                           "from": event["from"], "deadline": event["valid_until"]})
    return renewed


async def apply_risk_grace(now: datetime | None = None) -> list[dict]:
    """Approvals made before risk input existed are assumed to be the highest tier. They stay valid for
    the grace period counted from the first run of this check, then lapse into re-approval through the
    same approval expiry as any other (RQ-08). An approval that carries its stated input is untouched."""
    if registry.RUNTIME_PATH is None:
        return []
    now = now or datetime.now(UTC)
    capped = []
    async with REGISTER_LOCK:
        doc = registry.runtime()
        started = doc.get("risk_tier_grace_started_at")
        if not started:
            started = doc["risk_tier_grace_started_at"] = now.isoformat(timespec="seconds")
            doc["history"].append({"type": "risk-grace-started", "actor": "system", "at": started,
                                   "until": risk_tier.grace_end(started).isoformat(timespec="seconds")})
            capped.append(doc["history"][-1])
        end = risk_tier.grace_end(started)
        for server_id, spec in doc["servers"].items():
            if risk_tier.legacy_review(spec, started, now) is None or not spec.get("valid_until"):
                continue
            until = datetime.fromisoformat(spec["valid_until"])
            if until <= end:
                continue
            spec["valid_until"] = end.isoformat(timespec="seconds")
            event = {"type": "risk-grace-capped", "server_id": server_id, "actor": "system",
                     "at": now.isoformat(timespec="seconds"), "from": until.isoformat(timespec="seconds"),
                     "valid_until": spec["valid_until"]}
            doc["history"].append(event)
            capped.append(event)
        if capped:
            registry.save_runtime(doc)
            await registry.sync()
    return capped


async def catalog_watch() -> None:
    """Background drift watch. Calls themselves re-check the contract on the same
    connection that executes, so this loop only keeps the dashboard and the policy
    input current; it is not what makes execution safe."""
    while True:
        try:
            await refresh_all_catalogs()
            await review.lapse_expired_acceptances()
            await apply_risk_grace()
            await renew_approvals()  # after the refresh: renewal reads the contract it just checked
        except Exception:
            pass
        try:
            await _cleanup_expired_flow_fingerprints()
        except Exception:
            logging.getLogger(__name__).warning("expired flow fingerprint cleanup failed", exc_info=True)
        await asyncio.sleep(CATALOG_REFRESH_SECONDS)


async def _cleanup_expired_flow_fingerprints() -> None:
    """Remove expired comparison data without changing the append-only decision ledger."""
    await db.execute("DELETE FROM flow_fingerprints WHERE expires_at <= now()")


async def _contract(server_id: str, tool_name: str) -> dict:
    server = await db.fetch_one(
        """SELECT s.*, (SELECT reason FROM ops_suspensions x WHERE x.server_id=s.id AND x.resumed_at IS NULL)
                         AS automatic_stop_reason FROM mcp_servers s WHERE s.id=%s""", (server_id,))
    tool = await db.fetch_one(
        "SELECT * FROM mcp_tools WHERE server_id=%s AND name=%s", (server_id, tool_name)
    )
    if not server or not tool or not registry.server(server_id):
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
    # An operator's time-limited acceptance of the intake's critical findings counts while it lasts
    # (D-90); when it runs out the raw count is what the policy sees again.
    critical = await db.fetch_one(
        """SELECT COALESCE(sum(critical_count),0) AS critical_count,
                  (SELECT COALESCE(max(a.critical_count),0) FROM accepted_risks a WHERE a.intake_id=%s::uuid
                      AND a.expires_at>now() AND a.revoked_at IS NULL) AS accepted FROM
           (SELECT DISTINCT ON (scanner, COALESCE(summary->>'evidence_mode', 'live'))
                   critical_count FROM supply_chain_reports
            WHERE source_ref=%s AND scanner <> 'AI-Infra-Guard mcp-scan'
            ORDER BY scanner, COALESCE(summary->>'evidence_mode', 'live'), id DESC) latest_per_scanner""",
        ((registry.server(server_id) or {}).get("intake_id"), server["source_ref"]),
    )
    raw_critical = int(critical["critical_count"]) if critical else 0
    return {
        "registered": True,
        "enabled": bool(tool["enabled"] and server["status"] != "DISABLED"
                        and not server.get("automatic_stop_reason")
                        and not disposal.blocked(server_id=server_id)),
        "schema_hash_match": bool(tool["approved_schema_hash"] and tool["approved_schema_hash"] == tool["observed_schema_hash"]
                                  and output_contract.observed_matches(tool)),
        "description_hash_match": bool(tool["approved_description_hash"] and tool["approved_description_hash"] == tool["observed_description_hash"]),
        "version_match": bool(tool["approved_server_version"] and tool["approved_server_version"] == tool["observed_server_version"]),
        "known_tools_only": selective.available(latest, tool_name),
        "metadata_safe": selective.available(latest, tool_name),
        "supplier_approved": server["status"] != "BLOCKED_SUPPLY_CHAIN",
        "critical_vulnerabilities": 0 if raw_critical <= int(critical["accepted"] or 0) else raw_critical,
        "critical_accepted": raw_critical if 0 < raw_critical <= int(critical["accepted"] or 0) else 0,
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
def untrusted_markers(arguments: dict) -> list[str]:
    found: set[str] = set()
    for key, value in (arguments or {}).items():
        for text in classify._strings(value):
            if poisoning.text_findings(text):
                found.add(str(key))
                break
    return sorted(found)


# CTL-24 / RSK-24. 원격 endpoint가 평문이면 요청·응답이 경로 위에서 읽히고 바뀐다.
# 루프백과 컨테이너 내부 망은 이 판단에서 제외한다 - 거기까지 TLS를 요구하면
# 아무도 지키지 않는 규칙이 하나 더 생긴다.
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _endpoint_host(endpoint: str | None) -> str:
    from urllib.parse import urlsplit
    value = (endpoint or "").strip()
    if not value:
        return ""
    if not value.startswith(("http://", "https://")):
        return ""
    return (urlsplit(value).hostname or "").lower()


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
    if endpoint in registry.runtime_endpoints():
        return True  # 관리자가 Console 등록 절차에서 이 엔드포인트 자체를 승인했다(D-49)
    allowed = await opa_document("egress")
    entries = (allowed or {}).get("allowed_hosts") if isinstance(allowed, dict) else None
    if not isinstance(entries, list):
        return False
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


def _outbound_text(arguments: dict) -> str:
    """Every string the call carries out. Presidio reads it; OPA only gets entity types."""
    parts: list[str] = []

    def walk(value: Any, depth: int = 0) -> None:
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, dict) and depth < 6:
            for item in value.values():
                walk(item, depth + 1)
        elif isinstance(value, list) and depth < 6:
            for item in value[:200]:
                walk(item, depth + 1)

    walk(arguments)
    return "\n".join(parts)


def _privacy_ignore(cls: classify.Classification) -> Callable[[str, str], bool]:
    """A recipient address is where the call goes, not what it discloses; an internal
    colleague's address is not personal data the organisation hides from itself."""
    recipients = {d.value.lower() for d in cls.destinations if d.kind == "email"}
    internal = tuple("@" + domain.lower() for domain in
                     registry.catalog().get("organization", {}).get("internal_email_domains", []))

    def ignore(entity: str, value: str) -> bool:
        value = value.lower()
        return entity == "EMAIL_ADDRESS" and (value in recipients or value.endswith(internal))
    return ignore


async def _sequence_flags(user_token: str, cls: classify.Classification) -> list[str]:
    """P-CHAIN-001 input. v1 linked calls by a signed agent session; v2 links them by the
    verified principal, which a client cannot split by opening new tasks."""
    if not any(d.external for d in cls.destinations):
        return []
    row = await db.fetch_one(
        """SELECT 1 FROM decisions
            WHERE user_token=%s AND data_class='important' AND action='r' AND upstream_executed
              AND created_at > now() - make_interval(mins => %s) LIMIT 1""",
        (user_token, CHAIN_WINDOW_MINUTES))
    return ["sensitive_read_then_send"] if row else []


async def _flow_sources(user_token: str, server_id: str, cls: classify.Classification,
                        provider_hosted: bool = False, outbound_text: str | None = None,
                        observed: dict | None = None, *, connection=None) -> list[str]:
    """POL-33 input: other servers whose important data this principal read in the window.

    The label follows the verified principal, as P-CHAIN-001 does. A write or execution on another
    server inside the window is where that data can cross between servers, and so is any call to a
    provider-hosted server: it receives every argument, a search query included.

    With `outbound_text` the call's text is compared with what was read, and `observed` receives the
    result per server for the decision record (D-142). In "content" mode a server then stays a source
    only when the text matches or the read could not be compared; in "coarse" mode, the default, every
    server in the window stays one and the comparison is a record only. Without `outbound_text`, and
    on any failure of the comparison, every server in the window is a source.
    """
    if cls.action not in {"w", "x"} and not provider_hosted:
        return []
    query = """SELECT d.server_id, f.salt, f.key_id, f.shingles, f.identifiers
             FROM decisions d LEFT JOIN flow_fingerprints f ON f.decision_id=d.id AND f.expires_at > now()
            WHERE d.user_token=%s AND d.server_id<>%s AND d.data_class='important' AND d.action='r' AND d.upstream_executed
              AND d.created_at > now() - make_interval(mins => %s) ORDER BY d.server_id"""
    params = (user_token, server_id, CHAIN_WINDOW_MINUTES)
    rows = (await (await connection.execute(query, params)).fetchall() if connection is not None
            else await db.fetch_all(query, params))
    if outbound_text is None:
        return sorted({row["server_id"] for row in rows})
    sources, seen = await asyncio.to_thread(flow_fingerprint.narrow, rows, outbound_text)
    if observed is not None:
        observed.update(seen)
    return sources if FLOW_MATCH_MODE == "content" else sorted(seen)


async def _dispatch_flow_recheck(connection, user_token: str, server_id: str, policy_input: dict,
                                 arguments: dict) -> str | None:
    """A larger source set invalidates the decision; never silently widen its permission."""
    tool = policy_input["tool"]
    cls = classify.Classification(server_id, tool["name"], base_action=tool["base_action"], action=tool["action"])
    sources = await _flow_sources(user_token, server_id, cls, tool["provider_hosted"],
                                  flow_fingerprint.leaf_text(arguments, keys=True), connection=connection)
    if set(sources) - set(policy_input["request"]["flow_sources"]):
        return "flow"
    return None


async def _remember_flow(user_token: str, server_id: str, decision_id: int, result: dict) -> None:
    """D-142: keep salted hashes of what an important read released, once its decision is recorded.

    Never raises. A read without a row stays a flow source for the whole window (the coarse mark),
    so a failure here over-blocks and never lets a flow through.
    """
    try:
        row = await db.fetch_one(
            "SELECT salt FROM flow_fingerprints WHERE user_token=%s AND expires_at > now() ORDER BY id DESC LIMIT 1",
            (user_token,))
        salt = bytes(row["salt"]) if row else secrets.token_bytes(16)
        shingles, identifiers = await asyncio.to_thread(
            flow_fingerprint.fingerprint, flow_fingerprint.leaf_text(result), salt, flow_fingerprint.MAX_HASHES)
        await db.execute("DELETE FROM flow_fingerprints WHERE expires_at < now()")
        await db.execute(
            """INSERT INTO flow_fingerprints(user_token, server_id, decision_id, salt, key_id, shingles, identifiers, expires_at)
               VALUES (%s,%s,%s,%s,%s,%s::bigint[],%s::bigint[], now() + make_interval(mins => %s))
               ON CONFLICT (decision_id) DO NOTHING""",
            (user_token, server_id, decision_id, salt, flow_fingerprint.KEY_ID, shingles, identifiers, CHAIN_WINDOW_MINUTES))
    except Exception as exc:
        logging.getLogger(__name__).warning("flow fingerprint not stored for decision %s: %s", decision_id, type(exc).__name__)


async def _relationship_scope(server_id: str, cls: classify.Classification) -> dict:
    """D-39: the paper's unit of analysis, applied to every call and not only at termination.

    A server with ACTIVE usage relationships admits the union of their allowed_resources;
    the policy judges a call whose scoped resources fall outside it. Terminating or
    terminated relationships are already refused by MCP-DECOMM-001.
    """
    rows = await db.fetch_all(
        "SELECT id, allowed_resources FROM usage_relationships WHERE server_id=%s AND status='ACTIVE' ORDER BY id",
        (server_id,))
    if not rows:
        return {"defined": False, "ids": [], "in_scope": True, "outside": []}
    allowed = [str(entry) for row in rows for entry in (row["allowed_resources"] or [])]
    outside = classify.outside_scope(cls.resources, allowed)
    return {"defined": True, "ids": [row["id"] for row in rows], "in_scope": not outside, "outside": outside[:20]}


def _risk_score(data_class: str, action: str, external: bool,
                privacy_types: list[str], sequence_flags: list[str]) -> int:
    """0-100 for investigation and sorting. Evidence, never a reason to allow or deny:
    the decision comes from concrete Rego conditions."""
    return min(100, (30 if data_class == "important" else 10 if data_class == "nonimportant" else 0)
               + (20 if action == "x" else 10 if action == "w" else 0)
               + (15 if external else 0) + (25 if privacy_types else 0)
               + (30 if sequence_flags else 0))


async def _reserve_call(request_id: str, user_token: str, server_id: str, tool: str,
                        arguments: dict, data_class: str, action: str = "r") -> dict:
    """Take this call's place in the ceilings, then report where it stands.

    Counting alone cannot hold a ceiling. The counts come from the audit table, which a
    call only reaches once it is over, so calls that arrive together each counted the
    others as absent and the whole batch passed a limit of one. The count and this
    call's own row are therefore written in one transaction, serialised per principal by
    an advisory lock, which is also what makes "how many is this person running right
    now" answerable at all: `decisions` has no row for a call still in flight.

    The lock is per principal, so two people never wait for each other, and it is held
    for one short transaction rather than for the tool call.

    The gateway measures and the policy decides, so the limits travel as part of the
    input rather than as a branch in this function.
    """
    fingerprint = canonical_hash({"server": server_id, "tool": tool, "arguments": arguments})
    async with db.transaction() as connection:
        # hashtext() maps the principal onto the advisory lock space; a collision costs
        # two principals a moment of waiting and never a wrong count.
        await connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (user_token,))
        # An identical write that was sent and never answered counts as still running: its
        # reservation may be long gone (the process died), the downstream effect may not be.
        cursor = await connection.execute(
            f"""SELECT count(*) AS active,
                      count(*) FILTER (WHERE fingerprint = %s) AS same_call,
                      EXISTS (SELECT 1 FROM dispatch_intents i
                               WHERE i.user_token = %s AND i.fingerprint = %s AND i.action IN ('w','x')
                                 AND {dispatch.UNSETTLED}) AS unsettled,
                      EXISTS (SELECT 1 FROM dispatch_intents i
                               WHERE i.user_token = %s AND i.fingerprint = %s
                                 AND %s IN ('w','x') AND {dispatch.REPLAY}) AS replay
                 FROM call_reservations
                WHERE user_token = %s AND released_at IS NULL AND expires_at > now()""",
            (fingerprint, user_token, fingerprint, user_token, fingerprint, action,
             dispatch.IDEMPOTENCY_TTL_SECONDS, user_token))
        open_calls = await cursor.fetchone()
        cursor = await connection.execute(
            """SELECT count(*) FILTER (WHERE decision = 'Block'
                                         AND policy_id = ANY(%s::text[])
                                         AND created_at > now() - make_interval(mins => %s)) AS recent_blocks
               FROM decisions WHERE user_token = %s AND created_at > now() - interval '1 hour'
                AND action <> 'connect'""",
            (list(DENIAL_POLICIES), BLOCK_STREAK_MINUTES, user_token))
        finished = await cursor.fetchone()
        # Count arrivals, including released/crashed calls. Moving a call from the
        # reservation table to the audit ledger must not create a gap or count it twice.
        # The second arm preserves the current window when upgrading an existing DB.
        cursor = await connection.execute(
            """SELECT count(*) FILTER (WHERE created_at > now() - make_interval(secs => %s)) AS recent_calls,
                      count(*) FILTER (WHERE data_class='important' AND created_at > now() - make_interval(mins => %s)) AS recent_important
               FROM (
                 SELECT request_id, created_at, data_class FROM call_reservations
                  WHERE user_token=%s AND created_at > now() - interval '1 hour'
                 UNION ALL
                 SELECT d.request_id, d.created_at, d.data_class FROM decisions d
                  WHERE d.user_token=%s AND d.created_at > now() - interval '1 hour'
                    AND d.action <> 'connect'  -- a refused connection is not a call (D-57)
                    AND NOT EXISTS (SELECT 1 FROM call_reservations r WHERE r.request_id=d.request_id)
               ) arrivals""",
            (RATE_LIMIT_WINDOW_SECONDS, IMPORTANT_BURST_MINUTES, user_token, user_token))
        arrivals = await cursor.fetchone()
        await connection.execute(
            """INSERT INTO call_reservations(request_id, user_token, server_id, tool_name, fingerprint, data_class, expires_at)
               VALUES (%s,%s,%s,%s,%s,%s, now() + make_interval(secs => %s))
               """,
            (request_id, user_token, server_id, tool, fingerprint, data_class, RESERVATION_TTL_SECONDS))
    active = int(open_calls["active"]) + 1  # this call now holds a place too
    return {
        # Prior arrivals only; P-RATE-001 uses >= so the configured limit is inclusive.
        "recent_calls": int(arrivals["recent_calls"]),
        "call_limit": RATE_LIMIT_CALLS,
        "recent_important": int(arrivals["recent_important"]),
        "important_limit": IMPORTANT_BURST_LIMIT,
        # CTL-28 / RSK-27. 한 건의 인가 거부는 오조작이지만 짧은 시간에 쌓인 거부는
        # 권한 경계를 더듬고 있다는 뜻이다. 막지는 않는다 - 막으면 정상 사용자의
        # 오타가 계정 정지가 된다. 증적을 올리고 사람이 본다.
        "recent_blocks": int(finished["recent_blocks"]) if finished else 0,
        "block_limit": BLOCK_STREAK_LIMIT,
        "active_calls": active,
        "concurrency_limit": CONCURRENCY_LIMIT,
        "duplicate_in_flight": (int(open_calls["same_call"]) > 0 or bool(open_calls["unsettled"])
                                or bool(open_calls["replay"])),
        "execution_timeout_ms": int(min(upstream.CONNECT_TIMEOUT, RESERVATION_TTL_SECONDS - 10) * 1000),
    }


async def _release_call(request_id: str, decision_id: int | None = None, intent: str | None = None) -> None:
    """Give the place back. Every exit from execute_call passes through here, and a
    reservation that is somehow never released still expires on its own.

    `intent` is how a sent call ended: "resolved" with a definite answer, "uncertain"
    without one. An uncertain call keeps its place; the intent row, not the reservation,
    is what refuses an identical write afterwards. One statement settles both, so the
    reservation is never freed while the intent still says pending.
    """
    try:
        await db.execute(
            """WITH settled AS (
                 UPDATE dispatch_intents SET state = %(intent)s, decision_id = %(decision)s, resolved_at = now()
                  WHERE request_id = %(id)s AND state = 'pending' AND %(intent)s::text IS NOT NULL)
               UPDATE call_reservations SET released_at = now()
                WHERE request_id = %(id)s AND released_at IS NULL AND %(intent)s::text IS DISTINCT FROM 'uncertain'""",
            {"id": request_id, "intent": intent, "decision": decision_id})
    except Exception:
        logging.getLogger(__name__).exception("call reservation release failed for %s", request_id)


_ledger_cache: dict[str, dict] = {}
OPA_DATA_ROOT = OPA_URL.split("/v1/data/")[0] + "/v1/data"


def _opa() -> httpx.AsyncClient:
    return connections.shared("opa", lambda: httpx.AsyncClient(timeout=5))


async def opa_document(name: str) -> Any:
    """읽기 전용 data 문서 조회. 정책이 실제로 들고 있는 값을 화면에 그대로 보인다."""
    try:
        response = await _opa().get(f"{OPA_DATA_ROOT}/{name}")
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
        response = await _opa().get(POLICY_LEDGER_URL)
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
    response = await _opa().post(OPA_URL, json={"input": input_document})
    response.raise_for_status()
    result = response.json().get("result")
    # Do not include an invalid policy response in the audit error verbatim.
    if not POLICY_RESULT.is_valid(result):
        raise RuntimeError("OPA returned an invalid decision contract")
    restrictions = result["restrictions"]
    enforceable = set(input_document.get("tool", {}).get("restrictable") or [])
    if (result["decision"] == "Restrict" and not restrictions) or not set(restrictions) <= enforceable:
        raise RuntimeError("OPA returned unenforceable restrictions")
    return result


async def _call_upstream(server_id: str, tool: str, arguments: dict, approval_id: str | None = None,
                         principal: str | None = None, *, dispatch_state: dict, pac_payload: dict,
                         laps: _Laps | None = None, _retry_list: bool = True) -> dict:
    """Recheck the contract and call, on one connection.

    Nothing is raised inside the MCP client context on purpose: an exception there is
    wrapped into an ExceptionGroup together with whatever the transport's teardown
    raises, and a "blocked by the contract check" would read as "the call's outcome
    is unknown". The decision is taken after the lease has been released.
    """
    spec = registry.server(server_id)
    if not spec:
        raise DispatchRejected("server is not in the catalog")
    if principal is None:
        raise DispatchRejected("authenticated dispatch principal is required")
    impact = (spec.get("tool_reviews") or {}).get(tool) or {}
    if impact.get("high_impact") or pac_payload.get("impact_scope_sha256"):
        approved = await db.fetch_one("SELECT * FROM approvals WHERE id=%s", (approval_id,)) if approval_id else None
        if not (high_impact.bound(approved, pac_payload, impact, canonical_hash)
                and approved["expires_at"] > datetime.now(UTC)):
            raise DispatchRejected("Human approval required", local_verdict(
                "P-HIGH-IMPACT-001", "Block", "중대 영향 호출의 개별 승인이 없습니다."))
    problem = None
    blocked_verdict = None
    payload: dict | None = None
    laps = laps or _Laps()
    laps.lap("dispatch")
    # The stage an exception interrupts gets the time up to it: a connect, listing or call that
    # fails is the MCP server's time, not the gateway's.
    stage = "connect"
    try:
        async with upstream.session(spec["endpoint"], principal=principal,
                                    protocol=registry.pinned_protocol(server_id), server_id=server_id,
                                    device_id=(pac_payload.get("transport_claims") or {}).get("device_id")) as client:
            if hasattr(client, "bind_evidence"):
                client.bind_evidence(dispatch_state, pac_payload.get('transport_claims') or {})
            protocol_version = str(getattr(client, "protocol_version", "")) or None
            dispatch_state["upstream_connected"] = True
            dispatch_state.setdefault("client", {})["upstream_session_reused"] = bool(getattr(client, "reused", False))
            laps.lap("connect")
            stage = "list"
            listed = await upstream.list_all_tools(client)
            registered = await db.fetch_all("SELECT * FROM mcp_tools WHERE server_id=%s", (server_id,))
            observed = {t.name: upstream.tool_view(t) for t in listed}
            # Same rule as refresh_catalog (D-69): the reviewed contract is what a client can reach — the
            # enabled tools' descriptions and schemas. Hosted servers answer from pods with different build
            # ids, so the version string is not part of it; unexposed helpers may change without blocking.
            enabled_rows = [row for row in registered if row["enabled"] and row["name"] == tool]
            if tool not in observed or not enabled_rows:
                problem = "MCP catalog changed before execution"
            else:
                for row in enabled_rows:
                    item = observed[row["name"]]
                    if (canonical_hash(item["description"]) != row["approved_description_hash"]
                            or canonical_hash(item["input_schema"]) != row["approved_schema_hash"]
                            or not output_contract.matches(row, item.get("output_schema"))):
                        problem = "MCP contract changed before execution"
                        break
                reviewed = spec.get("poisoning_review") or {}
                if (problem is None and not registry.review_matches(reviewed.get(tool), observed[tool])
                        and poisoning.findings(observed[tool])):
                    problem = "MCP tool metadata is unsafe"
            if problem:
                blocked_verdict = local_verdict("MCP-CATALOG-001", "Block", "요청한 도구의 승인 계약을 확인할 수 없습니다.")
            if problem is None and not Draft202012Validator(observed[tool]["input_schema"]).is_valid(arguments):
                problem = "Arguments do not match the approved input schema"
            laps.lap("list")
            stage = "recheck"
            if problem is None and approval_id is not None:
                # Discovery may take longer than the remaining approval lifetime.
                approval = await db.fetch_one("SELECT status, expires_at FROM approvals WHERE id=%s", (approval_id,))
                if (not approval or approval["status"] != "APPROVED"
                        or approval["expires_at"] <= datetime.now(UTC)):
                    problem = "Approval expired or was withdrawn before execution"
                if problem is None:
                    # Stored claims passed ingress once; approval does not undo a later logout or disposal.
                    try:
                        claims = pac_payload.get("transport_claims") or {}
                        revoked = disposal.blocked(jti=claims.get("jti"), raise_errors=True) or bool(await db.fetch_one(
                            "SELECT jti FROM agent_revoked_tokens WHERE jti=%s", (claims.get("jti"),)))
                    except Exception:
                        problem, blocked_verdict = "Requester revocation check unavailable", local_verdict(
                            "P-CONTROL-FAIL-CLOSED", "Block", "요청자 인증의 철회 상태를 확인하지 못해 실행을 차단했습니다.")
                    else:
                        if revoked:
                            problem, blocked_verdict = "Requester token revoked before dispatch", local_verdict(
                                "P-INPUT-001", "Block", "폐기되었거나 철회된 요청자 인증입니다.")
            if problem is None:
                person = await db.fetch_one("SELECT * FROM principals WHERE token=%s", (principal,))
                from .endpoint_plane import managed_failure
                failure = await managed_failure(person or {}, pac_payload.get("transport_claims") or {}, server=server_id)
                if failure:
                    problem = failure
                    blocked_verdict = local_verdict("ENDPOINT-MANAGED-001", "Block", failure)
                if not person or person["status"] != "active":
                    problem = "Principal was revoked before dispatch"
                elif not failure:
                    final_input = dict(dispatch_state["policy_input"])
                    final_input["now"] = datetime.now(UTC).isoformat()
                    live = next(row for row in registered if row["name"] == tool)
                    # The description and schema were just matched above; the build id this connection
                    # happened to report is not part of the reviewed contract (D-69).
                    live = {**live, "observed_server_version": live["approved_server_version"],
                            "observed_description_hash": canonical_hash(observed[tool]["description"]),
                            "observed_schema_hash": canonical_hash(observed[tool]["input_schema"])}
                    original = pac_payload["arguments"]
                    final_input["contract"] = await _contract(server_id, tool)
                    final_input["pac"] = await pac.build(
                        pac_payload, person, classify.classify(server_id, tool, original, principal), live,
                        final_input["contract"], final_input["context"], dispatch_state["request_id"],
                        GATEWAY_ENVIRONMENT, approval_id)
                    dispatch_state["policy_input"] = final_input
                    try:
                        verdict = await _policy(final_input)
                    except Exception:
                        verdict = local_verdict("P-CONTROL-FAIL-CLOSED", "Block", "실행 직전 PAC 재검증에 실패했습니다.")
                    if verdict["decision"] not in {"Allow", "Alert", "Restrict"}:
                        problem, blocked_verdict = "PAC changed before dispatch", verdict
                    elif verdict.get("restrictions", {}) != dispatch_state.get("restrictions", {}):
                        problem = "Restrictions changed before dispatch"
            laps.lap("recheck")
            if problem is None:
                stage = "intent"
                # The last transaction before the send: past this line a cutover or a
                # revocation no longer stops this call, so it is on record that it may have gone out.
                async def recheck(connection):
                    return await _dispatch_flow_recheck(connection, principal, server_id,
                                                        dispatch_state["policy_input"], pac_payload["arguments"])
                try:
                    refused = await dispatch.record(dispatch_state["request_id"], dispatch_state["action"], approval_id,
                                                     recheck=recheck)
                except Exception:
                    refused = "control"
                if refused == "control":
                    problem, blocked_verdict = "Final dispatch checks unavailable", local_verdict(
                        "P-CONTROL-FAIL-CLOSED", "Block", "전송 직전 확인을 완료하지 못해 실행을 차단했습니다.")
                elif refused == "terminated":
                    problem, blocked_verdict = "Server entered termination before dispatch", local_verdict(
                        "MCP-DECOMM-001", "Block", "종료·폐기 절차에 들어간 이용 관계입니다. 실행하지 않습니다.")
                elif refused == "principal":
                    problem, blocked_verdict = "Principal was revoked before dispatch", local_verdict(
                        "P-INPUT-001", "Block", "활성 상태의 등록 계정이 아닙니다.")
                elif refused == "suspended":
                    problem, blocked_verdict = "Server suspended before dispatch", local_verdict(
                        "MCP-REGISTRY-002", "Block", "자동 중지된 서버입니다.")
                elif refused == "user-suspended":
                    problem, blocked_verdict = "Use suspended before dispatch", local_verdict(
                        "P-SUSPEND-001", "Block", "관리자가 이 사용자의 이 서버 이용을 중지했습니다. 계정은 그대로이며 재개되면 다시 사용할 수 있습니다.")
                elif refused == "contract":
                    problem, blocked_verdict = "Tool restricted before dispatch", local_verdict(
                        "MCP-CATALOG-001", "Block", "요청한 도구의 승인 계약을 확인할 수 없습니다.")
                elif refused == "impact":
                    problem, blocked_verdict = "Human approval changed before dispatch", local_verdict(
                        "P-HIGH-IMPACT-001", "Block", "중대 영향 호출의 승인 또는 심사 범위가 유효하지 않습니다.")
                elif refused == "consent":
                    problem, blocked_verdict = "Consent changed before dispatch", local_verdict(
                        "P-CONSENT-001", "Block", "이 도구의 데이터 이용에 유효한 사용자 동의가 없습니다.")
                elif refused == "flow":
                    problem, blocked_verdict = "Flow sources changed before dispatch", local_verdict(
                        "P-FLOW-001", "Block", "중요정보 열람 이력이 변경되어 다시 판정해야 합니다.")
                elif refused == "approval":
                    problem = "Approval expired or was withdrawn before execution"
                elif refused == "duplicate":
                    problem, blocked_verdict = "Duplicate write at dispatch", local_verdict(
                        "P-RATE-003", "Block", "같은 변경 호출의 전송 이력이 있어 다시 실행하지 않습니다.")
                elif refused:
                    problem = "call reservation expired before dispatch"
                laps.lap("intent")
            if problem is None:
                stage = "call"
                dispatch_state["upstream_attempted"] = True
                result = await client.call_tool(tool, arguments)
                laps.lap("call")
                # A definite MCP response was received. Later conversion/teardown failure
                # withholds that response rather than erasing the known execution state.
                dispatch_state["upstream_executed"] = True
                payload = {"content": upstream.content_items(result), "is_error": bool(result.is_error)}
                # Only an approved output schema is enforced; an unpinned legacy approval is not (D-149).
                dispatch_state["_output_schema"] = (observed[tool].get("output_schema")
                                                    if all(r.get("approved_output_schema_hash") for r in enabled_rows) else None)
                if result.structured_content is not None or "structured_content" in getattr(result, "model_fields_set", set()):
                    payload["structured"] = result.structured_content
                dispatch_state.setdefault("client", {})["upstream_protocol_version"] = protocol_version
            if problem is not None:
                await upstream.release_pool(spec["endpoint"], principal, "dispatch-recheck")
            stage = "close"
    except BaseException as exc:
        laps.lap(stage)
        if stage == "list" and _retry_list and upstream.session_terminated(exc):
            return await _call_upstream(server_id, tool, arguments, approval_id, principal,
                                        dispatch_state=dispatch_state, pac_payload=pac_payload, laps=laps,
                                        _retry_list=False)
        raise
    laps.lap("close")
    if problem:
        raise DispatchRejected(problem, blocked_verdict)
    # Off the event loop: the native rule engine releases the GIL while it matches.
    guarded = await asyncio.to_thread(_guarded_result, payload or {"content": [], "is_error": True},
                                      protocol_version, dispatch_state.get("_output_schema"))
    laps.lap("inspect_out")
    return guarded


def _root_cause(exc: BaseException) -> str:
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    if isinstance(exc, local_jobs.LocalExecutionError):
        return str(exc)
    # SDK/provider/schema exceptions may quote response values or credentials.
    # Public MCP responses, audit rows and diagnostics retain the type only.
    return f"{type(exc).__name__}: 요청 처리를 완료하지 못했습니다."


def _storable(value: Any) -> Any:
    """The value with U+0000 replaced by U+FFFD in every string and key (PostgreSQL holds neither)."""
    if isinstance(value, str):
        return value.replace("\x00", "�")
    if isinstance(value, dict):
        return {_storable(key): _storable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_storable(item) for item in value]
    return value


def _decoded_strings(payload: Any) -> list[str]:
    strings, pending = [], [payload]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            strings.append(item)
        elif isinstance(item, dict):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    return strings


def _upstream_failure(exc: Exception, event: dict) -> dict:
    executed = bool(event.get("upstream_executed"))
    attempted = bool(event.get("upstream_attempted"))
    pending = [exc]
    seen = set()
    while pending:
        error = pending.pop()
        if id(error) in seen:
            continue
        seen.add(id(error))
        if getattr(error, 'local_policy', None):
            return local_verdict(error.local_policy, 'Block', str(error), upstream_executed=executed,
                                 upstream_attempted=attempted, result=None,
                                 result_evidence={'disposition':'unknown' if attempted else 'not_executed'})
        if isinstance(error, output_contract.WireRejected):
            return local_verdict("MCP-OUTPUT-001", "Block", "협상된 출력 형식과 일치하지 않아 결과를 보류했습니다.",
                                 upstream_executed=True, upstream_attempted=True, result=None,
                                 result_evidence={"disposition": "withheld"})
        if isinstance(error, output_contract.OutputSchemaTooComplex):
            return local_verdict("MCP-CATALOG-001", "Block", "도구 출력 스키마의 검사 한도를 초과했습니다.",
                                 upstream_executed=executed, upstream_attempted=attempted, result=None,
                                 result_evidence={"disposition": "withheld" if executed else "not_executed"})
        if isinstance(error, httpx.HTTPStatusError):
            event["upstream_http_status"] = error.response.status_code
        if isinstance(error, DestinationBlocked):
            return local_verdict(error.policy_id, "Block", "연결 목적지 주소 검사에 실패하여 연결을 차단했습니다.",
                                 upstream_executed=executed, upstream_attempted=attempted, result=None,
                                 result_evidence={"disposition": "withheld" if executed else "unknown" if attempted else "not_executed"},
                                 error=_root_cause(error))
        pending.extend(getattr(error, "exceptions", ()))
        if error.__cause__ is not None:
            pending.append(error.__cause__)
    return local_verdict("MCP-UPSTREAM-001", "Block",
                         "허용 후 MCP 처리를 완료하지 못했습니다. 실제 실행 여부는 하위 시스템 증거와 함께 확인해야 합니다.",
                         restrictions=event.get("restrictions") or {}, exception=event.get("exception"),
                         upstream_executed=executed, upstream_attempted=attempted, result=None,
                         result_evidence={"disposition": "withheld" if executed else "unknown" if attempted else "not_executed"},
                         error=_root_cause(exc))


def body_of(value) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def _validate_output(payload: dict, schema) -> None:
    # A tool error carries only its message; the official SDKs skip the output schema there,
    # and withholding it would hide the reason the model needs to retry. Structured data on an
    # error is still checked.
    if schema is None or payload.get("is_error") and "structured" not in payload:
        return
    try:
        output_contract.check_schema_bounds(schema)
        validator_class = validator_for(schema, default=None) if "$schema" in schema else Draft202012Validator
        if validator_class is None:
            raise ValueError("unsupported output schema dialect")
        validator_class.check_schema(schema)
        # No implicit network/filesystem resolution of provider-controlled $ref.
        validator = validator_class(schema, registry=Registry())
        if "structured" not in payload or not validator.is_valid(payload["structured"]):
            raise ValueError("output contract mismatch")
    except Exception as exc:
        # Validator errors contain response values; only a fixed reason may leave here.
        raise ResultRejected("승인된 출력 스키마와 도구 결과가 일치하지 않아 보류했습니다.", payload) from exc


def _guarded_result(payload: dict, protocol_version: str | None = None, output_schema=None) -> dict:
    """Upstream output is untrusted input too.

    A pinned description and schema say nothing about what a server returns at
    runtime, and that is where an injected instruction or an oversized blob arrives.
    """
    try:
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ResultRejected("도구 결과가 유효한 JSON이 아닙니다.") from exc
    if len(body.encode()) > MAX_RESULT_BYTES:
        raise ResultRejected(f"도구 결과가 {MAX_RESULT_BYTES} byte 상한을 넘었습니다.", payload)
    if classify.result_items(payload) > MAX_RESULT_ITEMS:
        raise ResultRejected(f"도구 결과가 {MAX_RESULT_ITEMS}건 상한을 넘었습니다.", payload)
    content = payload.get("content")
    if not isinstance(content, list) or any(not isinstance(item, dict) for item in content):
        raise ResultRejected("도구 결과의 content 구조가 MCP 형식이 아닙니다.", payload)
    _validate_output(payload, output_schema)
    payload = output_contract.for_protocol(payload, protocol_version)
    content = payload["content"]
    if any(item.get("type") != "text" for item in content):
        raise ResultRejected("반환하지 않는 결과 형식입니다.", payload)
    if any(not isinstance(item.get("text"), str) for item in content):
        raise ResultRejected("text 결과에 문자열 본문이 없습니다.", payload)
    # JSON escapes newlines; inspect decoded strings too so line-boundary rules survive serialization.
    text = [body, *_decoded_strings(payload)]
    if reasons := poisoning.result_findings("\n".join(text)):
        raise ResultRejected(f"도구 결과에 모델을 조종하는 지시가 포함되어 있습니다: {', '.join(reasons)}", payload)
    return payload


async def _inspected_result(payload: dict, ignore: privacy.Ignore | None = None) -> tuple[dict, list[str]]:
    """Inspect every representation that the MCP facade can release."""
    try:
        async with asyncio.timeout(OUTPUT_INSPECTION_TIMEOUT_SECONDS):
            result, kinds = await privacy.mask_payload(payload, ignore)
            # Assignment rules need key/value context and line rules decoded text.
            scan = "\n".join([json.dumps(result, ensure_ascii=False, allow_nan=False), *_decoded_strings(result)])
            if remaining := await secret_scan.labels(scan):
                raise ResultRejected("응답에 마스킹되지 않은 Secret이 있어 보류했습니다: " + ", ".join(remaining), payload)
            # Masking can expand text; the released representation must fit too.
            if len(json.dumps(result, ensure_ascii=False).encode()) > MAX_RESULT_BYTES or classify.result_items(result) > MAX_RESULT_ITEMS:
                raise ResultRejected("검사 후 도구 결과가 반환 상한을 넘었습니다.", result)
            return result, kinds
    except TimeoutError as exc:
        raise privacy.InspectionUnavailable("출력 검사의 전체 대기·처리 기한을 초과했습니다.") from exc


def _audit_payload(payload: dict) -> dict:
    """Structure stays readable; long text becomes a digest.

    Mail bodies, file contents and SQL results are evidence of *what kind* of call it
    was, not something the audit table should hold a second copy of.
    """
    def shrink(value: Any, depth: int = 0) -> Any:
        if isinstance(value, str) and len(value) > 300:
            return {"sha256": canonical_hash(value), "chars": len(value), "head": value[:120]}
        if isinstance(value, dict) and depth < 4:
            return {k: shrink(v, depth + 1) for k, v in value.items()}
        if isinstance(value, list) and depth < 4:
            return [shrink(v, depth + 1) for v in value[:50]]
        return value
    return shrink(payload)


# The chain is appended under a row lock, so decision writes serialise on one row.
# That is the right trade for a single gateway; a multi-replica deployment wants one
# chain per instance, anchored together.
async def _record_decision(event: dict) -> int:
    event["outcome"] = outcome_axes(event)
    event["error"] = await secret_scan.redact_error(event.get("error"))
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
        # The response itself is not kept: digest, size, content types and what happened to it.
        "result_preview": event.get("result_evidence") or {"disposition": response_disposition(event)},
        "error": event.get("error"),
        "enforcement": event.get("enforcement") or "enforce",
        "would_decision": event.get("would_decision"),
        "would_policy_id": event.get("would_policy_id"),
        "policy_version": event.get("policy_version") or "unknown",
        "obligations": event.get("obligations") or [],
        "exception_id": (event.get("exception") or {}).get("id"),
        "conflicts": event.get("conflicts") or [],
        "environment": event.get("environment") or GATEWAY_ENVIRONMENT,
        "server_id": event.get("server_id"),
        "resource_id": event.get("resource_id"),
        "destinations": event.get("destinations") or [],
        "client": event.get("client") or {},
        "summary": event.get("summary"),
        "policy_input": event.get("policy_input"),
        "risk_score": int(event.get("risk_score") or 0),
        "privacy_types": event.get("privacy_types") or [],
        "sequence_flags": event.get("sequence_flags") or [],
        "outcome": event["outcome"],
    }
    # An upstream answer or error text can carry U+0000, which PostgreSQL refuses: the row would be
    # lost after the call ran. It is replaced before the fingerprint, so the chain covers what is stored.
    record = _storable(record)
    async with db.transaction() as connection:
        # Use dispatch's principal lock before appending a qualifying denial. A
        # call reaching the threshold commits its suspension before the next
        # call can reserve or dispatch for this employee.
        counts_for_suspend = (record["decision"] == "Block"
                              and record["policy_id"] in AUTO_SUSPEND_POLICIES
                              and record["user_token"] != "unknown" and record["server_id"])
        if counts_for_suspend or (record["data_class"] == "important" and record["action"] == "r"
                                  and record["upstream_executed"]):
            await connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (record["user_token"],))
        cursor = await connection.execute("SELECT head_sha256 FROM audit_chain WHERE id=1 FOR UPDATE")
        head = await cursor.fetchone()
        previous = head["head_sha256"] if head else GENESIS
        record["created_at"] = datetime.now(UTC)
        entry = hashlib.sha256((previous + _audit_fingerprint(record)).encode()).hexdigest()
        cursor = await connection.execute(
            """INSERT INTO decisions(
                 request_id, trace_id, user_token, role, tool_name, data_class, action,
                 decision, policy_id, reason, upstream_executed, restrictions,
                 approval_id, request_payload, result_preview, error,
                 enforcement, would_decision, would_policy_id,
                 policy_version, obligations, exception_id, conflicts, environment,
                 prev_sha256, entry_sha256, chain_version, upstream_attempted,
                 server_id, resource_id, destinations, client, summary,
                 policy_input, risk_score, privacy_types, sequence_flags, created_at, timings, outcome)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING id""",
            (
                record["request_id"], record["trace_id"], record["user_token"], record["role"],
                record["tool_name"], record["data_class"], record["action"], record["decision"],
                record["policy_id"], record["reason"], record["upstream_executed"],
                Jsonb(record["restrictions"]), record["approval_id"],
                Jsonb(record["request_payload"]),
                Jsonb(record["result_preview"]) if record["result_preview"] is not None else None,
                record["error"], record["enforcement"], record["would_decision"],
                record["would_policy_id"],
                record["policy_version"], Jsonb(record["obligations"]), record["exception_id"],
                Jsonb(record["conflicts"]), record["environment"],
                previous, entry, CHAIN_VERSION, record["upstream_attempted"],
                record["server_id"], record["resource_id"], Jsonb(record["destinations"]),
                Jsonb(record["client"]), record["summary"],
                Jsonb(record["policy_input"]) if record["policy_input"] is not None else None,
                record["risk_score"], Jsonb(record["privacy_types"]), Jsonb(record["sequence_flags"]),
                # Operational, outside the fingerprint: how long each stage took, not what was decided.
                record["created_at"], Jsonb(event["timings"]) if event.get("timings") else None,
                Jsonb(record["outcome"]),
            ),
        )
        row = await cursor.fetchone()
        await connection.execute(
            "UPDATE audit_chain SET head_sha256=%s, entries=entries+1, updated_at=now() WHERE id=1",
            (entry,),
        )
        if counts_for_suspend:
            # D-176: the suspension check is a consequence of this Block, not a condition of recording it.
            # A failure rolls back only this savepoint; the Block row stays in the append-only ledger, and
            # the check runs again on the next qualifying call, which counts this row too.
            try:
                async with connection.transaction():
                    await user_suspend.auto_suspend(
                        connection, record["user_token"], record["server_id"], AUTO_SUSPEND_POLICIES,
                        AUTO_SUSPEND_THRESHOLD, AUTO_SUSPEND_WINDOW_SECONDS, AUTO_SUSPEND_DURATION_SECONDS)
            except Exception:
                logging.getLogger(__name__).exception(
                    "automatic suspension check failed; decision %s stays Block", row["id"])
                # The failure is a ledger fact: an append after the rolled-back savepoint, with its own
                # savepoint so that a failure to write it cannot roll back the Block row either.
                try:
                    async with connection.transaction():
                        await review.record_event(
                            "auto-suspend-count-failed", "recorded", "decision", row["id"], "automatic",
                            reason="자동 중지 집계 실패",
                            scope={"decision_id": int(row["id"]), "user": record["user_token"],
                                   "server": record["server_id"], "policy_id": record["policy_id"]},
                            connection=connection)
                except Exception:
                    logging.getLogger(__name__).exception(
                        "automatic suspension failure not recorded; decision %s stays Block", row["id"])
    return int(row["id"])


CONNECTION_DENIAL_WINDOW_SECONDS = 60
CONNECTION_DENIALS_PER_WINDOW = 20


async def record_connection_denial(user: dict, server_id: str | None, method: str, client: dict, *,
                                  policy_id: str = "MCP-REGISTRY-001",
                                  reason: str = "등록·승인되지 않은 MCP 경로의 연결을 차단했습니다.",
                                  summary: str = "미등록 MCP 연결 차단") -> int | None:
    """A refused connection is evidence too; it is not a tools/call execution.

    One harness start sends initialize, GET and discovery to the same path, and a stale
    config retries on every start. The first refusal per principal and path per minute
    stands for the rest, and a principal spraying paths stops adding rows after 20 a
    minute; the 404 is returned either way. Every row takes the audit-chain lock, so an
    unbounded path here would let one token slow down every other decision.
    """
    server_id = server_id[:120] if server_id else None  # None: the aggregate endpoint
    seen = await db.fetch_one(
        """SELECT max(id) FILTER (WHERE server_id=%s) AS same, count(*) AS n FROM decisions
            WHERE user_token=%s AND action='connect' AND created_at > now() - make_interval(secs => %s)""",
        (server_id, user["principal"], CONNECTION_DENIAL_WINDOW_SECONDS))
    if seen and seen["same"]:
        return int(seen["same"])
    if seen and seen["n"] >= CONNECTION_DENIALS_PER_WINDOW:
        return None
    await policy_ledger()
    event = {
        "request_id": str(uuid.uuid4()), "trace_id": "connection-" + uuid.uuid4().hex,
        "user_token": user["principal"], "role": user["roles"][0],
        "server_id": server_id, "tool_name": method[:80],
        # Nothing was read or sent; the class only fills the column. Ceilings skip
        # action='connect' rows (_reserve_call), so this never counts as an access.
        "data_class": "public", "action": "connect", "upstream_executed": False,
        "upstream_attempted": False, "client": {**client, "event_kind": "mcp-connection"},
        "request_payload": {"server_id": server_id, "method": method[:80]},
        "summary": summary,
        **local_verdict(policy_id, "Block", reason),
    }
    return await _record_decision(event)


async def verify_audit_chain(connection=None, seal: dict | None = None) -> dict:
    """Walk the chain and name the first row that does not follow from the previous.

    An edited or deleted row cannot be made to fit again without rewriting every row
    after it, so this answers "was the audit log tampered with" with a row id rather
    than with an assurance. A retention seal (D-141, signed outside the database) is the
    only thing that lets the walk start after GENESIS; a row it covers is resurrected.
    """
    if seal is None:
        seal = retention.current_seal()
    if connection is None:
        async with db.transaction() as snapshot:
            await snapshot.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            return await verify_audit_chain(snapshot, seal)
    rows = await (await connection.execute(
        "SELECT id, " + ", ".join(AUDIT_COLUMNS) + ", prev_sha256, entry_sha256, chain_version"
        " FROM decisions ORDER BY id"
    )).fetchall()
    head = await (await connection.execute("SELECT head_sha256, entries FROM audit_chain WHERE id=1")).fetchone()
    return walk_chain(rows, head, seal)


async def _decision_payload(event: dict, laps: _Laps) -> dict:
    event["timings"] = laps.view()
    decision_id = await _record_decision(event)
    # Keep the reservation until the decision is durably recorded. If persistence
    # fails, its TTL keeps the unconfirmed call counted instead of allowing a retry
    # (and the pending intent turns uncertain once the reservation is gone).
    if event.get("request_id"):
        attempted = bool(event.get("upstream_attempted"))
        intent = ('confirmed_not_executed' if not attempted and (event.get('client') or {}).get('local_execution')
                  else None if not attempted else 'resolved' if event.get('upstream_executed') else 'uncertain')
        await _release_call(event["request_id"], decision_id,
                            intent)
    return {**event, "decision_id": decision_id, "latency_ms": int((time.perf_counter() - laps.started) * 1000)}


async def execute_call(payload: dict, approval_granted: bool = False, approval_id: str | None = None) -> dict:
    """One tools/call through the enforced path.

    payload: {"server_id", "tool", "arguments", "user_token", "client"}. Identity is
    the verified transport principal placed in user_token by the ingress; nothing in
    `arguments` is ever read as identity.
    """
    laps = _Laps()
    request_id = str(uuid.uuid4())
    server_id = str(payload.get("server_id") or "")
    tool = str(payload.get("tool") or "")
    arguments = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {}
    user_token = str(payload.get("user_token") or "")
    with tracer.start_as_current_span("mcp.gateway.call", record_exception=False, set_status_on_exception=False) as span:
        trace_id = f"{span.get_span_context().trace_id:032x}"
        cls = classify.classify(server_id, tool, arguments, user_token)
        suspension_error = None
        suspend_module = globals().get("user_suspend")
        expire_suspension = getattr(suspend_module, "expire", None)
        if expire_suspension:
            try:
                await expire_suspension(user_token, server_id)
            except Exception as exc:
                suspension_error = exc
        # An administrator's stop (DEV-79) and a live automatic stop share the same state row.
        principal = (None if suspension_error else await db.fetch_one(
            """SELECT p.*, EXISTS (SELECT 1 FROM user_server_suspensions u WHERE u.user_token=p.token
                                    AND u.server_id=%s AND u.resumed_at IS NULL) AS server_suspended
                 FROM principals p WHERE p.token=%s""", (server_id, user_token)))
        role = principal["role"] if principal else "unknown"
        for key, value in (("mcp.server", server_id), ("mcp.tool", tool), ("mcp.role", role),
                           ("mcp.data_class", cls.data_class), ("mcp.action", cls.action)):
            span.set_attribute(key, value)

        base_event = {
            "request_id": request_id, "trace_id": trace_id, "user_token": user_token or "unknown",
            "role": role, "server_id": server_id, "tool_name": tool,
            "data_class": cls.data_class, "action": cls.action,
            "resource_id": cls.primary.id, "destinations": [d.view() for d in cls.destinations],
            "client": payload.get("client") or {}, "summary": cls.summary(),
            "classification": {"resources": [r.view() for r in cls.resources], "dlp": cls.dlp,
                               "notes": cls.notes, "base_action": cls.base_action},
            "upstream_executed": False, "upstream_attempted": False,
            "enforcement": "enforce", "would_decision": None, "would_policy_id": None,
            "approval_id": approval_id, "request_payload": {"server_id": server_id, "tool": tool, "arguments": arguments},
            "result": None, "error": None,
            "policy_input": None, "risk_score": 0, "privacy_types": [], "sequence_flags": [],
        }

        if suspension_error:
            base_event.update(local_verdict(
                "P-CONTROL-FAIL-CLOSED", "Block", "사용자 중지 상태를 확인할 수 없어 실행하지 않았습니다.",
                error=_root_cause(suspension_error)))
            return await _decision_payload(base_event, laps)

        await policy_ledger()
        if not principal or principal["status"] != "active":
            base_event.update(local_verdict("P-INPUT-001", "Block", "활성 상태의 등록 계정이 아닙니다."))
            return await _decision_payload(base_event, laps)

        if not registry.server(server_id):
            base_event.update(local_verdict("MCP-REGISTRY-001", "Block", "검토된 카탈로그나 승인 도입 신청에 없는 서버입니다."))
            return await _decision_payload(base_event, laps)

        from .endpoint_plane import managed_failure
        failure = await managed_failure(principal, payload.get("transport_claims") or {}, server=server_id)
        if failure:
            base_event.update(local_verdict("ENDPOINT-MANAGED-001", "Block", failure))
            return await _decision_payload(base_event, laps)
        allowed = registry.allowed_principals(server_id)
        if allowed is not None and user_token not in allowed:
            base_event.update(local_verdict("MCP-REGISTRY-003", "Block",
                "이 서비스의 도입 승인 사용 주체에 포함되지 않습니다." if allowed else
                "도입 신청·승인 기록이 없는 직접 등록입니다. 도입 신청으로 다시 등록해야 실행합니다."))
            return await _decision_payload(base_event, laps)
        sunset = await tool_sunset.check(server_id, tool)
        sunset_verdict = tool_sunset.call_verdict(sunset)
        if sunset_verdict:
            base_event.update(local_verdict(sunset_verdict[0], "Block", sunset_verdict[1]))
            return await _decision_payload(base_event, laps)
        if principal.get("server_suspended"):
            base_event.update(local_verdict(
                "P-SUSPEND-001", "Block", "관리자가 이 사용자의 이 서버 이용을 중지했습니다. 계정은 그대로이며 재개되면 다시 사용할 수 있습니다."))
            return await _decision_payload(base_event, laps)
        laps.lap("identity")

        # Reserved before any check that can pass, so a burst cannot race past the
        # ceilings while each of its calls is being classified. A store that cannot
        # answer is not an empty ceiling: without a reservation there is no basis for
        # the numbers the policy is about to judge.
        try:
            context = await _reserve_call(request_id, user_token, server_id, tool, arguments, cls.data_class, cls.action)
        except Exception as exc:
            base_event.update(local_verdict(
                "P-CONTROL-FAIL-CLOSED", "Block",
                "호출 예약 상태 저장소를 사용할 수 없어 실행하지 않았습니다.", error=_root_cause(exc)))
            return await _decision_payload(base_event, laps)
        laps.lap("reserve")

        # A schema rarely bounds length, and the arguments go to the provider as they are:
        # a 200 KB string reached an outside provider before it refused it (D-59, pj1).
        if len(json.dumps(arguments, ensure_ascii=False).encode()) > MAX_ARGUMENT_BYTES:
            base_event.update(local_verdict(
                "P-INPUT-SCHEMA-001", "Block", f"도구 인자가 {MAX_ARGUMENT_BYTES // 1024}KB를 넘어 보내지 않았습니다."))
            return await _decision_payload(base_event, laps)
        # PostgreSQL text and jsonb cannot hold U+0000: a call carrying it could not be recorded as it was
        # sent, so it is not sent.
        if any("\x00" in value for value in _decoded_strings(arguments)):
            base_event.update(local_verdict(
                "P-INPUT-SCHEMA-001", "Block", "도구 인자에 기록할 수 없는 NUL 문자가 있어 보내지 않았습니다."))
            return await _decision_payload(base_event, laps)

        tool_row = await db.fetch_one("SELECT * FROM mcp_tools WHERE server_id=%s AND name=%s", (server_id, tool))
        # Arguments are checked against the approved schema before the policy sees
        # them. The same check runs again on the live schema right before dispatch.
        if tool_row and tool_row.get("input_schema") and tool_row["enabled"]:
            if not Draft202012Validator(tool_row["input_schema"]).is_valid(arguments):
                base_event.update(local_verdict(
                    "P-INPUT-SCHEMA-001", "Block", "도구 인자가 승인된 입력 형식과 다릅니다."))
                return await _decision_payload(base_event, laps)
        # What the reviewer scoped for this tool (D-91): inputs, masking, transfer grade, flows, consent.
        tool_review = ((registry.server(server_id) or {}).get("tool_reviews") or {}).get(tool) or {}
        if tool_review.get("inputs") is not None and (outside := sorted(set(arguments) - set(tool_review["inputs"]))):
            base_event.update(local_verdict(
                "P-INPUT-FIELD-001", "Block", "승인된 입력 항목 밖의 인자는 보내지 않습니다: " + ", ".join(outside[:10])))
            return await _decision_payload(base_event, laps)
        laps.lap("schema")

        if cls.action == "r" and (reason := classify.bulk_read_reason(server_id, tool, arguments, MAX_RESULT_ITEMS)):
            base_event.update(local_verdict("P-VOLUME-002", "Block", reason))
            return await _decision_payload(base_event, laps)

        # PDF 8~10쪽. What leaves the organisation is inspected before the policy sees
        # the call; if the inspection cannot run, the call does not either.
        external = any(d.external for d in cls.destinations)
        # A provider-hosted server receives every argument, reads included: a search
        # query sent to GitHub has left the organisation whatever the tool's action is.
        server_spec = registry.server(server_id) or {}
        provider_hosted = (server_spec.get("deployment") == "provider"
                           or classify.url_destination(server_spec.get("endpoint")).external)
        ignore = _privacy_ignore(cls)
        outbound, masked_types = arguments, []
        try:
            if cls.action in {"w", "x"} or external or provider_hosted:
                secrets_found = await secret_scan.labels(json.dumps(arguments, ensure_ascii=False))
                cls.dlp = sorted(set(cls.dlp) | set(secrets_found))
                base_event["classification"]["dlp"] = cls.dlp
            findings = (await privacy.analyze(_outbound_text(arguments), ignore)
                        if cls.action in {"w", "x"} or external or provider_hosted else [])
            if tool_review.get("mask"):
                # POL-31: what Presidio finds is replaced before it leaves; the policy judges what is sent.
                # Masking runs string by string, so the masked whole is analysed again: a value found only
                # in the context of other fields would otherwise leave as "masked".
                outbound, masked_types = await privacy.mask_payload(arguments, ignore)
                residual = await privacy.analyze(_outbound_text(outbound), ignore)
        except privacy.InspectionUnavailable as exc:
            base_event.update(local_verdict(
                "P-DATA-INSPECTION-001", "Block", "민감정보 검사를 완료하지 못해 실행을 차단했습니다.",
                error=str(exc)))
            return await _decision_payload(base_event, laps)
        laps.lap("inspect_in")
        privacy_types = sorted({item["entity_type"] for item in findings})
        sent_types = (sorted({item["entity_type"] for item in residual}) if tool_review.get("mask")
                      else privacy_types)
        sequence_flags = await _sequence_flags(user_token, cls)
        flow_observed: dict[str, str] = {}
        flow_sources = await _flow_sources(user_token, server_id, cls, provider_hosted,
                                           flow_fingerprint.leaf_text(arguments, keys=True), flow_observed)
        base_event.update(privacy_types=privacy_types, sequence_flags=sequence_flags,
                          risk_score=_risk_score(cls.data_class, cls.action, external,
                                                 privacy_types, sequence_flags + flow_sources))

        contract = await _contract(server_id, tool)
        policy_input = {
            # §11.6 환경정보와 상황정보. 시각은 Gateway가 재고 정책이 판단한다.
            "environment": GATEWAY_ENVIRONMENT,
            "now": datetime.now(UTC).isoformat(),
            "principal": {
                "role": role, "synthetic": bool(principal["synthetic"]),
                "department": principal.get("department"),
                "shadow_endpoints": await endpoint_plane.shadow_count_for(user_token),
                "shadow_listeners": await endpoint_plane.shadow_listener_count_for(user_token),
            },
            "resource": {
                "id": cls.primary.id, "kind": cls.primary.kind, "data_class": cls.data_class,
                "owner_department": cls.primary.owner_department,
                "classification": {"required": True, "source": "registry/catalog.toml",
                                   "version": registry.catalog_version()},
            },
            "resources": [r.view() for r in cls.resources],
            "destinations": [d.view() for d in cls.destinations],
            "relationship": await _relationship_scope(server_id, cls),
            "tool": {"server": server_id, "name": tool, "action": cls.action,
                     "base_action": cls.base_action, "restrictable": cls.restrictable,
                     "provider_hosted": provider_hosted, "accepts_from": tool_review.get("accepts_from") or []},
            "request": {"untrusted_markers": untrusted_markers(arguments), "dlp": cls.dlp,
                        "pii_types": sent_types, "masked_types": masked_types,
                        "outbound_sha256": canonical_hash(outbound) if masked_types else None,
                        "sequence_flags": sequence_flags, "flow_sources": flow_sources,
                        "flow_observed": flow_observed, "flow_match_mode": FLOW_MATCH_MODE},
            "approval": {"granted": approval_granted, "id": approval_id},
            "contract": contract,
            "context": context,
        }
        policy_input["pac"] = await pac.build(payload, principal, cls, tool_row, contract, context,
                                             request_id, GATEWAY_ENVIRONMENT, approval_id)
        base_event["policy_input"] = policy_input  # kept for replay against a candidate policy
        laps.lap("context")
        try:
            result = await _policy(policy_input)
        except Exception as exc:
            result = local_verdict("P-CONTROL-FAIL-CLOSED", "Block", "OPA 정책 결정에 실패하여 기본 차단했습니다.")
            base_event["error"] = _root_cause(exc)
        if result["decision"] == "Block" and result["policy_id"] == "PAC-01":
            # The caller can only fix what it is told: which argument left the approved scope.
            try:
                gap = pac.argument_gap(principal, cls.server, cls.tool, arguments)
            except Exception:
                gap = ""
            if gap:
                result = {**result, "reason": f"{result['reason']} — {gap}. 승인된 범위 안의 값으로 바꾸거나 관리자에게 범위 변경을 요청하세요."}
        laps.lap("policy")

        policy_basis = result
        mode = await enforcement_mode()
        base_event["enforcement"] = mode
        # A PAC denial or approval ranked below the selected policy is still in force:
        # monitoring relaxes only when no always-enforced Block/Approval is among the
        # findings. Alerts (MCP-SHADOW-*) are observations and do not switch it off.
        enforced_findings = [result["policy_id"], *(c.get("policy_id", "") for c in result.get("conflicts") or []
                                                    if c.get("decision") in {"Block", "Approval"})]
        if (mode == "monitor" and result["decision"] != "Allow"
                and not any(pid.startswith(ALWAYS_ENFORCED) for pid in enforced_findings)):
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

        # POL-08: asked only when the call would otherwise run, in either enforcement mode.
        if result["decision"] in {"Allow", "Alert", "Restrict"} and tool_review.get("consent"):
            try:
                reason = await consent.missing(user_token, server_id, tool, cls.data_class, tool_review,
                                               principal=principal)
            except Exception as exc:
                result = local_verdict("P-CONTROL-FAIL-CLOSED", "Block", "동의 요청을 확인할 수 없어 실행하지 않았습니다.",
                                       error=_root_cause(exc))
            else:
                if reason:
                    result = local_verdict("P-CONSENT-001", "Block", reason,
                                           conditions={"matched": ["tool_reviews.consent"], "violated": ["user_consents"]})
            base_event.update(result)
            span.set_attribute("mcp.decision", result["decision"])
            span.set_attribute("mcp.policy_id", result["policy_id"])

        if (tool_review.get("high_impact") or payload.get("impact_scope_sha256")) and result["decision"] != "Block":
            approved = await db.fetch_one("SELECT * FROM approvals WHERE id=%s", (approval_id,)) if approval_granted and approval_id else None
            if not (high_impact.bound(approved, payload, tool_review, canonical_hash)
                    and approved["expires_at"] > datetime.now(UTC)):
                result = local_verdict("P-HIGH-IMPACT-001", "Approval", "중대 영향 호출은 개별 사람 승인이 필요합니다.",
                                       conflicts=[policy_basis])
                base_event.update(result)
                span.set_attribute("mcp.decision", result["decision"])
                span.set_attribute("mcp.policy_id", result["policy_id"])

        # D-191: 외부 AI 게이트웨이 애드온은 판정만 받고 전송은 호출한 쪽이 한다. 승인 대기 행도 만들지 않는다 —
        # 승인되면 이 게이트웨이가 같은 호출을 직접 보내 이중 실행되기 때문이다.
        decide_only = bool(payload.get("_decide_only"))
        if result["decision"] == "Approval" and not decide_only:
            new_approval_id = str(uuid.uuid4())
            stored = {k: payload.get(k) for k in ("server_id", "tool", "arguments", "user_token", "client", "transport_claims")}
            stored.update(pac_request_id=request_id, pac_digest=pac.digest(policy_input["pac"]))
            explanation = None
            if tool_review.get("high_impact"):
                stored["impact_scope_sha256"] = canonical_hash(high_impact.terms(tool_review))
                explanation = high_impact.explanation(new_approval_id, arguments, tool_review,
                    policy_basis, cls.data_class, cls.action, server_id, tool)
            async with db.transaction() as connection:
                await connection.execute(
                    """INSERT INTO approvals(id, request_fingerprint, request_payload, status, requested_by, expires_at, explanation)
                       VALUES (%s,%s,%s,'PENDING',%s,%s,%s)""",
                    (new_approval_id, canonical_hash(stored), Jsonb(stored), user_token,
                     datetime.now(UTC) + timedelta(minutes=APPROVAL_TTL_MINUTES), Jsonb(explanation)),
                )
                if explanation:
                    await review.record_event("call-request", "recorded", "approval", new_approval_id, user_token,
                        applicant=user_token, scope={"explanation": explanation, "request_fingerprint": canonical_hash(stored)},
                        connection=connection)
            base_event["approval_id"] = new_approval_id
        elif result["decision"] in {"Allow", "Alert", "Restrict"} and decide_only:
            base_event["effective_arguments"], base_event["restrictions_applied"] = classify.apply_restrictions(
                cls, outbound, result.get("restrictions") or {})
        elif result["decision"] in {"Allow", "Alert", "Restrict"}:
            effective, applied = classify.apply_restrictions(cls, outbound, result.get("restrictions") or {})
            base_event["restrictions_applied"] = applied
            try:
                with tracer.start_as_current_span("mcp.upstream.call", record_exception=False, set_status_on_exception=False) as upstream_span:
                    upstream_span.set_attribute("mcp.server", server_id)
                    upstream_span.set_attribute("mcp.transport", "streamable-http")
                    renewed = await db.execute(
                        """UPDATE call_reservations SET expires_at=now()+make_interval(secs => %s)
                           WHERE request_id=%s AND released_at IS NULL AND expires_at > now()""",
                        (RESERVATION_TTL_SECONDS, request_id))
                    dispatch_budget = min(upstream.CONNECT_TIMEOUT,
                                          RESERVATION_TTL_SECONDS - OUTPUT_INSPECTION_TIMEOUT_SECONDS - 10)
                    if not renewed or dispatch_budget <= 0:
                        raise DispatchRejected("call reservation expired before dispatch")
                    # Bound discovery + dispatch together; per-message timeouts alone
                    # let a slow session outlive the reservation. Reserve the output
                    # inspection budget and a margin too. Response loss stays unknown.
                    async with asyncio.timeout(dispatch_budget):
                        raw_result = await _call_upstream(server_id, tool, effective, approval_id, user_token,
                                                         dispatch_state=base_event, pac_payload=payload, laps=laps)
                base_event["upstream_executed"] = True
                try:
                    base_event["result"], output_types = await _inspected_result(raw_result, ignore)
                    await asyncio.to_thread(_validate_output, base_event["result"], base_event.pop("_output_schema", None))
                    released = output_contract.for_protocol(base_event["result"], payload.get("_response_protocol"))
                    base_event["result"] = await asyncio.to_thread(_guarded_result, released, payload.get("_response_protocol"))
                except privacy.InspectionUnavailable as exc:
                    # Executed, answer withheld: MCP-OUTPUT-001 below records exactly that.
                    base_event["control_failure"] = True
                    raise ResultRejected(f"출력 검사 실패: {exc}", raw_result) from exc
                laps.lap("inspect_out")
                # The digest is of what the client receives (masked), not of the raw answer.
                base_event["result_evidence"] = response_evidence(
                    base_event["result"], "masked" if output_types else "returned", output_types)
                base_event["privacy_types"] = sorted(set(privacy_types) | set(output_types))
                base_event["effective_arguments"] = effective
                classify.remember_navigation(user_token, cls, True)
                if base_event["result"].get("is_error"):
                    # The server ran the call and answered with a tool error (missing
                    # file, bad SQL). That is a definite outcome, not an unknown one.
                    base_event["error"] = upstream.text_of(base_event["result"]["content"])
            except (DispatchRejected, upstream.CredentialUnavailable) as exc:
                base_event.update(exc.verdict if isinstance(exc, DispatchRejected) and exc.verdict else local_verdict(
                    "P-CONTROL-FAIL-CLOSED", "Block",
                    "실행 직전 계약 또는 승인 재검증에 실패하여 도구 호출을 전달하지 않았습니다.",
                    upstream_attempted=False, error=str(exc),
                ))
                span.record_exception(RuntimeError(_root_cause(exc)))
                # Record the drift now so the next call is refused up front.
                try:
                    await refresh_catalog(server_id)
                except Exception:
                    pass
            except ResultRejected as exc:
                # The call did run upstream; only the answer is withheld.
                base_event.update(local_verdict(
                    "MCP-OUTPUT-001", "Block",
                    "upstream 결과가 출력 통제에 걸려 반환하지 않았습니다. 호출 자체는 실행됐습니다.",
                    restrictions=base_event.get("restrictions") or {},
                    exception=base_event.get("exception"),
                    upstream_executed=True, result=None, error=str(exc),
                    result_evidence=exc.evidence or {"disposition": "withheld"},
                ))
                span.record_exception(RuntimeError(_root_cause(exc)))
            except Exception as exc:
                base_event.update(_upstream_failure(exc, base_event))
                span.record_exception(RuntimeError(_root_cause(exc)))

        base_event.pop("_output_schema", None)
        response = await _decision_payload(base_event, laps)
        if (base_event["data_class"] == "important" and base_event["action"] == "r"
                and base_event["upstream_executed"] and base_event.get("result")):
            await _remember_flow(user_token, server_id, response["decision_id"], base_event["result"])
        return response


async def approve_request(approval_id: str, reviewer_token: str, reason: str | None = None,
                          evidence_sha256: str | None = None) -> dict:
    reviewer = await db.fetch_one("SELECT * FROM principals WHERE token=%s", (reviewer_token,))
    if not reviewer or reviewer["role"] != "admin" or reviewer["status"] != "active":
        raise ValueError("합성 관리자만 승인할 수 있습니다.")
    row = await db.fetch_one("SELECT * FROM approvals WHERE id=%s", (approval_id,))
    if not row or row["status"] != "PENDING":
        raise ValueError("대기 중인 승인 요청이 아닙니다.")
    # §8.6 forbids a self-approved exception and the exception ledger enforces it
    # (requested_by != approved_by). The same rule has to hold for the per-call approval
    # an administrator raises for their own high-risk call, or the control is one click
    # by one person - which is the thing an approval step exists to prevent.
    call = {"server": row["request_payload"].get("server_id"), "tool": row["request_payload"].get("tool")}
    try:
        await review.require_independent("call-approve", "approval", approval_id, reviewer_token, row["requested_by"], call)
    except review.NotIndependent as exc:
        raise ValueError("자기가 요청한 호출은 자기가 승인할 수 없습니다. 다른 승인자가 처리해야 합니다.") from exc
    if row["expires_at"] <= datetime.now(UTC):
        await db.execute("UPDATE approvals SET status='EXPIRED' WHERE id=%s AND status='PENDING'", (approval_id,))
        raise ValueError("승인 요청의 10분 유효시간이 지났습니다.")

    if row.get("explanation"):
        await _require_explanation(row, reviewer_token, evidence_sha256)
        if reason != "scope_confirmed":
            raise ValueError("중대 영향 요청의 검토 근거가 필요합니다.")
        reason = high_impact.REASONS[reason]
        call = {"explanation": row["explanation"], "evidence_sha256": evidence_sha256,
                "request_fingerprint": row["request_fingerprint"]}

    async with db.transaction() as connection:
        claimed = await (await connection.execute(
            """UPDATE approvals SET status='APPROVED', reviewed_by=%s, reviewed_at=now()
               WHERE id=%s AND status='PENDING' AND expires_at>now() RETURNING *""",
            (reviewer_token, approval_id))).fetchone()
        if claimed:
            await review.record_event("call-approve", "approved", "approval", approval_id, reviewer_token,
                                      applicant=claimed["requested_by"], reason=reason, scope=call, connection=connection)
    if not claimed:
        raise ValueError("다른 승인자가 먼저 처리했습니다.")
    payload = claimed["request_payload"]
    if canonical_hash(payload) != claimed["request_fingerprint"]:
        await db.execute("UPDATE approvals SET status='REJECTED' WHERE id=%s", (approval_id,))
        raise ValueError("승인 요청 내용의 무결성 검증에 실패했습니다.")

    result = await execute_call(payload, approval_granted=True, approval_id=approval_id)
    # A granted call that did not run is not a rejection. Stopped before dispatch and
    # dispatched-but-unconfirmed are different facts; the second may have had an effect.
    final_status = ("EXECUTED" if result["upstream_executed"]
                    else "UNCONFIRMED" if result.get("upstream_attempted") else "NOT_EXECUTED")
    await db.execute(
        "UPDATE approvals SET status=%s, executed_decision_id=%s WHERE id=%s",
        (final_status, result["decision_id"], approval_id),
    )
    return result


async def approval_evidence(approval_id: str, actor: str) -> dict:
    row = await db.fetch_one("SELECT * FROM approvals WHERE id=%s", (approval_id,))
    if not row or not row.get("explanation"):
        raise ValueError("중대 영향 결정 증빙이 없습니다.")
    digest = canonical_hash(row["explanation"])
    await review.record_event("call-explanation-view", "recorded", "approval", approval_id, actor,
                              scope={"evidence_sha256": digest})
    events = await review.events_for("approval", approval_id)
    people = await db.fetch_all("SELECT token, display_name FROM principals WHERE token = ANY(%s::text[])",
                                (list({e["actor"] for e in events}),))
    names = {p["token"]: p["display_name"] for p in people}
    # Free-form reasons and request/response bodies are never copied into the export.
    history = [{"id": e["id"], "kind": e["kind"], "outcome": e["outcome"], "actor": e["actor"],
                "actor_display_name": names.get(e["actor"]),
                "created_at": e["created_at"],
                "reason": e["reason"] if e.get("reason") in high_impact.REASONS.values() else None}
               for e in events]
    decisions = await db.fetch_all(
        """SELECT id, decision, policy_id, upstream_executed, upstream_attempted, outcome, created_at
           FROM decisions WHERE approval_id=%s ORDER BY id""", (approval_id,))
    return {"explanation": row["explanation"], "evidence_sha256": digest,
            "status": "REVOKED" if row.get("revoked_at") else row["status"],
            "events": history, "decisions": decisions, "effect_reversal": False}


async def _require_explanation(row: dict, actor: str, digest: str | None) -> None:
    if digest != canonical_hash(row["explanation"]) or not await db.fetch_one(
        """SELECT id FROM approval_events WHERE target_kind='approval' AND target_id=%s
           AND kind='call-explanation-view' AND actor=%s AND scope->>'evidence_sha256'=%s LIMIT 1""",
        (str(row["id"]), actor, digest)):
        raise ValueError("설명 증빙을 열람한 뒤 처리해야 합니다.")


async def revoke_approval(approval_id: str, actor: str, digest: str) -> dict:
    person = await db.fetch_one("SELECT * FROM principals WHERE token=%s", (actor,))
    row = await db.fetch_one("SELECT * FROM approvals WHERE id=%s", (approval_id,))
    if not person or person["role"] != "admin" or person["status"] != "active":
        raise ValueError("관리자만 승인을 번복할 수 있습니다.")
    if not row or not row.get("explanation") or not await review.same_person(actor, row.get("reviewed_by")):
        raise ValueError("중대 영향 호출의 승인자만 번복할 수 있습니다.")
    await _require_explanation(row, actor, digest)
    async with db.transaction() as connection:
        changed = await (await connection.execute(
            """UPDATE approvals SET revoked_at=now(), revoked_by=%s WHERE id=%s AND revoked_at IS NULL
               AND status IN ('APPROVED','UNCONFIRMED','EXECUTED','NOT_EXECUTED') RETURNING id""",
            (actor, approval_id))).fetchone()
        if not changed:
            raise ValueError("번복할 수 있는 승인이 아닙니다.")
        await review.record_event("call-revoke", "recorded", "approval", approval_id, actor,
            applicant=row["requested_by"], reason=high_impact.REASONS["approval_withdrawn"],
            scope={"explanation": row["explanation"], "evidence_sha256": digest, "effect_reversal": False}, connection=connection)
    return {"approval_id": approval_id, "status": "REVOKED", "effect_reversal": False}


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
                  max(r.imported_at) AS last_scanned_at,
                  min(r.vuln_db_updated_at) FILTER (WHERE r.scanner = 'Trivy') AS vuln_db_updated_at,
                  string_agg(DISTINCT r.scanner || ' ' || COALESCE(r.scanner_version, '—'), ', ') AS scanners
           FROM mcp_servers s
           LEFT JOIN supply_chain_reports r ON r.source_ref = s.source_ref
           GROUP BY s.id, s.source_ref, s.scan_path ORDER BY s.id"""
    )


async def reject_request(approval_id: str, reviewer_token: str, note: str,
                         evidence_sha256: str | None = None) -> dict:
    """The other half of an approval.

    Without it a reviewer's only options are "approve" or "let it expire", and the
    audit cannot tell a considered refusal apart from someone going to lunch.
    """
    reviewer = await db.fetch_one("SELECT * FROM principals WHERE token=%s", (reviewer_token,))
    if not reviewer or reviewer["role"] != "admin" or reviewer["status"] != "active":
        raise ValueError("합성 관리자만 승인 요청을 처리할 수 있습니다.")
    if not note.strip():
        raise ValueError("거부 사유는 비워둘 수 없습니다.")
    row = await db.fetch_one("SELECT * FROM approvals WHERE id=%s", (approval_id,))
    scope = {"server": (row or {}).get("request_payload", {}).get("server_id"),
             "tool": (row or {}).get("request_payload", {}).get("tool")}
    if row and row.get("explanation"):
        await _require_explanation(row, reviewer_token, evidence_sha256)
        if note != "request_inappropriate":
            raise ValueError("거부 근거가 올바르지 않습니다.")
        note = high_impact.REASONS[note]
        scope = {"explanation": row["explanation"], "evidence_sha256": evidence_sha256}
    async with db.transaction() as connection:
        claimed = await (await connection.execute(
            """UPDATE approvals SET status='REJECTED', reviewed_by=%s, reviewed_at=now(), review_note=%s
               WHERE id=%s AND status='PENDING' RETURNING id, requested_by, review_note, request_payload""",
            (reviewer_token, note.strip(), approval_id))).fetchone()
        if claimed:
            await review.record_event("call-reject", "rejected", "approval", approval_id, reviewer_token, applicant=claimed["requested_by"],
                                      reason=note.strip(), scope=scope, connection=connection)
    if not claimed:
        raise ValueError("대기 중인 승인 요청이 아닙니다.")
    spec = registry.server(claimed["request_payload"].get("server_id"))
    if spec:
        await upstream.release_pool(spec["endpoint"], claimed["requested_by"], "approval-rejected")
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

    return imported
