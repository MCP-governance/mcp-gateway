"""Isolated dashboard queue pagination tests using SQL fixtures, no live services."""
import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from typing import Literal
import unittest
from unittest.mock import AsyncMock


ROOT = Path(__file__).resolve().parents[1] / "gateway/app"
NOW = datetime(2026, 10, 31, tzinfo=UTC)


class HTTPError(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        super().__init__(detail)


def function(path, name, scope, defaults=None):
    node = next(n for n in ast.parse(path.read_text(encoding="utf-8")).body
                if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
    node.decorator_list = []
    if defaults is not None:
        node.args.defaults = [ast.Constant(value) for value in defaults]
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), str(path), "exec"), scope)
    return scope[name]


class ReadPathsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.addCleanup(self.conn.close)
        self.conn.row_factory = sqlite3.Row
        self.conn.create_function("now", 0, lambda: NOW.isoformat())
        self.conn.executescript("""
            CREATE TABLE signup_requests(id INTEGER, username TEXT, display_name TEXT, status TEXT,
              requested_at TEXT, reviewed_at TEXT, reviewed_by TEXT);
            CREATE TABLE dispatch_intents(request_id TEXT, user_token TEXT, server_id TEXT,
              tool_name TEXT, action TEXT, attempted_at TEXT, decision_id INTEGER, state TEXT);
            CREATE TABLE principals(token TEXT, display_name TEXT);
            CREATE TABLE call_reservations(request_id TEXT, released_at TEXT, expires_at TEXT);
        """)
        async def fetch_all(sql, params=()):
            sql = sql.replace("%s::text", "?").replace("%s", "?")
            rows = []
            for row in self.conn.execute(sql, params):
                data = dict(row)
                if data.get("attempted_at"):
                    data["attempted_at"] = datetime.fromisoformat(data["attempted_at"])
                rows.append(data)
            return rows

        async def fetch_one(sql, params=()):
            return (await fetch_all(sql, params))[0]

        self.db = SimpleNamespace(fetch_all=fetch_all, fetch_one=fetch_one)
        self.identity = AsyncMock(return_value={"roles": ["admin"]})
        scope = {"db": self.db, "Literal": Literal, "current_identity": self.identity, "HTTPException": HTTPError}
        self.signups = function(ROOT / "agent_service.py", "list_signup_requests", scope, [None, None, 1])
        scope = {"db": self.db}
        tree = ast.parse((ROOT / "dispatch.py").read_text(encoding="utf-8"))
        scope["UNSETTLED"] = next(ast.literal_eval(n.value) for n in tree.body
                                  if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "UNSETTLED" for t in n.targets))
        dispatch = SimpleNamespace(
            uncertain=function(ROOT / "dispatch.py", "uncertain", scope),
            uncertain_count=function(ROOT / "dispatch.py", "uncertain_count", scope))
        self.intents = function(ROOT / "main.py", "dispatch_intents", {"dispatch": dispatch}, [None, 1])

    async def test_signup_pending_count_includes_requests_older_than_latest_hundred(self):
        for i in range(300):
            self.conn.execute("INSERT INTO signup_requests VALUES (?, ?, '', ?, ?, NULL, NULL)",
                              (i, f"user-{i}", "pending" if i < 150 else "approved", (NOW + timedelta(seconds=i)).isoformat()))
        recent = await self.signups()
        self.assertTrue(all(row["status"] == "approved" for row in recent["requests"]))
        self.assertEqual(recent["pending_total"], 150)
        first = await self.signups(status="pending")
        second = await self.signups(status="pending", page=2)
        self.assertEqual((first["total"], len(first["requests"]), len(second["requests"])), (150, 100, 50))
        self.assertEqual(len({row["id"] for row in first["requests"] + second["requests"]}), 150)
        self.assertTrue(all(row["status"] == "pending" for row in second["requests"]))
        self.assertEqual((await self.signups(status="pending", page=999))["page"], 2)

    async def test_signup_employee_cannot_read_count_or_requests(self):
        self.identity.return_value = {"roles": ["employee"]}
        with self.assertRaises(HTTPError) as failure:
            await self.signups(status="pending")
        self.assertEqual(failure.exception.status_code, 403)

    async def test_all_unresolved_intents_are_reachable_beyond_two_hundred(self):
        for i in range(305):
            self.conn.execute("INSERT INTO dispatch_intents VALUES (?, 'alice', 'docs', 'read', 'r', ?, NULL, 'uncertain')",
                              (f"request-{i:03}", (NOW + timedelta(seconds=i)).isoformat()))
        self.conn.execute("INSERT INTO dispatch_intents VALUES ('resolved', 'alice', 'docs', 'read', 'r', ?, NULL, 'confirmed_executed')", (NOW.isoformat(),))
        self.conn.execute("INSERT INTO dispatch_intents VALUES ('running', 'alice', 'docs', 'read', 'r', ?, NULL, 'pending')", (NOW.isoformat(),))
        self.conn.execute("INSERT INTO call_reservations VALUES ('running', NULL, ?)", ((NOW + timedelta(minutes=1)).isoformat(),))
        first = await self.intents()
        second = await self.intents(page=2)
        self.assertEqual((first["total"], len(first["rows"]), len(second["rows"])), (305, 200, 105))
        ids = {r["request_id"] for r in first["rows"] + second["rows"]}
        self.assertEqual(len(ids), 305)
        self.assertNotIn("running", ids)
        self.assertNotIn("resolved", ids)
        self.assertIn("request-000", {r["request_id"] for r in second["rows"]})
        self.conn.execute("UPDATE dispatch_intents SET state='confirmed_executed' WHERE request_id <> 'request-000'")
        shrunk = await self.intents(page=2)
        self.assertEqual((shrunk["total"], shrunk["page"]), (1, 1))
        self.assertEqual(shrunk["rows"][0]["request_id"], "request-000")

    async def test_empty_queues_have_one_page_and_no_invented_items(self):
        signups = await self.signups(status="pending", page=50)
        intents = await self.intents(page=50)
        self.assertEqual((signups["total"], signups["pending_total"], signups["page"]), (0, 0, 1))
        self.assertEqual(signups["requests"], [])
        self.assertEqual((intents["total"], intents["page"]), (0, 1))
        self.assertEqual(intents["rows"], [])


if __name__ == "__main__":
    unittest.main()
