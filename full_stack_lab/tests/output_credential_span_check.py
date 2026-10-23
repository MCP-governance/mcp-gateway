"""Gateway image only (Presidio): a credential quoted inside a document is masked, a structured one withholds.

10-23 PJ1: read_multiple_files over the MCP Python SDK docs was withheld whole, because the
"text=<documents>" assignment matched an OAuth example inside the text.
"""
from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gateway"))
from app import privacy  # noqa: E402

DOC = "# OAuth\n\nConfigure the client:\n\n    client_secret=s3cr3tValue9\n    password=hunter2hunter\n\nThen run the server.\n"


class CredentialSpan(unittest.TestCase):
    def test_document_quote_is_masked_not_withheld(self):
        masked, kinds = asyncio.run(privacy.mask_payload({"content": [{"type": "text", "text": DOC}]}))
        text = masked["content"][0]["text"]
        self.assertIn("Then run the server.", text)
        self.assertNotIn("hunter2hunter", text)
        self.assertTrue(kinds)

    def test_millisecond_timestamp_is_not_card(self):
        stamp = next(n for n in range(1761200000000, 1761200000100) if privacy._luhn(str(n)))
        self.assertIsNone(privacy._identifier_number(stamp))
        self.assertEqual(privacy._identifier_number(4111111111111111), "CARD_NUMBER")

    def test_structured_credential_is_withheld(self):
        with self.assertRaises(privacy.InspectionUnavailable):
            asyncio.run(privacy.mask_payload({"structuredContent": {"password": "hunter2hunter"}}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
