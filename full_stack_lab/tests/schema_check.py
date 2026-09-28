#!/usr/bin/env python3
"""Every boot re-runs the schema files in order; none may narrow a CHECK another widened.

    python3 tests/schema_check.py

agent_tables.sql, lifecycle_tables.sql and v2_tables.sql each `DROP/ADD CONSTRAINT` on
every start, in that order (core.bootstrap, agent_service.lifespan). If an earlier file
re-adds a constraint with fewer values than a later file allows, the first row that uses
a later value (an 'anomaly' A.I.G job) makes the next start fail with CheckViolation.
Static only: parses the SQL, needs no database.
"""
from __future__ import annotations

import pathlib
import re
import sys

APP = pathlib.Path(__file__).resolve().parent.parent / "gateway" / "app"
FILES = ("agent_tables.sql", "lifecycle_tables.sql", "v2_tables.sql")  # boot order
CHECK = re.compile(r"ADD CONSTRAINT (\w+)\s+CHECK \(\s*\w+ IN \(([^)]*)\)\)", re.S)


def main() -> int:
    seen: dict[str, tuple[str, set[str]]] = {}
    failures = []
    for name in FILES:
        for constraint, values in CHECK.findall((APP / name).read_text(encoding="utf-8")):
            allowed = set(re.findall(r"'([^']*)'", values))
            if constraint in seen and seen[constraint][1] != allowed:
                failures.append(f"{constraint}: {seen[constraint][0]} {sorted(seen[constraint][1])} != {name} {sorted(allowed)}")
            seen[constraint] = (name, allowed)
    for failure in failures:
        print("FAIL", failure, file=sys.stderr)
    if not seen:
        print("FAIL 제약을 하나도 읽지 못했습니다.", file=sys.stderr)
        return 1
    print(f"PASS 기동마다 다시 만드는 CHECK 제약 {len(seen)}개가 파일 사이에서 같다" if not failures else "")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
