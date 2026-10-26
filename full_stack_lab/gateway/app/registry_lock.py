"""Lock generation from live servers: the only registry-side code that needs upstream discovery."""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from typing import Any

from . import registry, upstream


async def build_lock() -> dict:
    """Discover every catalog server now and describe it as a lock document."""
    result: dict[str, Any] = {"generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
                              "catalog": registry.catalog_version(), "servers": {}}
    for server_id, spec in sorted(registry.servers().items()):
        discovered = await upstream.discover(spec["endpoint"])
        result["servers"][server_id] = {
            "package": registry.source_ref(spec),
            "server_name": discovered["advertised_name"],
            "server_version": discovered["version"],
            "protocol_version": discovered["protocol_version"],
            "tools": {tool["name"]: registry.tool_hashes(tool)
                      for tool in sorted(discovered["tools"], key=lambda t: t["name"])},
        }
    return result


def main(argv: list[str]) -> None:
    if argv == ["lock"]:
        print(json.dumps(asyncio.run(build_lock()), ensure_ascii=False, indent=1, sort_keys=True))
    else:
        print("usage: python -m app.registry_lock lock", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main(sys.argv[1:])
