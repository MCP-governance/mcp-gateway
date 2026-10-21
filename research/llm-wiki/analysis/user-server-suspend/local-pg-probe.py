"""DEV-79 local one-off: the shipped SQL of user_suspend / core principal query / dispatch.record on a real PostgreSQL.

Not part of the product or its test suite: needs `pip install pgserver "psycopg[binary]"` in a scratch venv and a
scratch data directory (argv[1]). pgcrypto is unavailable in that PostgreSQL build, so CREATE EXTENSION lines are
stripped from the schema files; nothing here uses it. The product code is loaded by AST from the repository.
Run: python local-pg-probe.py <scratch-dir>   (PYTHONIOENCODING=utf-8)
"""
import pgserver, pathlib, sys, asyncio, re, ast, json, psycopg
from psycopg.rows import dict_row
from contextlib import asynccontextmanager
from types import SimpleNamespace as NS
ROOT = pathlib.Path(__file__).resolve().parents[4] / "full_stack_lab"
APP = ROOT/"gateway/app"
srv = pgserver.get_server(pathlib.Path(sys.argv[1]), cleanup_mode='stop')  # throwaway server in a scratch directory
uri = srv.get_uri()
print(uri)

def apply_all():
    import subprocess
    with psycopg.connect(uri, autocommit=True) as c:
        c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        for f in [ROOT/"db/init.sql", APP/"agent_tables.sql", APP/"lifecycle_tables.sql", APP/"v2_tables.sql", APP/"oidc_tables.sql", APP/"ops_tables.sql", APP/"siem_tables.sql", APP/"ops_tables.sql"]:
            try:
                c.execute(re.sub(r"CREATE EXTENSION[^;]*;", "", f.read_text(encoding="utf-8")))
                print("applied", f.name)
            except Exception as e:
                print("FAILED", f.name, type(e).__name__, str(e)[:300])
apply_all()

import uuid, hashlib, os
from datetime import datetime, timezone
from psycopg.types.json import Jsonb


def production(path, names, ns):
    tree = ast.parse((APP/path).read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if getattr(n, "name", None) in names or
             isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in n.targets)]
    assert len(nodes) == len(names), (names, [getattr(n, 'name', None) for n in nodes])
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(APP/path), "exec"), ns)
    return NS(**ns)


class DB:
    async def conn(self):
        return await psycopg.AsyncConnection.connect(uri, row_factory=dict_row, autocommit=False)

    @asynccontextmanager
    async def transaction(self):
        c = await self.conn()
        try:
            yield c
            await c.commit()
        except BaseException:
            await c.rollback()
            raise
        finally:
            await c.close()

    async def fetch_one(self, q, p=()):
        async with self.transaction() as c:
            return await (await c.execute(q, p)).fetchone()

    async def fetch_all(self, q, p=()):
        async with self.transaction() as c:
            return await (await c.execute(q, p)).fetchall()

    async def execute(self, q, p=()):
        async with self.transaction() as c:
            return (await c.execute(q, p)).rowcount


db = DB()
review = production("review.py", {"record_event"}, {"db": db, "Jsonb": Jsonb, "json": json, "Any": object})
mod = production("user_suspend.py", {"TARGET", "suspend", "resume", "listing"}, {"db": db, "review": review})
consts = production("dispatch.py", {"UNSETTLED", "CATALOG_OK", "_INSERT", "REPLAY", "IDEMPOTENCY_TTL_SECONDS", "_Refused", "record"},
    {"db": db, "consent": NS(for_dispatch=None), "high_impact": NS(bound=None),
     "canonical_hash": lambda v: hashlib.sha256(json.dumps(v, sort_keys=True).encode()).hexdigest(),
     "Jsonb": Jsonb, "os": os})

tree = ast.parse((APP/"core.py").read_text(encoding="utf-8"))
PQ = None
for n in ast.walk(tree):
    if isinstance(n, ast.AsyncFunctionDef) and n.name == "execute_call":
        for c in ast.walk(n):
            if isinstance(c, ast.Constant) and isinstance(c.value, str) and "server_suspended" in c.value:
                PQ = c.value
assert PQ


async def main():
    ok = []

    def check(name, cond):
        print(("PASS " if cond else "FAIL ") + name)
        ok.append(bool(cond))
    for t in ("emp-a", "emp-b", "admin"):
        await db.execute("INSERT INTO principals(token,display_name,role) VALUES (%s,%s,%s)", (t, t, "admin" if t == "admin" else "employee"))
    for sid in ("gitea", "filesystem"):
        await db.execute("""INSERT INTO mcp_servers(id,display_name,transport,source_url,source_ref,supplier,status,status_reason)
                            VALUES (%s,%s,'http','u','r','s','READY','ok')""", (sid, sid))
        await db.execute("""INSERT INTO mcp_tools(server_id,name,action,enabled,approved_schema_hash,observed_schema_hash,
                            approved_description_hash,observed_description_hash,scope_review) VALUES (%s,'read','r',true,'h','h','d','d','{}')""", (sid,))
        await db.execute("INSERT INTO catalog_snapshots(server_id,catalog_hash,tool_count,exact_match) VALUES (%s,'c',1,true)", (sid,))

    async def reserve(user, server):
        rid = str(uuid.uuid4())
        await db.execute("""INSERT INTO call_reservations(request_id,user_token,server_id,tool_name,fingerprint,data_class,expires_at)
                            VALUES (%s,%s,%s,'read',%s,'public',now()+interval '2 minutes')""", (rid, user, server, rid))
        return rid

    async def principal(user, server):
        return await db.fetch_one(PQ, (server, user))

    check("identity query: nobody suspended at start", (await principal("emp-a", "gitea"))["server_suspended"] is False)
    check("identity query: unknown token -> no row", await principal("ghost", "gitea") is None)
    r_unsent = await reserve("emp-a", "gitea")
    r_sent = await reserve("emp-a", "gitea")
    await db.execute("INSERT INTO dispatch_intents(request_id,user_token,server_id,tool_name,action,fingerprint) VALUES (%s,'emp-a','gitea','read','r','x')", (r_sent,))
    first = await mod.suspend("emp-a", "gitea", "admin", "policy-violation-check")
    check("suspend counts in-flight (unsent=1, sent=1)", (first["unsent"], first["sent"]) == (1, 1))
    check("identity query: pair suspended", (await principal("emp-a", "gitea"))["server_suspended"] is True)
    check("identity query: other server not suspended", (await principal("emp-a", "filesystem"))["server_suspended"] is False)
    check("identity query: other employee not suspended", (await principal("emp-b", "gitea"))["server_suspended"] is False)
    try:
        await mod.suspend("emp-a", "gitea", "admin2", "again")
        check("duplicate suspend refused", False)
    except ValueError:
        check("duplicate suspend refused (ValueError)", True)
    try:
        await mod.suspend("ghost", "gitea", "admin", "reason!")
        check("unknown user refused", False)
    except LookupError:
        check("unknown user refused (LookupError)", True)
    try:
        await mod.suspend("emp-a", "nowhere", "admin", "reason!")
        check("unknown server refused", False)
    except LookupError:
        check("unknown server refused (LookupError)", True)
    ev = await db.fetch_all("SELECT * FROM approval_events WHERE target_kind=%s ORDER BY id", (mod.TARGET,))
    check("exactly one suspend event with actor/scope/time",
          len(ev) == 1 and ev[0]["kind"] == "user-server-suspend" and ev[0]["actor"] == "admin"
          and ev[0]["scope"]["server"] == "gitea" and ev[0]["scope"]["user"] == "emp-a" and ev[0]["created_at"] is not None)
    check("record(): unsent call of suspended pair -> user-suspended", await consts.record(r_unsent, "r") == "user-suspended")
    r_other = await reserve("emp-a", "filesystem")
    check("record(): same employee, other server -> intent written", await consts.record(r_other, "r") is None)
    r_b = await reserve("emp-b", "gitea")
    check("record(): other employee, same server -> intent written", await consts.record(r_b, "r") is None)
    rows = await db.fetch_all("SELECT request_id FROM dispatch_intents WHERE request_id=%s", (r_unsent,))
    check("no intent row for the refused call", rows == [])
    lst = await mod.listing()
    check("listing shows active row with names", len(lst) == 1 and lst[0]["resumed_at"] is None
          and lst[0]["server_name"] == "gitea" and lst[0]["suspended_by"] == "admin")
    done = await mod.resume(first["id"], "admin", "resume-note")
    check("resume returns the row", done["server_id"] == "gitea")
    try:
        await mod.resume(first["id"], "admin", "again!!")
        check("second resume refused", False)
    except ValueError:
        check("second resume refused (ValueError)", True)
    check("identity query after resume: not suspended", (await principal("emp-a", "gitea"))["server_suspended"] is False)
    r_after = await reserve("emp-a", "gitea")
    check("record() after resume -> intent written", await consts.record(r_after, "r") is None)
    ev = await db.fetch_all("SELECT kind,outcome,actor FROM approval_events WHERE target_kind=%s ORDER BY id", (mod.TARGET,))
    check("events: suspend then resume, nothing else", [(e["kind"], e["outcome"]) for e in ev] == [("user-server-suspend", "held"), ("user-server-resume", "approved")])
    try:
        await db.execute("UPDATE approval_events SET reason='x' WHERE target_kind=%s", (mod.TARGET,))
        check("events immutable", False)
    except Exception as e:
        check("events immutable (trigger) -> %s" % type(e).__name__, True)
    again = await mod.suspend("emp-a", "gitea", "admin", "repeat-block")
    check("re-suspend after resume makes a new row", again["id"] != first["id"])
    await mod.resume(again["id"], "admin", "resume-note-2")
    holder = await db.conn()
    await holder.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("emp-b",))
    task = asyncio.create_task(mod.suspend("emp-b", "filesystem", "admin", "concurrency-check"))
    await asyncio.sleep(1.0)
    waiting = await db.fetch_one("SELECT count(*) AS n FROM pg_stat_activity WHERE wait_event_type='Lock' AND query ILIKE '%%pg_advisory_xact_lock%%'")
    check("suspend is blocked while the per-employee lock is held (waiting=%s)" % waiting["n"], not task.done() and waiting["n"] >= 1)
    await holder.commit()
    await holder.close()
    res = await asyncio.wait_for(task, 5)
    check("suspend completes after the holder commits", res["server_id"] == "filesystem")
    print("RESULT", sum(ok), "/", len(ok))
    return all(ok)

import selectors
sys.exit(0 if asyncio.run(main(), loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector())) else 1)
