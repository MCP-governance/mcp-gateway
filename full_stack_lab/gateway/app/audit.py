"""Read-only projections of the canonical ledger; never export call bodies."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder

from . import activity, db, review
from .outcomes import recorded_outcome

DECISIONS = {"Allow", "Alert", "Restrict", "Approval", "Block"}


async def alerts(limit=100, *, since=None, until=None, hours=None, before=0, seen=0, read_ranges=None, alert_id=None):
    predicates(since=since, until=until)
    if hours is not None and (since or until):
        raise HTTPException(422, "기간과 시간 수는 함께 지정할 수 없습니다.")
    now = datetime.now(timezone.utc)
    if hours is not None:
        until, since = now, now - timedelta(hours=hours)
    where, params = ["NOT a.synthetic"], []
    if alert_id:
        where.append("a.id=%s")
        params.append(alert_id)
    for value, op in ((since, ">="), (until, "<=")):
        if value:
            where.append(f"a.created_at {op} %s")
            params.append(value)
    base = " AND ".join(where)
    count = await db.fetch_one("SELECT count(*) AS n FROM ops_alerts a WHERE " + base, tuple(params))
    rows = await db.fetch_all(
        "SELECT a.id,a.kind,a.origin,a.origin_id,a.created_at,a.evidence,s.display_name AS server_name, "
        "d.client->>'device_id' AS decision_endpoint, d.reason, d.upstream_attempted, d.upstream_executed, "
        "ep.hostname, p.display_name AS owner_name "
        "FROM ops_alerts a LEFT JOIN mcp_servers s ON s.id=a.evidence->>'server_id' "
        "LEFT JOIN decisions d ON a.origin='decision' AND d.id::text=a.origin_id "
        "LEFT JOIN endpoint_agents ep ON ep.endpoint_id=coalesce(a.evidence->>'endpoint_id', d.client->>'device_id') "
        "LEFT JOIN principals p ON p.token=coalesce(ep.owner_token, a.evidence->>'user_token', d.user_token) WHERE "
        + base + (" AND a.id < %s" if before else "") + " ORDER BY a.id DESC LIMIT %s",
        (*params, *([before] if before else []), limit + 1))
    for row in rows:
        row["evidence"] = dict(row.get("evidence") or {})
        kind = {"endpoint-inventory": "config", "endpoint-listener": "listener"}.get(row.get("origin"))
        if kind:
            row["evidence"].update(record_kind=kind, record_id=row.get("origin_id"))
        if row.get("decision_endpoint"):
            row["evidence"]["endpoint_id"] = row["decision_endpoint"]
        row["execution"] = ("실행됨" if row.get("upstream_executed") else "실행 미확인"
                            if row.get("upstream_attempted") else "실행 안 함"
                            if row.get("upstream_attempted") is False else "미확인")
    day_since = now - timedelta(hours=24)
    day = await db.fetch_one("SELECT count(*) AS n FROM ops_alerts WHERE NOT synthetic AND created_at >= %s AND created_at <= %s", (day_since, now))
    ranges = []
    for item in (read_ranges or "").split(","):
        if not item:
            continue
        if not re.fullmatch(r"\d{1,18}(-\d{1,18})?", item) or len(ranges) >= 1000:
            raise HTTPException(422, "읽음 범위 확인 필요")
        parts = list(map(int, item.split("-")))
        low, high = parts[0], parts[-1]
        if low > high:
            raise HTTPException(422, "읽음 범위 확인 필요")
        ranges.append((low, high))
    unread = await db.fetch_one("SELECT count(*) AS n FROM ops_alerts WHERE NOT synthetic AND id > %s"
        + (" AND NOT (" + " OR ".join("id BETWEEN %s AND %s" for _ in ranges) + ")" if ranges else ""),
        (seen, *(value for pair in ranges for value in pair)))
    more = len(rows) > limit
    return {"alerts": rows[:limit], "total": int(count["n"] or 0), "last_24h": int(day["n"] or 0),
            "unread_count": int(unread["n"] or 0), "has_more": more,
            "next_before": rows[limit-1]["id"] if more else None,
            "since": since, "until": until, "day_since": day_since, "day_until": now}
EXECUTIONS = {"executed", "not-sent", "unknown", "withheld", "connection-denied"}
KINDS = {"tools/call", "mcp-connection"}
# Deliberately exclude request_payload, result, policy_input and client-reported data.
PROJECTION = """id,created_at,request_id,trace_id,user_token,role,server_id,tool_name,action,
    data_class,decision,policy_id,approval_id,upstream_attempted,upstream_executed,outcome,
    error AS outcome_error,
    (SELECT i.state FROM dispatch_intents i WHERE i.request_id=decisions.request_id) AS intent_state,
    result_preview->>'disposition' AS response_disposition,
    result_preview->>'sha256' AS response_sha256,
    COALESCE(client->>'event_kind','tools/call') AS event_kind,prev_sha256,entry_sha256,chain_version"""


def predicates(*, before=0, decision=None, server=None, principal=None, policy=None,
               event_kind=None, execution=None, since=None, until=None, trace_id=None,
               person=None, endpoint=None, query=None, view="ledger"):
    clauses, params = [], []
    for name, value, allowed in (("decision", decision, DECISIONS), ("execution", execution, EXECUTIONS),
                                 ("event_kind", event_kind, KINDS)):
        if value and value not in allowed:
            raise HTTPException(422, f"지원하지 않는 {name} 필터입니다.")
    if any(value and value.tzinfo is None for value in (since, until)):
        raise HTTPException(422, "조회 시각에는 시간대가 필요합니다.")
    if since and until and since > until:
        raise HTTPException(422, "조회 시작 시각이 종료 시각보다 늦습니다.")
    if view not in {"ledger", "calls"}:
        raise HTTPException(422, "지원하지 않는 조회 방식입니다.")
    if view == "calls":
        selected, params = activity.filter_predicates(decision=decision, server=server, principal=principal,
            person=person, policy=policy, event_kind=event_kind, execution=execution, endpoint=endpoint,
            since=since, until=until, query=query, trace_id=trace_id, before=before)
        where = " AND ".join(selected) or "true"
        return f"id IN (SELECT d.id FROM decisions d LEFT JOIN principals p ON p.token=d.user_token WHERE {where})", params
    if person or endpoint or query:
        raise HTTPException(422, "검색 필터에는 호출 조회 방식이 필요합니다.")
    for column, value, operator in (("id", before, "<"), ("decision", decision, "="),
                                  ("server_id", server, "="), ("user_token", principal, "="),
                                  ("policy_id", policy, "="), ("trace_id", trace_id, "="),
                                  ("created_at", since, ">="), ("created_at", until, "<=")):
        if value:
            clauses.append(f"{column} {operator} %s")
            params.append(value)
    if event_kind:
        clauses.append("COALESCE(client->>'event_kind','tools/call')=%s")
        params.append(event_kind)
    if execution:
        clauses.append({"executed": "upstream_executed=true",
            "not-sent": "upstream_attempted=false AND upstream_executed=false",
            "unknown": "upstream_attempted=true AND upstream_executed=false",
            "withheld": "upstream_executed=true AND (result_preview->>'disposition'='withheld' OR policy_id='MCP-OUTPUT-001')",
            "connection-denied": "COALESCE(client->>'event_kind','tools/call')='mcp-connection'"}[execution])
    return " AND ".join(clauses) or "true", params


async def events(limit: int = 100, connection=None, **filters) -> dict:
    where, params = predicates(**filters)
    query = f"SELECT {PROJECTION} FROM decisions WHERE {where} ORDER BY id DESC LIMIT %s"
    params.append(limit+1)
    if connection:
        rows = await (await connection.execute(query, params)).fetchall()
    else:
        rows = await db.fetch_all(query, params)
    more = len(rows) > limit
    rows = await review.mark_invalid(rows[:limit], connection=connection)
    rows = [with_outcome(row) for row in rows]
    return {"events": rows, "has_more": more, "next_before": rows[-1]["id"] if more else None,
            "source": "postgresql/decisions", "projection": "redacted", "filters": filters}


async def detail(event_id: int) -> dict:
    row = await db.fetch_one(f"SELECT {PROJECTION} FROM decisions WHERE id=%s", (event_id,))
    if not row:
        raise HTTPException(404, "감사 이벤트가 없습니다.")
    return with_outcome((await review.mark_invalid([row]))[0])


def with_outcome(row: dict) -> dict:
    row = dict(row)
    error = row.pop("outcome_error", None)
    row["outcome_axes"] = recorded_outcome({**row, "error": error})
    row["outcome_axes"] = {**row["outcome_axes"], "route": "게이트웨이",
                           "execution": "실행됨" if row.get("upstream_executed") else "실행 미확인"
                           if row.get("upstream_attempted") else "실행 안 함"}
    row.pop("intent_state", None)
    return row


async def export(limit: int, **filters) -> dict:
    from .core import verify_audit_chain
    async with db.transaction() as connection:
        await connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        page = await events(limit=limit, connection=connection, **filters)
        verification = await verify_audit_chain(connection)
    payload = jsonable_encoder({"schema": "mcpgw-audit-export/v1", **page, "verification": verification})
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return {"manifest": {"sha256": hashlib.sha256(encoded).hexdigest(), "count": len(page["events"]),
                         "canonicalization": "UTF-8 JSON, sorted keys, compact separators",
                         "scope": "조회 조건에 해당하는 페이지. 원문 대신 감사 필드만 포함.",
                         "verification_scope": "동일 DB 스냅샷의 전체 원장. 이 파일만으로 원문 체인을 재검증할 수 없음."},
            "payload": payload}
