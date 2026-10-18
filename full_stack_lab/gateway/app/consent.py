"""POL-08: the employee's own consent to one tool at one data grade, asked out of band in the console.

The harness that made the call cannot answer for the person: an MCP elicitation travels through the
same client the agent drives (and some clients auto-accept it), so the request waits in the console,
where the employee signs in. A consent is bound to the reviewed terms of the tool; when a reviewer
changes the purpose, destinations or inputs, the old consent no longer covers the call.
"""
from __future__ import annotations

import os

from . import db, review
from .contract import canonical_hash

CONSENT_DAYS = int(os.getenv("CONSENT_DAYS", "90"))
RANK = {"public": 0, "nonimportant": 1, "important": 2}
DECISIONS = {"grant": ("GRANTED", ("PENDING", "DENIED", "REVOKED")),
             "deny": ("DENIED", ("PENDING",)),
             "revoke": ("REVOKED", ("GRANTED",))}


def terms_hash(tool_review: dict) -> str:
    return canonical_hash(review.scope_terms(tool_review))


def _rank(grade: str) -> int:
    return RANK.get(grade, RANK["important"])  # an unknown grade is asked as the highest


async def missing(user_token: str, server_id: str, tool: str, data_class: str, tool_review: dict) -> str | None:
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
    await db.execute(
        """INSERT INTO user_consents(user_token, server_id, tool_name, grade, terms_hash, purpose)
           VALUES (%s,%s,%s,%s,%s,%s)
           ON CONFLICT (user_token, server_id, tool_name, grade, terms_hash) DO UPDATE
              SET status='PENDING', requested_at=now(), decided_at=NULL, expires_at=NULL
            WHERE user_consents.status='REVOKED'
               OR (user_consents.status='GRANTED' AND user_consents.expires_at <= now())""",
        (user_token, server_id, tool, grade, terms, str(tool_review.get("purpose") or "")[:200]))
    return "이 도구의 데이터 이용에 사용자 동의가 필요합니다. 콘솔의 동의 요청을 확인하세요."


async def mine(user_token: str) -> list[dict]:
    return await db.fetch_all(
        """SELECT id, server_id, tool_name, grade, purpose, requested_at, decided_at, expires_at,
                  CASE WHEN status='GRANTED' AND expires_at <= now() THEN 'EXPIRED' ELSE status END AS status
             FROM user_consents WHERE user_token=%s
            ORDER BY (status='PENDING') DESC, requested_at DESC LIMIT 200""", (user_token,))


async def decide(consent_id: int, user_token: str, decision: str) -> dict | None:
    """Only the person the consent belongs to decides it; every change is an approval event."""
    status, from_states = DECISIONS[decision]
    row = await db.fetch_one(
        """UPDATE user_consents SET status=%s, decided_at=now(),
                  expires_at = CASE WHEN %s='GRANTED' THEN now() + make_interval(days => %s) END
            WHERE id=%s AND user_token=%s AND status = ANY(%s)
        RETURNING id, server_id, tool_name, grade, terms_hash, status, expires_at""",
        (status, status, CONSENT_DAYS, consent_id, user_token, list(from_states)))
    if row:
        await review.record_event("user-consent", status.lower(), "consent", row["id"], user_token,
                                  scope={"server": row["server_id"], "tool": row["tool_name"],
                                         "grade": row["grade"], "terms": row["terms_hash"]})
    return row


if __name__ == "__main__":
    base = {"purpose": "사내 문서 변환", "asset": "문서", "action": "r", "destinations": [], "inputs": None,
            "mask": False, "grade": "public", "accepts_from": [], "consent": True}
    assert terms_hash({**base, "reviewed_by": "a", "reviewed_at": "1"}) == terms_hash({**base, "reviewed_by": "b"})
    assert terms_hash(base) != terms_hash({**base, "purpose": "외부 공유"})
    assert _rank("unknown") == RANK["important"] and _rank("public") < _rank("nonimportant")
    print("consent self-check ok")
