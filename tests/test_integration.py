import asyncio
import sys
import threading
import time

import anyio
import httpx
import pytest
from mcp import Client, MCPDeprecationWarning
from starlette.applications import Starlette
from starlette.responses import Response, StreamingResponse
from starlette.routing import Route

from examples.demo_server import create_demo_app
from mcp_gateway import __main__ as command_line
from mcp_gateway.app import create_app
from mcp_gateway.config import Settings, Upstream


class Recorder:
    def __init__(self, app):
        self.app = app
        self.requests = []

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            self.requests.append((scope["method"], scope["path"], dict(scope["headers"])))
        await self.app(scope, receive, send)


@pytest.mark.parametrize("json_response", [True, False], ids=["json", "sse"])
@pytest.mark.parametrize("mode", ["legacy", "auto"])
def test_official_sdk_tools_resources_prompts_and_session(live_server, json_response, mode):
    upstream = Recorder(create_demo_app(json_response=json_response))
    with live_server(upstream) as origin:
        settings = Settings({"demo": Upstream(origin + "/mcp")})
        with live_server(create_app(settings)) as gateway:
            async def exercise():
                async with Client(gateway + "/mcp/demo/", mode=mode) as client:
                    listed = await client.list_tools()
                    assert listed.tools[0].name == "echo"
                    result = await client.call_tool("echo", {"text": "원문 그대로"})
                    assert result.content[0].text == "원문 그대로"
                    assert result.structured_content == {"echo": "원문 그대로"}
                    resources = await client.list_resources()
                    assert str(resources.resources[0].uri) == "demo://message"
                    resource = await client.read_resource("demo://message")
                    assert resource.contents[0].text == "hello from upstream"
                    prompts = await client.list_prompts()
                    assert prompts.prompts[0].name == "greeting"
                    prompt = await client.get_prompt("greeting")
                    assert prompt.messages[0].content.text == "Say hello."
                    if mode == "legacy":
                        with pytest.warns(MCPDeprecationWarning, match="ping is removed"):
                            await client.send_ping()
            asyncio.run(exercise())
    assert upstream.requests
    assert all(path == "/mcp" for _, path, _ in upstream.requests)
    if mode == "legacy":
        assert any(method == "DELETE" for method, _, _ in upstream.requests)
        sessions = {headers[b"mcp-session-id"] for _, _, headers in upstream.requests if b"mcp-session-id" in headers}
        assert len(sessions) == 1


def test_concurrent_clients_keep_distinct_upstream_sessions(live_server):
    upstream = Recorder(create_demo_app(json_response=True))
    with live_server(upstream) as origin:
        with live_server(create_app(Settings({"demo": Upstream(origin + "/mcp")}))) as gateway:
            async def call(text):
                async with Client(gateway + "/mcp/demo", mode="legacy") as client:
                    result = await client.call_tool("echo", {"text": text})
                    return result.content[0].text

            async def exercise():
                assert await asyncio.gather(call("client-A"), call("client-B")) == ["client-A", "client-B"]
            asyncio.run(exercise())
    sessions = {headers[b"mcp-session-id"] for _, _, headers in upstream.requests if b"mcp-session-id" in headers}
    assert len(sessions) == 2


def test_sse_flushes_before_completion_and_disconnect_closes_upstream(live_server):
    closed = threading.Event()

    async def upstream(request):
        async def events():
            try:
                yield b'id: first\nevent: message\ndata: {"message":"original"}\n\n'
                await anyio.sleep_forever()
            finally:
                closed.set()
        return StreamingResponse(events(), media_type="text/event-stream")

    with live_server(Starlette(routes=[Route("/mcp", upstream)])) as origin:
        with live_server(create_app(Settings({"demo": Upstream(origin + "/mcp")}))) as gateway:
            start = time.monotonic()
            with httpx.stream("GET", gateway + "/mcp/demo", timeout=3, trust_env=False) as response:
                assert response.status_code == 200
                # Keep the iterator: dropping it closes the connection and would fake a disconnect.
                chunks = response.iter_raw()
                assert next(chunks) == b'id: first\nevent: message\ndata: {"message":"original"}\n\n'
                assert time.monotonic() - start < 2
                assert not closed.wait(0.3), "upstream stream closed while the client was still reading"
            assert closed.wait(3), "downstream disconnect did not close the idle upstream stream"


def idle_events(closed=None):
    async def endpoint(request):
        async def events():
            try:
                yield b"data: open\n\n"
                await anyio.sleep_forever()
            finally:
                if closed:
                    closed.set()
        return StreamingResponse(events(), media_type="text/event-stream")
    return endpoint


def test_open_streams_to_one_server_do_not_block_another(live_server):
    async def plain(request):
        return Response(b"ok")

    routes = [Route("/events", idle_events()), Route("/plain", plain, methods=["POST"])]
    with live_server(Starlette(routes=routes)) as origin:
        settings = Settings({"events": Upstream(origin + "/events"), "plain": Upstream(origin + "/plain")},
                            max_connections_per_server=2, connect_timeout_seconds=0.3)
        with live_server(create_app(settings)) as gateway, httpx.Client(trust_env=False, timeout=5) as client:
            streams = [client.send(client.build_request("GET", gateway + "/mcp/events"), stream=True) for _ in range(2)]
            try:
                chunks = [response.iter_raw() for response in streams]
                assert [next(chunk) for chunk in chunks] == [b"data: open\n\n"] * 2
                assert client.post(gateway + "/mcp/plain").text == "ok"
                limited = client.get(gateway + "/mcp/events")
                assert limited.status_code == 503
                assert limited.json() == {"detail": "upstream connection limit reached"}
            finally:
                for response in streams:
                    response.close()


def test_command_line_server_stops_despite_idle_stream(live_server, tmp_path, monkeypatch):
    closed = threading.Event()
    with live_server(Starlette(routes=[Route("/mcp", idle_events(closed))])) as origin:
        config = tmp_path / "proxy.toml"
        config.write_text(f'[proxy]\nshutdown_timeout_seconds = 0.2\n[servers.demo]\nurl = "{origin}/mcp"\n')
        launched = {}
        monkeypatch.setattr(sys, "argv", ["mcp-gateway", "--config", str(config)])
        monkeypatch.setattr(command_line.uvicorn, "run", lambda app, **options: launched.update(app=app, **options))
        command_line.main()
        assert launched["timeout_graceful_shutdown"] == 0.2
        options = {key: value for key, value in launched.items() if key not in ("app", "host", "port")}

        with httpx.Client(trust_env=False, timeout=5) as client:
            with live_server(launched["app"], **options) as gateway:
                response = client.send(client.build_request("GET", gateway + "/mcp/demo"), stream=True)
                chunks = response.iter_raw()
                assert next(chunks) == b"data: open\n\n"
                stopping = time.monotonic()
            assert time.monotonic() - stopping < 1.5, "idle SSE stream held the proxy open"
            assert closed.wait(3), "shutdown did not close the upstream stream"
            response.close()


def test_socket_timeout_and_streaming_upload(live_server):
    async def upstream(request):
        body = await request.body()
        if body == b"slow":
            await anyio.sleep(0.3)
        return Response(body, headers={"Mcp-Session-Id": "original-session"})

    with live_server(Starlette(routes=[Route("/mcp", upstream, methods=["POST"])])) as origin:
        settings = Settings({"demo": Upstream(origin + "/mcp")}, read_timeout_seconds=0.1)
        with live_server(create_app(settings)) as gateway:
            async def exercise():
                async def chunks():
                    for value in (b"first", b"second", b"third"):
                        yield value
                        await asyncio.sleep(0.01)
                async with httpx.AsyncClient(trust_env=False) as client:
                    response = await client.post(gateway + "/mcp/demo", content=chunks())
                    assert response.content == b"firstsecondthird"
                    assert response.headers["mcp-session-id"] == "original-session"
                    timed_out = await client.post(gateway + "/mcp/demo", content=b"slow")
                    assert timed_out.status_code == 504
            asyncio.run(exercise())
