"""In-process host metrics, DNS/TCP timing, cache and Console authorization checks."""
from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gateway"))
from app import agent_contract, agent_service, oidc
from app.system_metrics import SystemMetrics, cpu_counters, memory_usage


class Clock:
    def __init__(self):
        self.now = 10.0

    def __call__(self):
        return self.now


class MetricsMathTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.proc = Path(self.tmp.name)
        self.sampler = SystemMetrics("http://gateway:8080", self.proc)

    def tearDown(self):
        self.tmp.cleanup()

    def stat(self, counters):
        (self.proc / "stat").write_text("cpu " + " ".join(map(str, counters)) + "\ncpu0 999 999\n")

    def test_cpu_delta_ignores_guest_ticks_and_counts_iowait_idle(self):
        self.stat([100, 0, 0, 100, 20, 0, 0, 0, 80, 0])
        self.assertIsNone(self.sampler.cpu_usage(10)["percent"])
        self.stat([130, 0, 0, 150, 40, 0, 0, 0, 10000, 9999])
        measured = self.sampler.cpu_usage(15)
        self.assertEqual(measured, {"percent": 30.0, "scope": "linux_host", "interval_seconds": 5.0})

    def test_reset_zero_delta_missing_and_malformed_never_fabricate_zero(self):
        self.stat([100, 0, 0, 100, 0, 0, 0, 0])
        self.sampler.cpu_usage(1)
        self.assertIsNone(self.sampler.cpu_usage(2)["percent"])
        self.stat([90, 0, 0, 120, 0, 0, 0, 0])
        self.assertIsNone(self.sampler.cpu_usage(3)["percent"])
        self.stat([100, 0, 0, 130, 0, 0, 0, 0])
        self.assertEqual(self.sampler.cpu_usage(4)["percent"], 50.0)
        (self.proc / "stat").unlink()
        self.assertIsNone(self.sampler.cpu_usage(5)["percent"])
        self.stat([110, 0, 0, 140, 0, 0, 0, 0])
        self.assertIsNone(self.sampler.cpu_usage(6)["percent"])
        for text in ("cpu 1 2", "cpu 1 2 3 4 5 6 7 -8", "cpu bad 2 3 4 5 6 7 8"):
            (self.proc / "stat").write_text(text)
            self.assertIsNone(cpu_counters(self.proc))
        self.stat([500, 0, 0, 500, 0, 0, 0, 0])
        stale = self.sampler.cpu_usage(1000000)
        self.assertIsNone(stale["percent"])
        self.assertIsNone(stale["interval_seconds"])
        self.stat([530, 0, 0, 570, 0, 0, 0, 0])
        self.assertEqual(self.sampler.cpu_usage(1000005)["percent"], 30.0)

    def test_memory_memavailable_bytes_partial_and_invalid_values(self):
        path = self.proc / "meminfo"
        path.write_text("MemTotal: 1000 kB\nMemFree: 50 kB\nMemAvailable: 400 kB\n")
        result = memory_usage(self.proc)
        self.assertEqual(result, {"total_bytes": 1024000, "used_bytes": 614400,
                                  "available_bytes": 409600, "percent": 60.0, "scope": "linux_host"})
        for value in ("", "MemAvailable: 1200 kB\n", "MemAvailable: -1 kB\n", "MemAvailable: 40 MB\n"):
            path.write_text("MemTotal: 1000 kB\n" + value)
            result = memory_usage(self.proc)
            self.assertEqual(result["total_bytes"], 1024000)
            self.assertIsNone(result["used_bytes"])
            self.assertIsNone(result["percent"])
        path.unlink()
        self.assertTrue(all(memory_usage(self.proc)[key] is None for key in ("total_bytes", "used_bytes", "available_bytes", "percent")))


class MetricsSamplingTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.proc = Path(self.tmp.name)
        (self.proc / "stat").write_text("cpu 100 0 0 100 0 0 0 0\n")
        (self.proc / "meminfo").write_text("MemTotal: 1000 kB\nMemAvailable: 400 kB\n")
        self.clock = Clock()

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def test_latency_fixed_hostname_port_monotonic_and_writer_cleanup(self):
        writer = Mock()
        writer.wait_closed = AsyncMock()

        async def connected(host, port):
            self.clock.now += 0.0123
            return object(), writer

        for url, expected in (("http://gateway:8080/", ("gateway", 8080)),
                              ("http://gateway/path?api_key=secret", ("gateway", 80)),
                              ("https://gateway/path", ("gateway", 443)),
                              ("https://[::1]/path", ("::1", 443))):
            writer.reset_mock()
            writer.wait_closed.reset_mock()
            sampler = SystemMetrics(url, self.proc, clock=self.clock)
            with patch("app.system_metrics.asyncio.open_connection", AsyncMock(side_effect=connected)) as connect:
                result = await sampler.network_rtt()
            self.assertEqual(result, {"rtt_ms": 12.3, "source": "console_gateway_tcp", "state": "ok"})
            connect.assert_awaited_once_with(*expected)
            writer.close.assert_called_once()
            writer.wait_closed.assert_awaited_once()
        for url in ("ftp://gateway:21", "http://gateway:bad", "http://gateway:0", "http://gateway:65536", "http://[broken", "gateway:8080", "http:///nohost"):
            sampler = SystemMetrics(url, self.proc, clock=self.clock)
            with patch("app.system_metrics.asyncio.open_connection", AsyncMock()) as connect:
                result = await sampler.network_rtt()
            connect.assert_not_awaited()
            self.assertEqual(result["state"], "unavailable")
            self.assertIsNone(result["rtt_ms"])

    async def test_network_failure_independent_from_host_stats(self):
        sampler = SystemMetrics("http://gateway:8080", self.proc, clock=self.clock)
        with patch("app.system_metrics.asyncio.open_connection", AsyncMock(side_effect=OSError("http://private-host/?api_key=secret"))):
            result = await sampler.sample()
            self.assertEqual(result["memory"]["percent"], 60.0)
            self.assertIsNone(result["cpu"]["percent"])
            self.assertEqual(result["network"]["state"], "unavailable")
            self.assertNotIn("private-host", str(result))
            (self.proc / "stat").unlink()
            self.clock.now += 6
            result = await sampler.sample()
            self.assertEqual(result["memory"]["percent"], 60.0)
            self.assertIsNone(result["cpu"]["percent"])

    async def test_cache_concurrent_requests_preserves_measurement_timestamp(self):
        calls = []

        writers = []

        async def connected(host, port):
            calls.append((host, port))
            await asyncio.sleep(0)
            self.clock.now += 0.02
            writer = Mock()
            writer.wait_closed = AsyncMock()
            writers.append(writer)
            return object(), writer

        sampler = SystemMetrics("http://gateway:8080", self.proc, clock=self.clock)
        with patch("app.system_metrics.asyncio.open_connection", AsyncMock(side_effect=connected)):
            results = await asyncio.gather(*(sampler.sample() for _ in range(20)))
            self.assertEqual(len(calls), 1)
            self.assertTrue(all(result["measured_at"] == results[0]["measured_at"] for result in results))
            self.assertIsNotNone(datetime.fromisoformat(results[0]["measured_at"]).tzinfo)
            self.assertIsNone(results[0]["cpu"]["percent"])
            self.clock.now += 4.9
            self.assertEqual((await sampler.sample())["measured_at"], results[0]["measured_at"])
            self.assertEqual(len(calls), 1)
            (self.proc / "stat").write_text("cpu 130 0 0 170 0 0 0 0\n")
            self.clock.now += 0.2
            second = await sampler.sample()
            self.assertEqual(len(calls), 2)
            self.assertEqual(second["cpu"]["percent"], 30.0)
            self.assertEqual(second["cpu"]["interval_seconds"], 5.12)
            (self.proc / "meminfo").unlink()
            (self.proc / "stat").write_text("cpu 160 0 0 240 0 0 0 0\n")
            self.clock.now += 6
            third = await sampler.sample()
            self.assertIsNone(third["memory"]["percent"])
            self.assertEqual(third["cpu"]["percent"], 30.0)
            self.assertEqual(third["network"]["state"], "ok")
        for writer in writers:
            writer.close.assert_called_once()
            writer.wait_closed.assert_awaited_once()

    async def test_tcp_connection_and_writer_cleanup_deadline_is_bounded(self):
        async def slow(host, port):
            await asyncio.sleep(3)

        sampler = SystemMetrics("http://gateway:8080", self.proc, clock=self.clock)
        with patch("app.system_metrics.asyncio.open_connection", AsyncMock(side_effect=slow)):
            self.assertEqual((await sampler.network_rtt())["state"], "unavailable")
        writer = Mock()

        async def slow_close():
            await asyncio.sleep(3)

        writer.wait_closed = AsyncMock(side_effect=slow_close)
        with patch("app.system_metrics.asyncio.open_connection", AsyncMock(return_value=(object(), writer))):
            self.assertEqual((await sampler.network_rtt())["state"], "ok")
        writer.close.assert_called_once()
        writer.wait_closed.assert_awaited_once()


class MetricsAuthorizationTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(agent_service.app)
        self.sample = AsyncMock(return_value={"measured_at": "2026-10-13T00:00:00+00:00", "cpu": {}, "memory": {}, "network": {}})

    def test_missing_auth_and_employee_cannot_collect_metrics(self):
        with patch.object(agent_service.system_metrics_sampler, "sample", self.sample):
            self.assertEqual(self.client.get("/api/system/metrics").status_code, 401)
            identity = AsyncMock(return_value={"roles": ["employee"]})
            with patch.object(agent_service, "authenticated_user", identity):
                self.assertEqual(self.client.get("/api/system/metrics", headers={"Authorization": "Bearer test"}).status_code, 403)
            identity.assert_awaited_once_with("Bearer test", require_scope=agent_contract.CONSOLE_SCOPE)
        self.sample.assert_not_awaited()

    def test_mcp_token_scope_cannot_read_admin_metrics(self):
        with patch.object(agent_contract, "authenticate", return_value=({"user_id": "root"}, {"sub": "root", "scope": "mcp", "jti": "00000000-0000-4000-8000-000000000001"})), \
             patch.object(oidc, "validate_session", AsyncMock()), \
             patch("app.disposal.blocked", return_value=False), \
             patch.object(agent_service.system_metrics_sampler, "sample", self.sample), \
             patch.object(agent_contract.db, "fetch_one", AsyncMock()) as fetch:
            self.assertEqual(self.client.get("/api/system/metrics", headers={"Authorization": "Bearer harness-token"}).status_code, 403)
            fetch.assert_not_awaited()
        self.sample.assert_not_awaited()

    def test_admin_console_receives_no_store_response_after_authentication(self):
        identity = AsyncMock(return_value={"roles": ["admin"]})
        with patch.object(agent_service, "authenticated_user", identity), \
             patch.object(agent_service.system_metrics_sampler, "sample", self.sample):
            response = self.client.get("/api/system/metrics", headers={"Authorization": "Bearer console-token"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.sample.return_value)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        identity.assert_awaited_once_with("Bearer console-token", require_scope=agent_contract.CONSOLE_SCOPE)
        self.sample.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
