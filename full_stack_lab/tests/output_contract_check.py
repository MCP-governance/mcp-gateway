"""D-149. --pure: stdlib approval/shape checks; default: Gateway image checks too.

No MCP server is created. AsyncMock models database/SDK I/O, not live MCP evidence.
"""
from __future__ import annotations

import ast
from contextlib import ExitStack, asynccontextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

APP = Path(__file__).resolve().parents[1] / "gateway" / "app"
if not APP.exists():
    APP = Path("/app/app")
PURE = "--pure" in sys.argv
if PURE:
    sys.argv.remove("--pure")


def definitions(filename, names, namespace):
    tree = ast.parse((APP / filename).read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if getattr(n, "name", None) in names or
             isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in n.targets)]
    if len(nodes) != len(names):
        raise AssertionError("production definitions missing")
    module = ModuleType("output_contract_unit")
    module.__dict__.update(namespace)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(APP / filename), "exec"), module.__dict__)
    return module


digest = definitions("contract.py", {"canonical_hash"}, {"hashlib": hashlib, "json": json}).canonical_hash
contract = definitions("output_contract.py", {
    "NO_OUTPUT_SCHEMA_HASH", "OBJECT_PROTOCOLS", "JSON_PROTOCOLS", "approved_hash", "matches",
    "observed_matches", "for_protocol", "check_schema_bounds", "MAX_SCHEMA_DEPTH", "MAX_SCHEMA_NODES",
    "MAX_SCHEMA_BYTES", "OutputSchemaTooComplex", "WireRejected"}, {"canonical_hash": digest, "math": __import__("math")})
selective = definitions("selective.py", {"restricted_tools", "available"}, {})
schema = {"type": "object", "properties": {"count": {"type": "integer"}}, "required": ["count"]}


class PureContract(unittest.TestCase):
    def test_schema_resource_bounds_reject_large_and_deep_documents(self):
        contract.check_schema_bounds(schema)
        deep = {"type": "object"}
        for _ in range(contract.MAX_SCHEMA_DEPTH):
            deep = {"properties": {"nested": deep}}
        with self.assertRaises(contract.OutputSchemaTooComplex):
            contract.check_schema_bounds(deep)
        wide = {"anyOf": [{"type": "string"} for _ in range(contract.MAX_SCHEMA_NODES)]}
        with self.assertRaises(contract.OutputSchemaTooComplex):
            contract.check_schema_bounds(wide)
        large = {"description": "x" * contract.MAX_SCHEMA_BYTES}
        with self.assertRaises(contract.OutputSchemaTooComplex):
            contract.check_schema_bounds(large)

    def test_legacy_approval_is_unpinned_and_never_adopts_the_observation(self):
        # Approved before output schemas were pinned: not restricted on them (as before), and the
        # observed schema is not taken as approved - re-approval by a person pins it.
        for row in ({}, {"approved_output_schema_hash": None}):
            self.assertTrue(contract.matches(row, None))
            self.assertTrue(contract.matches(row, schema))
            self.assertTrue(contract.observed_matches({**row, "observed_output_schema_hash": digest(schema)}))
            self.assertEqual(contract.approved_hash({**row, "observed_output_schema_hash": digest(schema)}),
                             digest(None))

    def test_add_change_remove_and_explicit_approval(self):
        row = {"approved_output_schema_hash": digest(schema)}
        self.assertTrue(contract.matches(row, deepcopy(schema)))
        self.assertFalse(contract.matches(row, {"type": "object"}))
        self.assertFalse(contract.matches(row, None))
        self.assertTrue(contract.matches({"approved_output_schema_hash": digest(None)}, None))

    def test_modern_preserves_all_json_values_including_explicit_null(self):
        for value in ({}, [], [1, 2], "public", 0, False, None):
            with self.subTest(value=value):
                payload = {"content": [], "structured": value}
                self.assertEqual(contract.for_protocol(payload, "2026-07-28"), payload)
        self.assertNotIn("structured", contract.for_protocol({"content": []}, "2026-07-28"))

    def test_object_era_and_unknown_preserve_value_as_text(self):
        for version in ("2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25", "future", None):
            for value in ([], "public", 0, False, None):
                with self.subTest(version=version, value=value):
                    source = {"content": [{"type": "text", "text": "summary"}], "structured": value}
                    converted = contract.for_protocol(source, version)
                    self.assertNotIn("structured", converted)
                    self.assertEqual(json.loads(converted["content"][-1]["text"]), value)
                    self.assertIn("structured", source)  # shared payload was not mutated
            obj = {"content": [], "structured": {"count": 1}}
            result = contract.for_protocol(obj, version)
            self.assertEqual("structured" in result, version in {None, "2025-06-18", "2025-11-25"})

    def test_output_drift_restricts_only_affected_tool(self):
        finding = {"type": "contract-drift", "tool": "read", "fields": ["output_schema"], "enabled": True}
        self.assertEqual(selective.restricted_tools([finding]), ["read"])
        self.assertFalse(selective.available({"exact_match": False, "restricted_tools": ["read"]}, "read"))
        self.assertTrue(selective.available({"exact_match": False, "restricted_tools": ["read"]}, "other"))

    def test_lock_diff_and_poisoning_review_migration(self):
        registry = definitions("registry.py", {"tool_hashes", "review_matches"}, {
            "canonical_hash": digest, "NO_OUTPUT_SCHEMA_HASH": digest(None)})
        tool = {"name": "read", "description": "Read count", "input_schema": {"type": "object"}}
        old = {k: v for k, v in registry.tool_hashes(tool).items() if k != "output_schema_sha256"}
        self.assertTrue(registry.review_matches(old, tool))
        # A legacy review covered description and input; the output schema is unpinned (D-149).
        self.assertTrue(registry.review_matches(old, {**tool, "output_schema": schema}))
        self.assertFalse(registry.review_matches(registry.tool_hashes(tool), {**tool, "output_schema": schema}))
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from contracts_check import diff
        before = {"servers": {"s": {"tools": {"read": old}}}}
        after = {"servers": {"s": {"tools": {"read": registry.tool_hashes(tool)}}}}
        self.assertEqual(diff(before, after), [])
        after["servers"]["s"]["tools"]["read"] = registry.tool_hashes({**tool, "output_schema": schema})
        self.assertEqual(diff(before, after), ["s.read: output_schema 변경"])


class CatalogContract(unittest.IsolatedAsyncioTestCase):
    async def test_fresh_output_drift_blocks_dispatch_with_catalog_policy(self):
        # Reuse the deterministic D-140 database/transport doubles; no real server.
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from dispatch_recheck_check import Checks
        sender = Checks()
        sender.setUp()
        current = sender.ns["upstream"].tool_view(None)
        sender.ns["upstream"].tool_view = lambda _: {**current, "output_schema": schema}
        # Pinned as "no output schema": a schema appearing at send time is drift.
        sender.ns["db"].fetch_all.return_value[0]["approved_output_schema_hash"] = digest(None)
        verdict = await sender.send()
        self.assertEqual((verdict["decision"], verdict["policy_id"]), ("Block", "MCP-CATALOG-001"))
        sender.client.call_tool.assert_not_awaited()
        self.assertFalse(sender.event["upstream_attempted"])
        sender.ns["db"].fetch_all.return_value[0]["approved_output_schema_hash"] = digest(schema)
        verdict = await sender.send()
        self.assertEqual(verdict["decision"], "Allow")
        sender.client.call_tool.assert_awaited_once()

    async def test_schema_drift_reapproval_and_legacy_transition(self):
        core = definitions("core.py", {"refresh_catalog", "approve_contract"}, {
            "db": SimpleNamespace(fetch_one=AsyncMock(), fetch_all=AsyncMock(), execute=AsyncMock(), transaction=None),
            "registry": SimpleNamespace(server=lambda _: {}, is_console_registration=lambda _: False,
                                        review_matches=lambda *args: False),
            "canonical_hash": digest, "output_contract": contract, "selective": selective,
            "Jsonb": lambda obj: SimpleNamespace(obj=obj), "_discover": AsyncMock(),
            "poisoning": SimpleNamespace(findings=lambda _: []),
            "upstream": SimpleNamespace(release_pool=AsyncMock(), credential_source=lambda *args: "none"),
            "ops_response": SimpleNamespace(catalog_alerts=AsyncMock(), contain_drift=AsyncMock()),
            "review": SimpleNamespace(record_event=AsyncMock())})
        for old_schema, approved_hash in [(None, None), (schema, digest(schema))]:
            with self.subTest(old_schema=old_schema):
                tool = {"name": "read", "description": "Read count", "input_schema": {"type": "object"},
                        "output_schema": old_schema, "annotations": None}
                row = {"name": "read", "enabled": True, "approved_description_hash": digest(tool["description"]),
                       "approved_schema_hash": digest(tool["input_schema"]), "approved_server_version": "1",
                       "observed_description_hash": digest(tool["description"]), "observed_schema_hash": digest(tool["input_schema"]),
                       "observed_server_version": "1", "approved_output_schema_hash": approved_hash,
                       "observed_output_schema_hash": digest(old_schema)}
                server = {"id": "s", "status": "READY", "status_reason": "", "lifecycle": "OPERATING", "endpoint": "https://invalid.example"}
                snapshots = []

                async def fetch_one(query, params):
                    return deepcopy(server) if "FROM mcp_servers" in query else (snapshots[-1] if snapshots else None)

                async def statement(query, params):
                    compact = " ".join(query.split())
                    result = None
                    if compact.startswith("UPDATE mcp_tools SET observed_description_hash=%s"):
                        row.update(observed_description_hash=params[0], observed_schema_hash=params[1], observed_server_version=params[2])
                    elif compact.startswith("UPDATE mcp_tools SET output_schema=%s"):
                        row.update(output_schema=params[0].obj, observed_output_schema_hash=params[1])
                    elif compact.startswith("UPDATE mcp_tools SET approved_description_hash = COALESCE"):
                        row.update(approved_description_hash=row["observed_description_hash"], approved_schema_hash=row["observed_schema_hash"],
                                   approved_output_schema_hash=row["observed_output_schema_hash"], approved_server_version=row["observed_server_version"])
                    elif compact.startswith("UPDATE mcp_servers SET status=%s"):
                        server["status"] = params[0]
                    elif compact.startswith("INSERT INTO catalog_snapshots"):
                        result = {"id": len(snapshots) + 1, "catalog_hash": params[2], "exact_match": params[4] if len(params) == 7 else True,
                                  "server_version": params[1], "restricted_tools": params[6] if len(params) == 7 else []}
                        snapshots.append(result)
                    return SimpleNamespace(fetchone=AsyncMock(return_value=result))

                connection = SimpleNamespace(execute=AsyncMock(side_effect=statement))

                @asynccontextmanager
                async def transaction():
                    yield connection

                with ExitStack() as patches:
                    for name, replacement in {
                        "fetch_one": AsyncMock(side_effect=fetch_one),
                        "fetch_all": AsyncMock(side_effect=lambda *args: [deepcopy(row)]),
                        "execute": AsyncMock(side_effect=statement), "transaction": transaction,
                    }.items():
                        patches.enter_context(patch.object(core.db, name, replacement))
                    patches.enter_context(patch.object(core, "_discover", AsyncMock(side_effect=lambda _: {
                        "tools": [deepcopy(tool)], "version": "1", "advertised_name": "s", "protocol_version": "2026-07-28"})))
                    patches.enter_context(patch.object(core.registry, "server", return_value={"poisoning_review": {}}))
                    patches.enter_context(patch.object(core.registry, "is_console_registration", return_value=False))
                    patches.enter_context(patch.object(core.poisoning, "findings", return_value=[]))
                    patches.enter_context(patch.object(core.ops_response, "catalog_alerts", AsyncMock()))
                    patches.enter_context(patch.object(core.upstream, "release_pool", AsyncMock()))
                    patches.enter_context(patch.object(core.review, "record_event", AsyncMock()))
                    self.assertEqual((await core.refresh_catalog("s"))["status"], "READY")
                    tool["output_schema"] = {"type": "object", "properties": {"value": {"type": "string"}}}
                    changed = await core.refresh_catalog("s")
                    # A legacy (unpinned) approval is not restricted on output schemas and does not adopt one.
                    self.assertEqual(changed["status"], "READY" if approved_hash is None else "DRIFT")
                    if approved_hash is not None:
                        self.assertIn("output_schema", next(f["fields"] for f in changed["findings"] if f["type"] == "contract-drift"))
                    self.assertEqual(row["approved_output_schema_hash"], approved_hash)
                    approved = await core.approve_contract("s", "reviewer", "검토 완료")
                    self.assertEqual(approved["status"], "READY")
                    self.assertEqual(row["approved_output_schema_hash"], digest(tool["output_schema"]))
                    self.assertTrue(contract.matches(row, tool["output_schema"]))
                    tool["output_schema"] = None
                    self.assertEqual((await core.refresh_catalog("s"))["status"], "DRIFT")

if not PURE:
    os.environ.setdefault("OTEL_SDK_DISABLED", "true")
    sys.path.insert(0, str(APP.parent))
    from app import core, mcp_facade, output_contract, upstream
    from mcp import types
    from mcp.server.runner import _dump_result
    from pydantic import ValidationError

    class GatewayContract(unittest.IsolatedAsyncioTestCase):
        def test_unbounded_schema_is_rejected_during_tool_catalog_conversion(self):
            tool = SimpleNamespace(name="read", description="", input_schema={}, output_schema={"type": "object"})
            for _ in range(output_contract.MAX_SCHEMA_DEPTH):
                tool.output_schema = {"properties": {"nested": tool.output_schema}}
            with self.assertRaises(output_contract.OutputSchemaTooComplex):
                upstream.tool_view(tool)

        def test_approved_schema_rejects_missing_mismatched_and_remote_refs(self):
            for payload, approved in [
                ({"content": [], "structured": {"count": "private"}}, schema),
                ({"content": []}, schema),
                ({"content": [], "structured": {}}, {"$ref": "https://invalid.example/schema"}),
                ({"content": [], "structured": {}}, {"type": "invalid"}),
                ({"content": [], "structured": {}}, {"$schema": "https://invalid.example/dialect"}),
                ({"content": [], "structured": {"a": 1}}, {
                    "$schema": "http://json-schema.org/draft-07/schema#", "dependencies": {"a": ["b"]}}),
            ]:
                with self.subTest(approved=approved), self.assertRaises(core.ResultRejected) as error:
                    core._guarded_result(payload, "2026-07-28", approved)
                self.assertEqual(error.exception.evidence["disposition"], "withheld")
                self.assertNotIn("private", str(error.exception))
            self.assertEqual(core._guarded_result({"content": [], "structured": {"count": 1}},
                                                 "2026-07-28", schema)["structured"], {"count": 1})

        def test_tool_error_message_passes_but_structured_error_is_checked(self):
            error = {"content": [{"type": "text", "text": "rate limited, retry later"}], "is_error": True}
            self.assertEqual(core._guarded_result(error, "2026-07-28", schema)["content"], error["content"])
            with self.assertRaises(core.ResultRejected):
                core._guarded_result({**error, "structured": {"count": "private"}}, "2026-07-28", schema)

        def test_sdk_render_versions_and_explicit_null_wire(self):
            for value in ({"count": 1}, [1], "public", 0, False, None):
                for version in ("2025-03-26", "2025-06-18", "2025-11-25", "2026-07-28"):
                    with self.subTest(value=value, version=version):
                        result = core._guarded_result({"content": [], "structured": value}, "2026-07-28")
                        outcome = {"decision": "Allow", "policy_id": "P-AUTHZ-ALLOW-001", "upstream_executed": True,
                                   "result": result, "result_evidence": {"disposition": "returned"}}
                        wire = _dump_result(mcp_facade._render(outcome, version))
                        if version == "2026-07-28" or (version != "2025-03-26" and isinstance(value, dict)):
                            self.assertIn("structuredContent", wire)
                            self.assertEqual(wire["structuredContent"], value)
                        else:
                            self.assertNotIn("structuredContent", wire)
                            self.assertEqual(json.loads(wire["content"][0]["text"]), value)

        async def test_masked_value_must_still_match_output_contract(self):
            payload = {"content": [], "structured": {"count": 1}}
            masked = {"content": [], "structured": {"count": "[REDACTED]"}}
            with patch.object(core.privacy, "mask_payload", AsyncMock(return_value=(masked, ["PII"]))), \
                    patch.object(core.secret_scan, "labels", AsyncMock(return_value=[])):
                released, _ = await core._inspected_result(payload)
            with self.assertRaises(core.ResultRejected):
                core._validate_output(released, schema)

        async def test_sdk_public_request_preserves_null_and_validation_receipt(self):
            answer = types.CallToolResult.model_validate({"content": [], "structuredContent": None})
            client = SimpleNamespace(session=SimpleNamespace(send_request=AsyncMock(return_value=answer)))
            returned = await upstream.ContractClient(client).call_tool("read", {})
            self.assertIn("structured_content", returned.model_fields_set)
            core._validate_output({"content": [], "structured": returned.structured_content}, {"type": "null"})
            client.session.send_request.side_effect = ValidationError.from_exception_data("wire", [])
            with self.assertRaises(output_contract.WireRejected) as error:
                await upstream.ContractClient(client).call_tool("read", {})
            verdict = core._upstream_failure(ExceptionGroup("transport", [error.exception]), {})
            self.assertEqual((verdict["decision"], verdict["policy_id"]), ("Block", "MCP-OUTPUT-001"))
            self.assertTrue(verdict["upstream_executed"])
            self.assertIsNone(verdict["result"])



if __name__ == "__main__":
    unittest.main(verbosity=2)
