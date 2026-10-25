"""D-234: an approval's audience may be every active employee ("*"), still an envelope."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gateway"))
os.environ["OTEL_SDK_DISABLED"] = "true"
from app import core, pac, registry, review  # noqa: E402


class Audience(unittest.TestCase):
    def test_permits(self):
        self.assertTrue(registry.permits(None, "a"))
        self.assertTrue(registry.permits(["*"], "anyone"))
        self.assertTrue(registry.permits(["a"], "a"))
        self.assertFalse(registry.permits(["a"], "b"))
        self.assertFalse(registry.permits([], "a"))

    def test_everyone_envelope_keeps_reviewed_action_and_constraint(self):
        spec = {"allowed_principals": ["*"], "tools": {"read": "r"}, "intake_id": "i",
                "parameter_constraints": {"read": {"type": "object"}}, "valid_until": "2099-01-01T00:00:00+00:00"}
        with patch.object(registry, "server", lambda server: spec):
            self.assertTrue(pac.scope({"token": "someone"}, "s", "read", "r", [], {})["allowed"])
            self.assertFalse(pac.scope({"token": "someone"}, "s", "read", "w", [], {})["allowed"])
            self.assertFalse(pac.scope({"token": "someone"}, "s", "missing", "r", [], {})["allowed"])


class ChangeAudience(unittest.IsolatedAsyncioTestCase):
    """POST /api/registry/servers/{id}/audience: only the people change, and each change is a ledger event."""

    def setUp(self):
        self.doc = {"servers": {"docs": {"intake_id": "i-1", "allowed_principals": ["*"], "tools": {"read": "r"}}},
                    "history": [], "usage_relationships": [], "contracts": {}}
        self.saved = []
        self.events = AsyncMock()
        people = [{"token": "emp-kim", "user_id": "kim"}, {"token": "emp-lee", "user_id": "lee"}]

        async def fetch_all(sql, params=()):
            return [p for p in people if p["user_id"] in params[0]]

        for item in (patch.object(registry, "runtime", lambda: self.doc), patch.object(registry, "save_runtime", self.saved.append),
                     patch.object(registry, "sync", AsyncMock()), patch.object(review, "record_event", self.events),
                     patch.object(core.db, "fetch_one", AsyncMock(return_value={"submitted_by": "emp-park"})),
                     patch.object(core.db, "fetch_all", fetch_all)):
            item.start()
            self.addCleanup(item.stop)

    async def test_requester_selected_and_all(self):
        out = await core.update_server_audience("docs", "requester", [], "admin")
        self.assertEqual(out["principals"], ["emp-park"])
        out = await core.update_server_audience("docs", "selected", ["lee", "kim", " "], "admin")
        self.assertEqual(out["principals"], ["emp-kim", "emp-lee"])
        out = await core.update_server_audience("docs", "all", [], "admin")
        self.assertEqual(out["principals"], ["*"])
        self.assertEqual(self.doc["servers"]["docs"]["allowed_principals"], ["*"])
        self.assertEqual([e.args[0] for e in self.events.await_args_list], ["server-audience"] * 3)
        self.assertEqual(self.events.await_args_list[1].kwargs["scope"]["previous"], ["emp-park"])
        self.assertEqual(self.doc["servers"]["docs"]["tools"], {"read": "r"})  # 도구·분류는 그대로

    async def test_unknown_people_and_unregistered_servers_are_refused_without_change(self):
        for users in ([], ["ghost"]):
            with self.assertRaises(ValueError):
                await core.update_server_audience("docs", "selected", users, "admin")
        with self.assertRaises(LookupError):
            await core.update_server_audience("nope", "all", [], "admin")
        self.doc["servers"]["direct"] = {"allowed_principals": ["x"]}  # 도입 신청 없이 등록된 서버
        with self.assertRaises(LookupError):
            await core.update_server_audience("direct", "all", [], "admin")
        self.assertEqual(self.doc["servers"]["docs"]["allowed_principals"], ["*"])
        self.assertEqual(self.saved, [])
        self.events.assert_not_awaited()


if __name__ == "__main__":
    unittest.main(verbosity=1)
