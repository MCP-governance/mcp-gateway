"""Risk tier of an intake request from what the applicant stated (DEV-71).

Pure and deterministic: the same input always yields the same tier. The table is a policy
choice, not a value any law prescribes, and it replaces no impact assessment: a person performs
and signs the assessment, this module only reads a table and says how many people must approve.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any

VERSION = 1
FIELDS = ("data_class", "personal_data", "external_transfer", "permission", "users", "autonomy")
LABELS = {"data_class": "데이터 등급", "personal_data": "처리 개인정보", "external_transfer": "외부 전송",
          "permission": "실행 권한", "users": "예상 사용자 수", "autonomy": "자율성"}
CHOICES = {
    "data_class": {"public": "공개", "nonimportant": "내부", "important": "중요"},
    "personal_data": {"none": "없음", "general": "일반 개인정보", "unique_id": "고유식별정보", "sensitive": "민감정보"},
    "permission": {"r": "읽기", "w": "쓰기", "x": "실행"},
    "autonomy": {"approve_each": "건별 확인", "supervised": "감독 하 실행", "autonomous": "자율 실행"},
}
POINTS = {
    "data_class": {"public": 0, "nonimportant": 1, "important": 3},
    "personal_data": {"none": 0, "general": 1, "unique_id": 3, "sensitive": 4},
    "permission": {"r": 0, "w": 2, "x": 3},
    "autonomy": {"approve_each": 0, "supervised": 1, "autonomous": 2},
}
EXTERNAL_POINTS = 2
USER_BANDS = ((10, 0), (100, 1), (1000, 2))  # users at or under the limit; more than 1000 scores 3
OVER_BANDS_POINTS = 3
MAX_USERS = 10_000_000

TIERS = ("low", "medium", "high", "very_high")
TIER_LABELS = {"low": "낮음", "medium": "보통", "high": "높음", "very_high": "매우 높음"}
SCORE_LIMITS = ((3, "low"), (7, "medium"), (11, "high"))  # a score above the last limit is very_high
# A combination that is serious whatever the sum says lifts the tier to at least this one.
FLOORS = (
    ("민감정보 외부 전송", lambda i: i["personal_data"] == "sensitive" and i["external_transfer"], "very_high"),
    ("중요 데이터 외부 전송", lambda i: i["data_class"] == "important" and i["external_transfer"], "high"),
    ("자율 실행 권한", lambda i: i["permission"] == "x" and i["autonomy"] == "autonomous", "high"),
)

# D-189. High and very high need two different administrators; a written reason never substitutes for one.
# Very high also needs the written reason ("required"). Critical finding acceptance is separate (review.accept_risk).
APPROVAL = {
    "low": {"approvers": 1, "reason": "none"},
    "medium": {"approvers": 1, "reason": "none"},
    "high": {"approvers": 2, "reason": "none"},
    "very_high": {"approvers": 2, "reason": "required"},
}
MIN_REASON = 10  # the length approval already asks of a written risk acceptance

ASSUMED_TIER = "very_high"  # an existing approval with no stated input
GRACE_DAYS = 30


def digest(value: dict[str, Any]) -> str:
    raw = json.dumps({key: value.get(key) for key in FIELDS}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _invalid(key: str, value: Any) -> bool:
    if key == "external_transfer":
        return not isinstance(value, bool)
    if key == "users":
        return isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_USERS
    return not isinstance(value, str) or value not in CHOICES[key]


def _user_points(users: int) -> int:
    return next((points for limit, points in USER_BANDS if users <= limit), OVER_BANDS_POINTS)


def assess(raw: Any) -> dict[str, Any]:
    """Tier of a stated input, or a hold naming what is missing or wrong. No tier is ever guessed."""
    stated = raw if isinstance(raw, dict) else {}
    missing = [key for key in FIELDS if stated.get(key) is None]
    wrong = [key for key in FIELDS if key not in missing and _invalid(key, stated[key])]
    wrong += [str(key) for key in stated if key not in FIELDS]
    if missing or wrong:
        messages = []
        if missing:
            messages.append("위험 등급 입력 누락: " + ", ".join(LABELS[key] for key in missing))
        if wrong:
            messages.append("위험 등급 입력 값 오류: " + ", ".join(LABELS.get(key, key) for key in wrong))
        return {"status": "hold", "tier": None, "score": None, "missing": missing, "invalid": wrong, "messages": messages}
    score = (sum(POINTS[key][stated[key]] for key in POINTS) + (EXTERNAL_POINTS if stated["external_transfer"] else 0)
             + _user_points(stated["users"]))
    tier = next((name for limit, name in SCORE_LIMITS if score <= limit), "very_high")
    floors = []
    for name, applies, floor in FLOORS:
        if applies(stated):
            floors.append(name)
            tier = max(tier, floor, key=TIERS.index)
    return {"status": "ok", "tier": tier, "score": score, "floors": floors, "missing": [], "invalid": [], "messages": [],
            "input_sha256": digest(stated), "version": VERSION}


def decide(tier: str, approvers: int, reason: str | None) -> tuple[str, str]:
    """What the next approval click means: finish it ("approve"), record it as the first of two
    ("cosign") or refuse it for a missing written reason ("refuse"). `approvers` counts the person
    clicking plus the different people who already recorded theirs for this same input."""
    rule, written = APPROVAL[tier], len((reason or "").strip()) >= MIN_REASON
    label = TIER_LABELS[tier]
    if rule["reason"] == "required" and not written:
        return "refuse", f"{label} 등급은 위험 수용 사유({MIN_REASON}자 이상)가 필요합니다."
    if approvers >= rule["approvers"]:
        return "approve", ""
    return "cosign", f"{label} 등급은 서로 다른 관리자 {rule['approvers']}명의 승인이 필요합니다. 현재 {approvers}명."


def grace_end(started_at: str | datetime) -> datetime:
    started = datetime.fromisoformat(started_at) if isinstance(started_at, str) else started_at
    return started + timedelta(days=GRACE_DAYS)


def legacy_review(spec: dict[str, Any], started_at: str | None, now: datetime | None = None) -> dict[str, Any] | None:
    """An approval that predates risk input counts as the highest tier until it is re-approved with
    input. It stays valid for the grace period, then waits for re-approval. None when not applicable."""
    if spec.get("risk_assessment") or not spec.get("intake_id") or not started_at:
        return None
    now = now or datetime.now(timezone.utc)
    end = grace_end(started_at)
    left = math.ceil((end - now).total_seconds() / 86400)
    return {"tier": ASSUMED_TIER, "state": "grace" if now < end else "expired",
            "until": end.isoformat(timespec="seconds"), "days_left": max(left, 0)}


def cap_until(proposed: datetime, spec: dict[str, Any], started_at: str | None) -> datetime:
    """An approval without input is never extended past the end of its grace period."""
    if spec.get("risk_assessment") or not spec.get("intake_id") or not started_at:
        return proposed
    return min(proposed, grace_end(started_at))


def package(stated: Any, intake: dict[str, Any]) -> list[dict[str, str]]:
    """The stated input laid out against the items an impact assessment asks for, as a draft a person
    copies into the form of the jurisdiction concerned."""
    stated = stated if isinstance(stated, dict) else {}
    assessed = assess(stated)

    def show(key: str) -> str:
        value = stated.get(key)
        if value is None:
            return "—"
        if key == "external_transfer":
            return "있음" if value else "없음"
        return f"{value}명" if key == "users" else CHOICES[key].get(value, "—")

    rule = APPROVAL.get(assessed["tier"]) if assessed["tier"] else None
    if not rule:
        way = "—"
    elif rule["approvers"] == 1:
        way = "관리자 1명"
    else:
        way = f"관리자 {rule['approvers']}명" + (" 및 위험 수용 사유" if rule["reason"] == "required" else "")
    return [
        {"item": "처리 대상", "value": intake.get("display_name") or "—", "form": "처리 시스템"},
        {"item": "처리 목적", "value": intake.get("purpose") or "—", "form": "처리의 목적·성격"},
        {"item": LABELS["data_class"], "value": show("data_class"), "form": "처리 정보의 민감도"},
        {"item": LABELS["personal_data"], "value": show("personal_data"), "form": "개인정보 항목"},
        {"item": LABELS["external_transfer"], "value": show("external_transfer"), "form": "제3자 제공·국외 이전"},
        {"item": LABELS["users"], "value": show("users"), "form": "영향받는 정보주체 범위"},
        {"item": LABELS["permission"], "value": show("permission"), "form": "시스템이 수행하는 작업"},
        {"item": LABELS["autonomy"], "value": show("autonomy"), "form": "자동화 결정·사람 개입"},
        {"item": "위험 등급", "value": TIER_LABELS[assessed["tier"]] if assessed["tier"] else "—", "form": "위험 수준"},
        {"item": "승인 방식", "value": way, "form": "위험 처리 결정권자"},
    ]
