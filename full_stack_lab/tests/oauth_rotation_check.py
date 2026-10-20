"""Deterministic refresh/revocation interleavings and rollback checks, without a live DB."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, ExitStack
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import uuid

from starlette.requests import Request
from termination_lab_support import isolated_disposal

os.environ.setdefault("OTEL_SDK_DISABLED", "true")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gateway"))
from app import idp


class Cursor:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []

    async def fetchone(self):
        return deepcopy(self.row)

    async def fetchall(self):
        return deepcopy(self.rows)


class Connection:
    def __init__(self, database):
        self.database = database
        self.state = None
        self.acquired = []

    async def execute(self, query, params=None):
        return await self.database.query(query, params, self)


class RotationDB:
    def __init__(self):
        self.family = uuid.uuid4()
        self.parent = "rt_fixture_parent"
        self.parent_hash = idp._sha(self.parent)
        now = datetime.now(UTC)
        self.state = {"refresh": {self.parent_hash: {"id": uuid.uuid4(), "family_id": self.family,
                      "user_id": "alice", "client_id": "fixture", "expires_at": now + timedelta(hours=1),
                      "rotated_at": None, "revoked_at": None}},
                      "issued": {"initial-access": {"family_id": self.family, "expires_at": now + timedelta(hours=1)}},
                      "revoked": set()}
        self.principal = {"token": "alice", "user_id": "alice", "status": "active", "managed_required": False, "ok": True}
        self.locks = {}
        self.pause_issue = False
        self.issue_started = asyncio.Event()
        self.allow_issue = asyncio.Event()
        self.fail_refresh_insert = False
        self.race_reads = False
        self.reads = 0
        self.read_barrier = asyncio.Event()

    @asynccontextmanager
    async def transaction(self):
        connection = Connection(self)
        try:
            yield connection
        except BaseException:
            raise
        else:
            if connection.state is not None:
                self.state = connection.state
        finally:
            for lock in reversed(connection.acquired):
                lock.release()

    async def fetch_one(self, query, params):
        return (await self.query(query, params)).row

    async def execute(self, query, params):
        await self.query(query, params)
        return 1

    async def query(self, query, params, connection=None):
        compact = " ".join(query.split())
        if "pg_advisory_xact_lock" in compact:
            assert connection is not None, "Family lock must be transaction-scoped"
            lock = self.locks.setdefault(params[0], asyncio.Lock())
            await lock.acquire()
            connection.acquired.append(lock)
            connection.state = deepcopy(self.state)
            return Cursor()
        if connection is not None and connection.state is None:
            connection.state = deepcopy(self.state)
        state = connection.state if connection is not None else self.state
        if "FROM oauth_refresh_tokens WHERE token_sha256=%s" in compact:
            row = deepcopy(state["refresh"].get(params[0]))
            if connection is None and self.race_reads and compact.startswith("SELECT *"):
                self.reads += 1
                if self.reads >= 2:
                    self.read_barrier.set()
                await self.read_barrier.wait()
            return Cursor(row)
        if compact.startswith("SELECT jti,expires_at FROM oauth_issued_tokens WHERE family_id=%s"):
            return Cursor(rows=[{"jti": token, "expires_at": row["expires_at"]}
                                for token, row in state["issued"].items() if row["family_id"] == params[0]])
        if compact.startswith("SELECT token_sha256 FROM oauth_refresh_tokens WHERE family_id=%s"):
            return Cursor(rows=[{"token_sha256": digest} for digest, row in state["refresh"].items()
                                if row["family_id"] == params[0]])
        if "FROM principals" in compact:
            return Cursor(deepcopy(self.principal))
        if compact.startswith("UPDATE oauth_refresh_tokens SET rotated_at"):
            for row in state["refresh"].values():
                if row["id"] == params[0]:
                    row["rotated_at"] = datetime.now(UTC)
        elif compact.startswith("INSERT INTO oauth_issued_tokens"):
            if self.pause_issue:
                self.issue_started.set()
                await self.allow_issue.wait()
            state["issued"][params[0]] = {"family_id": params[3], "expires_at": params[4]}
        elif compact.startswith("INSERT INTO oauth_refresh_tokens"):
            if self.fail_refresh_insert:
                raise RuntimeError("Injected issuance failure")
            identity, family, user, client, digest, expires = params
            state["refresh"][digest] = {"id": identity, "family_id": family, "user_id": user, "client_id": client,
                                         "expires_at": expires, "rotated_at": None, "revoked_at": None}
        elif compact.startswith("UPDATE oauth_refresh_tokens SET revoked_at"):
            for row in state["refresh"].values():
                if row["family_id"] == params[0]:
                    row["revoked_at"] = row["revoked_at"] or datetime.now(UTC)
        elif compact.startswith("INSERT INTO agent_revoked_tokens") and "FROM oauth_issued_tokens" in compact:
            state["revoked"].update(identity for identity, row in state["issued"].items()
                                      if row["family_id"] == params[0] and row["expires_at"] > datetime.now(UTC))
        else:
            raise AssertionError(f"Unexpected query: {query}")
        return Cursor()


class OAuthRotationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = RotationDB()
        self.request = Request({"type": "http", "client": ("127.0.0.1", 1), "headers": []})
        self.patches = ExitStack()
        self.patches.enter_context(isolated_disposal())
        self.patches.enter_context(patch.dict(os.environ, {"AUTH_PROVIDER": "local"}))
        for name in ("fetch_one", "execute", "transaction"):
            self.patches.enter_context(patch.object(idp.db, name, getattr(self.db, name)))
        self.patches.enter_context(patch.object(idp, "issue_token", self.issue_token))
        self.addCleanup(self.patches.close)

    def issue_token(self, user, **kwargs):
        identity = str(uuid.uuid4())
        return "test-access-" + identity, {"jti": identity, "exp": datetime.now(UTC) + timedelta(minutes=10)}

    async def refresh(self, client="fixture"):
        return await idp.token(self.request, grant_type="refresh_token", client_id=client,
                               username=None, password=None, refresh_token=self.db.parent)

    def assert_family_revoked(self):
        self.assertTrue(all(row["revoked_at"] for row in self.db.state["refresh"].values() if row["family_id"] == self.db.family))
        self.assertTrue(all(identity in self.db.state["revoked"] for identity, row in self.db.state["issued"].items()
                            if row["family_id"] == self.db.family))

    async def test_concurrent_refresh_has_at_most_one_success_and_revokes_descendants(self):
        self.db.race_reads = True
        replies = await asyncio.wait_for(asyncio.gather(self.refresh(), self.refresh()), 2)
        self.assertEqual(sum(isinstance(reply, dict) for reply in replies), 1)
        self.assert_family_revoked()

    async def paused_issuance(self, concurrent):
        self.db.pause_issue = True
        winner = asyncio.create_task(self.refresh())
        await asyncio.wait_for(self.db.issue_started.wait(), 1)
        follower = asyncio.create_task(concurrent())
        for _ in range(5):
            await asyncio.sleep(0)
        self.db.allow_issue.set()
        return await asyncio.wait_for(asyncio.gather(winner, follower), 2)

    async def test_reuse_during_issuance_cannot_leave_valid_descendants(self):
        replies = await self.paused_issuance(self.refresh)
        self.assertEqual(sum(isinstance(reply, dict) for reply in replies), 1)
        self.assert_family_revoked()

    async def test_revocation_endpoint_waits_for_issuance_commit(self):
        replies = await self.paused_issuance(lambda: idp.revoke(self.db.parent, token_type_hint="refresh_token"))
        self.assertIsInstance(replies[0], dict)
        self.assertEqual(replies[1].status_code, 200)
        self.assert_family_revoked()

    async def test_issue_failure_rolls_back_rotation_and_partial_access_issuance(self):
        self.db.fail_refresh_insert = True
        with self.assertRaisesRegex(RuntimeError, "Injected issuance failure"):
            await self.refresh()
        self.assertIsNone(self.db.state["refresh"][self.db.parent_hash]["rotated_at"])
        self.assertEqual(set(self.db.state["issued"]), {"initial-access"})

    async def test_expiry_revocation_and_client_mismatch_remain_denied(self):
        self.db.state["refresh"][self.db.parent_hash]["expires_at"] = datetime.now(UTC) - timedelta(seconds=1)
        self.assertEqual((await self.refresh()).status_code, 400)
        self.db.state["refresh"][self.db.parent_hash].update(expires_at=datetime.now(UTC) + timedelta(hours=1),
                                                            revoked_at=datetime.now(UTC))
        self.assertEqual((await self.refresh()).status_code, 400)
        self.db.state["refresh"][self.db.parent_hash]["revoked_at"] = None
        self.assertEqual((await self.refresh("other-client")).status_code, 400)
        self.assertIsNone(self.db.state["refresh"][self.db.parent_hash]["rotated_at"])
        self.assertEqual(len(self.db.state["issued"]), 1)

    async def test_managed_account_rejects_refresh_and_revokes_family(self):
        self.db.principal["managed_required"] = True
        response = await self.refresh()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(json.loads(response.body)["error"], "invalid_grant")
        self.assert_family_revoked()

    async def test_password_success_and_bad_password_semantics_are_preserved(self):
        from app import agent_service
        with patch.object(agent_service, "login_allowed", return_value=True), \
             patch.object(agent_service, "record_failed_login") as failed:
            response = await idp.token(self.request, grant_type="password", client_id="fixture",
                                       username="alice", password="test-only", refresh_token=None)
            self.assertIsInstance(response, dict)
            self.db.principal["ok"] = False
            response = await idp.token(self.request, grant_type="password", client_id="fixture",
                                       username="alice", password="bad-test-only", refresh_token=None)
            self.assertEqual(response.status_code, 400)
            failed.assert_called_once()


if __name__ == "__main__":
    unittest.main()
