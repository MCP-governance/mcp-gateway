"""Connections from the Gateway to the registered MCP servers.

Upstreams are registered Streamable HTTP endpoints. The Gateway never forwards the
employee's token upstream. Internal lab servers use their own downstream credentials;
remote SaaS credentials must be separately provisioned and bound to resource and caller.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import json
import logging
import time
import math
from collections import OrderedDict
from contextlib import AsyncExitStack, asynccontextmanager
from http.cookiejar import CookieJar, DefaultCookiePolicy
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp_types.version import HANDSHAKE_PROTOCOL_VERSIONS, MODERN_PROTOCOL_VERSIONS

from . import db

CONNECT_TIMEOUT = float(os.getenv("UPSTREAM_TIMEOUT_SECONDS", "90"))


class CredentialUnavailable(ValueError):
    pass


def credential_headers(endpoint: str, principal: str | None = None) -> dict:
    """Operator-provisioned SaaS credentials, bound to an exact resource and principals.

    None is reserved for control-plane metadata discovery. Dispatch always supplies
    the transport-authenticated principal. No request header or SSO token enters here.
    """
    location = os.getenv('MCP_UPSTREAM_CREDENTIALS_FILE', '')
    if not location:
        return {}
    try:
        path = Path(location)
        if path.stat().st_mode & 0o077:
            raise ValueError('credential file permissions')
        rows = json.loads(path.read_text())['credentials']
        matches = [r for r in rows if r['endpoint'] == endpoint]
        if not matches:
            return {}
        if len(matches) != 1:
            raise ValueError('ambiguous resource binding')
        row = matches[0]
        principals = row['allowed_principals']
        if not isinstance(principals, list) or not principals or any(not isinstance(p, str) or not p for p in principals):
            raise ValueError('principal binding format')
        url = urlsplit(endpoint)
        if url.scheme != 'https' or url.username or url.password or url.fragment:
            raise ValueError('credential transport')
        if principal is not None and principal not in principals:
            raise ValueError('principal binding')
        expiry = row['expires_at']
        if type(expiry) not in (int, float) or not math.isfinite(expiry) or expiry < 0 or (expiry and expiry <= time.time()):
            raise ValueError('credential expiration')
        token = row['access_token']
        if not isinstance(token, str) or not token or any(c in token for c in '\r\n'):
            raise ValueError('credential format')
        return {'Authorization': 'Bearer ' + token}
    except (OSError, ValueError, TypeError, KeyError) as exc:
        # Do not include the file content, path, vendor error or token in audit/logs.
        raise CredentialUnavailable('Upstream credential is unavailable, expired, or outside its binding') from exc


class _Lease:
    __slots__ = ("client", "loop", "users", "evicted")

    def __init__(self, client: httpx2.AsyncClient, loop: asyncio.AbstractEventLoop) -> None:
        self.client, self.loop, self.users, self.evicted = client, loop, 0, False


# Dispatch connections are reused per (endpoint, principal, credential): a tools/call
# no longer pays a TCP and TLS handshake every time. The MCP session itself is still
# opened and closed per call (D-79), and a pool entry is never shared between
# principals, so nothing an upstream ties to a connection crosses callers. Cookies are
# not kept at all, as with the fresh client each call used to get.
POOL_SIZE = int(os.getenv("UPSTREAM_POOL_SIZE", "32"))
_pool: OrderedDict[tuple, _Lease] = OrderedDict()


def _client(timeout: float, headers: dict) -> httpx2.AsyncClient:
    # trust_env=False: a proxy variable in the Gateway's environment must not reroute
    # policy-approved calls to somewhere the registry never approved.
    return httpx2.AsyncClient(timeout=timeout, trust_env=False, follow_redirects=False, headers=headers,
                              cookies=CookieJar(policy=DefaultCookiePolicy(allowed_domains=[])),
                              limits=httpx2.Limits(max_keepalive_connections=4, keepalive_expiry=60))


async def close_pool(endpoint: str | None = None, principal: str | None = None) -> int:
    """Drop the warm connections of one endpoint and/or one principal (None = any).

    An idle one is closed now; one a call is using is closed by that call when it lets go,
    and nothing new can be borrowed from either. The client holds the credential header
    it was built with, so this is also how a removed credential leaves memory.
    """
    doomed = [key for key in _pool if (endpoint is None or key[0] == endpoint) and (principal is None or key[1] == principal)]
    loop = asyncio.get_running_loop()
    for key in doomed:
        lease = _pool.pop(key)
        lease.evicted = True
        if not lease.users and lease.loop is loop:
            await lease.client.aclose()
    return len(doomed)


async def release_pool(endpoint: str | None, principal: str | None, reason: str) -> int:
    """close_pool here, and tell the other gateway processes through the database."""
    closed = await close_pool(endpoint, principal)
    try:
        await db.execute("INSERT INTO upstream_pool_events(endpoint, principal, reason) VALUES (%s,%s,%s)",
                         (endpoint, principal, reason))
        await db.execute("DELETE FROM upstream_pool_events WHERE created_at < now() - interval '1 day'")
    except Exception:
        # The announcement is for warm sockets in other processes. The cutover and the revocation
        # already stand, and the dispatch boundary refuses on its own, so a failed note is logged only.
        logging.getLogger(__name__).exception("pool closure announcement failed")
    return closed


SWEEP_SECONDS = 2.0
_swept: dict = {"at": 0.0, "id": None}


async def _sweep() -> None:
    """Apply closures another process announced. Read at most every SWEEP_SECONDS, so a call
    pays one query per interval, and never fails a call: the dispatch boundary refuses a
    cut-off principal or server on its own, a stale connection only costs a warm socket."""
    now = time.monotonic()
    if now - _swept["at"] < SWEEP_SECONDS:
        return
    _swept["at"] = now
    try:
        if _swept["id"] is None:
            _swept["id"] = (await db.fetch_one("SELECT COALESCE(max(id), 0) AS last FROM upstream_pool_events"))["last"]
            return
        for row in await db.fetch_all("SELECT id, endpoint, principal FROM upstream_pool_events WHERE id > %s ORDER BY id",
                                      (_swept["id"],)):
            _swept["id"] = row["id"]
            await close_pool(row["endpoint"], row["principal"])
    except Exception:
        pass


@asynccontextmanager
async def _dispatch_client(endpoint: str, principal: str, headers: dict, timeout: float):
    loop = asyncio.get_running_loop()
    await _sweep()
    key = (endpoint, principal, timeout, hashlib.sha256(json.dumps(headers, sort_keys=True).encode()).hexdigest())
    lease = _pool.get(key)
    if lease is None or lease.loop is not loop or lease.client.is_closed:
        # A rotated or removed credential changes the key, another event loop or a closed client
        # replaces the entry: the client built before must not stay behind holding the credential.
        # One still in use on its own loop is closed there by its last user.
        for stale in [k for k in _pool if k[:2] == key[:2]]:
            old = _pool.pop(stale)
            old.evicted = True
            if not old.users and old.loop is loop:
                await old.client.aclose()
        lease = _pool[key] = _Lease(_client(timeout, headers), loop)
    _pool.move_to_end(key)
    lease.users += 1
    try:
        while len(_pool) > POOL_SIZE:
            _, old = _pool.popitem(last=False)
            old.evicted = True
            if not old.users and old.loop is loop:
                await old.client.aclose()
        yield lease.client
    finally:
        lease.users -= 1
        if lease.evicted and not lease.users:
            await lease.client.aclose()


@asynccontextmanager
async def session(endpoint: str, timeout: float = CONNECT_TIMEOUT, principal: str | None = None,
                  protocol: str | None = None):
    """One MCP session. With a principal (dispatch) the HTTP connection comes from the pool.

    `protocol` is the version recorded when the contract was approved (DEV-29 stage 1). A handshake-era
    server is opened with `initialize` directly instead of first probing `server/discover`; a 2026-era
    server is spoken to in that version with no discovery round trip at all. A server that moved to
    another version fails the call (closed) and shows up as drift in the catalog check. Unrecorded
    versions keep the SDK's probe."""
    headers = credential_headers(endpoint, principal)
    async with AsyncExitStack() as stack:
        if principal is None:
            http_client = await stack.enter_async_context(_client(timeout, headers))
        else:
            http_client = await stack.enter_async_context(_dispatch_client(endpoint, principal, headers, timeout))
        yield await stack.enter_async_context(
            Client(streamable_http_client(endpoint, http_client=http_client), read_timeout_seconds=timeout,
                   mode=connect_mode(protocol)))


def connect_mode(protocol: str | None) -> str:
    if protocol in HANDSHAKE_PROTOCOL_VERSIONS:
        return "legacy"
    return protocol if protocol in MODERN_PROTOCOL_VERSIONS else "auto"


MAX_TOOL_PAGES = 50


async def list_all_tools(client: Client) -> list:
    """Every page of tools/list. A contract compared on the first page alone missed tools the server
    put on later pages, and an enabled tool there blocked every call to the server (DEV-44)."""
    tools, cursor = [], None
    for _ in range(MAX_TOOL_PAGES):
        page = await client.list_tools(cursor=cursor)
        tools.extend(page.tools)
        cursor = page.next_cursor
        if not cursor:
            return tools
    raise ValueError("tools/list did not finish within the page limit")


def tool_view(tool: Any) -> dict:
    annotations = getattr(tool, "annotations", None)
    return {
        "name": tool.name,
        "description": tool.description or "",
        "input_schema": tool.input_schema,
        "annotations": annotations.model_dump(exclude_none=True) if annotations else None,
    }


async def discover(endpoint: str) -> dict:
    async with session(endpoint, timeout=30) as client:
        listed = await list_all_tools(client)
        info = client.server_info
        return {
            "advertised_name": (info.name if info else "") or "",
            "version": (info.version if info else "") or "unknown",
            "protocol_version": str(client.protocol_version),
            "tools": [tool_view(tool) for tool in listed],
        }


async def handshake(endpoint: str, timeout: float = 5) -> dict:
    """Open one MCP session and close it: the server speaks the protocol, nothing more.

    No tools/list, so this says nothing about the contract - refresh_catalog does that.
    """
    async with session(endpoint, timeout=timeout) as client:
        info = client.server_info
        return {
            "advertised_name": (info.name if info else "") or "",
            "version": (info.version if info else "") or "unknown",
            "protocol_version": str(client.protocol_version),
        }


def content_items(result: Any) -> list[dict]:
    """Upstream content as plain dicts, preserved item by item for the client."""
    items = []
    for item in result.content or []:
        try:
            items.append(item.model_dump(mode="json", by_alias=True, exclude_none=True))
        except AttributeError:
            items.append({"type": "text", "text": str(item)})
    return items


def text_of(items: list[dict]) -> str:
    return "\n".join(str(item.get("text", "")) for item in items if item.get("type") == "text")
