"""Verify a running proxy and demo through the official MCP client.

With --admin-token it also checks the console: the page is served with its CSP, and
the calls this script just made were recorded with the tool name and outcome.
"""
import argparse
import asyncio

import httpx
from mcp import Client


async def check(url, admin_token=None):
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
    if not admin_token:
        return
    headers = {"Authorization": f"Bearer {admin_token}"}
    async with httpx.AsyncClient(trust_env=False) as client:
        page = await client.get(url + "/console/")
        assert page.status_code == 200 and "script-src 'self'" in page.headers["content-security-policy"]
        assert (await client.get(url + "/admin/api/overview")).status_code == 401
        for _ in range(50):  # the recorder writes in the background
            events = (await client.get(url + "/admin/api/events", params={"tool": "echo"}, headers=headers)).json()["events"]
            if len(events) >= 2:
                break
            await asyncio.sleep(0.1)
        assert len(events) >= 2 and all(e["outcome"] == "ok" and e["server"] == "demo" for e in events), events
        clients = {e["client_name"] for e in events}
        overview = (await client.get(url + "/admin/api/overview", headers=headers)).json()
        assert overview["recorder"]["dropped"] == 0
    print(f"PASS console CSP, admin token required, {len(events)} echo calls recorded (clients: {sorted(filter(None, clients))})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--admin-token")
    args = parser.parse_args()
    asyncio.run(check(args.url.rstrip("/"), args.admin_token))
