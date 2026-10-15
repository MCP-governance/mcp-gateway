"""Stateful managed-endpoint checks against a dedicated PostgreSQL database.

Run only in the prepared Gateway image with SCENARIO_DATABASE_URL explicitly set
to the database risk_scenarios_20261014, for example:
  python - < stateful_endpoint_check.py

The script refuses DATABASE_URL-only configuration and any other database name.
It creates a unique scratch schema, invokes the real endpoint_plane functions,
queries committed effects through independent connections, records reset-before /
reset-after state, then drops only the schema it created. It never resets a database.
No MCP server is started or mocked.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import re
import secrets
import sys
import uuid

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


TARGET_DB = "risk_scenarios_20261014"
EXPECT_ATOMIC = "--expect-atomic" in sys.argv
SCHEMA = "risk_endpoint_" + uuid.uuid4().hex
assert re.fullmatch(r"risk_endpoint_[a-f0-9]{32}", SCHEMA)

SCENARIO_URL = os.environ.get("SCENARIO_DATABASE_URL", "").strip()
if not SCENARIO_URL:
    raise SystemExit("Set SCENARIO_DATABASE_URL explicitly; DATABASE_URL fallback is forbidden.")
try:
    DBNAME = conninfo_to_dict(SCENARIO_URL).get("dbname")
except Exception as exc:
    raise SystemExit("SCENARIO_DATABASE_URL is not valid PostgreSQL connection info.") from exc
if DBNAME != TARGET_DB:
    raise SystemExit(f"Refusing database {DBNAME!r}; expected exactly {TARGET_DB!r}.")

# Make the application's db module point only at the explicit scenario URL before
# importing endpoint_plane. The test replaces its DB helpers with schema-scoped
# connections so application SQL cannot fall through to public tables.
os.environ["DATABASE_URL"] = SCENARIO_URL
os.environ["IDP_ISSUER"] = "https://mcp-gateway.invalid"
os.environ["ENDPOINT_GATEWAY_IPS"] = "192.0.2.10"
os.environ["ENDPOINT_TAILSCALE_NODE_ID"] = "risk-scenarios-fixture"
if __file__ != "<stdin>":
    sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "full_stack_lab" / "gateway"))

from app import db, endpoint_plane  # noqa: E402

if conninfo_to_dict(db.DATABASE_URL).get("dbname") != TARGET_DB:
    raise SystemExit("Application DB configuration did not resolve to the dedicated scenario DB.")

pool = AsyncConnectionPool(SCENARIO_URL, min_size=1, max_size=6, open=False,
                           kwargs={"row_factory": dict_row})
schema_created = False
results: list[dict] = []


@asynccontextmanager
async def tx():
    async with pool.connection() as connection:
        async with connection.transaction():
            await connection.execute(
                sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(SCHEMA)))
            await connection.execute("SELECT set_config('application_name', %s, true)", (SCHEMA,))
            yield connection


async def fetch_one(query, params=None):
    async with tx() as connection:
        cursor = await connection.execute(query, params)
        return await cursor.fetchone()


async def fetch_all(query, params=None):
    async with tx() as connection:
        cursor = await connection.execute(query, params)
        return list(await cursor.fetchall())


async def execute(query, params=None):
    async with tx() as connection:
        cursor = await connection.execute(query, params)
        return cursor.rowcount


def install_db_boundary():
    db.transaction = tx
    db.fetch_one = fetch_one
    db.fetch_all = fetch_all
    db.execute = execute


async def independent(query, params=None):
    """Observe committed effects via a fresh connection, outside app helper calls."""
    async with await psycopg.AsyncConnection.connect(SCENARIO_URL, row_factory=dict_row) as connection:
        async with connection.transaction():
            await connection.execute(
                sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(SCHEMA)))
            cursor = await connection.execute(query, params)
            return await cursor.fetchall()


async def reset_snapshot(label):
    row = await independent("""SELECT
      (SELECT count(*) FROM principals) AS principals,
      (SELECT count(*) FROM endpoint_agents) AS devices,
      (SELECT count(*) FROM endpoint_enrollment_tokens) AS grants,
      (SELECT count(*) FROM endpoint_managed_events) AS events""")
    state = dict(row[0])
    print(json.dumps({"observation": label, "db": TARGET_DB, "schema": SCHEMA, **state}), flush=True)
    return state


async def create_schema():
    global schema_created
    async with pool.connection() as connection:
        async with connection.transaction():
            await connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(SCHEMA)))
    schema_created = True
    async with tx() as connection:
        await connection.execute("""
          CREATE TABLE principals (
            token text PRIMARY KEY, status text NOT NULL DEFAULT 'active',
            managed_required boolean NOT NULL DEFAULT false
          );
          CREATE TABLE mcp_servers (
            id text PRIMARY KEY, status text NOT NULL, lifecycle text NOT NULL
          );
          CREATE TABLE endpoint_agents (
            endpoint_id text PRIMARY KEY, hostname text NOT NULL, platform text NOT NULL,
            agent_version text NOT NULL, owner_token text REFERENCES principals(token),
            enrolled_at timestamptz NOT NULL DEFAULT now(), last_seen_at timestamptz NOT NULL DEFAULT now(),
            key_hash text, key_prefix text, scopes jsonb NOT NULL DEFAULT '[]',
            status text NOT NULL DEFAULT 'active', issued_by text, issued_at timestamptz,
            managed_state text NOT NULL DEFAULT 'unmanaged'
              CHECK (managed_state IN ('unmanaged','pending','active','quarantined')),
            device_epoch text, local_username text, local_uid integer, detail jsonb NOT NULL DEFAULT '{}',
            policy_hash text, heartbeat_at timestamptz, configuration_hashes jsonb NOT NULL DEFAULT '{}',
            enforcement_checks jsonb NOT NULL DEFAULT '{}', activated_by text, activated_at timestamptz
          );
          CREATE TABLE endpoint_enrollment_tokens (
            token_hash text PRIMARY KEY, owner_token text NOT NULL REFERENCES principals(token),
            issued_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL,
            consumed_at timestamptz, endpoint_id text REFERENCES endpoint_agents(endpoint_id)
          );
          CREATE TABLE endpoint_managed_events (
            id bigserial PRIMARY KEY, endpoint_id text, owner_token text NOT NULL,
            kind text NOT NULL, detail jsonb NOT NULL DEFAULT '{}', observed_at timestamptz NOT NULL DEFAULT now()
          );
          INSERT INTO mcp_servers(id,status,lifecycle)
            VALUES ('scenario-policy-server','READY','OPERATING');
        """)
    install_db_boundary()


async def seed_principal(token):
    await execute("INSERT INTO principals(token,status,managed_required) VALUES (%s,'active',true)", (token,))


async def enroll(owner, *, hostname):
    grant = await endpoint_plane.enrollment_token(owner)
    raw_key = secrets.token_urlsafe(32)
    device = await endpoint_plane.consume_enrollment(
        grant["enrollment_token"], raw_key, hostname, "risk-user", 42001, platform="linux")
    assert device["managed_state"] == "pending" and device["status"] == "active"
    assert device["device_epoch"] and device["key_hash"] == endpoint_plane._hash_key(raw_key)
    return device, raw_key


def claims(device, *, epoch=None):
    return {"device_id": device["endpoint_id"],
            "device_epoch": epoch if epoch is not None else device["device_epoch"],
            "device_policy": device.get("policy_hash"), "scope": "mcp"}


async def send_valid_heartbeat(device):
    policy = await endpoint_plane.managed_policy(device)
    checks = {name: True for name in endpoint_plane.managed_checks(device)}
    response = await endpoint_plane.heartbeat(
        device, policy["policy_hash"], policy["configuration_hashes"], checks)
    assert response["compliant"] is True
    device["policy_hash"] = policy["policy_hash"]
    return policy


async def observe_device(endpoint_id):
    row = await independent("""SELECT endpoint_id,status,managed_state,device_epoch,heartbeat_at,
      policy_hash,configuration_hashes,enforcement_checks,activated_by,activated_at
      FROM endpoint_agents WHERE endpoint_id=%s""", (endpoint_id,))
    assert len(row) == 1, "Independent query must find exactly one fixture device"
    return dict(row[0])


async def install_journal_failure_trigger():
    function = sql.Identifier(SCHEMA, "reject_terminal_event")
    async with tx() as connection:
        await connection.execute(sql.SQL("""
          CREATE FUNCTION {}() RETURNS trigger LANGUAGE plpgsql AS $$
          BEGIN
            IF NEW.kind IN ('activated','revoked') THEN
              RAISE EXCEPTION 'scenario_journal_failure' USING ERRCODE='P0001';
            END IF;
            RETURN NEW;
          END $$
        """).format(function))
        await connection.execute("""
          CREATE TRIGGER reject_terminal_event BEFORE INSERT ON endpoint_managed_events
          FOR EACH ROW EXECUTE FUNCTION reject_terminal_event()
        """)


async def remove_journal_failure_trigger():
    async with tx() as connection:
        await connection.execute("DROP TRIGGER IF EXISTS reject_terminal_event ON endpoint_managed_events")
        await connection.execute(sql.SQL("DROP FUNCTION IF EXISTS {}()").format(
            sql.Identifier(SCHEMA, "reject_terminal_event")))


async def capture_journal_failure(awaitable):
    try:
        result = await awaitable
    except Exception as exc:
        return {"raised":True,"type":type(exc).__name__,"sqlstate":getattr(exc,"sqlstate",None)}
    return {"raised":False,"result":result}


async def expect_denied(awaitable, label):
    try:
        result = await awaitable
    except (PermissionError, ValueError) as exc:
        return str(exc)
    raise AssertionError(f"{label} unexpectedly succeeded: {result!r}")


async def case_admit_activate_stale_revoke():
    owner, admin = "scenario-owner-main", "scenario-independent-admin"
    await seed_principal(owner)
    await seed_principal(admin)
    device, raw_key = await enroll(owner, hostname="scenario-main")
    before = await observe_device(device["endpoint_id"])
    assert before["managed_state"] == "pending"
    denied = await endpoint_plane.managed_failure(
        {"token": owner, "managed_required": True}, claims(device))
    assert denied and "활성 상태가 아니거나" in denied
    policy = await send_valid_heartbeat(device)
    activated = await endpoint_plane.activate_managed(
        device["endpoint_id"], admin, policy["policy_hash"], "scenario approval")
    assert activated["managed_state"] == "active"
    device["managed_state"] = "active"
    active = await observe_device(device["endpoint_id"])
    assert active["managed_state"] == "active" and active["activated_by"] == admin
    assert active["configuration_hashes"] == policy["configuration_hashes"]
    assert all(active["enforcement_checks"].values())
    assert await endpoint_plane.managed_failure(
        {"token": owner, "managed_required": True}, claims(device)) is None

    # Backdate only the dedicated fixture DB, avoiding a real 180-second sleep.
    await execute("UPDATE endpoint_agents SET heartbeat_at=now()-interval '181 seconds' WHERE endpoint_id=%s",
                  (device["endpoint_id"],))
    stale_failure = await endpoint_plane.managed_failure(
        {"token": owner, "managed_required": True}, claims(device))
    assert stale_failure and "만료" in stale_failure
    await send_valid_heartbeat(device)
    assert await endpoint_plane.managed_failure(
        {"token": owner, "managed_required": True}, claims(device)) is None

    epoch_failure = await endpoint_plane.managed_failure(
        {"token": owner, "managed_required": True}, claims(device, epoch="stale-epoch"))
    assert epoch_failure and "활성 상태가 아니거나" in epoch_failure
    result = await endpoint_plane.revoke_device(device["endpoint_id"], admin)
    assert result["status"] == "revoked"
    after = await observe_device(device["endpoint_id"])
    assert after["status"] == "revoked" and after["device_epoch"] == device["device_epoch"]
    revoked_failure = await endpoint_plane.managed_failure(
        {"token": owner, "managed_required": True}, claims(device))
    assert revoked_failure and "활성 상태가 아니거나" in revoked_failure
    await expect_denied(endpoint_plane.authenticate_device(raw_key, "inventory"), "revoked device key")
    events = await independent("SELECT kind FROM endpoint_managed_events WHERE endpoint_id=%s ORDER BY id",
                               (device["endpoint_id"],))
    kinds = [row["kind"] for row in events]
    assert "enrolled" in kinds and "activated" in kinds and "revoked" in kinds
    return {"case":"admit_activate_stale_revoke", "endpoint_id":device["endpoint_id"],
            "pending_denied":True,"active_effect_independently_observed":True,
            "stale_heartbeat_denied":True,"wrong_epoch_denied":True,
            "revoke_effect_independently_observed":True,"epoch_preserved_on_revoke":True,
            "event_kinds":kinds}


async def case_invalid_heartbeat_quarantines():
    owner = "scenario-owner-invalid"
    await seed_principal(owner)
    device, _ = await enroll(owner, hostname="scenario-invalid-heartbeat")
    policy = await endpoint_plane.managed_policy(device)
    checks = {name: True for name in endpoint_plane.managed_checks(device)}
    result = await endpoint_plane.heartbeat(
        device, "0" * 64, policy["configuration_hashes"], checks)
    assert result["compliant"] is False and result["state"] == "quarantined"
    persisted = await observe_device(device["endpoint_id"])
    assert persisted["managed_state"] == "quarantined"
    denied = await endpoint_plane.managed_failure(
        {"token":owner,"managed_required":True}, claims(device))
    assert denied and "활성 상태가 아니거나" in denied
    row = await independent("SELECT count(*) AS n FROM endpoint_managed_events WHERE endpoint_id=%s AND kind='quarantined'",
                            (device["endpoint_id"],))
    assert row[0]["n"] >= 1
    return {"case":"invalid_heartbeat_quarantines", "endpoint_id":device["endpoint_id"],
            "persisted_state":"quarantined","event_count":row[0]["n"]}


async def case_stale_activation_race():
    owner, admin = "scenario-owner-race", "scenario-admin-race"
    await seed_principal(owner)
    await seed_principal(admin)
    device, _ = await enroll(owner, hostname="scenario-activation-race")
    policy = await send_valid_heartbeat(device)
    actual_managed_policy = endpoint_plane.managed_policy
    entered, release = asyncio.Event(), asyncio.Event()

    async def gate_after_snapshot(snapshot):
        computed = await actual_managed_policy(snapshot)
        entered.set()
        await release.wait()
        return computed

    endpoint_plane.managed_policy = gate_after_snapshot
    task = asyncio.create_task(endpoint_plane.activate_managed(
        device["endpoint_id"], admin, policy["policy_hash"], "stale snapshot race"))
    stale_change_committed = False
    try:
        await asyncio.wait_for(entered.wait(), timeout=10)
        # Commit a changed heartbeat attestation after activation read its snapshot.
        # The CAS UPDATE must not activate based on that now-stale evidence.
        await execute("UPDATE endpoint_agents SET configuration_hashes='{}'::jsonb WHERE endpoint_id=%s",
                      (device["endpoint_id"],))
        stale_change_committed = True
    finally:
        if not stale_change_committed and not task.done():
            task.cancel()
        release.set()
        endpoint_plane.managed_policy = actual_managed_policy
        await asyncio.gather(task, return_exceptions=True)
    try:
        await asyncio.wait_for(task, timeout=10)
    except ValueError as exc:
        if "정상 설치 증거" not in str(exc):
            raise
    else:
        raise AssertionError("Stale activation race was accepted")
    persisted = await observe_device(device["endpoint_id"])
    assert persisted["managed_state"] == "pending" and persisted["activated_at"] is None
    return {"case":"stale_activation_race", "endpoint_id":device["endpoint_id"],
            "activation_rejected":True,"persisted_state":"pending",
            "independent_configuration_hashes":persisted["configuration_hashes"]}


async def case_activation_journal_failure():
    owner, admin = "scenario-owner-journal-activate", "scenario-admin-journal-activate"
    await seed_principal(owner)
    await seed_principal(admin)
    device, _ = await enroll(owner, hostname="scenario-activate-journal-failure")
    policy = await send_valid_heartbeat(device)
    try:
        await install_journal_failure_trigger()
        outcome = await capture_journal_failure(endpoint_plane.activate_managed(
            device["endpoint_id"], admin, policy["policy_hash"], "journal failure injection"))
    finally:
        await remove_journal_failure_trigger()
    persisted = await observe_device(device["endpoint_id"])
    events = await independent("SELECT count(*) AS n FROM endpoint_managed_events WHERE endpoint_id=%s AND kind='activated'",
                               (device["endpoint_id"],))
    assert outcome["raised"] and outcome["sqlstate"] == "P0001", outcome
    if EXPECT_ATOMIC:
        assert persisted["managed_state"] == "pending" and persisted["activated_at"] is None, persisted
        assert events[0]["n"] == 0
    else:
        assert persisted["managed_state"] == "active" and persisted["activated_at"] is not None, persisted
        assert events[0]["n"] == 0
    return {"case":"activation_journal_failure","endpoint_id":device["endpoint_id"],
            "expect_atomic":EXPECT_ATOMIC,"event_insert_failed":True,
            "state_after_failure":persisted["managed_state"],"activation_event_count":events[0]["n"],
            "known_finding_exposed":not EXPECT_ATOMIC}


async def case_revoke_journal_failure():
    owner, admin = "scenario-owner-journal-revoke", "scenario-admin-journal-revoke"
    await seed_principal(owner)
    await seed_principal(admin)
    device, _ = await enroll(owner, hostname="scenario-revoke-journal-failure")
    policy = await send_valid_heartbeat(device)
    await endpoint_plane.activate_managed(
        device["endpoint_id"], admin, policy["policy_hash"], "prepare revoke failure case")
    try:
        await install_journal_failure_trigger()
        outcome = await capture_journal_failure(
            endpoint_plane.revoke_device(device["endpoint_id"], admin))
    finally:
        await remove_journal_failure_trigger()
    persisted = await observe_device(device["endpoint_id"])
    events = await independent("SELECT count(*) AS n FROM endpoint_managed_events WHERE endpoint_id=%s AND kind='revoked'",
                               (device["endpoint_id"],))
    assert outcome["raised"] and outcome["sqlstate"] == "P0001", outcome
    if EXPECT_ATOMIC:
        assert persisted["status"] == "active" and persisted["managed_state"] == "active", persisted
        assert events[0]["n"] == 0
    else:
        assert persisted["status"] == "revoked" and persisted["managed_state"] == "active", persisted
        assert events[0]["n"] == 0
    return {"case":"revoke_journal_failure","endpoint_id":device["endpoint_id"],
            "expect_atomic":EXPECT_ATOMIC,"event_insert_failed":True,
            "status_after_failure":persisted["status"],"revocation_event_count":events[0]["n"],
            "known_finding_exposed":not EXPECT_ATOMIC}


CASE_SET = (case_admit_activate_stale_revoke,
            case_invalid_heartbeat_quarantines,
            case_stale_activation_race,
            case_activation_journal_failure,
            case_revoke_journal_failure)


async def main():
    failed = None
    before = after = None
    await pool.open(wait=True)
    try:
        await create_schema()
        before = await reset_snapshot("reset_before")
        assert before == {"principals":0,"devices":0,"grants":0,"events":0}
        for case in CASE_SET:
            result = await case()
            results.append(result)
            print(json.dumps({"ok":True,**result}), flush=True)
        after = await reset_snapshot("reset_after_before_drop")
    except Exception as exc:
        failed = {"type":type(exc).__name__,"detail":str(exc)[:400]}
    finally:
        if schema_created:
            try:
                after = after or await reset_snapshot("reset_after_failure_before_drop")
                async with pool.connection() as connection:
                    async with connection.transaction():
                        await connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(SCHEMA)))
                async with await psycopg.AsyncConnection.connect(SCENARIO_URL, row_factory=dict_row) as connection:
                    row = await (await connection.execute("SELECT to_regnamespace(%s) AS remaining", (SCHEMA,))).fetchone()
                    assert row["remaining"] is None, "Scratch schema remains after cleanup"
            except Exception as exc:
                failed = {"type":"cleanup_failed","detail":str(exc)[:400]}
        await pool.close()
        await db.close()
    output = {"ok":failed is None and len(results)==len(CASE_SET),"expect_atomic":EXPECT_ATOMIC,
              "db_name":TARGET_DB,"scratch_schema":SCHEMA,
              "expected_case_count":len(CASE_SET),"completed_case_count":len(results),
              "schema_created_by_this_process":schema_created,"schema_removed":schema_created and failed is None,
              "reset_before":before,"reset_after_before_drop":after,"cases":results}
    if failed:
        output["failure"] = failed
    print(json.dumps(output), flush=True)
    return 0 if output["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
