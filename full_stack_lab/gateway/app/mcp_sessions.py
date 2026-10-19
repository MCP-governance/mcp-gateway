"""Inbound MCP session bindings and append-only termination events."""
from __future__ import annotations

import hashlib

from . import db


def _digest(session_id: str) -> str:
    return hashlib.sha256(session_id.encode()).hexdigest()


async def register(session_id: str, principal: str, jti: str, device_id: str | None,
                   server_id: str | None) -> None:
    await db.execute(
        """INSERT INTO mcp_client_sessions(session_hash,principal,token_jti,device_id,server_id)
           VALUES (%s,%s,%s,%s,%s) ON CONFLICT (session_hash) DO NOTHING""",
        (_digest(session_id), principal, jti, device_id, server_id))


async def active(session_id: str, principal: str, jti: str) -> bool:
    return bool(await db.fetch_one(
        """SELECT 1 FROM mcp_client_sessions
            WHERE session_hash=%s AND principal=%s AND token_jti=%s AND terminated_at IS NULL""",
        (_digest(session_id), principal, jti)))


async def terminate(*, reason: str, principal: str | None = None, device_id: str | None = None,
                    server_id: str | None = None, session_id: str | None = None) -> int:
    filters, values = ["terminated_at IS NULL"], []
    for column, value in (("principal", principal), ("device_id", device_id), ("server_id", server_id),
                          ("session_hash", _digest(session_id) if session_id else None)):
        if value is not None:
            filters.append(f"{column}=%s")
            values.append(value)
    async with db.transaction() as connection:
        result = await connection.execute(
            f"UPDATE mcp_client_sessions SET terminated_at=now(), termination_reason=%s WHERE {' AND '.join(filters)}",
            (reason, *values))
        count = result.rowcount
        await connection.execute(
            """INSERT INTO mcp_session_events(reason,principal,device_id,server_id,session_hash,sessions_closed)
               VALUES (%s,%s,%s,%s,%s,%s)""",
            (reason, principal, device_id, server_id, _digest(session_id) if session_id else None, count))
    return count
