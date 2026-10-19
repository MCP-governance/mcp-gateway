"""In-process catalog rollback checks with a stateful database/discovery substitute."""
from __future__ import annotations

from contextlib import ExitStack, asynccontextmanager
from copy import deepcopy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("OTEL_SDK_DISABLED", "true")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gateway"))
from app import core

TOOL_A = {"name": "read_record", "description": "Read a selected record.",
          "input_schema": {"type": "object", "properties": {"id": {"type": "string"}}},
          "annotations": {"readOnlyHint": True}}
TOOL_B = {"name": "read_record", "description": "Read a selected numeric record.",
          "input_schema": {"type": "object", "properties": {"id": {"type": "integer"}}},
          "annotations": {"readOnlyHint": False}}


class CatalogDB:
    def __init__(self):
        self.servers, self.tools, self.snapshots = {}, {}, []
        self.observation_writes = []

    def register(self, server_id):
        self.servers[server_id] = {"id": server_id, "status": "READY", "status_reason": "approved", "endpoint": "http://unit.invalid",
                                   "lifecycle": "OPERATING"}
        self.tools[server_id] = {"name": TOOL_A["name"], "enabled": True,
                                 "description": TOOL_A["description"], "input_schema": deepcopy(TOOL_A["input_schema"]),
                                 "annotations": deepcopy(TOOL_A["annotations"]),
                                 "approved_description_hash": core.canonical_hash(TOOL_A["description"]),
                                 "approved_schema_hash": core.canonical_hash(TOOL_A["input_schema"]),
                                 "approved_server_version": "1", "observed_server_version": "1",
                                 "observed_description_hash": None, "observed_schema_hash": None}

    def snapshot(self, params, exact_match=None):
        server_id, version, catalog_hash, count = params[:4]
        if exact_match is None:
            exact_match = params[4]
        record = {"id": len(self.snapshots) + 1, "server_id": server_id, "server_version": version,
                  "catalog_hash": catalog_hash, "tool_count": count, "exact_match": exact_match,
                  "restricted_tools": params[6] if len(params) > 6 else None}
        self.snapshots.append(record)
        return {"id": record["id"]}

    async def fetch_one(self, query, params):
        if "FROM mcp_servers" in query:
            return deepcopy(self.servers.get(params[0]))
        if "FROM catalog_snapshots" in query:
            history = [row for row in self.snapshots if row["server_id"] == params[0]]
            if "AND catalog_hash=%s" in query:
                history = [row for row in history if row["catalog_hash"] == params[1]]
            return deepcopy(history[-1]) if history else None
        if "INSERT INTO catalog_snapshots" in query:
            return self.snapshot(params)
        raise AssertionError(f"Unexpected fetch_one: {query}")

    async def fetch_all(self, query, params):
        if "FROM mcp_tools" in query:
            return [deepcopy(self.tools[params[0]])]
        raise AssertionError(f"Unexpected fetch_all: {query}")

    @asynccontextmanager
    async def transaction(self):
        class Connection:
            async def execute(inner, query, params):
                if query.startswith("SELECT id FROM mcp_servers"):
                    row = {"id": params[0]}
                elif query.startswith("INSERT INTO catalog_snapshots"):
                    row = self.snapshot(params)
                else:
                    await self.execute(query, params)
                    row = None
                class Cursor:
                    async def fetchone(inner):
                        return row
                return Cursor()
        yield Connection()

    async def execute(self, query, params):
        compact = " ".join(query.split())
        if compact.startswith("UPDATE mcp_tools SET observed_description_hash=%s"):
            description_hash, schema_hash, version, description, schema, annotations, server_id, name = params
            row = self.tools[server_id]
            assert row["name"] == name
            row.update(observed_description_hash=description_hash, observed_schema_hash=schema_hash,
                       observed_server_version=version, description=description,
                       input_schema=deepcopy(schema.obj), annotations=deepcopy(annotations.obj))
            self.observation_writes.append(server_id)
        elif compact.startswith("UPDATE mcp_tools SET approved_server_version=%s"):
            row = self.tools[params[2]]
            if row["approved_description_hash"] == row["observed_description_hash"] and row["approved_schema_hash"] == row["observed_schema_hash"]:
                row.update(approved_server_version=params[0], observed_server_version=params[1])
        elif compact.startswith("UPDATE mcp_servers SET status=%s"):
            self.servers[params[3]].update(status=params[0], status_reason=params[1])
        elif compact.startswith("UPDATE mcp_servers SET drift_observed_at=now()"):
            self.servers[params[0]]["drift_observed_at"] = "observed"
        elif compact.startswith("UPDATE mcp_tools SET approved_description_hash = COALESCE"):
            row = self.tools[params[0]]
            row.update(approved_description_hash=row["observed_description_hash"],
                       approved_schema_hash=row["observed_schema_hash"], approved_server_version=row["observed_server_version"])
        elif compact.startswith("INSERT INTO catalog_snapshots"):
            self.snapshot(params, exact_match=True)
        else:
            raise AssertionError(f"Unexpected execute: {query}")
        return 1


class CatalogRefreshTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = CatalogDB()
        self.db.register("alpha")
        self.db.register("beta")
        self.current = {"alpha": TOOL_A, "beta": TOOL_A}
        self.patches = ExitStack()
        for name in ("fetch_one", "fetch_all", "execute", "transaction"):
            self.patches.enter_context(patch.object(core.db, name, getattr(self.db, name)))
        self.patches.enter_context(patch.object(core, "_discover", self.discover))
        self.patches.enter_context(patch.object(core.registry, "server", return_value={"poisoning_review": {}}))
        self.patches.enter_context(patch.object(core.registry, "is_console_registration", return_value=False))
        self.patches.enter_context(patch.object(core.poisoning, "findings", return_value=[]))
        self.patches.enter_context(patch.object(core.ops_response, "catalog_alerts", new=AsyncMock()))
        self.patches.enter_context(patch.object(core.ops_response, "contain_drift", new=AsyncMock()))
        self.patches.enter_context(patch.object(core.upstream, "release_pool", new=AsyncMock()))
        self.addCleanup(self.patches.close)

    async def discover(self, server_id):
        return {"tools": [deepcopy(self.current[server_id])], "version": "1", "protocol_version": "2025-11-25"}

    async def test_approved_a_changed_b_returned_a_restores_current_metadata(self):
        self.assertEqual((await core.refresh_catalog("alpha"))["status"], "READY")
        self.current["alpha"] = TOOL_B
        self.assertEqual((await core.refresh_catalog("alpha"))["status"], "DRIFT")
        self.current["alpha"] = TOOL_A
        self.assertEqual((await core.refresh_catalog("alpha"))["status"], "READY")
        row = self.db.tools["alpha"]
        self.assertEqual(row["description"], TOOL_A["description"])
        self.assertEqual(row["input_schema"], TOOL_A["input_schema"])
        self.assertEqual(row["annotations"], TOOL_A["annotations"])
        self.assertEqual(row["observed_description_hash"], row["approved_description_hash"])
        self.assertEqual(row["observed_schema_hash"], row["approved_schema_hash"])
        self.assertEqual(self.db.observation_writes, ["alpha", "alpha", "alpha"])

    async def test_approval_after_rollback_cannot_approve_stale_b(self):
        await core.refresh_catalog("alpha")
        self.current["alpha"] = TOOL_B
        await core.refresh_catalog("alpha")
        self.current["alpha"] = TOOL_A
        await core.refresh_catalog("alpha")
        approval = await core.approve_contract("alpha", "admin", "Review current returned catalog")
        self.assertEqual(approval["changed"], [])
        self.assertEqual(approval["status"], "READY")
        self.assertEqual(self.db.tools["alpha"]["approved_schema_hash"], core.canonical_hash(TOOL_A["input_schema"]))

    async def test_consecutive_unchanged_catalog_skips_metadata_and_snapshot_writes(self):
        await core.refresh_catalog("alpha")
        for _ in range(3):
            self.assertEqual((await core.refresh_catalog("alpha"))["status"], "READY")
        self.assertEqual(self.db.observation_writes, ["alpha"])
        self.assertEqual(len(self.db.snapshots), 1)
        self.db.tools["alpha"]["observed_schema_hash"] = None
        await core.refresh_catalog("alpha")
        self.assertEqual(self.db.observation_writes, ["alpha", "alpha"])

    async def test_snapshot_comparison_is_isolated_by_server(self):
        await core.refresh_catalog("alpha")
        self.current["beta"] = TOOL_B
        await core.refresh_catalog("beta")
        await core.refresh_catalog("alpha")
        self.assertEqual(self.db.observation_writes, ["alpha", "beta"])
        self.current["beta"] = TOOL_A
        await core.refresh_catalog("beta")
        self.assertEqual(self.db.observation_writes, ["alpha", "beta", "beta"])
        self.assertEqual(self.db.tools["beta"]["description"], TOOL_A["description"])


if __name__ == "__main__":
    unittest.main()
