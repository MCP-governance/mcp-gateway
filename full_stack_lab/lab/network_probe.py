"""Read-only TCP inventory for the corporate Docker lab.

Targets are supplied by the host from Compose-managed container addresses.  This
is intentionally not a CIDR sweep: unused Docker addresses and the host are out
of scope, and the probe sends no application payload.
"""
from __future__ import annotations

import json
import os
import socket
import time


def values(name: str) -> list[str]:
    return sorted({value.strip() for value in os.getenv(name, "").split(",") if value.strip()})


def main() -> int:
    targets = values("LAB_NET_TARGETS")
    ports = sorted({int(value) for value in values("LAB_NET_PORTS") if value.isdigit()})
    if not targets or not ports:
        raise SystemExit("LAB_NET_TARGETS and LAB_NET_PORTS are required")
    timeout = float(os.getenv("LAB_NET_TIMEOUT_SECONDS", "0.25"))
    started = time.time()
    open_ports: list[dict] = []
    for target in targets:
        for port in ports:
            try:
                with socket.create_connection((target, port), timeout=timeout):
                    open_ports.append({"ip": target, "port": port, "transport": "tcp"})
            except OSError:
                pass
    print(json.dumps({
        "scope": "compose-managed-container-addresses",
        "method": "tcp-connect-only",
        "target_count": len(targets),
        "targets": targets,
        "ports": ports,
        "open": open_ports,
        "elapsed_seconds": round(time.time() - started, 3),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
