"""Audit rows as sentences a person can read.

The decisions table is evidence; this module is the narrator. Every view of
activity - the Console timeline, `./console.sh watch`, reports - goes through
`describe()` so the same row reads the same way everywhere.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from . import db

DECISION_KO = {"Allow": "허용", "Alert": "허용·경보", "Restrict": "제한 실행", "Approval": "승인 대기", "Block": "차단"}
ACTION_KO = {"r": "읽기", "w": "쓰기", "x": "외부전송·실행"}
CLASS_KO = {"public": "공개", "nonimportant": "내부", "important": "중요"}
TONE = {"Allow": "ok", "Alert": "warn", "Restrict": "info", "Approval": "hold", "Block": "stop"}


def _time(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone().strftime("%H:%M:%S")
    return str(value or "")[11:19]


def describe(row: dict) -> dict:
    decision = row.get("decision") or "?"
    who = row.get("display_name") or row.get("user_token") or "알 수 없음"
    dept = row.get("department")
    client = row.get("client") or {}
    station = client.get("workstation")
    target = row.get("resource_id") or ""
    destinations = row.get("destinations") or []
    if destinations:
        target = ", ".join(d.get("value", "") for d in destinations[:2])
    server, tool = row.get("server_id") or "?", row.get("tool_name") or "?"
    outcome = "실행됨" if row.get("upstream_executed") else ("실행 여부 미확인" if row.get("upstream_attempted") else "실행 안 함")
    if decision == "Approval":
        outcome = "관리자 승인 대기"
    headline = (f"{who}({dept})" if dept else who) + (f" @{station}" if station else "")
    line = (f"{_time(row.get('created_at'))}  {DECISION_KO.get(decision, decision):<5}  {headline} · "
            f"{server}.{tool} {target[:90]}  [{row.get('policy_id')}] {row.get('reason', '')[:80]}")
    return {
        "id": row.get("id"), "at": row.get("created_at"), "decision": decision,
        "decision_ko": DECISION_KO.get(decision, decision), "tone": TONE.get(decision, ""),
        "who": who, "department": dept, "role": row.get("role"), "workstation": station,
        "agent": client.get("agent"), "task_id": client.get("task_id"),
        "harness": (client.get("harness") or {}).get("name"),
        "server": server, "tool": tool, "target": target,
        "action": row.get("action"), "action_ko": ACTION_KO.get(row.get("action") or "", row.get("action")),
        "data_class": row.get("data_class"), "data_class_ko": CLASS_KO.get(row.get("data_class") or "", row.get("data_class")),
        "policy_id": row.get("policy_id"), "reason": row.get("reason"), "outcome": outcome,
        "executed": bool(row.get("upstream_executed")), "approval_id": row.get("approval_id"),
        "trace_id": row.get("trace_id"), "error": row.get("error"),
        "exception_id": row.get("exception_id"), "enforcement": row.get("enforcement"),
        "would_decision": row.get("would_decision"), "summary": row.get("summary"),
        "risk_score": row.get("risk_score") or 0, "privacy_types": row.get("privacy_types") or [],
        "sequence_flags": row.get("sequence_flags") or [],
        "line": line,
    }


async def recent(after: int = 0, limit: int = 100, user_token: str | None = None,
                 decision: str | None = None, server: str | None = None, person: str | None = None) -> dict:
    clauses, params = ["d.id > %s"], [after]
    if user_token:
        clauses.append("d.user_token = %s"); params.append(user_token)
    if decision:
        clauses.append("d.decision = %s"); params.append(decision)
    if server:
        clauses.append("d.server_id = %s"); params.append(server)
    if person:
        clauses.append("(p.display_name ILIKE %s OR d.user_token ILIKE %s)"); params += [f"%{person}%", f"%{person}%"]
    order = "ASC" if after else "DESC"
    rows = await db.fetch_all(
        f"""SELECT d.id, d.created_at, d.user_token, d.role, d.server_id, d.tool_name, d.resource_id,
                   d.destinations, d.client, d.summary, d.data_class, d.action, d.decision, d.policy_id,
                   d.reason, d.upstream_executed, d.upstream_attempted, d.approval_id, d.trace_id, d.error,
                   d.exception_id, d.enforcement, d.would_decision, d.risk_score, d.privacy_types,
                   d.sequence_flags, p.display_name, p.department
              FROM decisions d LEFT JOIN principals p ON p.token = d.user_token
             WHERE {' AND '.join(clauses)} ORDER BY d.id {order} LIMIT %s""",
        (*params, min(max(limit, 1), 500)))
    described = [describe(dict(row)) for row in rows]
    if not after:
        described.reverse()
    cursor = max([after] + [int(r["id"]) for r in described])
    return {"rows": described, "cursor": cursor}
