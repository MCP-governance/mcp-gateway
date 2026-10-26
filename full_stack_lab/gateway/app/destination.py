"""Resolve at the TCP boundary; keep the HTTP origin and TLS name unchanged.

Also holds the endpoint URL rules that need no other app module, so the console can use them without core."""
from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from urllib.parse import urlsplit


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


def registration_endpoint(value: str) -> str:
    endpoint = value.strip()
    parts = urlsplit(endpoint)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password or parts.fragment:
        raise ValueError("http(s)://호스트/경로 형식의 MCP 엔드포인트여야 합니다. 자격 정보는 URL에 넣지 않습니다.")
    if not transport_secure(endpoint):
        raise ValueError("사내 서비스가 아니면 HTTPS 엔드포인트만 등록할 수 있습니다.")
    return endpoint


# CTL-24 / RSK-24. 원격 endpoint가 평문이면 요청·응답이 경로 위에서 읽히고 바뀐다.
# 루프백과 컨테이너 내부 망은 이 판단에서 제외한다 - 거기까지 TLS를 요구하면
# 아무도 지키지 않는 규칙이 하나 더 생긴다.
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _endpoint_host(endpoint: str | None) -> str:
    value = (endpoint or "").strip()
    if not value:
        return ""
    if not value.startswith(("http://", "https://")):
        return ""
    return (urlsplit(value).hostname or "").lower()


def transport_secure(endpoint: str | None) -> bool:
    value = (endpoint or "").strip().lower()
    if not value.startswith(("http://", "https://")):
        return True  # stdio 등 네트워크를 타지 않는 전송
    if value.startswith("https://"):
        return True
    host = _endpoint_host(value)
    # 도커 내부 서비스 이름과 루프백은 이 호스트 밖으로 나가지 않는다.
    return host in LOCAL_HOSTS or "." not in host
