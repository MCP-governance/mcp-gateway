"""Who is calling. The credential a client shows the proxy never reaches an upstream."""
from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass

import anyio
import httpx

from .config import Settings
from .store import KEY_PREFIX, Store

log = logging.getLogger("mcp_gateway")

# Removed from every relayed request, whether or not auth is on: a LiteLLM key sent
# by mistake to an MCP server would be a credential leaked to a third party.
CREDENTIAL_HEADERS = {"authorization", "x-litellm-api-key"}
LOCAL_KEY_CACHE_SECONDS = 5


@dataclass(frozen=True)
class Principal:
    name: str
    auth: str  # none | key | litellm
    key_id: str | None = None
    servers: tuple[str, ...] = ("*",)
    rate_per_minute: int = 0

    def may_use(self, server: str) -> bool:
        return "*" in self.servers or server in self.servers


class Denied(Exception):
    def __init__(self, status: int, reason: str):
        super().__init__(reason)
        self.status = status
        self.reason = reason


def presented_key(headers) -> str | None:
    scheme, _, value = headers.get("authorization", "").partition(" ")
    if scheme.lower() == "bearer" and value.strip():
        return value.strip()
    value = headers.get("x-litellm-api-key", "").strip()
    if value.lower().startswith("bearer "):
        value = value[7:].strip()
    return value or None


class Authenticator:
    def __init__(self, settings: Settings, store: Store | None, litellm: httpx.AsyncClient | None = None):
        self.settings = settings
        self.store = store
        self.litellm = litellm
        # Hash of the secret -> (expiry, principal or None for a rejected key).
        self.cache: dict[str, tuple[float, Principal | None]] = {}

    async def authenticate(self, headers, client_ip: str | None) -> Principal:
        auth = self.settings.auth
        if not auth.providers:
            return Principal(name=client_ip or "anonymous", auth="none", rate_per_minute=auth.default_rate_per_minute)
        secret = presented_key(headers)
        if not secret:
            raise Denied(401, "missing credential")
        digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
        cached = self.cache.get(digest)
        if cached and cached[0] > time.monotonic():
            if cached[1] is None:
                raise Denied(401, "invalid credential")
            return cached[1]
        if secret.startswith(KEY_PREFIX) and "keys" in auth.providers:
            principal, ttl = await self._local(secret), LOCAL_KEY_CACHE_SECONDS
        elif "litellm" in auth.providers:
            principal, ttl = await self._litellm(secret), auth.litellm_cache_seconds
        else:
            principal, ttl = None, LOCAL_KEY_CACHE_SECONDS
        if len(self.cache) > 10000:
            self.cache.clear()
        self.cache[digest] = (time.monotonic() + ttl, principal)
        if principal is None:
            raise Denied(401, "invalid credential")
        return principal

    def forget(self) -> None:
        # Key changes in the console take effect on the next request, not after the cache.
        self.cache.clear()

    async def _local(self, secret: str) -> Principal | None:
        row = await anyio.to_thread.run_sync(self.store.key_by_secret, secret)
        now = time.time()
        if row is None or row["disabled_at"] or (row["expires_at"] and row["expires_at"] <= now):
            return None
        return Principal(
            name=row["name"], auth="key", key_id=row["id"], servers=tuple(row["servers"]),
            rate_per_minute=row["rate_per_minute"] or self.settings.auth.default_rate_per_minute,
        )

    async def _litellm(self, secret: str) -> Principal | None:
        auth = self.settings.auth
        try:
            response = await self.litellm.get(
                auth.litellm_url.rstrip("/") + "/key/info", headers={"Authorization": f"Bearer {secret}"})
        except httpx.HTTPError as error:
            # Fail closed: an unverifiable key is not a valid key.
            log.warning("LiteLLM key check failed: %s", type(error).__name__)
            raise Denied(503, "key service unavailable") from None
        if response.status_code in (400, 401, 403, 404):
            return None
        if response.status_code != 200:
            log.warning("LiteLLM key check answered %s", response.status_code)
            raise Denied(503, "key service unavailable")
        try:
            info = response.json().get("info") or {}
        except (ValueError, AttributeError):
            raise Denied(503, "key service unavailable") from None
        if not isinstance(info, dict):
            raise Denied(503, "key service unavailable")
        if info.get("blocked"):
            return None
        metadata = info.get("metadata") if isinstance(info.get("metadata"), dict) else {}
        servers = metadata.get("mcp_proxy_servers")
        if not (isinstance(servers, list) and all(isinstance(s, str) for s in servers)):
            servers = list(auth.litellm_default_servers)
        rate = metadata.get("mcp_proxy_rate_per_minute")
        name = info.get("key_alias") or info.get("user_id") or f"litellm:{secret[:7]}…"
        return Principal(
            name=str(name)[:100], auth="litellm", key_id=f"litellm:{hashlib.sha256(secret.encode()).hexdigest()[:12]}",
            servers=tuple(servers),
            rate_per_minute=rate if isinstance(rate, int) and not isinstance(rate, bool) and rate >= 0
            else auth.default_rate_per_minute,
        )


class RateLimiter:
    """Token bucket per principal: a burst of `per_minute`, refilled evenly over a minute."""

    def __init__(self):
        self.buckets: dict[str, tuple[float, float]] = {}

    def retry_after(self, who: str, per_minute: int, now: float | None = None) -> float | None:
        if per_minute <= 0:
            return None
        now = time.monotonic() if now is None else now
        tokens, last = self.buckets.get(who, (float(per_minute), now))
        tokens = min(float(per_minute), tokens + (now - last) * per_minute / 60)
        if tokens < 1:
            self.buckets[who] = (tokens, now)
            return (1 - tokens) * 60 / per_minute
        self.buckets[who] = (tokens - 1, now)
        return None
