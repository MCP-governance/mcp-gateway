"""Risk tier of an intake request: same input, same tier; approval method per tier; missing input holds;
existing approvals without input get a grace period and then wait for re-approval."""
from __future__ import annotations

import asyncio
import itertools
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gateway"))
from app import risk_tier
try:
    from fastapi import HTTPException
    from app import agent_service, core
except ModuleNotFoundError:
    HTTPException = agent_service = core = None

BASE = {"data_class": "nonimportant", "personal_data": "general", "external_transfer": False,
        "permission": "r", "users": 50, "autonomy": "approve_each"}
REASON = "위험을 알고 수용하는 사유입니다."
REQUEST_ID = "00000000-0000-0000-0000-0000000000a1"
ASSURANCE = {"legal_entity": "Example Provider Ltd.", "supplier_contact": "support@example.test",
             "security_contact": "security@example.test", "support_end": "2030-12-31",
             "vulnerability_policy_url": "https://example.test/security"}


def rank(stated):
    return risk_tier.TIERS.index(risk_tier.assess(stated)["tier"])


class RiskTierPureCheck(unittest.TestCase):
    def test_same_input_gives_same_tier_regardless_of_key_order_and_repetition(self):
        first = risk_tier.assess(BASE)
        for _ in range(50):
            self.assertEqual(risk_tier.assess(dict(reversed(list(BASE.items())))), first)
        self.assertEqual(first["input_sha256"], risk_tier.digest(dict(sorted(BASE.items()))))
        self.assertNotEqual(first["input_sha256"], risk_tier.assess({**BASE, "users": 51})["input_sha256"])

    def test_raising_any_one_answer_never_lowers_the_tier(self):
        scales = {"data_class": ["public", "nonimportant", "important"],
                  "personal_data": ["none", "general", "unique_id", "sensitive"],
                  "external_transfer": [False, True], "permission": ["r", "w", "x"],
                  "users": [1, 10, 11, 100, 101, 1000, 1001], "autonomy": ["approve_each", "supervised", "autonomous"]}
        keys = list(scales)
        checked = 0
        for values in itertools.product(*scales.values()):
            stated = dict(zip(keys, values))
            for key in keys:
                for higher in scales[key][scales[key].index(stated[key]) + 1:]:
                    self.assertGreaterEqual(rank({**stated, key: higher}), rank(stated), (stated, key, higher))
                    checked += 1
        self.assertGreater(checked, 3000)

    def test_user_scale_boundaries(self):
        score = lambda users: risk_tier.assess({**BASE, "users": users})["score"]
        self.assertEqual([score(1), score(10), score(11), score(100), score(101), score(1000), score(1001), score(10_000_000)],
                         [score(1), score(1), score(1) + 1, score(1) + 1, score(1) + 2, score(1) + 2, score(1) + 3, score(1) + 3])

    def test_score_to_tier_boundaries(self):
        cases = [({}, 3, "low"), ({"users": 500}, 4, "medium"),
                 ({"external_transfer": True, "permission": "w", "users": 11}, 7, "medium"),
                 ({"external_transfer": True, "permission": "w", "users": 11, "autonomy": "supervised"}, 8, "high"),
                 ({"personal_data": "unique_id", "external_transfer": True, "permission": "w", "users": 1001}, 11, "high"),
                 ({"personal_data": "unique_id", "external_transfer": True, "permission": "w", "users": 1001,
                   "autonomy": "supervised"}, 12, "very_high")]
        for change, score, tier in cases:
            result = risk_tier.assess({**BASE, **change})
            self.assertEqual((result["score"], result["tier"], result["floors"]), (score, tier, []), change)

    def test_floors_lift_the_tier_whatever_the_sum(self):
        quiet = {**BASE, "data_class": "public", "personal_data": "none", "users": 1}
        self.assertEqual(risk_tier.assess(quiet)["tier"], "low")
        sensitive = risk_tier.assess({**quiet, "personal_data": "sensitive", "external_transfer": True})
        self.assertEqual((sensitive["tier"], sensitive["floors"]), ("very_high", ["민감정보 외부 전송"]))
        self.assertLess(sensitive["score"], 8)
        important = risk_tier.assess({**quiet, "data_class": "important", "external_transfer": True})
        self.assertEqual((important["tier"], important["floors"]), ("high", ["중요 데이터 외부 전송"]))
        autonomous = risk_tier.assess({**quiet, "permission": "x", "autonomy": "autonomous"})
        self.assertEqual((autonomous["tier"], autonomous["floors"]), ("high", ["자율 실행 권한"]))
        self.assertEqual(risk_tier.assess({**quiet, "permission": "x"})["tier"], "low")

    def test_missing_input_gives_no_tier_and_names_what_is_missing(self):
        for key in risk_tier.FIELDS:
            result = risk_tier.assess({k: v for k, v in BASE.items() if k != key})
            self.assertEqual((result["status"], result["tier"], result["score"], result["missing"]), ("hold", None, None, [key]))
            self.assertIn(risk_tier.LABELS[key], result["messages"][0])
        for empty in ({}, None, [], "x", {**BASE, "users": None}):
            result = risk_tier.assess(empty)
            self.assertEqual((result["status"], result["tier"]), ("hold", None))
            self.assertNotIn("input_sha256", result)

    def test_wrong_values_also_hold(self):
        for change in ({"users": 0}, {"users": 10_000_001}, {"users": True}, {"users": "5"}, {"users": 5.5},
                       {"external_transfer": "yes"}, {"external_transfer": 1}, {"permission": "rw"},
                       {"data_class": "secret"}, {"autonomy": None, "extra": 1}, {"unknown": 1}):
            result = risk_tier.assess({**BASE, **change})
            self.assertEqual((result["status"], result["tier"]), ("hold", None), change)
        self.assertIn("값 오류", risk_tier.assess({**BASE, "users": 0})["messages"][0])

    def test_data_class_order_matches_what_registration_compares(self):
        self.assertEqual(list(risk_tier.CHOICES["data_class"]), ["public", "nonimportant", "important"])

    def test_approval_method_per_tier(self):
        decide = risk_tier.decide
        for tier in ("low", "medium"):
            self.assertEqual(decide(tier, 1, "")[0], "approve")
        self.assertEqual(decide("high", 1, "")[0], "cosign")
        self.assertEqual(decide("high", 1, "짧은 사유")[0], "cosign")
        self.assertEqual(decide("high", 1, " " * 6 + "짧은 사유")[0], "cosign")
        self.assertEqual(decide("high", 1, REASON)[0], "approve")
        self.assertEqual(decide("high", 2, "")[0], "approve")
        self.assertEqual(decide("very_high", 2, "")[0], "refuse")
        self.assertEqual(decide("very_high", 1, REASON)[0], "cosign")
        self.assertEqual(decide("very_high", 2, REASON)[0], "approve")
        self.assertIn("매우 높음", decide("very_high", 2, "")[1])
        self.assertIn("1명", decide("high", 1, "")[1])

    def test_existing_approval_without_input_is_assumed_highest_for_thirty_days(self):
        started = "2026-10-20T00:00:00+00:00"
        legacy = {"intake_id": "i-1", "valid_until": "2027-06-01T00:00:00+00:00"}
        day = timedelta(days=1)
        begin = datetime(2026, 10, 20, tzinfo=timezone.utc)
        first = risk_tier.legacy_review(legacy, started, begin)
        self.assertEqual((first["tier"], first["state"], first["days_left"], first["until"]),
                         ("very_high", "grace", 30, "2026-11-19T00:00:00+00:00"))
        last = risk_tier.legacy_review(legacy, started, begin + 30 * day - timedelta(seconds=1))
        self.assertEqual((last["state"], last["days_left"]), ("grace", 1))
        over = risk_tier.legacy_review(legacy, started, begin + 30 * day)
        self.assertEqual((over["state"], over["days_left"]), ("expired", 0))
        self.assertIsNone(risk_tier.legacy_review({**legacy, "risk_assessment": {"tier": "low"}}, started, begin))
        self.assertIsNone(risk_tier.legacy_review({"valid_until": "2027-06-01T00:00:00+00:00"}, started, begin))
        self.assertIsNone(risk_tier.legacy_review(legacy, None, begin))

    def test_renewal_never_passes_the_end_of_the_grace_period(self):
        started = "2026-10-20T00:00:00+00:00"
        legacy = {"intake_id": "i-1"}
        end = datetime(2026, 11, 19, tzinfo=timezone.utc)
        self.assertEqual(risk_tier.cap_until(datetime(2027, 1, 1, tzinfo=timezone.utc), legacy, started), end)
        early = datetime(2026, 11, 1, tzinfo=timezone.utc)
        self.assertEqual(risk_tier.cap_until(early, legacy, started), early)
        later = datetime(2027, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(risk_tier.cap_until(later, {**legacy, "risk_assessment": {"tier": "low"}}, started), later)
        self.assertEqual(risk_tier.cap_until(later, legacy, None), later)

    def test_impact_package_maps_the_stated_input_to_assessment_items(self):
        rows = risk_tier.package({**BASE, "external_transfer": True}, {"display_name": "Example", "purpose": "문서 요약에 씁니다."})
        shown = {row["item"]: row["value"] for row in rows}
        self.assertEqual((shown["처리 대상"], shown["데이터 등급"], shown["처리 개인정보"], shown["외부 전송"], shown["예상 사용자 수"]),
                         ("Example", "내부", "일반 개인정보", "있음", "50명"))
        self.assertEqual((shown["위험 등급"], shown["승인 방식"]), ("보통", "관리자 1명"))
        self.assertTrue(all(row["form"] for row in rows))
        empty = {row["item"]: row["value"] for row in risk_tier.package({}, {})}
        self.assertEqual((empty["위험 등급"], empty["승인 방식"], empty["데이터 등급"]), ("—", "—", "—"))
        very = {row["item"]: row["value"] for row in risk_tier.package(
            {**BASE, "personal_data": "sensitive", "external_transfer": True}, {})}
        self.assertEqual((very["위험 등급"], very["승인 방식"]), ("매우 높음", "관리자 2명 및 위험 수용 사유"))


@unittest.skipIf(agent_service is None, "게이트웨이 이미지 의존성이 없어 승인 경로는 건너뜀")
class RiskTierApprovalCheck(unittest.TestCase):
    def row(self, stated):
        return {"id": REQUEST_ID, "status": "VALIDATED", "commit_sha": "d" * 40, "submitted_by": "emp",
                "submitter_user_id": "user-emp", "display_name": "Example", "intake_kind": "repository",
                "requested_transport": "stdio", "exit_terms": {}, "provenance": {"kind": "source"},
                "repository_url": "https://github.com/example/server", "risk_input": stated}

    def approve(self, stated, *, reason="", earlier=(), same=False, done=None):
        """Runs approve_mcp_request as admin-b with the database replaced; returns (result or error, mocks)."""
        mocks = SimpleNamespace(hold=AsyncMock(), event=AsyncMock(), transition=AsyncMock(return_value={"id": REQUEST_ID}),
                                 publish=AsyncMock(return_value=("http://internal/git/x", {"match": True, "sha256": "e" * 64})))
        gate = AsyncMock(return_value={"blockers": [], "critical": None, "vuln_db": None})

        async def run():
            with patch.object(agent_service, "current_identity", new=AsyncMock(
                    return_value={"roles": ["admin"], "principal": "admin-b", "user_id": "user-b"})), \
                    patch.object(agent_service.review, "lapse_expired_acceptances", new=AsyncMock()), \
                    patch.object(agent_service.db, "fetch_one", new=AsyncMock(side_effect=[self.row(stated), done])), \
                    patch.object(agent_service.db, "fetch_all", new=AsyncMock(return_value=[{"actor": a} for a in earlier])), \
                    patch.object(agent_service.review, "same_person", new=AsyncMock(return_value=same)), \
                    patch.object(agent_service.review, "record_event", new=mocks.event), \
                    patch.object(agent_service.review, "transition", new=mocks.transition), \
                    patch.object(agent_service.review, "intake_gate", new=gate), \
                    patch.object(agent_service, "hold_intake", new=mocks.hold), \
                    patch.object(agent_service, "publish_internal_repo", new=mocks.publish):
                return await agent_service.approve_mcp_request(
                    REQUEST_ID, agent_service.IntakeApproval(**ASSURANCE, risk_acceptance=reason), None)
        try:
            return asyncio.run(run()), mocks
        except HTTPException as exc:
            return exc, mocks

    def test_request_without_stated_input_is_held(self):
        result, mocks = self.approve({})
        self.assertIsInstance(result, HTTPException)
        self.assertEqual(result.status_code, 409)
        self.assertIn("위험 등급 입력 누락", result.detail)
        mocks.hold.assert_awaited_once()
        mocks.transition.assert_not_awaited()

    def test_low_tier_is_approved_by_one_administrator(self):
        result, mocks = self.approve(BASE)
        self.assertEqual(result["message"], "승인하고 사내 저장소에 게시했습니다.")
        scope = mocks.transition.await_args.kwargs["scope"]
        self.assertEqual((scope["risk_tier"], scope["approvers"]), ("low", ["admin-b"]))
        mocks.event.assert_not_awaited()

    def test_high_tier_first_approver_is_recorded_and_the_request_stays_open(self):
        high = {**BASE, "external_transfer": True, "permission": "w", "users": 11, "autonomy": "supervised"}
        result, mocks = self.approve(high)
        self.assertTrue(result["pending"])
        self.assertIn("2명", result["message"])
        mocks.transition.assert_not_awaited()
        mocks.publish.assert_not_awaited()
        args, kwargs = mocks.event.await_args
        self.assertEqual(args[:5], ("intake-cosign", "recorded", "intake", REQUEST_ID, "admin-b"))
        self.assertEqual(kwargs["scope"]["input_sha256"], risk_tier.assess(high)["input_sha256"])

    def test_the_same_person_clicking_twice_is_not_a_second_approver(self):
        high = {**BASE, "external_transfer": True, "permission": "w", "users": 11, "autonomy": "supervised"}
        result, mocks = self.approve(high, earlier=["admin-b"], same=True, done={"found": 1})
        self.assertTrue(result["pending"])
        mocks.event.assert_not_awaited()

    def test_high_tier_second_administrator_completes_it(self):
        high = {**BASE, "external_transfer": True, "permission": "w", "users": 11, "autonomy": "supervised"}
        result, mocks = self.approve(high, earlier=["admin-a"])
        self.assertEqual(result["message"], "승인하고 사내 저장소에 게시했습니다.")
        scope = mocks.transition.await_args.kwargs["scope"]
        self.assertEqual((scope["risk_tier"], scope["approvers"]), ("high", ["admin-b", "admin-a"]))

    def test_high_tier_one_administrator_with_a_written_reason_completes_it(self):
        high = {**BASE, "external_transfer": True, "permission": "w", "users": 11, "autonomy": "supervised"}
        result, mocks = self.approve(high, reason=REASON)
        self.assertEqual(result["message"], "승인하고 사내 저장소에 게시했습니다.")
        mocks.event.assert_not_awaited()

    def test_very_high_tier_needs_the_reason_and_a_second_administrator(self):
        very = {**BASE, "personal_data": "sensitive", "external_transfer": True}
        refused, mocks = self.approve(very, earlier=["admin-a"])
        self.assertIsInstance(refused, HTTPException)
        self.assertIn("위험 수용 사유", refused.detail)
        mocks.transition.assert_not_awaited()
        first, mocks = self.approve(very, reason=REASON)
        self.assertTrue(first["pending"])
        self.assertEqual(mocks.event.await_args.kwargs["reason"], REASON)
        done, mocks = self.approve(very, reason=REASON, earlier=["admin-a"])
        scope = mocks.transition.await_args.kwargs["scope"]
        self.assertEqual((scope["risk_tier"], scope["approvers"]), ("very_high", ["admin-b", "admin-a"]))

    def test_filing_accepts_no_input_but_refuses_an_incomplete_one(self):
        filed = {"display_name": "Example", "repository_url": "https://github.com/example/server",
                 "requested_transport": "stdio", "purpose": "use repository MCP safely"}
        self.assertIsNone(agent_service.McpIntake(**filed).risk_input)
        self.assertEqual(agent_service.McpIntake(**filed, risk_input=BASE).risk_input.users, 50)
        with self.assertRaises(Exception):
            agent_service.McpIntake(**filed, risk_input={"data_class": "public"})
        with self.assertRaises(Exception):
            agent_service.McpIntake(**filed, risk_input={**BASE, "users": 0})

    def test_an_approval_without_input_does_not_block_a_new_request_for_the_same_source(self):
        filed = agent_service.McpIntake(display_name="Example", repository_url="https://github.com/example/server",
                                        requested_transport="stdio", purpose="use repository MCP safely", risk_input=BASE)
        found = AsyncMock(return_value={"id": REQUEST_ID, "status": "APPROVED"})

        async def run():
            with patch.object(agent_service, "current_identity", new=AsyncMock(return_value={"roles": ["employee"], "principal": "emp"})),                     patch.object(agent_service.db, "fetch_one", new=found):
                await agent_service.create_mcp_request(filed, None)
        with self.assertRaises(HTTPException) as refused:
            asyncio.run(run())
        self.assertEqual(refused.exception.status_code, 409)
        sql = found.await_args.args[0]
        self.assertIn("status <> 'APPROVED' OR (intake_kind='repository' AND jsonb_typeof(evidence->'risk_assessment')='object')", sql)

    def test_only_administrators_correct_the_input_and_it_is_recorded(self):
        stated = agent_service.ImpactInput(**BASE)

        async def run(roles):
            with patch.object(agent_service, "current_identity", new=AsyncMock(return_value={"roles": roles, "principal": "admin-b"})), \
                    patch.object(agent_service.review, "transition", new=AsyncMock(return_value={"id": REQUEST_ID})) as transition:
                return await agent_service.set_risk_input(REQUEST_ID, stated, None), transition
        with self.assertRaises(HTTPException) as refused:
            asyncio.run(run(["employee"]))
        self.assertEqual(refused.exception.status_code, 403)
        result, transition = asyncio.run(run(["admin"]))
        self.assertIn("낮음", result["message"])
        self.assertEqual(transition.await_args.kwargs["kind"], "risk-input")
        self.assertEqual(transition.await_args.kwargs["scope"]["input_sha256"], risk_tier.assess(BASE)["input_sha256"])

    def test_list_shows_the_tier_and_counts_only_first_approvals_of_the_current_input(self):
        current = risk_tier.assess(BASE)["input_sha256"]
        rows = [{"id": REQUEST_ID, "risk_input": {**BASE, "personal_data": "sensitive", "external_transfer": True}},
                {"id": "r-2", "risk_input": {}}]
        sensitive = risk_tier.assess(rows[0]["risk_input"])["input_sha256"]
        events = [{"target_id": REQUEST_ID, "actor": "admin-a", "digest": sensitive},
                  {"target_id": REQUEST_ID, "actor": "admin-a", "digest": sensitive},
                  {"target_id": REQUEST_ID, "actor": "admin-c", "digest": current}]
        with patch.object(agent_service.db, "fetch_all", new=AsyncMock(return_value=events)):
            listed = asyncio.run(agent_service.with_risk(rows, counted=True))
        self.assertEqual((listed[0]["risk"]["tier"], listed[0]["risk"]["required"], listed[0]["risk"]["approvals"]),
                         ("very_high", 2, 1))
        self.assertEqual((listed[1]["risk"]["status"], listed[1]["risk"]["tier"], listed[1]["risk"]["approvals"]), ("hold", None, 0))


@unittest.skipIf(core is None, "게이트웨이 이미지 의존성이 없어 기존 승인 유예 경로는 건너뜀")
class RiskGraceCheck(unittest.TestCase):
    def doc(self):
        later = "2027-06-01T00:00:00+00:00"
        return {"servers": {"legacy": {"intake_id": "i-1", "valid_until": later},
                            "assessed": {"intake_id": "i-2", "valid_until": later, "risk_assessment": {"tier": "low"}},
                            "no-intake": {"valid_until": later}},
                "contracts": {}, "usage_relationships": [], "history": []}

    def run_grace(self, doc, now):
        save, sync = MagicMock(), AsyncMock()
        with patch.object(core.registry, "RUNTIME_PATH", Path("servers.json")), \
                patch.object(core.registry, "runtime", return_value=doc), \
                patch.object(core.registry, "save_runtime", save), patch.object(core.registry, "sync", sync):
            capped = asyncio.run(core.apply_risk_grace(now))
        return capped, save, sync

    def test_grace_starts_once_and_caps_only_approvals_without_input(self):
        doc = self.doc()
        begin = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
        capped, save, sync = self.run_grace(doc, begin)
        end = (begin + timedelta(days=30)).isoformat(timespec="seconds")
        self.assertEqual(doc["risk_tier_grace_started_at"], begin.isoformat(timespec="seconds"))
        self.assertEqual([event["type"] for event in capped], ["risk-grace-started", "risk-grace-capped"])
        self.assertEqual(doc["servers"]["legacy"]["valid_until"], end)
        self.assertEqual(doc["servers"]["assessed"]["valid_until"], "2027-06-01T00:00:00+00:00")
        self.assertEqual(doc["servers"]["no-intake"]["valid_until"], "2027-06-01T00:00:00+00:00")
        save.assert_called_once()
        sync.assert_awaited_once()
        capped, save, sync = self.run_grace(doc, begin + timedelta(days=5))
        self.assertEqual(capped, [])
        self.assertEqual(doc["risk_tier_grace_started_at"], begin.isoformat(timespec="seconds"))
        save.assert_not_called()
        sync.assert_not_awaited()

    def test_without_a_runtime_directory_nothing_is_written(self):
        save = MagicMock()
        with patch.object(core.registry, "RUNTIME_PATH", None), patch.object(core.registry, "save_runtime", save):
            self.assertEqual(asyncio.run(core.apply_risk_grace()), [])
        save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
