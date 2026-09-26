"""Connections from the Gateway to the registered MCP servers.

Every upstream is a Streamable HTTP endpoint on the internal `tools` network. The
Gateway never forwards the employee's token upstream (MCP authorization spec: token
passthrough is forbidden) - it connects with no credentials at all, and whatever a
server uses towards its own downstream system is that server's credential.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

CONNECT_TIMEOUT = float(os.getenv("UPSTREAM_TIMEOUT_SECONDS", "90"))


@asynccontextmanager
async def session(endpoint: str, timeout: float = CONNECT_TIMEOUT):
    # trust_env=False: a proxy variable in the Gateway's environment must not reroute
    # policy-approved calls to somewhere the registry never approved.
    async with httpx2.AsyncClient(timeout=timeout, trust_env=False, follow_redirects=False) as http_client:
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
