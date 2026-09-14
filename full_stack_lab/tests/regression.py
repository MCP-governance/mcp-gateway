#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8080"
EMAIL = "customer@bob.local"
_token: str | None = None


def request(path: str, body: dict | None = None, token: str | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    with urlopen(Request(BASE + path, data=data, headers=headers), timeout=10) as response:
        return json.load(response)


def token() -> str:
    """The gateway API needs a signed synthetic identity like every other ingress."""
    global _token
    if _token is None:
        _token = request("/api/session", {
            "email": EMAIL, "password": os.getenv("MOCK_SSO_PASSWORD", "test-password"),
        })["access_token"]
    return _token


def wait_ready() -> None:
    for _ in range(60):
        try:
            if request("/api/health")["status"] == "ok":
                print("PASS core services ready")
                return
        except (OSError, KeyError, HTTPError, URLError):
            pass
        time.sleep(1)
    raise SystemExit("FAIL gateway did not become healthy")


def refresh(expected: str) -> None:
    for _ in range(40):
        try:
            result = request("/api/catalog/refresh", {}, token())["results"][0]
            if result["status"] == expected:
                print(f"PASS catalog status {expected}")
                return
        except (OSError, KeyError, HTTPError, URLError):
            pass
        time.sleep(1)
    raise SystemExit(f"FAIL catalog did not become {expected}")


def expect_block(policy_id: str) -> None:
    result = request("/api/calls", {"tool_name": "read_document", "document_id": "notice-001"}, token())
    if result["decision"] != "Block" or result["policy_id"] != policy_id:
        raise SystemExit(f"FAIL expected Block/{policy_id}, got {result['decision']}/{result['policy_id']}")
    if result["effect_before"] != result["effect_after"] or result["upstream_executed"]:
        raise SystemExit("FAIL blocked request reached upstream")
    print(f"PASS {policy_id} effect {result['effect_before']}->{result['effect_after']}")


def expect_unauthenticated() -> None:
    """The control point must not accept a caller that asserts its own identity."""
    call = {"tool_name": "read_document", "document_id": "notice-001"}
    for name, bad_token in (("anonymous", None), ("forged", "not-a-real-token")):
        try:
            request("/api/calls", call, bad_token)
        except HTTPError as error:
            if error.code != 401:
                raise SystemExit(f"FAIL {name} call returned {error.code}, expected 401") from error
            continue
        raise SystemExit(f"FAIL {name} call was accepted")
    print("PASS gateway API rejects anonymous and forged identities")


if __name__ == "__main__":
    commands = {
        "wait": wait_ready,
        "refresh": lambda: refresh(sys.argv[2]),
        "block": lambda: expect_block(sys.argv[2]),
        "unauthenticated": expect_unauthenticated,
    }
    if len(sys.argv) < 2 or sys.argv[1] not in commands:
        raise SystemExit("usage: regression.py wait | refresh STATUS | block POLICY_ID | unauthenticated")
    commands[sys.argv[1]]()
