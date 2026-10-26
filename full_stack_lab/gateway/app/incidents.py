"""Incident records backed by the append-only decision ledger."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import logging
from psycopg.types.json import Jsonb
from uuid import UUID

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder

from . import alert_store, audit, core, db, incident_pack

LOG = logging.getLogger(__name__)

# min/max keeps concurrent supplements from shrinking the immutable initial scope.
CASE_SELECT = """SELECT c.*,
    LEAST(c.scope_since, (SELECT min((e.scope->>'scope_since')::timestamptz) FROM approval_events e
      WHERE e.kind='incident-supplement' AND e.target_kind='incident' AND e.target_id=c.id::text)) AS effective_since,
    GREATEST(c.scope_until, (SELECT max((e.scope->>'scope_until')::timestamptz) FROM approval_events e
      WHERE e.kind='incident-supplement' AND e.target_kind='incident' AND e.target_id=c.id::text)) AS effective_until,
    COALESCE((SELECT (e.scope->>'handled_at')::timestamptz FROM approval_events e
      WHERE e.kind='incident-supplement' AND e.target_kind='incident' AND e.target_id=c.id::text
      AND e.scope->>'handled_at' IS NOT NULL ORDER BY e.id DESC LIMIT 1), c.handled_at) AS effective_handled_at,
    COALESCE((SELECT (e.scope->>'fix_available_at')::timestamptz FROM approval_events e
      WHERE e.kind='incident-supplement' AND e.target_kind='incident' AND e.target_id=c.id::text
      AND e.scope->>'fix_available_at' IS NOT NULL ORDER BY e.id DESC LIMIT 1), c.fix_available_at) AS effective_fix_available_at
    FROM incident_cases c"""


def actor_ref(actor: str | None) -> str | None:
    return hashlib.sha256(actor.encode()).hexdigest() if actor else None


def report_facts(reports: list[dict]) -> list[dict]:
    return [{**row, **row.get("scope", {})} for row in reports]


def case_deadlines(case: dict, now: datetime, reports: list[dict]) -> list[dict]:
    rows = incident_pack.deadlines(case["detected_at"], case["jurisdictions"], now,
        document=case.get("pack_snapshot"), assessed_at=case.get("assessed_at"),
        fix_available_at=case.get("effective_fix_available_at", case.get("fix_available_at")),
        handled_at=case.get("effective_handled_at", case.get("handled_at")),
        incident_type=case.get("incident_type"), reports=report_facts(reports))
    # A stored legacy case lacks frozen rules; partial projections may omit the column entirely.
    if "pack_snapshot" in case and not case["pack_snapshot"]:
        for row in rows:
            row.update(status="수동 확인 필요", due_at=None, remaining_seconds=None, pack_version=None,
                       applicability="수동 확인 필요")
    return rows


def clean_row(row: dict) -> dict:
    value = audit.with_outcome(row)
    actor = value.pop("user_token", "")
    value["actor_ref"] = hashlib.sha256(actor.encode()).hexdigest() if actor else None
    value["reason_ref"] = actor_ref(value.pop("reason", None))
    value["reason_code"] = value.get("policy_id")
    value["policy_version"] = value.get("policy_version")
    invalid = value.get("invalid")
    if invalid:
        value["invalid"] = {"by_ref": actor_ref(invalid["by"]), "at": invalid["at"],
                            "reason_ref": actor_ref(invalid["reason"])}
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
        if started > detected or (assessed and assessed < detected) or since > until:
            raise ValueError("사고·영향 범위의 시각 순서를 확인하세요.")
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc
    scope = {key: data.get(key) for key in ("server_id", "tool_name", "principal") if data.get(key)}
    snapshot = {"schema": "mint-incident-jurisdictions/v1", "packs": [selected[key] for key in jurisdictions]}
    try:
        facts = {key: incident_pack.parse_time(data[key]) if data.get(key) else None
                 for key in ("handled_at", "fix_available_at")}
        if any(value and value > datetime.now(timezone.utc) for value in facts.values()):
            raise ValueError("기산 시각은 미래일 수 없습니다.")
        if facts["handled_at"] and facts["handled_at"] < detected:
            raise ValueError("처리 종료 시각을 확인하세요.")
        if data.get("incident_type") not in {None, "vulnerability", "severe-incident"}:
            raise ValueError("사고 유형을 확인하세요.")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    async with db.transaction() as connection:
        row = await (await connection.execute(
            """INSERT INTO incident_cases(title,started_at,detected_at,assessed_at,scope_since,scope_until,
               scope,jurisdictions,created_by,pack_snapshot,incident_type,handled_at,fix_available_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (data["title"], started, detected, assessed, since, until, Jsonb(scope), jurisdictions, actor,
             Jsonb(snapshot), data.get("incident_type"), facts["handled_at"], facts["fix_available_at"]))).fetchone()
        await connection.execute(
            """INSERT INTO approval_events(kind,outcome,target_kind,target_id,actor,reason,scope)
               VALUES ('incident-created','recorded','incident',%s,%s,%s,%s)""",
            (str(row["id"]), actor, "사고 범위와 관할 기한 기록", Jsonb(scope)))
    return await detail(row["id"])


async def supplement(incident_id: UUID, data: dict, actor: str) -> dict:
    case = await db.fetch_one(CASE_SELECT + " WHERE c.id=%s", (incident_id,))
    if not case:
        raise HTTPException(404, "사고 기록이 없습니다.")
    try:
        since, until = incident_pack.parse_time(data["scope_since"]), incident_pack.parse_time(data["scope_until"])
        if since > until or since > case["effective_since"] or until < case["effective_until"]:
            raise ValueError("영향 범위는 기존 범위를 포함해야 합니다.")
        facts = {"scope_since": since.isoformat(), "scope_until": until.isoformat()}
        for key in ("handled_at", "fix_available_at"):
            if data.get(key):
                value = incident_pack.parse_time(data[key])
                if value > datetime.now(timezone.utc) or (key == "handled_at" and value < case["detected_at"]):
                    raise ValueError("기산 시각을 확인하세요.")
                facts[key] = value.isoformat()
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc
    await db.execute(
        """INSERT INTO approval_events(kind,outcome,target_kind,target_id,actor,scope)
           VALUES ('incident-supplement','recorded','incident',%s,%s,%s)""", (str(incident_id), actor, Jsonb(facts)))
    return await detail(incident_id)


async def list_cases() -> dict:
    heartbeat = await db.fetch_one("SELECT checked_at,last_failed_at FROM incident_timer_heartbeat WHERE id=1")
    timer_available = bool(heartbeat and not heartbeat.get("last_failed_at") and
                           (datetime.now(timezone.utc)-heartbeat["checked_at"]).total_seconds() <= 30)
    rows = await db.fetch_all(CASE_SELECT + " ORDER BY c.created_at DESC LIMIT 200")
    result = []
    for row in rows:
        reports = await db.fetch_all(
            """SELECT created_at,scope FROM approval_events WHERE kind='incident-report'
               AND target_kind='incident-stage' AND target_id=%s ORDER BY id""", (str(row["id"]),))
        completed = {(r["jurisdiction"], r["stage"]): r.get("submitted_at") or r["created_at"] for r in report_facts(reports)}
        deadlines = case_deadlines(row, datetime.now(timezone.utc), reports)
        for stage in deadlines:
            stage["reported_at"] = completed.get((stage["jurisdiction"], stage["stage"]))
            if stage["reported_at"] and stage["status"] != "수동 확인 필요":
                stage["status"] = "보고 완료"
            elif not timer_available and stage["status"] not in {"수동 확인 필요", "초과"}:
                stage["status"] = "확인 불가"
        result.append({"id": row["id"], "title": row["title"], "started_at": row["started_at"],
                       "detected_at": row["detected_at"], "jurisdictions": row["jurisdictions"], "deadlines": deadlines})
    status = "실패" if heartbeat and heartbeat.get("last_failed_at") else "정상" if timer_available else "확인 불가"
    return {"incidents": jsonable_encoder(result), "timer_status": status}


async def detail(incident_id: UUID | str) -> dict:
    case = await db.fetch_one(CASE_SELECT + " WHERE c.id=%s", (incident_id,))
    if not case:
        raise HTTPException(404, "사고 기록이 없습니다.")
    captured_at = datetime.now(timezone.utc)
    since, until = case.get("effective_since", case["scope_since"]), case.get("effective_until", case["scope_until"])
    where, params = audit.predicates(server=case["scope"].get("server_id"), principal=case["scope"].get("principal"),
                                     since=since, until=until, event_kind="tools/call")
    clauses = [where]
    params = list(params)
    if case["scope"].get("tool_name"):
        clauses.append("tool_name=%s")
        params.append(case["scope"]["tool_name"])
    # Same first-covering-annotation semantics as review.mark_invalid, inside the call snapshot.
    query = f"""SELECT {audit.PROJECTION},policy_version,reason,
        (SELECT jsonb_build_object('reason',a.reason,'by',a.created_by,'at',a.created_at)
         FROM audit_annotations a WHERE a.target_kind='decision' AND a.first_id<=decisions.id
         AND a.last_id>=decisions.id ORDER BY a.id LIMIT 1) AS invalid
        FROM decisions WHERE {' AND '.join(clauses)} ORDER BY id"""
    async with db.transaction() as connection:
        await connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        events = list(await (await connection.execute(query, params)).fetchall())
        total = await (await connection.execute(f"SELECT count(*) AS count FROM decisions WHERE {' AND '.join(clauses)}", params)).fetchone()
        verification = await core.verify_audit_chain(connection)
    server_ids = sorted({row["server_id"] for row in events if row.get("server_id")} |
                        ({case["scope"]["server_id"]} if case["scope"].get("server_id") else set()))
    approval_ids = sorted({str(row["approval_id"]) for row in events if row.get("approval_id")})
    approval_history = await db.fetch_all(
        """SELECT kind,outcome,target_kind,target_id,actor,created_at,
                  scope->>'scope_since' AS scope_since,scope->>'scope_until' AS scope_until,
                  scope->>'handled_at' AS handled_at,scope->>'fix_available_at' AS fix_available_at
           FROM approval_events WHERE created_at<=%s AND (
              target_kind='incident' AND target_id=%s OR target_kind='server' AND target_id=ANY(%s::text[])
              OR target_kind='approval' AND target_id=ANY(%s::text[])
              OR target_kind='intake' AND target_id IN
                 (SELECT id::text FROM mcp_intake_requests WHERE registered_server_id=ANY(%s::text[]))) ORDER BY id""",
        (captured_at, str(case["id"]), server_ids, approval_ids, server_ids))
    suspensions = await db.fetch_all(
        """SELECT server_id,source,created_at,resumed_at FROM ops_suspensions
           WHERE created_at<=%s AND (resumed_at IS NULL OR resumed_at>=%s)
             AND server_id=ANY(%s::text[]) ORDER BY id""", (captured_at, since, server_ids))
    reports = await db.fetch_all(
        """SELECT created_at,actor,scope FROM approval_events WHERE kind='incident-report'
           AND target_kind='incident-stage' AND target_id=%s AND created_at<=%s ORDER BY id""", (str(incident_id), captured_at))
    scope_snapshot = {key: value for key, value in case["scope"].items() if key != "principal"}
    if case["scope"].get("principal"):
        scope_snapshot["principal_ref"] = hashlib.sha256(case["scope"]["principal"].encode()).hexdigest()
    calls = [clean_row(row) for row in events]
    invalid_count = sum(bool(row.get("invalid")) for row in calls)
    evidence_package = incident_pack.seal({
        "schema": "mint-incident-evidence/v1", "incident_id": str(case["id"]),
        "title": case["title"], "started_at": case["started_at"], "detected_at": case["detected_at"],
        "jurisdictions": case["jurisdictions"], "pack_snapshot": case.get("pack_snapshot"),
        "incident_type": case.get("incident_type"),
        "created_at": captured_at, "history_until": captured_at, "scope": {**scope_snapshot, "since": since, "until": until},
        "initial_scope": {"since": case["scope_since"], "until": case["scope_until"]},
        "query_count": total["count"], "included_count": len(events), "total_count": len(events),
        "invalid_count": invalid_count, "valid_count": len(events)-invalid_count,
        "count_matches": incident_pack.count_matches(total["count"], len(events)),
        "calls": calls,
        "chain_verification": verification,
        "approval_and_revocation_history": [{**{key: value for key, value in row.items() if key not in {"actor", "reason"}},
                                             "actor_ref": hashlib.sha256(row["actor"].encode()).hexdigest() if row.get("actor") else None}
                                            for row in approval_history],
        "connection_stop_history": [{key: value for key, value in row.items() if key not in {"reason", "resumed_by", "resume_note"}}
                                    for row in suspensions],
        "jurisdiction_deadlines": case_deadlines(case, captured_at, reports),
        "reported_stages": [{"recorded_at": row["created_at"],
                             "reported_at": row["scope"].get("submitted_at") or row["created_at"],
                             **{key: value for key, value in row["scope"].items() if key in {"incident_id", "jurisdiction", "stage"}},
                             "actor_ref": hashlib.sha256(row["actor"].encode()).hexdigest() if row.get("actor") else None}
                            for row in reports],
    })
    public_case = {key: value for key, value in case.items() if key not in {"scope", "created_by"}}
    public_case["scope"] = scope_snapshot
    public_case["created_by_ref"] = hashlib.sha256(case["created_by"].encode()).hexdigest()
    return {"incident": jsonable_encoder(public_case), "evidence_package": jsonable_encoder(evidence_package),
            "package_hash_valid": incident_pack.verify_package(jsonable_encoder(evidence_package))}


async def report(incident_id: UUID, jurisdiction: str, stage: str, actor: str, note: str,
                 submitted_at: datetime | None = None) -> dict:
    case = await db.fetch_one(CASE_SELECT + " WHERE c.id=%s", (incident_id,))
    if not case:
        raise HTTPException(404, "사고 기록이 없습니다.")
    if jurisdiction not in case["jurisdictions"] or (jurisdiction, stage) not in {
        (row["jurisdiction"], row["stage"]) for row in case_deadlines(case, datetime.now(timezone.utc), [])
    }:
        raise HTTPException(422, "사고의 관할 보고 단계가 아닙니다.")
    now = datetime.now(timezone.utc)
    try:
        submitted = incident_pack.parse_time(submitted_at) if submitted_at else now
        if submitted < case["detected_at"] or submitted > now:
            raise ValueError("보고 제출 시각을 확인하세요.")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    await db.execute(
        """INSERT INTO approval_events(kind,outcome,target_kind,target_id,actor,reason,scope)
           VALUES ('incident-report','recorded','incident-stage',%s,%s,%s,%s)""",
        (str(incident_id), actor, note, Jsonb({"incident_id": str(incident_id), "jurisdiction": jurisdiction,
                                           "stage": stage, "submitted_at": submitted.isoformat()})))
    return await detail(incident_id)


async def check_deadlines() -> None:
    failed = False
    try:
        rows = await db.fetch_all(CASE_SELECT)
        now = datetime.now(timezone.utc)
        for case in rows:
            try:
                reports = await db.fetch_all(
                    """SELECT created_at,scope FROM approval_events WHERE kind='incident-report'
                       AND target_kind='incident-stage' AND target_id=%s ORDER BY id""", (str(case["id"]),))
                completed = {(row["jurisdiction"], row["stage"]) for row in report_facts(reports)}
                for deadline in incident_pack.alertable(case_deadlines(case, now, reports), completed):
                    await alert_store.emit_alert("incident-deadline", "incident",
                        f"{case['id']}:{deadline['jurisdiction']}:{deadline['stage']}:{deadline['status']}",
                        {"incident_id": str(case["id"]), "jurisdiction": deadline["jurisdiction"],
                         "stage": deadline["stage"], "due_at": deadline["due_at"].isoformat(), "status": deadline["status"]})
            except Exception:
                failed = True
                LOG.exception("Incident deadline failed for %s", case["id"])
        if failed:
            raise RuntimeError("사고 기한 검사 실패")
        await db.execute("""INSERT INTO incident_timer_heartbeat(id,checked_at,last_failed_at) VALUES (1,now(),NULL)
            ON CONFLICT (id) DO UPDATE SET checked_at=EXCLUDED.checked_at,last_failed_at=NULL""")
    except Exception:
        await db.execute("""INSERT INTO incident_timer_heartbeat(id,checked_at,last_failed_at) VALUES (1,'epoch',now())
            ON CONFLICT (id) DO UPDATE SET last_failed_at=EXCLUDED.last_failed_at""")
        raise
