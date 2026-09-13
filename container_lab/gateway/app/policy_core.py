"""Small, dependency-free helpers shared by the gateway and its self-check."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from typing import Any


PATH_CLASSES = {
    "/data/public/notice.txt": "public",
    "/data/nonimportant/team-note.txt": "nonimportant",
    "/data/sensitive/secret.txt": "important",
}

APPROVED_TOOL = {
    "server_id": "file-mcp",
    "name": "read_file",
    "description": "Read one approved synthetic lab file.",
    "input_schema": {
        "type": "object",
        "properties": {"path": {"type": "string", "enum": sorted(PATH_CLASSES)}},
        "required": ["path"],
        "additionalProperties": False,
    },
}
METADATA_RISK = re.compile(r"\\b(bypass|curl|exfiltrat|ignore|secret|upload)\\b", re.IGNORECASE)


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def sha256(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def classify_path(path: str) -> str | None:
    return PATH_CLASSES.get(path)


def scan_catalog(tools: object) -> dict[str, bool]:
    """Tiny AIG-inspired MCP catalog preflight before the Rego decision."""
    if not isinstance(tools, list):
        return {"known_tools_only": False, "schema_hash_match": False, "description_hash_match": False, "metadata_safe": False}
    matching = [tool for tool in tools if isinstance(tool, dict) and tool.get("server_id") == APPROVED_TOOL["server_id"] and tool.get("name") == APPROVED_TOOL["name"]]
    tool = matching[0] if len(matching) == 1 else {}
    description = tool.get("description") if isinstance(tool, dict) else None
    # ponytail: metadata keywords are a lab-only tripwire; use a maintained scanner for production coverage.
    return {
        "known_tools_only": len(tools) == 1 and len(matching) == 1,
        "schema_hash_match": sha256(tool.get("input_schema")) == sha256(APPROVED_TOOL["input_schema"]),
        "description_hash_match": sha256(description) == sha256(APPROVED_TOOL["description"]),
        "metadata_safe": isinstance(description, str) and not METADATA_RISK.search(description),
    }


def assertion_payload(call: dict[str, Any], role: str) -> dict[str, str]:
    return {
        "request_id": str(call["request_id"]),
        "session_id": str(call["session_id"]),
        "user_id": str(call["user_id"]),
        "agent_id": str(call["agent_id"]),
        "tool_call_id": str(call["tool_call_id"]),
        "server_id": str(call["server_id"]),
        "tool_name": str(call["tool_name"]),
        "arguments_sha256": sha256(call["arguments"]),
        "role": role,
    }


def sign_assertion(call: dict[str, Any], role: str, secret: str) -> str:
    payload = canonical(assertion_payload(call, role)).encode()
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def verify_assertion(call: dict[str, Any], role: str, signature: str | None, secret: str) -> bool:
    if not signature:
        return False
    return hmac.compare_digest(sign_assertion(call, role, secret), signature)
