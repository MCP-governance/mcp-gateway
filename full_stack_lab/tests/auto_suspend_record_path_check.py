"""D-176 판정 기록 경로: 자동 중지 집계가 실패해도 Block 판정 행은 원장에 남아야 한다.

PostgreSQL 없이 실행한다. core._record_decision과 automatic_suspend.suspend를 저장된 함수 본문 그대로
추출하고, 트랜잭션은 저장점(SAVEPOINT) 규칙을 흉내 낸다: 중첩 트랜잭션 안의 오류는 그 저장점의 작업만
되돌리고, 바깥 트랜잭션에서 난 오류는 그 안의 작업 전부를 버린다.
"""
from __future__ import annotations

import ast
import copy
from datetime import UTC, datetime, timedelta
import hashlib
import importlib.util
import logging
from contextlib import asynccontextmanager
from pathlib import Path
import re
from types import SimpleNamespace
import unittest

LAB = Path(__file__).resolve().parents[1]
APP = LAB / "gateway" / "app"
GENESIS = "0" * 64
EXPECTED_POLICIES = ("MCP-EGRESS-002", "MCP-DATA-EGRESS-001", "P-DLP-001", "P-CHAIN-001", "P-FLOW-001")


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def selected(path: Path, names, namespace):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes = [node for node in tree.body if getattr(node, "name", None) in names
             or isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in node.targets)]
    found = {getattr(n, "name", None) for n in nodes}
    found.update(t.id for n in nodes if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name))
    if not set(names) <= found:
        raise AssertionError(f"missing production definitions: {set(names) - found}")
    exec(compile(ast.fix_missing_locations(ast.Module(
        body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *nodes],
        type_ignores=[])), str(path), "exec"), namespace)
    return SimpleNamespace(**namespace)


outcomes = load("outcomes_under_test", APP / "outcomes.py")
contract = load("contract_under_test", APP / "contract.py")


class Cursor:
    def __init__(self, row):
        self.row = row

    async def fetchone(self):
        return self.row


class Connection:
    """One transaction's working copy. A nested transaction is a savepoint: an error inside it restores
    the copy taken when it started, then propagates."""

    def __init__(self, ledger):
        self.ledger = ledger
        self.state = copy.deepcopy(ledger.committed)

    @asynccontextmanager
    async def transaction(self):
        saved = copy.deepcopy(self.state)
        try:
            yield self
        except BaseException:
            self.state = saved
            raise

    async def execute(self, query, params=()):
        return self.ledger.sql(self.state, query, tuple(params))


class Ledger:
    """Committed rows plus the aggregate failure switch. A failing top-level transaction commits nothing."""

    def __init__(self):
        self.committed = {"decisions": [], "suspensions": [], "events": [], "head": GENESIS}
        self.count_fails = False
        self.count_calls = 0

    @asynccontextmanager
    async def transaction(self):
        connection = Connection(self)
        yield connection
        self.committed = connection.state

    def sql(self, state, query, params):
        if "pg_advisory_xact_lock" in query:
            return Cursor(None)
        if "FROM audit_chain" in query:
            return Cursor({"head_sha256": state["head"]})
        if query.lstrip().startswith("INSERT INTO decisions"):
            columns = [c.strip() for c in re.search(r"INSERT INTO decisions\((.*?)\)\s*VALUES", query, re.S)
                       .group(1).split(",")]
            row = dict(zip(columns, params, strict=True))
            row["id"] = len(state["decisions"]) + 1
            state["decisions"].append(row)
            return Cursor({"id": row["id"]})
        if "UPDATE audit_chain SET head_sha256" in query:
            state["head"] = params[0]
            return Cursor(None)
        if "SELECT count(*) AS n FROM decisions" in query:
            self.count_calls += 1
            if self.count_fails:
                raise OSError("aggregate unavailable")
            user, server, policies, _window = params
            n = sum(1 for d in state["decisions"] if d["user_token"] == user and d["server_id"] == server
                    and d["decision"] == "Block" and d["policy_id"] in policies)
            return Cursor({"n": n})
        if "UPDATE user_server_suspensions SET resumed_at=expires_at" in query:
            return Cursor(None)
        if "INSERT INTO user_server_suspensions" in query:
            user, server, duration = params
            if any(s["user"] == user and s["server"] == server and s["resumed_at"] is None
                   for s in state["suspensions"]):
                return Cursor(None)
            now = datetime.now(UTC)
            row = {"id": len(state["suspensions"]) + 1, "user": user, "server": server, "resumed_at": None,
                   "suspended_by": "automatic", "suspended_at": now,
                   "expires_at": now + timedelta(seconds=duration)}
            state["suspensions"].append(row)
            return Cursor({"id": row["id"], "suspended_at": row["suspended_at"], "expires_at": row["expires_at"]})
        if "SELECT count(*) FILTER (WHERE i.request_id IS NULL)" in query:
            return Cursor({"unsent": 0, "sent": 0})
        raise AssertionError(f"unexpected SQL: {query.strip()[:80]}")


def build_core(ledger: Ledger):
    async def record_event(kind, outcome, target_kind, target_id, actor, *, reason=None, scope=None, connection=None):
        connection.state["events"].append({"kind": kind, "outcome": outcome, "actor": actor, "scope": scope})
        return len(connection.state["events"])

    auto = selected(APP / "automatic_suspend.py", ["_expire_locked", "suspend"],
                    {"TARGET": "user-server-suspension", "review": SimpleNamespace(record_event=record_event)})

    async def redact_error(error):
        return error

    async def audit_fingerprint_free(record):
        return contract.audit_fingerprint(record)

    namespace = {
        "__name__": "core_under_test", "logging": logging, "hashlib": hashlib,
        "datetime": datetime, "UTC": UTC, "GENESIS": GENESIS, "CHAIN_VERSION": contract.CHAIN_VERSION,
        "GATEWAY_ENVIRONMENT": "test", "outcome_axes": outcomes.outcome_axes,
        "_audit_fingerprint": contract.audit_fingerprint, "_audit_payload": lambda v: v,
        "response_disposition": lambda e: "not_executed", "Jsonb": lambda v: v,
        "db": SimpleNamespace(transaction=ledger.transaction),
        "secret_scan": SimpleNamespace(redact_error=redact_error),
        "user_suspend": SimpleNamespace(auto_suspend=auto.suspend),
        "AUTO_SUSPEND_THRESHOLD": 2, "AUTO_SUSPEND_WINDOW_SECONDS": 600, "AUTO_SUSPEND_DURATION_SECONDS": 900,
    }
    return selected(APP / "core.py", ["_record_decision", "_storable", "AUTO_SUSPEND_POLICIES"], namespace)


def block_event(n: int, policy: str = "P-DLP-001") -> dict:
    return {"request_id": f"req-{n}", "trace_id": f"trace-{n}", "user_token": "employee", "role": "staff",
            "tool_name": "send_mail", "data_class": "nonimportant", "action": "w", "decision": "Block",
            "policy_id": policy, "reason": "synthetic", "upstream_executed": False,
            "server_id": "wiki", "request_payload": {}}


class DecisionRecordPath(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.ledger = Ledger()
        self.core = build_core(self.ledger)

    def decisions(self):
        return self.ledger.committed["decisions"]

    def suspensions(self):
        return self.ledger.committed["suspensions"]

    async def test_policy_list_is_the_narrow_auto_suspend_set(self):
        self.assertEqual(tuple(self.core.AUTO_SUSPEND_POLICIES), EXPECTED_POLICIES)

    async def test_block_row_and_chain_head_persist_on_the_ordinary_path(self):
        self.assertEqual(await self.core._record_decision(block_event(1)), 1)
        self.assertEqual([d["decision"] for d in self.decisions()], ["Block"])
        self.assertNotEqual(self.ledger.committed["head"], GENESIS)
        self.assertEqual(self.suspensions(), [])

    async def test_threshold_writes_block_row_then_automatic_suspension_and_record(self):
        await self.core._record_decision(block_event(1))
        await self.core._record_decision(block_event(2))
        self.assertEqual(len(self.decisions()), 2)
        self.assertEqual(len(self.suspensions()), 1)
        event, = self.ledger.committed["events"]
        self.assertEqual((event["kind"], event["outcome"], event["actor"]),
                         ("user-server-suspend", "held", "automatic"))
        self.assertEqual(event["scope"]["violations"], 2)

    async def test_non_counting_block_never_reaches_the_aggregate(self):
        await self.core._record_decision(block_event(1, policy="MCP-REGISTRY-001"))
        self.assertEqual(self.ledger.count_calls, 0)
        self.assertEqual(len(self.decisions()), 1)

    async def test_aggregate_failure_keeps_the_block_row(self):
        await self.core._record_decision(block_event(1))
        self.ledger.count_fails = True
        returned = await self.core._record_decision(block_event(2))  # must neither raise nor drop the row
        self.assertEqual(returned, 2)
        self.assertEqual([d["request_id"] for d in self.decisions()], ["req-1", "req-2"])
        self.assertEqual(self.suspensions(), [])

    async def test_aggregate_failure_leaves_the_decision_blocked_and_is_logged(self):
        self.ledger.count_fails = True
        with self.assertLogs("core_under_test", level="ERROR"):
            await self.core._record_decision(block_event(1))
        self.assertEqual(len(self.decisions()), 1)
        self.assertEqual(self.decisions()[0]["decision"], "Block")

    async def test_failed_check_is_retried_and_the_kept_row_counts_on_the_next_call(self):
        await self.core._record_decision(block_event(1))
        self.ledger.count_fails = True
        await self.core._record_decision(block_event(2))
        self.ledger.count_fails = False
        await self.core._record_decision(block_event(3))
        self.assertEqual(len(self.decisions()), 3)
        self.assertEqual(len(self.suspensions()), 1)
        self.assertEqual(self.ledger.committed["events"][0]["scope"]["violations"], 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
