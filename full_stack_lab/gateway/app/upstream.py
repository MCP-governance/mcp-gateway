"""Connections from the Gateway to the registered MCP servers.

Upstreams are registered Streamable HTTP endpoints. The Gateway never forwards the
employee's token upstream. Internal lab servers use their own downstream credentials;
remote SaaS credentials must be separately provisioned and bound to resource and caller.
"""
from __future__ import annotations

import os
import json
import time
import math
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

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


@asynccontextmanager
async def session(endpoint: str, timeout: float = CONNECT_TIMEOUT, principal: str | None = None):
    # trust_env=False: a proxy variable in the Gateway's environment must not reroute
    # policy-approved calls to somewhere the registry never approved.
    async with httpx2.AsyncClient(timeout=timeout, trust_env=False, follow_redirects=False,
                                 headers=credential_headers(endpoint, principal)) as http_client:
        async with Client(streamable_http_client(endpoint, http_client=http_client),
                          read_timeout_seconds=timeout) as client:
            yield client


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
        listed = await client.list_tools()
        info = client.server_info
        return {
            "advertised_name": (info.name if info else "") or "",
            "version": (info.version if info else "") or "unknown",
            "protocol_version": str(client.protocol_version),
            "tools": [tool_view(tool) for tool in listed.tools],
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
