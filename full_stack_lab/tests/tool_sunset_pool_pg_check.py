"""S4-01: tool_sunset.check under the concurrency of one harness start, against isolated PostgreSQL.

A harness connects to every approved server at once, so tools/list asks for the state of ten tools
in parallel. Each check must hold at most one pool connection, and a failed check must leave its
audit event instead of vanishing. Needs DATABASE_URL to an empty database (dropped schema is fine).
"""
from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone
from unittest.mock import patch

os.environ.setdefault("DB_POOL_MAX", "10")
os.environ.setdefault("DB_POOL_TIMEOUT", "3")

from app import db, registry, retention, tool_sunset  # noqa: E402
from termination_lab_support import Checks, apply_schema, isolated_disposal, run  # noqa: E402

CHECKS = Checks("tool sunset pool PostgreSQL")
SERVER = "sunset-srv"
TOOLS = [f"tool_{i:02d}" for i in range(10)]
REVIEWED = {"tool_reviews": {t: {"reviewed_at": datetime.now(timezone.utc).isoformat()} for t in TOOLS}}


async def events(kind: str) -> list[dict]:
    return await db.fetch_all("SELECT target_id, outcome, reason FROM approval_events WHERE kind=%s ORDER BY id", (kind,))


async def concurrent_list() -> None:
    started = time.monotonic()
    states = await asyncio.gather(*(tool_sunset.check(SERVER, t) for t in TOOLS))
    elapsed = time.monotonic() - started
    unavailable = [t for t, s in zip(TOOLS, states) if not s.get("available", True)]
    CHECKS.ok("ten-concurrent-checks-all-available", not unavailable and elapsed < float(os.environ["DB_POOL_TIMEOUT"]),
              unavailable=unavailable, seconds=round(elapsed, 2))


async def coverage_gap_is_recorded() -> None:
    real = retention.setting

    async def short_retention():
        return {**await real(), "days": 30}
    with patch.object(retention, "setting", short_retention):
        state = await tool_sunset.check(SERVER, TOOLS[0])
    rows = [r for r in await events("tool-sunset-check") if r["target_id"] == f"{SERVER}/{TOOLS[0]}"]
    CHECKS.ok("coverage-gap-keeps-tool-and-leaves-event", state.get("available") and state["status"] == "자료 없음" and len(rows) == 1,
              state=state.get("status"), events=rows)


async def failure_is_recorded() -> None:
    async def broken(*_args, **_kwargs):
        raise RuntimeError("synthetic")
    with patch.object(tool_sunset, "_last_event", broken):
        state = await tool_sunset.check(SERVER, TOOLS[1])
    rows = [r for r in await events("tool-sunset-check") if r["target_id"] == f"{SERVER}/{TOOLS[1]}"]
    CHECKS.ok("failure-is-unavailable-and-recorded", state.get("available") is False and len(rows) == 1
              and rows[0]["reason"] == "RuntimeError", events=rows)


async def main() -> int:
    await apply_schema()
    with isolated_disposal(), patch.object(registry, "server", lambda sid: REVIEWED if sid == SERVER else None):
        await CHECKS.case("concurrent", concurrent_list())
        await CHECKS.case("coverage", coverage_gap_is_recorded())
        await CHECKS.case("failure", failure_is_recorded())
    return CHECKS.finish()


if __name__ == "__main__":
    run(main)
