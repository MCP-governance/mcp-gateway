"""DEV-74 automatic employee/server stop state and fail-closed boundary checks."""
from __future__ import annotations

import ast
import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[2]
APP = ROOT / "gateway" / "app"
CORE = (APP / "core.py").read_text(encoding="utf-8")
DISPATCH = (APP / "dispatch.py").read_text(encoding="utf-8")
SUSPEND = (APP / "automatic_suspend.py").read_text(encoding="utf-8")
TABLES = (APP / "ops_tables.sql").read_text(encoding="utf-8")
POLICY = (REPO / "docs" / "ai" / "POLICY.md").read_text(encoding="utf-8")
NOW = datetime(2026, 10, 21, 4, 0, tzinfo=timezone.utc)


class Cursor:
    def __init__(self, row):
        self.row = row

    async def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, decisions=None):
        self.decisions = list(decisions or [])
        self.rows = []
        self.events = []
        self.fail_count = False
        self.insert_lock = asyncio.Lock()

    async def execute(self, query, params=()):
        if "SELECT count(*) AS n FROM decisions" in query:
            if self.fail_count:
                raise OSError("aggregate unavailable")
            user, server, policies, window = params
            cutoff = NOW - timedelta(seconds=window)
            count = sum(1 for d in self.decisions if d["user"] == user and d["server"] == server
                        and d["policy"] in policies and d["created_at"] > cutoff)
            return Cursor({"n": count})
        if "UPDATE user_server_suspensions SET resumed_at=expires_at" in query:
            user, server = params
            row = next((r for r in self.rows if r["user"] == user and r["server"] == server
                        and r["resumed_at"] is None and r["expires_at"] <= NOW), None)
            if not row:
                return Cursor(None)
            row.update(resumed_at=row["expires_at"], resumed_by="automatic", resume_note="자동 중지 기간 만료")
            return Cursor({"id": row["id"], "expires_at": row["expires_at"]})
        if "INSERT INTO user_server_suspensions" in query:
            user, server, duration = params
            async with self.insert_lock:
                await asyncio.sleep(0)
                if any(r["user"] == user and r["server"] == server and r["resumed_at"] is None for r in self.rows):
                    return Cursor(None)
                row = {"id": len(self.rows) + 1, "user": user, "server": server,
                       "expires_at": NOW + timedelta(seconds=duration), "resumed_at": None,
                       "suspended_by": "automatic"}
                self.rows.append(row)
                return Cursor({"id": row["id"], "suspended_at": NOW, "expires_at": row["expires_at"]})
        if "SELECT count(*) FILTER (WHERE i.request_id IS NULL)" in query:
            return Cursor({"unsent": 0, "sent": 0})
        return Cursor(None)


class Checks(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(SUSPEND)
        wanted = {"_expire_locked", "suspend"}
        code = compile(ast.Module(body=[node for node in tree.body
                                        if isinstance(node, ast.AsyncFunctionDef) and node.name in wanted],
                                 type_ignores=[]), "automatic_suspend.py", "exec")
        self.store = FakeConnection()
        async def record_event(kind, outcome, target, target_id, actor, **kwargs):
            self.store.events.append({"kind": kind, "outcome": outcome, "target_id": target_id,
                                      "actor": actor, **kwargs})
        ns = {"TARGET": "user-server-suspension", "review": SimpleNamespace(record_event=record_event)}
        exec(code, ns)
        self.auto_suspend = ns["suspend"]
        self.expire_locked = ns["_expire_locked"]
        self.policies = ("MCP-EGRESS-002", "MCP-DATA-EGRESS-001",
                         "P-DLP-001", "P-CHAIN-001", "P-FLOW-001")
        tree = ast.parse(CORE)
        assigned = next(node for node in tree.body if isinstance(node, ast.Assign)
                        and any(isinstance(target, ast.Name) and target.id == "AUTO_SUSPEND_POLICIES"
                                for target in node.targets))
        self.assertEqual(tuple(ast.literal_eval(assigned.value)), self.policies)

    def block(self, policy, seconds=0):
        self.store.decisions.append({"user": "employee", "server": "wiki", "policy": policy,
                                     "created_at": NOW - timedelta(seconds=seconds)})

    def test_below_threshold_is_not_suspended_and_denial_policy_list_is_narrow(self):
        self.block("MCP-EGRESS-002")
        result = asyncio.run(self.auto_suspend(self.store, "employee", "wiki", self.policies, 2, 600, 900))
        self.assertFalse(result)
        self.assertEqual((self.store.rows, self.store.events), ([], []))
        excluded = ("MCP-EGRESS-001", "P-CONSENT-001", "P-APPROVAL-EXPIRY-001", "MCP-CATALOG-001",
                    "MCP-REGISTRY-001", "ENDPOINT-MANAGED-001", "P-CONTROL-FAIL-CLOSED", "P-SUSPEND-001",
                    "PAC-09", "PAC-10", "PAC-11", "PAC-12")
        self.assertFalse(set(excluded) & set(self.policies))

    def test_threshold_creates_one_d181_state_row_and_complete_automatic_record(self):
        self.block("P-DLP-001")
        self.block("MCP-EGRESS-002")
        result = asyncio.run(self.auto_suspend(self.store, "employee", "wiki", self.policies, 2, 600, 900))
        self.assertTrue(result)
        self.assertEqual(len(self.store.rows), 1)
        event, = self.store.events
        self.assertEqual((event["kind"], event["outcome"], event["actor"]),
                         ("user-server-suspend", "held", "automatic"))
        self.assertEqual({k: event["scope"][k] for k in ("user", "server", "threshold", "violations", "window_seconds")},
                         {"user": "employee", "server": "wiki", "threshold": 2,
                          "violations": 2, "window_seconds": 600})
        self.assertEqual(event["scope"]["expires_at"], (NOW + timedelta(seconds=900)).isoformat())

    def test_old_denial_outside_window_is_excluded(self):
        self.block("P-DLP-001", seconds=601)
        self.block("MCP-EGRESS-002")
        result = asyncio.run(self.auto_suspend(self.store, "employee", "wiki", self.policies, 2, 600, 900))
        self.assertFalse(result)

    def test_non_violation_policy_does_not_count(self):
        self.block("P-CONSENT-001")
        self.block("P-APPROVAL-EXPIRY-001")
        result = asyncio.run(self.auto_suspend(self.store, "employee", "wiki", self.policies, 1, 600, 900))
        self.assertFalse(result)

    def test_expiry_releases_state_and_records_automatic_resume(self):
        self.store.rows.append({"id": 1, "user": "employee", "server": "wiki",
                                "expires_at": NOW - timedelta(seconds=1), "resumed_at": None})
        result = asyncio.run(self.expire_locked(self.store, "employee", "wiki"))
        self.assertTrue(result)
        row = self.store.rows[0]
        self.assertEqual((row["resumed_at"], row["resumed_by"]),
                         (NOW - timedelta(seconds=1), "automatic"))
        self.assertFalse(row["resumed_at"] is None and row["expires_at"] > NOW)
        event, = self.store.events
        self.assertEqual((event["kind"], event["actor"], event["reason"]),
                         ("user-server-resume", "automatic", "자동 중지 기간 만료"))

    def test_aggregate_error_bubbles_for_fail_closed_call_path(self):
        self.store.fail_count = True
        with self.assertRaisesRegex(OSError, "aggregate unavailable"):
            asyncio.run(self.auto_suspend(self.store, "employee", "wiki", self.policies, 1, 600, 900))
        self.assertEqual((self.store.rows, self.store.events), ([], []))
        self.assertIn('"P-CONTROL-FAIL-CLOSED"', CORE)

    def test_dispatch_checks_shared_active_state_and_expiration(self):
        self.assertIn("user_server_suspensions", DISPATCH)
        self.assertIn("x.expires_at > clock_timestamp()", DISPATCH)
        self.assertIn("P-SUSPEND-001", CORE)
        self.assertIn("P-SUSPEND-001", POLICY)
        self.assertRegex(TABLES, r"UNIQUE INDEX IF NOT EXISTS user_server_suspensions_active")

    def test_threshold_window_and_duration_are_environment_settings(self):
        for setting in ("AUTO_SUSPEND_THRESHOLD", "AUTO_SUSPEND_WINDOW_SECONDS", "AUTO_SUSPEND_DURATION_SECONDS"):
            self.assertIn(f'os.getenv("{setting}"', CORE)

    def test_d181_resume_route_and_console_expiry_display_remain_connected(self):
        main = (APP / "main.py").read_text(encoding="utf-8")
        console = (APP / "agent_static" / "console.js").read_text(encoding="utf-8")
        self.assertIn("user_suspend.resume(suspension_id", main)
        self.assertIn("expires_at", console)
        self.assertIn("해제 예정", console)
        self.assertIn("P-SUSPEND-001", POLICY)

    def test_concurrent_threshold_has_one_insert_and_one_event(self):
        self.block("P-DLP-001")
        async def run_pair():
            async def attempt():
                return await self.auto_suspend(self.store, "employee", "wiki", self.policies, 1, 600, 900)
            return await asyncio.gather(attempt(), attempt())
        results = asyncio.run(run_pair())
        self.assertEqual(sum(results), 1)
        self.assertEqual((len(self.store.rows), len(self.store.events)), (1, 1))
        self.assertIn("pg_advisory_xact_lock(hashtext(%s))", CORE)
        self.assertIn("ON CONFLICT (user_token, server_id) WHERE resumed_at IS NULL DO NOTHING", SUSPEND)


if __name__ == "__main__":
    unittest.main(verbosity=2)
