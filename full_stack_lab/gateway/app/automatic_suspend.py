"""DEV-74 automation on the employee/server suspension state established by D-181."""
from __future__ import annotations

from . import db, review

TARGET = "user-server-suspension"


async def _expire_locked(connection, user_token: str, server_id: str) -> bool:
    row = await (await connection.execute(
        """UPDATE user_server_suspensions SET resumed_at=expires_at, resumed_by='automatic',
                  resume_note='자동 중지 기간 만료'
             WHERE user_token=%s AND server_id=%s AND resumed_at IS NULL
               AND expires_at IS NOT NULL AND expires_at <= clock_timestamp()
             RETURNING id, expires_at""", (user_token, server_id))).fetchone()
    if not row:
        return False
    await review.record_event(
        "user-server-resume", "approved", TARGET, row["id"], "automatic",
        reason="자동 중지 기간 만료",
        scope={"user": user_token, "server": server_id, "expired_at": row["expires_at"].isoformat()},
        connection=connection)
    return True


async def expire(user_token: str | None = None, server_id: str | None = None) -> None:
    """Close an elapsed automatic stop under the same employee lock used by dispatch."""
    if user_token is None or server_id is None:
        rows = await db.fetch_all(
            """SELECT DISTINCT user_token, server_id FROM user_server_suspensions
                 WHERE resumed_at IS NULL AND expires_at <= clock_timestamp() ORDER BY user_token, server_id""")
        for row in rows:
            await expire(row["user_token"], row["server_id"])
        return
    async with db.transaction() as connection:
        await connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (user_token,))
        await _expire_locked(connection, user_token, server_id)


async def suspend(connection, user_token: str, server_id: str, policies: tuple[str, ...],
                  threshold: int, window_seconds: int, duration_seconds: int) -> bool:
    """Add one D-181 state row and ledger event when this pair reaches its configured threshold."""
    if threshold < 1 or window_seconds < 1 or duration_seconds < 1:
        raise ValueError("자동 중지 임계·관측 창·중지 기간은 양수여야 합니다.")
    await _expire_locked(connection, user_token, server_id)
    count = await (await connection.execute(
        """SELECT count(*) AS n FROM decisions
             WHERE user_token=%s AND server_id=%s AND decision='Block'
               AND policy_id=ANY(%s::text[])
               AND created_at > clock_timestamp() - make_interval(secs => %s)""",
        (user_token, server_id, list(policies), window_seconds))).fetchone()
    violations = int(count["n"])
    if violations < threshold:
        return False
    row = await (await connection.execute(
        """INSERT INTO user_server_suspensions(user_token, server_id, reason, suspended_by, expires_at)
             VALUES (%s,%s,'반복 위반 자동 중지','automatic',clock_timestamp()+make_interval(secs => %s))
             ON CONFLICT (user_token, server_id) WHERE resumed_at IS NULL DO NOTHING
             RETURNING id, suspended_at, expires_at""",
        (user_token, server_id, duration_seconds))).fetchone()
    if not row:
        return False
    flight = await (await connection.execute(
        """SELECT count(*) FILTER (WHERE i.request_id IS NULL) AS unsent,
                  count(*) FILTER (WHERE i.state='pending') AS sent
             FROM call_reservations r LEFT JOIN dispatch_intents i USING (request_id)
            WHERE r.user_token=%s AND r.server_id=%s AND r.released_at IS NULL AND r.expires_at > clock_timestamp()""",
        (user_token, server_id))).fetchone()
    expires_at = row["expires_at"]
    await review.record_event(
        "user-server-suspend", "held", TARGET, row["id"], "automatic",
        reason="반복 위반 자동 중지",
        scope={"user": user_token, "server": server_id, "threshold": threshold,
               "violations": violations, "window_seconds": window_seconds,
               "expires_at": expires_at.isoformat(), "policy_ids": list(policies),
               "unsent": int(flight["unsent"]), "sent": int(flight["sent"])},
        connection=connection)
    return True
