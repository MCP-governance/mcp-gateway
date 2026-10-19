"""Output approval and negotiated result shapes (D-149)."""
from __future__ import annotations

from .contract import canonical_hash


NO_OUTPUT_SCHEMA_HASH = canonical_hash(None)
OBJECT_PROTOCOLS = {"2025-06-18", "2025-11-25"}
JSON_PROTOCOLS = {"2026-07-28"}


class WireRejected(RuntimeError):
    """SDK received a result that violates the negotiated wire contract."""


def approved_hash(row: dict) -> str:
    # Old approvals approved no output contract; never adopt a first observation.
    return row.get("approved_output_schema_hash") or NO_OUTPUT_SCHEMA_HASH


def matches(row: dict, schema) -> bool:
    return approved_hash(row) == canonical_hash(schema)


def observed_matches(row: dict) -> bool:
    return approved_hash(row) == (row.get("observed_output_schema_hash") or NO_OUTPUT_SCHEMA_HASH)


def for_protocol(payload: dict, protocol: str | None) -> dict:
    if "structured" not in payload:
        return payload
    value = payload["structured"]
    if protocol in JSON_PROTOCOLS or (protocol in OBJECT_PROTOCOLS and isinstance(value, dict)):
        return payload
    # Unknown/old callers get the conservative object-era behavior used before D-149.
    if protocol is None and isinstance(value, dict):
        return payload
    result = {key: item for key, item in payload.items() if key != "structured"}
    # Preserve the structured value even when the provider's text is only a summary.
    import json
    text = json.dumps(value, ensure_ascii=False, allow_nan=False)
    content = list(result.get("content") or [])
    if not any(item.get("type") == "text" and item.get("text") == text for item in content):
        content.append({"type": "text", "text": text})
    result["content"] = content
    result["structured_dropped"] = type(value).__name__
    return result
