"""Stored-SBOM impact matching and existing server-stop path checks; no database or MCP service."""
import asyncio
import ast
import sys
import types
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "gateway"))
try:
    import psycopg  # noqa: F401
except ModuleNotFoundError:
    psycopg = types.ModuleType("psycopg")
    psycopg.Error = Exception
    rows = types.ModuleType("psycopg.rows")
    rows.dict_row = object()
    errors = types.ModuleType("psycopg.errors")
    errors.UniqueViolation = Exception
    pgtypes = types.ModuleType("psycopg.types")
    json_types = types.ModuleType("psycopg.types.json")
    json_types.Jsonb = lambda value: value
    pool = types.ModuleType("psycopg_pool")
    pool.AsyncConnectionPool = object
    psycopg.__path__ = []
    sys.modules.update({"psycopg": psycopg, "psycopg.rows": rows, "psycopg.errors": errors, "psycopg.types": pgtypes,
                        "psycopg.types.json": json_types, "psycopg_pool": pool})
ops_response = types.ModuleType("app.ops_response")
ops_response.suspend = AsyncMock()
sys.modules["app.ops_response"] = ops_response
from app import sbom_impact  # noqa: E402

ops_tree = ast.parse((ROOT / "gateway" / "app" / "ops_response.py").read_text(encoding="utf-8"))
ops_suspend = next(node for node in ops_tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "suspend")
ops_namespace = {"Jsonb": lambda value: value, "db": None}
exec(compile(ast.Module(body=[ops_suspend], type_ignores=[]), "ops_response.py", "exec"), ops_namespace)
server_suspend = ops_namespace["suspend"]


def row(server, generation, inventory=None, *, status="IMPORTED", scan_status="DONE",
        source_match=True, truncated=False, sbom_id=1):
    return {"server_id": server, "display_name": server.title(), "intake_id": f"intake-{server}",
            "source_ref": f"source:{server}", "runtime_id": f"runtime-{server}-{generation}" if generation else None,
            "generation": generation, "source_match": source_match,
            "scan_status": scan_status if status else None,
            "sbom_id": sbom_id, "sbom_status": status or None,
            "inventory": inventory, "truncated": truncated}


class SbomImpactCheck(unittest.TestCase):
    def test_semver_range_boundaries_and_unknown_versions(self):
        self.assertTrue(sbom_impact._matches("1.4.0", sbom_impact._range(">=1.2.0 <2.0.0")))
        self.assertFalse(sbom_impact._matches("2.0.0", sbom_impact._range(">=1.2.0 <2.0.0")))
        self.assertTrue(sbom_impact._matches("1.0.0-alpha.2", sbom_impact._range("<1.0.0")))
        self.assertIsNone(sbom_impact._matches("2026.10", sbom_impact._range(">=1.0.0")))
        with self.assertRaises(ValueError):
            sbom_impact._range("latest")
        with self.assertRaises(ValueError):
            sbom_impact._range("1.2.3,")
        self.assertIsNone(sbom_impact._matches("１.２.３", sbom_impact._range(">=1.0.0")))
        self.assertIsNone(sbom_impact._matches("1.2.3-alpha..beta", sbom_impact._range(">=1.0.0")))

    def test_admin_routes_and_console_page_are_admin_only(self):
        service = ast.parse((ROOT / "gateway" / "app" / "agent_service.py").read_text(encoding="utf-8"))
        admin_pages = next(node.value for node in service.body if isinstance(node, ast.Assign)
                           and any(isinstance(target, ast.Name) and target.id == "PAGES_BY_ROLE" for target in node.targets))
        admin = next(value for key, value in zip(admin_pages.keys, admin_pages.values)
                     if isinstance(key, ast.Constant) and key.value == "admin")
        self.assertIn("sbom-impact", [item.value for item in admin.elts])
        routes = {decorator.args[0].value: node for node in service.body
                  if isinstance(node, ast.AsyncFunctionDef) for decorator in node.decorator_list
                  if isinstance(decorator, ast.Call) and decorator.args and isinstance(decorator.args[0], ast.Constant)
                  and decorator.args[0].value in ("/api/supply-chain/impact", "/api/supply-chain/impact/stop")}
        self.assertEqual(set(routes), {"/api/supply-chain/impact", "/api/supply-chain/impact/stop"})
        for route in routes.values():
            self.assertTrue(any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                                and node.func.id == "Depends" and node.args
                                and isinstance(node.args[0], ast.Name) and node.args[0].id == "admin_caller"
                                for node in ast.walk(route)))

    def test_query_separates_affected_unaffected_unknown_and_missing(self):
        rows = [
            row("affected", 2, [{"name": "alpha", "version": "1.4.0", "purl": "pkg:npm/alpha@1.4.0"}]),
            row("unaffected", 1, [{"name": "alpha", "version": "2.0.0"}]),
            row("unknown-version", 1, [{"name": "alpha", "version": "rolling"}]),
            row("truncated", 1, [], truncated=True),
            row("truncated-match", 1, [{"name": "alpha", "version": "2.0.0"}], truncated=True),
            row("missing", 1, None, status=None, sbom_id=None),
            row("source-mismatch", 1, [{"name": "alpha", "version": "1.4.0"}], source_match=False),
            row("scan-pending", 1, [{"name": "alpha", "version": "1.4.0"}], scan_status="PENDING"),
            row("no-generation", None, [{"name": "alpha", "version": "1.4.0"}]),
        ]
        with patch.object(sbom_impact.db, "fetch_all", new=AsyncMock(return_value=rows)):
            result = asyncio.run(sbom_impact.impact("alpha", ">=1.0.0 <2.0.0"))
        self.assertEqual(result["counts"], {"affected": 1, "unaffected": 1, "unknown": 3, "no_data": 4})
        by_server = {item["server_id"]: item for item in result["servers"]}
        self.assertEqual(by_server["affected"]["judgement"], "영향 있음")
        self.assertEqual(by_server["affected"]["generation"], 2)
        self.assertEqual(by_server["affected"]["evidence"][0]["sbom_id"], 1)
        self.assertEqual(by_server["truncated"]["judgement"], "판단 불가")
        self.assertEqual(by_server["truncated-match"]["judgement"], "판단 불가")
        self.assertEqual(by_server["missing"]["judgement"], "자료 없음")
        for server in ("source-mismatch", "scan-pending", "no-generation"):
            self.assertEqual(by_server[server]["judgement"], "자료 없음")
            self.assertEqual(by_server[server]["evidence"], [])

    def test_stop_deduplicates_server_and_reports_partial_failure_with_batch(self):
        rows = [
            row("server-a", 1, [{"name": "alpha", "version": "1.0.0"}]),
            row("server-a", 2, [{"name": "alpha", "version": "1.1.0"}]),
            row("server-b", 1, [{"name": "alpha", "version": "1.2.0"}]),
            row("server-c", 1, [{"name": "alpha", "version": "2.0.0"}]),
            row("server-d", 1, [{"name": "alpha", "version": "1.3.0"}]),
        ]

        async def suspend(server_id, source, reason, evidence, batch=None):
            self.assertEqual(source, "supply-chain")
            self.assertEqual(reason, "취약 판본")
            self.assertIsNotNone(batch)
            self.assertEqual(len(evidence["sbom_generations"]), 2 if server_id == "server-a" else 1)
            if server_id == "server-b":
                raise RuntimeError("unavailable")
            if server_id == "server-d":
                return False
            return True

        with patch.object(sbom_impact.db, "fetch_all", new=AsyncMock(return_value=rows)), \
             patch.object(sbom_impact.ops_response, "suspend", new=AsyncMock(side_effect=suspend)) as stop:
            result = asyncio.run(sbom_impact.stop_affected("alpha", "<2.0.0", "admin", "취약 판본"))
        self.assertEqual(result["counts"], {"succeeded": 1, "skipped": 1, "failed": 1})
        self.assertEqual(result["succeeded"], ["server-a"])
        self.assertEqual(result["skipped"], ["server-d"])
        self.assertEqual(result["failed"][0]["server_id"], "server-b")
        self.assertEqual(stop.await_count, 3)

    def test_existing_server_stop_writes_batch_on_append_only_event(self):
        class Cursor:
            def __init__(self, row=None):
                self.row = row

            async def fetchone(self):
                return self.row

        class Connection:
            def __init__(self):
                self.statements = []

            async def execute(self, statement, args=()):
                self.statements.append((statement, args))
                if "FOR UPDATE" in statement:
                    return Cursor({"status": "READY"})
                return Cursor({"id": 51} if "INSERT INTO ops_suspensions" in statement else None)

        connection = Connection()

        @asynccontextmanager
        async def transaction():
            yield connection

        server_suspend.__globals__["db"] = types.SimpleNamespace(
            transaction=transaction, fetch_one=AsyncMock(return_value={"status": "READY", "suspended": False}))
        created = asyncio.run(server_suspend("server-a", "supply-chain", "취약 판본",
                                             {"package": "alpha", "requested_by": "admin"}, batch="batch-1"))
        ledger = next(args for statement, args in connection.statements if "INSERT INTO approval_events" in statement)
        self.assertTrue(created)
        self.assertEqual(ledger[2]["source"], "supply-chain")
        self.assertEqual(ledger[2]["package"], "alpha")
        self.assertEqual(ledger[2]["requested_by"], "admin")
        self.assertEqual(ledger[2]["batch"], "batch-1")
        self.assertTrue(any("SET status='DISABLED'" in s for s, _ in connection.statements))
        self.assertTrue(any("UPDATE mcp_runtimes SET status='STOPPING'" in s for s, _ in connection.statements))

    def test_already_stopped_server_is_skipped_without_changing_its_reason_or_runtime(self):
        for status, suspended in (("DISABLED", True), ("DISABLED", False),
                                  ("BLOCKED_SUPPLY_CHAIN", False), ("READY", True)):
            with self.subTest(status=status, suspended=suspended):
                db = types.SimpleNamespace(
                    fetch_one=AsyncMock(return_value={"status": status, "suspended": suspended}),
                    transaction=AsyncMock(side_effect=AssertionError("already stopped")))
                server_suspend.__globals__["db"] = db
                self.assertFalse(asyncio.run(server_suspend(
                    "server-a", "supply-chain", "새 사유", {"package": "alpha"})))
                db.transaction.assert_not_called()

    def test_concurrent_stop_loses_insert_without_overwriting_existing_state(self):
        class Cursor:
            def __init__(self, value):
                self.value = value

            async def fetchone(self):
                return self.value

        class Connection:
            def __init__(self):
                self.statements = []

            async def execute(self, statement, args=()):
                self.statements.append(statement)
                if "FOR UPDATE" in statement:
                    return Cursor({"status": "READY"})
                if "INSERT INTO ops_suspensions" in statement:
                    return Cursor(None)
                raise AssertionError("a skipped stop changed state")

        connection = Connection()

        @asynccontextmanager
        async def transaction():
            yield connection

        server_suspend.__globals__["db"] = types.SimpleNamespace(
            transaction=transaction, fetch_one=AsyncMock(return_value={"status": "READY", "suspended": False}))
        self.assertFalse(asyncio.run(server_suspend("server-a", "supply-chain", "새 사유", {})))
        self.assertEqual(len(connection.statements), 2)

    def test_server_disabled_during_stop_is_skipped_after_row_lock(self):
        class Cursor:
            async def fetchone(self):
                return {"status": "DISABLED"}

        statements = []

        class Connection:
            async def execute(self, statement, args=()):
                statements.append(statement)
                return Cursor()

        @asynccontextmanager
        async def transaction():
            yield Connection()

        server_suspend.__globals__["db"] = types.SimpleNamespace(
            transaction=transaction, fetch_one=AsyncMock(return_value={"status": "READY", "suspended": False}))
        self.assertFalse(asyncio.run(server_suspend("server-a", "supply-chain", "새 사유", {})))
        self.assertEqual(len(statements), 1)


if __name__ == "__main__":
    unittest.main()
