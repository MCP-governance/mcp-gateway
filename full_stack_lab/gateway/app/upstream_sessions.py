"""Process-local, conversation-bound MCP sessions (D-115); no response cache."""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass


downstream: ContextVar[tuple[str, str] | None] = ContextVar("upstream_downstream", default=None)


def conversation_id(conversation):
    return hashlib.sha256(json.dumps(conversation).encode()).hexdigest()


@dataclass(frozen=True)
class Key:
    principal: str
    downstream: tuple[str, str]
    server: str
    credential: str
    endpoint: str
    protocol: str
    timeout: float
    internal: bool = False


class Closed(RuntimeError):
    pass


class Lease:
    def __init__(self, key, factory, validate):
        self.key = key
        self.validate = validate
        self.busy = True
        self.reused = False
        self.evicted = False
        self.born = self.used = time.monotonic()
        self.ready = asyncio.get_running_loop().create_future()
        self.stop = asyncio.Event()
        self.task = asyncio.create_task(self._own(factory))

    async def _own(self, factory):
        # SDK transports own AnyIO cancel scopes: enter and exit on the same task.
        try:
            async with factory() as client:
                self.ready.set_result(client)
                await self.stop.wait()
        except BaseException:
            if not self.ready.done():
                self.ready.set_exception(Closed("Upstream session could not be opened"))
        finally:
            self.evicted = True

    def discard(self):
        self.evicted = True
        if self.ready.done():
            self.stop.set()
        else:
            self.ready.set_exception(Closed("Upstream session was discarded while opening"))
            self.task.cancel()

    def _client(self):
        if self.evicted or self.task.done():
            raise Closed("Upstream session was discarded before dispatch")
        if not self.validate():
            self.discard()
            raise Closed("Upstream credential changed before dispatch")
        return self.ready.result()

    async def list_tools(self, **kwargs):
        return await self._client().list_tools(**kwargs)

    async def call_tool(self, *args, **kwargs):
        result = await self._client().call_tool(*args, **kwargs)
        if result.is_error:
            self.discard()
        return result


class Pool:
    def __init__(self, size=32, idle=60.0, lifetime=600.0):
        self.size, self.idle, self.lifetime = max(1, size), idle, lifetime
        self.entries = {}
        self.changed = asyncio.Condition()
        self.generation = 0

    async def close(self, endpoint=None, principal=None, conversation=None):
        async with self.changed:
            self.generation += 1
            doomed = [lease for key, lease in self.entries.items()
                      if (endpoint is None or key.endpoint == endpoint)
                      and (principal is None or key.principal == principal)
                      and (conversation is None or conversation_id(key.downstream) == conversation)]
            for lease in doomed:
                self.entries.pop(lease.key, None)
                lease.discard()
            self.changed.notify_all()
        await self._finish(doomed)
        return len(doomed)

    async def _finish(self, leases):
        if leases:
            tasks = [lease.task for lease in leases]
            _, pending = await asyncio.wait(tasks, timeout=5)
            for task in pending:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            for lease in leases:
                # A cancelled borrower may never have consumed the opening error.
                if lease.ready.done() and not lease.ready.cancelled():
                    lease.ready.exception()

    async def prune(self, invalid=None, generation=None):
        now = time.monotonic()
        async with self.changed:
            if generation is not None and generation != self.generation:
                raise Closed("Upstream pool changed before session acquisition")
            doomed = [lease for lease in self.entries.values()
                      if lease.evicted or now - lease.born >= self.lifetime
                      or (not lease.busy and now - lease.used >= self.idle)
                      or (invalid is not None and invalid(lease.key))]
            for lease in doomed:
                self.entries.pop(lease.key, None)
                lease.discard()
            if doomed:
                self.generation += 1
            generation = self.generation
            self.changed.notify_all()
        await self._finish(doomed)
        return generation

    @asynccontextmanager
    async def borrow(self, key, factory, validate=lambda: True, generation=None):
        generation = self.generation if generation is None else generation
        generation = await self.prune(lambda old: old.principal == key.principal and old.server == key.server
                                      and (old.credential, old.endpoint, old.protocol, old.timeout, old.internal)
                                      != (key.credential, key.endpoint, key.protocol, key.timeout, key.internal), generation=generation)
        while True:
            retired = None
            async with self.changed:
                if generation != self.generation:
                    raise Closed("Upstream pool changed while waiting for a session")
                lease = self.entries.get(key)
                if lease is not None and not lease.busy and not lease.evicted:
                    lease.busy = True
                    lease.reused = True
                    break
                if lease is None and len(self.entries) < self.size:
                    lease = self.entries[key] = Lease(key, factory, validate)
                    break
                if lease is None:
                    idle = [old for old in self.entries.values() if not old.busy]
                    if idle:
                        retired = min(idle, key=lambda old: old.used)
                        del self.entries[retired.key]
                        retired.discard()
                        self.changed.notify_all()
                if retired is None:
                    # One session per key preserves state during concurrent conversation calls.
                    # core._call_upstream's dispatch_budget also bounds this queue wait.
                    await self.changed.wait()
            if retired is not None:
                await self._finish([retired])
        try:
            await asyncio.shield(lease.ready)
            lease._client()
            yield lease
        except BaseException:
            lease.discard()
            raise
        finally:
            if lease.evicted:
                await self._finish([lease])
            async with self.changed:
                lease.busy = False
                lease.used = time.monotonic()
                if lease.evicted and self.entries.get(key) is lease:
                    del self.entries[key]
                self.changed.notify_all()
