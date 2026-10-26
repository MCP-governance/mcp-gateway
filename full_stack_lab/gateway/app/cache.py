"""Single-flight TTL cache for the admin summary endpoints.

/api/overview and /api/latency each run a dozen aggregate queries, and /api/health
is unauthenticated, so without this a Console poll (or anyone hitting /api/health)
repeats the same work on every call. A short TTL turns N concurrent callers into one
computation (the in-flight Future is shared) without a background refresh task.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Hashable
from typing import Any


class TTLCache:
    def __init__(self, seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.seconds = seconds
        self._clock = clock
        self._entries: dict[Hashable, tuple[float, asyncio.Future]] = {}

    async def get(self, key: Hashable, compute: Callable[[], Awaitable[Any]]) -> Any:
        now = self._clock()
        entry = self._entries.get(key)
        if entry is None or now - entry[0] >= self.seconds:
            future: asyncio.Future = asyncio.get_running_loop().create_future()
            self._entries[key] = (now, future)
            try:
                future.set_result(await compute())
            except BaseException as exc:
                # Let the next call retry instead of waiting out the TTL. A cancelled first caller
                # (client gone) must also release the waiters sharing its Future, or they hang.
                if self._entries.get(key, (None, None))[1] is future:
                    del self._entries[key]
                if isinstance(exc, asyncio.CancelledError):
                    future.cancel()
                    raise
                future.set_exception(exc)
            entry = (now, future)
        return await entry[1]
