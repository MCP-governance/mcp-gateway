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


@dataclass(frozen=True)
class Settings:
    servers: dict[str, Upstream]
    connect_timeout_seconds: float = 10
    read_timeout_seconds: float = 0
    write_timeout_seconds: float = 30
    allowed_origins: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.servers or any(not SERVER_NAME.fullmatch(name) for name in self.servers):
            raise ValueError("configure at least one server with a valid route name")
        for name in ("connect_timeout_seconds", "read_timeout_seconds", "write_timeout_seconds"):
            value = getattr(self, name)
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or value < 0
                    or (name != "read_timeout_seconds" and value == 0)):
                raise ValueError(f"invalid {name}")
        if not isinstance(self.allowed_origins, (tuple, list)) or any(
                not isinstance(origin, str) for origin in self.allowed_origins):
            raise ValueError("allowed_origins must be a list of exact origin strings")


def load_config(path: str | Path) -> Settings:
    with Path(path).open("rb") as source:
        document = tomllib.load(source)
    if set(document) - {"proxy", "servers"}:
        raise ValueError("unknown configuration section")
    server_table = document.get("servers", {})
    options = document.get("proxy", {})
    if not isinstance(server_table, dict) or not isinstance(options, dict):
        raise ValueError("proxy and servers must be TOML tables")
    servers = {}
    for name, entry in server_table.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("headers", {}), dict):
            raise ValueError("server and headers must be TOML tables")
        if set(entry) - {"url", "headers"}:
            raise ValueError(f"unknown configuration for server {name}")
        headers = {}
        for header, value in entry.get("headers", {}).items():
            if isinstance(value, dict) and set(value) == {"env"}:
                variable = value["env"]
                if not isinstance(variable, str) or not os.environ.get(variable):
                    raise ValueError(f"missing upstream credential environment variable for {name}")
                value = os.environ[variable]
            headers[header] = value
        servers[name] = Upstream(entry["url"], headers)
    return Settings(servers=servers, **options)
