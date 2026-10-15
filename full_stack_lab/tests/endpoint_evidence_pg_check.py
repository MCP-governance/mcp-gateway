"""PostgreSQL behaviour of the endpoint evidence receivers, in a database nobody else uses.

Run ONLY against a disposable PostgreSQL started for this check (see the work report for the
container recipe). The check refuses a database that already has the endpoint tables, applies the
schema files itself, and never deletes decision rows. The agent code is the real collector code;
the Gateway side is the real receiver code over a real PostgreSQL. No MCP server is involved.

    EVIDENCE_LAB=isolated DATABASE_URL=postgresql://... INIT_SQL=/schema/init.sql \
        python endpoint_evidence_pg_check.py
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

os.environ.setdefault("OTEL_SDK_DISABLED", "true")
HERE = Path(__file__).resolve().parent
for candidate in (HERE.parent / "gateway", Path("/app"), Path(os.getcwd())):
    if (candidate / "app" / "endpoint_plane.py").exists():
        sys.path.insert(0, str(candidate))
        break

import psycopg  # noqa: E402
from psycopg.errors import CheckViolation  # noqa: E402
from psycopg.types.json import Jsonb  # noqa: E402
from app import db, endpoint_plane, main  # noqa: E402

AGENT_DIR = Path(os.environ.get("AGENT_DIR") or HERE.parents[1] / "endpoint-agent")
APP_DIR = Path(endpoint_plane.__file__).parent
INIT_SQL = Path(os.environ.get("INIT_SQL") or HERE.parent / "db" / "init.sql")


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, AGENT_DIR / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


agent = load("pg_agent", "agent.py")
observer = load("pg_observer", "os-observer.py")
PASSED: list[str] = []


def ok(name: str) -> None:
    PASSED.append(name)
    print("PASS", name, flush=True)


async def scalar(query, params=None):
    row = await db.fetch_one(query, params)
    return next(iter(row.values()))


async def bootstrap_schema():
    if not os.environ.get("DATABASE_URL") or os.environ.get("EVIDENCE_LAB") != "isolated":
        raise SystemExit("EVIDENCE_LAB=isolated and a disposable DATABASE_URL are required")
    async with await psycopg.AsyncConnection.connect(os.environ["DATABASE_URL"], autocommit=True) as connection:
        found = await (await connection.execute("SELECT to_regclass('public.endpoint_agents') AS t")).fetchone()
        if found[0] is not None:
            raise SystemExit("the database already has endpoint tables; use a fresh disposable database")
        for path in (INIT_SQL, APP_DIR / "agent_tables.sql", APP_DIR / "lifecycle_tables.sql", APP_DIR / "v2_tables.sql"):
            await connection.execute(path.read_text(encoding="utf-8"))
        for _ in range(2):  # every start runs these again
            await connection.execute((APP_DIR / "v2_tables.sql").read_text(encoding="utf-8"))
    ok("schema applies on a fresh database and again without error")


async def agents():
    for endpoint_id, managed in (("ep-a", True), ("ep-b", True), ("ep-c", True), ("ep-d", False)):
        await db.execute(
            """INSERT INTO endpoint_agents(endpoint_id,hostname,platform,agent_version,owner_token,device_epoch,local_username,local_uid)
               VALUES (%s,%s,'Linux 6.8',%s,%s,%s,%s,1001)""",
            (endpoint_id, "host-" + endpoint_id, "managed-1" if managed else "3.1.0", "owner-" + endpoint_id[-1],
             "epoch-1" if managed else None, "user-" + endpoint_id[-1] if managed else None))


def entries(count, prefix="/fixture/cfg"):
    return [{"config_path": f"{prefix}-{n}.json", "server_label": f"srv-{n}", "transport": "streamable-http",
             "endpoint_ref": f"https://fixture-{n}.invalid/mcp"} for n in range(count)]


async def walk(call, **kwargs):
    seen, cursor, pages = [], None, 0
    while True:
        page = await call(limit=200, cursor=cursor, **kwargs)
        seen += [row["id"] for row in page["rows"]]
        pages += 1
        cursor = page["next_cursor"]
        if cursor is None:
            return seen, pages, page


async def check_paging():
    await endpoint_plane.ingest("ep-a", entries(450), complete=True, origin="automatic")
    first = await endpoint_plane.inventory_page(None, 200)
    assert (first["total"], len(first["rows"]), bool(first["next_cursor"])) == (450, 200, True), first["total"]
    await endpoint_plane.ingest("ep-a", entries(5, "/fixture/late"), complete=False, origin="automatic")
    ids, pages, last = await walk(endpoint_plane.inventory_page)
    assert last["total"] == 455 and pages == 3 and len(ids) == len(set(ids)) == 455 and ids == sorted(ids, reverse=True)
    resumed, cursor = [], first["next_cursor"]
    while cursor:
        page = await endpoint_plane.inventory_page(None, 200, cursor)
        resumed += [row["id"] for row in page["rows"]]
        cursor = page["next_cursor"]
    first_ids = [row["id"] for row in first["rows"]]
    assert len(resumed) == 250 and max(resumed) < min(first_ids), "rows added after page one must not shift page two"
    assert (await endpoint_plane.inventory_page("registered", 10))["total"] == 0
    assert (await endpoint_plane.inventory_page("shadow,retired-residue", 10))["total"] == 455
    ok("inventory total is counted apart from the 200-row window and a cursor walks every row once, newest first")

    findings = [{"source": "network", "address": f"10.0.{n // 250}.{n % 250 + 1}", "port": 7000 + n % 50, "mcp_evidence": "confirmed",
                 "server_name": f"s{n}"} for n in range(260)]
    await endpoint_plane.ingest_listeners("ep-a", findings, complete=True, sources=["network"], origin="automatic")
    ids, pages, last = await walk(endpoint_plane.listeners_page)
    assert (last["total"], len(ids), len(set(ids)), pages) == (260, 260, 260, 2)
    ok("listeners page beyond 200 rows with a stable order and the real total")

    events = [{"event_id": f"boot-fixture:{n:05d}", "observed_at": datetime.now(UTC) - timedelta(minutes=30, seconds=n), "kind": "execution-denied",
               "details": {"executable": f"tool{n}", "profile": "mcpgw-u"}} for n in range(230)]
    for start in range(0, 230, 100):
        await endpoint_plane.ingest_os_events("ep-a", events[start:start + 100])
    ids, pages, last = await walk(endpoint_plane.os_events_page)
    assert (last["total"], len(ids), len(set(ids)), pages) == (230, 230, 230, 2)
    summary = await main.endpoint_inventory(None, {})
    assert summary["pages"]["entries"]["total"] == 455 and len(summary["entries"]) == 200
    assert summary["pages"]["listeners"]["total"] == 260 and len(summary["listeners"]) == 200
    assert summary["pages"]["os_events"]["total"] == 230 and len(summary["os_events"]) == 200
    assert summary["pages"]["entries"]["next_cursor"] and summary["coverage"]["known_endpoints"] >= 3
    ok("the summary API reports totals and a next cursor next to its 200-row windows")

    seen, cursor = [], None
    while True:
        page = await endpoint_plane.observations_page(2, cursor)
        seen += [row["endpoint_id"] for row in page["rows"]]
        assert page["total"] == 4
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert sorted(set(seen)) == ["ep-a", "ep-b", "ep-c", "ep-d"] and len(seen) == 16
    assert {row["state"] for row in page["rows"]} <= {"success", "partial", "unknown", "failed"}
    ok("observation status pages by endpoint with channel state and freshness kept apart")


async def check_provenance():
    folder = Path(tempfile.mkdtemp())
    (folder / "mcp.json").write_text(json.dumps({"mcpServers": {
        "local": {"command": "npx", "args": ["-y", "some-mcp"], "env": {"TOKEN": "fixture-secret-value"}},
        "remote": {"url": "https://user:fixture-pass@mcp.example/mcp?key=fixture-key"}}}), encoding="utf-8")
    with mock.patch.object(agent, "SCAN_PATHS", [folder]):
        collected = agent.collect_configs()
    await endpoint_plane.ingest("ep-b", collected, complete=True, origin="automatic")
    rows = await db.fetch_all("SELECT * FROM endpoint_inventory WHERE endpoint_id='ep-b' ORDER BY id")
    assert len(rows) == 2
    for row in rows:
        provenance = row["provenance"]
        stored = {key: row[key] for key in agent.INVENTORY_FIELDS}
        assert provenance["state"] == "match", provenance
        assert provenance["server_projection_sha256"] == endpoint_plane.canonical_sha256(stored)
        assert provenance["agent_projection_sha256"] == provenance["server_projection_sha256"]
        assert provenance["received_at"] and provenance["collector"] == "config-file" and provenance["raw_sha256"]
        assert "fixture-secret-value" not in json.dumps(row["raw"], default=str) + json.dumps(provenance)
    tampered = json.loads(json.dumps(collected[0]))
    tampered["server_label"] = "renamed-after-hashing"
    await endpoint_plane.ingest("ep-b", [tampered], complete=False, origin="manual")
    changed = await db.fetch_one("SELECT provenance, origin FROM endpoint_inventory WHERE endpoint_id='ep-b' AND server_label='renamed-after-hashing'")
    assert changed["provenance"]["state"] == "mismatch" and changed["origin"] == "manual"
    legacy = {key: value for key, value in collected[1].items() if key != "provenance"}
    await endpoint_plane.ingest("ep-b", [legacy], complete=False)
    unreported = await db.fetch_one("SELECT provenance, origin FROM endpoint_inventory WHERE endpoint_id='ep-b' AND server_label=%s", (legacy["server_label"],))
    assert unreported["provenance"]["state"] == "unreported" and unreported["origin"] == "manual"
    ok("config entries store agent hash, server-recomputed hash over exactly the stored fields, steps, collector and time; mismatch and unreported are distinct")

    row = {"address": "127.0.0.1", "port": 7311, "process_name": "ghidramcp", "command_line": "ghidramcp --token fixture-secret"}
    with mock.patch.object(agent, "local_listeners", return_value=[row]), \
         mock.patch.object(agent, "probe_mcp", return_value={"server_name": "ghidra", "server_version": "1.0", "protocol_version": "2025-06-18", "path": "/mcp"}):
        findings = agent.listener_findings({"probe_mcp": True})
    await endpoint_plane.ingest_listeners("ep-b", findings, complete=True, sources=["local-socket"], origin="automatic")
    stored = await db.fetch_one("SELECT * FROM endpoint_listeners WHERE endpoint_id='ep-b'")
    assert stored["provenance"]["state"] == "match" and stored["origin"] == "automatic"
    assert stored["provenance"]["server_projection_sha256"] == endpoint_plane.canonical_sha256(
        endpoint_plane.projection_of(stored, endpoint_plane.LISTENER_FIELDS))
    ok("listeners store the same provenance and recompute over the stored columns")

    apparmor = ('apparmor="DENIED" operation="exec" class="file" profile="mcpgw-u" name="/usr/bin/{}" pid=77 comm="{}" '
                'requested_mask="x" denied_mask="x" fsuid=1001 ouid=0')
    stamp = str(int((datetime.now(UTC) - timedelta(minutes=2)).timestamp() * 1e6))
    records = [{"_BOOT_ID": "boot-fixture-b", "__CURSOR": f"s={n}", "__REALTIME_TIMESTAMP": stamp, "MESSAGE": apparmor.format(name, comm)}
               for n, (name, comm) in enumerate((("git", "claude"), ("curl", "bash")))]
    events = [main.EndpointOSEvent.model_validate(observer.event(record, 1001, "mcpgw-u", f"journal-line-{n}")).model_dump()
              for n, record in enumerate(records)]
    result = await endpoint_plane.ingest_os_events("ep-b", events)
    assert (result["accepted"], result["duplicates"]) == (2, 0)
    stored = await db.fetch_all("SELECT * FROM endpoint_os_events WHERE endpoint_id='ep-b' ORDER BY id")
    assert [row["denial_class"] for row in stored] == ["harness_startup", "blocked_attempt"]
    assert all(row["provenance"]["state"] == "match" and row["origin"] == "os_event" for row in stored)
    assert stored[0]["details"]["parent_executable"] == "claude" and stored[0]["details"]["profile"] == "mcpgw-u"
    projection = {"event_id": stored[0]["event_id"], "observed_at": endpoint_plane.canonical_time(stored[0]["observed_at"]),
                  "kind": stored[0]["kind"], "details": stored[0]["details"], "denial_class": stored[0]["denial_class"]}
    assert stored[0]["provenance"]["server_projection_sha256"] == endpoint_plane.canonical_sha256(projection)
    page = await endpoint_plane.os_events_page(denial_class="harness_startup", limit=50)
    assert page["total"] == 1 and page["rows"][0]["denial_class"] == "harness_startup"
    detail = await endpoint_plane.record_detail("os-event", stored[1]["id"])
    assert detail["denial_class"] == "blocked_attempt" and detail["provenance"]["collector"] == "journal-apparmor" and detail["record_kind"] == "os-event"
    assert await endpoint_plane.record_detail("os-event", 10**9) is None
    ok("OS events keep process info and class, match their hashes, are filterable by class and have a detail record")

    try:
        await db.execute("UPDATE endpoint_listeners SET origin='operator' WHERE endpoint_id='ep-b'")
    except CheckViolation:
        ok("the origin column accepts only automatic, manual and os_event")
    else:
        raise AssertionError("origin CHECK missing")


async def check_dedupe():
    (collected,) = [e for e in entries(1, "/fixture/dedupe")]
    collected["provenance"] = {"raw_sha256": "c" * 64, "projection_sha256": None, "transformations": [], "collector": "config-file"}
    first = await endpoint_plane.ingest("ep-c", [collected], complete=False, origin="automatic")
    again = await endpoint_plane.ingest("ep-c", [collected], complete=False, origin="automatic")
    count = await scalar("SELECT count(*) FROM endpoint_inventory WHERE endpoint_id='ep-c'")
    assert (first["duplicates"], again["duplicates"], count) == (0, 1, 1)
    ok("an inventory replay with the same raw hash is counted as a duplicate and adds no row")

    def event(event_id, raw="raw-journal-line-X"):
        return main.EndpointOSEvent.model_validate(agent.seal_os_event(
            {"event_id": event_id, "observed_at": datetime.now(UTC).isoformat(), "kind": "execution-denied",
             "details": {"executable": "git"}, "denial_class": "unknown"}, raw, "journal-apparmor", [])).model_dump()
    one = await endpoint_plane.ingest_os_events("ep-c", [event("boot-fixture-c:cursor-1")])
    same_key = await endpoint_plane.ingest_os_events("ep-c", [event("boot-fixture-c:cursor-1")])
    new_key = await endpoint_plane.ingest_os_events("ep-c", [event("boot-fixture-c:cursor-2")])
    assert (one["accepted"], same_key["accepted"], new_key["accepted"], new_key["duplicates"]) == (1, 0, 0, 1)
    digest = agent.hashlib.sha256(b"raw-journal-line-X").hexdigest()
    await db.execute("UPDATE endpoint_os_events SET received_at = now() - interval '8 days' WHERE raw_sha256=%s", (digest,))
    outside = await endpoint_plane.ingest_os_events("ep-c", [event("boot-fixture-c:cursor-3")])
    assert outside["accepted"] == 1
    assert await scalar("SELECT count(*) FROM endpoint_os_events WHERE endpoint_id='ep-c'") == 2
    ok("an OS event with the same raw hash inside the window is a replay; outside the window it is new")


async def decision(token, created, client):
    return await scalar(
        """INSERT INTO decisions(request_id,trace_id,created_at,user_token,role,tool_name,data_class,action,decision,policy_id,reason,server_id,client)
           VALUES (%s,%s,%s,%s,'employee','git_log','important','r','Allow','P-AUTHZ-ALLOW-001','fixture','git',%s) RETURNING id""",
        (uuid.uuid4(), uuid.uuid4().hex, created, token, Jsonb(client)))


async def check_correlation():
    now = datetime.now(UTC)
    traceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    near = await decision("owner-a", now - timedelta(seconds=20), {"device_id": "ep-a", "traceparent": traceparent})
    far = await decision("owner-a", now - timedelta(hours=2), {"device_id": "ep-a"})
    stranger = await decision("owner-z", now - timedelta(seconds=20), {"device_id": "ep-a"})
    unbound = await decision("owner-a", now - timedelta(seconds=20), {"workstation": "ep-a"})
    stamp = lambda delta: now - timedelta(seconds=delta)
    close = main.EndpointOSEvent.model_validate({"event_id": "boot-fixture-corr:near-0001", "observed_at": stamp(15).isoformat(), "kind": "execution-denied",
                                                 "details": {"executable": "curl", "parent_executable": "bash"}, "denial_class": "blocked_attempt",
                                                 "provenance": {"collector": "journal-apparmor"}}).model_dump()
    old = {**close, "event_id": "boot-fixture-corr:old-0001", "observed_at": stamp(7200)}
    await endpoint_plane.ingest_os_events("ep-a", [close, old])
    await endpoint_plane.ingest_listeners("ep-a", [{"source": "network", "address": "10.9.9.9", "port": 7777, "mcp_evidence": "confirmed"}],
                                          complete=False, origin="automatic")
    found = await endpoint_plane.correlate(decision_id=near)
    assert found["bound"] and found["anchor"]["traceparent"] == traceparent and found["anchor"]["endpoint_id"] == "ep-a"
    kinds = {record["kind"] for record in found["records"]}
    assert {"os-event", "listener"} <= kinds, kinds
    titles = {record["title"] for record in found["records"] if record["kind"] == "os-event"}
    assert titles == {"curl"}, titles
    assert all(record["at"] and "source" in record and "origin" in record for record in found["records"])
    assert len({(record["kind"], record["id"]) for record in found["records"]}) == len(found["records"])
    wide = await endpoint_plane.correlate(decision_id=far, window_seconds=99999)
    assert wide["window_seconds"] == 3600 and wide["bound"]
    for blocked in (stranger, unbound):
        none = await endpoint_plane.correlate(decision_id=blocked)
        assert none["bound"] is False and none["records"] == [], none
    assert await endpoint_plane.correlate(decision_id=10**9) is None
    event_id = await scalar("SELECT id FROM endpoint_os_events WHERE event_id='boot-fixture-corr:near-0001'")
    reverse = await endpoint_plane.correlate(kind="os-event", record_id=event_id)
    assert [record["id"] for record in reverse["records"]] == [near] and reverse["records"][0]["source"] == "gateway"
    assert reverse["records"][0]["traceparent"] == traceparent and reverse["records"][0]["kind"] == "decision"
    ok("correlation lists same-device same-principal records inside the window, each with its own source and time, and the reverse lookup finds the call")
    before = await scalar("SELECT count(*) FROM decisions")
    try:
        await db.execute("UPDATE decisions SET reason='x' WHERE id=%s", (near,))
    except psycopg.errors.RaiseException:
        pass
    else:
        raise AssertionError("decision rows must stay append-only")
    assert await scalar("SELECT count(*) FROM decisions") == before
    ok("correlation never touches the append-only decision ledger")


async def check_network():
    now = datetime.now(UTC)
    policy = {"policy_hash": "a" * 64, "configuration_hashes": {"managed-mcp.json": "b" * 64}}
    checks = {key: True for key in endpoint_plane.MANAGED_CHECKS}

    async def beat(endpoint_id, quality, hashes=None):
        device = await db.fetch_one("SELECT * FROM endpoint_agents WHERE endpoint_id=%s", (endpoint_id,))
        with mock.patch.object(endpoint_plane, "managed_policy", mock.AsyncMock(return_value=policy)):
            return await endpoint_plane.heartbeat(device, policy["policy_hash"], hashes or policy["configuration_hashes"], checks, None, quality)

    def sample(**changes):
        return {"measured_at": now, "rtt_p50_ms": 12.0, "rtt_p95_ms": 20.0, "jitter_ms": 1.5, "failure_pct": 0.0, "probes": 6, **changes}

    await db.execute("INSERT INTO endpoint_network_samples(endpoint_id,measured_at,rtt_p50_ms,rtt_p95_ms,jitter_ms,failure_pct,probes) VALUES ('ep-a',%s,9,9,0,0,6),('ep-a',%s,8,8,0,0,6)",
                     (now - timedelta(days=8), now - timedelta(days=6)))
    await db.execute("INSERT INTO endpoint_network_samples(endpoint_id,measured_at,rtt_p50_ms,rtt_p95_ms,jitter_ms,failure_pct,probes) VALUES ('ep-b',%s,50,60,2,50,6)",
                     (now - timedelta(minutes=10),))
    await beat("ep-a", sample(measured_at=now - timedelta(minutes=1), rtt_p50_ms=10.0, rtt_p95_ms=14.0, failure_pct=16.7))
    await beat("ep-a", sample())
    await beat("ep-a", sample())
    samples = await db.fetch_all("SELECT measured_at FROM endpoint_network_samples WHERE endpoint_id='ep-a' ORDER BY measured_at")
    assert len(samples) == 3, samples
    assert not any(row["measured_at"] < now - timedelta(days=7) for row in samples) and any(row["measured_at"] < now - timedelta(days=5) for row in samples)
    ok("heartbeats store one sample per measurement time and the ingest removes rows older than seven days")

    view = await endpoint_plane.network_quality()
    assert set(view) == {"devices", "summary"} and set(view["summary"]) == {"p50_ms", "p95_ms", "failure_pct", "devices"}
    keys = {"endpoint_id", "hostname", "measured_at", "rtt_p50_ms", "rtt_p95_ms", "jitter_ms", "failure_pct", "state"}
    assert all(set(device) == keys for device in view["devices"])
    states = {device["endpoint_id"]: device["state"] for device in view["devices"]}
    assert states == {"ep-a": "fresh", "ep-b": "stale", "ep-c": "unknown"}, states
    assert view["summary"]["devices"] == 1
    assert view["summary"]["p50_ms"] == 10.0 and view["summary"]["p95_ms"] == 20.0, view["summary"]
    assert abs(view["summary"]["failure_pct"] - 16.7 * 6 / 12) <= 0.051, view["summary"]
    ep_c = next(device for device in view["devices"] if device["endpoint_id"] == "ep-c")
    assert ep_c["measured_at"] is None and ep_c["rtt_p50_ms"] is None
    ok("network quality returns the exact contract; stale and unknown devices stay out of the fresh summary")

    receipt = (await db.fetch_one("SELECT detail->'install_receipt' AS receipt FROM endpoint_agents WHERE endpoint_id='ep-a'"))["receipt"]
    assert receipt["match"] is True
    assert receipt["provider_artifact_sha256"] == policy["configuration_hashes"] and receipt["installed_sha256"] == policy["configuration_hashes"]
    await beat("ep-a", None, {"managed-mcp.json": "d" * 64})
    changed = (await db.fetch_one("SELECT detail->'install_receipt' AS receipt, managed_state FROM endpoint_agents WHERE endpoint_id='ep-a'"))
    assert changed["receipt"]["match"] is False and changed["receipt"]["installed_sha256"]["managed-mcp.json"] == "d" * 64
    assert changed["managed_state"] == "quarantined"
    ok("the install receipt keeps the provider artifact hash and the installed file hash as separate roles")


async def check_idempotent_rerun():
    before = await scalar("SELECT count(*) FROM endpoint_inventory")
    async with await psycopg.AsyncConnection.connect(os.environ["DATABASE_URL"], autocommit=True) as connection:
        await connection.execute((APP_DIR / "v2_tables.sql").read_text(encoding="utf-8"))
    assert await scalar("SELECT count(*) FROM endpoint_inventory") == before
    ok("re-running the schema keeps the stored rows")


async def main_check():
    await bootstrap_schema()
    try:
        await agents()
        await check_paging()
        await check_provenance()
        await check_dedupe()
        await check_correlation()
        await check_network()
        await check_idempotent_rerun()
    finally:
        await db.close()
    print(json.dumps({"passed": len(PASSED)}), flush=True)


if __name__ == "__main__":
    asyncio.run(main_check())
