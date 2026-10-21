"""An administrator stops one employee's use of one MCP server and later lets it resume (DEV-79).

The console account, the employee's other servers and everyone else's use of this server are
untouched, so this is neither the account status nor the server-wide stop of ops_response.
Calls are refused in execute_call (the principal row carries the flag) and again in the final
dispatch transaction; the rows here are only the state, the record of who did what is the
append-only approval_events entry written in the same transaction.
"""
from __future__ import annotations

import uuid

from . import db, review

TARGET = "user-server-suspension"


async def suspend(user_token: str, server_id: str, actor: str, reason: str, batch: str | None = None) -> dict:
    async with db.transaction() as connection:
        # The lock dispatch.record() takes before its final intent INSERT: a call already past it is on its
        # way and is recorded below, every later one sees this row.
        await connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (user_token,))
        if not await (await connection.execute(
                "SELECT 1 FROM principals WHERE token=%s AND status <> 'deleted'", (user_token,))).fetchone():
            raise LookupError("관리대장에 없는 사용자입니다.")
        if not await (await connection.execute("SELECT 1 FROM mcp_servers WHERE id=%s", (server_id,))).fetchone():
            raise LookupError("등록되지 않은 서버입니다.")
        row = await (await connection.execute(
            """INSERT INTO user_server_suspensions(user_token, server_id, reason, suspended_by)
               VALUES (%s,%s,%s,%s) ON CONFLICT (user_token, server_id) WHERE resumed_at IS NULL DO NOTHING
               RETURNING id, suspended_at""", (user_token, server_id, reason, actor))).fetchone()
        if not row:
            raise ValueError("이미 중지된 이용입니다.")
        # A call that was reserved but not yet sent is refused at dispatch. One already sent cannot be taken
        # back by the gateway, so the record says how many there were.
        flight = await (await connection.execute(
            """SELECT count(*) FILTER (WHERE i.request_id IS NULL) AS unsent,
                      count(*) FILTER (WHERE i.state = 'pending') AS sent
                 FROM call_reservations r LEFT JOIN dispatch_intents i USING (request_id)
                WHERE r.user_token=%s AND r.server_id=%s AND r.released_at IS NULL AND r.expires_at > now()""",
            (user_token, server_id))).fetchone()
        scope = {"user": user_token, "server": server_id, "unsent": int(flight["unsent"]), "sent": int(flight["sent"])}
        if batch:
            scope["batch"] = batch
        await review.record_event(
            "user-server-suspend", "held", TARGET, row["id"], actor, reason=reason, scope=scope, connection=connection)
    return {"id": row["id"], "user_token": user_token, "server_id": server_id, "suspended_at": row["suspended_at"],
            "unsent": int(flight["unsent"]), "sent": int(flight["sent"])}


async def resume(suspension_id: int, actor: str, note: str, batch: str | None = None) -> dict:
    async with db.transaction() as connection:
        row = await (await connection.execute(
            """UPDATE user_server_suspensions SET resumed_at=now(), resumed_by=%s, resume_note=%s
                WHERE id=%s AND resumed_at IS NULL RETURNING id, user_token, server_id""",
            (actor, note, suspension_id))).fetchone()
        if not row:
            raise ValueError("중지 상태가 아닙니다.")
        scope = {"user": row["user_token"], "server": row["server_id"]}
        if batch:
            scope["batch"] = batch
        await review.record_event(
            "user-server-resume", "approved", TARGET, row["id"], actor, reason=note, scope=scope, connection=connection)
    return row


async def operating_servers() -> list[str]:
    # The same set endpoint_plane and pc_kit treat as in service.
    rows = await db.fetch_all("SELECT id FROM mcp_servers WHERE status IN ('READY','DRIFT') AND lifecycle='OPERATING' ORDER BY id")
    return [row["id"] for row in rows]


async def suspend_all(user_token: str, actor: str, reason: str) -> dict:
    """Stop one employee's use of every operating server: suspend() once per server, each in its own transaction.

    A failure on one server does not undo the others. The result lists what was stopped (with its own row and
    record), what was already stopped, and what failed, so nothing is reported as a total.
    """
    if not await db.fetch_one("SELECT 1 FROM principals WHERE token=%s AND status <> 'deleted'", (user_token,)):
        raise LookupError("관리대장에 없는 사용자입니다.")
    batch = uuid.uuid4().hex
    result = {"batch": batch, "user_token": user_token, "suspended": [], "skipped": [], "failed": []}
    for server_id in await operating_servers():
        try:
            result["suspended"].append(await suspend(user_token, server_id, actor, reason, batch=batch))
        except ValueError as exc:
            result["skipped"].append({"server_id": server_id, "reason": str(exc)})
        except Exception as exc:  # per server, and reported; never counted as stopped
            result["failed"].append({"server_id": server_id, "error": type(exc).__name__})
    return result


async def resume_all(user_token: str, actor: str, note: str) -> dict:
    """Resume every active stop of one employee, one resume() per row, reported the same way as suspend_all."""
    batch = uuid.uuid4().hex
    result = {"batch": batch, "user_token": user_token, "resumed": [], "skipped": [], "failed": []}
    for row in await db.fetch_all(
            "SELECT id, server_id FROM user_server_suspensions WHERE user_token=%s AND resumed_at IS NULL ORDER BY id",
            (user_token,)):
        try:
            result["resumed"].append(await resume(row["id"], actor, note, batch=batch))
        except ValueError as exc:
            result["skipped"].append({"id": row["id"], "server_id": row["server_id"], "reason": str(exc)})
        except Exception as exc:
            result["failed"].append({"id": row["id"], "server_id": row["server_id"], "error": type(exc).__name__})
    return result


async def listing() -> list[dict]:
    return await db.fetch_all(
        """SELECT s.id, s.user_token, p.display_name, s.server_id, m.display_name AS server_name, s.reason,
                  s.suspended_at, a.display_name AS suspended_by, s.resumed_at, r.display_name AS resumed_by, s.resume_note
             FROM user_server_suspensions s
             LEFT JOIN principals p ON p.token = s.user_token
             LEFT JOIN mcp_servers m ON m.id = s.server_id
             LEFT JOIN principals a ON a.token = s.suspended_by
             LEFT JOIN principals r ON r.token = s.resumed_by
            ORDER BY (s.resumed_at IS NULL) DESC, s.id DESC LIMIT 200""")
