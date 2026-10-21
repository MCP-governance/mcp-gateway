"""Start each locally installed public MCP server over stdio and do initialize + tools/list + one read call.

Run as the NON-managed pj1 user on PJ1 (control group / install check). Server commands come from
servers.json next to this file (written by the install step). Prints one JSON line per server.
usage: python -I local_probe.py servers.json [name ...]
"""
import asyncio, hashlib, json, os, sys, time
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def probe(name: str, spec: dict) -> dict:
    started = time.perf_counter()
    params = StdioServerParameters(command=spec["command"], args=spec["args"],
                                   env={**os.environ, **spec.get("env", {})}, cwd=spec.get("cwd"))
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                init = await asyncio.wait_for(session.initialize(), spec.get("init_timeout", 60))
                tools = (await session.list_tools()).tools
                listed = [t.model_dump(mode="json", exclude_none=True) for t in tools]
                out = {"name": name, "ok": True, "server": init.serverInfo.name, "version": init.serverInfo.version,
                       "protocol": init.protocolVersion, "tool_count": len(listed), "tools": [t["name"] for t in listed],
                       "tools_sha256": hashlib.sha256(json.dumps(listed, sort_keys=True).encode()).hexdigest()}
                if spec.get("call"):
                    tool, arguments = spec["call"]
                    result = await asyncio.wait_for(session.call_tool(tool, arguments), 180)
                    text = "".join(getattr(c, "text", "") for c in result.content)
                    out["call"] = {"tool": tool, "isError": result.isError, "chars": len(text), "head": text[:160]}
        out["seconds"] = round(time.perf_counter() - started, 2)
        return out
    except BaseException as exc:  # noqa: BLE001
        inner = exc.exceptions[0] if isinstance(exc, BaseExceptionGroup) and exc.exceptions else exc
        return {"name": name, "ok": False, "error": f"{type(inner).__name__}: {str(inner)[:300]}",
                "seconds": round(time.perf_counter() - started, 2)}


async def main():
    specs = json.load(open(sys.argv[1]))
    for name in sys.argv[2:] or list(specs):
        print(json.dumps(await probe(name, specs[name]), ensure_ascii=False), flush=True)

asyncio.run(main())
