"""Admin API and web console. Served only when an admin token is configured.

The console reads what the proxy recorded and manages the proxy's own keys. Like the
governance console on main, it never calls an MCP server: upstream reachability comes
from the HTTP-level probe, and "tools" are the tool names seen in relayed calls.
"""
from __future__ import annotations

import hmac
import math
import mimetypes
import time
from pathlib import Path

import anyio
import httpx
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import __version__

CONSOLE = Path(__file__).parent / "console"
# Browsers refuse a module script not served as JavaScript. On Windows mimetypes reads
# the registry, which often maps .js to text/plain, and it does not know .mjs at all.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/javascript", ".mjs")
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


class Secured:
    """Adds the console's security headers to a wrapped ASGI app (static files)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                names = {name.lower() for name, _ in message.get("headers", [])}
                message["headers"] = list(message.get("headers", [])) + [
                    (name.lower().encode(), value.encode()) for name, value in SECURITY_HEADERS.items()
                    if name.lower().encode() not in names]
            await send(message)
        await self.app(scope, receive, send_with_headers)


def redact_url(url: str) -> str:
    # A query string can carry an API key; the console shows only that there was one.
    parsed = httpx.URL(url)
    return str(parsed.copy_with(query=None)) + ("?…" if parsed.query else "")


def _json(data, status: int = 200) -> JSONResponse:
    return JSONResponse(data, status_code=status, headers=SECURITY_HEADERS)


def _int(value, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def routes(runtime) -> list:
    settings = runtime.settings
    token = settings.admin.token

    async def ready(request: Request) -> JSONResponse:
        states = {name: (runtime.health.latest[name]["state"] if runtime.health else "unknown")
                  for name in settings.servers}
        down = [name for name, state in states.items() if state == "down"]
        return JSONResponse({"ready": not down, "servers": states}, status_code=503 if down else 200)

    public = [Route("/api/ready", ready)]
    if not token:
        return public

    def admin(handler):
        async def guarded(request: Request):
            scheme, _, presented = request.headers.get("authorization", "").partition(" ")
            if scheme.lower() != "bearer" or not hmac.compare_digest(presented.strip().encode(), token.encode()):
                return JSONResponse({"detail": "admin token required"}, status_code=401,
                                    headers={**SECURITY_HEADERS, "WWW-Authenticate": 'Bearer realm="mcp-proxy-admin"'})
            return await handler(request)
        return guarded

    def need_store():
        if runtime.store is None:
            return _json({"detail": "recording is off: set [store] path"}, 409)
        return None

    def server_view(name: str) -> dict:
        upstream = settings.servers[name]
        health = runtime.health.latest.get(name, {}) if runtime.health else {}
        return {
            "name": name, "url": redact_url(upstream.url), "headers": sorted(upstream.headers),
            "health": health, "history": list(runtime.health.history[name]) if runtime.health else [],
            "active": sum(1 for item in runtime.active.values() if item["server"] == name),
            "max_connections": settings.max_connections_per_server,
        }

    async def overview(request: Request) -> JSONResponse:
        hours = _int(request.query_params.get("hours"), 24, 1, 24 * 30)
        bucket = 300 if hours <= 6 else 3600 if hours <= 72 else 86400
        since = time.time() - hours * 3600
        summary = await anyio.to_thread.run_sync(runtime.store.summary, since, bucket) if runtime.store else None
        return _json({
            "version": __version__, "started_at": runtime.started_at, "now": time.time(),
            "window_hours": hours, "bucket_seconds": bucket, "since": since, "summary": summary,
            "servers": [server_view(name) for name in settings.servers],
            "active": len(runtime.active),
            "recorder": {"enabled": runtime.recorder is not None,
                         "written": runtime.recorder.written if runtime.recorder else 0,
                         "dropped": runtime.recorder.dropped if runtime.recorder else 0},
            "auth": {"providers": list(settings.auth.providers)},
        })

    async def events(request: Request) -> JSONResponse:
        if (missing := need_store()) is not None:
            return missing
        query = request.query_params
        after = query.get("after_id")
        before = query.get("before_id")
        rows = await anyio.to_thread.run_sync(lambda: runtime.store.events(
            server=query.get("server") or None, outcome=query.get("outcome") or None,
            principal=query.get("principal") or None, tool=query.get("tool") or None,
            search=(query.get("q") or "").strip()[:100] or None,
            after_id=_int(after, 0, 0, 2**62) if after else None,
            before_id=_int(before, 0, 0, 2**62) if before else None,
            limit=_int(query.get("limit"), 200, 1, 1000)))
        return _json({"events": rows})

    async def event(request: Request) -> JSONResponse:
        if (missing := need_store()) is not None:
            return missing
        row = await anyio.to_thread.run_sync(runtime.store.event, _int(request.path_params["id"], 0, 0, 2**62))
        return _json(row) if row else _json({"detail": "no such event"}, 404)

    async def servers(request: Request) -> JSONResponse:
        return _json({"servers": [server_view(name) for name in settings.servers]})

    async def check(request: Request) -> JSONResponse:
        name = request.path_params["name"]
        if name not in settings.servers:
            return _json({"detail": "unknown server"}, 404)
        return _json(await runtime.health.check(name))

    async def active(request: Request) -> JSONResponse:
        now = time.time()
        rows = sorted(runtime.active.values(), key=lambda item: item["started_at"])
        return _json({"active": [{**item, "age_seconds": round(now - item["started_at"], 1)} for item in rows]})

    async def keys(request: Request) -> JSONResponse:
        if (missing := need_store()) is not None:
            return missing
        rows = await anyio.to_thread.run_sync(runtime.store.keys)
        usage = await anyio.to_thread.run_sync(runtime.store.key_usage, time.time() - 86400)
        return _json({"keys": [{**row, "usage_24h": usage.get(row["id"], {"calls": 0, "denied": 0})} for row in rows],
                      "enabled": "keys" in settings.auth.providers, "servers": sorted(settings.servers)})

    def key_fields(body: dict, *, creating: bool) -> dict | str:
        fields = {}
        if creating or "name" in body:
            name = body.get("name")
            if not isinstance(name, str) or not name.strip() or len(name) > 100:
                return "name must be 1-100 characters"
            fields["name"] = name.strip()
        if creating or "servers" in body:
            chosen = body.get("servers")
            if (not isinstance(chosen, list) or not chosen or any(not isinstance(s, str) for s in chosen)
                    or set(chosen) - set(settings.servers) - {"*"}):
                return "servers must list configured servers or \"*\""
            fields["servers"] = sorted(set(chosen))
        if "rate_per_minute" in body:
            rate = body["rate_per_minute"]
            if isinstance(rate, bool) or not isinstance(rate, int) or not 0 <= rate <= 100000:
                return "rate_per_minute must be 0-100000"
            fields["rate_per_minute"] = rate
        if "expires_days" in body:
            days = body["expires_days"]
            if days is None:
                fields["expires_at"] = None
            elif (isinstance(days, bool) or not isinstance(days, (int, float)) or not math.isfinite(days)
                  or not 0 < days <= 3650):
                return "expires_days must be between 0 and 3650"
            else:
                fields["expires_at"] = time.time() + days * 86400
        if not creating and "disabled" in body:
            if not isinstance(body["disabled"], bool):
                return "disabled must be true or false"
            fields["disabled_at"] = time.time() if body["disabled"] else None
        return fields

    async def body_of(request: Request) -> dict | None:
        try:
            body = await request.json()
        except ValueError:
            return None
        return body if isinstance(body, dict) else None

    async def create_key(request: Request) -> JSONResponse:
        if (missing := need_store()) is not None:
            return missing
        body = await body_of(request)
        fields = key_fields(body, creating=True) if body is not None else "send a JSON object"
        if isinstance(fields, str):
            return _json({"detail": fields}, 422)
        row, secret = await anyio.to_thread.run_sync(lambda: runtime.store.create_key(
            fields["name"], fields["servers"], fields.get("rate_per_minute", 0), fields.get("expires_at")))
        # The secret exists only in this response; the store keeps its hash.
        return _json({"key": row, "secret": secret}, 201)

    async def update_key(request: Request) -> JSONResponse:
        if (missing := need_store()) is not None:
            return missing
        body = await body_of(request)
        fields = key_fields(body, creating=False) if body is not None else "send a JSON object"
        if isinstance(fields, str):
            return _json({"detail": fields}, 422)
        row = await anyio.to_thread.run_sync(lambda: runtime.store.update_key(request.path_params["id"], **fields))
        if row is None:
            return _json({"detail": "no such key"}, 404)
        runtime.auth.forget()
        return _json({"key": row})

    async def config(request: Request) -> JSONResponse:
        store = await anyio.to_thread.run_sync(runtime.store.stats) if runtime.store else None
        return _json({
            "version": __version__,
            "proxy": {
                "connect_timeout_seconds": settings.connect_timeout_seconds,
                "read_timeout_seconds": settings.read_timeout_seconds,
                "write_timeout_seconds": settings.write_timeout_seconds,
                "shutdown_timeout_seconds": settings.shutdown_timeout_seconds,
                "max_connections_per_server": settings.max_connections_per_server,
                "allowed_origins": list(settings.allowed_origins),
            },
            "auth": {
                "providers": list(settings.auth.providers),
                "litellm_url": redact_url(settings.auth.litellm_url) if settings.auth.litellm_url else None,
                "litellm_cache_seconds": settings.auth.litellm_cache_seconds,
                "litellm_default_servers": list(settings.auth.litellm_default_servers),
                "default_rate_per_minute": settings.auth.default_rate_per_minute,
            },
            "store": {"path": settings.store.path, "retention_days": settings.store.retention_days,
                      "record_arguments": settings.store.record_arguments, **(store or {})},
            "health": {"interval_seconds": settings.health.interval_seconds,
                       "timeout_seconds": settings.health.timeout_seconds},
            "servers": [{"name": name, "url": redact_url(up.url), "headers": sorted(up.headers)}
                        for name, up in settings.servers.items()],
        })

    async def metrics(request: Request) -> Response:
        lines = [
            "# HELP mcp_proxy_requests_total Relayed and refused requests since start, by outcome.",
            "# TYPE mcp_proxy_requests_total counter",
        ]
        for (server, outcome), count in sorted(runtime.totals.items()):
            lines.append(f'mcp_proxy_requests_total{{server="{server}",outcome="{outcome}"}} {count}')
        lines += ["# HELP mcp_proxy_active_requests Requests waiting on or streaming from an upstream.",
                  "# TYPE mcp_proxy_active_requests gauge"]
        for name in settings.servers:
            count = sum(1 for item in runtime.active.values() if item["server"] == name)
            lines.append(f'mcp_proxy_active_requests{{server="{name}"}} {count}')
        lines += ["# HELP mcp_proxy_upstream_up 1 when the last probe got an HTTP answer below 500.",
                  "# TYPE mcp_proxy_upstream_up gauge"]
        for name in settings.servers:
            state = runtime.health.latest[name]["state"] if runtime.health else "unknown"
            if state != "unknown":
                lines.append(f'mcp_proxy_upstream_up{{server="{name}"}} {1 if state == "up" else 0}')
        lines += ["# HELP mcp_proxy_records_dropped_total Records lost to a full queue or a failed write.",
                  "# TYPE mcp_proxy_records_dropped_total counter",
                  f"mcp_proxy_records_dropped_total {runtime.recorder.dropped if runtime.recorder else 0}"]
        return PlainTextResponse("\n".join(lines) + "\n", headers={"Cache-Control": "no-store"},
                                 media_type="text/plain; version=0.0.4")

    def page(name: str):
        async def serve(request: Request) -> Response:
            return FileResponse(CONSOLE / name, headers=SECURITY_HEADERS)
        return serve

    async def to_console(request: Request) -> Response:
        return RedirectResponse("/console/")

    return public + [
        Route("/admin/api/overview", admin(overview)),
        Route("/admin/api/events", admin(events)),
        Route("/admin/api/events/{id:int}", admin(event)),
        Route("/admin/api/servers", admin(servers)),
        Route("/admin/api/servers/{name}/check", admin(check), methods=["POST"]),
        Route("/admin/api/active", admin(active)),
        Route("/admin/api/keys", admin(keys)),
        Route("/admin/api/keys", admin(create_key), methods=["POST"]),
        Route("/admin/api/keys/{id}", admin(update_key), methods=["PATCH"]),
        Route("/admin/api/config", admin(config)),
        Route("/admin/metrics", admin(metrics)),
        Route("/console", to_console),
        Route("/console/", page("console.html")),
        Route("/console/login", page("login.html")),
        Mount("/console/static", app=Secured(StaticFiles(directory=CONSOLE / "static"))),
    ]

