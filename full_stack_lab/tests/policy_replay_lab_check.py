"""The frozen replay corpus (the PAC-15 one that `console.sh test` replays) against the OPA of a disposable lab (no recorded traffic, no MCP call).

Same comparison as `python -m app.replay` + tests/replay_check.py, for a candidate policy bundle served
by a lab OPA: every labelled attack must still stop and every normal case must pass.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

os.environ.setdefault("OTEL_SDK_DISABLED", "true")
LAB = Path(__file__).resolve().parent.parent
for candidate in (LAB / "gateway", Path("/app")):
    if (candidate / "app").is_dir():
        sys.path.insert(0, str(candidate))
        break
sys.path.insert(0, str(LAB / "tests"))
from app import core, db, replay
import replay_check

OPA = LAB / "opa"


async def main() -> int:
    failed = 0
    try:
        await core.bootstrap()
        for corpus in ("replay_cases_pac15.json",):
            report = await replay.run(1, str(OPA / corpus))
            problems = replay_check.check(report)
            cases = report["frozen_corpus"]["cases"]
            print(f"{corpus}: {len(cases)} cases, missed attacks {report['frozen_corpus']['missed_attacks']}, "
                  f"false blocks {report['frozen_corpus']['false_blocks']} - {'PASS' if not problems else 'FAIL'}")
            for problem in problems:
                print("  -", problem)
            failed += bool(problems)
    finally:
        await db.close()
    return failed


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
