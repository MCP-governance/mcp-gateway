"""Server consent regression with production AST bodies and an isolated DB double.

No MCP server, PostgreSQL, or live harness is started. Existing tests remain unchanged.
"""
from __future__ import annotations

import ast
import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

APP = Path(__file__).resolve().parents[1] / "gateway" / "app"
PERSON = {"token": "employee", "role": "employee"}
ITEM = {"purpose": "문서 확인", "consent": True, "grade": "public", "destinations": []}


def definitions(path, namespace):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    tree.body = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Assign))]
    exec(compile(tree, str(path), "exec"), namespace)
    return SimpleNamespace(**namespace)


class Database:
    """Models unique rows and transaction rollback, not PostgreSQL locking semantics."""
    def __init__(self):
        self.rows, self.events, self.queries = [], [], []
        self.lock = asyncio.Lock()
        self.fail_insert = None
        self.fail_event = None

    @asynccontextmanager
    async def transaction(self):
        async with self.lock:
            before = deepcopy((self.rows, self.events))
            try:
                yield self
            except BaseException:
                self.rows, self.events = before
                raise

    async def fetch_all(self, sql, args):
        self.queries.append((sql, args))
        if "SELECT grade, status" in sql:
            return [deepcopy(r) for r in self.rows if
                    (r["user_token"], r["server_id"], r["tool_name"], r["terms_hash"]) == tuple(args)
                    and (r["status"] != "GRANTED" or r["live"])]
        if "FROM user_consents WHERE user_token" in sql:
            return [deepcopy(r) for r in self.rows if r["user_token"] == args[0]]
        raise AssertionError(sql)

    async def execute(self, sql, args):
        self.queries.append((sql, args))
        await asyncio.sleep(0)
        if "INSERT INTO user_consents" in sql:
            user, server, tool, grade, terms, purpose, scope = args[:7]
            if tool == self.fail_insert:
                raise RuntimeError("synthetic DB failure")
            assert "WHERE NOT EXISTS" in sql and "grade=ANY(%s)" in sql
            assert "user_consents.status='REVOKED'" in sql and "expires_at <= now()" in sql
            assert tuple(args[7:11]) == (user, server, tool, terms)
            covering = [r for r in self.rows if (r["user_token"], r["server_id"], r["tool_name"], r["terms_hash"])
                        == (user, server, tool, terms) and r["grade"] in args[11]
                        and r["status"] == "GRANTED" and r["live"]]
            if covering:
                return SimpleNamespace(rowcount=0)
            key = (user, server, tool, grade, terms)
            row = next((r for r in self.rows if tuple(r[k] for k in
                       ("user_token", "server_id", "tool_name", "grade", "terms_hash")) == key), None)
            if row:
                if row["status"] == "REVOKED" or row["status"] == "GRANTED" and not row["live"]:
                    row.update(status="PENDING", live=False)
            else:
                self.rows.append(dict(id=len(self.rows) + 1, user_token=user, server_id=server,
                                      tool_name=tool, grade=grade, terms_hash=terms, purpose=purpose,
                                      terms=scope, status="PENDING", live=False))
            return SimpleNamespace(rowcount=1)
        if sql.lstrip().startswith("SELECT id"):
            server, user, ids, states = args
            assert "FOR UPDATE" in sql and "ORDER BY tool_name" in sql
            found = [r for r in self.rows if r["server_id"] == server and r["user_token"] == user
                     and r["id"] in ids and r["status"] in states]
            return SimpleNamespace(fetchall=AsyncMock(return_value=deepcopy(found)))
        if sql.lstrip().startswith("UPDATE user_consents"):
            status, grant, days, server, user, ids, states = args
            assert "status=ANY(%s)" in sql and status == grant and days > 0
            found = [r for r in self.rows if r["server_id"] == server and r["user_token"] == user
                     and r["id"] in ids and r["status"] in states]
            for row in found:
                row.update(status=status, live=status == "GRANTED", expires_at=days if status == "GRANTED" else None)
            return SimpleNamespace(fetchall=AsyncMock(return_value=deepcopy(found)))
        raise AssertionError(sql)

    async def record_event(self, *args, **kwargs):
        assert kwargs.pop("connection") is self
        if len(self.events) == self.fail_event:
            raise RuntimeError("synthetic audit failure")
        self.events.append((args, kwargs))


class Checks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = Database()
        self.spec = {"tools": {f"tool{i}": "r" for i in range(6)},
                     "tool_reviews": {f"tool{i}": dict(ITEM, purpose=f"문서 확인 {i}") for i in range(6)}}
        self.allowed, self.hidden, self.unreviewed = None, set(), set()
        self.registry = SimpleNamespace(
            server=lambda server: self.spec if server == "files" else None,
            permits=lambda allowed, token: allowed is None or "*" in allowed or token in allowed, ALL_PRINCIPALS="*", allowed_principals=lambda server: self.allowed,
            reviewed_tools=lambda server: set(self.spec["tools"]) - self.unreviewed)
        self.consent = definitions(APP / "consent.py", {
            "os": os, "db": self.db, "registry": self.registry,
            "pac": SimpleNamespace(visible=lambda person, server, tool, action: tool not in self.hidden),
            "review": SimpleNamespace(scope_terms=lambda item: {k: v for k, v in item.items()
                                        if k not in {"reviewed_by", "reviewed_at"}}, record_event=self.db.record_event),
            "canonical_hash": lambda obj: hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest(),
            "Jsonb": lambda obj: obj,
        })

    async def missing(self, grade="nonimportant", tool="tool0"):
        return await self.consent.missing("employee", "files", tool, grade,
                                          self.spec["tool_reviews"][tool], principal=PERSON)

    async def decide(self, decision="grant", ids=None, user="employee", server="files"):
        return await self.consent.decide_server(server, ids if ids is not None else [r["id"] for r in self.db.rows],
                                                user, decision)

    async def test_first_block_queues_six_distinct_tool_terms_without_grants(self):
        self.assertIn("동의", await self.missing())
        self.assertEqual(len(self.db.rows), 6)
        self.assertEqual({r["status"] for r in self.db.rows}, {"PENDING"})
        self.assertEqual(len({r["terms_hash"] for r in self.db.rows}), 6)
        self.assertFalse(self.db.events)

    async def test_repeated_concurrent_requests_do_not_duplicate(self):
        await asyncio.gather(*(self.missing(tool=f"tool{i % 6}") for i in range(12)))
        self.assertEqual(len(self.db.rows), 6)

    async def test_only_permitted_reviewed_consent_tools_are_queued(self):
        self.hidden.add("tool1")
        self.unreviewed.add("tool2")
        self.spec["tool_reviews"]["tool3"]["consent"] = False
        self.spec["tool_reviews"].pop("tool4")
        self.spec["tool_reviews"]["outside"] = ITEM
        await self.missing()
        self.assertEqual({r["tool_name"] for r in self.db.rows}, {"tool0", "tool5"})

    async def test_no_requests_for_other_principal_or_unknown_server(self):
        self.allowed = ["other"]
        await self.consent.request_server(PERSON, "files", "public")
        self.allowed = None
        await self.consent.request_server(PERSON, "other", "public")
        self.assertEqual(self.db.rows, [])

    async def test_mismatched_principal_is_rejected(self):
        with self.assertRaises(ValueError):
            await self.consent.missing("other", "files", "tool0", "public", ITEM, principal=PERSON)
        self.assertFalse(self.db.rows)

    async def test_unknown_grade_is_important_for_every_tool(self):
        await self.missing("unknown")
        self.assertEqual({r["grade"] for r in self.db.rows}, {"important"})

    async def test_one_grant_covers_six_calls_and_appends_six_tool_events(self):
        await self.missing()
        rows = await self.decide()
        self.assertEqual(len(rows), 6)
        for tool in self.spec["tools"]:
            self.assertIsNone(await self.missing(tool=tool))
        self.assertEqual(len(self.db.events), 6)
        for row, (args, event) in zip(self.db.rows, self.db.events):
            self.assertEqual(args, ("user-consent", "approved", "consent", row["id"], "employee"))
            self.assertEqual(event["scope"], {"server": "files", "tool": row["tool_name"],
                             "grade": row["grade"], "terms": row["terms_hash"], "status": "GRANTED"})

    async def test_deny_keeps_all_calls_blocked_without_reopening(self):
        await self.missing()
        await self.decide("deny")
        for tool in self.spec["tools"]:
            self.assertIn("동의하지 않았", await self.missing(tool=tool))
        self.assertEqual({r["status"] for r in self.db.rows}, {"DENIED"})
        self.assertEqual(len(self.db.rows), 6)
        self.assertEqual({args[1] for args, _ in self.db.events}, {"rejected"})

    async def test_batch_does_not_reopen_existing_denial_or_live_higher_grant(self):
        await self.missing("important")
        await self.decide()
        self.db.rows[0].update(status="DENIED", live=False)
        self.db.rows[1].update(status="REVOKED", live=False)
        await self.missing("public", "tool1")
        self.assertEqual(len(self.db.rows), 8)
        self.assertEqual(self.db.rows[0]["status"], "DENIED")
        self.assertEqual(self.db.rows[2]["status"], "GRANTED")

    async def test_terms_change_and_grade_increase_require_fresh_consent(self):
        await self.missing("public")
        await self.decide()
        self.spec["tool_reviews"]["tool0"]["purpose"] = "다른 목적"
        self.assertIn("동의", await self.missing("public"))
        self.assertEqual(len(self.db.rows), 7)
        self.assertIn("동의", await self.missing("important", "tool1"))
        self.assertEqual(len(self.db.rows), 13)
        self.assertEqual(len(self.db.events), 6)

    async def test_expiry_and_revocation_requeue_without_grant(self):
        await self.missing()
        await self.decide()
        self.db.rows[0]["live"] = False
        self.db.rows[1].update(status="REVOKED", live=False)
        await self.missing()
        self.assertEqual([r["status"] for r in self.db.rows[:3]], ["PENDING", "PENDING", "GRANTED"])

    async def test_unseen_new_request_is_not_approved_by_old_snapshot(self):
        await self.missing()
        ids = [r["id"] for r in self.db.rows]
        self.spec["tools"]["new_tool"] = "r"
        self.spec["tool_reviews"]["new_tool"] = dict(ITEM)
        await self.missing()
        await self.decide(ids=ids)
        self.assertEqual(self.db.rows[-1]["status"], "PENDING")

    async def test_wrong_owner_server_missing_stale_duplicate_empty_ids_have_no_partial_effect(self):
        await self.missing()
        for kwargs in ({"user": "other"}, {"server": "other"}, {"ids": [1, 99]},
                       {"ids": [1, 1]}, {"ids": []}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                await self.decide(**kwargs)
        await self.decide(ids=[1])
        with self.assertRaises(ValueError):
            await self.decide()
        self.assertEqual(len(self.db.events), 1)
        self.assertEqual(self.db.rows[1]["status"], "PENDING")

    async def test_conflicting_decisions_only_one_commits(self):
        await self.missing()
        result = await asyncio.gather(self.decide("grant"), self.decide("deny"), return_exceptions=True)
        self.assertEqual(sum(isinstance(r, ValueError) for r in result), 1)
        self.assertEqual(len(self.db.events), 6)

    async def test_audit_failure_rolls_back_every_tool_and_event(self):
        await self.missing()
        self.db.fail_event = 2
        with self.assertRaises(RuntimeError):
            await self.decide()
        self.assertEqual({r["status"] for r in self.db.rows}, {"PENDING"})
        self.assertFalse(self.db.events)

    async def test_request_failure_rolls_back_all_pending_rows(self):
        self.db.fail_insert = "tool3"
        with self.assertRaises(RuntimeError):
            await self.missing()
        self.assertFalse(self.db.rows)

    async def test_failed_storage_recovers_to_pending_then_requires_explicit_grant(self):
        self.db.fail_insert = "tool3"
        with self.assertRaises(RuntimeError):
            await self.missing()
        self.db.fail_insert = None
        self.assertIn("동의", await self.missing())
        self.assertEqual({r["status"] for r in self.db.rows}, {"PENDING"})
        await self.decide()
        self.assertIsNone(await self.missing())

    async def test_cancellation_during_audit_rolls_back_and_releases_transaction(self):
        await self.missing()
        entered, release = asyncio.Event(), asyncio.Event()
        original = self.consent.decide_server.__globals__["review"].record_event

        async def pause(*args, **kwargs):
            entered.set()
            await release.wait()
            return await original(*args, **kwargs)

        self.consent.decide_server.__globals__["review"].record_event = pause
        task = asyncio.create_task(self.decide())
        try:
            await asyncio.wait_for(entered.wait(), 1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        finally:
            self.consent.decide_server.__globals__["review"].record_event = original
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.assertEqual({r["status"] for r in self.db.rows}, {"PENDING"})
        self.assertFalse(self.db.events)
        self.assertEqual(len(await self.decide()), 6)

    async def test_list_does_not_truncate_a_server_at_200_rows(self):
        self.db.rows = [dict(id=i, user_token="employee") for i in range(201)]
        self.assertEqual(len(await self.consent.mine("employee")), 201)
        self.assertNotIn("LIMIT 200", self.db.queries[-1][0])

    async def test_actual_core_gate_decision_policy_and_storage_failure(self):
        tree = ast.parse((APP / "core.py").read_text(encoding="utf-8"))
        gate = next(n for n in ast.walk(tree) if isinstance(n, ast.If) and
                    'result[\'decision\']' in ast.unparse(n.test) and
                    'tool_review.get(\'consent\')' in ast.unparse(n.test))
        body = ast.unparse(gate)
        namespace = dict(consent=self.consent, tool_review=self.spec["tool_reviews"]["tool0"],
                         user_token="employee", server_id="files", tool="tool0", principal=PERSON,
                         cls=SimpleNamespace(data_class="nonimportant"), base_event={},
                         span=SimpleNamespace(set_attribute=lambda *args: None), _root_cause=str,
                         local_verdict=lambda policy, decision, reason, **kw: dict(policy_id=policy, decision=decision))
        exec("async def gate(result):\n" + "\n".join("    " + line for line in body.splitlines()) +
             "\n    return result\n", namespace)
        for decision in ("Allow", "Alert", "Restrict"):
            result = await namespace["gate"]({"decision": decision, "policy_id": "original"})
            self.assertEqual(result, {"decision": "Block", "policy_id": "P-CONSENT-001"})
        result = await namespace["gate"]({"decision": "Block", "policy_id": "original"})
        self.assertEqual(result["policy_id"], "original")
        await self.decide()
        self.assertEqual((await namespace["gate"]({"decision": "Allow", "policy_id": "original"}))["decision"], "Allow")
        self.db.rows.clear()
        self.db.fail_insert = "tool3"
        self.assertEqual(await namespace["gate"]({"decision": "Allow"}),
                         {"decision": "Block", "policy_id": "P-CONTROL-FAIL-CLOSED"})
        self.assertFalse(self.db.rows)

    async def test_api_uses_authenticated_principal_and_returns_conflict(self):
        tree = ast.parse((APP / "agent_service.py").read_text(encoding="utf-8"))
        handler = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "decide_server_consent")
        handler.decorator_list = []

        class HTTPException(Exception):
            def __init__(self, status_code, detail):
                self.status_code, self.detail = status_code, detail

        namespace = dict(consent=self.consent, current_identity=AsyncMock(return_value={"principal": "employee"}),
                         HTTPException=HTTPException, ServerConsentDecision=object, Header=lambda **kw: None)
        exec(compile(ast.Module(body=[handler], type_ignores=[]), str(APP / "agent_service.py"), "exec"), namespace)
        await self.missing()
        request = SimpleNamespace(consent_ids=[r["id"] for r in self.db.rows], decision="grant")
        result = await namespace["decide_server_consent"]("files", request, "transport-credential")
        self.assertEqual(len(result["consents"]), 6)
        namespace["current_identity"].assert_awaited_once_with("transport-credential")
        with self.assertRaises(HTTPException) as error:
            await namespace["decide_server_consent"]("files", request)
        self.assertEqual(error.exception.status_code, 409)


def load_tests(loader, tests, pattern):
    # Execute the original four consent tests without optional Gateway imports or edits.
    legacy = APP.parents[1] / "tests" / "remaining_controls_check.py"
    tree = ast.parse(legacy.read_text(encoding="utf-8"))
    selected = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ConsentTest")
    fixture = Checks()
    fixture.setUp()
    from unittest.mock import patch
    base = next(n for n in tree.body if isinstance(n, ast.Assign) and
                any(isinstance(t, ast.Name) and t.id == "BASE" for t in n.targets))
    namespace = dict(unittest=unittest, asyncio=asyncio, AsyncMock=AsyncMock, patch=patch, consent=fixture.consent)
    exec(compile(ast.Module(body=[base, selected], type_ignores=[]), str(legacy), "exec"), namespace)
    tests.addTests(loader.loadTestsFromTestCase(namespace["ConsentTest"]))
    return tests


if __name__ == "__main__":
    unittest.main(verbosity=2)
