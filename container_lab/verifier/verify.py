from __future__ import annotations

import json
import sys
from pathlib import Path


def read_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: verify.py <request-id>")
        return 2
    request_id = sys.argv[1]
    audits = [event for event in read_events(Path("/audit/gateway.jsonl")) if event.get("request_id") == request_id]
    effects = [event for event in read_events(Path("/effects/effects.jsonl")) if event.get("request_id") == request_id]
    audit = audits[-1] if audits else None
    if not audit:
        outcome = {"request_id": request_id, "status": "FAIL", "reason": "no gateway audit event"}
    elif audit["decision"] == "DENY":
        passed = not audit["upstream_called"] and not effects
        outcome = {
            "request_id": request_id,
            "status": "PASS" if passed else "FAIL",
            "decision": "DENY",
            "upstream_called": audit["upstream_called"],
            "matching_effects": len(effects),
            "rule": "a blocked request must leave no mock-MCP effect",
        }
    else:
        passed = audit["decision"] == "ALLOW" and audit["upstream_called"] and len(effects) == 1
        outcome = {
            "request_id": request_id,
            "status": "PASS" if passed else "FAIL",
            "decision": audit["decision"],
            "upstream_called": audit["upstream_called"],
            "matching_effects": len(effects),
            "rule": "an allowed request must leave exactly one mock-MCP effect",
        }
    print(json.dumps(outcome, ensure_ascii=False, indent=2))
    return 0 if outcome["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
