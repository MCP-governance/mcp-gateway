"""PostgreSQL integration for endpoint snapshot completeness and source scoping.

Run only from the prepared Gateway Python environment with an explicit
SCENARIO_DATABASE_URL whose database name is exactly risk_scenarios_20261014.
The script creates/drops one UUID schema and never resets the database or uses the
application DATABASE_URL as a fallback. No MCP process or application enrollment is used.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import re
import sys
import uuid

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

TARGET_DB = "risk_scenarios_20261014"
SCHEMA = "risk_snapshot_" + uuid.uuid4().hex
assert re.fullmatch(r"risk_snapshot_[a-f0-9]{32}", SCHEMA)
SCENARIO_URL = os.environ.get("SCENARIO_DATABASE_URL", "").strip()
if not SCENARIO_URL:
    raise SystemExit("Set SCENARIO_DATABASE_URL explicitly; DATABASE_URL fallback is forbidden.")
try:
    if conninfo_to_dict(SCENARIO_URL).get("dbname") != TARGET_DB:
        raise SystemExit(f"Refusing DB; SCENARIO_DATABASE_URL must name {TARGET_DB!r}.")
except Exception as exc:
    if isinstance(exc, SystemExit):
        raise
    raise SystemExit("SCENARIO_DATABASE_URL is invalid PostgreSQL connection info.") from exc

GATEWAY = (Path('/app') if Path('/app/app/endpoint_plane.py').is_file()
           else Path(__file__).resolve().parents[4] / 'full_stack_lab' / 'gateway')
sys.path.insert(0, str(GATEWAY))
os.environ["DATABASE_URL"] = SCENARIO_URL
from app import db, endpoint_plane  # noqa: E402

if conninfo_to_dict(db.DATABASE_URL).get("dbname") != TARGET_DB:
    raise SystemExit("Application DB configuration did not resolve to the dedicated scenario DB.")

pool = AsyncConnectionPool(SCENARIO_URL, min_size=1, max_size=4, open=False,
                           kwargs={"row_factory": dict_row})
schema_created = False


@asynccontextmanager
async def tx():
    async with pool.connection() as connection:
        async with connection.transaction():
            await connection.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(SCHEMA)))
            await connection.execute("SELECT set_config('application_name', %s, true)", (SCHEMA,))
            yield connection


async def fetch_one(query, params=None):
    async with tx() as connection:
        cursor = await connection.execute(query, params) if params is not None else await connection.execute(query)
        return await cursor.fetchone()


async def fetch_all(query, params=None):
    async with tx() as connection:
        cursor = await connection.execute(query, params) if params is not None else await connection.execute(query)
        return list(await cursor.fetchall())


async def execute(query, params=None):
    async with tx() as connection:
        cursor = await connection.execute(query, params) if params is not None else await connection.execute(query)
        return cursor.rowcount


def install_db_boundary():
    db.transaction = tx
    db.fetch_one = fetch_one
    db.fetch_all = fetch_all
    db.execute = execute


async def independent(query, params=None):
    async with await psycopg.AsyncConnection.connect(SCENARIO_URL, row_factory=dict_row) as connection:
        async with connection.transaction():
            await connection.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(SCHEMA)))
            cursor = await connection.execute(query, params) if params is not None else await connection.execute(query)
            return list(await cursor.fetchall())


async def create_schema():
    global schema_created
    async with pool.connection() as connection:
        async with connection.transaction():
            await connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(SCHEMA)))
    schema_created = True
    async with tx() as connection:
        await connection.execute("""
          CREATE TABLE endpoint_agents (
            endpoint_id text PRIMARY KEY, hostname text NOT NULL DEFAULT 'fixture',
            platform text NOT NULL DEFAULT 'linux', agent_version text NOT NULL DEFAULT 'fixture',
            owner_token text NOT NULL DEFAULT 'fixture-owner', detail jsonb NOT NULL DEFAULT '{}',
            status_jsonb jsonb NOT NULL DEFAULT '{}',
            last_seen_at timestamptz NOT NULL DEFAULT now(), last_scan_at timestamptz
          );
          CREATE TABLE mcp_servers (
            id text PRIMARY KEY, transport text NOT NULL DEFAULT 'streamable-http', endpoint text,
            display_name text, advertised_name text, lifecycle text NOT NULL DEFAULT 'OPERATING',
            status text NOT NULL DEFAULT 'READY'
          );
          CREATE TABLE endpoint_inventory (
            id bigserial PRIMARY KEY, endpoint_id text NOT NULL REFERENCES endpoint_agents(endpoint_id) ON DELETE CASCADE,
            reported_at timestamptz NOT NULL DEFAULT now(), config_path text NOT NULL,
            server_label text NOT NULL, transport text NOT NULL, endpoint_ref text NOT NULL,
            fingerprint text NOT NULL, registry_match text REFERENCES mcp_servers(id),
            classification text NOT NULL CHECK (classification IN ('registered','shadow','retired-residue')),
            raw jsonb NOT NULL DEFAULT '{}', UNIQUE(endpoint_id,fingerprint)
          );
          CREATE TABLE endpoint_listeners (
            id bigserial PRIMARY KEY, endpoint_id text NOT NULL REFERENCES endpoint_agents(endpoint_id) ON DELETE CASCADE,
            observed_at timestamptz NOT NULL DEFAULT now(),
            source text NOT NULL CHECK (source IN ('local-socket','network','stdio-process')),
            address text NOT NULL, port integer, process_name text, command_line text,
            mcp_evidence text NOT NULL CHECK (mcp_evidence IN ('confirmed','suspected','unknown')),
            server_name text, server_version text, protocol_version text, fingerprint text NOT NULL,
            registry_match text REFERENCES mcp_servers(id),
            classification text NOT NULL CHECK (classification IN ('registered','shadow','retired-residue')),
            raw jsonb NOT NULL DEFAULT '{}', UNIQUE(endpoint_id,fingerprint)
          );
          CREATE TABLE termination_cases (
            id text PRIMARY KEY, server_id text, status text NOT NULL
          );
        """)
    install_db_boundary()


async def observe(label):
    rows = await independent("""
      SELECT (SELECT count(*) FROM endpoint_inventory WHERE endpoint_id='snapshot-fixture') AS inventory,
             (SELECT count(*) FROM endpoint_listeners WHERE endpoint_id='snapshot-fixture') AS listeners,
             (SELECT count(*) FROM endpoint_listeners WHERE endpoint_id='snapshot-fixture' AND source='local-socket') AS local_socket,
             (SELECT count(*) FROM endpoint_listeners WHERE endpoint_id='snapshot-fixture' AND source='network') AS network,
             (SELECT count(*) FROM endpoint_listeners WHERE endpoint_id='snapshot-fixture' AND source='stdio-process') AS stdio_process,
             (SELECT array_agg(fingerprint ORDER BY fingerprint) FROM endpoint_listeners WHERE endpoint_id='snapshot-fixture') AS listener_fingerprints,
             (SELECT detail FROM endpoint_agents WHERE endpoint_id='snapshot-fixture') AS detail,
             (SELECT status_jsonb FROM endpoint_agents WHERE endpoint_id='snapshot-fixture') AS status_jsonb
    """)
    state = dict(rows[0])
    print(json.dumps({"observation": label, "db": TARGET_DB, "schema": SCHEMA, **state}, default=str), flush=True)
    return state


async def seed():
    async with tx() as connection:
        await connection.execute("INSERT INTO endpoint_agents(endpoint_id) VALUES ('snapshot-fixture')")
        await connection.execute("""
          INSERT INTO endpoint_inventory(endpoint_id,config_path,server_label,transport,endpoint_ref,
            fingerprint,classification,raw)
          VALUES ('snapshot-fixture','/fixture/config.json','old','streamable-http','https://old.invalid/mcp',
            'inventory-old','shadow','{}')
        """)
        for source, fingerprint, address in (
            ("local-socket", "listener-local", "unix:/fixture.sock"),
            ("network", "listener-network", "192.0.2.10"),
            ("stdio-process", "listener-stdio", "process:fixture"),
        ):
            await connection.execute("""
              INSERT INTO endpoint_listeners(endpoint_id,source,address,port,mcp_evidence,fingerprint,classification,raw)
              VALUES ('snapshot-fixture',%s,%s,NULL,'suspected',%s,'shadow','{}')
            """, (source,address,fingerprint))


async def run_cases():
    await seed()
    before = await observe("before")
    assert before["inventory"] == 1 and before["listeners"] == 3
    fixture = {"config_path":"/fixture/new.json","server_label":"new","transport":"streamable-http",
               "endpoint_ref":"https://fixture.invalid/mcp"}
    result = await endpoint_plane.ingest("snapshot-fixture", [fixture], complete=False)
    state = await observe("inventory-incomplete")
    assert result["accepted"] == 1 and state["inventory"] == 2, (result,state)

    # Legacy unmarked empty input remains compatible for upserts but cannot delete.
    await endpoint_plane.ingest("snapshot-fixture", [])
    state = await observe("inventory-legacy-unmarked-empty")
    assert state["inventory"] == 2, state
    # Only an explicit complete marker authorizes full inventory reconciliation.
    await endpoint_plane.ingest("snapshot-fixture", [], complete=True)
    state = await observe("inventory-explicit-complete-empty")
    assert state["inventory"] == 0, state

    before_bad = await observe("listener-before-invalid")
    try:
        await endpoint_plane.ingest_listeners("snapshot-fixture", [
            {"source":"network","address":"192.0.2.11","mcp_evidence":"suspected"}],
            complete=True, sources=["stdio-process"])
    except (ValueError, TypeError):
        pass
    else:
        raise AssertionError("source/findings mismatch was accepted")
    after_bad = await observe("listener-after-invalid")
    assert (before_bad["listeners"],before_bad["local_socket"],before_bad["network"],before_bad["stdio_process"]) == (
        after_bad["listeners"],after_bad["local_socket"],after_bad["network"],after_bad["stdio_process"]), (before_bad,after_bad)

    # Partial process collection records a fresh report but preserves last success.
    await endpoint_plane.observation_status("snapshot-fixture", "process", "success", 1, "")
    successful = (await independent("SELECT detail FROM endpoint_agents WHERE endpoint_id='snapshot-fixture'"))[0]["detail"]
    last_success = successful["observation"]["process"]["last_success_at"]
    await endpoint_plane.ingest_listeners("snapshot-fixture", [{
        "source":"stdio-process","address":"process:fixture","mcp_evidence":"suspected"}],
        complete=False, sources=["stdio-process"])
    partial = (await independent("SELECT detail FROM endpoint_agents WHERE endpoint_id='snapshot-fixture'"))[0]["detail"]
    process_status = partial["observation"]["process"]
    assert process_status["state"] == "partial" and process_status["sources"] == ["stdio-process"], process_status
    assert process_status["last_success_at"] == last_success and process_status["reported_at"] != last_success, process_status

    # Stale telemetry remains explicitly stale while conservative count is retained.
    await execute("""UPDATE endpoint_agents SET detail=jsonb_set(jsonb_set(detail,'{observation,process,state}',to_jsonb('success'::text)),'{observation,process,reported_at}',to_jsonb((now()-interval '181 seconds')::text))
                    WHERE endpoint_id='snapshot-fixture'""")
    stale_detail = (await independent("SELECT detail FROM endpoint_agents WHERE endpoint_id='snapshot-fixture'"))[0]["detail"]
    stale_status = stale_detail["observation"]["process"]
    observed_at = (await independent("SELECT observed_at FROM endpoint_listeners WHERE endpoint_id='snapshot-fixture' AND source='stdio-process' LIMIT 1"))[0]["observed_at"]
    freshness = endpoint_plane.observation_freshness(stale_status, observed_at)
    conservative_count = await endpoint_plane.shadow_listener_count_for("fixture-owner")
    assert freshness == "stale", {"freshness":freshness,"status":stale_status}
    # The partial report inserted a new fingerprint and must retain the three older rows.
    assert conservative_count == 4, conservative_count

    # A complete empty scan scoped to stdio removes that source only.
    result = await endpoint_plane.ingest_listeners("snapshot-fixture", [], complete=True, sources=["stdio-process"])
    scoped = await observe("listener-stdio-scoped-empty")
    assert scoped["stdio_process"] == 0 and scoped["network"] == 1 and scoped["local_socket"] == 1, (result,scoped)

    # Trigger a failure after the receiver has upserted but before snapshot deletion;
    # committed state must remain identical to the pre-call snapshot.
    async with tx() as connection:
        await connection.execute("""
          CREATE FUNCTION reject_snapshot_delete() RETURNS trigger LANGUAGE plpgsql AS $$
          BEGIN RAISE EXCEPTION 'snapshot_delete_failure' USING ERRCODE='P0001'; END $$;
          CREATE TRIGGER reject_snapshot_delete BEFORE DELETE ON endpoint_listeners
          FOR EACH ROW EXECUTE FUNCTION reject_snapshot_delete();
        """)
    rollback_before = await observe("listener-rollback-before")
    try:
        try:
            await endpoint_plane.ingest_listeners("snapshot-fixture", [{
                "source":"stdio-process","address":"process:rollback","mcp_evidence":"suspected"}],
                complete=True, sources=None)
        except Exception as exc:
            print(json.dumps({"case":"listener_delete_failure","raised":type(exc).__name__,
                              "sqlstate":getattr(exc,"sqlstate",None)}), flush=True)
        else:
            raise AssertionError("injected delete failure was not raised")
    finally:
        async with tx() as connection:
            await connection.execute("DROP TRIGGER IF EXISTS reject_snapshot_delete ON endpoint_listeners")
            await connection.execute("DROP FUNCTION IF EXISTS reject_snapshot_delete()")
    rollback_after = await observe("listener-rollback-after")
    assert (rollback_before["listeners"],rollback_before["local_socket"],rollback_before["network"],rollback_before["stdio_process"],
            rollback_before["listener_fingerprints"],rollback_before["detail"],rollback_before["status_jsonb"]) == (
        rollback_after["listeners"],rollback_after["local_socket"],rollback_after["network"],rollback_after["stdio_process"],
        rollback_after["listener_fingerprints"],rollback_after["detail"],rollback_after["status_jsonb"]), (
        rollback_before,rollback_after)
    assert rollback_after["listeners"] == 2, rollback_after
    return {"inventory_incomplete_kept_old": True, "legacy_unmarked_empty_preserved": True,
            "explicit_complete_cleared": True,
            "source_mismatch_no_mutation": True, "stdio_scope_preserved_other_sources": True,
            "partial_process_preserved_last_success": True, "stale_preserved_and_count_conservative": True,
            "listener_delete_failure_rolled_back": True}


async def main():
    await pool.open(wait=True)
    result = None
    try:
        await create_schema()
        result = await run_cases()
        print(json.dumps({"result":"PASS","cases":result,"schema":SCHEMA}), flush=True)
    finally:
        if schema_created:
            async with pool.connection() as connection:
                async with connection.transaction():
                    await connection.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(SCHEMA)))
            print(json.dumps({"observation":"schema-dropped","schema":SCHEMA}), flush=True)
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
