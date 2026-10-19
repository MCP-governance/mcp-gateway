"""D-140 lock interleavings against the isolated PostgreSQL lab.

Run only through termination_dispatch_lab.sh. Product dispatch/consent/audit code
uses its real psycopg pool; observer and competing transactions are independent
PostgreSQL connections. No MCP endpoint is called.
"""
from __future__ import annotations

import asyncio
import random
import uuid

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app import classify, consent, core, db, dispatch, flow_fingerprint
from termination_lab_support import Checks, add_principal, add_server, apply_schema, reservation, run

CHECKS = Checks("dispatch recheck PostgreSQL interleavings")
TOKEN = "dispatch-recheck-user"
SERVER = "dispatch-recheck-server"
TOOL = "dispatch-recheck-tool"
REVIEW = {"consent": True, "purpose": "lab", "grade": "nonimportant"}


async def connect(name: str):
    conn = await psycopg.AsyncConnection.connect(db.DATABASE_URL, row_factory=dict_row)
    await conn.execute("SELECT set_config('application_name', %s, false)", (name,))
    await conn.commit()
    return conn


async def fixture(*, with_consent: bool = False) -> tuple[str, int | None]:
    rid = str(uuid.uuid4())
    review = {**REVIEW, "purpose": rid} if with_consent else {}
    await add_principal(TOKEN)
    await add_server(SERVER)
    await db.execute(
        """INSERT INTO mcp_tools(server_id,name,action,enabled,scope_review,
                  approved_schema_hash,observed_schema_hash,approved_description_hash,observed_description_hash)
           VALUES (%s,%s,'w',true,%s,%s,%s,%s,%s)
           ON CONFLICT (server_id,name) DO UPDATE SET action='w',enabled=true,scope_review=EXCLUDED.scope_review,
             approved_schema_hash=EXCLUDED.approved_schema_hash,observed_schema_hash=EXCLUDED.observed_schema_hash,
             approved_description_hash=EXCLUDED.approved_description_hash,
             observed_description_hash=EXCLUDED.observed_description_hash""",
        (SERVER, TOOL, Jsonb(review), "schema", "schema", "description", "description"))
    await db.execute(
        """INSERT INTO catalog_snapshots(server_id,catalog_hash,tool_count,exact_match)
           VALUES (%s,'lab',1,true)""", (SERVER,))
    await reservation(rid, TOKEN, SERVER, TOOL, fingerprint="dispatch-recheck-" + rid)
    consent_id = None
    if with_consent:
        row = await db.fetch_one(
            """INSERT INTO user_consents(user_token,server_id,tool_name,grade,terms_hash,status,expires_at)
               VALUES (%s,%s,%s,'nonimportant',%s,'GRANTED',now()+interval '1 hour') RETURNING id""",
            (TOKEN, SERVER, TOOL, consent.terms_hash(review)))
        consent_id = row["id"]
    return rid, consent_id


async def waiting(query_fragment: str, *, app: str | None = None, timeout: float = 8) -> dict:
    """Wait until PostgreSQL reports the named statement waiting on an actual lock."""
    observer = await connect("dispatch-recheck-observer")
    try:
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            row = await (await observer.execute(
                """SELECT pid,query,wait_event_type,wait_event FROM pg_stat_activity
                    WHERE datname=current_database() AND pid<>pg_backend_pid()
                      AND wait_event_type='Lock' AND query ILIKE %s
                      AND EXISTS (SELECT 1 FROM pg_locks l WHERE l.pid=pg_stat_activity.pid AND NOT l.granted)
                      AND (%s::text IS NULL OR application_name=%s) LIMIT 1""",
                ("%" + query_fragment + "%", app, app))).fetchone()
            if row:
                return row
            await asyncio.sleep(0.01)
        raise AssertionError(f"PostgreSQL lock wait not observed: {query_fragment}")
    finally:
        await observer.close()


def callback_gate():
    reached = asyncio.Event()
    release = asyncio.Event()

    async def wait_at_callback():
        reached.set()
        await release.wait()

    return reached, release, wait_at_callback


async def table_gate(table: str):
    if table != "approval_events":
        raise ValueError("unsupported lock gate")
    conn = await connect("dispatch-recheck-gate")
    await conn.execute("BEGIN")
    await conn.execute("LOCK TABLE approval_events IN ACCESS EXCLUSIVE MODE")
    return conn


async def account_dispatch_first() -> None:
    rid, _ = await fixture()
    writer = None
    dispatch_task = update_task = None
    reached, release, wait_at_callback = callback_gate()
    try:
        async def recheck(_connection):
            await wait_at_callback()
            return None

        dispatch_task = asyncio.create_task(dispatch.record(rid, "w", recheck=recheck))
        await asyncio.wait_for(reached.wait(), 8)
        writer = await connect("dispatch-recheck-account-writer")
        await writer.execute("BEGIN")
        update_task = asyncio.create_task(writer.execute(
            "UPDATE principals SET status='disabled' WHERE token=%s", (TOKEN,)))
        await waiting("UPDATE principals", app="dispatch-recheck-account-writer")
        release.set()
        result = await dispatch_task
        CHECKS.ok("principal UPDATE waits for dispatch SHARE and follows intent commit", result is None)
        await update_task
        await writer.commit()
        count = await db.fetch_one("SELECT count(*) AS n FROM dispatch_intents WHERE request_id=%s", (rid,))
        CHECKS.ok("dispatch-first branch records exactly one intent", count["n"] == 1)
    finally:
        release.set()
        for task in (dispatch_task, update_task):
            if task and not task.done():
                task.cancel()
        await asyncio.gather(*(task for task in (dispatch_task, update_task) if task), return_exceptions=True)
        if writer and not writer.closed:
            await writer.rollback()
            await writer.close()


async def account_update_first() -> None:
    rid, _ = await fixture()
    writer = await connect("dispatch-recheck-account-writer")
    await writer.execute("BEGIN")
    await writer.execute("UPDATE principals SET status='disabled' WHERE token=%s", (TOKEN,))
    task = asyncio.create_task(dispatch.record(rid, "w"))
    try:
        await waiting("SELECT token FROM principals")
        await writer.commit()
        result = await task
        count = await db.fetch_one("SELECT count(*) AS n FROM dispatch_intents WHERE request_id=%s", (rid,))
        CHECKS.ok("committed disable is rechecked and refuses without intent", result == "principal" and count["n"] == 0,
                  result=result, intents=count["n"])
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if not writer.closed:
            await writer.rollback()
            await writer.close()


async def consent_dispatch_first() -> None:
    rid, consent_id = await fixture(with_consent=True)
    task = revoke = None
    reached, release, wait_at_callback = callback_gate()
    try:
        async def recheck(_connection):
            await wait_at_callback()
            return None

        task = asyncio.create_task(dispatch.record(rid, "w", recheck=recheck))
        await asyncio.wait_for(reached.wait(), 8)
        revoke = asyncio.create_task(consent.decide(consent_id, TOKEN, "revoke"))
        await waiting("UPDATE user_consents")
        release.set()
        CHECKS.ok("dispatch holding consent SHARE commits before revoke", await task is None)
        revoked = await revoke
        CHECKS.ok("consent.decide revoke proceeds after intent commit", revoked and revoked["status"] == "REVOKED")
    finally:
        release.set()
        for pending in (task, revoke):
            if pending and not pending.done():
                pending.cancel()
        await asyncio.gather(*(pending for pending in (task, revoke) if pending), return_exceptions=True)


async def consent_revoke_first() -> None:
    rid, consent_id = await fixture(with_consent=True)
    gate = await table_gate("approval_events")
    revoke = dispatch_task = None
    try:
        revoke = asyncio.create_task(consent.decide(consent_id, TOKEN, "revoke"))
        await waiting("INSERT INTO approval_events")
        dispatch_task = asyncio.create_task(dispatch.record(rid, "w"))
        await waiting("SELECT id FROM user_consents")
        await gate.commit()
        changed = await revoke
        result = await dispatch_task
        count = await db.fetch_one("SELECT count(*) AS n FROM dispatch_intents WHERE request_id=%s", (rid,))
        CHECKS.ok("consent.decide revoke commit is rechecked before dispatch intent",
                  changed and changed["status"] == "REVOKED" and result == "consent" and count["n"] == 0,
                  result=result, intents=count["n"])
    finally:
        if not gate.closed:
            await gate.rollback()
        await gate.close()
        for pending in (revoke, dispatch_task):
            if pending and not pending.done():
                pending.cancel()
        await asyncio.gather(*(pending for pending in (revoke, dispatch_task) if pending), return_exceptions=True)


def important_read_event(server_id: str) -> dict:
    return {"request_id": str(uuid.uuid4()), "trace_id": uuid.uuid4().hex,
            "user_token": TOKEN, "role": "employee", "server_id": server_id,
            "tool_name": "read", "data_class": "important", "action": "r",
            "decision": "Alert", "policy_id": "P-IMPORTANT-ALERT-001",
            "reason": "isolated PostgreSQL interleaving", "upstream_executed": True}


async def flow_dispatch_first() -> None:
    rid, _ = await fixture()
    task = publisher = None
    reached, release, wait_at_callback = callback_gate()
    # Reads published by earlier rounds stay in the 10-minute window: they are the decision's sources.
    source = "new-source-" + rid
    tool = {"name": TOOL, "base_action": "w", "action": "w", "provider_hosted": False}
    cls = classify.Classification(SERVER, TOOL, base_action="w", action="w")
    baseline = await core._flow_sources(TOKEN, SERVER, cls, False, flow_fingerprint.leaf_text({"body": "lab"}, keys=True))
    policy_input = {"tool": tool, "request": {"flow_sources": baseline}}
    try:
        async def recheck(conn):
            await wait_at_callback()
            return await core._dispatch_flow_recheck(conn, TOKEN, SERVER, policy_input, {"body": "lab"})

        task = asyncio.create_task(dispatch.record(rid, "w", recheck=recheck))
        await asyncio.wait_for(reached.wait(), 8)
        publisher = asyncio.create_task(core._record_decision(important_read_event(source)))
        await waiting("pg_advisory_xact_lock")
        release.set()
        result = await task
        CHECKS.ok("dispatch holding advisory commits before a new important-read publication", result is None, result=result)
        await publisher
        row = await db.fetch_one("SELECT count(*) AS n FROM decisions WHERE user_token=%s AND server_id=%s",
                                 (TOKEN, source))
        CHECKS.ok("queued read is published after dispatch intent", row["n"] == 1, n=row["n"])
    finally:
        release.set()
        for pending in (task, publisher):
            if pending and not pending.done():
                pending.cancel()
        await asyncio.gather(*(pending for pending in (task, publisher) if pending), return_exceptions=True)


async def flow_publication_first() -> None:
    rid, _ = await fixture()
    chain = await connect("dispatch-recheck-chain-writer")
    await chain.execute("BEGIN")
    await chain.execute("SELECT id FROM audit_chain WHERE id=1 FOR UPDATE")
    publisher = asyncio.create_task(core._record_decision(important_read_event("new-source")))
    dispatch_task = None
    try:
        await waiting("SELECT head_sha256 FROM audit_chain")
        policy_input = {"tool": {"name": TOOL, "base_action": "w", "action": "w", "provider_hosted": False},
                        "request": {"flow_sources": []}}
        reached, release, wait_at_callback = callback_gate()

        async def recheck(conn):
            await wait_at_callback()
            return await core._dispatch_flow_recheck(conn, TOKEN, SERVER, policy_input, {"body": "lab"})

        dispatch_task = asyncio.create_task(dispatch.record(rid, "w", recheck=recheck))
        await waiting("pg_advisory_xact_lock")
        await chain.commit()
        await publisher
        await asyncio.wait_for(reached.wait(), 8)
        release.set()
        result = await dispatch_task
        count = await db.fetch_one("SELECT count(*) AS n FROM dispatch_intents WHERE request_id=%s", (rid,))
        CHECKS.ok("published important read is seen by final flow recheck", result == "flow" and count["n"] == 0,
                  result=result, intents=count["n"])
    finally:
        if 'release' in locals():
            release.set()
        if not chain.closed:
            await chain.rollback()
            await chain.close()
        if not publisher.done():
            publisher.cancel()
            await asyncio.gather(publisher, return_exceptions=True)
        if dispatch_task and not dispatch_task.done():
            dispatch_task.cancel()
            await asyncio.gather(dispatch_task, return_exceptions=True)


async def main() -> int:
    await apply_schema()
    await add_principal(TOKEN)
    await db.execute("INSERT INTO audit_chain(id,head_sha256,entries) VALUES (1,'genesis',0) ON CONFLICT (id) DO NOTHING")
    await CHECKS.case("account_dispatch_first", account_dispatch_first())
    await db.execute("UPDATE principals SET status='active' WHERE token=%s", (TOKEN,))
    await CHECKS.case("account_update_first", account_update_first())
    await db.execute("UPDATE principals SET status='active' WHERE token=%s", (TOKEN,))
    await CHECKS.case("consent_dispatch_first", consent_dispatch_first())
    await CHECKS.case("consent_revoke_first", consent_revoke_first())
    await CHECKS.case("flow_dispatch_first", flow_dispatch_first())
    await CHECKS.case("flow_publication_first", flow_publication_first())

    # Randomized launch order exercises both writer-first and dispatcher-first
    # schedules repeatedly. pg_stat_activity is the barrier; every task is joined.
    deadlocks_before = await db.fetch_one("SELECT deadlocks FROM pg_stat_database WHERE datname=current_database()")
    failures = 0
    for trial in range(30):
        order = [account_dispatch_first, account_update_first, consent_dispatch_first,
                 consent_revoke_first, flow_dispatch_first, flow_publication_first]
        random.shuffle(order)
        for case in order:
            try:
                await case()
            except Exception as exc:
                failures += 1
                print(f"trial {trial} {case.__name__}: {type(exc).__name__}: {exc}", flush=True)
                break
            finally:
                await db.execute("UPDATE principals SET status='active' WHERE token=%s", (TOKEN,))
    deadlocks_after = await db.fetch_one("SELECT deadlocks FROM pg_stat_database WHERE datname=current_database()")
    CHECKS.ok("30 randomized lock-order rounds terminate without deadlock", failures == 0
              and deadlocks_after["deadlocks"] == deadlocks_before["deadlocks"],
              failed_rounds=failures, deadlocks=deadlocks_after["deadlocks"] - deadlocks_before["deadlocks"])
    return CHECKS.finish()


if __name__ == "__main__":
    run(main)
