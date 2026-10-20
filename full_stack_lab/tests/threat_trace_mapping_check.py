"""Offline integrity checks for reviewed evidence, not product/runtime acceptance."""
import ast
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WIKI = REPO / "research/llm-wiki"
sys.path.insert(0, str(WIKI / "tools"))
from threat_trace_review import render_review, review_references  # noqa: E402


class ThreatTraceMapping(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.review = json.loads((WIKI / "analysis/threat-trace-review-1020/review.json").read_text(encoding="utf-8"))
        cls.evidence = {r["id"]: r for r in cls.review["evidence"]}

    def test_original_requirements_and_runtime_ids_are_separate(self):
        source = json.loads((WIKI / "threats/extracted/policies.json").read_text(encoding="utf-8"))
        originals = {r["source_id"]: r for r in source["policies"] if r["sheet"] == "정책 최종본"}
        ledger = json.loads((REPO / "full_stack_lab/opa/policy_ledger.json").read_text(encoding="utf-8"))["policy_ledger"]
        policies = self.review["policies"]
        self.assertEqual(len(policies), 24)
        self.assertEqual({r["source_id"] for r in policies}, set(originals))
        self.assertEqual(self.review["source_sha256"], source["sha256"])
        for row in policies:
            with self.subTest(policy=row["source_id"]):
                original = originals[row["source_id"]]
                self.assertEqual(row["source_row"], original["row"])
                self.assertEqual(row["source_requirement"], original["fields"]["정책 내용"])
                self.assertEqual(row["title"], original["fields"]["정책명"])
                self.assertLessEqual(set(row["runtime_candidates"]), set(ledger))
                self.assertTrue(row["limitations"])

    def test_frozen_hashes_symbols_and_evidence_lines_exist(self):
        refs = [r for p in self.review["policies"] for r in review_references(p, self.evidence)]
        refs += [r for f in self.review["findings"] for r in f["evidence_references"]]
        unique = {(r["path"], r["symbol"], r["anchor"]): r for r in refs}
        for r in unique.values():
            with self.subTest(path=r["path"], symbol=r["symbol"], anchor=r["anchor"]):
                path = (REPO / r["path"]).resolve()
                self.assertTrue(path.is_relative_to(REPO))
                data = path.read_bytes().replace(b"\r\n", b"\n")
                self.assertEqual(hashlib.sha256(data).hexdigest(), r["normalized_sha256"])
                text = data.decode("utf-8")
                lines = text.splitlines()
                self.assertTrue(1 <= r["line"] <= r["end_line"] <= len(lines))
                if r["symbol"]:
                    nodes = [n for n in ast.walk(ast.parse(text)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == r["symbol"]]
                    self.assertEqual(len(nodes), 1)
                    self.assertEqual((nodes[0].lineno, nodes[0].end_lineno), (r["line"], r["end_line"]))
                if r["anchor"]:
                    self.assertIn(r["anchor"], lines[r["line"] - 1])

    def test_catalog_preserves_review_and_never_claims_runtime_pass(self):
        catalog = json.loads((WIKI / "catalogs/threats.json").read_text(encoding="utf-8"))
        source = {p["source_id"]: p for p in self.review["policies"]}
        self.assertEqual(len(catalog), 24)
        for record in catalog:
            row = source[record["source_id"]]
            self.assertEqual(record["verification"], "static-candidate-mapping")
            self.assertTrue(record["independent_review"]["files_match_review"])
            self.assertEqual(record["code_references"], row["code_references"])
            self.assertEqual(record["regression_tests"], row["regression_tests"])
            self.assertTrue(all('/tests/' not in r["path"] for r in record["code_candidates"]))
            self.assertTrue(all(t["execution_in_this_review"] == "미실행" for t in record["regression_tests"]))
        approval_tests = source["PAC16"]["regression_tests"]
        self.assertFalse(any(r["path"].endswith("reservation_effect_check.py") for r in approval_tests))

    def test_render_has_24_rows_and_exposes_stale_snapshot(self):
        before = json.dumps(self.review, sort_keys=True)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.json"
            render_review(path, self.review, {"changed.py"})
            text = path.with_name("README.md").read_text(encoding="utf-8")
            self.assertEqual(sum(line.startswith("| PAC") for line in text.splitlines()), 24)
            self.assertIn("불일치 — 재검토 필요: changed.py", text)
            self.assertIn("결정 필요", text)
        self.assertEqual(json.dumps(self.review, sort_keys=True), before)


if __name__ == "__main__":
    unittest.main()
