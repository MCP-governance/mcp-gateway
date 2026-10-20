"""D-188 root solo approval mode: only root, only when switched on, never self-approval."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gateway"))
from app import review, risk_tier  # noqa: E402

ROOT = {"user_id": "root", "roles": ["admin"], "principal": "root"}


class RootSolo(unittest.TestCase):
    def test_only_root_and_only_when_on(self):
        with patch.dict(os.environ, {"ROOT_SOLO_APPROVAL": "1"}):
            self.assertTrue(review.solo_operator(ROOT))
            self.assertFalse(review.solo_operator({**ROOT, "user_id": "admin1"}))
            self.assertFalse(review.solo_operator({**ROOT, "roles": ["employee"]}))
        for value in ("0", "", "true"):
            with patch.dict(os.environ, {"ROOT_SOLO_APPROVAL": value}):
                self.assertFalse(review.solo_operator(ROOT))
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(review.solo_operator(ROOT))

    def test_solo_count_meets_every_tier_but_keeps_written_reason_rules(self):
        for tier, rule in risk_tier.APPROVAL.items():
            verdict, _ = risk_tier.decide(tier, max(1, rule["approvers"]), "충분히 긴 위험 수용 사유입니다")
            self.assertEqual(verdict, "approve", tier)
            if rule["reason"] == "required":
                self.assertEqual(risk_tier.decide(tier, rule["approvers"], "")[0], "refuse", tier)

    def test_lab_compose_leaves_it_off(self):
        lab = (Path(__file__).resolve().parents[1] / "compose.yaml").read_text(encoding="utf-8")
        field = (Path(__file__).resolve().parents[1] / "compose.field.yaml").read_text(encoding="utf-8")
        self.assertNotIn("ROOT_SOLO_APPROVAL", lab)
        self.assertIn("ROOT_SOLO_APPROVAL: ${ROOT_SOLO_APPROVAL:-1}", field)


if __name__ == "__main__":
    unittest.main()
