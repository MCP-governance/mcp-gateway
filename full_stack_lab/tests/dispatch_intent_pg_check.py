"""Call reservation atomicity, the dispatch boundary and pool closure against a real PostgreSQL.

Run through termination_dispatch_lab.sh in the isolated lab. Everything here is the gateway's own
SQL and code on a real database; no MCP server is involved (tests/dispatch_effect_lab.py sends real
calls). The upstream connection pool is exercised without traffic (unit level)."""
from __future__ import annotations

import asyncio
import random
import uuid

from psycopg.types.json import Jsonb

from app import core, db, decommission, dispatch, upstream
from termination_lab_support import Checks, add_principal, add_server, apply_schema, isolated_disposal, reservation, run

CHECKS = Checks("dispatch intent and reservation atomicity (PostgreSQL)")


async def reserve(token, server, tool, arguments, rid=None, action="r"):
    rid = rid or str(uuid.uuid4())
    return rid, await core._reserve_call(rid, token, server, tool, arguments, "nonimportant", action)


async def completed_write_replay():
    token, args = "u-completed", {"x": "completed"}
    await add_principal(token)
    rid, _ = await reserve(token, "srv", "t", args, action="w")
    CHECKS.ok("first write records an intent", await dispatch.record(rid, "w") is None)
    await core._release_call(rid, 5001, "resolved")
    await db.execute("UPDATE call_reservations SET expires_at=now()-interval '1 day' WHERE request_id=%s", (rid,))
    retry, context = await reserve(token, "srv", "t", args, action="w")
    CHECKS.ok("completed write stays duplicate after lease expiry", context["duplicate_in_flight"])
    CHECKS.ok("final dispatch also refuses completed write", await dispatch.record(retry, "w") == "duplicate")
    await core._release_call(retry)
    read, context = await reserve(token, "srv", "t", args, action="r")
    CHECKS.ok("completed writes do not prevent a read", not context["duplicate_in_flight"])
    await core._release_call(read)
    changed, context = await reserve(token, "srv", "t", {"x": "changed"}, action="w")
    CHECKS.ok("different arguments are independent", not context["duplicate_in_flight"])
    await core._release_call(changed)
    await db.execute("UPDATE dispatch_intents SET resolved_at=now()-make_interval(secs => %s) WHERE request_id=%s",
                     (dispatch.IDEMPOTENCY_TTL_SECONDS + 1, rid))
    later, context = await reserve(token, "srv", "t", args, action="w")
    CHECKS.ok("definite outcome expires at the documented retention boundary", not context["duplicate_in_flight"])
    CHECKS.ok("write after retention can record", await dispatch.record(later, "w") is None)
    await core._release_call(later, 5002, "uncertain")
    await db.execute("UPDATE dispatch_intents SET resolved_at=now()-interval '10 years' WHERE request_id=%s", (later,))
    retry, context = await reserve(token, "srv", "t", args, action="w")
    CHECKS.ok("uncertain write does not expire with retention", context["duplicate_in_flight"])
    await core._release_call(retry)
    await dispatch.resolve(later, "not_executed", "admin", "synthetic lab: checked no effect")
    fresh, context = await reserve(token, "srv", "t", args, action="w")
    CHECKS.ok("confirmed not executed permits retry", not context["duplicate_in_flight"])
    await core._release_call(fresh)


async def stale_dispatch_replay_race():
    token = "u-final-replay"
    await add_principal(token)
    ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    for rid in ids:
        await reservation(rid, token, "srv", fingerprint="same-final-write")
    results = await asyncio.gather(*(dispatch.record(rid, "w") for rid in ids))
    CHECKS.ok("stale admitted contexts cannot both dispatch a write", results.count(None) == 1
              and results.count("duplicate") == 1, results=results)
    for rid in ids:
        await core._release_call(rid, 5003, "resolved")


def fingerprint(arguments, server="srv", tool="t"):
    return core.canonical_hash({"server": server, "tool": tool, "arguments": arguments})


async def identical_concurrent():
    results = await asyncio.gather(*[reserve("u-a", "srv", "t", {"x": 1}) for _ in range(24)])
    admitted = [r for _, r in results if not r["duplicate_in_flight"]]
    actives = sorted(r["active_calls"] for _, r in results)
    CHECKS.ok("identical call: exactly one reservation is not a duplicate", len(admitted) == 1, admitted=len(admitted))
    CHECKS.ok("identical call: active counts are serialised 1..24", actives == list(range(1, 25)), actives=actives)
    for rid, _ in results:
        await core._release_call(rid)


async def ceilings_distinct():
    results = await asyncio.gather(*[reserve("u-b", "srv", "t", {"x": i}) for i in range(core.CONCURRENCY_LIMIT * 3)])
    contexts = [r for _, r in results]
    within = [c for c in contexts if c["active_calls"] <= core.CONCURRENCY_LIMIT]
    CHECKS.ok("concurrency ceiling: only CONCURRENCY_LIMIT reservations fall within it", len(within) == core.CONCURRENCY_LIMIT,
              within=len(within), limit=core.CONCURRENCY_LIMIT)
    CHECKS.ok("concurrency ceiling: no distinct call is flagged duplicate", not any(c["duplicate_in_flight"] for c in contexts))
    recent = sorted(c["recent_calls"] for c in contexts)
    CHECKS.ok("rate window: each reservation sees exactly the earlier arrivals", recent == list(range(len(contexts))), recent=recent)
    CHECKS.ok("principals do not share a ceiling", (await reserve("u-c", "srv", "t", {"x": 0}))[1]["active_calls"] == 1)
    for rid, _ in results:
        await core._release_call(rid)


async def release_and_expiry():
    rid, first = await reserve("u-d", "srv", "t", {"y": 1})
    twin, second = await reserve("u-d", "srv", "t", {"y": 1})
    CHECKS.ok("open reservation refuses its identical twin", not first["duplicate_in_flight"] and second["duplicate_in_flight"])
    await core._release_call(rid)
    await core._release_call(twin)
    third_id, third = await reserve("u-d", "srv", "t", {"y": 1})
    CHECKS.ok("after both are released the identical call is a separate request", not third["duplicate_in_flight"])
    await core._release_call(third_id)
    old = core.RESERVATION_TTL_SECONDS
    core.RESERVATION_TTL_SECONDS = 1
    try:
        short_id, _ = await reserve("u-e", "srv", "t", {"z": 1})
        await asyncio.sleep(1.5)
        _, after = await reserve("u-e", "srv", "t", {"z": 1})
        CHECKS.ok("expired reservation no longer refuses the identical call", not after["duplicate_in_flight"])
        renewed = await db.execute(
            "UPDATE call_reservations SET expires_at=now()+interval '1 minute' WHERE request_id=%s AND released_at IS NULL AND expires_at > now()",
            (short_id,))
        CHECKS.ok("an expired reservation cannot be renewed for dispatch", renewed == 0)
        refused = await dispatch.record(short_id, "w")
        CHECKS.ok("an expired reservation cannot be recorded for dispatch", refused == "reservation", refused=refused)
    finally:
        core.RESERVATION_TTL_SECONDS = old


async def release_vs_reserve_race():
    both_admitted = 0
    for round_ in range(40):
        token = f"u-race-{round_}"
        await add_principal(token)
        first, _ = await reserve(token, "srv", "t", {"r": 1})
        await asyncio.sleep(random.random() * 0.01)
        _, a, b = await asyncio.gather(core._release_call(first), reserve(token, "srv", "t", {"r": 1}), reserve(token, "srv", "t", {"r": 1}))
        both_admitted += int(not a[1]["duplicate_in_flight"] and not b[1]["duplicate_in_flight"])
    CHECKS.ok("release racing two identical arrivals admits at most one of them", both_admitted == 0, both_admitted=both_admitted)


async def boundary_refusals():
    await add_principal("u-f")
    rid = str(uuid.uuid4())
    await reservation(rid, "u-f", "srv")
    CHECKS.ok("boundary: recorded while server operating and principal active", await dispatch.record(rid, "w") is None)
    row = await db.fetch_one("SELECT state, action FROM dispatch_intents WHERE request_id=%s", (rid,))
    CHECKS.ok("boundary: intent starts pending", row and row["state"] == "pending" and row["action"] == "w", row=row)
    await add_server("srv-down")
    await db.execute("UPDATE mcp_servers SET lifecycle='TERMINATING' WHERE id='srv-down'")
    rid2 = str(uuid.uuid4())
    await reservation(rid2, "u-f", "srv-down")
    CHECKS.ok("boundary: a terminating server is refused", await dispatch.record(rid2, "w") == "terminated")
    await add_principal("u-gone", status="disabled")
    rid3 = str(uuid.uuid4())
    await reservation(rid3, "u-gone", "srv")
    CHECKS.ok("boundary: a disabled principal is refused", await dispatch.record(rid3, "w") == "principal")
    count = await db.fetch_one("SELECT count(*) AS n FROM dispatch_intents WHERE request_id = ANY(%s::uuid[])", ([rid2, rid3],))
    CHECKS.ok("boundary: refused calls leave no intent", count["n"] == 0)


async def unsettled_blocks_identical_write():
    await add_principal("u-g")
    rid = str(uuid.uuid4())
    await reservation(rid, "u-g", "srv", "t", fingerprint({"w": 1}))
    await dispatch.record(rid, "w")
    await db.execute("UPDATE call_reservations SET expires_at = now() - interval '1 second' WHERE request_id=%s", (rid,))
    other, context = await reserve("u-g", "srv", "t", {"w": 1})
    CHECKS.ok("a pending intent whose reservation is gone (process died) refuses the identical write", context["duplicate_in_flight"])
    await core._release_call(other)
    CHECKS.ok("it is listed as needing confirmation", any(str(r["request_id"]) == rid for r in await dispatch.uncertain()))
    other, context = await reserve("u-g", "srv", "t", {"w": 2})
    CHECKS.ok("a different call is not refused", not context["duplicate_in_flight"])
    await core._release_call(other)
    resolved = await dispatch.resolve(rid, "not_executed", "admin-1", "downstream checked")
    CHECKS.ok("an administrator closes it", resolved["state"] == "confirmed_not_executed")
    other, context = await reserve("u-g", "srv", "t", {"w": 1})
    CHECKS.ok("after confirmation the identical write is allowed again", not context["duplicate_in_flight"])
    await core._release_call(other)
    try:
        await dispatch.resolve(rid, "executed", "admin-1", "")
        CHECKS.ok("a confirmed intent cannot be confirmed twice", False)
    except ValueError:
        CHECKS.ok("a confirmed intent cannot be confirmed twice", True)

    rid = str(uuid.uuid4())
    await reservation(rid, "u-g", "srv", "t", fingerprint({"read": 1}))
    await dispatch.record(rid, "r")
    await db.execute("UPDATE call_reservations SET expires_at = now() - interval '1 second' WHERE request_id=%s", (rid,))
    other, context = await reserve("u-g", "srv", "t", {"read": 1})
    CHECKS.ok("an unanswered read does not refuse its identical twin", not context["duplicate_in_flight"])
    await core._release_call(other)

    rid = str(uuid.uuid4())
    await reservation(rid, "u-g", "srv", "t", fingerprint({"late": 1}))
    await dispatch.record(rid, "w")
    await core._release_call(rid, 4242, "uncertain")
    row = await db.fetch_one("SELECT state, decision_id FROM dispatch_intents WHERE request_id=%s", (rid,))
    live = await db.fetch_one("SELECT released_at FROM call_reservations WHERE request_id=%s", (rid,))
    CHECKS.ok("an unanswered send keeps its place and is marked uncertain",
              row["state"] == "uncertain" and row["decision_id"] == 4242 and live["released_at"] is None, row=row)
    rid2 = str(uuid.uuid4())
    await reservation(rid2, "u-g", "srv", "t", fingerprint({"ok": 1}))
    await dispatch.record(rid2, "w")
    await core._release_call(rid2, 4243, "resolved")
    row = await db.fetch_one("SELECT state FROM dispatch_intents WHERE request_id=%s", (rid2,))
    live = await db.fetch_one("SELECT released_at FROM call_reservations WHERE request_id=%s", (rid2,))
    CHECKS.ok("an answered send resolves the intent and frees the place together",
              row["state"] == "resolved" and live["released_at"] is not None)


async def approval_is_consumed_once():
    await add_principal("u-h")
    approval = str(uuid.uuid4())
    approved = {"server_id": "srv", "tool": "t", "arguments": {"a": 1}, "user_token": "u-h"}
    await db.execute(
        """INSERT INTO approvals(id, request_fingerprint, request_payload, status, requested_by, expires_at)
           VALUES (%s,'f',%s,'APPROVED','u-h', now() + interval '10 minutes')""", (approval, Jsonb(approved)))
    rids = [str(uuid.uuid4()) for _ in range(8)]
    for rid in rids:
        await reservation(rid, "u-h", "srv", "t", fingerprint({"a": 1}))
    outcomes = await asyncio.gather(*[dispatch.record(rid, "w", approval) for rid in rids])
    CHECKS.ok("one approved write admits one dispatch; identical writes are duplicates",
              outcomes.count(None) == 1 and outcomes.count("duplicate") == 7, outcomes=outcomes)
    status = await db.fetch_one("SELECT status FROM approvals WHERE id=%s", (approval,))
    CHECKS.ok("the approval is consumed at the send", status["status"] == "UNCONFIRMED")
    intents = await db.fetch_one("SELECT count(*) AS n FROM dispatch_intents WHERE request_id = ANY(%s::uuid[])", (rids,))
    CHECKS.ok("refused uses leave no intent behind", intents["n"] == 1)
    read_retry = str(uuid.uuid4())
    await reservation(read_retry, "u-h", "srv", "t", fingerprint({"a": 1}))
    CHECKS.ok("consumed approval also refuses a read without duplicate-write gating",
              await dispatch.record(read_retry, "r", approval) == "approval")

    other = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO approvals(id, request_fingerprint, request_payload, status, requested_by, expires_at)
           VALUES (%s,'f',%s,'APPROVED','u-h', now() + interval '10 minutes')""", (other, Jsonb(approved)))
    for label, args, who in (("another request", {"a": 2}, "u-h"), ("another principal", {"a": 1}, "u-a")):
        rid = str(uuid.uuid4())
        await reservation(rid, who, "srv", "t", fingerprint(args))
        refused = await dispatch.record(rid, "w", other)
        left = await db.fetch_one("SELECT status FROM approvals WHERE id=%s", (other,))
        CHECKS.ok(f"an approval is not spent on {label}, and stays unspent", refused == "approval" and left["status"] == "APPROVED",
                  refused=refused, status=left["status"])


async def cutover_race():
    await add_principal("u-i")
    await add_server("srv-cut", "http://mcp-cut:8000/mcp")
    rids = [str(uuid.uuid4()) for _ in range(240)]
    for rid in rids:
        await reservation(rid, "u-i", "srv-cut", "t", f"f-{rid}")

    async def send(rid, delay):
        await asyncio.sleep(delay)
        return await dispatch.record(rid, "w")

    async def terminate():
        await asyncio.sleep(0.06)
        return await decommission.open_case("srv-cut", "lab cutover", "admin-1")

    *sent, case = await asyncio.gather(*[send(rid, i * 0.002) for i, rid in enumerate(rids)], terminate())
    cutover = (await db.fetch_one("SELECT cutover_at FROM termination_cases WHERE server_id='srv-cut'"))["cutover_at"]
    recorded = await db.fetch_one("SELECT count(*) AS n, max(attempted_at) AS last FROM dispatch_intents WHERE server_id='srv-cut'")
    done, refused = sent.count(None), sent.count("terminated")
    CHECKS.ok("cutover: every dispatch is recorded or refused", done + refused == len(rids), recorded=done, refused=refused)
    CHECKS.ok("cutover: both sides of the race were exercised", 0 < done < len(rids), recorded=done, refused=refused)
    CHECKS.ok("cutover: no dispatch is recorded after the cutover instant", recorded["last"] <= cutover, last=recorded["last"], cutover=cutover)
    CHECKS.ok("cutover: the recorded ones are exactly the intents in the table", recorded["n"] == done)
    events = await db.fetch_one("SELECT count(*) AS n FROM upstream_pool_events WHERE endpoint='http://mcp-cut:8000/mcp'")
    CHECKS.ok("cutover: the termination announces the pool closure", events["n"] >= 1)
    record = await decommission._case(case["case"]["id"])
    activity = await decommission._post_cutover(record)
    CHECKS.ok("cutover: calls sent before it and answered after it are reported apart", "straddled" in activity, activity=activity)
    CHECKS.ok("cutover: live reservations are not yet counted as lost", activity["unknown"] == 0, activity=activity)
    await db.execute("UPDATE call_reservations SET expires_at = now() - interval '1 second' WHERE server_id='srv-cut'")
    after = await decommission._post_cutover(record)
    CHECKS.ok("cutover: once their reservations are gone those sends count as unknown execution",
              after["unknown"] == done, unknown=after["unknown"], recorded=done)


async def pool_closure():
    pool = upstream._pool
    pool.clear()
    endpoint = "https://lab-a.example.test/mcp"
    async with upstream._dispatch_client(endpoint, "p1", {"Authorization": "Bearer one"}, 30):
        pass
    async with upstream._dispatch_client(endpoint, "p2", {"Authorization": "Bearer two"}, 30):
        pass
    async with upstream._dispatch_client("https://lab-b.example.test/mcp", "p1", {}, 30):
        pass
    CHECKS.ok("pool: three warm entries", len(pool) == 3)
    clients = [lease.client for lease in pool.values()]
    closed = await upstream.close_pool(endpoint=endpoint)
    CHECKS.ok("pool: closing an endpoint drops every principal's entry for it", closed == 2 and len(pool) == 1)
    CHECKS.ok("pool: the dropped clients are closed", sum(c.is_closed for c in clients) == 2)
    closed = await upstream.close_pool(principal="p1")
    CHECKS.ok("pool: closing a principal drops its entries on every endpoint", closed == 1 and not pool)

    async with upstream._dispatch_client(endpoint, "p3", {"Authorization": "Bearer three"}, 30) as held:
        await upstream.close_pool(principal="p3")
        CHECKS.ok("pool: an entry in use is detached but not closed under the call", not held.is_closed and not pool)
    CHECKS.ok("pool: it is closed when the call lets go", held.is_closed)

    async with upstream._dispatch_client(endpoint, "p4", {"Authorization": "Bearer old"}, 30):
        pass
    old = next(iter(pool.values())).client
    async with upstream._dispatch_client(endpoint, "p4", {}, 30):
        pass
    CHECKS.ok("pool: a removed credential's client is closed and does not stay holding it",
              old.is_closed and not any("old" in str(lease.client.headers.get("authorization", "")) for lease in pool.values()))

    pool.clear()
    async with upstream._dispatch_client(endpoint, "p5", {}, 30):
        pass
    upstream._swept.update(at=0.0, id=0)
    await db.execute("INSERT INTO upstream_pool_events(endpoint, principal, reason) VALUES (%s,%s,'lab')", (endpoint, "p5"))
    async with upstream._dispatch_client("https://lab-c.example.test/mcp", "p9", {}, 30):
        pass
    CHECKS.ok("pool: a closure announced by another process is applied on the next use",
              not any(k[0] == endpoint and k[1] == "p5" for k in pool))
    pool.clear()


async def main():
    with isolated_disposal():
        return await scenarios()


async def scenarios():
    await apply_schema()
    for token in ("u-a", "u-b", "u-c", "u-d", "u-e"):
        await add_principal(token)
    await add_server("srv")
    for case in (identical_concurrent, ceilings_distinct, release_and_expiry, release_vs_reserve_race, boundary_refusals,
                 unsettled_blocks_identical_write, approval_is_consumed_once, cutover_race, pool_closure,
                 completed_write_replay, stale_dispatch_replay_race):
        await CHECKS.case(case.__name__, case())
    return CHECKS.finish()


if __name__ == "__main__":
    run(main)
