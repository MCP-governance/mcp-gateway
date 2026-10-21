"""Query stored Syft summaries and contain affected servers through the existing stop path."""
from __future__ import annotations

import re
import uuid

from . import db, ops_response

_SEMVER = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_BOUND = re.compile(r"(>=|<=|>|<|=)?\s*(\S+)")


def _version(value: str) -> tuple[int, int, int, tuple[str, ...]] | None:
    match = _SEMVER.fullmatch(value or "")
    if not match:
        return None
    prerelease = tuple(match[4].split(".")) if match[4] else ()
    if any(not part or (part.isdigit() and len(part) > 1 and part.startswith("0")) for part in prerelease):
        return None
    return int(match[1]), int(match[2]), int(match[3]), prerelease


def _compare(left: tuple, right: tuple) -> int:
    if left[:3] != right[:3]:
        return (left[:3] > right[:3]) - (left[:3] < right[:3])
    a, b = left[3], right[3]
    if not a or not b:
        return 0 if not a and not b else 1 if not a else -1
    for x, y in zip(a, b):
        if x == y:
            continue
        xn, yn = x.isdigit(), y.isdigit()
        if xn and yn:
            return (int(x) > int(y)) - (int(x) < int(y))
        if xn != yn:
            return -1 if xn else 1
        return (x > y) - (x < y)
    return (len(a) > len(b)) - (len(a) < len(b))


def _range(value: str) -> list[tuple[str, tuple]]:
    if not value.strip() or re.search(r"(?:^\s*,|,\s*(?:,|$))", value):
        raise ValueError("판본 범위 형식 오류")
    tokens = [token for token in re.split(r"[\s,]+", value.strip()) if token]
    if not tokens or len(tokens) > 4:
        raise ValueError("판본 범위 형식 오류")
    bounds = []
    for token in tokens:
        match = _BOUND.fullmatch(token)
        parsed = _version(match[2]) if match else None
        if not parsed:
            raise ValueError("판본 범위는 세 자리 의미 판본으로 입력하세요.")
        bounds.append((match[1] or "=", parsed))
    return bounds


def _matches(version: str, bounds: list[tuple[str, tuple]]) -> bool | None:
    parsed = _version(version)
    if parsed is None:
        return None
    for operator, bound in bounds:
        compared = _compare(parsed, bound)
        if not {"=": compared == 0, ">": compared > 0, ">=": compared >= 0,
                "<": compared < 0, "<=": compared <= 0}[operator]:
            return False
    return True


async def impact(package: str, version_range: str) -> dict:
    name = package.strip().casefold()
    if not name:
        raise ValueError("패키지 이름이 필요합니다.")
    bounds = _range(version_range)
    # shortcut: DB keeps only 200 SBOM components; a missing package in a truncated row is unknown.
    rows = await db.fetch_all(
        """SELECT s.id AS server_id, s.display_name, i.id::text AS intake_id,
                  i.source_ref, r.id::text AS runtime_id, r.generation,
                  (r.source_commit=i.commit_sha) AS source_match,
                  sr.id AS sbom_id, sr.status AS sbom_status,
                  i.evidence->'scanners'->'syft'->>'status' AS scan_status,
                  sr.summary->'inventory' AS inventory,
                  COALESCE((sr.summary->>'truncated')::boolean, false) AS truncated
             FROM mcp_servers s
             LEFT JOIN LATERAL (
                  SELECT id,source_ref,commit_sha,evidence FROM mcp_intake_requests
                   WHERE registered_server_id=s.id
                   ORDER BY updated_at DESC,created_at DESC,id DESC LIMIT 1
             ) i ON true
             LEFT JOIN mcp_runtimes r ON r.intake_id=i.id
             LEFT JOIN LATERAL (
                  SELECT id,status,summary FROM supply_chain_reports
                   WHERE source_ref=i.source_ref AND scanner='Syft'
                   ORDER BY imported_at DESC,id DESC LIMIT 1
             ) sr ON true
            ORDER BY s.id,r.generation NULLS FIRST""")
    servers = []
    for row in rows:
        inventory = row.get("inventory")
        if (row.get("sbom_status") != "IMPORTED" or row.get("scan_status") != "DONE"
                or (row.get("generation") is not None and row.get("source_match") is not True)
                or not isinstance(inventory, list)):
            judgement, evidence = "자료 없음", []
        else:
            components = [item for item in inventory if isinstance(item, dict)
                          and str(item.get("name") or "").strip().casefold() == name]
            evidence = [{"name": item.get("name"), "version": item.get("version"),
                         "purl": item.get("purl"), "sbom_id": row["sbom_id"]} for item in components]
            checks = [_matches(str(item.get("version") or ""), bounds) for item in components]
            if any(result is True for result in checks):
                judgement = "영향 있음"
            elif any(result is None for result in checks) or row.get("truncated"):
                judgement = "판단 불가"
            else:
                judgement = "영향 없음"
        servers.append({"server_id": row["server_id"], "server_name": row.get("display_name") or row["server_id"],
                        "runtime_id": row.get("runtime_id"), "generation": row.get("generation"),
                        "judgement": judgement, "evidence": evidence,
                        "sbom_truncated": bool(row.get("truncated")) if row.get("sbom_id") else None})
    counts = {key: sum(item["judgement"] == value for item in servers)
              for key, value in (("affected", "영향 있음"), ("unaffected", "영향 없음"),
                                 ("unknown", "판단 불가"), ("no_data", "자료 없음"))}
    return {"package": package.strip(), "version_range": version_range.strip(), "counts": counts, "servers": servers}


async def stop_affected(package: str, version_range: str, actor: str, reason: str) -> dict:
    result = await impact(package, version_range)
    batch = str(uuid.uuid4())
    affected = {}
    for row in result["servers"]:
        if row["judgement"] == "영향 있음":
            affected.setdefault(row["server_id"], []).append(row)
    succeeded, skipped, failed = [], [], []
    for server_id, generations in affected.items():
        evidence = {"package": result["package"], "version_range": result["version_range"],
                    "requested_by": actor, "sbom_generations": generations}
        try:
            created = await ops_response.suspend(
                server_id, "supply-chain", reason, evidence, batch=batch)
            (succeeded if created else skipped).append(server_id)
        except Exception as exc:
            failed.append({"server_id": server_id, "reason": type(exc).__name__})
    return {"batch": batch, "succeeded": succeeded, "skipped": skipped, "failed": failed,
            "counts": {"succeeded": len(succeeded), "skipped": len(skipped), "failed": len(failed)}}
