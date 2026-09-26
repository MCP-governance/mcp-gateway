"""Exercise fail-closed checks, exact MCP bytes and transport token boundaries."""
import json

import httpx
import pytest
from fastapi import HTTPException

from services import agent, gateway


TOOLS = [{"name": "echo", "description": "Echo public text", "inputSchema": {"type": "object"}}]


def wire(value, status=200, headers=None):
    data = value if isinstance(value, bytes) else json.dumps(value).encode()
    return httpx.Response(status, stream=httpx.ByteStream(data), headers=headers or {"content-type": "application/json"})


@pytest.fixture
def checks(monkeypatch):
    async def auth(request):
        if request.headers.get("authorization") != "Bearer employee":
            raise HTTPException(401, "Keycloak login required")
        return {"sub": "alice", "roles": ["employee"]}
    monkeypatch.setattr(gateway, "authenticate", auth)
    monkeypatch.setattr(agent, "authenticate", auth)
    monkeypatch.setenv("SERVICE_TOKEN", "internal-only")
    observations = []
    monkeypatch.setattr(gateway, "emit", lambda *args: observations.append(args))
    monkeypatch.setattr(agent, "emit", lambda *args: observations.append(args))
    return observations


@pytest.mark.anyio
@pytest.mark.parametrize("failure,status", [("approval", 403), ("opa", 403), ("presidio", 403),
                                             ("decision-down", 503), ("presidio-down", 503), ("opa-down", 503)])
async def test_denied_calls_never_execute(checks, failure, status):
    calls = []
    def handler(request):
        calls.append(request)
        if request.url.host == "mcp-server":
            assert json.loads(request.content)["method"] == "tools/list"
            return wire({"jsonrpc": "2.0", "id": "gateway-discovery", "result": {"tools": TOOLS}})
        if request.url.path == "/tools/register":
            assert request.headers["x-service-token"] == "internal-only"
            return wire({"approved": failure != "approval", "hash": "one"})
        if request.url.path == "/tools/demo/echo":
            return wire({"approved": failure != "approval", "hash": "one"}, 503 if failure == "decision-down" else 200)
        if request.url.host == "opa":
            return wire({"result": failure != "opa"}, 503 if failure == "opa-down" else 200)
        return wire([{"entity_type": "EMAIL_ADDRESS"}] if failure == "presidio" else [], 503 if failure == "presidio-down" else 200)
    app = gateway.create_app()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as dependencies:
        app.state.client = dependencies
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gateway") as client:
            result = await client.post("/mcp/demo", headers={"authorization": "Bearer employee"},
                                       json={"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "echo", "arguments": {"text": "public"}}})
    assert result.status_code == status
    assert ("mcp-gateway", "decision", {"status": "blocked", "server": "demo", "tool": "echo", "approved": False}) in checks
    assert "public" not in repr(checks)
    assert sum(r.url.host == "mcp-server" for r in calls) == 1


@pytest.mark.anyio
async def test_approved_call_preserves_bytes_and_strips_transport_credentials(checks):
    body = b'{ "jsonrpc":"2.0", "id":4, "method":"tools/call", "params":{"name":"echo", "arguments":{"text":"public"}} }'
    executions = []
    def handler(request):
        if request.url.host == "mcp-server":
            assert "authorization" not in request.headers
            assert "x-litellm-api-key" not in request.headers
            assert "x-service-token" not in request.headers
            assert "x-hop-secret" not in request.headers
            assert request.headers["mcp-session-id"] == "session-a"
            if json.loads(request.content)["method"] == "tools/list":
                return wire({"jsonrpc": "2.0", "id": "gateway-discovery", "result": {"tools": TOOLS}})
            executions.append(request.content)
            return wire(b'data: {"jsonrpc":"2.0","id":4,"result":{"content":[]}}\n\n', headers={"content-type": "text/event-stream", "mcp-session-id": "session-a"})
        if request.url.path == "/tools/register":
            assert json.loads(request.content)["definition"] == TOOLS[0]
            return wire({"hash": "one", "approved": True})
        if request.url.host == "evidence-decision-api":
            return wire({"hash": "one", "approved": True})
        if request.url.host == "opa":
            assert json.loads(request.content)["input"]["subject"] == "alice"
            return wire({"result": True})
        return wire([])
    app = gateway.create_app()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as dependencies:
        app.state.client = dependencies
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gateway") as client:
            result = await client.post("/mcp/demo", content=body,
                                       headers={"authorization": "Bearer employee", "x-litellm-api-key": "employee-secret", "x-service-token": "spoof", "connection": "x-hop-secret", "x-hop-secret": "bad", "mcp-session-id": "session-a"})
    assert result.status_code == 200
    assert result.headers["mcp-session-id"] == "session-a"
    assert result.content.startswith(b"data:")
    assert executions == [body]


@pytest.mark.anyio
async def test_tools_list_sse_registers_definition_and_preserves_result(checks):
    source = b"data: " + json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"tools": TOOLS}}).encode() + b"\n\n"
    registered = []
    def handler(request):
        if request.url.host == "mcp-server":
            return wire(source, headers={"content-type": "text/event-stream"})
        registered.append(json.loads(request.content))
        return wire({"hash": "one", "approved": False})
    app = gateway.create_app()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as dependencies:
        app.state.client = dependencies
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gateway") as client:
            result = await client.post("/mcp/demo", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers={"authorization": "Bearer employee"})
    assert result.content == source
    assert registered == [{"server": "demo", "tool": "echo", "definition": TOOLS[0]}]


@pytest.mark.anyio
async def test_no_auth_and_json_batch_rejected_before_forward(checks):
    app = gateway.create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gateway") as client:
        assert (await client.post("/mcp/demo", content=b"{}")).status_code == 401
        assert (await client.post("/mcp/demo", json=[{"method": "tools/call"}], headers={"authorization": "Bearer employee"})).status_code == 400
        assert (await client.post("/mcp/demo", content=b"x" * (gateway.MAX_BODY + 1), headers={"authorization": "Bearer employee"})).status_code == 413


@pytest.mark.anyio
async def test_agent_uses_separate_litellm_key(checks, monkeypatch):
    monkeypatch.setenv("LITELLM_MASTER_KEY", "service-key")
    seen = []
    def handler(request):
        seen.append(request)
        return wire({"choices": []})
    app = agent.create_app()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as dependencies:
        app.state.client = dependencies
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://agent") as client:
            assert (await client.post("/v1/chat/completions", content=b'{"model":"demo"}', headers={"authorization": "Bearer employee", "x-litellm-api-key": "user"})).status_code == 200
            assert (await client.post("/mcp/demo", content=b'{"jsonrpc":"2.0","method":"ping","id":1}', headers={"authorization": "Bearer employee"})).status_code == 200
    assert seen[0].headers["authorization"] == "Bearer service-key"
    assert "x-litellm-api-key" not in seen[0].headers
    assert seen[1].headers["authorization"] == "Bearer employee"
    assert seen[0].content == b'{"model":"demo"}'


@pytest.mark.anyio
async def test_changed_definition_revokes_previous_approval_before_execution(checks):
    approved = True
    seen = []
    changed = [{**TOOLS[0], "description": "Changed definition"}]
    def handler(request):
        nonlocal approved
        if request.url.host == "mcp-server":
            seen.append(json.loads(request.content)["method"])
            return wire({"jsonrpc": "2.0", "id": "gateway-discovery", "result": {"tools": changed}})
        if request.url.path == "/tools/register":
            assert json.loads(request.content)["definition"]["description"] == "Changed definition"
            approved = False
            return wire({"hash": "changed", "approved": False})
        return wire({"hash": "changed", "approved": approved})
    app = gateway.create_app()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as dependencies:
        app.state.client = dependencies
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gateway") as client:
            result = await client.post("/mcp/demo", headers={"authorization": "Bearer employee"},
                                       json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "echo", "arguments": {}}})
    assert result.status_code == 403
    assert seen == ["tools/list"]


@pytest.mark.anyio
@pytest.mark.parametrize("method", ["GET", "DELETE"])
async def test_empty_transports_have_no_chunked_body(checks, method):
    seen = []
    def handler(request):
        seen.append(request)
        return wire(b"", status=204)
    app = gateway.create_app()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as dependencies:
        app.state.client = dependencies
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gateway") as client:
            result = await client.request(method, "/mcp/demo?resume=1", headers={"authorization": "Bearer employee", "mcp-session-id": "session-a"})
    assert result.status_code == 204
    assert seen[0].content == b""
    assert "transfer-encoding" not in seen[0].headers
    assert seen[0].url.query == b"resume=1"


@pytest.mark.anyio
@pytest.mark.parametrize("module", [gateway, agent])
async def test_proxy_clients_never_reuse_upstream_cookie_between_users(checks, module):
    seen = []
    def handler(request):
        seen.append(request)
        return wire(b"", status=204, headers={"set-cookie": "upstream_session=secret; Path=/"})
    app = module.create_app()
    async with app.router.lifespan_context(app):
        # Use the real configured pool, with only its network transport replaced.
        app.state.client._transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as client:
            for _ in range(2):
                result = await client.delete("/mcp/demo", headers={"authorization": "Bearer employee", "cookie": "client_session=secret"})
                assert result.status_code == 204
        assert app.state.client._trust_env is False
        assert len(app.state.client.cookies) == 0
    assert len(seen) == 2
    assert all("cookie" not in request.headers for request in seen)
