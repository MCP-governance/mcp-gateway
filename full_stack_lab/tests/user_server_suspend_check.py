"""DEV-79 per-employee, per-server stop: unit checks with DB doubles, not PostgreSQL or real MCP evidence.

Standard library only. Production definitions are loaded by AST (no optional Gateway imports); the dispatch
race reuses the interleaving harness of dispatch_recheck_check. SQL is matched by text, never run: the
statements themselves are exercised on the device (see the report).
"""
from __future__ import annotations

import ast
import asyncio
from contextlib import asynccontextmanager, nullcontext
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import time
from types import ModuleType, SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch
import uuid

HERE = Path(__file__).resolve().parent
APP = HERE.parent / "gateway" / "app"
if not APP.exists():
    APP = Path("/app/app")
sys.path.insert(0, str(HERE))
import dispatch_recheck_check as recheck  # noqa: E402  (same directory)

NOW = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)
OUTCOMES = {"recorded", "approved", "rejected", "refused", "held"}  # approval_events CHECK


def production(filename, names, namespace):
    tree = ast.parse((APP / filename).read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if getattr(n, "name", None) in names or
             isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in n.targets)]
    if len(nodes) != len(names):
        raise AssertionError("missing production definitions")
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(APP / filename), "exec"), namespace)
    return NS(**namespace)


def cursor(row=None):
    return NS(fetchone=AsyncMock(return_value=row))


class Store:
    """State rows and approval_events with commit/rollback. A statement is recognised by its text."""

    def __init__(self):
        self.users, self.servers = {"emp-a", "emp-b"}, {"gitea", "filesystem"}
        self.rows, self.events, self.flight = [], [], {}
        self.fail_commit, self.first_statements = False, []

    @asynccontextmanager
    async def transaction(self):
        tx = NS(rows=[], resumed=[], events=[], statements=[])

        async def execute(query, params=()):
            return await self.statement(tx, " ".join(query.split()), params)
        try:
            yield NS(execute=execute)
            if self.fail_commit:
                raise OSError("injected commit failure")
        finally:
            self.first_statements = tx.statements
        self.rows.extend(tx.rows)
        for row, fields in tx.resumed:
            row.update(fields)
        self.events.extend(tx.events)

    def active(self, tx, user, server):
        return [r for r in self.rows + tx.rows if (r["user_token"], r["server_id"]) == (user, server)
                and r["resumed_at"] is None and all(r is not x for x, _ in tx.resumed)]

    async def statement(self, tx, query, params):
        tx.statements.append(query)
        if "pg_advisory_xact_lock" in query:
            return cursor()
        if "FROM principals WHERE token" in query:
            return cursor({"x": 1} if params[0] in self.users else None)
        if "FROM mcp_servers WHERE id" in query:
            return cursor({"x": 1} if params[0] in self.servers else None)
        if query.startswith("SELECT user_token, server_id FROM user_server_suspensions"):
            found = next((row for row in self.rows if row["id"] == params[0] and row["resumed_at"] is None), None)
            return cursor({"user_token": found["user_token"], "server_id": found["server_id"]} if found else None)
        if query.startswith("INSERT INTO user_server_suspensions"):
            user, server, reason, actor = params
            if self.active(tx, user, server):
                return cursor(None)
            row = {"id": len(self.rows) + len(tx.rows) + 1, "user_token": user, "server_id": server, "reason": reason,
                   "suspended_by": actor, "suspended_at": NOW, "resumed_at": None}
            tx.rows.append(row)
            return cursor({"id": row["id"], "suspended_at": NOW})
        if "FROM call_reservations r LEFT JOIN dispatch_intents" in query:
            unsent, sent = self.flight.get(params, (0, 0))
            return cursor({"unsent": unsent, "sent": sent})
        if query.startswith("UPDATE user_server_suspensions"):
            actor, note, found = params
            for row in self.rows:
                if row["id"] == found and row["resumed_at"] is None and all(row is not x for x, _ in tx.resumed):
                    tx.resumed.append((row, {"resumed_at": NOW, "resumed_by": actor, "resume_note": note}))
                    return cursor({"id": row["id"], "user_token": row["user_token"], "server_id": row["server_id"]})
            return cursor(None)
        if query.startswith("INSERT INTO approval_events(kind,outcome,target_kind,target_id,actor,applicant,reason,scope)"):
            kind, outcome, target_kind, target_id, actor, applicant, reason, scope = params
            assert outcome in OUTCOMES, "approval_events CHECK would roll this back"
            tx.events.append({"id": len(self.events) + len(tx.events) + 1, "kind": kind, "outcome": outcome,
                              "target_kind": target_kind, "target_id": target_id, "actor": actor,
                              "applicant": applicant, "reason": reason, "scope": scope, "created_at": NOW})
            return cursor({"id": tx.events[-1]["id"]})
        raise AssertionError("unexpected SQL: " + query)


def load_user_suspend(store):
    record_event = production("review.py", {"record_event"}, {
        "db": NS(fetch_one=AsyncMock()), "Jsonb": lambda value, **kw: value, "json": json, "Any": object}).record_event
    return production("user_suspend.py", {"TARGET", "MANUAL_OPERATION_SLOTS", "operation_key", "suspend", "resume", "listing"},
                      {"db": NS(POOL_MAX=10, transaction=store.transaction), "asyncio": asyncio,
                       "review": NS(record_event=record_event),
                       "local_jobs": NS(is_local=lambda _: False,
                                        quiesce=AsyncMock(),
                                        resume_user_stop=AsyncMock())})


class LedgerChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.store = Store()
        self.mod = load_user_suspend(self.store)

    async def test_suspend_records_who_whom_which_server_and_when(self):
        result = await self.mod.suspend("emp-a", "gitea", "admin", "정책 위반 조사")
        self.assertEqual((result["user_token"], result["server_id"], result["suspended_at"]), ("emp-a", "gitea", NOW))
        self.assertEqual(len(self.store.rows), 1)
        self.assertEqual(self.store.rows[0]["suspended_by"], "admin")
        (event,) = self.store.events
        self.assertEqual((event["kind"], event["outcome"], event["actor"], event["reason"]),
                         ("user-server-suspend", "held", "admin", "정책 위반 조사"))
        self.assertEqual((event["target_kind"], event["target_id"]), (self.mod.TARGET, str(result["id"])))
        self.assertEqual((event["scope"]["user"], event["scope"]["server"]), ("emp-a", "gitea"))
        self.assertIsNotNone(event["created_at"])

    async def test_pair_operation_lock_precedes_the_dispatch_employee_lock(self):
        await self.mod.suspend("emp-a", "gitea", "admin", "사유 기록")
        statements = self.store.first_statements
        self.assertIn("pg_advisory_xact_lock(1431523923, hashtext(%s))", statements[0])
        self.assertLess(next(i for i, q in enumerate(statements) if "1431523923" in q),
                        next(i for i, q in enumerate(statements) if q == "SELECT pg_advisory_xact_lock(hashtext(%s))"))

    async def test_calls_in_flight_are_counted_in_the_record(self):
        self.store.flight[("emp-a", "gitea")] = (2, 1)
        result = await self.mod.suspend("emp-a", "gitea", "admin", "사유 기록")
        self.assertEqual((result["unsent"], result["sent"]), (2, 1))
        self.assertEqual((self.store.events[0]["scope"]["unsent"], self.store.events[0]["scope"]["sent"]), (2, 1))

    async def test_second_suspend_changes_nothing_and_adds_no_record(self):
        await self.mod.suspend("emp-a", "gitea", "admin", "사유 기록")
        with self.assertRaisesRegex(ValueError, "이미 중지"):
            await self.mod.suspend("emp-a", "gitea", "other-admin", "다시 중지")
        self.assertEqual((len(self.store.rows), len(self.store.events)), (1, 1))
        self.assertEqual(self.store.rows[0]["suspended_by"], "admin")

    async def test_other_employee_and_other_server_are_separate_pairs(self):
        await self.mod.suspend("emp-a", "gitea", "admin", "사유 기록")
        await self.mod.suspend("emp-b", "gitea", "admin", "사유 기록")
        await self.mod.suspend("emp-a", "filesystem", "admin", "사유 기록")
        self.assertEqual(len(self.store.rows), 3)

    async def test_unknown_employee_or_server_is_refused_without_record(self):
        for user, server in (("nobody", "gitea"), ("emp-a", "nowhere")):
            with self.assertRaises(LookupError):
                await self.mod.suspend(user, server, "admin", "사유 기록")
        self.assertEqual((self.store.rows, self.store.events), ([], []))

    async def test_resume_records_the_actor_and_second_resume_adds_nothing(self):
        suspended = await self.mod.suspend("emp-a", "gitea", "admin", "사유 기록")
        await self.mod.resume(suspended["id"], "admin-2", "조사 종료")
        row = self.store.rows[0]
        self.assertEqual((row["resumed_at"], row["resumed_by"]), (NOW, "admin-2"))
        self.assertEqual([e["kind"] for e in self.store.events], ["user-server-suspend", "user-server-resume"])
        self.assertEqual((self.store.events[1]["outcome"], self.store.events[1]["actor"], self.store.events[1]["reason"]),
                         ("approved", "admin-2", "조사 종료"))
        with self.assertRaisesRegex(ValueError, "중지 상태가 아닙니다"):
            await self.mod.resume(suspended["id"], "admin-2", "다시 재개")
        with self.assertRaises(ValueError):
            await self.mod.resume(999, "admin-2", "없는 중지")
        self.assertEqual(len(self.store.events), 2)

    async def test_pair_can_be_suspended_again_after_resume_with_a_new_row(self):
        first = await self.mod.suspend("emp-a", "gitea", "admin", "사유 기록")
        await self.mod.resume(first["id"], "admin", "조사 종료")
        second = await self.mod.suspend("emp-a", "gitea", "admin", "재발 방지")
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(len(self.store.rows), 2)

    async def test_state_and_record_commit_together_or_not_at_all(self):
        self.store.fail_commit = True
        with self.assertRaises(OSError):
            await self.mod.suspend("emp-a", "gitea", "admin", "사유 기록")
        self.assertEqual((self.store.rows, self.store.events), ([], []))
        self.store.fail_commit = False
        suspended = await self.mod.suspend("emp-a", "gitea", "admin", "사유 기록")
        self.store.fail_commit = True
        with self.assertRaises(OSError):
            await self.mod.resume(suspended["id"], "admin", "조사 종료")
        self.assertIsNone(self.store.rows[0]["resumed_at"])
        self.assertEqual(len(self.store.events), 1)

    def test_no_code_edits_the_ledger(self):
        source = (APP / "user_suspend.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"(UPDATE|DELETE\s+FROM)\s+(approval_events|decisions|audit_chain)", source, re.I))
        self.assertEqual(re.findall(r"INSERT INTO (\w+)", source), ["user_server_suspensions"])  # events: review.record_event


class Stop(Exception):
    pass


class GateChecks(unittest.IsolatedAsyncioTestCase):
    """The decision in execute_call, up to the point where the call would be reserved."""

    def setUp(self):
        ledger = json.loads((HERE.parent / "opa" / "policy_ledger.json").read_text(encoding="utf-8"))["policy_ledger"]
        self.suspended = {("emp-a", "gitea")}
        self.failing = False
        self.queries = []

        async def fetch_one(query, params=()):
            self.queries.append((" ".join(query.split()), params))
            if self.failing:
                raise OSError("suspension store unavailable")
            server, token = params
            return {"token": token, "role": "employee", "status": "active", "synthetic": False,
                    "server_suspended": (token, server) in self.suspended}
        self.db = NS(fetch_one=AsyncMock(side_effect=fetch_one))
        self.reserve = AsyncMock(side_effect=Stop("reached reservation"))
        self.mode = AsyncMock(return_value="monitor")
        self.recorded = []

        async def decision_payload(event, laps):
            self.recorded.append(event)
            return event
        span = NS(get_span_context=lambda: NS(trace_id=1), set_attribute=lambda *a: None, record_exception=lambda e: None)
        cls = NS(data_class="public", action="r", base_action="r", destinations=[], resources=[], dlp=[], notes=[],
                 primary=NS(id="asset", kind="file", owner_department=None), summary=lambda: "unit")
        ns = {"__package__": "suspend_unit", "uuid": uuid, "time": time, "Any": object, "db": self.db, "_ledger_cache": ledger,
              "GATEWAY_ENVIRONMENT": "prod", "policy_ledger": AsyncMock(), "_reserve_call": self.reserve,
              "tracer": NS(start_as_current_span=lambda *a, **k: nullcontext(span)),
              "classify": NS(classify=lambda *a: cls), "_decision_payload": decision_payload,
              "tool_sunset": NS(check=AsyncMock(return_value={}), call_verdict=lambda state: None),
              "registry": NS(server=lambda s: {"endpoint": "http://unit.invalid"}, permits=lambda allowed, token: allowed is None or "*" in allowed or token in allowed, ALL_PRINCIPALS="*", allowed_principals=lambda s: None),
              "enforcement_mode": self.mode, "_root_cause": lambda exc: type(exc).__name__, "MAX_ARGUMENT_BYTES": 10000}
        self.core = production("core.py", {"execute_call", "_Laps", "local_verdict"}, ns)
        endpoint = ModuleType("suspend_unit.endpoint_plane")
        endpoint.managed_failure = AsyncMock(return_value=None)
        package = ModuleType("suspend_unit")
        package.__path__ = []
        modules = patch.dict(sys.modules, {"suspend_unit": package, "suspend_unit.endpoint_plane": endpoint})
        modules.start()
        self.addCleanup(modules.stop)

    async def call(self, user="emp-a", server="gitea"):
        return await self.core.execute_call({"server_id": server, "tool": "read", "arguments": {}, "user_token": user})

    async def test_suspended_pair_is_blocked_with_its_own_policy_before_anything_runs(self):
        result = await self.call()
        self.assertEqual((result["decision"], result["policy_id"]), ("Block", "P-SUSPEND-001"))
        self.reserve.assert_not_awaited()
        self.assertFalse(result["upstream_attempted"] or result["upstream_executed"])
        self.assertEqual(self.recorded, [result])
        self.assertEqual((result["policy_name"], result["priority"]), ("직원별 MCP 서버 이용 중지", 2014))

    async def test_observation_mode_does_not_relax_it(self):
        result = await self.call()
        self.assertEqual(result["decision"], "Block")
        self.mode.assert_not_awaited()

    async def test_other_employee_and_other_server_pass_the_gate(self):
        for user, server in (("emp-b", "gitea"), ("emp-a", "filesystem")):
            self.reserve.reset_mock()
            result = await self.call(user, server)
            self.reserve.assert_awaited_once()
            self.assertNotEqual(result["policy_id"], "P-SUSPEND-001")

    async def test_resume_lets_the_next_call_through(self):
        self.assertEqual((await self.call())["policy_id"], "P-SUSPEND-001")
        self.suspended.clear()
        self.reserve.reset_mock()
        self.assertNotEqual((await self.call())["policy_id"], "P-SUSPEND-001")
        self.reserve.assert_awaited_once()

    async def test_state_is_read_with_the_identity_row_for_this_pair(self):
        await self.call()
        query, params = self.queries[0]
        self.assertEqual(params, ("gitea", "emp-a"))
        for fragment in ("FROM principals p", "user_server_suspensions u", "u.user_token=p.token", "u.server_id=%s",
                         "u.resumed_at IS NULL", "AS server_suspended"):
            self.assertIn(fragment, query)

    async def test_unreadable_state_runs_nothing(self):
        self.failing = True
        with self.assertRaises(OSError):
            await self.call()
        self.reserve.assert_not_awaited()
        self.assertEqual(self.recorded, [])


class DispatchChecks(unittest.IsolatedAsyncioTestCase):
    """The final transaction before the send, on the interleaving harness of the D-140 checks."""

    def setUp(self):
        class Database(recheck.Database):
            suspended = False

            async def statement(self, query, params=()):
                if query.startswith("INSERT INTO dispatch_intents"):
                    for fragment in ("FROM user_server_suspensions x", "x.user_token=r.user_token", "x.server_id=s.id",
                                     "x.resumed_at IS NULL"):
                        if fragment not in query:
                            raise AssertionError("final intent must exclude a suspended pair: " + fragment)
                    if self.suspended:
                        await self.gate("insert")
                        return recheck.cursor(count=0)
                if query.startswith("UPDATE user_server_suspensions"):
                    await self.lock("advisory")
                    self.pending[asyncio.current_task()].change = ("suspended", True)
                    return recheck.cursor()
                return await super().statement(query, params)

            async def why(self, query, params=()):
                assert "AS user_suspended" in query
                return {**await super().why(query, params), "user_suspended": self.suspended}

            async def stop(self):
                async with self.transaction() as connection:
                    await connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("employee",))
                    await connection.execute("UPDATE user_server_suspensions")
        with patch.object(recheck, "Database", Database):
            self.base = recheck.Checks("test_suspend_commits_before_dispatch_enters")
            self.base.setUp()
        self.db = self.base.db

    def blocked(self, result, intents=()):
        self.assertEqual((result["decision"], result["policy_id"]), ("Block", "P-SUSPEND-001"))
        self.assertEqual(self.db.intents, list(intents))
        self.base.client.call_tool.assert_not_awaited()
        self.assertFalse(self.base.event["upstream_attempted"] or self.base.event["upstream_executed"])

    async def test_stop_committed_before_dispatch_refuses_the_send(self):
        await self.db.stop()
        self.blocked(await self.base.send())

    async def test_stop_waits_for_a_dispatch_already_inside_and_refuses_the_next(self):
        self.db.pause = "server"
        task = asyncio.create_task(self.base.send())
        try:
            await asyncio.wait_for(self.db.reached.wait(), 2)
            stopping = asyncio.create_task(self.db.stop())
            # The dispatch holds the per-employee lock, so the stop waits for it: that call was already past.
            await self.base.wait_for_lock("advisory", 2)
            self.assertFalse(stopping.done())
            self.db.resume.set()
            self.assertEqual(await asyncio.wait_for(task, 2), {"decision": "Allow", "policy_id": "P-AUTHZ-ALLOW-001"})
            await asyncio.wait_for(stopping, 2)
        finally:
            await self.base.finish(task)
        self.assertTrue(self.db.suspended)
        self.base.client.call_tool.reset_mock()
        self.blocked(await self.base.send("next"), intents=["request"])

    async def test_uncommitted_stop_makes_dispatch_wait_and_then_see_it(self):
        async with self.db.transaction() as connection:
            await connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("employee",))
            await connection.execute("UPDATE user_server_suspensions")
            task = asyncio.create_task(self.base.send())
            try:
                await self.base.wait_for_lock("advisory", 2)
                self.assertFalse(task.done())
            finally:
                if task.done():
                    await self.base.finish(task)
        try:
            self.blocked(await asyncio.wait_for(task, 2))
        finally:
            await self.base.finish(task)

    async def test_after_resume_the_send_goes_out(self):
        self.db.suspended = True
        self.blocked(await self.base.send())
        self.db.suspended = False
        self.base.client.call_tool.reset_mock()
        result = await self.base.send("after-resume")
        self.assertEqual((result["decision"], result["policy_id"]), ("Allow", "P-AUTHZ-ALLOW-001"))
        self.base.client.call_tool.assert_awaited_once()
        self.assertEqual(self.db.intents, ["after-resume"])

    async def test_unreadable_state_at_dispatch_is_a_recorded_fail_closed(self):
        self.db.fail = "insert"
        self.blocked_by_control(await self.base.send())

    def blocked_by_control(self, result):
        self.assertEqual((result["decision"], result["policy_id"]), ("Block", "P-CONTROL-FAIL-CLOSED"))
        self.assertEqual(self.db.intents, [])
        self.base.client.call_tool.assert_not_awaited()


class WiringChecks(unittest.TestCase):
    def test_ledger_entry_is_unique_gateway_enforced_and_a_block(self):
        ledger = json.loads((HERE.parent / "opa" / "policy_ledger.json").read_text(encoding="utf-8"))["policy_ledger"]
        entry = ledger["P-SUSPEND-001"]
        self.assertEqual((entry["enforced_by"], entry["outcome"], entry["status"]), ("gateway", "차단", "운영"))
        self.assertEqual(len(ledger), len({p["priority"] for p in ledger.values()}))

    def test_table_has_one_active_row_per_pair(self):
        sql = (APP / "ops_tables.sql").read_text(encoding="utf-8")
        self.assertRegex(sql, r"CREATE TABLE IF NOT EXISTS user_server_suspensions")
        self.assertRegex(sql, r"UNIQUE INDEX IF NOT EXISTS user_server_suspensions_active\s+ON user_server_suspensions\(user_token, server_id\) WHERE resumed_at IS NULL")

    def test_routes_are_admin_only_and_proxied_by_the_console(self):
        tree = ast.parse((APP / "main.py").read_text(encoding="utf-8"))
        routes = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call) and decorator.args and isinstance(decorator.args[0], ast.Constant) \
                            and str(decorator.args[0].value).startswith("/api/suspensions"):
                        routes[(decorator.func.attr, decorator.args[0].value)] = ast.unparse(node.args)
        self.assertEqual(sorted(routes), [("get", "/api/suspensions"), ("post", "/api/suspensions"),
                                          ("post", "/api/suspensions/{suspension_id}/resume")])
        for args in routes.values():
            self.assertIn("Depends(admin_caller)", args)
        self.assertIn('"suspensions"', (APP / "agent_service.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2, argv=[sys.argv[0]])
