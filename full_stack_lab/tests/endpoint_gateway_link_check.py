"""Offline link regression: production SQL predicates + shared projection; no live PostgreSQL or MCP."""
import ast
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

APP = Path(__file__).resolve().parents[1] / "gateway" / "app"
tree = ast.parse((APP / "endpoint_plane.py").read_text(encoding="utf-8"))
names = {"DECISION_DEVICE", "GATEWAY_DECISION", "LINK_FIELDS", "assign_links", "self_summary", "tool_events_page"}
nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names
         or isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in n.targets)]
scope = {"__package__": "link_test_app", "datetime": datetime, "UTC": timezone.utc, "os": os,
         "managed_platform": lambda device: "linux", "_bounds": lambda limit, cursor: (limit, cursor),
         "_window": lambda rows, limit: (rows[:limit], None)}
exec(compile(ast.Module(body=nodes, type_ignores=[]), "endpoint_plane.py", "exec"), scope)
spec = importlib.util.spec_from_file_location("link_outcomes", APP / "outcomes.py")
outcomes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(outcomes)
package = ModuleType("link_test_app")
package.connectors = SimpleNamespace(DEVICE_PREFIX="device:", CATALOG={})
package.pac = SimpleNamespace(servers_for=lambda owner: [])
package.outcomes = outcomes


class LinkRules(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""CREATE TABLE decisions(id,decision,policy_id,reason,created_at,outcome,
            upstream_attempted,upstream_executed,result_preview,error,server_id,tool_name,user_token,client);
            CREATE TABLE endpoint_tool_events(path,server,tool,called_at,endpoint_id);
            CREATE TABLE endpoint_agents(owner_token);
            INSERT INTO endpoint_tool_events VALUES('gateway','hf','search',100,'pc-a');
            INSERT INTO endpoint_agents VALUES('employee');""")
        # Only PostgreSQL time arithmetic changes to numeric seconds. All production filters/count/order stay intact.
        self.query = scope["GATEWAY_DECISION"].split("LEFT JOIN LATERAL (", 1)[1].split(") g ON TRUE", 1)[0]
        self.query = self.query.replace("FROM decisions d", "FROM decisions d, endpoint_tool_events e, endpoint_agents a")
        self.query = self.query.replace("interval '30 seconds'", "30").replace("interval '5 seconds'", "5")
        self.query = self.query.replace("extract(epoch FROM d.created_at - e.called_at)", "d.created_at - e.called_at")
        # SQLite has no array_agg; group_concat over the same window keeps the production order of candidates.
        self.query = self.query.replace("array_agg(d.id) OVER", "group_concat(d.id) OVER")

    def add(self, client, at=99, **overrides):
        row = dict(id=243, decision="Alert", policy_id="P-ANOMALY-001", reason="경보", created_at=at,
                   outcome=None, upstream_attempted=1, upstream_executed=1, result_preview=None, error=None,
                   server_id="hf", tool_name="search", user_token="employee", client=json.dumps(client))
        row.update(overrides)
        self.db.execute("INSERT INTO decisions VALUES(" + ",".join("?" for _ in row) + ")", tuple(row.values()))

    def link(self):
        found = self.db.execute(self.query).fetchone()
        row = dict(found) if found else {"decision_id": None}
        row["candidate_ids"] = [int(i) for i in str(row.get("candidate_ids") or "").split(",") if i]
        async def no_lookup(sql, params=()):
            raise AssertionError("one call never needs a second decision lookup")
        scope["db"] = SimpleNamespace(fetch_all=no_lookup)
        asyncio.run(scope["assign_links"]([row]))
        return row

    def test_same_employee_other_pc_does_not_make_the_right_call_ambiguous(self):
        self.add({"workstation": "pc-a"})
        self.add({"workstation": "pc-b"}, id=244, at=100)
        row = self.link()
        self.assertEqual((row["decision_id"], row["decision"], row["policy_id"], row["candidate_count"], row["link_strength"]),
                         (243, "Alert", "P-ANOMALY-001", 1, "supporting"))

    def test_device_precedence_empty_legacy_keys_and_no_unknown_device_fallback(self):
        for client, expected in [({"device_id": "pc-a", "workstation": "pc-b"}, 243),
                                 ({"device_id": "pc-b", "workstation": "pc-a"}, None),
                                 ({"device_id": "", "endpoint_id": "pc-a"}, 243),
                                 ({"endpoint_id": "pc-b", "workstation": "pc-a"}, None),
                                 ({"workstation": "pc-a"}, 243), ({}, None)]:
            with self.subTest(client=client):
                self.db.execute("DELETE FROM decisions")
                self.add(client)
                self.assertEqual(self.link()["decision_id"], expected)

    def test_time_window_boundaries_and_multiple_candidates(self):
        for at, expected in [(69.999, None), (70, 243), (105, 243), (105.001, None)]:
            self.db.execute("DELETE FROM decisions")
            self.add({"device_id": "pc-a"}, at=at)
            self.assertEqual(self.link()["decision_id"], expected)
        self.db.execute("DELETE FROM decisions")
        self.add({"device_id": "pc-a"})
        self.add({"device_id": "pc-a"}, id=244, at=100)
        # A burst: one reported call with two candidates takes the nearest (244 at the same second) as supporting.
        row = self.link()
        self.assertEqual((row["decision_id"], row["candidate_count"], row["link_strength"]), (244, 2, "supporting"))

    def test_person_server_tool_and_route_must_all_match(self):
        for override in ({"user_token": "other"}, {"server_id": "other"}, {"tool_name": "other"}):
            self.db.execute("DELETE FROM decisions")
            self.add({"device_id": "pc-a"}, **override)
            self.assertIsNone(self.link()["decision_id"])
        self.db.execute("DELETE FROM decisions")
        self.add({"device_id": "pc-a"})
        self.db.execute("UPDATE endpoint_tool_events SET path='local'")
        self.assertIsNone(self.link()["decision_id"])

    def test_pc_and_web_share_sql_and_ambiguity_projection(self):
        for count in (1, 2):
            event = {"called_at": datetime.now(timezone.utc), "decision_id": 243, "candidate_count": count,
                     "candidate_ids": [243] if count == 1 else [243, 244],
                     "decision": "Alert", "policy_id": "P-ANOMALY-001", "path": "gateway"}
            seen = []
            async def rows(sql, params=()):
                if "FROM endpoint_tool_events e JOIN endpoint_agents" in sql:
                    self.assertIn(scope["GATEWAY_DECISION"], sql)
                    self.assertIn("g.candidate_count", sql)
                    seen.append(sql)
                    return [deepcopy(event)]
                if "WITH RECURSIVE" in sql:
                    return [{"id": "pc-a"}]
                if "FROM decisions d LEFT JOIN" in sql:
                    self.assertIn(scope["DECISION_DEVICE"] + " = ANY(%s)", sql)
                    self.assertIn("'exact' AS link_strength", sql)
                return []
            async def one(sql, params=()):
                return {"n": 1, "token": "employee"}
            scope["db"] = SimpleNamespace(fetch_all=rows, fetch_one=one)
            with patch.dict(sys.modules, {"link_test_app": package, "link_test_app.outcomes": outcomes}):
                pc = asyncio.run(scope["self_summary"]({"endpoint_id": "pc-a", "owner_token": "employee"}))
                web = asyncio.run(scope["tool_events_page"]())
            self.assertEqual(len(seen), 2)
            for key in ("decision_id", "decision", "policy_id", "link_strength"):
                self.assertEqual(pc["calls"][0][key], web["rows"][0][key])
            self.assertEqual(web["rows"][0]["link_strength"], "supporting")


class AlertNames(unittest.TestCase):
    def test_names_are_read_only_joins_and_evidence_ids_are_preserved(self):
        captured = []
        tree = ast.parse((APP / "audit.py").read_text(encoding="utf-8"))
        alerts = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "alerts")
        async def one(query, params):
            return {"n": 1}
        async def rows(query, params):
            captured.append(query)
            self.assertEqual(query.count("%s"), len(params))
            return [{"id": 1, "origin": "endpoint-inventory", "origin_id": "73", "hostname": "pc-name",
                     "owner_name": "직원", "evidence": {"endpoint_id": "long-id"}}]
        namespace = {"datetime": datetime, "timedelta": timedelta, "timezone": timezone,
                     "predicates": lambda **kwargs: None, "db": SimpleNamespace(fetch_one=one, fetch_all=rows)}
        exec(compile(ast.Module(body=[alerts], type_ignores=[]), "audit.py", "exec"), namespace)
        result = asyncio.run(namespace["alerts"]())
        self.assertIn("ep.hostname, p.display_name AS owner_name", captured[0])
        self.assertIn("LEFT JOIN endpoint_agents ep", captured[0])
        self.assertIn("LEFT JOIN principals p", captured[0])
        self.assertEqual(result["alerts"][0]["evidence"], {"endpoint_id": "long-id", "record_kind": "config", "record_id": "73"})
        self.assertEqual(result["alerts"][0]["owner_name"], "직원")


if __name__ == "__main__":
    unittest.main(verbosity=2)
