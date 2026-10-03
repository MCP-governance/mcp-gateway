"""Read-only projections of the canonical ledger; never export call bodies."""
from __future__ import annotations

import hashlib
import json
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder

from . import db

DECISIONS = {"Allow", "Alert", "Restrict", "Approval", "Block"}
EXECUTIONS = {"executed", "not-sent", "unknown", "withheld"}
KINDS = {"tools/call", "mcp-connection"}
# Deliberately exclude request_payload, result, policy_input and client-reported data.
PROJECTION = """id,created_at,request_id,trace_id,user_token,role,server_id,tool_name,action,
    data_class,decision,policy_id,approval_id,upstream_attempted,upstream_executed,
    result_preview->>'disposition' AS response_disposition,
    result_preview->>'sha256' AS response_sha256,
    COALESCE(client->>'event_kind','tools/call') AS event_kind,prev_sha256,entry_sha256,chain_version"""


def predicates(*, before=0, decision=None, server=None, principal=None, policy=None,
               event_kind=None, execution=None, since=None, until=None, trace_id=None):
    clauses, params = [], []
    for name, value, allowed in (("decision", decision, DECISIONS), ("execution", execution, EXECUTIONS),
                                 ("event_kind", event_kind, KINDS)):
        if value and value not in allowed:
            raise HTTPException(422, f"지원하지 않는 {name} 필터입니다.")
    if any(value and value.tzinfo is None for value in (since, until)):
        raise HTTPException(422, "조회 시각에는 시간대가 필요합니다.")
    if since and until and since > until:
        raise HTTPException(422, "조회 시작 시각이 종료 시각보다 늦습니다.")
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
            "withheld": "upstream_executed=true AND (result_preview->>'disposition'='withheld' OR policy_id='MCP-OUTPUT-001')"}[execution])
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
    rows = rows[:limit]
    return {"events": rows, "has_more": more, "next_before": rows[-1]["id"] if more else None,
            "source": "postgresql/decisions", "projection": "redacted", "filters": filters}


async def detail(event_id: int) -> dict:
    row = await db.fetch_one(f"SELECT {PROJECTION} FROM decisions WHERE id=%s", (event_id,))
    if not row:
        raise HTTPException(404, "감사 이벤트가 없습니다.")
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
