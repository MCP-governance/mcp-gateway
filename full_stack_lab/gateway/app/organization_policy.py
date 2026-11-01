"""Read-only organization policy definitions, kept separate from runtime enforcement evidence."""
import json
import re
from pathlib import Path


def catalog() -> dict:
    try:
        result = json.loads(Path(__file__).with_name("organization_policies.json").read_text(encoding="utf-8"))
        policies = result["policies"]
        if result["schema"] != 1 or not isinstance(policies, list):
            raise ValueError("Invalid organization policy catalog")
        seen = set()
        for policy in policies:
            if not isinstance(policy, dict) or not re.fullmatch(r"POL-\d{3}", str(policy.get("id", ""))):
                raise ValueError("Invalid policy identifier")
            if policy["id"] in seen or any(not isinstance(policy.get(key), str) for key in ("name", "stage", "content")):
                raise ValueError("Invalid policy definition")
            seen.add(policy["id"])
        return {"source_state": "available", "policies": policies}
    except (OSError, ValueError, KeyError, TypeError):
        return {"source_state": "unavailable", "policies": []}
