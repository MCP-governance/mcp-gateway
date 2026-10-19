"""Synthetic inputs that an intake approval now requires, kept in one place for the checks that walk
request -> approval -> registration: supplier assurance (DEV-68) and the impact input (DEV-71).

Every value is made up and uses a reserved example domain. They stand in for what a person would state
and are never a real supplier's evidence. gateway/app/acceptance.py runs in the image without this
directory and keeps its own copy of the two values; keep them equal.

Plain Python with no imports from the gateway, so a shell script can use it too:
    python3 tests/intake_fixture.py [key=value ...]     # approval body as JSON
"""
from __future__ import annotations

import json
import sys

# The five required fields. The support end is far enough ahead that no run date lets it lapse.
SUPPLIER_ASSURANCE = {
    "legal_entity": "Example Provider Ltd.",
    "supplier_contact": "support@example.com",
    "security_contact": "security@example.com",
    "support_end": "2099-12-31",
    "vulnerability_policy_url": "https://example.com/security/policy",
}

# Scores "low", so one administrator approves it, which is what these checks intend. Registration refuses a
# data class above the stated one, hence the parameter for the checks that register an "important" server.
IMPACT_INPUT = {"data_class": "nonimportant", "personal_data": "none", "external_transfer": False,
                "permission": "r", "users": 5, "autonomy": "approve_each"}


def impact_input(data_class: str = "nonimportant") -> dict:
    return {**IMPACT_INPUT, "data_class": data_class}


def approval_body(**extra) -> dict:
    """Body of POST /api/mcp-requests/{id}/approve that carries the required supplier assurance."""
    return {**SUPPLIER_ASSURANCE, **extra}


if __name__ == "__main__":
    print(json.dumps(approval_body(**dict(item.split("=", 1) for item in sys.argv[1:])), ensure_ascii=False))
