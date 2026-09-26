"""Official SDK MCP server used by the two architecture deployments."""
import os

import httpx
from mcp.server.mcpserver import MCPServer

from services.shared import emit

mcp = MCPServer("Architecture MCP Server")


@mcp.tool()
async def echo(text: str) -> str:
    """Return public, non-sensitive text."""
    emit("mcp-server", "tool_call", {"server": "demo", "tool": "echo"})
    return text


@mcp.tool()
async def fetch_internal() -> dict:
    """Read the configured internal API status."""
    emit("mcp-server", "tool_call", {"server": "demo", "tool": "fetch_internal"})
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
        result = await client.get(os.getenv("INTERNAL_API_URL", "http://internal-api:8000/status"))
        result.raise_for_status()
        return result.json()


@mcp.tool()
async def fetch_external() -> dict:
    """Read the configured external API status."""
    emit("mcp-server", "tool_call", {"server": "demo", "tool": "fetch_external"})
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
        result = await client.get(os.getenv("EXTERNAL_API_URL", "http://external-api:8000/status"))
        result.raise_for_status()
        return result.json()


app = mcp.streamable_http_app(streamable_http_path="/mcp", json_response=True, host="0.0.0.0")
