from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime

import httpx
from mcp import Client, StdioServerParameters
from mcp.client.sse import sse_client

from . import db
from .core import approve_request, execute_call

API = "http://gateway:8080"


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


async def post(path: str, body: dict) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(API + path, json=body)
        response.raise_for_status()
        return response.json()


async def run() -> dict:
    checks: list[dict] = []

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
        ("Allow", {"user_token": "cust-demo", "tool_name": "read_document", "document_id": "notice-001"}, True),
        ("Alert", {"user_token": "emp-demo", "tool_name": "read_document", "document_id": "secret-001"}, True),
        ("Restrict", {"user_token": "admin-demo", "tool_name": "send_external", "document_id": "notice-001", "destination": "not-approved.example", "content": "A" * 120}, True),
        ("Approval", {"user_token": "admin-demo", "tool_name": "send_external", "document_id": "secret-001", "destination": "not-approved.example", "content": "synthetic important"}, False),
        ("Block", {"user_token": "cust-demo", "tool_name": "read_document", "document_id": "secret-001"}, False),
    ]
    approval_id = None
    for expected_decision, body, should_execute in scenarios:
        result = await post("/api/calls", body)
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

    stdio_upstream = await post("/api/calls", {"user_token": "cust-demo", "tool_name": "get_current_time", "timezone": "Asia/Seoul"})
    checks.append(check(stdio_upstream["decision"] == "Allow" and stdio_upstream["upstream_executed"], "stdio-upstream", "mcp-server-time"))

    github = await post("/api/calls", {"user_token": "cust-demo", "tool_name": "github_get_file", "owner": "MCP-governance", "repo": "mcp-gateway", "path": "README.md"})
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

    async with Client("http://gateway:8080/mcp/") as client:
        tools = await client.list_tools()
        protocol_version = str(client.protocol_version)
        result = await client.call_tool("read_document", {"user_token": "cust-demo", "document_id": "notice-001"})
        structured = tool_payload(result)
    checks.append(check({"read_document", "write_document", "send_external", "get_current_time", "github_get_file"} == {tool.name for tool in tools.tools}, "streamable-http-ingress", protocol_version))
    checks.append(check(not result.is_error and structured["decision"] == "Allow", "streamable-http-call", "actual MCP tools/call"))

    parameters = StdioServerParameters(command=sys.executable, args=["-m", "app.stdio_entry"])
    async with Client(parameters) as client:
        result = await client.call_tool("read_document", {"user_token": "cust-demo", "document_id": "notice-001"})
        structured = tool_payload(result)
    checks.append(check(not result.is_error and structured["decision"] == "Allow", "stdio-ingress", "actual MCP tools/call"))

    async with Client(sse_client("http://gateway-sse:8081/sse")) as client:
        result = await client.call_tool("read_document", {"user_token": "cust-demo", "document_id": "notice-001"})
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
