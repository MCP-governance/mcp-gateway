"""DEV-79 whole-employee stop and resume: unit checks on the same doubles as user_server_suspend_check.

Standard library only. The batch functions are loaded by AST and loop over the single-pair suspend() and
resume(), so each pair keeps its own row and record. Partial failure and the route and console wiring are
checked here; PostgreSQL, the HTTP stack and the device are not exercised.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock
import uuid

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import user_server_suspend_check as base  # noqa: E402  (same directory; its checks do not run on import)

APP = base.APP
CONSOLE = APP / "agent_static" / "console.js"
SINGLE = {"TARGET", "suspend", "resume", "listing"}
BATCH = {"operating_servers", "suspend_all", "resume_all"}


class BulkStore(base.Store):
    def __init__(self):
        super().__init__()
        self.servers = {"gitea", "filesystem", "wiki"}
        self.operating = ["filesystem", "gitea", "wiki"]  # the query orders by id
        self.fail_stop, self.fail_resume, self.stale_listing = set(), set(), False

    async def fetch_one(self, query, params=()):
        if "FROM principals WHERE token" in query:
            return {"x": 1} if params[0] in self.users else None
        raise AssertionError("unexpected fetch_one: " + query)

    async def fetch_all(self, query, params=()):
        if "FROM mcp_servers WHERE status IN" in query:
            return [{"id": server} for server in self.operating]
        if "FROM user_server_suspensions WHERE user_token" in query:
            return [{"id": r["id"], "server_id": r["server_id"]} for r in self.rows
                    if r["user_token"] == params[0] and (self.stale_listing or r["resumed_at"] is None)]
        raise AssertionError("unexpected fetch_all: " + query)

    async def statement(self, tx, query, params):
        if query.startswith("INSERT INTO user_server_suspensions") and params[1] in self.fail_stop:
            raise OSError("injected stop failure")
        if query.startswith("UPDATE user_server_suspensions") and params[2] in self.fail_resume:
            raise OSError("injected resume failure")
        return await super().statement(tx, query, params)


def load(store):
    record_event = base.production("review.py", {"record_event"}, {
        "db": NS(fetch_one=AsyncMock()), "Jsonb": lambda value, **kw: value, "json": json, "Any": object}).record_event
    return base.production("user_suspend.py", SINGLE | BATCH,
                           {"db": store, "review": NS(record_event=record_event), "uuid": uuid})


class BulkChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.store = BulkStore()
        self.mod = load(self.store)

    def active_servers(self, user="emp-a"):
        return sorted(r["server_id"] for r in self.store.rows if r["user_token"] == user and r["resumed_at"] is None)

    async def test_stop_all_writes_one_row_and_one_record_per_operating_server(self):
        result = await self.mod.suspend_all("emp-a", "admin", "사고 대응 중지")
        self.assertEqual(sorted(s["server_id"] for s in result["suspended"]), ["filesystem", "gitea", "wiki"])
        self.assertEqual((result["skipped"], result["failed"]), ([], []))
        self.assertEqual(len(self.store.rows), 3)
        self.assertEqual(len({r["id"] for r in self.store.rows}), 3)
        self.assertEqual(len(self.store.events), 3)
        for event in self.store.events:
            self.assertEqual((event["kind"], event["outcome"], event["actor"]), ("user-server-suspend", "held", "admin"))
            self.assertEqual(event["scope"]["batch"], result["batch"])
            self.assertEqual(event["scope"]["user"], "emp-a")

    async def test_pair_already_stopped_is_skipped_and_gets_no_second_record(self):
        await self.mod.suspend("emp-a", "gitea", "admin", "개별 중지")
        self.assertNotIn("batch", self.store.events[0]["scope"])  # the single-pair record keeps its shape
        result = await self.mod.suspend_all("emp-a", "admin-2", "사고 대응 중지")
        self.assertEqual(sorted(s["server_id"] for s in result["suspended"]), ["filesystem", "wiki"])
        self.assertEqual(result["skipped"], [{"server_id": "gitea", "reason": "이미 중지된 이용입니다."}])
        self.assertEqual(result["failed"], [])
        self.assertEqual(len(self.store.rows), 3)
        self.assertEqual(len(self.store.events), 3)
        gitea = [r for r in self.store.rows if r["server_id"] == "gitea"]
        self.assertEqual((len(gitea), gitea[0]["suspended_by"]), (1, "admin"))

    async def test_resume_all_reopens_every_active_stop_under_its_own_batch(self):
        stopped = await self.mod.suspend_all("emp-a", "admin", "사고 대응 중지")
        result = await self.mod.resume_all("emp-a", "admin-2", "조사 종료")
        self.assertEqual(sorted(r["server_id"] for r in result["resumed"]), ["filesystem", "gitea", "wiki"])
        self.assertEqual((result["skipped"], result["failed"]), ([], []))
        self.assertEqual(self.active_servers(), [])
        self.assertTrue(all(r["resumed_by"] == "admin-2" for r in self.store.rows))
        resumes = self.store.events[3:]
        self.assertEqual([e["kind"] for e in resumes], ["user-server-resume"] * 3)
        self.assertEqual({e["scope"]["batch"] for e in resumes}, {result["batch"]})
        self.assertNotEqual(result["batch"], stopped["batch"])

    async def test_resume_with_nothing_active_is_an_empty_result(self):
        result = await self.mod.resume_all("emp-a", "admin", "조사 종료")
        self.assertEqual((result["resumed"], result["skipped"], result["failed"]), ([], [], []))
        self.assertEqual(len(self.store.events), 0)

    async def test_partial_stop_failure_is_reported_and_its_pair_is_not_stopped(self):
        self.store.fail_stop = {"wiki"}
        result = await self.mod.suspend_all("emp-a", "admin", "사고 대응 중지")
        self.assertEqual(sorted(s["server_id"] for s in result["suspended"]), ["filesystem", "gitea"])
        self.assertEqual(result["failed"], [{"server_id": "wiki", "error": "OSError"}])
        self.assertEqual(result["skipped"], [])
        self.assertEqual(self.active_servers(), ["filesystem", "gitea"])
        self.assertEqual(len(self.store.events), 2)

    async def test_partial_resume_failure_is_reported_and_its_pair_stays_stopped(self):
        await self.mod.suspend_all("emp-a", "admin", "사고 대응 중지")
        wiki = next(r["id"] for r in self.store.rows if r["server_id"] == "wiki")
        self.store.fail_resume = {wiki}
        result = await self.mod.resume_all("emp-a", "admin-2", "조사 종료")
        self.assertEqual(sorted(r["server_id"] for r in result["resumed"]), ["filesystem", "gitea"])
        self.assertEqual(result["failed"], [{"id": wiki, "server_id": "wiki", "error": "OSError"}])
        self.assertEqual(self.active_servers(), ["wiki"])
        self.assertEqual(len(self.store.events), 3 + 2)

    async def test_stop_that_lost_a_race_to_resume_is_reported_as_skipped(self):
        await self.mod.suspend_all("emp-a", "admin", "사고 대응 중지")
        first = self.store.rows[0]
        await self.mod.resume(first["id"], "admin-2", "먼저 재개")
        self.store.stale_listing = True  # the listing still shows the row resume_all reads first
        result = await self.mod.resume_all("emp-a", "admin-3", "조사 종료")
        self.assertEqual(len(result["resumed"]), 2)
        self.assertEqual([s["id"] for s in result["skipped"]], [first["id"]])
        self.assertEqual(result["skipped"][0]["reason"], "중지 상태가 아닙니다.")
        self.assertEqual(result["failed"], [])

    async def test_unknown_employee_is_refused_with_nothing_written(self):
        with self.assertRaises(LookupError):
            await self.mod.suspend_all("nobody", "admin", "사고 대응 중지")
        self.assertEqual((self.store.rows, self.store.events), ([], []))

    async def test_no_operating_server_is_an_empty_success(self):
        self.store.operating = []
        result = await self.mod.suspend_all("emp-a", "admin", "사고 대응 중지")
        self.assertEqual((result["suspended"], result["skipped"], result["failed"]), ([], [], []))
        self.assertTrue(result["batch"])
        self.assertEqual((self.store.rows, self.store.events), ([], []))


class BulkWiringChecks(unittest.TestCase):
    def test_bulk_routes_are_admin_only(self):
        import ast
        tree = ast.parse((APP / "main.py").read_text(encoding="utf-8"))
        routes = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call) and decorator.args and isinstance(decorator.args[0], ast.Constant) \
                            and str(decorator.args[0].value).startswith("/api/user-suspensions/"):
                        routes[(decorator.func.attr, decorator.args[0].value)] = ast.unparse(node.args)
        self.assertEqual(sorted(routes), [("post", "/api/user-suspensions/resume-all"),
                                          ("post", "/api/user-suspensions/stop-all")])
        for args in routes.values():
            self.assertIn("Depends(admin_caller)", args)

    def test_bulk_routes_are_proxied_by_the_console(self):
        self.assertIn('"user-suspensions/"', (APP / "agent_service.py").read_text(encoding="utf-8"))

    def test_bulk_code_adds_no_table_and_no_write_outside_the_state_row(self):
        source = (APP / "user_suspend.py").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"INSERT INTO (\w+)", source), ["user_server_suspensions"])
        self.assertIsNone(re.search(r"\b(CREATE|ALTER|DROP)\s+TABLE\b", source, re.I))

    def test_console_has_both_actions_and_counts_failures(self):
        source = CONSOLE.read_text(encoding="utf-8")
        for fragment in ('data-act="suspend-all"', 'data-act="resume-all"', '"user-suspensions/stop-all"',
                         '"user-suspensions/resume-all"', "실패 ${r.failed.length}건"):
            self.assertIn(fragment, source)


if __name__ == "__main__":
    unittest.main(verbosity=2, argv=[sys.argv[0]])
