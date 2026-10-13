"""Solution Linux host usage and Console-to-Gateway DNS/TCP connection duration."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
import re
import time
from urllib.parse import urlsplit


def cpu_counters(proc_root: Path) -> tuple[int, ...] | None:
    try:
        with (proc_root / "stat").open(encoding="ascii") as stream:
            row = stream.readline().split()
        if len(row) < 9 or row[0] != "cpu":
            return None
        # guest/guest_nice are already included in user/nice; count the first eight only.
        counters = tuple(int(value) for value in row[1:9])
        return counters if all(value >= 0 for value in counters) else None
    except (OSError, UnicodeError, ValueError):
        return None


def memory_usage(proc_root: Path) -> dict:
    result = {"total_bytes": None, "used_bytes": None, "available_bytes": None,
              "percent": None, "scope": "linux_host"}
    try:
        text = (proc_root / "meminfo").read_text(encoding="ascii")
    except (OSError, UnicodeError):
        return result
    values = {}
    for key in ("MemTotal", "MemAvailable"):
        match = re.search(rf"^{key}:\s+(\d+)\s+kB\s*$", text, re.MULTILINE)
        values[key] = int(match[1]) * 1024 if match else None
    total, available = values["MemTotal"], values["MemAvailable"]
    if total is None or total <= 0:
        return result
    result["total_bytes"] = total
    if available is not None and 0 <= available <= total:
        result.update(available_bytes=available, used_bytes=total - available,
                      percent=round((total - available) * 100 / total, 2))
    return result


class SystemMetrics:
    def __init__(self, gateway_url: str, proc_root: Path = Path("/proc"), *, clock=time.monotonic):
        self.gateway_host, self.gateway_port = None, None
        try:
            target = urlsplit(gateway_url)
            if target.scheme in {"http", "https"} and target.hostname:
                port = target.port if target.port is not None else 443 if target.scheme == "https" else 80
                if 1 <= port <= 65535:
                    self.gateway_host, self.gateway_port = target.hostname, port
        except ValueError:
            pass
        self.proc_root = proc_root
        self.clock = clock
        self.lock = asyncio.Lock()
        self.previous_cpu = None
        self.cached = None
        self.cached_at = None

    def cpu_usage(self, now: float) -> dict:
        result = {"percent": None, "scope": "linux_host", "interval_seconds": None}
        counters = cpu_counters(self.proc_root)
        if counters is None:
            self.previous_cpu = None
            return result
        previous = self.previous_cpu
        self.previous_cpu = (counters, now)
        if previous is None:
            return result
        old, then = previous
        interval = now - then
        if interval <= 0 or interval > 30 or any(current < prior for current, prior in zip(counters, old)):
            return result
        total = sum(counters) - sum(old)
        idle = counters[3] + counters[4] - old[3] - old[4]
        if total > 0 and 0 <= idle <= total:
            result.update(percent=round((total - idle) * 100 / total, 2),
                          interval_seconds=round(interval, 3))
        return result

    async def network_rtt(self) -> dict:
        result = {"rtt_ms": None, "source": "console_gateway_tcp", "state": "unavailable"}
        if not self.gateway_host or not self.gateway_port:
            return result
        writer = None
        try:
            # The target is fixed deployment configuration, never a caller-supplied address.
            async with asyncio.timeout(2):
                try:
                    started = self.clock()
                    _, writer = await asyncio.open_connection(self.gateway_host, self.gateway_port)
                    elapsed = self.clock() - started
                    if elapsed >= 0:
                        result.update(rtt_ms=round(elapsed * 1000, 2), state="ok")
                finally:
                    if writer is not None:
                        writer.close()
                        await writer.wait_closed()
        except (OSError, ValueError, TimeoutError):
            pass
        return result

    async def sample(self) -> dict:
        async with self.lock:
            now = self.clock()
            if self.cached_at is not None and 0 <= now - self.cached_at < 5:
                return self.cached
            cpu = self.cpu_usage(now)
            memory = memory_usage(self.proc_root)
            network = await self.network_rtt()
            self.cached = {"measured_at": datetime.now(UTC).isoformat(timespec="milliseconds"),
                           "cpu": cpu, "memory": memory, "network": network}
            self.cached_at = self.clock()
            return self.cached
