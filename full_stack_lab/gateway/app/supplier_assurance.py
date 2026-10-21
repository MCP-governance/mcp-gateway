"""Pure helpers for supplier evidence and runtime registry exports."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

REQUIRED_FIELDS = (
    "legal_entity", "supplier_contact", "security_contact", "support_end", "vulnerability_policy_url",
)
OPTIONAL_FIELDS = ("subprocessors", "sbom_submitted", "vex_submitted", "contract_basis_ref", "exit_strategy")
ASSURANCE_FIELDS = REQUIRED_FIELDS + OPTIONAL_FIELDS
UNCONFIRMED = "확인 안 됨"  # 받지 못한 항목을 있다고 적지 않는다. 화면·내보내기·기록 모두 이 말로 적는다.
EXPORT_FIELDS = (
    "server_id", "display_name", "supplier", "endpoint", "source_url", "license", "valid_until",
    *ASSURANCE_FIELDS,
)


def validate(value: dict[str, Any] | None, *, today: date | None = None, required: bool = True) -> list[str]:
    assurance = value or {}
    labels = {
        "legal_entity": "공급자 법인명", "supplier_contact": "공급자 연락처",
        "security_contact": "보안 연락처", "support_end": "지원 종료일",
        "vulnerability_policy_url": "취약점 공개 정책 주소",
    }
    lengths = {"legal_entity": 200, "supplier_contact": 300, "security_contact": 300,
               "support_end": 10, "vulnerability_policy_url": 500,
               "contract_basis_ref": 500, "exit_strategy": 1000}
    if any(not isinstance(assurance.get(key), str) for key in REQUIRED_FIELDS if assurance.get(key) is not None):
        errors = ["필수 공급자 보증 항목은 문자열이어야 합니다."]
    else:
        errors = []
    missing = [labels[key] for key in REQUIRED_FIELDS if not str(assurance.get(key) or "").strip()]
    if missing and required:
        errors.append(f"필수 공급자 보증 항목 누락: {', '.join(missing)}")
    raw_date = str(assurance.get("support_end") or "").strip()
    if raw_date:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_date):
            errors.append("지원 종료일은 YYYY-MM-DD 형식이어야 합니다.")
        else:
            try:
                end_date = date.fromisoformat(raw_date)
            except ValueError:
                errors.append("지원 종료일은 유효한 날짜여야 합니다.")
                end_date = None
            if end_date is not None and end_date < (today or datetime.now(timezone.utc).date()):
                errors.append("지원 종료일이 지났습니다. 재승인 대기 서버는 새 지원 근거로 다시 심사해야 합니다.")
    if any(len(str(assurance.get(key) or "").strip()) > limit for key, limit in lengths.items()):
        errors.append("공급자 보증 항목의 길이가 허용 범위를 넘었습니다.")
    if assurance.get("subprocessors") not in (None, "미확인", "있음", "없음"):
        errors.append("하위 처리자 여부 값이 올바르지 않습니다.")
    if any(key in assurance and not isinstance(assurance[key], bool) for key in ("sbom_submitted", "vex_submitted")):
        errors.append("SBOM/VEX 제출 여부는 참 또는 거짓이어야 합니다.")
    if any(key in assurance and not isinstance(assurance[key], str) for key in ("contract_basis_ref", "exit_strategy")):
        errors.append("계약 근거와 종료 전략은 문자열이어야 합니다.")
    policy_url = str(assurance.get("vulnerability_policy_url") or "").strip()
    if policy_url:
        try:
            parsed = urlsplit(policy_url)
            valid_url = parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password
        except ValueError:
            valid_url = False
        if not valid_url:
            errors.append("취약점 공개 정책 주소는 호스트가 포함된 HTTPS URL이어야 합니다.")
    return errors


def provided(assurance: dict[str, Any] | None, key: str) -> bool:
    value = (assurance or {}).get(key)
    return isinstance(value, bool) or (isinstance(value, str) and value.strip() not in ("", "미확인"))


def unconfirmed(assurance: dict[str, Any] | None) -> list[str]:
    """Items the approver did not receive. They stay empty in the record and are named here."""
    return [key for key in ASSURANCE_FIELDS if not provided(assurance, key)]


def support_expiry(support_end: str) -> datetime:
    """Use the day after the stated EOL date as the existing approval lapse boundary."""
    return datetime.combine(date.fromisoformat(support_end) + timedelta(days=1), time.min, timezone.utc)


def renewal_until(until: datetime, days: int, support_end: str | None) -> datetime:
    proposed = until + timedelta(days=days)
    return min(proposed, support_expiry(support_end)) if support_end else proposed


def export_rows(runtime_doc: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for server_id, spec in sorted((runtime_doc.get("servers") or {}).items()):
        if not spec.get("intake_id"):
            continue
        assurance = spec.get("supplier_assurance") or {}
        rows.append({
            "server_id": server_id,
            "display_name": spec.get("display_name") or "",
            "supplier": spec.get("supplier") or "",
            "endpoint": spec.get("endpoint") or "",
            "source_url": spec.get("source_url") or "",
            "license": spec.get("license") or "",
            "valid_until": spec.get("valid_until") or "",
            **{key: assurance[key] if provided(assurance, key) else UNCONFIRMED for key in ASSURANCE_FIELDS},
        })
    return rows


def export_hash(rows: list[dict[str, Any]]) -> str:
    raw = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def export_json(runtime_doc: dict[str, Any]) -> tuple[bytes, str]:
    rows = export_rows(runtime_doc)
    digest = export_hash(rows)
    payload = {"servers": rows, "sha256": digest}
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"), digest


def export_csv(runtime_doc: dict[str, Any]) -> tuple[bytes, str]:
    rows = export_rows(runtime_doc)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=EXPORT_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig"), export_hash(rows)


def matches_registry(runtime_doc: dict[str, Any], exported_rows: list[dict[str, Any]]) -> bool:
    normalized = []
    for row in exported_rows:
        value = dict(row)
        for key in ("sbom_submitted", "vex_submitted"):
            if value.get(key) == "True":
                value[key] = True
            elif value.get(key) == "False":
                value[key] = False
        normalized.append(value)
    return export_rows(runtime_doc) == normalized
