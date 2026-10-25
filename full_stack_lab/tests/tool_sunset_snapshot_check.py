"""Batched sunset regression checks; standard library only."""
from __future__ import annotations

import asyncio
import ast
import copy
import importlib.util
import logging
import random
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock
from tool_sunset_check import load_module

APP = Path(__file__).resolve().parents[1] / "gateway" / "app"
NOW = datetime(2026, 10, 21, 9, tzinfo=timezone.utc)

# The pre-refactor rule is kept independent of the new batch implementation.
async def legacy_check(server_id: str, tool_name: str, now: datetime | None = None) -> dict:
    """Record extensions or sunset atomically; uncertainty always leaves the tool usable."""
    now = now or datetime.now(timezone.utc)
    spec = registry.server(server_id) or {}
    tool_review = (spec.get("tool_reviews") or {}).get(tool_name)
    if not tool_review:
        return {"active": True, "eligible": False, "last_use": None, "deadline": None, "status": "미심사"}
    reviewed_text = tool_review.get("reviewed_at")
    try:
        reviewed_at = datetime.fromisoformat(str(reviewed_text).replace("Z", "+00:00"))
        # Read before taking the transaction's connection: a second pool connection per check deadlocked
        # the pool when a harness listed ten servers at once.
        setting = await retention.setting()
        async with db.transaction() as connection:
            key = target_id(server_id, tool_name)
            await connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (key,))
            event = await _last_event(connection, server_id, tool_name)
            if event and event["kind"] == "tool-sunset" and event["outcome"] == "held":
                return {"active": False, "available": True, "eligible": True,
                        "last_use": event["scope"].get("last_use"),
                        "deadline": event["scope"].get("deadline"), "status": "재심사 필요"}
            cutoff = now - timedelta(days=max(IDLE_DAYS + GRACE_DAYS, OBSERVATION_DAYS))
            covered, coverage_reason = await _coverage(connection, cutoff, setting)
            if not covered:
                check_event = await _last_check(connection, server_id, tool_name)
                if not check_event or check_event["scope"].get("window_start") != cutoff.isoformat():
                    await review.record_event(
                        "tool-sunset-check", "recorded", TARGET, key, "automatic", reason=coverage_reason,
                        scope={"server": server_id, "tool": tool_name, "window_start": cutoff.isoformat(),
                               "observation_days": OBSERVATION_DAYS, "idle_days": IDLE_DAYS,
                               "grace_days": GRACE_DAYS}, connection=connection)
                return {"active": True, "available": True, "eligible": True, "last_use": None, "deadline": None,
                        "status": "자료 없음", "reason": coverage_reason}
            row = await (await connection.execute(
                """SELECT max(created_at) AS last_use FROM decisions
                     WHERE server_id=%s AND tool_name=%s AND upstream_executed
                       AND created_at <= %s
                       AND COALESCE(client->>'event_kind','tools/call')='tools/call'""",
                (server_id, tool_name, now))).fetchone()
            last_use = row["last_use"] if row else None
            result = evaluate(reviewed_at, last_use, now)
            key = target_id(server_id, tool_name)
            if result["expired"]:
                scope = {"server": server_id, "tool": tool_name,
                         "last_use": last_use.isoformat() if last_use else None,
                         "observation_days": OBSERVATION_DAYS, "idle_days": IDLE_DAYS,
                         "grace_days": GRACE_DAYS, "window_start": cutoff.isoformat(),
                         "inactive_at": result["inactive_at"].isoformat(), "deadline": result["deadline"].isoformat()}
                await review.record_event("tool-sunset", "held", TARGET, key, "automatic",
                                          reason="도구 이용 기한 만료", scope=scope, connection=connection)
                return {"active": False, "available": True, "eligible": True, **result, "status": "재심사 필요"}
            # The deadline moves with every call by seconds; one extension a day per tool is the record worth keeping
            # (an event per call grew the ledger by the call count). The decision still uses the exact last use.
            if result["recent"] and last_use and (not event or event["kind"] != "tool-sunset-extension"
                                                   or str(event["scope"].get("deadline") or "")[:10]
                                                   != result["deadline"].astimezone(timezone.utc).date().isoformat()):
                scope = {"server": server_id, "tool": tool_name, "last_use": last_use.isoformat(),
                         "observation_days": OBSERVATION_DAYS, "idle_days": IDLE_DAYS, "grace_days": GRACE_DAYS,
                         "window_start": cutoff.isoformat(), "deadline": result["deadline"].isoformat(),
                         "previous_deadline": (event or {}).get("scope", {}).get("deadline") or
                                              (reviewed_at + timedelta(days=IDLE_DAYS)).isoformat()}
                await review.record_event("tool-sunset-extension", "approved", TARGET, key, "automatic",
                                          reason="관측 기간 안에 이용 이력이 있습니다.", scope=scope, connection=connection)
            return {"active": True, "available": True, "eligible": True, **result, "status": "사용 가능"}
    except Exception as exc:
        try:
            await review.record_event(
                "tool-sunset-check", "recorded", TARGET, target_id(server_id, tool_name), "automatic",
                reason=type(exc).__name__, scope={"server": server_id, "tool": tool_name,
                                                  "observation_days": OBSERVATION_DAYS})
        except Exception:
            logger.exception("도구 이용 상태 확인 실패를 기록하지 못했습니다: %s/%s", server_id, tool_name)
        return {"active": True, "available": False, "eligible": True, "last_use": None, "deadline": None,
                "status": "자료 없음", "reason": type(exc).__name__}


async def legacy_coverage(connection, cutoff, setting):
    if max(IDLE_DAYS + GRACE_DAYS, OBSERVATION_DAYS) > int(setting["days"]):
        return False, "미사용 판정 기간이 원장 보존 기간보다 깁니다."
    seal = retention.current_seal()
    if seal:
        if datetime.fromisoformat(str(seal["last_created_at"]).replace("Z", "+00:00")) >= cutoff:
            return False, "관측 창 일부가 폐기된 원장 구간과 겹칩니다."
    else:
        row = await (await connection.execute(
            "SELECT a.entries, (SELECT count(*) FROM decisions) AS retained FROM audit_chain a WHERE a.id=1"
        )).fetchone()
        if row and int(row["entries"]) != int(row["retained"]):
            return False, "원장 봉인 자료를 확인할 수 없습니다."
    return True, ""


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def fetchone(self):
        return self.rows[0] if self.rows else None

    async def fetchall(self):
        return self.rows


class Transaction:
    def __init__(self, connection, outer=False):
        self.connection, self.outer = connection, outer

    async def __aenter__(self):
        if self.outer:
            self.connection.transactions += 1
        self.before = len(self.connection.events)
        return self.connection

    async def __aexit__(self, exc_type, *_args):
        if exc_type or (self.outer and self.connection.fail_commit):
            del self.connection.events[self.before:]
        if self.outer and self.connection.fail_commit:
            raise RuntimeError("commit unavailable")
        return False


class Connection:
    def __init__(self, uses=None, events=None, entries=0, retained=0):
        self.uses, self.events = uses or {}, copy.deepcopy(events or [])
        self.entries, self.retained = entries, retained
        self.queries, self.transactions = [], 0
        self.fail, self.fail_event, self.fail_commit = None, None, False

    def transaction(self):
        return Transaction(self)

    async def execute(self, query, params=None):
        self.queries.append(query)
        if self.fail and self.fail in query:
            raise RuntimeError("synthetic read failure")
        if "approval_events" in query:
            targets = params[1] if isinstance(params[1], list) else [params[1]]
            kinds = params[2] if "kind=ANY" in query else ["tool-sunset-check"]
            rows = {}
            for event in self.events:
                if event["target_id"] in targets and event["kind"] in kinds:
                    rows[event["target_id"]] = event
            return Cursor(list(rows.values()))
        if "audit_chain" in query:
            return Cursor([{"entries": self.entries, "retained": self.retained}])
        if "max(created_at)" in query:
            names = params[1] if isinstance(params[1], list) else [params[1]]
            rows = [{"tool_name": name, "last_use": self.uses.get(name)} for name in names
                    if self.uses.get(name) is None or self.uses[name] <= params[2]]
            return Cursor(rows)
        return Cursor([])

    async def record_event(self, kind, outcome, target_kind, target_id, actor, **kwargs):
        if target_id == self.fail_event:
            self.events.append({"rolled_back": True})
            raise RuntimeError("synthetic append failure")
        self.events.append({"kind": kind, "outcome": outcome, "target_kind": target_kind,
                            "target_id": target_id, "actor": actor, "reason": kwargs.get("reason"),
                            "scope": copy.deepcopy(kwargs.get("scope", {})), "created_at": NOW})


def fixture(reviews, connection=None, *, days=366, seal=None):
    module, ports = load_module()
    connection = connection or Connection()
    ports.registry.server = lambda _server: {"tool_reviews": reviews}
    ports.retention.setting = AsyncMock(return_value={"days": days})
    ports.retention.current_seal = lambda: seal
    ports.review.record_event = connection.record_event
    ports.db.transaction = lambda: Transaction(connection, outer=True)
    return module, ports, connection


def review_at(at):
    return {"reviewed_at": at.isoformat()}


def old_checker(module):
    namespace = dict(module.__dict__)
    namespace["_coverage"] = types.FunctionType(legacy_coverage.__code__, namespace)
    return types.FunctionType(legacy_check.__code__, namespace, argdefs=(None,))


class SnapshotCheck(unittest.TestCase):
    def test_list_uses_one_server_transaction_and_constant_queries(self):
        async def run(count):
            reviews = {f"tool{i}": review_at(NOW) for i in range(count)}
            module, ports, connection = fixture(reviews)
            rows = [{"server_id": "srv", "name": name, "action": "r", "description": name,
                     "display_name": "server", "input_schema": {}, "output_schema": None} for name in reviews]
            namespace = {
                "types": types.SimpleNamespace(Tool=lambda **kw: types.SimpleNamespace(**kw)),
                "db": types.SimpleNamespace(fetch_all=AsyncMock(return_value=rows),
                                            fetch_one=AsyncMock(return_value={"role": "user"})),
                "registry": types.SimpleNamespace(permits=lambda *_: True, allowed_principals=lambda _: None,
                                                  reviewed_tools=lambda _: set(reviews)),
                "pac": types.SimpleNamespace(visible=lambda *_: True), "tool_sunset": module,
                "output_contract": types.SimpleNamespace(JSON_PROTOCOLS=set(), OBJECT_PROTOCOLS=set()),
                "logger": logging.getLogger("snapshot"), "SEPARATOR": "__"}
            tree = ast.parse((APP / "mcp_facade.py").read_text(encoding="utf-8"))
            node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "_approved_tools")
            exec(compile(ast.Module(body=[node], type_ignores=[]), "facade", "exec"), namespace)
            result = await namespace["_approved_tools"]("user", principal="employee")
            self.assertEqual(len(result), count)
            self.assertEqual(connection.transactions, 1)
            self.assertEqual(ports.retention.setting.await_count, 1)
            self.assertEqual(sum("count(*)" in q for q in connection.queries), 1)
            self.assertEqual(sum("max(created_at)" in q for q in connection.queries), 1)
            self.assertEqual(sum("approval_events" in q for q in connection.queries), 2)
            original, old_ports, old_connection = fixture(reviews)
            for name in reviews:
                await old_checker(original)("srv", name, NOW)
            self.assertEqual(old_connection.transactions, count)
            self.assertEqual(len(old_connection.queries), 4 * count)
            self.assertEqual(old_ports.retention.setting.await_count, count)
            return len(connection.queries)
        self.assertEqual([asyncio.run(run(n)) for n in (1, 10, 100)], [6, 6, 6])

    def test_randomized_50_snapshots_match_original_and_single_checks(self):
        async def run():
            rng = random.Random(243247)
            for case in range(50):
                with self.subTest(case=case):
                    reviews, uses, events = {}, {}, []
                    for i in range(10):
                        name = f"tool{i}"
                        reviews[name] = review_at(NOW - timedelta(days=rng.randrange(250)))
                        uses[name] = (NOW - timedelta(days=rng.randrange(200))) if rng.choice([True, False]) else None
                        kind = rng.choice([None, "tool-sunset", "tool-sunset-extension", "tool-sunset-review"])
                        if kind:
                            events.append({"target_id": f"srv/{name}", "kind": kind,
                                           "outcome": "held" if kind == "tool-sunset" else "approved",
                                           "scope": {"last_use": None,
                                                     "deadline": (NOW + timedelta(days=rng.randrange(-10, 150))).isoformat()}})
                        if rng.choice([True, False]):
                            events.append({"target_id": f"srv/{name}", "kind": "tool-sunset-check",
                                           "outcome": "recorded", "scope": {"window_start":
                                           (NOW - timedelta(days=rng.choice([120, 121]))).isoformat()}})
                    days = rng.choice([60, 366])
                    seal = rng.choice([None, {"last_created_at": (NOW - timedelta(days=100)).isoformat()},
                                       {"last_created_at": (NOW - timedelta(days=200)).isoformat()}])
                    modules = [fixture(reviews, Connection(uses, events), days=days, seal=seal) for _ in range(3)]
                    batch = await modules[0][0].check_many("srv", list(reviews), NOW)
                    singles = {name: await modules[1][0].check("srv", name, NOW) for name in reviews}
                    original = {name: await old_checker(modules[2][0])("srv", name, NOW) for name in reviews}
                    self.assertEqual(batch, original)
                    self.assertEqual(singles, original)
                    appended = [m[2].events[len(events):] for m in modules]
                    self.assertEqual(appended[0], appended[2])
                    self.assertEqual(appended[1], appended[2])
        asyncio.run(run())

    def test_cache_versions_and_absolute_boundaries(self):
        async def run():
            reviews = {"a": review_at(NOW - timedelta(days=90) + timedelta(hours=1))}
            module, ports, connection = fixture(reviews)
            async def read(at, hit):
                before = sum("approval_events" in q for q in connection.queries)
                state = (await module.check_many("srv", ["a"], at))["a"]
                after = sum("approval_events" in q for q in connection.queries)
                self.assertEqual(after == before, hit)
                return state
            await read(NOW, False)
            await read(NOW + timedelta(minutes=1), True)
            reviews["a"] = review_at(NOW - timedelta(days=90) + timedelta(hours=2))
            await read(NOW + timedelta(minutes=2), False)
            ports.retention.current_seal = lambda: {"last_id": 1, "last_created_at": (NOW - timedelta(days=200)).isoformat()}
            await read(NOW + timedelta(minutes=3), False)
            ports.retention.setting.return_value = {"days": 400}
            await read(NOW + timedelta(minutes=4), False)
            await read(NOW + timedelta(hours=2), False)
            midnight = NOW.replace(hour=0) + timedelta(days=1)
            await read(midnight - timedelta(microseconds=1), True)
            await read(midnight, False)
            await read(midnight + timedelta(seconds=1), True)
            expired = await read(NOW + timedelta(days=30, hours=2), False)
            self.assertFalse(expired["active"])
            held = await read(NOW + timedelta(days=300), True)
            self.assertEqual(held["status"], "재심사 필요")
            await module.approve_review("srv", ["a"], "reviewer")
            reviews["a"] = review_at(NOW + timedelta(days=300))
            self.assertTrue((await read(NOW + timedelta(days=300), False))["active"])
        asyncio.run(run())

    def test_unsealed_entries_and_coverage_proof_memo(self):
        async def run():
            module, _, connection = fixture({"a": review_at(NOW)})
            await module.check_many("srv", ["a"], NOW)
            await module.check_many("srv", ["a"], NOW + timedelta(minutes=1))
            self.assertEqual(sum("count(*)" in q for q in connection.queries), 1)
            connection.entries = connection.retained = 1
            await module.check_many("srv", ["a"], NOW + timedelta(minutes=2))
            self.assertEqual(sum("count(*)" in q for q in connection.queries), 2)
            self.assertEqual(sum("max(created_at)" in q for q in connection.queries), 2)
        asyncio.run(run())

    def test_missing_evidence_and_exceptions_never_cache(self):
        async def run():
            for mode in ("short", "gap", "read", "date", "missing", "commit"):
                with self.subTest(mode=mode):
                    reviews = {"a": review_at(NOW)}
                    module, ports, connection = fixture(reviews)
                    if mode == "short":
                        ports.retention.setting.return_value = {"days": 30}
                    elif mode == "gap":
                        connection.entries = 1
                    elif mode == "read":
                        connection.fail = "max(created_at)"
                    elif mode == "commit":
                        connection.fail_commit = True
                    elif mode == "date":
                        reviews["a"]["reviewed_at"] = "invalid"
                    else:
                        reviews["a"] = {"action": "r"}
                    for _ in range(2):
                        state = (await module.check_many("srv", ["a"], NOW))["a"]
                        self.assertTrue(state["active"])
                        self.assertEqual(state["status"], "자료 없음")
                        self.assertFalse(module._states)
                    self.assertEqual(len(connection.events), 1 if mode in ("short", "gap") else 2)
        asyncio.run(run())

    def test_bad_tool_and_failed_append_do_not_hide_neighbors(self):
        async def run():
            reviews = {"bad-date": {"reviewed_at": "invalid"}, "bad-append": review_at(NOW - timedelta(days=200)),
                       "good": review_at(NOW), "other": review_at(NOW)}
            module, _, connection = fixture(reviews)
            real_record = connection.record_event
            async def record(*args, **kwargs):
                connection.fail_event = "srv/bad-append" if kwargs.get("connection") else None
                return await real_record(*args, **kwargs)
            module.review.record_event = record
            states = await module.check_many("srv", list(reviews), NOW)
            self.assertFalse(states["bad-date"]["available"])
            self.assertFalse(states["bad-append"]["available"])
            self.assertTrue(states["good"]["available"])
            self.assertTrue(states["other"]["available"])
            self.assertFalse(any("rolled_back" in event for event in connection.events))
            self.assertEqual(connection.transactions, 1)
        asyncio.run(run())

    def test_call_bypasses_state_cache_and_new_use_can_invalidate_snapshot(self):
        async def run():
            module, _, connection = fixture({"a": review_at(NOW - timedelta(days=80))})
            await module.check_many("srv", ["a"], NOW)
            connection.uses["a"] = NOW
            state = await module.check("srv", "a", NOW)
            self.assertEqual(state["last_use"], NOW)
            module.invalidate("srv", "a")
            state = (await module.check_many("srv", ["a"], NOW))["a"]
            self.assertEqual(state["last_use"], NOW)
            self.assertEqual(sum("max(created_at)" in q for q in connection.queries), 3)
        asyncio.run(run())

    def test_inflight_invalidation_and_cache_limits(self):
        async def run():
            module, ports, connection = fixture({"a": review_at(NOW)})
            real_setting = ports.retention.setting
            async def setting():
                module.invalidate("srv", "a")
                return await real_setting()
            ports.retention.setting = setting
            await module.check_many("srv", ["a"], NOW)
            self.assertFalse(module._states)
            module.CACHE_LIMIT = 2
            for name in ("a", "b", "c"):
                module._cache_state("srv", name, (), NOW,
                                    {"active": True, "available": True, "status": "사용 가능"})
            self.assertEqual(len(module._states), 2)
            self.assertNotIn(("srv", "a"), module._states)
        asyncio.run(run())

    def test_recent_window_boundary_and_clock_rollback(self):
        async def run():
            module, _, connection = fixture({"a": review_at(NOW)},
                                            Connection({"a": NOW - timedelta(days=30)}))
            first = (await module.check_many("srv", ["a"], NOW))["a"]
            self.assertTrue(first["recent"])
            second = (await module.check_many("srv", ["a"], NOW + timedelta(microseconds=1)))["a"]
            self.assertFalse(second["recent"])
            await module.check_many("srv", ["a"], NOW - timedelta(seconds=1))
            self.assertEqual(sum("max(created_at)" in q for q in connection.queries), 3)
        asyncio.run(run())

    def test_held_precedes_incomplete_coverage_and_proof_recovers_with_time(self):
        async def run():
            event = {"target_id": "srv/held", "kind": "tool-sunset", "outcome": "held", "scope": {}}
            module, ports, connection = fixture({"held": review_at(NOW)}, Connection(events=[event]), days=30)
            self.assertFalse((await module.check_many("srv", ["held"], NOW))["held"]["active"])
            self.assertFalse(any("count(*)" in query for query in connection.queries))
            reviews = {"a": review_at(NOW)}
            seal = {"last_created_at": (NOW - timedelta(days=120)).isoformat()}
            module, _, _ = fixture(reviews, seal=seal)
            self.assertEqual((await module.check_many("srv", ["a"], NOW))["a"]["status"], "자료 없음")
            self.assertEqual((await module.check_many("srv", ["a"], NOW + timedelta(microseconds=1)))["a"]["status"],
                             "사용 가능")
            module, _, connection = fixture({"held": review_at(NOW)}, Connection(events=[event]))
            connection.fail_commit = True
            self.assertFalse((await module.check_many("srv", ["held"], NOW))["held"]["available"])
            self.assertFalse(module._states)
        asyncio.run(run())

    def test_all_sunset_writers_share_lock_order_and_commit_invalidates_use(self):
        async def run():
            module, _, connection = fixture({"b": review_at(NOW), "a": review_at(NOW)})
            await module.check_many("srv", ["b", "a"], NOW)
            await module.approve_review("srv", ["a", "b"], "reviewer")
            locks = [query for query in connection.queries if "pg_advisory_xact_lock" in query]
            self.assertEqual(len(locks), 2)
            self.assertEqual(locks[0], locks[1])
            self.assertIn("ORDER BY lock_key", locks[0])
            self.assertIn("DISTINCT hashtext(key)", locks[0])
            tree = ast.parse((APP / "core.py").read_text(encoding="utf-8"))
            function = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
                            and any(isinstance(n, ast.Call) and ast.unparse(n.func) == "tool_sunset.invalidate"
                                    for n in ast.walk(node)))
            commit = max(i for i, node in enumerate(function.body) if isinstance(node, ast.AsyncWith))
            invalidation = next(i for i, node in enumerate(function.body)
                                if any(isinstance(n, ast.Call) and ast.unparse(n.func) == "tool_sunset.invalidate"
                                       for n in ast.walk(node)))
            self.assertGreater(invalidation, commit)
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()

