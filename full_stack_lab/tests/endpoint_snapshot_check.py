"""Endpoint snapshot contract checks (unit adapter only; no app DB/network).

Run from the repository root:
  python -X utf8 -m unittest full_stack_lab.tests.endpoint_snapshot_check -v

These tests deliberately exercise only application schemas/functions with an in-memory
DB adapter. They do not establish PostgreSQL transaction isolation or deployed receiver
behavior. Run the same cases with the dedicated risk_scenarios_20261014 schema before
using them as database rollback evidence.
"""
from __future__ import annotations

import copy
import inspect
import sys
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "full_stack_lab" / "gateway"))
from app import endpoint_plane, main  # noqa: E402

SOURCES = ("local-socket", "network", "stdio-process")


class UnitCursor:
    def __init__(self, row=None, rows=None, rowcount=0):
        self.row = row
        self.rows = list(rows or [])
        self.rowcount = rowcount

    async def fetchone(self):
        return self.row

    async def fetchall(self):
        return list(self.rows)


class UnitDBAdapter:
    """Small transactional SQL recorder; never opens a database connection."""

    def __init__(self, *, fail_sql: str | None = None, detail=None):
        self.fail_sql = fail_sql
        self.detail = detail or {}
        self.calls: list[tuple[str, object]] = []
        self.effects: list[tuple[str, object]] = []
        self.transactions = 0
        self.in_transaction = False

    async def fetch_one(self, query, params=None):
        self.calls.append((query, params))
        if "FROM endpoint_agents" in query:
            return {"endpoint_id": "unit-endpoint", "owner_token": "unit-owner", "detail": self.detail}
        if "count(*) AS n" in query:
            return {"n": 7}  # Conservative prior shadow count fixture.
        return None

    async def fetch_all(self, query, params=None):
        self.calls.append((query, params))
        return []

    async def execute(self, query, params=None):
        self.calls.append((query, params))
        if self.fail_sql and self.fail_sql.lower() in query.lower():
            raise RuntimeError("injected unit-adapter SQL failure")
        if any(word in query.lstrip().upper()[:24] for word in ("INSERT", "UPDATE", "DELETE")):
            self.effects.append((query, copy.deepcopy(params)))
        if "FROM endpoint_agents" in query:
            return UnitCursor(row={"endpoint_id": "unit-endpoint", "owner_token": "unit-owner", "detail": self.detail})
        if "count(*) AS n" in query:
            return UnitCursor(row={"n": 7})
        return UnitCursor(rowcount=0)

    @asynccontextmanager
    async def transaction(self):
        self.transactions += 1
        old_effects = copy.deepcopy(self.effects)
        self.in_transaction = True
        try:
            yield self
        except BaseException:
            self.effects = old_effects
            raise
        finally:
            self.in_transaction = False

    def patch(self):
        return mock.patch.multiple(
            endpoint_plane.db,
            fetch_one=mock.AsyncMock(side_effect=self.fetch_one),
            fetch_all=mock.AsyncMock(side_effect=self.fetch_all),
            execute=mock.AsyncMock(side_effect=self.execute),
            transaction=self.transaction,
        )

    def effect_sql(self):
        return [query.lower() for query, _ in self.effects]


class EndpointSnapshotModels(unittest.TestCase):
    def test_legacy_endpoint_report_defaults_to_incomplete_snapshot(self):
        parsed = main.EndpointReport.model_validate({"endpoint_id": "ep-unit", "entries": []})
        self.assertIs(parsed.complete, False)
        incomplete = main.EndpointReport.model_validate(
            {"endpoint_id": "ep-unit", "entries": [], "complete": False})
        self.assertIs(incomplete.complete, False)

    def test_legacy_listener_report_defaults_to_incomplete_snapshot(self):
        parsed = main.ListenerReport.model_validate({"endpoint_id": "ep-unit", "findings": []})
        self.assertIs(parsed.complete, False)
        self.assertIsNone(parsed.sources)

    def test_plane_receiver_defaults_are_fail_closed(self):
        self.assertIs(inspect.signature(endpoint_plane.ingest).parameters["complete"].default, False)
        self.assertIs(inspect.signature(endpoint_plane.ingest_listeners).parameters["complete"].default, False)

    def test_listener_report_accepts_unique_nonempty_source_scope(self):
        parsed = main.ListenerReport.model_validate({
            "endpoint_id": "ep-unit", "findings": [], "complete": True,
            "sources": ["stdio-process"],
        })
        self.assertEqual(parsed.sources, ["stdio-process"])

    def test_listener_report_rejects_empty_duplicate_or_unknown_sources(self):
        for sources in ([], ["network", "network"], ["filesystem"], [""]):
            with self.subTest(sources=sources), self.assertRaises(Exception):
                main.ListenerReport.model_validate({
                    "endpoint_id": "ep-unit", "findings": [], "sources": sources,
                })


class EndpointSnapshotIngest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.entry = {"config_path": "/fixture/config.json", "server_label": "fixture",
                      "transport": "streamable-http", "endpoint_ref": "https://fixture.invalid/mcp"}
        self.network = {"source": "network", "address": "192.0.2.10", "port": 7311,
                        "mcp_evidence": "suspected", "server_name": "fixture-network"}
        self.stdio = {"source": "stdio-process", "address": "process:fixture", "port": None,
                      "process_name": "fixture-mcp", "mcp_evidence": "suspected"}

    def patch_helpers(self, adapter):
        return (
            adapter.patch(),
            mock.patch.object(endpoint_plane, "_registry_index", new=mock.AsyncMock(return_value=[{
                "id": "__gateway__", "lifecycle": "OPERATING", "status": "READY",
                "keys": {endpoint_plane.SELF_MCP_NAME, "http://gateway:8080/mcp/"},
                "bases": {"http://gateway:8080/mcp/"},
            }])),
            mock.patch.object(endpoint_plane, "_link_residue_to_cases", new=mock.AsyncMock()),
        )

    async def test_incomplete_inventory_never_deletes_unseen_rows(self):
        adapter = UnitDBAdapter()
        patches = self.patch_helpers(adapter)
        with patches[0], patches[1], patches[2]:
            await endpoint_plane.ingest("unit-endpoint", [self.entry], complete=False)
        self.assertFalse(any("delete from endpoint_inventory" in q for q in adapter.effect_sql()))
        self.assertEqual(adapter.transactions, 1)

    async def test_unmarked_empty_inventory_is_partial_and_preserves_last_success(self):
        from datetime import UTC, datetime, timedelta
        prior_success = (datetime.now(UTC) - timedelta(seconds=30)).isoformat()
        adapter = UnitDBAdapter(detail={"observation": {"inventory": {
            "state": "success", "reported_at": prior_success,
            "last_success_at": prior_success, "accepted_count": 4,
        }}})
        patches = self.patch_helpers(adapter)
        with patches[0], patches[1], patches[2]:
            result = await endpoint_plane.ingest("unit-endpoint", [])
        self.assertFalse(result["complete"])
        self.assertFalse(any("delete from endpoint_inventory" in q for q in adapter.effect_sql()))
        updates = [(q, params) for q, params in adapter.effects
                   if "update endpoint_agents" in q.lower()]
        observation = None
        for _query, params in updates:
            for value in params or ():
                payload = getattr(value, "obj", None)
                if isinstance(payload, dict) and "inventory" in payload:
                    observation = payload["inventory"]
        self.assertIsNotNone(observation)
        self.assertEqual(observation["state"], "partial")
        self.assertEqual(observation["accepted_count"], 0)
        self.assertGreater(observation["reported_at"], prior_success)
        self.assertEqual(observation["last_success_at"], prior_success)

    async def test_complete_inventory_reconciles_unseen_rows(self):
        adapter = UnitDBAdapter()
        patches = self.patch_helpers(adapter)
        with patches[0], patches[1], patches[2]:
            await endpoint_plane.ingest("unit-endpoint", [self.entry], complete=True)
        self.assertTrue(any("delete from endpoint_inventory" in q for q in adapter.effect_sql()))
        self.assertEqual(adapter.transactions, 1)

    async def test_incomplete_listener_snapshot_never_deletes_any_source(self):
        adapter = UnitDBAdapter()
        patches = self.patch_helpers(adapter)
        with patches[0], patches[1], patches[2]:
            await endpoint_plane.ingest_listeners(
                "unit-endpoint", [self.stdio], complete=False, sources=["stdio-process"])
        self.assertFalse(any("delete from endpoint_listeners" in q for q in adapter.effect_sql()))
        self.assertEqual(adapter.transactions, 1)

    async def test_unmarked_empty_listener_snapshot_is_partial_and_never_deletes(self):
        adapter = UnitDBAdapter()
        patches = self.patch_helpers(adapter)
        with patches[0], patches[1], patches[2]:
            result = await endpoint_plane.ingest_listeners("unit-endpoint", [])
        self.assertFalse(result["complete"])
        self.assertFalse(any("delete from endpoint_listeners" in q for q in adapter.effect_sql()))
        observations = {}
        for query, params in adapter.effects:
            if "update endpoint_agents" not in query.lower():
                continue
            for value in params or ():
                payload = getattr(value, "obj", None)
                if isinstance(payload, dict):
                    observations.update(payload)
        self.assertEqual(observations["network"]["state"], "partial")
        self.assertEqual(observations["network"]["sources"], ["local-socket", "network"])
        self.assertEqual(observations["process"]["state"], "partial")
        self.assertEqual(observations["process"]["sources"], ["stdio-process"])

    async def test_gateway_name_claim_alone_does_not_classify_stdio_as_registered(self):
        finding = {"source": "stdio-process", "address": "process:claimed-gateway", "port": None,
                   "process_name": "fixture", "server_name": endpoint_plane.SELF_MCP_NAME,
                   "mcp_evidence": "suspected"}
        adapter = UnitDBAdapter()
        patches = self.patch_helpers(adapter)
        with patches[0], patches[1], patches[2]:
            result = await endpoint_plane.ingest_listeners(
                "unit-endpoint", [finding], complete=False, sources=["stdio-process"])
        self.assertEqual(result["counts"]["shadow"], 1)
        self.assertEqual(result["counts"]["registered"], 0)

    async def test_registered_server_name_does_not_approve_direct_listener(self):
        gateway_entry = {
            "id": "__gateway__", "lifecycle": "OPERATING", "status": "READY",
            "keys": {endpoint_plane.SELF_MCP_NAME, "http://gateway:8080/mcp/"},
            "bases": {"http://gateway:8080/mcp/"},
        }
        registered_entry = {
            "id": "known-server", "lifecycle": "OPERATING", "status": "READY",
            "keys": {"known-server", "http://known.invalid/mcp/"},
        }
        index = mock.AsyncMock(return_value=[gateway_entry, registered_entry])
        adapter = UnitDBAdapter()
        with adapter.patch(), mock.patch.object(endpoint_plane, "_registry_index", new=index), \
             mock.patch.object(endpoint_plane, "_link_residue_to_cases", new=mock.AsyncMock()):
            result = await endpoint_plane.ingest_listeners("unit-endpoint", [{
                "source": "stdio-process", "address": "process:direct-known", "port": None,
                "process_name": "known-server", "server_name": "known-server",
                "mcp_evidence": "suspected",
            }], complete=False, sources=["stdio-process"])
        self.assertEqual(result["counts"]["shadow"], 1)
        self.assertEqual(result["counts"]["registered"], 0)

    async def test_observation_status_route_scopes_authorize_only_own_endpoint_and_channel(self):
        # Calling the handler directly tests its endpoint/scope body checks. It does not
        # exercise FastAPI dependency transport authentication or deployed harness routing.
        device = {"endpoint_id": "unit-endpoint", "scopes": {"inventory"}}
        observation_status = mock.AsyncMock(return_value={"state": "recorded"})
        request = main.ObservationReport(endpoint_id="other-endpoint", channel="process", state="success")
        with mock.patch.object(endpoint_plane, "observation_status", new=observation_status):
            with self.assertRaises(main.HTTPException) as raised:
                await main.endpoint_observation_status(request, device)
        self.assertEqual(raised.exception.status_code, 403)
        observation_status.assert_not_awaited()

        for channel in ("process", "network", "os"):
            for state in ("success", "partial"):
                request = main.ObservationReport(endpoint_id="unit-endpoint", channel=channel, state=state)
                with self.subTest(channel=channel, state=state), \
                     mock.patch.object(endpoint_plane, "observation_status", new=observation_status):
                    with self.assertRaises(main.HTTPException) as raised:
                        await main.endpoint_observation_status(request, device)
                    self.assertEqual(raised.exception.status_code, 403)
        observation_status.assert_not_awaited()

        # Inventory credentials may submit a negative diagnostic for their own endpoint.
        request = main.ObservationReport(
            endpoint_id="unit-endpoint", channel="process", state="unauthorized")
        with mock.patch.object(endpoint_plane, "observation_status", new=observation_status):
            result = await main.endpoint_observation_status(request, device)
        self.assertEqual(result, {"state": "recorded"})
        # Offline-buffer kwargs (DEV-80, 22cf622) are sent at their defaults here, so the
        # SQL path is unchanged. Keep the five values checked before and pin the defaults.
        observation_status.assert_awaited_once_with(
            "unit-endpoint", "process", "unauthorized", 0, "",
            buffer_event_uid=None, dropped_count=0, buffer_reason=None)

    async def test_incomplete_process_observation_preserves_last_success(self):
        self.assertTrue(hasattr(endpoint_plane, "observation_status"))
        from datetime import UTC, datetime, timedelta
        prior_success = (datetime.now(UTC) - timedelta(seconds=30)).isoformat()
        detail = {"observation": {"process": {
            "state": "success", "reported_at": prior_success,
            "last_success_at": prior_success, "accepted_count": 3,
        }}}
        adapter = UnitDBAdapter(detail=detail)
        patches = self.patch_helpers(adapter)
        with patches[0], patches[1], patches[2]:
            await endpoint_plane.ingest_listeners(
                "unit-endpoint", [self.stdio], complete=False, sources=["stdio-process"])
        updates = [(q, params) for q, params in adapter.effects
                   if "update endpoint_agents" in q.lower()]
        self.assertTrue(updates, "partial snapshot must update endpoint observation telemetry")
        observation = None
        for _query, params in updates:
            for value in params or ():
                payload = getattr(value, "obj", None)
                if isinstance(payload, dict) and "process" in payload:
                    observation = payload["process"]
        self.assertIsNotNone(observation, "read the Jsonb.obj payload rather than its truncated repr")
        self.assertEqual(observation["state"], "partial")
        self.assertEqual(observation["accepted_count"], 1)
        self.assertEqual(observation["sources"], ["stdio-process"])
        self.assertGreater(observation["reported_at"], prior_success)
        self.assertEqual(observation["last_success_at"], prior_success)

    async def test_observation_status_writes_partial_process_channel(self):
        adapter = UnitDBAdapter()
        with adapter.patch():
            await endpoint_plane.observation_status(
                "unit-endpoint", "process", "partial", 1, "source_failed")
        updates = [(q, params) for q, params in adapter.effects
                   if "update endpoint_agents" in q.lower()]
        self.assertTrue(updates)
        observation = None
        for _query, params in updates:
            for value in params or ():
                payload = getattr(value, "obj", None)
                if isinstance(payload, dict) and "process" in payload:
                    observation = payload["process"]
        self.assertIsNotNone(observation)
        self.assertEqual(observation["state"], "partial")
        self.assertEqual(observation["accepted_count"], 1)
        self.assertEqual(observation["error_code"], "source_failed")
        self.assertIn("reported_at", observation)
        self.assertIn("last_success_at", observation)

    def test_observation_freshness_distinguishes_known_stale_from_unknown(self):
        from datetime import UTC, datetime, timedelta
        now = datetime(2026, 10, 14, 12, 10, tzinfo=UTC)
        recent = (now - timedelta(seconds=30)).isoformat()
        old = (now - timedelta(seconds=181)).isoformat()
        future = (now + timedelta(seconds=1)).isoformat()
        self.assertEqual(endpoint_plane.observation_freshness(
            {"state":"success", "reported_at":recent}, recent, now), "fresh")
        self.assertEqual(endpoint_plane.observation_freshness(
            {"state":"success", "reported_at":old}, old, now), "stale")
        self.assertEqual(endpoint_plane.observation_freshness(
            {"state":"partial", "reported_at":recent}, recent, now), "unknown")
        self.assertEqual(endpoint_plane.observation_freshness(
            {"state":"success"}, recent, now), "unknown")
        self.assertEqual(endpoint_plane.observation_freshness(
            {"state":"success", "reported_at":"not-a-time"}, recent, now), "unknown")
        self.assertIn(endpoint_plane.observation_freshness(
            {"state":"success", "reported_at":future}, future, now), {"stale", "unknown"})

    async def test_complete_stdio_scope_delete_is_source_limited(self):
        adapter = UnitDBAdapter()
        patches = self.patch_helpers(adapter)
        with patches[0], patches[1], patches[2]:
            await endpoint_plane.ingest_listeners(
                "unit-endpoint", [], complete=True, sources=["stdio-process"])
        deletes = [(q, p) for q, p in adapter.effects if "delete from endpoint_listeners" in q.lower()]
        self.assertEqual(len(deletes), 1)
        query, params = deletes[0]
        self.assertIn("source", query.lower(), "scoped delete must constrain source in SQL")
        self.assertIn("stdio-process", repr(params))
        self.assertEqual(adapter.transactions, 1)

    async def test_findings_outside_declared_sources_rejected_before_mutation(self):
        self.assertIn("complete", inspect.signature(endpoint_plane.ingest_listeners).parameters)
        self.assertIn("sources", inspect.signature(endpoint_plane.ingest_listeners).parameters)
        adapter = UnitDBAdapter()
        patches = self.patch_helpers(adapter)
        with patches[0], patches[1], patches[2]:
            with self.assertRaises((ValueError, TypeError)):
                await endpoint_plane.ingest_listeners(
                    "unit-endpoint", [self.network], complete=True, sources=["stdio-process"])
        self.assertEqual(adapter.effects, [])

    async def test_invalid_source_list_rejected_before_mutation(self):
        self.assertIn("sources", inspect.signature(endpoint_plane.ingest_listeners).parameters)
        self.assertIn("complete", inspect.signature(endpoint_plane.ingest_listeners).parameters)
        for sources in ([], ["network", "network"], ["invalid"], [""]):
            adapter = UnitDBAdapter()
            patches = self.patch_helpers(adapter)
            with self.subTest(sources=sources), patches[0], patches[1], patches[2]:
                with self.assertRaises((ValueError, TypeError)):
                    await endpoint_plane.ingest_listeners(
                        "unit-endpoint", [], complete=True, sources=sources)
            self.assertEqual(adapter.effects, [])

    async def test_mid_ingest_database_failure_rolls_back_prior_mutations(self):
        adapter = UnitDBAdapter(fail_sql="DELETE FROM endpoint_listeners")
        patches = self.patch_helpers(adapter)
        with patches[0], patches[1], patches[2]:
            with self.assertRaisesRegex(RuntimeError, "injected unit-adapter"):
                await endpoint_plane.ingest_listeners(
                    "unit-endpoint", [self.stdio], complete=True, sources=None)
        self.assertEqual(adapter.effects, [], "transaction adapter must roll back inserts before failure")
        self.assertEqual(adapter.transactions, 1)

    async def test_shadow_count_query_does_not_coerce_to_zero_on_unknown_or_stale(self):
        # The adapter returns an existing conservative count. Source freshness policy
        # belongs in SQL/application code; this test rejects a hard-coded healthy zero.
        adapter = UnitDBAdapter()
        with adapter.patch():
            count = await endpoint_plane.shadow_listener_count_for("unit-owner")
        self.assertEqual(count, 7)
        self.assertEqual(adapter.transactions, 0)
        queries = [q.lower() for q, _ in adapter.calls if "endpoint_listeners" in q.lower()]
        self.assertTrue(queries)
        self.assertFalse(any("last_success_at" in q or "reported_at >" in q for q in queries),
                         "staleness should be displayed as unknown, not used to erase the conservative count")


if __name__ == "__main__":
    unittest.main(verbosity=2)

