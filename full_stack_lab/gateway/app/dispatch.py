"""The durable record of a tools/call that is about to leave, and what happens to the unanswered ones.

The audit ledger learns of a call only when its decision is recorded, after the answer.
A process that dies between the send and the answer leaves no trace there, and once the
reservation expired the identical write was sent again. This row is written in the same
database immediately before the send, so "we may have sent it" survives the process.
It is never retried by the gateway. An administrator who has checked the downstream
system closes it; until then an identical write is refused (P-RATE-003).
"""
from __future__ import annotations

import os
from psycopg.types.json import Jsonb

from . import db, high_impact
from .contract import canonical_hash

# Sent and not answered: recorded as such (timeout, lost response), or still marked
# pending after its reservation is gone, which means the process that sent it is gone.
UNSETTLED = """(i.state = 'uncertain' OR (i.state = 'pending' AND NOT EXISTS (
        SELECT 1 FROM call_reservations r
         WHERE r.request_id = i.request_id AND r.released_at IS NULL AND r.expires_at > now())))"""

OUTCOMES = {"executed": "confirmed_executed", "not_executed": "confirmed_not_executed"}
IDEMPOTENCY_TTL_SECONDS = int(os.getenv("IDEMPOTENCY_TTL_SECONDS", "86400"))
if IDEMPOTENCY_TTL_SECONDS <= 0:
    raise ValueError("IDEMPOTENCY_TTL_SECONDS must be positive")

# Unanswered sends never expire; only definite outcomes have a replay window.
REPLAY = """i.action IN ('w','x') AND (i.state IN ('pending','uncertain') OR
    (i.state IN ('resolved','confirmed_executed') AND
     i.resolved_at > now() - make_interval(secs => %s)))"""


class _Refused(Exception):
    pass


CATALOG_OK = """EXISTS (
                SELECT 1 FROM mcp_tools t
                JOIN LATERAL (SELECT exact_match,restricted_tools FROM catalog_snapshots
                              WHERE server_id=s.id ORDER BY id DESC LIMIT 1) c ON true
                WHERE t.server_id=s.id AND t.name=r.tool_name AND t.enabled
                  AND t.approved_schema_hash=t.observed_schema_hash
                  AND t.approved_description_hash=t.observed_description_hash
                  AND (c.exact_match OR (c.restricted_tools IS NOT NULL AND NOT t.name=ANY(c.restricted_tools))))"""

_INSERT = f"""INSERT INTO dispatch_intents(request_id, user_token, server_id, tool_name, action, fingerprint)
           SELECT r.request_id, r.user_token, r.server_id, r.tool_name, %s, r.fingerprint
             FROM call_reservations r
             JOIN principals p ON p.token = r.user_token AND p.status = 'active'
             JOIN mcp_servers s ON s.id = r.server_id AND COALESCE(s.lifecycle, 'OPERATING') = 'OPERATING'
            WHERE r.request_id = %s AND r.released_at IS NULL AND r.expires_at > clock_timestamp()
              AND s.status <> 'DISABLED'
              AND NOT EXISTS (SELECT 1 FROM ops_suspensions x WHERE x.server_id=s.id AND x.resumed_at IS NULL)
              AND NOT EXISTS (SELECT 1 FROM disposal_blocks x WHERE x.server_id=s.id AND x.kind IN ('server','credential'))
              AND {CATALOG_OK}
              FOR SHARE OF s"""


async def record(request_id: str, action: str, approval_id: str | None = None) -> str | None:
    """Write the intent, or say why the call may no longer be sent.

    One statement checks the reservation, the principal and the server and writes the row.
    The server row is locked in share mode: a termination takes the same row before it
    stamps its cutover, so every dispatch is either recorded before the cutover or refused
    after it, never in between. An approved call also consumes its approval here, in the same
    transaction: the approval is single-use at the one place that sends, not only where it was claimed.
    """
    try:
        async with db.transaction() as connection:
            row = await (await connection.execute(
                "SELECT user_token, fingerprint FROM call_reservations WHERE request_id=%s", (request_id,))).fetchone()
            if not row:
                raise _Refused
            # Same lock as reservation: even a stale policy context cannot dispatch two writes.
            await connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (row["user_token"],))
            if action in {"w", "x"} and await (await connection.execute(
                    f"""SELECT 1 FROM dispatch_intents i WHERE i.user_token=%s AND i.fingerprint=%s
                         AND i.request_id<>%s AND {REPLAY} LIMIT 1""",
                    (row["user_token"], row["fingerprint"], request_id, IDEMPOTENCY_TTL_SECONDS))).fetchone():
                raise _Refused("duplicate")
            # Last, after the per-principal wait: a share lock held across that wait starves a termination.
            # Acquire before the INSERT so a snapshot published while waiting is visible
            # to the next statement under READ COMMITTED, not the pre-lock snapshot.
            tool = await (await connection.execute(
                """SELECT s.id, t.scope_review FROM mcp_servers s JOIN call_reservations r ON r.server_id=s.id
                   JOIN mcp_tools t ON t.server_id=s.id AND t.name=r.tool_name
                   WHERE r.request_id=%s FOR SHARE OF s, t""", (request_id,))).fetchone()
            impact = (tool or {}).get("scope_review") or {}
            approval = await (await connection.execute(
                "SELECT * FROM approvals WHERE id=%s FOR UPDATE", (approval_id,))).fetchone() if approval_id else None
            approved = (approval or {}).get("request_payload") or {}
            if impact.get("high_impact") or approved.get("impact_scope_sha256"):
                if not high_impact.bound(approval, approved, impact, canonical_hash):
                    raise _Refused("impact")
                if not await (await connection.execute(
                    """SELECT id FROM approval_events WHERE target_kind='approval' AND target_id=%s
                       AND kind='call-approve' AND outcome='approved' AND actor=%s
                       AND scope->'explanation'=%s AND scope->>'request_fingerprint'=%s LIMIT 1""",
                    (str(approval_id), approval["reviewed_by"], Jsonb(approval["explanation"]), approval["request_fingerprint"]))).fetchone():
                    raise _Refused("impact")
            if not (await connection.execute(_INSERT, (action, request_id))).rowcount:
                raise _Refused
            if approval_id:
                # What is sent must be what was approved: the approval row holds the approved request,
                # the intent the fingerprint and principal of this one. The digest the policy checks
                # binds high-risk calls only; this binds every approved call.
                row = await (await connection.execute(
                    """SELECT a.request_payload, i.fingerprint, i.user_token FROM approvals a, dispatch_intents i
                        WHERE a.id = %s AND i.request_id = %s""", (approval_id, request_id))).fetchone()
                approved = (row or {}).get("request_payload") or {}
                if not row or row["user_token"] != approved.get("user_token") or row["fingerprint"] != canonical_hash(
                        {"server": approved.get("server_id"), "tool": approved.get("tool"), "arguments": approved.get("arguments")}):
                    raise _Refused("approval")
                if not (await connection.execute(
                        "UPDATE approvals SET status = 'UNCONFIRMED' WHERE id = %s AND status = 'APPROVED' AND revoked_at IS NULL AND expires_at > clock_timestamp()",
                        (approval_id,))).rowcount:
                    raise _Refused("approval")
        return None
    except _Refused as refusal:
        # A replayed write to a server that is also closing reports the closure: that is what an operator acts on.
        if refusal.args and refusal.args[0] != "duplicate":
            return refusal.args[0]
        duplicate = bool(refusal.args)
    why = await db.fetch_one(
        f"""SELECT (SELECT p.status FROM principals p WHERE p.token = r.user_token) AS principal,
                  (SELECT COALESCE(s.lifecycle, 'OPERATING') FROM mcp_servers s WHERE s.id = r.server_id) AS lifecycle,
                  s.status AS server_status, {CATALOG_OK} AS catalog_ok
             FROM call_reservations r JOIN mcp_servers s ON s.id=r.server_id
             WHERE r.request_id = %s AND r.released_at IS NULL AND r.expires_at > now()""",
        (request_id,))
    if not why:
        return "duplicate" if duplicate else "reservation"
    if why["principal"] != "active":
        return "principal"
    if why["lifecycle"] != "OPERATING":
        return "terminated"
    if why["server_status"] == "DISABLED":
        return "suspended"
    if not why["catalog_ok"]:
        return "contract"
    return "duplicate" if duplicate else "reservation"


async def uncertain(limit: int = 200) -> list[dict]:
    rows = await db.fetch_all(
        f"""SELECT i.request_id, i.user_token, p.display_name, i.server_id, i.tool_name, i.action,
                   i.attempted_at, i.decision_id
              FROM dispatch_intents i LEFT JOIN principals p ON p.token = i.user_token
             WHERE {UNSETTLED} ORDER BY i.attempted_at DESC LIMIT %s""", (limit,))
    return [{**row, "request_id": str(row["request_id"]), "attempted_at": row["attempted_at"].isoformat()}
            for row in rows]


async def uncertain_count(server_id: str | None = None, user_token: str | None = None, unledgered: bool = False) -> int:
    row = await db.fetch_one(
        f"""SELECT count(*) AS n FROM dispatch_intents i
             WHERE {UNSETTLED} AND (%s::text IS NULL OR i.server_id = %s) AND (%s::text IS NULL OR i.user_token = %s)
               AND (NOT %s OR i.decision_id IS NULL)""",
        (server_id, server_id, user_token, user_token, unledgered))
    return int(row["n"])


async def resolve(request_id: str, outcome: str, actor: str, note: str) -> dict:
    """An administrator checked the downstream system and says whether the call took effect."""
    if outcome not in OUTCOMES:
        raise ValueError("확인 결과는 실행됨 또는 실행 안 됨이어야 합니다.")
    row = await db.fetch_one(
        f"""WITH closed AS (
              UPDATE dispatch_intents i SET state = %s, resolved_at = now(), resolved_by = %s, note = %s
               WHERE i.request_id = %s AND {UNSETTLED}
               RETURNING i.request_id, i.server_id, i.tool_name, i.state, i.resolved_at),
            freed AS (
              UPDATE call_reservations SET released_at = now()
               WHERE request_id IN (SELECT request_id FROM closed) AND released_at IS NULL)
            SELECT * FROM closed""", (OUTCOMES[outcome], actor, note.strip() or None, request_id))
    if not row:
        raise ValueError("이미 확인했거나 실행 확인이 필요한 호출이 아닙니다.")
    return {**row, "request_id": str(row["request_id"]), "resolved_at": row["resolved_at"].isoformat()}
