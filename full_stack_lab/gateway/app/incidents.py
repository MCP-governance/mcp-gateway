"""Incident records backed by the append-only decision ledger."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from psycopg.types.json import Jsonb
from uuid import UUID

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder

from . import audit, core, db, incident_pack, ops_response


def clean_row(row: dict) -> dict:
    value = audit.with_outcome(row)
    actor = value.pop("user_token", "")
    value["actor_ref"] = hashlib.sha256(actor.encode()).hexdigest() if actor else None
    return value


async def create(data: dict, actor: str) -> dict:
    try:
        selected = incident_pack.packs()
        jurisdictions = list(dict.fromkeys(data["jurisdictions"]))
        if not jurisdictions or any(item not in selected for item in jurisdictions):
            raise ValueError("관할 팩을 하나 이상 선택해야 합니다.")
        started, detected = incident_pack.parse_time(data["started_at"]), incident_pack.parse_time(data["detected_at"])
        assessed = incident_pack.parse_time(data["assessed_at"]) if data.get("assessed_at") else None
        since, until = incident_pack.parse_time(data["scope_since"]), incident_pack.parse_time(data["scope_until"])
        if started > detected or (assessed and assessed < detected) or since > until or until > detected:
            raise ValueError("사고·영향 범위의 시각 순서를 확인하세요.")
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc
    scope = {key: data.get(key) for key in ("server_id", "tool_name", "principal") if data.get(key)}
    row = await db.fetch_one(
        """INSERT INTO incident_cases(title,started_at,detected_at,assessed_at,scope_since,scope_until,scope,jurisdictions,created_by)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        (data["title"], started, detected, assessed, since, until, Jsonb(scope),
         jurisdictions, actor))
    await db.execute(
        """INSERT INTO approval_events(kind,outcome,target_kind,target_id,actor,reason,scope)
           VALUES ('incident-created','recorded','incident',%s,%s,%s,%s)""",
        (str(row["id"]), actor, "사고 범위와 관할 기한 기록", Jsonb(scope)))
    return await detail(row["id"])


async def list_cases() -> dict:
    heartbeat = await db.fetch_one("SELECT checked_at FROM incident_timer_heartbeat WHERE id=1")
    timer_available = bool(heartbeat and (datetime.now(timezone.utc)-heartbeat["checked_at"]).total_seconds() <= 30)
    rows = await db.fetch_all("SELECT * FROM incident_cases ORDER BY created_at DESC LIMIT 200")
    result = []
    for row in rows:
        stage_rows = await db.fetch_all(
            """SELECT scope->>'jurisdiction' AS jurisdiction,scope->>'stage' AS stage,max(created_at) AS reported_at
               FROM approval_events WHERE kind='incident-report' AND target_kind='incident-stage' AND target_id=%s
               GROUP BY scope->>'jurisdiction',scope->>'stage'""", (str(row["id"]),))
        completed = {(r["jurisdiction"], r["stage"]): r["reported_at"] for r in stage_rows}
        deadlines = incident_pack.deadlines(row["detected_at"], row["jurisdictions"], datetime.now(timezone.utc), assessed_at=row["assessed_at"])
        for stage in deadlines:
            stage["reported_at"] = completed.get((stage["jurisdiction"], stage["stage"]))
            if stage["reported_at"]:
                stage["status"] = "보고 완료"
            elif not timer_available and stage["status"] not in {"수동 확인 필요", "초과"}:
                stage["status"] = "확인 불가"
        result.append({"id": row["id"], "title": row["title"], "started_at": row["started_at"],
                       "detected_at": row["detected_at"], "jurisdictions": row["jurisdictions"], "deadlines": deadlines})
    return {"incidents": jsonable_encoder(result), "timer_status": "정상" if timer_available else "확인 불가"}


async def detail(incident_id: UUID | str) -> dict:
    case = await db.fetch_one("SELECT * FROM incident_cases WHERE id=%s", (incident_id,))
    if not case:
        raise HTTPException(404, "사고 기록이 없습니다.")
    where, params = audit.predicates(server=case["scope"].get("server_id"), principal=case["scope"].get("principal"),
                                     since=case["scope_since"], until=case["scope_until"], event_kind="tools/call")
    clauses = [where]
    params = list(params)
    if case["scope"].get("tool_name"):
        clauses.append("tool_name=%s")
        params.append(case["scope"]["tool_name"])
    query = f"SELECT {audit.PROJECTION} FROM decisions WHERE {' AND '.join(clauses)} ORDER BY id"
    async with db.transaction() as connection:
        await connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        events = list(await (await connection.execute(query, params)).fetchall())
        total = await (await connection.execute(f"SELECT count(*) AS count FROM decisions WHERE {' AND '.join(clauses)}", params)).fetchone()
        verification = await core.verify_audit_chain(connection)
    approval_history = await db.fetch_all(
        """SELECT kind,outcome,target_kind,target_id,actor,reason,created_at FROM approval_events
           WHERE created_at BETWEEN %s AND %s AND (target_kind='incident' AND target_id=%s
              OR target_kind='server' AND target_id=ANY(%s)) ORDER BY id""",
        (case["scope_since"], case["scope_until"], str(case["id"]),
         [case["scope"]["server_id"]] if case["scope"].get("server_id") else []))
    suspensions = await db.fetch_all(
        """SELECT server_id,source,reason,created_at,resumed_at,resumed_by,resume_note FROM ops_suspensions
           WHERE created_at BETWEEN %s AND %s AND (%s IS NULL OR server_id=%s) ORDER BY id""",
        (case["scope_since"], case["scope_until"], case["scope"].get("server_id"), case["scope"].get("server_id")))
    reports = await db.fetch_all(
        """SELECT created_at,actor,scope FROM approval_events WHERE kind='incident-report'
           AND target_kind='incident-stage' AND target_id=%s ORDER BY id""", (str(incident_id),))
    scope_snapshot = {key: value for key, value in case["scope"].items() if key != "principal"}
    if case["scope"].get("principal"):
        scope_snapshot["principal_ref"] = hashlib.sha256(case["scope"]["principal"].encode()).hexdigest()
    evidence_package = incident_pack.seal({
        "schema": "mint-incident-evidence/v1", "incident_id": str(case["id"]),
        "title": case["title"], "started_at": case["started_at"], "detected_at": case["detected_at"],
        "jurisdictions": case["jurisdictions"],
        "created_at": datetime.now(timezone.utc), "scope": {**scope_snapshot, "since": case["scope_since"], "until": case["scope_until"]},
        "query_count": total["count"], "included_count": len(events),
        "count_matches": incident_pack.count_matches(total["count"], len(events)),
        "calls": [clean_row(row) for row in events],
        "chain_verification": verification,
        "approval_and_revocation_history": [{**{key: value for key, value in row.items() if key not in {"actor", "reason"}},
                                             "actor_ref": hashlib.sha256(row["actor"].encode()).hexdigest() if row.get("actor") else None}
                                            for row in approval_history],
        "connection_stop_history": [{key: value for key, value in row.items() if key not in {"reason", "resumed_by", "resume_note"}}
                                    for row in suspensions],
        "jurisdiction_deadlines": incident_pack.deadlines(case["detected_at"], case["jurisdictions"], datetime.now(timezone.utc), assessed_at=case["assessed_at"]),
        "reported_stages": [{"reported_at": row["created_at"], **row["scope"],
                             "actor_ref": hashlib.sha256(row["actor"].encode()).hexdigest() if row.get("actor") else None}
                            for row in reports],
    })
    public_case = {key: value for key, value in case.items() if key not in {"scope", "created_by"}}
    public_case["scope"] = scope_snapshot
    public_case["created_by_ref"] = hashlib.sha256(case["created_by"].encode()).hexdigest()
    return {"incident": jsonable_encoder(public_case), "evidence_package": jsonable_encoder(evidence_package),
            "package_hash_valid": incident_pack.verify_package(jsonable_encoder(evidence_package))}


async def report(incident_id: UUID, jurisdiction: str, stage: str, actor: str, note: str) -> dict:
    case = await db.fetch_one("SELECT jurisdictions FROM incident_cases WHERE id=%s", (incident_id,))
    if not case:
        raise HTTPException(404, "사고 기록이 없습니다.")
    if jurisdiction not in case["jurisdictions"] or (jurisdiction, stage) not in {
        (row["jurisdiction"], row["stage"]) for row in incident_pack.deadlines(datetime.now(timezone.utc), [jurisdiction], datetime.now(timezone.utc), assessed_at=datetime.now(timezone.utc))
    }:
        raise HTTPException(422, "사고의 관할 보고 단계가 아닙니다.")
    await db.execute(
        """INSERT INTO approval_events(kind,outcome,target_kind,target_id,actor,reason,scope)
           VALUES ('incident-report','recorded','incident-stage',%s,%s,%s,%s)""",
        (str(incident_id), actor, note, Jsonb({"incident_id": str(incident_id), "jurisdiction": jurisdiction, "stage": stage})))
    return await detail(incident_id)


async def check_deadlines() -> None:
    await db.execute("INSERT INTO incident_timer_heartbeat(id,checked_at) VALUES (1,now()) ON CONFLICT (id) DO UPDATE SET checked_at=EXCLUDED.checked_at")
    rows = await db.fetch_all("SELECT id,detected_at,assessed_at,jurisdictions FROM incident_cases")
    now = datetime.now(timezone.utc)
    for case in rows:
        completed_rows = await db.fetch_all(
            """SELECT scope->>'jurisdiction' AS jurisdiction,scope->>'stage' AS stage FROM approval_events
               WHERE kind='incident-report' AND target_kind='incident-stage' AND target_id=%s""", (str(case["id"]),))
        completed = {(row["jurisdiction"], row["stage"]) for row in completed_rows}
        deadlines = incident_pack.deadlines(case["detected_at"], case["jurisdictions"], now, assessed_at=case["assessed_at"])
        for deadline in incident_pack.alertable(deadlines, completed):
            await ops_response.emit_alert("incident-deadline", "incident", f"{case['id']}:{deadline['jurisdiction']}:{deadline['stage']}:{deadline['status']}",
                {"incident_id": str(case["id"]), "jurisdiction": deadline["jurisdiction"], "stage": deadline["stage"], "due_at": deadline["due_at"].isoformat(), "status": deadline["status"]})

