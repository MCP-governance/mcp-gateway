from __future__ import annotations

import asyncio
import json
import os
import pathlib
import re
import sys
from datetime import UTC, datetime

import httpx
import httpx2
import psycopg
from mcp import Client, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError

from . import db
from .core import (RATE_LIMIT_CALLS, IMPORTANT_BURST_LIMIT, _policy, _recent_activity, _tool_spec, effect_count,
                   approve_request, execute_call, set_enforcement_mode, supply_chain_coverage,
                   verify_audit_chain)

API = "http://gateway:8080"
EMAILS = {"partner-demo": "partner@bob.local", "emp-demo": "miso@bob.local", "admin-demo": "admin@bob.local"}


TOKENS: dict[str, str] = {}


async def sign_in() -> None:
    """The gateway holds only the public key, so the test logs in like any client."""
    password = os.getenv("MOCK_SSO_PASSWORD", "test-password")
    async with httpx.AsyncClient(timeout=15) as client:
        for principal, email in EMAILS.items():
            response = await client.post(API + "/api/session", json={"email": email, "password": password})
            response.raise_for_status()
            TOKENS[principal] = response.json()["access_token"]


def bearer(principal: str) -> dict:
    """A synthetic signed identity, the only thing any ingress now accepts."""
    return {"Authorization": "Bearer " + TOKENS[principal]}


def check(condition: bool, name: str, details: str = "") -> dict:
    if not condition:
        raise AssertionError(f"{name}: {details}")
    return {"name": name, "status": "PASS", "details": details}


def tool_payload(result) -> dict:
    if result.structured_content is not None:
        return result.structured_content
    for item in result.content:
        text = getattr(item, "text", "")
        try:
            value = json.loads(text)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            continue
    raise AssertionError("MCP tool returned no JSON object")


async def post(path: str, body: dict, principal: str = "partner-demo") -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(API + path, json=body, headers=bearer(principal))
        response.raise_for_status()
        return response.json()


async def run() -> dict:
    checks: list[dict] = []
    await sign_in()
    checks.append(check(len(TOKENS) == 3, "synthetic-login", "gateway는 공개키만 보유하므로 IdP에 로그인"))
    send_spec = await _tool_spec("send_external")
    checks.append(check(send_spec == {"server_id": "mock-http", "registry_name": "send_external", "action": "x"},
                        "registry-is-action-source", json.dumps(send_spec, ensure_ascii=False)))

    async with httpx.AsyncClient(timeout=30) as client:
        health = (await client.get(API + "/api/health")).json()
        matrix = (await client.get(API + "/api/policy/matrix")).json()
    checks.append(check(health["status"] == "ok", "core-health", json.dumps(health["components"], ensure_ascii=False)))
    checks.append(check(len(matrix["cells"]) == 27, "rego-333-cells", "27 policy combinations"))
    allowed = {("partner", "public", "r")}
    allowed |= {("employee", "public", "r"), ("employee", "nonimportant", "r"), ("employee", "nonimportant", "w"), ("employee", "important", "r")}
    allowed |= {("admin", data_class, action) for data_class in ("public", "nonimportant", "important") for action in ("r", "w", "x")}
    for cell in matrix["cells"]:
        observed = cell["decision"] != "Block"
        expected = (cell["role"], cell["data_class"], cell["action"]) in allowed
        check(observed == expected, "rego-333-exact", json.dumps(cell, ensure_ascii=False))
    checks.append(check(True, "rego-333-exact", "14 permitted or controlled, 13 blocked"))

    scenarios = [
        ("Allow", "partner-demo", {"tool_name": "read_document", "document_id": "notice-001"}, True),
        ("Alert", "emp-demo", {"tool_name": "read_document", "document_id": "secret-001"}, True),
        ("Restrict", "admin-demo", {"tool_name": "send_external", "document_id": "notice-001", "destination": "not-approved.example", "content": "A" * 120}, True),
        ("Approval", "admin-demo", {"tool_name": "send_external", "document_id": "secret-001", "destination": "not-approved.example", "content": "synthetic important"}, False),
        ("Block", "partner-demo", {"tool_name": "read_document", "document_id": "secret-001"}, False),
    ]
    approval_id = None
    for expected_decision, principal, body, should_execute in scenarios:
        result = await post("/api/calls", body, principal)
        checks.append(check(result["decision"] == expected_decision, f"decision-{expected_decision.lower()}", result["policy_id"]))
        checks.append(check(result["upstream_executed"] is should_execute, f"effect-{expected_decision.lower()}", f"{result['effect_before']}->{result['effect_after']}"))
        if should_execute and body["tool_name"] != "get_current_time":
            check(result["effect_after"] == result["effect_before"] + 1, "effect-increment")
        if not should_execute:
            check(result["effect_after"] == result["effect_before"], "effect-blocked")
        if expected_decision == "Restrict":
            checks.append(check(result["effective_arguments"]["destination"] == "restricted.invalid" and len(result["effective_arguments"]["content"]) == 80, "restriction-applied", "destination + 80 chars"))
        if expected_decision == "Approval":
            approval_id = result["approval_id"]

    async with httpx.AsyncClient(timeout=10) as client:
        anonymous = await client.post(API + "/api/calls", json={"tool_name": "read_document", "document_id": "notice-001"})
        forged = await client.post(API + "/api/calls", headers={"Authorization": "Bearer not-a-real-token"},
                                   json={"tool_name": "read_document", "document_id": "notice-001"})
        anonymous_approval = await client.post(API + "/api/approvals/" + approval_id + "/approve", json={})
        partner_approval = await client.post(API + "/api/approvals/" + approval_id + "/approve",
                                              headers=bearer("partner-demo"), json={})
    checks.append(check(anonymous.status_code == 401 and forged.status_code == 401, "api-identity-required",
                        "anonymous=%s forged=%s" % (anonymous.status_code, forged.status_code)))
    checks.append(check(anonymous_approval.status_code == 401 and partner_approval.status_code == 403,
                        "approval-identity-required",
                        "anonymous=%s partner=%s" % (anonymous_approval.status_code, partner_approval.status_code)))

    approved = await approve_request(approval_id, "admin-demo")
    checks.append(check(approved["decision"] == "Allow" and approved["upstream_executed"], "approval-revalidation", approved["policy_id"]))
    checks.append(check(approved["effect_after"] == approved["effect_before"] + 1, "approval-effect", f"{approved['effect_before']}->{approved['effect_after']}"))

    expired = await execute_call({"user_token": "admin-demo", "tool_name": "send_external", "document_id": "secret-001", "destination": "outside.example", "content": "expiry test"})
    await db.execute("UPDATE approvals SET expires_at=now()-interval '1 second' WHERE id=%s", (expired["approval_id"],))
    try:
        await approve_request(expired["approval_id"], "admin-demo")
        expired_blocked = False
    except ValueError:
        expired_blocked = True
    checks.append(check(expired_blocked, "approval-expiry", "expired request rejected"))

    stdio_upstream = await post("/api/calls", {"tool_name": "get_current_time", "timezone": "Asia/Seoul"})
    checks.append(check(stdio_upstream["decision"] == "Allow" and stdio_upstream["upstream_executed"], "stdio-upstream", "mcp-server-time"))

    github = await post("/api/calls", {"tool_name": "github_get_file", "owner": "MCP-governance", "repo": "mcp-gateway", "path": "README.md"})
    checks.append(check(github["decision"] == "Block" and github["policy_id"] == "MCP-REGISTRY-002", "github-auth-deferred", "registered but disabled"))

    unknown = await execute_call({"user_token": "admin-demo", "tool_name": "shadow_export", "document_id": "notice-001"})
    checks.append(check(unknown["decision"] == "Block" and unknown["policy_id"] == "MCP-REGISTRY-001", "unregistered-tool", "no upstream execution"))

    await db.execute("DELETE FROM supply_chain_reports WHERE scanner='acceptance-fixture'")
    try:
        await db.execute(
            """INSERT INTO supply_chain_reports(
                 scanner, scanner_version, source_ref, report_path, status, critical_count, summary
               ) VALUES ('acceptance-fixture','1','demo-v1','memory://critical-fixture','TEST',1,'{}')"""
        )
        supply_block = await execute_call({"user_token": "partner-demo", "tool_name": "read_document", "document_id": "notice-001"})
        checks.append(check(
            supply_block["decision"] == "Block"
            and supply_block["policy_id"] == "MCP-SUPPLY-001"
            and supply_block["effect_before"] == supply_block["effect_after"],
            "supply-chain-gate",
            f"critical report stopped upstream {supply_block['effect_before']}->{supply_block['effect_after']}",
        ))
    finally:
        await db.execute("DELETE FROM supply_chain_reports WHERE scanner='acceptance-fixture'")

    async with httpx2.AsyncClient(headers=bearer("partner-demo"), timeout=30) as http_client:
        async with Client(streamable_http_client("http://gateway:8080/mcp/", http_client=http_client)) as client:
            tools = await client.list_tools()
            protocol_version = str(client.protocol_version)
            result = await client.call_tool("read_document", {"document_id": "notice-001"})
            structured = tool_payload(result)
            # Methods this gateway does not mediate are refused, not left undefined.
            refusals = {}
            for label, call in (("resources/list", client.list_resources), ("prompts/list", client.list_prompts)):
                try:
                    await call()
                    refusals[label] = "not refused"
                except MCPError as error:
                    refusals[label] = error.message[:60]
                except Exception as error:
                    refusals[label] = type(error).__name__
    checks.append(check(all("MCP-METHOD-001" in value for value in refusals.values()),
                        "mcp-method-scope", json.dumps(refusals, ensure_ascii=False)))
    checks.append(check({"read_document", "write_document", "send_external", "get_current_time", "github_get_file"} == {tool.name for tool in tools.tools}, "streamable-http-ingress", protocol_version))
    checks.append(check(not result.is_error and structured["decision"] == "Allow", "streamable-http-call", "actual MCP tools/call"))
    checks.append(check(all("user_token" not in (tool.input_schema.get("properties") or {}) for tool in tools.tools),
                        "ingress-schema-has-no-identity", "identity is not a tool argument"))

    # No Authorization header at all: the ingress must refuse rather than fall back
    # to a default principal.
    async with httpx2.AsyncClient(timeout=30) as http_client:
        async with Client(streamable_http_client("http://gateway:8080/mcp/", http_client=http_client)) as client:
            try:
                anonymous_call = await client.call_tool("read_document", {"document_id": "notice-001"})
                anonymous_refused = bool(anonymous_call.is_error)
            except Exception:
                anonymous_refused = True
    checks.append(check(anonymous_refused, "mcp-ingress-identity-required", "unauthenticated tools/call refused"))

    parameters = StdioServerParameters(command=sys.executable, args=["-m", "app.stdio_entry"],
                                       env={"GATEWAY_STDIO_PRINCIPAL": "partner-demo"})
    async with Client(parameters) as client:
        result = await client.call_tool("read_document", {"document_id": "notice-001"})
        structured = tool_payload(result)
    checks.append(check(not result.is_error and structured["decision"] == "Allow", "stdio-ingress", "identity bound at spawn time"))

    unbound = StdioServerParameters(command=sys.executable, args=["-m", "app.stdio_entry"])
    async with Client(unbound) as client:
        try:
            unbound_call = await client.call_tool("read_document", {"document_id": "notice-001"})
            unbound_refused = bool(unbound_call.is_error)
        except Exception:
            unbound_refused = True
    checks.append(check(unbound_refused, "stdio-ingress-identity-required", "unbound stdio ingress refused"))

    # Observation mode: permission opinions are recorded instead of applied, while
    # integrity controls keep enforcing. Both halves matter, so both are checked.
    async with httpx.AsyncClient(timeout=30) as client:
        flipped = await client.put(API + "/api/enforcement", headers=bearer("admin-demo"), json={"mode": "monitor"})
        checks.append(check(flipped.status_code == 200, "monitor-switch", flipped.text[:120]))
        denied = await client.put(API + "/api/enforcement", headers=bearer("emp-demo"), json={"mode": "enforce"})
        checks.append(check(denied.status_code == 403, "monitor-switch-admin-only", str(denied.status_code)))
    try:
        observed = await post("/api/calls", {"tool_name": "read_document", "document_id": "secret-001"}, "partner-demo")
        checks.append(check(
            observed["decision"] == "Allow" and observed["policy_id"] == "P-MONITOR-001"
            and observed["would_decision"] == "Block" and observed["would_policy_id"] == "P-333-DENY-001"
            and observed["upstream_executed"] and observed["effect_after"] == observed["effect_before"] + 1,
            "monitor-observes-permission",
            f"{observed['policy_id']} would={observed['would_policy_id']}"))
        integrity = await execute_call({"user_token": "admin-demo", "tool_name": "shadow_export", "document_id": "notice-001"})
        checks.append(check(
            integrity["decision"] == "Block" and integrity["policy_id"] == "MCP-REGISTRY-001"
            and integrity["would_decision"] is None
            and integrity["effect_after"] == integrity["effect_before"],
            "monitor-still-enforces-integrity", integrity["policy_id"]))
        async with httpx.AsyncClient(timeout=30) as client:
            summary = (await client.get(API + "/api/monitor/summary?hours=1")).json()
        checks.append(check(
            summary["enforcement"] == "monitor" and summary["would_have_stopped"] >= 1
            and summary["affected_principals"] >= 1,
            "monitor-summary", f"{summary['would_have_stopped']} calls would have been stopped"))
    finally:
        await set_enforcement_mode("enforce", "admin-demo")
    checks.append(check((await post("/api/calls", {"tool_name": "read_document", "document_id": "secret-001"}, "partner-demo"))["decision"] == "Block",
                        "enforce-restored", "관찰 모드를 끄면 즉시 다시 차단"))

    # Volume controls. Flooding the gateway with real calls to trip the ceiling would
    # add a minute to every run and pollute the effect log, so the two halves are
    # checked separately: that the gateway measures, and that OPA decides on it.
    activity = await _recent_activity("partner-demo")
    checks.append(check(
        activity["recent_calls"] >= 1 and activity["call_limit"] == RATE_LIMIT_CALLS
        and activity["important_limit"] == IMPORTANT_BURST_LIMIT,
        "volume-signal-measured", json.dumps(activity, ensure_ascii=False)))
    contract = {"registered": True, "enabled": True, "schema_hash_match": True,
                "description_hash_match": True, "version_match": True, "known_tools_only": True,
                "metadata_safe": True, "supplier_approved": True, "critical_vulnerabilities": 0}
    over_rate = await _policy({
        "principal": {"role": "admin"}, "resource": {"data_class": "public"},
        "tool": {"action": "r"}, "approval": {"granted": False}, "contract": contract,
        "context": {**activity, "recent_calls": activity["call_limit"]}})
    checks.append(check(over_rate["policy_id"] == "P-RATE-001", "rate-limit-decision", over_rate["policy_id"]))
    burst = await _policy({
        "principal": {"role": "employee"}, "resource": {"data_class": "important"},
        "tool": {"action": "r"}, "approval": {"granted": False}, "contract": contract,
        "context": {**activity, "recent_important": activity["important_limit"]}})
    checks.append(check(burst["policy_id"] == "P-VOLUME-001" and burst["decision"] == "Approval",
                        "important-burst-escalates", burst["policy_id"]))

    async with httpx.AsyncClient(timeout=30) as client:
        # An address that does not exist, so a real account is not locked out by the test.
        statuses = [(await client.post(API + "/api/session", json={
            "email": "nobody@bob.local", "password": "wrong"})).status_code for _ in range(12)]
        successful = [(await client.post(API + "/api/session", json={
            "email": "partner@bob.local", "password": os.getenv("MOCK_SSO_PASSWORD", "test-password")})).status_code for _ in range(12)]
    checks.append(check(429 in statuses, "login-attempt-ceiling", f"statuses={sorted(set(statuses))}"))
    checks.append(check(all(status == 200 for status in successful), "successful-login-not-throttled", f"statuses={sorted(set(successful))}"))

    # Rejecting is the other half of approving. Without it a reviewer can only approve
    # or let the request expire, and the audit cannot tell refusal from inattention.
    pending = await post("/api/calls", {"tool_name": "send_external", "document_id": "secret-001",
                                        "destination": "not-approved.example", "content": "거부 대상"}, "admin-demo")
    before = effect_count()
    approval = pending["approval_id"]
    async with httpx.AsyncClient(timeout=30) as client:
        empty_note = await client.post(API + f"/api/approvals/{approval}/reject", headers=bearer("admin-demo"), json={"note": ""})
        as_employee = await client.post(API + f"/api/approvals/{approval}/reject", headers=bearer("emp-demo"), json={"note": "안 됩니다"})
        rejected = await client.post(API + f"/api/approvals/{approval}/reject", headers=bearer("admin-demo"),
                                     json={"note": "외부 전송 근거가 부족합니다."})
        after_reject = await client.post(API + f"/api/approvals/{approval}/approve", headers=bearer("admin-demo"), json={})
    checks.append(check(empty_note.status_code == 422 and as_employee.status_code == 403,
                        "approval-reject-guards", f"empty={empty_note.status_code} employee={as_employee.status_code}"))
    checks.append(check(rejected.status_code == 200 and rejected.json()["status"] == "REJECTED"
                        and rejected.json()["review_note"], "approval-reject", rejected.text[:100]))
    checks.append(check(after_reject.status_code == 409, "approval-reject-is-final", str(after_reject.status_code)))
    checks.append(check(effect_count() == before, "approval-reject-no-effect", f"{before}->{effect_count()}"))

    # The department axis is inert until an operator enables it, but the input has to
    # carry real values or turning it on later finds nothing to compare.
    departments = {row["role"]: row["department"] for row in await db.fetch_all("SELECT role, department FROM principals")}
    documents = await db.fetch_all("SELECT id, owner_department, classification_source, classification_version FROM documents")
    owners = {row["id"]: row["owner_department"] for row in documents}
    checks.append(check(all(departments.get(role) for role in ("partner", "employee", "admin"))
                        and owners.get("secret-001") and owners.get("work-001"),
                        "policy-input-organisational-axis",
                        json.dumps({"principals": departments, "documents": owners}, ensure_ascii=False)))
    checks.append(check(all(row["classification_source"] == "manual-registry" and row["classification_version"] for row in documents),
                        "classification-registry-provenance", "모든 합성 문서에 관리대장 출처와 버전이 있음"))
    unchanged = await post("/api/calls", {"tool_name": "read_document", "document_id": "secret-001"}, "emp-demo")
    checks.append(check(unchanged["decision"] == "Alert" and unchanged["policy_id"] == "P-IMPORTANT-ALERT-001",
                        "department-scope-disabled-by-default",
                        f"{unchanged['decision']}/{unchanged['policy_id']}"))

    coverage = {row["server_id"]: row for row in await supply_chain_coverage()}
    checks.append(check(
        coverage["mock-http"]["scan_path"] == "full_stack_lab/mock_server"
        and coverage["mock-stdio"]["scan_path"] == "full_stack_lab/gateway"
        and coverage["github"]["scan_path"] is None,
        "supply-chain-scan-targets",
        json.dumps({k: v["scan_path"] for k, v in coverage.items()}, ensure_ascii=False)))
    checks.append(check(
        all(row["source_ref"] for row in coverage.values()),
        "supply-chain-attribution-key", "모든 서버가 고정된 source_ref를 가짐"))

    # ── PaC 프레임워크 §11 연계 ────────────────────────────────────────────
    # 정책이 관리대장과 예외 대장을 실제로 읽고 집행하는지, 그리고 그 근거가 증적에
    # 남는지 확인한다. Rego 단위 시험은 정책 파일 안에서만 참이므로 여기서 한 번 더
    # 실제 DB·Registry 값으로 확인한다.
    async with httpx.AsyncClient(timeout=30) as client:
        ledger_view = (await client.get(API + "/api/policy/ledger")).json()
    ledger = {entry["policy_id"]: entry for entry in ledger_view["policies"]}
    checks.append(check(
        ledger_view["policy_set"].get("version") and len(ledger) >= 20
        and ledger_view["deployed_rego"]["status"] == "ACTIVE",
        "pac-ledger-published",
        f"{len(ledger)} policies, set {ledger_view['policy_set'].get('version')}"))

    # §11.8 정책 코드만으로 목적과 근거를 대신할 수 없다. Gateway가 직접 내는
    # policy_id도 관리대장에 있어야 한다.
    declared = set()
    for source in (pathlib.Path(__file__).parent).glob("*.py"):
        declared |= {pid for pid in re.findall(r'"((?:P|MCP)-[A-Z0-9][A-Z0-9-]*[A-Z0-9])"', source.read_text(encoding="utf-8"))}
    missing = sorted(declared - set(ledger))
    checks.append(check(not missing, "pac-every-policy-id-has-ledger-entry",
                        f"{len(declared)}개 정책 ID 모두 관리대장에 있음" if not missing else str(missing)))

    # §8 예외: 범위 안에서는 완화되고, 범위 밖 같은 등급 문서는 그대로 차단된다.
    excepted = await post("/api/calls", {"tool_name": "read_document", "document_id": "audit-001"}, "partner-demo")
    checks.append(check(
        excepted["decision"] == "Alert" and excepted["policy_id"] == "P-333-DENY-001"
        and excepted["exception"]["id"] == "EXC-001"
        and "사후 수동 검토 적용" in excepted["obligations"],
        "pac-exception-applies", json.dumps(excepted.get("exception"), ensure_ascii=False)))
    outside = await post("/api/calls", {"tool_name": "read_document", "document_id": "secret-001"}, "partner-demo")
    checks.append(check(
        outside["decision"] == "Block" and outside["policy_id"] == "P-333-DENY-001"
        and outside["exception"] is None,
        "pac-exception-stays-in-scope", f"{outside['decision']}/{outside['policy_id']}"))

    # §11.14 진 정책도 증적에 남는다. 최종 판단만 남기면 충돌 자체를 볼 수 없다.
    conflicting = await post("/api/calls", {"tool_name": "read_document", "document_id": "secret-001"}, "emp-demo")
    checks.append(check(
        conflicting["policy_id"] == "P-IMPORTANT-ALERT-001"
        and {item["policy_id"] for item in conflicting["conflicts"]} == {"P-333-ALLOW-001"}
        and all(item["priority"] > conflicting["priority"] for item in conflicting["conflicts"]),
        "pac-conflicts-recorded", json.dumps(conflicting["conflicts"], ensure_ascii=False)))

    # §11.4.1 승인 유효기간 만료 확인. Registry의 기한만 바꾸고 정책 코드는 건드리지 않는다.
    await db.execute("UPDATE mcp_tools SET approval_valid_until=now()-interval '1 day' WHERE server_id='mock-http' AND name='read_document'")
    try:
        stale = await post("/api/calls", {"tool_name": "read_document", "document_id": "notice-001"}, "partner-demo")
        checks.append(check(
            stale["decision"] == "Block" and stale["policy_id"] == "P-APPROVAL-EXPIRY-001"
            and stale["effect_after"] == stale["effect_before"],
            "pac-expired-approval-blocks", f"{stale['policy_id']} {stale['effect_before']}->{stale['effect_after']}"))
    finally:
        await db.execute("UPDATE mcp_tools SET approval_valid_until=timestamptz '2027-06-30 23:59:59+00' WHERE server_id='mock-http' AND name='read_document'")
    restored = await post("/api/calls", {"tool_name": "read_document", "document_id": "notice-001"}, "partner-demo")
    checks.append(check(restored["decision"] == "Allow", "pac-reapproval-restores", restored["policy_id"]))

    # §11.17 판단 증적: 정책 버전·의무·환경이 감사 테이블에 실제로 들어갔는가.
    recorded = await db.fetch_one(
        "SELECT policy_id, policy_version, obligations, exception_id, conflicts, environment, chain_version"
        " FROM decisions WHERE policy_id='P-333-DENY-001' AND exception_id IS NOT NULL ORDER BY id DESC LIMIT 1")
    checks.append(check(
        bool(recorded) and recorded["policy_version"] == ledger["P-333-DENY-001"]["version"]
        and recorded["exception_id"] == "EXC-001" and recorded["environment"]
        and recorded["chain_version"] == 3 and recorded["obligations"],
        "pac-decision-evidence-recorded", json.dumps(recorded, ensure_ascii=False, default=str)))

    chain = await verify_audit_chain()
    checks.append(check(chain["intact"], "audit-chain-intact", json.dumps(chain, ensure_ascii=False)))
    checks.append(check(chain["checked"] > 0, "audit-chain-populated", f"{chain['checked']} chained entries"))
    try:
        await db.execute("UPDATE decisions SET reason='tampered' WHERE id=(SELECT max(id) FROM decisions)")
        append_only = False
    except psycopg.Error:
        append_only = True
    checks.append(check(append_only, "audit-append-only", "gateway 계정은 decisions를 수정할 수 없음"))

    async with Client(sse_client("http://gateway-sse:8081/sse", headers=bearer("partner-demo"))) as client:
        result = await client.call_tool("read_document", {"document_id": "notice-001"})
        structured = tool_payload(result)
    checks.append(check(not result.is_error and structured["decision"] == "Allow", "legacy-sse-ingress", "compatibility adapter"))

    return {
        "status": "PASS",
        "generated_at": datetime.now(UTC).isoformat(),
        "checks": checks,
        "summary": {"passed": len(checks), "failed": 0},
    }


if __name__ == "__main__":
    try:
        print(json.dumps(asyncio.run(run()), ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False, indent=2))
        raise
