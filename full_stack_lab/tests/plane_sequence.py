"""One real harness session across administrative changes: contract drift and a withdrawn
registration (D-62). The session stays open, so what changes is the Gateway's state, not
the client: the same Claude Code connection calls before, during and after each change.

  SSHPW=... python3 plane_sequence.py --console URL --ssh managed-pj1@HOST --person user \
      --server context7 --tool resolve-library-id --arguments '{"query":"x","libraryName":"fastapi"}' \
      --drift-on 'bash /tmp/r.sh sol /tmp/drift_on.sh' --drift-off 'bash /tmp/r.sh sol /tmp/drift_off.sh' < admin.json

--drift-on/--drift-off are operator commands run between calls (they change the approved
contract hash on the appliance and put it back). The withdrawal uses the Console API.
Prints one JSON line per step; exit 1 when a step does not match.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time

from plane_evidence import Harness, console, ledger_after


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("--console", "--ssh", "--person", "--server", "--tool", "--arguments", "--drift-on", "--drift-off"):
        parser.add_argument(name, required=True)
    parser.add_argument("--cwd", default="/tmp")
    parser.add_argument("--exec", default=None)
    parser.add_argument("--settle", type=int, default=130, help="seconds for the device policy and token to refresh")
    args = parser.parse_args()
    base = args.console.rstrip("/")
    token = console(base, "/auth/mock-login", body=json.load(sys.stdin))["access_token"]
    harness = Harness(args, "claude").start(args.cwd)
    failures = 0

    def step(name: str, expect: dict) -> None:
        nonlocal failures
        cursor = console(base, "/gw/activity?limit=1", token)["cursor"]
        answer = harness.tool(args.server, args.tool, json.loads(args.arguments))
        rows = ledger_after(base, token, cursor, args.person, args.server, args.tool, 1)
        row = rows[0] if len(rows) == 1 else {}
        got = {"decision": row.get("decision"), "policy_id": row.get("policy_id"), "attempted": row.get("attempted"),
               "executed": row.get("executed"), "response": row.get("response"), "decision_id": row.get("id"),
               "evidence_sha256": row.get("evidence_sha256"), "event": row.get("event_kind")}
        ok = len(rows) == 1 and all(got.get(k) == v for k, v in expect.items())
        failures += not ok
        print(json.dumps({"step": name, **got, "ledger_rows": len(rows), "ok": ok, "mock": False,
                          **({} if ok else {"expected": expect, "harness_answer": json.dumps(answer, ensure_ascii=False)[:300]})},
                         ensure_ascii=False), flush=True)

    try:
        step("approved", {"executed": True})
        subprocess.run(args.drift_on, shell=True, check=True, stdout=subprocess.DEVNULL)
        step("contract-drift", {"decision": "Block", "policy_id": "MCP-CATALOG-001", "attempted": False, "executed": False})
        subprocess.run(args.drift_off, shell=True, check=True, stdout=subprocess.DEVNULL)
        step("drift-restored", {"executed": True})
        console(base, f"/gw/registry/servers/{args.server}", token, method="DELETE")
        time.sleep(args.settle)
        step("registration-withdrawn", {"decision": "Block", "policy_id": "MCP-REGISTRY-001", "attempted": False, "executed": False})
    finally:
        harness.close_io()
    print(json.dumps({"steps": 4, "failed": failures}))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
