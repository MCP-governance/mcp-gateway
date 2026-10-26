import sys
import unittest
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gateway"))
from app import incident_pack
try:
    from app import incidents
except ModuleNotFoundError as exc:
    if exc.name != "psycopg":
        raise
    incidents = None


class IncidentPackCheck(unittest.TestCase):
    def test_package_hash_and_count_agreement(self):
        package = incident_pack.seal({"schema": "mint-incident-evidence/v1", "query_count": 2, "included_count": 2})
        self.assertTrue(incident_pack.verify_package(package))
        self.assertTrue(incident_pack.count_matches(2, 2))
        self.assertFalse(incident_pack.count_matches(3, 2))
        package["included_count"] = 3
        self.assertFalse(incident_pack.verify_package(package))

    def test_deadline_comes_from_pack_and_manual_values_have_no_timer(self):
        detected = datetime(2026, 10, 20, 0, tzinfo=timezone.utc)
        result = incident_pack.deadlines(detected, ["KR-NETWORK", "KR-PRIVACY"], detected)
        self.assertEqual(result[0]["due_at"], detected + timedelta(hours=24))
        self.assertEqual(result[1]["status"], "수동 확인 필요")
        self.assertIsNone(result[1]["remaining_seconds"])

    def test_overdue_excludes_reported_stage(self):
        detected = datetime(2026, 10, 1, tzinfo=timezone.utc)
        rows = incident_pack.deadlines(detected, ["KR-NETWORK"], datetime(2026, 10, 3, tzinfo=timezone.utc))
        self.assertEqual(incident_pack.overdue(rows, set()), rows)
        self.assertEqual(incident_pack.overdue(rows, {("KR-NETWORK", "notification")}), [])

    def test_imminent_stage_is_selected_for_alert(self):
        now = datetime(2026, 10, 20, tzinfo=timezone.utc)
        rows = incident_pack.deadlines(now-timedelta(hours=18), ["KR-NETWORK"], now)
        self.assertEqual(rows[0]["status"], "임박")
        self.assertEqual(incident_pack.alertable(rows, set()), rows)


@unittest.skipIf(incidents is None, "게이트웨이 시험 환경의 psycopg 필요")
class IncidentTimerCheck(unittest.IsolatedAsyncioTestCase):
    async def test_overdue_stage_emits_existing_alert(self):
        detected = datetime.now(timezone.utc) - timedelta(days=2)
        case = {"id": "00000000-0000-0000-0000-000000000001", "detected_at": detected,
                "jurisdictions": ["KR-NETWORK"]}
        with patch.object(incidents.db, "execute", new_callable=AsyncMock) as execute, \
             patch.object(incidents.db, "fetch_all", new_callable=AsyncMock) as fetch_all, \
             patch.object(incidents.ops_response, "emit_alert", new_callable=AsyncMock) as emit:
            fetch_all.side_effect = [[case], []]
            await incidents.check_deadlines()
        execute.assert_awaited_once()
        emit.assert_awaited_once()
        self.assertEqual(emit.await_args.args[0], "incident-deadline")
        self.assertEqual(emit.await_args.args[1], "incident")
        self.assertEqual(emit.await_args.args[3]["status"], "초과")


@unittest.skipIf(incidents is None, "게이트웨이 시험 환경의 psycopg 필요")
class IncidentPackageAssemblyCheck(unittest.IsolatedAsyncioTestCase):
    async def test_package_count_chain_and_hash(self):
        from app import audit
        now = datetime(2026, 10, 20, tzinfo=timezone.utc)
        case = {"id": "00000000-0000-0000-0000-000000000001", "title": "합성 사고",
                "started_at": now, "detected_at": now, "assessed_at": None,
                "scope_since": now-timedelta(hours=1), "scope_until": now,
                "scope": {"server_id": "sample", "principal": "staff@example.invalid"},
                "jurisdictions": ["KR-NETWORK"], "created_by": "admin@example.invalid"}
        event = {"id": 1, "created_at": now, "request_id": "req-1", "trace_id": "trace-1",
                 "user_token": "staff@example.invalid", "role": "user", "server_id": "sample",
                 "tool_name": "read", "action": "read", "data_class": "public", "decision": "Allow",
                 "policy_id": "P-TEST", "approval_id": None, "upstream_attempted": True,
                 "upstream_executed": True, "outcome": None, "outcome_error": None, "intent_state": None,
                 "response_disposition": None, "response_sha256": "abc", "event_kind": "tools/call",
                 "prev_sha256": "prev", "entry_sha256": "entry", "chain_version": 8}

        class Cursor:
            def __init__(self, value): self.value = value
            async def fetchall(self): return self.value
            async def fetchone(self): return self.value

        connection = AsyncMock()
        connection.execute = AsyncMock(side_effect=[Cursor(None), Cursor([event]), Cursor({"count": 1})])

        @asynccontextmanager
        async def transaction():
            yield connection

        with patch.object(incidents.db, "fetch_one", new_callable=AsyncMock, return_value=case), \
             patch.object(incidents.db, "fetch_all", new_callable=AsyncMock, side_effect=[[], [], []]), \
             patch.object(incidents.db, "transaction", transaction), \
             patch.object(incidents.core, "verify_audit_chain", new_callable=AsyncMock,
                          return_value={"intact": True, "checked": 1}), \
             patch.object(audit, "predicates", return_value=("server_id=%s", ["sample"])):
            result = await incidents.detail(case["id"])
        package = result["evidence_package"]
        self.assertEqual(package["query_count"], 1)
        self.assertEqual(package["included_count"], 1)
        self.assertTrue(package["count_matches"])
        self.assertTrue(package["chain_verification"]["intact"])
        self.assertTrue(result["package_hash_valid"])
        self.assertNotIn("staff@example.invalid", str(package))



class IncidentRevisionPureCheck(unittest.TestCase):
    def setUp(self):
        self.detected = datetime(2027, 1, 1, tzinfo=timezone.utc)

    def test_nis2_missing_submission_keeps_final_and_progress_manual(self):
        rows = incident_pack.deadlines(self.detected, ["EU-NIS2"], self.detected)
        selected = {row["stage"]: row for row in rows}
        for stage in ("final", "progress", "final-after-handling"):
            self.assertEqual(selected[stage]["status"], "수동 확인 필요")
            self.assertIsNone(selected[stage]["due_at"])

    def test_old_recording_timestamp_is_not_submission_evidence(self):
        rows = incident_pack.deadlines(self.detected, ["EU-NIS2"], self.detected,
            reports=[{"jurisdiction": "EU-NIS2", "stage": "notification", "created_at": self.detected}])
        self.assertTrue(all(r["due_at"] is None for r in rows if r["stage"] in
                            {"final", "progress", "final-after-handling"}))

    def test_nis2_month_end_progress_and_handled_final(self):
        notification = datetime(2027, 1, 31, 10, tzinfo=timezone.utc)
        reports = [{"jurisdiction": "EU-NIS2", "stage": "notification", "submitted_at": notification}]
        rows = incident_pack.deadlines(self.detected, ["EU-NIS2"], notification, reports=reports)
        selected = {row["stage"]: row for row in rows}
        self.assertEqual(selected["progress"]["due_at"], datetime(2027, 2, 28, 10, tzinfo=timezone.utc))
        self.assertIsNone(selected["final-after-handling"]["due_at"])
        handled = datetime(2027, 3, 2, 10, tzinfo=timezone.utc)
        rows = incident_pack.deadlines(self.detected, ["EU-NIS2"], handled, reports=reports, handled_at=handled)
        selected = {row["stage"]: row for row in rows}
        self.assertEqual(selected["final-after-handling"]["due_at"], datetime(2027, 4, 2, 10, tzinfo=timezone.utc))
        rows = incident_pack.deadlines(self.detected, ["EU-NIS2"], notification, reports=reports,
                                        handled_at=notification+timedelta(days=1))
        self.assertIn("final", {row["stage"] for row in rows})
        self.assertNotIn("progress", {row["stage"] for row in rows})

    def test_submission_uses_actual_time_and_earliest_notification(self):
        recorded = datetime(2027, 2, 2, tzinfo=timezone.utc)
        reports = [{"jurisdiction": "EU-NIS2", "stage": "notification", "created_at": recorded,
                    "submitted_at": "2027-01-30T00:00:00Z"},
                   {"jurisdiction": "EU-NIS2", "stage": "notification", "created_at": recorded,
                    "submitted_at": recorded}]
        rows = incident_pack.deadlines(self.detected, ["EU-NIS2"], recorded, reports=reports)
        self.assertEqual(next(r for r in rows if r["stage"] == "progress")["due_at"],
                         datetime(2027, 2, 28, tzinfo=timezone.utc))
        self.assertEqual(incident_pack.add_month(datetime(2028, 1, 31, tzinfo=timezone.utc)).day, 29)
        self.assertEqual(incident_pack.add_month(datetime(2027, 12, 31, tzinfo=timezone.utc)).year, 2028)

    def test_cra_type_and_final_anchors_are_distinct(self):
        for kind, expected in (("vulnerability", "vulnerability-final"), ("severe-incident", "final")):
            rows = incident_pack.deadlines(self.detected, ["EU-CRA"], self.detected, incident_type=kind)
            self.assertEqual(len(rows), 3)
            self.assertIn(expected, {r["stage"] for r in rows})
            self.assertIsNone(next(r for r in rows if r["stage"] == expected)["due_at"])
        rows = incident_pack.deadlines(self.detected, ["EU-CRA"], self.detected,
                                       incident_type="vulnerability", fix_available_at=self.detected)
        self.assertEqual(next(r for r in rows if r["stage"] == "vulnerability-final")["due_at"],
                         self.detected+timedelta(days=14))
        reports = [{"jurisdiction": "EU-CRA", "stage": "notification", "submitted_at": self.detected}]
        rows = incident_pack.deadlines(self.detected, ["EU-CRA"], self.detected,
                                       incident_type="severe-incident", reports=reports)
        self.assertEqual(next(r for r in rows if r["stage"] == "final")["due_at"],
                         datetime(2027, 2, 1, tzinfo=timezone.utc))
        rows = incident_pack.deadlines(self.detected, ["EU-CRA"], self.detected)
        self.assertTrue(all(r["status"] == "수동 확인 필요" for r in rows))

    def test_effective_dates_and_snapshot_are_frozen(self):
        for key, boundary in (("KR-NETWORK", "2026-10-01T00:00:00+09:00"),
                              ("EU-CRA", "2026-09-11T00:00:00+00:00")):
            start = incident_pack.parse_time(boundary)
            for moment, manual in ((start-timedelta(microseconds=1), True), (start, False)):
                rows = incident_pack.deadlines(moment, [key], moment, incident_type="severe-incident")
                self.assertEqual(rows[0]["status"] == "수동 확인 필요", manual)
        document = {"schema": "mint-incident-jurisdictions/v1", "packs": [incident_pack.packs()["KR-NETWORK"]]}
        document["packs"][0]["stages"][0]["hours"] = 48
        rows = incident_pack.deadlines(self.detected, ["KR-NETWORK"], self.detected, document=document)
        self.assertEqual(rows[0]["due_at"], self.detected+timedelta(hours=48))
        self.assertEqual(rows[0]["pack_version"], "2026-10-20.2")


def isolated_incidents():
    """Compile the actual functions with DB/HTTP adapters, without importing gateway dependencies."""
    import ast
    import hashlib
    import logging
    from types import SimpleNamespace
    from uuid import UUID
    from app.outcomes import recorded_outcome

    class InputError(Exception):
        def __init__(self, status_code, detail):
            self.status_code, self.detail = status_code, detail
            super().__init__(detail)

    def encode(value):
        if isinstance(value, dict): return {key: encode(item) for key, item in value.items()}
        if isinstance(value, (tuple, list)): return [encode(item) for item in value]
        return value.isoformat() if isinstance(value, datetime) else value

    namespace = dict(datetime=datetime, timezone=timezone, hashlib=hashlib, logging=logging, UUID=UUID,
                     incident_pack=incident_pack, HTTPException=InputError, Jsonb=lambda obj: obj,
                     jsonable_encoder=encode, recorded_outcome=recorded_outcome)
    for filename, names in (("audit.py", {"PROJECTION", "predicates", "with_outcome"}),):
        tree = ast.parse((Path(__file__).resolve().parents[1]/"gateway"/"app"/filename).read_text(encoding="utf-8"))
        body = [node for node in tree.body if getattr(node, "name", "") in names or
                isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in
                names | {"DECISIONS", "EXECUTIONS", "KINDS"} for t in node.targets)]
        exec(compile(ast.Module(body=body, type_ignores=[]), filename, "exec"), namespace)
    namespace["audit"] = SimpleNamespace(**{key: namespace[key] for key in ("PROJECTION", "predicates", "with_outcome")})
    namespace["db"] = SimpleNamespace(fetch_one=AsyncMock(), fetch_all=AsyncMock(), execute=AsyncMock())
    namespace["core"] = SimpleNamespace(verify_audit_chain=AsyncMock(return_value={"intact": True}))
    namespace["ops_response"] = SimpleNamespace(emit_alert=AsyncMock())
    path = Path(__file__).resolve().parents[1]/"gateway"/"app"/"incidents.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    tree.body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
    exec(compile(tree, str(path), "exec"), namespace)
    return SimpleNamespace(**namespace)


class IncidentRevisionAdapterCheck(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.api = isolated_incidents()
        self.now = datetime(2026, 10, 20, tzinfo=timezone.utc)
        self.case = dict(id="00000000-0000-0000-0000-000000000001", title="합성 사고",
                         started_at=self.now, detected_at=self.now, assessed_at=None,
                         scope_since=self.now, scope_until=self.now+timedelta(hours=2),
                         effective_since=self.now, effective_until=self.now+timedelta(hours=2),
                         scope={"principal": "staff@example.invalid"}, jurisdictions=["KR-NETWORK"],
                         created_by="admin@example.invalid",
                         pack_snapshot={"schema": "mint-incident-jurisdictions/v1",
                                        "packs": [incident_pack.packs()["KR-NETWORK"]]})

    async def test_detected_time_does_not_cap_scope_and_create_is_atomic(self):
        api = self.api
        connection = AsyncMock()
        connection.execute.return_value.fetchone.return_value = {"id": self.case["id"]}
        @asynccontextmanager
        async def transaction(): yield connection
        api.db.transaction = transaction
        # The function's globals retain these adapter objects, so no module import is replaced.
        with patch.dict(api.create.__globals__, detail=AsyncMock(return_value={"ok": True})):
            result = await api.create({**self.case, "principal": "staff@example.invalid"}, "admin@example.invalid")
        self.assertEqual(result, {"ok": True})
        self.assertEqual(connection.execute.await_count, 2)
        params = connection.execute.await_args_list[0].args[1]
        self.assertGreater(params[5], params[2])
        self.assertEqual(params[9]["packs"][0]["version"], "2026-10-20.2")
        api.db.execute.assert_not_awaited()

    async def test_supplement_only_appends_and_rejects_shrink(self):
        api = self.api
        api.db.fetch_one.return_value = self.case
        with patch.dict(api.supplement.__globals__, detail=AsyncMock(return_value={})):
            await api.supplement(self.case["id"], {"scope_since": self.now,
                                  "scope_until": self.now+timedelta(hours=3)}, "admin@example.invalid")
            with self.assertRaises(api.HTTPException):
                await api.supplement(self.case["id"], {"scope_since": self.now,
                                      "scope_until": self.now+timedelta(hours=1)}, "admin@example.invalid")
        api.db.execute.assert_awaited_once()
        self.assertIn("INSERT INTO approval_events", api.db.execute.await_args.args[0])
        self.assertIn("min(", api.CASE_SELECT)
        self.assertIn("max(", api.CASE_SELECT)

    async def test_timer_failure_continues_other_cases_and_never_refreshes_success(self):
        api = self.api
        case = {**self.case, "detected_at": datetime.now(timezone.utc)-timedelta(days=2)}
        api.db.fetch_all.side_effect = [[case, {**case, "id": "second"}], [], []]
        api.ops_response.emit_alert.side_effect = [RuntimeError("delivery failed"), None]
        with self.assertLogs(level="ERROR"):
            with self.assertRaises(RuntimeError): await api.check_deadlines()
        self.assertEqual(api.ops_response.emit_alert.await_count, 2)
        api.db.execute.assert_awaited_once()
        self.assertIn("SET last_failed_at=", api.db.execute.await_args.args[0])
        self.assertNotIn("SET checked_at=", api.db.execute.await_args.args[0])

    async def test_timer_success_is_after_alert_and_failure_state_recovers(self):
        api = self.api
        sequence = []
        case = {**self.case, "detected_at": datetime.now(timezone.utc)-timedelta(days=2)}
        api.db.fetch_all.side_effect = [[case], []]
        async def emit(*args): sequence.append("alert")
        async def execute(*args): sequence.append("success")
        api.ops_response.emit_alert.side_effect = emit
        api.db.execute.side_effect = execute
        await api.check_deadlines()
        self.assertEqual(sequence, ["alert", "success"])
        self.assertIn("last_failed_at=NULL", api.db.execute.await_args.args[0])
        api.db.fetch_one.return_value = {"checked_at": datetime.now(timezone.utc), "last_failed_at": self.now}
        api.db.fetch_all.side_effect = [[]]
        self.assertEqual((await api.list_cases())["timer_status"], "실패")
        api.db.fetch_one.return_value["last_failed_at"] = None
        api.db.fetch_all.side_effect = [[]]
        self.assertEqual((await api.list_cases())["timer_status"], "정상")

    async def test_repeated_timer_failures_keep_failure_status(self):
        api = self.api
        api.db.fetch_all.side_effect = RuntimeError("query failed")
        for _ in range(2):
            with self.assertRaises(RuntimeError): await api.check_deadlines()
        self.assertEqual(api.db.execute.await_count, 2)
        self.assertTrue(all("SET last_failed_at=" in call.args[0] for call in api.db.execute.await_args_list))

    async def test_scheduler_continues_existing_responses_after_incident_failure(self):
        import ast
        import logging
        path = Path(__file__).resolve().parents[1]/"gateway"/"app"/"ops_response.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        tick = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "tick")
        class WithoutImport(ast.NodeTransformer):
            def visit_ImportFrom(self, node): return None
        tick = WithoutImport().visit(tick)
        connection = AsyncMock()
        connection.execute.return_value.fetchone.return_value = {"acquired": True}
        @asynccontextmanager
        async def session(): yield connection
        api = self.api
        api.db.pool = AsyncMock(return_value=type("Pool", (), {"connection": staticmethod(session)})())
        namespace = dict(db=api.db, incidents=type("Timer", (), {"check_deadlines": AsyncMock(side_effect=RuntimeError())}),
                         LOG=logging.getLogger(__name__), observed_alerts=AsyncMock(),
                         contain_repeated=AsyncMock(), self_test=AsyncMock())
        exec(compile(ast.Module(body=[tick], type_ignores=[]), str(path), "exec"), namespace)
        with self.assertLogs(level="ERROR"): await namespace["tick"]("http://opa.invalid")
        for name in ("observed_alerts", "contain_repeated", "self_test"):
            namespace[name].assert_awaited_once()

    async def test_package_links_approval_scope_history_invalidity_and_policy(self):
        api = self.api
        event = dict(id=7, created_at=self.now, user_token="staff@example.invalid", server_id="actual-server",
                     approval_id="00000000-0000-0000-0000-000000000007", policy_id="P-TEST",
                     policy_version="recorded-version", reason="sensitive raw reason", decision="Block",
                     invalid={"by": "admin@example.invalid", "reason": "sensitive annotation", "at": self.now})
        class Cursor:
            def __init__(self, value): self.value = value
            async def fetchall(self): return self.value
            async def fetchone(self): return self.value
        connection = AsyncMock()
        connection.execute.side_effect = [Cursor(None), Cursor([event]), Cursor({"count": 1})]
        @asynccontextmanager
        async def transaction(): yield connection
        api.db.transaction = transaction
        api.db.fetch_one.return_value = self.case
        history = [dict(kind="call-approve", outcome="approved", target_kind="approval", target_id=event["approval_id"],
                        actor="admin@example.invalid", created_at=self.now-timedelta(hours=1))]
        stop = [dict(server_id="actual-server", source="repeated", created_at=self.now-timedelta(hours=3), resumed_at=None)]
        api.db.fetch_all.side_effect = [history, stop, []]
        result = await api.detail(self.case["id"])
        pack = result["evidence_package"]
        self.assertEqual((pack["total_count"], pack["invalid_count"], pack["valid_count"]), (1, 1, 0))
        self.assertTrue(pack["count_matches"])
        self.assertTrue(result["package_hash_valid"])
        self.assertEqual(pack["calls"][0]["policy_version"], "recorded-version")
        self.assertEqual(pack["calls"][0]["reason_code"], "P-TEST")
        for secret in ("staff@example.invalid", "admin@example.invalid", "sensitive raw reason", "sensitive annotation"):
            self.assertNotIn(secret, str(pack))
        first_query, params = api.db.fetch_all.await_args_list[0].args
        self.assertIn("target_kind='approval'", first_query)
        self.assertEqual(params[2], ["actual-server"])
        self.assertEqual(params[3], [event["approval_id"]])
        self.assertIn("registered_server_id", first_query)
        self.assertNotIn("BETWEEN", first_query)
        stop_query = api.db.fetch_all.await_args_list[1].args[0]
        self.assertNotIn("%s IS NULL", stop_query)
        self.assertIn("resumed_at IS NULL OR resumed_at>=%s", stop_query)
        projection = connection.execute.await_args_list[1].args[0]
        self.assertIn("a.first_id<=decisions.id", projection)
        self.assertIn("ORDER BY a.id LIMIT 1", projection)
        self.assertNotIn("request_payload", projection)
        api.core.verify_audit_chain.assert_awaited_once_with(connection)

    def test_valid_projection_has_no_reason_or_actor_prose(self):
        row = self.api.clean_row(dict(id=8, policy_id="P-TEST", user_token="raw actor", reason="raw reason"))
        self.assertNotIn("user_token", row)
        self.assertNotIn("reason", row)
        self.assertIsNone(row["policy_version"])
        self.assertFalse(row.get("invalid"))

    def test_legacy_case_has_no_automatic_current_deadline(self):
        case = {**self.case, "pack_snapshot": None}
        rows = self.api.case_deadlines(case, self.now, [])
        self.assertTrue(all(r["status"] == "수동 확인 필요" and r["due_at"] is None for r in rows))

    async def test_old_report_cannot_hide_unknown_pack_applicability(self):
        api = self.api
        api.db.fetch_one.return_value = {"checked_at": datetime.now(timezone.utc), "last_failed_at": None}
        api.db.fetch_all.side_effect = [[{**self.case, "pack_snapshot": None}],
            [{"created_at": self.now, "scope": {"jurisdiction": "KR-NETWORK", "stage": "notification"}}]]
        result = await api.list_cases()
        self.assertEqual(result["incidents"][0]["deadlines"][0]["status"], "수동 확인 필요")

    async def test_report_submission_is_separate_from_recording_and_rejects_future(self):
        api = self.api
        submitted = datetime.now(timezone.utc)-timedelta(hours=1)
        api.db.fetch_one.return_value = {**self.case, "detected_at": submitted-timedelta(hours=1)}
        with patch.dict(api.report.__globals__, detail=AsyncMock(return_value={})):
            await api.report(self.case["id"], "KR-NETWORK", "notification", "admin@example.invalid", "raw note", submitted)
            with self.assertRaises(api.HTTPException):
                await api.report(self.case["id"], "KR-NETWORK", "notification", "admin", "", datetime.now(timezone.utc)+timedelta(days=1))
        api.db.execute.assert_awaited_once()
        self.assertEqual(api.db.execute.await_args.args[1][3]["submitted_at"], submitted.isoformat())



@unittest.skipUnless(incidents is not None and __import__("os").environ.get("MINT_INCIDENT_PG_CHECK") == "1",
                     "솔루션 게이트웨이에서 MINT_INCIDENT_PG_CHECK=1로 PostgreSQL 조회 계획 확인")
class IncidentPostgresPlanCheck(unittest.IsolatedAsyncioTestCase):
    async def test_server_optional_scope_queries_bind_in_postgres(self):
        # EXPLAIN without ANALYZE validates psycopg binding and schema without reading call bodies or writing rows.
        for server in (None, "synthetic-incident-scope"):
            api = isolated_incidents()
            now = datetime.now(timezone.utc)
            case = dict(id="00000000-0000-0000-0000-000000000066", title="합성 범위",
                        started_at=now, detected_at=now, scope_since=now, scope_until=now,
                        scope={"server_id": server} if server else {}, jurisdictions=["KR-NETWORK"],
                        pack_snapshot=None, created_by="synthetic-admin")
            event = dict(id=1, created_at=now, server_id="synthetic-incident-scope", user_token="synthetic-user",
                         approval_id="00000000-0000-0000-0000-000000000007", policy_id="P-TEST", decision="Block")
            class Cursor:
                def __init__(self, value): self.value = value
                async def fetchall(self): return self.value
                async def fetchone(self): return self.value
            connection = AsyncMock()
            connection.execute.side_effect = [Cursor(None), Cursor([event]), Cursor({"count": 1})]
            @asynccontextmanager
            async def transaction(): yield connection
            api.db.transaction = transaction
            api.db.fetch_one.return_value = case
            api.db.fetch_all.side_effect = [[], [], []]
            await api.detail(case["id"])
            queries = [(api.CASE_SELECT+" WHERE c.id=%s", (case["id"],))]
            queries += [call.args for call in connection.execute.await_args_list[1:]]
            queries += [call.args for call in api.db.fetch_all.await_args_list]
            async with incidents.db.transaction() as live:
                for query, params in queries:
                    await live.execute("EXPLAIN " + query, params)


if __name__ == "__main__":
    unittest.main()
