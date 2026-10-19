"""Pure contract helpers: canonical hashing, the policy-result schema, the audit chain's
column sets. Nothing here reads the environment, opens a connection or starts tracing,
so replay, registry and offline tools can import it without importing the Gateway
(ROADMAP 6: "순수 계약 모듈"). core re-exports the names for older callers.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from jsonschema import Draft202012Validator


# OPA is a trust boundary too. Only policy fields may enter the execution event;
# a malformed result must never become Allow through monitor mode.
POLICY_RESULT = Draft202012Validator({
    "type": "object", "additionalProperties": False,
    "required": ["decision", "policy_id", "reason", "restrictions"],
    "properties": {
        "decision": {"enum": ["Allow", "Alert", "Restrict", "Approval", "Block"]},
        "policy_id": {"type": "string", "minLength": 1},
        "reason": {"type": "string", "minLength": 1},
        "restrictions": {
            "type": "object", "additionalProperties": False,
            "properties": {"max_chars": {"type": "integer", "minimum": 0, "maximum": 100000},
                           "journal_bcc": {"type": "string", "pattern": "^[^@\\s]+@[^@\\s]+$"}},
        },
        **{key: {"type": "string"} for key in (
            "policy_name", "policy_version", "policy_status", "policy_set_version", "environment")},
        **{key: {"type": "array", "items": {"type": "string"}} for key in (
            "risk_ids", "control_ids", "requirement_ids", "obligations")},
        "priority": {"type": ["integer", "null"]},
        "conditions": {"type": "object"},
        "exception": {"type": ["object", "null"], "required": ["id"],
                      "properties": {"id": {"type": "string", "minLength": 1}}},
        "conflicts": {"type": "array", "items": {"type": "object"}},
    },
})


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


AUDIT_COLUMN_SETS = {
    1: (
        "request_id", "trace_id", "user_token", "role", "tool_name", "data_class", "action",
        "decision", "policy_id", "reason", "upstream_executed", "restrictions", "approval_id",
        "request_payload", "result_preview", "error",
    ),
    2: (
        "request_id", "trace_id", "user_token", "role", "tool_name", "data_class", "action",
        "decision", "policy_id", "reason", "upstream_executed", "restrictions", "approval_id",
        "request_payload", "result_preview", "error",
        "enforcement", "would_decision", "would_policy_id",
    ),
    3: (
        "request_id", "trace_id", "user_token", "role", "tool_name", "data_class", "action",
        "decision", "policy_id", "reason", "upstream_executed", "restrictions", "approval_id",
        "request_payload", "result_preview", "error",
        "enforcement", "would_decision", "would_policy_id",
        # §11.17 정책 판단 및 집행 증적
        "policy_version", "obligations", "exception_id", "conflicts", "environment",
    ),
}
AUDIT_COLUMN_SETS[4] = (*AUDIT_COLUMN_SETS[3], "upstream_attempted")
# v5: which registered server, which resource, where it was going, and from which
# workstation/agent - the fields a reader needs to understand the row without a join.
AUDIT_COLUMN_SETS[5] = (*AUDIT_COLUMN_SETS[4], "server_id", "resource_id", "destinations", "client", "summary")
# v6: the PDF-integration fields - the policy input (for replay against a candidate
# policy), the investigation risk score, Presidio entity types and chain flags.
# origin/main (cc086e5) added these on v1 as *its* "v5"; v2's v5 means other columns,
# so the merged line records them as v6. A database written by v1's v5 is not migrated
# (v2 needs `./console.sh reset`): verifying its rows against v2's v5 would fail, and
# accepting either definition would let a row tampered in a column only one covers pass.
AUDIT_COLUMN_SETS[6] = (*AUDIT_COLUMN_SETS[5], "policy_input", "risk_score", "privacy_types", "sequence_flags")
AUDIT_COLUMN_SETS[7] = (*AUDIT_COLUMN_SETS[6], "created_at")
AUDIT_COLUMN_SETS[8] = (*AUDIT_COLUMN_SETS[7], "outcome")
CHAIN_VERSION = 8
AUDIT_COLUMNS = AUDIT_COLUMN_SETS[CHAIN_VERSION]
GENESIS = "0" * 64


def audit_fingerprint(record: dict, version: int = CHAIN_VERSION) -> str:
    """One canonical form for both the append and the later verification.

    Values are normalised to str / bool / None / JSON documents so that the hash of a
    row read back from PostgreSQL matches the hash computed when it was written.
    """
    normalised = {}
    for column in AUDIT_COLUMN_SETS[version]:
        value = record.get(column)
        if column == "created_at" and value is not None:
            timestamp = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
            if timestamp.tzinfo is None:
                raise ValueError("audit timestamp requires a timezone")
            normalised[column] = timestamp.astimezone(UTC).isoformat(timespec="microseconds")
        elif column in {"upstream_executed", "upstream_attempted"}:
            normalised[column] = bool(value)
        elif isinstance(value, (dict, list)) or value is None:
            normalised[column] = value
        else:
            normalised[column] = str(value)
    return canonical_hash(normalised)


def walk_chain(rows, head: dict | None, seal: dict | None = None) -> dict:
    """Name the first row that does not follow from the previous one.

    A retention seal (D-141, signed outside the database) is the only thing that lets the
    walk start after GENESIS, and a row at or below it is a resurrected disposal.
    """
    previous = seal["last_sha256"] if seal else GENESIS
    chained = 0
    for row in rows:
        if seal and row["id"] <= seal["last_id"]:
            return {"intact": False, "checked": 0, "broken_at": row["id"],
                    "reason": "폐기한 구간의 행이 다시 있습니다. 백업 복원으로 되살아났을 수 있습니다."}
        if row["entry_sha256"] is None:
            # Written before the chain existed. It anchors nothing and claims nothing.
            continue
        version = int(row["chain_version"] or 1)
        if version not in AUDIT_COLUMN_SETS:
            return {"intact": False, "checked": chained, "broken_at": row["id"],
                    "reason": f"알 수 없는 체인 버전 {version}입니다."}
        expected = hashlib.sha256((previous + audit_fingerprint(row, version)).encode()).hexdigest()
        if row["prev_sha256"] != previous:
            return {"intact": False, "checked": chained, "broken_at": row["id"],
                    "reason": "이전 항목과 연결되지 않습니다. 앞의 행이 지워졌을 수 있습니다."}
        if row["entry_sha256"] != expected:
            return {"intact": False, "checked": chained, "broken_at": row["id"],
                    "reason": "항목 내용이 기록된 해시와 다릅니다."}
        previous = row["entry_sha256"]
        chained += 1
    if head and head["head_sha256"] != previous:
        return {"intact": False, "checked": chained, "broken_at": None,
                "reason": "마지막 항목이 체인 head와 다릅니다. 끝부분이 잘렸을 수 있습니다."}
    return {"intact": True, "checked": chained, "head": previous,
            "entries_recorded": int(head["entries"]) if head else None,
            "sealed_through": seal["last_id"] if seal else None}
