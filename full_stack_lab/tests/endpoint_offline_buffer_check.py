"""Durable endpoint offline queue regression checks; no Gateway or device required."""
from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "endpoint-agent"))

from offline_buffer import BufferFull, EventBuffer, flush  # noqa: E402


NOW = datetime(2026, 10, 21, tzinfo=timezone.utc)


def event(number: int) -> dict:
    raw = f"journal-row-{number}".encode()
    return {"event_id": f"boot:cursor-{number}", "observed_at": NOW.isoformat(),
            "kind": "execution-denied", "details": {"executable": "git"}, "denial_class": "blocked_attempt",
            "provenance": {"raw_sha256": hashlib.sha256(raw).hexdigest(), "collector": "journal-apparmor"}}


class OfflineBufferChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "os-buffer.jsonl"
        self.buffer = EventBuffer(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_normal_delivery(self):
        self.buffer.enqueue([event(1), event(2)], now=NOW)
        received = []
        self.assertEqual(flush(self.buffer, received.extend), 2)
        self.assertEqual([item["event_id"] for item in received], ["boot:cursor-1", "boot:cursor-2"])
        self.assertEqual(self.buffer.pending(now=NOW), [])

    def test_offline_enqueue_reconnect_has_no_loss_or_duplicate(self):
        rows = [event(n) for n in range(1, 8)]
        self.buffer.enqueue(rows, now=NOW)

        def disconnected(_batch):
            raise ConnectionError("offline")

        with self.assertRaises(ConnectionError):
            flush(self.buffer, disconnected)
        self.assertEqual(len(self.buffer.pending(now=NOW)), 7)
        self.buffer.enqueue(rows, now=NOW + timedelta(minutes=1))
        received: dict[str, dict] = {}
        count = flush(self.buffer, lambda batch: [received.setdefault(item["provenance"]["raw_sha256"], item)
                                                   for item in batch])
        self.assertEqual((count, len(received), self.buffer.pending()), (7, 7, []))

    def test_capacity_stops_collection_and_records_drop_count(self):
        buffer = EventBuffer(self.path, max_bytes=8192, max_events=2)
        buffer.enqueue([event(1), event(2)], now=NOW)
        with self.assertRaises(BufferFull):
            buffer.enqueue([event(3)], now=NOW)
        with self.assertRaises(BufferFull):
            buffer.enqueue([event(3)], now=NOW)
        self.assertEqual((len(buffer.pending(now=NOW)), buffer.dropped_count()), (2, 1))
        self.assertEqual(buffer.drop_report()["buffer_reason"], "capacity")

    def test_byte_cap_stops_collection(self):
        buffer = EventBuffer(self.path, max_bytes=1024, max_events=10)
        with self.assertRaises(BufferFull):
            buffer.enqueue([event(n) for n in range(10)], now=NOW)
        self.assertEqual(buffer.dropped_count(), 10)

    def test_truncated_final_line_is_removed_and_prior_rows_survive(self):
        self.buffer.enqueue([event(1)], now=NOW)
        with self.path.open("ab") as stream:
            stream.write(b'{"uid":"partial')
        self.assertEqual([row["uid"] for row in self.buffer.pending(now=NOW)],
                         [event(1)["provenance"]["raw_sha256"]])
        self.assertTrue(self.path.read_bytes().endswith(b"\n"))

    def test_process_kill_leftover_atomic_temp_is_removed_on_restart(self):
        self.buffer.enqueue([event(1)], now=NOW)
        stale = self.path.parent / (self.path.name + ".interrupted.tmp")
        stale.write_bytes(b"partial replacement")
        restarted = EventBuffer(self.path)
        self.assertFalse(stale.exists())
        self.assertEqual(len(restarted.pending(now=NOW)), 1)

    def test_process_restart_reloads_pending_rows(self):
        self.buffer.enqueue([event(1), event(2)], now=NOW)
        restarted = EventBuffer(self.path)
        received = []
        self.assertEqual(flush(restarted, received.extend), 2)
        self.assertEqual(received, [event(1), event(2)])

    def test_clock_rollback_does_not_expire_rows_early(self):
        self.buffer.enqueue([event(1)], now=NOW)
        backwards = NOW - timedelta(days=30)
        self.assertEqual(len(self.buffer.pending(now=backwards)), 1)
        self.assertEqual(len(EventBuffer(self.path).pending(now=backwards)), 1)

    def test_retention_expiry_is_counted_and_not_silent(self):
        self.buffer.enqueue([event(1)], now=NOW)
        self.assertEqual(self.buffer.pending(now=NOW + timedelta(days=8)), [])
        self.assertEqual(self.buffer.dropped_count(), 1)

    def test_secrets_and_raw_records_are_refused(self):
        with self.assertRaises(ValueError):
            self.buffer.enqueue([{**event(1), "raw_event": "sensitive source text"}], now=NOW)
        with self.assertRaises(ValueError):
            self.buffer.enqueue([{**event(1), "details": {"access_token": "secret"}}], now=NOW)
        self.assertEqual(self.buffer.pending(now=NOW), [])


if __name__ == "__main__":
    unittest.main()
