"""Security-boundary checks; provider success is tested separately against Keycloak."""
import asyncio
import hashlib
import json
import logging
import os
import secrets
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import audit, main, oidc, secret_scan
from intake_worker import gitleaks_counts


class AuditTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def test_admin_boundary_and_limits(self):
        async def denied():
            raise HTTPException(403, "admin required")
        main.app.dependency_overrides[main.admin_caller] = denied
        for path in ("/api/audit/events", "/api/audit/export", "/api/audit/events/1"):
            self.assertEqual(self.client.get(path).status_code, 403)
        main.app.dependency_overrides[main.admin_caller] = lambda: {"roles": ["admin"]}
        self.assertEqual(self.client.get("/api/audit/events?limit=501").status_code, 422)
        self.assertEqual(self.client.get("/api/audit/events?since=2026-10-03T00:00:00").status_code, 422)

    def test_unknown_remains_unknown_and_filters_are_parameterized(self):
        where, params = audit.predicates(server="'; DELETE FROM decisions; --", execution="unknown")
        self.assertNotIn("DELETE", where)
        self.assertIn("upstream_attempted=true AND upstream_executed=false", where)
        self.assertEqual(params, ["'; DELETE FROM decisions; --"])
        for column in ("request_payload", "policy_input", "result,", "password", "token_sha256"):
            self.assertNotIn(column, audit.PROJECTION)
        with self.assertRaises(HTTPException):
            audit.predicates(since=datetime.now(), until=datetime.now(UTC))

    def test_pagination(self):
        # The second query is the invalid-row annotations (review.mark_invalid): none here.
        with patch.object(audit.db, "fetch_all", AsyncMock(side_effect=[[{"id": 3}, {"id": 2}, {"id": 1}], []])):
            page = asyncio.run(audit.events(limit=2))
        self.assertEqual([row["id"] for row in page["events"]], [3, 2])
        self.assertTrue(page["has_more"])
        self.assertEqual(page["next_before"], 2)


class OidcTest(unittest.TestCase):
    def test_callback_code_is_not_logged(self):
        record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
            ("127.0.0.1", "GET", "/auth/oidc/callback?code=private-code&state=private-state", "1.1", 303), None)
        oidc.RedactCallbackQuery().filter(record)
        self.assertNotIn("private-code", record.getMessage())
        self.assertNotIn("private-state", record.getMessage())
        self.assertIn("/auth/oidc/callback", record.getMessage())

    def test_local_password_bypass_is_disabled(self):
        with patch.dict(os.environ, {"AUTH_PROVIDER": "oidc"}):
            with self.assertRaises(HTTPException) as denied:
                oidc.local_login_allowed()
            self.assertEqual(denied.exception.status_code, 403)
            for scope in ("console", "mcp", ""):
                with self.assertRaises(HTTPException):
                    asyncio.run(oidc.validate_session({"scope": scope}))
            asyncio.run(oidc.validate_session({"scope": "mcp", "device_id": "managed-test-device"}))

    def test_encrypted_upstream_credentials(self):
        with patch.dict(os.environ, {"OIDC_SESSION_SECRET": "test-only-"*8}):
            token = "synthetic-provider-credential"
            sealed = oidc.seal(token)
            self.assertNotIn(token.encode(), sealed)
            self.assertEqual(oidc.unseal(sealed), token)

    def test_client_wiring_has_one_owner_and_one_oauth_registry(self):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from app import agent_contract, oidc_client
        self.assertIs(oidc.oauth, oidc_client.oauth)
        for name in oidc.__all__:
            self.assertIs(getattr(oidc, name), getattr(oidc_client, name), name)
        self.assertEqual(agent_contract.CONSOLE_SCOPE, oidc_client.CONSOLE_SCOPE)
        self.assertEqual(oidc.CONSOLE_SCOPE, "console")
        env = {"AUTH_PROVIDER": "oidc", "OIDC_ISSUER": "https://idp.example/realms/x/", "OIDC_CLIENT_ID": "cid",
               "OIDC_CLIENT_SECRET": "client-secret", "OIDC_REDIRECT_URI": "https://gw.example/auth/oidc/callback",
               "OIDC_SESSION_SECRET": "session-secret-" * 3, "OIDC_PROVIDER_LABEL": "SSO"}
        with patch.dict(os.environ, env), patch.dict(oidc.oauth._registry, clear=True),                 patch.dict(oidc.oauth._clients, clear=True):
            # Settings are read per call, never frozen at import.
            self.assertEqual(oidc.settings(), {"provider": "oidc", "issuer": "https://idp.example/realms/x",
                                               "client_id": "cid", "redirect_uri": env["OIDC_REDIRECT_URI"], "label": "SSO"})
            with patch.dict(os.environ, {"OIDC_CLIENT_ID": "other"}):
                self.assertEqual(oidc.settings()["client_id"], "other")
            first = oidc.client()
            self.assertIs(oidc_client.client(), first)
            self.assertIs(oidc.oauth.create_client("organization"), first)
            self.assertEqual(list(oidc_client.oauth._registry), ["organization"])
            self.assertIsInstance(first, oidc_client.PinnedOAuthApp)
            self.assertIs(first.client_cls, oidc_client.PinnedOAuthClient)
            self.assertEqual((first.client_id, first.client_secret), ("cid", "client-secret"))
            self.assertEqual(first._server_metadata_url,
                             "https://idp.example/realms/x/.well-known/openid-configuration")
            self.assertEqual(first.client_kwargs, {"scope": "openid profile", "code_challenge_method": "S256",
                                                   "timeout": 10, "trust_env": False})
            key = hashlib.sha256(env["OIDC_SESSION_SECRET"].encode()).digest()
            sealed = oidc.seal("token")
            self.assertEqual(AESGCM(key).decrypt(sealed[:12], sealed[12:], b"mcpgw-oidc-session"), b"token")
            self.assertEqual(oidc.unseal(oidc_client.seal("again")), "again")
            with patch.dict(os.environ, {"OIDC_DISCOVERY_URL": "http://keycloak:8080/realms/x/.well-known/openid-configuration"}),                     patch.dict(oidc.oauth._registry, clear=True), patch.dict(oidc.oauth._clients, clear=True):
                self.assertEqual(oidc.client()._server_metadata_url,
                                 "http://keycloak:8080/realms/x/.well-known/openid-configuration")
        with patch.dict(os.environ, {**env, "OIDC_CLIENT_SECRET": ""}), patch.dict(oidc.oauth._registry, clear=True),                 patch.dict(oidc.oauth._clients, clear=True):
            with self.assertRaises(HTTPException) as unconfigured:
                oidc.client()
            self.assertEqual(unconfigured.exception.status_code, 503)
            self.assertEqual(oidc.oauth._registry, {})

    def test_handoff_cannot_be_reused_or_empty(self):
        from starlette.requests import Request
        request = Request({"type": "http", "headers": []})
        with patch.object(oidc.db, "fetch_one", AsyncMock(return_value=None)):
            with self.assertRaises(HTTPException) as denied:
                asyncio.run(oidc.session(request))
            self.assertEqual(denied.exception.status_code, 401)


class SecretTest(unittest.TestCase):
    def test_real_scanner_checks_url_values_and_rejects_allow_comments(self):
        token = "npm_" + secrets.token_hex(18)
        for text in (f"https://external.example/?key={token}&page=1",
                     f"https://external.example/?key={token}#gitleaks:allow",
                     f"https://external.example/?key={token}%20%23%20gitleaks:allow"):
            self.assertIn("gitleaks:npm-access-token", asyncio.run(secret_scan.labels(text)))

    def test_sanitized_artifact(self):
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder)/"report.json"
            report.write_text(json.dumps([{"RuleID": "github-pat", "File": folder+"/config.env",
                "StartLine": 2, "Secret": "synthetic-secret", "Match": "sensitive source snippet"}]))
            counts, findings = gitleaks_counts(report, Path(folder))
            self.assertEqual(counts["HIGH"], 1)
            self.assertEqual(findings[0]["target"], "config.env")
            self.assertNotIn("synthetic-secret", report.read_text())
            self.assertNotIn("sensitive source snippet", report.read_text())

    def test_missing_scanner_fails_closed(self):
        # The scanner is the in-process library now; a missing one must still block, never read as "clean".
        with patch.object(secret_scan, "LIBRARY", "/missing/libmcpgw_gitleaks.so"), patch.object(secret_scan, "_library", None):
            with self.assertRaises(secret_scan.InspectionUnavailable):
                asyncio.run(secret_scan.labels("ordinary outbound text"))


if __name__ == "__main__":
    unittest.main()
