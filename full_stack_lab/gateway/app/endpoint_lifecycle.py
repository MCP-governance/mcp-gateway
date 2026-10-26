"""Endpoint revocation: stop jobs, revoke the row, then drop tokens, pooled credentials and sessions."""
from __future__ import annotations

from psycopg.types.json import Jsonb

from . import db, idp, local_jobs, mcp_sessions, upstream


async def revoke_device(endpoint_id: str, actor: str) -> dict:
    await local_jobs.quiesce(device_id=endpoint_id)
    # A failed journal append must not leave an unrecorded committed transition.
    async with db.transaction() as connection:
        row = await (await connection.execute(
            "UPDATE endpoint_agents SET status='revoked', issued_by=%s WHERE endpoint_id=%s RETURNING owner_token",
            (actor, endpoint_id))).fetchone()
        if not row:
            raise ValueError("등록되지 않은 엔드포인트입니다.")
        if row["owner_token"]:
            await connection.execute(
                "INSERT INTO endpoint_managed_events(endpoint_id,owner_token,kind,detail) VALUES (%s,%s,'revoked',%s)",
                (endpoint_id, row["owner_token"], Jsonb({"actor": actor})))
    await idp.revoke_device_tokens(endpoint_id)
    if row["owner_token"]:
        await upstream.release_pool(None, row["owner_token"], "device-revoked")
    await mcp_sessions.terminate(reason="device-revoked", device_id=endpoint_id)
    return {"endpoint_id": endpoint_id, "status": "revoked"}
