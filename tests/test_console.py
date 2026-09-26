"""Recording, the admin API and the console. The relay must stay byte-for-byte the same."""
import json
import time

import httpx
import pytest
from starlette.testclient import TestClient

from mcp_gateway.app import create_app
from mcp_gateway.config import AdminSettings, HealthSettings, Settings, StoreSettings, Upstream

TOKEN = "admin-token-for-tests-0123"
ADMIN = {"Authorization": f"Bearer {TOKEN}"}


def stream(body: bytes, content_type="application/json", status=200, headers=None):
    return httpx.Response(status, stream=httpx.ByteStream(body), headers={"content-type": content_type, **(headers or {})})


def console(tmp_path, handler, *, token=TOKEN, record_arguments=False, url="http://files:9000/mcp?api_key=secret"):
    settings = Settings(
        {"files": Upstream(url, {"X-Api-Key": "upstream-secret"})},
        admin=AdminSettings(token=token), store=StoreSettings(path=str(tmp_path / "proxy.db"), record_arguments=record_arguments),
    )
    return TestClient(create_app(settings, transport=httpx.MockTransport(handler)))


def rpc(method, id=1, **params):
    return json.dumps({"jsonrpc": "2.0", "id": id, "method": method, "params": params}).encode()


def wait_for_events(client, count, **query):
    # The recorder writes in the background; poll the API the console uses.
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        events = client.get("/admin/api/events", params=query, headers=ADMIN).json()["events"]
        if len(events) >= count:
            return events
        time.sleep(0.05)
    raise AssertionError(f"expected {count} recorded events, got {len(events)}")


def test_recording_keeps_relayed_bytes_identical(tmp_path):
    request_body = rpc("tools/call", 7, name="read_file", arguments={"path": "/notes.md"})
    answer = b'event: message\r\ndata: {"jsonrpc":"2.0","id":7,"result":{"content":[{"type":"text","text":"hi"}]}}\r\n\r\n'
    seen = []

    def handler(request):
        seen.append(request.content)
        return stream(answer, "text/event-stream", headers={"Mcp-Session-Id": "s-1"})

    with console(tmp_path, handler) as client:
        response = client.post("/mcp/files", content=request_body, headers={"Mcp-Session-Id": "s-1", "User-Agent": "claude-code/2.1"})
        assert response.content == answer
        assert seen == [request_body]
        [event] = wait_for_events(client, 1)
    assert (event["outcome"], event["tool"], event["mcp_methods"], event["sse_events"]) == ("ok", "read_file", "tools/call", 1)
    assert event["session"] and event["session"] != "s-1"  # a hash, never the session id itself
    assert event["arguments"] is None
    assert event["bytes_in"] == len(request_body) and event["bytes_out"] == len(answer)


def test_outcomes_tool_error_protocol_error_upstream_error_and_denials(tmp_path):
    answers = iter([
        stream(b'{"jsonrpc":"2.0","id":1,"result":{"isError":true,"content":[{"type":"text","text":"no such file"}]}}'),
        stream(b'{"jsonrpc":"2.0","id":1,"error":{"code":-32601,"message":"Method not found"}}'),
        stream(b"boom", "text/plain", status=500),
    ])
    with console(tmp_path, lambda request: next(answers), record_arguments=True) as client:
        client.post("/mcp/files", content=rpc("tools/call", name="read_file", arguments={"path": "/x"}))
        client.post("/mcp/files", content=rpc("prompts/get", name="p"))
        client.post("/mcp/files", content=rpc("tools/list"))
        client.post("/mcp/nope", content=b"{}")
        client.post("/mcp/files", headers={"Origin": "https://evil.example"})
        events = wait_for_events(client, 5)
    by_outcome = {e["outcome"]: e for e in events}
    assert by_outcome["tool_error"]["error_message"] == "no such file"
    assert json.loads(by_outcome["tool_error"]["arguments"]) == {"path": "/x"}
    assert by_outcome["rpc_error"]["error_code"] == -32601
    assert by_outcome["upstream_error"]["status"] == 500
    denied = [e for e in events if e["outcome"] == "denied"]
    assert {e["reason"] for e in denied} == {"unknown MCP server", "origin is not allowed"}
    assert all(e["source"] == "proxy" for e in denied)


def test_admin_api_needs_the_token_and_redacts_secrets(tmp_path):
    with console(tmp_path, lambda request: stream(b"{}")) as client:
        assert client.get("/admin/api/overview").status_code == 401
        assert client.get("/admin/api/overview", headers={"Authorization": "Bearer wrong-token-000000"}).status_code == 401
        overview = client.get("/admin/api/overview", headers=ADMIN)
        assert overview.status_code == 200
        assert overview.headers["cache-control"] == "no-store"
        config = client.get("/admin/api/config", headers=ADMIN).text
        servers = client.get("/admin/api/servers", headers=ADMIN).json()["servers"]
    assert "secret" not in config and "upstream-secret" not in config
    assert servers[0]["url"] == "http://files:9000/mcp?…"
    assert servers[0]["headers"] == ["X-Api-Key"]


def test_overview_summarises_the_window(tmp_path):
    def handler(request):
        return stream(b'{"jsonrpc":"2.0","id":1,"result":{}}')

    with console(tmp_path, handler) as client:
        for _ in range(3):
            client.post("/mcp/files", content=rpc("tools/call", name="search"))
        client.post("/mcp/files", content=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-11-25", "clientInfo": {"name": "codex-mcp-client", "version": "0.157"}}}).encode())
        wait_for_events(client, 4)
        o = client.get("/admin/api/overview?hours=1", headers=ADMIN).json()
    s = o["summary"]
    assert s["totals"] == {"ok": 4}
    assert s["tools"][0]["tool"] == "search" and s["tools"][0]["n"] == 3
    assert {c["client"] for c in s["clients"]} >= {"codex-mcp-client"}
    assert o["bucket_seconds"] == 300 and s["series"]
    assert o["recorder"]["dropped"] == 0


def test_keys_are_shown_once_and_stored_as_hashes(tmp_path):
    with console(tmp_path, lambda request: stream(b"{}")) as client:
        created = client.post("/admin/api/keys", headers=ADMIN, json={"name": "ysg", "servers": ["files"], "rate_per_minute": 30})
        assert created.status_code == 201
        secret = created.json()["secret"]
        assert secret.startswith("mcpp_")
        listed = client.get("/admin/api/keys", headers=ADMIN).json()
        assert secret not in json.dumps(listed)
        assert "hash" not in listed["keys"][0]
        key_id = listed["keys"][0]["id"]
        assert client.post("/admin/api/keys", headers=ADMIN, json={"name": "x", "servers": ["nope"]}).status_code == 422
        assert client.post("/admin/api/keys", headers=ADMIN, content=b"[]").status_code == 422
        disabled = client.patch(f"/admin/api/keys/{key_id}", headers=ADMIN, json={"disabled": True}).json()["key"]
        assert disabled["disabled_at"]
        assert client.patch("/admin/api/keys/missing", headers=ADMIN, json={"name": "y"}).status_code == 404
    raw = (tmp_path / "proxy.db").read_bytes()
    assert secret.encode() not in raw


def test_console_pages_carry_a_strict_csp(tmp_path):
    with console(tmp_path, lambda request: stream(b"{}")) as client:
        page = client.get("/console/")
        script = client.get("/console/static/console.js")
        module = client.get("/console/static/charts.mjs")
        assert client.get("/console", follow_redirects=False).headers["location"] == "/console/"
        assert client.get("/console/login").status_code == 200
    assert page.status_code == script.status_code == module.status_code == 200
    # Module scripts load only when served as JavaScript (Windows maps .js from the registry).
    assert script.headers["content-type"].startswith("text/javascript")
    assert module.headers["content-type"].startswith("text/javascript")
    for response in (page, script):
        policy = response.headers["content-security-policy"]
        assert "script-src 'self'" in policy and "style-src 'self'" in policy and "frame-ancestors 'none'" in policy
        assert response.headers["x-content-type-options"] == "nosniff"


def test_without_a_token_there_is_no_admin_surface(tmp_path):
    with console(tmp_path, lambda request: stream(b"{}"), token=None) as client:
        for path in ("/admin/api/overview", "/console/", "/console/static/console.js", "/admin/metrics"):
            assert client.get(path, headers=ADMIN).status_code == 404
        assert client.get("/api/ready").json() == {"ready": True, "servers": {"files": "unknown"}}


def test_metrics_count_outcomes(tmp_path):
    with console(tmp_path, lambda request: stream(b'{"jsonrpc":"2.0","id":1,"result":{}}')) as client:
        client.post("/mcp/files", content=rpc("tools/call", name="a"))
        client.post("/mcp/nowhere")
        text = client.get("/admin/metrics", headers=ADMIN).text
    assert 'mcp_proxy_requests_total{server="files",outcome="ok"} 1' in text
    # A route name the config does not know is client input; it must not become a label.
    assert 'mcp_proxy_requests_total{server="(unknown)",outcome="denied"} 1' in text
    assert "nowhere" not in text


@pytest.mark.parametrize("status,state", [(405, "up"), (503, "degraded")])
def test_health_probe_and_readiness(live_server, status, state):
    from starlette.applications import Starlette
    from starlette.responses import Response
    from starlette.routing import Route

    async def upstream(request):
        return Response(status_code=status)

    with live_server(Starlette(routes=[Route("/mcp", upstream)])) as origin:
        settings = Settings({"files": Upstream(origin + "/mcp"), "gone": Upstream("http://127.0.0.1:9/mcp")},
                            admin=AdminSettings(token=TOKEN), health=HealthSettings(timeout_seconds=2))
        with TestClient(create_app(settings)) as client:
            files = client.post("/admin/api/servers/files/check", headers=ADMIN).json()
            gone = client.post("/admin/api/servers/gone/check", headers=ADMIN).json()
            ready = client.get("/api/ready")
    assert (files["state"], files["status"]) == (state, status)
    assert gone["state"] == "down" and gone["error"]
    assert ready.status_code == 503 and ready.json()["servers"]["gone"] == "down"
