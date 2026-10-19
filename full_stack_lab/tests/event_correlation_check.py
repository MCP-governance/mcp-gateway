"""Pure projection checks for call, dispatch and endpoint event correlation."""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "gateway"
sys.path.insert(0, str(APP))

from app.event_correlation import correlation_result  # noqa: E402


class EventCorrelationCheck(unittest.TestCase):
    def setUp(self):
        self.at = datetime(2026, 10, 20, 3, 0, tzinfo=timezone.utc)
        self.call = {"id": 42, "created_at": self.at, "request_id": "req-42", "trace_id": "trace-42",
                     "user_token": "subject-a", "device_id": "device-a", "decision": "Allow",
                     "policy_id": "P-TEST", "server_id": "calendar", "tool_name": "create"}
        self.intent = {"attempted_at": self.at + timedelta(seconds=1), "decision_id": 42, "state": "resolved"}

    def event(self, *, seconds=0, endpoint="device-a", subject="subject-a"):
        return {"kind": "os-event", "id": 8, "at": self.at + timedelta(seconds=seconds),
                "endpoint_id": endpoint, "event_user_token": subject, "title": "agent.exe"}

    def correlate(self, events=None, call=None):
        return correlation_result(call or self.call, self.intent, events or [], bound=True, window_seconds=10)

    def test_exact_request_trace_and_decision_links(self):
        result = self.correlate([self.event()])
        by_kind = {r["kind"]: r for r in result["records"]}
        self.assertEqual(by_kind["decision"]["link_basis"], ["request_id", "trace_id"])
        self.assertEqual(by_kind["dispatch-intent"]["link_basis"], ["request_id", "decision_id"])
        endpoint = next(r for r in result["records"] if r["kind"] == "os-event")
        self.assertEqual(endpoint["link_basis"], ["same_endpoint", "same_principal", "time_window"])
        self.assertEqual(endpoint["link_strength"], "corroborating")

    def test_window_edges_are_inclusive(self):
        result = self.correlate([self.event(seconds=-10), self.event(seconds=10), self.event(seconds=11)])
        self.assertEqual(sum(r["kind"] == "os-event" for r in result["records"]), 2)

    def test_other_device_is_excluded(self):
        result = self.correlate([self.event(endpoint="device-b")])
        self.assertFalse(any(r["kind"] == "os-event" for r in result["records"]))

    def test_different_subject_is_excluded(self):
        result = self.correlate([self.event(subject="subject-b")])
        self.assertFalse(any(r["kind"] == "os-event" for r in result["records"]))

    def test_trace_less_legacy_decision_still_correlates_by_device_subject_and_time(self):
        legacy = {**self.call, "request_id": None, "trace_id": None}
        result = self.correlate([self.event()], legacy)
        decision = next(r for r in result["records"] if r["kind"] == "decision")
        self.assertEqual(decision["trace_id"], None)
        self.assertEqual(decision["link_basis"], [])
        self.assertTrue(any(r["kind"] == "os-event" for r in result["records"]))
        self.assertFalse(any(r["kind"] == "dispatch-intent" for r in result["records"]))


if __name__ == "__main__":
    unittest.main()
