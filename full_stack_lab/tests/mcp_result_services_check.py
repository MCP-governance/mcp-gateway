"""Opt-in appliance checks against the real Presidio services and Gitleaks binary.

No MCP server is created. Synthetic identifiers/credentials carry no real rights.
Run in an isolated Gateway container process, never by starting a local stack.
"""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gateway"))
from app import core, mcp_facade, privacy, secret_scan


class RealInspectors(unittest.IsolatedAsyncioTestCase):
    async def test_numeric_identifier_and_sensitive_key_are_withheld(self):
        for structured in ({"rrn": 9001011234567}, {"person@example.net": "public"}):
            with self.subTest(kind="numeric" if "rrn" in structured else "key"):
                with self.assertRaises(privacy.InspectionUnavailable):
                    await core._inspected_result(core._guarded_result({"content": [], "structured": structured}))

    async def test_real_gitleaks_detects_structured_assignments_before_release(self):
        # Deliberately high-entropy test strings; these are not issued credentials.
        for key, value in (("client_secret", "Nk37yhf0M81vZRcq6WxAiJ5dtHeuSF2oKBgYP4Lr"),
                           ("aws_secret_access_key", "tp2FKXrH9gbUqP6hSca7dZWnVL8RoJy5xA03mKe1")):
            payload = {"content": [], "structured": {key: value}}
            with self.subTest(key=key):
                self.assertTrue(await secret_scan.labels(json.dumps(payload)), "Detector must recognize the synthetic fixture")
                try:
                    inspected, _ = await core._inspected_result(core._guarded_result(payload))
                except (core.ResultRejected, privacy.InspectionUnavailable):
                    continue
                self.assertNotIn(value, json.dumps(inspected))

    async def test_clean_numbers_empty_values_and_booleans_survive(self):
        payload = {"content": [], "structured": {"count": 0, "id": 12, "ratio": 0.5,
                   "enabled": False, "empty": {}, "missing": None, "items": [1, 2, 3]}}
        inspected, kinds = await core._inspected_result(core._guarded_result(payload))
        self.assertEqual(inspected, payload)
        self.assertEqual(kinds, [])
        rendered = mcp_facade._render({"decision": "Allow", "upstream_executed": True, "result": inspected,
                                       "result_evidence": {"disposition": "returned"}})
        self.assertEqual(rendered.structured_content, payload["structured"])

    async def test_string_identifier_is_actually_masked(self):
        payload = {"content": [], "structured": {"email": "person@example.net"}}
        inspected, kinds = await core._inspected_result(core._guarded_result(payload))
        self.assertIn("EMAIL_ADDRESS", kinds)
        self.assertNotIn("person@example.net", json.dumps(inspected))

    async def test_low_entropy_assignment_is_withheld_by_real_presidio(self):
        for key, value in (("password", "abcdefgh"), ("client_secret", "abcdefgh"),
                           ("api_key", "a" * 20), ("access_token", "a" * 20)):
            payload = {"content": [], "structured": {key: value}}
            with self.subTest(key=key), self.assertRaises(privacy.InspectionUnavailable):
                await core._inspected_result(core._guarded_result(payload))


if __name__ == "__main__":
    unittest.main()
