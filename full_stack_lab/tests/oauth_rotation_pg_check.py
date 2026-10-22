"""Native PostgreSQL refresh-family checks in a fresh, disposable schema.

Run ONLY on the solution appliance, from full_stack_lab, after deploying idp.py:
    docker compose exec -T gateway python - < tests/oauth_rotation_pg_check.py
Or pass this file on stdin to `docker exec -i <gateway-container> python -`.

Uses the image's DATABASE_URL without printing it. Requires schema-create permission
and DB_POOL_MAX >= 3. No production rows/accounts are read or written. Only token
signing is mocked; transaction/rotation/revocation SQL and PostgreSQL locks are real.
The unique schema is created without reuse and dropped only if this process created
it. This validates DB concurrency/rollback, not real JWTs or a managed MCP harness.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, ExitStack
from datetime import UTC, datetime, timedelta
import json
import logging
import os
from pathlib import Path
import re
import secrets
import sys
from unittest.mock import patch
import uuid

import psycopg
from psycopg import sql
from starlette.requests import Request

os.environ.setdefault("OTEL_SDK_DISABLED", "true")
logging.getLogger("psycopg.pool").disabled = True
if __file__ != "<stdin>":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gateway"))
from app import db, idp


class NativeRotationCheck:
    def __init__(self):
        self.schema = "oauth_rotation_check_" + uuid.uuid4().hex
        assert re.fullmatch(r"oauth_rotation_check_[a-f0-9]{32}", self.schema)
        self.original_transaction = db.transaction
        self.original_issue = idp._issue
        self.request = Request({"type": "http", "client": ("127.0.0.1", 1), "headers": []})
        self.created = False
        self.removed = False
        self.case = "create_test_schema"
        self.passed = 0

    @asynccontextmanager
    async def transaction(self):
        async with self.original_transaction() as connection:
            # No public fallback: a missing fixture table must fail, never touch production.
            await connection.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(self.schema)))
            await connection.execute("SELECT set_config('application_name', %s, true)", (self.schema,))
            yield connection

    async def fetch_one(self, query, params):
        async with self.transaction() as connection:
            return await (await connection.execute(query, params)).fetchone()

    async def execute(self, query, params=None):
        async with self.transaction() as connection:
            return await connection.execute(query, params)

    async def create(self):
        async with self.original_transaction() as connection:
            await connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.created = True
        async with self.transaction() as connection:
            await connection.execute("""
                CREATE TABLE principals (
                    token text PRIMARY KEY, user_id text UNIQUE NOT NULL,
                    status text NOT NULL, managed_required boolean NOT NULL
                );
                CREATE TABLE oauth_issued_tokens (
                    jti text PRIMARY KEY, user_id text NOT NULL, client_id text NOT NULL,
                    family_id uuid NOT NULL, issued_at timestamptz NOT NULL DEFAULT now(),
                    expires_at timestamptz NOT NULL
                );
                CREATE TABLE oauth_refresh_tokens (
                    id uuid PRIMARY KEY, family_id uuid NOT NULL, user_id text NOT NULL,
                    client_id text NOT NULL, token_sha256 text UNIQUE NOT NULL,
                    issued_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL,
                    rotated_at timestamptz, revoked_at timestamptz
                );
                CREATE TABLE agent_revoked_tokens (jti uuid PRIMARY KEY, expires_at timestamptz NOT NULL);
                -- Family revocation first stops local jobs bound to the revoked access tokens
                -- (local_jobs.prepare_token_revocation); only the columns it reads or writes.
                CREATE TABLE local_jobs (
                    id uuid PRIMARY KEY, token_jti uuid, state text NOT NULL DEFAULT 'queued',
                    stop_requested boolean NOT NULL DEFAULT false, started_at timestamptz,
                    stopped_at timestamptz, finished_at timestamptz
                );
                INSERT INTO principals VALUES ('rotation_fixture', 'rotation_fixture', 'active', false);
            """)

    async def seed(self):
        family = uuid.uuid4()
        raw_refresh = "rt_test_" + secrets.token_urlsafe(24)
        async with self.transaction() as connection:
            await connection.execute(
                """INSERT INTO oauth_refresh_tokens(id,family_id,user_id,client_id,token_sha256,expires_at)
                   VALUES (%s,%s,'rotation_fixture','rotation_fixture',%s,%s)""",
                (uuid.uuid4(), family, idp._sha(raw_refresh), datetime.now(UTC) + timedelta(hours=1)))
            await connection.execute(
                """INSERT INTO oauth_issued_tokens(jti,user_id,client_id,family_id,expires_at)
                   VALUES (%s,'rotation_fixture','rotation_fixture',%s,%s)""",
                (str(uuid.uuid4()), family, datetime.now(UTC) + timedelta(hours=1)))
        return family, raw_refresh

    def signing_stub(self, user, **kwargs):
        identity = str(uuid.uuid4())
        return "unsigned-test-access-" + identity, {"jti": identity, "exp": datetime.now(UTC) + timedelta(minutes=10)}

    async def refresh(self, raw_refresh):
        return await idp.token(self.request, grant_type="refresh_token", client_id="rotation_fixture",
                               username=None, password=None, refresh_token=raw_refresh)

    async def assert_family_revoked(self, family):
        refresh = await self.fetch_one(
            "SELECT count(*) AS active FROM oauth_refresh_tokens WHERE family_id=%s AND revoked_at IS NULL", (family,))
        access = await self.fetch_one(
            """SELECT count(*) AS active FROM oauth_issued_tokens i
               LEFT JOIN agent_revoked_tokens r ON r.jti=i.jti::uuid
               WHERE i.family_id=%s AND i.expires_at>now() AND r.jti IS NULL""", (family,))
        assert refresh["active"] == 0, "Family has an unrevoked refresh descendant"
        assert access["active"] == 0, "Family has an unrevoked access descendant"

    async def concurrent_refresh(self):
        family, raw_refresh = await self.seed()
        replies = await asyncio.wait_for(asyncio.gather(self.refresh(raw_refresh), self.refresh(raw_refresh)), 5)
        assert sum(isinstance(reply, dict) for reply in replies) == 1, "Concurrent refresh must issue exactly once"
        await self.assert_family_revoked(family)

    async def wait_for_lock_waiter(self):
        async with asyncio.timeout(3):
            while True:
                row = await self.fetch_one(
                    """SELECT EXISTS(SELECT 1 FROM pg_stat_activity
                       WHERE application_name=%s AND wait_event_type='Lock') AS waiting""", (self.schema,))
                if row["waiting"]:
                    return
                await asyncio.sleep(0.01)

    async def revoke_during_issuance(self):
        family, raw_refresh = await self.seed()
        entered, release = asyncio.Event(), asyncio.Event()

        async def gated_issue(*args, **kwargs):
            entered.set()
            await release.wait()
            return await self.original_issue(*args, **kwargs)

        winner = follower = None
        with patch.object(idp, "_issue", gated_issue):
            try:
                winner = asyncio.create_task(self.refresh(raw_refresh))
                await asyncio.wait_for(entered.wait(), 3)
                follower = asyncio.create_task(idp.revoke(raw_refresh, token_type_hint="refresh_token"))
                await self.wait_for_lock_waiter()
                assert not follower.done(), "Revocation must wait for the issuance transaction"
                release.set()
                replies = await asyncio.wait_for(asyncio.gather(winner, follower), 5)
                assert isinstance(replies[0], dict), "Winner should issue before queued revocation"
                assert replies[1].status_code == 200, "Revocation response must remain HTTP 200"
            finally:
                release.set()
                for task in (winner, follower):
                    if task is not None and not task.done():
                        task.cancel()
                await asyncio.gather(*(task for task in (winner, follower) if task is not None), return_exceptions=True)
        await self.assert_family_revoked(family)

    async def rollback_on_insert_failure(self):
        family, raw_refresh = await self.seed()
        constraint = "fail_child_" + uuid.uuid4().hex
        await self.execute(sql.SQL(
            "ALTER TABLE oauth_refresh_tokens ADD CONSTRAINT {} CHECK (family_id <> {} OR token_sha256 = {})"
        ).format(sql.Identifier(constraint), sql.Literal(family), sql.Literal(idp._sha(raw_refresh))))
        try:
            await self.refresh(raw_refresh)
        except psycopg.errors.CheckViolation:
            pass
        else:
            raise AssertionError("Fixture constraint must reject descendant refresh insertion")
        parent = await self.fetch_one("SELECT rotated_at FROM oauth_refresh_tokens WHERE token_sha256=%s", (idp._sha(raw_refresh),))
        count = await self.fetch_one("SELECT count(*) AS count FROM oauth_issued_tokens WHERE family_id=%s", (family,))
        assert parent["rotated_at"] is None, "Failed issuance must roll back parent rotation"
        assert count["count"] == 1, "Failed issuance must roll back partial access insertion"

    async def run(self):
        failed = None
        try:
            if not os.environ.get("DATABASE_URL"):
                raise RuntimeError("Runtime DATABASE_URL must be configured")
            if db.POOL_MAX < 3:
                raise RuntimeError("This concurrency check requires three test DB connections")
            await self.create()
            with ExitStack() as patches:
                patches.enter_context(patch.dict(os.environ, {"AUTH_PROVIDER": "local"}))
                patches.enter_context(patch.object(idp, "issue_token", self.signing_stub))
                patches.enter_context(patch.object(db, "transaction", self.transaction))
                patches.enter_context(patch.object(db, "fetch_one", self.fetch_one))
                patches.enter_context(patch.object(db, "execute", self.execute))
                for name in ("concurrent_refresh", "revoke_during_issuance", "rollback_on_insert_failure"):
                    self.case = name
                    await getattr(self, name)()
                    self.passed += 1
                    print(json.dumps({"case": name, "ok": True}), flush=True)
        except Exception as exc:
            failed = {"case": self.case, "error_type": type(exc).__name__, "sqlstate": getattr(exc, "sqlstate", None)}
            if isinstance(exc, AssertionError):
                failed["detail"] = str(exc)
        finally:
            if self.created:
                try:
                    async with self.original_transaction() as connection:
                        await connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))
                    self.removed = True
                except Exception as exc:
                    failed = {"case": "drop_just_created_schema", "error_type": type(exc).__name__, "sqlstate": getattr(exc, "sqlstate", None)}
            try:
                await db.close()
            except Exception as exc:
                failed = {"case": "close_test_pool", "error_type": type(exc).__name__, "sqlstate": getattr(exc, "sqlstate", None)}
        result = {"ok": failed is None and self.passed == 3 and self.removed,
                  "passed": self.passed, "schema": self.schema, "schema_removed": self.removed}
        if failed:
            result["failure"] = failed
        print(json.dumps(result), flush=True)
        return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(NativeRotationCheck().run()))
