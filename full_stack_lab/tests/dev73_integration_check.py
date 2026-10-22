"""DEV-73 merge into main: what must not change for a server that does not run on a device.

A remote server (everything before DEV-73) must neither write a local stop row nor wait for a local
stop receipt when it is stopped, suspended or resumed, and a token revocation with no local job must
find nothing to wait for. Standard library only; database doubles stand in for PostgreSQL.
"""
import ast
import asyncio
import sys
import types
import unittest
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

APP = Path(__file__).resolve().parents[1] / "gateway/app"

# A package the extracted functions can run their `from . import x` lines against.
PACKAGE = types.ModuleType("dev73_integration_pkg")
PACKAGE.__path__ = []
sys.modules[PACKAGE.__name__] = PACKAGE


def extract(file, names, namespace):
    tree = ast.parse((APP / file).read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
    assert {n.name for n in nodes} == set(names), names
    namespace.update(__name__=PACKAGE.__name__ + "." + file[:-3], __package__=PACKAGE.__name__)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(APP / file), "exec"), namespace)
    return SimpleNamespace(**{n.name: namespace[n.name] for n in nodes})


def register(**modules):
    for name, module in modules.items():
        sys.modules[f"{PACKAGE.__name__}.{name}"] = module
        setattr(PACKAGE, name, module)


class Database:
    """Records every statement; `running` is whether a started local job is still unstopped."""
    def __init__(self, running=False):
        self.statements, self.running = [], running

    async def run(self, query, params=None):
        self.statements.append(" ".join(query.split()))
        result = {"status": "READY"} if "SELECT status FROM mcp_servers" in query else {"id": 1}
        return SimpleNamespace(fetchone=AsyncMock(return_value=result))

    async def execute(self, query, params=None):
        await self.run(query, params)

    async def fetch_one(self, query, params=None):
        self.statements.append(" ".join(query.split()))
        if "FROM mcp_servers s WHERE s.id=" in query:
            return {"status": "READY", "suspended": False}
        return {"id": "job"} if self.running else None

    @asynccontextmanager
    async def transaction(self):
        yield SimpleNamespace(execute=self.run)

    def touched(self, text):
        return [s for s in self.statements if text in s]


def local_runner(servers, db, run_seconds=0):
    """The product's quiesce/resume/is_local, reading a registry double."""
    register(registry=SimpleNamespace(server=lambda server_id: servers.get(server_id)))
    return extract("local_jobs.py", {"is_local", "quiesce", "resume", "prepare_token_revocation"},
                   {"asyncio": asyncio, "db": db, "RUN_SECONDS": run_seconds - 5})


REMOTE = {"github": {"endpoint": "https://github.example/mcp"}}
LOCAL = {"files": {"endpoint": "local:files", "local": {"manifest_sha256": "a" * 64}}}


class RemoteServerKeepsItsBehavior(unittest.IsolatedAsyncioTestCase):
    async def test_stopping_or_resuming_a_remote_server_touches_no_local_state(self):
        db = Database(running=True)  # even a stray running row must not be waited on
        runner = local_runner({**REMOTE, **LOCAL}, db)
        await runner.quiesce(server_id="github")
        await runner.quiesce(server_id="github", user_token="alice")
        await runner.resume(server_id="github")
        await runner.resume(server_id="github", user_token="alice")
        self.assertEqual(db.statements, [])

    async def test_unknown_server_is_treated_as_remote(self):
        db = Database(running=True)
        runner = local_runner({}, db)
        await runner.quiesce(server_id="gone")
        self.assertEqual(db.statements, [])

    async def test_a_local_server_still_closes_admission_and_waits_for_the_stop(self):
        db = Database(running=False)
        runner = local_runner(LOCAL, db)
        await runner.quiesce(server_id="files")
        self.assertEqual(len(db.touched("INSERT INTO local_run_stops")), 1)
        self.assertEqual(len(db.touched("UPDATE local_jobs")), 1)
        await runner.resume(server_id="files")
        self.assertEqual(len(db.touched("DELETE FROM local_run_stops")), 1)

        stuck = Database(running=True)
        with self.assertRaises(RuntimeError):
            await local_runner(LOCAL, stuck).quiesce(server_id="files")

    async def test_user_and_device_scopes_still_apply_without_a_server(self):
        db = Database(running=False)
        runner = local_runner(REMOTE, db)
        await runner.quiesce(user_token="alice")
        await runner.quiesce(device_id="device")
        self.assertEqual(len(db.touched("INSERT INTO local_run_stops")), 2)
        with self.assertRaises(ValueError):
            await runner.quiesce()

    async def test_token_revocation_without_local_jobs_finds_nothing_to_wait_for(self):
        db = Database(running=False)
        locks = []
        connection = SimpleNamespace(execute=AsyncMock(side_effect=lambda q, p=None: locks.append(p[0])))
        runner = local_runner(REMOTE, db)
        await runner.prepare_token_revocation(connection, [{"jti": "b"}, {"jti": "a"}, {"jti": "a"}])
        self.assertEqual(locks, ["local:token:a", "local:token:b"])  # one lock per token, in a fixed order
        self.assertEqual([s.split()[0] for s in db.statements], ["UPDATE", "SELECT"])
        self.assertTrue(all("local_jobs" in s for s in db.statements))
        db.statements.clear()
        await runner.prepare_token_revocation(connection, [])
        self.assertEqual(db.statements, [])

    async def test_automatic_suspension_of_a_remote_server_completes_with_its_original_statements(self):
        ops_db = Database()
        local_db = Database(running=True)
        runner = local_runner({**REMOTE, **LOCAL}, local_db)
        ops = extract("ops_response.py", {"suspend"}, {
            "db": ops_db, "local_jobs": runner, "Jsonb": lambda value: value})
        self.assertTrue(await ops.suspend("github", "drift", "자동 중지", {"findings": []}))
        self.assertEqual(local_db.statements, [])
        self.assertEqual(ops_db.touched("local_"), [])
        self.assertTrue(ops_db.touched("UPDATE mcp_servers SET status='DISABLED'"))

    async def test_resuming_a_remote_server_does_not_delete_a_local_stop_row(self):
        for servers, expected in ((REMOTE, 0), (LOCAL, 1)):
            with self.subTest(servers=list(servers)):
                ops_db = Database()
                runner = local_runner(servers, Database())

                @contextmanager
                def locked(_):
                    yield

                register(disposal=SimpleNamespace(locked=locked, DIRECTORY="", read=lambda: []))
                ops = extract("ops_response.py", {"resume"}, {
                    "db": ops_db, "local_jobs": runner, "review": SimpleNamespace(record_event=AsyncMock())})
                server_id = next(iter(servers))

                async def run(query, params=None):
                    ops_db.statements.append(" ".join(query.split()))
                    row = {"lifecycle": "OPERATING", "id": 1}
                    return SimpleNamespace(fetchone=AsyncMock(return_value=row))
                ops_db.transaction = lambda: _transaction(run)
                await ops.resume(server_id, "admin", "확인")
                self.assertEqual(len(ops_db.touched("local_run_stops")), expected)


@asynccontextmanager
async def _transaction(run):
    yield SimpleNamespace(execute=run)


if __name__ == "__main__":
    unittest.main()
