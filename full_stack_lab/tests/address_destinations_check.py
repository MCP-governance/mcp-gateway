"""S4-02: a one-click remote registration whose URL argument matched no address can be given its hosts.

10-25 field test: AWS Knowledge `aws___read_documentation` (requests[].url) and Microsoft Learn `microsoft_docs_fetch`
(url) were registered with `"pattern": "(?!)"`, so every call was PAC-01. The scope review route must move such a
derived pattern to the reviewed destinations, also for a remote registration (constraints_derived False).
"""
from __future__ import annotations

import copy
import re
import unittest
from unittest.mock import AsyncMock, patch

from app import core, registry, review, tool_sunset

URL = {"type": "string", "pattern": "(?!)"}
SPEC = {"intake_id": "00000000-0000-0000-0000-000000000001", "constraints_derived": False,
        "tools": {"aws___read_documentation": "r", "aws___search_documentation": "r"},
        "tool_reviews": {name: {"purpose": "공개 문서 조회", "asset": "AWS 문서", "destinations": [], "inputs": None,
                                "mask": True, "grade": "public", "accepts_from": [], "consent": True}
                         for name in ("aws___read_documentation", "aws___search_documentation")},
        "parameter_constraints": {
            "aws___read_documentation": {"type": "object", "additionalProperties": False, "properties": {"requests": {
                "type": "array", "items": {"type": "object", "properties": {"url": URL, "max_length": {"type": "integer"}}}}}},
            "aws___search_documentation": {"type": "object", "additionalProperties": False,
                                           "properties": {"search_phrase": {"type": "string"}}}}}


class ExistingRegistration(unittest.IsolatedAsyncioTestCase):
    async def test_scope_review_moves_the_empty_address_pattern_to_reviewed_hosts(self):
        doc = {"servers": {"aws": copy.deepcopy(SPEC)}, "history": []}
        saved = []
        review_item = {**SPEC["tool_reviews"]["aws___read_documentation"], "destinations": ["docs.aws.amazon.com"]}
        with patch.object(registry, "runtime", return_value=doc), patch.object(registry, "save_runtime", side_effect=saved.append), \
                patch.object(registry, "sync", AsyncMock()), patch.object(core.db, "fetch_one", AsyncMock(return_value={"submitted_by": "emp"})), \
                patch.object(core.db, "fetch_all", AsyncMock(return_value=[])), patch.object(review, "require_independent", AsyncMock()), \
                patch.object(review, "record_event", AsyncMock()), patch.object(tool_sunset, "approve_review", AsyncMock()):
            await core.review_tool_scopes("aws", {"aws___read_documentation": review_item}, "admin-b")
        constraints = saved[-1]["servers"]["aws"]["parameter_constraints"]
        pattern = constraints["aws___read_documentation"]["properties"]["requests"]["items"]["properties"]["url"]["pattern"]
        self.assertTrue(re.search(pattern, "https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints-s3.html"))
        self.assertFalse(re.search(pattern, "https://169.254.169.254/latest"))
        self.assertEqual(constraints["aws___search_documentation"], SPEC["parameter_constraints"]["aws___search_documentation"])
        self.assertEqual(saved[-1]["servers"]["aws"]["tool_reviews"]["aws___read_documentation"]["destinations"], ["docs.aws.amazon.com"])


if __name__ == "__main__":
    unittest.main()
