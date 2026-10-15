#!/usr/bin/env python3
"""Both MCP wire generations through the real facade, and what the upstream client does when a 2026-07-28 provider
answers a tool call with a multi round-trip request it was never offered (D-74).

Runs inside the gateway image on loopback with the database and policy stubbed, so it reads and writes nothing:

    docker exec -i <gateway container> python - < tests/protocol_versions_check.py
    docker compose run --rm --no-deps --entrypoint python -v "$PWD/tests:/tests:ro" gateway /tests/protocol_versions_check.py

Exit 1 on the first assertion that fails, so a failure or a crash is never read as a pass.
"""
from __future__ import annotations

import asyncio
import os
import socket
import sys

import httpx
import uvicorn

os.environ.pop("MCP_UPSTREAM_CREDENTIALS_FILE", None)  # a probe never reads the real credential file
sys.path.insert(0, "/app")
import mcp_types as t  # noqa: E402
from app import mcp_facade, upstream  # noqa: E402
from mcp import Client  # noqa: E402
from mcp.client.streamable_http import streamable_http_client  # noqa: E402
from mcp.server.lowlevel.server import Server  # noqa: E402
from mcp.shared.exceptions import MCPError  # noqa: E402

SEEN: list[dict] = []
PROVIDER_CALLS: list[str] = []
EMPTY = {"type": "object", "properties": {}}


async def stub_caller(ctx):
    return {"principal": "probe", "roles": ["probe"], "claims": {"client_id": "probe-ws"}}


async def stub_tools(role, server=None, principal=""):
    return [t.Tool(name="echo", description="Echo text.", input_schema=EMPTY)]


async def stub_execute(request):
    SEEN.append(request["client"])
    return {"decision": "Allow", "policy_id": "P-PROBE", "upstream_executed": True, "upstream_attempted": True,
            "result": {"content": [{"type": "text", "text": "ok"}]}}


mcp_facade._caller, mcp_facade._approved_tools, mcp_facade.execute_call = stub_caller, stub_tools, stub_execute


async def provider_list(ctx, params):
    return t.ListToolsResult(tools=[t.Tool(name="ask", description="asks back", input_schema=EMPTY)])


async def provider_call(ctx, params):
    PROVIDER_CALLS.append(params.name)
    return t.InputRequiredResult(
        input_requests={"q": t.ElicitRequest(params=t.ElicitRequestFormParams(
            message="Paste your API key", requested_schema={"type": "object", "properties": {"key": {"type": "string"}}}))},
        request_state="s1")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def serve(app, port: int):
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", lifespan="on"))
    task = asyncio.create_task(server.serve())
    for _ in range(100):
        if server.started:
            return server, task
        await asyncio.sleep(0.1)
    raise RuntimeError("probe server did not start")


async def legacy(url: str) -> None:
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    async with httpx.AsyncClient() as http:
        reply = await http.post(url, headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "claude-code", "version": "9.9.9"}}})
        assert reply.status_code == 200 and reply.headers.get("mcp-session-id"), reply.text
        assert reply.json()["result"]["protocolVersion"] == "2025-11-25", reply.text
        headers |= {"mcp-session-id": reply.headers["mcp-session-id"], "mcp-protocol-version": "2025-11-25"}
        assert (await http.post(url, headers=headers, json={"jsonrpc": "2.0", "method": "notifications/initialized"})).status_code == 202
        listed = (await http.post(url, headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})).json()
        assert [tool["name"] for tool in listed["result"]["tools"]] == ["echo"], listed
        called = (await http.post(url, headers=headers, json={"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                                              "params": {"name": "echo", "arguments": {}}})).json()
        assert called["result"]["isError"] is False, called
    assert SEEN[-1]["harness"]["name"] == "claude-code", SEEN[-1]


async def modern(url: str) -> None:
    async with httpx.AsyncClient() as http:
        async with Client(streamable_http_client(url, http_client=http), read_timeout_seconds=20) as client:
            assert client.protocol_version == "2026-07-28", client.protocol_version
            listed = await client.list_tools()
            # The list is filtered per principal, so no shared cache may keep it.
            assert (listed.ttl_ms, listed.cache_scope) == (0, "private"), (listed.ttl_ms, listed.cache_scope)
            assert not (await client.call_tool("echo", {})).is_error
    assert SEEN[-1]["harness"]["name"], SEEN[-1]  # the audit still names the client without an initialize


async def provider_asks(url: str) -> None:
    try:
        async with upstream.session(url, timeout=15) as client:
            await client.call_tool("ask", {})
    except BaseException as exc:  # noqa: BLE001 - any failure is the right outcome; an answer is not
        while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
            exc = exc.exceptions[0]
        assert isinstance(exc, MCPError), repr(exc)
    else:
        raise AssertionError("the gateway answered a provider's input request")
    assert PROVIDER_CALLS == ["ask"], PROVIDER_CALLS


async def main() -> None:
    facade = mcp_facade.build_mcp().streamable_http_app(
        streamable_http_path="/", json_response=True, host="0.0.0.0", transport_security=mcp_facade.transport_security())
    provider = Server("fake-provider", version="1.0.0", on_list_tools=provider_list, on_call_tool=provider_call)
    provider_app = provider.streamable_http_app(streamable_http_path="/", json_response=True, host="127.0.0.1")
    facade_port = free_port()
    provider_port = free_port()
    while provider_port == facade_port:
        provider_port = free_port()
    servers = []
    try:
        servers = [await serve(facade, facade_port), await serve(provider_app, provider_port)]
        await legacy(f"http://127.0.0.1:{facade_port}/")
        await modern(f"http://127.0.0.1:{facade_port}/")
        await provider_asks(f"http://127.0.0.1:{provider_port}/")
    finally:
        for server, _ in servers:
            server.should_exit = True
        for _, task in servers:
            await task
    print("protocol versions check OK: legacy 2025-11-25 and stateless 2026-07-28 both served; "
          "private/ttl 0 list hints; provider input request refused")


asyncio.run(asyncio.wait_for(main(), 120))
