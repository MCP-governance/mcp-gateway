"""Regression checks for root solo approval boundaries; uses only local source and stdlib."""
import ast
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gateway"))
from app import risk_tier  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SERVICE = (ROOT / "gateway/app/agent_service.py").read_text(encoding="utf-8")
REVIEW = (ROOT / "gateway/app/review.py").read_text(encoding="utf-8")
CORE = (ROOT / "gateway/app/core.py").read_text(encoding="utf-8")
CONSOLE = (ROOT / "gateway/app/agent_static/console.js").read_text(encoding="utf-8")
CLI = (ROOT / "console.sh").read_text(encoding="utf-8")


def function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    return ast.get_source_segment(source, node)


class RootSolo(unittest.TestCase):
    def test_mode_is_exact_opt_in_and_only_marks_root_admin(self):
        mode = function_source(REVIEW, "solo_mode_enabled")
        actor = function_source(REVIEW, "solo_operator")
        self.assertIn('os.getenv("ROOT_SOLO_APPROVAL") == "1"', mode)
        self.assertIn('user.get("user_id") == "root"', actor)
        self.assertIn('"admin" in (user.get("roles") or ())', actor)
        for value in ("0", "", "true"):
            with patch.dict(os.environ, {"ROOT_SOLO_APPROVAL": value}):
                self.assertFalse(os.getenv("ROOT_SOLO_APPROVAL") == "1")
        with patch.dict(os.environ, {"ROOT_SOLO_APPROVAL": "1"}):
            self.assertTrue(os.getenv("ROOT_SOLO_APPROVAL") == "1")

    def test_solo_mode_does_not_change_actual_approver_count(self):
        gate = function_source(SERVICE, "risk_tier_gate")
        self.assertIn("approvers = 1 + len(others)", gate)
        self.assertIn("solo_mode, solo = review.solo_mode_enabled(), review.solo_operator(user)", gate)
        self.assertIn('risk_tier.decide(assessed["tier"], approvers, reason)', gate)
        self.assertNotIn("approvers = max(", gate)
        self.assertNotIn("approvers +=", gate)
        self.assertIn('"solo_mode": solo_mode', gate)
        self.assertIn('"solo_operator": solo', gate)
        self.assertIn('"solo_mode": bool(risk_record.get("solo_mode"))', SERVICE)
        self.assertIn('"solo_operator": bool(risk_record.get("solo_operator"))', SERVICE)

    def test_risk_tier_still_requires_second_approver_where_required(self):
        high = risk_tier.decide("high", 1, "")
        high_with_reason = risk_tier.decide("high", 1, "written risk acceptance reason")
        very_high_with_reason = risk_tier.decide("very_high", 1, "written risk acceptance reason")
        very_high_with_two = risk_tier.decide("very_high", 2, "written risk acceptance reason")
        self.assertEqual(high[0], "cosign")
        self.assertEqual(high_with_reason[0], "cosign")  # D-189: a written reason no longer replaces the second administrator
        self.assertEqual(very_high_with_reason[0], "cosign")  # still pending a distinct second approver
        self.assertEqual(very_high_with_two[0], "approve")

    def test_self_approval_guard_is_independent_of_solo_mode(self):
        guard = function_source(REVIEW, "require_independent")
        self.assertIn("if actor == applicant", guard)
        self.assertIn("actor_user == applicant_user", guard)
        self.assertIn('await record_event(kind, "refused"', guard)
        self.assertIn("raise NotIndependent", guard)
        self.assertNotIn("solo_operator", guard)

    def test_mode_is_preserved_in_ledger_and_shown_in_console(self):
        gate = function_source(SERVICE, "risk_tier_gate")
        self.assertIn('"solo_mode": solo_mode', gate)
        self.assertIn('"solo_operator": solo', gate)
        self.assertIn('"solo_mode": bool(risk_record.get("solo_mode"))', SERVICE)
        self.assertIn('"solo_operator": bool(risk_record.get("solo_operator"))', SERVICE)
        self.assertIn("solo_mode", CORE)
        self.assertIn('"승인 방식"', CONSOLE)
        self.assertIn('"단독 운영"', CONSOLE)
        self.assertIn('"일반 운영"', CONSOLE)
        self.assertIn('"—"', CONSOLE)

    def test_field_mode_defaults_on_lab_off_and_account_password_uses_stdin(self):
        lab = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        field = (ROOT / "compose.field.yaml").read_text(encoding="utf-8")
        self.assertNotIn("ROOT_SOLO_APPROVAL", lab)
        self.assertIn("ROOT_SOLO_APPROVAL: ${ROOT_SOLO_APPROVAL:-1}", field)
        self.assertIn("--role 관리자|직원", CLI)
        command = CLI[CLI.index("field_add_account()") : CLI.index("# 설치 권한", CLI.index("field_add_account()"))]
        self.assertIn("read -r -s", command)
        self.assertIn(r'''printf '%s' "$pw" | docker compose''', command)
        self.assertNotIn('echo "$pw"', command)
        self.assertNotIn("PASSWORD=", command)
        self.assertNotIn("TOKEN=", command)


if __name__ == "__main__":
    unittest.main()
