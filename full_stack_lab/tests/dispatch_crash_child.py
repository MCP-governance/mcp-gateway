"""Child process of dispatch_effect_lab.py: sends one real tools/call through the gateway path and
is killed by the parent while it is between the send and the answer.

mode "after-send": the call reaches the Gitea MCP server and takes effect, the answer is never
processed. mode "before-send": the process stops at the send and the call never leaves.
Only the connection wrapper below is a test hook; the gateway code and the MCP server are real."""
import asyncio
import os
import sys
from contextlib import asynccontextmanager

from app import core, secret_scan, upstream
from termination_lab_support import call_payload, mint, signing_keys

mode, token, title, marker = sys.argv[1:5]


class Held:
    def __init__(self, client):
        self.client = client

    async def call_tool(self, name, arguments, *args, **kwargs):
        if mode == "after-send":
            await self.client.call_tool(name, arguments, *args, **kwargs)
        with open(marker, "w", encoding="utf-8") as handle:
            handle.write(mode)
        await asyncio.sleep(3600)

    def __getattr__(self, name):
        return getattr(self.client, name)


real_session = upstream.session


@asynccontextmanager
async def held_session(*args, **kwargs):
    async with real_session(*args, **kwargs) as client:
        yield Held(client)


async def no_secrets(text):
    return []


async def main():
    secret_scan.labels = no_secrets
    upstream.session = held_session
    _, claims = mint(token)
    await core.execute_call(call_payload(token, "gitea", "issue_write",
                                         {"method": "create", "owner": "bob", "repo": "payment-service", "title": title, "body": "lab"}, claims))


if __name__ == "__main__":
    signing_keys_env = os.environ.get("AGENT_JWT_PRIVATE_KEY")
    if not signing_keys_env:
        signing_keys()
    asyncio.run(main())
