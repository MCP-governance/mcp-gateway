"""D-177 untested branches and real gateway wiring checks."""
from __future__ import annotations

import asyncio
import ast
from contextlib import ExitStack
import importlib.util
import logging
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "gateway" / "app"
NOW = datetime(2026, 10, 21, tzinfo=timezone.utc)


class Cursor:
    def __init__(self, row=None):
        self.row = row

    async def fetchone(self):
        return self.row


class Connection:
    def __init__(self, *, event=None, entries=0, retained=0):
        self.event, self.entries, self.retained = event, entries, retained

    async def execute(self, query, params=None):
        if "kind=ANY" in query:
            return Cursor(self.event)
        if "audit_chain" in query:
            return Cursor({"entries": self.entries, "retained": self.retained})
        return Cursor(None)


class Transaction:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, *args):
        return False


def load_sunset():
    package_name = "tool_sunset_paths_fixture"
    package = types.ModuleType(package_name)
    package.__path__ = []
    package.db = types.SimpleNamespace(transaction=None, fetch_all=AsyncMock())
    package.registry = types.SimpleNamespace(server=lambda _server: {})
    package.retention = types.SimpleNamespace(
        setting=AsyncMock(return_value={"days": 366}), current_seal=lambda: None)
    package.review = types.SimpleNamespace(record_event=AsyncMock())
    sys.modules[package_name] = package
    spec = importlib.util.spec_from_file_location(package_name + ".tool_sunset", APP / "tool_sunset.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, package


tool_sunset, ports = load_sunset()


def load_function(path, function_name, namespace):
    source = ast.parse(path.read_text(encoding="utf-8"))
    function = next(node for node in source.body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name)
    module = ast.Module(body=[function], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(path), "exec"), namespace)
    return namespace[function_name]


class ToolSunsetBranchCheck(unittest.TestCase):
    def setUp(self):
        ports.registry.server = lambda _server: {"tool_reviews": {"old": {
            "reviewed_at": (NOW - timedelta(days=200)).isoformat()}}}
        ports.db.transaction = lambda: Transaction(Connection())
        ports.db.fetch_all = AsyncMock(return_value=[])
        ports.retention.setting = AsyncMock(return_value={"days": 366})
        ports.retention.current_seal = lambda: None
        ports.review.record_event = AsyncMock()

    def test_held_sunset_is_still_inactive_before_a_review_event(self):
        event = {"kind": "tool-sunset", "outcome": "held", "scope": {
            "last_use": None, "deadline": (NOW - timedelta(days=1)).isoformat()}}
        ports.db.transaction = lambda: Transaction(Connection(event=event))
        state = asyncio.run(tool_sunset.check("srv", "old", NOW))
        self.assertFalse(state["active"])
        self.assertEqual(state["status"], "재심사 필요")
        ports.review.record_event.assert_not_awaited()

    def test_seal_overlap_returns_no_evidence(self):
        ports.retention.current_seal = lambda: {"last_created_at": NOW.isoformat()}
        state = asyncio.run(tool_sunset.check("srv", "old", NOW))
        self.assertTrue(state["active"])
        self.assertEqual(state["status"], "자료 없음")
        self.assertEqual(state["reason"], "관측 창 일부가 폐기된 원장 구간과 겹칩니다.")
        self.assertEqual(ports.review.record_event.await_args.args[:2], ("tool-sunset-check", "recorded"))

    def test_seal_count_mismatch_returns_no_evidence(self):
        ports.db.transaction = lambda: Transaction(Connection(entries=12, retained=11))
        state = asyncio.run(tool_sunset.check("srv", "old", NOW))
        self.assertTrue(state["active"])
        self.assertEqual(state["status"], "자료 없음")
        self.assertEqual(state["reason"], "원장 봉인 자료를 확인할 수 없습니다.")
        self.assertEqual(ports.review.record_event.await_args.args[:2], ("tool-sunset-check", "recorded"))


class ToolSunsetListIsolationCheck(unittest.TestCase):
    def test_failed_status_hides_only_one_tool_and_preserves_call_verdicts(self):
        rows = [
            {"server_id": "srv", "name": name, "action": "r", "description": name,
             "input_schema": {"type": "object"}, "output_schema": None, "display_name": "server"}
            for name in ("a", "b")
        ]

        class Tool:
            def __init__(self, **values):
                self.__dict__.update(values)

        async def fetch_all(*_args):
            return rows

        async def fetch_one(*_args):
            return {"role": "user"}

        async def status(_server, name):
            return {"active": True, "available": name != "a"}

        namespace = {
            "types": types.SimpleNamespace(Tool=Tool),
            "db": types.SimpleNamespace(fetch_all=fetch_all, fetch_one=fetch_one),
            "registry": types.SimpleNamespace(permits=lambda allowed, token: allowed is None or "*" in allowed or token in allowed, ALL_PRINCIPALS="*", allowed_principals=lambda _server: None,
                                              reviewed_tools=lambda _server: {"a", "b"}),
            "tool_sunset": types.SimpleNamespace(check=status, listable=tool_sunset.listable),
            "pac": types.SimpleNamespace(visible=lambda *_args: True),
            "output_contract": types.SimpleNamespace(JSON_PROTOCOLS=set(), OBJECT_PROTOCOLS=set()),
            "SEPARATOR": "__", "logger": logging.getLogger("test.mcp_facade"),
        }
        function_name = "_approved_tools"
        approved_tools = load_function(APP / "mcp_facade.py", function_name, namespace)
        with self.assertLogs("test.mcp_facade", level="ERROR") as logs:
            result = asyncio.run(approved_tools("user", principal="employee"))

        self.assertEqual([item.name for item in result], ["srv__b"])
        self.assertTrue(any("srv/a" in line for line in logs.output))
        self.assertEqual(tool_sunset.call_verdict({"active": True, "available": False})[0],
                         "P-CONTROL-FAIL-CLOSED")
        self.assertIsNone(tool_sunset.call_verdict({"active": True, "available": True}))


try:
    sys.path.insert(0, str(ROOT / "gateway"))
    from app import core, mcp_facade, endpoint_plane  # noqa: E402
    APP_IMPORT_ERROR = None
except Exception as exc:  # Missing application dependencies are reported as skipped integration cases.
    core = mcp_facade = endpoint_plane = None
    APP_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"


@unittest.skipIf(APP_IMPORT_ERROR, f"gateway integration dependencies unavailable: {APP_IMPORT_ERROR}")
class ToolSunsetIntegrationCheck(unittest.TestCase):
    def test_real_tools_list_hides_inactive_tool_and_keeps_active_tool(self):
        rows = [
            {"server_id": "srv", "name": "old", "action": "r", "description": "old tool",
             "input_schema": {"type": "object"}, "output_schema": None, "display_name": "server"},
            {"server_id": "srv", "name": "ok", "action": "r", "description": "active tool",
             "input_schema": {"type": "object"}, "output_schema": None, "display_name": "server"},
        ]
        states = {"old": {"active": False, "available": True}, "ok": {"active": True, "available": True}}
        with patch.object(mcp_facade.db, "fetch_all", AsyncMock(return_value=rows)), \
             patch.object(mcp_facade.db, "fetch_one", AsyncMock(return_value={"role": "user"})), \
             patch.object(mcp_facade.registry, "allowed_principals", return_value=None), \
             patch.object(mcp_facade.registry, "reviewed_tools", return_value={"old", "ok"}), \
             patch.object(mcp_facade.pac, "visible", return_value=True), \
             patch.object(mcp_facade.tool_sunset, "check", AsyncMock(side_effect=lambda _s, t: states[t])):
            result = asyncio.run(mcp_facade._approved_tools("user", principal="employee"))
        self.assertEqual([item.name for item in result], ["srv__ok"])

    def test_failed_status_lookup_hides_only_that_tool_and_keeps_other_callable(self):
        rows = [
            {"server_id": "srv", "name": name, "action": "r", "description": name,
             "input_schema": {"type": "object"}, "output_schema": None, "display_name": "server"}
            for name in ("a", "b")
        ]

        async def state(_server, name):
            return ({"active": True, "available": False} if name == "a" else
                    {"active": True, "available": True})

        with patch.object(mcp_facade.db, "fetch_all", AsyncMock(return_value=rows)), \
             patch.object(mcp_facade.db, "fetch_one", AsyncMock(return_value={"role": "user"})), \
             patch.object(mcp_facade.registry, "allowed_principals", return_value=None), \
             patch.object(mcp_facade.registry, "reviewed_tools", return_value={"a", "b"}), \
             patch.object(mcp_facade.pac, "visible", return_value=True), \
             patch.object(mcp_facade.tool_sunset, "check", AsyncMock(side_effect=state)), \
             self.assertLogs("app.mcp_facade", level="ERROR") as logs:
            result = asyncio.run(mcp_facade._approved_tools("user", principal="employee"))

        self.assertEqual([item.name for item in result], ["srv__b"])
        self.assertTrue(any("srv/a" in line for line in logs.output))
        self.assertEqual(tool_sunset.call_verdict({"active": True, "available": False})[0],
                         "P-CONTROL-FAIL-CLOSED")
        self.assertIsNone(tool_sunset.call_verdict({"active": True, "available": True}))

    def test_unavailable_tool_call_blocks_and_active_tool_reaches_upstream(self):
        classified = types.SimpleNamespace(
            data_class="public", action="r", primary=types.SimpleNamespace(id="resource", kind="record",
                                                                             owner_department=None),
            destinations=[], resources=[], dlp=[], notes=[], base_action="r", restrictable=False,
            summary=lambda: {},
        )
        principal = {"token": "employee", "role": "user", "status": "active", "synthetic": False,
                    "server_suspended": False, "department": None}

        async def return_event(event, _laps):
            return event

        async def sunset_status(_server, name):
            return {"active": True, "available": name != "a"}

        with ExitStack() as stack:
            patches = [
                patch.object(core.classify, "classify", return_value=classified),
                patch.object(core.user_suspend, "expire", AsyncMock()),
                patch.object(core.db, "fetch_one", AsyncMock(side_effect=[principal, principal, None])),
                patch.object(core, "policy_ledger", AsyncMock()),
                patch.object(core.registry, "server", return_value={"ok": True}),
                patch.object(core.registry, "allowed_principals", return_value=["employee"]),
                patch.object(endpoint_plane, "managed_failure", AsyncMock(return_value=None)),
                patch.object(core.tool_sunset, "check", AsyncMock(side_effect=sunset_status)),
                patch.object(core, "_reserve_call", AsyncMock(return_value={})),
                patch.object(core, "_sequence_flags", AsyncMock(return_value=[])),
                patch.object(core, "_flow_sources", AsyncMock(return_value=[])),
                patch.object(core, "_contract", AsyncMock(return_value={})),
                patch.object(core, "_relationship_scope", AsyncMock(return_value={})),
                patch.object(endpoint_plane, "shadow_count_for", AsyncMock(return_value=0)),
                patch.object(endpoint_plane, "shadow_listener_count_for", AsyncMock(return_value=0)),
                patch.object(core.pac, "build", AsyncMock(return_value={})),
                patch.object(core, "_policy", AsyncMock(return_value={
                    "decision": "Allow", "policy_id": "P-AUTHZ-ALLOW-001", "reason": "allowed", "conflicts": []})),
                patch.object(core, "enforcement_mode", AsyncMock(return_value="enforce")),
                patch.object(core.classify, "apply_restrictions", return_value=({}, [])),
                patch.object(core.db, "execute", AsyncMock(return_value=1)),
                patch.object(core, "_call_upstream", AsyncMock(return_value={"content": []})),
                patch.object(core, "_inspected_result", AsyncMock(return_value=({"content": []}, []))),
                patch.object(core, "_validate_output"),
                patch.object(core, "_guarded_result", return_value={"content": []}),
                patch.object(core, "_decision_payload", AsyncMock(side_effect=return_event)),
            ]
            for context in patches:
                stack.enter_context(context)
            call_upstream = core._call_upstream
            blocked = asyncio.run(core.execute_call({"server_id": "srv", "tool": "a", "arguments": {},
                                                     "user_token": "employee"}))
            allowed = asyncio.run(core.execute_call({"server_id": "srv", "tool": "b", "arguments": {},
                                                     "user_token": "employee"}))

        self.assertEqual((blocked["decision"], blocked["policy_id"]), ("Block", "P-CONTROL-FAIL-CLOSED"))
        self.assertTrue(allowed["upstream_executed"])
        call_upstream.assert_awaited_once()

    def test_real_execute_call_blocks_inactive_tool(self):
        classified = types.SimpleNamespace(
            data_class="public", action="r", primary=types.SimpleNamespace(id="resource"), destinations=[],
            resources=[], dlp=[], notes=[], base_action="r", summary=lambda: {})
        principal = {"token": "employee", "role": "user", "status": "active", "server_suspended": False}
        sunset_state = {"active": False, "available": True}

        async def return_event(event, _laps):
            return event

        with patch.object(core.classify, "classify", return_value=classified), \
             patch.object(core.user_suspend, "expire", AsyncMock()), \
             patch.object(core.db, "fetch_one", AsyncMock(return_value=principal)), \
             patch.object(core, "policy_ledger", AsyncMock()), \
             patch.object(core.registry, "server", return_value={"ok": True}), \
             patch.object(core.registry, "allowed_principals", return_value=["employee"]), \
             patch.object(endpoint_plane, "managed_failure", AsyncMock(return_value=None)), \
             patch.object(core.tool_sunset, "check", AsyncMock(return_value=sunset_state)), \
             patch.object(core, "_decision_payload", AsyncMock(side_effect=return_event)):
            result = asyncio.run(core.execute_call({"server_id": "srv", "tool": "old", "user_token": "employee"}))
        self.assertEqual((result["decision"], result["policy_id"]), ("Block", "P-APPROVAL-EXPIRY-001"))


if __name__ == "__main__":
    unittest.main()
