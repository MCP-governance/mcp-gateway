from __future__ import annotations

import asyncio
import json
import os
import pathlib
import re
import sys
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import httpx
import httpx2
import psycopg
from mcp import Client, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError

from . import db, privacy
from .core import (CHAIN_VERSION, EFFECT_LOG, RATE_LIMIT_CALLS, IMPORTANT_BURST_LIMIT, _policy, _recent_activity, _tool_spec, canonical_hash, effect_count,
                   approve_request, execute_call, set_enforcement_mode, supply_chain_coverage,
                   verify_audit_chain)

# 주소를 코드에 박아두면 compose 바깥(네이티브 실행, CI 러너)에서 acceptance가
# "정책 실패"가 아니라 DNS 실패로 끝난다. 기본값은 compose 서비스 이름 그대로다.
API = os.getenv("GATEWAY_URL", "http://gateway:8080").rstrip("/")
SSE_URL = os.getenv("GATEWAY_SSE_URL", "http://gateway-sse:8081/sse")
UPSTREAM_ENDPOINT_REF = os.getenv("HTTP_MCP_URL", "http://mock-http-mcp:9000/mcp/")
EMAILS = {"partner-demo": "nkk@bob.local", "emp-demo": "miso@bob.local", "admin-demo": "kkg@bob.local"}


TOKENS: dict[str, str] = {}


async def sign_in() -> None:
    """The gateway holds only the public key, so the test logs in like any client."""
    password = os.getenv("MOCK_SSO_PASSWORD", "test-password")
    async with httpx.AsyncClient(timeout=15) as client:
        for principal, email in EMAILS.items():
            response = await client.post(API + "/api/session", json={"email": email, "password": password})
            response.raise_for_status()
            TOKENS[principal] = response.json()["access_token"]


def bearer(principal: str) -> dict:
    """A synthetic signed identity, the only thing any ingress now accepts."""
    return {"Authorization": "Bearer " + TOKENS[principal]}


def check(condition: bool, name: str, details: str = "") -> dict:
    if not condition:
        raise AssertionError(f"{name}: {details}")
    return {"name": name, "status": "PASS", "details": details}


def public_read_executes(result: dict) -> bool:
    """A repeated run may raise the real anomaly Alert without denying the read."""
    return bool(result["upstream_executed"] and (
        (result["decision"] == "Allow" and result["policy_id"] == "P-333-ALLOW-001")
        or (result["decision"] == "Alert" and result["policy_id"] == "P-ANOMALY-001")))


def tool_payload(result) -> dict:
    if result.structured_content is not None:
        return result.structured_content
    for item in result.content:
        text = getattr(item, "text", "")
        try:
            value = json.loads(text)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            continue
    raise AssertionError("MCP tool returned no JSON object")


async def post(path: str, body: dict, principal: str = "partner-demo") -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(API + path, json=body, headers=bearer(principal))
        response.raise_for_status()
        return response.json()


async def termination_checks() -> list[dict]:
    """전주기의 마지막 구간을 실제 동작으로 검증한다.

    대상은 `github`이다. 인증 전이라 의도적으로 DISABLED이고 어떤 시나리오도 이
    서버를 쓰지 않으므로, 폐기했다가 되돌려도 다른 검증에 영향이 없다. 운영 중인
    `mock-http`를 쓰면 이 검증이 나머지 전부를 깨뜨린다.

    끝나면 반드시 되돌린다. 검증이 환경을 바꿔 놓고 끝나면 두 번째 실행의 결과가
    첫 번째와 달라지고, 그때부터 이 파일의 통과는 아무것도 뜻하지 않는다.
    """
    from . import decommission
    from .core import enforcement_mode, set_enforcement_mode

    checks: list[dict] = []
    target = "github"
    case_id = None
    try:
        opened = await decommission.open_case(
            target, "acceptance: 전주기 종료 검증", "admin-demo", "GitHub MCP · 합성 종료 검증")
        case_id = opened["case"]["id"]
        checks.append(check(opened["case"]["status"] == "OPEN" and opened["case"]["cutover_at"],
                            "termination-opens-with-cutover", "차단 시작 시각이 케이스와 함께 고정됨"))

        server = await db.fetch_one("SELECT lifecycle FROM mcp_servers WHERE id=%s", (target,))
        checks.append(check(server["lifecycle"] == "TERMINATING",
                            "termination-marks-lifecycle", server["lifecycle"]))

        # 종료 절차에 들어간 서버의 호출은 권한을 따지기 전에 끊긴다.
        blocked = await execute_call({"tool_name": "github_get_file", "user_token": "admin-demo",
                                      "owner": "MCP-governance", "repo": "mcp-gateway", "path": "README.md"})
        checks.append(check(blocked["decision"] == "Block" and blocked["policy_id"] == "MCP-DECOMM-001",
                            "termination-blocks-calls", blocked["policy_id"]))
        checks.append(check(blocked["upstream_executed"] is False,
                            "termination-no-upstream-effect", "차단된 호출은 upstream에 닿지 않음"))

        # 관찰 모드는 권한 판정에 대한 의견일 뿐이다. 폐기는 무결성 통제이므로
        # 관찰 중에도 풀리면 안 된다. 풀리면 C3의 근거 자체가 사라진다.
        previous = await enforcement_mode()
        await set_enforcement_mode("monitor", "admin-demo")
        under_monitor = await execute_call({"tool_name": "github_get_file", "user_token": "admin-demo",
                                            "owner": "MCP-governance", "repo": "mcp-gateway", "path": "README.md"})
        await set_enforcement_mode(previous, "admin-demo")
        checks.append(check(under_monitor["decision"] == "Block"
                            and under_monitor["policy_id"] == "MCP-DECOMM-001",
                            "termination-enforced-under-monitor", under_monitor["policy_id"]))

        # 원격 제공자가 하위 위임 자격을 고지하지 않으면 모집단을 열거할 수 없다.
        # 논문 E3과 같은 상황이고, 판정은 T3여야 한다.
        assessed = await decommission.assess(case_id, "admin-demo")
        criteria = assessed["case"]["criteria"]
        checks.append(check(assessed["case"]["grade"] == "T3",
                            "termination-undisclosed-provider-is-T3",
                            json.dumps(criteria["C1"]["gaps"], ensure_ascii=False)[:200]))
        checks.append(check(criteria["C1"]["met"] is False and criteria["C4"]["met"] is False,
                            "termination-c1-c4-are-gating", "모집단과 증거 접근은 성립 요건"))

        # 차단 이후 실행된 호출이 0건이라는 사실은 제공자가 아니라 이 강제 경로가
        # 만든다. 방금 두 번 막혔으므로 시도 수는 늘고 실행 수는 그대로다.
        checks.append(check(criteria["C3"]["post_cutover_executed"] == 0
                            and criteria["C3"]["post_cutover_blocked"] >= 2,
                            "termination-c3-measured-by-gateway",
                            f"executed={criteria['C3']['post_cutover_executed']} "
                            f"blocked={criteria['C3']['post_cutover_blocked']}"))

        # T3는 잔존 범위를 산정할 수 없으므로 위험 수용 없이 닫히지 않는다.
        refused = None
        try:
            await decommission.close_case(case_id, "admin-demo", "acceptance 종결 시도")
        except ValueError as exc:
            refused = str(exc)
        checks.append(check(refused is not None, "termination-t3-needs-risk-acceptance", refused or ""))

        # 제공자 고지와 대상별 증거가 갖춰지면 등급이 올라간다. 판정이 근거에
        # 반응하지 않으면 그것은 판정이 아니라 표기다.
        targets = await db.fetch_all(
            "SELECT id, holder FROM revocation_targets WHERE case_id=%s", (case_id,))
        for row in targets:
            await decommission.revoke_target(str(row["id"]), "admin-demo", "REVOKED",
                                             "acceptance: 회수 확인")
            await decommission.add_evidence(
                case_id, "provider-attestation" if row["holder"] == "provider" else "revocation-response",
                f"target:{row['id']}", "acceptance", {"note": "합성 증거"}, "admin-demo",
                target_id=str(row["id"]))
        await decommission.add_evidence(
            case_id, "liveness-probe", "github endpoint 도달 가능성", "acceptance",
            {"reachable": False}, "admin-demo")
        upgraded = await decommission.assess(case_id, "admin-demo")
        checks.append(check(upgraded["case"]["grade"] == "T1",
                            "termination-evidence-upgrades-grade",
                            json.dumps(upgraded["case"]["criteria"]["rationale"], ensure_ascii=False)))

        activity = await decommission._post_cutover(upgraded["case"])
        with patch.object(decommission, "_post_cutover", AsyncMock(return_value={**activity, "unknown": 1})):
            uncertain = await decommission.assess(case_id, "admin-demo")
        checks.append(check(uncertain["case"]["grade"] == "T3"
                            and not uncertain["case"]["criteria"]["C3"]["met"],
                            "termination-unknown-execution-prevents-T1"))
        await decommission.assess(case_id, "admin-demo")

        closed = await decommission.close_case(case_id, "admin-demo", "acceptance 종결")
        checks.append(check(closed["case"]["status"] == "CLOSED"
                            and closed["case"]["lifecycle"] == "RETIRED",
                            "termination-close-retires-server", closed["case"]["lifecycle"]))

        # 종결된 케이스는 다시 판정하지 않는다. 재개가 기록되는 조작이어야 한다.
        reassess_refused = None
        try:
            await decommission.assess(case_id, "admin-demo")
        except ValueError as exc:
            reassess_refused = str(exc)
        checks.append(check(reassess_refused is not None,
                            "termination-closed-case-is-final", reassess_refused or ""))

        # 관리자 전용. 직원 토큰으로는 케이스 목록조차 볼 수 없어야 한다.
        async with httpx.AsyncClient(timeout=10) as client:
            forbidden = await client.get(API + "/api/termination/cases", headers=bearer("emp-demo"))
        checks.append(check(forbidden.status_code == 403,
                            "termination-admin-only", str(forbidden.status_code)))

        # 제공자 고지 요청서. T3의 원인에 대해 조직이 할 수 있는 유일한 조치다.
        disclosure = await decommission.disclosure_request(case_id)
        checks.append(check("자격 회수 확인 요청" in disclosure["markdown"]
                            and disclosure["has_contract_basis"] is False,
                            "termination-disclosure-request",
                            f"contract_basis={disclosure['has_contract_basis']}"))
    finally:
        # 되돌리기. 케이스를 지우면 회수 대상과 증거는 ON DELETE CASCADE로 함께 간다.
        if case_id:
            await db.execute("DELETE FROM termination_cases WHERE id=%s", (case_id,))
        await db.execute(
            """UPDATE mcp_servers SET lifecycle='OPERATING', termination_case_id=NULL,
                 status='DISABLED', status_reason='인증정보를 저장하지 않아 의도적으로 비활성'
               WHERE id=%s""", (target,))
    return checks


async def drill_checks() -> list[dict]:
    """폐기 드릴. 실제로 끊지 않고 도달 가능한 최선 등급을 계산하는지 본다.

    드릴이 케이스를 만들거나 lifecycle을 바꾸면 그것은 드릴이 아니라 종료다.
    "계산해 봤더니 실행됐다"는 가장 나쁜 종류의 부작용이다.
    """
    from . import decommission

    checks: list[dict] = []
    before = await db.fetch_one("SELECT lifecycle FROM mcp_servers WHERE id='github'")
    cases_before = await db.fetch_one("SELECT count(*) AS n FROM termination_cases")

    # 원격 + 종료 조건 미확인 → 천장이 T3. 이 사실은 종료를 시작한 뒤에 알면 늦다.
    remote = await decommission.drill("github")
    checks.append(check(remote["best_attainable_grade"] == "T3" and remote["blockers"],
                        "drill-remote-without-terms-is-capped-at-T3",
                        json.dumps(remote["blockers"], ensure_ascii=False)[:200]))

    # 로컬 stdio는 이중 위임 계층이 없어 제공자 고지를 요구하지 않는다. 요구하면
    # 로컬 서버가 영원히 T3가 되고 아무도 이 판정을 쓰지 않는다.
    local = await decommission.drill("mock-stdio")
    checks.append(check(local["best_attainable_grade"] == "T1" and not local["blockers"],
                        "drill-local-stdio-can-reach-T1", local["best_attainable_grade"]))

    # 계약 조건이 있으면 천장이 올라간다. 드릴이 조건에 반응하지 않으면 그것은
    # 계산이 아니라 전송 방식으로 정해진 상수다.
    await db.execute(
        """UPDATE mcp_servers SET exit_terms='{"provider_credential_disclosure": true}'::jsonb
           WHERE id='github'""")
    with_terms = await decommission.drill("github")
    await db.execute("UPDATE mcp_servers SET exit_terms='{}'::jsonb WHERE id='github'")
    checks.append(check(with_terms["best_attainable_grade"] == "T2",
                        "drill-reacts-to-contract-terms", with_terms["best_attainable_grade"]))

    after = await db.fetch_one("SELECT lifecycle FROM mcp_servers WHERE id='github'")
    cases_after = await db.fetch_one("SELECT count(*) AS n FROM termination_cases")
    checks.append(check(after["lifecycle"] == before["lifecycle"]
                        and cases_after["n"] == cases_before["n"],
                        "drill-has-no-side-effects",
                        f"lifecycle={after['lifecycle']} cases={cases_after['n']}"))
    return checks


async def endpoint_plane_checks() -> list[dict]:
    """엔드포인트 평면이 강제 경로 밖의 것을 실제로 분류하는지 본다."""
    from . import endpoint_plane

    checks: list[dict] = []
    endpoint = "acceptance-endpoint-001"
    try:
        await endpoint_plane.enroll(endpoint, "acceptance-host", "linux", "1.0.0", "emp-demo")
        result = await endpoint_plane.ingest(endpoint, [
            {"config_path": "/tmp/claude_desktop_config.json", "server_label": "합성 문서 MCP",
             "transport": "streamable-http", "endpoint_ref": UPSTREAM_ENDPOINT_REF},
            {"config_path": "/tmp/claude_desktop_config.json", "server_label": "local-notes",
             "transport": "stdio", "endpoint_ref": "npx -y @example/notes-mcp"},
        ])
        checks.append(check(result["counts"]["registered"] == 1 and result["counts"]["shadow"] == 1,
                            "endpoint-classifies-registered-and-shadow",
                            json.dumps(result["counts"], ensure_ascii=False)))

        # 섀도 설정은 그 사람의 호출 판정에 반영된다. 막지는 않고 증적을 강화한다.
        shadow_count = await endpoint_plane.shadow_count_for("emp-demo")
        checks.append(check(shadow_count == 1, "endpoint-shadow-reaches-policy-input", str(shadow_count)))
        alerted = await execute_call({"tool_name": "read_document", "user_token": "emp-demo",
                                      "document_id": "work-001"})
        checks.append(check(alerted["decision"] == "Alert" and alerted["policy_id"] == "MCP-SHADOW-001",
                            "endpoint-shadow-upgrades-to-alert", alerted["policy_id"]))
        checks.append(check(alerted["upstream_executed"] is True,
                            "endpoint-shadow-does-not-block", "경고이지 차단이 아님"))

        # 보고는 누적이 아니라 교체다. 설정에서 지워진 항목이 남아 있으면 잔존이
        # 해소돼도 모집단이 영원히 확정되지 않는다.
        replaced = await endpoint_plane.ingest(endpoint, [
            {"config_path": "/tmp/claude_desktop_config.json", "server_label": "합성 문서 MCP",
             "transport": "streamable-http", "endpoint_ref": UPSTREAM_ENDPOINT_REF},
        ])
        checks.append(check(replaced["removed"] == 1 and replaced["counts"]["shadow"] == 0,
                            "endpoint-report-replaces-previous", f"removed={replaced['removed']}"))
        cleared = await execute_call({"tool_name": "read_document", "user_token": "emp-demo",
                                      "document_id": "work-001"})
        checks.append(check(cleared["policy_id"] == "P-333-ALLOW-001",
                            "endpoint-cleared-shadow-restores-allow", cleared["policy_id"]))

        # 위험 범주 매핑표가 실재하지 않는 정책을 가리키면, 화면은 있는데 통제는
        # 없는 연결이 된다. 정책 관리대장과 대조한다.
        from .core import policy_ledger
        ledger = await policy_ledger(refresh=True)
        rows = await db.fetch_all("SELECT id, mapped_policy_ids FROM aig_risk_catalog")
        missing = sorted({pid for row in rows for pid in row["mapped_policy_ids"] if pid not in ledger})
        checks.append(check(not missing and len(rows) == 13,
                            "aig-risk-catalog-maps-to-real-policies",
                            f"categories={len(rows)} missing={missing}"))
    finally:
        await db.execute("DELETE FROM endpoint_agents WHERE endpoint_id=%s", (endpoint,))
    return checks


async def run() -> dict:
    checks: list[dict] = []
    await sign_in()
    checks.append(check(len(TOKENS) == 3, "synthetic-login", "gateway는 공개키만 보유하므로 IdP에 로그인"))
    send_spec = await _tool_spec("send_external")
    checks.append(check(send_spec == {"server_id": "mock-http", "registry_name": "send_external", "action": "x"},
                        "registry-is-action-source", json.dumps(send_spec, ensure_ascii=False)))

    async with httpx.AsyncClient(timeout=30) as client:
        health = (await client.get(API + "/api/health")).json()
        matrix = (await client.get(API + "/api/policy/matrix")).json()
    checks.append(check(health["status"] == "ok", "core-health", json.dumps(health["components"], ensure_ascii=False)))
    checks.append(check(len(matrix["cells"]) == 27, "rego-333-cells", "27 policy combinations"))
    allowed = {("partner", "public", "r")}
    allowed |= {("employee", "public", "r"), ("employee", "nonimportant", "r"), ("employee", "nonimportant", "w"), ("employee", "important", "r")}
    allowed |= {("admin", data_class, action) for data_class in ("public", "nonimportant", "important") for action in ("r", "w", "x")}
    for cell in matrix["cells"]:
        observed = cell["decision"] != "Block"
        expected = (cell["role"], cell["data_class"], cell["action"]) in allowed
        check(observed == expected, "rego-333-exact", json.dumps(cell, ensure_ascii=False))
    checks.append(check(True, "rego-333-exact", "14 permitted or controlled, 13 blocked"))

    scenarios = [
        ("Allow", "partner-demo", {"tool_name": "read_document", "document_id": "notice-001"}, True),
        ("Alert", "emp-demo", {"tool_name": "read_document", "document_id": "secret-001"}, True),
        ("Restrict", "admin-demo", {"tool_name": "send_external", "document_id": "notice-001", "destination": "not-approved.example", "content": "A" * 120}, True),
        ("Approval", "admin-demo", {"tool_name": "send_external", "document_id": "secret-001", "destination": "review@corp.invalid", "content": "synthetic important"}, False),
        ("Block", "partner-demo", {"tool_name": "read_document", "document_id": "secret-001"}, False),
    ]
    approval_id = None
    for expected_decision, principal, body, should_execute in scenarios:
        result = await post("/api/calls", body, principal)
        checks.append(check(public_read_executes(result) if expected_decision == "Allow" else result["decision"] == expected_decision,
                            f"decision-{expected_decision.lower()}", result["policy_id"]))
        checks.append(check(result["upstream_executed"] is should_execute, f"effect-{expected_decision.lower()}", f"{result['effect_before']}->{result['effect_after']}"))
        if should_execute and body["tool_name"] != "get_current_time":
            check(result["effect_after"] == result["effect_before"] + 1, "effect-increment")
        if not should_execute:
            check(result["effect_after"] == result["effect_before"], "effect-blocked")
        if expected_decision == "Restrict":
            checks.append(check(result["effective_arguments"]["destination_sha256"] == canonical_hash("restricted.invalid") and result["effective_arguments"]["content_chars"] == 80, "restriction-applied", "destination digest + 80 chars"))
        if expected_decision == "Approval":
            approval_id = result["approval_id"]

    pii = await post("/api/calls", {"tool_name": "send_external", "document_id": "notice-001",
                                      "destination": "outside.example", "content": "Contact demo@example.com"}, "admin-demo")
    checks.append(check(pii["decision"] == "Block" and pii["policy_id"] == "MCP-DATA-EGRESS-001"
                        and not pii["upstream_attempted"] and pii["effect_before"] == pii["effect_after"],
                        "pii-egress-block-before-upstream", pii["policy_id"]))
    pii_row = await db.fetch_one("SELECT request_payload,policy_input,privacy_types FROM decisions WHERE id=%s",
                                 (pii["decision_id"],))
    checks.append(check("EMAIL_ADDRESS" in pii_row["privacy_types"] and
                        "demo@example.com" not in json.dumps(pii_row, default=str) and
                        "demo@example.com" not in json.dumps(pii, default=str),
                        "pii-evidence-keeps-types-not-values"))
    masked, kinds = await privacy.mask_text("주민번호 900101-1234567 / 010-1234-5678")
    checks.append(check({"KR_RRN", "KR_PHONE"}.issubset(kinds) and
                        "900101-1234567" not in masked and "010-1234-5678" not in masked,
                        "presidio-korean-identifiers-masked", str(kinds)))

    async with httpx.AsyncClient(timeout=10) as client:
        anonymous = await client.post(API + "/api/calls", json={"tool_name": "read_document", "document_id": "notice-001"})
        forged = await client.post(API + "/api/calls", headers={"Authorization": "Bearer not-a-real-token"},
                                   json={"tool_name": "read_document", "document_id": "notice-001"})
        anonymous_approval = await client.post(API + "/api/approvals/" + approval_id + "/approve", json={})
        partner_approval = await client.post(API + "/api/approvals/" + approval_id + "/approve",
                                              headers=bearer("partner-demo"), json={})
    checks.append(check(anonymous.status_code == 401 and forged.status_code == 401, "api-identity-required",
                        "anonymous=%s forged=%s" % (anonymous.status_code, forged.status_code)))
    checks.append(check(anonymous_approval.status_code == 401 and partner_approval.status_code == 403,
                        "approval-identity-required",
                        "anonymous=%s partner=%s" % (anonymous_approval.status_code, partner_approval.status_code)))

    approved = await approve_request(approval_id, "admin-demo")
    checks.append(check(approved["decision"] == "Allow" and approved["upstream_executed"], "approval-revalidation", approved["policy_id"]))
    checks.append(check(approved["effect_after"] == approved["effect_before"] + 1, "approval-effect", f"{approved['effect_before']}->{approved['effect_after']}"))
    checks.append(check("review@corp.invalid" not in json.dumps(approved["result"]) and
                        "[REDACTED]" in json.dumps(approved["result"]),
                        "presidio-masks-upstream-output", json.dumps(approved["result"], ensure_ascii=False)))
    last_effect = json.loads(EFFECT_LOG.read_text(encoding="utf-8").splitlines()[-1])
    checks.append(check(last_effect["tool"] == "send_external" and "arguments_sha256" in last_effect
                        and "destination" not in last_effect and "content" not in last_effect,
                        "upstream-effect-log-has-digest-only"))

    expired = await execute_call({"user_token": "admin-demo", "tool_name": "send_external", "document_id": "secret-001", "destination": "review.corp.invalid", "content": "expiry test"})
    await db.execute("UPDATE approvals SET expires_at=now()-interval '1 second' WHERE id=%s", (expired["approval_id"],))
    try:
        await approve_request(expired["approval_id"], "admin-demo")
        expired_blocked = False
    except ValueError:
        expired_blocked = True
    checks.append(check(expired_blocked, "approval-expiry", "expired request rejected"))

    stdio_upstream = await post("/api/calls", {"tool_name": "get_current_time", "timezone": "Asia/Seoul"})
    checks.append(check(public_read_executes(stdio_upstream), "stdio-upstream", "mcp-server-time"))

    github = await post("/api/calls", {"tool_name": "github_get_file", "owner": "MCP-governance", "repo": "mcp-gateway", "path": "README.md"})
    checks.append(check(github["decision"] == "Block" and github["policy_id"] == "MCP-REGISTRY-002", "github-auth-deferred", "registered but disabled"))

    unknown = await execute_call({"user_token": "admin-demo", "tool_name": "shadow_export", "document_id": "notice-001"})
    checks.append(check(unknown["decision"] == "Block" and unknown["policy_id"] == "MCP-REGISTRY-001", "unregistered-tool", "no upstream execution"))

    await db.execute("DELETE FROM supply_chain_reports WHERE scanner='acceptance-fixture'")
    try:
        await db.execute(
            """INSERT INTO supply_chain_reports(
                 scanner, scanner_version, source_ref, report_path, status, critical_count, summary
               ) VALUES ('acceptance-fixture','1','demo-v1','memory://critical-fixture','TEST',1,'{}')"""
        )
        supply_block = await execute_call({"user_token": "partner-demo", "tool_name": "read_document", "document_id": "notice-001"})
        checks.append(check(
            supply_block["decision"] == "Block"
            and supply_block["policy_id"] == "MCP-SUPPLY-001"
            and supply_block["effect_before"] == supply_block["effect_after"],
            "supply-chain-gate",
            f"critical report stopped upstream {supply_block['effect_before']}->{supply_block['effect_after']}",
        ))
    finally:
        await db.execute("DELETE FROM supply_chain_reports WHERE scanner='acceptance-fixture'")

    async with httpx2.AsyncClient(headers=bearer("partner-demo"), timeout=30) as http_client:
        async with Client(streamable_http_client(API + "/mcp/", http_client=http_client)) as client:
            tools = await client.list_tools()
            protocol_version = str(client.protocol_version)
            result = await client.call_tool("read_document", {"document_id": "notice-001"})
            structured = tool_payload(result)
            # Methods this gateway does not mediate are refused, not left undefined.
            refusals = {}
            for label, call in (("resources/list", client.list_resources), ("prompts/list", client.list_prompts)):
                try:
                    await call()
                    refusals[label] = "not refused"
                except MCPError as error:
                    refusals[label] = error.message[:60]
                except Exception as error:
                    refusals[label] = type(error).__name__
    checks.append(check(all("MCP-METHOD-001" in value for value in refusals.values()),
                        "mcp-method-scope", json.dumps(refusals, ensure_ascii=False)))
    checks.append(check({"read_document", "write_document", "send_external", "get_current_time", "github_get_file"} == {tool.name for tool in tools.tools}, "streamable-http-ingress", protocol_version))
    checks.append(check(not result.is_error and public_read_executes(structured), "streamable-http-call", "actual MCP tools/call"))
    checks.append(check(all("user_token" not in (tool.input_schema.get("properties") or {}) for tool in tools.tools),
                        "ingress-schema-has-no-identity", "identity is not a tool argument"))

    # No Authorization header at all: the ingress must refuse rather than fall back
    # to a default principal.
    async with httpx2.AsyncClient(timeout=30) as http_client:
        async with Client(streamable_http_client(API + "/mcp/", http_client=http_client)) as client:
            try:
                anonymous_call = await client.call_tool("read_document", {"document_id": "notice-001"})
                anonymous_refused = bool(anonymous_call.is_error)
            except Exception:
                anonymous_refused = True
    checks.append(check(anonymous_refused, "mcp-ingress-identity-required", "unauthenticated tools/call refused"))

    # 부모 환경을 물려준다. env를 통째로 갈아끼우면 자식이 DATABASE_URL·OPA_URL을
    # 잃고 기본값으로 떨어져, 이 시험이 stdio ingress가 아니라 환경변수가 컨테이너
    # 기본값과 같은지를 재게 된다.
    parameters = StdioServerParameters(command=sys.executable, args=["-m", "app.stdio_entry"],
                                       env={**os.environ, "GATEWAY_STDIO_PRINCIPAL": "partner-demo"})
    async with Client(parameters) as client:
        result = await client.call_tool("read_document", {"document_id": "notice-001"})
        structured = tool_payload(result)
    checks.append(check(not result.is_error and public_read_executes(structured), "stdio-ingress", "identity bound at spawn time"))

    # 신원만 빼고 나머지는 같은 환경이다. 그래야 "신원이 없어서 거부됐다"와
    # "DB에 못 붙어서 죽었다"가 구분된다.
    unbound_env = {key: value for key, value in os.environ.items() if key != "GATEWAY_STDIO_PRINCIPAL"}
    unbound = StdioServerParameters(command=sys.executable, args=["-m", "app.stdio_entry"],
                                    env=unbound_env)
    async with Client(unbound) as client:
        try:
            unbound_call = await client.call_tool("read_document", {"document_id": "notice-001"})
            unbound_refused = bool(unbound_call.is_error)
        except Exception:
            unbound_refused = True
    checks.append(check(unbound_refused, "stdio-ingress-identity-required", "unbound stdio ingress refused"))

    # Observation mode: permission opinions are recorded instead of applied, while
    # integrity controls keep enforcing. Both halves matter, so both are checked.
    async with httpx.AsyncClient(timeout=30) as client:
        flipped = await client.put(API + "/api/enforcement", headers=bearer("admin-demo"), json={"mode": "monitor"})
        checks.append(check(flipped.status_code == 200, "monitor-switch", flipped.text[:120]))
        denied = await client.put(API + "/api/enforcement", headers=bearer("emp-demo"), json={"mode": "enforce"})
        checks.append(check(denied.status_code == 403, "monitor-switch-admin-only", str(denied.status_code)))
    try:
        observed = await post("/api/calls", {"tool_name": "read_document", "document_id": "secret-001"}, "partner-demo")
        checks.append(check(
            observed["decision"] == "Allow" and observed["policy_id"] == "P-MONITOR-001"
            and observed["would_decision"] == "Block" and observed["would_policy_id"] == "P-333-DENY-001"
            and observed["upstream_executed"] and observed["effect_after"] == observed["effect_before"] + 1,
            "monitor-observes-permission",
            f"{observed['policy_id']} would={observed['would_policy_id']}"))
        integrity = await execute_call({"user_token": "admin-demo", "tool_name": "shadow_export", "document_id": "notice-001"})
        checks.append(check(
            integrity["decision"] == "Block" and integrity["policy_id"] == "MCP-REGISTRY-001"
            and integrity["would_decision"] is None
            and integrity["effect_after"] == integrity["effect_before"],
            "monitor-still-enforces-integrity", integrity["policy_id"]))
        async with httpx.AsyncClient(timeout=30) as client:
            summary = (await client.get(API + "/api/monitor/summary?hours=1")).json()
        checks.append(check(
            summary["enforcement"] == "monitor" and summary["would_have_stopped"] >= 1
            and summary["affected_principals"] >= 1,
            "monitor-summary", f"{summary['would_have_stopped']} calls would have been stopped"))
    finally:
        await set_enforcement_mode("enforce", "admin-demo")
    checks.append(check((await post("/api/calls", {"tool_name": "read_document", "document_id": "secret-001"}, "partner-demo"))["decision"] == "Block",
                        "enforce-restored", "관찰 모드를 끄면 즉시 다시 차단"))

    # Volume controls. Flooding the gateway with real calls to trip the ceiling would
    # add a minute to every run and pollute the effect log, so the two halves are
    # checked separately: that the gateway measures, and that OPA decides on it.
    activity = await _recent_activity("partner-demo")
    checks.append(check(
        activity["recent_calls"] >= 1 and activity["call_limit"] == RATE_LIMIT_CALLS
        and activity["important_limit"] == IMPORTANT_BURST_LIMIT,
        "volume-signal-measured", json.dumps(activity, ensure_ascii=False)))
    contract = {"registered": True, "enabled": True, "schema_hash_match": True,
                "description_hash_match": True, "version_match": True, "known_tools_only": True,
                "metadata_safe": True, "supplier_approved": True, "critical_vulnerabilities": 0}
    over_rate = await _policy({
        "principal": {"role": "admin"}, "resource": {"data_class": "public"},
        "tool": {"action": "r"}, "approval": {"granted": False}, "contract": contract,
        "context": {**activity, "recent_calls": activity["call_limit"]}})
    checks.append(check(over_rate["policy_id"] == "P-RATE-001", "rate-limit-decision", over_rate["policy_id"]))
    burst = await _policy({
        "principal": {"role": "employee"}, "resource": {"data_class": "important"},
        "tool": {"action": "r"}, "approval": {"granted": False}, "contract": contract,
        "context": {**activity, "recent_important": activity["important_limit"]}})
    checks.append(check(burst["policy_id"] == "P-VOLUME-001" and burst["decision"] == "Approval",
                        "important-burst-escalates", burst["policy_id"]))

    async with httpx.AsyncClient(timeout=30) as client:
        # An address that does not exist, so a real account is not locked out by the test.
        statuses = [(await client.post(API + "/api/session", json={
            "email": "nobody@bob.local", "password": "wrong"})).status_code for _ in range(12)]
        successful = [(await client.post(API + "/api/session", json={
            "email": "nkk@bob.local", "password": os.getenv("MOCK_SSO_PASSWORD", "test-password")})).status_code for _ in range(12)]
    checks.append(check(429 in statuses, "login-attempt-ceiling", f"statuses={sorted(set(statuses))}"))
    checks.append(check(all(status == 200 for status in successful), "successful-login-not-throttled", f"statuses={sorted(set(successful))}"))

    # Rejecting is the other half of approving. Without it a reviewer can only approve
    # or let the request expire, and the audit cannot tell refusal from inattention.
    pending = await post("/api/calls", {"tool_name": "send_external", "document_id": "secret-001",
                                        "destination": "review.corp.invalid", "content": "거부 대상"}, "admin-demo")
    before = effect_count()
    approval = pending["approval_id"]
    async with httpx.AsyncClient(timeout=30) as client:
        empty_note = await client.post(API + f"/api/approvals/{approval}/reject", headers=bearer("admin-demo"), json={"note": ""})
        as_employee = await client.post(API + f"/api/approvals/{approval}/reject", headers=bearer("emp-demo"), json={"note": "안 됩니다"})
        rejected = await client.post(API + f"/api/approvals/{approval}/reject", headers=bearer("admin-demo"),
                                     json={"note": "외부 전송 근거가 부족합니다."})
        after_reject = await client.post(API + f"/api/approvals/{approval}/approve", headers=bearer("admin-demo"), json={})
    checks.append(check(empty_note.status_code == 422 and as_employee.status_code == 403,
                        "approval-reject-guards", f"empty={empty_note.status_code} employee={as_employee.status_code}"))
    checks.append(check(rejected.status_code == 200 and rejected.json()["status"] == "REJECTED"
                        and rejected.json()["review_note"], "approval-reject", rejected.text[:100]))
    checks.append(check(after_reject.status_code == 409, "approval-reject-is-final", str(after_reject.status_code)))
    checks.append(check(effect_count() == before, "approval-reject-no-effect", f"{before}->{effect_count()}"))

    # The department axis is inert until an operator enables it, but the input has to
    # carry real values or turning it on later finds nothing to compare.
    departments = {row["role"]: row["department"] for row in await db.fetch_all("SELECT role, department FROM principals")}
    documents = await db.fetch_all("SELECT id, owner_department, classification_source, classification_version FROM documents")
    owners = {row["id"]: row["owner_department"] for row in documents}
    checks.append(check(all(departments.get(role) for role in ("partner", "employee", "admin"))
                        and owners.get("secret-001") and owners.get("work-001"),
                        "policy-input-organisational-axis",
                        json.dumps({"principals": departments, "documents": owners}, ensure_ascii=False)))
    checks.append(check(all(row["classification_source"] == "manual-registry" and row["classification_version"] for row in documents),
                        "classification-registry-provenance", "모든 합성 문서에 관리대장 출처와 버전이 있음"))
    unchanged = await post("/api/calls", {"tool_name": "read_document", "document_id": "secret-001"}, "emp-demo")
    checks.append(check(unchanged["decision"] == "Alert" and unchanged["policy_id"] == "P-IMPORTANT-ALERT-001",
                        "department-scope-disabled-by-default",
                        f"{unchanged['decision']}/{unchanged['policy_id']}"))

    coverage = {row["server_id"]: row for row in await supply_chain_coverage()}
    checks.append(check(
        coverage["mock-http"]["scan_path"] == "full_stack_lab/mock_server"
        and coverage["mock-stdio"]["scan_path"] == "full_stack_lab/gateway"
        and coverage["github"]["scan_path"] is None,
        "supply-chain-scan-targets",
        json.dumps({k: v["scan_path"] for k, v in coverage.items()}, ensure_ascii=False)))
    checks.append(check(
        all(row["source_ref"] for row in coverage.values()),
        "supply-chain-attribution-key", "모든 서버가 고정된 source_ref를 가짐"))

    # ── PaC 프레임워크 §11 연계 ────────────────────────────────────────────
    # 정책이 관리대장과 예외 대장을 실제로 읽고 집행하는지, 그리고 그 근거가 증적에
    # 남는지 확인한다. Rego 단위 시험은 정책 파일 안에서만 참이므로 여기서 한 번 더
    # 실제 DB·Registry 값으로 확인한다.
    async with httpx.AsyncClient(timeout=30) as client:
        ledger_view = (await client.get(API + "/api/policy/ledger")).json()
    ledger = {entry["policy_id"]: entry for entry in ledger_view["policies"]}
    checks.append(check(
        ledger_view["policy_set"].get("version") and len(ledger) >= 20
        and ledger_view["deployed_rego"]["status"] == "ACTIVE",
        "pac-ledger-published",
        f"{len(ledger)} policies, set {ledger_view['policy_set'].get('version')}"))

    # §11.8 정책 코드만으로 목적과 근거를 대신할 수 없다. Gateway가 직접 내는
    # policy_id도 관리대장에 있어야 한다.
    declared = set()
    for source in (pathlib.Path(__file__).parent).glob("*.py"):
        declared |= {pid for pid in re.findall(r'"((?:P|MCP)-[A-Z0-9][A-Z0-9-]*[A-Z0-9])"', source.read_text(encoding="utf-8"))}
    missing = sorted(declared - set(ledger))
    checks.append(check(not missing, "pac-every-policy-id-has-ledger-entry",
                        f"{len(declared)}개 정책 ID 모두 관리대장에 있음" if not missing else str(missing)))

    # §8 예외: 범위 안에서는 완화되고, 범위 밖 같은 등급 문서는 그대로 차단된다.
    excepted = await post("/api/calls", {"tool_name": "read_document", "document_id": "audit-001"}, "partner-demo")
    checks.append(check(
        excepted["decision"] == "Alert" and excepted["policy_id"] == "P-333-DENY-001"
        and excepted["exception"]["id"] == "EXC-001"
        and "사후 수동 검토 적용" in excepted["obligations"],
        "pac-exception-applies", json.dumps(excepted.get("exception"), ensure_ascii=False)))
    outside = await post("/api/calls", {"tool_name": "read_document", "document_id": "secret-001"}, "partner-demo")
    checks.append(check(
        outside["decision"] == "Block" and outside["policy_id"] == "P-333-DENY-001"
        and outside["exception"] is None,
        "pac-exception-stays-in-scope", f"{outside['decision']}/{outside['policy_id']}"))

    # §11.14 진 정책도 증적에 남는다. 최종 판단만 남기면 충돌 자체를 볼 수 없다.
    conflicting = await post("/api/calls", {"tool_name": "read_document", "document_id": "secret-001"}, "emp-demo")
    checks.append(check(
        conflicting["policy_id"] == "P-IMPORTANT-ALERT-001"
        and {item["policy_id"] for item in conflicting["conflicts"]} == {"P-333-ALLOW-001"}
        and all(item["priority"] > conflicting["priority"] for item in conflicting["conflicts"]),
        "pac-conflicts-recorded", json.dumps(conflicting["conflicts"], ensure_ascii=False)))

    # §11.4.1 승인 유효기간 만료 확인. Registry의 기한만 바꾸고 정책 코드는 건드리지 않는다.
    await db.execute("UPDATE mcp_tools SET approval_valid_until=now()-interval '1 day' WHERE server_id='mock-http' AND name='read_document'")
    try:
        stale = await post("/api/calls", {"tool_name": "read_document", "document_id": "notice-001"}, "partner-demo")
        checks.append(check(
            stale["decision"] == "Block" and stale["policy_id"] == "P-APPROVAL-EXPIRY-001"
            and stale["effect_after"] == stale["effect_before"],
            "pac-expired-approval-blocks", f"{stale['policy_id']} {stale['effect_before']}->{stale['effect_after']}"))
    finally:
        await db.execute("UPDATE mcp_tools SET approval_valid_until=timestamptz '2027-06-30 23:59:59+00' WHERE server_id='mock-http' AND name='read_document'")
    restored = await post("/api/calls", {"tool_name": "read_document", "document_id": "notice-001"}, "partner-demo")
    checks.append(check(public_read_executes(restored), "pac-reapproval-restores", restored["policy_id"]))

    # §11.17 판단 증적: 정책 버전·의무·환경이 감사 테이블에 실제로 들어갔는가.
    recorded = await db.fetch_one(
        "SELECT policy_id, policy_version, obligations, exception_id, conflicts, environment, chain_version"
        " FROM decisions WHERE policy_id='P-333-DENY-001' AND exception_id IS NOT NULL ORDER BY id DESC LIMIT 1")
    checks.append(check(
        bool(recorded) and recorded["policy_version"] == ledger["P-333-DENY-001"]["version"]
        and recorded["exception_id"] == "EXC-001" and recorded["environment"]
        and recorded["chain_version"] == CHAIN_VERSION and recorded["obligations"],
        "pac-decision-evidence-recorded", json.dumps(recorded, ensure_ascii=False, default=str)))

    chain = await verify_audit_chain()
    checks.append(check(chain["intact"], "audit-chain-intact", json.dumps(chain, ensure_ascii=False)))
    checks.append(check(chain["checked"] > 0, "audit-chain-populated", f"{chain['checked']} chained entries"))
    try:
        await db.execute("UPDATE decisions SET reason='tampered' WHERE id=(SELECT max(id) FROM decisions)")
        append_only = False
    except psycopg.Error:
        append_only = True
    checks.append(check(append_only, "audit-append-only", "gateway 계정은 decisions를 수정할 수 없음"))

    async with Client(sse_client(SSE_URL, headers=bearer("partner-demo"))) as client:
        result = await client.call_tool("read_document", {"document_id": "notice-001"})
        structured = tool_payload(result)
    checks.append(check(not result.is_error and public_read_executes(structured), "legacy-sse-ingress", "compatibility adapter"))

    checks.extend(await termination_checks())
    checks.extend(await drill_checks())
    checks.extend(await endpoint_plane_checks())

    # CTL-28. 인가 거부가 창 안에서 상한을 넘으면 같은 권한의 같은 호출이어도
    # 증적이 올라가야 한다. 이 시험이 없으면 정책을 좁히다가 조용히 죽일 수 있다.
    # 막지 않는다는 것도 함께 확인한다 - 막으면 오조작이 계정 정지가 된다.
    #
    # 맨 끝에 두는 이유: decisions는 append-only라 이 시험이 만든 이력을 되돌릴 수
    # 없고, 그 이력이 같은 주체의 뒤 시험 판정을 바꾼다.
    for _ in range(6):
        await post("/api/calls", {"tool_name": "read_document", "document_id": "secret-001"}, "partner-demo")
    anomalous = await post("/api/calls", {"tool_name": "read_document", "document_id": "notice-001"}, "partner-demo")
    checks.append(check(anomalous["policy_id"] == "P-ANOMALY-001" and anomalous["decision"] == "Alert"
                        and anomalous["upstream_executed"] is True,
                        "anomaly-streak-raises-evidence", anomalous["policy_id"]))

    return {
        "status": "PASS",
        "generated_at": datetime.now(UTC).isoformat(),
        "checks": checks,
        "summary": {"passed": len(checks), "failed": 0},
    }


if __name__ == "__main__":
    try:
        print(json.dumps(asyncio.run(run()), ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False, indent=2))
        raise
