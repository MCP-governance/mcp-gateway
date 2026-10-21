"""Read-only discovery of public remote MCP servers (initialize + tools/list), no credentials.

Prints one JSON line per endpoint: advertised name/version, protocol, tool names, SHA-256 of the
canonical tool list, and the error class when it fails. Used for the 2026-10-20 intake record;
it does not register anything.
usage: python remote_probe.py URL [URL ...]
"""
import asyncio, hashlib, json, os, sys, time
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def probe(url: str) -> dict:
    started = time.perf_counter()
    try:
        async with streamablehttp_client(url, timeout=30) as (read, write, _):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                tools = (await session.list_tools()).tools
        listed = [t.model_dump(mode="json", exclude_none=True) for t in tools]
        if os.environ.get("DUMP"):  # catalog lines for t4_replay.py
            with open(os.environ["DUMP"], "a") as dump:
                dump.write(json.dumps({"kind": "catalog", "server": init.serverInfo.name, "url": url, "tools": listed},
                                      ensure_ascii=False) + "\n")
        return {"url": url, "ok": True, "name": init.serverInfo.name, "version": init.serverInfo.version,
                "protocol": init.protocolVersion, "tools": [t["name"] for t in listed],
                "tools_sha256": hashlib.sha256(json.dumps(listed, sort_keys=True).encode()).hexdigest(),
                "seconds": round(time.perf_counter() - started, 2)}
    except BaseException as exc:  # noqa: BLE001 — record any failure class, never pass
        inner = exc.exceptions[0] if isinstance(exc, BaseExceptionGroup) and exc.exceptions else exc
        return {"url": url, "ok": False, "error": f"{type(inner).__name__}: {str(inner)[:200]}",
                "seconds": round(time.perf_counter() - started, 2)}


async def main():
    for url in sys.argv[1:]:
        print(json.dumps(await probe(url), ensure_ascii=False), flush=True)

asyncio.run(main())
