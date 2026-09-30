"""Intake automation, partial scanner evidence and report authorization regressions."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

LAB = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(LAB / "supply_chain"), str(LAB / "gateway")]
from exit_terms import conclude, investigate
from app import agent_service, core
from fastapi.testclient import TestClient
import intake_worker as worker


class InvestigationTest(unittest.TestCase):
    def test_pinned_evidence_and_a_conclusion_without_a_verification_record(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "README.md").write_text("API key credentials\nAdministrator can revoke\nSession expires\nAudit log retention\n")
            result = investigate(root, "https://github.com/example/server", "a" * 40)
            self.assertEqual(result["status"], "INVESTIGATED")
            self.assertEqual(result["scanned_files"], 1)
            self.assertNotIn("verified_by", result)
            for criterion in result["criteria"].values():
                self.assertEqual(criterion["status"], "CANDIDATE")
                self.assertIn("/blob/" + "a" * 40, criterion["evidence"][0]["url"])
            # Keywords alone ("API key", "revoke") are candidates. With no sentence saying what the
            # server holds, the conclusion is T3 - and it is a conclusion, not the admin's record.
            conclusion = conclude(result, "", "streamable-http")
            self.assertEqual((conclusion["method"], conclusion["grade"]), ("rules", "T3"))
            self.assertNotIn("verified_by", conclusion)

    def test_missing_documents_and_external_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            root.mkdir()
            outside = Path(temp) / "secrets.md"
            outside.write_text("credential revoke audit expiry")
            (root / "external.md").symlink_to(outside)
            (root / "main.py").write_text('raise RuntimeError("must not execute")')
            result = investigate(root, "https://github.com/example/server", "b" * 40)
            self.assertEqual(result["scanned_files"], 0)
            self.assertTrue(all(c["status"] == "NOT_FOUND" for c in result["criteria"].values()))

    def test_limits_are_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for index in range(3):
                (root / f"doc{index}.md").write_text("audit")
            with patch("exit_terms.MAX_FILES", 2):
                result = investigate(root, "https://github.com/example/server", "c" * 40)
            self.assertEqual(result["scanned_files"], 2)
            self.assertTrue(result["truncated"])


class Connection:
    def __init__(self):
        self.calls = []
        self.commits = 0

    def execute(self, sql, args=None):
        self.calls.append((sql, args))

    def commit(self):
        self.commits += 1


class ValidationTest(unittest.TestCase):
    def validate(self, fail=None, critical=False):
        request_id = uuid4()
        connection = Connection()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            work, reports = root / "work", root / "reports"
            reports.mkdir()

            def clone(url, checkout):
                checkout.mkdir(parents=True)
                (checkout / "README.md").write_text("API key revocation and audit retention")
                return "d" * 40

            def run(command, **kwargs):
                name = command[0]
                suffix = {"syft": "sbom.cdx.json", "trivy": "trivy.json", "semgrep": "semgrep.json"}[name]
                path = reports / f"intake-{request_id}-{suffix}"
                if name == fail:
                    return worker.subprocess.CompletedProcess(command, 2, "", "scanner unavailable")
                body = {
                    "syft": {"bomFormat": "CycloneDX", "components": [{"name": "example", "version": "1.0"}]},
                    "trivy": {"SchemaVersion": 2, "Results": [{"Target": "requirements.txt", "Vulnerabilities": [
                        {"VulnerabilityID": "CVE-fixture", "Severity": "CRITICAL" if critical else "HIGH",
                         "PkgName": "example", "InstalledVersion": "1.0", "FixedVersion": "2.0"}]}]},
                    "semgrep": {"results": [], "errors": []},
                }[name]
                path.write_text(json.dumps(body))
                return worker.subprocess.CompletedProcess(command, 0, "", "")

            with patch.multiple(worker, WORK_DIR=work, REPORT_DIR=reports), patch.object(worker, "clone", clone), patch.object(worker, "run", run):
                # A prior artifact must not mask this attempt's scanner failure.
                (reports / f"intake-{request_id}-sbom.cdx.json").write_text('{"bomFormat":"CycloneDX","components":[]}')
                worker.validate(connection, {"id": request_id, "repository_url": "https://github.com/example/server"})
            final = [args for sql, args in connection.calls if "SET status=%s" in sql][-1]
            evidence = final[5].obj
            stored = [args for sql, args in connection.calls if "INSERT INTO supply_chain_reports" in sql]
            self.assertGreaterEqual(connection.commits, 4)
            self.assertTrue((reports / f"intake-{request_id}-exit-terms.json").exists())
            return final, evidence, stored

    def test_success_persists_inventory_and_fix_versions(self):
        final, evidence, stored = self.validate()
        self.assertEqual(final[0], "VALIDATED")
        self.assertEqual(final[1], "HIGH")
        self.assertEqual(len(evidence["reports"]), 4)
        self.assertEqual(stored[0][-1].obj["inventory"][0]["name"], "example")
        self.assertEqual(stored[1][-1].obj["findings"][0]["fixed_version"], "2.0")

    def test_failure_preserves_other_reports_and_cannot_pass(self):
        final, evidence, stored = self.validate(fail="syft")
        self.assertEqual(final[0:2], ("FAILED", "UNASSESSED"))
        self.assertEqual(evidence["scanners"]["syft"]["status"], "FAILED")
        self.assertEqual(len(stored), 2)
        self.assertEqual(len(evidence["reports"]), 3)

    def test_critical_is_rejected(self):
        final, _, _ = self.validate(critical=True)
        self.assertEqual(final[0], "REJECTED")


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.id = uuid4()
        self.row = {"id": str(self.id), "source_ref": "intake:example/server@dddd",
                    "evidence": {"reports": [f"intake-{self.id}-sbom.cdx.json"]}}
        self.client = TestClient(agent_service.app)

    def identity(self, role):
        return patch.object(agent_service, "current_identity", AsyncMock(return_value={"roles": [role], "principal": "test-user"}))

    def test_submission_enters_queue_atomically(self):
        db = AsyncMock(side_effect=[None, {"id": str(self.id), "status": "VALIDATION_QUEUED"}])
        with self.identity("employee"), patch.object(agent_service.db, "fetch_one", db):
            response = self.client.post("/api/mcp-requests", json={
                "display_name": "Example", "repository_url": "https://github.com/example/server",
                "requested_transport": "stdio", "purpose": "use repository MCP safely"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["request"]["status"], "VALIDATION_QUEUED")
        self.assertIn("'VALIDATION_QUEUED'", db.call_args.args[0])

    def test_public_origin_can_submit_but_other_origin_cannot(self):
        body = {"display_name": "Example", "repository_url": "https://github.com/example/server",
                "requested_transport": "stdio", "purpose": "use repository MCP safely"}
        db = AsyncMock(side_effect=[None, {"id": str(self.id), "status": "VALIDATION_QUEUED"}])
        with patch.dict(os.environ, {"IDP_ISSUER": "https://mcp-gw.internal"}), self.identity("employee"), patch.object(agent_service.db, "fetch_one", db):
            allowed = self.client.post("/api/mcp-requests", json=body, headers={"origin": "https://mcp-gw.internal"})
            blocked = self.client.post("/api/mcp-requests", json=body, headers={"origin": "https://elsewhere.invalid"})
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(db.await_count, 2)

    def test_reports_are_admin_only(self):
        with self.identity("employee"):
            self.assertEqual(self.client.get(f"/api/mcp-requests/{self.id}/report").status_code, 403)
            self.assertEqual(self.client.get(f"/api/mcp-requests/{self.id}/artifacts/sbom").status_code, 403)
        # Real identity dependency rejects unauthenticated requests.
        self.assertEqual(self.client.get(f"/api/mcp-requests/{self.id}/report").status_code, 401)

    def test_download_allowlist_and_symlink(self):
        with tempfile.TemporaryDirectory() as temp, self.identity("admin"), patch.object(agent_service.db, "fetch_one", AsyncMock(return_value=self.row)), patch.object(agent_service, "INTAKE_REPORT_DIR", Path(temp)):
            root = Path(temp)
            artifact = root / f"intake-{self.id}-sbom.cdx.json"
            artifact.write_text('{"bomFormat":"CycloneDX"}')
            response = self.client.get(f"/api/mcp-requests/{self.id}/artifacts/sbom")
            self.assertEqual(response.status_code, 200)
            self.assertIn("attachment", response.headers["content-disposition"])
            self.assertEqual(self.client.get(f"/api/mcp-requests/{self.id}/artifacts/unknown").status_code, 404)
            self.assertEqual(self.client.get(f"/api/mcp-requests/{self.id}/artifacts/trivy").status_code, 404)
            artifact.unlink()
            artifact.symlink_to(root / "other.json")
            self.assertEqual(self.client.get(f"/api/mcp-requests/{self.id}/artifacts/sbom").status_code, 404)

    def test_discovery_does_not_bypass_remote_approval(self):
        row = {"status": "VALIDATED", "commit_sha": "d" * 40,
               "requested_transport": "streamable-http", "exit_terms": {},
               "evidence": {"exit_terms_discovery": {"status": "REVIEW_REQUIRED"}}}
        with self.identity("admin"), patch.object(agent_service.db, "fetch_one", AsyncMock(return_value=row)), patch.object(agent_service, "SCAN_REQUIRED_FOR_APPROVAL", False):
            response = self.client.post(f"/api/mcp-requests/{self.id}/approve")
        self.assertEqual(response.status_code, 409)
        self.assertIn("증거 문서", response.json()["detail"])

    def test_signup_is_pending_until_admin_approves(self):
        with patch.object(agent_service.db, "fetch_one", AsyncMock(side_effect=[None, {"id": str(self.id)}])):
            response = self.client.post("/auth/signup", json={
                "username": "newuser", "display_name": "New User", "password": "password-123"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "pending")

    def test_approval_publishes_verified_commit_before_state_change(self):
        pending = {"id": self.id, "status": "VALIDATED", "commit_sha": "d" * 40,
                   "requested_transport": "stdio", "exit_terms": {},
                   "repository_url": "https://github.com/example/server"}
        approved = {"id": self.id, "status": "APPROVED", "internal_repo_url": "http://internal/git/corpadmin/mcp-test"}
        db = AsyncMock(side_effect=[pending, approved])
        publisher = AsyncMock(return_value=approved["internal_repo_url"])
        with self.identity("admin"), patch.object(agent_service.db, "fetch_one", db), \
             patch.object(agent_service, "publish_internal_repo", publisher), \
             patch.object(agent_service, "SCAN_REQUIRED_FOR_APPROVAL", False):
            response = self.client.post(f"/api/mcp-requests/{self.id}/approve")
        self.assertEqual(response.status_code, 200)
        publisher.assert_awaited_once_with(pending)
        self.assertIn("internal_repo_url", db.await_args.args[0])


class AnomalyScanTest(unittest.TestCase):
    def test_live_local_model_queues_anomaly_scan_after_audit(self):
        async def decide():
            return await core._decision_payload(
                {"policy_id": "P-ANOMALY-001", "server_id": "server-1"},
                asyncio.get_running_loop().time(),
            )

        config = {"MCP_SCAN_AUTO_ON_ANOMALY": "1", "MCP_SCAN_BASE_URL": "http://ollama:11434/v1",
                  "MCP_SCAN_MODEL": "local-model", "MCP_SCAN_API_KEY": "local-key",
                  "MCP_SCAN_EVIDENCE_MODE": "live"}
        execute = AsyncMock()
        with patch.dict(os.environ, config), patch.object(core, "_record_decision", AsyncMock(return_value="decision-1")), \
             patch.object(core.db, "execute", execute):
            self.assertEqual(asyncio.run(decide())["decision_id"], "decision-1")
            self.assertIn("'anomaly'", execute.await_args.args[0])
            self.assertEqual(execute.await_args.args[1][1], "server-1")
            execute.reset_mock()
            with patch.dict(os.environ, {"MCP_SCAN_EVIDENCE_MODE": "test-double"}):
                asyncio.run(decide())
            execute.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
