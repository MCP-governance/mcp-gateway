"""DEV-75 rule and integration-wiring checks; standard library only."""
from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "gateway" / "app"


class Cursor:
    def __init__(self, row=None):
        self.row = row

    async def fetchone(self):
        return self.row


class Connection:
    def __init__(self, last_use=None, event=None, check_event=None, fail=False):
        self.last_use, self.event, self.check_event, self.fail = last_use, event, check_event, fail

    async def execute(self, query, params=None):
        if self.fail and "SELECT max(created_at)" in query:
            raise RuntimeError("aggregate unavailable")
        if "kind=ANY" in query:
            return Cursor(self.event)
        if "kind='tool-sunset-check'" in query:
            return Cursor(self.check_event)
        if "SELECT max(created_at)" in query:
            return Cursor({"last_use": self.last_use})
        if "audit_chain" in query:
            return Cursor({"entries": 0, "retained": 0})
        return Cursor({"ok": True})


class Transaction:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, *args):
        return False


def load_module():
    """Load the production rule module with tiny database ports, not app dependencies."""
    package_name = "tool_sunset_fixture"
    package = types.ModuleType(package_name)
    package.__path__ = []
    package.db = types.SimpleNamespace(transaction=None, fetch_all=AsyncMock())
    package.registry = types.SimpleNamespace(server=lambda _server: {})
    package.retention = types.SimpleNamespace(setting=AsyncMock(return_value={"days": 366}),
                                              current_seal=lambda: None)
    package.review = types.SimpleNamespace(record_event=AsyncMock())
    sys.modules[package_name] = package
    spec = importlib.util.spec_from_file_location(package_name + ".tool_sunset", APP / "tool_sunset.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, package


tool_sunset, ports = load_module()


class ToolSunsetCheck(unittest.TestCase):
    def setUp(self):
        ports.registry.server = lambda _server: {}
        ports.db.transaction = None
        ports.retention.setting = AsyncMock(return_value={"days": 366})
        ports.retention.current_seal = lambda: None
        ports.review.record_event = AsyncMock()

    def test_recent_activity_moves_expiry_and_respects_grace(self):
        now = datetime(2026, 10, 21, tzinfo=timezone.utc)
        result = tool_sunset.evaluate(now - timedelta(days=200), now - timedelta(days=2), now)
        self.assertTrue(result["recent"])
        self.assertFalse(result["expired"])
        self.assertEqual(result["deadline"], now + timedelta(days=118))

    def test_expired_tool_appends_automatic_sunset(self):
        async def run():
            now = datetime(2026, 10, 21, tzinfo=timezone.utc)
            ports.registry.server = lambda _server: {"tool_reviews": {"old": {
                "reviewed_at": (now - timedelta(days=200)).isoformat()}}}
            ports.db.transaction = lambda: Transaction(Connection())
            state = await tool_sunset.check("srv", "old", now)
            self.assertFalse(state["active"])
            args = ports.review.record_event.await_args.args
            self.assertEqual(args[:5], ("tool-sunset", "held", tool_sunset.TARGET, "srv/old", "automatic"))
            self.assertEqual(ports.review.record_event.await_args.kwargs["scope"]["tool"], "old")
            self.assertIsNone(ports.review.record_event.await_args.kwargs["scope"]["last_use"])
        asyncio.run(run())

    def test_recent_window_appends_extension(self):
        async def run():
            now = datetime(2026, 10, 21, tzinfo=timezone.utc)
            last_use = now - timedelta(days=2)
            ports.registry.server = lambda _server: {"tool_reviews": {"used": {
                "reviewed_at": (now - timedelta(days=100)).isoformat()}}}
            ports.db.transaction = lambda: Transaction(Connection(last_use))
            state = await tool_sunset.check("srv", "used", now)
            self.assertTrue(state["active"])
            self.assertTrue(state["recent"])
            self.assertEqual(ports.review.record_event.await_args.args[:2], ("tool-sunset-extension", "approved"))
            self.assertEqual(ports.review.record_event.await_args.args[4], "automatic")
            self.assertEqual(ports.review.record_event.await_args.kwargs["scope"]["last_use"], last_use.isoformat())
        asyncio.run(run())

    def test_missing_retention_window_is_not_counted_as_unused(self):
        async def run():
            now = datetime(2026, 10, 21, tzinfo=timezone.utc)
            ports.registry.server = lambda _server: {"tool_reviews": {"unknown": {
                "reviewed_at": (now - timedelta(days=200)).isoformat()}}}
            ports.db.transaction = lambda: Transaction(Connection())
            ports.retention.setting = AsyncMock(return_value={"days": 60})
            state = await tool_sunset.check("srv", "unknown", now)
            self.assertTrue(state["active"])
            self.assertEqual(state["status"], "자료 없음")
            self.assertEqual(ports.review.record_event.await_args.args[:2], ("tool-sunset-check", "failed"))
        asyncio.run(run())

    def test_aggregation_failure_does_not_deactivate(self):
        async def run():
            now = datetime(2026, 10, 21, tzinfo=timezone.utc)
            ports.registry.server = lambda _server: {"tool_reviews": {"unknown": {
                "reviewed_at": (now - timedelta(days=200)).isoformat()}}}
            ports.db.transaction = lambda: Transaction(Connection(fail=True))
            state = await tool_sunset.check("srv", "unknown", now)
            self.assertTrue(state["active"])
            self.assertFalse(state["available"])
            self.assertEqual(ports.review.record_event.await_args.args[0], "tool-sunset-check")
        asyncio.run(run())

    def test_reapproval_is_an_append_only_human_event(self):
        async def run():
            now = datetime(2026, 10, 21, tzinfo=timezone.utc)
            ports.registry.server = lambda _server: {"tool_reviews": {"old": {
                "reviewed_at": (now - timedelta(days=200)).isoformat()}}}
            ports.db.transaction = lambda: Transaction(Connection())
            expired = await tool_sunset.check("srv", "old", now)
            self.assertFalse(expired["active"])
            await tool_sunset.approve_review("srv", ["old"], "admin-2")
            args = ports.review.record_event.await_args.args
            self.assertEqual(args[:5], ("tool-sunset-review", "approved", tool_sunset.TARGET, "srv/old", "admin-2"))
            ports.registry.server = lambda _server: {"tool_reviews": {"old": {"reviewed_at": now.isoformat()}}}
            reviewed = {"kind": "tool-sunset-review", "outcome": "approved", "scope": {}}
            ports.db.transaction = lambda: Transaction(Connection(event=reviewed))
            restored = await tool_sunset.check("srv", "old", now)
            self.assertTrue(restored["active"])
        asyncio.run(run())

    def test_list_and_call_use_sunset_state_and_existing_policy(self):
        facade = (APP / "mcp_facade.py").read_text(encoding="utf-8")
        core = (APP / "core.py").read_text(encoding="utf-8")
        self.assertIn('await tool_sunset.check(row["server_id"], row["name"])', facade)
        self.assertIn("tool_sunset.listable(sunset)", facade)
        self.assertIn("tool_sunset.call_verdict(sunset)", core)
        self.assertFalse(tool_sunset.listable({"active": False, "available": True}))
        self.assertEqual(tool_sunset.call_verdict({"active": False, "available": True})[0], "P-APPROVAL-EXPIRY-001")
        self.assertEqual(tool_sunset.call_verdict({"active": True, "available": False})[0], "P-CONTROL-FAIL-CLOSED")


if __name__ == "__main__":
    unittest.main()
