"""Human review records of an intake: who approved what, and what had to hold first (D-90..D-92).

Three things live here because the Console API (agent_service) and the Gateway (core, main) both
need the same answer: whether a person may approve a request they did not make, whether an
intake's source and scan evidence are complete and fresh enough to approve, and which tools of a
registration a human has reviewed.
"""
from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from . import db, high_impact, provenance
from .classify import ADDRESS_ARG

SCANNERS = ("Syft", "Trivy", "Semgrep", "Gitleaks")
RISK_ACCEPTANCE_MAX_DAYS = 30
RISK_ACCEPTANCE_MIN_REASON = 10
DESTINATION = re.compile(r"^(\*\.)?[a-z0-9]([a-z0-9.-]*[a-z0-9])?(:\d{1,5})?$")
ARGUMENT = re.compile(r"^[A-Za-z_$][A-Za-z0-9_.$-]{0,63}$")
SERVER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class NotIndependent(PermissionError):
    """The approver is the person who asked."""


async def record_event(kind: str, outcome: str, target_kind: str, target_id: Any, actor: str, *,
                       applicant: str | None = None, reason: str | None = None, scope: dict | None = None,
                       connection=None) -> int:
    query = """INSERT INTO approval_events(kind,outcome,target_kind,target_id,actor,applicant,reason,scope)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id"""
    params = (kind, outcome, target_kind, str(target_id), actor, applicant, reason,
              Jsonb(scope or {}, dumps=lambda value: json.dumps(value, default=str)))
    if connection is None:
        return (await db.fetch_one(query, params))["id"]
    return (await (await connection.execute(query, params)).fetchone())["id"]


async def events_for(target_kind: str, target_id: Any) -> list[dict]:
    return await db.fetch_all(
        """SELECT id, kind, outcome, actor, applicant, reason, scope, created_at FROM approval_events
            WHERE target_kind=%s AND target_id=%s ORDER BY id""", (target_kind, str(target_id)))


async def same_person(first: str | None, second: str | None) -> bool:
    """Two principal tokens that name one person: the same token, or two tokens of one user id."""
    if not first or not second:
        return False
    if first == second:
        return True
    rows = await db.fetch_all("SELECT token, user_id FROM principals WHERE token = ANY(%s::text[])", ([first, second],))
    users = {row["token"]: row["user_id"] for row in rows}
    return bool(users.get(first)) and users.get(first) == users.get(second)


async def require_independent(kind: str, target_kind: str, target_id: Any, actor: str, applicant: str | None,
                              scope: dict | None = None, *, actor_user: str | None = None,
                              applicant_user: str | None = None) -> None:
    """Server-side rule behind every approval: the person who asked cannot be the one who approves.
    The refusal is itself recorded, so an attempt is visible and not only a missing approval.
    Callers that already hold both user ids pass them and save the lookup."""
    if actor == applicant:
        same = True
    elif actor_user and applicant_user:
        same = actor_user == applicant_user
    else:
        same = await same_person(actor, applicant)
    if same:
        await record_event(kind, "refused", target_kind, target_id, actor, applicant=applicant,
                           reason="신청자와 승인자가 같습니다.", scope=scope)
        raise NotIndependent("본인이 신청한 건은 본인이 승인할 수 없습니다. 다른 관리자가 처리해야 합니다.")


SOLO_MODE_SETTING = "ROOT_SOLO_APPROVAL"  # the variable's name only; its value is never written to the ledger


def solo_mode_enabled() -> bool:
    """Whether this deployment is configured for a single root operator."""
    return os.getenv("ROOT_SOLO_APPROVAL") == "1"


def solo_operator(user: dict) -> bool:
    """Mark approvals made by root while the single-operator mode is enabled."""
    return (solo_mode_enabled() and user.get("user_id") == "root"
            and "admin" in (user.get("roles") or ()))


async def record_solo_mode_observation() -> bool:
    """Start-up record of the single-operator setting (D-188). Writes a row only when the observed value
    differs from the last recorded one, so a restart with the same setting adds nothing and a change is
    recorded once. Stores the boolean, never the raw environment value. Returns whether a row was written."""
    observed = solo_mode_enabled()
    async with db.transaction() as connection:
        # Two starts at once must not both see "no row yet" and both write.
        await connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("solo-mode-observation",))
        last = await (await connection.execute(
            """SELECT scope FROM approval_events WHERE kind='solo-mode' AND target_kind='config' AND target_id=%s
               ORDER BY id DESC LIMIT 1""", (SOLO_MODE_SETTING,))).fetchone()
        previous = last["scope"].get("solo_mode") if last else None
        if last is not None and previous == observed:
            return False
        await record_event("solo-mode", "recorded", "config", SOLO_MODE_SETTING, "system",
                           reason="단독 운영 모드 켜짐 관측" if observed else "단독 운영 모드 꺼짐 관측",
                           scope={"solo_mode": observed, "previous_solo_mode": previous,
                                  "observed_at": datetime.now(UTC).isoformat()},
                           connection=connection)
        return True


async def transition(query: str, params: tuple, **event: Any) -> dict | None:
    """A status change and its approval event in one transaction. None when the row was no longer in
    the expected state, in which case nothing is recorded."""
    async with db.transaction() as connection:
        row = await (await connection.execute(query, params)).fetchone()
        if row:
            await record_event(**event, connection=connection)
        return row


# ── intake gate: provenance, freshness, critical findings ───────────────────────

async def intake_reports(row: dict) -> list[dict]:
    return await db.fetch_all(
        """SELECT id, scanner, scanner_version, source_ref, status, critical_count, high_count, medium_count,
                  summary, imported_at, vuln_db_updated_at
             FROM supply_chain_reports WHERE source_ref=%s AND report_path LIKE %s ORDER BY id""",
        (row.get("source_ref"), f"%/intake-{row['id']}-%"))


async def active_acceptance(intake_id: Any, commit: str | None) -> dict | None:
    return await db.fetch_one(
        """SELECT * FROM accepted_risks WHERE intake_id=%s AND commit_sha=%s AND expires_at>now()
              AND revoked_at IS NULL ORDER BY expires_at DESC LIMIT 1""", (intake_id, commit or ""))


async def intake_gate(row: dict, *, verified: bool = False, now: datetime | None = None) -> dict:
    """Why an intake cannot be approved (or registered) yet. `verified` also demands that the
    artifact was compared with the copy in use, which approval does itself and registration re-checks."""
    now = now or datetime.now(UTC)
    blockers: list[dict] = []

    def block(code: str, message: str) -> None:
        blockers.append({"code": code, "message": message})

    remote = row.get("intake_kind") == "remote-endpoint"
    record = row.get("provenance") or {}
    gaps = provenance.missing(record, intake_kind="remote-endpoint" if remote else "repository",
                              source_url=(row.get("endpoint_url") if remote else row.get("repository_url")) or "")
    if gaps:
        block("provenance-missing", "출처 정보 누락: " + ", ".join(gaps))
    elif not remote and record.get("version") != row.get("commit_sha"):
        block("provenance-mismatch", "출처 커밋 불일치")
    check = provenance.verification(record)
    if verified and not remote and check.get("match") is not True:
        block("provenance-unverified", "배포 파일 대조 안 됨")
    gate: dict[str, Any] = {"provenance": {"missing": gaps, "verified": check.get("match") is True},
                            "scanners": [], "vuln_db": None, "critical": None}
    if not remote:
        states = (row.get("evidence") or {}).get("scanners") or {}
        reports = {report["scanner"]: report for report in await intake_reports(row)}
        for name in SCANNERS:
            state, report = (states.get(name.lower()) or {}).get("status"), reports.get(name)
            gate["scanners"].append({"scanner": name, "version": report and report["scanner_version"],
                                     "status": state, "scanned_at": report and report["imported_at"],
                                     "critical_count": report and report["critical_count"],
                                     "high_count": report and report["high_count"]})
            if state != "DONE":
                block("scan-incomplete", f"{name} 검사 미완료")
            elif not report:
                block("scan-report-missing", f"{name} 보고서 없음")
            elif not report["scanner_version"]:
                block("scan-version-missing", f"{name} 버전 없음")
        updated = (reports.get("Trivy") or {}).get("vuln_db_updated_at")
        age = provenance.vuln_db_age(updated, now)
        gate["vuln_db"] = {"updated_at": updated, "age_days": None if age is None else round(age.total_seconds() / 86400, 1),
                           "max_days": provenance.VULN_DB_MAX_AGE.days}
        if "Trivy" in reports and updated is None:
            block("vuln-db-unknown", "취약점 DB 갱신 시각 없음")
        elif age is not None and age > provenance.VULN_DB_MAX_AGE:
            block("vuln-db-stale", f"취약점 DB {age.days}일 전 갱신 (기준 {provenance.VULN_DB_MAX_AGE.days}일)")
        count = sum(int(report["critical_count"]) for report in reports.values())
        ids = sorted({finding["id"] for report in reports.values() for finding in (report["summary"] or {}).get("findings", [])
                      if finding.get("severity") == "CRITICAL"})
        acceptance = await active_acceptance(row["id"], row.get("commit_sha")) if count else None
        covered = bool(acceptance and acceptance["critical_count"] >= count and set(ids) <= set(acceptance["finding_ids"]))
        gate["critical"] = {"count": count, "ids": ids, "covered": covered, "acceptance": acceptance}
        if count and not covered:
            block("critical", f"치명적 발견 {count}건 · 위험 수용 필요")
    gate.update(ok=not blockers, blockers=blockers)
    return gate


async def accept_risk(intake_id: UUID, actor: str, reason: str, days: int) -> dict:
    """An operator accepts the critical findings of one validated commit until expires_at."""
    reason = reason.strip()
    if len(reason) < RISK_ACCEPTANCE_MIN_REASON:
        raise ValueError(f"위험 수용 사유는 {RISK_ACCEPTANCE_MIN_REASON}자 이상이어야 합니다.")
    if not 1 <= days <= RISK_ACCEPTANCE_MAX_DAYS:
        raise ValueError(f"위험 수용 기한은 1~{RISK_ACCEPTANCE_MAX_DAYS}일입니다.")
    row = await db.fetch_one("SELECT * FROM mcp_intake_requests WHERE id=%s", (intake_id,))
    if (not row or row["intake_kind"] != "repository" or row["status"] not in {"HOLD", "VALIDATED"}
            or row["risk_level"] != "CRITICAL" or not row.get("validated_at") or not row.get("commit_sha")):
        raise ValueError("치명적 발견으로 보류된, 검증을 마친 소스 도입 요청만 위험을 수용할 수 있습니다.")
    await require_independent("risk-accept", "intake", intake_id, actor, row["submitted_by"])
    gate = await intake_gate(row)
    if any(item["code"] in {"scan-incomplete", "scan-report-missing"} for item in gate["blockers"]):
        raise ValueError("검사가 모두 끝나지 않은 요청은 위험을 수용할 수 없습니다.")
    critical = gate["critical"]
    expires = datetime.now(UTC) + timedelta(days=days)
    async with db.transaction() as connection:
        accepted = await (await connection.execute(
            """INSERT INTO accepted_risks(intake_id, commit_sha, critical_count, finding_ids, reason, accepted_by, expires_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (intake_id, row["commit_sha"], critical["count"], Jsonb(critical["ids"]), reason, actor, expires))).fetchone()
        await connection.execute(
            """UPDATE mcp_intake_requests SET status='VALIDATED', review_note=%s, updated_at=now()
                WHERE id=%s AND status='HOLD'""", ("위험 수용 기록됨 · 기한 내 승인 가능", intake_id))
        await record_event("risk-accept", "approved", "intake", intake_id, actor, applicant=row["submitted_by"], reason=reason,
                           scope={"commit": row["commit_sha"], "critical": critical["count"], "findings": critical["ids"],
                                  "expires_at": expires.isoformat(timespec="seconds")}, connection=connection)
    return accepted


async def lapse_expired_acceptances() -> list[dict]:
    """A request that rested on an accepted risk goes back to hold when the acceptance runs out."""
    rows = await db.fetch_all(
        """UPDATE mcp_intake_requests r SET status='HOLD', review_note='위험 수용 기한이 지나 재검토가 필요합니다.',
                  updated_at=now()
            WHERE r.status IN ('VALIDATED', 'APPROVED') AND r.risk_level='CRITICAL'
              AND EXISTS (SELECT 1 FROM accepted_risks a WHERE a.intake_id=r.id AND a.commit_sha=r.commit_sha)
              AND NOT EXISTS (SELECT 1 FROM accepted_risks a WHERE a.intake_id=r.id AND a.commit_sha=r.commit_sha
                                 AND a.expires_at>now() AND a.revoked_at IS NULL)
        RETURNING r.id, r.submitted_by, r.registered_server_id""")
    for row in rows:
        await record_event("risk-lapse", "held", "intake", row["id"], "system", applicant=row["submitted_by"],
                           reason="위험 수용 기한 만료", scope={"server": row["registered_server_id"]})
    return rows


# ── per-tool scope review ────────────────────────────────────────────────────────────

def normalize_tool_reviews(tools: dict[str, str], reviews: dict | None, reviewer: str, now: datetime | None = None) -> dict:
    """Each approved tool needs a human-written scope: purpose, asset, action and external destinations."""
    reviews = reviews or {}
    unreviewed = sorted(set(tools) - set(reviews))
    if unreviewed:
        raise ValueError("범위를 심사하지 않은 도구가 있습니다: " + ", ".join(unreviewed))
    extra = sorted(set(reviews) - set(tools))
    if extra:
        raise ValueError("승인하지 않은 도구의 범위 심사입니다: " + ", ".join(extra))
    stamp = (now or datetime.now(UTC)).isoformat(timespec="seconds")
    normalized = {}
    for name, item in sorted(reviews.items()):
        purpose, asset = str(item.get("purpose") or "").strip(), str(item.get("asset") or "").strip()
        if not 4 <= len(purpose) <= 200 or not 2 <= len(asset) <= 200:
            raise ValueError(f"{name}: 목적(4자 이상)과 자산(2자 이상)이 필요합니다.")
        destinations = sorted({str(value).strip().lower() for value in item.get("destinations") or [] if str(value).strip()})
        if len(destinations) > 10 or not all(DESTINATION.fullmatch(value) for value in destinations):
            raise ValueError(f"{name}: 외부 목적지는 호스트 이름 10개 이하로 적으세요.")
        inputs = item.get("inputs")
        if inputs is not None:
            inputs = sorted({str(value) for value in inputs})
            if not all(ARGUMENT.fullmatch(value) for value in inputs):
                raise ValueError(f"{name}: 허용 입력 항목은 인자 이름으로 적으세요.")
        accepts = sorted({str(value).strip() for value in item.get("accepts_from") or [] if str(value).strip()})
        if not all(SERVER.fullmatch(value) for value in accepts):
            raise ValueError(f"{name}: 중요정보를 넘겨받을 서버는 서버 ID로 적으세요.")
        grade = item.get("grade") or "public"
        if grade not in ("public", "nonimportant"):
            raise ValueError(f"{name}: 외부 전송 등급은 공개 또는 일반만 승인할 수 있습니다.")
        normalized[name] = {"purpose": purpose, "asset": asset, "action": tools[name], "destinations": destinations,
                            "inputs": inputs, "mask": bool(item.get("mask")), "grade": grade,
                            "accepts_from": accepts, "consent": bool(item.get("consent")),
                            "reviewed_by": reviewer, "reviewed_at": stamp}
        normalized[name].update(high_impact.normalize(item))
    return normalized


def scope_terms(item: dict) -> dict:
    """What a person agreed to for one tool, without who or when: a change re-opens consent and approvals."""
    return {key: value for key, value in item.items() if key not in ("reviewed_by", "reviewed_at")}


_ADDRESS_ARG = ADDRESS_ARG


def check_inputs(name: str, schema: dict, inputs: list[str]) -> None:
    """POL-31: a reviewer narrows the argument set of the pinned contract; a required argument stays."""
    allowed, advertised = set(inputs), set((schema or {}).get("properties") or {})
    if allowed - advertised:
        raise ValueError(f"{name}: 계약에 없는 입력 항목입니다: " + ", ".join(sorted(allowed - advertised)))
    if missing := set((schema or {}).get("required") or []) - allowed:
        raise ValueError(f"{name}: 필수 입력 항목은 뺄 수 없습니다: " + ", ".join(sorted(missing)))


def derived_constraints(advertised: dict[str, dict], reviews: dict[str, dict]) -> dict[str, dict]:
    """The argument scope a registration gets without anyone writing JSON Schema.

    Each approved tool takes exactly the arguments its pinned contract advertises (no extras), and an
    argument that names an address may only point at the destinations the reviewer listed, over HTTPS.
    That closes the file:, data: and internal-host reads a converter or fetcher would otherwise do.
    """
    out = {}
    for name, item in reviews.items():
        schema = json.loads(json.dumps(advertised[name].get("input_schema") or {}))
        hosts = item.get("destinations") or []
        # No reviewed destination means no address at all: an empty list used to admit any HTTPS host.
        pattern = ("^https://(" + "|".join(re.escape(h) for h in hosts) + r")(:443)?([/?#]|$)" if hosts else "(?!)")

        def pin(node, key=""):
            # Addresses nest: a list of URLs, an object with a url field, a $defs entry, an anyOf branch.
            if not isinstance(node, dict):
                return
            if node.get("type") == "string" and (node.get("format") in ("uri", "url", "iri") or _ADDRESS_ARG.search(key)):
                node["pattern"] = pattern
            for child_key, child in (node.get("properties") or {}).items():
                pin(child, child_key)
            for child in (node.get("$defs") or node.get("definitions") or {}).values():
                pin(child)
            items = node.get("items")
            for child in (items if isinstance(items, list) else [items]):
                pin(child, key)
            for branch in ("anyOf", "oneOf", "allOf"):
                for child in node.get(branch) or []:
                    pin(child, key)

        pin(schema)
        if item.get("inputs") is not None:
            check_inputs(name, schema, item["inputs"])
            schema["properties"] = {k: v for k, v in (schema.get("properties") or {}).items() if k in item["inputs"]}
        # Keep $defs so $ref inside the advertised contract still resolves (DEV-44).
        out[name] = {**{k: v for k, v in schema.items() if k in ("$defs", "definitions", "required", "properties")},
                     "type": "object", "properties": schema.get("properties") or {}, "additionalProperties": False}
    return out


# ── audit annotations: a ledger row that is known to be invalid ───────────────────────

ANNOTATION_MAX_SPAN = 10_000
ANNOTATION_MIN_REASON = 10


async def annotate(first_id: int, last_id: int, reason: str, actor: str) -> dict:
    """Mark decisions first_id..last_id as invalid without touching them: the hash chain stays whole
    and the annotation says, next to the rows, that nobody may count them as evidence."""
    reason = reason.strip()
    if len(reason) < ANNOTATION_MIN_REASON:
        raise ValueError(f"무효 처리 사유는 {ANNOTATION_MIN_REASON}자 이상이어야 합니다.")
    if first_id > last_id or last_id - first_id >= ANNOTATION_MAX_SPAN:
        raise ValueError(f"범위는 시작이 끝보다 작거나 같고 {ANNOTATION_MAX_SPAN}건 미만이어야 합니다.")
    found = await db.fetch_one("SELECT count(*) AS n FROM decisions WHERE id BETWEEN %s AND %s", (first_id, last_id))
    if not found["n"]:
        raise ValueError("이 범위에 판정 기록이 없습니다.")
    try:
        async with db.transaction() as connection:
            row = await (await connection.execute(
                """INSERT INTO audit_annotations(target_kind, first_id, last_id, reason, created_by)
                   VALUES ('decision',%s,%s,%s,%s) RETURNING *""", (first_id, last_id, reason, actor))).fetchone()
            await record_event("audit-annotate", "recorded", "decision", f"{first_id}-{last_id}", actor, reason=reason,
                               scope={"rows": int(found["n"])}, connection=connection)
    except UniqueViolation as exc:
        raise ValueError("같은 범위의 무효 처리가 이미 있습니다.") from exc
    return row


async def annotations(connection=None) -> list[dict]:
    query = "SELECT * FROM audit_annotations ORDER BY id DESC LIMIT 200"
    if connection is None:
        return await db.fetch_all(query)
    return await (await connection.execute(query)).fetchall()


async def mark_invalid(rows: list[dict], key: str = "id", connection=None) -> list[dict]:
    """Adds `invalid` ({reason, by, at} or None) to each ledger row an annotation covers."""
    ids = [int(row[key]) for row in rows if row.get(key) is not None]
    if not ids:
        return rows
    query = """SELECT first_id, last_id, reason, created_by, created_at FROM audit_annotations
                WHERE target_kind='decision' AND first_id<=%s AND last_id>=%s ORDER BY id"""
    params = (max(ids), min(ids))
    covering = (await db.fetch_all(query, params) if connection is None
                else await (await connection.execute(query, params)).fetchall())
    for row in rows:
        row["invalid"] = next(({"reason": item["reason"], "by": item["created_by"], "at": item["created_at"]}
                               for item in covering if item["first_id"] <= int(row[key] or 0) <= item["last_id"]), None)
    return rows
