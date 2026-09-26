"""Pick a free /16 for this checkout's small Docker networks.

Docker's default /16 and /20 pools can run out while other labs are active.
The chosen prefix is stored in the ignored .env so restarts keep their subnet.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import subprocess
import sys
from pathlib import Path


def occupied_networks() -> list[ipaddress.IPv4Network]:
    ids = subprocess.check_output(["docker", "network", "ls", "-q"], text=True).split()
    networks: list[ipaddress.IPv4Network] = []
    if ids:
        for item in json.loads(subprocess.check_output(["docker", "network", "inspect", *ids], text=True)):
            for config in item.get("IPAM", {}).get("Config") or []:
                subnet = config.get("Subnet")
                if subnet:
                    network = ipaddress.ip_network(subnet, strict=False)
                    if isinstance(network, ipaddress.IPv4Network):
                        networks.append(network)
    try:
        routes = subprocess.check_output(["ip", "-4", "route", "show"], text=True)
    except FileNotFoundError:
        routes = ""
    for line in routes.splitlines():
        candidate = line.split()[0]
        if candidate == "default":
            continue
        try:
            networks.append(ipaddress.ip_network(candidate, strict=False))
        except ValueError:
            continue
    return networks


def choose(path: Path, occupied: list[ipaddress.IPv4Network]) -> str:
    start = int(hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:4], 16) % 50
    for step in range(50):
        second = 200 + (start + step) % 50
        candidate = ipaddress.ip_network(f"10.{second}.0.0/16")
        if all(not candidate.overlaps(existing) for existing in occupied):
            return f"10.{second}"
    raise RuntimeError("Docker 네트워크와 겹치지 않는 10.200-249 대역을 찾지 못했습니다.")


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--self-check":
        first = choose(Path("/tmp/network-prefix-check"), [])
        second = choose(Path("/tmp/network-prefix-check"), [ipaddress.ip_network(f"{first}.0.0/16")])
        assert first != second
        try:
            choose(Path("/tmp/network-prefix-check"), [ipaddress.ip_network("10.0.0.0/8")])
        except RuntimeError:
            pass
        else:
            raise AssertionError("exhausted address space must fail")
        print("network prefix self-check OK")
        raise SystemExit(0)
    try:
        print(choose(Path(sys.argv[1]), occupied_networks()))
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        sys.exit(f"네트워크 대역 자동 선택 실패: {exc}")
