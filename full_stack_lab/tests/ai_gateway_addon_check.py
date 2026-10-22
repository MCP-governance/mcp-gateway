"""AI 게이트웨이 애드온(D-191) 단위 시험. DB·OPA·LiteLLM은 대역이며 실제 MCP·LiteLLM 실행 증거가 아니다.

    python tests/ai_gateway_addon_check.py        (게이트웨이 의존성이 설치된 파이썬)
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import types
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "full_stack_lab" / "gateway"
ADDON = ROOT / "addons" / "litellm"
sys.path.insert(0, str(APP))
os.environ["OTEL_SDK_DISABLED"] = "true"
from app import addon, core, endpoint_plane  # noqa: E402
from fastapi import HTTPException  # noqa: E402


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# LiteLLM이 없는 환경에서도 가드레일 로직을 시험하도록 기반 클래스만 대역으로 둔다.
base = types.ModuleType("litellm.integrations.custom_guardrail")
base.CustomGuardrail = type("CustomGuardrail", (), {"__init__": lambda self, **kw: None})
for dotted in ("litellm", "litellm.integrations"):
    sys.modules.setdefault(dotted, types.ModuleType(dotted))
sys.modules["litellm.integrations.custom_guardrail"] = base
os.environ["MINT_GATEWAY_URL"] = "https://mint.test"
guardrail_module = load("mint_guardrail", ADDON / "mint_guardrail.py")
generator = load("gen_mcp_servers", ADDON / "gen_mcp_servers.py")

EMPLOYEE = {"principal": "tok-alice", "roles": ["employee"], "claims": {"jti": "j1", "scope": "mcp", "client_id": "pc-1"}}
CONSOLE = {"principal": "tok-alice", "roles": ["employee"], "claims": {"jti": "j2", "scope": "console"}}


class GatewayDecideOnly(unittest.IsolatedAsyncioTestCase):
    async def run_call(self, policy):
        cls = SimpleNamespace(action="r", base_action="r", data_class="public", destinations=[], resources=[],
                              dlp=[], notes=[], restrictable=["max_chars"],
                              primary=SimpleNamespace(id="asset", kind="file", owner_department=None),
                              summary=lambda: "synthetic read")

        async def fetch(query, params=()):
            return {"role": "employee", "status": "active", "synthetic": True} if "principals" in query else None

        connection = SimpleNamespace(execute=AsyncMock())

        class Tx:
            async def __aenter__(self):
                return connection

            async def __aexit__(self, *exc):
                return False

        async def record(event, laps):
            return {**event, "decision_id": 7}

        upstream_call = AsyncMock()
        changes = [(core.db, {"fetch_one": AsyncMock(side_effect=fetch), "transaction": lambda: Tx()}),
                   (core.registry, {"server": Mock(return_value={"endpoint": "http://internal", "tool_reviews": {}}),
                                    "allowed_principals": Mock(return_value=None), "catalog_version": Mock(return_value="t")}),
                   (core.classify, {"classify": Mock(return_value=cls)}),
                   (endpoint_plane, {"managed_failure": AsyncMock(return_value=None),
                                     "shadow_count_for": AsyncMock(return_value=0),
                                     "shadow_listener_count_for": AsyncMock(return_value=0)}),
                   (core.pac, {"build": AsyncMock(return_value={}), "digest": Mock(return_value="d")}),
                   (core.privacy, {"analyze": AsyncMock(return_value=[])}),
                   (core.secret_scan, {"labels": AsyncMock(return_value=[])}),
                   (core.review, {"record_event": AsyncMock()}),
                   (core.tool_sunset, {"check": AsyncMock(return_value=None), "call_verdict": Mock(return_value=None)}),
                   (core, {"policy_ledger": AsyncMock(), "_reserve_call": AsyncMock(return_value={}),
                           "_privacy_ignore": Mock(return_value=None), "_contract": AsyncMock(return_value={}),
                           "_relationship_scope": AsyncMock(return_value={}), "_sequence_flags": AsyncMock(return_value=[]),
                           "_flow_sources": AsyncMock(return_value=[]), "_policy": AsyncMock(return_value=policy),
                           "enforcement_mode": AsyncMock(return_value="enforce"),
                           "_decision_payload": AsyncMock(side_effect=record), "_call_upstream": upstream_call})]
        with ExitStack() as stack:
            for target, attributes in changes:
                for name, value in attributes.items():
                    stack.enter_context(patch.object(target, name, value))
            result = await core.execute_call({"server_id": "context7", "tool": "resolve-library-id",
                                              "arguments": {"libraryName": "react"}, "user_token": "tok-alice",
                                              "_decide_only": True})
        return result, connection, upstream_call

    async def test_allow_is_judged_but_never_sent(self):
        result, _, upstream_call = await self.run_call({"decision": "Allow", "policy_id": "P-AUTHZ-ALLOW-001", "reason": "ok"})
        upstream_call.assert_not_awaited()
        self.assertEqual((result["decision"], result["policy_id"], result["decision_id"]), ("Allow", "P-AUTHZ-ALLOW-001", 7))
        self.assertFalse(result["upstream_attempted"])
        self.assertEqual(result["effective_arguments"], {"libraryName": "react"})

    async def test_approval_writes_no_pending_row_and_block_stays_block(self):
        result, connection, upstream_call = await self.run_call(
            {"decision": "Approval", "policy_id": "P-APPROVAL-001", "reason": "승인 필요"})
        self.assertEqual(result["decision"], "Approval")
        # 승인되면 MINT가 같은 호출을 한 번 더 보내므로 승인 대기 행을 만들지 않는다.
        self.assertFalse([c for c in connection.execute.await_args_list if "approvals" in str(c.args[0])])
        upstream_call.assert_not_awaited()
        result, _, upstream_call = await self.run_call({"decision": "Block", "policy_id": "MCP-REGISTRY-003", "reason": "x"})
        self.assertEqual((result["decision"], result["policy_id"]), ("Block", "MCP-REGISTRY-003"))
        upstream_call.assert_not_awaited()


class AddonRoutes(unittest.IsolatedAsyncioTestCase):
    request = {"server_id": "context7", "tool": "resolve-library-id", "arguments": {"libraryName": "react"},
               "gateway": "litellm", "asserted": {"user_id": "mallory"}, "call_ref": "c1"}

    async def decide(self, outcome, user=EMPLOYEE, request=None):
        executed = AsyncMock(return_value=outcome)
        with patch.object(core, "execute_call", executed):
            return await addon.decide(user, request or self.request), executed

    async def test_identity_is_the_token_and_assertion_is_only_recorded(self):
        verdict, executed = await self.decide({"decision": "Allow", "policy_id": "P", "decision_id": 7,
                                               "effective_arguments": self.request["arguments"]})
        payload = executed.await_args.args[0]
        self.assertEqual(payload["user_token"], "tok-alice")
        self.assertTrue(payload["_decide_only"])
        self.assertEqual(payload["client"]["asserted"], {"user_id": "mallory"})
        self.assertEqual(payload["client"]["ingress"], addon.INGRESS)
        self.assertTrue(verdict["allow"])
        self.assertIsNone(verdict["effective_arguments"])  # 바뀐 인자가 없으면 생략
        self.assertFalse(verdict["upstream_executed"])

    async def test_only_allow_family_with_a_recorded_decision_may_proceed(self):
        for decision, decision_id, allow in (("Allow", 1, True), ("Alert", 1, True), ("Restrict", 1, True),
                                             ("Approval", 1, False), ("Block", 1, False), ("Allow", None, False)):
            verdict, _ = await self.decide({"decision": decision, "policy_id": "P", "decision_id": decision_id})
            self.assertEqual(verdict["allow"], allow, (decision, decision_id))

    async def test_restricted_arguments_are_returned(self):
        verdict, _ = await self.decide({"decision": "Restrict", "policy_id": "P", "decision_id": 3,
                                        "effective_arguments": {"libraryName": "re"}})
        self.assertEqual(verdict["effective_arguments"], {"libraryName": "re"})

    async def test_console_token_cannot_act_as_an_employee(self):
        for call in (addon.decide(CONSOLE, self.request),
                     addon.record_result(CONSOLE, {"decision_id": 1, "outcome": "executed", "is_error": False})):
            with self.assertRaises(HTTPException) as caught:
                await call
            self.assertEqual(caught.exception.status_code, 403)

    async def test_result_attaches_only_to_own_addon_decision(self):
        result = {"decision_id": 7, "outcome": "executed", "is_error": False, "result_sha256": "a" * 64, "result_bytes": 5}
        record = AsyncMock(return_value=11)
        for row, recorded in (({"user_token": "tok-alice", "client": {"ingress": addon.INGRESS}}, True),
                              ({"user_token": "tok-bob", "client": {"ingress": addon.INGRESS}}, False),
                              ({"user_token": "tok-alice", "client": {"ingress": "mcp"}}, False), (None, False)):
            record.reset_mock()
            with patch.object(addon.db, "fetch_one", AsyncMock(return_value=row)), patch.object(addon.review, "record_event", record):
                answer = await addon.record_result(EMPLOYEE, result)
            self.assertEqual(answer["recorded"], recorded)
            self.assertEqual(record.await_count, 1 if recorded else 0)


class Guardrail(unittest.IsolatedAsyncioTestCase):
    def make(self, handler):
        guard = guardrail_module.MintGuardrail()
        guard._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.requests = []
        return guard

    def data(self, **extra):
        return {"mcp_tool_name": "resolve-library-id", "mcp_arguments": {"libraryName": "react"}, "mcp_server_name": "context7",
                "incoming_bearer_token": "tok-alice", "user_api_key_user_id": "mallory",
                "litellm_logging_obj": SimpleNamespace(litellm_call_id="call-1"), **extra}

    def reply(self, body, status=200):
        def handler(request):
            self.requests.append(request)
            return httpx.Response(status, json=body)
        return handler

    async def test_allow_passes_and_sends_employee_token_not_the_asserted_user(self):
        guard = self.make(self.reply({"allow": True, "decision": "Allow", "decision_id": 7, "effective_arguments": None}))
        data = self.data()
        self.assertIs(await guard.async_pre_call_hook(None, None, data, "call_mcp_tool"), data)
        request = self.requests[0]
        self.assertEqual(request.headers["authorization"], "Bearer tok-alice")
        body = json.loads(request.content)
        self.assertEqual((body["server_id"], body["tool"], body["asserted"]), ("context7", "resolve-library-id", {"user_id": "mallory"}))
        self.assertNotIn("modified_arguments", data)

    async def test_block_missing_token_and_every_failure_stop_the_call(self):
        cases = [(self.reply({"allow": False, "decision": "Block", "policy_id": "MCP-REGISTRY-003", "reason": "x"}), {}),
                 (self.reply({"allow": False, "decision": "Approval", "policy_id": "P-APPROVAL-001", "reason": "x"}), {}),
                 (self.reply({"detail": "no"}, 401), {}), (self.reply({"detail": "boom"}, 500), {}),
                 (lambda request: httpx.Response(200, content=b"not json"), {}),
                 (lambda request: (_ for _ in ()).throw(httpx.ConnectError("down")), {}),
                 (self.reply({"allow": True}), {"incoming_bearer_token": None})]
        for handler, extra in cases:
            guard = self.make(handler)
            with self.assertRaises(HTTPException) as caught:
                await guard.async_pre_call_hook(None, None, self.data(**extra), "call_mcp_tool")
            self.assertEqual(caught.exception.status_code, 403)

    async def test_non_mcp_call_is_left_alone_and_restriction_rewrites_arguments(self):
        guard = self.make(self.reply({"allow": True, "decision_id": 7, "effective_arguments": {"libraryName": "re"}}))
        llm = {"messages": []}
        self.assertIs(await guard.async_pre_call_hook(None, None, llm, "completion"), llm)
        self.assertEqual(self.requests, [])
        data = self.data()
        await guard.async_pre_call_hook(None, None, data, "call_mcp_tool")
        self.assertEqual(data["modified_arguments"], {"libraryName": "re"})

    async def test_post_hook_records_result_once_and_never_raises(self):
        guard = self.make(self.reply({"allow": True, "decision_id": 7}))
        await guard.async_pre_call_hook(None, None, self.data(), "call_mcp_tool")
        result = SimpleNamespace(isError=False, model_dump_json=lambda: '{"content":[]}')
        await guard.async_post_mcp_tool_call_hook({"litellm_call_id": "call-1"}, SimpleNamespace(mcp_tool_call_response=result), None, None)
        body = json.loads(self.requests[-1].content)
        self.assertEqual((self.requests[-1].url.path, body["decision_id"], body["outcome"], body["is_error"], body["result_bytes"]),
                         ("/api/addon/v1/mcp-result", 7, "executed", False, 14))
        count = len(self.requests)
        await guard.async_post_mcp_tool_call_hook({"litellm_call_id": "call-1"}, SimpleNamespace(mcp_tool_call_response=result), None, None)
        self.assertEqual(len(self.requests), count)  # 같은 호출은 한 번만 기록
        guard = self.make(lambda request: (_ for _ in ()).throw(httpx.ConnectError("down")))
        guard._pending["call-2"] = ("tok-alice", 8)
        self.assertIsNone(await guard.async_post_mcp_tool_call_hook({"litellm_call_id": "call-2"}, result, None, None))


class Generator(unittest.TestCase):
    def test_only_serving_servers_and_litellm_safe_alias(self):
        rows = [{"id": "context7", "status": "ACTIVE"}, {"id": "my-docs", "status": "ACTIVE", "lifecycle": "OPERATING"},
                {"id": "off", "status": "DISABLED"}, {"id": "bad", "status": "BLOCKED_SUPPLY_CHAIN"},
                {"id": "stopped", "status": "ACTIVE", "lifecycle": "STOPPED"}, {"id": "Bad Id", "status": "ACTIVE"},
                {"id": "unknown"}]
        ids = generator.serving(rows)
        self.assertEqual(ids, ["context7", "my-docs"])
        text = generator.render(ids, "https://mint.test/")
        self.assertIn("  my_docs:\n    url: https://mint.test/mcp/my-docs/\n", text)
        self.assertIn("auth_type: oauth_delegate", text)
        self.assertIn("x-mcp-my_docs-authorization", text)
        self.assertNotIn("Bearer sk-", text)  # 서비스 키를 싣지 않는다


if __name__ == "__main__":
    unittest.main()
