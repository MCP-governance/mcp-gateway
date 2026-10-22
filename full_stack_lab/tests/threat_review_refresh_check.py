"""Offline checks for retained review history and the rendered supersession link."""
import ast
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WIKI = REPO / "research/llm-wiki"


class ReviewRefreshChecks(unittest.TestCase):
    def test_previous_bytes_and_changed_reference_history_are_retained(self):
        review = json.loads((WIKI / "analysis/threat-trace-review-1020/review.json").read_text(encoding="utf-8"))
        refresh = review["refresh"]
        previous = (WIKI / "analysis/threat-trace-review-1020" / refresh["previous_snapshot"]).read_bytes()
        self.assertEqual(hashlib.sha256(previous).hexdigest(), refresh["previous_sha256"])
        self.assertEqual(json.loads(previous)["reviewed_commit"], refresh["previous_commit"])
        delta = json.loads((WIKI / "analysis/threat-trace-review-1021/delta-review.json").read_text(encoding="utf-8"))
        self.assertEqual(delta["to_commit"], review["reviewed_commit"])
        self.assertEqual(len(delta["files"]), refresh["changed_files"])
        self.assertEqual(sum(len(f["references"]) for f in delta["files"]), refresh["stale_unique_references"])
        self.assertTrue(all(f["assessment"] and f["old_sha256"] != f["new_sha256"] for f in delta["files"]))

    def test_ast_renderer_exposes_supersession_and_stale_files_without_mutation(self):
        source = ast.parse((WIKI / "tools/threat_trace_review.py").read_text(encoding="utf-8"))
        names = {"render_review", "link"}
        nodes = [node for node in source.body if isinstance(node, ast.FunctionDef) and node.name in names]
        self.assertEqual({node.name for node in nodes}, names)
        namespace = {}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "selected_review_renderer", "exec"), namespace)
        review = json.loads((WIKI / "analysis/threat-trace-review-1020/review.json").read_text(encoding="utf-8"))
        before = copy.deepcopy(review)
        with tempfile.TemporaryDirectory() as directory:
            namespace["render_review"](Path(directory) / "review.json", review, {"changed.py"})
            rendered = (Path(directory) / "README.md").read_text(encoding="utf-8")
        self.assertIn(review["refresh"]["previous_snapshot"], rendered)
        self.assertIn(review["refresh"]["previous_sha256"], rendered)
        self.assertIn("불일치 — 재검토 필요: changed.py", rendered)
        self.assertEqual(review, before)


if __name__ == "__main__":
    unittest.main()
