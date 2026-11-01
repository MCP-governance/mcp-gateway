"""Offline projections, SQL contracts and authenticated API validation; no MCP or live DB."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pglast import parse_sql

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gateway"))
from app import audit, endpoint_plane, main, outcomes


def valid_sql(query, params):
    assert query.count("%s") == len(params), (query, params)
    parse_sql(query.replace("%s", "NULL"))


class Axes(unittest.TestCase):
    def test_six_call_outcomes_and_no_byte_inference(self):
        for verdict, result, attempted, executed, expected in [
            ("Allow", {}, True, True, "업무 성공"),
            ("Alert", {}, True, True, "업무 성공"),
            ("Alert", {"isError": True}, True, True, "도구 오류"),
            ("Block", None, False, False, "미실행"),
            ("Allow", {"isError": True}, True, True, "도구 오류"),
            (None, None, None, None, "미확인"),
        ]:
            with self.subTest(verdict=verdict, result=result):
                event = {"decision_id": 41 if verdict else None, "candidate_count": 1,
                         "decision": verdict, "policy_id": "P-SCOPE-001" if verdict == "Block" else "P-AUTHZ-ALLOW-001",
                         "path": "gateway", "upstream_attempted": attempted, "upstream_executed": executed,
                         "result": result, "output_bytes": 100}
                event["outcome"] = outcomes.outcome_axes(event) if verdict else None
                before = deepcopy(event)
                axes = outcomes.endpoint_outcome(event)
                self.assertEqual(event, before)
                self.assertEqual(axes["task"], expected)
                self.assertEqual(axes["route"], "게이트웨이")
                if verdict == "Block":
                    self.assertEqual((axes["decision"], axes["execution"]), ("정책 거부", "실행 안 함"))
                if not verdict:
                    self.assertEqual(axes["decision"], "원장 연결 없음")
        self.assertEqual(outcomes.endpoint_outcome({"path": "local", "failed": True})["task"], "도구 오류")


class ReadModels(unittest.IsolatedAsyncioTestCase):
    async def test_endpoint_link_ambiguity_and_redacted_projection(self):
        rows = [{"id": i, "decision_id": 41, "candidate_count": count, "path": "gateway", "decision": "Alert",
                 "policy_id": "P-ANOMALY-001", "upstream_attempted": True, "upstream_executed": True,
                 "outcome": {"task": "도구 오류"}, "error": "private", "result_preview": {"sha256": "digest"}}
                for i, count in [(3, 1), (2, 2), (1, 1)]]
        async def one(query, params):
            valid_sql(query, params)
            return {"n": 3}
        async def all_rows(query, params):
            valid_sql(query, params)
            self.assertIn("d.client->>'device_id'=e.endpoint_id", query)
            self.assertIn("count(*) OVER ()", query)
            return deepcopy(rows)
        with patch.object(endpoint_plane.db, "fetch_one", side_effect=one), patch.object(endpoint_plane.db, "fetch_all", side_effect=all_rows):
            page = await endpoint_plane.tool_events_page(limit=2)
        self.assertEqual(page["next_cursor"], "2")
        self.assertEqual(page["rows"][0]["decision"], "Alert")
        self.assertEqual(page["rows"][0]["policy_id"], "P-ANOMALY-001")
        self.assertEqual(page["rows"][0]["link_strength"], "supporting")
        self.assertIsNone(page["rows"][1]["decision_id"])
        self.assertEqual(page["rows"][1]["outcome_axes"]["decision"], "원장 연결 없음")
        for row in page["rows"]:
            self.assertFalse({"error", "result_preview", "outcome"} & row.keys())

    async def test_device_filters_apply_to_rows_counts_and_agents(self):
        calls = []
        async def one(query, params):
            calls.append((query, params)); valid_sql(query, params)
            return {"n": 21}
        async def rows(query, params):
            calls.append((query, params)); valid_sql(query, params)
            return []
        filters = {"endpoint": "ep/1", "q": "김%_", "state": "quarantined"}
        with patch.object(endpoint_plane.db, "fetch_one", side_effect=one), patch.object(endpoint_plane.db, "fetch_all", side_effect=rows):
            for function in [endpoint_plane.inventory_page, endpoint_plane.listeners_page, endpoint_plane.os_events_page]:
                page = await function(limit=5, cursor="42", **filters)
                self.assertEqual(page["total"], 21)
                self.assertIsNone(page["next_cursor"])
            self.assertEqual(await endpoint_plane.agents(**filters), [])
        self.assertEqual(len(calls), 7)
        for query, params in calls:
            self.assertIn("a2.managed_state=%s", query)
            self.assertIn("p2.display_name", query)
            self.assertEqual(tuple(params[:3]), ("ep/1", "quarantined", "%김\\%\\_%"))

    async def test_alert_window_pagination_unread_and_evidence_navigation(self):
        queries = []
        async def one(query, params):
            valid_sql(query, params); queries.append((query, params))
            return {"n": 7}
        async def rows(query, params):
            valid_sql(query, params); queries.append((query, params))
            return [{"id": i, "origin": "endpoint-listener", "origin_id": "73", "evidence": {"endpoint_id": "ep/1"}}
                    for i in (6, 5, 4)]
        since = datetime(2026, 11, 1, tzinfo=timezone.utc)
        until = since + timedelta(hours=24)
        with patch.object(audit.db, "fetch_one", side_effect=one), patch.object(audit.db, "fetch_all", side_effect=rows):
            page = await audit.alerts(2, since=since, until=until, before=10, read_ranges="1-3,6")
            hours = await audit.alerts(2, hours=24)
        self.assertEqual(page["total"], 7)
        self.assertEqual(page["unread_count"], 7)
        self.assertEqual(page["next_before"], 5)
        self.assertEqual(page["alerts"][0]["evidence"]["record_kind"], "listener")
        self.assertEqual(page["alerts"][0]["evidence"]["record_id"], "73")
        self.assertEqual(hours["until"] - hours["since"], timedelta(hours=24))
        self.assertIn("a.created_at >= %s AND a.created_at <= %s", queries[0][0])
        self.assertEqual(queries[0][1], (since, until))
        self.assertIn("a.id < %s", queries[1][0])
        self.assertEqual(queries[1][1], (since, until, 10, 3))
        self.assertIn("AND NOT (id BETWEEN %s AND %s OR id BETWEEN %s AND %s)", queries[3][0])
        self.assertEqual(queries[3][1], (0, 1, 3, 6, 6))

    async def test_bad_time_ranges_fail_before_querying(self):
        aware = datetime.now(timezone.utc)
        for args in [{"since": aware.replace(tzinfo=None)}, {"since": aware, "until": aware-timedelta(seconds=1)},
                     {"since": aware, "hours": 24}]:
            with patch.object(audit.db, "fetch_one", new=AsyncMock()) as query:
                with self.assertRaises(HTTPException) as caught:
                    await audit.alerts(**args)
                self.assertEqual(caught.exception.status_code, 422)
                query.assert_not_called()


class API(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.saved = dict(main.app.dependency_overrides)

    def tearDown(self):
        main.app.dependency_overrides.clear()
        main.app.dependency_overrides.update(self.saved)

    def test_api_auth_and_validation(self):
        response = self.client.get("/api/audit/alerts")
        self.assertIn(response.status_code, (401, 403))
        main.app.dependency_overrides[main.admin_caller] = lambda: {"principal": "unit-admin"}
        for url in ["/api/audit/alerts?hours=0", "/api/audit/alerts?hours=8761", "/api/audit/alerts?before=-1",
                    "/api/endpoint/inventory?state=invalid", "/api/endpoint/inventory/entries?limit=201"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 422)
        with patch.object(audit, "alerts", new=AsyncMock(return_value={"alerts": []})) as handler:
            self.assertEqual(self.client.get("/api/audit/alerts?hours=24&read_ranges=1-3&alert_id=42").status_code, 200)
            self.assertEqual(handler.await_args.kwargs["hours"], 24)
            self.assertEqual(handler.await_args.kwargs["read_ranges"], "1-3")
        with patch.object(endpoint_plane, "inventory_page", new=AsyncMock(return_value={"rows": []})) as handler:
            self.assertEqual(self.client.get("/api/endpoint/inventory/entries?endpoint=ep1&q=kim&state=pending").status_code, 200)
            self.assertEqual(handler.await_args.kwargs, {"endpoint": "ep1", "q": "kim", "state": "pending"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
