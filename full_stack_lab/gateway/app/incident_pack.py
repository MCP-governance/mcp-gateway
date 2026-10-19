"""Incident scope snapshots and jurisdiction deadline calculations."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

REGISTRY_DIR = Path(os.getenv("REGISTRY_DIR", "/registry"))
PACK_PATH = REGISTRY_DIR / "incident_jurisdictions.json"
if not PACK_PATH.is_file():
    PACK_PATH = REGISTRY_DIR / "field" / "incident_jurisdictions.json"
if not PACK_PATH.is_file():
    PACK_PATH = Path(__file__).resolve().parents[2] / "registry" / "field" / "incident_jurisdictions.json"


def packs(document: dict | None = None) -> dict[str, dict]:
    document = document or json.loads(PACK_PATH.read_text(encoding="utf-8"))
    if document.get("schema") != "mint-incident-jurisdictions/v1":
        raise ValueError("관할 팩 형식을 확인할 수 없습니다.")
    result = {pack["id"]: pack for pack in document.get("packs", [])}
    if len(result) != len(document.get("packs", [])):
        raise ValueError("관할 팩 식별자가 중복됩니다.")
    return result


def parse_time(value: str | datetime) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        raise ValueError("시각에는 시간대가 필요합니다.")
    return parsed.astimezone(timezone.utc)


def deadlines(detected_at: str | datetime, jurisdiction_ids: list[str], now: str | datetime,
              document: dict | None = None, assessed_at: str | datetime | None = None,
              fix_available_at: str | datetime | None = None) -> list[dict]:
    available = packs(document)
    detected, current = parse_time(detected_at), parse_time(now)
    assessed = parse_time(assessed_at) if assessed_at else None
    fix_available = parse_time(fix_available_at) if fix_available_at else None
    rows = []
    for jurisdiction in jurisdiction_ids:
        pack = available.get(jurisdiction)
        if not pack:
            raise ValueError(f"알 수 없는 관할 팩: {jurisdiction}")
        for stage in pack["stages"]:
            anchor = {"assessment": assessed, "fix_available": fix_available}.get(stage.get("start"), detected)
            needs_anchor = stage.get("start") in {"assessment", "fix_available"}
            due = None if stage.get("status") == "수동 확인 필요" or stage.get("hours") is None or (needs_anchor and anchor is None) else anchor + timedelta(hours=stage["hours"])
            remaining = None if due is None else int((due-current).total_seconds())
            rows.append({"jurisdiction": jurisdiction, "jurisdiction_name": pack["name"],
                         "stage": stage["id"], "stage_name": stage["name"], "due_at": due,
                         "remaining_seconds": remaining,
                         "alert_before_hours": pack.get("alert_before_hours", 0),
                         "status": "수동 확인 필요" if stage.get("status") == "수동 확인 필요" or (needs_anchor and anchor is None) else
                                   "초과" if remaining is not None and remaining < 0 else
                                   "임박" if remaining is not None and remaining <= pack.get("alert_before_hours", 0) * 3600 else "기한 내",
                         "reference": stage["reference"], "note": stage.get("note")})
    return rows


def package_hash(package: dict) -> str:
    payload = {key: value for key, value in package.items() if key != "package_sha256"}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                         default=lambda value: value.isoformat() if isinstance(value, datetime) else str(value)).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def seal(package: dict) -> dict:
    return {**package, "package_sha256": package_hash(package)}


def verify_package(package: dict) -> bool:
    return package.get("package_sha256") == package_hash(package)


def count_matches(query_count: int, included_count: int) -> bool:
    return query_count == included_count


def overdue(deadline_rows: list[dict], completed: set[tuple[str, str]]) -> list[dict]:
    return [row for row in deadline_rows if row["due_at"] and row["remaining_seconds"] < 0
            and (row["jurisdiction"], row["stage"]) not in completed]


def alertable(deadline_rows: list[dict], completed: set[tuple[str, str]]) -> list[dict]:
    return [row for row in deadline_rows if row["status"] in {"임박", "초과"}
            and (row["jurisdiction"], row["stage"]) not in completed]

