"""D-115 unit evidence only: fake functions/objects, no MCP server, database or network.

python -m unittest discover -s full_stack_lab/tests -p upstream_session_reuse_test.py -v
The SDK/DB adapters and core dependencies are substituted; the production pool and
selected production function bodies execute unchanged, including on Python 3.10.
"""
from __future__ import annotations

import ast
import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timezone, timedelta
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch


APP = Path(__file__).resolve().parents[1] / "gateway" / "app"


def functions(file, names, namespace):
    tree = ast.parse((APP / file).read_text(encoding="utf-8"))
    selected = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and node.name in names]
    assert len(selected) == len(names)
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(APP / file), "exec"), namespace)
    return namespace


spec = importlib.util.spec_from_file_location("stage2_sessions", APP / "upstream_sessions.py")
sessions = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = sessions
spec.loader.exec_module(sessions)


def key(**kwargs):
    return replace(sessions.Key("alice", ("chat-a", "jwt-a"), "server-a", "hash-a",
                                "https://a.example/mcp", "2025-11-25", 90), **kwargs)


class PoolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.pool = sessions.Pool(size=8)
        self.opened, self.closed = [], []

    async def asyncTearDown(self):
        await self.pool.close()

    @asynccontextmanager
    async def factory(self):
        task = asyncio.current_task()
        client = NS(list_tools=AsyncMock(return_value="listed"),
                    call_tool=AsyncMock(side_effect=lambda arg: NS(value=arg, is_error=False)))
        self.opened.append(client)
        try:
            yield client
        finally:
            self.assertIs(asyncio.current_task(), task)
            self.closed.append(client)

    async def test_T1_reuse_without_reopening(self):
        for index in range(20):
            async with self.pool.borrow(key(), self.factory) as lease:
                self.assertEqual(lease.reused, index > 0)
                self.assertEqual(await lease.list_tools(), "listed")
        self.assertEqual(len(self.opened), 1)
        self.assertEqual(self.opened[0].list_tools.await_count, 20)
        self.assertFalse(self.closed)

    async def test_T2_T3_every_key_boundary_is_separate(self):
        cases = [key(), key(principal="bob"), key(downstream=("chat-b", "jwt-a")),
                 key(downstream=("chat-a", "jwt-b")), key(server="server-b")]
        for item in cases:
            async with self.pool.borrow(item, self.factory):
                pass
        self.assertEqual(len(self.opened), len(cases))
        self.assertEqual(len(self.pool.entries), len(cases))

    async def test_T4_T5_close_active_and_refuse_waiter(self):
        async with self.pool.borrow(key(), self.factory) as lease:
            async def waiter():
                async with self.pool.borrow(key(), self.factory):
                    self.fail("revoked waiter created or borrowed a session")
            waiting = asyncio.create_task(waiter())
            await asyncio.sleep(0)
            self.assertEqual(await self.pool.close(principal="alice"), 1)
            with self.assertRaises(sessions.Closed):
                await lease.call_tool("blocked")
            with self.assertRaises(sessions.Closed):
                await waiting
        self.assertEqual(len(self.closed), 1)

    async def test_T5_endpoint_and_downstream_closure_are_scoped(self):
        for item in [key(), key(principal="bob"), key(server="b", endpoint="https://b.example/mcp")]:
            async with self.pool.borrow(item, self.factory):
                pass
        self.assertEqual(await self.pool.close(principal="alice", conversation=sessions.conversation_id(key().downstream)), 2)
        self.assertEqual([item.principal for item in self.pool.entries], ["bob"])
        self.assertEqual(await self.pool.close(endpoint=key().endpoint), 1)

    async def test_T6_rotation_retires_all_old_conversations(self):
        for item in [key(), key(downstream=("b", "jwt-a"))]:
            async with self.pool.borrow(item, self.factory):
                pass
        async with self.pool.borrow(key(credential="hash-new"), self.factory):
            pass
        self.assertEqual(len(self.closed), 2)
        self.assertEqual([item.credential for item in self.pool.entries], ["hash-new"])

    async def test_configuration_change_retires_old_session(self):
        for item in [key(), key(endpoint="https://new.example/mcp"), key(protocol="2025-06-18"), key(timeout=30), key(internal=True)]:
            async with self.pool.borrow(item, self.factory):
                pass
        self.assertEqual(len(self.opened), 5)
        self.assertEqual(len(self.closed), 4)

    async def test_T6_rotation_during_borrow_prevents_send(self):
        valid = True
        async with self.pool.borrow(key(), self.factory, lambda: valid) as lease:
            valid = False
            with self.assertRaises(sessions.Closed):
                await lease.call_tool("blocked")
        self.opened[0].call_tool.assert_not_awaited()
        self.assertEqual(len(self.closed), 1)

    async def test_T9_ten_concurrent_calls_serialize_one_session(self):
        active, peak = 0, 0
        async def call(n):
            nonlocal active, peak
            async with self.pool.borrow(key(), self.factory) as lease:
                active += 1
                peak = max(peak, active)
                await asyncio.sleep(0)
                result = await lease.call_tool(n)
                active -= 1
                return result.value
        self.assertEqual(await asyncio.gather(*(call(n) for n in range(10))), list(range(10)))
        self.assertEqual((peak, len(self.opened)), (1, 1))

    async def test_expiry_idle_and_maximum_lifetime(self):
        async with self.pool.borrow(key(), self.factory) as lease:
            pass
        lease.used -= 61
        await self.pool.prune()
        self.assertTrue(lease.evicted)
        async with self.pool.borrow(key(), self.factory) as active:
            active.born -= 601
            await self.pool.prune()
            with self.assertRaises(sessions.Closed):
                await active.call_tool("blocked")
        self.assertEqual(len(self.closed), 2)

    async def test_capacity_evicts_idle_not_active(self):
        self.pool.size = 1
        async with self.pool.borrow(key(), self.factory):
            pass
        async with self.pool.borrow(key(principal="bob"), self.factory):
            self.assertEqual(len(self.pool.entries), 1)
        self.assertEqual(len(self.closed), 1)

    async def test_T10_error_and_cancellation_discard(self):
        with self.assertRaises(ValueError):
            async with self.pool.borrow(key(), self.factory):
                raise ValueError("unit failure")
        entered = asyncio.Event()
        async def caller():
            async with self.pool.borrow(key(), self.factory):
                entered.set()
                await asyncio.Event().wait()
        task = asyncio.create_task(caller())
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(self.pool.entries)
        self.assertEqual(len(self.closed), 2)

    async def test_tool_error_is_definite_response_but_session_is_discarded(self):
        async with self.pool.borrow(key(), self.factory) as lease:
            self.opened[-1].call_tool.side_effect = None
            self.opened[-1].call_tool.return_value = NS(is_error=True)
            self.assertTrue((await lease.call_tool("tool-error")).is_error)
        self.assertFalse(self.pool.entries)
        self.assertEqual(len(self.closed), 1)

    async def test_opening_failure_is_closed_not_success(self):
        @asynccontextmanager
        async def broken():
            raise ValueError("unit failure")
            yield
        with self.assertRaises(sessions.Closed):
            async with self.pool.borrow(key(), broken):
                self.fail("opening failed")
        self.assertFalse(self.pool.entries)

    async def test_close_while_opening_unblocks_borrower(self):
        opening = asyncio.Event()
        @asynccontextmanager
        async def slow():
            opening.set()
            await asyncio.Event().wait()
            yield
        async def call():
            async with self.pool.borrow(key(), slow):
                self.fail("closed opening yielded")
        task = asyncio.create_task(call())
        await opening.wait()
        await self.pool.close(principal="alice")
        with self.assertRaises(sessions.Closed):
            await asyncio.wait_for(task, 1)

    async def test_revocation_during_rotation_cleanup_prevents_reopen(self):
        closing, finish = asyncio.Event(), asyncio.Event()
        @asynccontextmanager
        async def held_close():
            try:
                yield object()
            finally:
                closing.set()
                await finish.wait()
        async with self.pool.borrow(key(), held_close):
            pass
        async def rotate():
            async with self.pool.borrow(key(credential="new"), self.factory):
                self.fail("revoked acquisition reopened")
        task = asyncio.create_task(rotate())
        await closing.wait()
        await self.pool.close(principal="alice")
        finish.set()
        with self.assertRaises(sessions.Closed):
            await task
        self.assertFalse(self.opened)

    async def test_slow_idle_eviction_does_not_hold_revocation_lock(self):
        self.pool.size = 2
        closing, finish = asyncio.Event(), asyncio.Event()
        @asynccontextmanager
        async def slow_close():
            try:
                yield object()
            finally:
                closing.set()
                await finish.wait()
        async with self.pool.borrow(key(), self.factory) as active:
            async with self.pool.borrow(key(principal="bob"), slow_close):
                pass
            async def acquire():
                async with self.pool.borrow(key(principal="carol"), self.factory):
                    self.fail("acquisition resumed across a revocation")
            task = asyncio.create_task(acquire())
            try:
                await closing.wait()
                await asyncio.wait_for(self.pool.close(principal="alice"), 1)
                self.assertTrue(active.evicted)
            finally:
                finish.set()
            with self.assertRaises(sessions.Closed):
                await task


class WiringTests(unittest.IsolatedAsyncioTestCase):
    def upstream_functions(self):
        return functions("upstream.py", {"session", "_session", "ContractClient", "connect_mode", "list_all_tools", "credential_hash", "_sweep", "close_pool", "close_downstream", "release_pool", "maintain_pool"}, {
            "asynccontextmanager": asynccontextmanager, "AsyncExitStack": __import__("contextlib").AsyncExitStack,
            "CONNECT_TIMEOUT": 90, "HANDSHAKE_PROTOCOL_VERSIONS": {"2025-11-25"},
            "MODERN_PROTOCOL_VERSIONS": {"2026-07-28"}, "Client": object, "MAX_TOOL_PAGES": 50,
            "hashlib": hashlib, "json": json, "upstream_sessions": sessions, "_sessions": sessions.Pool(),
            "_dispatch_allowed": AsyncMock(return_value=True), "asyncio": asyncio,
            "_sweep_lock": asyncio.Lock(), "_connected": {}, "refresh_connected": AsyncMock(),
            "_internal_endpoint": AsyncMock(return_value=False),
        })

    async def test_T7_every_page_bypasses_positive_ttl_cache(self):
        ns = self.upstream_functions()
        sent = []
        async def listing(cursor=None, cache_mode="use"):
            self.assertEqual(cache_mode, "bypass")
            sent.append(cursor)
            return NS(tools=[len(sent)], next_cursor="next" if cursor is None else None, ttl_ms=60000)
        client = NS(list_tools=listing)
        self.assertEqual(await ns["list_all_tools"](client), [1, 2])
        self.assertEqual(await ns["list_all_tools"](client), [3, 4])
        self.assertEqual(sent, [None, "next", None, "next"])

    async def test_T1_T7_sdk_cache_none_and_operator_headers_only(self):
        ns = self.upstream_functions()
        configs, transport_headers = [], []
        @asynccontextmanager
        async def http_client(timeout, headers, endpoint, internal):
            self.assertEqual((endpoint, internal), ("https://a.example/mcp", False))
            transport_headers.append(headers)
            yield object()
        @asynccontextmanager
        async def sdk_client(transport, **kwargs):
            configs.append(kwargs)
            yield object()
        ns.update(_client=http_client, Client=sdk_client, streamable_http_client=lambda *a, **kw: object())
        async with ns["_session"]("https://a.example/mcp", 90, None, "2025-11-25", {"Authorization": "Bearer operator"}, False):
            pass
        self.assertIsNone(configs[0]["cache"])
        self.assertEqual(configs[0]["mode"], "legacy")
        self.assertEqual(transport_headers, [{"Authorization": "Bearer operator"}])

    async def test_legacy_only_reuse_and_no_downstream_fallback(self):
        ns = self.upstream_functions()
        opened, closed = [], []
        @asynccontextmanager
        async def factory(*args):
            opened.append(args)
            try:
                yield object()
            finally:
                closed.append(args)
        ns.update(_session=factory, credential_headers=lambda *args: {}, _sweep=AsyncMock())
        token = sessions.downstream.set(("chat", "jwt"))
        try:
            for protocol, server_id in [("2025-11-25", "a"), ("2025-11-25", "a"),
                                        ("2026-07-28", "a"), (None, "a"), ("2025-11-25", None)]:
                async with ns["session"]("https://a.example/mcp", principal="alice", protocol=protocol, server_id=server_id):
                    pass
            self.assertEqual(len(opened), 4)
            sessions.downstream.set(None)
            async with ns["session"]("https://a.example/mcp", principal="alice", protocol="2025-11-25", server_id="a"):
                pass
            self.assertEqual(len(opened), 5)
        finally:
            sessions.downstream.reset(token)
            await ns["_sessions"].close()
        self.assertEqual(len(closed), 5)

    async def test_A_internal_classification_reaches_raw_and_pooled_transports(self):
        ns = self.upstream_functions()
        seen = []
        @asynccontextmanager
        async def http_client(timeout, headers, endpoint, internal):
            seen.append((endpoint, internal))
            yield object()
        @asynccontextmanager
        async def dispatch_client(endpoint, principal, headers, timeout, internal):
            seen.append((endpoint, internal, principal))
            yield object()
        @asynccontextmanager
        async def sdk_client(*args, **kwargs):
            yield object()
        ns.update(_client=http_client, _dispatch_client=dispatch_client, Client=sdk_client,
                  streamable_http_client=lambda *args, **kwargs: object())
        for principal in (None, "alice"):
            async with ns["_session"]("https://a.example/mcp", 90, principal, "2025-11-25", {}, True):
                pass
        self.assertEqual(seen, [("https://a.example/mcp", True), ("https://a.example/mcp", True, "alice")])

    async def test_A_internal_classification_change_cannot_reuse_old_MCP_session(self):
        ns = self.upstream_functions()
        opened, closed = [], []
        @asynccontextmanager
        async def factory(*args):
            opened.append(args[-1])
            try:
                yield object()
            finally:
                closed.append(args[-1])
        ns.update(_sweep=AsyncMock(), credential_headers=lambda *args: {}, _session=factory)
        token = sessions.downstream.set(("chat", "jwt"))
        try:
            for internal in (True, False):
                ns["_internal_endpoint"].return_value = internal
                async with ns["session"]("https://a.example/mcp", principal="alice", server_id="a", protocol="2025-11-25"):
                    pass
            self.assertEqual(opened, [True, False])
            self.assertEqual(closed, [True])
        finally:
            sessions.downstream.reset(token)
            await ns["_sessions"].close()

    async def test_T11_initial_cursor_skips_prestart_events_before_any_session(self):
        ns = self.upstream_functions()
        close = AsyncMock()
        ns.update(_swept={"at": 0, "id": None}, SWEEP_SECONDS=2, time=NS(monotonic=lambda: 10), close_pool=close,
                  db=NS(fetch_one=AsyncMock(return_value={"last": 5}), fetch_all=AsyncMock()))
        await ns["_sweep"]()
        close.assert_not_awaited()
        ns["db"].fetch_all.assert_not_awaited()
        self.assertEqual(ns["_swept"]["id"], 5)

    async def test_T11_initialization_failure_refuses_to_open(self):
        ns = self.upstream_functions()
        ns.update(_swept={"at": 0, "id": None}, SWEEP_SECONDS=2, time=NS(monotonic=lambda: 10),
                  db=NS(fetch_one=AsyncMock(side_effect=RuntimeError("unit failure"))))
        with self.assertRaises(RuntimeError):
            await ns["_sweep"]()
        self.assertIsNone(ns["_swept"]["id"])

    async def test_T11_first_dispatches_wait_for_initial_cursor_then_apply_new_event(self):
        ns = self.upstream_functions()
        entered, finish = asyncio.Event(), asyncio.Event()
        async def initial(*args):
            entered.set()
            await finish.wait()
            return {"last": 5}
        clock = NS(value=10)
        close = AsyncMock()
        ns.update(_swept={"at": 0, "id": None}, SWEEP_SECONDS=2, time=NS(monotonic=lambda: clock.value),
                  close_pool=close, db=NS(fetch_one=AsyncMock(side_effect=initial), fetch_all=AsyncMock(return_value=[
                      {"id": 6, "endpoint": "a", "principal": "alice", "reason": "principal"}])))
        first = asyncio.create_task(ns["_sweep"]())
        await entered.wait()
        second = asyncio.create_task(ns["_sweep"]())
        await asyncio.sleep(0)
        self.assertFalse(second.done())
        finish.set()
        await asyncio.gather(first, second)
        self.assertEqual(ns["db"].fetch_one.await_count, 1)
        close.assert_not_awaited()
        clock.value = 13
        await ns["_sweep"]()
        ns["db"].fetch_all.assert_awaited_once()
        self.assertEqual(ns["db"].fetch_all.await_args.args[1], (5,))
        close.assert_awaited_once_with("a", "alice")

    async def test_T11_failed_close_does_not_advance_cursor(self):
        ns = self.upstream_functions()
        ns.update(_swept={"at": 0, "id": 3}, SWEEP_SECONDS=2, time=NS(monotonic=lambda: 10),
                  close_pool=AsyncMock(side_effect=RuntimeError("unit failure")),
                  db=NS(fetch_all=AsyncMock(return_value=[{"id": 5, "endpoint": "a", "principal": "alice", "reason": "principal"}])))
        await ns["_sweep"]()
        self.assertEqual(ns["_swept"]["id"], 3)

    def test_conversation_uses_transport_session_and_verified_jti(self):
        ns = functions("mcp_facade.py", {"_conversation", "_headers"}, {"Any": object, "HANDSHAKE_PROTOCOL_VERSIONS": {"2025-11-25"}})
        ctx = NS(protocol_version="2025-11-25", request=NS(headers={"mcp-session-id": "chat"}))
        self.assertEqual(ns["_conversation"](ctx, {"claims": {"jti": "verified"}}), ("chat", "verified"))
        self.assertIsNone(ns["_conversation"](ctx, {"claims": {}}))
        ctx.protocol_version = "2026-07-28"
        self.assertIsNone(ns["_conversation"](ctx, {"claims": {"jti": "verified"}}))

    def test_T12_pinned_generation_and_unknown_version(self):
        mode = self.upstream_functions()["connect_mode"]
        self.assertEqual(mode("2025-11-25"), "legacy")
        self.assertEqual(mode("2026-07-28"), "2026-07-28")
        self.assertEqual(mode(None), "auto")
        self.assertEqual(mode("unknown"), "auto")

    async def test_session_does_not_replace_authoritative_policy_checks(self):
        ns = self.upstream_functions()
        @asynccontextmanager
        async def factory(*args):
            yield object()
        ns.update(_sweep=AsyncMock(), _dispatch_allowed=AsyncMock(return_value=False),
                  close_pool=AsyncMock(), credential_headers=lambda *args: {}, _session=factory)
        async with ns["session"]("a", principal="alice", server_id="a", protocol="2025-11-25"):
            pass
        ns["_dispatch_allowed"].assert_not_awaited()

    async def test_maintenance_closes_rotation_revocation_and_expiry_without_new_call(self):
        for changed, valid in [(True, True), (False, False), (False, True)]:
            with self.subTest(changed=changed, valid=valid):
                ns = self.upstream_functions()
                prune, close = AsyncMock(), AsyncMock()
                ns.update(_sweep=AsyncMock(), _sessions=NS(entries={key(): object()}, prune=prune),
                          credential_headers=lambda *a: {}, credential_hash=lambda headers: "changed" if changed else "hash-a",
                          _dispatch_allowed=AsyncMock(return_value=valid), close_pool=close, SWEEP_SECONDS=2,
                          asyncio=NS(sleep=AsyncMock(side_effect=asyncio.CancelledError)))
                with self.assertRaises(asyncio.CancelledError):
                    await ns["maintain_pool"]()
                self.assertEqual(close.await_count, 1 if changed or not valid else 0)
                prune.assert_awaited_once()

    async def test_T11_downstream_event_only_closes_matching_conversation(self):
        ns = self.upstream_functions()
        close = AsyncMock()
        ns.update(_swept={"at": 0, "id": 0}, SWEEP_SECONDS=2, time=NS(monotonic=lambda: 10),
                  _sessions=NS(close=close),
                  db=NS(fetch_all=AsyncMock(return_value=[{"id": 2, "endpoint": None, "principal": "alice", "reason": "downstream:digest"}])))
        await ns["_sweep"]()
        close.assert_awaited_once_with(principal="alice", conversation="digest")

    async def test_successful_delete_closes_and_failed_delete_preserves_session(self):
        for status in (200, 202, 204, 404, 405):
            with self.subTest(status=status):
                close = AsyncMock()
                async def app(scope, receive, send):
                    await send({"type": "http.response.start", "status": status})
                user = {"principal": "alice", "claims": {"jti": "verified"}}
                ns = functions("main.py", {"RequireBearer"}, {
                    "authenticated_user": AsyncMock(return_value=user), "upstream": NS(close_downstream=close),
                    "HTTPException": type("HTTPException", (Exception,), {}),
                })
                await ns["RequireBearer"](app)({"type": "http", "method": "DELETE", "headers": [
                    (b"authorization", b"Bearer employee"), (b"mcp-session-id", b"chat")]}, AsyncMock(), AsyncMock())
                self.assertEqual(close.await_count, 1 if status in (200, 202, 204) else 0)

    async def test_A_error_envelope_preserves_B_context_and_always_resets_it(self):
        async def execute(payload):
            self.assertEqual(sessions.downstream.get(), ("chat", "jwt"))
            self.assertEqual(payload["user_token"], "alice")
            if failed:
                raise RuntimeError("unit private error")
            return {"decision": "Allow"}
        ns = functions("mcp_facade.py", {"build_mcp"}, {
            "Any": object, "types": NS(ListToolsResult=object, CallToolResult=object, CallToolRequestParams=object),
            "Server": lambda *args, **kwargs: NS(**kwargs),
            "_caller": AsyncMock(return_value={"principal": "alice", "claims": {"jti": "jwt"}}),
            "_scope": lambda ctx: "a", "_client_context": lambda *args: {},
            "_conversation": lambda *args: ("chat", "jwt"), "upstream_sessions": sessions,
            "execute_call": execute, "_render": lambda outcome, protocol=None: outcome,
            # A remote server: no local-run parameter check is involved.
            "registry": NS(server=lambda server_id: {}), "local_jobs": NS(validate_params=lambda params: None),
        })
        facade = ns["build_mcp"]()
        for failed in (False, True):
            with self.subTest(failed=failed):
                if failed:
                    with self.assertRaisesRegex(ValueError, "도구 호출을 완료하지 못했습니다"):
                        await facade.on_call_tool(None, NS(name="tool", arguments={}))
                else:
                    self.assertEqual(await facade.on_call_tool(None, NS(name="tool", arguments={})), {"decision": "Allow"})
                self.assertIsNone(sessions.downstream.get())

    def test_T10_only_exact_sdk_session_404_is_retryable(self):
        class MCPError(Exception):
            def __init__(self, code, message):
                self.code, self.message = code, message
        group = type("UnitExceptionGroup", (BaseException,), {})
        ns = functions("upstream.py", {"session_terminated"}, {"BaseExceptionGroup": group})
        module = ModuleType("mcp.shared.exceptions")
        module.MCPError = MCPError
        with patch.dict(sys.modules, {"mcp.shared.exceptions": module}):
            self.assertTrue(ns["session_terminated"](MCPError(-32600, "Session terminated")))
            self.assertFalse(ns["session_terminated"](MCPError(-32603, "Session terminated")))
            self.assertFalse(ns["session_terminated"](ValueError("Session terminated")))


class DispatchRejected(Exception):
    def __init__(self, message, verdict=None):
        super().__init__(message)
        self.verdict = verdict


class DispatchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.trace = []
        self.client = NS(call_tool=AsyncMock(return_value=NS(content=[], is_error=False, structured_content=None)))
        @asynccontextmanager
        async def session(*args, **kwargs):
            self.trace.append("session")
            yield self.client
        async def fetch_all(*args):
            return [{"enabled": True, "name": "tool", "approved_description_hash": "description",
                     "approved_schema_hash": {}, "approved_server_version": "1"}]
        async def fetch_one(sql, params):
            if "approvals" in sql:
                return {"status": "APPROVED", "expires_at": datetime.now(timezone.utc) + timedelta(minutes=1)}
            if "agent_revoked_tokens" in sql:
                return None
            return {"status": "active"}
        self.listed = AsyncMock(return_value=[NS(name="tool")])
        self.policy = AsyncMock(return_value={"decision": "Allow", "restrictions": {}})
        self.record = AsyncMock(return_value=None)
        self.release = AsyncMock()
        digest = functions("contract.py", {"canonical_hash"}, {"hashlib": hashlib, "json": json})["canonical_hash"]
        output_contract = NS(**functions("output_contract.py", {"approved_hash", "matches"}, {
            "canonical_hash": digest, "NO_OUTPUT_SCHEMA_HASH": digest(None)}))
        review_matches = functions("registry.py", {"tool_hashes", "review_matches"}, {
            "canonical_hash": lambda value: value, "NO_OUTPUT_SCHEMA_HASH": None})["review_matches"]
        ns = {
            "DispatchRejected": DispatchRejected, "registry": NS(
                server=lambda _: {"endpoint": "https://a.example/mcp", "poisoning_review": {
                    "tool": {"description_sha256": "description", "schema_sha256": {}}}},
                pinned_protocol=lambda _: "2025-11-25",
                tool_hashes=lambda _: {"description_sha256": "description", "schema_sha256": {}},
                review_matches=review_matches),
            "upstream": NS(session=session, list_all_tools=self.listed, release_pool=self.release,
                           tool_view=lambda _: {"description": "description", "input_schema": {}},
                           content_items=lambda _: [], session_terminated=lambda exc: str(exc) == "expired",
                           credential_source=lambda *args: "none"),
            "db": NS(fetch_all=fetch_all, fetch_one=fetch_one), "canonical_hash": lambda value: value,
            "disposal": NS(blocked=lambda **kwargs: False),
            "Draft202012Validator": lambda _: NS(is_valid=lambda args: True),
            "datetime": datetime, "UTC": timezone.utc, "local_verdict": lambda pid, decision, msg: {"policy_id": pid, "decision": decision},
            "pac": NS(build=AsyncMock(return_value={})), "classify": NS(classify=lambda *args: None),
            "_contract": AsyncMock(return_value={}), "GATEWAY_ENVIRONMENT": "unit", "_policy": self.policy,
            "dispatch": NS(record=self.record), "asyncio": asyncio,
            "output_contract": output_contract, "_guarded_result": lambda value, protocol=None, schema=None: value,
        }
        self.ns = functions("core.py", {"_call_upstream"}, ns)
        self.laps = NS(lap=lambda name: self.trace.append(name))
        self.state = {"policy_input": {"context": {}}, "request_id": "unit", "action": "r", "restrictions": {}}
        self.endpoint = ModuleType("stage2_core.endpoint_plane")
        self.endpoint.managed_failure = AsyncMock(return_value=None)
        self.ns["__package__"] = "stage2_core"
        self.modules = patch.dict(sys.modules, {"stage2_core": ModuleType("stage2_core"), "stage2_core.endpoint_plane": self.endpoint})
        self.modules.start()
        self.addCleanup(self.modules.stop)

    async def call(self):
        return await self.ns["_call_upstream"]("a", "tool", {}, "approval", "alice", dispatch_state=self.state,
                                              pac_payload={"arguments": {}, "transport_claims": {"jti": "unit-requester"}}, laps=self.laps)

    async def test_T4_policy_rechecked_every_call_on_same_connection(self):
        await self.call()
        await self.call()
        self.assertEqual(self.listed.await_count, 2)
        self.assertEqual(self.policy.await_count, 2)
        self.assertEqual(self.record.await_count, 2)
        self.assertEqual(self.client.call_tool.await_count, 2)

    async def test_T4_T5_final_cutover_and_approval_revoke_prevent_send(self):
        for refusal in ["principal", "terminated", "approval"]:
            with self.subTest(refusal=refusal):
                self.record.return_value = refusal
                with self.assertRaises(DispatchRejected) as caught:
                    await self.call()
                self.client.call_tool.assert_not_awaited()
                if refusal == "terminated":
                    self.assertEqual(caught.exception.verdict, {"policy_id": "MCP-DECOMM-001", "decision": "Block"})
        self.assertEqual(self.release.await_count, 3)

    async def test_terminating_server_through_real_session_wrapper_keeps_decommission_policy(self):
        ns = WiringTests().upstream_functions()
        @asynccontextmanager
        async def factory(*args):
            yield self.client
        ns.update(_sweep=AsyncMock(), credential_headers=lambda *args: {}, _session=factory,
                  _dispatch_allowed=AsyncMock(return_value=False))
        self.ns["upstream"].session = ns["session"]
        self.record.return_value = "terminated"
        with self.assertRaises(DispatchRejected) as caught:
            await self.call()
        self.assertEqual(caught.exception.verdict, {"decision": "Block", "policy_id": "MCP-DECOMM-001"})
        self.record.assert_awaited_once()
        self.client.call_tool.assert_not_awaited()
        ns["_dispatch_allowed"].assert_not_awaited()

    async def test_T7_changed_contract_closes_and_never_sends(self):
        self.ns["upstream"].tool_view = lambda _: {"description": "changed", "input_schema": {}}
        with self.assertRaisesRegex(DispatchRejected, "MCP contract changed before execution"):
            await self.call()
        self.client.call_tool.assert_not_awaited()
        self.release.assert_awaited_once()

    async def test_T4_policy_failure_remains_fail_closed(self):
        self.policy.side_effect = RuntimeError("unit OPA failure")
        with self.assertRaises(DispatchRejected) as caught:
            await self.call()
        self.assertEqual(caught.exception.verdict, {"policy_id": "P-CONTROL-FAIL-CLOSED", "decision": "Block"})
        self.client.call_tool.assert_not_awaited()

    async def test_T10_list_expiry_retries_once_before_intent(self):
        self.listed.side_effect = [ValueError("expired"), [NS(name="tool")]]
        await self.call()
        self.assertEqual(self.trace.count("session"), 2)
        self.record.assert_awaited_once()
        self.client.call_tool.assert_awaited_once()

    async def test_T10_second_list_failure_stops_and_call_failure_never_retries(self):
        self.listed.side_effect = ValueError("expired")
        with self.assertRaises(ValueError):
            await self.call()
        self.assertEqual(self.listed.await_count, 2)
        self.record.assert_not_awaited()
        self.listed.side_effect = None
        self.client.call_tool.side_effect = ValueError("expired")
        with self.assertRaises(ValueError):
            await self.call()
        self.client.call_tool.assert_awaited_once()
        self.assertTrue(self.state["upstream_attempted"])
        self.assertNotIn("upstream_executed", self.state)


if __name__ == "__main__":
    unittest.main()
