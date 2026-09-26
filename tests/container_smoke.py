"""Verify a running proxy and demo through the official MCP client."""
import argparse
import asyncio

import httpx
from mcp import Client


async def check(url):
    async with httpx.AsyncClient(trust_env=False) as client:
        response = await client.get(url + "/api/health")
        response.raise_for_status()
        assert response.json()["mode"] == "proxy"
    for mode in ("legacy", "auto"):
        async with Client(url + "/mcp/demo/", mode=mode) as client:
            assert (await client.list_tools()).tools[0].name == "echo"
            result = await client.call_tool("echo", {"text": "container smoke"})
            assert result.content[0].text == "container smoke"
            assert result.structured_content == {"echo": "container smoke"}
            assert len((await client.list_resources()).resources) == 1
            assert (await client.read_resource("demo://message")).contents[0].text == "hello from upstream"
            assert (await client.list_prompts()).prompts[0].name == "greeting"
            assert (await client.get_prompt("greeting")).messages[0].content.text == "Say hello."
    print("PASS proxy health, official MCP SDK legacy/auto, tools/resources/prompts")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    args = parser.parse_args()
    asyncio.run(check(args.url.rstrip("/")))
