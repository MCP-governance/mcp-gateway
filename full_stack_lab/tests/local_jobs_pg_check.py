"""DEV-73 (D-175) device job channel against isolated PostgreSQL.

Run through termination_dispatch_lab.sh. No MCP server and no container engine is involved:
the device side is driven through the same claim/complete functions its HTTP routes call.
"""
from __future__ import annotations

import asyncio

from app import db, local_jobs
from termination_lab_support import Checks, apply_schema, run

CHECKS = Checks("local MCP job channel PostgreSQL")
DEVICE_A, DEVICE_B, DEVICE_OFF = "lj-device-a", "lj-device-b", "lj-device-off"
LOCAL = {"manifest": {"server_id": "srv"}, "signature": "c2ln", "manifest_sha256": "a" * 64}


async def device(endpoint_id: str, managed: str = "active") -> dict:
    await db.execute(
        """INSERT INTO endpoint_agents(endpoint_id, hostname, platform, agent_version, owner_token, status,
                                       managed_state, local_username, local_uid)
           VALUES (%s,'lab','linux','lab','lj-owner','active',%s,'managed-lab',2001)
           ON CONFLICT (endpoint_id) DO UPDATE SET managed_state=EXCLUDED.managed_state""",
        (endpoint_id, managed))
    return {"endpoint_id": endpoint_id}


async def answered(target: dict, method: str, result=None, error=None, *, after: float = 0.2) -> dict | None:
    await asyncio.sleep(after)
    job = await local_jobs.claim(target, 2)
    if job:
        await local_jobs.complete(target, job["id"], result, error)
    return job


async def main() -> int:
    await apply_schema()
    a, b = await device(DEVICE_A), await device(DEVICE_B)
    await device(DEVICE_OFF, managed="unmanaged")

    # A device only ever sees its own rows, and a result for someone else's row is refused.
    waiting = asyncio.create_task(local_jobs.exchange(DEVICE_A, LOCAL, "tools/list", {}, 5))
    await asyncio.sleep(0.2)
    stolen = await local_jobs.claim(b, 0.3)
    job = await local_jobs.claim(a, 2)
    refused = await local_jobs.complete(b, job["id"], {"tools": []}, None)
    accepted = await local_jobs.complete(a, job["id"], {"tools": [{"name": "x", "inputSchema": {"type": "object"}}]}, None)
    result = await waiting
    CHECKS.ok("job goes only to the caller's device and only that device can answer",
              stolen is None and job["method"] == "tools/list" and not refused and accepted and result["tools"][0]["name"] == "x"
              and job["manifest"] == LOCAL["manifest"] and job["signature"] == LOCAL["signature"])

    again = await local_jobs.complete(a, job["id"], {"tools": []}, None)
    CHECKS.ok("a finished job cannot be answered twice", not again)

    try:
        await local_jobs.exchange(DEVICE_A, LOCAL, "tools/call", {"name": "x", "arguments": {}}, 0.5)
        CHECKS.ok("unclaimed job is reported as not started", False)
    except local_jobs.NotStarted:
        row = await db.fetch_one("SELECT state FROM local_jobs WHERE device_id=%s ORDER BY created_at DESC LIMIT 1", (DEVICE_A,))
        late = await local_jobs.claim(a, 0.2)
        CHECKS.ok("unclaimed job is reported as not started and can no longer be taken",
                  row["state"] == "expired" and late is None)

    taker = asyncio.create_task(local_jobs.claim(a, 2))
    try:
        await local_jobs.exchange(DEVICE_A, LOCAL, "tools/call", {"name": "x", "arguments": {}}, 0.6)
        CHECKS.ok("taken but unanswered job is an unknown outcome", False)
    except local_jobs.NotStarted:
        CHECKS.ok("taken but unanswered job is an unknown outcome", False, got="NotStarted")
    except TimeoutError:
        CHECKS.ok("taken but unanswered job is an unknown outcome", (await taker) is not None)

    try:
        await local_jobs.exchange(DEVICE_OFF, LOCAL, "initialize", {}, 1)
        CHECKS.ok("inactive device gets no job", False)
    except local_jobs.NotStarted:
        count = await db.fetch_one("SELECT count(*) AS n FROM local_jobs WHERE device_id=%s", (DEVICE_OFF,))
        CHECKS.ok("inactive device gets no job", count["n"] == 0)

    helper = asyncio.create_task(answered(a, "tools/call", error="도구 실행 실패"))
    try:
        await local_jobs.exchange(DEVICE_A, LOCAL, "tools/call", {"name": "x", "arguments": {}}, 3)
        CHECKS.ok("device error surfaces as a failure", False)
    except RuntimeError as exc:
        await helper
        CHECKS.ok("device error surfaces as a failure", "도구 실행 실패" in str(exc))

    big = {"content": [{"type": "text", "text": "x" * (local_jobs.MAX_RESULT_BODY + 10)}]}
    helper = asyncio.create_task(answered(a, "tools/call", result=big))
    try:
        await local_jobs.exchange(DEVICE_A, LOCAL, "tools/call", {"name": "x", "arguments": {}}, 3)
        CHECKS.ok("oversized result is refused", False)
    except RuntimeError as exc:
        await helper
        CHECKS.ok("oversized result is refused", "상한" in str(exc))

    # Two claimers on one device: each job is handed out once.
    jobs = [asyncio.create_task(local_jobs.exchange(DEVICE_A, LOCAL, "initialize", {}, 3)) for _ in range(4)]
    await asyncio.sleep(0.3)
    claimed = await asyncio.gather(*[local_jobs.claim(a, 0.5) for _ in range(6)])
    ids = [c["id"] for c in claimed if c]
    for job_id in ids:
        await local_jobs.complete(a, job_id, {"protocolVersion": "2025-06-18", "serverInfo": {"name": "s", "version": "1"}}, None)
    await asyncio.gather(*jobs)
    CHECKS.ok("concurrent claims hand each job out once", len(ids) == 4 and len(set(ids)) == 4)

    # The SDK models accept what a stdio server sends, through the client _call_upstream uses.
    client = local_jobs.LocalClient(DEVICE_A, LOCAL, 3)
    replies = [{"protocolVersion": "2025-06-18", "serverInfo": {"name": "fs", "version": "2.0"}},
               {"tools": [{"name": "read_file", "description": "d", "inputSchema": {"type": "object"}}], "nextCursor": "p2"},
               {"content": [{"type": "text", "text": "hello"}], "isError": False}]

    async def device_loop():
        for reply in replies:
            job = await local_jobs.claim(a, 3)
            await local_jobs.complete(a, job["id"], reply, None)
    loop = asyncio.create_task(device_loop())
    await client.start()
    page = await client.list_tools()
    called = await client.call_tool("read_file", {"path": "x"})
    await loop
    CHECKS.ok("SDK result models parse the device's answers",
              client.server_info.name == "fs" and page.tools[0].name == "read_file" and page.next_cursor == "p2"
              and called.content[0].text == "hello" and called.is_error is False)

    from app import registry
    original = registry.server
    registry.server = lambda server_id: {"local": {**LOCAL, "observer_device": DEVICE_A}}
    try:
        try:
            async with local_jobs.session("local:srv", 1, None, discovery=False):
                pass
            fell_back = True
        except local_jobs.NotStarted as exc:
            fell_back = "관리형 엔드포인트에서 호출" not in str(exc)
        queued = await db.fetch_one("SELECT count(*) AS n FROM local_jobs WHERE state='queued'")
        CHECKS.ok("a call without a caller device never falls back to the observer", not fell_back and queued["n"] == 0)
    finally:
        registry.server = original

    return CHECKS.finish()


if __name__ == "__main__":
    run(main)
