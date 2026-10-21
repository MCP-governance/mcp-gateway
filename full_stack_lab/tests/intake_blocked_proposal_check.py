"""A blocked or tool-less intake proposal must not supply a displayed risk tier."""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "gateway"))
from app import risk_tier

source = (LAB / "gateway/app/agent_service.py").read_text(encoding="utf-8")
function = next(node for node in ast.walk(ast.parse(source))
                if isinstance(node, ast.AsyncFunctionDef) and node.name == "with_risk")
scope = {"risk_tier": risk_tier}
exec(compile(ast.Module(body=[function], type_ignores=[]), str(LAB / "gateway/app/agent_service.py"), "exec"), scope)
with_risk = scope["with_risk"]


RISK = {"data_class": "important", "personal_data": "none", "external_transfer": True,
        "permission": "x", "users": 1, "autonomy": "autonomous"}


class BlockedProposalCheck(unittest.IsolatedAsyncioTestCase):
    async def listed(self, proposal):
        row = {"id": "request-1", "risk_input": {}, "evidence": {"approval_proposal": proposal}}
        result = await with_risk([row])
        return result[0]["risk"]

    async def test_blocked_proposal_stays_on_hold_without_approval_count(self):
        shown = await self.listed({"blockers": [{"code": "execution-missing"}], "tools": {"lookup": "r"},
                                   "risk": risk_tier.assess(RISK)})
        self.assertEqual((shown["status"], shown["tier"], shown["required"], shown["approvals"]),
                         ("hold", None, None, 0))

    async def test_proposal_without_tools_stays_on_hold(self):
        shown = await self.listed({"blockers": [], "tools": {}, "risk": risk_tier.assess(RISK)})
        self.assertEqual((shown["status"], shown["tier"], shown["required"]), ("hold", None, None))

    async def test_unblocked_proposal_with_tools_keeps_tier_display(self):
        shown = await self.listed({"blockers": [], "tools": {"lookup": "r"}, "risk": risk_tier.assess(RISK)})
        self.assertEqual((shown["status"], shown["tier"], shown["required"], shown["approvals"]),
                         ("ok", "high", 2, 0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
