"""Ledger retention: jurisdiction floors and the sealed prefix of the audit chain (D-141).

A seal lives in the signed disposal journal (D-123), outside PostgreSQL, so a DB backup
restore cannot roll it back. It says "decisions up to last_id are disposed and the chain
continued from last_sha256". verify_audit_chain starts from that hash and treats any row
at or below last_id as resurrected. Nothing here deletes a decision row: the purge step is
held for the owner's decision on README principle 5 (docs/ai/LEDGER_RETENTION.md).
"""
import json
import re
from datetime import datetime, timedelta

from . import disposal

# Month/year floors are rounded up to the longest calendar span (6 months = 184 days,
# 1 year = 366, 3 years = 1096), so a day count never falls short of the clause.
# Sources: research/llm-wiki/analysis/compliance/dev-plan/README.md 7장 (binding duties only).
FLOORS = {
    "EU": (184, "LIB-M01 Art. 19(1)·26(6)"),
    "CN": (184, "LIB-M10 제23조제3호"),
    "US-FED": (366, "LIB-M18 부록 B 1"),
    "IN": (366, "LIB-M44 규칙 8(3)"),
    "KR-CREDIT": (1096, "LIB-L02 제20조제2항"),
    "US-CO": (1096, "LIB-M15 6-1-1702(4)·6-1-1703"),
}
# RQ-01: 12 months covers EU, CN, US-FED and IN; it is also the floor when no pack is chosen.
DEFAULT_DAYS = 366
HEX = re.compile(r"[0-9a-f]{64}")


def floor(jurisdictions) -> int:
    unknown = sorted(set(jurisdictions) - FLOORS.keys())
    if unknown:
        raise ValueError("알 수 없는 관할입니다: " + ", ".join(unknown))
    # Two packs apply together: the longer floor wins.
    return max((FLOORS[j][0] for j in jurisdictions), default=DEFAULT_DAYS)


def check(days, jurisdictions) -> int:
    required = floor(jurisdictions)
    if not isinstance(days, int) or isinstance(days, bool) or days < required:
        raise ValueError(f"보존 기간은 관할 하한 {required}일 이상이어야 합니다.")
    return required


def validate_seal(detail: dict, at: str) -> dict:
    """A seal must name a two-person, retention-expired prefix; anything else is corruption."""
    try:
        last_id, digest = detail["last_id"], detail["last_sha256"]
        ok = (isinstance(last_id, int) and last_id >= 1 and isinstance(digest, str) and HEX.fullmatch(digest)
              and all(isinstance(detail.get(k), str) and detail[k] for k in ("reason", "requested_by", "approved_by"))
              and detail["requested_by"] != detail["approved_by"])
        check(detail["retention_days"], detail["jurisdictions"])
        expired = (datetime.fromisoformat(detail["last_created_at"]) + timedelta(days=detail["retention_days"])
                   <= datetime.fromisoformat(at))
    except (KeyError, TypeError, ValueError) as exc:
        raise disposal.IntegrityError("원장 봉인 기록 손상") from exc
    if not ok:
        raise disposal.IntegrityError("원장 봉인 기록 손상")
    if not expired:
        raise disposal.IntegrityError("보존 기간 안의 구간을 봉인한 기록")
    return detail


def seal_of(records) -> dict | None:
    """Seals are cumulative, so the newest one is the chain's starting point."""
    seal = None
    for record in records:
        if record["kind"] != "ledger":
            continue
        detail = validate_seal(record["detail"], record["at"])
        if seal and detail["last_id"] <= seal["last_id"]:
            raise disposal.IntegrityError("원장 봉인 순서 손상")
        seal = detail
    return seal


def current_seal(directory=None) -> dict | None:
    # An unreadable journal gives no seal: a purged prefix then breaks the chain at its
    # first row (fail closed), and disposal.watch already alarms on the journal itself.
    directory = directory or disposal.DIRECTORY
    try:
        with disposal.locked(directory):
            return seal_of(disposal.read(directory))
    except (disposal.IntegrityError, OSError):
        return None


async def setting() -> dict:
    from . import db
    row = await db.fetch_one("SELECT value, updated_by, updated_at FROM gateway_settings WHERE key='ledger_retention'")
    value = json.loads(row["value"]) if row else {"days": DEFAULT_DAYS, "jurisdictions": []}
    return {**value, "floor_days": floor(value["jurisdictions"]),
            "floors": {code: {"days": days, "source": source} for code, (days, source) in FLOORS.items()},
            "updated_by": row["updated_by"] if row else None, "updated_at": row["updated_at"] if row else None}


async def set_setting(days: int, jurisdictions: list[str], actor: str) -> dict:
    from . import db, review
    jurisdictions = sorted(set(jurisdictions))
    required = check(days, jurisdictions)
    value = {"days": days, "jurisdictions": jurisdictions}
    async with db.transaction() as connection:
        await connection.execute(
            """INSERT INTO gateway_settings(key, value, updated_by) VALUES ('ledger_retention',%s,%s)
               ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_by=EXCLUDED.updated_by, updated_at=now()""",
            (json.dumps(value), actor))
        await review.record_event("ledger-retention", "recorded", "audit", "decisions", actor,
                                  scope={**value, "floor_days": required}, connection=connection)
    return {**value, "floor_days": required, "updated_by": actor}
