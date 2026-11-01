"""Give only the disposable CI lab fixture a bounded validity window."""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

LAB_CAPABILITIES = Path(__file__).resolve().parents[2] / "full_stack_lab/registry/capabilities.json"


def prepare(document: dict, now: datetime) -> dict:
    result = json.loads(json.dumps(document))
    for grant in result["capabilities"]:
        grant["valid_from"] = (now - timedelta(minutes=1)).isoformat()
        grant["valid_until"] = (now + timedelta(days=1)).isoformat()
    return result


def main() -> None:
    # This file is mounted by the disposable lab, never by field/deploy registries.
    if os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("CI") != "true":
        raise SystemExit("Only a disposable GitHub Actions runner may prepare the lab fixture")
    document = json.loads(LAB_CAPABILITIES.read_text(encoding="utf-8"))
    LAB_CAPABILITIES.write_text(json.dumps(prepare(document, datetime.now(UTC)), ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")


if __name__ == "__main__":
    main()
