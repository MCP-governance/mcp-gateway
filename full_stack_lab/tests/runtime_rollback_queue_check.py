"""DEV-78: the success path of the rollback (queueing the prior image, restoring the contract bytes), the run_job
branch that carries the prior evidence forward, and the refusals that must not loop or go unrecorded.

runtime_rollback_check.py pins the pieces and runtime_rollback_reconcile_check.py the refusals; this file drives what
those could not while runtime/worker.py lacked `import uuid` and the rollback branch of run_job read a key it had
never set (D-180 defects 1-3, 5, 6, docs/ai analysis runtime-rollback/defects-1021.md). Nothing here injects anything
into the worker. No database, container engine or network is involved; the request tests need the gateway's own
dependencies and are skipped without them.
"""
import copy
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import runtime_rollback_reconcile_check as base
from runtime_rollback_reconcile_check import (  # noqa: F401
    API, CURRENT, INTAKE, PRIOR, PRIOR_EVIDENCE, Cursor, Harness, Ledger, ApiLedger, hashlib,
    normalised, tool_bytes, worker)

if API:
    from runtime_rollback_reconcile_check import HTTPException, agent_service


class RollbackQueue(Harness):
    def test_requested_rollback_queues_the_prior_image_without_fetch_build_or_verification(self):
        ledger = Ledger()
        self.run_reconcile(ledger)
        self.assertEqual(self.calls, [])
        self.assertEqual(ledger.row(2)["status"], "STOPPED")
        queued = ledger.row(3)
        self.assertEqual(queued["status"], "QUEUED")
        self.assertEqual(queued["image_id"], ledger.row(1)["image_id"])
        self.assertEqual((queued["recipe_id"], queued["recipe_sha256"], queued["source_commit"]),
                         ("markitdown-mcp", "9" * 64, "c" * 40))
        self.assertEqual(queued["rollback_target_generation"], 1)
        self.assertEqual(queued["rollback_contract"], PRIOR)
        self.assertEqual(queued["requested_by"], "admin-1")

    def test_contract_hash_after_rollback_equals_the_prior_approval_byte_for_byte(self):
        ledger = Ledger()
        self.assertNotEqual(worker.approved_contract(ledger, INTAKE)["sha256"], PRIOR["sha256"])
        self.run_reconcile(ledger)
        self.assertEqual(tool_bytes(ledger.tools), tool_bytes(PRIOR["tools"]))
        self.assertEqual(hashlib.sha256(tool_bytes(ledger.tools)).hexdigest(), PRIOR["sha256"])
        self.assertEqual(worker.approved_contract(ledger, INTAKE)["sha256"], PRIOR["sha256"])
        self.assertEqual(ledger.tools["convert"]["approved_output_schema_hash"],
                         PRIOR["tools"]["convert"]["approved_output_schema_hash"])

    def test_transition_order_and_ledger_history(self):
        ledger = Ledger()
        self.run_reconcile(ledger)
        # stopped first, then the contract, then the queue row; the whole switch is committed together.
        self.assertEqual([s for s in ledger.steps if not s.startswith("event:")],
                         ["stopped", "contract-restored", "queued", "commit"])
        self.assertEqual(ledger.steps[-1], "commit")
        self.assertEqual([k for k in ledger.kinds() if k.startswith("runtime-") and k != "runtime-active"],
                         ["runtime-stopped", "runtime-rollback-queued"])
        stopped, queued = ledger.events[-2:]
        self.assertEqual((stopped["outcome"], stopped["scope"]["generation"]), ("recorded", 2))
        self.assertEqual(queued["outcome"], "recorded")
        self.assertEqual(queued["actor"], worker.WORKER_ID)
        self.assertEqual(queued["target_id"], str(INTAKE))
        self.assertEqual({k: v for k, v in queued["scope"].items() if k != "runtime"},
                         {"generation": 3, "from_generation": 2, "to_generation": 1,
                          "contract_sha256": PRIOR["sha256"]})
        # nothing was written to the earlier events (append-only: the history only grew).
        self.assertEqual(ledger.events[0]["scope"]["contract"], PRIOR)
        self.assertEqual(ledger.events[1]["scope"]["contract"], CURRENT)

    def test_queued_generation_inherits_the_stored_snapshot_when_it_becomes_active(self):
        ledger = Ledger()
        self.run_reconcile(ledger)
        ledger.tools["convert"]["approved_description_hash"] = "0" * 64   # drift after the restore
        worker.event(ledger, ledger.row(3), "runtime-active")
        active = ledger.events[-1]
        self.assertEqual(active["kind"], "runtime-active")
        self.assertEqual(active["scope"]["generation"], 3)
        self.assertEqual(active["scope"]["contract"], PRIOR, "the snapshot is re-recorded as it was, not re-read")

    def test_revocation_marker_of_another_generation_does_not_block(self):
        ledger = Ledger()
        ledger.add_event("runtime-revoked", {"generation": 2})
        self.run_reconcile(ledger)
        self.assertEqual(ledger.row(3)["status"], "QUEUED")

    def test_queued_event_names_the_new_generation_row_not_the_stopped_one(self):
        ledger = Ledger()
        self.run_reconcile(ledger)
        queued = ledger.events[-1]
        self.assertEqual(queued["kind"], "runtime-rollback-queued")
        self.assertEqual(queued["scope"]["generation"], 3)
        self.assertEqual(queued["scope"]["runtime"], str(ledger.row(3)["id"]))
        self.assertNotEqual(queued["scope"]["runtime"], str(ledger.row(2)["id"]))


class MarkingLedger(Ledger):
    """Ledger that also applies the refusal marker the worker writes onto a generation it stops."""

    def execute(self, query, params=()):
        q = normalised(query)
        if q.startswith("UPDATE mcp_runtimes SET status='STOPPING'"):
            reason, runtime_id = params
            target = next(r for r in self.runtimes if r["id"] == runtime_id and r["status"] == "ACTIVE")
            marker = {"stop_refused": True} if "stop_refused" in q else {}
            target.update(status="STOPPING", error=reason, evidence={**target["evidence"], **marker})
            self.steps.append("stopping")
            return Cursor()
        return super().execute(query, params)


def active_rollback_ledger(**evidence):
    """Generation 3 is ACTIVE as a rollback to generation 1; generation 2 was stopped by the first rollback."""
    ledger = MarkingLedger(state="STOPPED")
    ledger.tools = copy.deepcopy(PRIOR["tools"])
    third = ledger.runtime(3, "ACTIVE", "1", evidence={**PRIOR_EVIDENCE, "answered": {"tools": 1}, **evidence})
    third.update(image_id=ledger.row(1)["image_id"], rollback_target_generation=1,
                 rollback_contract=copy.deepcopy(PRIOR))
    ledger.runtimes.append(third)
    ledger.add_event("runtime-active", {"generation": 3, "contract": copy.deepcopy(PRIOR)})
    return ledger


class RollbackGenerationStops(Harness):
    def container_gone(self, ledger):
        real = worker.reconcile

        def reconcile(*args):
            with mock.patch.object(worker, "inspect", lambda *_a: None):
                real(*args)
        with mock.patch.object(worker, "reconcile", reconcile):
            self.run_reconcile(ledger, verify=lambda *_a, **_k: {})

    def test_rollback_generation_stopped_by_failed_source_verification_is_not_queued_again(self):
        ledger = active_rollback_ledger(source_verification_error="bad")   # MCP-SUPPLY-001 on the inherited evidence
        self.run_reconcile(ledger, verify=False)
        self.assertEqual(self.calls, [])
        self.assertEqual(ledger.row(3)["status"], "STOPPED")
        self.assertIn("MCP-SUPPLY-001", ledger.row(3)["error"])
        self.assertEqual(len(ledger.runtimes), 3, "no fourth generation")
        self.assertNotIn("runtime-rollback-queued", ledger.kinds())
        self.assertNotIn("queued", ledger.steps)
        self.assertNotIn("contract-restored", ledger.steps)
        self.assertEqual(ledger.steps[-1], "commit")

    def test_the_halt_is_written_to_the_ledger_with_the_reason(self):
        ledger = active_rollback_ledger(source_verification_error="bad")
        self.run_reconcile(ledger, verify=False)
        halts = [e for e in ledger.events if e["kind"] == "runtime-rollback-refused"]
        self.assertEqual(len(halts), 1)
        halt = halts[0]
        self.assertEqual((halt["outcome"], halt["actor"], halt["target_id"]), ("refused", worker.WORKER_ID, str(INTAKE)))
        self.assertEqual((halt["scope"]["generation"], halt["scope"]["runtime"]), (3, str(ledger.row(3)["id"])))
        self.assertIn("다시 큐잉하지 않습니다", halt["reason"])
        self.assertIn("MCP-SUPPLY-001", halt["reason"])

    def test_every_refusal_of_a_running_rollback_generation_halts_instead_of_queueing(self):
        causes = {"revoked": lambda l: l.add_event("runtime-revoked", {"generation": 1}),
                  "server blocked": lambda l: l.server.update(status="BLOCKED_SUPPLY_CHAIN"),
                  "suspended": lambda l: setattr(l, "suspended", True)}
        for name, change in causes.items():
            with self.subTest(name):
                ledger = active_rollback_ledger()
                change(ledger)
                self.run_reconcile(ledger, verify=lambda *_a, **_k: {})
                self.assertEqual(ledger.row(3)["status"], "STOPPED")
                self.assertEqual(len(ledger.runtimes), 3)
                self.assertNotIn("runtime-rollback-queued", ledger.kinds())
                self.assertEqual(ledger.kinds().count("runtime-rollback-refused"), 1)

    def test_a_vanished_container_is_an_interruption_and_still_recovers_by_queueing_again(self):
        ledger = active_rollback_ledger()
        self.container_gone(ledger)
        self.assertEqual(ledger.row(3)["status"], "STOPPED")
        queued = ledger.row(4)
        self.assertEqual((queued["status"], queued["rollback_target_generation"]), ("QUEUED", 1))
        self.assertEqual(queued["image_id"], ledger.row(1)["image_id"])
        self.assertNotIn("runtime-rollback-refused", ledger.kinds())
        self.assertEqual(ledger.events[-1]["scope"]["runtime"], str(queued["id"]))

    def test_the_generation_that_carried_the_admin_request_is_queued_not_halted(self):
        ledger = MarkingLedger()      # generation 2 was stopped by the request itself, no refusal marker
        self.run_reconcile(ledger)
        self.assertEqual(ledger.row(3)["status"], "QUEUED")
        self.assertNotIn("runtime-rollback-refused", ledger.kinds())


class RunJobRollbackBranch(unittest.TestCase):
    """run_job for a rolled-back generation, with the engine, the approval check and the ledger replaced."""

    def run_job(self, target_evidence):
        ledger = Ledger(state="STOPPED")
        job = ledger.runtime(3, "BUILDING", "1")
        job.update(image_id=ledger.row(1)["image_id"], rollback_target_generation=1, rollback_contract=copy.deepcopy(PRIOR))
        self.advanced, self.events, self.calls = [], [], []

        class Connection:
            def execute(_self, query, params=()):
                assert normalised(query).startswith("SELECT image_id,evidence FROM mcp_runtimes"), query
                return Cursor([{"image_id": job["image_id"], "evidence": target_evidence}])

            def commit(_self):
                self.calls.append("commit")

            def rollback(_self):
                self.calls.append("rollback")

        def advance(_connection, runtime, expected, status, *, commit=True, **fields):
            self.advanced.append((expected, status, fields))
            return {**runtime, "status": status, **{k: v for k, v in fields.items() if k != "evidence"}}

        def forbidden(name):
            def call(*_a, **_k):
                self.calls.append(name)
                raise AssertionError(name + " must not run in the rollback branch")
            return call
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder, True)
        patches = [mock.patch.object(worker, "WORK_DIR", Path(folder)),
                   mock.patch.object(worker, "approval_problem", lambda *_a, **_k: None),
                   mock.patch.object(worker, "inspect", lambda *_a: {"Id": job["image_id"]}),
                   mock.patch.object(worker, "advance", advance),
                   mock.patch.object(worker, "event", lambda _c, _r, kind, outcome="recorded", reason=None, scope=None:
                                     self.events.append({"kind": kind, "outcome": outcome, "reason": reason, "scope": scope})),
                   mock.patch.object(worker, "start", lambda *_a: self.calls.append("start")),
                   mock.patch.object(worker, "answers", lambda *_a: {"protocol_version": "2025-11-25", "server": "x"}),
                   mock.patch.object(worker, "remove_runtime_resources", lambda *_a: 0),
                   mock.patch.object(worker, "log", lambda *_a: None),
                   mock.patch.object(worker, "endpoint", lambda *_a: "http://x"),
                   mock.patch.object(worker, "fetch_source", forbidden("fetch_source")),
                   mock.patch.object(worker, "build", forbidden("build")),
                   mock.patch.object(worker, "verify_source_provenance", forbidden("verify_source_provenance"))]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        worker.run_job(Connection(), job, {"repo": {"id": "markitdown-mcp", "sha256": "9" * 64, "port": 8000, "path": "/mcp"}},
                       {"gateways": []})

    def test_rolled_back_generation_reaches_active_on_the_evidence_of_the_approved_one(self):
        self.run_job(copy.deepcopy(PRIOR_EVIDENCE))
        self.assertEqual([(a, b) for a, b, _ in self.advanced],
                         [("BUILDING", "STARTING"), ("STARTING", "VERIFYING"), ("VERIFYING", "ACTIVE")])
        starting = self.advanced[0][2]
        self.assertEqual(starting["source_archive_sha256"], PRIOR_EVIDENCE["source_archive_sha256"])
        self.assertEqual(starting["evidence"]["source_attestation"], PRIOR_EVIDENCE["source_attestation"])
        self.assertEqual(starting["evidence"]["provenance_verification"], PRIOR_EVIDENCE["provenance_verification"])
        built = next(e for e in self.events if e["kind"] == "runtime-built")
        self.assertEqual(built["scope"], {k: PRIOR_EVIDENCE[k] for k in (
            "source_archive_sha256", "image_id", "packages_sha256", "base_image", "build_seconds")})
        self.assertIn("runtime-active", [e["kind"] for e in self.events])

    def test_a_prior_approval_without_a_source_fingerprint_is_refused_not_run(self):
        evidence = copy.deepcopy(PRIOR_EVIDENCE)
        del evidence["source_archive_sha256"]
        self.run_job(evidence)
        self.assertEqual([(a, b) for a, b, _ in self.advanced], [("BUILDING", "FAILED")])
        self.assertIn("소스 지문", self.advanced[0][2]["error"])
        self.assertNotIn("start", self.calls)
        self.assertNotIn("runtime-built", [e["kind"] for e in self.events])
        self.assertIn("runtime-failed", [e["kind"] for e in self.events])

    def test_a_blank_source_fingerprint_is_refused_too(self):
        self.run_job({**PRIOR_EVIDENCE, "source_archive_sha256": ""})
        self.assertEqual([(a, b) for a, b, _ in self.advanced], [("BUILDING", "FAILED")])

    def test_missing_evidence_keys_are_named_in_the_event_instead_of_failing_on_them(self):
        evidence = copy.deepcopy(PRIOR_EVIDENCE)
        del evidence["packages_sha256"], evidence["build_seconds"]
        self.run_job(evidence)
        self.assertEqual(self.advanced[-1][1], "ACTIVE")
        built = next(e for e in self.events if e["kind"] == "runtime-built")
        self.assertEqual(built["scope"]["missing"], ["packages_sha256", "build_seconds"])
        self.assertNotIn("packages_sha256", built["scope"])
        self.assertEqual(built["scope"]["source_archive_sha256"], PRIOR_EVIDENCE["source_archive_sha256"])


@unittest.skipUnless(API, "needs the gateway's own dependencies (fastapi, a real psycopg)")
class RequestRefusalIsRecorded(unittest.TestCase):
    ADMIN = base.RollbackRequest.ADMIN
    call = base.RollbackRequest.call

    def refusal(self, ledger, generation=1):
        before = copy.deepcopy(ledger.events)
        with self.assertRaises(HTTPException) as caught:
            self.call(ledger, generation=generation)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(ledger.runtimes[2]["status"], "ACTIVE", "the refused request changed nothing")
        self.assertEqual(ledger.marked, {})
        self.assertEqual(ledger.events[:len(before)], before, "append-only: earlier history is unchanged")
        added = ledger.events[len(before):]
        self.assertEqual(len(added), 1)
        record = added[0]
        self.assertEqual((record["kind"], record["outcome"], record["target_kind"], record["target_id"], record["actor"]),
                         ("runtime-rollback-request-refused", "refused", "intake", str(INTAKE), "admin-principal"))
        self.assertEqual(record["reason"], caught.exception.detail)
        self.assertEqual(record["scope"], {"to_generation": generation, "note": "새 판본 장애로 되돌립니다"})
        self.assertNotEqual(record["kind"], "runtime-rollback-refused", "told apart from the worker's refusal")
        self.assertNotIn("runtime-rollback", [e["kind"] for e in ledger.events])
        return record

    def test_each_kind_of_refusal_leaves_who_why_and_which_version(self):
        def revoked(l):
            l.events.append({"kind": "runtime-revoked", "scope": {"generation": 1}})

        def history_gone(l):
            l.events.pop(0)
        cases = {"server withdrawn": lambda l: l.server.update(status="DISABLED"),
                 "relationship ended": lambda l: setattr(l, "stopped_server", True),
                 "revoked version": revoked, "no approval history": history_gone,
                 "image gone": lambda l: l.runtimes[1].update(image_id=None),
                 "tool set changed": lambda l: l.tools.update(extra=base.tool("p", "1.0"))}
        reasons = set()
        for name, change in cases.items():
            with self.subTest(name):
                ledger = ApiLedger()
                change(ledger)
                reasons.add(self.refusal(ledger)["reason"])
        self.assertGreater(len(reasons), 3, "each cause is recorded with its own reason")

    def test_the_version_asked_for_is_the_one_recorded(self):
        ledger = ApiLedger()
        record = self.refusal(ledger, generation=2)       # the running generation itself
        self.assertEqual(record["scope"]["to_generation"], 2)

    def test_a_denied_or_malformed_request_is_not_a_refused_rollback_and_a_good_one_leaves_no_refusal(self):
        ledger = ApiLedger()
        with self.assertRaises(HTTPException):
            self.call(ledger, user={"roles": ["employee"], "principal": "e-1"})
        with self.assertRaises(HTTPException):
            self.call(ledger, note="첫 줄\n둘째 줄")
        self.assertEqual(ledger.statements, [])
        self.call(ledger)
        self.assertNotIn("runtime-rollback-request-refused", [e["kind"] for e in ledger.events])
        self.assertIn("runtime-rollback", [e["kind"] for e in ledger.events])

    def test_request_code_only_adds_to_the_ledger(self):
        source = Path(agent_service.__file__).read_text(encoding="utf-8")
        start = source.index("async def rollback_runtime")
        end = source.index('@app.get("/api/mcp-requests/{request_id}/report")')
        block = re.sub(r"\s+", " ", source[start:end]).upper()
        self.assertNotRegex(block, r"(UPDATE|DELETE FROM|TRUNCATE) APPROVAL_EVENTS")


if __name__ == "__main__":
    unittest.main()
