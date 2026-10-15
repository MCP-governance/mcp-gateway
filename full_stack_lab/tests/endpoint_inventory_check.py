"""Offline inventory privacy and route tests; no real database or MCP is used."""
import importlib.util
import json
import sys
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "full_stack_lab" / "gateway"))
from app import endpoint_plane

spec = importlib.util.spec_from_file_location("inventory_agent", REPO / "endpoint-agent" / "agent.py")
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


class FakeCursor:
    def __init__(self, row=None, rowcount=0):
        self.row = row
        self.rowcount = rowcount

    async def fetchone(self):
        return self.row

    async def fetchall(self):
        return []


class FakeConnection:
    def __init__(self):
        self.calls = []

    async def execute(self, query, params=None):
        self.calls.append((query, params))
        if "FROM endpoint_agents" in query:
            return FakeCursor({"endpoint_id": "unit"})
        return FakeCursor(rowcount=0)


class FakeTransaction:
    def __init__(self):
        self.connection = FakeConnection()

    @asynccontextmanager
    async def transaction(self):
        yield self.connection


class Inventory(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.base = "https://gateway.example/mcp"
        self.gateway = {"id": "__gateway__", "lifecycle": "OPERATING", "status": "READY",
                        "keys": {self.base, endpoint_plane.SELF_MCP_NAME}, "bases": {self.base}}
        self.server = {"id": "git", "lifecycle": "OPERATING", "status": "READY", "keys": {"git"}}

    def test_gateway_name_cannot_approve_external_url(self):
        self.assertIsNone(endpoint_plane._match([self.gateway, self.server], "streamable-http",
                          "http://127.0.0.1:9876", endpoint_plane.SELF_MCP_NAME))

    def test_gateway_name_cannot_approve_stdio(self):
        self.assertIsNone(endpoint_plane._match([self.gateway, self.server], "stdio",
                          "python unapproved.py", endpoint_plane.SELF_MCP_NAME))
        self.assertIsNone(endpoint_plane._match([self.gateway, self.server], "stdio", self.base + "/git", "x"))

    def test_real_gateway_routes_and_direct_registered_server(self):
        endpoint_plane.check_route_matching()
        self.assertEqual(endpoint_plane._match([self.gateway, self.server], "streamable-http", self.base, "x")["id"], "__gateway__")

    def test_collector_hides_url_credentials(self):
        for url in ("https://user:synthetic-password@vendor.example/mcp",
                    "http://127.0.0.1:8000/mcp?token=synthetic-secret", "https://vendor.example/mcp#synthetic-secret"):
            with self.subTest(url=url):
                ref = agent.describe("local", {"url": url})["endpoint_ref"]
                self.assertTrue(ref.startswith("sha256:"))
                self.assertNotIn("synthetic", ref)
        self.assertEqual(agent.describe("git", {"url": self.base + "/git/"})["endpoint_ref"], self.base + "/git/")

    async def test_receiver_hides_legacy_stdio_arguments(self):
        raw = {"config_path": "/synthetic/mcp.json", "server_label": "local", "transport": "stdio",
               "endpoint_ref": "python server.py --token synthetic-secret"}
        adapter = FakeTransaction()
        with mock.patch.object(endpoint_plane.db, "transaction", new=adapter.transaction), \
             mock.patch.object(endpoint_plane.db, "fetch_one", new=mock.AsyncMock(side_effect=AssertionError("must use transaction connection"))), \
             mock.patch.object(endpoint_plane.db, "fetch_all", new=mock.AsyncMock(side_effect=AssertionError("must use transaction connection"))), \
             mock.patch.object(endpoint_plane.db, "execute", new=mock.AsyncMock(side_effect=AssertionError("must use transaction connection"))), \
             mock.patch.object(endpoint_plane, "_registry_index", new=mock.AsyncMock(return_value=[self.gateway, self.server])), \
             mock.patch.object(endpoint_plane, "_link_residue_to_cases", new=mock.AsyncMock()):
            await endpoint_plane.ingest("unit", [raw])
            inserted = next(params for query, params in adapter.connection.calls if "INSERT INTO endpoint_inventory" in query)
            self.assertTrue(inserted[4].startswith("sha256:"))
            self.assertNotIn("synthetic-secret", json.dumps(inserted[-1].obj))

    async def test_receiver_does_not_persist_legacy_url_secrets(self):
        raw = {"config_path": "/synthetic/mcp.json", "server_label": "local", "transport": "streamable-http",
               "endpoint_ref": "https://user:synthetic-password@vendor.example/mcp?token=synthetic-secret"}
        adapter = FakeTransaction()
        with mock.patch.object(endpoint_plane.db, "transaction", new=adapter.transaction), \
             mock.patch.object(endpoint_plane.db, "fetch_one", new=mock.AsyncMock(side_effect=AssertionError("must use transaction connection"))), \
             mock.patch.object(endpoint_plane.db, "fetch_all", new=mock.AsyncMock(side_effect=AssertionError("must use transaction connection"))), \
             mock.patch.object(endpoint_plane.db, "execute", new=mock.AsyncMock(side_effect=AssertionError("must use transaction connection"))), \
             mock.patch.object(endpoint_plane, "_registry_index", new=mock.AsyncMock(return_value=[self.gateway, self.server])), \
             mock.patch.object(endpoint_plane, "_link_residue_to_cases", new=mock.AsyncMock()):
            result = await endpoint_plane.ingest("unit", [raw])
            self.assertEqual(result["counts"]["shadow"], 1)
            inserted = next(params for query, params in adapter.connection.calls if "INSERT INTO endpoint_inventory" in query)
            self.assertTrue(inserted[4].startswith("sha256:"))
            self.assertNotIn("synthetic-secret", json.dumps(inserted[-1].obj))
            self.assertNotIn("synthetic-password", json.dumps(inserted[-1].obj))
        self.assertIn("synthetic-secret", raw["endpoint_ref"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
