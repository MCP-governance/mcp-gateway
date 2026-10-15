"""Audit rows as sentences a person can read.

The decisions table is evidence; this module is the narrator. Every view of
activity - the Console timeline, `./console.sh watch`, reports - goes through
`describe()` so the same row reads the same way everywhere.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from . import db, review

DECISION_KO = {"Allow": "허용", "Alert": "허용·경보", "Restrict": "제한 실행", "Approval": "승인 대기", "Block": "차단"}
ACTION_KO = {"r": "읽기", "w": "쓰기", "x": "외부전송·실행", "connect": "연결"}
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
    evidence = row.get("result_preview") or {}
    # Rows written before D-62 have no disposition; derive it from the execution flags.
    response = evidence.get("disposition") or (
        "withheld" if row.get("upstream_executed") and row.get("policy_id") == "MCP-OUTPUT-001"
        else "returned" if row.get("upstream_executed")
        else "unknown" if row.get("upstream_attempted") else "not_executed")
    conflicts = row.get("conflicts") or []
    pac_failures = sorted({pid for pid in [row.get("policy_id"), *(c.get("policy_id") for c in conflicts)]
                           if pid and (pid.startswith("PAC-") or pid in {"INPUT_CONTRACT", "POLICY_BUNDLE"})})
    # The row exists because the call reached the Gateway. A device-bound token adds
    # the endpoint plane: that harness ran on an enrolled, kernel-confined account.
    # A call refused because the device failed (ENDPOINT-MANAGED-001) or a refused
    # connection was enforced by the Gateway alone.
    endpoint = (client.get("device_id") and row.get("policy_id") != "ENDPOINT-MANAGED-001"
                and (client.get("event_kind") or "tools/call") == "tools/call")
    planes = ["gateway"] + (["endpoint"] if endpoint else [])
    headline = (f"{who}({dept})" if dept else who) + (f" @{station}" if station else "")
    line = (f"{_time(row.get('created_at'))}  {DECISION_KO.get(decision, decision):<5}  {headline} · "
            f"{server}.{tool} {target[:90]}  [{row.get('policy_id')}] {row.get('reason', '')[:80]}")
    return {
        "id": row.get("id"), "at": row.get("created_at"), "decision": decision,
        "decision_ko": DECISION_KO.get(decision, decision), "tone": TONE.get(decision, ""),
        "who": who, "principal": row.get("user_token"), "department": dept, "role": row.get("role"), "workstation": station,
        "agent": client.get("agent"), "task_id": client.get("task_id"), "traceparent": client.get("traceparent"),
        "harness": (client.get("harness") or {}).get("name"),
        "event_kind": client.get("event_kind") or "tools/call",
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
        "attempted": bool(row.get("upstream_attempted")),
        "response": response, "response_bytes": evidence.get("bytes"), "response_sha256": evidence.get("sha256"),
        "response_types": evidence.get("content_types") or [], "masked_types": evidence.get("masked_types") or [],
        "conflicts": conflicts, "pac_failures": pac_failures,
        "planes": planes, "device_id": client.get("device_id"), "evidence_sha256": row.get("entry_sha256"),
        "timings": row.get("timings") or {},
        "line": line,
    }


async def recent(after: int = 0, limit: int = 100, user_token: str | None = None,
                 decision: str | None = None, server: str | None = None, person: str | None = None,
                 event_kind: str | None = None, execution: str | None = None,
                 endpoint: str | None = None, policy: str | None = None,
                 since: datetime | None = None, until: datetime | None = None,
                 page: int = 1, query: str | None = None) -> dict:
    base_clauses, base_params = [], []
    if user_token:
        base_clauses.append("d.user_token = %s"); base_params.append(user_token)
    clauses, params = list(base_clauses), list(base_params)
    if decision:
        clauses.append("d.decision = %s"); params.append(decision)
    if server:
        clauses.append("d.server_id = %s"); params.append(server)
    if person:
        clauses.append("(p.display_name ILIKE %s OR d.user_token ILIKE %s)"); params += [f"%{person}%", f"%{person}%"]
    if endpoint:
        clauses.append("(COALESCE(d.client->>'workstation','') ILIKE %s OR COALESCE(d.client->>'endpoint_id','') ILIKE %s OR COALESCE(d.client->>'device_id','') ILIKE %s)")
        params += [f"%{endpoint}%", f"%{endpoint}%", f"%{endpoint}%"]
    if policy:
        clauses.append("d.policy_id ILIKE %s"); params.append(f"%{policy}%")
    if since:
        clauses.append("d.created_at >= %s"); params.append(since)
    if until:
        clauses.append("d.created_at <= %s"); params.append(until)
    if event_kind:
        clauses.append("COALESCE(d.client->>'event_kind','tools/call')=%s"); params.append(event_kind)
    if execution == "executed":
        clauses.append("d.upstream_executed=true")
    elif execution == "not-sent":
        clauses.append("d.upstream_attempted=false AND d.upstream_executed=false")
    elif execution == "unknown":
        clauses.append("d.upstream_attempted=true AND d.upstream_executed=false")
    elif execution == "withheld":
        clauses.append("d.upstream_executed=true AND (d.result_preview->>'disposition'='withheld' OR d.policy_id='MCP-OUTPUT-001')")
    elif execution == "connection-denied":
        clauses.append("COALESCE(d.client->>'event_kind','tools/call')='mcp-connection'")
    if query and query.strip():
        term = f"%{query.strip()}%"
        clauses.append("""(p.display_name ILIKE %s OR p.department ILIKE %s OR d.user_token ILIKE %s
            OR COALESCE(d.client->>'workstation','') ILIKE %s OR COALESCE(d.client->>'endpoint_id','') ILIKE %s
            OR COALESCE(d.client->>'harness','') ILIKE %s OR COALESCE(d.client->>'agent','') ILIKE %s
            OR d.server_id ILIKE %s OR d.tool_name ILIKE %s OR COALESCE(d.resource_id,'') ILIKE %s
            OR d.policy_id ILIKE %s OR COALESCE(d.trace_id::text,'') ILIKE %s OR d.reason ILIKE %s)""")
        params.extend([term] * 13)
    filtered_where = " AND ".join(clauses) or "true"
    filtered_params = tuple(params)
    page_size = min(max(limit, 1), 100)
    current_page = max(page, 1)
    if after:
        clauses.append("d.id > %s"); params.append(after)
    order = "ASC" if after else "DESC"
    offset = 0 if after else (current_page - 1) * page_size
    rows = await db.fetch_all(
        f"""SELECT d.id, d.created_at, d.user_token, d.role, d.server_id, d.tool_name, d.resource_id,
                   d.destinations, d.client, d.summary, d.data_class, d.action, d.decision, d.policy_id,
                   d.reason, d.upstream_executed, d.upstream_attempted, d.approval_id, d.trace_id, d.error,
                   d.exception_id, d.enforcement, d.would_decision, d.risk_score, d.privacy_types,
                   d.sequence_flags, d.result_preview, d.conflicts, d.entry_sha256, d.timings, p.display_name, p.department
              FROM decisions d LEFT JOIN principals p ON p.token = d.user_token
             WHERE {' AND '.join(clauses) or 'true'} ORDER BY d.id {order} LIMIT %s OFFSET %s""",
        (*params, page_size, offset))
    described = await review.mark_invalid([describe(dict(row)) for row in rows])
    if not after:
        described.reverse()
    cursor = max([after] + [int(r["id"]) for r in described])
    if after:
        return {"rows": described, "cursor": cursor}
    filtered = await db.fetch_one(
        f"""SELECT count(*) AS n, COALESCE(max(d.id), 0) AS cursor
              FROM decisions d LEFT JOIN principals p ON p.token = d.user_token
             WHERE {filtered_where}""", filtered_params)
    base_where = " AND ".join(base_clauses) or "true"
    total = await db.fetch_one(
        f"SELECT count(*) AS n FROM decisions d WHERE {base_where}", tuple(base_params))
    return {"rows": described, "cursor": int(filtered["cursor"] or 0),
            "total": int(total["n"] or 0), "filtered_total": int(filtered["n"] or 0),
            "page": current_page, "page_size": page_size}


async def analysis(user_token: str | None = None, decision: str | None = None,
                   server: str | None = None, person: str | None = None,
                   event_kind: str | None = None, execution: str | None = None,
                   endpoint: str | None = None, policy: str | None = None,
                   since: datetime | None = None, until: datetime | None = None,
                   query: str | None = None) -> dict:
    clauses, params = [], []
    if user_token:
        clauses.append("d.user_token = %s"); params.append(user_token)
    if decision:
        clauses.append("d.decision = %s"); params.append(decision)
    if server:
        clauses.append("d.server_id = %s"); params.append(server)
    if person:
        clauses.append("(p.display_name ILIKE %s OR d.user_token ILIKE %s)")
        params += [f"%{person}%", f"%{person}%"]
    if endpoint:
        clauses.append("(COALESCE(d.client->>'workstation','') ILIKE %s OR COALESCE(d.client->>'endpoint_id','') ILIKE %s OR COALESCE(d.client->>'device_id','') ILIKE %s)")
        params += [f"%{endpoint}%", f"%{endpoint}%", f"%{endpoint}%"]
    if policy:
        clauses.append("d.policy_id ILIKE %s"); params.append(f"%{policy}%")
    if since:
        clauses.append("d.created_at >= %s"); params.append(since)
    if until:
        clauses.append("d.created_at <= %s"); params.append(until)
    if event_kind:
        clauses.append("COALESCE(d.client->>'event_kind','tools/call')=%s"); params.append(event_kind)
    if execution == "executed":
        clauses.append("d.upstream_executed=true")
    elif execution == "not-sent":
        clauses.append("d.upstream_attempted=false AND d.upstream_executed=false")
    elif execution == "unknown":
        clauses.append("d.upstream_attempted=true AND d.upstream_executed=false")
    elif execution == "withheld":
        clauses.append("d.upstream_executed=true AND (d.result_preview->>'disposition'='withheld' OR d.policy_id='MCP-OUTPUT-001')")
    elif execution == "connection-denied":
        clauses.append("COALESCE(d.client->>'event_kind','tools/call')='mcp-connection'")
    if query and query.strip():
        term = f"%{query.strip()}%"
        clauses.append("""(p.display_name ILIKE %s OR p.department ILIKE %s OR d.user_token ILIKE %s
            OR COALESCE(d.client->>'workstation','') ILIKE %s OR COALESCE(d.client->>'endpoint_id','') ILIKE %s
            OR COALESCE(d.client->>'harness','') ILIKE %s OR COALESCE(d.client->>'agent','') ILIKE %s
            OR d.server_id ILIKE %s OR d.tool_name ILIKE %s OR COALESCE(d.resource_id,'') ILIKE %s
            OR d.policy_id ILIKE %s OR COALESCE(d.trace_id::text,'') ILIKE %s OR d.reason ILIKE %s)""")
        params.extend([term] * 13)
    where = " AND ".join(clauses) or "true"
    joins = "FROM decisions d LEFT JOIN principals p ON p.token = d.user_token"
    args = tuple(params)
    bounds = await db.fetch_one(
        f"SELECT count(*) AS n, min(d.created_at) AS first, max(d.created_at) AS last {joins} WHERE {where}", args)
    total = int(bounds["n"] or 0)
    if not total:
        return {"total": 0, "bucket": "hour", "series": [], "responses": [],
                "hours": [], "harnesses": [], "servers": [], "people": []}
    span = (bounds["last"] - bounds["first"]).total_seconds()
    unit = "hour" if span <= 172800 else "day" if span <= 10368000 else "month"
    series_rows = await db.fetch_all(
        f"""SELECT date_trunc('{unit}', d.created_at AT TIME ZONE 'Asia/Seoul') AS bucket,
                    d.decision, count(*) AS n
               {joins} WHERE {where} GROUP BY 1, 2 ORDER BY 1""", args)
    hour_rows = await db.fetch_all(
        f"""SELECT extract(hour FROM d.created_at AT TIME ZONE 'Asia/Seoul')::int AS hour,
                    d.decision, count(*) AS n
               {joins} WHERE {where} GROUP BY 1, 2 ORDER BY 1""", args)
    response_rows = await db.fetch_all(
        f"""SELECT COALESCE(d.result_preview->>'disposition',
                    CASE WHEN d.upstream_executed AND d.policy_id='MCP-OUTPUT-001' THEN 'withheld'
                         WHEN d.upstream_executed THEN 'returned'
                         WHEN d.upstream_attempted THEN 'unknown' ELSE 'not_executed' END) AS response,
                    count(*) AS n
               {joins} WHERE {where} GROUP BY 1""", args)
    dimension_rows = {}
    dimensions = {
        "harnesses": "COALESCE(d.client->'harness'->>'name', d.client->>'agent', '알 수 없음')",
        "servers": "COALESCE(d.server_id, '알 수 없음')",
        "people": "COALESCE(p.display_name, d.user_token, '알 수 없음')",
    }
    for name, expression in dimensions.items():
        dimension_rows[name] = await db.fetch_all(
            f"""SELECT {expression} AS key, d.decision, count(*) AS n
                   {joins} WHERE {where} GROUP BY 1, 2""", args)

    decisions = ("Allow", "Alert", "Restrict", "Approval", "Block")
    def grouped(rows: list, cap: int = 12) -> list[dict]:
        groups = {}
        for row in rows:
            item = groups.setdefault(row["key"], {"key": row["key"], "total": 0, **{key: 0 for key in decisions}})
            count = int(row["n"] or 0)
            item[row["decision"]] = count
            item["total"] += count
        ordered = sorted(groups.values(), key=lambda item: item["total"], reverse=True)
        if len(ordered) <= cap:
            return ordered
        other = {"key": "기타", "total": 0, **{key: 0 for key in decisions}}
        for item in ordered[cap:]:
            for key in ("total", *decisions):
                other[key] += item[key]
        return ordered[:cap] + [other]

    return {
        "total": total, "bucket": unit,
        "series": [{"at": row["bucket"], "decision": row["decision"], "n": int(row["n"] or 0)} for row in series_rows],
        "hours": [{"hour": int(row["hour"]), "decision": row["decision"], "n": int(row["n"] or 0)} for row in hour_rows],
        "responses": [{"response": row["response"], "n": int(row["n"] or 0)} for row in response_rows],
        "harnesses": grouped(dimension_rows["harnesses"]),
        "servers": grouped(dimension_rows["servers"]),
        "people": grouped(dimension_rows["people"]),
    }
