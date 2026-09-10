"""Small, dependency-free helpers shared by the gateway and its self-check."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any


PATH_CLASSES = {
    "/data/public/notice.txt": "public",
    "/data/nonimportant/team-note.txt": "nonimportant",
    "/data/sensitive/secret.txt": "important",
}


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def sha256(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def classify_path(path: str) -> str | None:
    return PATH_CLASSES.get(path)


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
