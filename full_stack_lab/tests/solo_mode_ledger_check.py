"""D-188 보강: root 단독 운영 설정의 기동 관측이 승인 원장에 값이 바뀔 때만 남는지 확인한다.

PostgreSQL 없이 돈다. approval_events를 메모리 목록으로 흉내 내고, review.record_solo_mode_observation과
review.record_event의 실제 코드를 그대로 실행한다. psycopg는 가짜 모듈로 대체한다(게이트웨이 이미지 밖에서도 돈다).
"""
import ast
import asyncio
import importlib.util
import json
import os
import sys
import types
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB / "gateway"))
REVIEW_PATH = LAB / "gateway/app/review.py"
SERVICE_PATH = LAB / "gateway/app/agent_service.py"
SECRET = "sk-test-SENTINEL-0001"  # must never reach the ledger even if it is in the environment


class Jsonb:
    def __init__(self, obj, dumps=None):
        self.obj = obj


class FakeCursor:
    def __init__(self, row=None):
        self.row = row

    async def fetchone(self):
        return self.row


class FakeLedger:
    """approval_events as a list. Only the two statements the observation runs are understood."""

    def __init__(self):
        self.rows = []
        self.fail_insert = False

    @asynccontextmanager
    async def transaction(self):
        yield FakeConnection(self)


class FakeConnection:
    def __init__(self, ledger):
        self.ledger = ledger

    async def execute(self, query, params=None):
        if "pg_advisory_xact_lock" in query:
            return FakeCursor()
        if query.lstrip().startswith("SELECT scope FROM approval_events"):
            matches = [r for r in self.ledger.rows if r["kind"] == "solo-mode" and r["target_id"] == params[0]]
            return FakeCursor({"scope": matches[-1]["scope"]} if matches else None)
        if query.lstrip().startswith("INSERT INTO approval_events"):
            if self.ledger.fail_insert:
                raise OSError("ledger unavailable")
            kind, outcome, target_kind, target_id, actor, applicant, reason, scope = params
            self.ledger.rows.append({"kind": kind, "outcome": outcome, "target_kind": target_kind,
                                     "target_id": target_id, "actor": actor, "applicant": applicant,
                                     "reason": reason, "scope": scope.obj})
            return FakeCursor({"id": len(self.ledger.rows)})
        raise AssertionError(f"unexpected statement: {query[:80]}")


def load_review(ledger):
    stubs = {
        "psycopg": types.ModuleType("psycopg"),
        "psycopg.errors": types.ModuleType("psycopg.errors"),
        "psycopg.types": types.ModuleType("psycopg.types"),
        "psycopg.types.json": types.ModuleType("psycopg.types.json"),
        "app.db": ledger,
        "app.high_impact": types.ModuleType("app.high_impact"),
        "app.provenance": types.ModuleType("app.provenance"),
        "app.classify": types.ModuleType("app.classify"),
    }
    stubs["psycopg.errors"].UniqueViolation = type("UniqueViolation", (Exception,), {})
    stubs["psycopg.types.json"].Jsonb = Jsonb
    stubs["app.classify"].ADDRESS_ARG = None
    with patch.dict(sys.modules, stubs):
        spec = importlib.util.spec_from_file_location("app.review_ledger_check", REVIEW_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def start(review, env_value):
    """One gateway start: the observation runs once per process start, so each call is one start."""
    env = {"ROOT_SOLO_APPROVAL": env_value} if env_value is not None else {}
    with patch.dict(os.environ, env, clear=False):
        if env_value is None:
            os.environ.pop("ROOT_SOLO_APPROVAL", None)
        return asyncio.run(review.record_solo_mode_observation())


class SoloModeLedger(unittest.TestCase):
    def setUp(self):
        self.ledger = FakeLedger()
        self.review = load_review(self.ledger)

    def test_first_start_with_mode_on_writes_one_row(self):
        self.assertTrue(start(self.review, "1"))
        self.assertEqual(len(self.ledger.rows), 1)
        row = self.ledger.rows[0]
        self.assertEqual((row["kind"], row["outcome"], row["target_kind"], row["target_id"], row["actor"]),
                         ("solo-mode", "recorded", "config", "ROOT_SOLO_APPROVAL", "system"))
        self.assertIs(row["scope"]["solo_mode"], True)
        self.assertIsNone(row["scope"]["previous_solo_mode"])

    def test_restart_with_same_value_writes_nothing(self):
        start(self.review, "1")
        self.assertFalse(start(self.review, "1"))
        self.assertFalse(start(self.review, "1"))
        self.assertEqual(len(self.ledger.rows), 1)

    def test_first_start_with_mode_off_is_recorded_too(self):
        self.assertTrue(start(self.review, None))
        self.assertIs(self.ledger.rows[0]["scope"]["solo_mode"], False)
        self.assertFalse(start(self.review, None))
        self.assertEqual(len(self.ledger.rows), 1)

    def test_change_writes_exactly_one_transition_row(self):
        start(self.review, "1")
        self.assertTrue(start(self.review, None))
        self.assertEqual(len(self.ledger.rows), 2)
        transition = self.ledger.rows[1]["scope"]
        self.assertIs(transition["solo_mode"], False)
        self.assertIs(transition["previous_solo_mode"], True)
        self.assertFalse(start(self.review, None))
        self.assertTrue(start(self.review, "1"))
        self.assertEqual(len(self.ledger.rows), 3)
        self.assertIs(self.ledger.rows[2]["scope"]["previous_solo_mode"], False)

    def test_only_the_boolean_is_stored_not_the_raw_value_or_secrets(self):
        with patch.dict(os.environ, {"TEST_TOKEN_FOR_CHECK": SECRET}):
            start(self.review, "1")
        dumped = json.dumps(self.ledger.rows, ensure_ascii=False)
        self.assertNotIn(SECRET, dumped)
        self.assertNotIn("ROOT_SOLO_APPROVAL=", dumped)
        self.assertIs(self.ledger.rows[0]["scope"]["solo_mode"], True)  # a bool, not the string "1"
        self.assertEqual(set(self.ledger.rows[0]["scope"]), {"solo_mode", "previous_solo_mode", "observed_at"})
        self.assertIsNone(self.ledger.rows[0]["applicant"])

    def test_observation_never_updates_or_deletes_ledger_rows(self):
        source = REVIEW_PATH.read_text(encoding="utf-8")
        node = next(n for n in ast.parse(source).body
                    if isinstance(n, ast.AsyncFunctionDef) and n.name == "record_solo_mode_observation")
        body = ast.get_source_segment(source, node)
        self.assertNotIn("UPDATE", body)
        self.assertNotIn("DELETE", body)

    def test_ledger_write_failure_propagates_to_the_caller(self):
        self.ledger.fail_insert = True
        with self.assertRaises(OSError):
            start(self.review, "1")

    def test_startup_wraps_the_observation_so_failure_is_logged_not_fatal(self):
        tree = ast.parse(SERVICE_PATH.read_text(encoding="utf-8"))
        lifespan = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "lifespan")
        tries = [n for n in ast.walk(lifespan) if isinstance(n, ast.Try)
                 and "record_solo_mode_observation" in "".join(ast.unparse(s) for s in n.body)]
        self.assertEqual(len(tries), 1, "record_solo_mode_observation must be called inside one try block")
        handler = tries[0].handlers[0]
        self.assertIsNotNone(handler.type)
        self.assertEqual(ast.unparse(handler.type), "Exception")
        self.assertIn("LOG.exception", ast.unparse(handler))
        self.assertNotIn("raise", ast.unparse(handler))


if __name__ == "__main__":
    unittest.main()
