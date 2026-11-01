"""Compare record and evidence selections without starting the service stack."""
import ast
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
from types import SimpleNamespace
import unittest


class FilterTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / "gateway/app"
        def load(file, names, scope):
            tree = ast.parse((root / file).read_text(encoding="utf-8"))
            nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names
                     or isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in n.targets)]
            exec(compile(ast.Module(body=nodes, type_ignores=[]), file, "exec"), scope)
            return scope
        self.activity = load("activity.py", {"filter_predicates"}, {})["filter_predicates"]
        self.audit = load("audit.py", {"predicates", "DECISIONS", "EXECUTIONS", "KINDS", "PROJECTION"},
                          {"activity": SimpleNamespace(filter_predicates=self.activity), "HTTPException": ValueError})
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.executescript("""
          CREATE TABLE principals(token TEXT, display_name TEXT, department TEXT);
          INSERT INTO principals VALUES ('alice','Alice','A'),('bob','Bob','B');
          CREATE TABLE decisions(id INTEGER, user_token TEXT, decision TEXT, server_id TEXT, client TEXT,
            policy_id TEXT, created_at TEXT, upstream_executed BOOLEAN, upstream_attempted BOOLEAN,
            result_preview TEXT, tool_name TEXT, resource_id TEXT, trace_id TEXT, reason TEXT);
        """)
        for i in range(1, 7):
            self.db.execute("INSERT INTO decisions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                i, "bob" if i == 2 else "alice", "Block", "docs",
                json.dumps({"workstation": "other" if i == 3 else "pc-1", "event_kind": "mcp-connection" if i == 4 else "tools/call"}),
                "OTHER" if i == 5 else "POL-001", "2026-10-31T01:00:00+00:00", 0, 0, "{}", "read", "", "trace-1", "needle"))

    def select(self, where, params):
        sql = "SELECT d.id FROM decisions d LEFT JOIN principals p ON p.token=d.user_token WHERE " + where
        sql = re.sub(r"(d\.\w+)->>'([^']+)'", r"json_extract(\1, '$.\2')", sql)
        sql = sql.replace(" ILIKE ", " LIKE ").replace("::text", "").replace("%s", "?")
        values = [v.isoformat() if isinstance(v, datetime) else v for v in params]
        return [r[0] for r in self.db.execute(sql, values)]

    def test_record_and_export_select_same_ids_with_all_filters_and_cursor(self):
        filters = dict(person="lic", endpoint="pc-1", policy="POL-", query="needle", principal="alice",
                       trace_id="trace-1", before=6, event_kind="tools/call", execution="not-sent",
                       decision="Block", server="docs", since=datetime(2026, 10, 31, tzinfo=timezone.utc))
        clauses, params = self.activity(**filters)
        where, args = self.audit["predicates"](view="calls", **filters)
        self.assertEqual(self.select(" AND ".join(clauses), params), [1])
        self.assertEqual(self.select(where, args), [1])
        filters["before"] = 1
        where, args = self.audit["predicates"](view="calls", **filters)
        self.assertEqual(self.select(where, args), [])

    def test_employee_scope_cannot_be_overridden_by_principal_filter(self):
        clauses, params = self.activity(user_token="alice", principal="bob")
        self.assertEqual(self.select(" AND ".join(clauses), params), [])

    def test_legacy_exact_policy_and_invalid_filter_rejection(self):
        where, args = self.audit["predicates"](policy="POL-")
        self.assertEqual(where, "policy_id = %s")
        self.assertEqual(args, ["POL-"])
        for filters in ({"person":"alice"}, {"view":"wrong"}, {"view":"calls", "decision":"wrong"},
                        {"view":"calls", "since":datetime(2026, 10, 31)}):
            with self.assertRaises(ValueError):
                self.audit["predicates"](**filters)
        where, args = self.audit["predicates"](view="calls", query="' OR true --")
        self.assertNotIn("' OR true --", where)
        self.assertEqual(self.select(where, args), [])

    def test_evidence_projection_and_admin_guards_remain(self):
        for field in ("request_payload", "policy_input", "d.client", "resource_id"):
            self.assertNotIn(field, self.audit["PROJECTION"])
        root = Path(__file__).resolve().parents[1] / "gateway/app"
        tree = ast.parse((root / "main.py").read_text(encoding="utf-8"))
        for name in ("audit_export", "audit_events", "audit_event", "audit_verify"):
            node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
            self.assertIn("Depends(admin_caller)", ast.unparse(node.args))
        tree = ast.parse((root / "audit.py").read_text(encoding="utf-8"))
        export = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "export")
        self.assertIn("REPEATABLE READ, READ ONLY", ast.unparse(export))


if __name__ == "__main__":
    unittest.main()
