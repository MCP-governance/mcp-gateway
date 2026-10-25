"""Intake provenance, supply-chain gate, tool scope review, approver independence, re-approval,
per-harness minimal set, audit annotation and PAC-05 delegation, against a real PostgreSQL and a real
OPA that serves this repository's policy bundle.

Run ONLY in a disposable lab (docs/ai/TESTING.md "격리 DB 시험"): a fresh PostgreSQL loaded with db/init.sql,
an OPA container serving ./opa, and this file run in the gateway image with the lab's DATABASE_URL, OPA_URL,
POLICY_LEDGER_URL, REGISTRY_DIR (the repository's registry/) and a writable REGISTRY_RUNTIME_DIR.

What is real: the SQL, constraints and append-only triggers, the Console and Gateway routes, the policy
decisions. What is a double (unit level, not real-environment evidence): the MCP server behind the
endpoints (tools/list and the final dispatch are canned answers), the PII analyzer (finds nothing), the
internal Git archive check, and the intake worker's scan output, which is inserted as rows shaped like the worker's.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import HTTPException
from psycopg import errors as pg_errors
from psycopg.types.json import Jsonb

os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("IDP_ISSUER", "https://gateway.lab.test")
os.environ.setdefault("ENDPOINT_GATEWAY_IPS", "10.0.0.5")
for candidate in (Path(__file__).resolve().parent.parent / "gateway", Path("/app")):
    if (candidate / "app").is_dir():
        sys.path.insert(0, str(candidate))
        break
from app import activity, agent_service, audit, core, db, endpoint_plane, main, mcp_facade, privacy, registry, review, upstream
from app.agent_contract import AUDIENCE, ISSUER
from intake_fixture import approval_body, impact_input
from termination_lab_support import isolated_disposal, signing_keys

PASSED: list[str] = []
ENDPOINT = "https://notes.example.test/mcp"
SEARCH_SCHEMA = {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"], "additionalProperties": False}
CONSTRAINT = {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"], "additionalProperties": False}
READ_SCHEMA = {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"], "additionalProperties": False}
PEOPLE = {
    "wbsb-admin-a": ("user-wbsb-a", "admin"), "wbsb-admin-b": ("user-wbsb-b", "admin"),
    "wbsb-emp": ("user-wbsb-e", "employee"), "wbsb-emp2": ("user-wbsb-f", "employee"),
}
WHO: dict = {}


def ok(name: str) -> None:
    PASSED.append(name)
    print("PASS", name, flush=True)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def as_(token: str) -> None:
    user_id, role = PEOPLE[token]
    WHO.clear()
    WHO.update(principal=token, user_id=user_id, roles=[role], name=token, department="시험", email=f"{token}@lab.test",
               managed_required=False)


async def identity(authorization=None) -> dict:
    return dict(WHO)


class Upstream:
    """Unit-level double of one MCP server's tools/list. Not a real MCP server."""
    version = "1.0.0"
    search_schema = SEARCH_SCHEMA
    calls = 0

    @classmethod
    def tools(cls) -> list[dict]:
        return [
            {"name": "search", "description": "Search the notes", "input_schema": cls.search_schema, "annotations": {"read_only_hint": True}},
            {"name": "read", "description": "Read one note", "input_schema": READ_SCHEMA, "annotations": {"read_only_hint": True}},
            {"name": "admin_dump", "description": "Dump everything", "input_schema": READ_SCHEMA, "annotations": {}},
        ]

    @classmethod
    async def discover(cls, endpoint: str, principal: str | None = None) -> dict:
        return {"advertised_name": "notes", "version": cls.version, "protocol_version": "2025-06-18", "tools": cls.tools()}

    @classmethod
    async def call(cls, *args, **kwargs) -> dict:
        cls.calls += 1
        return core._guarded_result({"content": [{"type": "text", "text": "ok"}], "is_error": False})


async def no_masking(value, ignore=None):
    """The lab has no PII analyzer service: output inspection is a double that finds nothing."""
    return value, []


async def no_findings(text, ignore=None):
    """The lab has no PII analyzer service: inbound inspection is a double that finds nothing."""
    return []


async def proxy(path, authorization, method="GET", body=None, timeout=15):
    """The Console's hop to the Gateway, in process: the Gateway functions are the real ones."""
    try:
        if path == "/api/registry/intake-discover":
            return await main.registry_intake_discover(main.RegistryDiscover(**body), dict(WHO))
        if path == "/api/registry/discover":
            return await core.discover_for_registration(body["endpoint"])
        if path == "/api/registry/servers" and method == "POST":
            return await core.register_server(body, WHO["principal"])
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    raise AssertionError(f"unexpected gateway path {path}")


def claims(token: str, **extra) -> dict:
    now = time.time()
    return {"sub": PEOPLE[token][0], "iss": ISSUER, "aud": AUDIENCE, "jti": str(uuid.uuid4()), "nbf": now - 5, "exp": now + 600,
            "scope": "mcp", **extra}


async def call(token: str, server: str, tool: str, arguments: dict, *, extra_claims: dict | None = None, client: dict | None = None) -> dict:
    return await core.execute_call({"server_id": server, "tool": tool, "arguments": arguments, "user_token": token,
                                    "client": client or {"harness": {"name": "claude-code", "user_agent": "claude-code/2"}},
                                    "transport_claims": claims(token, **(extra_claims or {}))})


async def events(kind: str | None = None, target: str | None = None) -> list[dict]:
    rows = await db.fetch_all("SELECT * FROM approval_events ORDER BY id")
    return [row for row in rows if (kind is None or row["kind"] == kind) and (target is None or row["target_id"] == str(target))]


async def set_runtime(server_id: str, **changes) -> None:
    async with core.REGISTER_LOCK:
        doc = registry.runtime()
        for key, value in changes.items():
            if value is None:
                doc["servers"][server_id].pop(key, None)
            else:
                doc["servers"][server_id][key] = value
        registry.save_runtime(doc)
        await registry.sync()


def scope_of(body: dict) -> dict:
    # /register takes IntakeRegistration, which has no parameter_constraints: that field is
    # fixed at contract review time and carried forward from the approved contract (D-49).
    return {key: body[key] for key in ("server_id", "endpoint", "catalog_hash", "tools", "data_class", "valid_days", "poisoning_ack", "tool_reviews")}


def review_body(server_id: str, catalog_hash: str, tools: dict, reviews: dict, allowed: list[str]) -> dict:
    return {"server_id": server_id, "endpoint": ENDPOINT, "catalog_hash": catalog_hash, "tools": tools, "data_class": "nonimportant",
            "valid_days": 30, "poisoning_ack": False, "tool_reviews": reviews, "allowed_principals": allowed,
            "review_note": "시험용 계약과 사용 범위를 검토했습니다.",
            "parameter_constraints": {name: CONSTRAINT if name == "search" else {**CONSTRAINT, "properties": {"id": {"type": "string"}}, "required": ["id"]}
                                      for name in tools}}


REVIEWS = {"search": {"purpose": "공개 노트 검색", "asset": "notes", "destinations": []},
           "read": {"purpose": "공개 노트 읽기", "asset": "notes", "destinations": ["notes-cdn.example.com"]}}


async def wait_for_opa() -> None:
    for _ in range(60):
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                if (await client.get(core.OPA_URL.split("/v1/")[0] + "/health")).status_code == 200:
                    return
        except httpx.HTTPError:
            pass
        await asyncio.sleep(1)
    raise RuntimeError("OPA did not answer")


async def setup() -> None:
    await wait_for_opa()
    await core.bootstrap()
    for token, (user_id, role) in PEOPLE.items():
        await db.execute(
            """INSERT INTO principals(token, user_id, email, display_name, role, department)
               VALUES (%s,%s,%s,%s,%s,'시험') ON CONFLICT (token) DO NOTHING""", (token, user_id, f"{token}@lab.test", token, role))


# ── remote service: consent, independence, scope review, registration ──────────────────────────────

async def remote_service_flow(console: httpx.AsyncClient) -> str:
    found = await core.discover_for_registration(ENDPOINT)
    tools = {"search": "r", "read": "r"}
    as_("wbsb-emp")
    made = await console.post("/api/mcp-requests", json={"display_name": "Notes", "intake_kind": "remote-endpoint", "endpoint_url": ENDPOINT,
                                                       "requested_transport": "streamable-http", "purpose": "공개 노트를 검색하고 읽는 데 씁니다.",
                                                       "risk_input": impact_input(), "requested_tools": list(tools)})
    check(made.status_code == 200, f"신청: {made.text}")
    intake = made.json()["request"]["id"]
    consent = await events("user-consent", intake)
    check(len(consent) == 1 and consent[0]["actor"] == "wbsb-emp" and consent[0]["applicant"] == "wbsb-emp", "사용자 동의가 별도 기록으로 남아야 함")
    ok("신청 시 사용자 동의가 신청자 이름으로 따로 기록된다")

    as_("wbsb-admin-a")
    body = review_body("notes", found["catalog_hash"], tools, REVIEWS, ["wbsb-emp"])
    missing_scope = await console.post(f"/api/mcp-requests/{intake}/review-contract", json={k: v for k, v in body.items() if k != "tool_reviews"})
    check(missing_scope.status_code == 422, f"도구 범위 없는 계약 검토가 통과함: {missing_scope.status_code}")
    reviewed = await console.post(f"/api/mcp-requests/{intake}/review-contract", json=body)
    check(reviewed.status_code == 200, f"계약 검토: {reviewed.text}")
    row = await db.fetch_one("SELECT status, provenance FROM mcp_intake_requests WHERE id=%s", (intake,))
    p = row["provenance"]
    check(row["status"] == "REMOTE_REVIEWED" and p["kind"] == "provider-hosted" and p["source_url"] == ENDPOINT, f"출처 기록: {p}")
    check(p["artifact"] == {"applicable": False, "reason": "해당 없음", "endpoint": ENDPOINT} and "sha256" not in p["artifact"], "제공자 호스팅에 해시를 지어내면 안 됨")
    ok("원격 서비스의 출처는 '해당 없음'과 엔드포인트로 기록되고 해시는 없다")

    gate = await review.intake_gate(await db.fetch_one("SELECT * FROM mcp_intake_requests WHERE id=%s", (intake,)))
    check(gate["ok"], f"원격 gate: {gate['blockers']}")
    await db.execute("UPDATE mcp_intake_requests SET provenance='{}' WHERE id=%s", (intake,))
    held = await console.post(f"/api/mcp-requests/{intake}/approve", json=approval_body(risk_acceptance="시험용 위험 수용 사유입니다."))
    check(held.status_code == 409, f"출처 없는 원격 승인: {held.status_code}")
    check((await db.fetch_one("SELECT status FROM mcp_intake_requests WHERE id=%s", (intake,)))["status"] == "HOLD", "출처 누락은 보류여야 함")
    ok("출처 기록이 없으면 승인되지 않고 보류된다 (원격)")
    await console.post(f"/api/mcp-requests/{intake}/review-contract", json=body)  # review again: the record comes back

    # the applicant (also an administrator) cannot review or approve what they asked for
    as_("wbsb-admin-b")
    own = await console.post("/api/mcp-requests", json={"display_name": "Notes (own)", "intake_kind": "remote-endpoint", "endpoint_url": "https://other.example.test/mcp",
                                                       "requested_transport": "streamable-http", "purpose": "관리자 본인 신청을 본인이 승인하는지 확인합니다.",
                                                       "risk_input": impact_input(), "requested_tools": list(tools)})
    check(own.status_code == 200, f"본인 신청: {own.status_code} {own.text}")
    own_id = own.json()["request"]["id"]
    own_body = {**body, "endpoint": "https://other.example.test/mcp"}
    refused_review = await console.post(f"/api/mcp-requests/{own_id}/review-contract", json=own_body)
    check(refused_review.status_code == 403, f"신청자의 계약 검토: {refused_review.status_code}")
    refused_approve = await console.post(f"/api/mcp-requests/{own_id}/approve", json=approval_body(risk_acceptance="자기 승인 시험입니다. 거부되어야 합니다."))
    check(refused_approve.status_code == 403, f"신청자의 승인: {refused_approve.status_code}")
    refusals = [e for e in await events(target=own_id) if e["outcome"] == "refused"]
    check({e["kind"] for e in refusals} == {"contract-review", "intake-approve"} and all(e["actor"] == e["applicant"] == "wbsb-admin-b" for e in refusals),
          f"거부 기록: {refusals}")
    check((await db.fetch_one("SELECT status FROM mcp_intake_requests WHERE id=%s", (own_id,)))["status"] == "HOLD", "신청자 승인 시도가 상태를 바꿈")
    ok("신청자는 자기 신청의 계약 검토·승인을 서버에서 거부당하고 그 시도가 남는다")
    await console.post(f"/api/mcp-requests/{own_id}/reject", json={"note": "시험 정리를 위해 거부합니다."})

    # an independent administrator approves; approval and consent stay two records
    as_("wbsb-admin-a")
    approved = await console.post(f"/api/mcp-requests/{intake}/approve", json=approval_body(risk_acceptance="시험용 위험 수용 사유입니다."))
    check(approved.status_code == 200, f"승인: {approved.text}")
    approval = (await events("intake-approve", intake))[-1]
    check(approval["outcome"] == "approved" and approval["actor"] == "wbsb-admin-a" and approval["applicant"] == "wbsb-emp"
          and approval["scope"]["tools"] == tools and approval["scope"]["contract_sha256"] == found["catalog_hash"] and approval["reason"],
          f"승인 기록: {approval}")
    ok("독립된 관리자의 승인은 승인자·신청자·사유·범위와 함께 기록된다")

    registered = await console.post(f"/api/mcp-requests/{intake}/register", json=scope_of(body))
    check(registered.status_code == 200, f"등록: {registered.text}")
    rows = {r["name"]: r for r in await db.fetch_all("SELECT name, enabled, scope_review FROM mcp_tools WHERE server_id='notes'")}
    check(rows["search"]["enabled"] and rows["read"]["enabled"] and not rows["admin_dump"]["enabled"], f"도구 상태: {rows}")
    check(rows["read"]["scope_review"]["destinations"] == ["notes-cdn.example.com"] and rows["read"]["scope_review"]["action"] == "r", "범위 심사가 저장됨")
    ok("등록한 도구마다 사람이 승인한 범위(목적·자산·행위·외부 목적지)가 저장된다")
    check(any(e["kind"] == "server-register" for e in await events(target="notes")), "등록 기록")
    return intake


async def positive_control() -> None:
    result = await call("wbsb-emp", "notes", "search", {"q": "x"})
    check(result["decision"] == "Allow" and Upstream.calls >= 1, f"정상 호출: {result['decision']} {result['policy_id']} {result.get('reason')}")
    ok("범위를 심사한 도구의 정상 호출은 허용된다 (대조군)")


async def unreviewed_tool() -> None:
    names = {t.name for t in await mcp_facade._approved_tools("employee", "notes", "wbsb-emp")}
    check(names == {"search", "read"}, f"tools/list: {names}")
    await set_runtime("notes", tool_reviews={"search": (registry.runtime()["servers"]["notes"]["tool_reviews"]["search"])})
    names = {t.name for t in await mcp_facade._approved_tools("employee", "notes", "wbsb-emp")}
    check(names == {"search"}, f"범위 미심사 도구가 목록에 남음: {names}")
    before = Upstream.calls
    blocked = await call("wbsb-emp", "notes", "read", {"id": "1"})
    check(blocked["decision"] == "Block" and blocked["policy_id"] == "MCP-REGISTRY-002" and Upstream.calls == before,
          f"범위 미심사 도구 호출: {blocked['decision']} {blocked['policy_id']}")
    ok("범위를 심사하지 않은 도구는 tools/list에서 빠지고 tools/call은 MCP-REGISTRY-002로 거부된다")
    as_("wbsb-admin-a")
    for_applicant = "wbsb-emp"
    try:
        await core.review_tool_scopes("notes", {"read": REVIEWS["read"]}, for_applicant)
        raise AssertionError("신청자가 자기 서버의 범위를 심사함")
    except review.NotIndependent:
        pass
    await core.review_tool_scopes("notes", {"read": REVIEWS["read"]}, "wbsb-admin-b")
    names = {t.name for t in await mcp_facade._approved_tools("employee", "notes", "wbsb-emp")}
    check(names == {"search", "read"}, f"범위 심사 뒤 목록: {names}")
    check((await events("tool-scope-review", "notes"))[-1]["actor"] == "wbsb-admin-b", "범위 심사 기록")
    ok("기존 등록의 범위 심사는 신청자가 아닌 관리자만 기록할 수 있다")


async def expiry_revocation_contract_change(intake: str) -> None:
    window = (datetime.now(UTC) + timedelta(days=3)).isoformat(timespec="seconds")
    # expiry
    await set_runtime("notes", valid_until=(datetime.now(UTC) - timedelta(minutes=1)).isoformat(timespec="seconds"))
    before = Upstream.calls
    expired = await call("wbsb-emp", "notes", "search", {"q": "x"})
    check(expired["decision"] == "Block" and expired["policy_id"] == "P-APPROVAL-EXPIRY-001" and Upstream.calls == before,
          f"만료 뒤 호출: {expired['decision']} {expired['policy_id']}")
    check(await core.renew_approvals() == [], "이미 만료된 승인이 갱신됨")
    ok("승인 만료 뒤 호출은 거부되고 만료된 승인은 갱신으로 되살아나지 않는다")

    # contract change
    await set_runtime("notes", valid_until=window)
    Upstream.search_schema = {**SEARCH_SCHEMA, "properties": {"q": {"type": "string"}, "extra": {"type": "string"}}}
    refreshed = await core.refresh_catalog("notes")
    check(refreshed["status"] == "DRIFT", f"계약 변경 감지: {refreshed['status']}")
    before = Upstream.calls
    drifted = await call("wbsb-emp", "notes", "search", {"q": "x"})
    check(drifted["decision"] == "Block" and drifted["policy_id"] == "MCP-CATALOG-001" and Upstream.calls == before,
          f"계약 변경 뒤 호출: {drifted['decision']} {drifted['policy_id']}")
    check(await core.renew_approvals() == [], "계약이 바뀐 승인이 갱신됨")
    ok("계약이 바뀐 뒤 호출은 MCP-CATALOG-001로 거부되고 승인은 갱신되지 않는다")

    Upstream.search_schema = SEARCH_SCHEMA
    check((await core.refresh_catalog("notes"))["status"] == "READY", "계약 복원")

    # renewal rests on more than the contract
    await db.execute("UPDATE mcp_intake_requests SET status='HOLD' WHERE id=%s", (intake,))
    check(await core.renew_approvals() == [], "신청이 보류로 돌아갔는데 갱신됨")
    await db.execute("UPDATE mcp_intake_requests SET status='APPROVED' WHERE id=%s", (intake,))
    kept = registry.runtime()["servers"]["notes"]["tool_reviews"]
    await set_runtime("notes", tool_reviews={"search": kept["search"]})
    check(await core.renew_approvals() == [], "범위 심사가 빠진 도구가 있는데 갱신됨")
    await set_runtime("notes", tool_reviews=kept)
    renewed = await core.renew_approvals()
    check(len(renewed) == 1 and renewed[0]["server_id"] == "notes", f"모든 근거가 그대로일 때만 갱신: {renewed}")
    ok("갱신은 계약·신청 상태·도구 범위 심사가 모두 그대로일 때만 일어난다")

    # revocation
    names = {t.name for t in await mcp_facade._approved_tools("employee", "notes", "wbsb-emp")}
    check(names == {"search", "read"}, "철회 전 목록")
    await core.deregister_server("notes", "wbsb-admin-a", "시험 철회")
    before = Upstream.calls
    revoked = await call("wbsb-emp", "notes", "search", {"q": "x"})
    check(revoked["decision"] == "Block" and revoked["policy_id"] == "MCP-REGISTRY-001" and Upstream.calls == before,
          f"철회 뒤 호출: {revoked['decision']} {revoked['policy_id']}")
    check(await mcp_facade._approved_tools("employee", "notes", "wbsb-emp") == []
          and await mcp_facade._approved_tools("employee", None, "wbsb-emp") == [], "철회한 서버가 tools/list에 남음")
    check(any(e["kind"] == "server-deregister" for e in await events(target="notes")), "철회 기록")
    ok("철회한 서버는 tools/list에서 사라지고 호출은 MCP-REGISTRY-001로 거부된다")


# ── per-harness minimal set ─────────────────────────────────────────────────────────────────────────

async def minimal_set(console: httpx.AsyncClient) -> None:
    # a live registration for two people, so the rendered set can differ per person
    Upstream.search_schema = SEARCH_SCHEMA
    found = await core.discover_for_registration(ENDPOINT)
    as_("wbsb-emp")
    made = (await console.post("/api/mcp-requests", json={"display_name": "Notes 2", "intake_kind": "remote-endpoint", "endpoint_url": ENDPOINT,
                                                        "requested_transport": "streamable-http", "purpose": "하네스별 최소 집합을 확인합니다.",
                                                        "risk_input": impact_input(), "requested_tools": ["search"]})).json()["request"]["id"]
    as_("wbsb-admin-a")
    body = review_body("notes2", found["catalog_hash"], {"search": "r"}, {"search": REVIEWS["search"]}, ["wbsb-emp"])
    check((await console.post(f"/api/mcp-requests/{made}/review-contract", json=body)).status_code == 200, "계약 검토")
    check((await console.post(f"/api/mcp-requests/{made}/approve", json=approval_body(risk_acceptance="시험용 위험 수용 사유입니다."))).status_code == 200, "승인")
    check((await console.post(f"/api/mcp-requests/{made}/register", json=scope_of(body))).status_code == 200, "등록")
    await db.execute("UPDATE mcp_servers SET status='READY', lifecycle='OPERATING' WHERE id IN ('filesystem','git')")

    def device(owner: str) -> dict:
        return {"device_epoch": "e1", "owner_token": owner, "local_username": "emp", "local_uid": 1001, "detail": {}}

    mine = await endpoint_plane.managed_policy(device("wbsb-emp"))
    other = await endpoint_plane.managed_policy(device("wbsb-emp2"))
    lab_user = await endpoint_plane.managed_policy(device("emp-ysg"))
    check(mine["servers"] == ["notes2"], f"허용된 사용자의 서버 집합: {mine['servers']}")
    check(other["servers"] == [], f"허용되지 않은 사용자에게 서버가 내려감: {other['servers']}")
    check({"filesystem", "git"} <= set(lab_user["servers"]) and "notes2" not in lab_user["servers"], f"카탈로그 권한 사용자: {lab_user['servers']}")
    claude = __import__("json").loads(mine["files"]["managed-mcp.json"])["mcpServers"]
    check(set(claude) == {"notes2"}, f"Claude 설정: {set(claude)}")
    check("[mcp_servers.notes2]" in mine["files"]["managed_config.toml"] and "filesystem" not in mine["files"]["managed_config.toml"]
          and "notes2" not in other["files"]["managed_config.toml"], "Codex 설정")
    route = os.environ["IDP_ISSUER"].rstrip("/") + "/mcp/notes2/"
    check(__import__("json").loads(mine["files"]["managed-settings.json"])["allowedMcpServers"] == [{"serverUrl": route}], "허용 서버 URL")
    ok("렌더링된 Claude·Codex 설정에는 그 사용자에게 승인된 서버만 들어간다")
    await core.deregister_server("notes2", "wbsb-admin-a")
    gone = await endpoint_plane.managed_policy(device("wbsb-emp"))
    check(gone["servers"] == [] and "notes2" not in gone["files"]["managed-mcp.json"] and "notes2" not in gone["files"]["managed_config.toml"]
          and gone["policy_hash"] != mine["policy_hash"], "철회한 서버가 설정에 남음")
    check(await mcp_facade._approved_tools("employee", "notes2", "wbsb-emp") == [], "철회한 서버가 목록에 남음")
    ok("등록을 철회한 서버는 렌더링된 설정과 tools/list에서 함께 사라진다")


# ── PAC-05 delegation ───────────────────────────────────────────────────────────────────────────────

async def delegation(console: httpx.AsyncClient) -> None:
    Upstream.search_schema = SEARCH_SCHEMA
    found = await core.discover_for_registration(ENDPOINT)
    as_("wbsb-emp")
    made = (await console.post("/api/mcp-requests", json={"display_name": "Notes 3", "intake_kind": "remote-endpoint", "endpoint_url": ENDPOINT,
                                                        "requested_transport": "streamable-http", "purpose": "위임 호출 거부를 확인합니다.",
                                                        "risk_input": impact_input(), "requested_tools": ["search"]})).json()["request"]["id"]
    as_("wbsb-admin-a")
    body = review_body("notes3", found["catalog_hash"], {"search": "r"}, {"search": REVIEWS["search"]}, ["wbsb-emp"])
    await console.post(f"/api/mcp-requests/{made}/review-contract", json=body)
    await console.post(f"/api/mcp-requests/{made}/approve", json=approval_body(risk_acceptance="시험용 위험 수용 사유입니다."))
    check((await console.post(f"/api/mcp-requests/{made}/register", json=scope_of(body))).status_code == 200, "등록")
    control = await call("wbsb-emp", "notes3", "search", {"q": "x"})
    check(control["decision"] == "Allow", f"대조군: {control['decision']} {control['policy_id']}")
    before = Upstream.calls
    for label, extra, client in (
        ("act 클레임", {"act": {"sub": "agent-7"}}, None),
        ("on_behalf_of 클레임", {"on_behalf_of": "user-wbsb-e"}, None),
        ("위임 헤더", {}, {"harness": {"name": "claude-code"}, "delegation_headers": ["x-on-behalf-of"]}),
    ):
        refused = await call("wbsb-emp", "notes3", "search", {"q": "x"}, extra_claims=extra, client=client)
        check(refused["decision"] == "Block" and refused["policy_id"] == "PAC-05-DELEGATION-UNSUPPORTED", f"{label}: {refused['decision']} {refused['policy_id']}")
    check(Upstream.calls == before, "위임을 주장한 호출이 업스트림에 전달됨")
    ok("위임을 주장하는 호출(act·on_behalf_of·헤더)은 PAC-05-DELEGATION-UNSUPPORTED로 거부된다")
    await core.set_enforcement_mode("monitor", "wbsb-admin-a")
    try:
        monitored = await call("wbsb-emp", "notes3", "search", {"q": "x"}, extra_claims={"act": {"sub": "agent-7"}})
        check(monitored["decision"] == "Block" and monitored["policy_id"] == "PAC-05-DELEGATION-UNSUPPORTED", "관찰 모드에서 위임 거부가 풀림")
    finally:
        await core.set_enforcement_mode("enforce", "wbsb-admin-a")
    ok("관찰 모드에서도 위임 거부는 풀리지 않는다")
    only_client = await call("wbsb-emp", "notes3", "search", {"q": "x"},
                             client={"harness": {"name": "some-agent", "user_agent": "evil/9"}, "agent": "some-agent"})
    check(only_client["decision"] == "Allow", f"clientInfo만 있는 호출: {only_client['decision']} {only_client['policy_id']}")
    stored = (await db.fetch_one("SELECT policy_input->'pac'->'facts'->'delegation' AS d FROM decisions WHERE id=%s", (only_client["decision_id"],)))["d"]
    check(stored["agent_identity"] == {"source": "client_info", "verified": False} and stored["asserted"] is False, f"기록: {stored}")
    ok("clientInfo·User-Agent는 판정에 쓰이지 않고 검증 안 된 출처로만 기록된다")
    await core.deregister_server("notes3", "wbsb-admin-a")


# ── repository intake: provenance, freshness, critical findings ─────────────────────────────────────

async def seed_repo(applicant: str, name: str, *, db_age_days: float | None = 1, critical: int = 0, status: str | None = None,
                    failed: tuple[str, ...] = (), no_report: tuple[str, ...] = (), provenance: dict | None = ..., license_spdx: str | None = "MIT") -> str:
    intake = str(uuid.uuid4())
    commit = uuid.uuid4().hex + uuid.uuid4().hex[:8]
    source_ref = f"intake:example/{name}@{commit[:12]}"
    scanners = {n: {"status": "FAILED" if n in failed else "DONE"} for n in ("syft", "trivy", "semgrep", "gitleaks")}
    record = ({"kind": "source", "source_url": f"https://github.com/example/{name}", "version": commit, "version_immutable": True,
               "license": {"spdx": license_spdx, "source": "trivy"} if license_spdx else None,
               "artifact": {"applicable": True, "kind": "source-tree", "sha256": uuid.uuid4().hex * 2, "files": 12, "bytes": 3456}}
              if provenance is ... else provenance)
    await db.execute(
        """INSERT INTO mcp_intake_requests(id, submitted_by, display_name, repository_url, requested_transport, purpose, status, risk_level,
               commit_sha, source_ref, evidence, validated_at, intake_kind, provenance, risk_input)
           VALUES (%s,%s,%s,%s,'stdio','시험용 소스 도입입니다.',%s,%s,%s,%s,%s,now(),'repository',%s,%s)""",
        (intake, applicant, name, f"https://github.com/example/{name}", status or ("HOLD" if critical else "VALIDATED"),
         "CRITICAL" if critical else "LOW", commit, source_ref, Jsonb({"scanners": scanners, "reports": []}), Jsonb(record or {}), Jsonb(impact_input())))
    findings = [{"severity": "CRITICAL", "id": f"CVE-2026-{1000 + i}", "title": "x", "target": "requirements.txt"} for i in range(critical)]
    stamp = None if db_age_days is None else datetime.now(UTC) - timedelta(days=db_age_days)
    for scanner, version in (("Syft", "v1.51.1"), ("Trivy", "0.74.0"), ("Semgrep", "1.172.0"), ("Gitleaks", "8.30.1")):
        if scanner.lower() in no_report:
            continue
        await db.execute(
            """INSERT INTO supply_chain_reports(scanner, scanner_version, source_ref, report_path, status, critical_count, high_count,
                   medium_count, vuln_db_updated_at, summary) VALUES (%s,%s,%s,%s,'IMPORTED',%s,0,0,%s,%s)""",
            (scanner, version, source_ref, f"/reports/intake-{intake}-{scanner.lower()}.json", critical if scanner == "Trivy" else 0,
             stamp if scanner == "Trivy" else None, Jsonb({"findings": findings if scanner == "Trivy" else []})))
    return intake


async def status_of(intake: str) -> str:
    return (await db.fetch_one("SELECT status FROM mcp_intake_requests WHERE id=%s", (intake,)))["status"]


async def repository_gate(console: httpx.AsyncClient) -> None:
    published = AsyncMock(side_effect=lambda row: ("http://git.lab/mcp/x", {"match": True, "source": "internal-repo-archive",
                                                                           "sha256": row["provenance"]["artifact"]["sha256"], "files": 12, "bytes": 3456}))
    with patch.object(agent_service, "publish_internal_repo", published):
        as_("wbsb-admin-a")
        for label, kwargs, needle in (
            ("취약점 DB가 7일보다 오래됨", {"db_age_days": 10}, "취약점 DB"),
            ("취약점 DB 시각 없음", {"db_age_days": None}, "갱신 시각 없음"),
            ("검사기 실패", {"failed": ("trivy",)}, "Trivy 검사 미완료"),
            ("보고서 없음", {"no_report": ("trivy",)}, "Trivy 보고서 없음"),
            ("출처 기록 없음", {"provenance": {}}, "출처 정보 누락"),
            ("라이선스 없음", {"license_spdx": None}, "라이선스"),
        ):
            intake = await seed_repo("wbsb-emp", "gate-" + uuid.uuid4().hex[:6], **kwargs)
            before = published.await_count
            response = await console.post(f"/api/mcp-requests/{intake}/approve", json=approval_body())
            check(response.status_code == 409 and needle in response.json()["detail"], f"{label}: {response.status_code} {response.text}")
            check(await status_of(intake) == "HOLD" and published.await_count == before, f"{label}: 보류가 아니거나 사본을 게시함")
            held = [e for e in await events("intake-hold", intake)]
            check(held and held[-1]["outcome"] == "held", f"{label}: 보류 기록 없음")
        ok("검사 실패·보고서 없음·취약점 DB 7일 초과/시각 없음·출처 누락은 승인되지 않고 보류된다")

        edge = await seed_repo("wbsb-emp", "edge-" + uuid.uuid4().hex[:6], db_age_days=6.9)
        check((await console.post(f"/api/mcp-requests/{edge}/approve", json=approval_body())).status_code == 200, "6.9일 된 DB는 통과해야 함")
        ok("취약점 DB가 기준(7일) 안이면 통과한다")

        attested = await seed_repo("wbsb-emp", "lic-" + uuid.uuid4().hex[:6], license_spdx=None)
        done = await console.post(f"/api/mcp-requests/{attested}/approve", json=approval_body(license="Apache-2.0"))
        check(done.status_code == 200, f"승인자 기재 라이선스: {done.text}")
        record = (await db.fetch_one("SELECT provenance FROM mcp_intake_requests WHERE id=%s", (attested,)))["provenance"]
        check(record["license"] == {"spdx": "Apache-2.0", "source": "operator", "by": "wbsb-admin-a"} and record["verification"]["match"] is True, f"{record}")
        ok("검사기가 읽지 못한 라이선스는 승인자가 기재하고 그 사실이 기록된다")

        mismatch = await seed_repo("wbsb-emp", "mismatch-" + uuid.uuid4().hex[:6])
        published.side_effect = agent_service.ProvenanceMismatch("기록한 해시 aaaa · 사본 해시 bbbb")
        refused = await console.post(f"/api/mcp-requests/{mismatch}/approve", json=approval_body())
        check(refused.status_code == 409 and await status_of(mismatch) == "HOLD", f"해시 불일치: {refused.status_code}")
        check((await events("provenance-mismatch", mismatch))[-1]["outcome"] == "held", "불일치 기록")
        ok("사본의 해시가 기록과 다르면 보류되고 등록되지 않는다")
        published.side_effect = lambda row: ("http://git.lab/mcp/x", {"match": True, "sha256": row["provenance"]["artifact"]["sha256"], "files": 12, "bytes": 3456})

        # critical finding: blocked until a different administrator accepts it for a limited time
        critical = await seed_repo("wbsb-admin-b", "crit-" + uuid.uuid4().hex[:6], critical=1)
        stuck = await console.post(f"/api/mcp-requests/{critical}/approve", json=approval_body())
        check(stuck.status_code == 409 and await status_of(critical) == "HOLD", "치명적 발견이 승인됨")
        as_("wbsb-admin-b")
        self_accept = await console.post(f"/api/mcp-requests/{critical}/accept-risk", json={"reason": "신청자 본인이 수용하려는 시도입니다.", "days": 7})
        check(self_accept.status_code == 403 and (await events("risk-accept", critical))[-1]["outcome"] == "refused", f"신청자의 위험 수용: {self_accept.status_code}")
        as_("wbsb-admin-a")
        short_reason = await console.post(f"/api/mcp-requests/{critical}/accept-risk", json={"reason": "짧음", "days": 7})
        check(short_reason.status_code == 422, "짧은 사유가 통과함")
        long_term = await console.post(f"/api/mcp-requests/{critical}/accept-risk", json={"reason": "기한이 너무 긴 수용 시도입니다.", "days": 31})
        check(long_term.status_code == 422, "기한 상한이 없음")
        accepted = await console.post(f"/api/mcp-requests/{critical}/accept-risk", json={"reason": "격리된 시험 환경에서만 쓰고 7일 안에 다시 검토합니다.", "days": 7})
        check(accepted.status_code == 200 and await status_of(critical) == "VALIDATED", f"위험 수용: {accepted.text}")
        check((await console.post(f"/api/mcp-requests/{critical}/approve", json=approval_body())).status_code == 200, "수용 뒤 승인")
        ok("치명적 발견은 다른 관리자가 사유와 기한(최대 30일)으로 수용해야 승인할 수 있다")
        return critical


async def accepted_risk_lifecycle(console: httpx.AsyncClient, intake: str) -> None:
    Upstream.search_schema = SEARCH_SCHEMA
    row = await db.fetch_one("SELECT * FROM mcp_intake_requests WHERE id=%s", (intake,))
    found = await core.discover_for_registration(ENDPOINT)
    scope = {"server_id": "codesrv", "endpoint": ENDPOINT, "catalog_hash": found["catalog_hash"], "tools": {"search": "r"}, "data_class": "nonimportant",
             "valid_days": 30, "poisoning_ack": False, "tool_reviews": {"search": REVIEWS["search"]}}
    as_("wbsb-admin-a")
    registered = await console.post(f"/api/mcp-requests/{intake}/register", json=scope)
    check(registered.status_code == 200, f"소스 서버 등록: {registered.text}")
    server = registry.server("codesrv")
    check(server["provenance"]["artifact"]["sha256"] == row["provenance"]["artifact"]["sha256"] and server["license"] == "MIT", "등록에 출처 기록이 실림")
    linked = await db.fetch_all("SELECT scanner FROM supply_chain_reports WHERE source_ref=%s", (registry.source_ref(server),))
    check({r["scanner"] for r in linked} == {"Syft", "Trivy", "Semgrep", "Gitleaks"}, f"승인된 릴리스에 연결된 보고서: {linked}")
    contract = await core._contract("codesrv", "search")
    check(contract["critical_vulnerabilities"] == 0 and contract["critical_accepted"] == 1, f"수용 중 계약: {contract}")
    ok("수용 기한 안에서는 치명적 발견이 보이되 정책에는 0으로 전달되고, 보고서는 승인된 릴리스에 연결된다")
    await db.execute("UPDATE accepted_risks SET expires_at = now() - interval '1 minute' WHERE intake_id=%s", (intake,))
    contract = await core._contract("codesrv", "search")
    check(contract["critical_vulnerabilities"] == 1 and contract["critical_accepted"] == 0, f"만료 뒤 계약: {contract}")
    before = Upstream.calls
    blocked = await call("wbsb-emp", "codesrv", "search", {"q": "x"})
    check(blocked["decision"] == "Block" and blocked["policy_id"] == "MCP-SUPPLY-001" and Upstream.calls == before, f"만료 뒤 호출: {blocked['policy_id']}")
    lapsed = await review.lapse_expired_acceptances()
    check([r["id"] for r in lapsed] == [row["id"]] and await status_of(intake) == "HOLD", f"보류 복귀: {lapsed}")
    check((await events("risk-lapse", intake))[-1]["outcome"] == "held" and await core.renew_approvals() == [], "기록 또는 갱신")
    again = await console.post(f"/api/mcp-requests/{intake}/approve", json=approval_body())
    check(again.status_code == 409, "만료된 수용으로 다시 승인됨")
    ok("위험 수용이 만료되면 요청은 보류로 돌아가고 호출은 MCP-SUPPLY-001로 거부되며 갱신되지 않는다")
    await core.deregister_server("codesrv", "wbsb-admin-a")


# ── audit annotations ──────────────────────────────────────────────────────────────────────────────

async def annotations(console_gateway: httpx.AsyncClient) -> None:
    rows = await db.fetch_all("SELECT id, entry_sha256, prev_sha256 FROM decisions ORDER BY id")
    check(len(rows) >= 6, "원장 행이 부족함")
    first, last = rows[1]["id"], rows[3]["id"]
    baseline = await core.verify_audit_chain()
    check(baseline["intact"], f"기준 원장: {baseline}")
    as_("wbsb-admin-a")
    response = await console_gateway.post("/api/audit/annotations", json={"first_id": first, "last_id": last, "reason": "신청자가 스스로 승인한 시험 대상이라 무효입니다."})
    check(response.status_code == 201, f"무효 처리: {response.text}")
    for bad, status in (({"first_id": first, "last_id": last, "reason": "신청자가 스스로 승인한 시험 대상이라 무효입니다."}, 422),
                        ({"first_id": first, "last_id": last, "reason": "짧음"}, 422), ({"first_id": last, "last_id": first, "reason": "범위가 뒤집힌 요청입니다."}, 422),
                        ({"first_id": 10 ** 9, "last_id": 10 ** 9 + 1, "reason": "없는 행을 가리키는 요청입니다."}, 422)):
        got = await console_gateway.post("/api/audit/annotations", json=bad)
        check(got.status_code == status, f"{bad}: {got.status_code}")
    after = await core.verify_audit_chain()
    check(after["intact"] and after["checked"] == baseline["checked"], f"원장 무결성: {after}")
    check([dict(r) for r in await db.fetch_all("SELECT id, entry_sha256, prev_sha256 FROM decisions ORDER BY id")] == [dict(r) for r in rows], "판정 행이 바뀜")
    feed = await activity.recent(limit=100)
    flagged = {r["id"] for r in feed["rows"] if r.get("invalid")}
    check(flagged == {r["id"] for r in rows if first <= r["id"] <= last}, f"활동 목록의 무효 표시: {flagged}")
    check((await audit.detail(first))["invalid"]["reason"].startswith("신청자가") and (await audit.detail(rows[0]["id"]))["invalid"] is None, "감사 상세")
    listed = (await audit.events(limit=100))["events"]
    check({e["id"] for e in listed if e["invalid"]} == flagged, "감사 목록")
    for statement in ("UPDATE decisions SET reason='x' WHERE id=%s", "DELETE FROM decisions WHERE id=%s"):
        try:
            await db.execute(statement, (first,))
            raise AssertionError("판정 행이 수정·삭제됨")
        except pg_errors.RaiseException:
            pass
    for statement in ("UPDATE audit_annotations SET reason='x'", "DELETE FROM audit_annotations", "UPDATE approval_events SET reason='x'", "DELETE FROM approval_events"):
        try:
            await db.execute(statement)
            raise AssertionError(f"{statement} 가 통과함")
        except pg_errors.RaiseException:
            pass
    ok("무효 처리는 판정 행과 해시 체인을 바꾸지 않고 활동·감사 목록에 '무효 처리'로 표시된다")
    ok("판정 원장·무효 처리·승인 기록은 UPDATE/DELETE가 거부된다")


async def amain() -> None:
    await setup()
    registered_upstream = [patch.object(upstream, "discover", Upstream.discover), patch.object(core, "_call_upstream", Upstream.call),
                           patch.object(agent_service, "current_identity", identity), patch.object(agent_service, "gateway_proxy", proxy),
                           patch.object(privacy, "mask_payload", no_masking), patch.object(privacy, "analyze", no_findings)]
    for patcher in registered_upstream:
        patcher.start()
    main.app.dependency_overrides[main.admin_caller] = identity
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=agent_service.app), base_url="http://console") as console, \
                httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://gateway") as gateway:
            intake = await remote_service_flow(console)
            await positive_control()
            await unreviewed_tool()
            await expiry_revocation_contract_change(intake)
            await minimal_set(console)
            await delegation(console)
            critical = await repository_gate(console)
            await accepted_risk_lifecycle(console, critical)
            await annotations(gateway)
    finally:
        for patcher in registered_upstream:
            patcher.stop()
        await db.close()
    print(f"PASS {len(PASSED)} checks")


if __name__ == "__main__":
    signing_keys()
    with isolated_disposal():
        asyncio.run(amain())
