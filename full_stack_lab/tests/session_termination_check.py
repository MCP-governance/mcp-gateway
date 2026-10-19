"""Inbound session lifecycle checks; database calls are AsyncMock-backed.

python -m unittest discover -s full_stack_lab/tests -p session_termination_check.py -v
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock


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
        digest, principal, jti = params
        row = self.sessions.get(digest)
        return {"ok": 1} if row and row["principal"] == principal and row["jti"] == jti and not row["terminated"] else None


fake_db_instance = SessionDB()
fake_db.execute = fake_db_instance.execute
fake_db.fetch_one = fake_db_instance.fetch_one
fake_db.transaction = fake_db_instance.transaction
spec = importlib.util.spec_from_file_location("session_test_gateway.mcp_sessions", APP / "mcp_sessions.py")
mcp_sessions = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mcp_sessions
spec.loader.exec_module(mcp_sessions)


class SessionTerminationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        fake_db_instance.sessions.clear()
        fake_db_instance.events.clear()
        fake_db_instance.execute.reset_mock()
        fake_db_instance.fetch_one.reset_mock()

    async def test_terminated_session_is_rejected_and_other_principal_remains_active(self):
        await mcp_sessions.register("session-alice", "alice-token", "jti-a", "device-a", "server-a")
        await mcp_sessions.register("session-bob", "bob-token", "jti-b", "device-b", "server-a")

        self.assertTrue(await mcp_sessions.active("session-alice", "alice-token", "jti-a"))
        self.assertEqual(await mcp_sessions.terminate(reason="principal-disabled", principal="alice-token"), 1)

        self.assertFalse(await mcp_sessions.active("session-alice", "alice-token", "jti-a"))
        self.assertTrue(await mcp_sessions.active("session-bob", "bob-token", "jti-b"))
        event_insert = next(call for call in fake_db_instance.execute.await_args_list
                            if call.args[0].startswith("INSERT INTO mcp_session_events"))
        self.assertEqual(event_insert.args[1][0], "principal-disabled")
        self.assertEqual(event_insert.args[1][-1], 1)

    async def test_server_cutover_closes_only_sessions_bound_to_that_server(self):
        await mcp_sessions.register("alice-a", "alice-token", "jti-a", None, "server-a")
        await mcp_sessions.register("alice-b", "alice-token", "jti-a", None, "server-b")

        self.assertEqual(await mcp_sessions.terminate(reason="termination", server_id="server-a"), 1)
        self.assertFalse(await mcp_sessions.active("alice-a", "alice-token", "jti-a"))
        self.assertTrue(await mcp_sessions.active("alice-b", "alice-token", "jti-a"))
        update = next(call for call in fake_db_instance.execute.await_args_list
                      if call.args[0].startswith("UPDATE mcp_client_sessions"))
        self.assertIn("server_id=%s", update.args[0])
        self.assertNotIn("principal=%s", update.args[0])


if __name__ == "__main__":
    unittest.main()
