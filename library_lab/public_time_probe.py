#!/usr/bin/env python3
"""Managed stdio runner for the public mcp-server-time package."""

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run(timezone: str) -> None:
    parameters = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server_time"])
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            tools = await session.list_tools()
            result = await session.call_tool("get_current_time", {"timezone": timezone})
            content = [item.text for item in result.content if hasattr(item, "text")]
    print(json.dumps({"server": "mcp-server-time", "tool": "get_current_time", "tools": [tool.name for tool in tools.tools], "content": content}))


if __name__ == "__main__":
    asyncio.run(run(sys.argv[1] if len(sys.argv) > 1 else "Asia/Seoul"))
