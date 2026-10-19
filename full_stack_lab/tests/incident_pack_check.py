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


if __name__ == "__main__":
    unittest.main()
