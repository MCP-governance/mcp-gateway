"""D-152: approval -> execution -> decision, with DB/HTTP unit doubles only.

Default loads production definitions with stdlib AST (no optional Gateway imports).
--gateway imports the installed Gateway instead. No real MCP/DB/OPA evidence.
"""
from __future__ import annotations

import ast
import asyncio
from contextlib import ExitStack, asynccontextmanager, nullcontext
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from types import ModuleType, SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, Mock, patch
import uuid

APP = Path(__file__).resolve().parents[1] / "gateway" / "app"
if not APP.exists():
    APP = Path("/app/app")
GATEWAY = "--gateway" in sys.argv
if GATEWAY:
    sys.argv.remove("--gateway")
    sys.path.insert(0, str(APP.parent))
    os.environ["OTEL_SDK_DISABLED"] = "true"
    from app import core as installed_core

UTC = timezone.utc


def production(filename, names, namespace):
    tree = ast.parse((APP / filename).read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if getattr(n, "name", None) in names]
    if len(nodes) != len(names):
        raise AssertionError("missing production definitions")
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(APP / filename), "exec"), namespace)
    return NS(**namespace)


digest = production("contract.py", {"canonical_hash"}, {"json": json, "hashlib": hashlib}).canonical_hash


class FreshRequesterChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.now = datetime.now(UTC)
        self.claims = {"sub": "employee-id", "iss": "issuer", "aud": "audience", "jti": str(uuid.uuid4()),
                       "nbf": (self.now - timedelta(minutes=1)).timestamp(),
                       "exp": (self.now + timedelta(minutes=4)).timestamp(), "scope": "mcp",
                       "device_id": "device", "device_epoch": 1, "device_policy": "policy"}
        self.payload = {"server_id": "existing-oss", "tool": "update", "arguments": {"value": "synthetic"},
                        "user_token": "employee", "transport_claims": self.claims}
        self.row = {"id": "approval", "status": "PENDING", "requested_by": "employee", "reviewed_by": "admin",
                    "request_payload": self.payload, "request_fingerprint": digest(self.payload),
                    "created_at": self.now, "expires_at": self.now + timedelta(minutes=10)}
        self.person = {"token": "employee", "user_id": "employee-id", "role": "employee", "status": "active",
                       "synthetic": True, "managed_required": True}
        self.device = {"owner_token": "employee", "status": "active", "managed_state": "active", "device_epoch": 1,
                       "heartbeat_at": self.now, "policy_hash": "policy"}
        self.revoked, self.signed_block, self.revocation_error = False, False, False
        self.after_approval = lambda: None
        self.after_discovery = lambda: None
        self.view = {"description": "synthetic contract", "input_schema": {"type": "object"}}
        self.tool = {"name": "update", "enabled": True, "input_schema": self.view["input_schema"],
                     "approved_description_hash": digest(self.view["description"]),
                     "approved_schema_hash": digest(self.view["input_schema"]), "approved_server_version": "pinned"}
        self.db = NS(fetch_one=AsyncMock(side_effect=self.fetch), fetch_all=AsyncMock(return_value=[self.tool]),
                     execute=AsyncMock(return_value=1))
        self.connection = NS(execute=AsyncMock(side_effect=self.claim_approval))

        @asynccontextmanager
        async def transaction():
            yield self.connection
        self.db.transaction = transaction
        self.client = NS(call_tool=AsyncMock(return_value=NS(is_error=False, structured_content=None)))

        @asynccontextmanager
        async def session(*args, **kwargs):
            yield self.client

        async def list_tools(*args):
            self.after_discovery()
            return [NS(name="update")]

        self.upstream = NS(session=session, list_all_tools=AsyncMock(side_effect=list_tools), tool_view=lambda _: self.view,
            release_pool=AsyncMock(), content_items=lambda _: [], CONNECT_TIMEOUT=30,
            CredentialUnavailable=type("CredentialUnavailable", (Exception,), {}))
        self.disposal = NS(blocked=Mock(side_effect=lambda **kw: self.signed_block))
        self.dispatch = NS(record=AsyncMock(return_value=None))
        self.endpoint = ModuleType("fresh_requester_unit.endpoint_plane")
        endpoint = production("endpoint_plane.py", {"managed_failure"}, {"db": self.db, "datetime": datetime,
            "UTC": UTC, "HEARTBEAT_SECONDS": 180, "managed_policy": AsyncMock(return_value={"policy_hash": "policy"})})
        self.endpoint.managed_failure = endpoint.managed_failure
        self.endpoint.shadow_count_for = AsyncMock(return_value=0)
        self.endpoint.shadow_listener_count_for = AsyncMock(return_value=0)
        registry = NS(server=lambda _: {"endpoint": "http://unit.invalid", "tool_reviews": {}},
                      allowed_principals=lambda _: None, pinned_protocol=lambda _: "pinned",
                      catalog_version=lambda: "unit", review_matches=lambda *args: True,
                      catalog=lambda: {"organization": {}})
        scope = {"allowed": True, "resources_allowed": True, "actions": ["w"], "environments": ["prod"],
                 "valid_from": (self.now - timedelta(minutes=1)).isoformat(),
                 "valid_until": (self.now + timedelta(minutes=10)).isoformat()}
        validator = lambda _: NS(is_valid=lambda value: isinstance(value, dict))
        self.pac = production("pac.py", {"build", "ns", "leaves"}, {"db": self.db, "datetime": datetime,
            "time": time, "registry": registry, "ISSUER": "issuer", "AUDIENCE": "audience", "VERSION": "pac15-v1",
            "BROKER": "broker", "scope": lambda *args: scope, "capabilities": lambda: {"execution_profile": {}},
            "delegation": lambda _: {"asserted": False}, "Draft202012Validator": validator, "canonical_hash": digest,
            "Jsonb": lambda v: v, "residency": NS(facts=lambda *args: {}, load_pack=lambda: {}),
            "transfer_binding": lambda *args: (False, [])})
        cls = NS(server="existing-oss", tool="update", action="w", base_action="w", data_class="public", destinations=[],
                 resources=[], dlp=[], notes=[], restrictable=[], primary=NS(id="asset", kind="record", owner_department=None),
                 summary=lambda: "synthetic update")
        classifier = NS(classify=lambda *args: cls, url_destination=lambda _: NS(external=False),
                        apply_restrictions=lambda cls, args, rules: (args, []), remember_navigation=Mock())
        self.ledger = AsyncMock(side_effect=lambda event: 91)
        span = NS(get_span_context=lambda: NS(trace_id=1), set_attribute=Mock(), record_exception=Mock())
        self.ns = {"__package__": "fresh_requester_unit", "asyncio": NS(to_thread=asyncio.to_thread, timeout=lambda _: nullcontext()),
            "json": json, "uuid": uuid, "time": time, "datetime": datetime, "UTC": UTC, "Any": object,
            "canonical_hash": digest, "db": self.db, "disposal": self.disposal, "dispatch": self.dispatch,
            "tool_sunset": NS(check=AsyncMock(return_value={}), call_verdict=lambda state: None), "upstream": self.upstream, "endpoint_plane": self.endpoint, "registry": registry, "classify": classifier,
            "pac": self.pac, "Draft202012Validator": validator, "_ledger_cache": {}, "GATEWAY_ENVIRONMENT": "prod",
            "output_contract": NS(matches=lambda *args: True, for_protocol=lambda value, _: value),
            "poisoning": NS(findings=lambda _: []), "privacy": NS(analyze=AsyncMock(return_value=[]),
                InspectionUnavailable=type("InspectionUnavailable", (Exception,), {})),
            "secret_scan": NS(labels=AsyncMock(return_value=[])), "tracer": NS(start_as_current_span=lambda *args, **kw: nullcontext(span)),
            "review": NS(require_independent=AsyncMock(), record_event=AsyncMock(side_effect=self.approved),
                         NotIndependent=type("NotIndependent", (Exception,), {})),
            "policy_ledger": AsyncMock(), "_privacy_ignore": lambda _: None, "_outbound_text": json.dumps,
            "_decoded_strings": lambda _: [], "untrusted_markers": lambda _: [], "_risk_score": lambda *args: 0,
            "_sequence_flags": AsyncMock(return_value=[]), "_flow_sources": AsyncMock(return_value=[]),
            "flow_fingerprint": NS(leaf_text=lambda *args, **kw: []), "FLOW_MATCH_MODE": "coarse",
            "_contract": AsyncMock(return_value={"lifecycle": "OPERATING", "enabled": True}),
            "_relationship_scope": AsyncMock(return_value={}), "_reserve_call": AsyncMock(return_value={
                "duplicate_in_flight": False, "active_calls": 1, "recent_calls": 0, "execution_timeout_ms": 1000}),
            "enforcement_mode": AsyncMock(return_value="enforce"), "_policy": AsyncMock(side_effect=self.policy),
            "_dispatch_flow_recheck": AsyncMock(return_value=None), "_record_decision": self.ledger, "_release_call": AsyncMock(),
            "_guarded_result": lambda value, *args: value, "_validate_output": lambda *args: None,
            "_inspected_result": AsyncMock(return_value=({"content": [], "is_error": False}, [])),
            "response_evidence": lambda *args: {}, "refresh_catalog": AsyncMock(),
            "_root_cause": lambda exc: type(exc).__name__, "MAX_ARGUMENT_BYTES": 10000,
            "RESERVATION_TTL_SECONDS": 120, "OUTPUT_INSPECTION_TIMEOUT_SECONDS": 10}
        names = {"approve_request", "execute_call", "_call_upstream", "_decision_payload", "local_verdict", "_Laps", "DispatchRejected"}
        if GATEWAY:
            from app import endpoint_plane
            self.stack = ExitStack()
            self.addCleanup(self.stack.close)
            self.stack.enter_context(patch.object(endpoint_plane, "managed_failure", self.endpoint.managed_failure))
            for name, value in self.ns.items():
                if hasattr(installed_core, name) and name not in {"__package__", "asyncio"}:
                    self.stack.enter_context(patch.object(installed_core, name, value))
            self.core = installed_core
        else:
            self.core = production("core.py", names, self.ns)
            package = ModuleType("fresh_requester_unit")
            package.__path__ = []
            modules = patch.dict(sys.modules, {"fresh_requester_unit": package,
                                              "fresh_requester_unit.endpoint_plane": self.endpoint})
            modules.start()
            self.addCleanup(modules.stop)

    async def fetch(self, query, params=()):
        if "agent_revoked_tokens" in query:
            self.assertEqual(params, (self.claims["jti"],))
            if self.revocation_error:
                raise OSError("revocation store unavailable")
            return {"jti": self.claims["jti"]} if self.revoked else None
        if "principals" in query:
            return ({"role": "admin", "status": "active", "user_id": "admin-id"}
                    if params == ("admin",) else self.person)
        if "endpoint_agents" in query:
            return self.device
        if "approvals" in query:
            return self.row
        if "mcp_tools" in query:
            return self.tool
        if "call_reservations" in query:
            return {"released_at": None, "expires_at": self.now + timedelta(minutes=2)}
        if "decisions" in query:
            return None
        raise AssertionError("unexpected SQL: " + query)

    async def claim_approval(self, query, params=()):
        self.assertIn("status='APPROVED'", query)
        self.row["status"] = "APPROVED"
        return NS(fetchone=AsyncMock(return_value=self.row))

    async def approved(self, *args, **kwargs):
        self.assertEqual(args[:2], ("call-approve", "approved"))
        self.after_approval()

    async def policy(self, document):
        # OPA HTTP double: verify the real PAC builder's temporal facts before returning a denial.
        auth = document["pac"]["facts"]["auth"]
        return self.core.local_verdict("P-AUTHZ-ALLOW-001", "Allow", "unit") if auth["verified"] else self.core.local_verdict(
            "PAC-04", "Block", "unit: invalid transport identity")

    async def run_approval(self):
        original = deepcopy(self.payload)
        result = await self.core.approve_request("approval", "admin")
        self.assertEqual(self.payload, original)
        self.ledger.assert_awaited_once()
        event = self.ledger.await_args.args[0]
        self.assertEqual((event["decision"], event["policy_id"]), (result["decision"], result["policy_id"]))
        self.assertEqual(event["approval_id"], "approval")
        self.assertEqual(event["user_token"], "employee")
        self.assertEqual(self.db.execute.await_args.args[1], (
            "EXECUTED" if result["upstream_executed"] else "NOT_EXECUTED", 91, "approval"))
        return result

    async def blocked(self, policy):
        result = await self.run_approval()
        self.assertEqual((result["decision"], result["policy_id"]), ("Block", policy))
        self.assertFalse(result["upstream_attempted"])
        self.assertFalse(result["upstream_executed"])
        self.client.call_tool.assert_not_awaited()
        self.dispatch.record.assert_not_awaited()
        return result

    async def test_jti_revoked_after_approval_before_dispatch(self):
        self.after_discovery = lambda: setattr(self, "revoked", True)
        await self.blocked("P-INPUT-001")
        self.disposal.blocked.assert_called_once_with(jti=self.claims["jti"], raise_errors=True)

    async def test_signed_disposal_blocks_without_database_revocation(self):
        self.after_discovery = lambda: setattr(self, "signed_block", True)
        await self.blocked("P-INPUT-001")
        self.assertFalse(self.revoked)

    async def test_isolated_device_after_approval(self):
        self.after_discovery = lambda: self.device.update(managed_state="quarantined")
        await self.blocked("ENDPOINT-MANAGED-001")

    async def test_subject_disabled_after_approval(self):
        self.after_approval = lambda: self.person.update(status="disabled")
        await self.blocked("P-INPUT-001")

    async def test_expired_token_keeps_original_pac_denial(self):
        self.claims["exp"] = (self.now - timedelta(seconds=1)).timestamp()
        self.row["request_fingerprint"] = digest(self.payload)
        result = await self.blocked("PAC-04")
        auth = result["policy_input"]["pac"]["facts"]["auth"]
        self.assertFalse(auth["verified"])
        self.assertLess(auth["valid_until_ns"], result["policy_input"]["pac"]["facts"]["now_ns"])

    async def test_token_expires_during_discovery(self):
        original_build = self.pac.build
        async def build(*args):
            document = await original_build(*args)
            if self.disposal.blocked.called:
                self.assertFalse(document["facts"]["auth"]["verified"])
            return document
        self.pac.build = AsyncMock(side_effect=build)
        fixed = self.now.timestamp()
        self.claims["exp"] = fixed + 1
        self.row["request_fingerprint"] = digest(self.payload)
        self.after_discovery = lambda: clock.__setitem__(0, fixed + 1)
        clock = [fixed]
        # Equality is expired, with no elapsed-time sleep or change to saved claims.
        with patch.object(time, "time_ns", side_effect=lambda: int(clock[0] * 1_000_000_000)):
            await self.blocked("PAC-04")
        self.assertEqual(self.pac.build.await_count, 2)

    async def test_revocation_database_failure_is_fail_closed(self):
        self.after_discovery = lambda: setattr(self, "revocation_error", True)
        await self.blocked("P-CONTROL-FAIL-CLOSED")

    async def test_disposal_read_exception_is_fail_closed(self):
        self.disposal.blocked.side_effect = OSError("signed list unavailable")
        await self.blocked("P-CONTROL-FAIL-CLOSED")
        self.disposal.blocked.assert_called_once_with(jti=self.claims["jti"], raise_errors=True)

    async def test_healthy_requester_executes_once_on_approval(self):
        result = await self.run_approval()
        self.assertEqual((result["decision"], result["policy_id"]), ("Allow", "P-AUTHZ-ALLOW-001"))
        self.assertTrue(result["upstream_executed"])
        self.assertTrue(result["upstream_attempted"])
        self.client.call_tool.assert_awaited_once_with("update", self.payload["arguments"])
        self.dispatch.record.assert_awaited_once()
        self.disposal.blocked.assert_called_once_with(jti=self.claims["jti"], raise_errors=True)


class DisposalFailureChecks(unittest.TestCase):
    def test_blocked_preserves_default_fail_closed_and_can_surface_failure(self):
        blocked = production("disposal.py", {"blocked"}, {
            "DIRECTORY": Path("unused"), "IntegrityError": type("IntegrityError", (RuntimeError,), {}),
            "locked": lambda _: nullcontext(), "read": Mock(side_effect=OSError("unavailable"))}).blocked
        self.assertTrue(blocked(jti="requester"))
        with self.assertRaisesRegex(OSError, "unavailable"):
            blocked(jti="requester", raise_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
