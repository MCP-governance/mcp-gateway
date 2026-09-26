import asyncio
import gzip

import httpx
import pytest
from starlette.testclient import TestClient

from mcp_gateway.app import RelayResponse, create_app
from mcp_gateway.config import Settings, Upstream


class Body(httpx.AsyncByteStream):
    def __init__(self, data=b"", *, error=None):
        self.data = data
        self.error = error
        self.closed = False

    async def __aiter__(self):
        yield self.data
        if self.error:
            raise self.error

    async def aclose(self):
        self.closed = True


def proxy(handler, *, upstream=None, **options):
    settings = Settings({"demo": upstream or Upstream("http://upstream:9000/mcp")}, **options)
    return TestClient(create_app(settings, transport=httpx.MockTransport(handler)))


@pytest.mark.parametrize("suffix", ["", "/"])
@pytest.mark.parametrize("method", ["POST", "GET", "DELETE", "OPTIONS"])
def test_relay_method_body_session_and_query(suffix, method):
    calls = []
    body = b'{"jsonrpc":"2.0", "id":"original", "method":"extension/custom", "params":{"x":1}}'
    result = b'{"jsonrpc":"2.0", "id":"original", "result":{"image":"unchanged"}}'
    stream = Body(result)

    def upstream(request):
        calls.append(request)
        return httpx.Response(201, stream=stream, headers={"Mcp-Session-Id": "session-A", "Content-Type": "application/json", "X-Upstream": "original"})

    with proxy(upstream, upstream=Upstream("http://upstream:9000/mcp?fixed=1")) as client:
        response = client.request(method, f"/mcp/demo{suffix}?a=1&a=2&encoded=%2F", content=body, headers={
            "Mcp-Session-Id": "session-A", "MCP-Protocol-Version": "2025-11-25", "Last-Event-ID": "event-9",
            "Authorization": "Bearer employee-token", "Content-Type": "application/json", "Accept": "application/json, text/event-stream",
        })
    assert len(calls) == 1
    request = calls[0]
    assert request.method == method
    assert str(request.url) == "http://upstream:9000/mcp?fixed=1&a=1&a=2&encoded=%2F"
    assert request.content == body
    assert request.headers["host"] == "upstream:9000"
    assert request.headers["mcp-session-id"] == "session-A"
    assert request.headers["mcp-protocol-version"] == "2025-11-25"
    assert request.headers["last-event-id"] == "event-9"
    assert "authorization" not in request.headers
    assert response.status_code == 201
    assert response.content == result
    assert response.headers["mcp-session-id"] == "session-A"
    assert response.headers["x-upstream"] == "original"
    assert stream.closed


@pytest.mark.parametrize("status", [202, 204, 400, 401, 404, 405, 503, 307])
def test_upstream_status_and_errors_not_wrapped_or_retried(status):
    calls = []
    body = b"" if status == 204 else b'original upstream response'

    def handler(request):
        calls.append(request)
        return httpx.Response(status, stream=Body(body), headers={"WWW-Authenticate": "Bearer", "Location": "https://other.example/mcp"})

    with proxy(handler) as client:
        response = client.post("/mcp/demo", content=b"notification", follow_redirects=False)
    assert response.status_code == status
    assert response.content == body
    assert response.headers["www-authenticate"] == "Bearer"
    assert len(calls) == 1


def test_hop_headers_credentials_and_duplicate_response_headers():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, stream=Body(b"ok"), headers=[
            ("Connection", "X-Internal"), ("X-Internal", "hidden"),
            ("Set-Cookie", "one=1"), ("Set-Cookie", "two=2"), ("Mcp-Session-Id", "abc"),
        ])

    with proxy(handler, upstream=Upstream("http://upstream/mcp", {"Authorization": "Bearer service-token", "X-Key": "configured"})) as client:
        response = client.post("/mcp/demo", headers={
            "Connection": "X-Hop", "X-Hop": "hidden", "Proxy-Authorization": "private",
            "Authorization": "Bearer user-token", "X-Key": "client-value",
        })
    assert calls[0].headers["authorization"] == "Bearer service-token"
    assert calls[0].headers["x-key"] == "configured"
    assert "x-hop" not in calls[0].headers
    assert "proxy-authorization" not in calls[0].headers
    assert "x-internal" not in response.headers
    assert response.headers.get_list("set-cookie") == ["one=1", "two=2"]
    assert response.headers["mcp-session-id"] == "abc"


def test_connection_pool_does_not_replay_another_clients_cookies():
    cookies = []

    def handler(request):
        cookies.append(request.headers.get("cookie"))
        return httpx.Response(200, stream=Body(b"ok"), headers={"Set-Cookie": "service-session=private; Path=/"})

    with proxy(handler) as client:
        client.get("/mcp/demo")
        client.cookies.clear()
        client.get("/mcp/demo")
    assert cookies == [None, None]


def test_compressed_response_is_forwarded_without_double_decoding():
    payload = gzip.compress(b"upstream text " * 100)

    def handler(request):
        return httpx.Response(200, stream=Body(payload), headers={"Content-Encoding": "gzip", "Content-Length": str(len(payload))})

    with proxy(handler) as client:
        with client.stream("GET", "/mcp/demo") as response:
            assert b"".join(response.iter_raw()) == payload
            assert response.headers["content-length"] == str(len(payload))


@pytest.mark.parametrize("error,status", [(httpx.ConnectError("secret-url"), 502), (httpx.ReadTimeout("secret-url"), 504)])
def test_transport_failure_does_not_disclose_upstream(error, status):
    calls = []

    def handler(request):
        calls.append(request)
        raise error

    with proxy(handler) as client:
        response = client.post("/mcp/demo", content=b"write")
    assert response.status_code == status
    assert "secret-url" not in response.text
    assert len(calls) == 1


def test_unknown_server_and_legacy_routes_do_not_reach_upstream():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, stream=Body(b"ok"))

    with proxy(handler) as client:
        for path in ("/mcp/unknown", "/mcp/demo/extra", "/mcp/", "/sse", "/api/policy"):
            assert client.post(path).status_code == 404
        assert client.put("/mcp/demo").status_code == 405
        assert client.get("/api/health").json() == {"status": "ok", "mode": "proxy", "servers": ["demo"]}
    assert calls == []


def test_origin_validation():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, stream=Body(b"ok"))

    with proxy(handler, allowed_origins=("http://localhost:8080",)) as client:
        assert client.get("/mcp/demo", headers={"Origin": "https://evil.example"}).status_code == 403
        assert client.get("/mcp/demo", headers=[("Origin", "http://localhost:8080"), ("Origin", "https://evil.example")]).status_code == 403
        assert client.get("/mcp/demo", headers={"Origin": "http://localhost:8080"}).status_code == 200
        assert client.get("/mcp/demo").status_code == 200
    assert len(calls) == 2
    assert calls[0].headers["origin"] == "http://localhost:8080"


@pytest.mark.parametrize("failure", ["disconnect", "send_error", "upstream_error"])
def test_response_always_closes_upstream(failure):
    async def check():
        body = Body(b"event", error=httpx.ReadError("broken") if failure == "upstream_error" else None)
        response = RelayResponse(httpx.Response(200, stream=body))
        sent = asyncio.Event()

        async def send(message):
            sent.set()
            if failure == "send_error":
                raise OSError("closed client")

        async def receive():
            await sent.wait()
            if failure == "disconnect":
                return {"type": "http.disconnect"}
            await asyncio.Event().wait()

        try:
            await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)
        except ExceptionGroup as errors:
            assert failure == "upstream_error"
            assert isinstance(errors.exceptions[0], httpx.ReadError)
        assert body.closed

    asyncio.run(check())
