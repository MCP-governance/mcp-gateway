"""Run analysis aggregation over isolated SQL fixtures without a service stack."""
import ast
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sqlite3
from types import SimpleNamespace
import unittest


class AnalysisScopeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.addCleanup(self.conn.close)
        self.conn.row_factory = sqlite3.Row
        self.start = datetime(2026, 10, 30, tzinfo=timezone.utc)
        self.conn.executescript("""
            CREATE TABLE principals(token TEXT, display_name TEXT, department TEXT);
            INSERT INTO principals VALUES ('alice', 'Alice', 'A'), ('bob', 'Bob', 'B');
            CREATE TABLE decisions(user_token TEXT, decision TEXT, server_id TEXT, client TEXT,
              policy_id TEXT, created_at TEXT, upstream_executed BOOLEAN, upstream_attempted BOOLEAN,
              result_preview TEXT, tool_name TEXT, resource_id TEXT, trace_id TEXT, reason TEXT);
        """)
        def bucket(unit, stamp):
            dt = datetime.fromisoformat(stamp).astimezone(timezone(timedelta(hours=9)))
            dt = dt.replace(minute=0, second=0, microsecond=0)
            if unit in {"day", "month"}:
                dt = dt.replace(hour=0)
            if unit == "month":
                dt = dt.replace(day=1)
            return dt.isoformat()
        self.conn.create_function("date_trunc", 2, bucket)
        self.conn.create_function("hour_of", 1, lambda stamp: datetime.fromisoformat(stamp).hour)

        async def fetch_all(sql, params=()):
            # Retain the query's filters and grouping; adapt PostgreSQL syntax for SQLite fixtures.
            sql = sql.replace("d.client->'harness'->>'name'", "json_extract(d.client, '$.harness.name')")
            sql = re.sub(r"(d\.\w+)->>'([^']+)'", r"json_extract(\1, '$.\2')", sql)
            sql = sql.replace(" AT TIME ZONE 'Asia/Seoul'", "")
            sql = sql.replace("extract(hour FROM d.created_at)", "hour_of(d.created_at)")
            sql = sql.replace("::int", "").replace("::text", "").replace(" ILIKE ", " LIKE ").replace("%s", "?")
            args = tuple(p.isoformat() if isinstance(p, datetime) else p for p in params)
            result = []
            for row in self.conn.execute(sql, args):
                item = dict(row)
                for key in ("first", "last", "bucket", "last_call"):
                    if item.get(key):
                        item[key] = datetime.fromisoformat(item[key])
                result.append(item)
            return result

        async def fetch_one(sql, params=()):
            return (await fetch_all(sql, params))[0]

        path = Path(__file__).resolve().parents[1] / "gateway/app/activity.py"
        nodes = [n for n in ast.parse(path.read_text(encoding="utf-8")).body
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in {"analysis", "filter_predicates"}]
        self.scope = {"datetime": datetime, "db": SimpleNamespace(fetch_all=fetch_all, fetch_one=fetch_one)}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), self.scope)

    def insert(self, owner="alice", decision="Block", endpoint="retired-endpoint", hour=1,
               server="docs", kind="tools/call", policy="P-1", reason="needle"):
        self.conn.execute("INSERT INTO decisions VALUES (?, ?, ?, ?, ?, ?, 0, 0, '{}', 'read', '', '', ?)",
                          (owner, decision, server, json.dumps({"workstation": endpoint, "event_kind": kind,
                           "harness": {"name": "codex"}}), policy, (self.start + timedelta(hours=hour)).isoformat(), reason))

    async def test_all_aggregates_preserve_employee_scope_and_selected_filters(self):
        self.insert()
        self.insert(owner="bob")
        self.insert(server="other")
        self.insert(hour=25)
        self.insert(kind="mcp-connection")
        self.insert(endpoint="other")
        self.insert(policy="P-2")
        self.insert(reason="excluded")
        result = await self.scope["analysis"](user_token="alice", server="docs", endpoint="retired-endpoint",
            policy="P-1", since=self.start, until=self.start + timedelta(days=1), query="needle", event_kind="tools/call")
        self.assertEqual(result["total"], 1)
        for name in ("servers", "people", "policies", "endpoints"):
            self.assertEqual(sum(row["total"] for row in result[name]), 1, name)
        self.assertEqual(sum(row["n"] for row in result["flows"]), 1)
        self.assertNotIn("Bob", str(result))

    async def test_historical_and_unknown_endpoints_and_policy_outcomes_are_kept(self):
        self.insert(hour=1)
        self.insert(decision="Alert", hour=2)
        self.insert(decision="Allow", endpoint="", hour=3)
        result = await self.scope["analysis"](user_token="alice")
        self.assertEqual(result["total"], 3)
        endpoints = {row["key"]: row for row in result["endpoints"]}
        self.assertEqual(endpoints["retired-endpoint"]["total"], 2)
        self.assertEqual(endpoints["retired-endpoint"]["last_call"], self.start + timedelta(hours=2))
        self.assertEqual(endpoints[""]["total"], 1)
        self.assertEqual(result["policies"][0]["total"], 2)
        self.assertEqual(result["policies"][0]["Allow"], 0)
        self.assertEqual(sum(row["n"] for row in result["flows"]), 3)

    async def test_other_bucket_preserves_totals_and_empty_shape_is_complete(self):
        empty = await self.scope["analysis"](user_token="bob")
        self.assertEqual(empty["total"], 0)
        for name in ("policies", "endpoints", "flows"):
            self.assertEqual(empty[name], [])
        for i in range(14):
            self.insert(endpoint=f"endpoint-{i}", policy=f"P-{i}", hour=i)
        result = await self.scope["analysis"](user_token="alice")
        for name in ("policies", "endpoints"):
            self.assertEqual(len(result[name]), 13)
            self.assertEqual(sum(row["total"] for row in result[name]), 14)
            self.assertTrue(result[name][-1]["other"])
        self.assertIsNotNone(result["endpoints"][-1]["last_call"])


if __name__ == "__main__":
    unittest.main()
