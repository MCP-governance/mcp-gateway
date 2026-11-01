"""Verify read-only detail metadata without changing termination judgments."""
import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import unittest


class DetailTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[1] / "gateway/app/decommission.py"
        nodes = [n for n in ast.parse(source.read_text(encoding="utf-8")).body
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in {"case_timeline", "case_detail"}]
        self.start = datetime(2026, 11, 1, tzinfo=timezone.utc)
        self.case = {"id":"case", "server_id":"docs", "status":"OPEN", "opened_at":self.start, "opened_by":"Admin", "reason":"종료"}
        self.targets, self.evidence, self.reads = [], [], []
        async def fetch_one(sql, params):
            self.reads.append(sql)
            return {"n":2} if "endpoint_inventory" in sql else self.case
        async def fetch_all(sql, params):
            self.reads.append(sql)
            return self.evidence if "termination_evidence" in sql else self.targets
        async def activity(case):
            return {"unknown":1}
        self.scope = {"db":SimpleNamespace(fetch_one=fetch_one,fetch_all=fetch_all), "timedelta":timedelta,
                      "SLA_DAYS":14,"_now":lambda:self.start+timedelta(days=15),"_row":lambda value:value,
                      "_post_cutover":activity,"EVIDENCE_KINDS":{"credential-check":{"label":"자격 확인"}},
                      "CRITERION_LABEL":{},"GRADE_LABEL":{"T3":"판단 불가"}}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),str(source),"exec"),self.scope)

    async def test_due_date_matches_list_rule_and_detail_is_read_only(self):
        detail = await self.scope["case_detail"]("case")
        self.assertEqual(detail["case"]["due_at"],self.start+timedelta(days=14))
        self.assertTrue(detail["case"]["overdue"])
        self.assertEqual(detail["endpoint_residue"],2)
        self.assertTrue(all(sql.lstrip().startswith("SELECT") for sql in self.reads))
        self.case["status"] = "CLOSED"
        self.assertFalse((await self.scope["case_detail"]("case"))["case"]["overdue"])

    async def test_history_uses_recorded_evidence_time_and_preserves_actor(self):
        self.case.update(assessed_at=self.start+timedelta(hours=3),assessed_by="Reviewer",grade="T3")
        self.evidence.append({"kind":"credential-check","recorded_at":self.start+timedelta(hours=2),
                              "observed_at":self.start-timedelta(days=1),"recorded_by":"Collector","target_id":"target"})
        detail = await self.scope["case_detail"]("case")
        self.assertEqual([event["kind"] for event in detail["timeline"]],["opened","evidence","assessed"])
        self.assertEqual(detail["timeline"][1]["at"],self.evidence[0]["recorded_at"])
        self.assertEqual(detail["timeline"][1]["actor"],"Collector")

    async def test_missing_timestamps_and_unknown_targets_do_not_invent_events(self):
        self.targets.append({"id":"unknown","status":"UNVERIFIABLE","revoked_by":"Admin"})
        self.case["criteria"] = {"reopened_note":"사유"}
        detail = await self.scope["case_detail"]("case")
        self.assertEqual([event["kind"] for event in detail["timeline"]],["opened"])
        self.assertEqual(detail["case"]["status"],"OPEN")


if __name__ == "__main__":
    unittest.main()
