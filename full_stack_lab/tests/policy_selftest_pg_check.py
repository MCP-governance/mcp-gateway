"""D-121 policy self-test against disposable PostgreSQL and the lab's real OPA.

Run only through termination_dispatch_lab.sh. OPA's policy management API is used
to upload one deliberately broken revision, then the original policy is restored.
No MCP endpoint is called and no decision rows are inserted by this test.
"""
from __future__ import annotations

import os
import json
from pathlib import Path
from urllib.parse import quote

import httpx

from app import db, ops_response
from termination_lab_support import Checks, apply_schema, run

CHECKS = Checks("policy self-test PostgreSQL and OPA")
OPA_URL = os.environ["OPA_URL"]
POLICY_PATH = "/policy/policy.rego"


async def actual_call_counts() -> tuple[int, int]:
    rows = await db.fetch_one("SELECT count(*) AS decisions, count(*) FILTER (WHERE COALESCE(client->>'event_kind','tools/call')='tools/call' AND action <> 'connect') AS calls FROM decisions")
    return int(rows["decisions"]), int(rows["calls"])


async def latest_test() -> dict:
    return await db.fetch_one("SELECT policy_hash,passed,results FROM alert_self_tests ORDER BY id DESC LIMIT 1")


def without_rule(source: str, rule: str) -> str:
    marker = f'candidate["{rule}"] := '
    if source.count(marker) != 1:
        raise ValueError(f"expected one {rule} rule")
    start = source.index(marker)

    def block_end(position: int) -> int:
        depth = 0
        for index in range(source.index("{", position), len(source)):
            depth += {"{": 1, "}": -1}.get(source[index], 0)
            if depth == 0:
                return index
        raise ValueError(f"unterminated {rule} rule")

    # `candidate[...] := {value} if {body}`: drop the body too, or the module no longer parses.
    end = block_end(start)
    if source[end + 1:].lstrip().startswith("if"):
        end = block_end(end + 1)
    return source[:start] + source[source.find("\n", end) + 1:]


async def policy_id_for_source(source: str) -> str:
    base = OPA_URL.split("/v1/")[0]
    async with httpx.AsyncClient(timeout=8, trust_env=False) as client:
        response = await client.get(base + "/v1/policies")
        if not response.is_success:
            raise httpx.HTTPStatusError(
                f"OPA policy list returned {response.status_code}: {response.text}",
                request=response.request, response=response)
        policies = response.json().get("result", [])
    matches = [policy.get("id") for policy in policies
               if policy.get("raw") == source and isinstance(policy.get("id"), str)]
    if len(matches) != 1:
        raise RuntimeError(f"expected one loaded OPA module matching {POLICY_PATH}; found {matches}")
    return matches[0]


async def upload_policy(policy_id: str, source: str) -> None:
    base = OPA_URL.split("/v1/")[0]
    url = base + "/v1/policies/" + quote(policy_id, safe="")
    async with httpx.AsyncClient(timeout=8, trust_env=False) as client:
        response = await client.put(url, content=source,
                                    headers={"Content-Type": "text/plain"})
        if not response.is_success:
            raise httpx.HTTPStatusError(
                f"OPA policy PUT {policy_id!r} returned {response.status_code}: {response.text}",
                request=response.request, response=response)


async def main() -> int:
    await apply_schema()
    before = await actual_call_counts()
    original = open(POLICY_PATH, encoding="utf-8").read()
    policy_id = await policy_id_for_source(original)
    broken_uploaded = False
    try:
        await ops_response.self_test(OPA_URL)
        good = await latest_test()
        cases = good["results"]
        expected = {
            "normal": ("Allow", "P-AUTHZ-ALLOW-001"),
            "new-tool": ("Block", "MCP-REGISTRY-001"),
            "unapproved-connection": ("Alert", "MCP-SHADOW-001"),
            "unapproved-listener": ("Alert", "MCP-SHADOW-002"),
            "call-burst": ("Approval", "P-VOLUME-001"),
            "repeated-denials": ("Alert", "P-ANOMALY-001"),
        }
        actual = {case["case"]: case for case in cases}
        correct = (good["passed"] and set(actual) == set(expected)
                   and all(actual[name]["passed"]
                           and all(actual[name]["actual"].get(k) == v for k, v in
                                   zip(("decision", "policy_id"), values))
                           for name, values in expected.items()))
        CHECKS.ok("loaded policy passes all six expected decision and policy ID cases", correct,
                  passed=good["passed"], cases=len(actual))

        alerts = await db.fetch_all("SELECT kind,synthetic,origin FROM ops_alerts ORDER BY id")
        synthetic = [row for row in alerts if row["synthetic"]]
        CHECKS.ok("five expected case alerts persist as synthetic and remain separate from live alerts",
                  len(synthetic) == 5 and all(row["origin"] in {"self-test", "catalog"} for row in synthetic)
                  and all(row["synthetic"] for row in alerts), kinds=[row["kind"] for row in alerts])

        broken_uploaded = True
        await upload_policy(policy_id, without_rule(original, "P-ANOMALY-001"))
        broken_info = await ops_response.release.policy_info(OPA_URL)
        corpus = json.loads(Path("/policy/replay_cases_pac15.json").read_text(encoding="utf-8"))["pac15_replay"]
        baseline = {**corpus["base"], **next(c["patch"] for c in corpus["cases"] if c["id"] == "normal-public-read")}
        probe = next(case for case in ops_response.self_test_cases(baseline) if case["name"] == "repeated-denials")
        async with httpx.AsyncClient(timeout=8, trust_env=False) as client:
            response = await client.post(OPA_URL, json={"input": probe["input"]})
            response.raise_for_status()
            broken_actual = response.json().get("result")
        CHECKS.ok("OPA serves the rule-reduced policy and no longer returns the removed policy ID",
                  not broken_info["matches"] and (not isinstance(broken_actual, dict)
                  or broken_actual.get("policy_id") != "P-ANOMALY-001"), actual=broken_actual)
        await ops_response.self_test(OPA_URL)
        broken = await latest_test()
        failure_alert = await db.fetch_one(
            "SELECT id,synthetic FROM ops_alerts WHERE kind='policy-self-test-failed' AND origin='self-test' AND origin_id=%s",
            (broken["policy_hash"],))
        CHECKS.ok("broken policy is recorded as failed and raises a synthetic alert",
                  not broken["passed"] and failure_alert is not None and failure_alert["synthetic"],
                  passed=broken["passed"], alert=bool(failure_alert), results=broken["results"])

        await upload_policy(policy_id, original)
        broken_uploaded = False
        unavailable = "http://127.0.0.1:1/v1/data/mcp/authz/decision"
        await ops_response.self_test(unavailable)
        outage = await latest_test()
        outage_alert = await db.fetch_one(
            "SELECT id,synthetic FROM ops_alerts WHERE kind='policy-self-test-failed' AND origin='self-test' AND origin_id=%s",
            (outage["policy_hash"],))
        CHECKS.ok("OPA outage is recorded as failed and raises a synthetic alert",
                  not outage["passed"] and outage_alert is not None and outage_alert["synthetic"],
                  passed=outage["passed"], alert=bool(outage_alert), results=outage["results"])
    finally:
        if broken_uploaded:
            try:
                await upload_policy(policy_id, original)
            except Exception as exc:
                raise RuntimeError(f"failed to restore OPA module {policy_id!r}") from exc

    after = await actual_call_counts()
    CHECKS.ok("synthetic self-tests leave decision and dashboard call counts unchanged", before == after,
              before=before, after=after)
    CHECKS.ok("dashboard-visible alert query excludes every synthetic alert",
              await db.fetch_one("SELECT count(*) AS n FROM ops_alerts WHERE NOT synthetic") == {"n": 0})
    return CHECKS.finish()


if __name__ == "__main__":
    run(main)
