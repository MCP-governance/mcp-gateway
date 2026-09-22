"""One-shot, LAB_MODE-gated corporate-network scenario.

The scenario deliberately keeps the known-vulnerable package as metadata only.
It exercises the real Gateway, isolated scanner queue, and retirement workflow
without installing or executing the vulnerable package.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

from . import core, db, decommission

ACTOR = "admin-demo"
EMPLOYEE = "emp-demo"
SERVER_ID = "mock-http"
REQUEST_ID = "dc6d56fd-75c3-48fc-9e5a-0290553a14c6"
SOURCE_URL = "https://github.com/modelcontextprotocol/servers"
SOURCE_REF = "npm:@modelcontextprotocol/server-filesystem@0.6.2"
ADVISORY = {
    "id": "GHSA-q66q-fx2p-7w4m",
    "cve": "CVE-2025-53109",
    "severity": "high",
    "url": "https://github.com/advisories/GHSA-q66q-fx2p-7w4m",
    "note": "LAB evidence: package metadata only; vulnerable package is never installed or run.",
}
EXIT_TERMS = {
    "provider_credential_disclosure": True,
    "revocation_evidence": True,
    "audit_access_retained": True,
}
NETWORK_INVENTORY = Path("/reports/aig-network-inventory.json")


def require_lab() -> None:
    if os.getenv("LAB_MODE") != "1":
        raise RuntimeError("This scenario is disabled unless LAB_MODE=1.")


def emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


async def seed() -> dict:
    """Register one controlled exception and prove it was callable before containment."""
    require_lab()
    await db.wait_until_ready()
    server = await db.fetch_one("SELECT lifecycle FROM mcp_servers WHERE id=%s", (SERVER_ID,))
    if not server or server["lifecycle"] != "OPERATING":
        raise RuntimeError("A fresh lab database is required before seed (run ./console.sh reset).")

    await db.execute(
        """UPDATE mcp_servers SET display_name=%s, source_url=%s, source_ref=%s,
               supplier=%s, status='READY', status_reason=%s, scan_path=%s, exit_terms=%s
             WHERE id=%s""",
        ("LAB | Filesystem MCP 0.6.2 metadata proxy", SOURCE_URL, SOURCE_REF,
         "Model Context Protocol (lab exception)",
         "LAB ONLY: controlled exception pending isolated SCA and A.I.G evidence.",
         "full_stack_lab/lab/candidates/filesystem-0.6.2", Jsonb(EXIT_TERMS), SERVER_ID),
    )
    await db.execute(
        """INSERT INTO mcp_intake_requests(
               id, submitted_by, display_name, repository_url, requested_transport, purpose,
               status, risk_level, review_note, reviewed_by, reviewed_at, commit_sha,
               source_ref, evidence, validated_at, exit_terms)
             VALUES (%s,%s,%s,%s,'streamable-http',%s,'APPROVED','HIGH',%s,%s,now(),%s,%s,%s,now(),%s)
             ON CONFLICT (id) DO NOTHING""",
        (REQUEST_ID, EMPLOYEE, "LAB EXCEPTION | @modelcontextprotocol/server-filesystem 0.6.2",
         SOURCE_URL, "Controlled exception to test containment; no vulnerable binary is installed.",
         "LAB ONLY: approved solely to exercise containment after verified advisory evidence.", ACTOR,
         "metadata-only:0.6.2", SOURCE_REF,
         Jsonb({"lab_only": True, "advisory": ADVISORY, "package_installed": False}),
         Jsonb(EXIT_TERMS)),
    )
    await db.execute(
        "DELETE FROM supply_chain_reports WHERE scanner=%s AND source_ref=%s",
        ("GitHub Advisory Database (lab evidence)", SOURCE_REF),
    )
    await db.execute(
        """INSERT INTO supply_chain_reports(
               scanner, scanner_version, source_ref, report_path, status, high_count, summary)
             VALUES (%s,%s,%s,%s,'VERIFIED_LAB',1,%s)""",
        ("GitHub Advisory Database (lab evidence)", ADVISORY["id"], SOURCE_REF,
         "full_stack_lab/lab/README.md", Jsonb({"advisory": ADVISORY, "lab_only": True})),
    )
    before = await core.execute_call({
        "tool_name": "read_document", "user_token": EMPLOYEE, "document_id": "notice-001",
        "lab_scenario": "before-containment",
    })
    if not before["upstream_executed"]:
        raise RuntimeError("Controlled exception did not reach the mock MCP before containment.")
    return {"phase": "introduced", "source_ref": SOURCE_REF, "pre_containment": before,
            "package_installed": False, "advisory": ADVISORY}


async def verify_supply() -> dict:
    """Return actual Trivy output separately from the manually verified advisory."""
    require_lab()
    trivy = await db.fetch_one(
        """SELECT critical_count, high_count, medium_count, summary, imported_at
             FROM supply_chain_reports WHERE scanner='Trivy' AND source_ref=%s
             ORDER BY id DESC LIMIT 1""", (SOURCE_REF,))
    advisory = await db.fetch_one(
        """SELECT high_count, summary, imported_at FROM supply_chain_reports
             WHERE scanner='GitHub Advisory Database (lab evidence)' AND source_ref=%s
             ORDER BY id DESC LIMIT 1""", (SOURCE_REF,))
    if not trivy or not advisory:
        raise RuntimeError("Trivy report and verified advisory evidence are both required.")
    return {"phase": "supply-chain", "trivy": trivy, "verified_advisory": advisory,
            "trivy_caught": bool(sum(int(trivy[key] or 0) for key in
                                      ("critical_count", "high_count", "medium_count")))}


def network_inventory() -> dict:
    if not NETWORK_INVENTORY.exists():
        raise RuntimeError("Run the lab network inventory before the A.I.G scan.")
    try:
        inventory = json.loads(NETWORK_INVENTORY.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("The lab network inventory is not valid JSON.") from exc
    if inventory.get("scope") != "compose-managed-container-addresses":
        raise RuntimeError("The network inventory escaped the Compose asset scope.")
    if not inventory.get("target_count"):
        raise RuntimeError("The network inventory contains no live container address.")
    if not any(item.get("port") == 9000 for item in inventory.get("open") or []):
        raise RuntimeError("The registered MCP TCP endpoint was not discovered.")
    return inventory


async def verify_network() -> dict:
    require_lab()
    inventory = network_inventory()
    return {"phase": "network-inventory", "scope": inventory["scope"],
            "target_count": inventory["target_count"], "open": inventory["open"]}


async def verify_aig() -> dict:
    """Test the real mcp-scan queue/SARIF path but do not convert a test double into control."""
    require_lab()
    report = await db.fetch_one(
        """SELECT critical_count, high_count, medium_count, summary, imported_at
             FROM supply_chain_reports WHERE scanner='AI-Infra-Guard mcp-scan' AND source_ref=%s
             ORDER BY id DESC LIMIT 1""", (SOURCE_REF,))
    if not report:
        raise RuntimeError("A.I.G mcp-scan report is missing.")
    summary = report["summary"] or {}
    mode = summary.get("evidence_mode")
    if mode not in {"live", "test-double"}:
        raise RuntimeError("A.I.G report has no usable evidence_mode: " + repr(mode))
    if not summary.get("total"):
        raise RuntimeError("A.I.G mcp-scan returned no finding at all.")
    # 배선 확인(test-double)과 실제 점검(live)은 둘 다 정상 경로다. 이전 판은
    # test-double만 통과시켜서, A.I.G를 실제로 연결하면 그 성공이 실패로 판정됐다.
    # 무엇을 주장할 수 있는지가 다를 뿐이라 주장 문구만 갈라 둔다.
    claim = ("live A.I.G findings attributed to this source_ref"
             if mode == "live"
             else "test-double output is evidence of queue/SARIF wiring only")
    return {"phase": "aig", "report": report, "evidence_mode": mode, "control_claim": claim}


async def contain() -> dict:
    """Contain only after both distinct evidence types exist, then prove no upstream effect."""
    require_lab()
    await verify_supply()
    await verify_aig()
    await db.execute(
        """UPDATE mcp_servers SET status='BLOCKED_SUPPLY_CHAIN', status_reason=%s
             WHERE id=%s AND lifecycle='OPERATING'""",
        ("LAB containment after verified GHSA evidence; A.I.G test-double retained as non-control evidence.",
         SERVER_ID),
    )
    result = await core.execute_call({
        "tool_name": "read_document", "user_token": EMPLOYEE, "document_id": "notice-001",
        "lab_scenario": "after-containment",
    })
    if (result["decision"] != "Block" or result["policy_id"] != "MCP-SUPPLY-001"
            or result["upstream_executed"] or result["effect_after"] != result["effect_before"]):
        raise RuntimeError("Containment did not produce MCP-SUPPLY-001 with zero upstream effect.")
    return {"phase": "contained", "decision": result}


async def open_retirement() -> dict:
    require_lab()
    detail = await decommission.open_case(
        SERVER_ID, "Verified vulnerable-version lab candidate must be removed.", ACTOR,
        "LAB | Filesystem MCP 0.6.2 controlled exception",
    )
    blocked = await core.execute_call({
        "tool_name": "read_document", "user_token": EMPLOYEE, "document_id": "notice-001",
        "lab_scenario": "post-cutover",
    })
    if blocked["upstream_executed"]:
        raise RuntimeError("A post-cutover call reached upstream.")
    return {"phase": "retirement-open", "case_id": str(detail["case"]["id"]),
            "post_cutover_decision": blocked, "targets": detail["targets"]}


async def finish_retirement() -> dict:
    """The console removes mock-http-mcp before this step, making liveness evidence real."""
    require_lab()
    case = await db.fetch_one(
        """SELECT id FROM termination_cases WHERE server_id=%s AND status <> 'CLOSED'
             ORDER BY opened_at DESC LIMIT 1""", (SERVER_ID,))
    if not case:
        raise RuntimeError("Open a retirement case before finishing it.")
    case_id = str(case["id"])
    detail = await decommission.case_detail(case_id)
    for target in detail["targets"]:
        target_id = str(target["id"])
        await decommission.revoke_target(target_id, ACTOR, "REVOKED", "LAB controlled revocation")
        kind = "provider-attestation" if target["holder"] == "provider" else "revocation-response"
        source = "provider-disclosure" if target["holder"] == "provider" else "gateway-ledger"
        await decommission.add_evidence(
            case_id, kind, target["label"], source,
            {"lab_only": True, "target_id": target_id, "status": "REVOKED"}, ACTOR,
            target_id=target_id,
        )
    probe = await decommission.probe(case_id, ACTOR)
    if probe["reachable"]:
        raise RuntimeError("The MCP endpoint is still reachable; remove mock-http-mcp before retirement.")
    assessed = await decommission.assess(case_id, ACTOR)
    grade = assessed["case"].get("grade")
    if grade != "T1":
        raise RuntimeError(f"Retirement did not meet T1: {grade}")
    closed = await decommission.close_case(case_id, ACTOR, "LAB removal verified after container deletion.")
    return {"phase": "retired", "grade": grade, "case": closed["case"],
            "probe": probe, "criteria": assessed["case"].get("criteria")}


async def summary() -> dict:
    require_lab()
    server = await db.fetch_one("SELECT id, display_name, status, lifecycle, source_ref FROM mcp_servers WHERE id=%s", (SERVER_ID,))
    request = await db.fetch_one("SELECT id, status, risk_level, source_ref FROM mcp_intake_requests WHERE id=%s", (REQUEST_ID,))
    reports = await db.fetch_all(
        """SELECT scanner, scanner_version, status, critical_count, high_count, medium_count, summary
             FROM supply_chain_reports WHERE source_ref=%s ORDER BY id""", (SOURCE_REF,))
    case = await db.fetch_one(
        """SELECT id, status, grade, closed_at FROM termination_cases WHERE server_id=%s
             ORDER BY opened_at DESC LIMIT 1""", (SERVER_ID,))
    decisions = await db.fetch_all(
        """SELECT decision, policy_id, upstream_executed, upstream_attempted, created_at
             FROM decisions WHERE tool_name='read_document' ORDER BY id DESC LIMIT 6""")
    return {"lab_mode": True, "package_installed": False, "network_inventory": network_inventory(), "server": server,
            "controlled_exception": request, "reports": reports, "retirement": case,
            "recent_gateway_decisions": decisions}


def self_check() -> dict:
    assert SOURCE_REF.endswith("@0.6.2")
    assert ADVISORY["id"].startswith("GHSA-")
    assert all(EXIT_TERMS.values())
    return {"ok": True, "source_ref": SOURCE_REF, "package_installed": False}


async def run(command: str) -> dict:
    if command == "seed":
        return await seed()
    if command == "verify-supply":
        return await verify_supply()
    if command == "verify-network":
        return await verify_network()
    if command == "verify-aig":
        return await verify_aig()
    if command == "contain":
        return await contain()
    if command == "open-retirement":
        return await open_retirement()
    if command == "finish-retirement":
        return await finish_retirement()
    if command == "summary":
        return await summary()
    if command == "self-check":
        require_lab()
        return self_check()
    raise ValueError(f"Unknown lab command: {command}")


async def run_and_close(command: str) -> dict:
    try:
        return await run(command)
    finally:
        await db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("self-check", "seed", "verify-network", "verify-supply", "verify-aig",
                                               "contain", "open-retirement", "finish-retirement", "summary"))
    args = parser.parse_args()
    emit(asyncio.run(run_and_close(args.command)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
