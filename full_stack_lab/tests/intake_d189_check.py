"""D-189: high needs two different administrators; very high needs two different administrators and a written reason.

One-click approval, separate approval and registration apply the same rule. Runs with the doubles of
intake_one_click_check; the gateway image dependencies are required for the approval-route cases."""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import intake_one_click_check as base

LAB = HERE.parent
sys.path.insert(0, str(LAB / "gateway"))
from app import risk_tier

REASON = "민감 의료 정보를 외부에서 다루는 위험을 알고 수용합니다."
SECOND = {"principal": "admin-b", "user_id": "admin-b", "roles": ["admin"]}


def function_source(name: str) -> str:
    text = (LAB / "gateway/app/core.py").read_text(encoding="utf-8")
    node = next(n for n in ast.walk(ast.parse(text)) if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
    return ast.get_source_segment(text, node)


class TableCheck(unittest.TestCase):
    def test_table_is_the_decided_one(self):
        self.assertEqual({tier: (rule["approvers"], rule["reason"]) for tier, rule in risk_tier.APPROVAL.items()},
                         {"low": (1, "none"), "medium": (1, "none"), "high": (2, "none"), "very_high": (2, "required")})

    def test_a_reason_never_replaces_an_approver(self):
        for tier in ("high", "very_high"):
            self.assertEqual(risk_tier.decide(tier, 1, REASON)[0], "cosign")
            self.assertEqual(risk_tier.decide(tier, 2, REASON)[0], "approve")
        self.assertEqual(risk_tier.decide("high", 2, "")[0], "approve")
        self.assertEqual(risk_tier.decide("very_high", 2, "")[0], "refuse")
        self.assertEqual(risk_tier.decide("very_high", 2, "  짧은 사유  ")[0], "refuse")

    def test_the_displayed_method_is_the_enforced_one(self):
        for tier, text in (("low", "관리자 1명"), ("medium", "관리자 1명"), ("high", "관리자 2명"),
                           ("very_high", "관리자 2명 및 위험 수용 사유")):
            stated = {"low": {"data_class": "public", "personal_data": "none", "external_transfer": False, "permission": "r",
                              "users": 1, "autonomy": "approve_each"}}.get("low")
            if tier != "low":
                stated = {"medium": {**stated, "data_class": "nonimportant", "permission": "w", "users": 50},
                          "high": {**stated, "data_class": "important", "external_transfer": True},
                          "very_high": {**stated, "personal_data": "sensitive", "external_transfer": True}}[tier]
            self.assertEqual(risk_tier.assess(stated)["tier"], tier)
            shown = {row["item"]: row["value"] for row in risk_tier.package(stated, {})}["승인 방식"]
            self.assertEqual(shown, text)

    def test_registration_repeats_both_conditions(self):
        source = function_source("register_server")
        self.assertIn('rule = risk_tier.APPROVAL[stated["tier"]]', source)
        self.assertIn('len(approvers) < rule["approvers"]', source)
        self.assertIn('rule["reason"] == "required" and not approved_risk.get("written_reason")', source)


@unittest.skipIf(base.service is None, "Gateway image required: " + globals().get("IMPORT_ERROR", ""))
class OneClickVeryHighCheck(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = base.ApprovalFlowCheck.asyncSetUp
    preview = base.ApprovalFlowCheck.preview
    approval = base.ApprovalFlowCheck.approval

    async def very_high(self):
        self.catalog["tools"][0]["description"] = "Search medical records"
        preview = await self.preview()
        self.assertEqual(preview["proposal"]["risk"]["tier"], "very_high")
        return preview

    async def test_no_reason_is_refused_before_anything_is_recorded(self):
        preview = await self.very_high()
        with self.assertRaises(base.HTTPException) as error:
            await base.service.approve_and_register(base.REQUEST_ID, self.approval(preview), self.admin, "console-token")
        self.assertEqual(error.exception.status_code, 422)
        self.assertIn("위험 수용 사유", error.exception.detail)
        self.assertNotIn("one_click_pending", self.state["evidence"])
        self.assertEqual(self.registered, [])

    async def test_one_administrator_with_a_reason_only_waits(self):
        preview = await self.very_high()
        first = await base.service.approve_and_register(
            base.REQUEST_ID, self.approval(preview, risk_reason=REASON), self.admin, "console-token")
        self.assertTrue(first["pending"])
        self.assertEqual(self.registered, [])
        self.assertEqual(self.state["evidence"]["one_click_pending"]["risk_reasons"], {"admin-a": REASON})

    async def test_second_administrator_needs_a_reason_too_and_completes_it_with_one(self):
        preview = await self.very_high()
        await base.service.approve_and_register(
            base.REQUEST_ID, self.approval(preview, risk_reason=REASON), self.admin, "console-token")
        base.service.current_identity.return_value = SECOND
        with self.assertRaises(base.HTTPException) as error:
            await base.service.approve_and_register(base.REQUEST_ID, self.approval(preview), SECOND, "console-token")
        self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(self.registered, [])
        await base.service.approve_and_register(
            base.REQUEST_ID, self.approval(preview, risk_reason=REASON), SECOND, "console-token")
        self.assertEqual(len(self.registered), 1)
        recorded = self.state["evidence"]["risk_assessment"]
        self.assertEqual((recorded["tier"], recorded["approvers"], recorded["written_reason"]),
                         ("very_high", ["admin-a", "admin-b"], True))
        self.assertEqual(recorded["reasons"], {"admin-a": REASON, "admin-b": REASON})

    async def test_the_same_person_with_a_reason_is_still_one_approver(self):
        preview = await self.very_high()
        request = self.approval(preview, risk_reason=REASON)
        await base.service.approve_and_register(base.REQUEST_ID, request, self.admin, "console-token")
        again = await base.service.approve_and_register(
            base.REQUEST_ID, request, {**self.admin, "principal": "admin-alias"}, "console-token")
        self.assertTrue(again["pending"])
        self.assertEqual(self.registered, [])

    async def test_high_tier_needs_no_reason_and_a_reason_does_not_help(self):
        self.state = base.row(grade="important")
        preview = await self.preview()
        self.assertEqual(preview["proposal"]["risk"]["tier"], "high")
        first = await base.service.approve_and_register(
            base.REQUEST_ID, self.approval(preview, risk_reason=REASON), self.admin, "console-token")
        self.assertTrue(first["pending"])
        base.service.current_identity.return_value = SECOND
        await base.service.approve_and_register(base.REQUEST_ID, self.approval(preview), SECOND, "console-token")
        self.assertEqual(len(self.registered), 1)
        self.assertEqual(self.state["evidence"]["risk_assessment"]["reasons"], {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
