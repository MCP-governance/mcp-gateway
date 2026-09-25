"""Compare recorded policy inputs with a candidate OPA; never call an MCP tool."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

import httpx

from . import db
from .core import POLICY_RESULT, canonical_hash

OPA_URL = os.getenv("REPLAY_OPA_URL", os.getenv("OPA_URL", "http://opa:8181/v1/data/mcp/authz/decision"))
EXECUTABLE = {"Allow", "Alert", "Restrict"}
POST_EXECUTION = {"MCP-OUTPUT-001", "MCP-UPSTREAM-001", "P-CONTROL-FAIL-CLOSED"}


def classify(recorded: dict, candidate: dict) -> str:
    baseline = recorded["would_decision"] if recorded["enforcement"] == "monitor" and recorded["would_decision"] else recorded["decision"]
    baseline_policy = recorded["would_policy_id"] if recorded["enforcement"] == "monitor" and recorded["would_policy_id"] else recorded["policy_id"]
    if baseline not in EXECUTABLE and candidate["decision"] in EXECUTABLE:
        return "newly_executable"
    if baseline in EXECUTABLE and candidate["decision"] not in EXECUTABLE:
        return "newly_nonexecuting"
    if (baseline, baseline_policy) != (
            candidate["decision"], candidate["policy_id"]):
        return "changed"
    return "same"


async def _candidate(client: httpx.AsyncClient, policy_input: dict) -> dict:
    response = await client.post(OPA_URL, json={"input": policy_input})
    response.raise_for_status()
    candidate = response.json().get("result")
    if not POLICY_RESULT.is_valid(candidate):
        raise RuntimeError("Candidate OPA returned an invalid decision contract")
    return candidate


async def run(limit: int, corpus_path: str = "/policy/replay_cases.json") -> dict:
    rows = await db.fetch_all(
        """SELECT id, request_id, trace_id, decision, policy_id, policy_version,
                  upstream_attempted, upstream_executed, enforcement,
                  would_decision, would_policy_id, policy_input
           FROM decisions WHERE policy_input IS NOT NULL ORDER BY id DESC LIMIT %s""",
        (limit,),
    )
    comparisons = []
    corpus = json.loads(Path(corpus_path).read_text(encoding="utf-8"))
    if not isinstance(corpus.get("base"), dict) or not isinstance(corpus.get("cases"), list):
        raise ValueError("Invalid frozen replay corpus")
    async with httpx.AsyncClient(timeout=8, trust_env=False) as client:
        for row in reversed(rows):
            if row["policy_id"] in POST_EXECUTION or row["policy_version"] == "unknown":
                continue
            candidate = await _candidate(client, row["policy_input"])
            category = classify(row, candidate)
            comparisons.append({
                "decision_id": row["id"], "request_id": str(row["request_id"]),
                "trace_id": row["trace_id"],
                "input_sha256": canonical_hash(row["policy_input"]),
                "recorded": {"decision": row["decision"], "policy_id": row["policy_id"],
                             "policy_version": row["policy_version"],
                             "upstream_attempted": row["upstream_attempted"],
                             "upstream_executed": row["upstream_executed"]},
                "baseline": {"decision": row["would_decision"] if row["enforcement"] == "monitor" and row["would_decision"] else row["decision"],
                             "policy_id": row["would_policy_id"] if row["enforcement"] == "monitor" and row["would_policy_id"] else row["policy_id"]},
                "candidate": {"decision": candidate["decision"], "policy_id": candidate["policy_id"],
                              "policy_version": candidate.get("policy_version")},
                "category": category,
            })
        cases = []
        for item in corpus["cases"]:
            if item.get("label") not in {"attack", "normal"} or not isinstance(item.get("patch"), dict):
                raise ValueError("Invalid frozen replay case")
            policy_input = {**corpus["base"], **item["patch"]}
            candidate = await _candidate(client, policy_input)
            executable = candidate["decision"] in EXECUTABLE
            cases.append({"id": item["id"], "label": item["label"],
                          "input_sha256": canonical_hash(policy_input),
                          "candidate": {"decision": candidate["decision"], "policy_id": candidate["policy_id"]},
                          "passed": executable == (item["label"] == "normal")})
    return {"mode": "policy-only; no MCP execution", "opa_url": OPA_URL,
            "compared": len(comparisons), "skipped": len(rows) - len(comparisons),
            "counts": {kind: sum(item["category"] == kind for item in comparisons)
                       for kind in ("same", "changed", "newly_executable", "newly_nonexecuting")},
            "comparisons": comparisons,
            "frozen_corpus": {"source": "synthetic labeled fixtures", "cases": cases,
                              "missed_attacks": sum(c["label"] == "attack" and not c["passed"] for c in cases),
                              "false_blocks": sum(c["label"] == "normal" and not c["passed"] for c in cases)}}


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--corpus", default="/policy/replay_cases.json")
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000:
        parser.error("--limit must be 1..1000")
    try:
        print(json.dumps(await run(args.limit, args.corpus), ensure_ascii=False, indent=2))
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
