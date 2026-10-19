"""DEV-70 unit checks. DB/HTTP doubles are not MCP or PostgreSQL execution evidence.

Default: standard-library-only pure/approval/dispatch checks, using production definitions.
--gateway: also import the installed Gateway and exercise execute_call and ToolReview.
"""
from __future__ import annotations

import ast
from contextlib import ExitStack, asynccontextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

APP = Path(__file__).resolve().parents[1] / "gateway" / "app"
if not APP.exists():
    APP = Path("/app/app")
GATEWAY = "--gateway" in sys.argv
if GATEWAY:
    sys.argv.remove("--gateway")
    sys.path.insert(0, str(APP.parent))
    os.environ["OTEL_SDK_DISABLED"] = "true"
    from app import core, agent_contract

spec = importlib.util.spec_from_file_location("high_impact", APP / "high_impact.py")
impact = importlib.util.module_from_spec(spec)
spec.loader.exec_module(impact)


def production(filename, names, namespace):
    tree = ast.parse((APP / filename).read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if getattr(n, "name", None) in names or
             isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in n.targets)]
    if len(nodes) != len(names):
        raise AssertionError("missing production definitions")
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(APP / filename), "exec"), namespace)
    return SimpleNamespace(**namespace)


digest = production("contract.py", {"canonical_hash"}, {"json": json, "hashlib": hashlib}).canonical_hash
UTC = timezone.utc
NOW = datetime.now(UTC)
ITEM = {"purpose": "personnel decision", "asset": "synthetic records", "high_impact": True,
        "impact_domains": ["employment"], "reviewed_by": "reviewer", "reviewed_at": "stamp"}
PAYLOAD = {"server_id": "existing-oss", "tool": "update", "arguments": {"employee": "private@example.com"},
           "user_token": "employee"}


def approval(status="APPROVED"):
    stored = {**deepcopy(PAYLOAD), "impact_scope_sha256": digest(impact.terms(ITEM))}
    explanation = impact.explanation("case", stored["arguments"], ITEM,
                                      {"policy_id": "P-AUTHZ-ALLOW-001", "decision": "Allow"}, "nonimportant", "w")
    return {"id": "case", "status": status, "request_payload": stored, "request_fingerprint": digest(stored),
            "requested_by": "employee", "reviewed_by": "reviewer", "explanation": explanation,
            "expires_at": NOW + timedelta(minutes=10), "review_note": "reviewed"}


class PureChecks(unittest.TestCase):
    def test_local_policy_ledger_has_unique_priority_and_reference_outcome(self):
        path = APP.parent.parent / "opa" / "policy_ledger.json"
        if not path.exists():
            path = Path("/policy/policy_ledger.json")
        ledger = json.loads(path.read_text(encoding="utf-8"))["policy_ledger"]
        self.assertEqual(len(ledger), len({p["priority"] for p in ledger.values()}))
        self.assertEqual((ledger["P-HIGH-IMPACT-001"]["enforced_by"], ledger["P-HIGH-IMPACT-001"]["outcome"]),
                         ("gateway", "추가 승인"))

    def test_label_requires_known_domains_and_real_boolean(self):
        self.assertFalse(impact.normalize({})["high_impact"])
        for item in ({"high_impact": True}, {"impact_domains": ["credit"]},
                     {"high_impact": "false"}, {"high_impact": True, "impact_domains": ["unknown"]}):
            with self.subTest(item=item), self.assertRaises(ValueError):
                impact.normalize(item)
        for domain in impact.DOMAINS:
            self.assertEqual(impact.normalize({"high_impact": True, "impact_domains": [domain, domain]})["impact_domains"], [domain])

    def test_approval_binds_every_request_field_scope_and_integrity(self):
        row = approval()
        self.assertTrue(impact.bound(row, PAYLOAD, ITEM, digest))
        for field in PAYLOAD:
            changed = {**PAYLOAD, field: "changed"}
            self.assertFalse(impact.bound(row, changed, ITEM, digest), field)
        for changes in ({"impact_domains": ["credit"]}, {"high_impact": False}, {"purpose": "different"}):
            self.assertFalse(impact.bound(row, PAYLOAD, {**ITEM, **changes}, digest))
        row["request_payload"]["arguments"] = {"changed": True}
        self.assertFalse(impact.bound(row, row["request_payload"], ITEM, digest))

    def test_unreviewed_replayed_and_revoked_approvals_fail(self):
        for status in ("PENDING", "REJECTED", "EXPIRED", "UNCONFIRMED", "EXECUTED", "NOT_EXECUTED"):
            self.assertFalse(impact.bound(approval(status), PAYLOAD, ITEM, digest))
        for change in ({"reviewed_by": None}, {"explanation": None}, {"revoked_at": NOW}):
            self.assertFalse(impact.bound({**approval(), **change}, PAYLOAD, ITEM, digest))
        self.assertFalse(impact.bound(None, PAYLOAD, ITEM, digest))

    def test_explanation_contains_no_values_keys_summaries_or_scope_prose(self):
        secret = "private@example.com"
        e = impact.explanation("case", {secret: [secret, {secret: 5}], "flag": True, "empty": None},
            {**ITEM, "purpose": secret, "asset": secret},
            {"policy_id": "P-AUTHZ-ALLOW-001", "decision": "Allow", "reason": secret}, "important", "w")
        self.assertNotIn(secret, json.dumps(e))
        self.assertEqual(e["arguments"], {"object": 2, "array": 1, "string": 1, "number": 1, "boolean": 1, "null": 1})
        self.assertFalse(e["effect_reversal"])


class ApprovalChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.row = approval("PENDING")
        self.connection = SimpleNamespace(execute=AsyncMock())
        self.connection.execute.return_value = SimpleNamespace(fetchone=AsyncMock(return_value=approval()))
        @asynccontextmanager
        async def transaction():
            yield self.connection
        self.db = SimpleNamespace(fetch_one=AsyncMock(), fetch_all=AsyncMock(return_value=[]),
                                  execute=AsyncMock(return_value=1), transaction=transaction)
        async def fetch(query, params=()):
            if "principals" in query:
                return {"role": "admin", "status": "active"}
            if "approval_events" in query:
                return {"id": 1}
            return self.row
        self.db.fetch_one.side_effect = fetch
        self.review = SimpleNamespace(record_event=AsyncMock(), require_independent=AsyncMock(),
                                      same_person=AsyncMock(return_value=True), events_for=AsyncMock(return_value=[]),
                                      NotIndependent=type("NotIndependent", (Exception,), {}))
        self.executed = AsyncMock(return_value={"upstream_executed": True, "decision_id": 7})
        self.ns = {"db": self.db, "review": self.review, "high_impact": impact, "canonical_hash": digest,
                   "datetime": datetime, "UTC": UTC, "execute_call": self.executed,
                   "registry": SimpleNamespace(server=lambda _: None)}
        self.mod = production("core.py", {"approve_request", "reject_request", "revoke_approval", "approval_evidence", "_require_explanation"}, self.ns)
        self.hash = digest(self.row["explanation"])

    async def test_approve_requires_view_of_same_snapshot_and_reason(self):
        for evidence, reason in ((None, None), ("0" * 64, "scope_confirmed"), (self.hash, "free text")):
            with self.assertRaises(ValueError):
                await self.mod.approve_request("case", "reviewer", reason, evidence)
        self.executed.assert_not_awaited()
        result = await self.mod.approve_request("case", "reviewer", "scope_confirmed", self.hash)
        self.assertTrue(result["upstream_executed"])
        event = self.review.record_event.await_args
        self.assertEqual(event.args[:2], ("call-approve", "approved"))
        self.assertEqual(event.kwargs["scope"]["explanation"], self.row["explanation"])
        self.assertEqual(event.kwargs["scope"]["request_fingerprint"], self.row["request_fingerprint"])

    async def test_missing_view_fails_closed(self):
        old = self.db.fetch_one.side_effect
        async def fetch(query, params=()):
            return None if "approval_events" in query else await old(query, params)
        self.db.fetch_one.side_effect = fetch
        with self.assertRaises(ValueError):
            await self.mod.approve_request("case", "reviewer", "scope_confirmed", self.hash)
        self.executed.assert_not_awaited()

    async def test_self_approval_and_expiry_do_not_execute(self):
        self.review.require_independent.side_effect = self.review.NotIndependent()
        with self.assertRaises(ValueError):
            await self.mod.approve_request("case", "employee", "scope_confirmed", self.hash)
        self.review.require_independent.side_effect = None
        self.row["expires_at"] = NOW - timedelta(seconds=1)
        with self.assertRaises(ValueError):
            await self.mod.approve_request("case", "reviewer", "scope_confirmed", self.hash)
        self.executed.assert_not_awaited()

    async def test_concurrent_claim_loser_does_not_execute(self):
        self.connection.execute.return_value.fetchone.return_value = None
        with self.assertRaises(ValueError):
            await self.mod.approve_request("case", "reviewer", "scope_confirmed", self.hash)
        self.executed.assert_not_awaited()

    async def test_event_store_failure_prevents_execution(self):
        self.review.record_event.side_effect = RuntimeError("event store unavailable")
        with self.assertRaises(RuntimeError):
            await self.mod.approve_request("case", "reviewer", "scope_confirmed", self.hash)
        self.executed.assert_not_awaited()

    async def test_reject_records_explanation_and_never_executes(self):
        await self.mod.reject_request("case", "reviewer", "request_inappropriate", self.hash)
        self.assertEqual(self.review.record_event.await_args.args[:2], ("call-reject", "rejected"))
        self.assertEqual(self.review.record_event.await_args.kwargs["scope"]["evidence_sha256"], self.hash)
        self.executed.assert_not_awaited()

    async def test_reversal_is_append_only_and_does_not_undo_effects(self):
        self.row["status"] = "EXECUTED"
        result = await self.mod.revoke_approval("case", "reviewer", self.hash)
        self.assertEqual(result["status"], "REVOKED")
        self.assertFalse(result["effect_reversal"])
        self.assertEqual(self.review.record_event.await_args.args[:2], ("call-revoke", "recorded"))
        self.assertIn("revoked_at IS NULL", self.connection.execute.await_args.args[0])
        self.assertNotIn("UPDATE decisions", self.connection.execute.await_args.args[0])
        self.executed.assert_not_awaited()
        self.review.same_person.return_value = False
        with self.assertRaises(ValueError):
            await self.mod.revoke_approval("case", "different-reviewer", self.hash)

    async def test_export_omits_free_text_and_call_bodies_but_logs_reader(self):
        self.review.events_for.return_value = [{"id": 1, "kind": "call-approve", "outcome": "approved", "actor": "reviewer",
             "created_at": NOW, "reason": "private@example.com", "scope": {"arguments": PAYLOAD["arguments"]}}]
        bundle = await self.mod.approval_evidence("case", "reader")
        self.assertNotIn("private@example.com", json.dumps(bundle, default=str))
        self.assertEqual(self.review.record_event.await_args.args[0], "call-explanation-view")
        self.assertEqual(self.review.record_event.await_args.args[4], "reader")
        self.assertNotIn("request_payload", self.db.fetch_all.await_args.args[0])

    async def test_evidence_resolves_display_names_without_replacing_audit_identity(self):
        self.review.events_for.return_value = [
            {"id": i, "kind": "call-approve", "outcome": "approved", "actor": actor, "created_at": NOW}
            for i, actor in enumerate(("reviewer", "unnamed", "deleted"), 1)]
        self.db.fetch_all.side_effect = [
            [{"token": "reviewer", "display_name": "심사자"}, {"token": "unnamed", "display_name": None}], []]
        bundle = await self.mod.approval_evidence("case", "reader")
        self.assertEqual([e["actor_display_name"] for e in bundle["events"]], ["심사자", None, None])
        self.assertEqual([e["actor"] for e in bundle["events"]], ["reviewer", "unnamed", "deleted"])
        lookup = self.db.fetch_all.await_args_list[0]
        self.assertIn("WHERE token = ANY(%s::text[])", lookup.args[0])
        self.assertEqual(set(lookup.args[1][0]), {"reviewer", "unnamed", "deleted"})


class DispatchChecks(unittest.IsolatedAsyncioTestCase):
    async def run_record(self, row, item=ITEM, event=True, consumed=True, approval_id="case"):
        self.queries = []
        async def execute(query, params=()):
            self.queries.append((query, params))
            value, count = None, 1
            if query.startswith("SELECT user_token"):
                value = {"user_token": "employee", "fingerprint": "fp"}
            elif "SELECT s.id, t.scope_review" in query:
                value = {"scope_review": item}
            elif "SELECT * FROM approvals" in query:
                value = row
            elif "SELECT id FROM approval_events" in query:
                value = {"id": 1} if event else None
            elif "SELECT a.request_payload" in query:
                value = {"request_payload": row["request_payload"], "user_token": "employee",
                         "fingerprint": digest({"server": PAYLOAD["server_id"], "tool": PAYLOAD["tool"], "arguments": PAYLOAD["arguments"]})}
            elif query.startswith("UPDATE approvals"):
                count = int(consumed)
            return SimpleNamespace(fetchone=AsyncMock(return_value=value), rowcount=count)
        @asynccontextmanager
        async def transaction():
            yield SimpleNamespace(execute=AsyncMock(side_effect=execute))
        db = SimpleNamespace(transaction=transaction)
        mod = production("dispatch.py", {"record", "_Refused", "CATALOG_OK", "_INSERT", "REPLAY"},
                         {"db": db, "high_impact": impact, "Jsonb": lambda v: v, "canonical_hash": digest,
                          "IDEMPOTENCY_TTL_SECONDS": 86400})
        return await mod.record("request", "r", approval_id)

    async def test_no_approval_or_event_or_changed_scope_never_creates_intent(self):
        for row, item, event, aid in ((None, ITEM, True, None), (approval(), ITEM, False, "case"),
             (approval(), {**ITEM, "impact_domains": ["credit"]}, True, "case"),
             ({**approval(), "revoked_at": NOW}, ITEM, True, "case"), (approval("UNCONFIRMED"), ITEM, True, "case")):
            self.assertEqual(await self.run_record(row, item, event, approval_id=aid), "impact")
            self.assertFalse(any(q.startswith("INSERT INTO dispatch_intents") for q, _ in self.queries))

    async def test_single_use_and_revocation_share_approval_lock(self):
        self.assertIsNone(await self.run_record(approval()))
        self.assertTrue(any("FOR UPDATE" in q and "approvals" in q for q, _ in self.queries))
        self.assertTrue(any("FOR SHARE OF s, t" in q for q, _ in self.queries))
        self.assertTrue(any("revoked_at IS NULL" in q and "clock_timestamp()" in q for q, _ in self.queries))
        self.assertEqual(await self.run_record(approval(), consumed=False), "approval")

    async def test_unlabelled_call_retains_execution_without_approval(self):
        self.assertIsNone(await self.run_record(None, {}, approval_id=None))


@unittest.skipUnless(GATEWAY, "Gateway image: rerun with --gateway")
class GatewayChecks(unittest.IsolatedAsyncioTestCase):
    async def monitor_overlap(self, policy, *, consent_missing=False, approved=False):
        from app import endpoint_plane
        item = {**ITEM, **({"consent": True} if consent_missing else {})}
        cls = SimpleNamespace(action="r", base_action="r", data_class="public", destinations=[], resources=[],
            dlp=[], notes=[], restrictable=["max_chars"], primary=SimpleNamespace(id="asset", kind="file", owner_department=None),
            summary=lambda: "synthetic read")
        row = approval() if approved else None
        if row:
            row["request_payload"]["impact_scope_sha256"] = digest(impact.terms(item))
            row["request_fingerprint"] = digest(row["request_payload"])
            self.assertTrue(impact.bound(row, PAYLOAD, item, digest))
        async def fetch(query, params=()):
            if "principals" in query:
                return {"role": "employee", "status": "active", "synthetic": True}
            return row if "FROM approvals" in query else None
        connection = SimpleNamespace(execute=AsyncMock())
        @asynccontextmanager
        async def tx():
            yield connection
        async def record(event, laps):
            return {**event, "decision_id": 1}
        upstream_call = AsyncMock()
        missing = AsyncMock(return_value="유효한 사용자 동의가 없습니다." if consent_missing else None)
        changes = [(core.db, {"fetch_one": AsyncMock(side_effect=fetch), "transaction": tx}),
            (core.registry, {"server": Mock(return_value={"endpoint": "http://internal", "tool_reviews": {"update": item}}),
                             "allowed_principals": Mock(return_value=None), "catalog_version": Mock(return_value="test")}),
            (core.classify, {"classify": Mock(return_value=cls)}),
            (endpoint_plane, {"managed_failure": AsyncMock(return_value=None),
                              "shadow_count_for": AsyncMock(return_value=0), "shadow_listener_count_for": AsyncMock(return_value=0)}),
            (core.pac, {"build": AsyncMock(return_value={}), "digest": Mock(return_value="unit-digest")}),
            (core.consent, {"missing": missing}),
            (core.privacy, {"analyze": AsyncMock(return_value=[])}),
            (core.secret_scan, {"labels": AsyncMock(return_value=[])}),
            (core.review, {"record_event": AsyncMock()}),
            (core, {"policy_ledger": AsyncMock(), "_reserve_call": AsyncMock(return_value={}), "_privacy_ignore": Mock(return_value=None),
                    "_contract": AsyncMock(return_value={}), "_relationship_scope": AsyncMock(return_value={}),
                    "_sequence_flags": AsyncMock(return_value=[]), "_flow_sources": AsyncMock(return_value=[]),
                    "_policy": AsyncMock(return_value=deepcopy(policy)), "enforcement_mode": AsyncMock(return_value="monitor"),
                    "_decision_payload": AsyncMock(side_effect=record), "_call_upstream": upstream_call})]
        with ExitStack() as stack:
            for target, attributes in changes:
                for name, value in attributes.items():
                    stack.enter_context(patch.object(target, name, value))
            result = await core.execute_call(PAYLOAD, approval_granted=True, approval_id="case" if approved else "forged")
        upstream_call.assert_not_awaited()
        self.assertFalse(result["upstream_attempted"])
        self.assertFalse(result["upstream_executed"])
        return result, connection, missing

    async def test_monitor_high_impact_keeps_residency_prohibition(self):
        for approved in (False, True):
            for consent_missing in (False, True):
                with self.subTest(approved=approved, consent_missing=consent_missing):
                    result, connection, missing = await self.monitor_overlap(
                        {"decision": "Block", "policy_id": "P-RESIDENCY-001", "reason": "unit"},
                        approved=approved, consent_missing=consent_missing)
                    self.assertEqual((result["decision"], result["policy_id"]), ("Block", "P-RESIDENCY-001"))
                    self.assertIsNone(result["would_decision"])
                    connection.execute.assert_not_awaited()
                    missing.assert_not_awaited()

    async def test_monitor_high_impact_keeps_residency_approval_and_explanation_basis(self):
        for approved in (False, True):
            for consent_missing in (False, True):
                with self.subTest(approved=approved, consent_missing=consent_missing):
                    result, connection, missing = await self.monitor_overlap(
                        {"decision": "Approval", "policy_id": "P-RESIDENCY-002", "reason": "unit"},
                        approved=approved, consent_missing=consent_missing)
                    self.assertEqual((result["decision"], result["policy_id"]),
                        ("Approval", "P-RESIDENCY-002" if approved else "P-HIGH-IMPACT-001"))
                    self.assertIsNone(result["would_decision"])
                    explanation = connection.execute.await_args.args[1][-1].obj
                    self.assertEqual(explanation["basis_policy_id"], "P-RESIDENCY-002")
                    missing.assert_not_awaited()

    async def test_monitor_high_impact_missing_consent_blocks_even_after_human_approval(self):
        for approved in (False, True):
            for decision in ("Allow", "Alert", "Restrict", "Block"):
                with self.subTest(approved=approved, decision=decision):
                    result, connection, missing = await self.monitor_overlap(
                        {"decision": decision, "policy_id": "P-AUTHZ-ALLOW-001", "reason": "unit"},
                        consent_missing=True, approved=approved)
                    self.assertEqual((result["decision"], result["policy_id"]), ("Block", "P-CONSENT-001"))
                    missing.assert_awaited_once()
                    connection.execute.assert_not_awaited()

    async def test_monitor_residency_conflict_cannot_be_relaxed_by_selected_policy(self):
        for policy_id, decision in (("P-RESIDENCY-001", "Block"), ("P-RESIDENCY-002", "Approval")):
            with self.subTest(policy_id=policy_id):
                result, _, _ = await self.monitor_overlap({"decision": "Approval", "policy_id": "P-X-APPROVAL-001",
                    "reason": "unit", "conflicts": [{"decision": decision, "policy_id": policy_id}]})
                self.assertEqual((result["decision"], result["policy_id"]), ("Approval", "P-HIGH-IMPACT-001"))
                self.assertIsNone(result["would_decision"])

    async def test_final_guard_refuses_before_connection(self):
        for row, aid in ((None, None), (None, "forged"), (approval("EXECUTED"), "case"),
                         ({**approval(), "revoked_at": NOW}, "case"),
                         ({**approval(), "expires_at": NOW - timedelta(seconds=1)}, "case")):
            with patch.object(core.registry, "server", return_value={"tool_reviews": {"update": ITEM}}), \
                 patch.object(core.db, "fetch_one", AsyncMock(return_value=row)), \
                 patch.object(core.upstream, "session", Mock()) as connect:
                with self.assertRaises(core.DispatchRejected) as caught:
                    await core._call_upstream("existing-oss", "update", PAYLOAD["arguments"], aid, "employee",
                                              dispatch_state={}, pac_payload=PAYLOAD)
                self.assertEqual(caught.exception.verdict["policy_id"], "P-HIGH-IMPACT-001")
                connect.assert_not_called()

    async def test_request_model_validates_label(self):
        self.assertTrue(agent_contract.ToolReview(purpose="업무 목적", asset="자료", high_impact=True,
                                                 impact_domains=["credit"]).high_impact)
        for fields in ({"high_impact": True}, {"high_impact": "false"}, {"impact_domains": ["credit"]}):
            with self.assertRaises(ValueError):
                agent_contract.ToolReview(purpose="업무 목적", asset="자료", **fields)

    async def test_allow_alert_restrict_and_monitor_all_wait_before_upstream(self):
        from app import endpoint_plane
        for mode in ("enforce", "monitor"):
            for verdict in ("Allow", "Alert", "Restrict", "Block"):
                with self.subTest(mode=mode, verdict=verdict):
                    cls = SimpleNamespace(action="r", base_action="r", data_class="public", destinations=[], resources=[],
                        dlp=[], notes=[], restrictable=["max_chars"], primary=SimpleNamespace(id="asset", kind="file", owner_department=None),
                        summary=lambda: "synthetic read")
                    row = {"role": "employee", "status": "active", "synthetic": True}
                    async def fetch(query, params=()):
                        return row if "principals" in query else None
                    @asynccontextmanager
                    async def tx():
                        yield SimpleNamespace(execute=AsyncMock())
                    async def record(e, laps):
                        return {**e, "decision_id": 1}
                    policy = {"decision": verdict, "policy_id": "P-AUTHZ-ALLOW-001" if verdict != "Block" else "MCP-CATALOG-001",
                              "restrictions": {"max_chars": 100} if verdict == "Restrict" else {}, "reason": "unit"}
                    changes = [(core.db, {"fetch_one": AsyncMock(side_effect=fetch), "transaction": tx}),
                        (core.registry, {"server": Mock(return_value={"endpoint": "http://internal", "tool_reviews": {"update": ITEM}}),
                                         "allowed_principals": Mock(return_value=None), "catalog_version": Mock(return_value="test")}),
                        (core.classify, {"classify": Mock(return_value=cls)}),
                        (endpoint_plane, {"managed_failure": AsyncMock(return_value=None),
                                          "shadow_count_for": AsyncMock(return_value=0), "shadow_listener_count_for": AsyncMock(return_value=0)}),
                        (core.pac, {"build": AsyncMock(return_value={}), "digest": Mock(return_value="unit-digest")}),
                        (core.privacy, {"analyze": AsyncMock(return_value=[])}),
                        (core.secret_scan, {"labels": AsyncMock(return_value=[])}),
                        (core, {"policy_ledger": AsyncMock(), "_reserve_call": AsyncMock(return_value={}), "_privacy_ignore": Mock(return_value=None),
                                "_contract": AsyncMock(return_value={}), "_relationship_scope": AsyncMock(return_value={}),
                                "_sequence_flags": AsyncMock(return_value=[]), "_flow_sources": AsyncMock(return_value=[]),
                                "_policy": AsyncMock(return_value=policy), "enforcement_mode": AsyncMock(return_value=mode),
                                "_decision_payload": AsyncMock(side_effect=record), "_call_upstream": AsyncMock()})]
                    with ExitStack() as stack:
                        for target, attributes in changes:
                            for name, value in attributes.items():
                                stack.enter_context(patch.object(target, name, value))
                        result = await core.execute_call(PAYLOAD, approval_granted=True, approval_id="forged")
                    self.assertEqual((result["decision"], result["policy_id"]),
                        ("Block", "MCP-CATALOG-001") if verdict == "Block" else ("Approval", "P-HIGH-IMPACT-001"))
                    changes[-1][1]["_call_upstream"].assert_not_awaited()


if __name__ == "__main__":
    unittest.main(verbosity=2)
