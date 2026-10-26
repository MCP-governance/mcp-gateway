from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Iterable
from contextlib import asynccontextmanager

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://mcp:demo-only-change-me@db:5432/mcp_governance"
)
POOL_MAX = int(os.getenv("DB_POOL_MAX", "10"))
POOL_TIMEOUT = float(os.getenv("DB_POOL_TIMEOUT", "10"))
# 0 = psycopg_pool's own default (unlimited queue) - today's behaviour, kept explicit.
POOL_MAX_WAITING = int(os.getenv("DB_POOL_MAX_WAITING", "0"))
# 0 = no timeout, today's behaviour. Refresh-token revocation holds a per-family
# advisory lock for as long as the revocation sweep takes (idp.py FAMILY_LOCK_SQL) and
# the call-reservation path takes its own advisory lock before a policy decision
# (core.py pg_advisory_xact_lock) - a statement/lock timeout here would abort those
# instead of making them wait, so it stays off unless a deployment measures its own
# worst case and opts in.
STATEMENT_TIMEOUT_MS = int(os.getenv("DB_STATEMENT_TIMEOUT_MS", "0"))
LOCK_TIMEOUT_MS = int(os.getenv("DB_LOCK_TIMEOUT_MS", "0"))

ADMIN_POOL_MAX = int(os.getenv("DB_ADMIN_POOL_MAX", "3"))
ADMIN_STATEMENT_TIMEOUT_MS = int(os.getenv("DB_ADMIN_STATEMENT_TIMEOUT_MS", "10000"))

# One shared pool per process. A single execute_call() runs a dozen statements, so
# connecting per statement means a dozen TCP handshakes and authentications for one
# policy decision, and PostgreSQL's max_connections becomes the concurrency limit.
_pool: AsyncConnectionPool | None = None
_pool_lock = asyncio.Lock()

# A second, small pool for the Console's read-only summary endpoints (/api/overview,
# /api/latency, /api/health) so a slow admin query cannot starve the judging pool
# above of connections a policy decision needs.
_admin_pool: AsyncConnectionPool | None = None
_admin_pool_lock = asyncio.Lock()


def _connect_kwargs(statement_timeout_ms: int, lock_timeout_ms: int = 0) -> dict:
    # Session settings go in the startup packet: a SET run from the pool's configure hook
    # leaves the connection in a transaction, and the pool then discards it as broken.
    options = " ".join(f"-c {name}={value}" for name, value in
                       (("statement_timeout", statement_timeout_ms), ("lock_timeout", lock_timeout_ms)) if value)
    return {"row_factory": dict_row, **({"options": options} if options else {})}


async def pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        async with _pool_lock:
            if _pool is None:
                created = AsyncConnectionPool(
                    DATABASE_URL, min_size=1, max_size=POOL_MAX, timeout=POOL_TIMEOUT,
                    max_waiting=POOL_MAX_WAITING, open=False,
                    kwargs=_connect_kwargs(STATEMENT_TIMEOUT_MS, LOCK_TIMEOUT_MS),
                )
                # wait=False so a not-yet-ready database surfaces at the first query
                # (where wait_until_ready retries) instead of at import time.
                await created.open(wait=False)
                _pool = created
    return _pool


async def admin_pool() -> AsyncConnectionPool:
    global _admin_pool
    if _admin_pool is None:
        async with _admin_pool_lock:
            if _admin_pool is None:
                created = AsyncConnectionPool(
                    DATABASE_URL, min_size=1, max_size=ADMIN_POOL_MAX, timeout=POOL_TIMEOUT,
                    open=False, kwargs=_connect_kwargs(ADMIN_STATEMENT_TIMEOUT_MS),
                )
                await created.open(wait=False)
                _admin_pool = created
    return _admin_pool


async def close() -> None:
    """Called from each app's lifespan so shutdown does not leak the pool's workers."""
    global _pool, _admin_pool
    if _pool is not None:
        await _pool.close()
        _pool = None
    if _admin_pool is not None:
        await _admin_pool.close()
        _admin_pool = None


@asynccontextmanager
async def transaction(*, connection=None):
    """A connection whose statements commit or roll back together.

    The per-statement helpers each run in their own transaction, which is fine for
    reads and single writes but not for the read-then-write of an audit chain append.
    """
    if connection is not None:
        async with connection.transaction():
            yield connection
        return
    async with (await pool()).connection() as connection:
        async with connection.transaction():
            yield connection


async def _run(connection, query: str, params: Iterable | None = None):
    if params is None:
        return await connection.execute(query)
    return await connection.execute(query, params)


async def fetch_all(query: str, params: Iterable | None = None, *, connection=None) -> list[dict]:
    if connection is not None:
        cursor = await _run(connection, query, params)
        return list(await cursor.fetchall())
    async with (await pool()).connection() as connection:
        cursor = await _run(connection, query, params)
        return list(await cursor.fetchall())


async def fetch_one(query: str, params: Iterable | None = None, *, connection=None) -> dict | None:
    if connection is not None:
        cursor = await _run(connection, query, params)
        return await cursor.fetchone()
    async with (await pool()).connection() as connection:
        cursor = await _run(connection, query, params)
        return await cursor.fetchone()


async def execute(query: str, params: Iterable | None = None, *, connection=None) -> int:
    if connection is not None:
        cursor = await _run(connection, query, params)
        return cursor.rowcount
    async with (await pool()).connection() as connection:
        cursor = await _run(connection, query, params)
        return cursor.rowcount


async def admin_fetch_all(query: str, params: Iterable | None = None) -> list[dict]:
    """Same as fetch_all(), but off the small admin pool - never the judging one."""
    async with (await admin_pool()).connection() as connection:
        cursor = await _run(connection, query, params)
        return list(await cursor.fetchall())


async def admin_fetch_one(query: str, params: Iterable | None = None) -> dict | None:
    async with (await admin_pool()).connection() as connection:
        cursor = await _run(connection, query, params)
        return await cursor.fetchone()


async def wait_until_ready(timeout: int = 45) -> None:
    started = time.monotonic()
    while True:
        try:
            row = await fetch_one("SELECT 1 AS ok")
            if row and row["ok"] == 1:
                return
        except (psycopg.Error, OSError, asyncio.TimeoutError) as exc:
            last = exc
        else:
            last = None
        if time.monotonic() - started >= timeout:
            raise RuntimeError(f"PostgreSQL did not become ready: {last}")
        await asyncio.sleep(1)
