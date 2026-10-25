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
import re
from collections import OrderedDict
from contextlib import AsyncExitStack, asynccontextmanager
from http.cookiejar import CookieJar, DefaultCookiePolicy
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx2
from mcp import Client, types
from mcp.client.streamable_http import streamable_http_client
from mcp_types.version import HANDSHAKE_PROTOCOL_VERSIONS, MODERN_PROTOCOL_VERSIONS
from pydantic import ValidationError

from . import db, output_contract, registry, upstream_sessions
from .destination import pin_transport

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
        # "*": the operator shares this credential with every caller the server's approval admits (D-234).
        if principal is not None and "*" not in principals and principal not in principals:
            raise ValueError('principal binding')
        expiry = row['expires_at']
        if type(expiry) not in (int, float) or not math.isfinite(expiry) or expiry < 0 or (expiry and expiry <= time.time()):
            raise ValueError('credential expiration')
        token = row['access_token']
        if not isinstance(token, str) or not token or any(c in token for c in '\n'):
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
# no longer pays a TCP and TLS handshake every time. Conversation-bound MCP sessions
# have their own lifetime (D-115), and a pool entry is never shared between
# principals, so nothing an upstream ties to a connection crosses callers. Cookies are
# not kept at all, as with the fresh client each call used to get.
POOL_SIZE = int(os.getenv("UPSTREAM_POOL_SIZE", "32"))
_pool: OrderedDict[tuple, _Lease] = OrderedDict()
_sessions = upstream_sessions.Pool(POOL_SIZE)


def credential_hash(headers: dict) -> str:
    return hashlib.sha256(json.dumps(headers, sort_keys=True).encode()).hexdigest()


def _client(timeout: float, headers: dict, endpoint: str, internal: bool) -> httpx2.AsyncClient:
    # trust_env=False: a proxy variable in the Gateway's environment must not reroute
    # policy-approved calls to somewhere the registry never approved.
    url = httpx2.URL(endpoint)
    target = (url.raw_host.decode("ascii"), url.port or (443 if url.scheme == "https" else 80))
    transport = pin_transport(httpx2.AsyncHTTPTransport(trust_env=False,
                              limits=httpx2.Limits(max_keepalive_connections=4, keepalive_expiry=60)),
                              target=target, internal=[target] if internal else [])
    return httpx2.AsyncClient(timeout=timeout, trust_env=False, follow_redirects=False, headers=headers,
                              transport=transport,
                              cookies=CookieJar(policy=DefaultCookiePolicy(allowed_domains=[])))


async def _internal_endpoint(endpoint: str) -> bool:
    host = urlsplit(endpoint).hostname or ""
    # deployment describes the termination contract, not the server's network location.
    if re.fullmatch(r"[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?", host):
        if any(spec.get("endpoint") == endpoint for spec in registry.servers().values()):
            return True
        # Approved executors are discovered before registration; the name alone is not approval.
        return bool(await db.fetch_one("SELECT id FROM mcp_runtimes WHERE endpoint=%s AND status='ACTIVE'",
                                       (endpoint,)))
    return False


async def close_pool(endpoint: str | None = None, principal: str | None = None) -> int:
    """Drop the warm connections of one endpoint and/or one principal (None = any).

    An idle one is closed now; one a call is using is closed by that call when it lets go,
    and nothing new can be borrowed from either. The client holds the credential header
    it was built with, so this is also how a removed credential leaves memory.
    """
    sessions = await _sessions.close(endpoint, principal)
    doomed = [key for key in _pool if (endpoint is None or key[0] == endpoint) and (principal is None or key[1] == principal)]
    loop = asyncio.get_running_loop()
    for key in doomed:
        lease = _pool.pop(key)
        lease.evicted = True
        if not lease.users and lease.loop is loop:
            await lease.client.aclose()
    return len(doomed) + sessions


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


async def close_downstream(principal: str, conversation: tuple[str, str]) -> None:
    digest = upstream_sessions.conversation_id(conversation)
    await _sessions.close(principal=principal, conversation=digest)
    await db.execute("INSERT INTO upstream_pool_events(endpoint, principal, reason) VALUES (NULL,%s,%s)",
                     (principal, "downstream:" + digest))
    from . import mcp_sessions
    await mcp_sessions.terminate(reason="client-delete", principal=principal, session_id=conversation[0])


async def active_downstream(session_id: str, principal: str, device_id: str | None,
                            server_id: str | None) -> bool:
    from . import mcp_sessions
    return await mcp_sessions.active(session_id, principal, device_id, server_id)


async def downstream_refusal(session_id: str) -> dict | None:
    from . import mcp_sessions
    return await mcp_sessions.refusal(session_id)


async def register_downstream(session_id: str, principal: str, jti: str, device_id: str | None,
                              server_id: str | None) -> None:
    from . import mcp_sessions
    await mcp_sessions.register(session_id, principal, jti, device_id, server_id)


SWEEP_SECONDS = 2.0
_swept: dict = {"at": 0.0, "id": None}
_sweep_lock = asyncio.Lock()


async def _sweep() -> None:
    """Apply closures another process announced. Read at most every SWEEP_SECONDS, so a call
    pays one query per interval, and never fails a call: the dispatch boundary refuses a
    cut-off principal or server on its own, a stale connection only costs a warm socket."""
    async with _sweep_lock:
        now = time.monotonic()
        if _swept["id"] is not None and now - _swept["at"] < SWEEP_SECONDS:
            return
        try:
            if _swept["id"] is None:
                # Every dispatch awaits this lock before opening; no session predates this cursor.
                _swept["id"] = (await db.fetch_one(
                    "SELECT COALESCE(max(id), 0) AS last FROM upstream_pool_events"))["last"]
            else:
                for row in await db.fetch_all("SELECT id, endpoint, principal, reason FROM upstream_pool_events WHERE id > %s ORDER BY id",
                                              (_swept["id"],)):
                    if row["reason"].startswith("downstream:"):
                        await _sessions.close(principal=row["principal"], conversation=row["reason"].split(":", 1)[1])
                    else:
                        await close_pool(row["endpoint"], row["principal"])
                    _swept["id"] = row["id"]
            _swept["at"] = now
        except Exception:
            if _swept["id"] is None:
                raise  # Opening before the initial cursor is known could lose a concurrent revocation.


async def maintain_pool() -> None:
    """Expire sessions and apply cross-process closure signals even without traffic."""
    while True:
        try:
            await _sweep()
            for key in list(_sessions.entries):
                try:
                    changed = credential_hash(credential_headers(key.endpoint, key.principal)) != key.credential
                    valid = await _dispatch_allowed(key.principal, key.server, key.endpoint)
                    if changed or not valid:
                        await close_pool(key.endpoint, key.principal)
                except Exception:
                    await close_pool(key.endpoint, key.principal)
            await _sessions.prune()
        except Exception:
            logging.getLogger(__name__).exception("upstream session maintenance failed")
        await asyncio.sleep(SWEEP_SECONDS)


async def _dispatch_allowed(principal: str, server_id: str, endpoint: str) -> bool:
    from . import registry
    spec = registry.server(server_id)
    if not spec or spec["endpoint"] != endpoint:
        return False
    intake = spec.get("intake_id") or None
    return bool(await db.fetch_one(
        """SELECT 1 FROM principals p, mcp_servers s
           WHERE p.token=%s AND p.status='active' AND s.id=%s AND s.endpoint=%s
             AND COALESCE(s.lifecycle,'OPERATING')='OPERATING'
             AND s.status NOT IN ('DISABLED','BLOCKED_SUPPLY_CHAIN','DRIFT')
             AND EXISTS (SELECT 1 FROM mcp_tools t WHERE t.server_id=s.id AND t.enabled)
             AND NOT EXISTS (SELECT 1 FROM mcp_tools t WHERE t.server_id=s.id AND t.enabled
                 AND t.approval_valid_until<=now())
             AND (%s::uuid IS NULL OR EXISTS (SELECT 1 FROM mcp_intake_requests i
                 WHERE i.id=%s::uuid AND i.status='APPROVED'))""", (principal, server_id, endpoint, intake, intake)))


@asynccontextmanager
async def _dispatch_client(endpoint: str, principal: str, headers: dict, timeout: float, internal: bool = False):
    loop = asyncio.get_running_loop()
    key = (endpoint, principal, timeout, credential_hash(headers), internal)
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
        lease = _pool[key] = _Lease(_client(timeout, headers, endpoint, internal), loop)
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
async def _session(endpoint: str, timeout: float, principal: str | None, protocol: str | None,
                   headers: dict, internal: bool):
    async with AsyncExitStack() as stack:
        if principal is None:
            http_client = await stack.enter_async_context(_client(timeout, headers, endpoint, internal))
        else:
            http_client = await stack.enter_async_context(_dispatch_client(endpoint, principal, headers, timeout, internal))
        client = await stack.enter_async_context(
            Client(streamable_http_client(endpoint, http_client=http_client), read_timeout_seconds=timeout,
                   mode=connect_mode(protocol), cache=None))
        yield ContractClient(client)


class ContractClient:
    """Keep SDK wire validation; MINT validates the approved output after receipt.

    Client.call_tool validates the mutable advertised schema before returning and
    treats explicit null as missing. send_request preserves receipt and field presence.
    No input-required retries or extension resolvers may execute extra calls here.
    """
    def __init__(self, client):
        self.client = client

    @property
    def protocol_version(self):
        return self.client.protocol_version

    @property
    def server_info(self):
        return self.client.server_info

    async def list_tools(self, **kwargs):
        return await self.client.list_tools(**kwargs)

    async def call_tool(self, name, arguments):
        request = types.CallToolRequest(params=types.CallToolRequestParams(name=name, arguments=arguments))
        try:
            return await self.client.session.send_request(request, types.CallToolResult)
        except ValidationError as exc:
            raise output_contract.WireRejected("도구 응답이 협상된 출력 형식과 일치하지 않습니다.") from exc


@asynccontextmanager
async def session(endpoint: str, timeout: float = CONNECT_TIMEOUT, principal: str | None = None,
                  protocol: str | None = None, server_id: str | None = None, device_id: str | None = None):
    if endpoint.startswith("local:"):
        # An approved local server runs on the caller's own device; there is no HTTP session to pool.
        from . import local_jobs
        async with local_jobs.session(endpoint, timeout, device_id, discovery=principal is None, principal=principal) as client:
            yield client
        return
    if principal:
        await _sweep()
    generation = _sessions.generation
    try:
        headers = credential_headers(endpoint, principal)
        internal = await _internal_endpoint(endpoint)
    except Exception:
        if principal:
            await close_pool(endpoint, principal)
        raise
    conversation = upstream_sessions.downstream.get()
    factory = lambda: _session(endpoint, timeout, principal, protocol, headers, internal)
    # Modern MCP has no session. Unknown versions must first be reviewed before reuse.
    if principal and server_id and conversation and protocol in HANDSHAKE_PROTOCOL_VERSIONS:
        key = upstream_sessions.Key(principal, conversation, server_id, credential_hash(headers),
                                    endpoint, protocol, timeout, internal)
        async with _sessions.borrow(key, factory, lambda: credential_hash(credential_headers(endpoint, principal))
                                    == key.credential, generation=generation) as client:
            yield client
    else:
        async with factory() as client:
            yield client


def connect_mode(protocol: str | None) -> str:
    if protocol in HANDSHAKE_PROTOCOL_VERSIONS:
        return "legacy"
    return protocol if protocol in MODERN_PROTOCOL_VERSIONS else "auto"


def session_terminated(exc: BaseException) -> bool:
    from mcp.shared.exceptions import MCPError
    if isinstance(exc, BaseExceptionGroup):
        return bool(exc.exceptions) and all(session_terminated(error) for error in exc.exceptions)
    # SDK translates a session's HTTP 404 to this exact protocol error, not a tool error.
    return isinstance(exc, MCPError) and exc.code == -32600 and exc.message == "Session terminated"


MAX_TOOL_PAGES = 50


async def list_all_tools(client: Client) -> list:
    """Every page of tools/list. A contract compared on the first page alone missed tools the server
    put on later pages, and an enabled tool there blocked every call to the server (DEV-44)."""
    tools, cursor = [], None
    for _ in range(MAX_TOOL_PAGES):
        page = await client.list_tools(cursor=cursor, cache_mode="bypass")
        tools.extend(page.tools)
        cursor = page.next_cursor
        if not cursor:
            return tools
    raise ValueError("tools/list did not finish within the page limit")


def tool_view(tool: Any) -> dict:
    annotations = getattr(tool, "annotations", None)
    output_schema = getattr(tool, "output_schema", None)
    if output_schema is not None:
        output_contract.check_schema_bounds(output_schema)
    return {
        "name": tool.name,
        "description": tool.description or "",
        "input_schema": tool.input_schema,
        "output_schema": output_schema,
        "annotations": annotations.model_dump(exclude_none=True) if annotations else None,
    }


async def discover(endpoint: str, principal: str | None = None) -> dict:
    async with session(endpoint, timeout=30, principal=principal) as client:
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
