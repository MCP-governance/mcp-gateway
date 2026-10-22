"""POL-08: the employee's own consent to one tool at one data grade, asked out of band in the console.

The harness that made the call cannot answer for the person: an MCP elicitation travels through the
same client the agent drives (and some clients auto-accept it), so the request waits in the console,
where the employee signs in. A consent is bound to the reviewed terms of the tool; when a reviewer
changes the purpose, destinations or inputs, the old consent no longer covers the call.
"""
from __future__ import annotations

import os

from psycopg.types.json import Jsonb

from . import db, pac, registry, review
from .contract import canonical_hash

CONSENT_DAYS = int(os.getenv("CONSENT_DAYS", "90"))
RANK = {"public": 0, "nonimportant": 1, "important": 2}
# decision → (new status, states it may come from, approval_events outcome, reason)
DECISIONS = {"grant": ("GRANTED", ("PENDING", "DENIED", "REVOKED"), "approved", "동의"),
             "deny": ("DENIED", ("PENDING",), "rejected", "동의 거부"),
             "revoke": ("REVOKED", ("GRANTED",), "rejected", "동의 철회")}


def terms_hash(tool_review: dict) -> str:
    return canonical_hash(review.scope_terms(tool_review))


def _rank(grade: str) -> int:
    return RANK.get(grade, RANK["important"])  # an unknown grade is asked as the highest


async def missing(user_token: str, server_id: str, tool: str, data_class: str, tool_review: dict,
                  *, principal: dict | None = None) -> str | None:
    """None when a live consent covers this call. Otherwise the reason, with a request left pending."""
    terms = terms_hash(tool_review)
    rows = await db.fetch_all(
        """SELECT grade, status FROM user_consents
            WHERE user_token=%s AND server_id=%s AND tool_name=%s AND terms_hash=%s
              AND (status <> 'GRANTED' OR expires_at > now())""",
        (user_token, server_id, tool, terms))
    grade = data_class if data_class in RANK else "important"
    if any(r["status"] == "GRANTED" and _rank(r["grade"]) >= _rank(grade) for r in rows):
        return None
    if any(r["status"] == "DENIED" and r["grade"] == grade for r in rows):
        return "사용자가 이 도구의 데이터 이용에 동의하지 않았습니다. 콘솔의 동의 목록에서 바꿀 수 있습니다."
    if principal is None:
        await _request(user_token, server_id, tool, grade, tool_review, db.execute)
    else:
        if principal["token"] != user_token:
            raise ValueError("동의 요청의 사용 주체가 일치하지 않습니다.")
        await request_server(principal, server_id, grade)
    return "이 도구의 데이터 이용에 사용자 동의가 필요합니다. 콘솔의 동의 요청을 확인하세요."


async def _request(user_token: str, server_id: str, tool: str, grade: str, tool_review: dict, execute) -> None:
    # Repeated calls must neither reopen a refusal nor create a lower-grade prompt under a live grant.
    await execute(
        """INSERT INTO user_consents(user_token, server_id, tool_name, grade, terms_hash, purpose, terms)
           SELECT %s,%s,%s,%s,%s,%s,%s
            WHERE NOT EXISTS (SELECT 1 FROM user_consents
                   WHERE user_token=%s AND server_id=%s AND tool_name=%s AND terms_hash=%s
                     AND grade=ANY(%s) AND status='GRANTED' AND expires_at > now())
           ON CONFLICT (user_token, server_id, tool_name, grade, terms_hash) DO UPDATE
              SET status='PENDING', requested_at=now(), decided_at=NULL, expires_at=NULL
            WHERE user_consents.status='REVOKED'
               OR (user_consents.status='GRANTED' AND user_consents.expires_at <= now())""",
        (user_token, server_id, tool, grade, terms_hash(tool_review), str(tool_review.get("purpose") or "")[:200],
         Jsonb(review.scope_terms(tool_review)), user_token, server_id, tool, terms_hash(tool_review),
         [candidate for candidate in RANK if _rank(candidate) >= _rank(grade)]))


async def request_server(principal: dict, server_id: str, data_class: str) -> None:
    """Queue reviewed, permitted tools together; this creates no grant or execution authority."""
    user_token = principal["token"]
    allowed = registry.allowed_principals(server_id)
    if allowed is not None and user_token not in allowed:
        return
    spec = registry.server(server_id) or {}
    reviewed = registry.reviewed_tools(server_id)
    grade = data_class if data_class in RANK else "important"
    async with db.transaction() as connection:
        for tool, action in sorted((spec.get("tools") or {}).items()):
            item = (spec.get("tool_reviews") or {}).get(tool) or {}
            if tool in reviewed and item.get("consent") and pac.visible(principal, server_id, tool, action):
                await _request(user_token, server_id, tool, grade, item, connection.execute)


async def mine(user_token: str) -> list[dict]:
    return await db.fetch_all(
        """SELECT id, server_id, tool_name, grade, purpose, terms, requested_at, decided_at, expires_at,
                  CASE WHEN status='GRANTED' AND expires_at <= now() THEN 'EXPIRED' ELSE status END AS status
             FROM user_consents WHERE user_token=%s
            ORDER BY (status='PENDING') DESC, requested_at DESC, id DESC""", (user_token,))


async def for_dispatch(connection, user_token: str, server_id: str, tool: str,
                       data_class: str, tool_review: dict) -> dict | None:
    """Lock a covering grant until the intent commits; decide()'s UPDATE must wait."""
    return await (await connection.execute(
        """SELECT id FROM user_consents
            WHERE user_token=%s AND server_id=%s AND tool_name=%s AND terms_hash=%s
              AND grade=ANY(%s) AND status='GRANTED' AND expires_at > clock_timestamp()
            ORDER BY id LIMIT 1 FOR SHARE""",
        (user_token, server_id, tool, terms_hash(tool_review),
         [grade for grade in RANK if _rank(grade) >= _rank(data_class)]))).fetchone()


async def decide(consent_id: int, user_token: str, decision: str) -> dict | None:
    """Only the person the consent belongs to decides it; the change and its event commit together."""
    status, from_states, outcome, reason = DECISIONS[decision]
    async with db.transaction() as connection:
        cursor = await connection.execute(
            """UPDATE user_consents SET status=%s, decided_at=now(),
                      expires_at = CASE WHEN %s='GRANTED' THEN now() + make_interval(days => %s) END
                WHERE id=%s AND user_token=%s AND status = ANY(%s)
            RETURNING id, server_id, tool_name, grade, terms_hash, status, expires_at""",
            (status, status, CONSENT_DAYS, consent_id, user_token, list(from_states)))
        row = await cursor.fetchone()
        if row:
            await review.record_event("user-consent", outcome, "consent", row["id"], user_token, reason=reason,
                                      scope={"server": row["server_id"], "tool": row["tool_name"],
                                             "grade": row["grade"], "terms": row["terms_hash"], "status": status},
                                      connection=connection)
    return row


async def decide_server(server_id: str, consent_ids: list[int], user_token: str, decision: str) -> list[dict]:
    """Decide exactly the displayed rows, atomically with one audit event per tool."""
    if not consent_ids or len(set(consent_ids)) != len(consent_ids):
        raise ValueError("동의 요청을 다시 확인하세요.")
    status, from_states, outcome, reason = DECISIONS[decision]
    async with db.transaction() as connection:
        # Stable lock order also serializes overlapping bulk decisions before any audit append.
        locked = await (await connection.execute(
            """SELECT id FROM user_consents
                WHERE server_id=%s AND user_token=%s AND id=ANY(%s) AND status=ANY(%s)
                ORDER BY tool_name, grade, terms_hash, id FOR UPDATE""",
            (server_id, user_token, consent_ids, list(from_states)))).fetchall()
        if len(locked) != len(consent_ids):
            raise ValueError("이미 처리됐거나 본인의 동의 요청이 아닙니다.")
        rows = await (await connection.execute(
            """UPDATE user_consents SET status=%s, decided_at=now(),
                      expires_at = CASE WHEN %s='GRANTED' THEN now() + make_interval(days => %s) END
                WHERE server_id=%s AND user_token=%s AND id=ANY(%s) AND status=ANY(%s)
            RETURNING id, server_id, tool_name, grade, terms_hash, status, expires_at""",
            (status, status, CONSENT_DAYS, server_id, user_token, consent_ids, list(from_states)))).fetchall()
        if len(rows) != len(consent_ids):
            raise ValueError("동의 요청을 다시 확인하세요.")
        for row in sorted(rows, key=lambda item: item["id"]):
            await review.record_event("user-consent", outcome, "consent", row["id"], user_token, reason=reason,
                                      scope={"server": row["server_id"], "tool": row["tool_name"],
                                             "grade": row["grade"], "terms": row["terms_hash"], "status": status},
                                      connection=connection)
    return rows


if __name__ == "__main__":
    base = {"purpose": "사내 문서 변환", "asset": "문서", "action": "r", "destinations": [], "inputs": None,
            "mask": False, "grade": "public", "accepts_from": [], "consent": True}
    assert terms_hash({**base, "reviewed_by": "a", "reviewed_at": "1"}) == terms_hash({**base, "reviewed_by": "b"})
    assert terms_hash(base) != terms_hash({**base, "purpose": "외부 공유"})
    assert _rank("unknown") == RANK["important"] and _rank("public") < _rank("nonimportant")
    # approval_events.outcome has a CHECK; a value outside it rolls the decision back.
    assert {d[2] for d in DECISIONS.values()} <= {"recorded", "approved", "rejected", "refused", "held"}
    print("consent self-check ok")
