"""Checks for refactoring 0-6 (audit R-05/R-14): /api/overview, /api/latency and
/api/health must never touch the judging pool, overview must never hold more than one
admin-pool connection at a time, and all three share a short single-flight cache.

Pure unit tests: app.db's pool functions are patched so no Postgres/OPA/network is
needed, matching the style of tests/ops_response_check.py and tests/data_residency_check.py.
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "gateway"))

from app import cache, db, main, release  # noqa: E402

ADMIN = {"principal": "admin-1", "roles": ["admin"]}


def run(coro):
    return asyncio.run(coro)


class TTLCacheTest(unittest.TestCase):
    def test_single_flight_under_concurrency(self):
        calls = 0

        async def compute():
            nonlocal calls
            calls += 1
            await asyncio.sleep(0)
            return "value"

        async def scenario():
            ttl = cache.TTLCache(5)
            return await asyncio.gather(*(ttl.get("k", compute) for _ in range(10)))

        results = run(scenario())
        self.assertEqual(calls, 1)
        self.assertEqual(results, ["value"] * 10)

    def test_expires_after_ttl_with_injected_clock(self):
        now = [1000.0]
        calls = 0

        async def compute():
            nonlocal calls
            calls += 1
            return calls

        async def scenario():
            ttl = cache.TTLCache(5, clock=lambda: now[0])
            first = await ttl.get("k", compute)
            now[0] += 4.9
            within_ttl = await ttl.get("k", compute)
            now[0] += 0.2  # 5.1s since the first computation
            after_ttl = await ttl.get("k", compute)
            return first, within_ttl, after_ttl

        first, within_ttl, after_ttl = run(scenario())
        self.assertEqual((first, within_ttl, after_ttl), (1, 1, 2))
        self.assertEqual(calls, 2)

    def test_distinct_keys_do_not_share_an_entry(self):
        seen = []

        async def scenario():
            ttl = cache.TTLCache(5)

            async def compute(label):
                seen.append(label)
                return label

            await ttl.get(1, lambda: compute("a"))
            await ttl.get(2, lambda: compute("b"))

        run(scenario())
        self.assertEqual(seen, ["a", "b"])

    def test_failed_computation_is_not_cached(self):
        calls = 0

        async def compute():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("boom")
            return "ok"

        async def scenario():
            ttl = cache.TTLCache(5)
            with self.assertRaises(RuntimeError):
                await ttl.get("k", compute)
            return await ttl.get("k", compute)

        self.assertEqual(run(scenario()), "ok")
        self.assertEqual(calls, 2)

    def test_cancelled_first_caller_releases_waiters(self):
        started = None

        async def slow():
            started.set()
            await asyncio.sleep(10)
            return "never"

        async def scenario():
            nonlocal started
            started = asyncio.Event()
            ttl = cache.TTLCache(5)
            first = asyncio.create_task(ttl.get("k", slow))
            await started.wait()
            waiter = asyncio.create_task(ttl.get("k", slow))
            await asyncio.sleep(0)
            first.cancel()
            done, _ = await asyncio.wait({waiter}, timeout=1)
            self.assertEqual(done, {waiter}, "a waiter on a cancelled computation must not hang")
            with self.assertRaises(asyncio.CancelledError):
                waiter.result()

            async def quick():
                return "ok"
            return await ttl.get("k", quick)

        self.assertEqual(run(scenario()), "ok")


class PolicyInfoCacheScopeTest(unittest.TestCase):
    """Only /api/health reuses policy answers; the policy self-test must see every change."""

    def test_uncached_calls_requery_and_rehash_but_health_reuses(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ("policy.rego", "pac15.rego", "decision.rego", "capabilities.json"):
                (root / name).write_text(name, encoding="utf-8")
            for name in release.POLICY_DATA_FILES:
                (root / name).write_text("{}", encoding="utf-8")
            query = AsyncMock(return_value={"loaded_sha256": None, "loaded_data_sha256": None})
            files = []
            real_cached = release._cached
            release._opa_query_cache = cache.TTLCache(5)
            with patch.object(release, "Path", lambda value: root if value == "/policy" else Path(value)),                  patch.object(release, "_query_opa", query),                  patch.object(release, "_cached", lambda path, loader: files.append(path) or real_cached(path, loader)),                  patch("app.registry.REGISTRY_DIR", root):
                run(release.policy_info("http://opa:8181/v1/data/x"))
                run(release.policy_info("http://opa:8181/v1/data/x"))
                self.assertEqual(query.await_count, 2)
                self.assertEqual(files, [])
                run(release.policy_info("http://opa:8181/v1/data/x", cached=True))
                run(release.policy_info("http://opa:8181/v1/data/x", cached=True))
                self.assertEqual(query.await_count, 3)
                self.assertTrue(files)


class FileHashCacheTest(unittest.TestCase):
    """release._cached() backs the policy-bundle hash in /api/health."""

    def test_rehashes_only_when_mtime_or_size_changes(self):
        calls = 0

        def loader(path):
            nonlocal calls
            calls += 1
            return path.read_text()

        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "bundle.json"
            target.write_text("one")

            self.assertEqual(release._cached(target, loader), "one")
            self.assertEqual(release._cached(target, loader), "one")
            self.assertEqual(calls, 1, "unchanged file must not be re-read")

            # A different length guarantees a (mtime_ns, size) change even if the
            # filesystem's mtime resolution is too coarse to tell two writes apart.
            target.write_text("two-is-longer")
            self.assertEqual(release._cached(target, loader), "two-is-longer")
            self.assertEqual(calls, 2, "a changed file must be re-hashed")


class PoolDefaultsTest(unittest.TestCase):
    """DB_POOL_* defaults must stay what the judging path already runs with."""

    def test_judging_pool_defaults_unchanged(self):
        self.assertEqual(db.POOL_MAX, 10)
        self.assertEqual(db.POOL_TIMEOUT, 10.0)
        self.assertEqual(db.POOL_MAX_WAITING, 0)
        self.assertEqual(db.STATEMENT_TIMEOUT_MS, 0)
        self.assertEqual(db.LOCK_TIMEOUT_MS, 0)

    def test_admin_pool_is_smaller_and_separate(self):
        created = []

        class FakePool:
            def __init__(self, conninfo, **kwargs):
                self.kwargs = kwargs
                created.append(self)

            async def open(self, wait=True):
                pass

            async def close(self):
                pass

        saved_pool, saved_admin = db._pool, db._admin_pool
        db._pool = db._admin_pool = None
        try:
            async def scenario():
                with patch.object(db, "AsyncConnectionPool", FakePool):
                    return await db.pool(), await db.admin_pool()

            judging, admin = run(scenario())
            self.assertIsNot(judging, admin)
            self.assertEqual(judging.kwargs["max_size"], db.POOL_MAX)
            self.assertEqual(admin.kwargs["max_size"], db.ADMIN_POOL_MAX)
            self.assertLess(db.ADMIN_POOL_MAX, db.POOL_MAX)
            # Defaults are 0 (off) for the judging pool, 10000ms (on) for the admin pool.
            # Set in the startup packet, never a configure hook (a SET there leaves the
            # connection in a transaction and the pool discards it).
            self.assertNotIn("configure", judging.kwargs)
            self.assertNotIn("configure", admin.kwargs)
            self.assertNotIn("options", judging.kwargs["kwargs"])
            self.assertEqual(admin.kwargs["kwargs"]["options"], f"-c statement_timeout={db.ADMIN_STATEMENT_TIMEOUT_MS}")
        finally:
            db._pool, db._admin_pool = saved_pool, saved_admin


class _AnyKeyRow(dict):
    """A fetch_one() row double: overview/latency/enforcement_mode read different keys."""

    def __missing__(self, key):
        return 0


class _FakeAdminPoolMixin:
    """Fails the test if the judging pool is touched; counts/serialises admin calls."""

    def setUp(self):
        self.judging_calls = 0
        self.admin_calls = 0
        self._in_flight_admin = 0
        self.max_concurrent_admin = 0

        async def fail_judging(*_args, **_kwargs):
            self.judging_calls += 1
            raise AssertionError("admin endpoint touched the judging pool")

        self._patches = [
            patch.object(db, "pool", AsyncMock(side_effect=fail_judging)),
            patch.object(db, "fetch_all", AsyncMock(side_effect=fail_judging)),
            patch.object(db, "fetch_one", AsyncMock(side_effect=fail_judging)),
            patch.object(db, "admin_fetch_all", AsyncMock(side_effect=self._admin_query_many)),
            patch.object(db, "admin_fetch_one", AsyncMock(side_effect=self._admin_query_one)),
        ]
        for patcher in self._patches:
            patcher.start()
        self.addCleanup(lambda: [patcher.stop() for patcher in self._patches])

    async def _admin_query(self, value):
        self._in_flight_admin += 1
        self.admin_calls += 1
        self.max_concurrent_admin = max(self.max_concurrent_admin, self._in_flight_admin)
        await asyncio.sleep(0)  # yield, so a concurrent caller would overlap here
        self._in_flight_admin -= 1
        return value

    async def _admin_query_many(self, _query, _params=None):
        return await self._admin_query([])

    async def _admin_query_one(self, _query, _params=None):
        return await self._admin_query(_AnyKeyRow())


class OverviewPoolTest(_FakeAdminPoolMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        main._overview_cache = cache.TTLCache(5)

    def test_never_touches_judging_pool(self):
        result = run(main.overview(user=ADMIN))
        self.assertEqual(self.judging_calls, 0)
        self.assertIn("today", result)

    def test_holds_at_most_one_admin_connection_at_once(self):
        run(main.overview(user=ADMIN))
        self.assertLessEqual(self.max_concurrent_admin, 1)

    def test_repeat_call_within_ttl_does_not_requery(self):
        run(main.overview(user=ADMIN))
        after_first = self.admin_calls
        run(main.overview(user=ADMIN))
        self.assertEqual(self.admin_calls, after_first)

    def test_concurrent_calls_compute_once(self):
        async def scenario():
            return await asyncio.gather(*(main.overview(user=ADMIN) for _ in range(10)))

        run(scenario())
        first_pass = self.admin_calls
        self.assertGreater(first_pass, 0)
        run(scenario())
        self.assertEqual(self.admin_calls, first_pass, "a fresh gather within the TTL must not requery")


class LatencyPoolTest(_FakeAdminPoolMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        main._latency_cache = cache.TTLCache(5)

    def test_never_touches_judging_pool(self):
        result = run(main.latency(hours=24, user=ADMIN))
        self.assertEqual(self.judging_calls, 0)
        self.assertEqual(result["window_hours"], 24)

    def test_repeat_call_within_ttl_does_not_requery(self):
        run(main.latency(hours=24, user=ADMIN))
        after_first = self.admin_calls
        run(main.latency(hours=24, user=ADMIN))
        self.assertEqual(self.admin_calls, after_first)

    def test_distinct_hours_are_distinct_cache_entries(self):
        run(main.latency(hours=24, user=ADMIN))
        after_24h = self.admin_calls
        run(main.latency(hours=1, user=ADMIN))
        self.assertGreater(self.admin_calls, after_24h)

    def test_concurrent_calls_compute_once(self):
        async def scenario():
            return await asyncio.gather(*(main.latency(hours=24, user=ADMIN) for _ in range(10)))

        run(scenario())
        first_pass = self.admin_calls
        run(scenario())
        self.assertEqual(self.admin_calls, first_pass)


class HealthPoolTest(_FakeAdminPoolMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        main._health_cache = cache.TTLCache(5)
        self._extra_patches = [
            patch.object(main, "policy_info", AsyncMock(return_value={"matches": True})),
            patch.object(main, "_probe", AsyncMock(return_value=True)),
        ]
        for patcher in self._extra_patches:
            patcher.start()
        self.addCleanup(lambda: [patcher.stop() for patcher in self._extra_patches])

    def test_never_touches_judging_pool(self):
        result = run(main.health())
        self.assertEqual(self.judging_calls, 0)
        self.assertIn("status", result)

    def test_repeat_call_within_ttl_does_not_requery(self):
        run(main.health())
        after_first = self.admin_calls
        run(main.health())
        self.assertEqual(self.admin_calls, after_first)

    def test_concurrent_calls_compute_once(self):
        async def scenario():
            return await asyncio.gather(*(main.health() for _ in range(10)))

        run(scenario())
        self.assertEqual(self.admin_calls, 1)


if __name__ == "__main__":
    unittest.main()
