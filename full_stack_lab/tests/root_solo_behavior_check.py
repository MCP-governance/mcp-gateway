"""D-188/D-189 행위 시험: 단독 운영 모드에서도 독립 승인 규칙이 지켜지고 승인마다 모드 표식이 남는다.

root_solo_check.py는 소스 문자열만 본다. 여기서는 승인 함수를 실제로 호출한다.
  - 경로 1: agent_service.approve_mcp_request (risk_tier_gate 포함) — 개별 승인
  - 경로 2: agent_service.approve_and_register — 한 화면 승인
  - 경로 3: core.register_server — 등록 때 승인 증거를 다시 확인
대역: 데이터베이스(`FakeLedger`가 approval_events·도입 신청·principals를 메모리에 둔다), 게이트웨이 HTTP,
저장소 게시(publish_internal_repo), 카탈로그 파일·registry 쓰기, 업스트림 MCP 탐색.
실제 코드: review.require_independent / same_person / record_event / transition, risk_tier,
solo_mode_enabled / solo_operator, 승인 함수 본문. 실제 PostgreSQL은 쓰지 않는다.
"""
from __future__ import annotations

import copy
import os
import sys
import unittest
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import intake_one_click_check as base  # noqa: E402  (행·카탈로그 상수만 빌려 쓴다)
from intake_fixture import local_manifest_keys, source_run

service, review, HTTPException = base.service, base.review, base.HTTPException
if service is not None:
    from app import core, risk_tier

REQUEST_ID = base.REQUEST_ID
REASON = "민감 정보 외부 전송의 위험을 알고 수용합니다."
ASSURANCE = {"legal_entity": "Example Provider Ltd.", "supplier_contact": "support@example.test",
             "security_contact": "security@example.test", "support_end": "2030-12-31",
             "vulnerability_policy_url": "https://example.test/security"}
USERS = {  # 토큰 -> 신원. tok-root와 tok-root-2는 한 사람(root)의 서로 다른 토큰이다.
    "tok-root": {"principal": "tok-root", "user_id": "root", "roles": ["admin"]},
    "tok-root-2": {"principal": "tok-root-2", "user_id": "root", "roles": ["admin"]},
    "tok-b": {"principal": "tok-b", "user_id": "admin-b", "roles": ["admin"]},
    "tok-emp": {"principal": "tok-emp", "user_id": "emp", "roles": ["admin"]},
    "tok-emp-2": {"principal": "tok-emp-2", "user_id": "emp", "roles": ["admin"]},
}
INPUTS = {  # 위험 등급 입력(저장소 신청용)
    "low": {"data_class": "public", "personal_data": "none", "external_transfer": False, "permission": "r",
            "users": 1, "autonomy": "approve_each"},
    "medium": {"data_class": "nonimportant", "personal_data": "general", "external_transfer": False,
               "permission": "r", "users": 500, "autonomy": "approve_each"},
    "high": {"data_class": "nonimportant", "personal_data": "general", "external_transfer": True,
             "permission": "w", "users": 11, "autonomy": "supervised"},
    "very_high": {"data_class": "nonimportant", "personal_data": "sensitive", "external_transfer": True,
                  "permission": "r", "users": 50, "autonomy": "approve_each"},
}


class Cursor:
    def __init__(self, row=None):
        self.row = row

    async def fetchone(self):
        return copy.deepcopy(self.row)


class FakeLedger:
    """approval_events·mcp_intake_requests·principals를 메모리에 두고, 승인 경로가 보내는 문장만 이해한다.
    모르는 문장이 오면 시험이 실패하게 한다(조용히 넘어가지 않는다)."""

    def __init__(self):
        self.events, self.intakes = [], {}
        self.tokens = {token: user["user_id"] for token, user in USERS.items()}

    def add_intake(self, row):
        self.intakes[str(row["id"])] = copy.deepcopy(row)

    def intake(self):
        return self.intakes[str(REQUEST_ID)]

    def kinds(self, kind, outcome=None):
        return [e for e in self.events if e["kind"] == kind and (outcome is None or e["outcome"] == outcome)]

    def _row(self, params):
        return self.intakes[str(params[0])]

    def run(self, sql, params=()):
        s = " ".join(sql.split())
        if s.startswith("SELECT signature_generation FROM local_approvals"):
            return None
        if s.startswith("INSERT INTO approval_events"):
            kind, outcome, target_kind, target_id, actor, applicant, reason, scope = params
            self.events.append({"id": len(self.events) + 1, "kind": kind, "outcome": outcome, "target_kind": target_kind,
                                "target_id": target_id, "actor": actor, "applicant": applicant, "reason": reason,
                                "scope": copy.deepcopy(scope.obj)})
            return {"id": len(self.events)}
        if s.startswith("SELECT pg_advisory_xact_lock"):
            return None
        if s.startswith("SELECT 1 AS found FROM principals WHERE token=%s AND user_id='root'"):
            return {"found": 1} if self.tokens.get(params[0]) == "root" else None
        if s.startswith(("SELECT r.*, p.user_id AS submitter_user_id", "SELECT r.*, p.department",
                         "SELECT * FROM mcp_intake_requests WHERE id")):
            row = self._row(params)
            return {**row, "submitter_user_id": self.tokens.get(row["submitted_by"])}
        if s.startswith("SELECT 1 AS found FROM approval_events WHERE kind='intake-cosign'"):
            rid, actor, sha = params
            return {"found": 1} if any(e["kind"] == "intake-cosign" and e["target_id"] == rid and e["actor"] == actor
                                       and e["scope"].get("input_sha256") == sha for e in self.events) else None
        if s.startswith("SELECT endpoint FROM mcp_runtimes"):
            return {"endpoint": base.CATALOG["endpoint"]}
        if s.startswith(("SELECT lifecycle FROM mcp_servers", "SELECT id, generation, image_id")):
            return None
        if s.startswith("UPDATE mcp_intake_requests SET status='HOLD'"):
            note, rid = params
            row = self.intakes[str(rid)]
            if row["status"] not in ("VALIDATED", "REMOTE_REVIEWED"):
                return None
            row.update(status="HOLD", review_note=note)
            return {"id": rid}
        if s.startswith("UPDATE mcp_intake_requests SET status='APPROVED', internal_repo_url=%s"):  # approve_mcp_request
            url, evidence, by, terms, provenance, rid = params
            row = self.intakes[str(rid)]
            if row["status"] != "VALIDATED":
                return None
            row.update(status="APPROVED", internal_repo_url=url, evidence=copy.deepcopy(evidence.obj), reviewed_by=by,
                       exit_terms=copy.deepcopy(terms.obj), provenance=copy.deepcopy(provenance.obj))
            return {"id": rid, "status": "APPROVED", "internal_repo_url": url, "reviewed_by": by, "reviewed_at": None,
                    "source_ref": row.get("source_ref"), "exit_terms": terms.obj}
        if s.startswith("UPDATE mcp_intake_requests SET status='APPROVED', evidence=%s, reviewed_by=%s"):  # 원격 서비스 승인
            evidence, by, rid, expected = params
            row = self.intakes[str(rid)]
            if row["status"] != "REMOTE_REVIEWED" or row["evidence"] != expected.obj:
                return None
            row.update(status="APPROVED", evidence=copy.deepcopy(evidence.obj), reviewed_by=by)
            return {"id": rid, "status": "APPROVED", "reviewed_by": by, "reviewed_at": None}
        if s.startswith("UPDATE mcp_intake_requests SET status='APPROVED', evidence=%s, provenance=%s, risk_input=%s"):
            evidence, provenance, risk_input, url, by, rid, expected = params  # approve_and_register
            row = self.intakes[str(rid)]
            if row["evidence"] != expected.obj or row["status"] not in ("HOLD", "VALIDATED", "REMOTE_REVIEWED", "APPROVED"):
                return None
            row.update(status="APPROVED", evidence=copy.deepcopy(evidence.obj), provenance=copy.deepcopy(provenance.obj),
                       risk_input=copy.deepcopy(risk_input.obj), internal_repo_url=url, reviewed_by=by)
            return {"id": rid, "status": "APPROVED"}
        if s.startswith("UPDATE mcp_intake_requests SET evidence=%s WHERE id=%s AND evidence=%s"):
            evidence, rid, expected, status = params
            row = self.intakes[str(rid)]
            if row["evidence"] != expected.obj or row["status"] != status:
                return None
            row["evidence"] = copy.deepcopy(evidence.obj)
            return {"id": rid, "status": row["status"]}
        if s.startswith("UPDATE mcp_intake_requests SET registered_server_id"):
            self.intakes[str(params[1])]["registered_server_id"] = params[0]
            return None
        if s.startswith(("UPDATE mcp_tools", "UPDATE mcp_servers", "UPDATE usage_relationships", "INSERT INTO catalog_snapshots",
                         "DELETE FROM supply_chain_reports", "INSERT INTO supply_chain_reports")):
            return None
        raise AssertionError("대역이 모르는 문장: " + s[:120])

    async def fetch_one(self, sql, params=(), *, connection=None):
        return self.run(sql, params)

    async def fetch_all(self, sql, params=(), *, connection=None):
        s = " ".join(sql.split())
        if s.startswith("SELECT token, user_id FROM principals"):
            return [{"token": t, "user_id": self.tokens[t]} for t in params[0] if t in self.tokens]
        if s.startswith("SELECT DISTINCT actor FROM approval_events WHERE kind='intake-cosign'"):
            rid, sha = params
            return [{"actor": a} for a in dict.fromkeys(e["actor"] for e in self.events if e["kind"] == "intake-cosign"
                    and e["target_id"] == rid and e["scope"].get("input_sha256") == sha)]
        raise AssertionError("대역이 모르는 문장: " + s[:120])

    async def execute(self, sql, params=None):
        self.run(sql, params or ())

    @asynccontextmanager
    async def transaction(self, *, connection=None):
        ledger = self

        class Connection:
            async def execute(self, sql, params=None):
                return Cursor(ledger.run(sql, params or ()))

        yield connection if connection is not None else Connection()


def repository_row(tier):
    row = base.row("repository")
    row["risk_input"] = copy.deepcopy(INPUTS[tier])
    return row


@unittest.skipIf(service is None, "게이트웨이 이미지 의존성이 없어 승인 경로 시험을 건너뜀")
class Lab(unittest.IsolatedAsyncioTestCase):
    env_mode = "1"  # ROOT_SOLO_APPROVAL

    @property
    def forced(self):
        """D-306: with the mode on, root carries out an approval alone (its own request, a high tier)."""
        return self.env_mode == "1"

    async def asyncSetUp(self):
        await self.start(self.env_mode)

    async def start(self, env_mode):
        """깨끗한 원장으로 다시 시작한다. 한 시험 안에서 여러 경우를 돌릴 때도 쓴다."""
        self.ledger = FakeLedger()
        self.published, self.registered = [], []
        self.catalog = copy.deepcopy(base.CATALOG)
        environ = patch.dict(os.environ)
        environ.start()
        self.addCleanup(environ.stop)
        os.environ.pop("ROOT_SOLO_APPROVAL", None)
        os.environ.update(local_manifest_keys())
        if env_mode is not None:
            os.environ["ROOT_SOLO_APPROVAL"] = env_mode

        async def identity(authorization):
            return copy.deepcopy(USERS[authorization])

        async def proxy(path, authorization, method="GET", body=None, **kwargs):
            if path == "/api/registry":
                return {"organization": {"jurisdiction_pack_enabled": False}}
            if path.endswith("/discover"):
                return copy.deepcopy(self.catalog)
            assert path == "/api/registry/servers", path
            assert self.ledger.intake()["status"] == "APPROVED"
            self.registered.append(copy.deepcopy(body))
            return {"valid_until": (base.NOW + timedelta(days=90)).isoformat(), "server_id": body["server_id"]}

        async def publish(pending):
            self.published.append(pending["id"])
            return "https://internal.test/docs", {"match": True, "sha256": "c" * 64}

        async def reports(current, *, connection=None):
            return [{"id": i, "scanner": name, "scanner_version": "1", "status": "DONE", "critical_count": 0,
                     "high_count": 0, "summary": {}, "imported_at": base.NOW, "vuln_db_updated_at": base.NOW}
                    for i, name in enumerate(review.SCANNERS)]

        for item in (patch.object(service.db, "fetch_one", self.ledger.fetch_one),
                     patch.object(service.db, "fetch_all", self.ledger.fetch_all),
                     patch.object(service.db, "execute", self.ledger.execute),
                     patch.object(service.db, "transaction", self.ledger.transaction),
                     patch.object(service, "current_identity", identity),
                     patch.object(service, "gateway_proxy", proxy),
                     patch.object(service, "publish_internal_repo", publish),
                     patch.object(review, "lapse_expired_acceptances", AsyncMock(return_value=[])),
                     patch.object(review, "intake_reports", reports),
                     patch.object(review, "active_acceptance", AsyncMock(return_value=None))):
            item.start()
            self.addCleanup(item.stop)

    # ── 경로 1: 개별 승인 ─────────────────────────────────────────────────────
    async def approve(self, token, reason=""):
        return await service.approve_mcp_request(
            REQUEST_ID, service.IntakeApproval(**ASSURANCE, risk_acceptance=reason), token)

    async def refused(self, token, reason="", status=409):
        with self.assertRaises(HTTPException) as caught:
            await self.approve(token, reason)
        self.assertEqual(caught.exception.status_code, status)
        return caught.exception

    def new_request(self, tier, submitted_by="employee"):
        self.ledger.add_intake({**repository_row(tier), "submitted_by": submitted_by})
        self.ledger.tokens.setdefault(submitted_by, submitted_by)
        self.assertEqual(risk_tier.assess(INPUTS[tier])["tier"], tier)

    def new_remote_request(self):
        """계약 검토를 마친 원격 서비스 신청(낮은 등급)."""
        row = base.row("remote-endpoint")
        row.update(status="REMOTE_REVIEWED", risk_input=copy.deepcopy(INPUTS["low"]), submitted_by="employee")
        row["provenance"] = base.intake_proposal.source_record(row, base.CATALOG)
        row["evidence"]["remote_contract"] = {
            "reviewed_by": "tok-b", "valid_until": (base.NOW + timedelta(days=30)).isoformat(), "version": base.CATALOG["version"],
            "advertised_name": base.CATALOG["server_name"], "protocol_version": base.CATALOG["protocol_version"],
            "allowed_principals": ["employee"], "registration": {"catalog_hash": base.CATALOG["catalog_hash"],
                                                                  "tools": {"lookup": "r"}, "data_class": "public"}}
        self.ledger.add_intake(row)
        self.ledger.tokens["employee"] = "employee"

    def approved_scope(self):
        (event,) = self.ledger.kinds("intake-approve", "approved")
        return event["scope"]

    def assert_not_approved(self):
        self.assertEqual(self.ledger.intake()["status"], "VALIDATED")
        self.assertEqual(self.published, [])
        self.assertEqual(self.ledger.kinds("intake-approve", "approved"), [])


class SoloApprovalRoute(Lab):
    """경로 1. 단독 모드 켜짐(현장 기본값)에서 개별 승인."""


    async def test_root_finishes_low_and_medium_alone(self):
        for tier in ("low", "medium"):
            with self.subTest(tier):
                await self.start(self.env_mode)
                self.new_request(tier)
                result = await self.approve("tok-root")
                self.assertEqual(result["request"]["status"], "APPROVED")
                self.assertEqual(self.ledger.intake()["status"], "APPROVED")
                scope = self.approved_scope()
                self.assertEqual((scope["risk_tier"], scope["approvers"]), (tier, ["tok-root"]))
                self.assertEqual(self.published, [REQUEST_ID])

    async def test_root_alone_cannot_finish_high_or_very_high(self):
        for tier, reason in (("high", ""), ("high", REASON), ("very_high", REASON)):
            with self.subTest(tier=tier, reason=bool(reason)):
                await self.start(self.env_mode)
                self.new_request(tier)
                result = await self.approve("tok-root", reason)
                if self.forced:
                    self.assertIsNot(result.get("pending"), True)
                    scope = self.approved_scope()
                    self.assertEqual((scope["approvers"], scope["solo_operator"]), (["tok-root"], True))
                    continue
                self.assertIs(result["pending"], True)
                self.assert_not_approved()
                (cosign,) = self.ledger.kinds("intake-cosign", "recorded")
                self.assertEqual((cosign["actor"], cosign["scope"]["approvers"], cosign["scope"]["tier"]), ("tok-root", 1, tier))

    async def test_very_high_without_a_reason_is_refused_even_for_solo_root(self):
        self.new_request("very_high")
        error = await self.refused("tok-root")
        self.assertIn("위험 수용 사유", error.detail)
        self.assert_not_approved()
        self.assertEqual(self.ledger.kinds("intake-cosign"), [])

    async def test_the_same_root_pressing_again_or_with_another_token_is_still_one_person(self):
        if self.forced:
            self.skipTest("단독 모드의 root는 첫 승인에서 끝난다(D-306)")
        for tier, reason in (("high", ""), ("very_high", REASON)):
            with self.subTest(tier):
                await self.start(self.env_mode)
                self.new_request(tier)
                for token in ("tok-root", "tok-root", "tok-root-2", "tok-root"):
                    self.assertIs((await self.approve(token, reason))["pending"], True)
                self.assert_not_approved()
                for cosign in self.ledger.kinds("intake-cosign"):
                    self.assertEqual(cosign["scope"]["approvers"], 1, cosign["actor"])

    async def test_applicant_cannot_approve_own_request_in_solo_mode(self):
        for tier in ("low", "high"):
            for submitted_by, token in (("tok-root", "tok-root"), ("tok-root", "tok-root-2"), ("tok-emp", "tok-emp"),
                                        ("tok-emp", "tok-emp-2")):
                with self.subTest(tier=tier, applicant=submitted_by, token=token):
                    await self.start(self.env_mode)
                    self.new_request(tier, submitted_by=submitted_by)
                    if self.forced and submitted_by == "tok-root":
                        await self.approve(token)
                        self.assertEqual(self.ledger.intake()["status"], "APPROVED")
                        (forced,) = self.ledger.kinds("intake-approve", "forced")
                        self.assertEqual((forced["actor"], forced["reason"]), (token, "root 강제 집행"))
                        continue
                    error = await self.refused(token, status=403)
                    self.assertIn("본인이 신청한 건", error.detail)
                    self.assert_not_approved()
                    (refused,) = self.ledger.kinds("intake-approve", "refused")
                    self.assertEqual((refused["actor"], refused["applicant"]), (token, submitted_by))
                    self.assertEqual(self.ledger.kinds("intake-cosign"), [])

    async def test_second_administrator_completes_high(self):
        # root finishes alone in single-operator mode, so it is the second one there.
        first, second = ("tok-b", "tok-root") if self.forced else ("tok-root", "tok-b")
        self.new_request("high")
        await self.approve(first)
        await self.approve(second)
        self.assertEqual(self.ledger.intake()["status"], "APPROVED")
        self.assertEqual(self.approved_scope()["approvers"], [second, first])

    async def test_very_high_needs_the_second_administrator_and_a_written_reason(self):
        first, second = ("tok-b", "tok-root") if self.forced else ("tok-root", "tok-b")
        self.new_request("very_high")
        await self.approve(first, REASON)
        await self.refused(second)  # the written reason binds root too
        await self.refused(second, "짧은 사유")
        self.assert_not_approved()
        await self.approve(second, REASON)
        self.assertEqual(self.approved_scope()["approvers"], [second, first])
        self.assertIs(self.ledger.intake()["evidence"]["risk_assessment"]["written_reason"], True)

    async def test_two_tokens_of_one_person_cannot_pass_as_the_second_administrator(self):
        if self.forced:
            self.skipTest("단독 모드의 root는 첫 승인에서 끝난다(D-306)")
        self.new_request("high")
        await self.approve("tok-root")
        self.assertIs((await self.approve("tok-root-2"))["pending"], True)
        self.assert_not_approved()

    async def test_markers_record_the_actual_values_for_the_approver(self):
        # (모드 값, 승인자) -> (solo_mode, solo_operator)
        for env, token, expected in (("1", "tok-root", (True, True)), ("1", "tok-b", (True, False)),
                                     ("0", "tok-root", (False, False)), ("true", "tok-root", (False, False)),
                                     ("", "tok-root", (False, False)), (None, "tok-root", (False, False)),
                                     (None, "tok-b", (False, False))):
            with self.subTest(env=env, token=token):
                await self.start(env)
                self.new_request("low")
                await self.approve(token)
                scope = self.approved_scope()
                self.assertEqual((scope["solo_mode"], scope["solo_operator"]), expected)
                self.assertEqual(self.ledger.intake()["evidence"]["risk_assessment"]["solo_mode"], expected[0])

    async def test_first_approval_markers_are_recorded_on_the_cosign_event(self):
        for env, token, expected in (("1", "tok-root", (True, True)), ("1", "tok-b", (True, False)),
                                     ("0", "tok-root", (False, False)), (None, "tok-b", (False, False))):
            with self.subTest(env=env, token=token):
                await self.start(env)
                self.new_request("high")
                await self.approve(token)
                if env == "1" and token == "tok-root":  # D-306: finished alone, the marks are on the approval
                    scope = self.approved_scope()
                    self.assertEqual((scope["solo_mode"], scope["solo_operator"]), expected)
                    continue
                (cosign,) = self.ledger.kinds("intake-cosign")
                self.assertEqual((cosign["scope"]["solo_mode"], cosign["scope"]["solo_operator"]), expected)

    async def test_second_approver_marker_is_the_second_approvers_own(self):
        await self.start("1")
        self.new_request("high")
        await self.approve("tok-b")  # 첫 승인자는 root가 아니다
        await self.approve("tok-root")  # 마무리하는 사람이 root
        scope = self.approved_scope()
        self.assertEqual((scope["solo_mode"], scope["solo_operator"], scope["approvers"]), (True, True, ["tok-root", "tok-b"]))
        # root 표식이 있어도 승인자는 둘이다: 표식은 사람 수를 바꾸지 않는다.
        self.assertEqual(len(set(scope["approvers"])), 2)

    async def test_remote_service_approval_records_the_marks_too(self):
        for env, token, expected in (("1", "tok-root", (True, True)), ("1", "tok-b", (True, False)),
                                     ("0", "tok-root", (False, False)), (None, "tok-b", (False, False))):
            with self.subTest(env=env, token=token):
                await self.start(env)
                self.new_remote_request()
                await self.approve(token, REASON)  # 종료 조건 증거가 없는 서비스는 서면 위험 수용 사유를 함께 낸다
                scope = self.approved_scope()
                self.assertEqual((scope["solo_mode"], scope["solo_operator"], scope["approvers"]), (*expected, [token]))

    async def test_risk_tier_gate_returns_the_marks_with_the_record(self):
        await self.start("1")
        self.new_request("low")
        row = self.ledger.intake()
        done = await service.risk_tier_gate(REQUEST_ID, row, USERS["tok-root"], "")
        self.assertEqual((done["pending"], done["record"]["solo_mode"], done["record"]["solo_operator"],
                          done["record"]["approvers"]), (False, True, True, ["tok-root"]))
        other = await service.risk_tier_gate(REQUEST_ID, row, USERS["tok-b"], "")
        self.assertEqual((other["record"]["solo_mode"], other["record"]["solo_operator"]), (True, False))


class OneClickLab(Lab):
    """경로 2 도우미. 한 화면 승인(approve_and_register). 위험 등급은 도구·데이터 등급에서 자동 산정된다."""

    async def open_review(self, tier):
        """등급 tier가 되는 신청을 열고 검토 화면(제안)을 돌려준다."""
        kind, grade, description = {
            "low": ("repository", "public", "Search public documentation"),
            "medium": ("remote-endpoint", "public", "Search public documentation"),
            "high": ("remote-endpoint", "important", "Search public documentation"),
            "very_high": ("remote-endpoint", "public", "Search medical records"),
        }[tier]
        row = base.row(kind, grade=grade)
        if kind == "repository":
            row["evidence"]["local_run"] = source_run(row)
        self.ledger.add_intake(row)
        self.ledger.tokens["employee"] = "employee"
        self.catalog["tools"][0]["description"] = description
        shown = await service.preview_intake_approval(REQUEST_ID, service.ApprovalPreview(), USERS["tok-root"], "tok-root")
        self.assertEqual(shown["proposal"]["risk"]["tier"], tier)
        return shown

    def request(self, shown, **kwargs):
        return service.OneClickApproval(proposal_sha256=shown["proposal_sha256"], tools=list(shown["proposal"]["tools"]), **kwargs)

    async def click(self, token, shown, reason=""):
        return await service.approve_and_register(REQUEST_ID, self.request(shown, risk_reason=reason), USERS[token], token)

    async def refused(self, token, shown, reason="", status=422):
        with self.assertRaises(HTTPException) as caught:
            await self.click(token, shown, reason)
        self.assertEqual(caught.exception.status_code, status)
        return caught.exception

    def pending(self):
        return (self.ledger.intake()["evidence"].get("one_click_pending") or {}).get("approvers")


class SoloOneClick(OneClickLab):
    """경로 2. 단독 모드 켜짐에서 한 화면 승인."""

    async def test_root_finishes_low_and_medium_alone(self):
        for tier in ("low", "medium"):
            with self.subTest(tier):
                await self.start(self.env_mode)
                shown = await self.open_review(tier)
                await self.click("tok-root", shown)
                self.assertEqual(len(self.registered), 1)
                self.assertEqual(self.ledger.intake()["evidence"]["risk_assessment"]["approvers"], ["tok-root"])

    async def test_root_alone_cannot_finish_high_or_very_high(self):
        for tier, reason in (("high", ""), ("high", REASON), ("very_high", REASON)):
            with self.subTest(tier=tier, reason=bool(reason)):
                await self.start(self.env_mode)
                shown = await self.open_review(tier)
                result = await self.click("tok-root", shown, reason)
                if self.forced:
                    self.assertEqual(len(self.registered), 1)
                    recorded = self.ledger.intake()["evidence"]["risk_assessment"]
                    self.assertEqual((recorded["approvers"], recorded["solo_operator"]), (["tok-root"], True))
                    continue
                self.assertIs(result["pending"], True)
                self.assertEqual((self.registered, self.ledger.intake()["status"]), ([], "HOLD" if tier != "low" else "VALIDATED"))
                self.assertEqual(self.pending(), ["tok-root"])

    async def test_very_high_without_a_reason_is_refused_even_for_solo_root(self):
        shown = await self.open_review("very_high")
        error = await self.refused("tok-root", shown)
        self.assertIn("위험 수용 사유", error.detail)
        self.assertIsNone(self.pending())
        self.assertEqual(self.registered, [])

    async def test_the_same_root_pressing_again_or_with_another_token_is_still_one_person(self):
        if self.forced:
            self.skipTest("단독 모드의 root는 첫 승인에서 끝난다(D-306)")
        for tier, reason in (("high", ""), ("very_high", REASON)):
            with self.subTest(tier):
                await self.start(self.env_mode)
                shown = await self.open_review(tier)
                for token in ("tok-root", "tok-root", "tok-root-2", "tok-root"):
                    self.assertIs((await self.click(token, shown, reason))["pending"], True)
                self.assertEqual(self.registered, [])
                self.assertEqual(self.pending(), ["tok-root"])

    async def test_applicant_cannot_approve_own_request_in_solo_mode(self):
        for submitted_by, token in (("tok-root", "tok-root"), ("tok-root", "tok-root-2"), ("tok-emp", "tok-emp"),
                                    ("tok-emp", "tok-emp-2")):
            with self.subTest(applicant=submitted_by, token=token):
                await self.start(self.env_mode)
                shown = await self.open_review("medium")
                self.ledger.intake()["submitted_by"] = submitted_by
                self.ledger.tokens.setdefault(submitted_by, submitted_by)
                if self.forced and submitted_by == "tok-root":
                    # The applicant is part of the reviewed proposal: open the review again as the new applicant's request.
                    shown = await service.preview_intake_approval(REQUEST_ID, service.ApprovalPreview(), USERS[token], token)
                    await self.click(token, shown)
                    self.assertEqual(len(self.registered), 1)
                    forced = self.ledger.kinds("intake-one-click", "forced")  # the review screen and the click each say so
                    self.assertTrue(forced and all(e["actor"] == token for e in forced))
                    continue
                error = await self.refused(token, shown, status=403)
                self.assertIn("본인이 신청한 건", error.detail)
                self.assertEqual((self.registered, self.ledger.intake()["status"]), ([], "HOLD"))
                (refused,) = self.ledger.kinds("intake-one-click", "refused")
                self.assertEqual((refused["actor"], refused["applicant"]), (token, submitted_by))

    async def test_second_administrator_completes_high_and_very_high(self):
        for tier, reason in (("high", ""), ("very_high", REASON)):
            with self.subTest(tier):
                await self.start(self.env_mode)
                first, second = ("tok-b", "tok-root") if self.forced else ("tok-root", "tok-b")
                shown = await self.open_review(tier)
                await self.click(first, shown, reason)
                if tier == "very_high":
                    await self.refused(second, shown)  # 두 번째 관리자도 사유를 쓴다
                    await self.refused(second, shown, "짧은 사유")
                    self.assertEqual(self.registered, [])
                await self.click(second, shown, reason)
                self.assertEqual(len(self.registered), 1)
                recorded = self.ledger.intake()["evidence"]["risk_assessment"]
                self.assertEqual((recorded["tier"], recorded["approvers"]), (tier, [first, second]))

    async def test_two_tokens_of_one_person_cannot_pass_as_the_second_administrator(self):
        if self.forced:
            self.skipTest("단독 모드의 root는 첫 승인에서 끝난다(D-306)")
        shown = await self.open_review("high")
        await self.click("tok-root", shown)
        self.assertIs((await self.click("tok-root-2", shown))["pending"], True)
        self.assertEqual(self.registered, [])


class ModeOffApprovalRoute(SoloApprovalRoute):
    """단독 모드가 꺼져 있어도 같은 승인 규칙이 같은 결과를 낸다(표식 값만 시험 안에서 따로 지정)."""
    env_mode = None


class ModeOffOneClick(SoloOneClick):
    env_mode = None


class RegisterServerRoute(OneClickLab):
    """경로 3. core.register_server는 승인 증거(risk_assessment)에서 승인자 수·사유를 다시 확인한다.
    정상 승인으로 만든 요청을 등록 본문으로 쓰고, 증거만 바꿔 가며 등록 함수를 호출한다."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.saved, self.doc = [], {"servers": {}, "contracts": {}, "usage_relationships": [], "history": []}
        self.upstream_tools = [{k: self.catalog["tools"][0][k] for k in ("name", "description", "input_schema", "output_schema",
                                                                           "annotations")}]
        self.catalog["catalog_hash"] = core.canonical_hash(self.upstream_tools)

        async def discover(endpoint, **kwargs):
            return {"version": self.catalog["version"], "advertised_name": self.catalog["server_name"],
                    "protocol_version": self.catalog["protocol_version"], "tools": copy.deepcopy(self.upstream_tools)}

        for item in (patch.object(core.upstream, "discover", discover),
                     patch.object(core.local_jobs, "applicant_device", AsyncMock(return_value="synthetic-device")),
                     patch.object(core.local_jobs, "_device", AsyncMock(return_value={"local_uid": 1001})),
                     patch.object(core.local_jobs, "approve_manifest", AsyncMock()),
                     patch.object(core.upstream, "release_pool", AsyncMock()),
                     patch.object(core.registry, "catalog", lambda: {}),
                     patch.object(core.registry, "reviewed_servers", lambda: {}),
                     patch.object(core.registry, "runtime", lambda: self.doc),
                     patch.object(core.registry, "save_runtime", lambda doc: self.saved.append(copy.deepcopy(doc))),
                     patch.object(core.registry, "sync", AsyncMock()),
                     patch.object(core, "refresh_catalog", AsyncMock(return_value={"status": "PENDING"}))):
            item.start()
            self.addCleanup(item.stop)

    async def approved(self, tier):
        """정상 승인(필요한 사람 수·사유)으로 끝낸 요청과 그 등록 본문."""
        shown = await self.open_review(tier)
        reason = REASON if tier == "very_high" else ""
        await self.click("tok-root", shown, reason)
        if tier in ("high", "very_high"):
            await self.click("tok-b", shown, reason)
        self.assertEqual(self.ledger.intake()["status"], "APPROVED")
        (body,) = self.registered[-1:]
        return body

    def set_evidence(self, **values):
        self.ledger.intake()["evidence"]["risk_assessment"].update(values)

    async def register(self, body):
        return await core.register_server(copy.deepcopy(body), "tok-root")

    async def refuses(self, body, message):
        with self.assertRaises(ValueError) as caught:
            await self.register(body)
        self.assertIn(message, str(caught.exception))
        self.assertEqual((self.saved, self.ledger.kinds("server-register")), ([], []))

    async def test_properly_approved_requests_register(self):
        for tier in ("medium", "high", "very_high"):
            with self.subTest(tier):
                await self.asyncSetUp()
                body = await self.approved(tier)
                result = await self.register(body)
                self.assertEqual(result["server_id"], body["server_id"])
                self.assertEqual(len(self.saved), 1)
                self.assertEqual(len(self.ledger.kinds("server-register", "approved")), 1)

    async def test_high_with_one_person_is_refused_whatever_the_solo_marks_say(self):
        body = await self.approved("high")
        for solo in (True, False, None):
            for approvers in (["tok-root"], ["tok-root", "tok-root"], ["tok-root", "tok-root-2"], []):
                with self.subTest(solo=solo, approvers=approvers):
                    self.set_evidence(approvers=approvers, solo_mode=solo, solo_operator=solo)
                    if solo and approvers and self.forced:
                        continue  # D-306: root's own carry-out in single-operator mode registers (next test)
                    await self.refuses(body, "서로 다른 관리자 두 명")
        # The mark alone is not enough: someone other than root, or the mode off, is still one person.
        for approvers in (["tok-b"], ["tok-emp", "tok-emp-2"]):
            with self.subTest(forged=approvers):
                self.set_evidence(approvers=approvers, solo_mode=True, solo_operator=True)
                await self.refuses(body, "서로 다른 관리자 두 명")

    async def test_root_carry_out_in_single_operator_mode_registers(self):
        body = await self.approved("high")
        self.set_evidence(approvers=["tok-root"], solo_mode=True, solo_operator=True)
        await self.register(body)
        self.assertEqual(len(self.saved), 1)

    async def test_high_with_two_different_administrators_registers(self):
        body = await self.approved("high")
        self.set_evidence(approvers=["tok-root", "tok-b"], solo_mode=True, solo_operator=True)
        await self.register(body)
        self.assertEqual(len(self.saved), 1)

    async def test_the_applicant_never_counts_as_an_approver(self):
        body = await self.approved("high")
        for approvers in (["employee", "tok-b"], ["tok-root", "employee"]):
            with self.subTest(approvers=approvers):
                self.set_evidence(approvers=approvers)
                await self.refuses(body, "신청자는 승인자로 셀 수 없습니다")

    async def test_very_high_needs_the_recorded_reason_as_well_as_two_people(self):
        body = await self.approved("very_high")
        self.set_evidence(written_reason=False)
        await self.refuses(body, "위험 수용 사유")
        self.set_evidence(written_reason=True, approvers=["tok-root"])
        await self.refuses(body, "서로 다른 관리자 두 명")
        self.set_evidence(written_reason=True, approvers=["tok-root", "tok-b"])
        await self.register(body)

    async def test_low_and_medium_register_with_one_approver(self):
        body = await self.approved("medium")
        self.set_evidence(approvers=["tok-root"])
        await self.register(body)
        self.assertEqual(len(self.saved), 1)

    async def test_registration_copies_the_solo_marks_of_the_approval_as_they_were(self):
        body = await self.approved("medium")
        for marks in ((True, True), (True, False), (False, False), (None, None)):
            with self.subTest(marks=marks):
                self.doc.update(servers={}, contracts={}, usage_relationships=[], history=[])
                self.set_evidence(solo_mode=marks[0], solo_operator=marks[1])
                await self.register(body)
                spec = self.saved[-1]["servers"][body["server_id"]]["risk_assessment"]
                self.assertEqual((spec["solo_mode"], spec["solo_operator"]), marks)



if __name__ == "__main__":
    unittest.main(verbosity=2)
