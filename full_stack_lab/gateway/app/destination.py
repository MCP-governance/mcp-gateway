"""Resolve at the TCP boundary; keep the HTTP origin and TLS name unchanged."""
from __future__ import annotations

import asyncio
import ipaddress
import socket
import time


class DestinationBlocked(ValueError):
    policy_id = "MCP-EGRESS-001"


class PinnedBackend:
    def __init__(self, backend, internal=(), target=None):
        self.backend = backend
        self.internal = frozenset(internal)
        self.target = target

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        if self.target is not None and (host, port) != self.target:
            raise DestinationBlocked("등록된 연결 목적지와 다릅니다.")
        started = time.monotonic()
        try:
            rows = await asyncio.wait_for(
                asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM), timeout)
            addresses = list(dict.fromkeys(row[4][0] for row in rows))
            if not addresses:
                raise ValueError("empty DNS answer")
            for address in addresses:
                if "%" in address:
                    raise ValueError("scoped address")
                ip = ipaddress.ip_address(address)
                ip = getattr(ip, "ipv4_mapped", None) or ip
                if (ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified
                        or getattr(ip, "is_site_local", False)
                        or ((host, port) not in self.internal and (not ip.is_global or ip.is_loopback))):
                    raise ValueError("prohibited address")
        except (OSError, ValueError, asyncio.TimeoutError) as exc:
            raise DestinationBlocked("목적지 주소를 안전하게 확인하지 못해 연결을 차단했습니다.") from exc
        remaining = None if timeout is None else max(0, timeout - (time.monotonic() - started))
        # The delegated backend sees a numeric IP only. HTTP origin, SNI and Host stay untouched.
        return await self.backend.connect_tcp(host=addresses[0], port=port, timeout=remaining,
                                              local_address=local_address, socket_options=socket_options)

    async def connect_unix_socket(self, *args, **kwargs):
        raise DestinationBlocked("등록되지 않은 로컬 소켓 연결을 차단했습니다.")

    async def sleep(self, seconds):
        await self.backend.sleep(seconds)


def pin_transport(transport, *, internal=(), target=None):
    # HTTPX/HTTPX2 do not expose network_backend on transports; pin only this version-bound seam.
    pool = transport._pool
    pool._network_backend = PinnedBackend(pool._network_backend, internal, target)
    return transport
