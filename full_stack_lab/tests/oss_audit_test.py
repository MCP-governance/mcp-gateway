"""Security-boundary checks; provider success is tested separately against Keycloak."""
import asyncio
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
        with patch.object(audit.db, "fetch_all", AsyncMock(return_value=[{"id": 3}, {"id": 2}, {"id": 1}])):
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
        with patch.dict(os.environ, {"GITLEAKS_BINARY": "/missing/gitleaks"}):
            with self.assertRaises(secret_scan.InspectionUnavailable):
                asyncio.run(secret_scan.labels("ordinary outbound text"))


if __name__ == "__main__":
    unittest.main()
