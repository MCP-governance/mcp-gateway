from __future__ import annotations

import asyncio
import json
import os
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
from .core import (RATE_LIMIT_CALLS, IMPORTANT_BURST_LIMIT, _policy, _recent_activity,
                   approve_request, execute_call, set_enforcement_mode, supply_chain_coverage,
                   verify_audit_chain)

API = "http://gateway:8080"
EMAILS = {"cust-demo": "customer@bob.local", "emp-demo": "miso@bob.local", "admin-demo": "admin@bob.local"}


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


async def post(path: str, body: dict, principal: str = "cust-demo") -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(API + path, json=body, headers=bearer(principal))
        response.raise_for_status()
        return response.json()


async def run() -> dict:
    checks: list[dict] = []
    await sign_in()
    checks.append(check(len(TOKENS) == 3, "synthetic-login", "gateway는 공개키만 보유하므로 IdP에 로그인"))

    async with httpx.AsyncClient(timeout=30) as client:
        health = (await client.get(API + "/api/health")).json()
        matrix = (await client.get(API + "/api/policy/matrix")).json()
    checks.append(check(health["status"] == "ok", "core-health", json.dumps(health["components"], ensure_ascii=False)))
    checks.append(check(len(matrix["cells"]) == 27, "rego-333-cells", "27 policy combinations"))
    allowed = {("customer", "public", "r")}
    allowed |= {("employee", "public", "r"), ("employee", "nonimportant", "r"), ("employee", "nonimportant", "w"), ("employee", "important", "r")}
    allowed |= {("admin", data_class, action) for data_class in ("public", "nonimportant", "important") for action in ("r", "w", "x")}
    for cell in matrix["cells"]:
        observed = cell["decision"] != "Block"
        expected = (cell["role"], cell["data_class"], cell["action"]) in allowed
        check(observed == expected, "rego-333-exact", json.dumps(cell, ensure_ascii=False))
    checks.append(check(True, "rego-333-exact", "14 permitted or controlled, 13 blocked"))

    scenarios = [
        ("Allow", "cust-demo", {"tool_name": "read_document", "document_id": "notice-001"}, True),
        ("Alert", "emp-demo", {"tool_name": "read_document", "document_id": "secret-001"}, True),
        ("Restrict", "admin-demo", {"tool_name": "send_external", "document_id": "notice-001", "destination": "not-approved.example", "content": "A" * 120}, True),
        ("Approval", "admin-demo", {"tool_name": "send_external", "document_id": "secret-001", "destination": "not-approved.example", "content": "synthetic important"}, False),
        ("Block", "cust-demo", {"tool_name": "read_document", "document_id": "secret-001"}, False),
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
            checks.append(check(result["effective_arguments"]["destination"] == "mentor-demo.invalid" and len(result["effective_arguments"]["content"]) == 80, "restriction-applied", "destination + 80 chars"))
        if expected_decision == "Approval":
            approval_id = result["approval_id"]

    async with httpx.AsyncClient(timeout=10) as client:
        anonymous = await client.post(API + "/api/calls", json={"tool_name": "read_document", "document_id": "notice-001"})
        forged = await client.post(API + "/api/calls", headers={"Authorization": "Bearer not-a-real-token"},
                                   json={"tool_name": "read_document", "document_id": "notice-001"})
        anonymous_approval = await client.post(API + "/api/approvals/" + approval_id + "/approve", json={})
        customer_approval = await client.post(API + "/api/approvals/" + approval_id + "/approve",
                                              headers=bearer("cust-demo"), json={})
    checks.append(check(anonymous.status_code == 401 and forged.status_code == 401, "api-identity-required",
                        "anonymous=%s forged=%s" % (anonymous.status_code, forged.status_code)))
    checks.append(check(anonymous_approval.status_code == 401 and customer_approval.status_code == 403,
                        "approval-identity-required",
                        "anonymous=%s customer=%s" % (anonymous_approval.status_code, customer_approval.status_code)))

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
        supply_block = await execute_call({"user_token": "cust-demo", "tool_name": "read_document", "document_id": "notice-001"})
        checks.append(check(
            supply_block["decision"] == "Block"
            and supply_block["policy_id"] == "MCP-SUPPLY-001"
            and supply_block["effect_before"] == supply_block["effect_after"],
            "supply-chain-gate",
            f"critical report stopped upstream {supply_block['effect_before']}->{supply_block['effect_after']}",
        ))
    finally:
        await db.execute("DELETE FROM supply_chain_reports WHERE scanner='acceptance-fixture'")

    async with httpx2.AsyncClient(headers=bearer("cust-demo"), timeout=30) as http_client:
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
                                       env={"GATEWAY_STDIO_PRINCIPAL": "cust-demo"})
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
        observed = await post("/api/calls", {"tool_name": "read_document", "document_id": "secret-001"}, "cust-demo")
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
    checks.append(check((await post("/api/calls", {"tool_name": "read_document", "document_id": "secret-001"}, "cust-demo"))["decision"] == "Block",
                        "enforce-restored", "관찰 모드를 끄면 즉시 다시 차단"))

    # Volume controls. Flooding the gateway with real calls to trip the ceiling would
    # add a minute to every run and pollute the effect log, so the two halves are
    # checked separately: that the gateway measures, and that OPA decides on it.
    activity = await _recent_activity("cust-demo")
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
    checks.append(check(429 in statuses, "login-attempt-ceiling", f"statuses={sorted(set(statuses))}"))

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

    chain = await verify_audit_chain()
    checks.append(check(chain["intact"], "audit-chain-intact", json.dumps(chain, ensure_ascii=False)))
    checks.append(check(chain["checked"] > 0, "audit-chain-populated", f"{chain['checked']} chained entries"))
    try:
        await db.execute("UPDATE decisions SET reason='tampered' WHERE id=(SELECT max(id) FROM decisions)")
        append_only = False
    except psycopg.errors.InsufficientPrivilege:
        append_only = True
    checks.append(check(append_only, "audit-append-only", "gateway 계정은 decisions를 수정할 수 없음"))

    async with Client(sse_client("http://gateway-sse:8081/sse", headers=bearer("cust-demo"))) as client:
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
