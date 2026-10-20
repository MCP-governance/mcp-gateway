"""D-122 detection, listing, final dispatch and lock ordering on isolated PostgreSQL.

Run only through termination_dispatch_lab.sh. Catalog discovery is replaced at
the product boundary so no MCP endpoint is called; database and product code are real.
"""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app import contract, core, db, dispatch, mcp_facade, ops_response
from termination_lab_support import Checks, add_principal, add_server, apply_schema, isolated_disposal, reservation, run

CHECKS = Checks("automatic suspension PostgreSQL")
TOKEN, ADMIN = "acceptance-employee", "acceptance-admin"
TARGET, OTHER = "gitea", "filesystem"
TARGET_TOOL, TARGET_PEER, OTHER_TOOL = "get_me", "get_gitea_mcp_server_version", "list_directory"
SCHEMA = {"type": "object", "properties": {}}
DESCRIPTION = "approved"


async def connect(name: str):
    conn = await psycopg.AsyncConnection.connect(db.DATABASE_URL, row_factory=dict_row)
    await conn.execute("SELECT set_config('application_name', %s, false)", (name,))
    await conn.commit()
    return conn


async def fixture(primary: str = TARGET, primary_tool: str = TARGET_TOOL) -> None:
    await add_principal(TOKEN)
    await add_principal(ADMIN, role="admin")
    tools = [(primary, primary_tool), (OTHER, OTHER_TOOL)]
    if primary == TARGET:
        tools.append((TARGET, TARGET_PEER))
    for server, tool in tools:
        await add_server(server)
        await db.execute(
            """INSERT INTO mcp_tools(server_id,name,action,enabled,scope_review,input_schema,
                      approved_schema_hash,observed_schema_hash,approved_description_hash,observed_description_hash)
               VALUES (%s,%s,'r',true,'{}',%s,'schema','schema','description','description')
               ON CONFLICT (server_id,name) DO UPDATE SET action='r',enabled=true,scope_review='{}',
                 input_schema=EXCLUDED.input_schema,approved_schema_hash='schema',observed_schema_hash='schema',
                 approved_description_hash='description',observed_description_hash='description'""",
            (server, tool, Jsonb(SCHEMA)))
        await db.execute(
            "UPDATE mcp_tools SET description=%s, approved_schema_hash=%s, observed_schema_hash=%s, "
            "approved_description_hash=%s, observed_description_hash=%s WHERE server_id=%s AND name=%s",
            (DESCRIPTION, contract.canonical_hash(SCHEMA), contract.canonical_hash(SCHEMA),
             contract.canonical_hash(DESCRIPTION), contract.canonical_hash(DESCRIPTION), server, tool))
    for server in {server for server, _ in tools}:
        await db.execute(
            "INSERT INTO catalog_snapshots(server_id,catalog_hash,tool_count,exact_match,restricted_tools) "
            "VALUES (%s,'lab',%s,true,'{}')", (server, sum(1 for owner, _ in tools if owner == server)))


def discovered(changed_schema: bool = False) -> dict:
    return {"version": "1.7.0", "protocol_version": "2025-03-26", "advertised_name": "lab",
            "tools": [{"name": name, "description": DESCRIPTION,
                       "input_schema": ({"type": "object", "properties": {"changed": {"type": "string"}}}
                                        if changed_schema and name == TARGET_TOOL else SCHEMA),
                       "output_schema": None, "annotations": None}
                      for name in (TARGET_TOOL, TARGET_PEER)]}


async def waiting(fragment: str, timeout: float = 8) -> None:
    observer = await connect("auto-suspend-observer")
    try:
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            row = await (await observer.execute(
                """SELECT 1 FROM pg_stat_activity a WHERE a.datname=current_database()
                     AND a.wait_event_type='Lock' AND a.query ILIKE %s
                     AND EXISTS (SELECT 1 FROM pg_locks l WHERE l.pid=a.pid AND NOT l.granted) LIMIT 1""",
                ("%" + fragment + "%",))).fetchone()
            if row:
                return
            await asyncio.sleep(0.01)
        raise AssertionError(f"PostgreSQL lock wait not observed: {fragment}")
    finally:
        await observer.close()


async def new_intent(server: str, tool: str) -> str:
    request_id = str(uuid.uuid4())
    await reservation(request_id, TOKEN, server, tool, fingerprint="auto-suspend-" + request_id)
    return request_id


async def intent_count(request_id: str) -> int:
    row = await db.fetch_one("SELECT count(*) AS n FROM dispatch_intents WHERE request_id=%s", (request_id,))
    return row["n"]


async def drift_detection_and_isolation() -> None:
    await fixture()
    with patch.object(core, "_discover", new=AsyncMock(return_value=discovered(changed_schema=True))):
        result = await core.refresh_catalog(TARGET)
    state = await db.fetch_one("SELECT status FROM mcp_servers WHERE id=%s", (TARGET,))
    snapshot = await db.fetch_one(
        "SELECT exact_match,restricted_tools FROM catalog_snapshots WHERE server_id=%s ORDER BY id DESC LIMIT 1",
        (TARGET,))
    listed_target = await mcp_facade._approved_tools("employee", TARGET, TOKEN)
    listed_other = await mcp_facade._approved_tools("employee", OTHER, TOKEN)
    CHECKS.ok("one-tool schema drift restricts that tool while keeping its server active",
              result["status"] == "DRIFT" and state["status"] != "DISABLED"
              and snapshot["restricted_tools"] == [TARGET_TOOL] and not any(tool.name == TARGET_TOOL for tool in listed_target)
              and any(tool.name == TARGET_PEER for tool in listed_target),
              status=state["status"], restricted=snapshot["restricted_tools"],
              target=[tool.name for tool in listed_target])
    CHECKS.ok("approved-tool query preserves another catalog server",
              any(tool.name == OTHER_TOOL for tool in listed_other),
              other=[tool.name for tool in listed_other])

    # Future or malformed drift evidence cannot be bounded to a reviewed tool, so it fails closed.
    await ops_response.contain_drift(TARGET, [{"type": "unclassified-contract-risk"}])
    stopped_state = await db.fetch_one("SELECT status FROM mcp_servers WHERE id=%s", (TARGET,))
    suspension = await db.fetch_one(
        "SELECT source,evidence,resumed_at FROM ops_suspensions WHERE server_id=%s AND resumed_at IS NULL",
        (TARGET,))
    CHECKS.ok("unclassifiable drift evidence automatically suspends its server",
              state["status"] != "DISABLED" and stopped_state["status"] == "DISABLED"
              and suspension["source"] == "drift"
              and suspension["evidence"]["findings"][0]["type"] == "unclassified-contract-risk"
              and suspension["resumed_at"] is None)

    stopped = await new_intent(TARGET, TARGET_PEER)
    unaffected = await new_intent(OTHER, OTHER_TOOL)
    denied = await dispatch.record(stopped, "r")
    allowed = await dispatch.record(unaffected, "r")
    CHECKS.ok("final intent query refuses only the stopped server", denied == "suspended"
              and await intent_count(stopped) == 0 and allowed is None and await intent_count(unaffected) == 1,
              target_reason=denied, target_intents=await intent_count(stopped), other_intents=await intent_count(unaffected))


async def anomaly_detection_and_admin_resume() -> None:
    await fixture(OTHER, OTHER_TOOL)
    for index in range(ops_response.REPEAT):
        await core._record_decision({
            "request_id": str(uuid.uuid4()), "trace_id": uuid.uuid4().hex, "user_token": TOKEN,
            "role": "employee", "server_id": OTHER, "tool_name": OTHER_TOOL,
            "data_class": "nonimportant", "action": "r", "decision": "Alert",
            "policy_id": "P-ANOMALY-001", "reason": "isolated anomaly signal", "upstream_executed": False,
        })
    await ops_response.contain_repeated()
    suspension = await db.fetch_one(
        "SELECT id,source,evidence FROM ops_suspensions WHERE server_id=%s AND resumed_at IS NULL", (OTHER,))
    CHECKS.ok("repeated anomaly decisions trigger server-wide stop at the configured threshold",
              bool(suspension) and suspension["source"] == "anomaly"
              and suspension["evidence"]["occurrences"] >= ops_response.REPEAT)

    pending = await new_intent(OTHER, OTHER_TOOL)
    CHECKS.ok("anomaly stop is not cleared without administrator action",
              await dispatch.record(pending, "r") == "suspended" and await intent_count(pending) == 0)
    resumed = await ops_response.resume(OTHER, ADMIN, "investigation completed")
    history = await db.fetch_one(
        "SELECT id,source,evidence,resumed_by,resume_note,resumed_at FROM ops_suspensions WHERE server_id=%s AND resumed_at IS NOT NULL",
        (OTHER,))
    event = await db.fetch_one(
        "SELECT count(*) AS n FROM approval_events WHERE kind='automatic-suspension-resume' AND target_id=%s AND actor=%s",
        (OTHER, ADMIN))
    request_id = await new_intent(OTHER, OTHER_TOOL)
    allowed = await dispatch.record(request_id, "r")
    CHECKS.ok("administrator resume is append-preserved and restores dispatch", resumed["status"] == "PENDING"
              and history["id"] == suspension["id"] and history["source"] == "anomaly"
              and history["evidence"]["occurrences"] >= ops_response.REPEAT
              and history["resumed_by"] == ADMIN and history["resume_note"] == "investigation completed"
              and history["resumed_at"] is not None and event["n"] == 1
              and allowed is None and await intent_count(request_id) == 1)


async def dispatch_wins_race() -> None:
    server, tool = "auto-suspend-race-dispatch", "race_tool"
    await fixture(server, tool)
    request_id = await new_intent(server, tool)
    reached, release = asyncio.Event(), asyncio.Event()

    async def callback(_connection):
        reached.set()
        await release.wait()
        return None

    dispatch_task = asyncio.create_task(dispatch.record(request_id, "r", recheck=callback))
    detector_task = None
    try:
        await asyncio.wait_for(reached.wait(), 8)
        detector_task = asyncio.create_task(ops_response.suspend(server, "anomaly", "lab stop", {"test": "race"}))
        await waiting("SELECT id FROM mcp_servers")
        release.set()
        CHECKS.ok("dispatch holding server SHARE commits one intent before suspension", await dispatch_task is None)
        await detector_task
        row = await db.fetch_one("SELECT resumed_at FROM ops_suspensions WHERE server_id=%s", (server,))
        CHECKS.ok("committed intent remains before the automatic suspension commit",
                  await intent_count(request_id) == 1 and row is not None and row["resumed_at"] is None)
    finally:
        release.set()
        for task in (dispatch_task, detector_task):
            if task and not task.done():
                task.cancel()
        await asyncio.gather(*(task for task in (dispatch_task, detector_task) if task), return_exceptions=True)


async def suspension_wins_race() -> None:
    server, tool = "auto-suspend-race-suspend", "race_tool"
    await fixture(server, tool)
    request_id = await new_intent(server, tool)
    gate = await connect("auto-suspend-row-gate")
    await gate.execute("BEGIN")
    await gate.execute("SELECT id FROM mcp_servers WHERE id=%s FOR UPDATE", (server,))
    detector_task = dispatch_task = None
    try:
        detector_task = asyncio.create_task(ops_response.suspend(server, "anomaly", "lab stop", {"test": "race"}))
        await waiting("SELECT id FROM mcp_servers")
        dispatch_task = asyncio.create_task(dispatch.record(request_id, "r"))
        await waiting("FOR SHARE OF s, t")
        await gate.commit()
        await detector_task
        result = await dispatch_task
        CHECKS.ok("suspension queued first commits before dispatch and leaves zero intents",
                  result == "suspended" and await intent_count(request_id) == 0, result=result,
                  intents=await intent_count(request_id))
    finally:
        if not gate.closed:
            await gate.rollback()
        await gate.close()
        for task in (detector_task, dispatch_task):
            if task and not task.done():
                task.cancel()
        await asyncio.gather(*(task for task in (detector_task, dispatch_task) if task), return_exceptions=True)


async def main() -> int:
    await apply_schema()
    await db.execute("INSERT INTO audit_chain(id,head_sha256,entries) VALUES (1,'genesis',0) ON CONFLICT DO NOTHING")
    with isolated_disposal():
        await CHECKS.case("drift_detection_and_isolation", drift_detection_and_isolation())
        await CHECKS.case("anomaly_detection_and_admin_resume", anomaly_detection_and_admin_resume())
        await CHECKS.case("dispatch_wins_race", dispatch_wins_race())
        await CHECKS.case("suspension_wins_race", suspension_wins_race())
    return CHECKS.finish()


if __name__ == "__main__":
    run(main)
