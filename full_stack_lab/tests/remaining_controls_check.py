"""POL-31 input fields and masking, POL-26 transfer binding, POL-33 flow sources, POL-08 consent (unit level).

The database is replaced by small doubles, so these cases show the decision logic only. The same controls
through the deployed Gateway, OPA and Presidio are exercised on the appliance (see the 2026-10-18 report).
"""
from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gateway"))
from app import classify, consent, core, pac, review  # noqa: E402

TOOLS = {"convert": "r", "post": "w"}
BASE = {"purpose": "사내 문서 변환", "asset": "문서", "destinations": ["learn.microsoft.com"]}


def normalized(**changes):
    reviews = {"convert": {**BASE, **changes}, "post": {**BASE, "destinations": []}}
    return review.normalize_tool_reviews(TOOLS, reviews, "admin")


class ReviewTermsTest(unittest.TestCase):
    def test_defaults_do_not_widen_anything(self):
        item = normalized()["convert"]
        self.assertEqual((item["inputs"], item["mask"], item["grade"], item["accepts_from"], item["consent"]),
                         (None, False, "public", [], False))

    def test_bad_terms_are_refused(self):
        for changes, needle in (({"inputs": ["uri", "bad name"]}, "입력 항목"),
                                ({"grade": "important"}, "등급"),
                                ({"accepts_from": ["../etc"]}, "서버")):
            with self.assertRaises(ValueError) as caught:
                normalized(**changes)
            self.assertIn(needle, str(caught.exception))

    def test_scope_terms_ignore_who_and_when_but_not_what(self):
        a, b = normalized()["convert"], {**normalized()["convert"], "reviewed_by": "other", "reviewed_at": "x"}
        self.assertEqual(review.scope_terms(a), review.scope_terms(b))
        self.assertNotEqual(consent.terms_hash(a), consent.terms_hash(normalized(purpose="외부 공유 목적")["convert"]))


class InputFieldsTest(unittest.TestCase):
    advertised = {"convert": {"input_schema": {"type": "object", "required": ["uri"],
                                               "properties": {"uri": {"type": "string"}, "headers": {"type": "object"}}}}}

    def test_narrowed_inputs_close_the_schema(self):
        from jsonschema import Draft202012Validator
        scope = review.derived_constraints(self.advertised, {"convert": {**BASE, "inputs": ["uri"]}})["convert"]
        ok = Draft202012Validator(scope).is_valid
        self.assertTrue(ok({"uri": "https://learn.microsoft.com/a"}))
        self.assertFalse(ok({"uri": "https://learn.microsoft.com/a", "headers": {"Authorization": "x"}}))
        self.assertIn("headers", self.advertised["convert"]["input_schema"]["properties"], "advertised schema mutated")

    def test_unknown_or_required_inputs_are_refused(self):
        for inputs, needle in ((["uri", "body"], "계약에 없는"), (["headers"], "필수")):
            with self.assertRaises(ValueError) as caught:
                review.derived_constraints(self.advertised, {"convert": {**BASE, "inputs": inputs}})
            self.assertIn(needle, str(caught.exception))


class TransferBindingTest(unittest.TestCase):
    def spec(self, runtime=True, **changes):
        return {"runtime": {"intake_id": "x"} if runtime else None,
                "tool_reviews": {"convert": {**normalized(**changes)["convert"]}}}

    def test_reviewed_destination_on_a_runtime_server_is_bound_to_purpose_and_grade(self):
        ok, pairs = pac.transfer_binding(self.spec(), "convert", ["learn.microsoft.com"])
        self.assertTrue(ok)
        self.assertEqual(pairs, [{"destination_id": "learn.microsoft.com", "grade": "public", "purpose": "사내 문서 변환"}])
        _, wider = pac.transfer_binding(self.spec(grade="nonimportant"), "convert", ["learn.microsoft.com"])
        self.assertEqual([p["grade"] for p in wider], ["public", "nonimportant"])

    def test_anything_else_fails_closed(self):
        for spec, feature, hosts in ((self.spec(), "convert", ["evil.example.net"]),
                                     (self.spec(), "convert", ["learn.microsoft.com", "evil.example.net"]),
                                     (self.spec(runtime=False), "convert", ["learn.microsoft.com"]),
                                     (self.spec(), "post", ["learn.microsoft.com"]),
                                     (self.spec(), "missing", ["learn.microsoft.com"])):
            ok, pairs = pac.transfer_binding(spec, feature, hosts)
            self.assertFalse(ok and pairs, (feature, hosts))
        self.assertEqual(pac.transfer_binding(self.spec(), "convert", []), (True, []))

    def test_wildcard_covers_subdomains_only(self):
        spec = self.spec(destinations=["*.example.com"])
        self.assertTrue(pac.transfer_binding(spec, "convert", ["docs.example.com"])[1])
        self.assertFalse(pac.transfer_binding(spec, "convert", ["example.com.evil.net"])[1])


class FlowSourcesTest(unittest.TestCase):
    def test_reads_carry_no_flow_and_writes_ask_the_ledger(self):
        fetch = AsyncMock(return_value=[{"server_id": "filesystem"}])
        read = classify.Classification("github", "search", "r", "r")
        write = classify.Classification("github", "create_issue", "w", "w")
        with patch.object(core.db, "fetch_all", fetch):
            self.assertEqual(asyncio.run(core._flow_sources("emp", "github", read)), [])
            fetch.assert_not_awaited()
            self.assertEqual(asyncio.run(core._flow_sources("emp", "github", write)), ["filesystem"])
        query, params = fetch.await_args.args
        self.assertIn("server_id<>%s", query)
        self.assertEqual(params[:2], ("emp", "github"))


class ProviderFlowTest(unittest.TestCase):
    def test_a_provider_hosted_read_carries_its_arguments_out(self):
        fetch = AsyncMock(return_value=[{"server_id": "filesystem"}])
        read = classify.Classification("context7", "query-docs", "r", "r")
        with patch.object(core.db, "fetch_all", fetch):
            self.assertEqual(asyncio.run(core._flow_sources("emp", "context7", read, provider_hosted=True)), ["filesystem"])


class AddressArgumentsTest(unittest.TestCase):
    def test_address_named_values_only(self):
        args = {"uri": "https://learn.microsoft.com/a", "body": "see https://evil.example.net/x",
                "targets": [{"url": "https://docs.example.com/b"}], "source_urls": ["https://a.example.org/c"]}
        self.assertEqual(sorted(classify.address_arguments(args)),
                         ["https://a.example.org/c", "https://docs.example.com/b", "https://learn.microsoft.com/a"])

    def test_a_non_web_address_is_infrastructure(self):
        self.assertEqual(classify.url_destination("file:///etc/passwd").category, "infrastructure")
        self.assertTrue(classify.url_destination("https://learn.microsoft.com/a").external)


class ConsentTest(unittest.TestCase):
    item = {**BASE, "action": "r", "inputs": None, "mask": False, "grade": "public", "accepts_from": [], "consent": True}

    def run_missing(self, rows, grade="nonimportant"):
        fetch, execute = AsyncMock(return_value=rows), AsyncMock(return_value=1)
        with patch.object(consent.db, "fetch_all", fetch), patch.object(consent.db, "execute", execute):
            return asyncio.run(consent.missing("emp", "markitdown", "convert", grade, self.item)), execute

    def test_a_higher_grant_covers_a_lower_grade(self):
        reason, execute = self.run_missing([{"grade": "important", "status": "GRANTED"}])
        self.assertIsNone(reason)
        execute.assert_not_awaited()

    def test_no_consent_leaves_a_request_and_blocks(self):
        reason, execute = self.run_missing([{"grade": "public", "status": "GRANTED"}])
        self.assertIn("동의", reason)
        execute.assert_awaited_once()
        self.assertEqual(execute.await_args.args[1][3], "nonimportant")

    def test_a_refusal_is_not_asked_again(self):
        reason, execute = self.run_missing([{"grade": "nonimportant", "status": "DENIED"}])
        self.assertIn("동의하지 않았", reason)
        execute.assert_not_awaited()

    def test_unknown_grade_is_asked_as_important(self):
        _, execute = self.run_missing([], grade="unknown")
        self.assertEqual(execute.await_args.args[1][3], "important")


if __name__ == "__main__":
    unittest.main(verbosity=1)
