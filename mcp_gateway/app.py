"""Relay HTTP bytes; MCP negotiation and sessions belong to the upstream server.

What the proxy adds sits on either side of the relay and never changes a byte of it:
before forwarding it may refuse (unknown server, Origin, credential, server not
granted to the key, rate), and while bytes pass it reads copies for the record.
"""
from __future__ import annotations

import hashlib
import itertools
import logging
import math
import os
import time
from collections import Counter, OrderedDict
from contextlib import AsyncExitStack, asynccontextmanager

import anyio
import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

from . import admin
from .auth import CREDENTIAL_HEADERS, Authenticator, Denied, Principal, RateLimiter
from .config import HOP_HEADERS, Settings, load_config
from .health import HealthMonitor
from .observe import COPY_LIMIT, ResponseObserver, summarize_request
from .store import Recorder, Store

log = logging.getLogger("mcp_gateway")


def forward_headers(raw: list[tuple[bytes, bytes]], excluded: set[str]) -> list[tuple[bytes, bytes]]:
    # Connection can nominate additional headers that only apply to this hop.
    blocked = HOP_HEADERS | excluded
    for name, value in raw:
        if name.lower() == b"connection":
            blocked |= {part.strip().lower() for part in value.decode("latin-1").split(",")}
    return [(name, value) for name, value in raw if name.decode("latin-1").lower() not in blocked]


class Capture:
    """A bounded copy of the request body, kept only for the record."""

    def __init__(self, limit: int = COPY_LIMIT):
        self.limit = limit
        self.data = bytearray()
        self.size = 0
        self.truncated = False

    def add(self, chunk: bytes) -> None:
        self.size += len(chunk)
        if self.truncated:
            return
        if len(self.data) + len(chunk) > self.limit:
            self.truncated = True
            self.data.clear()
        else:
            self.data += chunk


async def request_body(request: Request, capture: Capture | None = None):
    # An empty stream would still go upstream as chunked, giving a bodiless GET or
    # DELETE a body; send no content at all unless the client actually sent some.
    chunks = request.stream()
    first = await anext(chunks)
    if not first:
        return None

    async def replay():
        if capture:
            capture.add(first)
        yield first
        async for chunk in chunks:
            if capture:
                capture.add(chunk)
            yield chunk
    return replay()


class RelayResponse(StreamingResponse):
    def __init__(self, upstream: httpx.Response, *, observe=None, done=None):
        self.upstream = upstream
        self.observe = observe
        self.done = done
        self.bytes_out = 0
        self.failure: str | None = None
        super().__init__(self._body(), status_code=upstream.status_code)
        self.raw_headers = forward_headers(upstream.headers.raw, set())

    async def _body(self):
        try:
            async for chunk in self.upstream.aiter_raw():
                self.bytes_out += len(chunk)
                if self.observe:
                    try:
                        self.observe(chunk)
                    except Exception:  # noqa: BLE001 - a record is never worth a broken stream
                        log.exception("response observer failed; recording less detail")
                        self.observe = None
                yield chunk
        except httpx.HTTPError as error:
            self.failure = type(error).__name__
            raise

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
            if self.done:
                try:
                    self.done(self)
                except Exception:  # noqa: BLE001 - the stream is already finished; only the record is lost
                    log.exception("could not record a finished request")


def _hash(value: str | None) -> str | None:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12] if value else None


def _short(value: str | None, limit: int) -> str | None:
    return value if value is None or len(value) <= limit else value[:limit - 1] + "…"


class Runtime:
    """Per-process state shared by the relay, the admin API and the background tasks."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.clients: dict[str, httpx.AsyncClient] = {}
        self.store: Store | None = None
        self.recorder: Recorder | None = None
        self.auth: Authenticator | None = None
        self.limiter = RateLimiter()
        self.health: HealthMonitor | None = None
        self.active: dict[int, dict] = {}
        self.ids = itertools.count(1)
        self.started_at = time.time()
        # Session hash -> (client name, version) learned from initialize, so later
        # calls in the session name the client too. Bounded; old sessions fall out.
        self.sessions: OrderedDict[str, tuple[str | None, str | None]] = OrderedDict()
        # Process-lifetime counters for /admin/metrics; the store keeps the history.
        self.totals: Counter[tuple[str, str]] = Counter()

    def tally(self, server: str | None, outcome: str) -> None:
        # An unknown route name is client input; do not let it grow the label set.
        self.totals[(server if server in self.settings.servers else "(unknown)", outcome)] += 1

    def remember_client(self, session: str | None, name: str | None, version: str | None) -> None:
        if session and name:
            self.sessions[session] = (name, version)
            self.sessions.move_to_end(session)
            while len(self.sessions) > 5000:
                self.sessions.popitem(last=False)


def create_app(settings: Settings | None = None, *, transport=None) -> Starlette:
    settings = settings or load_config(os.environ.get("MCP_PROXY_CONFIG", "proxy.toml"))
    runtime = Runtime(settings)

    @asynccontextmanager
    async def lifespan(app: Starlette):
        timeout = httpx.Timeout(
            connect=settings.connect_timeout_seconds,
            read=settings.read_timeout_seconds or None,
            write=settings.write_timeout_seconds,
            pool=settings.connect_timeout_seconds,
        )
        limits = httpx.Limits(max_connections=settings.max_connections_per_server)
        async with AsyncExitStack() as stack:
            runtime.clients = {name: await stack.enter_async_context(httpx.AsyncClient(
                timeout=timeout, limits=limits, trust_env=False, follow_redirects=False, transport=transport,
            )) for name in settings.servers}
            app.state.clients = runtime.clients
            if settings.store.path:
                runtime.store = Store(settings.store.path)
                stack.callback(runtime.store.close)
                runtime.recorder = Recorder(runtime.store, settings.store.retention_days)
            litellm = None
            if "litellm" in settings.auth.providers:
                litellm = await stack.enter_async_context(httpx.AsyncClient(
                    timeout=httpx.Timeout(5), trust_env=False, follow_redirects=False, transport=transport))
            runtime.auth = Authenticator(settings, runtime.store, litellm)
            runtime.health = HealthMonitor(settings, runtime.clients)
            async with anyio.create_task_group() as tasks:
                probes = anyio.CancelScope()

                async def run_health():
                    with probes:
                        await runtime.health.run()

                if runtime.recorder:
                    tasks.start_soon(runtime.recorder.run)
                if settings.health.interval_seconds:
                    tasks.start_soon(run_health)
                try:
                    yield
                finally:
                    probes.cancel()
                    if runtime.recorder:
                        # Closing the queue lets the writer drain what is left, then stop.
                        await runtime.recorder.close()

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "mode": "proxy", "servers": sorted(settings.servers)})

    async def relay(request: Request):
        started, now = time.monotonic(), time.time()
        name = request.path_params["server"]
        client_ip = request.client.host if request.client else None
        session_header = request.headers.get("mcp-session-id")
        row = {
            "ts": now, "server": _short(name, 64), "http_method": request.method, "client_ip": client_ip,
            "user_agent": _short(request.headers.get("user-agent"), 200), "session": _hash(session_header),
            "principal": client_ip or "anonymous", "auth": "none",
        }

        def refuse(status: int, reason: str, headers: dict | None = None, *, source: str = "proxy",
                   outcome: str = "denied") -> JSONResponse:
            runtime.tally(name, outcome)
            if runtime.recorder:
                runtime.recorder.record({
                    **row, "status": status, "outcome": outcome, "source": source, "reason": reason,
                    "duration_ms": round((time.monotonic() - started) * 1000, 1),
                })
            return JSONResponse({"detail": reason}, status_code=status, headers=headers)

        upstream = settings.servers.get(name)
        if upstream is None:
            return refuse(404, "unknown MCP server")
        origins = request.headers.getlist("origin")
        if origins and (len(origins) != 1 or origins[0] not in settings.allowed_origins):
            return refuse(403, "origin is not allowed")
        try:
            principal: Principal = await runtime.auth.authenticate(request.headers, client_ip)
        except Denied as denial:
            challenge = {"WWW-Authenticate": 'Bearer realm="mcp-proxy"'} if denial.status == 401 else None
            return refuse(denial.status, denial.reason, challenge,
                          outcome="denied" if denial.status < 500 else "proxy_error")
        row.update(principal=principal.name, key_id=principal.key_id, auth=principal.auth)
        if not principal.may_use(name):
            return refuse(403, "server not allowed for this key")
        wait = runtime.limiter.retry_after(principal.key_id or principal.name, principal.rate_per_minute)
        if wait is not None:
            return refuse(429, "rate limit exceeded", {"Retry-After": str(math.ceil(wait))})

        excluded = {"host"} | CREDENTIAL_HEADERS | {header.lower() for header in upstream.headers}
        headers = forward_headers(request.headers.raw, excluded)
        headers.extend((key.encode("ascii"), value.encode("latin-1")) for key, value in upstream.headers.items())
        url = httpx.URL(upstream.url)
        query = b"&".join(part for part in (url.query, request.scope["query_string"]) if part)
        url = url.copy_with(query=query)
        capture = Capture() if runtime.recorder else None
        active_id = next(runtime.ids)
        runtime.active[active_id] = {
            "id": active_id, "server": name, "principal": principal.name, "http_method": request.method,
            "started_at": now, "phase": "waiting",
        }
        # A fresh Request avoids replaying cookies collected by the shared connection pool.
        outgoing = httpx.Request(request.method, url, headers=headers, content=await request_body(request, capture))
        try:
            response = await runtime.clients[name].send(outgoing, stream=True)
        except httpx.PoolTimeout:
            runtime.active.pop(active_id, None)
            log.warning("upstream %s connection limit reached", name)
            return refuse(503, "upstream connection limit reached", outcome="proxy_error")
        except httpx.TimeoutException:
            runtime.active.pop(active_id, None)
            return refuse(504, "upstream timeout", outcome="proxy_error")
        except httpx.HTTPError as error:
            runtime.active.pop(active_id, None)
            log.warning("upstream %s failed: %s", name, type(error).__name__)
            return refuse(502, "upstream unavailable", outcome="proxy_error")
        except BaseException:
            runtime.active.pop(active_id, None)
            raise
        ttfb = round((time.monotonic() - started) * 1000, 1)
        runtime.active[active_id]["phase"] = "streaming"
        if not runtime.recorder:
            def settle(relayed: RelayResponse) -> None:
                runtime.active.pop(active_id, None)
                failed = response.status_code >= 400 or relayed.failure
                runtime.tally(name, "upstream_error" if failed else "ok")
            return RelayResponse(response, done=settle)

        summary = summarize_request(
            bytes(capture.data), truncated=capture.truncated,
            encoded=bool(request.headers.get("content-encoding")), keep_arguments=settings.store.record_arguments)
        session = row["session"] or _hash(response.headers.get("mcp-session-id"))
        runtime.remember_client(session, summary.client_name, summary.client_version)
        client_name, client_version = (summary.client_name, summary.client_version)
        if not client_name and session in runtime.sessions:
            client_name, client_version = runtime.sessions[session]
        runtime.active[active_id].update(tool=summary.tool, method=",".join(summary.methods[:3]) or None)
        observer = ResponseObserver(
            response.headers.get("content-type", ""), response.headers.get("content-encoding", ""), summary.ids)

        def finish(relayed: RelayResponse) -> None:
            runtime.active.pop(active_id, None)
            result = observer.finish()
            if response.status_code >= 400:
                outcome = "upstream_error"
            elif relayed.failure:
                outcome = "upstream_error"
            else:
                outcome = result.outcome or "ok"
            runtime.tally(name, outcome)
            runtime.recorder.record({
                **row, "session": session, "status": response.status_code, "outcome": outcome, "source": "upstream",
                "reason": f"stream broke: {relayed.failure}" if relayed.failure else None,
                "mcp_methods": ",".join(dict.fromkeys(summary.methods))[:300] or None,
                "tool": summary.tool, "target": summary.target, "arguments": summary.arguments,
                "client_name": client_name, "client_version": client_version,
                "protocol_version": summary.protocol_version or request.headers.get("mcp-protocol-version"),
                "request_parse": summary.parse, "response_parse": result.parse,
                "error_code": result.error_code, "error_message": result.error_message,
                "server_methods": ",".join(result.server_methods) or None, "sse_events": result.sse_events,
                "ttfb_ms": ttfb, "duration_ms": round((time.monotonic() - started) * 1000, 1),
                "bytes_in": capture.size, "bytes_out": relayed.bytes_out,
            })

        return RelayResponse(response, observe=observer.feed, done=finish)

    methods = ["GET", "POST", "DELETE", "HEAD", "OPTIONS"]
    app = Starlette(lifespan=lifespan, routes=[
        Route("/api/health", health),
        Route("/mcp/{server}", relay, methods=methods),
        Route("/mcp/{server}/", relay, methods=methods),
        *admin.routes(runtime),
    ])
    app.state.runtime = runtime
    return app
