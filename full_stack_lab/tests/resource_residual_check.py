"""DEV-08: product definitions with AsyncMock DB/HTTP doubles, never an MCP server.

Runs with the standard library on the notebook. Cryptographic, PostgreSQL and
resource-server effects belong to resource_residual_pg_check.py on the appliance.
"""
from __future__ import annotations

import ast
import asyncio
import hashlib
import importlib.util
import os
import sys
import unittest
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

APP = Path(__file__).resolve().parent.parent / "gateway" / "app"
UTC = timezone.utc


def definitions(filename, names, namespace):
    tree = ast.parse((APP / filename).read_text(encoding="utf-8"))
    selected = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            node.decorator_list = []
            selected.append(node)
        elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in node.targets):
            selected.append(node)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id in names:
            selected.append(node)
    if len(selected) != len(names):
        raise AssertionError("product definitions missing")
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(APP / filename), "exec"), namespace)
    return SimpleNamespace(**namespace)


spec = importlib.util.spec_from_file_location("residual_upstream_sessions", APP / "upstream_sessions.py")
sessions = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = sessions
spec.loader.exec_module(sessions)


class Introspection(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = SimpleNamespace(fetch_one=AsyncMock())
        self.disposal = SimpleNamespace(blocked=Mock(return_value=False))
        self.managed = AsyncMock(return_value=None)
        self.validate = AsyncMock()
        package = ModuleType("residual_test_gateway")
        endpoint = ModuleType(package.__name__ + ".endpoint_plane")
        endpoint.managed_failure = self.managed
        oidc = ModuleType(package.__name__ + ".oidc")
        oidc.validate_session = self.validate
        self.modules = patch.dict(sys.modules, {package.__name__: package,
                                               endpoint.__name__: endpoint, oidc.__name__: oidc})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.environment = patch.dict(os.environ, {"AUTH_PROVIDER": "local"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.now = datetime.now(UTC)
        self.claims = {"jti": "token-id", "sub": "employee", "scope": "mcp", "client_id": "client",
                       "exp": int((self.now + timedelta(minutes=10)).timestamp()),
                       "iat": int(self.now.timestamp()), "iss": "issuer", "aud": "gateway"}
        self.refresh = {"revoked_at": None, "rotated_at": None, "expires_at": self.now + timedelta(hours=1),
                        "user_id": "employee", "client_id": "client"}
        self.person = {"token": "employee", "status": "active", "managed_required": False}
        self.jwt = SimpleNamespace(decode=Mock(return_value=self.claims), PyJWTError=ValueError)
        self.api = definitions("idp.py", {"introspection", "introspect"}, {
            "__name__": package.__name__ + ".idp", "__package__": package.__name__,
            "asyncio": asyncio, "datetime": datetime, "UTC": UTC, "db": self.db, "disposal": self.disposal,
            "os": os, "jwt": self.jwt, "ALGORITHM": "EdDSA", "AUDIENCE": "gateway", "ISSUER": "issuer",
            "public_key": lambda: "public", "_sha": lambda value: hashlib.sha256(value.encode()).hexdigest(),
            "Form": lambda *args, **kwargs: None, "Header": lambda *args, **kwargs: None,
            "HTTPException": PermissionError, "authenticated_user": AsyncMock(return_value={"roles": ["admin"]}),
            "JSONResponse": lambda body, headers: SimpleNamespace(body=body, headers=headers),
        })

    async def test_access_requeries_after_revocation_and_response_is_not_cacheable(self):
        self.db.fetch_one.side_effect = [None, self.person, {"revoked": True}]
        before = await self.api.introspect("access", "Bearer admin")
        after = await self.api.introspect("access", "Bearer admin")
        self.assertIs(before.body["active"], True)
        self.assertEqual(after.body, {"active": False})
        self.assertEqual(before.headers["Cache-Control"], "no-store")
        self.assertEqual(after.headers["Cache-Control"], "no-store")
        self.assertEqual(self.db.fetch_one.await_count, 3)

    async def test_access_account_and_managed_state_are_current(self):
        self.db.fetch_one.side_effect = [None, {**self.person, "status": "suspended"}, None, self.person]
        self.assertEqual(await self.api.introspection("access"), {"active": False})
        self.managed.return_value = "expired heartbeat"
        self.assertEqual(await self.api.introspection("access"), {"active": False})

    async def test_access_invalid_signature_and_signed_disposal_never_reuse_active(self):
        self.jwt.decode.side_effect = ValueError("invalid")
        self.assertEqual(await self.api.introspection("invalid"), {"active": False})
        self.jwt.decode.side_effect = None
        self.disposal.blocked.return_value = True
        self.assertEqual(await self.api.introspection("access"), {"active": False})
        self.db.fetch_one.assert_not_awaited()

    async def test_refresh_account_stop_then_recovery_requeries(self):
        self.db.fetch_one.side_effect = [self.refresh, self.person, self.refresh,
                                        {**self.person, "status": "suspended"}, self.refresh, self.person]
        self.assertIs((await self.api.introspection("rt_secret"))["active"], True)
        self.assertEqual(await self.api.introspection("rt_secret"), {"active": False})
        self.assertIs((await self.api.introspection("rt_secret"))["active"], True)

    async def test_refresh_missing_account_managed_transition_and_oidc_are_inactive(self):
        for person, provider in ((None, "local"), ({**self.person, "managed_required": True}, "local"),
                                 (self.person, "oidc")):
            with self.subTest(person=person, provider=provider), patch.dict(os.environ, {"AUTH_PROVIDER": provider}):
                self.db.fetch_one.side_effect = [self.refresh, person]
                self.assertEqual(await self.api.introspection("rt_secret"), {"active": False})

    async def test_refresh_revoked_rotated_expired_unknown_and_signed_list(self):
        for stored in (None, {**self.refresh, "revoked_at": self.now},
                       {**self.refresh, "rotated_at": self.now},
                       {**self.refresh, "expires_at": self.now - timedelta(seconds=1)}):
            with self.subTest(stored=stored):
                self.db.fetch_one.side_effect = None
                self.db.fetch_one.return_value = stored
                self.assertEqual(await self.api.introspection("rt_secret"), {"active": False})
        self.disposal.blocked.return_value = True
        self.db.fetch_one.reset_mock()
        self.assertEqual(await self.api.introspection("rt_secret"), {"active": False})
        self.db.fetch_one.assert_not_awaited()

    async def test_db_failure_does_not_fall_back_to_previous_active(self):
        self.db.fetch_one.side_effect = [self.refresh, self.person, RuntimeError("db unavailable"),
                                        self.refresh, self.person]
        self.assertIs((await self.api.introspection("rt_secret"))["active"], True)
        with self.assertRaisesRegex(RuntimeError, "db unavailable"):
            await self.api.introspection("rt_secret")
        self.assertIs((await self.api.introspection("rt_secret"))["active"], True)


class Evidence(unittest.TestCase):
    def setUp(self):
        self.model = definitions("decommission.py", {"EVIDENCE_KINDS", "STATE_EVIDENCE_FOR", "DEFAULT_STATE_EVIDENCE",
                                                    "_judge_target", "_evidence_shows_revoked"}, {})
        self.at = datetime.now(UTC)
        self.target = {"kind": "client-token", "holder": "org", "status": "REVOKED", "revoked_at": self.at,
                       "verification": "introspection", "expires_at": self.at + timedelta(minutes=10)}
        self.activity = {"executed": 0, "unknown": 0}

    def evidence(self, kind, **detail):
        return {"id": kind, "kind": kind, "observed_at": self.at, "detail": detail}

    def judge(self, evidence, **target):
        return self.model._judge_target({**self.target, **target}, evidence, self.activity, True)

    def test_issuer_inactive_stateless_gap_and_absent_evidence_are_separate(self):
        evidence = [self.evidence("introspection", active=False)]
        self.assertEqual(self.judge(evidence)["grade"], "T1")  # The issuer target only.
        stateless = self.judge(evidence, verification="stateless")
        self.assertEqual(stateless["grade"], "T2")
        self.assertFalse(stateless["criteria"]["C3"]["met"])
        self.assertTrue(stateless["criteria"]["C4"]["met"])
        self.assertEqual(self.judge([])["grade"], "T3")

    def test_resource_acceptance_overrides_inactive_introspection_for_token_kinds(self):
        for kind in ("client-token", "refresh-token"):
            with self.subTest(kind=kind):
                evidence = [self.evidence("introspection", active=False),
                            self.evidence("resource-rejection", rejected=False, http_status=200)]
                result = self.judge(evidence, kind=kind)
                self.assertEqual(result["grade"], "T2")
                self.assertFalse(result["criteria"]["C3"]["met"])
                evidence.append(self.evidence("resource-rejection", rejected=True, http_status=401))
                self.assertEqual(self.judge(evidence, kind=kind)["grade"], "T1")

    def test_resource_rejection_is_token_state_evidence_but_old_evidence_is_not(self):
        rejected = self.evidence("resource-rejection", rejected=True, http_status=401)
        self.assertEqual(self.judge([rejected])["grade"], "T1")
        rejected["observed_at"] -= timedelta(seconds=1)
        self.assertEqual(self.judge([rejected])["grade"], "T3")

    def test_provider_credential_acceptance_overrides_absence_from_issuer_list(self):
        evidence = [self.evidence("credential-check", present=False),
                    self.evidence("resource-rejection", rejected=False, http_status=200)]
        self.assertEqual(self.judge(evidence, kind="server-held-credential", holder="provider")["grade"], "T2")
        self.assertEqual(self.judge([], kind="server-held-credential", status="UNVERIFIABLE")["grade"], "T3")


class Pool(unittest.IsolatedAsyncioTestCase):
    async def test_busy_lease_and_waiter_cannot_reaccess_after_close(self):
        pool = sessions.Pool(size=1)
        key = sessions.Key("employee", ("conversation", "jti"), "server", "credential", "http://server/mcp", "legacy", 5)
        client = SimpleNamespace(call_tool=AsyncMock(return_value=SimpleNamespace(is_error=False)))
        closed = []

        @asynccontextmanager
        async def factory():
            try:
                yield client
            finally:
                closed.append(True)

        async def waiting():
            async with pool.borrow(key, factory):
                self.fail("ended pool generation was reused")

        try:
            async with pool.borrow(key, factory) as lease:
                await lease.call_tool("before", {})
                waiter = asyncio.create_task(waiting())
                await asyncio.sleep(0)
                self.assertEqual(await pool.close(endpoint=key.endpoint), 1)
                with self.assertRaises(sessions.Closed):
                    await lease.call_tool("after", {})
                with self.assertRaises(sessions.Closed):
                    await asyncio.wait_for(waiter, 1)
                self.assertFalse(pool.entries)
                self.assertEqual(len(closed), 1)
                self.assertEqual(client.call_tool.await_count, 1)
        finally:
            await pool.close()


class Executor(unittest.TestCase):
    def test_termination_stops_runtime_and_retries_leftovers_before_success(self):
        for lifecycle in ("TERMINATING", "RETIRED"):
            with self.subTest(lifecycle=lifecycle):
                runtime = {"id": "runtime", "intake_id": "intake", "status": "ACTIVE",
                           "source_commit": "commit", "image_id": "image"}
                current = {"status": "APPROVED", "intake_kind": "repository", "commit_sha": "commit",
                           "repository_url": "repository", "lifecycle": lifecycle, "server_status": "READY"}
                connection = Mock()
                connection.execute.side_effect = lambda query, *args: (
                    SimpleNamespace(fetchall=lambda: [runtime]) if query.startswith("SELECT * FROM mcp_runtimes")
                    else SimpleNamespace(fetchone=lambda: current) if "FROM mcp_intake_requests" in query
                    else SimpleNamespace(fetchone=lambda: {"id": "runtime"}))
                remove = Mock(side_effect=[1, 0])
                event = Mock()
                worker = definitions("../../runtime/worker.py", {"approval_problem", "reconcile"}, {
                    "names": lambda row: {"container": "owned-container"}, "inspect": Mock(return_value={"Image": "image"}),
                    "remove_runtime_resources": remove, "Jsonb": lambda value: value, "event": event, "log": Mock(),
                })
                worker.reconcile(connection, {}, {})
                event.assert_not_called()
                self.assertTrue(any("status='STOPPING'" in call.args[0] for call in connection.execute.call_args_list))
                runtime["status"] = "STOPPING"
                worker.reconcile(connection, {}, {})
                self.assertEqual(remove.call_count, 2)
                event.assert_called_once()
                self.assertEqual(event.call_args.args[2], "runtime-stopped")
                self.assertEqual(event.call_args.kwargs["scope"], {"left": 0})


if __name__ == "__main__":
    unittest.main()
