"""Relay HTTP bytes; MCP negotiation and sessions belong to the upstream server."""
from __future__ import annotations

import logging
import os
from contextlib import AsyncExitStack, asynccontextmanager

import anyio
import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

from .config import HOP_HEADERS, Settings, load_config

log = logging.getLogger("mcp_gateway")


def forward_headers(raw: list[tuple[bytes, bytes]], excluded: set[str]) -> list[tuple[bytes, bytes]]:
    # Connection can nominate additional headers that only apply to this hop.
    blocked = HOP_HEADERS | excluded
    for name, value in raw:
        if name.lower() == b"connection":
            blocked |= {part.strip().lower() for part in value.decode("latin-1").split(",")}
    return [(name, value) for name, value in raw if name.decode("latin-1").lower() not in blocked]


async def request_body(request: Request):
    # An empty stream would still go upstream as chunked, giving a bodiless GET or
    # DELETE a body; send no content at all unless the client actually sent some.
    chunks = request.stream()
    first = await anext(chunks)
    if not first:
        return None

    async def replay():
        yield first
        async for chunk in chunks:
            yield chunk
    return replay()


class RelayResponse(StreamingResponse):
    def __init__(self, upstream: httpx.Response):
        self.upstream = upstream
        super().__init__(upstream.aiter_raw(), status_code=upstream.status_code)
        self.raw_headers = forward_headers(upstream.headers.raw, set())

    async def __call__(self, scope, receive, send) -> None:
        try:
            # Watch receive even on ASGI 2.4: an idle SSE stream may never send
            # another event that would otherwise reveal the disconnected client.
            async with anyio.create_task_group() as group:
                async def stream():
                    try:
                        await self.stream_response(send)
                    except OSError:
                        pass
                    finally:
                        group.cancel_scope.cancel()

                group.start_soon(stream)
                await self.listen_for_disconnect(receive)
                group.cancel_scope.cancel()
        finally:
            # Also close on downstream disconnect, cancellation and mid-stream errors.
            with anyio.CancelScope(shield=True):
                await self.upstream.aclose()


def create_app(settings: Settings | None = None, *, transport=None) -> Starlette:
    settings = settings or load_config(os.environ.get("MCP_PROXY_CONFIG", "proxy.toml"))

    @asynccontextmanager
    async def lifespan(app: Starlette):
        timeout = httpx.Timeout(
            connect=settings.connect_timeout_seconds,
            read=settings.read_timeout_seconds or None,
            write=settings.write_timeout_seconds,
            pool=settings.connect_timeout_seconds,
        )
        limits = httpx.Limits(max_connections=settings.max_connections_per_server)
        async with AsyncExitStack() as clients:
            app.state.clients = {name: await clients.enter_async_context(httpx.AsyncClient(
                timeout=timeout, limits=limits, trust_env=False, follow_redirects=False, transport=transport,
            )) for name in settings.servers}
            yield

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "mode": "proxy", "servers": sorted(settings.servers)})

    async def relay(request: Request):
        name = request.path_params["server"]
        upstream = settings.servers.get(name)
        if upstream is None:
            return JSONResponse({"detail": "unknown MCP server"}, status_code=404)
        origins = request.headers.getlist("origin")
        if origins and (len(origins) != 1 or origins[0] not in settings.allowed_origins):
            return JSONResponse({"detail": "origin is not allowed"}, status_code=403)
        excluded = {"host", "authorization"} | {header.lower() for header in upstream.headers}
        headers = forward_headers(request.headers.raw, excluded)
        headers.extend((key.encode("ascii"), value.encode("latin-1")) for key, value in upstream.headers.items())
        url = httpx.URL(upstream.url)
        query = b"&".join(part for part in (url.query, request.scope["query_string"]) if part)
        url = url.copy_with(query=query)
        # A fresh Request avoids replaying cookies collected by the shared connection pool.
        outgoing = httpx.Request(request.method, url, headers=headers, content=await request_body(request))
        try:
            response = await request.app.state.clients[name].send(outgoing, stream=True)
        except httpx.PoolTimeout:
            log.warning("upstream %s connection limit reached", name)
            return JSONResponse({"detail": "upstream connection limit reached"}, status_code=503)
        except httpx.TimeoutException:
            return JSONResponse({"detail": "upstream timeout"}, status_code=504)
        except httpx.HTTPError as error:
            log.warning("upstream %s failed: %s", name, type(error).__name__)
            return JSONResponse({"detail": "upstream unavailable"}, status_code=502)
        return RelayResponse(response)

    methods = ["GET", "POST", "DELETE", "HEAD", "OPTIONS"]
    return Starlette(lifespan=lifespan, routes=[
        Route("/api/health", health),
        Route("/mcp/{server}", relay, methods=methods),
        Route("/mcp/{server}/", relay, methods=methods),
    ])
