"""D-140: deterministic DB interleavings, not PostgreSQL or real MCP evidence.

Standard library only: load production definitions without optional Gateway imports.
AsyncMock DB statements model transaction locks/commit/rollback; Events select the
interleaving without sleeps. The real sender runs with a unit-level client double.
"""
from __future__ import annotations

import ast
import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

APP = Path(__file__).resolve().parents[1] / "gateway" / "app"
if not APP.exists():
    APP = Path("/app/app")


def production(filename, names, namespace):
    tree = ast.parse((APP / filename).read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if getattr(n, "name", None) in names or
             isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in n.targets)]
    if len(nodes) != len(names):
        raise AssertionError("missing production definitions")
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(APP / filename), "exec"), namespace)
    return SimpleNamespace(**namespace)


spec = importlib.util.spec_from_file_location("flow_fingerprint", APP / "flow_fingerprint.py")
ff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ff)
digest = production("contract.py", {"canonical_hash"}, {"hashlib": hashlib, "json": json}).canonical_hash
UTC = timezone.utc
TERMS = {"consent": True, "purpose": "synthetic", "grade": "important"}


def cursor(row=None, rows=(), count=1):
    return SimpleNamespace(fetchone=AsyncMock(return_value=row), fetchall=AsyncMock(return_value=list(rows)), rowcount=count)


class Database:
    """One dispatcher and one control writer; this deliberately does not emulate SQL/MVCC."""
    def __init__(self):
        self.locks = {key: asyncio.Lock() for key in ("advisory", "server", "principal", "consent", "chain")}
        self.status, self.granted, self.unexpired = "active", True, True
        self.tool_review = dict(TERMS)
        self.reads, self.intents, self.history, self.pending = [], [], [], {}
        self.pause, self.reached, self.resume = None, asyncio.Event(), asyncio.Event()
        self.fail, self.failed, self.commits, self.rollbacks = None, None, 0, 0
        self.execute = AsyncMock(side_effect=self.statement)
        self.fetch_one = AsyncMock(side_effect=self.why)

    @asynccontextmanager
    async def transaction(self):
        task = asyncio.current_task()
        tx = SimpleNamespace(held=[], intents=[], change=None)
        self.pending[task] = tx
        try:
            yield SimpleNamespace(execute=self.execute)
        except BaseException:
            self.rollbacks += 1
            raise
        else:
            if self.fail == "commit":
                self.failed = "commit"
                self.rollbacks += 1
                raise OSError("injected commit failure")
            self.intents.extend(tx.intents)
            if tx.change:
                key, value = tx.change
                setattr(self, key, value)
            self.commits += 1
        finally:
            self.pending.pop(task)
            for key in reversed(tx.held):
                self.locks[key].release()

    async def lock(self, key):
        tx = self.pending[asyncio.current_task()]
        if key not in tx.held:
            self.history.append(("wait", key))
            await self.locks[key].acquire()
            tx.held.append(key)
            self.history.append(("lock", key))

    async def gate(self, stage):
        if self.fail == stage:
            self.failed = stage
            raise OSError("injected DB failure")
        if self.pause == stage:
            self.reached.set()
            await self.resume.wait()

    async def statement(self, query, params=()):
        tx = self.pending[asyncio.current_task()]
        self.history.append(("sql", query))
        if query.startswith("SELECT user_token"):
            return cursor({"user_token": "employee", "fingerprint": "fp"})
        if "SELECT 1 FROM dispatch_intents" in query:
            return cursor()
        if "pg_advisory_xact_lock" in query:
            await self.gate("advisory")
            await self.lock("advisory")
        elif "SELECT s.id, t.scope_review" in query:
            await self.gate("server")
            if "FOR SHARE OF s, t" not in query:
                raise AssertionError("server/tool locks missing")
            await self.lock("server")
            return cursor({"id": "destination", "scope_review": self.tool_review,
                           "tool_name": "send", "data_class": "nonimportant"})
        elif query.startswith("SELECT token FROM principals"):
            if "FOR SHARE" not in query or "FOR KEY SHARE" in query:
                raise AssertionError("status updates need a conflicting row lock")
            await self.gate("principal")
            await self.lock("principal")
        elif query.startswith("SELECT id FROM user_consents"):
            if "FOR SHARE" in query:
                await self.gate("consent")
                await self.lock("consent")
            if "clock_timestamp()" not in query or "status='GRANTED'" not in query:
                raise AssertionError("consent must use wall clock and status")
            return cursor({"id": 7} if self.granted and self.unexpired else None)
        elif "FROM decisions d LEFT JOIN flow_fingerprints" in query:
            if "advisory" not in tx.held:
                raise AssertionError("flow query outside principal lock")
            await self.gate("flow")
            return cursor(rows=self.reads)
        elif query.startswith("INSERT INTO dispatch_intents"):
            if "c.expires_at > clock_timestamp()" not in query or "p.status = 'active'" not in query:
                raise AssertionError("final intent must recheck status and expiry")
            # Freeze the statement snapshot, then offer a writer the original race window.
            active = self.status == "active"
            await self.gate("insert")
            if not active or params[2] is not None and (not self.granted or not self.unexpired):
                return cursor(count=0)
            tx.intents.append(params[1])
        elif query.startswith("UPDATE principals"):
            await self.lock("principal")
            tx.change = ("status", "disabled")
        elif query.startswith("UPDATE user_consents"):
            await self.lock("consent")
            tx.change = ("granted", False)
        elif "head_sha256 FROM audit_chain" in query:
            await self.lock("chain")
            return cursor({"head_sha256": "genesis"})
        elif query.startswith("INSERT INTO decisions"):
            return cursor({"id": 19})
        elif query.startswith("UPDATE audit_chain"):
            pass
        else:
            raise AssertionError("unexpected SQL: " + query)
        return cursor()

    async def why(self, query, params=()):
        return {"principal": self.status, "lifecycle": "OPERATING", "server_status": "ACTIVE", "catalog_ok": True}

    async def change(self, kind, started=None):
        async with self.transaction() as connection:
            if started:
                started.set()
            await connection.execute("UPDATE principals" if kind == "principal" else "UPDATE user_consents")


class Checks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = Database()
        self.consent = production("consent.py", {"for_dispatch", "_rank", "RANK"},
                                  {"terms_hash": lambda terms: digest(terms)})
        self.dispatch = production("dispatch.py", {"record", "_Refused", "CATALOG_OK", "_INSERT", "REPLAY"},
            {"db": self.db, "consent": self.consent, "high_impact": SimpleNamespace(),
             "Jsonb": lambda v: v, "canonical_hash": digest, "IDEMPOTENCY_TTL_SECONDS": 86400})
        self.client = SimpleNamespace(call_tool=AsyncMock(return_value=SimpleNamespace(is_error=False, structured_content=None)))
        @asynccontextmanager
        async def session(*args, **kwargs):
            yield self.client
        view = {"description": "synthetic contract", "input_schema": {"type": "object"}}
        tool = {"name": "send", "enabled": True, "approved_description_hash": digest(view["description"]),
                "approved_schema_hash": digest(view["input_schema"]), "approved_server_version": "pinned"}
        upstream = SimpleNamespace(session=session, list_all_tools=AsyncMock(return_value=[SimpleNamespace(name="send")]),
            tool_view=lambda t: view, release_pool=AsyncMock(), content_items=lambda r: [], session_terminated=lambda e: False,
            credential_source=lambda *args: "none")
        db = SimpleNamespace(fetch_all=AsyncMock(return_value=[tool]),
            fetch_one=AsyncMock(return_value={"status": "active"}))
        def classification(server, tool, base_action, action):
            return SimpleNamespace(action=action)
        self.ns = {"__package__": "dispatch_recheck_unit", "asyncio": asyncio, "db": db, "dispatch": self.dispatch,
            "output_contract": production("output_contract.py", {"approved_hash", "matches"},
                                          {"canonical_hash": digest, "NO_OUTPUT_SCHEMA_HASH": digest(None)}),
            "classify": SimpleNamespace(Classification=classification, classify=lambda *args: SimpleNamespace()), "flow_fingerprint": ff,
            "FLOW_MATCH_MODE": "coarse", "CHAIN_WINDOW_MINUTES": 10,
            "datetime": datetime, "UTC": UTC, "canonical_hash": digest, "upstream": upstream,
            "registry": SimpleNamespace(server=lambda s: {"endpoint": "http://unit.invalid"},
                                         pinned_protocol=lambda s: "pinned", tool_hashes=lambda t: {}, review_matches=lambda *args: False),
            "Draft202012Validator": lambda schema: SimpleNamespace(is_valid=lambda arguments: True),
            "poisoning": SimpleNamespace(findings=lambda t: []), "_ledger_cache": {}, "GATEWAY_ENVIRONMENT": "prod",
            "_Laps": lambda: SimpleNamespace(lap=lambda name: None), "_guarded_result": lambda payload, *args: payload,
            "_contract": AsyncMock(return_value={}), "pac": SimpleNamespace(build=AsyncMock(return_value={})),
            "_policy": AsyncMock(return_value={"decision": "Allow", "policy_id": "P-AUTHZ-ALLOW-001"})}
        self.core = production("core.py", {"_flow_sources", "_dispatch_flow_recheck", "_call_upstream", "DispatchRejected", "local_verdict"}, self.ns)
        self.policy = {"tool": {"name": "send", "base_action": "w", "action": "w", "provider_hosted": False},
                       "request": {"flow_sources": []}, "context": {}}

    async def send(self, request="request"):
        self.event = {"request_id": request, "action": self.policy["tool"]["action"], "policy_input": deepcopy(self.policy),
                      "upstream_attempted": False, "upstream_executed": False}
        endpoint = ModuleType("dispatch_recheck_unit.endpoint_plane")
        endpoint.managed_failure = AsyncMock(return_value=None)
        package = ModuleType("dispatch_recheck_unit")
        package.__path__ = []
        with patch.dict(sys.modules, {"dispatch_recheck_unit": package, "dispatch_recheck_unit.endpoint_plane": endpoint}):
            try:
                await self.core._call_upstream("destination", "send", {}, principal="employee",
                                               dispatch_state=self.event, pac_payload={"arguments": {}})
            except self.core.DispatchRejected as exc:
                return exc.verdict
        return {"decision": "Allow", "policy_id": "P-AUTHZ-ALLOW-001"}

    def blocked(self, result, policy):
        self.assertEqual((result["decision"], result["policy_id"]), ("Block", policy))
        self.assertEqual(self.db.intents, [])
        self.client.call_tool.assert_not_awaited()
        self.assertFalse(self.event["upstream_attempted"])
        self.assertFalse(self.event["upstream_executed"])

    async def finish(self, *tasks):
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def wait_for_lock(self, key, count=1):
        async def observe():
            while self.db.history.count(("wait", key)) < count:
                await asyncio.sleep(0)
        await asyncio.wait_for(observe(), 2)

    async def test_suspend_commits_before_dispatch_enters(self):
        await self.db.change("principal")
        result = await self.send()
        self.blocked(result, "P-INPUT-001")

    async def test_suspend_commits_later_than_dispatch_start_during_server_wait(self):
        self.db.pause = "server"
        task = asyncio.create_task(self.send())
        try:
            await asyncio.wait_for(self.db.reached.wait(), 2)
            await self.db.change("principal")
            self.db.resume.set()
            self.blocked(await asyncio.wait_for(task, 2), "P-INPUT-001")
        finally:
            await self.finish(task)

    async def test_uncommitted_suspend_holds_principal_then_dispatch_sees_commit(self):
        async with self.db.transaction() as connection:
            await connection.execute("UPDATE principals")
            task = asyncio.create_task(self.send())
            try:
                # Observe an attempted lock, not an elapsed-time assumption.
                await self.wait_for_lock("principal")
                self.assertFalse(task.done())
            finally:
                if task.done():
                    await self.finish(task)
        try:
            self.blocked(await asyncio.wait_for(task, 2), "P-INPUT-001")
        finally:
            await self.finish(task)

    async def test_revoke_commits_before_consent_lock(self):
        await self.db.change("consent")
        self.blocked(await self.send(), "P-CONSENT-001")

    async def test_revoke_commits_during_server_wait(self):
        self.db.pause = "server"
        task = asyncio.create_task(self.send())
        try:
            await asyncio.wait_for(self.db.reached.wait(), 2)
            await self.db.change("consent")
            self.db.resume.set()
            self.blocked(await asyncio.wait_for(task, 2), "P-CONSENT-001")
        finally:
            await self.finish(task)

    async def test_expiry_at_final_insert_uses_wall_clock_and_rolls_back(self):
        self.db.pause = "insert"
        task = asyncio.create_task(self.send())
        try:
            await asyncio.wait_for(self.db.reached.wait(), 2)
            self.db.unexpired = False
            self.db.resume.set()
            self.blocked(await asyncio.wait_for(task, 2), "P-CONSENT-001")
            self.assertEqual(self.db.rollbacks, 1)
        finally:
            await self.finish(task)

    async def test_intent_first_blocks_later_suspend_and_revoke_until_commit(self):
        for kind in ("principal", "consent"):
            with self.subTest(kind=kind):
                self.setUp()
                self.db.pause = "insert"
                send = asyncio.create_task(self.send())
                writer = None
                try:
                    await asyncio.wait_for(self.db.reached.wait(), 2)
                    started = asyncio.Event()
                    writer = asyncio.create_task(self.db.change(kind, started))
                    await asyncio.wait_for(started.wait(), 2)
                    self.assertFalse(writer.done())
                    self.assertEqual(self.db.intents, [])
                    self.db.resume.set()
                    self.assertEqual((await asyncio.wait_for(send, 2))["decision"], "Allow")
                    await asyncio.wait_for(writer, 2)
                    self.assertEqual(self.db.intents, ["request"])
                    self.client.call_tool.assert_awaited_once()
                    # Once the control change commits, a fresh request never leaves.
                    self.client.call_tool.reset_mock()
                    self.db.intents.clear()
                    self.db.pause = None
                    result = await self.send("next")
                    if kind == "consent":
                        self.blocked(result, "P-CONSENT-001")
                    else:
                        self.blocked(result, "P-INPUT-001")
                finally:
                    await self.finish(*[task for task in (send, writer) if task])

    async def test_new_read_commits_during_advisory_wait(self):
        self.db.pause = "advisory"
        task = asyncio.create_task(self.send())
        try:
            await asyncio.wait_for(self.db.reached.wait(), 2)
            async with self.db.transaction():
                await self.db.lock("advisory")
                self.db.reads = [{"server_id": "new-source"}]
            self.db.resume.set()
            self.blocked(await asyncio.wait_for(task, 2), "P-FLOW-001")
        finally:
            await self.finish(task)

    async def test_provider_read_rechecks_sources_but_internal_read_does_not_cross(self):
        self.db.reads = [{"server_id": "source"}]
        self.policy["tool"].update(action="r", base_action="r", provider_hosted=True)
        self.blocked(await self.send(), "P-FLOW-001")
        self.policy["tool"]["provider_hosted"] = False
        self.assertEqual((await self.send())["decision"], "Allow")

    async def test_existing_sources_remain_permitted_and_content_mode_does_not_overblock(self):
        self.db.reads = [{"server_id": "old-source"}]
        self.policy["request"]["flow_sources"] = ["old-source"]
        self.assertEqual((await self.send())["decision"], "Allow")
        self.db.intents.clear()
        self.client.call_tool.reset_mock()
        salt = b"synthetic-salt-01"
        shingles, identifiers = ff.fingerprint("completely unrelated synthetic document", salt)
        self.db.reads = [{"server_id": "old-source", "salt": salt, "key_id": ff.KEY_ID,
                          "shingles": shingles, "identifiers": identifiers}]
        self.policy["request"]["flow_sources"] = []
        self.ns["FLOW_MATCH_MODE"] = "content"
        self.assertEqual((await self.send())["decision"], "Allow")

    async def test_same_server_new_uncomparable_read_invalidates_content_decision(self):
        self.ns["FLOW_MATCH_MODE"] = "content"
        self.db.reads = [{"server_id": "previously-unmatched-source"}]
        self.blocked(await self.send(), "P-FLOW-001")

    async def test_db_lock_flow_and_commit_failures_never_send(self):
        for stage in ("advisory", "server", "principal", "consent", "flow", "insert", "commit"):
            with self.subTest(stage=stage):
                self.setUp()
                self.db.fail = stage
                self.blocked(await self.send(), "P-CONTROL-FAIL-CLOSED")
                self.assertEqual(self.db.failed, stage)
                self.assertEqual(self.db.rollbacks, 1)

    async def test_cancellation_rolls_back_and_releases_all_locks(self):
        self.db.pause = "insert"
        task = asyncio.create_task(self.send())
        try:
            await asyncio.wait_for(self.db.reached.wait(), 2)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertEqual(self.db.intents, [])
            self.client.call_tool.assert_not_awaited()
            self.assertTrue(all(not lock.locked() for lock in self.db.locks.values()))
        finally:
            await self.finish(task)

    async def test_important_read_publisher_takes_advisory_before_chain(self):
        core = production("core.py", {"_record_decision"}, {"db": self.db, "_storable": lambda v: v,
            "outcome_axes": lambda e: {}, "secret_scan": SimpleNamespace(redact_error=AsyncMock(return_value=None)),
            "GATEWAY_ENVIRONMENT": "prod", "_audit_payload": lambda v: v, "response_disposition": lambda e: "released",
            "hashlib": hashlib, "_audit_fingerprint": lambda r: "fp", "datetime": datetime, "UTC": UTC,
            "Jsonb": lambda v: v, "CHAIN_VERSION": 1, "GENESIS": "genesis"})
        event = {"request_id": "read", "trace_id": "trace", "user_token": "employee", "role": "employee",
                 "tool_name": "read", "data_class": "important", "action": "r", "decision": "Alert",
                 "policy_id": "P-IMPORTANT-ALERT-001", "reason": "synthetic", "upstream_executed": True}
        async with self.db.transaction():
            await self.db.lock("advisory")
            task = asyncio.create_task(core._record_decision(event))
            try:
                await self.wait_for_lock("advisory", 2)
                self.assertNotIn(("lock", "chain"), self.db.history)
            finally:
                if task.done():
                    await self.finish(task)
        try:
            self.assertEqual(await asyncio.wait_for(task, 2), 19)
            locks = [key for kind, key in self.db.history if kind == "lock"]
            self.assertEqual(locks, ["advisory", "advisory", "chain"])
        finally:
            await self.finish(task)

    async def test_consent_scope_and_grade_query_bindings(self):
        connection = SimpleNamespace(execute=AsyncMock(return_value=cursor({"id": 7})))
        for grade, covering in (("public", ["public", "nonimportant", "important"]),
                                ("nonimportant", ["nonimportant", "important"]),
                                ("important", ["important"]), ("unknown", ["important"])):
            await self.consent.for_dispatch(connection, "employee", "destination", "send", grade, TERMS)
            query, params = connection.execute.await_args.args
            self.assertEqual(params, ("employee", "destination", "send", digest(TERMS), covering))
            self.assertIn("terms_hash=%s", query)
            self.assertIn("FOR SHARE", query)
            self.assertIn("expires_at > clock_timestamp()", query)


if __name__ == "__main__":
    unittest.main(verbosity=2)
