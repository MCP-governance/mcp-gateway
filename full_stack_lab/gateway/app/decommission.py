"""종료·폐기 판정 엔진.

CISC-W'26 투고 논문의 C1~C4 기준과 T1~T3 등급을 실행 가능한 판정으로 옮긴다.
판정은 사람이 쓰는 문장이 아니라 관리대장 행에서 계산되는 값이어야 한다. 그래야
같은 케이스를 두 사람이 봤을 때 같은 등급이 나오고, 등급이 달라졌을 때 어느 행이
바뀌어서 달라졌는지 말할 수 있다.

이 모듈이 조직에 주는 것은 제공자가 주지 않는 두 가지다.

  C3(연속성) : 차단 시작 시각 이후 이 서버로 실제 실행된 호출이 몇 건인가.
               제공자의 폐기 응답이 아니라 이 조직의 강제 경로가 남긴 사실이다.
  C4(증거)   : 대상과 시점을 특정하는 증거가 대상마다 있는가.

반대로 C1(모집단)의 일부는 구조적으로 조직이 확보할 수 없다. 원격 서버가 하위
시스템에 대해 보유한 자격은 제공자가 고지하지 않으면 존재 여부조차 알 수 없다.
그 경우 이 엔진은 T1을 주지 않는다. 모르는 것을 모른다고 말하는 것이 판정이다.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from psycopg.types.json import Jsonb

from . import db

# 원격 제공자가 하위 시스템에 대해 별도 자격을 보유할 수 있는 transport. 로컬에서
# 프로세스로 뜨는 stdio 서버에는 이중 위임 계층이 없으므로 제공자 고지를 요구하는
# 것이 의미가 없다. 요구 조건을 전송 방식과 무관하게 두면 로컬 서버가 영원히 T3가
# 되고, 그러면 아무도 이 판정을 쓰지 않는다.
REMOTE_TRANSPORTS = {"Streamable HTTP", "streamable-http", "sse", "SSE"}

# 종료 절차의 기한. 케이스가 열린 채로 잊히면 "차단은 했으나 아무것도 회수되지
# 않은 상태"가 무기한 지속된다. 그 상태는 T2도 T3도 아니고 판정 자체가 없는
# 상태라 위험 보고에 잡히지도 않는다.
SLA_DAYS = int(os.getenv("TERMINATION_SLA_DAYS", "14"))

# 도입 시점에 확보해야 하는 종료 조건. 논문 5.2의 계약·조달 항목을 그대로 옮긴다.
# 여기 있는 것은 계약 조항의 존재이지 제공자가 실제로 고지했다는 사실이 아니다.
EXIT_TERMS = {
    "provider_credential_disclosure": "제공자가 하위 시스템에 대해 보유한 위임 자격을 고지한다",
    "revocation_evidence": "폐기 요청의 처리 결과를 대상·시점이 특정된 기록으로 제출한다",
    "audit_access_retained": "이용 종료 후에도 합의된 기간 동안 감사 기록에 접근할 수 있다",
}

GRADE_LABEL = {
    "T1": "종료",
    "T2": "부분 종료",
    "T3": "판단 불가",
}

CRITERION_LABEL = {
    "C1": "모집단",
    "C2": "수행 권한",
    "C3": "연속성",
    "C4": "증거 접근",
}


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


async def _server(server_id: str) -> dict:
    row = await db.fetch_one("SELECT * FROM mcp_servers WHERE id=%s", (server_id,))
    if not row:
        raise ValueError("등록되지 않은 서버입니다.")
    return row


async def _tool_names(server_id: str) -> list[str]:
    rows = await db.fetch_all("SELECT name FROM mcp_tools WHERE server_id=%s", (server_id,))
    return sorted(row["name"] for row in rows)


# ── 케이스 ──────────────────────────────────────────────────────────────────

async def open_case(server_id: str, reason: str, opened_by: str,
                    engagement_label: str | None = None) -> dict:
    """종료 절차를 시작하고 그 즉시 호출을 끊는다.

    순서가 중요하다. 회수를 먼저 하고 차단을 나중에 하면, 회수와 차단 사이에
    호출이 성립할 수 있는 구간이 생긴다. 그 구간은 C3이 정확히 세는 대상이므로
    스스로 C3을 깨뜨리는 절차가 된다. 차단이 먼저다.
    """
    server = await _server(server_id)
    if server["lifecycle"] != "OPERATING":
        raise ValueError("이미 종료 절차가 진행 중이거나 폐기된 서버입니다.")
    live = await db.fetch_one(
        """SELECT id FROM termination_cases WHERE server_id=%s
           AND status IN ('OPEN','REVOKING','ASSESSED','REOPENED')""",
        (server_id,),
    )
    if live:
        raise ValueError("이 서버에 진행 중인 종료 케이스가 이미 있습니다.")

    case_id = str(uuid.uuid4())
    cutover = _now()
    resources = await db.fetch_all(
        "SELECT name, action FROM mcp_tools WHERE server_id=%s ORDER BY name", (server_id,)
    )
    async with db.transaction() as connection:
        await connection.execute(
            """INSERT INTO termination_cases(
                 id, server_id, engagement_label, provider, allowed_resources, reason,
                 status, cutover_at, opened_by)
               VALUES (%s,%s,%s,%s,%s,%s,'OPEN',%s,%s)""",
            (case_id, server_id,
             engagement_label or f"{server['display_name']} · {server['supplier']}",
             server["supplier"], Jsonb([dict(row) for row in resources]), reason,
             cutover, opened_by),
        )
        await connection.execute(
            """UPDATE mcp_servers SET lifecycle='TERMINATING', lifecycle_changed_at=%s,
                 lifecycle_changed_by=%s, termination_case_id=%s WHERE id=%s""",
            (cutover, opened_by, case_id, server_id),
        )
    await seed_targets(case_id, opened_by)
    return await case_detail(case_id)


async def seed_targets(case_id: str, actor: str) -> list[dict]:
    """강제 경로와 엔드포인트 보고가 이미 알고 있는 회수 대상을 채운다.

    모집단을 사람이 백지에서 적게 하면 빠뜨린다. 조직이 자체 확보할 수 있는 몫은
    자동으로 올리고, 제공자만 아는 몫은 비워 둔 채 그것이 비어 있다는 사실을
    판정이 보게 한다. 빈칸을 채워주는 것이 아니라 빈칸을 드러내는 것이 목적이다.
    """
    case = await db.fetch_one("SELECT * FROM termination_cases WHERE id=%s", (case_id,))
    if not case:
        raise ValueError("존재하지 않는 종료 케이스입니다.")
    server = await _server(case["server_id"])
    created: list[dict] = []

    # (1) 이 서버를 실제로 호출한 주체. 게이트웨이 원장이 정본이다.
    callers = await db.fetch_all(
        """SELECT DISTINCT d.user_token, p.display_name, p.email
             FROM decisions d LEFT JOIN principals p ON p.token = d.user_token
            WHERE d.server_id = %s AND d.created_at < %s""",
        (case["server_id"], case["cutover_at"]),
    )
    for row in callers:
        created.append(await add_target(
            case_id, "client-token",
            f"{row['display_name'] or row['user_token']} 의 게이트웨이 접근 자격",
            "org", "gateway-ledger", actor,
            note=f"감사 기록에서 이 서버를 호출한 주체({row['user_token']})",
        ))

    # (2) 엔드포인트 설정에 남아 있는 이 서버 항목. 망 밖의 모집단이다.
    residue = await db.fetch_all(
        """SELECT i.endpoint_id, i.config_path, i.server_label, a.hostname
             FROM endpoint_inventory i JOIN endpoint_agents a USING (endpoint_id)
            WHERE i.registry_match=%s""",
        (case["server_id"],),
    )
    for row in residue:
        created.append(await add_target(
            case_id, "endpoint-config",
            f"{row['hostname']} · {row['config_path']} 의 '{row['server_label']}' 항목",
            "endpoint", "endpoint-agent", actor,
            note="엔드포인트 평면이 보고한 클라이언트 설정 잔존",
        ))

    # (3) 원격 제공자가 하위 시스템에 대해 보유한 자격. 조직은 존재조차 모른다.
    #     자리만 만들고 UNVERIFIABLE로 둔다. 이 행이 C1을 미충족으로 만든다.
    if (server.get("deployment") or "internal") == "provider":
        created.append(await add_target(
            case_id, "server-held-credential",
            f"{server['supplier']} 가 하위 시스템에 대해 보유한 위임 자격",
            "provider", "operator-manual", actor,
            status="UNVERIFIABLE",
            note="제공자가 보유 자격을 고지하기 전에는 대상을 열거할 수 없습니다(논문 3.2).",
        ))
    return created


async def add_target(case_id: str, kind: str, label: str, holder: str,
                     discovered_by: str, actor: str, status: str = "OUTSTANDING",
                     note: str | None = None) -> dict:
    case = await db.fetch_one("SELECT status FROM termination_cases WHERE id=%s", (case_id,))
    if not case:
        raise ValueError("존재하지 않는 종료 케이스입니다.")
    if case["status"] == "CLOSED":
        raise ValueError("종결된 케이스에는 회수 대상을 추가할 수 없습니다.")
    target_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO revocation_targets(id, case_id, kind, label, holder, discovered_by, status, note)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        (target_id, case_id, kind, label, holder, discovered_by, status, note),
    )
    await _invalidate(case_id, actor, f"회수 대상 추가: {label}")
    return await db.fetch_one("SELECT * FROM revocation_targets WHERE id=%s", (target_id,))


async def revoke_target(target_id: str, actor: str, status: str, note: str | None = None) -> dict:
    if status not in {"REVOKED", "EXPIRED", "UNVERIFIABLE", "OUTSTANDING"}:
        raise ValueError("알 수 없는 회수 상태입니다.")
    target = await db.fetch_one("SELECT * FROM revocation_targets WHERE id=%s", (target_id,))
    if not target:
        raise ValueError("존재하지 않는 회수 대상입니다.")
    revoked_at = _now() if status in {"REVOKED", "EXPIRED"} else None
    await db.execute(
        """UPDATE revocation_targets SET status=%s, revoked_at=%s, revoked_by=%s,
             note=COALESCE(%s, note) WHERE id=%s""",
        (status, revoked_at, actor if revoked_at else None, note, target_id),
    )
    await _invalidate(target["case_id"], actor, f"회수 상태 변경: {target['label']} → {status}")
    return await db.fetch_one("SELECT * FROM revocation_targets WHERE id=%s", (target_id,))


async def add_evidence(case_id: str, kind: str, subject: str, source: str,
                       detail: dict, actor: str, observed_at: datetime | None = None,
                       target_id: str | None = None) -> dict:
    """증거를 붙인다. 대상과 시점이 없는 증거는 받지 않는다.

    "폐기 요청을 보냈습니다"는 조치의 기록이지 대상 상태의 증거가 아니다(논문 3.1).
    그래서 subject와 observed_at이 필수 인자이고, 내용 해시를 함께 남겨 나중에
    첨부된 값이 바뀌었는지 확인할 수 있게 한다.
    """
    case = await db.fetch_one("SELECT status FROM termination_cases WHERE id=%s", (case_id,))
    if not case:
        raise ValueError("존재하지 않는 종료 케이스입니다.")
    if not subject.strip():
        raise ValueError("증거가 특정하는 대상을 적어야 합니다.")
    evidence_id = str(uuid.uuid4())
    when = observed_at or _now()
    await db.execute(
        """INSERT INTO termination_evidence(
             id, case_id, target_id, kind, subject, observed_at, source, detail, sha256, recorded_by)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (evidence_id, case_id, target_id, kind, subject.strip(), when, source,
         Jsonb(detail), _digest({"kind": kind, "subject": subject, "detail": detail}), actor),
    )
    await _invalidate(case_id, actor, f"증거 추가: {kind} · {subject}")
    return await db.fetch_one("SELECT * FROM termination_evidence WHERE id=%s", (evidence_id,))


async def _invalidate(case_id: str, actor: str, note: str) -> None:
    """근거가 바뀌면 판정은 즉시 낡는다.

    ASSESSED 상태로 두면 화면이 옛 등급을 현재 상태처럼 보여준다. 등급을 지우는
    편이 낫다. 낡은 판정과 판정 없음 중 위험한 것은 낡은 판정이다.
    """
    await db.execute(
        """UPDATE termination_cases
              SET status = CASE WHEN status='ASSESSED' THEN 'REVOKING' ELSE status END,
                  grade = CASE WHEN status='ASSESSED' THEN NULL ELSE grade END,
                  criteria = CASE WHEN status='ASSESSED'
                                  THEN jsonb_build_object('stale_note', %s::text) ELSE criteria END
            WHERE id=%s AND status IN ('OPEN','REVOKING','ASSESSED','REOPENED')""",
        (f"{note} (기록자 {actor})", case_id),
    )


# ── 판정 ────────────────────────────────────────────────────────────────────

async def _post_cutover(case: dict) -> dict:
    """차단 시작 이후 이 서버에 무슨 일이 있었는가. C3의 직접 증거."""
    row = await db.fetch_one(
        """SELECT count(*) FILTER (WHERE upstream_executed) AS executed,
                  count(*) FILTER (WHERE NOT upstream_executed AND NOT
                    COALESCE(upstream_attempted, policy_id='MCP-UPSTREAM-001')) AS blocked,
                  count(*) FILTER (WHERE NOT upstream_executed AND
                    COALESCE(upstream_attempted, policy_id='MCP-UPSTREAM-001')) AS unknown,
                  max(created_at) AS last_attempt
             FROM decisions WHERE server_id = %s AND created_at >= %s""",
        (case["server_id"], case["cutover_at"]),
    )
    return {
        "executed": int(row["executed"] or 0),
        "blocked": int(row["blocked"] or 0),
        "unknown": int(row["unknown"] or 0),
        "last_attempt": row["last_attempt"].isoformat() if row["last_attempt"] else None,
    }


async def _residue_count(server_id: str) -> int:
    row = await db.fetch_one(
        "SELECT count(*) AS n FROM endpoint_inventory WHERE registry_match=%s", (server_id,)
    )
    return int(row["n"] or 0)


async def assess(case_id: str, actor: str) -> dict:
    """C1~C4를 계산하고 가장 낮은 등급을 케이스 등급으로 둔다."""
    case = await db.fetch_one("SELECT * FROM termination_cases WHERE id=%s", (case_id,))
    if not case:
        raise ValueError("존재하지 않는 종료 케이스입니다.")
    if case["status"] == "CLOSED":
        raise ValueError("종결된 케이스는 다시 판정하지 않습니다. 재개한 뒤 판정하세요.")
    server = await _server(case["server_id"])
    targets = await db.fetch_all(
        "SELECT * FROM revocation_targets WHERE case_id=%s ORDER BY created_at", (case_id,)
    )
    evidence = await db.fetch_all(
        "SELECT * FROM termination_evidence WHERE case_id=%s ORDER BY observed_at", (case_id,)
    )
    by_target: dict[str, list[dict]] = {}
    case_wide: list[dict] = []
    for row in evidence:
        if row["target_id"]:
            by_target.setdefault(str(row["target_id"]), []).append(row)
        else:
            case_wide.append(row)

    remote = (server.get("deployment") or "internal") == "provider"
    activity = await _post_cutover(case)
    residue = await _residue_count(case["server_id"])

    # ── C1 모집단 ───────────────────────────────────────────────────────────
    c1_gaps: list[str] = []
    if not targets:
        c1_gaps.append("회수 대상이 하나도 열거되지 않았습니다.")
    unverifiable = [t for t in targets if t["status"] == "UNVERIFIABLE"]
    for target in unverifiable:
        c1_gaps.append(f"열거 여부를 확인할 수 없는 대상: {target['label']}")
    disclosed = any(
        row["kind"] == "provider-attestation" or row["source"] == "provider-disclosure"
        for row in evidence
    ) or any(t["discovered_by"] == "provider-disclosure" for t in targets)
    if remote and not disclosed:
        c1_gaps.append(
            "원격 제공자가 하위 위임 자격을 고지하지 않아 회수 대상의 모집단을 열거할 수 없습니다."
        )
    if residue:
        c1_gaps.append(f"엔드포인트 설정에 이 서버 항목이 {residue}건 남아 있습니다.")
    c1 = {"met": not c1_gaps, "gaps": c1_gaps,
          "targets": len(targets), "unverifiable": len(unverifiable),
          "provider_disclosed": disclosed, "endpoint_residue": residue}

    # ── C2 수행 권한 ────────────────────────────────────────────────────────
    c2_gaps: list[str] = []
    provider_held = [t for t in targets if t["holder"] == "provider"]
    for target in targets:
        if target["status"] in {"REVOKED", "EXPIRED"}:
            continue
        if target["holder"] == "provider":
            c2_gaps.append(f"제공자만 회수할 수 있고 아직 회수되지 않았습니다: {target['label']}")
        else:
            c2_gaps.append(f"조직이 회수할 수 있으나 아직 조치하지 않았습니다: {target['label']}")
    for target in provider_held:
        attested = any(row["kind"] == "provider-attestation" for row in by_target.get(str(target["id"]), []))
        if target["status"] in {"REVOKED", "EXPIRED"} and not attested:
            c2_gaps.append(f"제공자 보유 자격의 회수를 제공자 증명으로 확인하지 못했습니다: {target['label']}")
    c2 = {"met": not c2_gaps, "gaps": c2_gaps,
          "provider_held": len(provider_held),
          "outstanding": len([t for t in targets if t["status"] == "OUTSTANDING"])}

    # ── C3 연속성 ───────────────────────────────────────────────────────────
    c3_gaps: list[str] = []
    if not case["cutover_at"]:
        c3_gaps.append("차단 시작 시각이 없어 공백 구간을 계산할 수 없습니다.")
    if activity["executed"]:
        c3_gaps.append(
            f"차단 시작 이후에도 실제 실행된 호출이 {activity['executed']}건 있습니다."
        )
    if activity["unknown"]:
        c3_gaps.append(f"실행 여부가 확인되지 않은 호출이 {activity['unknown']}건 있어 차단을 증명할 수 없습니다.")
    lags = [
        (t["revoked_at"] - case["cutover_at"]).total_seconds()
        for t in targets if t["revoked_at"] and case["cutover_at"]
    ]
    if remote:
        probes = [row for row in evidence if row["kind"] == "liveness-probe"]
        reachable = [row for row in probes if row["detail"].get("reachable")]
        if not probes:
            c3_gaps.append("차단 이후 대상 endpoint의 도달 가능 여부를 확인한 기록이 없습니다.")
        elif reachable:
            c3_gaps.append(
                f"차단 이후에도 endpoint가 응답했습니다({len(reachable)}회). 전파가 완료되지 않았습니다."
            )
    c3 = {"met": not c3_gaps, "gaps": c3_gaps,
          "post_cutover_executed": activity["executed"],
          "post_cutover_blocked": activity["blocked"],
          "post_cutover_unknown": activity["unknown"],
          "last_attempt": activity["last_attempt"],
          "max_propagation_seconds": max(lags) if lags else None}

    # ── C4 증거 접근 ────────────────────────────────────────────────────────
    c4_gaps: list[str] = []
    if not evidence:
        c4_gaps.append("이 케이스에 첨부된 증거가 없습니다.")
    for target in targets:
        if not by_target.get(str(target["id"])):
            c4_gaps.append(f"대상·시점을 특정하는 증거가 없습니다: {target['label']}")
    c4 = {"met": not c4_gaps, "gaps": c4_gaps,
          "evidence": len(evidence), "case_wide_evidence": len(case_wide),
          "targets_with_evidence": len([t for t in targets if by_target.get(str(t["id"]))])}

    # ── 등급 ────────────────────────────────────────────────────────────────
    # C1과 C4는 판정의 성립 요건, C2와 C3은 충족 정도를 가른다(논문 5.1).
    if activity["unknown"]:
        grade = "T3"
        rationale = "차단 시작 이후 실행 여부가 미확인인 호출이 있어 종료를 입증할 수 없습니다."
    elif not c1["met"] or not c4["met"]:
        grade = "T3"
        rationale = "모집단 또는 증거 접근이 성립하지 않아 잔존 범위를 산정할 수 없습니다."
    elif not c2["met"] or not c3["met"]:
        grade = "T2"
        rationale = "모집단은 확정됐고 잔존 범위를 특정할 수 있으나 회수 또는 전파가 완결되지 않았습니다."
    else:
        grade = "T1"
        rationale = "네 기준이 모두 충족되어 이 이용 관계의 종료를 진술할 수 있습니다."

    criteria = {
        "C1": c1, "C2": c2, "C3": c3, "C4": c4,
        "grade": grade, "grade_label": GRADE_LABEL[grade], "rationale": rationale,
        "remote_provider": remote,
        "assessed_at": _now().isoformat(),
    }
    await db.execute(
        """UPDATE termination_cases SET status='ASSESSED', grade=%s, criteria=%s,
             assessed_by=%s, assessed_at=now() WHERE id=%s""",
        (grade, Jsonb(criteria), actor, case_id),
    )
    return await case_detail(case_id)


async def probe(case_id: str, actor: str) -> dict:
    """차단 이후에도 그 주소에 무엇이 있는지 확인하고 증거로 남긴다.

    이것은 catalog 갱신이 아니다. 계약을 다시 읽어 신뢰하는 행위와, 종료가
    전파됐는지 확인하는 행위는 목적이 반대다. 그래서 MCP 핸드셰이크를 하지 않고
    HTTP 응답 여부만 본다. 폐기한 서버와 다시 대화를 시작하지는 않는다.

    응답이 온다는 것이 곧 "회수 실패"는 아니다. 조직의 토큰이 폐기됐어도 그 주소
    자체는 다른 고객에게 계속 서비스한다. 그래서 이 증거의 이름은 도달 가능성이고,
    판정에서 C3(전파 완료)의 반증으로만 쓴다. 증거가 말하는 것 이상을 말하지 않는다.
    """
    case = await db.fetch_one("SELECT * FROM termination_cases WHERE id=%s", (case_id,))
    if not case:
        raise ValueError("존재하지 않는 종료 케이스입니다.")
    server = await _server(case["server_id"])
    endpoint = server["endpoint"] or ""
    if not endpoint.startswith(("http://", "https://")):
        raise ValueError("HTTP endpoint가 있는 서버에만 도달 확인을 할 수 있습니다.")

    import httpx

    detail: dict[str, Any] = {"endpoint": endpoint, "method": "HEAD"}
    try:
        async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
            response = await client.head(endpoint)
        detail.update({"reachable": True, "status_code": response.status_code})
    except Exception as exc:  # 연결 거부·이름 해석 실패·타임아웃 모두 도달 불가다.
        detail.update({"reachable": False, "error": str(exc)[:300]})

    evidence = await add_evidence(
        case_id, "liveness-probe",
        f"{server['display_name']} endpoint 도달 가능성",
        "gateway-probe", detail, actor,
    )
    return {"evidence": _row(dict(evidence)), "reachable": detail["reachable"]}


async def close_case(case_id: str, actor: str, note: str,
                     risk_acceptance: str | None = None) -> dict:
    """종결. T3는 위험 수용의 주체가 기록되지 않으면 닫히지 않는다."""
    case = await db.fetch_one("SELECT * FROM termination_cases WHERE id=%s", (case_id,))
    if not case:
        raise ValueError("존재하지 않는 종료 케이스입니다.")
    if case["status"] == "CLOSED":
        raise ValueError("이미 종결된 케이스입니다.")
    if case["status"] != "ASSESSED" or not case["grade"]:
        raise ValueError("판정하지 않은 케이스는 종결할 수 없습니다.")
    if not note.strip():
        raise ValueError("종결 사유를 적어야 합니다.")
    if case["grade"] == "T3" and not (risk_acceptance or "").strip():
        raise ValueError(
            "T3(판단 불가)는 잔존 범위를 산정할 수 없으므로 위험 수용 근거 없이 종결할 수 없습니다."
        )
    async with db.transaction() as connection:
        await connection.execute(
            """UPDATE termination_cases SET status='CLOSED', closed_by=%s, closed_at=now(),
                 close_note=%s, risk_accepted_by=%s,
                 risk_accepted_at = CASE WHEN %s::text IS NULL THEN NULL ELSE now() END,
                 risk_acceptance_note=%s
               WHERE id=%s""",
            (actor, note.strip(), actor if risk_acceptance else None,
             risk_acceptance, (risk_acceptance or None), case_id),
        )
        await connection.execute(
            """UPDATE mcp_servers SET lifecycle='RETIRED', status='DISABLED',
                 status_reason=%s, lifecycle_changed_at=now(), lifecycle_changed_by=%s
               WHERE id=%s""",
            (f"폐기 종결({case['grade']}) · {note.strip()[:160]}", actor, case["server_id"]),
        )
    return await case_detail(case_id)


async def reopen_case(case_id: str, actor: str, reason: str) -> dict:
    """새 증거나 잔존 발견으로 판정을 다시 여는 길.

    종결이 되돌릴 수 없으면 "닫지 않는 편이 안전하다"가 되고, 그러면 아무 케이스도
    닫히지 않는다. 재개는 기록이 남는 조작이어야 하고, 재개된 서버는 폐기 상태로
    돌아가지 않는다. 폐기했던 것을 되살리는 것은 재개가 아니라 새 도입이다.
    """
    case = await db.fetch_one("SELECT * FROM termination_cases WHERE id=%s", (case_id,))
    if not case:
        raise ValueError("존재하지 않는 종료 케이스입니다.")
    if case["status"] != "CLOSED":
        raise ValueError("종결된 케이스만 재개할 수 있습니다.")
    if not reason.strip():
        raise ValueError("재개 사유를 적어야 합니다.")
    async with db.transaction() as connection:
        await connection.execute(
            """UPDATE termination_cases SET status='REOPENED', grade=NULL,
                 criteria=jsonb_build_object('reopened_note', %s::text),
                 closed_by=NULL, closed_at=NULL WHERE id=%s""",
            (f"{reason.strip()} (재개자 {actor})", case_id),
        )
        await connection.execute(
            """UPDATE mcp_servers SET lifecycle='TERMINATING', lifecycle_changed_at=now(),
                 lifecycle_changed_by=%s WHERE id=%s""",
            (actor, case["server_id"]),
        )
    return await case_detail(case_id)


# ── 조회 ────────────────────────────────────────────────────────────────────

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


async def case_detail(case_id: str) -> dict:
    case = await db.fetch_one(
        """SELECT c.*, s.display_name, s.transport, s.endpoint, s.lifecycle, s.source_ref
             FROM termination_cases c JOIN mcp_servers s ON s.id = c.server_id
            WHERE c.id=%s""",
        (case_id,),
    )
    if not case:
        raise ValueError("존재하지 않는 종료 케이스입니다.")
    targets = await db.fetch_all(
        "SELECT * FROM revocation_targets WHERE case_id=%s ORDER BY created_at", (case_id,)
    )
    evidence = await db.fetch_all(
        "SELECT * FROM termination_evidence WHERE case_id=%s ORDER BY observed_at DESC", (case_id,)
    )
    activity = await _post_cutover(case)
    return _row({
        "case": dict(case),
        "targets": [dict(row) for row in targets],
        "evidence": [dict(row) for row in evidence],
        "activity": activity,
        "endpoint_residue": await _residue_count(case["server_id"]),
    })


async def list_cases(limit: int = 50) -> list[dict]:
    rows = await db.fetch_all(
        """SELECT c.id, c.server_id, c.engagement_label, c.provider, c.reason, c.status,
                  c.grade, c.cutover_at, c.opened_by, c.opened_at, c.assessed_at,
                  c.closed_at, c.criteria, s.display_name, s.lifecycle,
                  (SELECT count(*) FROM revocation_targets t WHERE t.case_id=c.id) AS targets,
                  (SELECT count(*) FROM revocation_targets t
                    WHERE t.case_id=c.id AND t.status='OUTSTANDING') AS outstanding,
                  (SELECT count(*) FROM termination_evidence e WHERE e.case_id=c.id) AS evidence,
                  (c.status <> 'CLOSED'
                   AND c.opened_at < now() - make_interval(days => %s)) AS overdue,
                  c.opened_at + make_interval(days => %s) AS due_at
             FROM termination_cases c JOIN mcp_servers s ON s.id=c.server_id
            ORDER BY c.opened_at DESC LIMIT %s""",
        (SLA_DAYS, SLA_DAYS, limit),
    )
    return [_row(dict(row)) for row in rows]


async def drill(server_id: str) -> dict:
    """폐기 드릴. 실제로 끊지 않고 "지금 이 서버를 끄면 어떻게 되는가"를 계산한다.

    드릴이 답하는 것은 현재 등급이 아니라 **도달 가능한 최선 등급**이다. 증거를
    전부 모으고 회수를 전부 마쳤다고 가정해도 T1에 닿지 못하는 서버가 있다.
    제공자가 하위 위임 자격을 고지하지 않기로 되어 있으면 C1의 천장이 이미
    정해져 있고, 그것은 종료를 시작한 뒤에 알아도 늦다.

    이 값을 도입 심사에서 보면 질문이 하나 늘어난다 — "들일 수 있는가"가 아니라
    "끊을 수 있는가". 끝낼 수 없는 것을 시작하지 않는 것이 유일한 완화다.
    """
    server = await _server(server_id)
    remote = (server.get("deployment") or "internal") == "provider"
    terms = server.get("exit_terms") or {}
    disclosure_agreed = bool(terms.get("provider_credential_disclosure"))
    evidence_agreed = bool(terms.get("revocation_evidence"))

    callers = await db.fetch_all(
        """SELECT d.user_token, p.display_name, count(*) AS calls,
                  max(d.created_at) AS last_call
             FROM decisions d LEFT JOIN principals p ON p.token = d.user_token
            WHERE d.server_id = %s AND d.upstream_executed
            GROUP BY d.user_token, p.display_name ORDER BY calls DESC""",
        (server_id,),
    )
    residue = await db.fetch_all(
        """SELECT a.hostname, i.config_path, i.server_label
             FROM endpoint_inventory i JOIN endpoint_agents a USING (endpoint_id)
            WHERE i.registry_match=%s""",
        (server_id,),
    )

    blockers: list[str] = []
    if remote and not disclosure_agreed:
        blockers.append(
            "제공자의 하위 위임 자격 고지가 계약에 없습니다. 고지 없이는 회수 대상의 "
            "모집단을 열거할 수 없어 C1이 성립하지 않습니다.")
    if remote and not evidence_agreed:
        blockers.append(
            "폐기 기록 제출이 계약에 없습니다. 제공자 보유 자격의 회수를 확인할 "
            "수단이 없어 C2를 충족한다고 볼 근거가 없습니다.")

    # 천장 계산. C1이 막히면 아무리 잘해도 T3, C2만 막히면 T2까지다.
    if remote and not disclosure_agreed:
        ceiling = "T3"
    elif remote and not evidence_agreed:
        ceiling = "T2"
    else:
        ceiling = "T1"

    return _row({
        "server_id": server_id,
        "display_name": server["display_name"],
        "transport": server["transport"],
        "remote_provider": remote,
        "lifecycle": server["lifecycle"],
        "exit_terms": terms,
        "best_attainable_grade": ceiling,
        "best_attainable_label": GRADE_LABEL[ceiling],
        "blockers": blockers,
        # 끊었을 때의 업무 영향. 판정과는 별개지만 종료를 결정하는 사람이
        # 가장 먼저 묻는 것이고, 이 수를 모르면 결정이 미뤄진다.
        "active_users": [dict(row) for row in callers],
        "would_revoke": {
            "client_tokens": len(callers),
            "endpoint_configs": len(residue),
            "provider_held": 1 if remote else 0,
        },
        "endpoint_residue": [dict(row) for row in residue],
        "note": "실제로 차단하지 않았습니다. 종료를 시작하려면 케이스를 여세요.",
    })


async def disclosure_request(case_id: str) -> dict:
    """제공자에게 보낼 고지 요청서.

    T3의 가장 흔한 원인은 제공자가 보유 자격을 고지하지 않는 것이고, 그 상태에서
    조직이 할 수 있는 일은 요청하는 것뿐이다. 그 요청을 매번 사람이 새로 쓰게
    두면 하지 않게 된다. 계약에 조항이 있으면 그것을 근거로 인용한다.
    """
    detail = await case_detail(case_id)
    case = detail["case"]
    server = await _server(case["server_id"])
    terms = server.get("exit_terms") or {}
    outstanding = [t for t in detail["targets"]
                   if t["holder"] == "provider" and t["status"] != "REVOKED"]
    criteria = case.get("criteria") or {}
    gaps = (criteria.get("C1") or {}).get("gaps", []) + (criteria.get("C2") or {}).get("gaps", [])

    asks = [
        ("보유 자격 목록",
         f"{server['display_name']}가 저희 조직의 이용 관계를 위해 하위 시스템에 대해 "
         "보유한 인가 자격의 전체 목록과 각 자격의 범위"),
        ("폐기 처리 결과",
         "위 자격의 폐기 처리 결과를 대상 식별자와 처리 시점이 특정된 기록으로"),
        ("감사 기록 접근",
         "이용 종료 이후 합의된 기간 동안의 감사 기록 접근 경로와 만료일"),
    ]
    basis = []
    for key, text in EXIT_TERMS.items():
        if terms.get(key):
            basis.append(f"도입 시 합의한 종료 조건: {text}")
    if not basis:
        basis.append(
            "도입 시 합의한 종료 조건이 기록되어 있지 않습니다. 본 요청은 계약 조항이 "
            "아니라 정보보호 점검 절차에 근거합니다.")

    body = "\n".join([
        f"# {server['display_name']} 이용 종료에 따른 자격 회수 확인 요청",
        "",
        f"- 이용 관계: {case['engagement_label']}",
        f"- 제공자: {case['provider']}",
        f"- 종료 사유: {case['reason']}",
        f"- 호출 차단 시각: {case['cutover_at']}",
        f"- 현재 판정: {case.get('grade') or '미판정'}"
        f"{' · ' + GRADE_LABEL[case['grade']] if case.get('grade') else ''}",
        "",
        "## 요청 근거",
        *[f"- {line}" for line in basis],
        "",
        "## 요청 사항",
        *[f"{index}. **{title}** — {text}" for index, (title, text) in enumerate(asks, 1)],
        "",
        "## 이 요청이 필요한 이유",
        "저희 조직은 이 이용 관계의 클라이언트 자격을 폐기하고 모든 도구 호출을 "
        "차단했습니다. 다만 MCP 인가 명세상 귀사의 서버가 하위 시스템에 대해 보유한 "
        "자격은 저희 조직이 회수할 수 없으며, 귀사의 고지 없이는 회수 대상의 범위를 "
        "확정할 수 없습니다. 확정되지 않은 범위는 잔존 위험의 상한을 산정할 수 없어 "
        "저희 내부 기준으로 '판단 불가'로 분류됩니다.",
        "",
        *(["## 현재 확인되지 않은 항목", *[f"- {gap}" for gap in gaps]] if gaps else []),
        *(["", "## 미회수로 남아 있는 대상",
           *[f"- {t['label']}" for t in outstanding]] if outstanding else []),
    ])
    return {
        "case_id": case_id,
        "server_id": case["server_id"],
        "provider": case["provider"],
        "has_contract_basis": bool(terms),
        "outstanding_provider_targets": len(outstanding),
        "markdown": body,
        "generated_at": _now().isoformat(),
    }


async def summary() -> dict:
    """조치가 필요한 것만 센다. 케이스 총계는 조치를 부르지 않는다."""
    rows = await db.fetch_all(
        """SELECT status, grade, count(*) AS n FROM termination_cases
            GROUP BY status, grade"""
    )
    open_cases = sum(int(r["n"]) for r in rows if r["status"] in {"OPEN", "REVOKING", "REOPENED"})
    awaiting_close = sum(int(r["n"]) for r in rows if r["status"] == "ASSESSED")
    unresolved = sum(int(r["n"]) for r in rows
                     if r["status"] != "CLOSED" and r["grade"] in {"T2", "T3"})
    # 기한을 넘긴 케이스. 차단만 하고 회수가 멈춘 상태는 판정이 없어서 위험 보고에
    # 잡히지 않는다. 그래서 기한을 세는 쪽은 판정이 아니라 이 요약이다.
    overdue_row = await db.fetch_one(
        """SELECT count(*) AS n FROM termination_cases
            WHERE status <> 'CLOSED' AND opened_at < now() - make_interval(days => %s)""",
        (SLA_DAYS,),
    )
    residue = await db.fetch_one(
        """SELECT count(*) AS n FROM endpoint_inventory WHERE classification='retired-residue'"""
    )
    shadow = await db.fetch_one(
        """SELECT count(*) AS n FROM endpoint_inventory WHERE classification='shadow'"""
    )
    return {
        "open_cases": open_cases,
        "awaiting_close": awaiting_close,
        "unresolved_grades": unresolved,
        "overdue": int(overdue_row["n"] or 0),
        "sla_days": SLA_DAYS,
        "retired_residue": int(residue["n"] or 0),
        "shadow_endpoints": int(shadow["n"] or 0),
    }


async def report(case_id: str) -> dict:
    """종료 판정서. 감사에 그대로 제출할 수 있는 형태로 묶는다."""
    detail = await case_detail(case_id)
    case = detail["case"]
    criteria = case.get("criteria") or {}
    lines = []
    for key in ("C1", "C2", "C3", "C4"):
        item = criteria.get(key) or {}
        lines.append({
            "criterion": key,
            "label": CRITERION_LABEL[key],
            "met": bool(item.get("met")),
            "gaps": item.get("gaps", []),
        })
    return {
        "case_id": case["id"],
        "server_id": case["server_id"],
        "engagement": case["engagement_label"],
        "provider": case["provider"],
        "reason": case["reason"],
        "grade": case.get("grade"),
        "grade_label": GRADE_LABEL.get(case.get("grade") or "", "미판정"),
        "rationale": criteria.get("rationale"),
        "criteria": lines,
        "cutover_at": case.get("cutover_at"),
        "assessed_at": case.get("assessed_at"),
        "closed_at": case.get("closed_at"),
        "risk_accepted_by": case.get("risk_accepted_by"),
        "targets": detail["targets"],
        "evidence": detail["evidence"],
        "gateway_observed": detail["activity"],
        "endpoint_residue": detail["endpoint_residue"],
        "generated_at": _now().isoformat(),
    }
