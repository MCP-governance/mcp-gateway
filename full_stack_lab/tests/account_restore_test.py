"""삭제된 계정 복구: 관리자만, 삭제 기록은 두고 복구 사건을 더하며, 이전 엔드포인트·동의는 되살리지 않는다."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gateway"))
from app import agent_service as service
from app import endpoint_plane, local_jobs, review

ADMIN = {"roles": ["admin"], "principal": "root", "user_id": "root"}
EMPLOYEE = {"roles": ["employee"], "principal": "emp-bob", "user_id": "bob"}


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def fetchone(self):
        return self.rows[0] if self.rows else None

    async def fetchall(self):
        return self.rows


class Connection:
    """Records every statement; answers the principal update and the consent revoke."""

    def __init__(self, restored=True):
        self.sql, self.restored = [], restored

    async def execute(self, query, params=None):
        self.sql.append(query)
        if "UPDATE principals" in query:
            return Cursor([{"token": "emp-soeun", "user_id": "soeun", "email": "soeun", "display_name": "박소은",
                            "role": "employee", "status": "active"}] if self.restored else [])
        if "UPDATE user_consents" in query:
            return Cursor([{"id": 7, "server_id": "git", "tool_name": "git_log", "grade": "public", "terms_hash": "h"}])
        return Cursor([])


class AccountRestoreTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(service.app)
        self.order = []

    def restore(self, caller, *, deleted=True, restored=True):
        connection = Connection(restored)

        @asynccontextmanager
        async def transaction():
            yield connection

        async def revoke(endpoint_id, actor):
            self.order.append(("revoke_device", endpoint_id, actor))

        async def resume(**kwargs):
            self.order.append(("resume", kwargs))

        record = AsyncMock(return_value=1)
        target = {"token": "emp-soeun", "status_changed_by": "emp-admin2", "status_changed_at": "t0"} if deleted else None
        with patch.object(service, "current_identity", AsyncMock(return_value=caller)), \
             patch.object(service.db, "fetch_one", AsyncMock(return_value=target)), \
             patch.object(service.db, "fetch_all", AsyncMock(return_value=[{"endpoint_id": "ep-old"}])), \
             patch.object(service.db, "transaction", transaction), \
             patch.object(endpoint_plane, "revoke_device", revoke), \
             patch.object(local_jobs, "resume", resume), \
             patch.object(review, "record_event", record):
            response = self.client.post("/api/accounts/soeun/restore")
        return response, connection, record

    def test_admin_restores_deleted_account_and_records_event(self):
        response, connection, record = self.restore(ADMIN)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["account"]["status"], "active")
        # 이전 엔드포인트는 상태를 바꾸기 전에 해제하고, 로컬 실행 정지는 마지막에 푼다.
        self.assertEqual(self.order[0], ("revoke_device", "ep-old", "root"))
        self.assertEqual(self.order[-1], ("resume", {"user_token": "emp-soeun"}))
        self.assertIn("UPDATE user_consents SET status='REVOKED'", connection.sql[1])
        kinds = [call.args[0] for call in record.await_args_list]
        self.assertEqual(kinds, ["user-consent", "account-restore"])
        scope = record.await_args_list[-1].kwargs["scope"]
        self.assertEqual(scope, {"deleted_by": "emp-admin2", "deleted_at": "t0", "revoked_devices": ["ep-old"], "revoked_consents": 1})

    def test_restore_never_edits_ledger_rows(self):
        _, connection, _ = self.restore(ADMIN)
        for statement in connection.sql:
            self.assertNotIn("approval_events", statement)
            self.assertNotIn("decisions", statement)

    def test_employee_cannot_restore(self):
        response, _, record = self.restore(EMPLOYEE)
        self.assertEqual(response.status_code, 403)
        record.assert_not_awaited()
        self.assertEqual(self.order, [])

    def test_account_that_is_not_deleted_is_refused_without_side_effects(self):
        response, _, record = self.restore(ADMIN, deleted=False)
        self.assertEqual(response.status_code, 404)
        record.assert_not_awaited()
        self.assertEqual(self.order, [])

    def test_lost_race_leaves_no_event(self):
        response, _, record = self.restore(ADMIN, restored=False)
        self.assertEqual(response.status_code, 409)
        record.assert_not_awaited()

    def test_deleted_list_is_admin_only_and_filters_deleted(self):
        fetch = AsyncMock(return_value=[{"user_id": "soeun"}])
        with patch.object(service, "current_identity", AsyncMock(return_value=ADMIN)), \
             patch.object(service.db, "fetch_all", fetch):
            response = self.client.get("/api/accounts/deleted")
        self.assertEqual(response.json(), {"accounts": [{"user_id": "soeun"}]})
        self.assertIn("status = 'deleted'", fetch.await_args.args[0])
        with patch.object(service, "current_identity", AsyncMock(return_value=EMPLOYEE)):
            self.assertEqual(self.client.get("/api/accounts/deleted").status_code, 403)

    def signup(self, status):
        with patch.object(service.db, "fetch_one", AsyncMock(return_value={"status": status})):
            return self.client.post("/auth/signup", json={"username": "soeun", "display_name": "박소은",
                                                          "password": "password-1111"})

    def test_signup_of_deleted_name_points_to_restore(self):
        response = self.signup("deleted")
        self.assertEqual(response.status_code, 409)
        self.assertIn("복구를 요청", response.json()["detail"])
        self.assertIn("이미 사용 중", self.signup("active").json()["detail"])

    def test_deleted_login_reason_points_to_restore(self):
        self.assertIn("복구를 요청", service.ACCOUNT_STATUS_REASON["deleted"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
