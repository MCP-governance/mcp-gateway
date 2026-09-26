"""Is each upstream reachable? An HTTP-level probe; the proxy never speaks MCP itself.

The probe is a GET that asks for JSON rather than an event stream, so a spec-following
MCP server answers at once (usually 405 or 406) instead of opening a stream. Any HTTP
answer below 500 means the server is there; the MCP session is none of our business.
"""
from __future__ import annotations

import time
from collections import deque

import anyio
import httpx

from .config import Settings

HISTORY = 60


class HealthMonitor:
    def __init__(self, settings: Settings, clients: dict[str, httpx.AsyncClient]):
        self.settings = settings
        self.clients = clients
        self.latest: dict[str, dict] = {name: {"state": "unknown"} for name in settings.servers}
        self.history: dict[str, deque] = {name: deque(maxlen=HISTORY) for name in settings.servers}

    async def run(self) -> None:
        while True:
            await self.check_all()
            await anyio.sleep(self.settings.health.interval_seconds)

    async def check_all(self) -> None:
        async with anyio.create_task_group() as group:
            for name in self.settings.servers:
                group.start_soon(self.check, name)

    async def check(self, name: str) -> dict:
        upstream = self.settings.servers[name]
        started = time.monotonic()
        result = {"checked_at": time.time()}
        try:
            with anyio.fail_after(self.settings.health.timeout_seconds):
                request = httpx.Request("GET", upstream.url, headers={**upstream.headers, "Accept": "application/json"})
                response = await self.clients[name].send(request, stream=True)
                await response.aclose()
            result.update(state="up" if response.status_code < 500 else "degraded", status=response.status_code)
        except TimeoutError:
            result.update(state="down", error="timeout")
        except httpx.HTTPError as error:
            result.update(state="down", error=type(error).__name__)
        result["latency_ms"] = round((time.monotonic() - started) * 1000, 1)
        self.latest[name] = result
        self.history[name].append(result)
        return result
