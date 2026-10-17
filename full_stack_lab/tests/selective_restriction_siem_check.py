"""Offline unit doubles and an ephemeral loopback HTTP receiver; no MCP/DB/container."""
from __future__ import annotations

import ast
import asyncio
import copy
import hashlib
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import AsyncMock, patch

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "gateway"))
from app import selective, siem


def production_functions(file, names, namespace):
    namespace.update(__name__="app.offline_unit", __package__="app")
    tree = ast.parse((LAB / "gateway/app" / file).read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
    exec(compile(ast.fix_missing_locations(ast.Module(
        body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *nodes],
        type_ignores=[])), file, "exec"), namespace)
    return namespace


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


class Cursor:
    def __init__(self, row):
        self.row = row

    async def fetchone(self):
        return self.row


class CatalogDB:
    def __init__(self):
        self.server = {"id": "alpha", "status": "READY", "status_reason": "", "lifecycle": "OPERATING",
                       "endpoint": "http://unit.invalid", "source_ref": "fixed", "automatic_stop_reason": None}
        self.observed = {name: {"name": name, "description": name, "input_schema": {"type": "object"}} for name in ("a", "b")}
        self.tools = {name: {**tool, "enabled": True, "approved_description_hash": digest(tool["description"]),
                            "approved_schema_hash": digest(tool["input_schema"]), "approved_server_version": "1",
                            "observed_description_hash": None, "observed_schema_hash": None} for name, tool in self.observed.items()}
        self.snapshots = []
        self.version = "1"

    @asynccontextmanager
    async def transaction(self):
        yield self

    async def execute(self, query, params=()):
        compact = " ".join(query.split())
        if compact.startswith("SELECT id FROM mcp_servers"):
            return Cursor({"id": "alpha"})
        if compact.startswith("INSERT INTO catalog_snapshots"):
            sid, version, hashed, count, exact, findings, restricted = params
            row = dict(id=len(self.snapshots) + 1, server_id=sid, server_version=version, catalog_hash=hashed, exact_match=exact,
                       findings=findings, restricted_tools=restricted)
            self.snapshots.append(row)
            return Cursor({"id": row["id"]})
        if compact.startswith("UPDATE mcp_tools SET observed_description_hash"):
            dh, sh, version, desc, schema, annotations, sid, name = params
            self.tools[name].update(observed_description_hash=dh, observed_schema_hash=sh, observed_server_version=version,
                                    description=desc, input_schema=schema, annotations=annotations)
        elif compact.startswith("UPDATE mcp_tools SET approved_server_version"):
            for row in self.tools.values():
                if (row["approved_description_hash"] == row["observed_description_hash"]
                        and row["approved_schema_hash"] == row["observed_schema_hash"]):
                    row.update(approved_server_version=params[0], observed_server_version=params[0])
        elif compact.startswith("UPDATE mcp_servers SET status=%s"):
            if self.server["status"] != "DISABLED":
                self.server.update(status=params[0], status_reason=params[1])
        elif compact.startswith("UPDATE mcp_servers SET drift_observed_at"):
            pass
        elif compact.startswith("UPDATE mcp_servers SET status='DISABLED'"):
            self.server["status"] = "DISABLED"
        else:
            raise AssertionError(compact)
        return Cursor(None)

    async def fetch_one(self, query, params=()):
        if "FROM mcp_servers" in query:
            return copy.deepcopy(self.server)
        if "FROM mcp_tools" in query:
            return copy.deepcopy(self.tools.get(params[1]))
        if "FROM catalog_snapshots" in query:
            return copy.deepcopy(self.snapshots[-1]) if self.snapshots else None
        if "FROM supply_chain_reports" in query:
            return {"critical_count": 0, "accepted": 0}
        raise AssertionError(query)

    async def fetch_all(self, query, params=()):
        if "FROM mcp_tools" in query:
            return copy.deepcopy(list(self.tools.values()))
        raise AssertionError(query)


class SelectiveChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = CatalogDB()
        self.suspend = AsyncMock()
        contain = production_functions("ops_response.py", {"contain_drift"},
            {"restricted_tools": selective.restricted_tools, "selected": lambda *_: True, "suspend": self.suspend})["contain_drift"]
        async def discover(_):
            return {"tools": copy.deepcopy(list(self.db.observed.values())), "version": self.db.version,
                    "protocol_version": "2025-11-25"}
        self.ns = production_functions("core.py", {"refresh_catalog", "_contract"}, {
            "db": self.db, "canonical_hash": digest, "selective": selective, "Jsonb": lambda value: value,
            "registry": types.SimpleNamespace(server=lambda _: {"poisoning_review": {}, "endpoint": "http://unit.invalid"}, pinned_protocol=lambda _: "2025-11-25"),
            "poisoning": types.SimpleNamespace(findings=lambda tool: ["unsafe"] if tool["description"] == "unsafe" else []),
            "upstream": types.SimpleNamespace(release_pool=AsyncMock()), "_discover": discover,
            "ops_response": types.SimpleNamespace(contain_drift=contain, catalog_alerts=AsyncMock()),
            "disposal": types.SimpleNamespace(blocked=lambda **_: False), "transport_secure": lambda _: True,
            "egress_allowed": AsyncMock(return_value=True),
        })
        self.ns["registry"].tool_hashes = digest

    async def refresh(self):
        return await self.ns["refresh_catalog"]("alpha")

    async def contract(self, name):
        return await self.ns["_contract"]("alpha", name)

    async def test_normal_and_other_tool_changed_with_version_rollover(self):
        await self.refresh()
        self.db.observed["a"]["input_schema"] = {"type": "string"}
        self.db.version = "2"
        await self.refresh()
        a, b = await self.contract("a"), await self.contract("b")
        self.assertFalse(a["known_tools_only"])
        self.assertFalse(a["schema_hash_match"])
        self.assertTrue(all(b[k] for k in ("known_tools_only", "schema_hash_match", "description_hash_match", "version_match", "metadata_safe")))
        self.assertEqual(self.db.snapshots[-1]["restricted_tools"], ["a"])
        self.suspend.assert_not_awaited()

    async def test_missing_and_unsafe_are_scoped_and_not_exposed(self):
        await self.refresh()
        del self.db.observed["a"]
        await self.refresh()
        self.assertFalse((await self.contract("a"))["known_tools_only"])
        self.assertTrue((await self.contract("b"))["known_tools_only"])
        self.db.observed["b"]["description"] = "unsafe"
        await self.refresh()
        self.assertFalse((await self.contract("b"))["metadata_safe"])
        self.assertEqual(self.db.snapshots[-1]["restricted_tools"], ["a", "b"])

    async def test_unapproved_tool_and_version_change_do_not_expand_approval(self):
        self.db.observed["new"] = {"name": "new", "description": "new", "input_schema": {}}
        self.db.version = "2"
        await self.refresh()
        self.assertTrue((await self.contract("b"))["known_tools_only"])
        self.assertFalse((await self.contract("new"))["registered"])
        self.assertNotIn("new", self.db.tools)

    async def test_return_to_pinned_contract_and_repeat_leave_history(self):
        original = copy.deepcopy(self.db.observed)
        await self.refresh()
        self.db.observed["a"]["description"] = "changed"
        await self.refresh()
        self.db.observed = original
        await self.refresh()
        self.assertTrue((await self.contract("a"))["known_tools_only"])
        self.assertEqual(len(self.db.snapshots), 3)
        await self.refresh()
        self.assertEqual(len(self.db.snapshots), 3)

    async def test_disabled_and_unknown_scope_fail_closed(self):
        await self.refresh()
        self.db.snapshots[-1].update(exact_match=False, restricted_tools=None)
        self.assertFalse((await self.contract("b"))["known_tools_only"])
        self.db.server.update(status="PENDING", automatic_stop_reason="stopped")
        self.assertEqual((await self.refresh())["status"], "DISABLED")
        self.assertFalse((await self.contract("b"))["enabled"])
        await self.ns["ops_response"].contain_drift("alpha", [{"type": "unrecognized"}])
        self.suspend.assert_awaited_once()

    def test_malformed_evidence_cannot_make_a_small_scope(self):
        for findings in (None, [None], [{"type": "contract-drift", "tool": "a", "fields": ["schema"]}],
                         [{"type": "unsafe-description", "tools": []}], [{"type": "contract-drift", "tool": "a", "fields": ["new"], "enabled": True}]):
            self.assertIsNone(selective.restricted_tools(findings))
        self.assertFalse(selective.available(None, "a"))

    async def dispatch_call(self, tool, refused=None):
        class Rejected(Exception):
            def __init__(self, message, verdict=None):
                super().__init__(message)
                self.verdict = verdict
        self.call = AsyncMock(return_value=types.SimpleNamespace(is_error=False, structured_content=None))
        @asynccontextmanager
        async def session(*_, **__):
            yield types.SimpleNamespace(call_tool=self.call)
        namespace = dict(self.ns)
        namespace.update({
            "DispatchRejected": Rejected, "_Laps": lambda: types.SimpleNamespace(lap=lambda *_: None),
            "datetime": datetime, "UTC": timezone.utc, "GATEWAY_ENVIRONMENT": "prod", "asyncio": asyncio,
            "Draft202012Validator": lambda _: types.SimpleNamespace(is_valid=lambda _: True),
            "classify": types.SimpleNamespace(classify=lambda *_: None),
            "pac": types.SimpleNamespace(build=AsyncMock(return_value={})), "_guarded_result": lambda value: value,
            "local_verdict": lambda policy, decision, reason: {"policy_id": policy, "decision": decision, "reason": reason},
            "dispatch": types.SimpleNamespace(record=AsyncMock(return_value=refused)),
            "upstream": types.SimpleNamespace(session=session, list_all_tools=AsyncMock(return_value=[types.SimpleNamespace(name=n) for n in self.db.observed]),
                tool_view=lambda t: self.db.observed[t.name], release_pool=AsyncMock(), session_terminated=lambda _: False,
                content_items=lambda _: [{"type": "text", "text": "unit response"}]),
        })
        async def policy(value):
            if value["contract"]["known_tools_only"]:
                return {"decision": "Allow", "policy_id": "P-AUTHZ-ALLOW-001", "restrictions": {}}
            return {"decision": "Block", "policy_id": "MCP-CATALOG-001", "restrictions": {}}
        namespace["_policy"] = policy
        original_fetch = self.db.fetch_one
        async def fetch(query, params=()):
            if "FROM principals" in query:
                return {"status": "active"}
            return await original_fetch(query, params)
        production_functions("core.py", {"_call_upstream"}, namespace)
        endpoint = types.SimpleNamespace(managed_failure=AsyncMock(return_value=None))
        with patch.object(self.db, "fetch_one", side_effect=fetch), patch.dict(sys.modules, {"app.endpoint_plane": endpoint}):
            try:
                result = await namespace["_call_upstream"]("alpha", tool, {}, None, "employee",
                    dispatch_state={"policy_input": {"context": {}}, "request_id": "request", "action": "r"},
                    pac_payload={"arguments": {}})
                return result, None
            except Rejected as exc:
                return None, exc.verdict

    async def test_same_connection_allows_healthy_tool_despite_other_changed_or_missing_tool(self):
        await self.refresh()
        self.db.observed["a"]["description"] = "changed"
        await self.refresh()
        result, verdict = await self.dispatch_call("b")
        self.assertIsNone(verdict)
        self.assertEqual(result["content"][0]["text"], "unit response")
        self.call.assert_awaited_once_with("b", {})
        del self.db.observed["a"]
        await self.refresh()
        result, verdict = await self.dispatch_call("b")
        self.assertIsNone(verdict)
        self.call.assert_awaited_once()

    async def test_same_connection_change_and_final_dispatch_restriction_use_catalog_policy(self):
        await self.refresh()
        self.db.observed["b"]["description"] = "changed after refresh"
        _, verdict = await self.dispatch_call("b")
        self.assertEqual((verdict["decision"], verdict["policy_id"]), ("Block", "MCP-CATALOG-001"))
        self.call.assert_not_awaited()
        self.db.observed["b"]["description"] = "b"
        _, verdict = await self.dispatch_call("b", "contract")
        self.assertEqual((verdict["decision"], verdict["policy_id"]), ("Block", "MCP-CATALOG-001"))
        self.call.assert_not_awaited()


class OutboxDB:
    def __init__(self):
        self.job = {"id": 1, "source": "decisions", "source_id": 7, "attempts": 0, "delivered_at": None}
        self.row = {"id": 7, "created_at": datetime(2026, 10, 17, tzinfo=timezone.utc), "decision": "Block", "policy_id": "MCP-CATALOG-001",
                    "upstream_attempted": False, "upstream_executed": False, "entry_sha256": "a" * 64,
                    "request_payload": "private-body", "reason": "private-reason", "client": {"token": "private-token"},
                    "user_token": "principal", "server_id": "server", "tool_name": "tool"}
        self.fail_commit = False

    @asynccontextmanager
    async def transaction(self):
        before = copy.deepcopy(self.job)
        try:
            yield self
            if self.fail_commit:
                raise OSError("commit failed")
        except BaseException:
            self.job = before
            raise

    async def execute(self, query, params=()):
        if query.startswith("SELECT * FROM siem_outbox"):
            return Cursor(copy.deepcopy(self.job) if self.job["delivered_at"] is None else None)
        if query.startswith("SELECT id,created_at"):
            return Cursor(self.row)
        if query.startswith("UPDATE siem_outbox"):
            self.job["attempts"] += 1
            if "delivered_at=now()" in query:
                self.job.update(delivered_at="now", last_error=None)
            else:
                self.job.update(last_error=params[0], delay=params[1])
            return Cursor(None)
        raise AssertionError(query)


class SiemChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = OutboxDB()
        self.patcher = patch.dict(sys.modules, {"app.db": self.db})
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.received, self.replies = [], [503, 200]
        received, replies = self.received, self.replies
        class Receiver(BaseHTTPRequestHandler):
            def do_POST(self):
                received.append((dict(self.headers), json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
                self.send_response(replies.pop(0) if replies else 200)
                self.send_header("Location", "https://never-follow.invalid")
                self.end_headers()
                self.wfile.write(b"private-response")

            def log_message(self, *_):
                pass
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.config = siem.settings({"SIEM_URL": f"http://127.0.0.1:{self.server.server_port}/ingest", "SIEM_ALLOW_LOOPBACK_HTTP": "1"})
        self.addCleanup(self.close_receiver)

    def close_receiver(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    async def test_http_failure_then_restart_retry_delivers_same_uid(self):
        await siem.deliver_one(self.config)
        self.assertEqual(self.db.job["last_error"], "HTTP-503")
        self.assertEqual(self.db.job["delay"], 5)
        self.assertIsNone(self.db.job["delivered_at"])
        await siem.deliver_one(self.config)
        self.assertEqual(self.db.job["attempts"], 2)
        self.assertIsNotNone(self.db.job["delivered_at"])
        self.assertEqual(self.received[0][0]["Idempotency-Key"], self.received[1][0]["Idempotency-Key"])
        self.assertNotIn("private", json.dumps(self.received))
        self.assertEqual(self.db.row["request_payload"], "private-body")

    async def test_receiver_ack_before_commit_failure_can_duplicate_with_stable_uid(self):
        self.replies[:] = [200, 200]
        self.db.fail_commit = True
        with self.assertRaises(OSError):
            await siem.deliver_one(self.config)
        self.assertIsNone(self.db.job["delivered_at"])
        self.db.fail_commit = False
        await siem.deliver_one(self.config)
        self.assertEqual(self.received[0][1], self.received[1][1])

    async def test_redirect_and_permanent_error_are_retained(self):
        self.replies[:] = [302, 401]
        await siem.deliver_one(self.config)
        self.assertEqual(len(self.received), 1)
        self.assertEqual(self.db.job["last_error"], "HTTP-302")
        self.db.job["attempts"] = 100000
        await siem.deliver_one(self.config)
        self.assertEqual(self.db.job["last_error"], "HTTP-401")
        self.assertEqual(self.db.job["delay"], 3600)

    async def test_timeout_and_poison_row_do_not_disappear_or_log_text(self):
        with patch.object(siem, "send", side_effect=TimeoutError("private-credential")):
            await siem.deliver_one(self.config)
        self.assertEqual(self.db.job["last_error"], "TimeoutError")
        self.db.row["decision"] = "invalid"
        await siem.deliver_one(self.config)
        self.assertEqual(self.db.job["last_error"], "ValueError")
        self.assertIsNone(self.db.job["delivered_at"])

    async def test_secret_rotation_is_read_from_file_each_attempt(self):
        self.replies[:] = [200, 200]
        payload = siem.event("decisions", self.db.row)
        with tempfile.TemporaryDirectory() as folder:
            token = Path(folder) / "token"
            config = {**self.config, "token_file": str(token)}
            token.write_text("first", encoding="utf-8")
            await asyncio.to_thread(siem.send, config, payload)
            token.write_text("second", encoding="utf-8")
            await asyncio.to_thread(siem.send, config, payload)
        self.assertEqual([h["Authorization"] for h, _ in self.received], ["Bearer first", "Bearer second"])

    def test_configuration_and_minimum_ocsf_fields(self):
        self.assertIsNone(siem.settings({}))
        for endpoint in ("http://127.0.0.1/", "http://remote.invalid/", "https://user:secret@remote.invalid/", "https://remote.invalid/?token=x", "https://remote.invalid/#secret"):
            with self.assertRaises(ValueError):
                siem.settings({"SIEM_URL": endpoint})
        payload = siem.event("approval_events", {**self.db.row, "kind": "contract-reapprove", "outcome": "approved", "scope": "private-scope"})
        self.assertEqual((payload["class_uid"], payload["type_uid"], payload["metadata"]["version"]), (0, 99, "1.4.0"))
        self.assertNotIn("private", json.dumps(payload))
        self.assertTrue({"category_uid", "class_uid", "activity_id", "type_uid", "severity_id", "time", "metadata"} <= payload.keys())
        with self.assertRaises(ValueError):
            siem.event("ops_alerts", {**self.db.row, "kind": "new-tool", "synthetic": True})
        alert = siem.event("ops_alerts", {**self.db.row, "kind": "new-tool", "synthetic": False})
        self.assertEqual(alert["unmapped"]["synthetic"], False)


if __name__ == "__main__":
    unittest.main()
