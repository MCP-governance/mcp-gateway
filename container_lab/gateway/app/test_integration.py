"""Run inside the gateway container against OPA and the mock MCP service."""

from __future__ import annotations

import asyncio
import os
import sys

import httpx

from app.policy_core import sign_assertion


async def main() -> None:
    call = {
        "request_id": f"catalog-{sys.argv[-1]}",
        "session_id": "catalog-test",
        "user_id": "customer-01",
        "agent_id": "catalog-test",
        "tool_call_id": "catalog-call",
        "server_id": "file-mcp",
        "tool_name": "read_file",
        "arguments": {"path": "/data/public/notice.txt"},
    }
    role = "customer"
    async with httpx.AsyncClient(timeout=8) as client:
        response = await client.post(
            "http://127.0.0.1:8080/tool-call",
            json=call,
            headers={"X-Agent-Role": role, "X-Agent-Assertion": sign_assertion(call, role, os.environ["AGENT_ASSERTION_SECRET"])},
        )
        response.raise_for_status()
    output = response.json()
    denied = "--expect-deny" in sys.argv
    assert output["decision"] == ("DENY" if denied else "ALLOW"), output
    assert output["upstream_called"] is not denied, output
    if denied:
        assert output["policy_id"] == "MCP-TOOL-POISON-001", output
    print(f"integration policy check: PASS ({output['policy_id']})")


asyncio.run(main())
