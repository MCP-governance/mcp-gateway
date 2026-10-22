"""W13 offline regressions; HTTP and native I/O doubles, no MCP/server execution.

The HTTP double applies the production request-local regexes with Python re.
It does not emulate Presidio's NLP or built-in recognizers. Synthetic token
formats test masking, never issuer validity. Native timing uses gated threads.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import secrets
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx

os.environ.setdefault("OTEL_SDK_DISABLED", "1")
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gateway"))
from app import core, endpoint_plane, mcp_facade, privacy, secret_scan


def request_double(url, *, json):
    text = json["text"]
    if url.endswith("/analyze"):
        found = []
        for recognizer in json["ad_hoc_recognizers"]:
            for pattern in recognizer["patterns"]:
                try:
                    compiled = re.compile(pattern["regex"])
                except re.error:
                    continue  # Variable-length lookbehind needs Presidio's regex engine.
                found.extend({"entity_type": recognizer["supported_entity"], "start": m.start(),
                              "end": m.end(), "score": pattern["score"]}
                             for m in compiled.finditer(text))
        return httpx.Response(200, json=found, request=httpx.Request("POST", url))
    # Merge overlapping findings before replacing so original offsets stay valid.
    spans = []
    for f in sorted(json["analyzer_results"], key=lambda f: (f["start"], f["end"])):
        if spans and f["start"] <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(spans[-1][1], f["end"]))
        else:
            spans.append((f["start"], f["end"]))
    for start, end in reversed(spans):
        text = text[:start] + "[REDACTED]" + text[end:]
    return httpx.Response(200, json={"text": text}, request=httpx.Request("POST", url))


def document(size, text="MCP SDK documentation.\n"):
    payload = {"content": [{"type": "text", "text": text}], "is_error": False}
    current = len(json.dumps(payload, ensure_ascii=False).encode())
    payload["content"][0]["text"] += " " * (size - current)
    assert len(json.dumps(payload, ensure_ascii=False).encode()) == size
    return payload


class DocumentInspection(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = AsyncMock()
        self.client.post.side_effect = request_double
        self.http_patch = patch.object(privacy, "_client", return_value=self.client)
        self.http_patch.start()
        self.addCleanup(self.http_patch.stop)

    async def test_placeholder_document_released_at_markitdown_size(self):
        payload = document(8_000, "MCP SDK documentation. api_key: <your-key>\n")
        payload["structured"] = {"markdown": payload["content"][0]["text"]}
        payload["content"][0]["text"] += " " * (16_094 - len(json.dumps(payload).encode()))
        self.assertEqual(len(json.dumps(payload).encode()), 16_094)
        with patch.object(secret_scan, "rule_ids", return_value=[]) as native:
            result, kinds = await core._inspected_result(payload)
        self.assertEqual(result, payload)
        self.assertEqual(kinds, [])
        native.assert_called_once()

    async def test_fractional_score_preserves_schema_but_numeric_pii_is_withheld(self):
        # The fractional digits alone satisfy the production KR_RRN pattern.
        score = 0.9901013123456
        payload = {"content": [], "structured": {"results": [{"similarity": score, "text": "public"}]}}
        result, kinds = await privacy.mask_payload(payload)
        self.assertEqual(result, payload)
        self.assertEqual(kinds, [])
        for value in (9901013123456, 9901013123456.0, "9901013123456"):
            original = {"content": [], "structured": {"id": value}}
            if isinstance(value, str):
                result, kinds = await privacy.mask_payload(original)
                self.assertEqual(result["structured"]["id"], "[REDACTED]")
                self.assertIn("KR_RRN", kinds)
            else:
                with self.assertRaises(privacy.InspectionUnavailable):
                    await privacy.mask_payload(original)

    async def test_cloudflare_fractional_score_released_at_68688_bytes(self):
        from cloudflare_output_fp_check import SCHEMA, at_size, sample
        payload = sample()
        payload["structured"]["results"][0]["similarity"] = 0.9901013123456
        payload = core._guarded_result(at_size(payload), "2025-11-25", SCHEMA)
        with patch.object(secret_scan, "rule_ids", return_value=[]):
            result, kinds = await core._inspected_result(payload)
        core._validate_output(result, SCHEMA)
        self.assertEqual((result, kinds), (payload, []))
        self.assertEqual(core.response_evidence(result, "returned")["bytes"], 68_688)

    async def test_sensitive_keys_and_fractional_text_are_still_protected(self):
        for key in ("person@example.net", "990101-3123456"):
            with self.assertRaises(privacy.InspectionUnavailable):
                await privacy.mask_payload({"content": [], "structured": {key: 0.9901013123456}})
        text = "score=0.9901013123456"
        result, kinds = await privacy.mask_payload({"text": text})
        self.assertNotEqual(result["text"], text)
        self.assertIn("KR_RRN", kinds)

    async def test_finite_placeholder_syntax_only_and_real_tokens_still_masked(self):
        token = "ghp_" + secrets.token_hex(18)
        for placeholder in ("<your-key>", "<YOUR_API_KEY>", "YOUR_API_KEY_HERE", "<your-password>"):
            with self.subTest(placeholder=placeholder):
                text = "api_key: " + placeholder
                result, kinds = await privacy.mask_text(text)
                self.assertEqual((result, kinds), (text, []))
        for text in ("api_key: " + token, "api_key: <your-key>\ntoken: " + token,
                     "api_key: <your-key-" + token + ">", "api_key: YOUR_API_KEY_HERE_" + token,
                     "password: abcdefgh", "api_key: <your-key>person@example.net"):
            result, kinds = await privacy.mask_text(text)
            self.assertNotEqual(result, text)
            self.assertTrue(kinds)
            self.assertNotIn(token, result)

    async def test_document_values_masked_and_actual_assignments_withheld(self):
        token = "ghp_" + secrets.token_hex(18)
        payload = {"content": [], "structured": {"markdown": "api_key: " + token + "\nmail person@example.net"}}
        original = deepcopy(payload)
        with patch.object(secret_scan, "rule_ids", return_value=[]):
            result, kinds = await core._inspected_result(payload)
        self.assertEqual(payload, original)
        self.assertNotIn(token, json.dumps(result))
        self.assertNotIn("person@example.net", json.dumps(result))
        self.assertIn("CREDENTIAL", kinds)
        self.assertIn("EMAIL_ADDRESS", kinds)
        for key, value in (("password", "abcdefgh"), ("api_key", token)):
            with self.assertRaises(privacy.InspectionUnavailable):
                await privacy.mask_payload({"structured": {key: value}})

    async def test_engine_failure_and_secret_residue_never_release_documents(self):
        payload = document(51_456)
        for failure in (OSError("synthetic load failure"), ValueError("synthetic engine failure")):
            with patch.object(secret_scan, "rule_ids", side_effect=failure):
                with self.assertRaises(privacy.InspectionUnavailable):
                    await core._inspected_result(payload)
        with patch.object(secret_scan, "rule_ids", return_value=["synthetic-token"]):
            with self.assertRaises(core.ResultRejected):
                await core._inspected_result(payload)

    async def test_unrelated_executor_queue_does_not_time_out_51kb_document(self):
        loop = asyncio.get_running_loop()
        default = ThreadPoolExecutor(max_workers=1)
        loop.set_default_executor(default)
        gate, started = threading.Event(), threading.Event()

        def occupied():
            started.set()
            gate.wait(5)

        pending = loop.run_in_executor(None, occupied)
        try:
            # No default executor is available to wait for the start signal.
            for _ in range(100):
                if started.is_set():
                    break
                await asyncio.sleep(0.001)
            self.assertTrue(started.is_set())
            with (patch.object(secret_scan, "rule_ids", return_value=[]) as native,
                  patch.object(secret_scan, "TIMEOUT_SECONDS", 0.05)):
                payload = document(51_456)
                result, kinds = await core._inspected_result(payload)
                self.assertEqual((result, kinds), (payload, []))
                native.assert_called_once()
        finally:
            gate.set()
            await pending
            default.shutdown(wait=True)

    def test_279kb_size_limit_unchanged(self):
        self.assertEqual(core.MAX_RESULT_BYTES, 262_144)
        with self.assertRaises(core.ResultRejected):
            core._guarded_result(document(279_610))


class ScanConcurrency(unittest.IsolatedAsyncioTestCase):
    async def test_submission_failure_returns_capacity_and_remains_fail_closed(self):
        slots = asyncio.Semaphore(4)
        with patch.object(secret_scan, "_slots", slots):
            with patch.object(secret_scan._executor, "submit", side_effect=RuntimeError("synthetic submit failure")):
                with self.assertRaises(privacy.InspectionUnavailable):
                    await secret_scan.labels("public document")
            self.assertEqual(slots._value, 4)
            with patch.object(secret_scan, "rule_ids", return_value=[]):
                self.assertEqual(await secret_scan.labels("recovered document"), [])

    async def test_running_scan_cancellation_keeps_capacity_until_thread_finishes(self):
        slots, gate, started = asyncio.Semaphore(1), threading.Event(), threading.Event()

        def blocked(data):
            started.set()
            gate.wait(5)
            return []

        with patch.object(secret_scan, "_slots", slots), patch.object(secret_scan, "rule_ids", blocked):
            task = asyncio.create_task(secret_scan.labels("public document"))
            try:
                for _ in range(200):
                    if started.is_set():
                        break
                    await asyncio.sleep(0.001)
                self.assertTrue(started.is_set())
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                self.assertEqual(slots._value, 0)
            finally:
                gate.set()
                if not task.done():
                    await task
                for _ in range(200):
                    if slots._value == 1:
                        break
                    await asyncio.sleep(0.001)
            self.assertEqual(slots._value, 1)

    async def test_timeout_and_cancellation_retain_slots_until_completion_then_recover(self):
        slots = asyncio.Semaphore(4)
        gate = threading.Event()

        def blocked(data):
            gate.wait(5)
            return []

        with (patch.object(secret_scan, "_slots", slots),
              patch.object(secret_scan, "rule_ids", blocked),
              patch.object(secret_scan, "TIMEOUT_SECONDS", 0.03)):
            tasks = [asyncio.create_task(secret_scan.labels("document text")) for _ in range(4)]
            fifth = None
            try:
                outcomes = await asyncio.gather(*tasks, return_exceptions=True)
                self.assertTrue(all(isinstance(o, privacy.InspectionUnavailable) for o in outcomes))
                self.assertEqual(slots._value, 0)
                fifth = asyncio.create_task(secret_scan.labels("fifth document"))
                await asyncio.sleep(0.01)
                self.assertFalse(fifth.done())
                fifth.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await fifth
                self.assertEqual(slots._value, 0)
            finally:
                gate.set()
                for _ in range(200):
                    if slots._value == 4:
                        break
                    await asyncio.sleep(0.001)
            self.assertEqual(slots._value, 4)
            self.assertEqual(await secret_scan.labels("recovered document"), [])

    async def test_output_deadline_still_includes_wait_for_scanner_capacity(self):
        slots = asyncio.Semaphore(0)
        payload = document(51_456)
        with (patch.object(secret_scan, "_slots", slots),
              patch.object(privacy, "mask_payload", AsyncMock(return_value=(payload, []))),
              patch.object(core, "OUTPUT_INSPECTION_TIMEOUT_SECONDS", 0.02)):
            with self.assertRaises(privacy.InspectionUnavailable) as failure:
                await core._inspected_result(payload)
        self.assertIn("전체 대기", str(failure.exception))


class FinalDecision(unittest.IsolatedAsyncioTestCase):
    setUp = DocumentInspection.setUp

    async def run_call(self, payload):
        cls = SimpleNamespace(action="r", base_action="r", data_class="public", destinations=[], resources=[],
                              dlp=[], notes=[], restrictable=[],
                              primary=SimpleNamespace(id="asset", kind="file", owner_department=None),
                              summary=lambda: "synthetic read")

        async def fetch(query, params=()):
            return {"role": "employee", "status": "active", "synthetic": True} if "principals" in query else None

        async def record(event, laps):
            return {**event, "decision_id": 7}

        changes = [(core.db, {"fetch_one": AsyncMock(side_effect=fetch), "fetch_all": AsyncMock(return_value=[]),
                              "execute": AsyncMock(return_value=1),
                              "transaction": Mock(side_effect=AssertionError("offline database boundary"))}),
                   (core.registry, {"server": Mock(return_value={"endpoint": "http://internal"}),
                                    "allowed_principals": Mock(return_value=None), "catalog_version": Mock(return_value="test")}),
                   (core.classify, {"classify": Mock(return_value=cls), "remember_navigation": Mock()}),
                   (endpoint_plane, {"managed_failure": AsyncMock(return_value=None),
                                     "shadow_count_for": AsyncMock(return_value=0),
                                     "shadow_listener_count_for": AsyncMock(return_value=0)}),
                   (core.pac, {"build": AsyncMock(return_value={}), "digest": Mock(return_value="test")}),
                   (core.user_suspend, {"expire": AsyncMock(return_value=None)}),
                   (core.consent, {"missing": AsyncMock(return_value=None)}),
                   (core.tool_sunset, {"check": AsyncMock(return_value=None), "call_verdict": Mock(return_value=None)}),
                   (core, {"policy_ledger": AsyncMock(), "_reserve_call": AsyncMock(return_value={}),
                           "_privacy_ignore": Mock(return_value=None), "_contract": AsyncMock(return_value={}),
                           "_relationship_scope": AsyncMock(return_value={}), "_sequence_flags": AsyncMock(return_value=[]),
                           "_flow_sources": AsyncMock(return_value=[]), "_decision_payload": record,
                           "_policy": AsyncMock(return_value={"decision": "Allow", "policy_id": "P-AUTHZ-ALLOW-001", "reason": "test"}),
                           "enforcement_mode": AsyncMock(return_value="enforce"),
                           "_call_upstream": AsyncMock(return_value=payload)})]
        with ExitStack() as stack:
            for target, attributes in changes:
                for name, value in attributes.items():
                    stack.enter_context(patch.object(target, name, value))
            return await asyncio.wait_for(core.execute_call({"server_id": "filesystem", "tool": "read_multiple_files",
                                            "user_token": "synthetic", "arguments": {"paths": ["/docs/sdk.md"]}}), 2)

    async def test_normal_document_and_real_secret_pii_have_expected_final_policy(self):
        token = "ghp_" + secrets.token_hex(18)
        for text, expected_types in (("api_key: <your-key>", []),
                                     ("api_key: " + token + "\nmail person@example.net", ["CREDENTIAL", "EMAIL_ADDRESS"])):
            with patch.object(secret_scan, "rule_ids", return_value=[]):
                verdict = await self.run_call(document(51_456, text))
            self.assertEqual((verdict["decision"], verdict["policy_id"]), ("Allow", "P-AUTHZ-ALLOW-001"))
            self.assertTrue(verdict["upstream_executed"])
            self.assertTrue(set(expected_types) <= set(verdict["privacy_types"]))
            wire = mcp_facade._render(verdict).model_dump_json(by_alias=True)
            self.assertNotIn(token, wire)
            self.assertNotIn("person@example.net", wire)

    async def test_engine_outage_and_secret_residue_have_output_block_policy(self):
        for failure in (OSError("synthetic load failure"), ValueError("synthetic engine failure"),
                        ["synthetic-secret-rule"]):
            scanner = Mock(side_effect=failure) if isinstance(failure, Exception) else Mock(return_value=failure)
            with patch.object(secret_scan, "rule_ids", scanner):
                verdict = await self.run_call(document(51_456))
            self.assertEqual((verdict["decision"], verdict["policy_id"]), ("Block", "MCP-OUTPUT-001"))
            self.assertTrue(verdict["upstream_executed"])
            self.assertIsNone(verdict["result"])
            self.assertEqual(verdict["result_evidence"]["disposition"], "withheld")


if __name__ == "__main__":
    unittest.main(verbosity=2)
