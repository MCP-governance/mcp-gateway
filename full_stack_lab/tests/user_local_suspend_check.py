"""Manual local stop ordering and exact-pair resume with asynchronous DB doubles.

This verifies the Python lock protocol, not PostgreSQL locking or a device receipt.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock

import user_server_suspend_check as base


class LockedStore(base.Store):
    def __init__(self):
        super().__init__()
        self.locks: dict[tuple, asyncio.Lock] = {}
        self.order: list[tuple] = []

    @asynccontextmanager
    async def transaction(self):
        tx = NS(rows=[], resumed=[], events=[], statements=[], held=[])

        async def execute(query, params=()):
            query = " ".join(query.split())
            if "pg_advisory_xact_lock" in query:
                key = ("pair" if "1431523923" in query else "user", params[0])
                lock = self.locks.setdefault(key, asyncio.Lock())
                await lock.acquire()
                tx.held.append(lock)
                self.order.append(("lock",) + key)
            return await self.statement(tx, query, params)

        try:
            yield NS(execute=execute)
            self.rows.extend(tx.rows)
            for row, fields in tx.resumed:
                row.update(fields)
            self.events.extend(tx.events)
        finally:
            self.first_statements = tx.statements
            for lock in reversed(tx.held):
                lock.release()


def load(store, jobs):
    record_event = base.production("review.py", {"record_event"}, {
        "db": NS(fetch_one=AsyncMock()), "Jsonb": lambda value, **kw: value,
        "json": base.json, "Any": object}).record_event
    return base.production("user_suspend.py", {
        "TARGET", "MANUAL_OPERATION_SLOTS", "operation_key", "suspend", "resume"},
        {"db": NS(POOL_MAX=10, transaction=store.transaction), "asyncio": asyncio,
         "review": NS(record_event=record_event), "local_jobs": jobs})


class LocalStopChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.store = LockedStore()
        self.stops = {("", "", ""), ("gitea", "", ""), ("", "emp-a", "")}
        self.waiting = asyncio.Event()
        self.ack = asyncio.Event()
        self.ack.set()

        async def quiesce(*, server_id, user_token):
            assert (server_id, user_token) == ("gitea", "emp-a")
            self.store.order.append(("quiesce", server_id, user_token))
            self.stops.add((server_id, user_token, ""))
            self.waiting.set()
            await self.ack.wait()

        async def resume_stop(connection, server_id, user_token):
            self.store.order.append(("resume-stop", server_id, user_token))
            self.stops.discard((server_id, user_token, ""))

        self.jobs = NS(is_local=lambda server: server == "gitea", quiesce=quiesce,
                       resume_user_stop=resume_stop)
        self.mod = load(self.store, self.jobs)

    async def test_local_stop_waits_for_ack_before_employee_lock_and_success(self):
        self.ack.clear()
        stop = asyncio.create_task(self.mod.suspend("emp-a", "gitea", "admin", "사고 대응"))
        await asyncio.wait_for(self.waiting.wait(), 1)
        self.assertEqual([entry[1] for entry in self.store.order if entry[0] == "lock"], ["pair"])
        self.assertFalse(stop.done())
        self.ack.set()
        await asyncio.wait_for(stop, 1)
        self.assertEqual([entry[1] for entry in self.store.order if entry[0] == "lock"], ["pair", "user"])
        self.assertIn(("gitea", "emp-a", ""), self.stops)
        self.assertEqual(len(self.store.rows), 1)

    async def test_resume_waits_behind_quiesce_and_cannot_erase_new_stop(self):
        old = await self.mod.suspend("emp-a", "gitea", "admin", "먼저 중지")
        self.waiting.clear()
        self.ack.clear()
        stop = asyncio.create_task(self.mod.suspend("emp-a", "gitea", "admin", "다시 중지"))
        await asyncio.wait_for(self.waiting.wait(), 1)
        resume = asyncio.create_task(self.mod.resume(old["id"], "admin", "재개"))
        await asyncio.sleep(.01)
        self.assertFalse(resume.done())
        self.assertIn(("gitea", "emp-a", ""), self.stops)
        self.ack.set()
        with self.assertRaisesRegex(ValueError, "이미 중지"):
            await asyncio.wait_for(stop, 1)
        await asyncio.wait_for(resume, 1)
        self.assertNotIn(("gitea", "emp-a", ""), self.stops)
        self.assertEqual(len(self.store.rows), 1)
        self.assertIsNotNone(self.store.rows[0]["resumed_at"])

    async def test_claim_during_ack_wait_sees_pair_stop_even_with_resume_waiting(self):
        old = await self.mod.suspend("emp-a", "gitea", "admin", "먼저 중지")
        self.waiting.clear()
        self.ack.clear()
        stop = asyncio.create_task(self.mod.suspend("emp-a", "gitea", "admin", "다시 중지"))
        await asyncio.wait_for(self.waiting.wait(), 1)
        resume = asyncio.create_task(self.mod.resume(old["id"], "admin", "재개"))

        async def claim(user, server):
            # Model the exact-pair stop tested by authorized() at claim/start.
            return (server, user, "") not in self.stops

        self.assertFalse(await claim("emp-a", "gitea"))
        self.assertTrue(await claim("emp-b", "gitea"))
        self.ack.set()
        with self.assertRaisesRegex(ValueError, "이미 중지"):
            await asyncio.wait_for(stop, 1)
        await asyncio.wait_for(resume, 1)
        self.assertTrue(await claim("emp-a", "gitea"))

    async def test_completed_resume_then_new_suspend_keeps_the_new_stop(self):
        old = await self.mod.suspend("emp-a", "gitea", "admin", "먼저 중지")
        await self.mod.resume(old["id"], "admin", "재개")
        self.assertNotIn(("gitea", "emp-a", ""), self.stops)
        await self.mod.suspend("emp-a", "gitea", "admin", "다시 중지")
        self.assertIn(("gitea", "emp-a", ""), self.stops)
        self.assertEqual(len([r for r in self.store.rows if r["resumed_at"] is None]), 1)
        self.assertTrue({("", "", ""), ("gitea", "", ""), ("", "emp-a", "")} <= self.stops)

    async def test_ack_failure_has_no_suspension_or_success_and_leaves_stop(self):
        working_quiesce = self.jobs.quiesce
        async def fail_quiesce(*, server_id, user_token):
            self.stops.add((server_id, user_token, ""))
            raise RuntimeError("receipt missing")
        self.jobs.quiesce = fail_quiesce
        with self.assertRaisesRegex(RuntimeError, "receipt missing"):
            await self.mod.suspend("emp-a", "gitea", "admin", "사고 대응")
        self.assertEqual((self.store.rows, self.store.events), ([], []))
        self.assertIn(("gitea", "emp-a", ""), self.stops)
        # Recovery: retry the stop to a recorded state, then explicitly resume.
        self.jobs.quiesce = working_quiesce
        stopped = await self.mod.suspend("emp-a", "gitea", "admin", "정지 확인 후 재시도")
        self.assertIn(("gitea", "emp-a", ""), self.stops)
        await self.mod.resume(stopped["id"], "admin", "재개")
        self.assertNotIn(("gitea", "emp-a", ""), self.stops)

    async def test_cancel_after_durable_stop_keeps_marker_without_state_row(self):
        self.ack.clear()
        stop = asyncio.create_task(self.mod.suspend("emp-a", "gitea", "admin", "사고 대응"))
        await asyncio.wait_for(self.waiting.wait(), 1)
        stop.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await stop
        self.assertEqual((self.store.rows, self.store.events), ([], []))
        self.assertIn(("gitea", "emp-a", ""), self.stops)
        self.ack.set()
        stopped = await self.mod.suspend("emp-a", "gitea", "admin", "재시도")
        await self.mod.resume(stopped["id"], "admin", "재개")
        self.assertNotIn(("gitea", "emp-a", ""), self.stops)

    async def test_remote_and_missing_subject_never_quiesce(self):
        await self.mod.suspend("emp-a", "filesystem", "admin", "사유")
        with self.assertRaises(LookupError):
            await self.mod.suspend("nobody", "gitea", "admin", "사유")
        self.assertEqual(self.store.order.count(("quiesce", "gitea", "emp-a")), 0)
        self.assertEqual(len(self.store.rows), 1)

    async def test_stop_delete_failure_rolls_back_resume_and_keeps_admission_closed(self):
        stopped = await self.mod.suspend("emp-a", "gitea", "admin", "사고 대응")
        async def fail_delete(connection, server_id, user_token):
            raise OSError("stop delete unavailable")
        self.jobs.resume_user_stop = fail_delete
        with self.assertRaisesRegex(OSError, "stop delete unavailable"):
            await self.mod.resume(stopped["id"], "admin", "재개")
        self.assertIsNone(self.store.rows[0]["resumed_at"])
        self.assertIn(("gitea", "emp-a", ""), self.stops)
        self.assertEqual([event["kind"] for event in self.store.events], ["user-server-suspend"])


class SourceContractChecks(unittest.IsolatedAsyncioTestCase):
    async def test_exact_pair_delete_even_if_catalog_no_longer_has_local_server(self):
        sql = []
        async def execute(query, params):
            sql.append((" ".join(query.split()), params))
        module = base.production("local_jobs.py", {"resume_user_stop"}, {})
        await module.resume_user_stop(NS(execute=execute), "gitea", "emp-a")
        self.assertEqual(sql, [("DELETE FROM local_run_stops WHERE server_id=%s AND user_token=%s AND device_id=''",
                                ("gitea", "emp-a"))])
        with self.assertRaises(ValueError):
            await module.resume_user_stop(NS(execute=execute), "gitea", "")

    async def test_single_routes_do_not_change_stops_outside_service_lock(self):
        source = (base.APP / "main.py").read_text(encoding="utf-8")
        for name in ("suspend_use", "resume_use"):
            start = source.index(f"async def {name}(")
            end = source.find("\n@app.", start + 1)
            body = source[start:end if end >= 0 else None]
            self.assertNotIn("local_jobs.quiesce", body)
            self.assertNotIn("local_jobs.resume(", body)

    async def test_database_trigger_refuses_unacknowledged_started_job(self):
        source = (base.APP / "local_run_tables.sql").read_text(encoding="utf-8")
        self.assertIn("TG_TABLE_NAME='user_server_suspensions'", source)
        self.assertIn("j.started_at IS NOT NULL AND j.stopped_at IS NULL", source)
        self.assertIn("RAISE EXCEPTION 'local container stop is unconfirmed", source)

    async def test_claim_and_start_read_scoped_stop_rows(self):
        source = (base.APP / "local_jobs.py").read_text(encoding="utf-8")
        self.assertIn("AS stopped", source)
        self.assertIn("x.user_token='' OR x.user_token=e.owner_token", source)
        self.assertIn("row['suspended'] or row['stopped']", source)
        self.assertIn("allowed = await authorized(connection,device", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
