"""Deterministic suggestions; only the recorded human approval enables them."""
from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import urlsplit


def digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                                     default=str).encode()).hexdigest()


def server_id(row: dict) -> str:
    address = urlsplit(row.get("endpoint_url") or row.get("repository_url") or "")
    source = address.hostname if row.get("intake_kind") == "remote-endpoint" else address.path.strip("/")
    slug = re.sub(r"[^a-z0-9]+", "-", (source or "mcp").lower()).strip("-")
    slug = re.sub(r"^[^a-z]+", "", slug)[:21].rstrip("-") or "mcp"
    return f"{slug}-{str(row['id']).replace('-', '')[:8]}"


def action(tool: dict) -> str:
    hints = {k.replace("_", "").lower(): v for k, v in (tool.get("annotations") or {}).items()}
    arguments = " ".join((tool.get("input_schema") or {}).get("properties") or {})
    if hints.get("destructivehint") is True or re.search(r"command|script|shell|exec", arguments, re.I):
        return "x"
    return tool.get("suggested") if tool.get("suggested") in {"r", "w", "x"} else (
        "r" if hints.get("readonlyhint") is True else "x" if hints.get("openworldhint") is True else "w")


def risk_input(row: dict, tools: list[dict]) -> dict:
    stated = row.get("risk_input") or {}
    text = json.dumps(tools, ensure_ascii=False).lower()
    personal = "sensitive" if re.search(r"health|medical|biometric|건강|의료|민감", text) else (
        "unique_id" if re.search(r"passport|ssn|주민등록|여권", text) else (
            "general" if re.search(r"email|phone|customer|person|이메일|고객|개인", text) else "none"))
    return {"data_class": stated.get("data_class", "important"), "personal_data": personal,
            "external_transfer": row.get("intake_kind") == "remote-endpoint" or any(
                (t.get("annotations") or {}).get("openWorldHint", (t.get("annotations") or {}).get("open_world_hint", True))
                is not False for t in tools),
            "permission": max((action(t) for t in tools), key=lambda a: "rwx".index(a), default="x"),
            "users": 1, "autonomy": "autonomous"}


def tool_reviews(row: dict, tools: list[dict]) -> dict:
    # Inferring a URL destination from an argument name would grant arbitrary egress. Keep it empty.
    return {t["name"]: {"purpose": row["purpose"][:200], "asset": row["display_name"][:200],
                        "destinations": [], "inputs": list((t.get("input_schema") or {}).get("properties") or {}),
                        "mask": True, "grade": "public", "accepts_from": [], "consent": True}
            for t in tools}


def supplier(row: dict) -> dict:
    record = row.get("provenance") or {}
    return {**(record.get("supplier_metadata") or {}), **((row.get("evidence") or {}).get("supplier_assurance") or {})}


def source_record(row: dict, found: dict) -> dict:
    if row.get("intake_kind") != "remote-endpoint":
        return row.get("provenance") or {}
    return {"kind": "provider-hosted", "source_url": row["endpoint_url"], "version": found["version"],
            "version_immutable": False, "license": {"spdx": None, "applicable": False},
            "artifact": {"applicable": False, "reason": "해당 없음", "endpoint": row["endpoint_url"]},
            "contract_sha256": found["catalog_hash"]}


def basis(row: dict) -> str:
    return digest({**{key: row.get(key) for key in ("submitted_by", "repository_url", "endpoint_url", "commit_sha",
                   "source_ref", "purpose", "requested_tools", "local_reason")},
                   "data_class": (row.get("risk_input") or {}).get("data_class", "important"),
                   "artifact": (row.get("provenance") or {}).get("artifact") if row.get("intake_kind") == "repository" else None})


def scan_basis(gate: dict) -> str:
    critical = gate.get("critical") or {}
    return digest({"scanners": gate.get("scanners"), "vuln_db": (gate.get("vuln_db") or {}).get("updated_at"),
                   "critical": {"count": critical.get("count"), "ids": critical.get("ids")}})
