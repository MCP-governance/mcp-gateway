"""HTTP clients kept per event loop, so a tools/call reuses warm connections.

Every call used to open a fresh client for OPA (twice) and Presidio (up to four
times): a TCP handshake per request for services one hop away. A client is bound to
the loop that created it, so the cache is keyed by the running loop.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable

import httpx

_clients: dict[str, tuple[asyncio.AbstractEventLoop, httpx.AsyncClient]] = {}


def shared(name: str, factory: Callable[[], httpx.AsyncClient]) -> httpx.AsyncClient:
    loop = asyncio.get_running_loop()
    entry = _clients.get(name)
    if entry is None or entry[0] is not loop or entry[1].is_closed:
        entry = (loop, factory())
        _clients[name] = entry
    return entry[1]


async def close() -> None:
    loop = asyncio.get_running_loop()
    for name, (owner, client) in list(_clients.items()):
        if owner is loop:
            del _clients[name]
            await client.aclose()
