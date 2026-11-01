"""Policy source freshness and final-decision evidence; isolated API tests, no live OPA or DB."""
import ast
import asyncio
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock


def load(core, db, info):
    path = Path(__file__).resolve().parents[1] / "gateway/app/main.py"
    names = {"policy_ledger_view", "policy_deployment_evidence"}
    nodes = [node for node in ast.parse(path.read_text(encoding="utf-8")).body if getattr(node, "name", "") in names]
    assert len(nodes) == 2
    for node in nodes:
        node.decorator_list = []
        if node.name == "policy_ledger_view":
            node.args.defaults = [ast.Constant(None)]
    ns = {"asyncio": asyncio, "datetime": datetime, "UTC": UTC, "timedelta": timedelta,
          "core": core, "db": db, "policy_info": info,
          "organization_policy": SimpleNamespace(catalog=lambda: {"source_state": "available", "policies": []}),
          "httpx": SimpleNamespace(HTTPError=ConnectionError)}
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(path), "exec"), ns)
    return ns


class EvidenceTests(unittest.IsolatedAsyncioTestCase):
    def test_organization_evidence_requires_administrator(self):
        path = Path(__file__).resolve().parents[1] / "gateway/app/main.py"
        node = next(n for n in ast.parse(path.read_text(encoding="utf-8")).body if getattr(n, "name", "") == "policy_ledger_view")
        self.assertEqual(ast.unparse(node.args.defaults[0]), "Depends(admin_caller)")

    def build(self, ledger):
        core = SimpleNamespace(OPA_URL="http://opa", GATEWAY_ENVIRONMENT="prod", ALWAYS_ENFORCED=("MCP-",),
                               opa_document=AsyncMock(side_effect=lambda name: ledger if name == "policy_ledger" else {}))
        db = SimpleNamespace(fetch_one=AsyncMock(return_value=None), fetch_all=AsyncMock(return_value=[
            {"policy_id": "P-1", "count": 2, "last_seen_at": datetime(2026, 10, 31, tzinfo=UTC)}]))
        info = AsyncMock(return_value={"loaded_sha256": "rules", "loaded_data_sha256": "data",
                                       "rules_match": True, "data_match": False})
        return load(core, db, info), db, info

    async def test_loaded_ledger_joins_record_counts_without_claiming_live_enforcement(self):
        ns, db, _ = self.build({"MCP-P2": {"priority": 20}, "P-1": {"priority": 10}})
        out = await ns["policy_ledger_view"]()
        self.assertEqual(out["source_state"], "loaded")
        self.assertEqual([p["policy_id"] for p in out["policies"]], ["P-1", "MCP-P2"])
        self.assertEqual(out["policies"][0]["monitor_behavior"], "eligible")
        self.assertEqual(out["policies"][1]["monitor_behavior"], "protected")
        self.assertEqual(out["policies"][0]["recent"]["count"], 2)
        self.assertEqual(out["policies"][1]["recent"]["count"], 0)
        self.assertNotIn("pol_ids", out["policies"][0])
        query, (since, until) = db.fetch_all.call_args.args
        self.assertIn("GROUP BY policy_id", query)
        self.assertEqual(until - since, timedelta(hours=24))
        self.assertEqual(until.isoformat(), out["checked_at"])

    async def test_missing_source_does_not_reuse_cached_ledger(self):
        for ledger in (None, []):
            ns, _, _ = self.build(ledger)
            out = await ns["policy_ledger_view"]()
            self.assertEqual(out["source_state"], "unavailable")
            self.assertEqual(out["policies"], [])

    async def test_empty_loaded_source_is_distinct_from_failure(self):
        ns, _, _ = self.build({})
        self.assertEqual((await ns["policy_ledger_view"]())["source_state"], "loaded")

    async def test_deployment_unknown_is_distinct_from_mismatch(self):
        ns, _, info = self.build({})
        self.assertEqual(await ns["policy_deployment_evidence"](), {"rules_match": True, "data_match": False})
        info.return_value = {"loaded_sha256": None, "loaded_data_sha256": None}
        self.assertIsNone(await ns["policy_deployment_evidence"]())
        info.side_effect = OSError("missing policy files")
        self.assertIsNone(await ns["policy_deployment_evidence"]())

    async def test_database_failure_never_becomes_zero_activity(self):
        ns, db, _ = self.build({})
        db.fetch_all.side_effect = RuntimeError("database unavailable")
        with self.assertRaises(RuntimeError):
            await ns["policy_ledger_view"]()


if __name__ == "__main__":
    unittest.main()
