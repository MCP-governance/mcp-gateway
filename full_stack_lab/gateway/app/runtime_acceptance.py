"""실제 DB/OPA/MCP를 이용한 실행 경계 회귀 검사. 격리된 실습 DB에서 실행한다."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import httpx
from mcp import Client, StdioServerParameters

from . import core, db, decommission, model_client
from .acceptance import check, tool_payload


async def run() -> dict:
    checks = []
    await core.policy_ledger(refresh=True)
    original_mode = await core.enforcement_mode()
    principals = await db.fetch_all("SELECT token,status FROM principals")
    valid = {"decision": "Allow", "policy_id": "P-333-ALLOW-001",
             "reason": "boundary fixture", "restrictions": {}}
    policy_input = {"tool": {"name": "send_external"}}
    client_factory = httpx.AsyncClient

    with patch.dict(os.environ, {"MODEL_TIMEOUT_SECONDS": "nan"}):
        checks.append(check(model_client.effective_timeout() == 20.0,
                            "invalid-model-timeout-uses-safe-default"))

    source = (await db.fetch_one("SELECT source_ref FROM mcp_servers WHERE id='mock-http'"))["source_ref"]
    marker = "runtime-evidence-mode-acceptance"
    try:
        for mode, critical in (("live", 2), ("advisory", 0)):
            await db.execute(
                """INSERT INTO supply_chain_reports
                   (scanner, source_ref, report_path, status, critical_count, summary)
                   VALUES ('AI-Infra-Guard mcp-scan', %s, %s, 'TEST', %s, %s::jsonb)""",
                (source, f"{marker}-{mode}", critical, json.dumps({"evidence_mode": mode})),
            )
            count = (await core._contract("mock-http", "read_document"))["critical_vulnerabilities"]
            if mode == "live":
                live_count = count
        checks.append(check(live_count >= 2 and count == live_count,
                            "advisory-scan-does-not-hide-live-critical"))
    finally:
        await db.execute("DELETE FROM supply_chain_reports WHERE report_path IN (%s, %s)",
                         (marker + "-live", marker + "-advisory"))

    def response(body):
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json=body))
        return patch.object(core.httpx, "AsyncClient",
                            lambda **kwargs: client_factory(transport=transport, **kwargs))

    invalid = [None, [], {}, {**valid, "decision": "ALLOW"},
               {**valid, "decision": "unknown"}, {**valid, "decision": ["Allow"]},
               {**valid, "policy_id": None}, {**valid, "reason": ""},
               {**valid, "restrictions": None}, {**valid, "upstream_executed": True},
               {**valid, "request_id": "forged"}, {**valid, "result": {"secret": "forged"}},
               {**valid, "obligations": "not-an-array"}, {**valid, "exception": {"id": []}}]
    invalid.extend({key: value for key, value in valid.items() if key != missing}
                   for missing in valid)
    invalid.extend({**valid, "decision": "Restrict", "restrictions": restrictions}
                   for restrictions in ({}, {"destination": "restricted.invalid"},
                       {"destination": "restricted.invalid", "max_chars": -1},
                       {"destination": "restricted.invalid", "max_chars": True},
                       {"destination": "restricted.invalid", "max_chars": "80"},
                       {"destination": "restricted.invalid", "max_chars": 80, "unsupported": True}))
    for index, value in enumerate(invalid):
        with response({"result": value}):
            try:
                await core._policy(policy_input)
            except RuntimeError:
                checks.append(check(True, f"invalid-policy-{index}"))
            else:
                raise AssertionError(f"invalid policy accepted: {value!r}")

    for decision in ("Allow", "Alert", "Approval", "Block", "Restrict"):
        expected = {**valid, "decision": decision}
        if decision == "Restrict":
            expected["restrictions"] = {"destination": "restricted.invalid", "max_chars": 0}
        with response({"result": expected}):
            checks.append(check(await core._policy(policy_input) == expected,
                                f"valid-policy-{decision.lower()}"))
        if decision == "Restrict":
            with response({"result": expected}):
                try:
                    await core._policy({"tool": {"name": "read_document"}})
                except RuntimeError:
                    checks.append(check(True, "unsupported-restriction-tool"))
                else:
                    raise AssertionError("restrictions silently ignored for read_document")

    public_call = {"user_token": "partner-demo", "tool_name": "read_document", "document_id": "notice-001"}
    try:
        for mode in ("enforce", "monitor"):
            await core.set_enforcement_mode(mode, "admin-demo")
            with response({"result": {**valid, "decision": "unknown"}}):
                result = await core.execute_call(public_call)
            checks.append(check(result["policy_id"] == "P-CONTROL-FAIL-CLOSED"
                                and result["decision"] == "Block" and not result["upstream_executed"]
                                and result["effect_before"] == result["effect_after"],
                                f"invalid-policy-blocks-{mode}"))

        await core.set_enforcement_mode("enforce", "admin-demo")
        for status in ("disabled", "locked"):
            await db.execute("UPDATE principals SET status=%s WHERE token='partner-demo'", (status,))
            result = await core.execute_call(public_call)
            checks.append(check(result["policy_id"] == "P-INPUT-001" and not result["upstream_executed"]
                                and result["effect_before"] == result["effect_after"], f"inactive-core-{status}"))
        before = core.effect_count()
        # 부모의 환경을 물려준다. env를 통째로 갈아끼우면 자식 프로세스가
        # DATABASE_URL·OPA_URL을 잃고 컨테이너 기본값으로 떨어져, 이 시험이
        # "stdio ingress가 정지 계정을 막는가"가 아니라 "환경변수가 컨테이너
        # 기본값과 같은가"를 재게 된다.
        parameters = StdioServerParameters(
            command=sys.executable, args=["-m", "app.stdio_entry"],
            env={**os.environ, "GATEWAY_STDIO_PRINCIPAL": "partner-demo"})
        async with Client(parameters) as client:
            result = tool_payload(await client.call_tool("read_document", {"document_id": "notice-001"}))
        checks.append(check(result["policy_id"] == "P-INPUT-001" and core.effect_count() == before,
                            "inactive-stdio-no-effect"))

        # Employee's pending request must not execute under the reviewer's identity.
        with patch.object(core, "_policy", AsyncMock(return_value={**valid, "decision": "Approval"})):
            pending = await core.execute_call({**public_call, "user_token": "emp-demo"})
        await db.execute("UPDATE principals SET status='disabled' WHERE token='emp-demo'")
        result = await core.approve_request(pending["approval_id"], "admin-demo")
        row = await db.fetch_one("SELECT status FROM approvals WHERE id=%s", (pending["approval_id"],))
        checks.append(check(result["policy_id"] == "P-INPUT-001" and row["status"] == "REJECTED"
                            and result["effect_before"] == result["effect_after"], "inactive-approval-requester"))

        send = {"user_token": "admin-demo", "tool_name": "send_external", "document_id": "secret-001",
                "destination": "review.corp.invalid", "content": "synthetic boundary check"}
        await core.set_enforcement_mode("monitor", "admin-demo")
        try:
            with patch.object(core, "_policy", AsyncMock(return_value={**valid, "decision": "Block", "policy_id": "P-CHAIN-001"})):
                chain = await core.execute_call({**send, "document_id": "notice-001"})
            checks.append(check(chain["policy_id"] == "P-CHAIN-001" and not chain["upstream_attempted"]
                                and chain["effect_before"] == chain["effect_after"],
                                "sensitive-chain-always-enforced-in-monitor"))
        finally:
            await core.set_enforcement_mode("enforce", "admin-demo")
        pending = await core.execute_call(send)
        check(pending["decision"] == "Approval", "approval-created", str(pending))
        await db.execute("UPDATE principals SET status='locked' WHERE token='admin-demo'")
        for action in (lambda: core.approve_request(pending["approval_id"], "admin-demo"),
                       lambda: core.reject_request(pending["approval_id"], "admin-demo", "test")):
            try:
                await action()
            except ValueError:
                pass
            else:
                raise AssertionError("inactive reviewer processed approval")
        checks.append(check(True, "inactive-reviewer-cannot-approve-or-reject"))
        await db.execute("UPDATE principals SET status='active' WHERE token='admin-demo'")

        call_upstream = core._call_upstream

        async def expire_before_dispatch(spec, arguments, approval_id=None):
            await db.execute("UPDATE approvals SET expires_at=now()-interval '1 second' WHERE id=%s", (approval_id,))
            return await call_upstream(spec, arguments, approval_id)

        with patch.object(core, "_call_upstream", expire_before_dispatch):
            result = await core.approve_request(pending["approval_id"], "admin-demo")
        checks.append(check(result["policy_id"] == "P-CONTROL-FAIL-CLOSED"
                            and result.get("upstream_attempted") is False and not result["upstream_executed"]
                            and result["effect_before"] == result["effect_after"], "approval-expires-before-dispatch", str(result)))

        # A tool can execute and then lose its response. Its audit row must not
        # claim a successful block; the independent MCP effect proves the difference.
        started = datetime.now(UTC)

        async def lose_response(spec, arguments, approval_id=None):
            await call_upstream(spec, arguments, approval_id)
            raise TimeoutError("synthetic response loss after upstream effect")

        with patch.object(core, "_call_upstream", lose_response):
            result = await core.execute_call({**public_call, "user_token": "admin-demo"})
        row = await db.fetch_one("SELECT * FROM decisions WHERE id=%s", (result["decision_id"],))
        checks.append(check(row["upstream_attempted"] and not row["upstream_executed"]
                            and result["effect_after"] == result["effect_before"] + 1,
                            "lost-response-persists-unknown-with-real-effect"))
        activity = await decommission._post_cutover({"server_id": "mock-http", "cutover_at": started})
        checks.append(check(activity["unknown"] == 1 and activity["blocked"] == 0,
                            "termination-does-not-count-unknown-as-blocked"))
        tampered = await db.fetch_all("SELECT * FROM decisions ORDER BY id")
        next(item for item in tampered if item["id"] == row["id"])["upstream_attempted"] = False
        with patch.object(db, "fetch_all", AsyncMock(return_value=tampered)):
            checks.append(check(not (await core.verify_audit_chain())["intact"], "attempt-flag-tamper-detected"))

        with patch.object(core, "_guarded_result", side_effect=core.ResultRejected("synthetic unsafe output")):
            result = await core.execute_call({**public_call, "user_token": "admin-demo"})
        checks.append(check(result["policy_id"] == "MCP-OUTPUT-001" and result["upstream_executed"]
                            and result["result"] is None
                            and result["effect_after"] == result["effect_before"] + 1,
                            "output-rejection-keeps-confirmed-execution"))

        with patch.object(core.privacy, "analyze", AsyncMock(side_effect=core.privacy.InspectionUnavailable("synthetic analyzer outage"))):
            result = await core.execute_call({**send, "document_id": "notice-001"})
        checks.append(check(result["policy_id"] == "P-DATA-INSPECTION-001" and
                            not result["upstream_attempted"] and result["effect_before"] == result["effect_after"],
                            "analyzer-outage-blocks-before-upstream"))

        with patch.object(core.privacy, "mask_payload", AsyncMock(side_effect=core.privacy.InspectionUnavailable("synthetic anonymizer outage"))):
            result = await core.execute_call({**public_call, "user_token": "admin-demo"})
        checks.append(check(result["policy_id"] == "MCP-OUTPUT-001" and result["upstream_executed"]
                            and result["result"] is None and result["effect_after"] == result["effect_before"] + 1,
                            "anonymizer-outage-withholds-result-after-execution"))

        with patch.object(core, "_policy", AsyncMock(return_value={**valid, "decision": "Restrict", "restrictions": {
                "destination": "restricted.invalid", "max_chars": 0}})):
            result = await core.execute_call({**send, "document_id": "notice-001"})
        checks.append(check(result["upstream_executed"] and result["effective_arguments"]["content_chars"] == 0
                            and result["effect_after"] == result["effect_before"] + 1, "zero-content-limit-enforced"))
        checks.append(check((await core.verify_audit_chain())["intact"], "runtime-audit-chain-intact"))
    finally:
        for principal in principals:
            await db.execute("UPDATE principals SET status=%s WHERE token=%s", (principal["status"], principal["token"]))
        await core.set_enforcement_mode(original_mode, "admin-demo")
        await db.close()
    return {"status": "PASS", "checks": checks, "summary": {"passed": len(checks), "failed": 0}}


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run()), ensure_ascii=False, indent=2))
