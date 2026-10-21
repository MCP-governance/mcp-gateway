"""Local DEV-78 checks for approved contract history, fail-closed rollback, and transition ordering."""
import hashlib
import json
import datetime
import sys
import types
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "runtime"), str(ROOT / "gateway" / "app")]
# The workstation has Python 3.10; the worker image uses 3.12. These checks do not parse recipes.
try:
    import tomllib  # noqa: F401
except ModuleNotFoundError:
    sys.modules["tomllib"] = types.SimpleNamespace(loads=lambda _text: {})
if not hasattr(datetime, "UTC"):
    from datetime import timezone
    datetime.UTC = timezone.utc
# Database and image scanning are outside this local state-machine check.
if "psycopg" not in sys.modules:
    psycopg = types.ModuleType("psycopg")
    psycopg.Error = Exception
    psycopg.connect = lambda *_args, **_kwargs: None
    rows = types.ModuleType("psycopg.rows")
    rows.dict_row = object()
    pgtypes = types.ModuleType("psycopg.types")
    json_types = types.ModuleType("psycopg.types.json")
    class Jsonb:
        def __init__(self, obj, **_kwargs):
            self.obj = obj
    json_types.Jsonb = Jsonb
    sys.modules.update({"psycopg": psycopg, "psycopg.rows": rows,
                        "psycopg.types": pgtypes, "psycopg.types.json": json_types})
if "image_scan" not in sys.modules:
    sys.modules["image_scan"] = types.SimpleNamespace(rescan=lambda *_args: None)
import worker  # noqa: E402


CONTRACT = {
    "server_id": "markitdown",
    "tools": {"convert": {
        "approved_description_hash": "a" * 64,
        "approved_schema_hash": "b" * 64,
        "approved_output_schema_hash": "c" * 64,
        "approved_server_version": "1.0",
    }},
}
CONTRACT["sha256"] = hashlib.sha256(
    json.dumps(CONTRACT["tools"], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
).hexdigest()


class Cursor:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class ContractConnection:
    def __init__(self):
        self.writes = []
        self.values = {"convert": dict(CONTRACT["tools"]["convert"])}

    def execute(self, query, params=()):
        if query.startswith("SELECT name FROM mcp_tools"):
            return Cursor([{"name": name} for name in self.values])
        if query.startswith("UPDATE mcp_tools"):
            self.writes.append((query, params))
            description, schema, output, version, server, name = params
            self.values[name] = {"approved_description_hash": description, "approved_schema_hash": schema,
                                 "approved_output_schema_hash": output, "approved_server_version": version}
        return Cursor()


class FakeApprovalConnection:
    def __init__(self, server=None, target=True, revoked=False):
        self.server = server or {"status": "APPROVED", "intake_kind": "repository", "commit_sha": "d" * 40,
                                 "repository_url": "repo", "lifecycle": "OPERATING", "server_status": "READY"}
        self.target = target
        self.revoked = revoked

    def execute(self, query, params=()):
        if "FROM mcp_intake_requests" in query:
            return Cursor([self.server] if self.server else [])
        if "FROM mcp_runtimes r WHERE r.intake_id" in query:
            return Cursor([{"image_id": "sha256:old", "source_commit": "c" * 40,
                            "recipe_id": "r", "recipe_sha256": "x", "status": "STOPPED",
                            "contract": CONTRACT}] if self.target else [])
        if "runtime-revoked" in query:
            return Cursor([{"1": 1}] if self.revoked else [])
        return Cursor()


class RollbackTests(unittest.TestCase):
    def test_restore_uses_the_exact_prior_d149_hashes_including_output_hash(self):
        connection = ContractConnection()
        self.assertTrue(worker.restore_contract(connection, CONTRACT))
        self.assertEqual(connection.values["convert"], CONTRACT["tools"]["convert"])
        self.assertEqual(connection.writes[0][1][2], "c" * 64)

    def test_modified_snapshot_or_changed_tool_set_is_refused(self):
        changed = {**CONTRACT, "tools": {"convert": {**CONTRACT["tools"]["convert"],
                                                       "approved_output_schema_hash": "e" * 64}}}
        connection = ContractConnection()
        self.assertFalse(worker.restore_contract(connection, changed))
        self.assertEqual(connection.writes, [])
        removed = {**CONTRACT, "tools": {}}
        self.assertFalse(worker.restore_contract(connection, removed))

    def test_unapproved_generation_and_revoked_generation_are_refused(self):
        job = {"intake_id": uuid.uuid4(), "source_commit": "c" * 40, "rollback_target_generation": 1,
               "image_id": "sha256:old", "recipe_id": "r", "recipe_sha256": "x", "rollback_contract": CONTRACT}
        recipes = {"repo": {"id": "r", "sha256": "x"}}
        self.assertIn("승인 판본", worker.approval_problem(FakeApprovalConnection(target=False), job, recipes))
        self.assertIn("중지된 판본", worker.approval_problem(FakeApprovalConnection(revoked=True), job, recipes))

    def test_termination_and_supply_chain_stop_win_over_rollback(self):
        job = {"intake_id": uuid.uuid4(), "source_commit": "c" * 40, "rollback_target_generation": 1,
               "image_id": "sha256:old", "recipe_id": "r", "recipe_sha256": "x", "rollback_contract": CONTRACT}
        recipes = {"repo": {"id": "r", "sha256": "x"}}
        for change in ({"lifecycle": "TERMINATING"}, {"server_status": "BLOCKED_SUPPLY_CHAIN"}):
            problem = worker.approval_problem(FakeApprovalConnection(server={
                "status": "APPROVED", "intake_kind": "repository", "commit_sha": "d" * 40,
                "repository_url": "repo", "lifecycle": "OPERATING", "server_status": "READY", **change}), job, recipes)
            self.assertTrue(problem)

    def test_active_runtime_history_appends_a_contract_snapshot(self):
        class EventConnection:
            def __init__(self):
                self.params = None

            def execute(self, query, params):
                if "SELECT registered_server_id" in query:
                    return Cursor([{"registered_server_id": "markitdown"}])
                if "FROM mcp_tools" in query:
                    return Cursor([{"name": name, **contract} for name, contract in CONTRACT["tools"].items()])
                if "FROM approval_events" in query:
                    return Cursor([{"actor": "admin-1", "created_at": "2026-10-21T01:00:00Z"}])
                if "INSERT INTO approval_events" in query:
                    self.params = params
                return Cursor()

        connection = EventConnection()
        worker.event(connection, {"id": uuid.uuid4(), "intake_id": "intake-1", "generation": 2}, "runtime-active")
        recorded = connection.params[-1].obj["contract"]
        self.assertEqual(recorded["sha256"], CONTRACT["sha256"])
        self.assertEqual(recorded["tools"], CONTRACT["tools"])
        self.assertEqual(recorded["approved_by"], "admin-1")
        self.assertIn("approval_events_append_only", (ROOT / "gateway/app/v2_tables.sql").read_text(encoding="utf-8"))

    def test_reconcile_stops_before_it_queues_the_prior_image_and_contract(self):
        source = (ROOT / "runtime/worker.py").read_text(encoding="utf-8")
        stopped = source.index("SET status='STOPPED'", source.index("def reconcile"))
        queued = source.index("INSERT INTO mcp_runtimes", stopped)
        self.assertLess(stopped, queued)
        schema = (ROOT / "gateway/app/v2_tables.sql").read_text(encoding="utf-8")
        self.assertIn("mcp_runtimes_one_live", schema)
        self.assertIn("status NOT IN ('STOPPED', 'FAILED')", schema)

    def test_calls_still_require_restored_input_and_output_contracts(self):
        dispatch = (ROOT / "gateway/app/dispatch.py").read_text(encoding="utf-8")
        self.assertIn("approved_schema_hash=t.observed_schema_hash", dispatch)
        self.assertIn("approved_output_schema_hash=t.observed_output_schema_hash", dispatch)


if __name__ == "__main__":
    unittest.main()
