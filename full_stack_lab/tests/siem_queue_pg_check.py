"""D-157: real PostgreSQL triggers, verified HTTPS and killed/restarted production workers.

Solution appliance only: tests/termination_dispatch_lab.sh run siem_queue_pg_check.py
Requires the runner's disposable database; never enters the product stack or calls MCP.
The receiver is a standard-library HTTPS server with a SQLite UID primary key.
"""
from __future__ import annotations

import asyncio
from collections import Counter
from contextlib import asynccontextmanager, closing
import os
from pathlib import Path
import re
import sqlite3
import ssl
import subprocess
import sys
import tempfile
import uuid

import psycopg
from psycopg.conninfo import conninfo_to_dict

from app import core, db, ops_response, review, siem
from termination_lab_support import Checks, apply_schema, isolated_disposal, run
from siem_tls_receiver import receiver

CHECKS = Checks("SIEM PostgreSQL queue / TLS / restart / UID deduplication")
LOCK = 721020157


@asynccontextmanager
async def worker(config, name, log):
    env = {**os.environ, "SIEM_URL": config["url"], "SIEM_CA_FILE": config["ca_file"], "PGAPPNAME": name}
    # Inherited secrets/configuration must not change this disposable receiver's contract.
    env.pop("SIEM_TOKEN_FILE", None)
    env.pop("SIEM_ALLOW_LOOPBACK_HTTP", None)
    with log.open("ab") as output:
        process = await asyncio.create_subprocess_exec(sys.executable, "-m", "app.siem", env=env,
                  stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT)
        try:
            yield process
        finally:
            if process.returncode is None:
                process.kill()
            await asyncio.wait_for(process.wait(), timeout=10)


async def until(query, params=(), *, predicate=bool, process=None):
    async with asyncio.timeout(20):
        while True:
            row = await db.fetch_one(query, params)
            if predicate(row):
                return row
            if process is not None and process.returncode is not None:
                raise AssertionError(f"worker exited unexpectedly: {process.returncode}")
            await asyncio.sleep(0.05)


async def source_rows():
    rows = await db.fetch_all("SELECT source,source_id FROM siem_outbox ORDER BY id")
    expected = {}
    for row in rows:
        source = row["source"]
        value = await db.fetch_one(f"SELECT {siem.SOURCE_COLUMNS[source]} FROM {source} WHERE id=%s", (row["source_id"],))
        expected[(source, row["source_id"])] = siem.event(source, value)
    return expected


async def triggers_and_restart(config, received, failures, store, folder):
    event_id = await core._record_decision({
        "request_id": str(uuid.uuid4()), "trace_id": "siem-synthetic-trace", "user_token": "siem-synthetic-principal",
        "role": "employee", "server_id": None, "tool_name": "siem-synthetic-tool", "data_class": "nonimportant",
        "action": "r", "decision": "Block", "policy_id": "MCP-CATALOG-001", "reason": "private-lab-reason",
        "request_payload": {"private-lab-body": "excluded"}, "upstream_executed": False,
    })
    initial = await db.fetch_one("SELECT * FROM siem_outbox WHERE source='decisions' AND source_id=%s", (event_id,))
    ledger = await db.fetch_one("SELECT * FROM decisions WHERE id=%s", (event_id,))
    uid = siem.event("decisions", ledger)["metadata"]["uid"]
    CHECKS.ok("production ledger append enqueues exactly one reference with chained UID",
              initial is not None and initial["attempts"] == 0 and uid == f"mint:decisions:{event_id}:{ledger['entry_sha256']}")
    # SQL rollback must roll back the reference too, including direct SQL writers.
    class RollbackFixture(Exception):
        pass
    rolled_back = None
    try:
        async with db.transaction() as connection:
            rolled_back = await review.record_event("siem-rollback", "recorded", "server", "lab", "lab", connection=connection)
            in_tx = await (await connection.execute(
                "SELECT 1 FROM siem_outbox WHERE source='approval_events' AND source_id=%s", (rolled_back,))).fetchone()
            CHECKS.ok("enqueue trigger is visible inside source transaction", in_tx is not None)
            raise RollbackFixture()
    except RollbackFixture:
        pass
    remaining = await db.fetch_one("SELECT 1 FROM siem_outbox WHERE source='approval_events' AND source_id=%s", (rolled_back,))
    CHECKS.ok("source rollback leaves no orphan delivery", remaining is None)

    for name, invalid in (("untrusted CA", {**config, "ca_file": ""}),
                          ("wrong hostname", {**config, "url": config["url"].replace("localhost", "127.0.0.1")})):
        try:
            await asyncio.to_thread(siem.send, invalid, siem.event("decisions", ledger))
        except ssl.SSLCertVerificationError:
            CHECKS.ok(f"TLS rejects {name} before HTTP delivery", not received)
        else:
            CHECKS.ok(f"TLS rejects {name} before HTTP delivery", False)

    crash_name = "siem-ack-crash-" + uuid.uuid4().hex
    # Test-only trigger in this disposable DB, not a hook or timing sleep in product code.
    await db.execute("""CREATE FUNCTION siem_lab_commit_barrier() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.delivered_at IS NOT NULL AND current_setting('application_name')=TG_ARGV[0] THEN
            PERFORM pg_advisory_xact_lock(721020157);
          END IF;
          RETURN NEW;
        END; $$""")
    await db.execute(psycopg.sql.SQL("""CREATE TRIGGER siem_lab_commit_barrier AFTER UPDATE ON siem_outbox
        FOR EACH ROW EXECUTE FUNCTION siem_lab_commit_barrier({})""").format(psycopg.sql.Literal(crash_name)))
    log = folder / "workers.log"
    try:
        async with await psycopg.AsyncConnection.connect(db.DATABASE_URL) as blocker:
            await blocker.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
            async with worker(config, crash_name, log) as first:
                failed = await until("SELECT * FROM siem_outbox WHERE id=%s", (initial["id"],),
                                     predicate=lambda row: row["attempts"] == 1, process=first)
                CHECKS.ok("receiver 503 retains reference and DB retry schedule",
                          failed["last_error"] == "HTTP-503" and failed["delivered_at"] is None
                          and failed["next_attempt_at"] > failed["created_at"] and len(received) == 1)
                await until("SELECT 1 FROM pg_stat_activity WHERE application_name=%s AND wait_event='advisory'",
                            (crash_name,), process=first)
                CHECKS.ok("verified HTTPS ACK precedes blocked outbox commit",
                          [(u, code) for u, code, _ in received] == [(uid, 503), (uid, 200)])

                approval = await review.record_event("siem-approved", "approved", "server", "lab", "lab")
                alert = await ops_response.emit_alert("unapproved-connection", "siem-lab", "real-path", {})
                synthetic = await ops_response.emit_alert("unapproved-connection", "siem-lab", "synthetic-path", {}, synthetic=True)
                filtered = await db.fetch_one("SELECT 1 FROM siem_outbox WHERE source='ops_alerts' AND source_id=%s", (synthetic["id"],))
                CHECKS.ok("synthetic alert is excluded by the real enqueue trigger", filtered is None)
                async with worker(config, "siem-competing-" + uuid.uuid4().hex, log) as other:
                    await until("SELECT 1 FROM siem_outbox WHERE source='approval_events' AND source_id=%s AND delivered_at IS NOT NULL",
                                (approval,), process=other)
                    await until("SELECT 1 FROM siem_outbox WHERE source='ops_alerts' AND source_id=%s AND delivered_at IS NOT NULL",
                                (alert["id"],), process=other)
                    held = await db.fetch_one("SELECT * FROM siem_outbox WHERE id=%s", (initial["id"],))
                    CHECKS.ok("SKIP LOCKED worker drains other events while ACKed row remains uncommitted",
                              held["delivered_at"] is None and held["attempts"] == 1 and len(received) == 4)
                first.kill()
                await asyncio.wait_for(first.wait(), timeout=10)
                CHECKS.ok("worker is killed at ACK/commit boundary", first.returncode == -9)
            # Release the DB wait so PostgreSQL can observe the dead client and roll back its transaction.
            await blocker.rollback()
        await until("SELECT count(*) AS n FROM pg_stat_activity WHERE application_name=%s", (crash_name,),
                    predicate=lambda row: row["n"] == 0)
        pending = await db.fetch_one("SELECT * FROM siem_outbox WHERE id=%s", (initial["id"],))
        CHECKS.ok("killed worker leaves the ACKed reference pending without incrementing committed attempts",
                  pending["delivered_at"] is None and pending["attempts"] == 1)
        async with worker(config, "siem-restarted-" + uuid.uuid4().hex, log) as restarted:
            await until("SELECT 1 FROM siem_outbox WHERE id=%s AND delivered_at IS NOT NULL", (initial["id"],), process=restarted)
        expected = await source_rows()
        expected_uids = {value["metadata"]["uid"] for value in expected.values()}
        with closing(sqlite3.connect(store)) as sink:
            stored = dict(sink.execute("SELECT uid,payload FROM events"))
            one = sink.execute("SELECT count(*) FROM events WHERE uid=?", (uid,)).fetchone()[0]
        CHECKS.ok("receiver UID deduplication stores exactly one event per source, zero loss",
                  len(expected_uids) == 3 and set(stored) == expected_uids and one == 1 and not failures)
        counts = Counter(u for u, _, _ in received)
        CHECKS.ok("only the interrupted event is retransmitted, always with the same payload and UID",
                  counts == Counter({key: 3 if key == uid else 1 for key in expected_uids})
                  and all(body == stored[u] for u, _, body in received))
        totals = await db.fetch_one("SELECT count(*) AS n, count(delivered_at) AS delivered, sum(attempts) AS attempts FROM siem_outbox")
        CHECKS.ok("all references commit after restart; committed counter excludes the rolled-back ACK",
                  totals == {"n": 3, "delivered": 3, "attempts": 4})
        text = log.read_text(encoding="utf-8")
        attempts = Counter(re.findall(r"SIEM attempt uid=(\S+)", text))
        responses = Counter(re.findall(r"SIEM response uid=(\S+)", text))
        commits = re.findall(r"SIEM queue committed uid=(\S+)", text)
        CHECKS.ok("worker logs count all five UID attempts including the ACK before crash",
                  attempts == responses == counts and len(commits) == 4 and "private-lab" not in text)
        unchanged = await db.fetch_one("SELECT * FROM decisions WHERE id=%s", (event_id,))
        CHECKS.ok("delivery and retry never mutate the append-only source ledger", unchanged == ledger)
    finally:
        await db.execute("DROP TRIGGER IF EXISTS siem_lab_commit_barrier ON siem_outbox")
        await db.execute("DROP FUNCTION IF EXISTS siem_lab_commit_barrier()")


async def main():
    target = conninfo_to_dict(db.DATABASE_URL)
    if (target.get("host") not in {"wbs-c-pg", "127.0.0.1", "localhost"}
            or not target.get("dbname", "").startswith("t_siem_queue_pg_check_py_")):
        raise RuntimeError("Use termination_dispatch_lab.sh with a fresh disposable SIEM test database")
    with isolated_disposal():
        await apply_schema()
        existing = await db.fetch_one("SELECT count(*) AS n FROM siem_outbox")
        if existing["n"]:
            raise RuntimeError("SIEM test database must have an empty queue")
        with tempfile.TemporaryDirectory(prefix="siem-pg-") as name:
            folder = Path(name)
            with receiver(folder) as (config, received, failures, store):
                await CHECKS.case("triggers_tls_crash_restart_dedup",
                    triggers_and_restart(config, received, failures, store, folder))
    return CHECKS.finish()


if __name__ == "__main__":
    run(main)
