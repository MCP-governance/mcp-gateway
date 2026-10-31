"""Exercise read-only termination counts and paging with isolated SQL fixtures."""
import ast
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import unittest


class ActionSummaryTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.addCleanup(self.conn.close)
        self.conn.row_factory = sqlite3.Row
        self.conn.create_function("now", 0, lambda: 10000000)
        self.conn.executescript("""
            CREATE TABLE mcp_servers(id TEXT, display_name TEXT, lifecycle TEXT);
            INSERT INTO mcp_servers VALUES ('docs', 'Docs', 'TERMINATING');
            CREATE TABLE termination_cases(id TEXT, server_id TEXT, relationship_id TEXT,
                engagement_label TEXT, provider TEXT, reason TEXT, status TEXT, grade TEXT,
                cutover_at REAL, opened_by TEXT, opened_at REAL, assessed_at REAL,
                closed_at REAL, criteria TEXT);
            CREATE TABLE revocation_targets(case_id TEXT, status TEXT);
            CREATE TABLE termination_evidence(case_id TEXT);
            CREATE TABLE endpoint_inventory(classification TEXT);
        """)
        # Keep PostgreSQL's query predicates and ordering; adapt casts and interval syntax only.
        async def fetch_all(sql, params=()):
            sql = sql.replace("%s::text", "?").replace("%s", "?")
            sql = sql.replace("make_interval(days => ?)", "(? * 86400)")
            return [dict(row) for row in self.conn.execute(sql, params)]

        async def fetch_one(sql, params=()):
            return (await fetch_all(sql, params))[0]

        source = Path(__file__).resolve().parents[1] / "gateway/app/decommission.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        functions = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef)
                     and n.name in {"summary", "list_cases"}]
        self.scope = {"db": SimpleNamespace(fetch_all=fetch_all, fetch_one=fetch_one),
                      "SLA_DAYS": 7, "_row": lambda row: row}
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), "exec"), self.scope)

    def insert(self, identity, status, grade=None, age=0):
        self.conn.execute("""INSERT INTO termination_cases(id, server_id, status, grade, opened_at)
                             VALUES (?, 'docs', ?, ?, ?)""", (identity, status, grade, 10000000 - age))

    async def test_all_unclosed_cases_need_action_including_ungraded_and_awaiting_close(self):
        for i, (status, grade) in enumerate([
            ("OPEN", None), ("REVOKING", None), ("ASSESSED", "T1"),
            ("REOPENED", "T2"), ("ASSESSED", "T3"), ("CLOSED", "T2")
        ]):
            self.insert(str(i), status, grade)
        result = await self.scope["summary"]()
        self.assertEqual(result["action_required"], 5)
        self.assertEqual(result["total_cases"], 6)
        rows = await self.scope["list_cases"](attention="required")
        self.assertEqual(len(rows), result["action_required"])
        self.assertTrue(all(row["status"] != "CLOSED" for row in rows))

    async def test_overdue_excludes_closed_and_cases_at_exact_deadline(self):
        self.insert("late", "OPEN", age=7 * 86400 + 1)
        self.insert("deadline", "OPEN", age=7 * 86400)
        self.insert("closed", "CLOSED", age=8 * 86400)
        rows = await self.scope["list_cases"](attention="overdue")
        self.assertEqual([row["id"] for row in rows], ["late"])
        self.assertEqual((await self.scope["summary"]())["overdue"], len(rows))

    async def test_filter_precedes_limit_and_paging_has_no_duplicates(self):
        for i in range(60):
            self.insert(f"closed-{i:02}", "CLOSED")
            self.insert(f"open-{i:02}", "OPEN", age=100)
        first = await self.scope["list_cases"](attention="required")
        second = await self.scope["list_cases"](attention="required", offset=50)
        self.assertEqual((len(first), len(second)), (50, 10))
        self.assertEqual(len({r["id"] for r in first + second}), 60)
        self.assertEqual((await self.scope["summary"]())["action_required"], 60)


if __name__ == "__main__":
    unittest.main()
