"""Inbound session lifecycle checks; database calls are AsyncMock-backed.

python -m unittest discover -s full_stack_lab/tests -p session_termination_check.py -v
"""
from __future__ import annotations

import ast
import asyncio
from datetime import UTC, datetime
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch


APP = Path(__file__).resolve().parents[1] / "gateway" / "app"
package = ModuleType("session_test_gateway")
package.__path__ = [str(APP)]
sys.modules[package.__name__] = package
fake_db = ModuleType("session_test_gateway.db")
sys.modules[fake_db.__name__] = fake_db


class Transaction:
    def __init__(self, owner):
        self.owner = owner

    async def __aenter__(self):
        return self.owner

    async def __aexit__(self, *_):
        return False


class SessionDB:
    def __init__(self):
        self.sessions = {}
        self.events = []
        self.execute = AsyncMock(side_effect=self._execute)
        self.fetch_one = AsyncMock(side_effect=self._fetch_one)

    def transaction(self):
        return Transaction(self)

    async def _execute(self, query, params):
        if query.startswith("INSERT INTO mcp_client_sessions"):
            digest, principal, jti, device, server = params
            self.sessions.setdefault(digest, {"principal": principal, "jti": jti, "device": device,
                                               "server": server, "terminated": False})
            return SimpleNamespace(rowcount=1)
        if query.startswith("UPDATE mcp_client_sessions"):
            reason, *filters = params
            where = query.split(" WHERE ", 1)[1]
            columns = [piece.split("=")[0] for piece in where.split(" AND ") if "=" in piece]
            match = dict(zip(columns, filters))
            count = 0
            for digest, row in self.sessions.items():
                actual = {"principal": row["principal"], "device_id": row["device"],
                          "server_id": row["server"], "session_hash": digest}
                if not row["terminated"] and all(actual[key] == value for key, value in match.items()):
                    row["terminated"] = True
                    row["reason"] = reason
                    count += 1
            return SimpleNamespace(rowcount=count)
        if query.startswith("INSERT INTO mcp_session_events"):
            self.events.append(params)
            return SimpleNamespace(rowcount=1)
        raise AssertionError(query)

    async def _fetch_one(self, query, params):
        if query.startswith("SELECT terminated_at"):
            row = self.sessions.get(params[0])
            return {"terminated_at": "now" if row["terminated"] else None,
                    "termination_reason": row.get("reason")} if row else None
        digest, principal, device, server = params
        row = self.sessions.get(digest)
        return {"ok": 1} if row and row["principal"] == principal and row["device"] == device \
            and row["server"] == server and not row["terminated"] else None


fake_db_instance = SessionDB()
fake_db.execute = fake_db_instance.execute
fake_db.fetch_one = fake_db_instance.fetch_one
fake_db.transaction = fake_db_instance.transaction
spec = importlib.util.spec_from_file_location("session_test_gateway.mcp_sessions", APP / "mcp_sessions.py")
mcp_sessions = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mcp_sessions
spec.loader.exec_module(mcp_sessions)
package.mcp_sessions = mcp_sessions


def functions(file, names, namespace):
    """Run only the named product definitions against the stubs in `namespace`."""
    tree = ast.parse((APP / file).read_text(encoding="utf-8"))
    selected = [node for node in tree.body if isinstance(node, (ast.AsyncFunctionDef, ast.ClassDef))
                and node.name in names]
    assert len(selected) == len(names)
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(APP / file), "exec"), namespace)
    return namespace


class Reply:
    """JSONResponse stand-in: the status and the body object, as sent."""

    def __init__(self, body, status_code=200, headers=None):
        self.body, self.status_code = body, status_code

    async def __call__(self, scope, receive, send):
        await send({"type": "http.response.start", "status": self.status_code, "headers": []})
        await send({"type": "http.response.body", "body": self.body})


USER = {"principal": "alice-token", "roles": ["employee"], "claims": {"jti": "jti-a", "device_id": "device-a"}}


class SessionTerminationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        fake_db_instance.sessions.clear()
        fake_db_instance.events.clear()
        fake_db_instance.execute.reset_mock()
        fake_db_instance.fetch_one.reset_mock()

    async def test_terminated_session_is_rejected_and_other_principal_remains_active(self):
        await mcp_sessions.register("session-alice", "alice-token", "jti-a", "device-a", "server-a")
        await mcp_sessions.register("session-bob", "bob-token", "jti-b", "device-b", "server-a")

        self.assertTrue(await mcp_sessions.active("session-alice", "alice-token", "device-a", "server-a"))
        self.assertEqual(await mcp_sessions.terminate(reason="principal-disabled", principal="alice-token"), 1)

        self.assertFalse(await mcp_sessions.active("session-alice", "alice-token", "device-a", "server-a"))
        self.assertTrue(await mcp_sessions.active("session-bob", "bob-token", "device-b", "server-a"))
        event_insert = next(call for call in fake_db_instance.execute.await_args_list
                            if call.args[0].startswith("INSERT INTO mcp_session_events"))
        self.assertEqual(event_insert.args[1][0], "principal-disabled")
        self.assertEqual(event_insert.args[1][-1], 1)

    async def test_server_cutover_closes_only_sessions_bound_to_that_server(self):
        await mcp_sessions.register("alice-a", "alice-token", "jti-a", None, "server-a")
        await mcp_sessions.register("alice-b", "alice-token", "jti-a", None, "server-b")

        self.assertEqual(await mcp_sessions.terminate(reason="termination", server_id="server-a"), 1)
        self.assertFalse(await mcp_sessions.active("alice-a", "alice-token", None, "server-a"))
        self.assertTrue(await mcp_sessions.active("alice-b", "alice-token", None, "server-b"))
        update = next(call for call in fake_db_instance.execute.await_args_list
                      if call.args[0].startswith("UPDATE mcp_client_sessions"))
        self.assertIn("server_id=%s", update.args[0])
        self.assertNotIn("principal=%s", update.args[0])

    async def test_token_rotation_keeps_session_for_same_principal_device_and_server(self):
        await mcp_sessions.register("rotating-session", "alice-token", "old-jti", "device-a", "server-a")
        await mcp_sessions.register("rotating-session", "alice-token", "new-jti", "device-a", "server-a")

        self.assertTrue(await mcp_sessions.active("rotating-session", "alice-token", "device-a", "server-a"))

    async def test_session_id_is_rejected_for_another_principal_or_device(self):
        await mcp_sessions.register("bound-session", "alice-token", "jti-a", "device-a", "server-a")

        self.assertFalse(await mcp_sessions.active("bound-session", "bob-token", "device-a", "server-a"))
        self.assertFalse(await mcp_sessions.active("bound-session", "alice-token", "device-b", "server-a"))
        self.assertFalse(await mcp_sessions.active("bound-session", "alice-token", "device-a", "server-b"))

    async def test_refusal_names_the_policy_by_how_the_session_ended(self):
        await mcp_sessions.register("cut", "alice-token", "jti-a", None, "server-a")
        await mcp_sessions.register("stopped", "bob-token", "jti-b", None, "server-b")
        await mcp_sessions.register("bound", "carol-token", "jti-c", None, "server-b")
        await mcp_sessions.terminate(reason="termination", server_id="server-a")
        await mcp_sessions.terminate(reason="principal-disabled", principal="bob-token")

        self.assertEqual((await mcp_sessions.refusal("cut"))["policy_id"], "MCP-DECOMM-001")
        self.assertEqual((await mcp_sessions.refusal("stopped"))["policy_id"], "PAC-14")
        self.assertEqual((await mcp_sessions.refusal("bound"))["policy_id"], "PAC-04")
        self.assertIsNone(await mcp_sessions.refusal("never-bound"))


class GatewayWiringTests(unittest.IsolatedAsyncioTestCase):
    """RequireBearer → ServerPath as main.py mounts them, product code run against stubs."""

    def gateway(self, servers, active=True, refusal=None):
        self.inner = AsyncMock()
        self.denial = AsyncMock(return_value=7)
        self.active = AsyncMock(return_value=active)
        ns = functions("main.py", {"RequireBearer", "ServerPath"}, {
            "authenticated_user": AsyncMock(return_value=USER),
            "HTTPException": type("HTTPException", (Exception,), {}),
            "JSONResponse": Reply, "asyncio": asyncio, "json": json,
            "_error_detail": AsyncMock(side_effect=lambda detail: detail),
            "registry": SimpleNamespace(servers=lambda: servers),
            "core": SimpleNamespace(record_connection_denial=self.denial),
            "upstream": SimpleNamespace(active_downstream=self.active,
                                        downstream_refusal=AsyncMock(return_value=refusal),
                                        register_downstream=AsyncMock(), close_downstream=AsyncMock()),
        })
        return ns["RequireBearer"](ns["ServerPath"](self.inner))

    async def call(self, app, *session_ids, path="/mcp/github/"):
        sent = []
        headers = [(b"authorization", b"Bearer t")] + [(b"mcp-session-id", value) for value in session_ids]
        body = {"type": "http.request", "body": b'{"method": "tools/call"}', "more_body": False}
        scope = {"type": "http", "method": "POST", "path": path, "root_path": "/mcp", "headers": headers}

        async def send(message):
            sent.append(message)

        await app(scope, AsyncMock(return_value=body), send)
        return (sent[0]["status"], sent[1]["body"]) if sent else (None, None)

    async def test_a_second_session_header_is_refused_before_any_session_is_used(self):
        app = self.gateway({"github": {}})
        status, body = await self.call(app, b"terminated", b"own-live")

        self.assertEqual(status, 400)
        self.active.assert_not_awaited()
        self.inner.assert_not_awaited()

    async def test_removed_server_keeps_its_registry_refusal_on_record(self):
        app = self.gateway({}, active=False)
        status, body = await self.call(app, b"old-session")

        self.assertEqual((status, body["decision"], body["policy_id"], body["decision_id"]),
                         (404, "Block", "MCP-REGISTRY-001", 7))
        self.assertEqual(self.denial.await_args.args[1:3], ("github", "tools/call"))
        self.assertNotIn("policy_id", self.denial.await_args.kwargs)
        self.active.assert_not_awaited()
        self.inner.assert_not_awaited()

    async def test_ended_session_is_404_with_its_policy_on_record(self):
        ended = {"policy_id": "MCP-DECOMM-001", "reason": "종료된 MCP 세션의 재사용을 차단했습니다.",
                 "summary": "종료된 MCP 세션 차단"}
        app = self.gateway({"github": {}}, active=False, refusal=ended)
        status, body = await self.call(app, b"ended")

        self.assertEqual((status, body["decision"], body["policy_id"], body["decision_id"]),
                         (404, "Block", "MCP-DECOMM-001", 7))
        self.active.assert_awaited_once_with("ended", "alice-token", "device-a", "github")
        self.assertEqual(self.denial.await_args.args[1], "github")
        self.assertEqual(self.denial.await_args.kwargs["policy_id"], "MCP-DECOMM-001")
        self.inner.assert_not_awaited()

    async def test_unbound_session_is_404_without_a_record_and_a_live_one_passes(self):
        status, body = await self.call(self.gateway({"github": {}}, active=False), b"from-before")
        self.assertEqual(status, 404)
        self.assertNotIn("policy_id", body)
        self.denial.assert_not_awaited()

        app = self.gateway({"github": {}})
        await self.call(app, b"live")
        self.inner.assert_awaited_once()
        self.assertEqual(self.inner.await_args.args[0]["mcp_server"], "github")

    async def test_aggregate_endpoint_checks_the_session_without_a_server(self):
        app = self.gateway({"github": {}})
        await self.call(app, b"live", path="/mcp/")
        self.active.assert_awaited_once_with("live", "alice-token", "device-a", None)

    async def test_failed_session_cutover_does_not_cost_the_deregistration_record(self):
        doc = {"servers": {"github": {"endpoint": "https://github.example/mcp"}}, "contracts": {},
               "usage_relationships": [], "history": []}
        review = SimpleNamespace(record_event=AsyncMock())
        release = AsyncMock()
        ns = functions("core.py", {"deregister_server"}, {
            "__name__": "session_test_gateway.core", "__package__": "session_test_gateway",
            "REGISTER_LOCK": asyncio.Lock(), "datetime": datetime, "UTC": UTC, "review": review,
            "registry": SimpleNamespace(runtime=lambda: doc, save_runtime=lambda _: None, sync=AsyncMock()),
            "upstream": SimpleNamespace(release_pool=release),
            # A remote server has nothing running on a device; the local stop is a no-op here.
            "local_jobs": SimpleNamespace(quiesce=AsyncMock()),
        })
        with patch.object(mcp_sessions, "terminate", AsyncMock(side_effect=RuntimeError("database unavailable"))):
            with self.assertRaises(RuntimeError):
                await ns["deregister_server"]("github", "admin")

        release.assert_awaited_once()
        review.record_event.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
