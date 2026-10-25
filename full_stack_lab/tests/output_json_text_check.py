"""S4-05·S4-06: output control on documents and on JSON carried as text, with an analyzer double.

10-25 field test: a 135 KB Markdown file (1,192 lines) was withheld as "more than 1000 items", and a 400-order JSON
file was withheld as "over the return cap after inspection" because the masking replaced 16-digit order IDs inside
the JSON text with an unquoted [REDACTED], the broken JSON was then counted line by line. The analyzer double finds
what Presidio's credit-card recognizer finds (a 16-digit Luhn number anywhere in the text).
"""
from __future__ import annotations

import asyncio
import json
import re
import unittest
from unittest.mock import patch

from app import classify, core, privacy

CARD = re.compile(r"\b4\d{15}\b")


async def analyze(text, ignore=None):
    return [{"entity_type": "CREDIT_CARD", "start": m.start(), "end": m.end(), "score": 0.9}
            for m in CARD.finditer(text) if privacy._luhn(m.group())]


async def mask_text(text, ignore=None):
    found = await analyze(text)
    return CARD.sub("[REDACTED]", text), sorted({f["entity_type"] for f in found})


def result(text):
    return {"content": [{"type": "text", "text": text}]}


class JsonText(unittest.TestCase):
    def mask(self, payload):
        with patch.object(privacy, "analyze", analyze), patch.object(privacy, "mask_text", mask_text):
            return asyncio.run(privacy.mask_payload(payload))

    def test_card_number_in_a_json_number_is_held_for_that_reason(self):
        orders = json.dumps({"orders": [{"order_id": 4111111111111111, "qty": 2}, {"order_id": 1234567890123456, "qty": 1}]}, indent=1)
        with self.assertRaises(privacy.InspectionUnavailable) as caught:
            self.mask(result(orders))
        self.assertIn("CARD_NUMBER", str(caught.exception))
        self.assertIn("숫자", str(caught.exception))

    def test_card_number_in_a_json_string_is_masked_and_the_json_stays_valid(self):
        orders = json.dumps({"orders": [{"note": "card 4111111111111111 on file", "ts": 1792900000000, "qty": 2}]}, indent=1)
        masked, kinds = self.mask(result(orders))
        document = json.loads(masked["content"][0]["text"])
        self.assertEqual(document["orders"][0], {"note": "card [REDACTED] on file", "ts": 1792900000000, "qty": 2})
        self.assertEqual(kinds, ["CREDIT_CARD"])
        self.assertEqual(classify.result_items(masked), 1)

    def test_json_text_without_findings_is_returned_byte_for_byte(self):
        text = '{"rows": [1,2,3]}'
        masked, kinds = self.mask(result(text))
        self.assertEqual((masked["content"][0]["text"], kinds), (text, []))


class DocumentLines(unittest.TestCase):
    def test_document_lines_are_not_records(self):
        handbook = "\n".join(f"## {i}절\n\n본문 {i}" for i in range(1200))
        self.assertEqual(classify.result_items(result(handbook)), 1)
        self.assertEqual(core._guarded_result(result(handbook)), result(handbook))

    def test_json_records_keep_the_item_limit_and_text_keeps_the_byte_limit(self):
        with self.assertRaisesRegex(core.ResultRejected, "건 상한"):
            core._guarded_result(result(json.dumps(list(range(core.MAX_RESULT_ITEMS + 1)))))
        with self.assertRaisesRegex(core.ResultRejected, "byte 상한"):
            core._guarded_result(result("가" * core.MAX_RESULT_BYTES))


if __name__ == "__main__":
    unittest.main()
