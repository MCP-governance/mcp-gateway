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


class FieldAccountGitTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(service.app)

    def test_deletion_blocks_root_and_tombstones_other_accounts(self):
        identity = {"roles": ["admin"], "principal": "root", "user_id": "root"}
        db = AsyncMock(return_value={"email": "alice"})
        with patch.object(service, "current_identity", AsyncMock(return_value=identity)), \
             patch.object(service.db, "fetch_one", db), \
             patch.dict(service.os.environ, {"MCP_FIELD_MODE": "0"}):
            self.assertEqual(self.client.delete("/api/accounts/root").status_code, 409)
            self.assertEqual(self.client.delete("/api/accounts/alice").status_code, 200)
        self.assertEqual(db.await_count, 1)
        self.assertIn("status='deleted'", db.await_args.args[0])

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
