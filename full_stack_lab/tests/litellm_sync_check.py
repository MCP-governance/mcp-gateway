"""LiteLLM management HTTP double + in-memory queue; no real MCP or product evidence.

    py -B -X utf8 full_stack_lab/tests/litellm_sync_check.py
"""
from __future__ import annotations

import asyncio
import copy
import importlib
import json
import os
import sys
import tempfile
import threading
import unittest
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gateway"))
from app import litellm_sync as sync  # noqa: E402

KEY = "a" * 64
OTHER_KEY = "b" * 64


class State:
    def __init__(self):
        self.server = None
        self.keys = {KEY: {"user_id": "lite-alice", "object_permission": {
            "mcp_servers": ["unrelated"], "mcp_tool_permissions": {"unrelated": ["keep"]}, "vector_stores": ["vec"]}}}
        self.teams = {"team": {"members_with_roles": [{"user_id": "lite-alice"}], "object_permission": {"mcp_servers": ["unrelated"]}}}
        self.credentials = [{"user_id": "external-owner", "credential_type": "oauth2"}]
        self.sessions = [{"user_id": "lite-alice"}, {"user_id": "external-owner"}, {"user_id": "unrelated-user"}]
        self.requests = []
        self.fail = None
        self.keep_server = self.wrong_server = self.keep_permissions = self.keep_credentials = self.keep_sessions = False
        self.explicit_access = True
        self.cascade_credentials = False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.dispatch()

    def do_POST(self):
        self.dispatch()

    def do_PUT(self):
        self.dispatch()

    def do_DELETE(self):
        self.dispatch()

    def dispatch(self):
        state = self.server.state
        method, parsed = self.command, urlsplit(self.path)
        path, query = parsed.path, parse_qs(parsed.query)
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        body = json.loads(raw) if raw else None
        state.requests.append((method, path, query, body, self.headers.get("Authorization")))
        status, result = 200, None
        if state.fail == (method, path):
            status, result = 503, {"error": "synthetic failure"}
        elif path == "/config/field/info":
            result = {"field_value": state.explicit_access}
        elif path == "/v1/mcp/server" and method in {"POST", "PUT"}:
            state.server = {**(state.server or {}), **body, "approval_status": "active"}
            status = 201 if method == "POST" else 202
            result = state.server
        elif path.endswith("/user-credentials"):
            result = state.credentials
        elif path.endswith(("/user-credential", "/oauth-user-credential")):
            if not state.keep_credentials:
                state.credentials = [c for c in state.credentials if c["user_id"] != query["user_id"][0]]
            result = {"has_credential": False}
        elif path == "/v1/mcp/sessions":
            if method == "DELETE" and not state.keep_sessions:
                state.sessions = [s for s in state.sessions if s["user_id"] != query["user_id"][0]]
            result = {"worker_pid": 123, "sessions": state.sessions}
        elif path in {"/key/info", "/team/info"}:
            key = query["key" if path.startswith("/key") else "team_id"][0]
            result = {"info" if path.startswith("/key") else "team_info":
                      (state.keys if path.startswith("/key") else state.teams)[key]}
        elif path in {"/key/update", "/team/update"}:
            if not state.keep_permissions:
                target = state.keys[body["key"]] if path.startswith("/key") else state.teams[body["team_id"]]
                target["object_permission"] = body["object_permission"]
            result = {"status": "success"}
        elif path.startswith("/v1/mcp/server/"):
            if method == "DELETE":
                if not state.keep_server:
                    state.server = None
                    if state.cascade_credentials:
                        state.credentials = []
                status = 202
            elif state.server is None:
                status = 404
            else:
                result = {**state.server, **({"allowed_tools": ["unapproved"]} if state.wrong_server else {})}
        else:
            status = 404
        data = json.dumps(result).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class HTTPTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.state = State()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.state = self.state
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = "http://127.0.0.1:" + str(self.server.server_port)
        self.api = sync.ManagementAPI(self.url)
        self.config = {"users": [{"mint_user_id": "alice", "litellm_user_id": "lite-alice", "key_hashes": [KEY]}],
                       "teams": [{"team_id": "team", "mint_user_ids": ["alice"]}], "workers": [self.url]}
        self.plan = {"server_id": "approved", "remote_id": "mint_approved", "active": True, "endpoint": "https://upstream.test/mcp",
                     "tools": ["read"], "allowed_users": ["alice"]}
        self.observations = []
        self.env = patch.dict(os.environ, {"MINT_LITELLM_ADMIN_KEY": "synthetic-management-key", "MINT_LITELLM_SYNC_KEY_FILE": "",
                                          "MINT_LITELLM_SYNC_KEY_ENV": "MINT_LITELLM_ADMIN_KEY"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    async def run_plan(self):
        return await sync.propagate(self.api, self.plan, self.config, self.observations)

    async def test_create_update_readback_and_preserve_unrelated_permissions(self):
        await self.run_plan()
        self.assertIn(("POST", "/v1/mcp/server"), [(r[0], r[1]) for r in self.state.requests])
        self.plan["tools"] = ["read", "search"]
        await self.run_plan()
        self.assertIn(("PUT", "/v1/mcp/server"), [(r[0], r[1]) for r in self.state.requests])
        for target in (self.state.keys[KEY], self.state.teams["team"]):
            self.assertEqual(target["object_permission"]["mcp_tool_permissions"]["mint_approved"], ["read", "search"])
            self.assertIn("unrelated", target["object_permission"]["mcp_servers"])
        self.assertEqual(self.state.keys[KEY]["object_permission"]["vector_stores"], ["vec"])
        self.assertTrue(self.observations[-1]["matches"])
        self.assertTrue(all(r[-1] == "Bearer synthetic-management-key" for r in self.state.requests))
        self.assertNotIn("employee-token", json.dumps(self.state.requests))

    async def test_delete_credentials_sessions_and_readback_including_unknown_credential_owner(self):
        await self.run_plan()
        self.plan["active"] = False
        await self.run_plan()
        self.assertIsNone(self.state.server)
        self.assertEqual(self.state.credentials, [])
        self.assertEqual(self.state.sessions, [{"user_id": "unrelated-user"}])
        self.assertEqual(self.state.keys[KEY]["object_permission"]["mcp_tool_permissions"]["mint_approved"], [])
        self.assertEqual(self.observations[-1], {"kind": "server", "present": False})
        self.assertTrue(any(o["kind"] == "credentials" and o["remaining"] == 0 for o in self.observations))
        self.assertTrue(any(o["kind"] == "sessions" and o["remaining"] == 0 for o in self.observations))
        await self.run_plan()  # recovery after a lost DELETE response is idempotent
        self.plan["subjects"] = sync.subjects(self.config)
        self.config["users"][0]["key_hashes"] = []
        self.state.keys[KEY]["status"] = "deleted"
        await self.run_plan()
        self.assertTrue(any(o["kind"] == "key" and o.get("absent") for o in self.observations))

    async def test_permission_update_preserves_existing_authentication_and_credentials(self):
        await self.run_plan()
        self.state.server.update(auth_type="oauth2", is_byok=True, credentials={"client_secret": "synthetic-upstream-secret"})
        self.plan["tools"] = ["read", "search"]
        await self.run_plan()
        self.assertEqual(self.state.server["auth_type"], "oauth2")
        self.assertTrue(self.state.server["is_byok"])
        body = next(r[3] for r in reversed(self.state.requests) if r[0] == "PUT")
        self.assertNotIn("auth_type", body)
        self.assertNotIn("credentials", body)
        self.assertNotIn("synthetic-upstream-secret", json.dumps(self.observations))

    async def test_success_response_with_server_readback_mismatch_fails(self):
        self.state.wrong_server = True
        with self.assertRaisesRegex(sync.SyncError, "server-readback-mismatch"):
            await self.run_plan()
        self.assertTrue(any(o["kind"] == "server" and not o["matches"] for o in self.observations))
        self.assertIsNone(self.state.server)

    async def test_success_response_with_permissions_mismatch_removes_partial_server(self):
        self.state.keep_permissions = True
        with self.assertRaisesRegex(sync.SyncError, "permissions-readback-mismatch"):
            await self.run_plan()
        self.assertIsNone(self.state.server)

    async def test_delete_readback_mismatch_never_completes(self):
        await self.run_plan()
        self.plan["active"] = False
        self.state.keep_server = True
        with self.assertRaisesRegex(sync.SyncError, "server-delete-readback-mismatch"):
            await self.run_plan()

    async def test_credentials_and_sessions_are_verified_independently(self):
        await self.run_plan()
        self.plan["active"] = False
        self.state.keep_credentials = self.state.keep_sessions = True
        with self.assertRaisesRegex(sync.SyncError, "credentials-readback-mismatch.*sessions-readback-mismatch"):
            await self.run_plan()
        self.assertIsNone(self.state.server)

    async def test_credential_owners_are_enumerated_before_server_cascade_delete(self):
        await self.run_plan()
        self.plan["active"] = False
        self.state.cascade_credentials = True
        await self.run_plan()
        self.assertEqual(self.state.sessions, [{"user_id": "unrelated-user"}])
        self.assertIn("external-owner", self.plan["session_users"])

    async def test_lost_population_evidence_cannot_turn_into_completion_after_retry(self):
        await self.run_plan()
        self.plan["active"] = False
        self.state.fail = ("GET", "/v1/mcp/server/mint_approved/user-credentials")
        with self.assertRaises(sync.SyncError):
            await self.run_plan()
        self.assertIsNone(self.state.server)
        self.assertTrue(self.plan["inventory_unknown"])
        self.state.fail = None
        with self.assertRaisesRegex(sync.SyncError, "credential-owner-inventory-unknown"):
            await self.run_plan()

    async def test_wrong_key_owner_and_team_membership_never_receive_tools(self):
        self.state.keys[KEY]["user_id"] = "mallory"
        self.state.teams["team"]["members_with_roles"].append({"user_id": "mallory"})
        with self.assertRaisesRegex(sync.SyncError, "key-owner-mismatch.*team-membership-mismatch"):
            await self.run_plan()
        self.assertIsNone(self.state.server)
        self.assertFalse([r for r in self.state.requests if r[1] in {"/key/update", "/team/update"}])

    async def test_unapproved_user_gets_explicit_empty_tools(self):
        self.plan["allowed_users"] = ["bob"]
        await self.run_plan()
        self.assertEqual(self.state.keys[KEY]["object_permission"]["mcp_tool_permissions"]["mint_approved"], [])
        self.assertEqual(self.state.teams["team"]["object_permission"]["mcp_tool_permissions"]["mint_approved"], [])

    async def test_open_default_and_unowned_server_are_not_adopted(self):
        self.state.explicit_access = False
        with self.assertRaisesRegex(sync.SyncError, "explicit-key-access-required"):
            await self.run_plan()
        self.assertIsNone(self.state.server)
        self.state.server = {"mcp_info": {"mint_server_id": "someone-else"}}
        with self.assertRaisesRegex(sync.SyncError, "server-ownership-conflict"):
            await self.run_plan()
        self.assertIsNotNone(self.state.server)

    async def test_secret_rotation_and_error_bodies_are_not_exposed(self):
        await self.api.request("GET", "/v1/mcp/server/nope", missing=True)
        with patch.dict(os.environ, {"MINT_LITELLM_ADMIN_KEY": "rotated-synthetic-key"}):
            await self.api.request("GET", "/v1/mcp/server/nope", missing=True)
        self.assertEqual(self.state.requests[-1][-1], "Bearer rotated-synthetic-key")
        self.state.fail = ("GET", "/v1/mcp/server/nope")
        with self.assertRaisesRegex(sync.SyncError, "^http-503$"):
            await self.api.request("GET", "/v1/mcp/server/nope", missing=True)

    async def test_failed_job_waits_retries_after_restart_and_appends_evidence(self):
        package = importlib.import_module("app")
        jobs, events = {}, []
        transaction_depth = 0
        guard = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock(), close=AsyncMock())

        async def execute(query, params=()):
            result = None
            if "pg_try_advisory" in query:
                result = {"ok": True}
            elif "SELECT * FROM litellm_sync_jobs" in query:
                result = copy.deepcopy(jobs.get(params[0]))
            elif "INSERT INTO litellm_sync_jobs" in query:
                jobs[params[0]] = {"server_id": params[0], "revision": 1, "attempts": 0, "subjects": [], "session_users": [],
                                   "fingerprint": None, "status": "pending", "inventory_unknown": False,
                                   "retry_at": datetime.now(timezone.utc)}
            elif "UPDATE litellm_sync_jobs" in query:
                self.assertEqual(query.count("%s"), len(params))
                if len(params) == 5:
                    bound, owners, unknown, event, sid = params
                    jobs[sid].update(subjects=bound.obj, session_users=owners.obj, inventory_unknown=unknown,
                                     event_id=event, attempts=jobs[sid]["attempts"] + 1)
                    return SimpleNamespace(fetchone=AsyncMock(return_value=None))
                state, digest, seconds, bound, owners, unknown, event, sid, revision = params
                row = jobs[sid]
                if row["revision"] == revision:
                    row.update(status=state, fingerprint=digest, subjects=bound.obj, session_users=owners.obj,
                               inventory_unknown=unknown,
                               event_id=event, attempts=row["attempts"] + 1,
                               retry_at=datetime.now(timezone.utc) + timedelta(seconds=seconds))
            return SimpleNamespace(fetchone=AsyncMock(return_value=result))

        @asynccontextmanager
        async def transaction():
            nonlocal transaction_depth
            transaction_depth += 1
            try:
                yield SimpleNamespace(execute=execute)
            finally:
                transaction_depth -= 1

        guard.execute = AsyncMock(side_effect=execute)

        @asynccontextmanager
        async def guard_connection():
            yield guard

        async def fetch_one(query, params):
            return await (await execute(query, params)).fetchone()

        async def record(*args, **kwargs):
            self.assertEqual(transaction_depth, 1)
            events.append({"outcome": args[1], **copy.deepcopy(kwargs["scope"])})
            return len(events)

        original_propagate = sync.propagate

        async def outside_transaction(*args):
            self.assertEqual(transaction_depth, 0)
            await original_propagate(*args)

        database = SimpleNamespace(transaction=transaction, fetch_one=fetch_one, execute=execute,
                                   pool=AsyncMock(return_value=SimpleNamespace(connection=guard_connection)),
                                   fetch_all=AsyncMock(side_effect=lambda q: [{"server_id": s} for s in jobs]))
        registry = SimpleNamespace(ALL_PRINCIPALS="*", runtime=lambda: {"servers": {"approved": {}}})
        review = SimpleNamespace(record_event=record)
        json_module = SimpleNamespace(Jsonb=lambda obj: SimpleNamespace(obj=obj))
        self.state.fail = ("POST", "/v1/mcp/server")
        with patch.object(package, "db", database, create=True), patch.object(package, "registry", registry, create=True), \
             patch.object(package, "review", review, create=True), \
             patch.dict(sys.modules, {"psycopg": SimpleNamespace(), "psycopg.types": SimpleNamespace(), "psycopg.types.json": json_module}), \
             patch.object(sync, "enabled", return_value=True), patch.object(sync, "configuration", return_value=(self.url, self.config)), \
             patch.object(sync, "propagate", side_effect=outside_transaction), \
             patch.object(sync, "desired", AsyncMock(side_effect=lambda sid: copy.deepcopy(self.plan))):
            await sync.reconcile()
            self.assertEqual(jobs["approved"]["status"], "failed")
            requests = len(self.state.requests)
            await sync.reconcile()
            self.assertEqual(len(self.state.requests), requests)
            self.state.fail = None
            jobs["approved"]["retry_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
            await sync.reconcile()
            self.assertEqual(jobs["approved"]["status"], "verified")
            # A revocation committed while HTTP was running must never finish the stale grant.
            jobs["approved"].update(status="pending", retry_at=datetime.now(timezone.utc))
            withdrawn = {**self.plan, "active": False, "tools": [], "allowed_users": [], "endpoint": None}
            with patch.object(sync, "desired", AsyncMock(side_effect=[copy.deepcopy(self.plan), copy.deepcopy(withdrawn)])):
                await sync.reconcile()
            self.assertEqual(jobs["approved"]["status"], "failed")
            self.assertIsNone(self.state.server)
            self.plan = withdrawn
            await sync.reconcile()
            self.assertEqual(jobs["approved"]["status"], "verified")
            # A concurrent enqueue must keep its immediate retry and newer revision.
            jobs["approved"].update(status="pending", retry_at=datetime.now(timezone.utc))

            async def enqueue_during_http(*args):
                await outside_transaction(*args)
                jobs["approved"].update(revision=2, status="pending", retry_at=datetime.now(timezone.utc))

            with patch.object(sync, "propagate", side_effect=enqueue_during_http):
                await sync.reconcile()
            self.assertEqual(jobs["approved"]["status"], "pending")
            self.assertEqual(jobs["approved"]["revision"], 2)
            self.assertEqual(events[-1]["failure"], "queued-revision-changed")
            await sync.reconcile()
            self.assertEqual(jobs["approved"]["status"], "verified")
        self.assertEqual([e["outcome"] for e in events], ["failed", "verified", "failed", "verified", "failed", "verified"])
        self.assertEqual([e["attempt"] for e in events], [1, 2, 3, 4, 5, 6])
        self.assertEqual(sum("pg_advisory_unlock" in call.args[0] for call in guard.execute.call_args_list), 7)
        guard.close.assert_not_awaited()
        self.assertEqual(events[-1]["evidence_class"], "G5")
        self.assertFalse(events[-1]["observations"][-1]["present"])
        self.assertNotIn("synthetic-management-key", json.dumps(events))


class BoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_writer_session_lock_is_released_on_cancellation_and_busy(self):
        package = importlib.import_module("app")
        for acquired, cancel_acquire in ((True, False), (False, False), (True, True)):
            async def execute(query):
                if "pg_try_advisory_lock" in query and cancel_acquire:
                    raise asyncio.CancelledError()
                return SimpleNamespace(fetchone=AsyncMock(return_value={"ok": acquired}))

            guard = SimpleNamespace(execute=AsyncMock(side_effect=execute), commit=AsyncMock(),
                                    rollback=AsyncMock(), close=AsyncMock())

            @asynccontextmanager
            async def connection():
                yield guard

            database = SimpleNamespace(pool=AsyncMock(return_value=SimpleNamespace(connection=connection)))
            with patch.object(package, "db", database, create=True), patch.object(sync, "enabled", return_value=True), \
                 patch.object(sync, "configuration", return_value=("http://localhost:4000", {})), \
                 patch.object(sync, "_reconcile", side_effect=asyncio.CancelledError()) as process:
                if acquired:
                    with self.assertRaises(asyncio.CancelledError):
                        await sync.reconcile()
                else:
                    await sync.reconcile()
                    process.assert_not_called()
            self.assertIn("pg_advisory_unlock", guard.execute.call_args.args[0])
            guard.rollback.assert_awaited_once()
            guard.close.assert_not_awaited()

    async def test_desired_state_requires_completed_registration_and_current_mint_scope(self):
        package = importlib.import_module("app")
        spec = {"intake_id": "intake", "valid_until": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                "endpoint": "https://upstream.test/mcp", "tools": {"read": "r"}, "allowed_principals": ["employee-token"]}
        row = {"status": "READY", "lifecycle": "OPERATING"}
        event = {"scope": {"intake": "intake"}}

        async def fetch_one(query, params):
            return row if "mcp_servers" in query else event

        async def fetch_all(query, params):
            if "mcp_tools" in query:
                return [{"name": "read"}, {"name": "not-in-approved-spec"}]
            self.assertEqual(params, (False, ["employee-token"]))  # (everyone?, tokens) D-234
            return [{"user_id": "alice"}]

        database = SimpleNamespace(fetch_one=fetch_one, fetch_all=fetch_all)
        registry = SimpleNamespace(ALL_PRINCIPALS="*", runtime=lambda: {"servers": {"approved": spec}})
        with patch.object(package, "db", database, create=True), patch.object(package, "registry", registry, create=True):
            plan = await sync.desired("approved")
            self.assertTrue(plan["active"])
            self.assertEqual(plan["tools"], ["read"])
            self.assertEqual(plan["allowed_users"], ["alice"])
            self.assertNotIn("employee-token", json.dumps(plan))
            for status, lifecycle in (("DISABLED", "OPERATING"), ("BLOCKED_SUPPLY_CHAIN", "OPERATING"),
                                      ("READY", "TERMINATING"), ("READY", "RETIRED"), ("PENDING", "OPERATING")):
                row.update(status=status, lifecycle=lifecycle)
                self.assertFalse((await sync.desired("approved"))["active"])
            row.update(status="READY", lifecycle="OPERATING")
            event["scope"]["intake"] = "different-approval"
            self.assertFalse((await sync.desired("approved"))["active"])
            event["scope"]["intake"] = "intake"
            spec["valid_until"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
            self.assertFalse((await sync.desired("approved"))["active"])

    async def test_local_or_embedded_credentials_are_never_sent_to_litellm(self):
        package = importlib.import_module("app")
        spec = {"intake_id": "intake", "valid_until": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                "endpoint": "local-run://approved", "tools": {"read": "r"}, "allowed_principals": ["token"]}
        database = SimpleNamespace(fetch_one=AsyncMock(side_effect=lambda q, p: {"status": "READY", "lifecycle": "OPERATING"}
                                   if "mcp_servers" in q else {"scope": {"intake": "intake"}}),
                                   fetch_all=AsyncMock(side_effect=lambda q, p: [{"name": "read"}] if "mcp_tools" in q else [{"user_id": "alice"}]))
        with patch.object(package, "db", database, create=True), \
             patch.object(package, "registry", SimpleNamespace(ALL_PRINCIPALS="*", runtime=lambda: {"servers": {"approved": spec}}), create=True):
            for endpoint in ("local-run://approved", "https://user:secret@upstream.test/mcp", "https://upstream.test/mcp?token=secret"):
                spec["endpoint"] = endpoint
                plan = await sync.desired("approved")
                self.assertFalse(plan["active"])
                self.assertTrue(plan["unsupported"])
                self.assertNotIn("secret", json.dumps(plan))

    async def test_shutdown_waits_for_inflight_management_write(self):
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()

        def blocking(*args):
            entered.set()
            release.wait(2)
            finished.set()

        api = sync.ManagementAPI("http://localhost:4000")
        with patch.object(api, "_request", side_effect=blocking), patch.object(sync, "management_key", return_value="synthetic"):
            request = asyncio.create_task(api.request("POST", "/v1/mcp/server", {}))
            await asyncio.to_thread(entered.wait, 2)
            request.cancel()
            await asyncio.sleep(0)
            self.assertFalse(request.done())
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await request
            self.assertTrue(finished.is_set())

    async def test_disabled_installation_does_not_read_config_database_or_secrets(self):
        with patch.dict(os.environ, {"MINT_LITELLM_SYNC_URL": ""}), \
             patch.object(sync, "configuration", side_effect=AssertionError("must not read")), \
             patch.object(sync, "management_key", side_effect=AssertionError("must not read")):
            await sync.initialize()
            await sync.enqueue("any")
            await sync.reconcile()
            await sync.watch()
            self.assertEqual(await sync.statuses(), {})

    async def test_origins_do_not_allow_credentials_redirects_or_paths(self):
        for value in ("https://user:secret@example.test", "https://example.test/?key=x", "file:///tmp/key", "https://example.test/path"):
            with self.assertRaises(sync.SyncError):
                sync.origin(value)
        self.assertEqual(sync.retry_seconds(0), 5)
        self.assertEqual(sync.retry_seconds(1000), 300)

    async def test_configuration_rejects_plain_keys_and_missing_worker_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bindings.json"
            value = {"users": [{"mint_user_id": "alice", "litellm_user_id": "a", "key_hashes": ["sk-plaintext"]}], "workers": ["http://localhost:4000"]}
            path.write_text(json.dumps(value), encoding="utf-8")
            with patch.dict(os.environ, {"MINT_LITELLM_SYNC_URL": "http://localhost:4000", "MINT_LITELLM_SYNC_BINDINGS_FILE": str(path)}):
                with self.assertRaisesRegex(sync.SyncError, "invalid-key-hash"):
                    sync.configuration()
                value["users"][0]["key_hashes"] = [KEY]
                value["workers"] = []
                path.write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaisesRegex(sync.SyncError, "worker-inventory-required"):
                    sync.configuration()
                with patch.dict(os.environ, {"DB_POOL_MAX": "1"}):
                    with self.assertRaisesRegex(sync.SyncError, "sync-requires-two-pool-connections"):
                        sync.configuration()


if __name__ == "__main__":
    unittest.main()
