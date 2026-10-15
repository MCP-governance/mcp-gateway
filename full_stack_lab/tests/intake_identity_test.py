"""Intake gate, accepted risks, tool scope normalisation and approver independence (unit level).

The database is replaced by small doubles here, so these cases only show the decision logic. The same
rules against a real PostgreSQL, OPA and the append-only triggers are in intake_identity_pg_check.py.
"""
from __future__ import annotations

import asyncio
import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gateway"))
from app import review  # noqa: E402

NOW = datetime(2026, 10, 15, 12, tzinfo=UTC)
COMMIT = "a" * 40


def intake(**changes) -> dict:
    row = {"id": uuid4(), "intake_kind": "repository", "repository_url": "https://github.com/o/r", "commit_sha": COMMIT, "source_ref": "intake:o/r@aaaaaaaaaaaa",
           "evidence": {"scanners": {name: {"status": "DONE"} for name in ("syft", "trivy", "semgrep", "gitleaks")}},
           "provenance": {"kind": "source", "source_url": "https://github.com/o/r", "version": COMMIT, "license": {"spdx": "MIT"},
                          "artifact": {"applicable": True, "sha256": "b" * 64},
                          "verification": {"match": True}}}
    return {**row, **changes}


def reports(*, age_days: float | None = 1, critical: int = 0, drop: str | None = None, versions: bool = True) -> list[dict]:
    findings = [{"severity": "CRITICAL", "id": f"CVE-{i}"} for i in range(critical)]
    result = []
    for name in review.SCANNERS:
        if name == drop:
            continue
        result.append({"scanner": name, "scanner_version": "1.0" if versions else None, "critical_count": critical if name == "Trivy" else 0,
                       "summary": {"findings": findings if name == "Trivy" else []}, "imported_at": NOW,
                       "vuln_db_updated_at": None if age_days is None or name != "Trivy" else NOW - timedelta(days=age_days)})
    return result


def gate(row: dict, found: list[dict], acceptance: dict | None = None, **kwargs) -> dict:
    with patch.object(review, "intake_reports", AsyncMock(return_value=found)), \
         patch.object(review, "active_acceptance", AsyncMock(return_value=acceptance)):
        return asyncio.run(review.intake_gate(row, now=NOW, **kwargs))


def codes(result: dict) -> set[str]:
    return {item["code"] for item in result["blockers"]}


class GateTest(unittest.TestCase):
    def test_complete_fresh_evidence_passes(self):
        result = gate(intake(), reports())
        self.assertTrue(result["ok"], result["blockers"])
        self.assertEqual([s["scanner"] for s in result["scanners"]], list(review.SCANNERS))

    def test_vulnerability_database_age_limit_is_seven_days(self):
        self.assertTrue(gate(intake(), reports(age_days=6.9))["ok"])
        self.assertEqual(codes(gate(intake(), reports(age_days=7.1))), {"vuln-db-stale"})
        self.assertEqual(codes(gate(intake(), reports(age_days=30))), {"vuln-db-stale"})

    def test_unknown_database_time_is_stale_not_fresh(self):
        self.assertEqual(codes(gate(intake(), reports(age_days=None))), {"vuln-db-unknown"})

    def test_scanner_outage_fails_closed(self):
        failed = intake(evidence={"scanners": {"syft": {"status": "DONE"}, "trivy": {"status": "FAILED", "error": "x"},
                                               "semgrep": {"status": "DONE"}, "gitleaks": {"status": "DONE"}}})
        self.assertEqual(codes(gate(failed, reports())), {"scan-incomplete"})
        self.assertEqual(codes(gate(intake(evidence={}), reports())), {"scan-incomplete"})
        self.assertEqual(codes(gate(intake(), reports(drop="Semgrep"))), {"scan-report-missing"})
        self.assertEqual(codes(gate(intake(), reports(versions=False))), {"scan-version-missing"})

    def test_critical_findings_block_until_a_live_acceptance_covers_them(self):
        self.assertEqual(codes(gate(intake(), reports(critical=2))), {"critical"})
        acceptance = {"critical_count": 2, "finding_ids": ["CVE-0", "CVE-1"]}
        self.assertTrue(gate(intake(), reports(critical=2), acceptance)["ok"])
        self.assertEqual(codes(gate(intake(), reports(critical=2), {"critical_count": 1, "finding_ids": ["CVE-0"]})), {"critical"})
        self.assertEqual(codes(gate(intake(), reports(critical=1), {"critical_count": 1, "finding_ids": ["CVE-9"]})), {"critical"})

    def test_provenance_gaps_and_mismatch_hold(self):
        self.assertEqual(codes(gate(intake(provenance={}), reports())), {"provenance-missing"})
        self.assertEqual(codes(gate(intake(commit_sha="c" * 40), reports())), {"provenance-mismatch"})
        weak = intake()
        weak["provenance"] = {**weak["provenance"], "license": None}
        result = gate(weak, reports())
        self.assertEqual(codes(result), {"provenance-missing"})
        self.assertIn("라이선스", result["blockers"][0]["message"])

    def test_registration_also_demands_the_copy_comparison(self):
        unverified = intake()
        unverified["provenance"] = {**unverified["provenance"], "verification": {"match": False}}
        self.assertTrue(gate(unverified, reports())["ok"])
        self.assertEqual(codes(gate(unverified, reports(), verified=True)), {"provenance-unverified"})
        self.assertTrue(gate(intake(), reports(), verified=True)["ok"])

    def test_hosted_service_needs_no_scan_but_needs_its_record(self):
        hosted = {"kind": "provider-hosted", "source_url": "https://mcp.example.com/mcp", "version": "2",
                  "artifact": {"applicable": False, "reason": "해당 없음", "endpoint": "https://mcp.example.com/mcp"}}
        row = intake(intake_kind="remote-endpoint", endpoint_url="https://mcp.example.com/mcp", repository_url="", provenance=hosted, evidence={})
        self.assertTrue(gate(row, [], verified=True)["ok"])
        self.assertEqual(codes(gate({**row, "provenance": {}}, [])), {"provenance-missing"})
        self.assertEqual(codes(gate({**row, "endpoint_url": "https://other.example.com/mcp"}, [])), {"provenance-missing"})


class AcceptanceRuleTest(unittest.TestCase):
    def accept(self, row, **kwargs):
        with patch.object(review.db, "fetch_one", AsyncMock(return_value=row)), \
             patch.object(review, "require_independent", AsyncMock()):
            return asyncio.run(review.accept_risk(uuid4(), "admin", kwargs.get("reason", "격리 환경에서만 쓰고 곧 다시 검토합니다."), kwargs.get("days", 7)))

    def test_reason_and_term_limits(self):
        with self.assertRaises(ValueError):
            self.accept(None, reason="짧음")
        for days in (0, review.RISK_ACCEPTANCE_MAX_DAYS + 1):
            with self.assertRaises(ValueError):
                self.accept(None, days=days)

    def test_only_a_validated_critical_source_intake_can_be_accepted(self):
        base = intake(status="HOLD", risk_level="CRITICAL", validated_at=NOW, submitted_by="emp")
        for changed in ({"status": "APPROVED"}, {"risk_level": "LOW"}, {"validated_at": None}, {"intake_kind": "remote-endpoint"}, {"commit_sha": None}):
            with self.assertRaises(ValueError, msg=str(changed)):
                self.accept({**base, **changed})
        with self.assertRaises(ValueError):
            self.accept(None)


class ScopeReviewTest(unittest.TestCase):
    tools = {"search": "r", "write": "w"}
    ok = {"search": {"purpose": "공개 노트 검색", "asset": "notes", "destinations": ["Notes-CDN.example.com", "notes-cdn.example.com"]},
          "write": {"purpose": "노트 작성", "asset": "notes", "destinations": []}}

    def test_every_approved_tool_needs_a_review_and_the_action_comes_from_the_approval(self):
        done = review.normalize_tool_reviews(self.tools, self.ok, "admin", NOW)
        self.assertEqual({k: v["action"] for k, v in done.items()}, self.tools)
        self.assertEqual(done["search"]["destinations"], ["notes-cdn.example.com"])
        self.assertEqual(done["search"]["reviewed_by"], "admin")
        injected = {**self.ok, "search": {**self.ok["search"], "action": "x"}}
        self.assertEqual(review.normalize_tool_reviews(self.tools, injected, "admin")["search"]["action"], "r")

    def test_gaps_are_refused(self):
        for reviews, needle in (({"search": self.ok["search"]}, "write"), ({**self.ok, "other": self.ok["search"]}, "other"),
                                ({**self.ok, "search": {**self.ok["search"], "purpose": "짧"}}, "목적"),
                                ({**self.ok, "search": {**self.ok["search"], "asset": ""}}, "자산"),
                                ({**self.ok, "search": {**self.ok["search"], "destinations": ["https://x.example.com/path"]}}, "목적지"),
                                ({**self.ok, "search": {**self.ok["search"], "destinations": [f"h{i}.example.com" for i in range(11)]}}, "목적지")):
            with self.assertRaises(ValueError) as caught:
                review.normalize_tool_reviews(self.tools, reviews, "admin")
            self.assertIn(needle, str(caught.exception))
        with self.assertRaises(ValueError):
            review.normalize_tool_reviews(self.tools, None, "admin")

    def test_derived_scope_closes_arguments_and_pins_addresses(self):
        from jsonschema import Draft202012Validator
        advertised = {"convert": {"input_schema": {"type": "object", "properties": {"uri": {"type": "string"}},
                                                   "required": ["uri"]}}}
        scope = review.derived_constraints(advertised, {"convert": {"destinations": ["learn.microsoft.com"]}})["convert"]
        ok = Draft202012Validator(scope).is_valid
        self.assertTrue(ok({"uri": "https://learn.microsoft.com/en-us/x"}))
        for bad in ({"uri": "file:///etc/passwd"}, {"uri": "https://learn.microsoft.com.evil.example/x"},
                    {"uri": "http://learn.microsoft.com/x"}, {"uri": "https://169.254.169.254/"},
                    {"uri": "https://learn.microsoft.com/x", "extra": 1}, {}):
            self.assertFalse(ok(bad), bad)
        self.assertEqual(advertised["convert"]["input_schema"]["properties"]["uri"], {"type": "string"}, "advertised schema mutated")
        nowhere = review.derived_constraints(advertised, {"convert": {"destinations": []}})["convert"]
        self.assertFalse(Draft202012Validator(nowhere).is_valid({"uri": "file:///etc/passwd"}))
        self.assertFalse(Draft202012Validator(nowhere).is_valid({"uri": "https://any.example.com/"}),
                         "no reviewed destination must not mean any HTTPS host")
        nested = {"fetch": {"input_schema": {
            "type": "object", "$defs": {"Target": {"type": "object", "properties": {"url": {"type": "string"}}}},
            "properties": {"urls": {"type": "array", "items": {"type": "string"}},
                           "target": {"$ref": "#/$defs/Target"},
                           "page": {"type": "object", "properties": {"link": {"anyOf": [{"type": "string"}, {"type": "null"}]}}}}}}}
        scope = review.derived_constraints(nested, {"fetch": {"destinations": ["docs.example.com"]}})["fetch"]
        ok = Draft202012Validator(scope).is_valid
        self.assertTrue(ok({"urls": ["https://docs.example.com/a"], "target": {"url": "https://docs.example.com/b"},
                            "page": {"link": None}}))
        for bad in ({"urls": ["https://docs.example.com/a", "file:///etc/shadow"]},
                    {"target": {"url": "http://169.254.169.254/latest"}},
                    {"page": {"link": "https://evil.example.net/"}}):
            self.assertFalse(ok(bad), bad)


class IndependenceTest(unittest.TestCase):
    def run_check(self, actor, applicant, **kwargs):
        record = AsyncMock(return_value=1)
        with patch.object(review, "record_event", record), patch.object(review, "same_person", AsyncMock(return_value=False)) as lookup:
            try:
                asyncio.run(review.require_independent("intake-approve", "intake", "id", actor, applicant, {"x": 1}, **kwargs))
                refused = False
            except review.NotIndependent:
                refused = True
        return refused, record, lookup

    def test_the_same_token_is_refused_and_the_refusal_is_recorded(self):
        refused, record, lookup = self.run_check("admin-a", "admin-a")
        self.assertTrue(refused)
        record.assert_awaited_once()
        self.assertEqual(record.await_args.args[:2], ("intake-approve", "refused"))
        lookup.assert_not_awaited()

    def test_two_tokens_of_one_user_are_refused_without_a_lookup(self):
        refused, _, lookup = self.run_check("a-1", "a-2", actor_user="user-1", applicant_user="user-1")
        self.assertTrue(refused)
        lookup.assert_not_awaited()

    def test_different_people_pass(self):
        refused, record, _ = self.run_check("a-1", "b-1", actor_user="user-1", applicant_user="user-2")
        self.assertFalse(refused)
        record.assert_not_awaited()

    def test_unknown_user_ids_fall_back_to_the_ledger(self):
        _, _, lookup = self.run_check("a-1", "b-1")
        lookup.assert_awaited_once()

    def test_no_applicant_cannot_be_the_approver(self):
        refused, _, _ = self.run_check("a-1", None)
        self.assertFalse(refused)


class ClockTest(unittest.TestCase):
    def test_age_boundary_uses_the_named_constant(self):
        from app import provenance
        self.assertEqual(provenance.VULN_DB_MAX_AGE, timedelta(days=7))
        self.assertEqual(review.RISK_ACCEPTANCE_MAX_DAYS, 30)


if __name__ == "__main__":
    unittest.main()
