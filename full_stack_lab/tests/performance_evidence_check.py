"""Isolated performance query and sample-state checks without PostgreSQL or a running stack."""
import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import AsyncMock


NOW = datetime(2026, 10, 31, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[1] / "gateway/app"


def extract(path, names, scope):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if getattr(n, "name", "") in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), scope)
    return scope


class PerformanceTests(unittest.IsolatedAsyncioTestCase):
    def latency(self, empty=False):
        summary = {"calls": 0 if empty else 4, "dispatched": 0 if empty else 2,
                   **{f"{name}_{p}": None if empty else 12.345
                      for name in ("gateway", "total", "upstream") for p in ("p50", "p95", "p99")}}
        db = SimpleNamespace(admin_fetch_one=AsyncMock(return_value=summary),
             admin_fetch_all=AsyncMock(side_effect=[[] if empty else [
                 {"stage": "call", "n": 2, "p50": 8.0, "p95": 10.0},
                 {"stage": "policy", "n": 4, "p50": 1.0, "p95": 2.0}], [], []]))
        scope = {"db": db, "datetime": SimpleNamespace(now=lambda tz: NOW), "UTC": UTC,
                 "timedelta": timedelta, "UPSTREAM_STAGES": ("connect", "list", "call", "close"),
                 "LATENCY_STAGES": ("policy", "call"), "decommission": SimpleNamespace(REAL_CALL="d.user_token <> 'unknown'")}
        return extract(ROOT / "main.py", {"_compute_latency"}, scope)["_compute_latency"], db

    async def test_all_queries_use_same_measured_window_and_admin_pool(self):
        compute, db = self.latency()
        result = await compute(24)
        self.assertEqual(result["window_end"], NOW.isoformat())
        self.assertEqual(result["window_start"], (NOW - timedelta(days=1)).isoformat())
        self.assertEqual((result["calls"], result["dispatched"]), (4, 2))
        self.assertEqual(result["total"]["p50"], 12.35)
        self.assertEqual([(s["stage"], s["n"]) for s in result["stages"]], [("policy", 4), ("call", 2)])
        self.assertEqual(result["server_sort"], "p95_desc")
        calls = db.admin_fetch_one.call_args_list + db.admin_fetch_all.call_args_list
        for call in calls:
            query, params = call.args
            self.assertEqual(params, (NOW - timedelta(days=1), NOW))
            self.assertIn("event_kind','tools/call')='tools/call'", query)
        server_query = db.admin_fetch_all.call_args_list[1].args[0]
        self.assertIn("ORDER BY p95 DESC NULLS LAST", server_query)
        self.assertIn("d.policy_id = 'MCP-UPSTREAM-001'", server_query)

    async def test_no_measurements_are_not_zero_duration(self):
        compute, _ = self.latency(empty=True)
        result = await compute(24)
        self.assertEqual(result["calls"], 0)
        self.assertIsNone(result["total"]["p50"])
        self.assertIsNone(result["upstream"]["p95"])

    async def test_query_failure_propagates(self):
        compute, db = self.latency()
        db.admin_fetch_one.side_effect = RuntimeError("database unavailable")
        with self.assertRaises(RuntimeError):
            await compute(24)

    async def test_endpoint_recent_expired_unknown_and_failed_samples_keep_provenance(self):
        def sample(identity, measured_at, value=0):
            return {"endpoint_id": identity, "hostname": identity, "measured_at": measured_at,
                    "rtt_p50_ms": value, "rtt_p95_ms": value, "jitter_ms": value,
                    "failure_pct": 100 if value is None else 0, "probes": 6}
        db = SimpleNamespace(fetch_all=AsyncMock(return_value=[
            sample("recent", NOW - timedelta(seconds=30)),
            sample("expired", NOW - timedelta(seconds=181), 99),
            sample("unknown", None, None), sample("failed", NOW, None)]),
            fetch_one=AsyncMock(return_value={}))
        scope = {"db": db, "datetime": SimpleNamespace(now=lambda tz: NOW), "UTC": UTC,
                 "HEARTBEAT_INTERVAL": 60, "Any": Any}
        methods = extract(ROOT / "endpoint_plane.py", {"network_quality", "_round"}, scope)
        result = await methods["network_quality"]()
        rows = {d["endpoint_id"]: d for d in result["devices"]}
        self.assertEqual(rows["recent"]["state"], "fresh")
        self.assertEqual(rows["recent"]["rtt_p50_ms"], 0)
        self.assertEqual(rows["recent"]["probes"], 6)
        self.assertEqual(rows["expired"]["state"], "stale")
        self.assertEqual(rows["unknown"]["state"], "unknown")
        self.assertEqual(rows["failed"]["failure_pct"], 100)
        self.assertIsNone(rows["failed"]["rtt_p50_ms"])
        self.assertEqual(result["checked_at"], NOW.isoformat())


if __name__ == "__main__":
    unittest.main()
