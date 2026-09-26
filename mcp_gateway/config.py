"""Startup configuration: fixed upstream URLs and independently supplied credentials."""
from __future__ import annotations

import math
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import httpx

HOP_HEADERS = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailer", "transfer-encoding", "upgrade", "proxy-connection",
}
HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
SERVER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


@dataclass(frozen=True)
class Upstream:
    url: str
    headers: dict[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        try:
            endpoint = httpx.URL(self.url)
        except (httpx.InvalidURL, TypeError):
            raise ValueError("invalid upstream URL") from None
        if (endpoint.scheme not in ("http", "https") or not endpoint.host
                or endpoint.userinfo or endpoint.fragment):
            raise ValueError("upstream URL must be HTTP(S), without credentials or a fragment")
        if len({name.lower() for name in self.headers}) != len(self.headers):
            raise ValueError("duplicate configured upstream header name")
        for name, value in self.headers.items():
            if (not HEADER_NAME.fullmatch(name) or name.lower() in HOP_HEADERS
                    or name.lower() in {"host", "content-length"}):
                raise ValueError("invalid configured upstream header name")
            if not isinstance(value, str) or any(c in value for c in "\r\n"):
                raise ValueError("invalid configured upstream header value")
            value.encode("latin-1")


def _number(value, name: str, *, zero: bool = True) -> None:
    if (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
            or value < 0 or (not zero and value == 0)):
        raise ValueError(f"invalid {name}")


def _count(value, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"invalid {name}")


def _names(value, name: str) -> None:
    if not isinstance(value, (tuple, list)) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be a list of strings")


@dataclass(frozen=True)
class AuthSettings:
    # Empty: anyone who reaches the proxy may use it, which is why it binds to loopback.
    providers: tuple[str, ...] = ()
    litellm_url: str | None = None
    litellm_cache_seconds: float = 60
    # Servers a LiteLLM key may use when its metadata names none ("*" = every server).
    litellm_default_servers: tuple[str, ...] = ()
    default_rate_per_minute: int = 0

    def __post_init__(self) -> None:
        _names(self.providers, "auth.providers")
        if len(set(self.providers)) != len(self.providers) or set(self.providers) - {"keys", "litellm"}:
            raise ValueError("auth.providers accepts \"keys\" and \"litellm\"")
        if "litellm" in self.providers:
            try:
                endpoint = httpx.URL(self.litellm_url or "")
            except (httpx.InvalidURL, TypeError):
                raise ValueError("invalid auth.litellm_url") from None
            if endpoint.scheme not in ("http", "https") or not endpoint.host or endpoint.userinfo:
                raise ValueError("auth.litellm_url must be an HTTP(S) URL without credentials")
        _number(self.litellm_cache_seconds, "auth.litellm_cache_seconds")
        _names(self.litellm_default_servers, "auth.litellm_default_servers")
        _count(self.default_rate_per_minute, "auth.default_rate_per_minute")


@dataclass(frozen=True)
class AdminSettings:
    # No token, no console: the admin API is not served at all.
    token: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.token is not None and (not isinstance(self.token, str) or len(self.token) < 16):
            raise ValueError("admin.token must be at least 16 characters")


@dataclass(frozen=True)
class StoreSettings:
    # No path, no record: the proxy relays without writing anything to disk.
    path: str | None = None
    retention_days: float = 14
    # Tool arguments can carry personal data, so they stay out of the record by default.
    record_arguments: bool = False

    def __post_init__(self) -> None:
        if self.path is not None and (not isinstance(self.path, str) or not self.path.strip()):
            raise ValueError("store.path must be a file path")
        _number(self.retention_days, "store.retention_days", zero=False)
        if not isinstance(self.record_arguments, bool):
            raise ValueError("store.record_arguments must be true or false")


@dataclass(frozen=True)
class HealthSettings:
    # Off unless configured: a probe is traffic the upstream did not ask for.
    interval_seconds: float = 0
    timeout_seconds: float = 5

    def __post_init__(self) -> None:
        _number(self.interval_seconds, "health.interval_seconds")
        _number(self.timeout_seconds, "health.timeout_seconds", zero=False)


@dataclass(frozen=True)
class Settings:
    servers: dict[str, Upstream]
    connect_timeout_seconds: float = 10
    read_timeout_seconds: float = 0
    write_timeout_seconds: float = 30
    # Idle SSE streams never finish on their own; without a limit a stop would wait forever.
    shutdown_timeout_seconds: float = 5
    # Each server gets its own pool, so one server's open streams cannot starve another.
    max_connections_per_server: int = 100
    allowed_origins: tuple[str, ...] = ()
    auth: AuthSettings = field(default_factory=AuthSettings)
    admin: AdminSettings = field(default_factory=AdminSettings)
    store: StoreSettings = field(default_factory=StoreSettings)
    health: HealthSettings = field(default_factory=HealthSettings)

    def __post_init__(self) -> None:
        if not self.servers or any(not SERVER_NAME.fullmatch(name) for name in self.servers):
            raise ValueError("configure at least one server with a valid route name")
        for name in ("connect_timeout_seconds", "read_timeout_seconds",
                     "write_timeout_seconds", "shutdown_timeout_seconds"):
            _number(getattr(self, name), name, zero=name not in ("connect_timeout_seconds", "write_timeout_seconds"))
        limit = self.max_connections_per_server
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("invalid max_connections_per_server")
        if not isinstance(self.allowed_origins, (tuple, list)) or any(
                not isinstance(origin, str) for origin in self.allowed_origins):
            raise ValueError("allowed_origins must be a list of exact origin strings")
        if "keys" in self.auth.providers and not self.store.path:
            raise ValueError("auth.providers \"keys\" needs store.path to keep the keys")
        unknown = set(self.auth.litellm_default_servers) - set(self.servers) - {"*"}
        if unknown:
            raise ValueError("auth.litellm_default_servers names an unknown server")


def _secret(value, what: str, *, required: bool = True):
    # {env = "NAME"} keeps a secret out of the file. An unset variable is a startup error
    # for what the proxy needs to work; for an optional feature it switches that feature off.
    if isinstance(value, dict) and set(value) == {"env"}:
        variable = value["env"]
        if not isinstance(variable, str):
            raise ValueError(f"invalid environment variable name for {what}")
        if not os.environ.get(variable):
            if required:
                raise ValueError(f"missing {what}: set its environment variable")
            return None
        return os.environ[variable]
    return value


def _section(document: dict, name: str) -> dict:
    table = document.get(name, {})
    if not isinstance(table, dict):
        raise ValueError(f"{name} must be a TOML table")
    # TOML arrays arrive as lists; the settings keep them as immutable tuples.
    return {key: tuple(value) if isinstance(value, list) else value for key, value in table.items()}


def load_config(path: str | Path) -> Settings:
    with Path(path).open("rb") as source:
        document = tomllib.load(source)
    if set(document) - {"proxy", "servers", "auth", "admin", "store", "health"}:
        raise ValueError("unknown configuration section")
    server_table = document.get("servers", {})
    if not isinstance(server_table, dict):
        raise ValueError("servers must be a TOML table")
    servers = {}
    for name, entry in server_table.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("headers", {}), dict):
            raise ValueError("server and headers must be TOML tables")
        if set(entry) - {"url", "headers"}:
            raise ValueError(f"unknown configuration for server {name}")
        headers = {header: _secret(value, f"upstream credential for {name}")
                   for header, value in entry.get("headers", {}).items()}
        servers[name] = Upstream(entry["url"], headers)
    admin = _section(document, "admin")
    if "token" in admin:
        # No token, no console - the safe way for an unset variable to fail.
        admin["token"] = _secret(admin["token"], "admin.token", required=False)
    return Settings(
        servers=servers, **_section(document, "proxy"),
        auth=AuthSettings(**_section(document, "auth")), admin=AdminSettings(**admin),
        store=StoreSettings(**_section(document, "store")), health=HealthSettings(**_section(document, "health")),
    )
