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

# One shared pool per process. A single execute_call() runs a dozen statements, so
# connecting per statement means a dozen TCP handshakes and authentications for one
# policy decision, and PostgreSQL's max_connections becomes the concurrency limit.
_pool: AsyncConnectionPool | None = None
_pool_lock = asyncio.Lock()


async def pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        async with _pool_lock:
            if _pool is None:
                created = AsyncConnectionPool(
                    DATABASE_URL, min_size=1, max_size=POOL_MAX, timeout=POOL_TIMEOUT,
                    open=False, kwargs={"row_factory": dict_row},
                )
                # wait=False so a not-yet-ready database surfaces at the first query
                # (where wait_until_ready retries) instead of at import time.
                await created.open(wait=False)
                _pool = created
    return _pool


async def close() -> None:
    """Called from each app's lifespan so shutdown does not leak the pool's workers."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def transaction():
    """A connection whose statements commit or roll back together.

    The per-statement helpers each run in their own transaction, which is fine for
    reads and single writes but not for the read-then-write of an audit chain append.
    """
    async with (await pool()).connection() as connection:
        async with connection.transaction():
            yield connection


async def fetch_all(query: str, params: Iterable | None = None) -> list[dict]:
    async with (await pool()).connection() as connection:
        cursor = await connection.execute(query, params or ())
        return list(await cursor.fetchall())


async def fetch_one(query: str, params: Iterable | None = None) -> dict | None:
    async with (await pool()).connection() as connection:
        cursor = await connection.execute(query, params or ())
        return await cursor.fetchone()


async def execute(query: str, params: Iterable | None = None) -> int:
    async with (await pool()).connection() as connection:
        cursor = await connection.execute(query, params or ())
        return cursor.rowcount


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
