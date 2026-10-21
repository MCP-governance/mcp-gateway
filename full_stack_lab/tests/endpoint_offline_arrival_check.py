"""DEV-80 arrival after reconnect: device buffer, Gateway receiver and ACK cursor in one process.

Unit level. The device side is the real os-observer.main() with its real offline buffer file and
cursor files. Only subprocess.run (journalctl), the agent's HTTP call, the root-ownership check
(this runner is a Windows user) and the device identity are replaced. The Gateway side is the real
main.endpoint_os_report, main.endpoint_observation_status and endpoint_plane.ingest_os_events over
an in-memory store. That store answers the INSERT by its two duplicate keys, and each test asserts
which key decided, so a change of key fails here. No database, Gateway or device is used. The
PostgreSQL behaviour of the same receiver is in endpoint_evidence_pg_check.py.

Duplicate keys (endpoint_plane.ingest_os_events):
  raw  (endpoint_id, raw_sha256) received within RAW_DEDUPE_DAYS of the first receipt -> not stored
  id   (endpoint_id, event_id) unique (ON CONFLICT DO NOTHING) -> stored once
Device ACK: a buffer row leaves the buffer only after the Gateway answered; the buffer uid is raw_sha256.
The ACK cursor (.journal-cursor) moves only after the buffer is empty and the Gateway answered.
"""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import stat
import sys
import tempfile
import unittest
import urllib.error
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "endpoint-agent"))
sys.path.insert(0, str(ROOT / "full_stack_lab" / "gateway"))

from app import endpoint_plane, main  # noqa: E402
from offline_buffer import EventBuffer  # noqa: E402


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / "endpoint-agent" / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


AGENT = load("arrival_agent", "agent.py")
observer = load("arrival_observer", "os-observer.py")
ENDPOINT = "ep-arrival"
BOOT = "boot-arrival"
NOW = datetime(2026, 10, 21, tzinfo=UTC)


class DeviceCrash(BaseException):
    """The observer process dies here. BaseException, so no except clause in main() catches it."""


class RootOwnedPath(type(Path())):
    """main() wants program and config paths owned by root with no group or other write bit. This runner
    has no such ownership, so stat() reports the owner and mode that check wants. exists() stays real."""

    def stat(self, *, follow_symlinks=True):
        real = os.stat(self, follow_symlinks=follow_symlinks)
        mode = 0o40700 if stat.S_ISDIR(real.st_mode) else 0o100600
        return os.stat_result((mode, real.st_ino, real.st_dev, real.st_nlink, 0, 0, real.st_size,
                               int(real.st_atime), int(real.st_mtime), int(real.st_ctime)))

    def exists(self, *, follow_symlinks=True):
        return os.path.exists(self)


class SmallBuffer(EventBuffer):
    """The same buffer with a three-event capacity, so overflow is reachable with five journal lines."""

    def __init__(self, path):
        super().__init__(path, max_events=3)


def journal_line(number):
    record = {"_BOOT_ID": BOOT, "__CURSOR": f"c{number:04d}",
              "__REALTIME_TIMESTAMP": str(int(NOW.timestamp() * 1_000_000) + number),
              "MESSAGE": f'apparmor="DENIED" operation="exec" profile="mcpgw-u" name="/usr/bin/tool{number}" '
                         'pid=7 comm="bash" fsuid=1001 ouid=0'}
    return json.dumps(record, sort_keys=True)


def sealed(number):
    line = journal_line(number)
    return observer.event(json.loads(line), 1001, "mcpgw-u", line)


def _device():
    return {"endpoint_id": ENDPOINT, "scopes": ["enforcement"]}


class Cursor:
    def __init__(self, row=None, rowcount=0):
        self.row, self.rowcount = row, rowcount

    async def fetchone(self):
        return self.row


class Store:
    """The three tables the receivers write, in memory. The statement text must still contain the
    duplicate clauses; the rows are then decided by those keys."""

    def __init__(self):
        self.now = NOW
        self.events, self.drops, self.decisions = [], [], []
        self.observation = {}

    @contextlib.asynccontextmanager
    async def transaction(self):
        yield self

    async def execute(self, query, params=None):
        text = " ".join(query.split())
        if text.startswith("INSERT INTO endpoint_os_events"):
            assert "NOT EXISTS (SELECT 1 FROM endpoint_os_events WHERE endpoint_id=%s AND raw_sha256=%s" in text, text
            assert "ON CONFLICT(endpoint_id,event_id) DO NOTHING" in text, text
            endpoint, event_id, raw, window_days = params[0], params[1], params[7], params[10]
            if any(row["endpoint"] == endpoint and row["raw"] == raw
                   and row["received"] > self.now - timedelta(days=window_days) for row in self.events):
                self.decisions.append(("raw_sha256", False))
                return Cursor(rowcount=0)
            if any(row["endpoint"] == endpoint and row["event_id"] == event_id for row in self.events):
                self.decisions.append(("event_id", False))
                return Cursor(rowcount=0)
            self.events.append({"endpoint": endpoint, "event_id": event_id, "raw": raw, "received": self.now})
            self.decisions.append(("new", True))
            return Cursor(rowcount=1)
        if text.startswith("INSERT INTO endpoint_buffer_events"):
            assert "ON CONFLICT(endpoint_id,event_uid)" in text, text
            endpoint, uid, count, reason = params
            held = next((drop for drop in self.drops if drop["endpoint"] == endpoint and drop["uid"] == uid), None)
            if held is None:
                self.drops.append({"endpoint": endpoint, "uid": uid, "count": count, "reason": reason})
                return Cursor(rowcount=1)
            # Same drop_uid: only a larger report replaces the row. Anything else leaves it as it is.
            if ("DO UPDATE SET" in text and "WHERE EXCLUDED.dropped_count > endpoint_buffer_events.dropped_count" in text
                    and count > held["count"]):
                held.update(count=count, reason=reason)
                return Cursor(rowcount=1)
            return Cursor(rowcount=0)
        if "FROM endpoint_agents" in text:
            return Cursor(row={"endpoint_id": ENDPOINT, "detail": {"observation": dict(self.observation)}})
        if text.startswith("UPDATE endpoint_agents"):
            self.observation.update(params[0].obj)
            return Cursor(rowcount=1)
        raise AssertionError(f"statement not modelled: {text[:90]}")


class Gateway:
    """One endpoint's Gateway: the real receivers, answered in memory. A test sets one fault at a time."""

    def __init__(self, store, ack_path):
        self.store, self.ack_path = store, ack_path
        self.answer_status = None       # answer this HTTP status and store nothing
        self.lose_answer = False        # store, then the answer never reaches the device
        self.crash_device = False       # store, then the device process dies before it acknowledges
        self.lose_status_answer = False # store the observation report, then its answer never reaches the device
        self.post_sizes, self.ack_present, self.answers = [], [], []

    def call(self, method, path, body=None):
        if path == "/api/endpoint/os-events":
            return self._os_events(body)
        if path == "/api/endpoint/observation-status":
            if self.answer_status:
                raise self._status_error(path)
            result = asyncio.run(main.endpoint_observation_status(main.ObservationReport.model_validate(body), _device()))
            if self.lose_status_answer:
                self.lose_status_answer = False
                raise ConnectionResetError("status answer lost after the Gateway committed the report")
            return result
        raise AssertionError(f"path not modelled: {path}")

    def _status_error(self, path):
        return urllib.error.HTTPError(f"https://gateway.test{path}", self.answer_status, "fixture", {}, io.BytesIO(b""))

    def _os_events(self, body):
        self.post_sizes.append(len(body["events"]))
        self.ack_present.append(self.ack_path.exists())
        if self.answer_status:
            raise self._status_error("/api/endpoint/os-events")
        result = asyncio.run(main.endpoint_os_report(main.EndpointOSReport.model_validate(body), _device()))
        self.answers.append(result)
        if self.crash_device:
            self.crash_device = False
            raise DeviceCrash("the device stopped after the Gateway committed the batch")
        if self.lose_answer:
            self.lose_answer = False
            raise ConnectionResetError("answer lost after the Gateway committed the batch")
        return result


class ArrivalChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = Path(self.temp.name) / "observer.json"
        self.config.write_text("{}", encoding="utf-8")
        self.journal = []
        self.store = Store()
        self.gateway = Gateway(self.store, self.config.with_suffix(".journal-cursor"))
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        for target, name, value in (
                (endpoint_plane.db, "transaction", self.store.transaction),
                (AGENT, "call", self.gateway.call),
                (AGENT, "endpoint_id", lambda: ENDPOINT),
                (AGENT, "validate_gateway", lambda: None),
                (observer, "_AGENT", AGENT),
                (observer, "Path", RootOwnedPath),
                (observer.subprocess, "run", self.journalctl)):
            self.stack.enter_context(mock.patch.object(target, name, value))
        self.stack.enter_context(mock.patch.object(os, "geteuid", create=True, return_value=0))

    def journalctl(self, command, **_options):
        if "--after-cursor" in command:
            after = command[command.index("--after-cursor") + 1]
            cursors = [cursor for cursor, _ in self.journal]
            lines = self.journal[cursors.index(after) + 1:]
        else:
            lines = self.journal
        return SimpleNamespace(stdout="".join(line + "\n" for _, line in lines))

    def add_journal(self, first, last):
        self.journal.extend((f"c{n:04d}", journal_line(n)) for n in range(first, last + 1))

    def run_observer(self):
        argv = ["os-observer.py", "--config", str(self.config), "--uid", "1001", "--profile", "mcpgw-u"]
        out = io.StringIO()
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(out):
            try:
                observer.main()
            except SystemExit as stopped:
                return stopped.code, out.getvalue()
        return 0, out.getvalue()

    def buffer(self):
        return EventBuffer(self.config.with_suffix(".os-buffer.jsonl"))

    def cursor(self, suffix):
        path = self.config.with_suffix(suffix)
        return path.read_text(encoding="utf-8").strip() if path.exists() else None

    def test_offline_events_all_arrive_after_reconnect_and_the_ack_cursor_moves_last(self):
        self.add_journal(1, 230)
        self.gateway.answer_status = 503
        self.run_observer()
        self.assertEqual(self.store.events, [])
        self.assertEqual(len(self.buffer().pending()), 230)
        self.assertIsNone(self.cursor(".journal-cursor"))
        self.assertEqual(self.cursor(".journal-buffer-cursor"), "c0230")

        self.gateway.answer_status = None
        self.assertEqual(self.run_observer()[0], 0)
        self.assertEqual(sorted(row["event_id"] for row in self.store.events),
                         sorted(f"{BOOT}:c{n:04d}" for n in range(1, 231)))
        self.assertEqual(sum(answer["accepted"] for answer in self.gateway.answers), 230)
        self.assertEqual(max(self.gateway.post_sizes), 100)
        self.assertFalse(any(self.gateway.ack_present), "the ACK cursor existed while a batch was being stored")
        self.assertEqual(self.buffer().pending(), [])
        self.assertEqual(self.cursor(".journal-cursor"), "c0230")
        self.assertEqual(self.store.observation["os"]["accepted_count"], 230)

    def test_a_gateway_error_never_moves_the_ack_cursor_and_each_retry_delivers_once(self):
        self.add_journal(1, 3)
        for status in (500, 503):
            self.gateway.answer_status = status
            self.assertEqual(self.run_observer()[0], 1)  # the failed observation report marks the run failed
            self.assertEqual(len(self.buffer().pending()), 3)
            self.assertIsNone(self.cursor(".journal-cursor"))
        self.assertEqual(self.store.events, [])

        self.gateway.answer_status = None
        self.assertEqual(self.run_observer()[0], 0)
        self.assertEqual([row["event_id"] for row in self.store.events], [f"{BOOT}:c000{n}" for n in (1, 2, 3)])
        self.assertEqual(self.cursor(".journal-cursor"), "c0003")

    def test_a_device_stop_after_the_gateway_stored_resends_and_the_gateway_keeps_one_copy(self):
        self.add_journal(1, 7)
        self.gateway.crash_device = True
        with self.assertRaises(DeviceCrash):
            self.run_observer()
        self.assertEqual(len(self.store.events), 7)
        self.assertEqual(len(self.buffer().pending()), 7)
        self.assertIsNone(self.cursor(".journal-cursor"))

        self.assertEqual(self.run_observer()[0], 0)
        self.assertEqual(len(self.store.events), 7)
        self.assertEqual(self.gateway.answers[-1]["duplicates"], 7)
        # The collection cursor was never written, so the restart also re-reads the journal and may send the
        # same lines again in that run. Every resent copy is decided by the raw hash, and none is stored twice.
        resent = self.store.decisions[7:]
        self.assertTrue(resent)
        self.assertEqual(set(resent), {("raw_sha256", False)})
        self.assertEqual(self.buffer().pending(), [])
        self.assertEqual(self.cursor(".journal-cursor"), "c0007")

    def test_a_lost_answer_after_the_gateway_stored_is_resent_and_stored_once(self):
        self.add_journal(1, 7)
        self.gateway.lose_answer = True
        self.run_observer()
        self.assertEqual(len(self.store.events), 7)
        self.assertEqual(len(self.buffer().pending()), 7)
        self.assertIsNone(self.cursor(".journal-cursor"))

        self.assertEqual(self.run_observer()[0], 0)
        self.assertEqual(len(self.store.events), 7)
        self.assertEqual(self.gateway.answers[-1]["duplicates"], 7)
        self.assertEqual(self.cursor(".journal-cursor"), "c0007")

    def test_the_gateway_keys_are_the_raw_hash_inside_seven_days_and_the_event_id(self):
        self.add_journal(1, 1)
        first = sealed(1)

        def post(event):
            return self.gateway.call("POST", "/api/endpoint/os-events", {"endpoint_id": ENDPOINT, "events": [event]})

        self.assertEqual(post(first)["accepted"], 1)
        # The same raw record under a new event_id: the raw hash decides.
        self.assertEqual(post({**first, "event_id": f"{BOOT}:c0001-rederived"})["duplicates"], 1)
        self.assertEqual(self.store.decisions[-1], ("raw_sha256", False))
        # The same event_id with a different raw record: the event_id key decides.
        other = {**first, "provenance": {**first["provenance"], "raw_sha256": hashlib.sha256(b"other").hexdigest()}}
        self.assertEqual(post(other)["duplicates"], 1)
        self.assertEqual(self.store.decisions[-1], ("event_id", False))
        self.assertEqual(len(self.store.events), 1)
        # Outside RAW_DEDUPE_DAYS the same raw record is new again.
        self.store.now = NOW + timedelta(days=endpoint_plane.RAW_DEDUPE_DAYS + 1)
        self.assertEqual(post({**first, "event_id": f"{BOOT}:c0001-rederived"})["accepted"], 1)
        self.assertEqual(len(self.store.events), 2)

    def test_a_buffer_overflow_is_reported_once_with_its_count_and_reason(self):
        with mock.patch.object(observer, "EventBuffer", SmallBuffer):
            self.add_journal(1, 5)
            self.assertEqual(self.run_observer()[0], 0)
            self.assertEqual(self.store.events, [])
            self.assertIsNone(self.cursor(".journal-buffer-cursor"))  # not moved: the five lines are read again later
            self.assertEqual([(drop["count"], drop["reason"]) for drop in self.store.drops], [(5, "capacity")])
            self.assertRegex(self.store.drops[0]["uid"], r"^[0-9a-f]{32}$")
            self.assertEqual(self.store.observation["os"]["error_code"], "offline_buffer_full")
            self.assertEqual(self.buffer().dropped_count(), 0)

    def test_a_drop_count_survives_a_gateway_outage_and_is_reported_after_reconnect(self):
        with mock.patch.object(observer, "EventBuffer", SmallBuffer):
            self.add_journal(1, 5)
            self.gateway.answer_status = 503
            self.assertEqual(self.run_observer()[0], 1)
            self.assertEqual(self.store.drops, [])
            self.assertEqual(self.buffer().dropped_count(), 5)  # kept, not cleared, because the report failed

            self.gateway.answer_status = None
            self.assertEqual(self.run_observer()[0], 0)
            self.assertEqual([(drop["count"], drop["reason"]) for drop in self.store.drops], [(5, "capacity")])
            self.assertEqual(self.buffer().dropped_count(), 0)

    def test_entries_expired_from_the_buffer_are_reported_as_retention(self):
        EventBuffer(self.config.with_suffix(".os-buffer.jsonl")).enqueue(
            [sealed(9001), sealed(9002)], now=datetime.now(UTC) - timedelta(days=8))
        self.add_journal(1, 3)
        self.assertEqual(self.run_observer()[0], 0)
        self.assertEqual([(drop["count"], drop["reason"]) for drop in self.store.drops], [(2, "retention")])
        self.assertEqual(len(self.store.events), 3)
        self.assertEqual(self.cursor(".journal-cursor"), "c0003")
        self.assertEqual(self.store.observation["os"]["error_code"], "offline_buffer_dropped")

    def test_seven_unique_refused_events_are_counted_seven_times_across_two_runs(self):
        # Five lines are refused in the first run and the same five are read again in the second run. Only
        # the two new lines are counted there, so the Gateway total is the unique count, 7, not 5 + 7 = 12.
        with mock.patch.object(observer, "EventBuffer", SmallBuffer):
            self.add_journal(1, 5)
            self.assertEqual(self.run_observer()[0], 0)
            self.add_journal(6, 7)
            self.assertEqual(self.run_observer()[0], 0)
            self.assertEqual(sum(drop["count"] for drop in self.store.drops), 7)
            self.assertEqual(sorted(drop["count"] for drop in self.store.drops), [2, 5])
            self.assertEqual(self.store.events, [])
            self.assertEqual(self.buffer().dropped_count(), 0)

    def test_a_lost_drop_report_is_raised_to_the_larger_count_and_never_lowered(self):
        # The first report is stored, its answer is lost, so the drop_uid and count 5 stay on the device. Eight
        # more unique refused lines then raise the same drop_uid to 13. A smaller report for that uid must not
        # lower the row.
        with mock.patch.object(observer, "EventBuffer", SmallBuffer):
            self.add_journal(1, 5)
            self.gateway.lose_status_answer = True
            self.assertEqual(self.run_observer()[0], 1)
            self.assertEqual([drop["count"] for drop in self.store.drops], [5])
            uid = self.store.drops[0]["uid"]
            self.assertEqual(self.buffer().dropped_count(), 5)

            self.add_journal(6, 13)
            self.assertEqual(self.run_observer()[0], 0)
            self.assertEqual([(drop["uid"], drop["count"]) for drop in self.store.drops], [(uid, 13)])
            self.assertEqual(self.buffer().dropped_count(), 0)

            late = {"endpoint_id": ENDPOINT, "channel": "os", "state": "partial", "accepted_count": 0,
                    "error_code": "offline_buffer_full", "buffer_event_uid": uid, "dropped_count": 4,
                    "buffer_reason": "capacity"}
            self.gateway.call("POST", "/api/endpoint/observation-status", late)
            self.assertEqual([(drop["uid"], drop["count"]) for drop in self.store.drops], [(uid, 13)])
            self.assertEqual(len(self.store.drops), 1)


if __name__ == "__main__":
    unittest.main()
