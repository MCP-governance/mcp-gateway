"""Field account deletion and Git organization membership regressions."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gateway"))
from app import agent_service as service
from app import mcp_sessions


class FieldAccountGitTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(service.app)

    def test_deletion_blocks_root_and_tombstones_other_accounts(self):
        identity = {"roles": ["admin"], "principal": "root", "user_id": "root"}
        db = AsyncMock(return_value={"email": "alice", "token": "emp-alice"})
        # Recording doubles for the DB-bound steps after the tombstone. Each one keeps the
        # call and its arguments so the assertions below can check that the step ran.
        execute = AsyncMock(return_value=1)
        fetch_all = AsyncMock(return_value=[])
        revoke = AsyncMock()
        release = AsyncMock(return_value=0)
        terminate = AsyncMock(return_value=0)
        with patch.object(service, "current_identity", AsyncMock(return_value=identity)), \
             patch.object(service.db, "fetch_one", db), \
             patch.object(service.db, "execute", execute), \
             patch.object(service.db, "fetch_all", fetch_all), \
             patch.object(service.idp, "revoke_principal_tokens", revoke), \
             patch.object(service.upstream, "release_pool", release), \
             patch.object(mcp_sessions, "terminate", terminate), \
             patch.dict(service.os.environ, {"MCP_FIELD_MODE": "0"}):
            self.assertEqual(self.client.delete("/api/accounts/root").status_code, 409)
            self.assertEqual(self.client.delete("/api/accounts/alice").status_code, 200)
        self.assertEqual(db.await_count, 1)
        self.assertIn("status='deleted'", db.await_args.args[0])
        # Added: the post-tombstone steps ran, with the principal key the tombstone returned.
        self.assertEqual(db.await_args.args[1], ("root", "alice"))
        revoke.assert_awaited_once_with("alice")
        release.assert_awaited_once_with(None, "emp-alice", "principal")
        execute.assert_awaited_once()
        self.assertIn("console_sessions", execute.await_args.args[0])
        self.assertEqual(execute.await_args.args[1], ("alice",))
        fetch_all.assert_awaited_once()
        self.assertIn("oidc_bindings", fetch_all.await_args.args[0])
        self.assertEqual(fetch_all.await_args.args[1], ("emp-alice",))
        terminate.assert_awaited_once_with(reason="principal-deleted", principal="emp-alice")

    def test_existing_gitea_user_still_joins_organization(self):
        service._gitea_ready.clear()
        seen = []

        def reply(request):
            seen.append((request.method, request.url.path))
            path = request.url.path
            if path == "/api/v1/users/alice":
                return httpx.Response(200, json={"is_admin": False})
            if path == "/api/v1/orgs/mcp":
                return httpx.Response(200, json={"username": "mcp"})
            if path == "/api/v1/orgs/mcp/teams":
                return httpx.Response(200, json=[{"id": 2, "name": "Members"}])
            if path == "/api/v1/teams/2/members/alice" and request.method == "PUT":
                return httpx.Response(204)
            return httpx.Response(404)

        client = httpx.AsyncClient(base_url="http://gitea", transport=httpx.MockTransport(reply))
        with patch.object(service, "gitea_admin_client", return_value=client):
            self.assertEqual(asyncio.run(service.ensure_gitea_user(
                {"email": "alice", "name": "Alice", "roles": ["employee"]})), "alice")
        self.assertIn(("PUT", "/api/v1/teams/2/members/alice"), seen)

    def test_new_team_grants_code_read_access(self):
        def reply(request):
            if request.url.path == "/api/v1/orgs/mcp":
                return httpx.Response(200, json={"username": "mcp"})
            if request.method == "GET":
                return httpx.Response(200, json=[])
            body = json.loads(request.content)
            self.assertEqual(body["units"], ["repo.code"])
            self.assertTrue(body["includes_all_repositories"])
            return httpx.Response(201, json={"id": 2})

        async def check():
            async with httpx.AsyncClient(base_url="http://gitea", transport=httpx.MockTransport(reply)) as client:
                return await service.ensure_gitea_team(client)

        self.assertEqual(asyncio.run(check()), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
