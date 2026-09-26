"""PostgreSQL persistence for the architecture service boundaries."""
from __future__ import annotations

import asyncio
import os
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

_pool: AsyncConnectionPool | None = None
_pool_lock = asyncio.Lock()


async def pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        async with _pool_lock:
            if _pool is None:
                created = AsyncConnectionPool(os.environ["DATABASE_URL"], min_size=1, max_size=8,
                                              open=False, kwargs={"row_factory": dict_row})
                await created.open()
                _pool = created
    return _pool


async def close() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def ingest(event: dict[str, Any]) -> dict:
    async with (await pool()).connection() as conn:
        async with conn.transaction():
            await conn.execute(
                "INSERT INTO evidence_events(trace_id, span_id, service, kind, payload) "
                "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (trace_id,span_id) DO NOTHING",
                (event["trace_id"], event["span_id"], event["service"], event["kind"], Jsonb(event)))
            cur = await conn.execute("SELECT * FROM evidence_events WHERE trace_id=%s AND span_id=%s",
                                     (event["trace_id"], event["span_id"]))
            return await cur.fetchone()


async def event(event_id: int) -> dict | None:
    async with (await pool()).connection() as conn:
        cur = await conn.execute("SELECT * FROM evidence_events WHERE id=%s", (event_id,))
        return await cur.fetchone()


async def analyze(event_id: int, risk: str, flags: list[str]) -> dict:
    async with (await pool()).connection() as conn:
        cur = await conn.execute(
            "UPDATE evidence_events SET risk=%s, flags=%s, analyzed_at=now() "
            "WHERE id=%s AND analyzed_at IS NULL RETURNING id,risk,flags",
            (risk, Jsonb(flags), event_id))
        row = await cur.fetchone()
        if row:
            return row
        cur = await conn.execute("SELECT id,risk,flags FROM evidence_events WHERE id=%s", (event_id,))
        return await cur.fetchone()


async def register(server: str, tool: str, digest: str, definition: dict) -> dict:
    async with (await pool()).connection() as conn:
        async with conn.transaction():
            cur = await conn.execute(
                "INSERT INTO tool_contracts(server,tool,hash,definition) VALUES (%s,%s,%s,%s) "
                "ON CONFLICT (server,tool) DO UPDATE SET "
                "approved=CASE WHEN tool_contracts.hash=EXCLUDED.hash THEN tool_contracts.approved ELSE false END, "
                "hash=EXCLUDED.hash, definition=EXCLUDED.definition, updated_at=now() "
                "RETURNING server,tool,hash,approved",
                (server, tool, digest, Jsonb(definition)))
            row = await cur.fetchone()
            await conn.execute("INSERT INTO audit_events(kind,payload) VALUES ('tool.register',%s)", (Jsonb(row),))
            return row


async def tool(server: str, name: str) -> dict | None:
    async with (await pool()).connection() as conn:
        cur = await conn.execute("SELECT server,tool,hash,approved FROM tool_contracts WHERE server=%s AND tool=%s",
                                 (server, name))
        return await cur.fetchone()


async def tools() -> list[dict]:
    async with (await pool()).connection() as conn:
        cur = await conn.execute("SELECT server,tool,hash,approved,updated_at FROM tool_contracts ORDER BY server,tool")
        return list(await cur.fetchall())


async def approve(server: str, tool_name: str, approved: bool, actor: str) -> dict | None:
    async with (await pool()).connection() as conn:
        async with conn.transaction():
            cur = await conn.execute("UPDATE tool_contracts SET approved=%s,updated_at=now() "
                                     "WHERE server=%s AND tool=%s RETURNING server,tool,hash,approved",
                                     (approved, server, tool_name))
            row = await cur.fetchone()
            if row:
                await conn.execute("INSERT INTO audit_events(kind,payload) VALUES ('tool.approval',%s)",
                                   (Jsonb({**row, "actor": actor}),))
            return row


async def events(limit: int) -> list[dict]:
    async with (await pool()).connection() as conn:
        cur = await conn.execute("SELECT id,trace_id,span_id,service,kind,payload,risk,flags,received_at "
                                 "FROM evidence_events ORDER BY id DESC LIMIT %s", (limit,))
        return list(await cur.fetchall())
