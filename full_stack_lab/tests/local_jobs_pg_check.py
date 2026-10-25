"""DEV-73 (D-175) device job channel against isolated PostgreSQL.

Run through termination_dispatch_lab.sh. No MCP server and no container engine is involved:
the device side is driven through the same claim/complete functions its HTTP routes call.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from app import db, local_jobs, registry
from termination_lab_support import APP, Checks, add_principal, add_server, apply_schema, isolated_disposal, run

CHECKS = Checks("local MCP job channel PostgreSQL")
DEVICE_A, DEVICE_B, DEVICE_OFF = "lj-device-a", "lj-device-b", "lj-device-off"
DEVICE_STALE, DEVICE_SILENT = "lj-device-stale", "lj-device-silent"
OWNER, SERVER = "lj-owner", "srv"
MANIFEST = {"server_id": SERVER, "image": "mirror.test/mcp/fs@sha256:" + "a" * 64, "mounts": [], "command": ["serve"], "env": {},
            "reason": {"kind": "local_file", "text": "로컬 데이터 시험을 위한 합성 승인"},
            "approval": {"generation": 1, "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()}}
LOCAL = {"manifest": MANIFEST, "signature": "c2ln", "manifest_sha256": hashlib.sha256(local_jobs.canonical(MANIFEST)).hexdigest(),
         "observer_device": DEVICE_A}


async def device(endpoint_id: str, managed: str = "active", heartbeat_age: float | None = 0) -> dict:
    """A fresh health report by default: the gateway only dispatches to a device that reported within 180 seconds."""
    await db.execute(
        """INSERT INTO endpoint_agents(endpoint_id, hostname, platform, agent_version, owner_token, status,
                                       managed_state, local_username, local_uid, heartbeat_at)
           VALUES (%s,'lab','linux','lab','lj-owner','active',%s,'managed-lab',2001,
                   CASE WHEN %s::float8 IS NULL THEN NULL ELSE now()-make_interval(secs=>%s::float8) END)
           ON CONFLICT (endpoint_id) DO UPDATE SET managed_state=EXCLUDED.managed_state, heartbeat_at=EXCLUDED.heartbeat_at""",
        (endpoint_id, managed, heartbeat_age, heartbeat_age))
    return {"endpoint_id": endpoint_id}


async def answered(target: dict, method: str, result=None, error=None, *, after: float = 0.2) -> dict | None:
    await asyncio.sleep(after)
    job = await local_jobs.claim(target, 2)
    if job:
        await local_jobs.complete(target, job["id"], result, error, stopped=True)
    return job


async def fixture() -> None:
    """The approval the gateway needs before any job exists: owner, server, reviewed intake, active policy, signed manifest."""
    await add_principal(OWNER)
    await add_server(SERVER)
    await db.execute("INSERT INTO policy_versions(id,source_path,source_sha256,status) VALUES('lj-policy','synthetic','version-1','ACTIVE')")
    intake = str(uuid.uuid4())
    await db.execute("""INSERT INTO mcp_intake_requests(id,submitted_by,display_name,repository_url,requested_transport,
        purpose,status,reviewed_by,local_observer_device) VALUES(%s,%s,'synthetic','https://example.test/repository',
        'stdio','synthetic','APPROVED','synthetic-reviewer',%s)""", (intake, OWNER, DEVICE_A))
    with patch.dict(os.environ, {"LOCAL_IMAGE_MIRRORS": "mirror.test/mcp"}):
        await local_jobs.approve_manifest(LOCAL, intake, observed=True)


async def main() -> int:
    await apply_schema()
    await db.execute((APP / "local_run_tables.sql").read_text(encoding="utf-8"))
    await add_principal(OWNER)
    a, b = await device(DEVICE_A), await device(DEVICE_B)
    await device(DEVICE_OFF, managed="unmanaged")
    stale, silent = await device(DEVICE_STALE, heartbeat_age=600), await device(DEVICE_SILENT, heartbeat_age=None)
    await fixture()
    # The calls below arrive as the owner's authenticated transport, as execute_call hands them over.
    local_jobs.transport_context.set({"_principal": OWNER})
    with isolated_disposal(), patch.object(registry, "server", return_value={"local": LOCAL}), \
            patch.object(local_jobs, "control_generation", return_value="control-1"), \
            patch.object(local_jobs, "_device_control", AsyncMock(return_value="control")), \
            patch.object(local_jobs, "_same_control", AsyncMock(return_value=True)):
        return await scenarios(a, b, stale, silent)


async def scenarios(a, b, stale, silent) -> int:

    # A device only ever sees its own rows, and a result for someone else's row is refused.
    waiting = asyncio.create_task(local_jobs.exchange(DEVICE_A, LOCAL, "tools/list", {}, 5))
    await asyncio.sleep(0.2)
    stolen = await local_jobs.claim(b, 0.3)
    job = await local_jobs.claim(a, 2)
    refused = await local_jobs.complete(b, job["id"], {"tools": []}, None, stopped=True)
    accepted = await local_jobs.complete(a, job["id"], {"tools": [{"name": "x", "inputSchema": {"type": "object"}}]}, None, stopped=True)
    result = await waiting
    CHECKS.ok("job goes only to the caller's device and only that device can answer",
              stolen is None and job["method"] == "tools/list" and not refused and accepted and result["tools"][0]["name"] == "x"
              and job["manifest"] == LOCAL["manifest"] and job["signature"] == LOCAL["signature"])

    again = await local_jobs.complete(a, job["id"], {"tools": []}, None, stopped=True)
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

    # The freshness rule stays: a device whose health report expired (or never came) gets no job and takes none.
    outcomes = {}
    for name, target in (("stale", stale), ("silent", silent)):
        try:
            await local_jobs.exchange(target["endpoint_id"], LOCAL, "tools/list", {}, 1)
            outcomes[name] = "accepted"
        except local_jobs.NotStarted as exc:
            outcomes[name] = "점검 보고" in str(exc)
        try:
            await local_jobs.claim(target, 0)
            outcomes[name + "_claim"] = "accepted"
        except local_jobs.NotStarted as exc:
            outcomes[name + "_claim"] = "점검 보고" in str(exc)
    rows = await db.fetch_one("SELECT count(*) AS n FROM local_jobs WHERE device_id IN (%s,%s)", (DEVICE_STALE, DEVICE_SILENT))
    CHECKS.ok("expired or missing health report: no job is created and none is handed out",
              all(v is True for v in outcomes.values()) and rows["n"] == 0, outcomes=outcomes)
    await device(DEVICE_STALE, heartbeat_age=0)
    revived = asyncio.create_task(answered(stale, "tools/list", result={"tools": []}))
    reply = await local_jobs.exchange(DEVICE_STALE, LOCAL, "tools/list", {}, 3)
    await revived
    CHECKS.ok("the same device works again after a fresh health report", reply == {"tools": []})

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

    # Several claimers on one device: a device runs one job at a time, so they take turns and none is handed out twice.
    jobs = [asyncio.create_task(local_jobs.exchange(DEVICE_A, LOCAL, "initialize", {}, 8)) for _ in range(4)]
    await asyncio.sleep(0.3)

    async def worker() -> list[str]:
        mine = []
        while not all(j.done() for j in jobs):
            taken = await local_jobs.claim(a, 0.3)
            if taken:
                mine.append(taken["id"])
                await local_jobs.complete(a, taken["id"], {"protocolVersion": "2025-06-18", "serverInfo": {"name": "s", "version": "1"}},
                                          None, stopped=True)
        return mine
    ids = [i for mine in await asyncio.gather(*[worker() for _ in range(3)]) for i in mine]
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
            await local_jobs.complete(a, job["id"], reply, None, stopped=True)
    loop = asyncio.create_task(device_loop())
    client.principal = OWNER
    await client.start()
    page = await client.list_tools()
    called = await client.call_tool("read_file", {"path": "x"})
    await loop
    CHECKS.ok("SDK result models parse the device's answers",
              client.server_info.name == "fs" and page.tools[0].name == "read_file" and page.next_cursor == "p2"
              and called.content[0].text == "hello" and called.is_error is False)

    # A call's initialize and tools/list are answered from the approval; only tools/call reaches the device,
    # whose container checks the approved contract itself (10-23: three containers per call ran out of time).
    queued = (await db.fetch_one("SELECT count(*) AS n FROM local_jobs"))["n"]
    caller = local_jobs.LocalClient(DEVICE_A, LOCAL, 3, discovery=False)
    await caller.start()
    await caller.list_tools()
    CHECKS.ok("a call starts no initialize or tools/list job",
              (await db.fetch_one("SELECT count(*) AS n FROM local_jobs"))["n"] == queued)

    original = registry.server
    registry.server = lambda server_id: {"local": {**LOCAL, "observer_device": DEVICE_A}}
    await db.execute("DELETE FROM local_jobs")
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
