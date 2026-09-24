"""Ending a usage relationship, and stating on what evidence it has ended.

Implements the judgment procedure of the team's CISC-W'26 paper
「원격 MCP 서비스 종료 시 권한 회수의 구조적 한계 및 종료 판정 기준 제안」 (section 5):

* The unit is the usage relationship: organisation · purpose · provider · allowed
  resources (registry `usage_relationships`). A case is opened per relationship.
* Every revocation target is judged on four criteria:
    C1 population     - enumerated and matched to an action (not UNVERIFIABLE)
    C2 authority      - someone with authority acted and the evidence can be obtained
    C3 continuity     - no gap between the action and propagation being complete
    C4 evidence       - evidence identifies the target's *state* and time and is readable
  C1 and C4 are prerequisites (unmet -> T3), C2 and C3 set the degree (unmet -> T2),
  all four -> T1. The case grade is the lowest target grade.
* Evidence is graded by what it can prove (paper 3.1): an RFC 7009 revocation response
  proves only that a request was processed, so it never satisfies C4 on its own;
  introspection proves the authorization server's view; a denial at the Gateway proves
  this organisation's enforced path; a credential check in the downstream system proves
  the server-held credential is gone.

The Gateway is the paper's 5.2 mitigation: it recorded, from the start, which
principals used the relationship, so C1's population and C4's evidence for the
organisation's side are collected here without asking the provider.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from psycopg.types.json import Jsonb

from . import db

SLA_DAYS = int(os.getenv("TERMINATION_SLA_DAYS", "14"))
GITEA_ADMIN_URL = os.getenv("GITEA_ADMIN_URL", "http://corp-git:3000").rstrip("/")
GITEA_ADMIN_USER = os.getenv("GITEA_ADMIN_USER", "corpadmin")
GITEA_ADMIN_PASSWORD = os.getenv("GITEA_ADMIN_PASSWORD", "corp-admin-lab-only")

EXIT_TERMS = {
    "provider_credential_disclosure": "제공자가 하위 시스템에 대해 보유한 위임 자격을 고지한다",
    "revocation_evidence": "폐기 처리 결과를 대상·시점이 특정된 기록으로 제출한다",
    "audit_access_retained": "이용 종료 후 합의 기간 동안 감사 기록에 접근할 수 있다",
}
GRADE_LABEL = {"T1": "종료", "T2": "부분 종료", "T3": "판단 불가"}
GRADE_RANK = {"T1": 1, "T2": 2, "T3": 3}
CRITERION_LABEL = {
    "C1": "모집단 — 회수 대상을 빠짐없이 열거하고 조치 대상과 대조하였는가",
    "C2": "수행 권한 — 조치 권한이 있고 증거를 제출받을 수 있는가",
    "C3": "연속성 — 조치부터 전파 완료까지 공백 구간이 없는가",
    "C4": "증거 접근 — 증거가 대상·시점을 특정하며 열람 가능한가",
}

# What each kind of evidence can prove. `state` = it identifies the target's state
# (not only that someone did something), which is what C4 requires.
EVIDENCE_KINDS: dict[str, dict] = {
    "gateway-denial": {"label": "게이트웨이 차단 확인", "state": True,
                       "proves": "조직의 강제 경로가 이 주체의 호출을 실행 전에 막았다",
                       "not_proves": "강제 경로 밖의 다른 경로"},
    "introspection": {"label": "토큰 조사 응답(RFC 7662)", "state": True,
                      "proves": "인가 서버가 판단하는 토큰의 활성 상태",
                      "not_proves": "자원 서버가 그 상태를 반영해 차단하는지"},
    "credential-check": {"label": "하위 시스템 자격 확인", "state": True,
                         "proves": "하위 시스템에 그 자격이 더 이상 존재하지 않는다",
                         "not_proves": "이미 복제·발급된 다른 자격"},
    "provider-attestation": {"label": "제공자 폐기 증명", "state": True,
                             "proves": "제공자가 대상·시점을 특정해 회수를 진술했다",
                             "not_proves": "진술의 진위(제3자 검증이 아님)"},
    "endpoint-inventory": {"label": "단말 설정 보고", "state": True,
                           "proves": "보고 시점에 단말 설정에서 항목이 사라졌다",
                           "not_proves": "보고 이후 재설치"},
    "revocation-response": {"label": "폐기 요청 응답(RFC 7009)", "state": False,
                            "proves": "폐기 요청이 처리되었다",
                            "not_proves": "대상이 그 시점에 유효했는지 — 200은 무효 토큰에도 반환된다"},
    "liveness-probe": {"label": "endpoint 도달 확인", "state": False,
                       "proves": "그 주소가 응답하는지",
                       "not_proves": "조직의 자격이 아직 유효한지(다른 고객에게 계속 서비스할 수 있다)"},
    "session-termination": {"label": "세션 종료 요청 응답(E2)", "state": False,
                            "proves": "세션 종료 요청에 서버가 보인 응답",
                            "not_proves": "세션·토큰의 소멸 — 405면 소멸 시점은 서버 정책에 달렸다"},
    "operator-statement": {"label": "담당자 진술", "state": False,
                           "proves": "담당자가 조치했다고 진술했다", "not_proves": "대상의 상태"},
}
# Which state evidence speaks to which kind of target.
STATE_EVIDENCE_FOR = {
    "gateway-route": {"gateway-denial"},
    "gateway-access": {"gateway-denial"},
    "server-held-credential": {"credential-check", "provider-attestation"},
    "endpoint-config": {"endpoint-inventory"},
    "client-token": {"introspection", "credential-check", "provider-attestation"},
    "refresh-token": {"introspection", "credential-check", "provider-attestation"},
}
DEFAULT_STATE_EVIDENCE = {"introspection", "credential-check", "provider-attestation"}


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def _row(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: _row(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_row(item) for item in value]
    return value


async def _server(server_id: str) -> dict:
    row = await db.fetch_one("SELECT * FROM mcp_servers WHERE id=%s", (server_id,))
    if not row:
        raise ValueError(f"등록되지 않은 서버입니다: {server_id}")
    return dict(row)


async def _case(case_id: str) -> dict:
    row = await db.fetch_one("SELECT * FROM termination_cases WHERE id=%s", (case_id,))
    if not row:
        raise ValueError("존재하지 않는 종료 케이스입니다.")
    return dict(row)


def _is_provider(server: dict) -> bool:
    return (server.get("deployment") or "internal") == "provider"


# ── relationships and readiness ─────────────────────────────────────────────
async def relationships() -> list[dict]:
    rows = await db.fetch_all(
        """SELECT u.*, s.display_name, s.deployment, s.lifecycle, s.status AS server_status,
                  s.exit_terms, s.server_held_credentials, s.supplier,
                  (SELECT count(DISTINCT d.user_token) FROM decisions d WHERE d.server_id=u.server_id
                     AND d.upstream_executed) AS users,
                  (SELECT count(*) FROM decisions d WHERE d.server_id=u.server_id AND d.upstream_executed) AS calls,
                  (SELECT id FROM termination_cases c WHERE c.relationship_id=u.id
                     ORDER BY opened_at DESC LIMIT 1) AS latest_case
             FROM usage_relationships u JOIN mcp_servers s ON s.id=u.server_id ORDER BY u.id""")
    out = []
    for row in rows:
        item = dict(row)
        item["readiness"] = await drill(row["server_id"])
        out.append(_row(item))
    return out


async def drill(server_id: str) -> dict:
    """What would ending this relationship look like - without ending it.

    The answer is the *best attainable* grade given the contract and what the
    organisation can verify itself. A provider that holds credentials it was never
    obliged to disclose caps the relationship at T3 before termination even starts;
    paper 5.2: that evidence cannot be obtained retroactively.
    """
    server = await _server(server_id)
    provider = _is_provider(server)
    terms = server.get("exit_terms") or {}
    creds = server.get("server_held_credentials") or []
    disclosed = bool(terms.get("provider_credential_disclosure")) and bool(creds)
    records = bool(terms.get("revocation_evidence"))
    org_verifiable = all(c.get("verify") for c in creds) if creds else False
    callers = await db.fetch_all(
        """SELECT d.user_token, p.display_name, p.department, count(*) AS calls, max(d.created_at) AS last_call
             FROM decisions d LEFT JOIN principals p ON p.token = d.user_token
            WHERE d.server_id = %s AND d.upstream_executed
            GROUP BY d.user_token, p.display_name, p.department ORDER BY calls DESC""", (server_id,))
    residue = await db.fetch_all(
        """SELECT a.hostname, i.config_path, i.server_label, i.classification
             FROM endpoint_inventory i JOIN endpoint_agents a USING (endpoint_id)
            WHERE i.registry_match=%s""", (server_id,))
    blockers = []
    if provider and not disclosed:
        blockers.append("제공자가 하위 시스템에 보유한 자격의 고지가 계약에 없습니다 → 회수 대상 모집단을 열거할 수 없어 C1이 성립하지 않습니다.")
    if provider and disclosed and not (records or org_verifiable):
        blockers.append("고지된 자격의 폐기를 확인할 수단(폐기 기록 제출 또는 조직의 직접 확인)이 없습니다 → C2·C3을 입증할 수 없습니다.")
    ceiling = "T3" if provider and not disclosed else ("T2" if provider and not (records or org_verifiable) else "T1")
    return _row({
        "server_id": server_id, "display_name": server["display_name"], "provider_operated": provider,
        "supplier": server.get("supplier"), "lifecycle": server.get("lifecycle"), "exit_terms": terms,
        "server_held_credentials": creds, "org_can_verify_credentials": org_verifiable,
        "best_attainable_grade": ceiling, "best_attainable_label": GRADE_LABEL[ceiling],
        "blockers": blockers, "active_users": [dict(r) for r in callers],
        "would_revoke": {"gateway_access": len(callers), "endpoint_configs": len(residue),
                         "server_held": len(creds) if disclosed else (1 if provider else 0)},
        "endpoint_residue": [dict(r) for r in residue],
        "note": "드릴은 아무것도 차단하지 않습니다. 종료를 시작하려면 케이스를 여세요.",
    })


# ── case lifecycle ───────────────────────────────────────────────────────────
async def open_case(target: str, reason: str, opened_by: str, engagement_label: str | None = None) -> dict:
    """Start termination. The cutover (the Gateway refusing every call of this
    relationship) happens first: revoking first and blocking later would open exactly
    the window C3 counts."""
    rel = await db.fetch_one("SELECT * FROM usage_relationships WHERE id=%s", (target,))
    server_id = rel["server_id"] if rel else target
    if not rel:
        rel = await db.fetch_one("SELECT * FROM usage_relationships WHERE server_id=%s ORDER BY id LIMIT 1", (server_id,))
    server = await _server(server_id)
    if server.get("lifecycle", "OPERATING") != "OPERATING":
        raise ValueError("이미 종료 절차가 진행 중이거나 폐기된 서버입니다.")
    live = await db.fetch_one(
        "SELECT id FROM termination_cases WHERE server_id=%s AND status IN ('OPEN','REVOKING','ASSESSED','REOPENED')",
        (server_id,))
    if live:
        raise ValueError("이 서버에 진행 중인 종료 케이스가 이미 있습니다.")
    case_id = str(uuid.uuid4())
    cutover = _now()
    allowed = rel["allowed_resources"] if rel else [
        dict(r) for r in await db.fetch_all("SELECT name, action FROM mcp_tools WHERE server_id=%s AND enabled ORDER BY name", (server_id,))]
    label = engagement_label or (f"{rel['purpose']} · {rel['provider']}" if rel else f"{server['display_name']} · {server['supplier']}")
    async with db.transaction() as connection:
        await connection.execute(
            """INSERT INTO termination_cases(id, server_id, relationship_id, engagement_label, provider,
                 allowed_resources, reason, status, cutover_at, opened_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s,'OPEN',%s,%s)""",
            (case_id, server_id, rel["id"] if rel else None, label,
             rel["provider"] if rel else server["supplier"], Jsonb(allowed), reason, cutover, opened_by))
        await connection.execute(
            """UPDATE mcp_servers SET lifecycle='TERMINATING', lifecycle_changed_at=%s,
                 lifecycle_changed_by=%s, termination_case_id=%s WHERE id=%s""",
            (cutover, opened_by, case_id, server_id))
        if rel:
            await connection.execute("UPDATE usage_relationships SET status='TERMINATING' WHERE id=%s", (rel["id"],))
    try:
        await seed_targets(case_id, opened_by)
    except Exception:
        # A half-opened case would leave the server cut over with no population to
        # judge. Undo both and let the caller see the error.
        await db.execute("DELETE FROM termination_cases WHERE id=%s", (case_id,))
        await db.execute(
            "UPDATE mcp_servers SET lifecycle='OPERATING', termination_case_id=NULL WHERE id=%s", (server_id,))
        if rel:
            await db.execute("UPDATE usage_relationships SET status='ACTIVE' WHERE id=%s", (rel["id"],))
        raise
    return await case_detail(case_id)


async def seed_targets(case_id: str, actor: str) -> list[dict]:
    """Fill the population with everything the organisation can enumerate itself,
    and make the part only the provider knows visible as a gap."""
    case = await _case(case_id)
    server = await _server(case["server_id"])
    created = [await add_target(
        case_id, "gateway-route", f"{server['display_name']} 로 가는 조직의 강제 경로(Gateway)",
        "org", "gateway-ledger", actor, note="차단 시작과 동시에 MCP-DECOMM-001로 막힌다", invalidate=False,
        subject_ref=f"route:{server['id']}", verification="gateway-probe")]
    callers = await db.fetch_all(
        """SELECT DISTINCT d.user_token, p.display_name, p.department
             FROM decisions d LEFT JOIN principals p ON p.token = d.user_token
            WHERE d.server_id = %s AND d.created_at < %s AND d.user_token <> 'unknown'""",
        (case["server_id"], case["cutover_at"]))
    for row in callers:
        created.append(await add_target(
            case_id, "gateway-access",
            f"{row['display_name'] or row['user_token']}({row['department'] or '-'})의 이 이용 관계 접근",
            "org", "gateway-ledger", actor, invalidate=False, subject_ref=row["user_token"],
            verification="gateway-probe",
            note="Gateway 원장이 개시 시점부터 기록한 이용 주체(논문 5.2)"))
    residue = await db.fetch_all(
        """SELECT i.endpoint_id, i.config_path, i.server_label, i.fingerprint, a.hostname
             FROM endpoint_inventory i JOIN endpoint_agents a USING (endpoint_id)
            WHERE i.registry_match=%s""", (case["server_id"],))
    for row in residue:
        created.append(await add_target(
            case_id, "endpoint-config", f"{row['hostname']} · {row['config_path']} 의 '{row['server_label']}' 항목",
            "endpoint", "endpoint-agent", actor, invalidate=False, subject_ref=row["fingerprint"],
            verification="endpoint-report", note="엔드포인트 평면이 보고한 클라이언트 설정 잔존"))
    if _is_provider(server):
        terms = server.get("exit_terms") or {}
        creds = server.get("server_held_credentials") or []
        if terms.get("provider_credential_disclosure") and creds:
            for cred in creds:
                created.append(await add_target(
                    case_id, "server-held-credential", cred["label"], "provider", "provider-disclosure", actor,
                    invalidate=False, subject_ref=json.dumps(cred, ensure_ascii=False),
                    verification=cred.get("verify") or "provider-attestation",
                    note=f"제공자 고지 · 하위 시스템 {cred.get('system')} · 조직 확인 방법 {cred.get('verify') or '없음'}"))
        else:
            created.append(await add_target(
                case_id, "server-held-credential",
                f"{server['supplier']} 가 하위 시스템에 대해 보유한 위임 자격(고지 없음)", "provider",
                "operator-manual", actor, status="UNVERIFIABLE", invalidate=False,
                note="제공자가 보유 자격을 고지하기 전에는 존재 여부조차 열거할 수 없습니다(논문 3.2)."))
    return created


async def add_target(case_id: str, kind: str, label: str, holder: str, discovered_by: str, actor: str,
                     status: str = "OUTSTANDING", note: str | None = None, invalidate: bool = True,
                     subject_ref: str | None = None, verification: str | None = None,
                     expires_at: datetime | None = None) -> dict:
    case = await _case(case_id)
    if case["status"] == "CLOSED":
        raise ValueError("종결된 케이스에는 회수 대상을 추가할 수 없습니다.")
    target_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO revocation_targets(id, case_id, kind, label, holder, discovered_by, status, note,
             subject_ref, verification, expires_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (target_id, case_id, kind, label, holder, discovered_by, status, note, subject_ref, verification, expires_at))
    if invalidate:
        await _invalidate(case_id, actor, f"회수 대상 추가: {label}")
    return dict(await db.fetch_one("SELECT * FROM revocation_targets WHERE id=%s", (target_id,)))


async def revoke_target(target_id: str, actor: str, status: str, note: str | None = None,
                        at: datetime | None = None) -> dict:
    """Record the revocation. `at` is when the action actually took effect (the cutover
    for the Gateway's own paths, the observation for a change seen at an endpoint or a
    downstream system); C4 accepts only evidence observed at or after it."""
    if status not in {"REVOKED", "EXPIRED", "UNVERIFIABLE", "OUTSTANDING"}:
        raise ValueError("알 수 없는 회수 상태입니다.")
    target = await db.fetch_one("SELECT * FROM revocation_targets WHERE id=%s", (target_id,))
    if not target:
        raise ValueError("존재하지 않는 회수 대상입니다.")
    revoked_at = (target["revoked_at"] or at or _now()) if status in {"REVOKED", "EXPIRED"} else None
    await db.execute(
        """UPDATE revocation_targets SET status=%s, revoked_at=%s, revoked_by=%s, note=COALESCE(%s, note)
           WHERE id=%s""",
        (status, revoked_at, actor if revoked_at else None, note, target_id))
    await _invalidate(str(target["case_id"]), actor, f"회수 상태 변경: {target['label']} → {status}")
    return dict(await db.fetch_one("SELECT * FROM revocation_targets WHERE id=%s", (target_id,)))


async def add_evidence(case_id: str, kind: str, subject: str, source: str, detail: dict, actor: str,
                       observed_at: datetime | None = None, target_id: str | None = None) -> dict:
    """Evidence without a subject and a time is not evidence (paper 3.1). The content
    hash lets a later reader tell whether an attached value was changed."""
    await _case(case_id)
    if kind not in EVIDENCE_KINDS:
        raise ValueError("알 수 없는 증거 종류입니다.")
    if not subject.strip():
        raise ValueError("증거가 특정하는 대상을 적어야 합니다.")
    evidence_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO termination_evidence(id, case_id, target_id, kind, subject, observed_at, source, detail,
             sha256, recorded_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (evidence_id, case_id, target_id, kind, subject.strip(), observed_at or _now(), source,
         Jsonb(detail), _digest({"kind": kind, "subject": subject, "detail": detail}), actor))
    await _invalidate(case_id, actor, f"증거 추가: {EVIDENCE_KINDS[kind]['label']} · {subject}")
    return dict(await db.fetch_one("SELECT * FROM termination_evidence WHERE id=%s", (evidence_id,)))


async def _invalidate(case_id: str, actor: str, note: str) -> None:
    """New facts make the last judgment stale; a stale grade is worse than none."""
    await db.execute(
        """UPDATE termination_cases
              SET status = CASE WHEN status='ASSESSED' THEN 'REVOKING' WHEN status='OPEN' THEN 'REVOKING' ELSE status END,
                  grade = CASE WHEN status='ASSESSED' THEN NULL ELSE grade END,
                  criteria = CASE WHEN status='ASSESSED' THEN jsonb_build_object('stale_note', %s::text) ELSE criteria END
            WHERE id=%s AND status IN ('OPEN','REVOKING','ASSESSED','REOPENED')""",
        (f"{note} (기록자 {actor})", case_id))


# ── automated evidence collection ────────────────────────────────────────────
SAMPLE_ARGUMENTS = {"repo_path": "/repos/handbook", "url": "http://intranet.bob.local/", "path": "/shared/public",
                    "owner": "bob", "repo": "handbook", "key": "cache:product:1", "sql": "SELECT 1"}


async def _probe_call(server_id: str) -> tuple[str, dict]:
    """A harmless, schema-valid call for this server, so the Gateway reaches its
    policy decision (and does not stop earlier on an invalid argument)."""
    rows = await db.fetch_all(
        "SELECT name, input_schema FROM mcp_tools WHERE server_id=%s AND enabled AND action='r' AND input_schema IS NOT NULL ORDER BY name",
        (server_id,))
    best = None
    for row in rows:
        required = (row["input_schema"] or {}).get("required") or []
        if not required:
            return row["name"], {}
        if all(name in SAMPLE_ARGUMENTS for name in required) and best is None:
            best = (row["name"], {name: SAMPLE_ARGUMENTS[name] for name in required})
    if best:
        return best
    raise ValueError("차단 확인에 쓸 수 있는 읽기 도구가 없습니다.")


async def collect(case_id: str, kinds: list[str], actor: str) -> dict:
    """Collect state evidence the organisation can obtain on its own."""
    case = await _case(case_id)
    if case["status"] == "CLOSED":
        raise ValueError("종결된 케이스에는 증거를 추가하지 않습니다.")
    server = await _server(case["server_id"])
    targets = [dict(t) for t in await db.fetch_all("SELECT * FROM revocation_targets WHERE case_id=%s ORDER BY created_at", (case_id,))]
    collected: list[dict] = []
    if "gateway" in kinds:
        if server.get("lifecycle") not in {"TERMINATING", "RETIRED"}:
            raise ValueError("차단이 시작되지 않은 서버에는 차단 확인을 보내지 않습니다.")
        from .core import execute_call
        tool, arguments = await _probe_call(server["id"])
        for target in targets:
            if target["kind"] not in {"gateway-route", "gateway-access"}:
                continue
            principal = target["subject_ref"] if target["kind"] == "gateway-access" else actor
            outcome = await execute_call({"server_id": server["id"], "tool": tool, "arguments": arguments,
                                          "user_token": principal,
                                          "client": {"agent": "termination-probe", "task_id": case_id}})
            blocked = outcome["decision"] == "Block" and not outcome["upstream_executed"]
            detail = {"decision_id": outcome["decision_id"], "decision": outcome["decision"],
                      "policy_id": outcome["policy_id"], "tool": tool, "principal": principal, "blocked": blocked}
            collected.append(await add_evidence(case_id, "gateway-denial", f"{principal} → {server['id']}.{tool}",
                                                "gateway", detail, actor, target_id=str(target["id"])))
            if blocked and outcome["policy_id"] == "MCP-DECOMM-001" and target["status"] == "OUTSTANDING":
                await revoke_target(str(target["id"]), actor, "REVOKED", "Gateway가 이 경로를 실행 전에 차단함을 확인",
                                    at=case["cutover_at"])
    if "endpoint" in kinds:
        for target in targets:
            if target["kind"] != "endpoint-config":
                continue
            still = await db.fetch_one("SELECT reported_at FROM endpoint_inventory WHERE fingerprint=%s", (target["subject_ref"],))
            detail = {"fingerprint": target["subject_ref"], "absent": still is None,
                      "last_report": still["reported_at"].isoformat() if still else None}
            evidence = await add_evidence(case_id, "endpoint-inventory", target["label"], "endpoint-agent",
                                          detail, actor, target_id=str(target["id"]))
            collected.append(evidence)
            if still is None and target["status"] == "OUTSTANDING":
                await revoke_target(str(target["id"]), actor, "REVOKED", "단말 보고에서 항목이 사라짐",
                                    at=evidence["observed_at"])
    if "credentials" in kinds:
        for target in targets:
            if target["kind"] != "server-held-credential" or target["verification"] != "gitea-token":
                continue
            cred = json.loads(target["subject_ref"])
            present, status_code = await _gitea_token_present(cred["account"], cred["token_name"])
            detail = {"system": cred.get("system"), "account": cred["account"], "token_name": cred["token_name"],
                      "present": present, "http_status": status_code, "checked_as": GITEA_ADMIN_USER}
            evidence = await add_evidence(case_id, "credential-check", cred["label"], "corp-git admin API",
                                          detail, actor, target_id=str(target["id"]))
            collected.append(evidence)
            if present is False and target["status"] == "OUTSTANDING":
                await revoke_target(str(target["id"]), actor, "REVOKED", "하위 시스템에서 자격이 사라진 것을 확인",
                                    at=evidence["observed_at"])
    if "liveness" in kinds and server.get("endpoint"):
        detail: dict[str, Any] = {"endpoint": server["endpoint"], "method": "HEAD"}
        try:
            async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
                response = await client.head(server["endpoint"])
            detail.update({"reachable": True, "status_code": response.status_code})
        except Exception as exc:
            detail.update({"reachable": False, "error": str(exc)[:200]})
        collected.append(await add_evidence(case_id, "liveness-probe", f"{server['display_name']} endpoint",
                                            "gateway", detail, actor))
    if "session" in kinds and server.get("endpoint"):
        from .experiments import session_termination
        detail = await session_termination(server["endpoint"])
        collected.append(await add_evidence(case_id, "session-termination", f"{server['display_name']} 세션 종료 요청",
                                            "gateway", detail, actor))
    return {"collected": [_row(dict(e)) for e in collected], "case": await case_detail(case_id)}


async def probe(case_id: str, actor: str) -> dict:
    """Kept for the v1 API: reachability only."""
    result = await collect(case_id, ["liveness"], actor)
    evidence = result["collected"][0] if result["collected"] else {}
    return {"evidence": evidence, "reachable": (evidence.get("detail") or {}).get("reachable")}


def _gitea_headers(sudo: str | None = None) -> dict:
    token = base64.b64encode(f"{GITEA_ADMIN_USER}:{GITEA_ADMIN_PASSWORD}".encode()).decode()
    headers = {"Authorization": f"Basic {token}"}
    if sudo:
        headers["Sudo"] = sudo
    return headers


async def _gitea_token_present(account: str, token_name: str) -> tuple[bool | None, int]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{GITEA_ADMIN_URL}/api/v1/users/{account}/tokens",
                                        headers=_gitea_headers(sudo=account))
        if response.status_code != 200:
            return None, response.status_code
        return any(t.get("name") == token_name for t in response.json()), 200
    except httpx.HTTPError:
        return None, 0


async def revoke_credential(target_id: str, actor: str) -> dict:
    """The organisation exercises its own authority over a disclosed server-held
    credential because it owns the downstream system (here: Gitea admin). This is
    the C2 route that does not depend on the provider's cooperation."""
    target = await db.fetch_one("SELECT * FROM revocation_targets WHERE id=%s", (target_id,))
    if not target or target["kind"] != "server-held-credential" or target["verification"] != "gitea-token":
        raise ValueError("조직이 직접 회수할 수 있는 하위 자격이 아닙니다.")
    cred = json.loads(target["subject_ref"])
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.delete(
            f"{GITEA_ADMIN_URL}/api/v1/users/{cred['account']}/tokens/{cred['token_name']}",
            headers=_gitea_headers(sudo=cred["account"]))
    case_id = str(target["case_id"])
    await add_evidence(case_id, "revocation-response", cred["label"], "corp-git admin API",
                       {"http_status": response.status_code, "method": "DELETE", "account": cred["account"],
                        "token_name": cred["token_name"]}, actor, target_id=target_id)
    if response.status_code in (204, 404):
        await revoke_target(target_id, actor, "REVOKED", "조직이 하위 시스템 관리자 권한으로 폐기")
    # The deletion response proves only that the request was processed; check state.
    return await collect(case_id, ["credentials"], actor)


# ── judgment ─────────────────────────────────────────────────────────────────
async def _post_cutover(case: dict, principal: str | None = None) -> dict:
    """What happened on this relationship after the cutover - C3's direct evidence."""
    params: list[Any] = [case["server_id"], case["cutover_at"]]
    extra = ""
    if principal:
        extra = " AND user_token = %s"
        params.append(principal)
    row = await db.fetch_one(
        f"""SELECT count(*) FILTER (WHERE upstream_executed) AS executed,
                   count(*) FILTER (WHERE NOT upstream_executed AND NOT COALESCE(upstream_attempted, false)) AS blocked,
                   count(*) FILTER (WHERE NOT upstream_executed AND COALESCE(upstream_attempted, false)) AS unknown,
                   max(created_at) AS last_attempt
              FROM decisions WHERE server_id = %s AND created_at >= %s{extra}""", tuple(params))
    return {"executed": int(row["executed"] or 0), "blocked": int(row["blocked"] or 0),
            "unknown": int(row["unknown"] or 0),
            "last_attempt": row["last_attempt"].isoformat() if row["last_attempt"] else None}


def _judge_target(target: dict, evidence: list[dict], activity: dict, provider_can_verify: bool) -> dict:
    """C1-C4 for one revocation target.

    C4 asks whether the evidence identifies the target's *state* and time - which a
    check showing "the credential still exists" does as much as one showing it gone.
    That is what makes T2 possible: the residual is known, so its upper bound can be
    set. Whether the state is "revoked" is C2's and C3's question.
    """
    kind = target["kind"]
    status = target["status"]
    revoked_at = target.get("revoked_at")
    state_kinds = STATE_EVIDENCE_FOR.get(kind, DEFAULT_STATE_EVIDENCE)
    state_evidence = [e for e in evidence
                      if e["kind"] in state_kinds and EVIDENCE_KINDS[e["kind"]]["state"]
                      and (not revoked_at or e["observed_at"] >= revoked_at)]
    confirmed = [e for e in state_evidence if _evidence_shows_revoked(e)]
    # C1
    c1_gaps = ["대상의 존재·범위를 열거할 수 없습니다."] if status == "UNVERIFIABLE" else []
    # C4
    c4_gaps = []
    if not state_evidence:
        weak = sorted({EVIDENCE_KINDS[e["kind"]]["label"] for e in evidence if not EVIDENCE_KINDS[e["kind"]]["state"]})
        c4_gaps.append("대상의 상태를 특정하는 증거가 없습니다."
                       + (f" ({', '.join(weak)}은(는) 요청 처리만 증명)" if weak else ""))
    # C2
    c2_gaps = []
    if status not in {"REVOKED", "EXPIRED"}:
        c2_gaps.append("아직 회수 조치가 기록되지 않았습니다." if target["holder"] != "provider"
                       else "제공자만 회수할 수 있는 자격이며 아직 회수되지 않았습니다.")
    elif target["holder"] == "provider":
        attested = any(e["kind"] == "provider-attestation" for e in confirmed)
        org_checked = provider_can_verify and any(e["kind"] == "credential-check" for e in confirmed)
        if not (attested or org_checked):
            c2_gaps.append("제공자 보유 자격의 회수를 제공자 증명이나 조직의 직접 확인으로 입증하지 못했습니다.")
    # C3
    c3_gaps = []
    if kind in {"gateway-route", "gateway-access"}:
        if activity["executed"]:
            c3_gaps.append(f"차단 이후에도 실행된 호출이 {activity['executed']}건 있습니다.")
        if activity["unknown"]:
            c3_gaps.append(f"실행 여부 미확인 호출이 {activity['unknown']}건 있습니다.")
    if target.get("verification") == "stateless" and target.get("expires_at") and revoked_at:
        gap = (target["expires_at"] - revoked_at).total_seconds()
        if gap > 0:
            c3_gaps.append(f"상태 비저장 토큰이라 폐기 후 만료까지 {int(gap)}초 동안 자원 접근이 가능했습니다(E1).")
    if status in {"REVOKED", "EXPIRED"} and not confirmed and not c3_gaps:
        c3_gaps.append("조치 이후 대상이 무효가 되었음을 확인한 기록이 없습니다(전파 완료 미확인).")
    if status not in {"REVOKED", "EXPIRED"} and not c3_gaps:
        c3_gaps.append("회수 전이라 전파를 판단할 수 없습니다.")
    crit = {"C1": {"met": not c1_gaps, "gaps": c1_gaps}, "C2": {"met": not c2_gaps, "gaps": c2_gaps},
            "C3": {"met": not c3_gaps, "gaps": c3_gaps}, "C4": {"met": not c4_gaps, "gaps": c4_gaps}}
    if not crit["C1"]["met"] or not crit["C4"]["met"]:
        grade = "T3"
    elif not crit["C2"]["met"] or not crit["C3"]["met"]:
        grade = "T2"
    else:
        grade = "T1"
    return {"criteria": crit, "grade": grade, "evidence_used": [str(e["id"]) for e in state_evidence]}


def _evidence_shows_revoked(evidence: dict) -> bool:
    detail = evidence.get("detail") or {}
    kind = evidence["kind"]
    if kind == "gateway-denial":
        return bool(detail.get("blocked"))
    if kind == "introspection":
        return detail.get("active") is False
    if kind == "credential-check":
        return detail.get("present") is False or detail.get("valid") is False
    if kind == "endpoint-inventory":
        return bool(detail.get("absent"))
    return kind == "provider-attestation"


async def assess(case_id: str, actor: str) -> dict:
    case = await _case(case_id)
    if case["status"] == "CLOSED":
        raise ValueError("종결된 케이스는 다시 판정하지 않습니다. 재개한 뒤 판정하세요.")
    server = await _server(case["server_id"])
    targets = [dict(t) for t in await db.fetch_all("SELECT * FROM revocation_targets WHERE case_id=%s ORDER BY created_at", (case_id,))]
    evidence = [dict(e) for e in await db.fetch_all("SELECT * FROM termination_evidence WHERE case_id=%s ORDER BY observed_at", (case_id,))]
    creds = server.get("server_held_credentials") or []
    provider_can_verify = bool(creds) and all(c.get("verify") for c in creds)
    case_activity = await _post_cutover(case)
    judged = []
    for target in targets:
        own = [e for e in evidence if e["target_id"] and str(e["target_id"]) == str(target["id"])]
        activity = await _post_cutover(case, target["subject_ref"]) if target["kind"] == "gateway-access" else case_activity
        result = _judge_target(target, own, activity, provider_can_verify)
        await db.execute("UPDATE revocation_targets SET criteria=%s, grade=%s WHERE id=%s",
                         (Jsonb(result["criteria"]), result["grade"], target["id"]))
        judged.append({**target, **result})
    notes = []
    if not targets:
        grade, notes = "T3", ["회수 대상이 하나도 열거되지 않았습니다."]
    else:
        grade = max((t["grade"] for t in judged), key=GRADE_RANK.__getitem__)
    if case_activity["unknown"]:
        grade = "T3"
        notes.append(f"차단 이후 실행 여부 미확인 호출 {case_activity['unknown']}건 — 종료를 입증할 수 없습니다.")
    summary = {}
    for key in ("C1", "C2", "C3", "C4"):
        gaps = [f"{t['label']}: {gap}" for t in judged for gap in t["criteria"][key]["gaps"]]
        summary[key] = {"met": not gaps, "gaps": gaps, "label": CRITERION_LABEL[key],
                        "targets_met": sum(1 for t in judged if t["criteria"][key]["met"])}
    worst = [t for t in judged if t["grade"] == grade]
    rationale = {
        "T1": "모든 회수 대상이 네 기준을 충족했습니다. 이 이용 관계의 종료를 진술할 수 있습니다.",
        "T2": "모집단과 증거는 확정됐으나 회수 또는 전파가 완결되지 않은 대상이 있어 잔존 범위의 상한만 설정할 수 있습니다.",
        "T3": "모집단을 열거하지 못했거나 상태를 특정하는 증거가 없는 대상이 있어 잔존 범위를 산정할 수 없습니다.",
    }[grade]
    criteria = {**summary, "grade": grade, "grade_label": GRADE_LABEL[grade], "rationale": rationale,
                "notes": notes, "determined_by": [t["label"] for t in worst][:5],
                "target_grades": {g: sum(1 for t in judged if t["grade"] == g) for g in ("T1", "T2", "T3")},
                "provider_operated": _is_provider(server), "post_cutover": case_activity,
                "assessed_at": _now().isoformat()}
    await db.execute(
        "UPDATE termination_cases SET status='ASSESSED', grade=%s, criteria=%s, assessed_by=%s, assessed_at=now() WHERE id=%s",
        (grade, Jsonb(criteria), actor, case_id))
    return await case_detail(case_id)


async def close_case(case_id: str, actor: str, note: str, risk_acceptance: str | None = None) -> dict:
    """T3 does not close without someone accepting the residual risk by name."""
    case = await _case(case_id)
    if case["status"] == "CLOSED":
        raise ValueError("이미 종결된 케이스입니다.")
    if case["status"] != "ASSESSED" or not case["grade"]:
        raise ValueError("판정하지 않은 케이스(또는 근거가 바뀐 뒤 다시 판정하지 않은 케이스)는 종결할 수 없습니다.")
    if not note.strip():
        raise ValueError("종결 사유를 적어야 합니다.")
    if case["grade"] == "T3" and not (risk_acceptance or "").strip():
        raise ValueError("T3(판단 불가)는 잔존 범위를 산정할 수 없으므로 위험 수용 근거 없이 종결할 수 없습니다.")
    async with db.transaction() as connection:
        await connection.execute(
            """UPDATE termination_cases SET status='CLOSED', closed_by=%s, closed_at=now(), close_note=%s,
                 risk_accepted_by=%s, risk_accepted_at = CASE WHEN %s::text IS NULL THEN NULL ELSE now() END,
                 risk_acceptance_note=%s WHERE id=%s""",
            (actor, note.strip(), actor if risk_acceptance else None, risk_acceptance, risk_acceptance or None, case_id))
        await connection.execute(
            """UPDATE mcp_servers SET lifecycle='RETIRED', status='DISABLED', status_reason=%s,
                 lifecycle_changed_at=now(), lifecycle_changed_by=%s WHERE id=%s""",
            (f"폐기 종결({case['grade']}) · {note.strip()[:160]}", actor, case["server_id"]))
        if case.get("relationship_id"):
            await connection.execute("UPDATE usage_relationships SET status='TERMINATED' WHERE id=%s", (case["relationship_id"],))
    return await case_detail(case_id)


async def reopen_case(case_id: str, actor: str, reason: str) -> dict:
    case = await _case(case_id)
    if case["status"] != "CLOSED":
        raise ValueError("종결된 케이스만 재개할 수 있습니다.")
    if not reason.strip():
        raise ValueError("재개 사유를 적어야 합니다.")
    async with db.transaction() as connection:
        await connection.execute(
            """UPDATE termination_cases SET status='REOPENED', grade=NULL, criteria=jsonb_build_object('reopened_note', %s::text),
                 closed_by=NULL, closed_at=NULL WHERE id=%s""", (f"{reason.strip()} (재개자 {actor})", case_id))
        await connection.execute(
            "UPDATE mcp_servers SET lifecycle='TERMINATING', lifecycle_changed_at=now(), lifecycle_changed_by=%s WHERE id=%s",
            (actor, case["server_id"]))
    return await case_detail(case_id)


async def restore_server(server_id: str, actor: str) -> dict:
    """Lab only: put a retired server back into service so the demo can be repeated.
    In an organisation, bringing a terminated relationship back is a new intake."""
    server = await _server(server_id)
    await db.execute(
        """UPDATE termination_cases SET status='CLOSED', closed_by=COALESCE(closed_by, %s), closed_at=COALESCE(closed_at, now()),
             close_note=COALESCE(close_note, '실습 복원으로 종결') WHERE server_id=%s AND status <> 'CLOSED'""",
        (actor, server_id))
    await db.execute(
        """UPDATE mcp_servers SET lifecycle='OPERATING', status='PENDING', status_reason='실습 복원 — 계약 재확인 대기',
             lifecycle_changed_at=now(), lifecycle_changed_by=%s, termination_case_id=NULL WHERE id=%s""", (actor, server_id))
    await db.execute("UPDATE usage_relationships SET status='ACTIVE' WHERE server_id=%s", (server_id,))
    return {"server_id": server_id, "previous_lifecycle": server.get("lifecycle"), "lifecycle": "OPERATING"}


# ── views ────────────────────────────────────────────────────────────────────
async def case_detail(case_id: str) -> dict:
    case = await db.fetch_one(
        """SELECT c.*, s.display_name, s.deployment, s.endpoint, s.lifecycle, s.source_ref, s.supplier,
                  s.exit_terms, s.server_held_credentials, u.purpose, u.organization, u.owner_department
             FROM termination_cases c JOIN mcp_servers s ON s.id = c.server_id
             LEFT JOIN usage_relationships u ON u.id = c.relationship_id
            WHERE c.id=%s""", (case_id,))
    if not case:
        raise ValueError("존재하지 않는 종료 케이스입니다.")
    targets = await db.fetch_all("SELECT * FROM revocation_targets WHERE case_id=%s ORDER BY created_at", (case_id,))
    evidence = await db.fetch_all("SELECT * FROM termination_evidence WHERE case_id=%s ORDER BY observed_at DESC", (case_id,))
    residue = await db.fetch_one("SELECT count(*) AS n FROM endpoint_inventory WHERE registry_match=%s", (case["server_id"],))
    return _row({
        "case": dict(case), "targets": [dict(t) for t in targets],
        "evidence": [{**dict(e), "meaning": EVIDENCE_KINDS.get(e["kind"], {})} for e in evidence],
        "activity": await _post_cutover(dict(case)), "endpoint_residue": int(residue["n"] or 0),
        "evidence_kinds": EVIDENCE_KINDS, "criteria_labels": CRITERION_LABEL,
    })


async def list_cases(limit: int = 50) -> list[dict]:
    rows = await db.fetch_all(
        """SELECT c.id, c.server_id, c.relationship_id, c.engagement_label, c.provider, c.reason, c.status, c.grade,
                  c.cutover_at, c.opened_by, c.opened_at, c.assessed_at, c.closed_at, c.criteria,
                  s.display_name, s.lifecycle,
                  (SELECT count(*) FROM revocation_targets t WHERE t.case_id=c.id) AS targets,
                  (SELECT count(*) FROM revocation_targets t WHERE t.case_id=c.id AND t.status='OUTSTANDING') AS outstanding,
                  (SELECT count(*) FROM termination_evidence e WHERE e.case_id=c.id) AS evidence,
                  (c.status <> 'CLOSED' AND c.opened_at < now() - make_interval(days => %s)) AS overdue,
                  c.opened_at + make_interval(days => %s) AS due_at
             FROM termination_cases c JOIN mcp_servers s ON s.id=c.server_id
            ORDER BY c.opened_at DESC LIMIT %s""", (SLA_DAYS, SLA_DAYS, limit))
    return [_row(dict(row)) for row in rows]


async def disclosure_request(case_id: str) -> dict:
    """The letter an organisation can send when the provider's part is the gap."""
    detail = await case_detail(case_id)
    case = detail["case"]
    server = await _server(case["server_id"])
    terms = server.get("exit_terms") or {}
    outstanding = [t for t in detail["targets"] if t["holder"] == "provider" and t["status"] != "REVOKED"]
    criteria = case.get("criteria") or {}
    gaps = (criteria.get("C1") or {}).get("gaps", []) + (criteria.get("C2") or {}).get("gaps", [])
    basis = [f"도입 시 합의한 종료 조건: {text}" for key, text in EXIT_TERMS.items() if terms.get(key)] or [
        "도입 시 합의한 종료 조건이 기록되어 있지 않습니다. 본 요청은 계약 조항이 아니라 정보보호 점검 절차에 근거합니다."]
    asks = [("보유 자격 목록", f"{server['display_name']}가 저희 조직의 이용 관계를 위해 하위 시스템에 대해 보유한 인가 자격의 전체 목록과 각 자격의 범위"),
            ("폐기 처리 결과", "위 자격의 폐기 처리 결과를 대상 식별자와 처리 시점이 특정된 기록으로"),
            ("감사 기록 접근", "이용 종료 이후 합의된 기간 동안의 감사 기록 접근 경로와 만료일")]
    body = "\n".join([
        f"# {server['display_name']} 이용 종료에 따른 자격 회수 확인 요청", "",
        f"- 이용 관계: {case['engagement_label']}", f"- 제공자: {case['provider']}",
        f"- 종료 사유: {case['reason']}", f"- 호출 차단 시각: {case['cutover_at']}",
        f"- 현재 판정: {case.get('grade') or '미판정'}{' · ' + GRADE_LABEL[case['grade']] if case.get('grade') else ''}", "",
        "## 요청 근거", *[f"- {line}" for line in basis], "",
        "## 요청 사항", *[f"{i}. **{title}** — {text}" for i, (title, text) in enumerate(asks, 1)], "",
        "## 이 요청이 필요한 이유",
        "저희 조직은 이 이용 관계의 모든 도구 호출을 강제 경로(MCP Gateway)에서 차단했고, 그 사실을 이용 주체별로 확인했습니다. "
        "다만 MCP 인가 명세상 귀사의 서버가 하위 시스템에 대해 보유한 자격은 저희 조직이 회수할 수 없으며, 귀사의 고지 없이는 "
        "회수 대상의 범위를 확정할 수 없습니다. 확정되지 않은 범위는 잔존 위험의 상한을 산정할 수 없어 저희 기준으로 '판단 불가(T3)'로 분류됩니다.",
        "", *(["## 현재 확인되지 않은 항목", *[f"- {gap}" for gap in gaps]] if gaps else []),
        *(["", "## 미회수로 남아 있는 대상", *[f"- {t['label']}" for t in outstanding]] if outstanding else []),
    ])
    return {"case_id": case_id, "server_id": case["server_id"], "provider": case["provider"],
            "has_contract_basis": bool(terms), "outstanding_provider_targets": len(outstanding),
            "markdown": body, "generated_at": _now().isoformat()}


async def summary() -> dict:
    rows = await db.fetch_all("SELECT status, grade, count(*) AS n FROM termination_cases GROUP BY status, grade")
    overdue = await db.fetch_one(
        "SELECT count(*) AS n FROM termination_cases WHERE status <> 'CLOSED' AND opened_at < now() - make_interval(days => %s)",
        (SLA_DAYS,))
    residue = await db.fetch_one("SELECT count(*) AS n FROM endpoint_inventory WHERE classification='retired-residue'")
    shadow = await db.fetch_one("SELECT count(*) AS n FROM endpoint_inventory WHERE classification='shadow'")
    return {"open_cases": sum(int(r["n"]) for r in rows if r["status"] in {"OPEN", "REVOKING", "REOPENED"}),
            "awaiting_close": sum(int(r["n"]) for r in rows if r["status"] == "ASSESSED"),
            "unresolved_grades": sum(int(r["n"]) for r in rows if r["status"] != "CLOSED" and r["grade"] in {"T2", "T3"}),
            "overdue": int(overdue["n"] or 0), "sla_days": SLA_DAYS,
            "retired_residue": int(residue["n"] or 0), "shadow_endpoints": int(shadow["n"] or 0)}


async def report(case_id: str) -> dict:
    """The judgment report (판정서): criteria, per-target grades, evidence and what each
    piece of evidence does and does not prove - submittable to an audit as is."""
    detail = await case_detail(case_id)
    case = detail["case"]
    criteria = case.get("criteria") or {}
    return {
        "case_id": case["id"], "server_id": case["server_id"], "relationship_id": case.get("relationship_id"),
        "relationship": {"organization": case.get("organization"), "purpose": case.get("purpose"),
                         "provider": case["provider"], "allowed_resources": case.get("allowed_resources")},
        "engagement": case["engagement_label"], "reason": case["reason"],
        "grade": case.get("grade"), "grade_label": GRADE_LABEL.get(case.get("grade") or "", "미판정"),
        "rationale": criteria.get("rationale"), "determined_by": criteria.get("determined_by"),
        "criteria": [{"criterion": k, "label": CRITERION_LABEL[k], "met": bool((criteria.get(k) or {}).get("met")),
                      "gaps": (criteria.get(k) or {}).get("gaps", [])} for k in ("C1", "C2", "C3", "C4")],
        "targets": [{"label": t["label"], "kind": t["kind"], "holder": t["holder"], "status": t["status"],
                     "grade": t.get("grade"), "criteria": t.get("criteria")} for t in detail["targets"]],
        "evidence": detail["evidence"], "gateway_observed": detail["activity"],
        "cutover_at": case.get("cutover_at"), "assessed_at": case.get("assessed_at"), "closed_at": case.get("closed_at"),
        "risk_accepted_by": case.get("risk_accepted_by"), "risk_acceptance_note": case.get("risk_acceptance_note"),
        "generated_at": _now().isoformat(),
    }
