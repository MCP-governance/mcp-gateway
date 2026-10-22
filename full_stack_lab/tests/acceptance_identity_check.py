"""Acceptance actors use separate Console sessions and real OAuth MCP grants.

These isolated transport checks do not claim real IdP, DB, or MCP execution.
"""
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gateway"))
from app import acceptance as a  # noqa: E402


class AcceptanceIdentityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.console = {who: f"console-{who}" for who in a.USERS}
        self.mcp = {who: f"mcp-{who}" for who in a.USERS}
        for name, value in (("USERS", dict(a.USERS)), ("PRINCIPAL", dict(a.PRINCIPAL)),
                            ("TOKENS", self.console.copy()), ("MCP_TOKENS", self.mcp.copy())):
            p = patch.object(a, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.client_type = httpx.AsyncClient

    def transport(self, handler):
        def client(**kwargs):
            return self.client_type(transport=httpx.MockTransport(handler), **kwargs)
        return patch.object(a.httpx, "AsyncClient", side_effect=client)

    async def test_sign_in_obtains_two_distinct_grants_for_each_actor(self):
        seen = []

        def handle(request):
            from urllib.parse import parse_qs
            seen.append(request)
            if request.url.path == "/api/session":
                email = json.loads(request.content)["email"]
                return httpx.Response(200, json={"access_token": "console:" + email})
            self.assertEqual(request.url, "http://test-idp/oauth/token")
            data = parse_qs(request.content.decode())
            self.assertEqual(data["grant_type"], ["password"])
            self.assertEqual(data["client_id"], ["acceptance-ws"])
            self.assertEqual(data["password"], ["fixture-password"])
            return httpx.Response(200, json={"access_token": "mcp:" + data["username"][0]})

        with self.transport(handle), patch.object(a.db, "execute", new=AsyncMock()) as execute, \
                patch.dict(os.environ, IDP_INTERNAL_URL="http://test-idp/", MOCK_SSO_PASSWORD="fixture-password"):
            await a.sign_in()
        self.assertEqual(execute.await_count, 4)
        self.assertEqual(len(seen), 8)
        for who, email in a.USERS.items():
            self.assertEqual(a.TOKENS[who], "console:" + email)
            self.assertEqual(a.MCP_TOKENS[who], "mcp:" + email)

    async def test_oauth_failure_aborts_without_console_fallback(self):
        a.TOKENS.clear()
        a.MCP_TOKENS.clear()

        def handle(request):
            if request.url.path == "/api/session":
                return httpx.Response(200, json={"access_token": "console-only"})
            return httpx.Response(403, json={"error": "access_denied"})

        with self.transport(handle), patch.object(a.db, "execute", new=AsyncMock()):
            with self.assertRaises(httpx.HTTPStatusError):
                await a.sign_in()
        self.assertFalse(a.MCP_TOKENS)
        with self.assertRaises(KeyError):
            a._http("employee")

    async def test_sdk_client_uses_mcp_grant(self):
        async with a._http("employee") as client:
            self.assertEqual(client.headers["Authorization"], "Bearer mcp-employee")
            self.assertEqual(client.headers["X-Workstation-Id"], "acceptance")
        self.assertEqual(a.TOKENS["employee"], "console-employee")

    async def test_direct_unknown_endpoints_use_mcp_and_anonymous_stays_anonymous(self):
        seen = []

        def handle(request):
            seen.append(request)
            token = request.headers.get("Authorization")
            if token is None:
                return httpx.Response(401)
            self.assertEqual(token, "Bearer mcp-employee")
            return httpx.Response(404, json={"policy_id": "MCP-REGISTRY-001", "decision": "Block", "decision_id": "refusal"})

        async def fetch_one(query, params=None):
            if "count(*)" in query:
                return {"n": 2}
            if "SELECT client" in query:
                return {"client": {"endpoint": "git"}}
            return {"tool_name": "initialize", "action": "connect", "client": {"event_kind": "mcp-connection"},
                    "upstream_attempted": False, "upstream_executed": False}

        with self.transport(handle), patch.object(a, "operating", new=AsyncMock()), \
                patch.object(a, "list_tools", new=AsyncMock(return_value=[SimpleNamespace(name="git_log")])), \
                patch.object(a, "call", new=AsyncMock(return_value={"decision": "Allow", "policy_id": "P-AUTHZ-ALLOW-001", "is_error": False})), \
                patch.object(a.db, "fetch_all", new=AsyncMock(return_value=[{"name": "git_log"}])), \
                patch.object(a.db, "fetch_one", new=fetch_one), \
                patch.object(a, "_reserve_call", new=AsyncMock(return_value={"recent_calls": 1, "recent_important": 0, "recent_blocks": 0})), \
                patch.object(a, "_release_call", new=AsyncMock()):
            await a.per_server_endpoint()
        self.assertEqual(len(seen), 7)
        self.assertEqual([r.method for r in seen], ["POST", "POST", "POST", "POST", "GET", "POST", "POST"])
        self.assertNotIn("Authorization", seen[-1].headers)

    async def test_deregistered_endpoint_uses_mcp_grant_after_console_delete(self):
        seen = []
        requests = 0

        def handle(request):
            nonlocal requests
            seen.append(request)
            path = request.url.path
            if path == "/mcp/acceptance-fetch/":
                self.assertEqual(request.headers["Authorization"], "Bearer mcp-employee")
                return httpx.Response(404)
            expected = "Bearer console-admin"
            if path == "/api/mcp-requests":
                self.assertEqual(json.loads(request.content)["requested_tools"], ["fetch"])
                requests += 1
                if requests == 1:
                    expected = "Bearer console-employee"
            self.assertEqual(request.headers["Authorization"], expected)
            if path == "/api/registry/discover":
                return httpx.Response(200, json={"tools": [{"name": "fetch"}], "catalog_hash": "fixture"})
            if path == "/api/registry/servers":
                return httpx.Response(409, text="도입 신청")
            if path == "/api/mcp-requests":
                return httpx.Response(200, json={"request": {"id": "other" if requests == 1 else "own"}})
            if "/own/" in path:
                return httpx.Response(403)
            if path.endswith("/approve"):
                count = sum(r.url.path == path for r in seen)
                return httpx.Response(409 if count == 1 else 200)
            if path.endswith("/register"):
                count = sum(r.url.path == path for r in seen)
                return httpx.Response(409 if count == 1 else 200, json={"status": "READY"})
            return httpx.Response(200)

        outputs = [
            {"decision": "Block", "policy_id": "MCP-REGISTRY-003", "upstream_attempted": False},
            {"decision": "Allow", "is_error": False, "text": "fixture"},
            {"decision": "Block", "policy_id": "PAC-01", "upstream_attempted": False},
            {"decision": "Block", "policy_id": "P-APPROVAL-EXPIRY-001"},
        ]
        with self.transport(handle), patch.object(a, "operating", new=AsyncMock()), \
                patch.object(a, "list_tools", new=AsyncMock(return_value=[SimpleNamespace(name="fetch")])), \
                patch.object(a, "call", new=AsyncMock(side_effect=outputs)), \
                patch.object(a.db, "execute", new=AsyncMock()):
            await a.console_registration_expires()
        self.assertEqual(seen[-2].method, "DELETE")
        self.assertEqual(seen[-1].url.path, "/mcp/acceptance-fetch/")

    async def test_console_management_keeps_console_session(self):
        def handle(request):
            self.assertEqual(request.headers["Authorization"], "Bearer console-admin")
            return httpx.Response(200, json={"authorization": {"bundle_id": "PAC15-CAPABILITIES-20261001", "pack_version": "test"}})
        with self.transport(handle):
            await a.authorization_bundle_served()

    async def test_relationship_queries_reach_scope_policy_after_volume_check(self):
        from app.classify import bulk_read_reason
        queries = []

        async def call(who, tool, arguments):
            self.assertEqual((who, tool), ("employee", "postgres__execute_sql"))
            self.assertIsNone(bulk_read_reason("postgres", "execute_sql", arguments, 100))
            queries.append(arguments["sql"])
            outside = "hr.employees" in arguments["sql"]
            return {"decision": "Alert" if outside else "Allow",
                    "policy_id": "P-SCOPE-001" if outside else "P-AUTHZ-ALLOW-001",
                    "is_error": False, "text": ""}

        with patch.object(a, "operating", new=AsyncMock()), patch.object(a, "call", new=call), \
                patch.object(a.db, "fetch_one", new=AsyncMock(return_value={"policy_input": {
                    "relationship": {"ids": ["UR-PG-ANALYTICS"], "outside": ["hr.employees"]}}})):
            await a.relationship_scope_alerts()
        self.assertEqual(len(queries), 2)
        for sql in queries:
            self.assertIsNotNone(bulk_read_reason("postgres", "execute_sql", {
                "sql": sql.rsplit(" LIMIT ", 1)[0]}, 100))


if __name__ == "__main__":
    unittest.main()
