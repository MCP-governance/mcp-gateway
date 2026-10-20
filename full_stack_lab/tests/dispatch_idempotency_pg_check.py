"""D-126 replay races against isolated PostgreSQL using the production dispatch.record.

Run through termination_dispatch_lab.sh. This test calls no MCP endpoint; PostgreSQL
stores only synthetic lab principals, reservations, and dispatch intents.
"""
from __future__ import annotations

import asyncio
import uuid

from app import core, db, dispatch
from termination_lab_support import Checks, add_principal, add_server, apply_schema, reservation, run

CHECKS = Checks("dispatch idempotency PostgreSQL races")
SERVER = "idempotency-pg-server"
TOOL = "idempotency-pg-tool"
OWNER = "idempotency-pg-owner"
OTHER = "idempotency-pg-other"


async def fixture(request_id: str, token: str, arguments: dict) -> str:
    digest = core.canonical_hash({"server": SERVER, "tool": TOOL, "arguments": arguments})
    await reservation(request_id, token, SERVER, TOOL, digest)
    return digest


async def deadlocks() -> int:
    row = await db.fetch_one("SELECT deadlocks FROM pg_stat_database WHERE datname=current_database()")
    return int(row["deadlocks"])


async def concurrent_record() -> None:
    before = await deadlocks()
    rounds, callers = 10, 8
    for round_id in range(rounds):
        args = {"round": round_id, "change": "same"}
        request_ids = [str(uuid.uuid4()) for _ in range(callers)]
        for request_id in request_ids:
            await fixture(request_id, OWNER, args)
        results = await asyncio.wait_for(
            asyncio.gather(*(dispatch.record(request_id, "w") for request_id in request_ids)), timeout=30)
        accepted = [request_id for request_id, result in zip(request_ids, results) if result is None]
        intents = await db.fetch_one(
            "SELECT count(*) AS n FROM dispatch_intents WHERE request_id = ANY(%s::uuid[])", (request_ids,))
        CHECKS.ok(f"round {round_id + 1}: one intent and duplicate refusals",
                  len(accepted) == 1 and results.count("duplicate") == callers - 1 and intents["n"] == 1,
                  accepted=len(accepted), duplicate=results.count("duplicate"), intents=intents["n"])
    after = await deadlocks()
    CHECKS.ok("repeated concurrent record calls have zero PostgreSQL deadlocks", after == before == 0,
              before=before, after=after)


async def completed_ttl_and_scope() -> None:
    original = str(uuid.uuid4())
    args = {"change": "completed"}
    digest = await fixture(original, OWNER, args)
    CHECKS.ok("first completed candidate records intent", await dispatch.record(original, "w") is None)
    await core._release_call(original, 6200, "uncertain")
    closed = await dispatch.resolve(original, "executed", "lab-admin", "synthetic lab confirmation")
    CHECKS.ok("operator confirmation stores confirmed_executed", closed["state"] == "confirmed_executed")

    inside = str(uuid.uuid4())
    await reservation(inside, OWNER, SERVER, TOOL, digest)
    CHECKS.ok("same principal and fingerprint inside TTL is refused",
              await dispatch.record(inside, "w") == "duplicate")

    other = str(uuid.uuid4())
    await reservation(other, OTHER, SERVER, TOOL, digest)
    CHECKS.ok("same fingerprint from another principal is allowed",
              await dispatch.record(other, "w") is None)

    changed = str(uuid.uuid4())
    await fixture(changed, OWNER, {"change": "different"})
    CHECKS.ok("different arguments from the same principal are allowed",
              await dispatch.record(changed, "w") is None)

    read = str(uuid.uuid4())
    await reservation(read, OWNER, SERVER, TOOL, digest)
    CHECKS.ok("read with a matching fingerprint is not blocked by write history",
              await dispatch.record(read, "r") is None)

    await db.execute("UPDATE dispatch_intents SET resolved_at=now()-make_interval(secs => %s) WHERE request_id=%s",
                     (dispatch.IDEMPOTENCY_TTL_SECONDS + 1, original))
    expired = str(uuid.uuid4())
    await reservation(expired, OWNER, SERVER, TOOL, digest)
    CHECKS.ok("same principal and fingerprint is allowed after DB timestamp exceeds TTL",
              await dispatch.record(expired, "w") is None)


async def unsettled_until_confirmed() -> None:
    args = {"change": "uncertain"}
    first = str(uuid.uuid4())
    digest = await fixture(first, OWNER, args)
    CHECKS.ok("unsettled candidate records intent", await dispatch.record(first, "w") is None)
    await db.execute("UPDATE dispatch_intents SET attempted_at=now()-interval '10 years' WHERE request_id=%s", (first,))

    pending_retry = str(uuid.uuid4())
    await reservation(pending_retry, OWNER, SERVER, TOOL, digest)
    CHECKS.ok("pending write remains refused regardless of age",
              await dispatch.record(pending_retry, "w") == "duplicate")

    await core._release_call(first, 6201, "uncertain")
    row = await db.fetch_one("SELECT state FROM dispatch_intents WHERE request_id=%s", (first,))
    CHECKS.ok("lost response is preserved as uncertain", row["state"] == "uncertain")
    uncertain_retry = str(uuid.uuid4())
    await reservation(uncertain_retry, OWNER, SERVER, TOOL, digest)
    CHECKS.ok("uncertain write remains refused pending operator confirmation",
              await dispatch.record(uncertain_retry, "w") == "duplicate")

    resolved = await dispatch.resolve(first, "not_executed", "lab-admin", "synthetic lab confirmed no effect")
    CHECKS.ok("operator confirmation stores confirmed_not_executed",
              resolved["state"] == "confirmed_not_executed")
    retry = str(uuid.uuid4())
    await reservation(retry, OWNER, SERVER, TOOL, digest)
    CHECKS.ok("confirmed not executed permits identical write",
              await dispatch.record(retry, "w") is None)


async def main() -> int:
    await apply_schema()
    for token in (OWNER, OTHER):
        await add_principal(token)
    await add_server(SERVER)
    await db.execute(
        """INSERT INTO mcp_tools(server_id,name,action,enabled,approved_schema_hash,observed_schema_hash,
                  approved_description_hash,observed_description_hash)
           VALUES (%s,%s,'w',true,'schema','schema','description','description')
           ON CONFLICT (server_id,name) DO UPDATE SET action='w',enabled=true,
             approved_schema_hash=EXCLUDED.approved_schema_hash,observed_schema_hash=EXCLUDED.observed_schema_hash,
             approved_description_hash=EXCLUDED.approved_description_hash,
             observed_description_hash=EXCLUDED.observed_description_hash""",
        (SERVER, TOOL))
    await db.execute("INSERT INTO catalog_snapshots(server_id,catalog_hash,tool_count,exact_match) VALUES (%s,'lab',1,true)",
                     (SERVER,))
    for case in (concurrent_record, completed_ttl_and_scope, unsettled_until_confirmed):
        await CHECKS.case(case.__name__, case())
    return CHECKS.finish()


if __name__ == "__main__":
    run(main)
