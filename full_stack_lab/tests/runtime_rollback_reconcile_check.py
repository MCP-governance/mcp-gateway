"""DEV-78: the rollback branch of the runtime worker's reconcile and the gateway's rollback request, with in-memory ledgers.

runtime_rollback_check.py pins the pieces (restore_contract, approval_problem, event). This file drives the
branches around them: the request that marks the ACTIVE generation STOPPING and records who asked, the worker's
refusal of every unsafe target (each refusal must leave an event and change nothing), the rolled-back generation
being judged on the evidence it inherited, and the run_job branch that must not fetch, build or verify again.
The success path of reconcile (queueing the prior image as a new generation and restoring the contract bytes) is
not here: it does not run today because runtime/worker.py never imports uuid (see the DEV-78 section of the
2026-10-21 criteria audit). No database, container engine or network is involved; the request tests need the
gateway's own dependencies and are skipped without them.
"""
import ast
import copy
import datetime
import hashlib
import importlib
import json
import sys
import types
import unittest
import uuid
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "supply_chain"), str(ROOT / "runtime"), str(ROOT / "gateway" / "app")]
# The workstation may have Python 3.10; the worker image uses 3.12. These checks do not parse recipes.
try:
    importlib.import_module("tomllib")
except ModuleNotFoundError:
    sys.modules["tomllib"] = types.SimpleNamespace(loads=lambda _text: {})
if not hasattr(datetime, "UTC"):
    datetime.UTC = datetime.timezone.utc
try:
    import psycopg  # noqa: F401
except ImportError:
    psycopg = types.ModuleType("psycopg")
    psycopg.Error = Exception
    psycopg.connect = lambda *_args, **_kwargs: None
    rows_module = types.ModuleType("psycopg.rows")
    rows_module.dict_row = object()
    json_types = types.ModuleType("psycopg.types.json")

    class Jsonb:
        def __init__(self, obj, **_kwargs):
            self.obj = obj
    json_types.Jsonb = Jsonb
    sys.modules.update({"psycopg": psycopg, "psycopg.rows": rows_module,
                        "psycopg.types": types.ModuleType("psycopg.types"), "psycopg.types.json": json_types})
try:
    importlib.import_module("image_scan")
except ImportError:
    sys.modules["image_scan"] = types.SimpleNamespace(rescan=lambda *_args: None)
import worker  # noqa: E402

# The request side lives in the gateway; it needs the gateway's own dependencies (fastapi, a real psycopg).
sys.path.append(str(ROOT / "gateway"))
import asyncio  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402
try:
    if not hasattr(psycopg, "__version__"):
        raise ImportError("psycopg is the local stand-in")
    from fastapi import HTTPException
    from app import agent_service
    API = True
except ImportError:
    API = False

INTAKE = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
SERVER_ID = "markitdown"


def contract(tools: dict) -> dict:
    encoded = json.dumps(tools, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {"server_id": SERVER_ID, "tools": tools, "sha256": hashlib.sha256(encoded).hexdigest(),
            "approved_by": "admin-1", "approved_at": "2026-10-20T01:00:00Z"}


def tool(letter: str, version: str) -> dict:
    return {"approved_description_hash": letter * 64, "approved_schema_hash": chr(ord(letter) + 1) * 64,
            "approved_output_schema_hash": chr(ord(letter) + 2) * 64, "approved_server_version": version}


PRIOR = contract({"convert": tool("a", "1.0")})      # what generation 1 ran under
CURRENT = contract({"convert": tool("d", "1.1")})    # what generation 2 (the one being rolled back) runs under
PRIOR_EVIDENCE = {"source_archive_sha256": "5" * 64, "source_attestation": {"signatures": [{"keyid": "release-key"}]},
                  "files": 12, "image_id": "sha256:" + "1" * 64, "packages_sha256": "6" * 64,
                  "base_image": "python@sha256:" + "7" * 64, "build_seconds": 31,
                  "provenance_verification": {"status": "검증됨", "keyid": "release-key", "sha256": "5" * 64}}


def normalised(query: str) -> str:
    return " ".join(query.split())


class Cursor:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class Ledger:
    """The rows reconcile reads and writes, with the same answers the SQL gives. An unknown statement fails the test."""

    def __init__(self, state: str = "STOPPING"):
        self.server = {"id": SERVER_ID, "status": "READY", "lifecycle": "OPERATING"}
        self.suspended = False
        self.relationship_ended = False
        self.registered = True
        self.tools = copy.deepcopy(CURRENT["tools"])
        self.events = []
        self.steps = []
        self.runtimes = [
            self.runtime(1, "STOPPED", "1", evidence=PRIOR_EVIDENCE),
            self.runtime(2, state, "2", evidence={**PRIOR_EVIDENCE, "source_archive_sha256": "8" * 64}),
        ]
        if state == "STOPPING":
            self.runtimes[1].update(rollback_target_generation=1, rollback_contract=copy.deepcopy(PRIOR),
                                    error="관리자가 승인 판본 되돌리기를 요청했습니다.")
        self.add_event("runtime-active", {"generation": 1, "contract": copy.deepcopy(PRIOR)})
        self.add_event("runtime-active", {"generation": 2, "contract": copy.deepcopy(CURRENT)})

    @staticmethod
    def runtime(generation: int, status: str, digit: str, evidence=None) -> dict:
        return {"id": uuid.UUID(int=generation), "intake_id": INTAKE, "generation": generation, "status": status,
                "recipe_id": "markitdown-mcp", "recipe_sha256": "9" * 64, "source_commit": "c" * 40,
                "image_id": "sha256:" + digest(digit), "requested_by": "admin-1", "attempts": 1,
                "evidence": evidence or {}, "error": None, "rollback_target_generation": None,
                "rollback_contract": None}

    def add_event(self, kind, scope, outcome="recorded", reason=None, actor="runtime-worker-1"):
        self.events.append({"id": len(self.events) + 1, "kind": kind, "outcome": outcome, "reason": reason,
                            "actor": actor, "target_id": str(INTAKE), "scope": scope})

    def kinds(self):
        return [event["kind"] for event in self.events]

    def row(self, generation):
        return next((r for r in self.runtimes if r["generation"] == generation), None)

    def commit(self):
        self.steps.append("commit")

    def rollback(self):
        self.steps.append("rollback")

    def marker(self, generation):
        return next((e for e in self.events if e["kind"] in worker_markers and
                     str(e["scope"].get("generation")) == str(generation)), None)

    def execute(self, query, params=()):
        q = normalised(query)
        if q.startswith("SELECT * FROM mcp_runtimes WHERE status IN ('ACTIVE','STOPPING')"):
            return Cursor(copy.deepcopy([r for r in self.runtimes if r["status"] in ("ACTIVE", "STOPPING")]))
        if "FROM mcp_intake_requests r LEFT JOIN mcp_servers s" in q:
            return Cursor([{"status": "APPROVED", "intake_kind": "repository", "commit_sha": "c" * 40,
                            "repository_url": "repo", "lifecycle": self.server["lifecycle"],
                            "server_status": self.server["status"], "server_id": SERVER_ID,
                            "suspended": self.suspended, "relationship_ended": self.relationship_ended}])
        if "FROM mcp_runtimes r WHERE r.intake_id" in q:
            target = self.row(params[2])
            if not target:
                return Cursor()
            return Cursor([{**{k: target[k] for k in ("image_id", "source_commit", "recipe_id", "recipe_sha256",
                                                      "status")}, "contract": self.approved(params[2])}])
        if q.startswith("SELECT 1 FROM approval_events WHERE target_kind='intake'") and "'runtime-revoked'" in q:
            return Cursor([{"1": 1}] if self.marker(params[1]) else [])
        if q.startswith("SELECT scope->'contract' AS contract FROM approval_events"):
            history = [e for e in self.events if e["kind"] == "runtime-active" and str(e["scope"].get("generation")) == params[1]]
            return Cursor([{"contract": history[-1]["scope"].get("contract")}] if history else [])
        if q.startswith("UPDATE mcp_runtimes SET status='STOPPING'"):
            reason, runtime_id = params
            target = next(r for r in self.runtimes if r["id"] == runtime_id and r["status"] == "ACTIVE")
            target.update(status="STOPPING", error=reason)
            self.steps.append("stopping")
            return Cursor()
        if "SET status='STOPPED'" in q:
            target = next((r for r in self.runtimes if r["id"] == params[1] and r["status"] == "STOPPING"), None)
            if not target:
                return Cursor()
            target.update(status="STOPPED", evidence={**target["evidence"], **params[0].obj})
            self.steps.append("stopped")
            return Cursor([copy.deepcopy(target)])
        if q.startswith("INSERT INTO approval_events"):
            kind, outcome, target_id, actor, reason, scope = params
            self.events.append({"id": len(self.events) + 1, "kind": kind, "outcome": outcome, "reason": reason,
                                "actor": actor, "target_id": target_id, "scope": scope.obj})
            self.steps.append("event:" + kind)
            return Cursor()
        if q.startswith("SELECT * FROM mcp_runtimes WHERE intake_id"):
            target = self.row(params[1])
            return Cursor([copy.deepcopy(target)] if target else [])
        if "FROM mcp_intake_requests i JOIN mcp_servers s" in q:
            if not self.registered:
                return Cursor()
            return Cursor([{**self.server, "suspended": self.suspended, "relationship_ended": self.relationship_ended}])
        if q.startswith("SELECT name FROM mcp_tools"):
            return Cursor([{"name": name} for name in self.tools])
        if q.startswith("UPDATE mcp_tools"):
            description, schema, output, version, _server, name = params
            self.tools[name] = {"approved_description_hash": description, "approved_schema_hash": schema,
                                "approved_output_schema_hash": output, "approved_server_version": version}
            self.steps.append("contract-restored")
            return Cursor()
        if q.startswith("INSERT INTO mcp_runtimes"):
            (new_id, intake, recipe_id, recipe_sha, commit, requested_by, image_id, target_generation,
             snapshot, _intake) = params
            new = self.runtime(max(r["generation"] for r in self.runtimes) + 1, "QUEUED", "0")
            new.update(id=new_id, intake_id=intake, recipe_id=recipe_id, recipe_sha256=recipe_sha,
                       source_commit=commit, requested_by=requested_by, image_id=image_id, attempts=0,
                       rollback_target_generation=target_generation, rollback_contract=snapshot.obj)
            self.runtimes.append(new)
            self.steps.append("queued")
            return Cursor([{"id": new["id"], "generation": new["generation"]}])
        if q.startswith("SELECT registered_server_id FROM mcp_intake_requests"):
            return Cursor([{"registered_server_id": SERVER_ID}])
        if "FROM mcp_tools WHERE server_id=%s ORDER BY name" in q:
            return Cursor([{"name": name, **self.tools[name]} for name in sorted(self.tools)])
        if "FROM approval_events WHERE target_kind='server'" in q:
            return Cursor([{"actor": "admin-1", "created_at": "2026-10-20T01:00:00Z"}])
        raise AssertionError("unexpected statement: " + q[:120])

    def approved(self, generation):
        history = [e for e in self.events if e["kind"] == "runtime-active"
                   and e["scope"].get("generation") == generation and e["scope"].get("contract") is not None]
        return history[-1]["scope"]["contract"] if history else None


worker_markers = ("runtime-revoked", "runtime-terminated", "runtime-supply-chain-stop")


def digest(digit: str) -> str:
    return digit * 64


def tool_bytes(tools: dict) -> bytes:
    return json.dumps(tools, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


class Harness(unittest.TestCase):
    """Runs reconcile with the container engine out of the picture and records anything that would build or fetch."""

    def run_reconcile(self, ledger, verify=None):
        self.calls = []

        def forbidden(name):
            def call(*_args, **_kwargs):
                self.calls.append(name)
                raise AssertionError(name + " must not run in the rollback branch")
            return call
        patches = [mock.patch.object(worker, name, forbidden(name)) for name in ("fetch_source", "build", "start")]
        patches += [
            mock.patch.object(worker, "remove_runtime_resources", lambda *_a: 0),
            mock.patch.object(worker, "inspect", lambda kind, name: {"Image": self.image_of(ledger, name)}),
            mock.patch.object(worker, "attach", lambda *_a: None),
            mock.patch.object(worker, "sync_egress", lambda *_a: None),
            mock.patch.object(worker, "log", lambda *_a: None),
            mock.patch.object(worker.image_scan, "rescan", lambda *_a: None),
        ]
        if verify is not False:
            patches.append(mock.patch.object(worker, "verify_source_provenance",
                                             verify or forbidden("verify_source_provenance")))
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        worker.reconcile(ledger, {"repo": {"id": "markitdown-mcp", "sha256": "9" * 64}}, {"gateways": ["gateway"]})

    @staticmethod
    def image_of(ledger, name):
        return next((r["image_id"] for r in ledger.runtimes if worker.names(r)["container"] == name), None)


class RollbackRefusal(Harness):
    """Each case stops the current generation (fail closed) and records why nothing was queued."""

    def refused(self, ledger, reason_part=None):
        before = copy.deepcopy(ledger.tools)
        self.run_reconcile(ledger)
        self.assertEqual(self.calls, [])
        self.assertEqual(len(ledger.runtimes), 2, "no generation was queued")
        self.assertEqual(ledger.row(2)["status"], "STOPPED")
        refusals = [e for e in ledger.events if e["kind"] == "runtime-rollback-refused"]
        self.assertEqual(len(refusals), 1)
        refusal = refusals[0]
        self.assertEqual((refusal["outcome"], refusal["actor"], refusal["target_id"]),
                         ("refused", worker.WORKER_ID, str(INTAKE)))
        self.assertEqual((refusal["scope"]["generation"], refusal["scope"]["runtime"]), (2, str(ledger.row(2)["id"])))
        self.assertTrue(refusal["reason"])
        if reason_part:
            self.assertIn(reason_part, refusal["reason"])
        self.assertNotIn("runtime-rollback-queued", ledger.kinds())
        self.assertEqual(ledger.steps[-1], "commit", "the refusal is committed, not lost with a rollback")
        self.assertEqual(ledger.tools, before, "a refused rollback leaves the current approval untouched")
        self.assertNotIn("contract-restored", ledger.steps)

    def test_target_generation_without_approval_history_is_refused(self):
        ledger = Ledger()
        ledger.events = [e for e in ledger.events if e["scope"].get("generation") != 1]
        self.refused(ledger, "유효성")

    def test_history_row_without_a_contract_snapshot_is_refused(self):
        ledger = Ledger()
        ledger.events[0]["scope"].pop("contract")
        self.refused(ledger, "유효성")

    def test_history_whose_hash_differs_from_the_request_snapshot_is_refused(self):
        ledger = Ledger()
        ledger.events[0]["scope"]["contract"]["sha256"] = "f" * 64
        self.refused(ledger, "유효성")

    def test_target_without_a_stored_image_is_refused(self):
        ledger = Ledger()
        ledger.row(1)["image_id"] = None
        self.refused(ledger)

    def test_revoked_terminated_or_supply_chain_stopped_generation_is_refused_per_marker(self):
        for kind in worker_markers:
            with self.subTest(kind):
                ledger = Ledger()
                ledger.add_event(kind, {"generation": 1})
                self.refused(ledger, "유효성")

    def test_server_withdrawn_terminated_or_supply_chain_stopped_is_refused_per_state(self):
        for name, change in (("DISABLED", {"status": "DISABLED"}),
                             ("BLOCKED_SUPPLY_CHAIN", {"status": "BLOCKED_SUPPLY_CHAIN"}),
                             ("TERMINATING", {"lifecycle": "TERMINATING"}),
                             ("TERMINATED", {"lifecycle": "TERMINATED"}),
                             ("RETIRED", {"lifecycle": "RETIRED"})):
            with self.subTest(name):
                ledger = Ledger()
                ledger.server.update(change)
                self.refused(ledger, "유효성")

    def test_suspended_or_ended_usage_relationship_is_refused(self):
        for name in ("suspended", "relationship_ended"):
            with self.subTest(name):
                ledger = Ledger()
                setattr(ledger, name, True)
                self.refused(ledger, "유효성")

    def test_missing_registered_server_is_refused(self):
        ledger = Ledger()
        ledger.registered = False
        self.refused(ledger, "유효성")

    def test_request_snapshot_without_tools_is_refused(self):
        ledger = Ledger()
        ledger.row(2)["rollback_contract"] = {"server_id": SERVER_ID, "tools": {}, "sha256": PRIOR["sha256"]}
        self.refused(ledger, "유효성")

    def test_tampered_snapshot_with_the_old_hash_is_refused_before_anything_is_written(self):
        ledger = Ledger()
        forged = copy.deepcopy(PRIOR)
        forged["tools"]["convert"]["approved_output_schema_hash"] = "e" * 64   # sha256 field left as approved
        ledger.row(2)["rollback_contract"] = forged
        self.refused(ledger, "해시")

    def test_tampered_snapshot_with_a_recomputed_hash_is_refused_by_the_history(self):
        ledger = Ledger()
        ledger.row(2)["rollback_contract"] = contract({"convert": tool("m", "9.9")})
        self.refused(ledger, "유효성")

    def test_changed_tool_set_is_refused(self):
        ledger = Ledger()
        ledger.tools["extra"] = tool("p", "1.0")
        self.refused(ledger, "도구 구성")


class ActiveRollbackGeneration(Harness):
    def active_ledger(self):
        ledger = Ledger(state="STOPPED")
        ledger.tools = copy.deepcopy(PRIOR["tools"])
        third = ledger.runtime(3, "ACTIVE", "1", evidence={**PRIOR_EVIDENCE, "answered": {"tools": 1}})
        third.update(image_id=ledger.row(1)["image_id"], rollback_target_generation=1,
                     rollback_contract=copy.deepcopy(PRIOR))
        ledger.runtimes.append(third)
        ledger.add_event("runtime-active", {"generation": 3, "contract": copy.deepcopy(PRIOR)})
        return ledger

    def test_reconcile_judges_the_rolled_back_generation_on_the_evidence_it_inherited(self):
        ledger = self.active_ledger()
        seen = []
        self.run_reconcile(ledger, verify=lambda evidence, **_k: seen.append(copy.deepcopy(evidence)) or {})
        self.assertEqual(self.calls, [])
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0], ledger.row(3)["evidence"])
        for key in ("source_archive_sha256", "source_attestation", "provenance_verification", "packages_sha256"):
            self.assertEqual(seen[0][key], PRIOR_EVIDENCE[key], key)
        self.assertEqual(ledger.row(3)["status"], "ACTIVE")
        self.assertEqual(len(ledger.runtimes), 3)

    def test_inherited_evidence_that_no_longer_verifies_stops_the_generation(self):
        ledger = self.active_ledger()
        ledger.row(3)["evidence"] = {**ledger.row(3)["evidence"], "source_verification_error": "bad"}
        ledger.registered = False   # keeps the follow-on rollback decision out of this check
        self.run_reconcile(ledger, verify=False)
        self.assertEqual(ledger.row(3)["status"], "STOPPED")
        self.assertIn("MCP-SUPPLY-001", ledger.row(3)["error"])
        self.assertIn("runtime-stopped", ledger.kinds())

    def test_rolled_back_generation_follows_the_same_revocation_rules(self):
        ledger = self.active_ledger()
        ledger.add_event("runtime-revoked", {"generation": 1})
        self.run_reconcile(ledger, verify=lambda *_a, **_k: {})
        self.assertEqual(ledger.row(3)["status"], "STOPPED")
        self.assertIn("철회", ledger.row(3)["error"])

    def test_rolled_back_generation_is_stopped_when_its_target_evidence_is_gone(self):
        ledger = self.active_ledger()
        ledger.events[0]["scope"].pop("contract")
        self.run_reconcile(ledger, verify=lambda *_a, **_k: {})
        self.assertEqual(ledger.row(3)["status"], "STOPPED")
        self.assertIn("이미지 증거", ledger.row(3)["error"])


class ApiCursor:
    def __init__(self, rows=()):
        self.rows = list(rows)

    async def fetchone(self):
        return self.rows[0] if self.rows else None

    async def fetchall(self):
        return self.rows


class ApiLedger:
    """What the rollback request reads and writes in its one transaction; a failure restores the snapshot taken at entry."""

    def __init__(self):
        self.server = {"id": SERVER_ID, "status": "READY", "lifecycle": "OPERATING"}
        self.stopped_server = False
        self.registered = True
        self.tools = {"convert": tool("d", "1.1")}
        self.runtimes = {1: {"status": "STOPPED", "image_id": "sha256:" + "1" * 64},
                         2: {"status": "ACTIVE", "image_id": "sha256:" + "2" * 64}}
        self.events = [{"kind": "runtime-active", "scope": {"generation": 1, "contract": copy.deepcopy(PRIOR)}},
                       {"kind": "runtime-active", "scope": {"generation": 2, "contract": copy.deepcopy(CURRENT)}}]
        self.marked = {}      # generation -> the rollback request written onto it
        self.statements = []
        self.fail_event = False

    def snapshot(self):
        return copy.deepcopy((self.runtimes, self.events, self.marked))

    async def execute(self, query, params=()):
        q = normalised(query)
        self.statements.append(q.split(" ")[0])
        if q.startswith("SELECT registered_server_id"):
            return ApiCursor([{"registered_server_id": SERVER_ID if self.registered else None}])
        if q.startswith("SELECT id,status,lifecycle FROM mcp_servers"):
            return ApiCursor([self.server])
        if "FROM ops_suspensions" in q:
            return ApiCursor([{"?column?": 1}] if self.stopped_server else [])
        if q.startswith("SELECT scope,created_at FROM approval_events WHERE kind='runtime-active'"):
            history = [e for e in self.events if e["kind"] == "runtime-active"
                       and str(e["scope"].get("generation")) == params[1] and e["scope"].get("contract") is not None]
            return ApiCursor([{"scope": history[-1]["scope"], "created_at": "2026-10-20T01:00:00Z"}] if history else [])
        if q.startswith("SELECT 1 FROM approval_events WHERE target_kind='intake'"):
            return ApiCursor([{"?column?": 1}] if any(
                e["kind"] in worker_markers and str(e["scope"].get("generation")) == params[1] for e in self.events) else [])
        if q.startswith("SELECT image_id,status FROM mcp_runtimes"):
            row = self.runtimes.get(params[1])
            return ApiCursor([dict(row)] if row else [])
        if q.startswith("SELECT generation FROM mcp_runtimes"):
            active = [g for g, r in self.runtimes.items() if r["status"] == "ACTIVE"]
            return ApiCursor([{"generation": max(active)}] if active else [])
        if q.startswith("SELECT name FROM mcp_tools"):
            return ApiCursor([{"name": name} for name in self.tools])
        if q.startswith("UPDATE mcp_runtimes SET status='STOPPING'"):
            generation, snapshot, _intake = params
            active = [g for g, r in self.runtimes.items() if r["status"] == "ACTIVE"]
            if not active:
                return ApiCursor()
            row = self.runtimes[max(active)]
            row["status"] = "STOPPING"
            self.marked[max(active)] = {"rollback_target_generation": generation, "rollback_contract": snapshot.obj}
            return ApiCursor([{"id": uuid.UUID(int=max(active)), "generation": max(active)}])
        if q.startswith("INSERT INTO approval_events"):
            if self.fail_event:
                raise RuntimeError("ledger unavailable")
            kind, outcome, target_kind, target_id, actor, _applicant, reason, scope = params
            self.events.append({"kind": kind, "outcome": outcome, "target_kind": target_kind, "target_id": target_id,
                                "actor": actor, "reason": reason, "scope": scope.obj})
            return ApiCursor([{"id": len(self.events)}])
        raise AssertionError("unexpected statement: " + q[:120])


@unittest.skipUnless(API, "needs the gateway's own dependencies (fastapi, a real psycopg)")
class RollbackRequest(unittest.TestCase):
    ADMIN = {"roles": ["admin"], "principal": "admin-principal"}

    def call(self, ledger, generation=1, note="  새 판본 장애로   되돌립니다 ", user=None):
        @asynccontextmanager
        async def transaction():
            before = ledger.snapshot()
            try:
                yield ledger
            except BaseException:
                ledger.runtimes, ledger.events, ledger.marked = before
                raise

        async def identity(_authorization):
            return user or self.ADMIN
        with mock.patch.object(agent_service, "current_identity", identity), \
                mock.patch.object(agent_service.db, "transaction", transaction):
            return asyncio.run(agent_service.rollback_runtime(
                INTAKE, agent_service.RuntimeRollback(generation=generation, note=note), "Bearer x"))

    def untouched(self, ledger):
        self.assertEqual(ledger.runtimes[2]["status"], "ACTIVE")
        self.assertEqual(ledger.marked, {})
        self.assertNotIn("runtime-rollback", [e["kind"] for e in ledger.events])

    def test_request_marks_the_active_generation_for_stop_and_records_who_asked_in_the_same_transaction(self):
        ledger = ApiLedger()
        result = self.call(ledger)
        self.assertIn("요청", result["message"])
        self.assertEqual(ledger.runtimes[2]["status"], "STOPPING")
        self.assertEqual(ledger.runtimes[1]["status"], "STOPPED")
        self.assertEqual(ledger.marked, {2: {"rollback_target_generation": 1, "rollback_contract": PRIOR}})
        asked = ledger.events[-1]
        self.assertEqual((asked["kind"], asked["outcome"], asked["target_kind"], asked["target_id"], asked["actor"]),
                         ("runtime-rollback", "recorded", "intake", str(INTAKE), "admin-principal"))
        self.assertEqual(asked["reason"], "새 판본 장애로 되돌립니다")
        self.assertEqual(asked["scope"], {"from_generation": 2, "to_generation": 1, "contract_sha256": PRIOR["sha256"]})
        self.assertEqual(ledger.events[0]["scope"]["contract"], PRIOR, "the approval history is only appended to")

    def test_ledger_failure_takes_the_stop_request_back_with_it(self):
        ledger = ApiLedger()
        ledger.fail_event = True
        with self.assertRaises(RuntimeError):
            self.call(ledger)
        self.untouched(ledger)

    def test_only_an_administrator_and_a_one_line_reason_may_ask(self):
        ledger = ApiLedger()
        with self.assertRaises(HTTPException) as denied:
            self.call(ledger, user={"roles": ["employee"], "principal": "e-1"})
        self.assertEqual(denied.exception.status_code, 403)
        with self.assertRaises(HTTPException) as multiline:
            self.call(ledger, note="첫 줄\n둘째 줄")
        self.assertEqual(multiline.exception.status_code, 422)
        self.untouched(ledger)
        self.assertEqual(ledger.statements, [], "nothing was read or written before the refusal")

    def refused(self, ledger, generation=1):
        with self.assertRaises(HTTPException) as caught:
            self.call(ledger, generation=generation)
        self.assertEqual(caught.exception.status_code, 409)
        self.untouched(ledger)
        self.assertNotIn("UPDATE", ledger.statements)

    def test_withdrawn_terminated_supply_chain_stopped_or_suspended_server_is_refused_per_state(self):
        for name, change in (("DISABLED", {"status": "DISABLED"}), ("BLOCKED_SUPPLY_CHAIN", {"status": "BLOCKED_SUPPLY_CHAIN"}),
                             ("TERMINATING", {"lifecycle": "TERMINATING"}), ("TERMINATED", {"lifecycle": "TERMINATED"}),
                             ("RETIRED", {"lifecycle": "RETIRED"})):
            with self.subTest(name):
                ledger = ApiLedger()
                ledger.server.update(change)
                self.refused(ledger)
        with self.subTest("suspended or relationship ended"):
            ledger = ApiLedger()
            ledger.stopped_server = True
            self.refused(ledger)
        with self.subTest("not registered"):
            ledger = ApiLedger()
            ledger.registered = False
            self.refused(ledger)

    def test_revoked_terminated_or_supply_chain_stopped_generation_is_refused_per_marker(self):
        for kind in worker_markers:
            with self.subTest(kind):
                ledger = ApiLedger()
                ledger.events.append({"kind": kind, "scope": {"generation": 1}})
                self.refused(ledger)

    def test_generation_without_approval_history_or_with_an_empty_snapshot_is_refused(self):
        ledger = ApiLedger()
        ledger.events.pop(0)
        self.refused(ledger)
        ledger = ApiLedger()
        ledger.events[0]["scope"]["contract"]["tools"] = {}
        self.refused(ledger)
        ledger = ApiLedger()
        ledger.events[0]["scope"].pop("contract")
        self.refused(ledger)

    def test_target_must_be_a_stopped_earlier_generation_with_its_image(self):
        for name, change in (("image gone", lambda l: l.runtimes[1].update(image_id=None)),
                             ("not stopped", lambda l: l.runtimes[1].update(status="FAILED"))):
            with self.subTest(name):
                ledger = ApiLedger()
                change(ledger)
                self.refused(ledger)
        with self.subTest("the running generation itself"):
            self.refused(ApiLedger(), generation=2)
        with self.subTest("nothing is running"):
            ledger = ApiLedger()
            ledger.runtimes[2]["status"] = "STOPPED"
            with self.assertRaises(HTTPException) as caught:
                self.call(ledger)
            self.assertEqual(caught.exception.status_code, 409)
            self.assertEqual(ledger.marked, {})
            self.assertNotIn("runtime-rollback", [e["kind"] for e in ledger.events])

    def test_changed_tool_set_is_refused(self):
        ledger = ApiLedger()
        ledger.tools["extra"] = tool("p", "1.0")
        self.refused(ledger)


class JobBranchShape(unittest.TestCase):
    """run_job needs a container engine; its rollback branch is pinned by structure instead."""

    @staticmethod
    def called(nodes):
        names = set()
        for node in nodes:
            for call in ast.walk(node):
                if isinstance(call, ast.Call):
                    func = call.func
                    names.add(func.id if isinstance(func, ast.Name) else getattr(func, "attr", ""))
        return names

    def test_rollback_branch_of_run_job_neither_fetches_builds_nor_verifies_provenance(self):
        tree = ast.parse((ROOT / "runtime" / "worker.py").read_text(encoding="utf-8"))
        run_job = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run_job")
        branch = next(n for n in ast.walk(run_job) if isinstance(n, ast.If) and n.orelse
                      and "rollback_target_generation" in ast.unparse(n.test) and "fetch_source" in ast.unparse(n.orelse))
        rollback, fresh = self.called(branch.body), self.called(branch.orelse)
        self.assertFalse(rollback & {"fetch_source", "verify_source_provenance", "build"}, rollback)
        self.assertTrue({"fetch_source", "verify_source_provenance", "build"} <= fresh)
        # the prior evidence is the one carried forward
        self.assertIn("target.get(\"evidence\")", ast.unparse(branch).replace("'", '"'))


if __name__ == "__main__":
    unittest.main()
