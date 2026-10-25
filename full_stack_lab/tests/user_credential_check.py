"""D-235: credentials an employee connects for a service that must see that employee (GitHub).

DB, OPA and GitHub are stand-ins here; this is not evidence about a real GitHub account or the real device.

    python tests/user_credential_check.py        (gateway dependencies installed)
"""
from __future__ import annotations

import ast
import base64
import json
import os
import sys
import tempfile
import unittest
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "gateway"))
os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["USER_CREDENTIAL_KEY"] = base64.urlsafe_b64encode(bytes(range(32))).decode()
from app import agent_service, core, decommission, upstream, user_credentials as uc  # noqa: E402

ENDPOINT = "https://api.githubcopilot.com/mcp/"
SPEC = {"endpoint": ENDPOINT, "display_name": "GitHub", "deployment": "provider", "tool_reviews": {}}
TOKEN = "github_pat_11AAAAAAA0abcdefghijklmnopqrstuvwxyz"
OTHER = "github_pat_11BBBBBBB0zyxwvutsrqponmlkjihgfedcba"


class FakeStore:
    """Just enough of db for user_credentials: one dict keyed by (principal, endpoint)."""

    def __init__(self):
        self.rows = {}
        self.events = []

    async def fetch_one(self, query, params=()):
        if "SELECT 1 FROM user_upstream_credentials" in query:
            return {"x": 1} if tuple(params) in self.rows else None
        row = self.rows.get(tuple(params))
        return dict(row) if row else None

    async def fetch_all(self, query, params=()):
        if "c.endpoint" in query:
            return [{"principal": p, "account": r["account"], "display_name": None, "user_id": p}
                    for (p, e), r in sorted(self.rows.items()) if e == params[0]]
        return [{"endpoint": e, **r} for (p, e), r in self.rows.items() if p == params[0]]

    async def execute(self, query, params=()):
        if "SET last_used_at" in query:
            self.rows[tuple(params)]["last_used_at"] = datetime.now(UTC)
            return
        return await self._tx(query, params)

    async def _tx(self, query, params):
        if query.lstrip().startswith("INSERT"):
            principal, endpoint, kind, account, blob, expires = params
            self.rows[(principal, endpoint)] = {"kind": kind, "account": account, "ciphertext": blob, "expires_at": expires,
                                                "created_at": datetime.now(UTC), "last_used_at": None}
            r = self.rows[(principal, endpoint)]
            return SimpleNamespace(fetchone=AsyncMock(return_value={k: r[k] for k in ("kind", "account", "expires_at", "created_at")}))
        principal, _, endpoint = params
        gone = [(k, r) for k, r in list(self.rows.items()) if k[0] == principal and (endpoint is None or k[1] == endpoint)]
        for k, _ in gone:
            del self.rows[k]
        return SimpleNamespace(fetchall=AsyncMock(return_value=[{"endpoint": k[1], "kind": r["kind"], "account": r["account"]}
                                                                for k, r in gone]))

    def transaction(self):
        store = self

        class Tx:
            async def __aenter__(self):
                return SimpleNamespace(execute=AsyncMock(side_effect=store._tx))

            async def __aexit__(self, *exc):
                return False
        return Tx()

    async def record_event(self, kind, outcome, target_kind, target_id, actor, **kw):
        self.events.append({"kind": kind, "target_id": target_id, "actor": actor, **kw})
        return len(self.events)


class StoreCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.store = FakeStore()
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(uc.db, "fetch_one", self.store.fetch_one))
        stack.enter_context(patch.object(uc.db, "fetch_all", self.store.fetch_all))
        stack.enter_context(patch.object(uc.db, "execute", self.store.execute))
        stack.enter_context(patch.object(uc.db, "transaction", self.store.transaction))
        stack.enter_context(patch.object(uc.review, "record_event", self.store.record_event))
        upstream._connected.clear()
        self.addCleanup(upstream._connected.clear)


class Storage(StoreCase):
    async def test_ciphertext_round_trip_and_binding(self):
        await uc.save("alice", ENDPOINT, TOKEN, "token", "alice-gh", None)
        blob = bytes(self.store.rows[("alice", ENDPOINT)]["ciphertext"])
        self.assertNotIn(TOKEN.encode(), blob)
        self.assertEqual((await uc.lookup("alice", ENDPOINT))["secret"], TOKEN)
        # A row copied to another employee or endpoint does not decrypt.
        self.store.rows[("bob", ENDPOINT)] = dict(self.store.rows[("alice", ENDPOINT)])
        self.assertIsNone(await uc.lookup("bob", ENDPOINT))
        with self.assertRaises(Exception):
            uc.unseal("alice", ENDPOINT + "x", blob)

    async def test_no_key_means_nothing_is_stored_or_read(self):
        with patch.dict(os.environ, {"USER_CREDENTIAL_KEY": ""}):
            self.assertFalse(uc.available())
            with self.assertRaises(uc.Unavailable):
                await uc.save("alice", ENDPOINT, TOKEN, "token", "a", None)
            self.assertEqual(self.store.rows, {})
        await uc.save("alice", ENDPOINT, TOKEN, "token", "a", None)
        with patch.dict(os.environ, {"USER_CREDENTIAL_KEY": base64.urlsafe_b64encode(bytes(32)).decode()}):
            self.assertIsNone(await uc.lookup("alice", ENDPOINT))  # another key: reads as not connected

    async def test_ledger_has_who_and_which_never_the_value(self):
        await uc.save("alice", ENDPOINT, TOKEN, "token", "alice-gh", datetime.now(UTC) + timedelta(days=30))
        await uc.remove("alice", ENDPOINT, "직원이 연결 해제")
        kinds = [e["kind"] for e in self.store.events]
        self.assertEqual(kinds, ["upstream-credential-connect", "upstream-credential-disconnect"])
        self.assertNotIn(TOKEN, json.dumps(self.store.events, default=str))
        self.assertEqual(self.store.events[0]["scope"]["account"], "alice-gh")
        self.assertEqual(self.store.rows, {})

    async def test_expired_and_bad_format_are_not_usable(self):
        with self.assertRaises(ValueError):
            await uc.save("alice", ENDPOINT, "has space", "token", "a", None)
        await uc.save("alice", ENDPOINT, TOKEN, "token", "a", datetime.now(UTC) - timedelta(seconds=1))
        await upstream.refresh_connected(ENDPOINT, "alice")
        with self.assertRaises(upstream.CredentialUnavailable):
            upstream.credential_headers(ENDPOINT, "alice")


class Selection(StoreCase):
    def setUp(self):
        super().setUp()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "credentials.json"
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.dict(os.environ, {"MCP_UPSTREAM_CREDENTIALS_FILE": str(self.path)}))
        stack.enter_context(patch.object(upstream, "_private_file", lambda path: True))

    def write(self, *rows):
        self.path.write_text(json.dumps({"credentials": [
            {"endpoint": ENDPOINT, "expires_at": 0, "allowed_principals": ["user"], "access_token": "operator-user", **r}
            for r in rows]}))

    def bearer(self, principal):
        return upstream.credential_choice(ENDPOINT, principal)

    async def test_employee_connection_beats_the_operator_row(self):
        self.write({})
        self.assertEqual(self.bearer("user"), ({"Authorization": "Bearer operator-user"}, "operator"))
        await uc.save("user", ENDPOINT, TOKEN, "token", "u", None)
        await upstream.refresh_connected(ENDPOINT, "user")
        self.assertEqual(self.bearer("user"), ({"Authorization": "Bearer " + TOKEN}, "employee"))
        self.assertEqual(upstream.credential_source(ENDPOINT, "user"), "employee")

    async def test_connected_value_goes_only_to_its_own_endpoint_and_employee(self):
        self.write({"endpoint": "https://elsewhere.example/mcp"})
        await uc.save("alice", ENDPOINT, TOKEN, "token", "a", None)
        await upstream.refresh_connected(ENDPOINT, "alice")
        self.assertEqual(upstream.credential_headers(ENDPOINT + "other", "alice"), {})
        self.assertEqual(upstream.credential_headers(ENDPOINT, "bob"), {})
        self.assertEqual(upstream.credential_headers(ENDPOINT, None), {})

    async def test_several_rows_for_one_endpoint_choose_by_principal(self):
        self.write({"allowed_principals": ["user"], "access_token": "for-user"},
                   {"allowed_principals": ["carol"], "access_token": "for-carol"},
                   {"allowed_principals": ["*"], "access_token": "for-everyone"})
        self.assertEqual(self.bearer("user")[0]["Authorization"], "Bearer for-user")
        self.assertEqual(self.bearer("carol")[0]["Authorization"], "Bearer for-carol")
        self.assertEqual(self.bearer("zed")[0]["Authorization"], "Bearer for-everyone")  # "*" is the fallback
        self.assertEqual(self.bearer(None)[0]["Authorization"], "Bearer for-everyone")  # discovery prefers the shared row

    async def test_unbound_ambiguous_and_malformed_rows_fail_closed(self):
        self.write({"allowed_principals": ["user"]}, {"allowed_principals": ["carol"], "access_token": "c"})
        with self.assertRaises(upstream.CredentialUnavailable):
            self.bearer("aaaa")  # rows exist, none is bound to this employee
        self.write({"allowed_principals": ["user"]}, {"allowed_principals": ["user"], "access_token": "dup"})
        with self.assertRaises(upstream.CredentialUnavailable):
            self.bearer("user")
        self.write({"allowed_principals": ["user"]}, {"allowed_principals": "carol"})
        with self.assertRaises(upstream.CredentialUnavailable):
            self.bearer("user")
        self.write({"expires_at": 1})
        with self.assertRaises(upstream.CredentialUnavailable):
            self.bearer("user")

    async def test_missing_connection_for_the_github_server(self):
        self.write({"allowed_principals": ["user"]})
        self.assertTrue(await upstream.missing_connection(SPEC, "aaaa"))
        self.assertFalse(await upstream.missing_connection(SPEC, "user"))
        await uc.save("aaaa", ENDPOINT, TOKEN, "token", "aaaa-gh", None)
        self.assertFalse(await upstream.missing_connection(SPEC, "aaaa"))
        # Removing the row is seen on the next call, and close_pool forgets the copy at once.
        await uc.remove("aaaa", ENDPOINT, "x")
        await upstream.close_pool(ENDPOINT, "aaaa")
        self.assertTrue(await upstream.missing_connection(SPEC, "aaaa"))
        self.assertFalse(await upstream.missing_connection({"endpoint": "https://mcp.other.example/mcp"}, "aaaa"))
        self.assertFalse(await upstream.missing_connection({**SPEC, "credential_scope": "shared"}, "aaaa"))

    @unittest.skipIf(os.name == "nt", "POSIX permission bits")
    def test_a_readable_credential_file_is_still_refused(self):
        self.write({})
        self.path.chmod(0o644)
        with patch.object(upstream, "_private_file", lambda path: not path.stat().st_mode & 0o077):
            with self.assertRaises(upstream.CredentialUnavailable):
                self.bearer("user")


def transport(handler):
    return lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)


class GitHubCalls(StoreCase):
    async def test_token_check_reads_login_and_expiry(self):
        seen = []

        def handler(request):
            seen.append((str(request.url), request.headers["authorization"]))
            return httpx.Response(200, json={"login": "octo"}, headers={"github-authentication-token-expiration": "2026-12-01 09:30:00 UTC"})
        with patch.object(uc, "_http", transport(handler)):
            login, expires = await uc.verify(uc.SERVICES["api.githubcopilot.com"], TOKEN)
        self.assertEqual((login, expires), ("octo", datetime(2026, 12, 1, 9, 30, tzinfo=UTC)))
        self.assertEqual(seen, [("https://api.github.com/user", "Bearer " + TOKEN)])

    async def test_failures_say_what_to_do_and_never_echo_the_token(self):
        service = uc.SERVICES["api.githubcopilot.com"]
        for response in (httpx.Response(401, json={"message": "Bad credentials " + TOKEN}), httpx.Response(403),
                         httpx.Response(200, json={}), httpx.Response(502, text=TOKEN)):
            with patch.object(uc, "_http", transport(lambda request, r=response: r)):
                with self.assertRaises(uc.Rejected) as caught:
                    await uc.verify(service, TOKEN)
            self.assertNotIn(TOKEN, str(caught.exception))

        def down(request):
            raise httpx.ConnectError("no route")
        with patch.object(uc, "_http", transport(down)):
            with self.assertRaises(uc.Rejected) as caught:
                await uc.verify(service, TOKEN)
        self.assertIn("연결하지 못했습니다", str(caught.exception))
        with self.assertRaises(uc.Rejected):
            await uc.verify(service, "short")

    async def test_device_flow_state_transitions(self):
        service = uc.SERVICES["api.githubcopilot.com"]
        replies = []
        calls = []

        def handler(request):
            calls.append(str(request.url))
            if request.url.path == "/login/device/code":
                return httpx.Response(200, json={"device_code": "dc-secret", "user_code": "ABCD-1234", "verification_uri": "https://github.com/login/device",
                                                 "expires_in": 900, "interval": 5})
            if request.url.host == "api.github.com":
                return httpx.Response(200, json={"login": "octo"})
            return httpx.Response(200, json=replies.pop(0))
        with patch.object(uc, "_http", transport(handler)), patch.dict(os.environ, {"GITHUB_OAUTH_CLIENT_ID": "Iv1.test"}):
            flow = await uc.device_start("alice", ENDPOINT, service)
            self.assertEqual((flow["user_code"], flow["interval"]), ("ABCD-1234", 5))
            self.assertNotIn("dc-secret", json.dumps(flow))
            fid = flow["flow_id"]
            # Too early: no request reaches GitHub.
            before = len(calls)
            self.assertEqual((await uc.device_poll("alice", fid, service))["state"], "pending")
            self.assertEqual(len(calls), before)
            # Another employee cannot use this flow.
            uc._flows[fid]["next"] = 0
            self.assertEqual((await uc.device_poll("mallory", fid, service))["state"], "expired")
            replies[:] = [{"error": "authorization_pending"}, {"error": "slow_down", "interval": 10},
                          {"access_token": TOKEN, "token_type": "bearer"}]
            self.assertEqual((await uc.device_poll("alice", fid, service))["state"], "pending")
            uc._flows[fid]["next"] = 0
            slow = await uc.device_poll("alice", fid, service)
            self.assertEqual((slow["state"], slow["interval"]), ("pending", 10))
            uc._flows[fid]["next"] = 0
            done = await uc.device_poll("alice", fid, service)
            self.assertEqual(done, {"state": "connected", "account": "octo"})
            self.assertEqual((await uc.lookup("alice", ENDPOINT))["secret"], TOKEN)
            self.assertNotIn(fid, uc._flows)
            self.assertEqual((await uc.device_poll("alice", fid, service))["state"], "expired")
            for error, state in (("expired_token", "expired"), ("access_denied", "denied"), ("incorrect_client_credentials", "failed")):
                fid = (await uc.device_start("alice", ENDPOINT, service))["flow_id"]
                uc._flows[fid]["next"] = 0
                replies[:] = [{"error": error}]
                self.assertEqual((await uc.device_poll("alice", fid, service))["state"], state)
                self.assertNotIn(fid, uc._flows)

    async def test_device_flow_is_hidden_without_a_client_id(self):
        with patch.dict(os.environ, {"GITHUB_OAUTH_CLIENT_ID": ""}):
            with self.assertRaises(uc.Rejected):
                await uc.device_start("alice", ENDPOINT, uc.SERVICES["api.githubcopilot.com"])


class Routes(StoreCase):
    def setUp(self):
        super().setUp()
        self.user = {"principal": "alice", "roles": ["employee"], "user_id": "alice"}
        agent_service.app.dependency_overrides[agent_service.caller] = lambda: self.user
        self.addCleanup(agent_service.app.dependency_overrides.clear)
        stack = ExitStack()
        self.addCleanup(stack.close)
        servers = {"github": SPEC, "context7": {"endpoint": "https://mcp.context7.com/mcp"}}
        stack.enter_context(patch.object(agent_service.registry, "servers", lambda: servers))
        stack.enter_context(patch.object(agent_service.registry, "server", servers.get))
        stack.enter_context(patch.object(agent_service.registry, "allowed_principals", lambda sid: ["*"]))
        stack.enter_context(patch.object(agent_service.upstream, "release_pool", AsyncMock()))
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=agent_service.app), base_url="http://test")
        self.addAsyncCleanup(self.client.aclose)

    async def test_list_connect_and_disconnect(self):
        listing = (await self.client.get("/api/my-connections")).json()
        self.assertEqual([c["server_id"] for c in listing["connections"]], ["github"])
        self.assertEqual((listing["connections"][0]["connected"], listing["available"]), (False, True))
        with patch.object(uc, "verify", AsyncMock(return_value=("octo", None))):
            answer = await self.client.post("/api/my-connections/github/token", json={"token": TOKEN})
        self.assertEqual(answer.status_code, 200)
        self.assertNotIn(TOKEN, answer.text)
        listing = (await self.client.get("/api/my-connections")).json()
        self.assertNotIn(TOKEN, json.dumps(listing, default=str))
        self.assertEqual(listing["connections"][0]["account"], "octo")
        self.assertEqual((await self.client.delete("/api/my-connections/github")).status_code, 200)
        self.assertEqual(self.store.rows, {})

    async def test_a_rejected_token_is_not_stored(self):
        with patch.object(uc, "verify", AsyncMock(side_effect=uc.Rejected("GitHub이 이 토큰을 받아들이지 않았습니다."))):
            answer = await self.client.post("/api/my-connections/github/token", json={"token": TOKEN})
        self.assertEqual(answer.status_code, 422)
        self.assertEqual(self.store.rows, {})
        # A server that does not need the employee's own account cannot be given a credential.
        self.assertEqual((await self.client.post("/api/my-connections/context7/token", json={"token": TOKEN})).status_code, 404)

    async def test_every_connection_route_needs_a_signed_in_employee(self):
        tree = ast.parse((ROOT / "gateway/app/agent_service.py").read_text(encoding="utf-8"))
        found = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef):
                paths = [d.args[0].value for d in node.decorator_list if isinstance(d, ast.Call) and d.args
                         and isinstance(d.args[0], ast.Constant)]
                if any(str(p).startswith("/api/my-connections") for p in paths):
                    found += 1
                    names = {a.args[0].id for a in node.args.defaults if isinstance(a, ast.Call) and a.args and isinstance(a.args[0], ast.Name)}
                    self.assertIn("caller", names, node.name)
        self.assertEqual(found, 5)
        self.assertIn("connections", agent_service.PAGES_BY_ROLE["employee"])


class Lifecycle(StoreCase):
    async def test_account_delete_and_disable_remove_every_connection(self):
        for actor_status in ("delete", "disable"):
            await uc.save("alice", ENDPOINT, TOKEN, "token", "a", None)
            await uc.save("alice", "https://other.example/mcp", OTHER, "token", "b", None)
            await uc.save("bob", ENDPOINT, OTHER, "token", "b", None)
            user = {"principal": "root", "roles": ["admin"], "user_id": "root"}
            patches = [patch.object(agent_service, "current_identity", AsyncMock(return_value=user)),
                       patch.object(agent_service.upstream, "release_pool", AsyncMock()),
                       patch.object(agent_service.idp, "revoke_principal_tokens", AsyncMock()),
                       patch.object(agent_service.local_jobs, "quiesce", AsyncMock()),
                       patch.object(agent_service.local_jobs, "resume", AsyncMock()),
                       patch("app.mcp_sessions.terminate", AsyncMock())]
            row = {"token": "alice", "user_id": "alice", "email": "alice@x", "display_name": "A", "role": "employee",
                   "status": "deleted", "status_changed_by": "root", "status_changed_at": None}
            fetch = AsyncMock(side_effect=[{"token": "alice"}, row])
            with ExitStack() as stack:
                for p in patches:
                    stack.enter_context(p)
                stack.enter_context(patch.object(agent_service.db, "fetch_one", fetch))
                stack.enter_context(patch.object(agent_service.db, "fetch_all", AsyncMock(return_value=[])))
                stack.enter_context(patch.object(agent_service.db, "execute", AsyncMock()))
                if actor_status == "delete":
                    await agent_service.delete_account("alice", authorization="Bearer x")
                else:
                    await agent_service.set_account_status("alice", agent_service.AccountStatus(status="disabled"),
                                                           authorization="Bearer x")
            self.assertEqual([k for k in self.store.rows if k[0] == "alice"], [], actor_status)
            self.assertIn(("bob", ENDPOINT), self.store.rows)
            reasons = [e["reason"] for e in self.store.events if e["kind"] == "upstream-credential-disconnect"]
            self.assertIn("계정 삭제" if actor_status == "delete" else "계정 중지", reasons)
            self.store.rows.clear()

    async def test_relationship_termination_deletes_the_organisations_copies_and_proves_it(self):
        await uc.save("alice", ENDPOINT, TOKEN, "token", "alice-gh", None)
        await uc.save("bob", ENDPOINT, OTHER, "token", "bob-gh", None)
        targets = []

        async def add_target(case_id, kind, label, holder, discovered, actor, **kw):
            targets.append({"id": f"t{len(targets)}", "kind": kind, "label": label, "holder": holder, "case_id": case_id, **kw})
            return targets[-1]
        server = {"id": "github", "endpoint": ENDPOINT, "display_name": "GitHub", "deployment": "provider", "supplier": "GitHub", "exit_terms": {}}

        async def fetch_all(query, params=()):
            if "FROM revocation_targets" in query:
                return [dict(t, status="OUTSTANDING", subject_ref=t["subject_ref"]) for t in targets if t.get("verification") == "credential-store"]
            if "c.endpoint" in query:
                return await self.store.fetch_all(query, params)
            return []
        revoked, evidence = [], []
        with ExitStack() as stack:
            stack.enter_context(patch.object(decommission, "_case", AsyncMock(return_value={"id": "c1", "server_id": "github", "status": "OPEN", "cutover_at": None})))
            stack.enter_context(patch.object(decommission, "_server", AsyncMock(return_value=server)))
            stack.enter_context(patch.object(decommission.db, "fetch_all", fetch_all))
            stack.enter_context(patch.object(decommission.db, "fetch_one", self.store.fetch_one))
            stack.enter_context(patch.object(decommission, "add_target", add_target))
            stack.enter_context(patch.object(decommission, "add_evidence", AsyncMock(side_effect=lambda c, kind, subject, source, detail, actor, **kw: (
                evidence.append((kind, subject, detail, kw["target_id"])) or {"observed_at": datetime.now(UTC)}))))
            stack.enter_context(patch.object(decommission, "revoke_target", AsyncMock(side_effect=lambda tid, actor, status, note=None, at=None: revoked.append((tid, status)))))
            created = await decommission.seed_targets("c1", "root")
            self.assertEqual(len([t for t in created if t.get("verification") == "credential-store"]), 2)
            self.assertTrue(all(t["holder"] == "org" and t["kind"] == "server-held-credential" for t in created if t.get("verification") == "credential-store"))
            await decommission.verify_connected("c1", "root")
        self.assertEqual(self.store.rows, {})
        self.assertEqual([r[1] for r in revoked], ["REVOKED", "REVOKED"])
        self.assertTrue(all(e[0] == "credential-check" and e[2]["present"] is False for e in evidence))
        self.assertNotIn(TOKEN, json.dumps(evidence, default=str))
        self.assertEqual(len([e for e in self.store.events if e["kind"] == "upstream-credential-disconnect"]), 2)

    async def test_a_target_stays_outstanding_while_the_row_is_still_there(self):
        await uc.save("alice", ENDPOINT, TOKEN, "token", "alice-gh", None)
        target = {"id": "t0", "kind": "server-held-credential", "label": "x", "verification": "credential-store", "subject_ref": "alice", "status": "OUTSTANDING"}
        revoked = []
        with ExitStack() as stack:
            stack.enter_context(patch.object(decommission, "_case", AsyncMock(return_value={"id": "c1", "server_id": "github"})))
            stack.enter_context(patch.object(decommission, "_server", AsyncMock(return_value={"id": "github", "endpoint": ENDPOINT})))
            stack.enter_context(patch.object(decommission.db, "fetch_all", AsyncMock(return_value=[target])))
            stack.enter_context(patch.object(decommission.db, "fetch_one", AsyncMock(return_value={"x": 1})))
            stack.enter_context(patch.object(decommission.user_credentials, "remove", AsyncMock(return_value=[])))
            stack.enter_context(patch.object(decommission, "add_evidence", AsyncMock(return_value={"observed_at": datetime.now(UTC)})))
            stack.enter_context(patch.object(decommission, "revoke_target", AsyncMock(side_effect=lambda *a, **k: revoked.append(a))))
            await decommission.verify_connected("c1", "root")
        self.assertEqual(revoked, [])


class Blocking(unittest.IsolatedAsyncioTestCase):
    async def run_call(self, *, lifecycle_row, missing, spec=SPEC):
        cls = SimpleNamespace(action="r", base_action="r", data_class="public", destinations=[], resources=[], dlp=[], notes=[],
                              restrictable=[], primary=SimpleNamespace(id="repo", kind="repo", owner_department=None),
                              summary=lambda: "read")

        async def fetch(query, params=()):
            if "principals" in query:
                return {"role": "employee", "status": "active", "server_suspended": False}
            if "lifecycle" in query:
                return lifecycle_row
            return None

        async def record(event, laps):
            return {**event, "decision_id": 9}
        upstream_call = AsyncMock()
        changes = [(core.db, {"fetch_one": AsyncMock(side_effect=fetch)}),
                   (core.registry, {"server": Mock(return_value=spec), "allowed_principals": Mock(return_value=["*"])}),
                   (core.classify, {"classify": Mock(return_value=cls)}),
                   (core.endpoint_plane, {"managed_failure": AsyncMock(return_value=None)}),
                   (core.tool_sunset, {"check": AsyncMock(return_value=None), "call_verdict": Mock(return_value=None)}),
                   (core.user_suspend, {"expire": AsyncMock()}),
                   (core.upstream, {"missing_connection": AsyncMock(return_value=missing)}),
                   (core, {"policy_ledger": AsyncMock(), "_reserve_call": AsyncMock(side_effect=RuntimeError("stop here")),
                           "_decision_payload": AsyncMock(side_effect=record), "_call_upstream": upstream_call})]
        with ExitStack() as stack:
            for target, attributes in changes:
                for name, value in attributes.items():
                    stack.enter_context(patch.object(target, name, value))
            result = await core.execute_call({"server_id": "github", "tool": "get_me", "arguments": {}, "user_token": "aaaa"})
        return result, upstream_call

    async def test_no_connection_blocks_before_the_provider_and_says_where_to_connect(self):
        result, upstream_call = await self.run_call(lifecycle_row={"x": 1}, missing=True)
        self.assertEqual((result["decision"], result["policy_id"]), ("Block", "MCP-CREDENTIAL-001"))
        self.assertIn("MINT 콘솔 『내 연결』에서 GitHub 계정을 연결하세요", result["reason"])
        self.assertFalse(result["upstream_attempted"] or result["upstream_executed"])
        upstream_call.assert_not_awaited()

    async def test_a_connected_employee_goes_on_and_a_terminating_server_keeps_its_own_reason(self):
        for lifecycle_row, missing in (({"x": 1}, False), (None, True)):
            result, _ = await self.run_call(lifecycle_row=lifecycle_row, missing=missing)
            self.assertNotEqual(result["policy_id"], "MCP-CREDENTIAL-001")
        result, _ = await self.run_call(lifecycle_row={"x": 1}, missing=True, spec={"endpoint": "https://mcp.other.example/mcp", "tool_reviews": {}})
        self.assertNotEqual(result["policy_id"], "MCP-CREDENTIAL-001")

    def test_the_policy_is_in_the_ledger_with_a_unique_priority(self):
        ledger = json.loads((ROOT / "opa/policy_ledger.json").read_text(encoding="utf-8"))["policy_ledger"]
        self.assertEqual(ledger["MCP-CREDENTIAL-001"]["enforced_by"], "gateway")
        self.assertEqual(len(ledger), len({p["priority"] for p in ledger.values()}))


if __name__ == "__main__":
    unittest.main(verbosity=1)
