"""Suggestions locally; real approval functions with DB/HTTP doubles in the gateway image.

No MCP implementation is created here. HTTP discovery fixtures are unit-test data,
not evidence of an MCP server, a model/harness run, deployment or independent effects.
"""
from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "gateway"))
sys.path.insert(0, str(LAB / "supply_chain"))
from app import intake_proposal, residency, supplier_assurance
from supplier_metadata import collect

try:
    from fastapi import HTTPException
    from app import agent_service as service, core, review
except (ModuleNotFoundError, ImportError) as exc:
    HTTPException = service = core = review = None
    IMPORT_ERROR = str(exc)

REQUEST_ID = UUID("8a34be6a-ff5b-4422-a397-aea587d1b15c")
NOW = datetime.now(timezone.utc)
TOOL = {"name": "lookup", "description": "Search public documentation", "input_schema": {
    "type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    "output_schema": None, "annotations": {"read_only_hint": True, "open_world_hint": False},
    "suggested": "r", "warnings": []}
CATALOG = {"endpoint": "https://example.test/mcp", "catalog_hash": "a" * 64,
           "server_name": "documentation", "version": "1.0", "protocol_version": "2025-11-25", "tools": [TOOL]}


URL_TOOL = {"name": "read_page", "description": "Read a page from docs.example.org or https://kb.example.net/articles. See README.md",
            "input_schema": {"$schema": "http://json-schema.org/draft-07/schema#", "type": "object",
                             "properties": {"url": {"type": "string"}}, "required": ["url"]},
            "output_schema": None, "annotations": {"readOnlyHint": True}, "suggested": "r", "warnings": []}


def row(kind="remote-endpoint", grade="public"):
    source = kind == "repository"
    return {"id": REQUEST_ID, "status": "VALIDATED" if source else "HOLD", "intake_kind": kind,
            "display_name": "문서 검색", "purpose": "업무 공개 문서 검색에 사용", "submitted_by": "employee",
            "submitter_user_id": "employee", "submitter_name": "신청 직원", "department": "개발",
            "endpoint_url": None if source else CATALOG["endpoint"], "repository_url": "https://github.com/org/docs" if source else "",
            "requested_transport": "stdio" if source else "streamable-http", "commit_sha": "b" * 40 if source else None,
            "source_ref": "docs@" + "b" * 40 if source else None, "validated_at": NOW if source else None,
            "internal_repo_url": None, "risk_level": "LOW", "risk_input": {"data_class": grade},
            "requested_tools": [], "exit_terms": {}, "registered_server_id": None,
            "provenance": {"kind": "source", "source_url": "https://github.com/org/docs", "version": "b" * 40,
                           "license": {"spdx": "MIT"}, "artifact": {"sha256": "c" * 64}} if source else {},
            "evidence": {"scanners": {name: {"status": "DONE"} for name in ("syft", "trivy", "semgrep", "gitleaks")}}}


class SuggestionCheck(unittest.TestCase):
    def test_id_is_valid_stable_and_distinct(self):
        first = row()
        self.assertRegex(intake_proposal.server_id(first), r"^[a-z][a-z0-9-]{1,30}$")
        self.assertEqual(intake_proposal.server_id(first), intake_proposal.server_id(first))
        self.assertNotEqual(intake_proposal.server_id(first), intake_proposal.server_id({**first, "id": "c" * 32}))
        monorepo = {**row("repository"), "repository_url": "https://github.com/modelcontextprotocol/servers",
                    "repository_path": "src/filesystem"}
        self.assertTrue(intake_proposal.server_id(monorepo).startswith("filesystem-"))

    def test_destructive_and_command_arguments_outrank_read_hint(self):
        self.assertEqual(intake_proposal.action(TOOL), "r")
        self.assertEqual(intake_proposal.action({**TOOL, "annotations": {"readOnlyHint": True, "destructiveHint": True}}), "x")
        self.assertEqual(intake_proposal.action({**TOOL, "input_schema": {"properties": {"shell_command": {}}}}), "x")

    def test_applicant_grade_preserved_and_other_inputs_derived(self):
        for grade in ("public", "nonimportant", "important"):
            value = intake_proposal.risk_input(row(grade=grade), [TOOL])
            self.assertEqual(value["data_class"], grade)
            self.assertTrue(value["external_transfer"])
            self.assertEqual(value["permission"], "r")
            self.assertEqual(value["users"], 1)
            self.assertEqual(value["autonomy"], "autonomous")
        self.assertFalse(intake_proposal.risk_input(row("repository"), [TOOL])["external_transfer"])

    def test_automatic_scope_grants_no_unknown_hosts_or_cross_server_data(self):
        scope = intake_proposal.tool_reviews(row(), [TOOL])["lookup"]
        self.assertEqual(scope["destinations"], [])
        self.assertEqual(scope["accepts_from"], [])
        self.assertTrue(scope["consent"])
        self.assertTrue(scope["mask"])

    def test_address_tool_gets_its_server_and_contract_hosts_as_a_suggestion(self):
        # S4-02: with no suggestion an address argument was registered to match nothing at all.
        hosts = intake_proposal.tool_reviews(row(), [URL_TOOL], {"read_page"})["read_page"]["destinations"]
        self.assertEqual(hosts, ["example.test", "docs.example.org", "kb.example.net"])
        self.assertEqual(intake_proposal.tool_reviews(row(), [URL_TOOL])["read_page"]["destinations"], [])
        self.assertEqual(intake_proposal.tool_reviews(row("repository"), [URL_TOOL], {"read_page"})["read_page"]["destinations"],
                         ["docs.example.org", "kb.example.net"])

    @unittest.skipIf(review is None, "review needs the gateway dependencies")
    def test_registered_address_pattern_follows_new_destinations_only_when_derived(self):
        derived = review.derived_constraints({"read_page": URL_TOOL}, {"read_page": {"destinations": []}})["read_page"]
        self.assertEqual(derived["properties"]["url"]["pattern"], "(?!)")
        self.assertTrue(review.pinned_addresses(derived))
        moved = review.repin_addresses(derived, ["docs.example.org"])
        self.assertRegex("https://docs.example.org/a", moved["properties"]["url"]["pattern"])
        self.assertNotRegex("https://evil.example/a", moved["properties"]["url"]["pattern"])
        written = {"type": "object", "properties": {"url": {"type": "string", "pattern": "^https://intranet\\.test/"}}}
        self.assertEqual(review.repin_addresses(written, ["docs.example.org"]), written)
        self.assertFalse(review.pinned_addresses(written))

    def test_fingerprint_binds_source_grade_tools_and_scan_counts(self):
        original = row("repository")
        changed = {**original, "requested_tools": ["lookup"]}
        self.assertNotEqual(intake_proposal.basis(original), intake_proposal.basis(changed))
        self.assertNotEqual(intake_proposal.digest({"catalog_hash": "a"}), intake_proposal.digest({"catalog_hash": "b"}))
        self.assertNotEqual(intake_proposal.scan_basis({"critical": {"count": 1}}),
                            intake_proposal.scan_basis({"critical": {"count": 2}}))

    def test_assurance_optional_but_invalid_or_expired_eol_refused(self):
        self.assertEqual(supplier_assurance.validate({}, required=False), [])
        self.assertTrue(supplier_assurance.validate({"support_end": "2020-01-01"}, required=False))
        self.assertTrue(supplier_assurance.validate({"vulnerability_policy_url": "http://example.test"}, required=False))
        until = NOW + timedelta(days=90)
        self.assertEqual(supplier_assurance.renewal_until(until, 1, None), until + timedelta(days=1))

    def test_pack_default_disabled_and_opt_in_missing_location_refused(self):
        self.assertFalse(residency.enabled({}))
        residency.require_location({}, "important", {})
        with self.assertRaises(ValueError):
            residency.require_location({}, "important", {"jurisdiction_pack_enabled": True})
        self.assertTrue(residency.enabled({"jurisdiction_pack_enabled": "invalid"}))

    def test_supplier_files_are_bounded_untrusted_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "package.json").write_text('{"author":{"name":"Example","email":"support@example.test"},"homepage":"https://example.test"}', encoding="utf-8")
            (root / "SECURITY.md").write_text("Contact security@example.test", encoding="utf-8")
            metadata = collect(root, "https://github.com/org/docs", "b" * 40)
            self.assertEqual(metadata["legal_entity"], "Example")
            self.assertEqual(metadata["security_contact"], "security@example.test")
            self.assertIn("b" * 40, metadata["vulnerability_policy_url"])
            self.assertNotIn("support_end", metadata)
            (root / "package.json").write_text("invalid JSON", encoding="utf-8")
            self.assertNotIn("supplier_contact", collect(root, "https://github.com/org/docs", "b" * 40))


@unittest.skipIf(service is None, "Gateway image required: " + globals().get("IMPORT_ERROR", ""))
class ApprovalFlowCheck(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.state = row()
        self.admin = {"principal": "admin-a", "user_id": "admin-a", "roles": ["admin"]}
        self.events = []
        self.registered = []
        self.catalog = copy.deepcopy(CATALOG)
        self.pack = False
        self.scanner_failure = False
        self.critical = 0

        @asynccontextmanager
        async def transaction():
            connection = MagicMock()
            connection.execute = AsyncMock()
            yield connection

        async def fetch_one(sql, params=(), *, connection=None):
            if sql.startswith("UPDATE mcp_intake_requests SET evidence"):
                self.assertEqual(params[2].obj, self.state["evidence"])
                self.state["evidence"] = copy.deepcopy(params[0].obj)
                return {"id": REQUEST_ID}
            return copy.deepcopy(self.state)

        async def transition(sql, params, **event):
            self.events.append(event)
            if "SET status='APPROVED'" in sql:
                self.assertEqual(params[6].obj, self.state["evidence"])
                self.state.update(status="APPROVED", evidence=copy.deepcopy(params[0].obj), provenance=copy.deepcopy(params[1].obj),
                                  risk_input=copy.deepcopy(params[2].obj), internal_repo_url=params[3], reviewed_by=params[4])
            else:
                self.assertEqual(params[2].obj, self.state["evidence"])
                self.state["evidence"] = copy.deepcopy(params[0].obj)
            return {"id": REQUEST_ID, "status": self.state["status"]}

        async def proxy(path, authorization, method="GET", body=None, **kwargs):
            if path == "/api/registry":
                return {"organization": {"jurisdiction_pack_enabled": self.pack}}
            if path.endswith("/discover"):
                return copy.deepcopy(self.catalog)
            self.assertEqual(path, "/api/registry/servers")
            self.assertEqual(self.state["status"], "APPROVED")
            self.registered.append(copy.deepcopy(body))
            return {"valid_until": (NOW + timedelta(days=90)).isoformat(), "server_id": body["server_id"]}

        async def reports(current, *, connection=None):
            return [{"id": i, "scanner": name, "scanner_version": "1", "status": "DONE", "critical_count": self.critical if i == 1 else 0,
                     "high_count": 0, "summary": {}, "imported_at": NOW, "vuln_db_updated_at": NOW}
                    for i, name in enumerate(review.SCANNERS)]

        async def same_person(a, b, *, connection=None):
            return a == b or {a, b} == {"admin-a", "admin-alias"}

        patches = [patch.object(service.db, "transaction", transaction), patch.object(service.db, "fetch_one", AsyncMock(side_effect=fetch_one)),
                   patch.object(service.db, "execute", AsyncMock()), patch.object(service, "gateway_proxy", AsyncMock(side_effect=proxy)),
                   patch.object(service, "current_identity", AsyncMock(return_value=self.admin)),
                   patch.object(service, "publish_internal_repo", AsyncMock(return_value=("https://internal.test/docs", {"match": True, "sha256": "c" * 64}))),
                   patch.object(review, "transition", AsyncMock(side_effect=transition)), patch.object(review, "record_event", AsyncMock()),
                   patch.object(review, "same_person", AsyncMock(side_effect=same_person)), patch.object(review, "intake_reports", AsyncMock(side_effect=reports)),
                   patch.object(review, "active_acceptance", AsyncMock(return_value=None))]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    async def preview(self):
        return await service.preview_intake_approval(REQUEST_ID, service.ApprovalPreview(), self.admin, "console-token")

    def approval(self, preview, **kwargs):
        return service.OneClickApproval(proposal_sha256=preview["proposal_sha256"], tools=list(preview["proposal"]["tools"]), **kwargs)

    async def test_remote_one_approval_registers_and_records_each_checked_tool(self):
        preview = await self.preview()
        await service.approve_and_register(REQUEST_ID, self.approval(preview), self.admin, "console-token")
        self.assertEqual(len(self.registered), 1)
        self.assertEqual(self.registered[0]["tools"], {"lookup": "r"})
        self.assertEqual(self.state["evidence"]["remote_contract"]["allowed_principals"], ["*"])  # D-234 default: all employees
        self.assertEqual(self.events[-1]["actor"], "admin-a")

    async def test_audience_requester_and_selected_land_in_the_contract(self):
        preview = await self.preview()
        await service.approve_and_register(REQUEST_ID, self.approval(preview, audience="requester"), self.admin, "console-token")
        self.assertEqual(self.state["evidence"]["remote_contract"]["allowed_principals"], ["employee"])
        self.assertEqual(self.events[-1]["scope"]["audience"], "requester")
        self.state = row()
        preview = await self.preview()
        people = AsyncMock(return_value=[{"token": "emp-kim", "user_id": "kim"}])
        with patch.object(service.db, "fetch_all", people):
            await service.approve_and_register(REQUEST_ID, self.approval(preview, audience="selected", audience_users=["kim", " "]),
                                               self.admin, "console-token")
        self.assertEqual(self.state["evidence"]["remote_contract"]["allowed_principals"], ["emp-kim"])
        self.assertEqual(self.events[-1]["scope"]["audience_principals"], ["emp-kim"])

    async def test_selected_audience_is_checked_before_a_first_approval_is_recorded(self):
        self.state = row(grade="important")  # 두 명이 필요한 등급: 첫 클릭이 대기를 기록하기 전에 사용 대상을 거른다
        preview = await self.preview()
        for users, expected in (([], "한 명 이상"), (["ghost"], "활성 계정이 아닌")):
            with patch.object(service.db, "fetch_all", AsyncMock(return_value=[])), self.assertRaises(service.HTTPException) as raised:
                await service.approve_and_register(REQUEST_ID, self.approval(preview, audience="selected", audience_users=users),
                                                   self.admin, "console-token")
            self.assertEqual(raised.exception.status_code, 422)
            self.assertIn(expected, raised.exception.detail)
        self.assertNotIn("one_click_pending", self.state["evidence"])
        self.assertEqual(self.registered, [])

    async def test_repository_one_approval_publishes_and_registers(self):
        self.state = row("repository")
        self.state['evidence']['local_run'] = {'source': {'commit': self.state['commit_sha']}}
        signed = {'manifest': {'source': self.state['evidence']['local_run']['source']}, 'signature': 'unit-fixture'}
        with patch.object(service, 'signed_local_run', AsyncMock(return_value=signed), create=True):
            preview = await self.preview()
            await service.approve_and_register(REQUEST_ID, self.approval(preview), self.admin, "console-token")
        service.publish_internal_repo.assert_awaited_once()
        self.assertEqual(len(self.registered), 1)
        self.assertEqual(self.state["provenance"]["verification"]["by"], "admin-a")
        self.assertEqual(self.registered[0]["endpoint"], service.local_jobs.PREFIX + preview['proposal']['server_id'])
        self.assertEqual(self.registered[0]['local'], signed)

    async def test_gateway_scope_guard_accepts_exact_review_and_refuses_edits(self):
        preview = await self.preview()
        await service.approve_and_register(REQUEST_ID, self.approval(preview), self.admin, "console-token")
        body = self.registered[0]

        class ReachedGate(Exception):
            pass

        with patch.object(review, "intake_gate", AsyncMock(side_effect=ReachedGate)), patch.object(core.registry, "catalog", return_value={}):
            with self.assertRaises(ReachedGate):
                await core.register_server(body, "admin-a")
            for change in ({"tools": {"lookup": "x"}}, {"valid_days": 365}, {"data_class": "important"},
                           {"catalog_hash": "d" * 64}, {"tool_reviews": {"lookup": {"purpose": "다른 목적", "asset": "다른 자산"}}}):
                with self.assertRaises(ValueError):
                    await core.register_server({**body, **change}, "admin-a")

    async def test_admin_may_lower_tool_action_only_and_gateway_accepts_it(self):
        # 공개 MCP가 readOnlyHint를 달지 않으면 읽기 도구도 쓰기로 제안된다.
        self.catalog["tools"][0] = {**TOOL, "annotations": {}, "suggested": "w"}
        preview = await self.preview()
        self.assertEqual(preview["proposal"]["tools"], {"lookup": "w"})
        with self.assertRaises(service.HTTPException) as raised:
            await service.approve_and_register(REQUEST_ID, self.approval(preview, actions={"lookup": "x"}), self.admin, "console-token")
        self.assertEqual(raised.exception.status_code, 422)
        await service.approve_and_register(REQUEST_ID, self.approval(preview, actions={"lookup": "r"}), self.admin, "console-token")
        body = self.registered[0]
        self.assertEqual(body["tools"], {"lookup": "r"})
        self.assertEqual(self.state["evidence"]["one_click_scope"]["actions"], {"lookup": "r"})

        class ReachedGate(Exception):
            pass

        with patch.object(review, "intake_gate", AsyncMock(side_effect=ReachedGate)), patch.object(core.registry, "catalog", return_value={}):
            with self.assertRaises(ReachedGate):
                await core.register_server(body, "admin-a")
            with self.assertRaises(ValueError):
                await core.register_server({**body, "tools": {"lookup": "w"}}, "admin-a")

    async def test_url_tool_suggested_hosts_reach_the_contract_and_the_approver_may_edit_them(self):
        self.catalog["tools"] = [URL_TOOL]
        preview = await self.preview()
        proposal = preview["proposal"]
        self.assertEqual(proposal["address_tools"], ["read_page"])
        self.assertRegex("https://docs.example.org/x", proposal["parameter_constraints"]["read_page"]["properties"]["url"]["pattern"])
        for wrong in ({"read_page": ["https://docs.example.org/"]}, {"lookup": ["docs.example.org"]}):
            with self.assertRaises(HTTPException) as raised:
                await service.approve_and_register(REQUEST_ID, self.approval(preview, destinations=wrong), self.admin, "console-token")
            self.assertEqual(raised.exception.status_code, 422)
        await service.approve_and_register(REQUEST_ID, self.approval(preview, destinations={"read_page": [" Learn.Example.org", "docs.example.org"]}),
                                           self.admin, "console-token")
        pattern = self.state["evidence"]["remote_contract"]["parameter_constraints"]["read_page"]["properties"]["url"]["pattern"]
        self.assertRegex("https://learn.example.org/a", pattern)
        self.assertNotRegex("https://kb.example.net/a", pattern)
        self.assertEqual(self.state["evidence"]["one_click_scope"]["destinations"], {"read_page": ["docs.example.org", "learn.example.org"]})
        body = self.registered[0]
        self.assertEqual(body["tool_reviews"]["read_page"]["destinations"], ["docs.example.org", "learn.example.org"])

        class ReachedGate(Exception):
            pass

        with patch.object(review, "intake_gate", AsyncMock(side_effect=ReachedGate)), patch.object(core.registry, "catalog", return_value={}):
            with self.assertRaises(ReachedGate):  # the gateway's scope guard accepts the edited destinations
                await core.register_server(body, "admin-a")
            edited = copy.deepcopy(body)
            edited["tool_reviews"]["read_page"]["destinations"] = ["evil.example"]
            with self.assertRaises(ValueError):
                await core.register_server(edited, "admin-a")

    async def test_second_review_keeps_scope_but_contract_drift_discards_first_approval(self):
        self.state = row(grade="important")
        preview = await self.preview()
        await service.approve_and_register(REQUEST_ID, self.approval(preview), self.admin, "console-token")
        unchanged = await self.preview()
        self.assertIn("pending", unchanged)
        self.assertEqual(unchanged["proposal_sha256"], preview["proposal_sha256"])
        self.catalog["catalog_hash"] = "d" * 64
        changed = await self.preview()
        self.assertNotIn("pending", changed)
        self.assertNotIn("one_click_pending", self.state["evidence"])

    async def test_same_person_cannot_approve(self):
        with self.assertRaises(HTTPException) as error:
            await service.preview_intake_approval(REQUEST_ID, service.ApprovalPreview(),
                {"principal": "employee", "user_id": "employee", "roles": ["admin"]}, "console-token")
        self.assertEqual(error.exception.status_code, 403)
        self.assertEqual(self.registered, [])

    async def test_contract_change_is_refused_without_registration(self):
        preview = await self.preview()
        self.catalog["catalog_hash"] = "d" * 64
        with self.assertRaises(HTTPException) as error:
            await service.approve_and_register(REQUEST_ID, self.approval(preview), self.admin, "console-token")
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.registered, [])

    async def test_failed_scan_disables_preview_and_refuses_forged_click(self):
        self.state = row("repository")
        self.state["evidence"]["scanners"]["semgrep"]["status"] = "FAILED"
        preview = await self.preview()
        self.assertIn("scan-incomplete", {b["code"] for b in preview["proposal"]["blockers"]})
        with self.assertRaises(HTTPException):
            await service.approve_and_register(REQUEST_ID, self.approval(preview), self.admin, "console-token")
        self.assertEqual(self.registered, [])

    async def test_high_tier_waits_and_alias_is_not_a_second_person(self):
        self.state = row(grade="important")
        preview = await self.preview()
        request = self.approval(preview)
        first = await service.approve_and_register(REQUEST_ID, request, self.admin, "console-token")
        self.assertTrue(first["pending"])
        self.assertEqual(self.state["status"], "HOLD")
        self.assertEqual(self.registered, [])
        self.assertTrue((await service.approve_and_register(REQUEST_ID, request,
            {**self.admin, "principal": "admin-alias"}, "console-token"))["pending"])
        second = {"principal": "admin-b", "user_id": "admin-b", "roles": ["admin"]}
        service.current_identity.return_value = second
        await service.approve_and_register(REQUEST_ID, request, second, "console-token")
        self.assertEqual(len(self.registered), 1)
        self.assertEqual(self.state["evidence"]["risk_assessment"]["approvers"], ["admin-a", "admin-b"])

    async def test_grade_change_after_display_is_refused(self):
        preview = await self.preview()
        self.state["risk_input"]["data_class"] = "important"
        with self.assertRaises(HTTPException):
            await service.approve_and_register(REQUEST_ID, self.approval(preview), self.admin, "console-token")
        self.assertEqual(self.registered, [])

    async def test_pack_activated_after_preview_requires_new_review(self):
        preview = await self.preview()
        self.pack = True
        with self.assertRaises(HTTPException):
            await service.approve_and_register(REQUEST_ID, self.approval(preview), self.admin, "console-token")
        self.assertEqual(self.registered, [])

    async def test_repository_without_endpoint_execution_is_not_registered(self):
        self.state = row("repository")
        preview = await self.preview()
        self.assertIn("execution-missing", {b["code"] for b in preview["proposal"]["blockers"]})
        with self.assertRaises(HTTPException):
            await service.approve_and_register(REQUEST_ID, service.OneClickApproval(
                proposal_sha256=preview["proposal_sha256"], tools=["lookup"]), self.admin, "console-token")


if __name__ == "__main__":
    unittest.main(verbosity=2)
