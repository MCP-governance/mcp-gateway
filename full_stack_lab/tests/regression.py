#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8080"


def request(path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = Request(BASE + path, data=data, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=10) as response:
        return json.load(response)


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
            result = request("/api/catalog/refresh", {})["results"][0]
            if result["status"] == expected:
                print(f"PASS catalog status {expected}")
                return
        except (OSError, KeyError, HTTPError, URLError):
            pass
        time.sleep(1)
    raise SystemExit(f"FAIL catalog did not become {expected}")


def expect_block(policy_id: str) -> None:
    result = request("/api/calls", {
        "user_token": "cust-demo", "tool_name": "read_document", "document_id": "notice-001"
    })
    if result["decision"] != "Block" or result["policy_id"] != policy_id:
        raise SystemExit(f"FAIL expected Block/{policy_id}, got {result['decision']}/{result['policy_id']}")
    if result["effect_before"] != result["effect_after"] or result["upstream_executed"]:
        raise SystemExit("FAIL blocked request reached upstream")
    print(f"PASS {policy_id} effect {result['effect_before']}->{result['effect_after']}")


if __name__ == "__main__":
    commands = {"wait": wait_ready, "refresh": lambda: refresh(sys.argv[2]), "block": lambda: expect_block(sys.argv[2])}
    if len(sys.argv) < 2 or sys.argv[1] not in commands:
        raise SystemExit("usage: regression.py wait | refresh STATUS | block POLICY_ID")
    commands[sys.argv[1]]()
