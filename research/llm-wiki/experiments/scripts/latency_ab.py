"""T3 latency A/B: the same MCP tool call direct to the server (A) and through the MINT gateway (B).

Official MCP Python SDK client, same host, same tool, same arguments; A and B interleaved so time-of-day
and network drift hit both. Cold = new session per call (initialize + tools/call + close);
warm = one long-lived session per path, tools/call only. Gateway headers come from a helper command
(the product's header-helper of the managed endpoint); its run time is recorded separately (token_ms)
and is not inside the call timings.
usage: python -I latency_ab.py --direct URL --gateway URL --tool NAME --args JSON --n 100 \
         --cafile ROOT.crt --helper "runuser -u managed-pj1 -- /path/header-helper" --out raw.csv
"""
import argparse, asyncio, csv, hashlib, json, shlex, ssl, subprocess, time
from datetime import datetime, timezone

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


def ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)


class Headers:
    """Gateway headers from the helper, re-run when older than max_age seconds."""

    def __init__(self, command: str, max_age: float = 120):
        self.command, self.max_age, self.value, self.at = command, max_age, None, 0.0

    def get(self) -> tuple[dict, float]:
        if self.value and time.monotonic() - self.at < self.max_age:
            return self.value, 0.0
        started = time.perf_counter()
        out = subprocess.run(shlex.split(self.command), capture_output=True, text=True, timeout=30, check=True).stdout
        self.value, self.at = json.loads(out), time.monotonic()  # never printed
        return self.value, ms(started)


class HelperAuth(httpx.Auth):
    """Per-request Authorization from the helper, like a harness headersHelper; a long warm session
    outlives one 300 s token, so headers fixed at session start would turn into 401 mid-run."""

    def __init__(self, helper: "Headers"):
        self.helper = helper

    def auth_flow(self, request):
        headers, _ = self.helper.get()
        request.headers.update(headers)
        yield request


def factory(context: ssl.SSLContext):
    def make(headers=None, timeout=None, auth=None):
        return httpx.AsyncClient(headers=headers, timeout=timeout, auth=auth, verify=context, follow_redirects=True)
    return make


def digest(result) -> tuple[int, str]:
    text = "".join(getattr(c, "text", "") for c in result.content)
    return len(text), hashlib.sha256(text.encode()).hexdigest()[:16]


async def cold(path, url, headers, tool, arguments, make):
    row = {"mode": "cold", "path": path}
    t0 = time.perf_counter()
    async with streamablehttp_client(url, headers=headers, timeout=60, httpx_client_factory=make) as (r, w, _):
        async with ClientSession(r, w) as session:
            t1 = time.perf_counter(); await session.initialize(); row["init_ms"] = ms(t1)
            t2 = time.perf_counter(); result = await session.call_tool(tool, arguments); row["call_ms"] = ms(t2)
    row["total_ms"] = ms(t0)
    row["is_error"] = bool(result.isError); row["chars"], row["sha"] = digest(result)
    return row


async def run(args):
    context = ssl.create_default_context()
    context.load_verify_locations(args.cafile)
    make, tool, arguments = factory(context), args.tool, json.loads(args.args)
    helper = Headers(args.helper)
    fields = ["mode", "path", "i", "at", "init_ms", "call_ms", "total_ms", "token_ms", "is_error", "chars", "sha", "error"]
    handle = open(args.out, "w", newline="")  # written row by row so an aborted run keeps its data
    writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore"); writer.writeheader()

    def stamp(row, i, token_ms=0.0):
        row.update(i=i, at=datetime.now(timezone.utc).isoformat(timespec="milliseconds"), token_ms=token_ms)
        writer.writerow(row); handle.flush(); print(json.dumps(row), flush=True)

    async def safe(coro, base):
        try:
            return await coro
        except BaseException as exc:  # noqa: BLE001 — a failed call is a row, never a silent skip
            inner = exc.exceptions[0] if isinstance(exc, BaseExceptionGroup) and exc.exceptions else exc
            return {**base, "error": f"{type(inner).__name__}: {str(inner)[:160]}"}

    for i in range(args.n):  # cold, interleaved A,B
        stamp(await safe(cold("A", args.direct, None, tool, arguments, make), {"mode": "cold", "path": "A"}), i)
        await asyncio.sleep(args.pause)
        headers, token_ms = helper.get()
        stamp(await safe(cold("B", args.gateway, headers, tool, arguments, make), {"mode": "cold", "path": "B"}), i, token_ms)
        await asyncio.sleep(args.pause)

    # warm: one session per path, kept open; call 0 is the first call on a fresh session
    async with streamablehttp_client(args.direct, timeout=60, httpx_client_factory=make) as (ra, wa, _), \
            streamablehttp_client(args.gateway, timeout=60, httpx_client_factory=make, auth=HelperAuth(helper)) as (rb, wb, _):
        async with ClientSession(ra, wa) as a, ClientSession(rb, wb) as b:
            await a.initialize(); await b.initialize()
            for i in range(args.n + 1):
                for path, session in (("A", a), ("B", b)):
                    base = {"mode": "warm", "path": path}

                    async def one():
                        t = time.perf_counter(); result = await session.call_tool(tool, arguments)
                        n, s = digest(result)
                        return {**base, "call_ms": ms(t), "total_ms": ms(t), "is_error": bool(result.isError), "chars": n, "sha": s}
                    stamp(await safe(one(), base), i)
                    await asyncio.sleep(args.pause)
    handle.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for name in ("--direct", "--gateway", "--tool", "--args", "--cafile", "--helper", "--out"):
        p.add_argument(name, required=True)
    p.add_argument("--n", type=int, default=100)
    p.add_argument("--pause", type=float, default=0.3)
    asyncio.run(run(p.parse_args()))
