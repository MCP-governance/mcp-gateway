"""Current source inventory must never rewrite historical execution evidence."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build_enterprise_analysis as builder
import build_integration_matrix as integration


class CodeRefreshTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.requirements = {"metadata": {"head": "historical"}, "records": [{
            "id": "REQ-01", "status": "verified_unit", "acceptance": "keep condition",
            "code_evidence": [{"path": "source.py", "symbol": "run"}],
            "test_evidence": [{"path": "test.py", "normalized_sha256": "old-test-hash",
                               "run_evidence": "old-run.json", "assertion_lines": [9]}],
            "result": {"exit_code": 0}, "unknown_future_field": [1, 2]}]}
        self.cases = [{"id": "IC-001", "status": "passed", "analysis_base_commit": "historical",
                       "checked_at": "2026-10-13", "code_evidence": [{"path": "source.py", "symbol": "run"}],
                       "our_code_evidence": ["old pointer"], "runtime_evidence": [{"sha256": "old-run-hash"}],
                       "test_evidence": [{"normalized_sha256": "old-test-hash"}],
                       "execution_records": [{"exit_code": 0}], "owner": "reviewer"}]
        for name, data in (("requirements.json", self.requirements), ("integration-cases.json", self.cases)):
            (self.folder / name).write_text(json.dumps(data))
        self.fresh = {"path": "source.py", "symbol": "run", "line_start": 10, "line_end": 20,
                      "normalized_sha256": "new-code-hash", "source_state": "committed_source",
                      "symbol_found": True}
        for target, value in (("OUT", self.folder),):
            self.enterContext(patch.object(builder, target, value))
        self.enterContext(patch.object(builder, "git", return_value=b"current-commit"))
        self.enterContext(patch.object(builder, "evidence", side_effect=lambda *args: dict(self.fresh)))
        self.enterContext(patch.object(integration, "CODE", {"run": ("source.py", "run", None)}))
        self.enterContext(patch.object(integration, "code_evidence", side_effect=lambda *args: dict(self.fresh)))

    def refresh(self):
        with contextlib.redirect_stdout(io.StringIO()):
            builder.refresh_code_only()

    def test_only_current_pointers_change_and_historical_results_survive(self):
        self.refresh()
        req = json.loads((self.folder / "requirements.json").read_text())
        case = json.loads((self.folder / "integration-cases.json").read_text())[0]
        self.assertEqual(req["metadata"]["head"], "historical")
        self.assertEqual(req["metadata"]["code_observation"]["commit"], "current-commit")
        self.assertEqual(req["records"][0]["code_evidence"][0]["source_commit"], "current-commit")
        for key, value in self.requirements["records"][0].items():
            if key != "code_evidence":
                self.assertEqual(req["records"][0][key], value, key)
        for key, value in self.cases[0].items():
            if key not in {"code_evidence", "our_code_evidence"}:
                self.assertEqual(case[key], value, key)
        self.assertEqual(case["our_code_evidence"], ["source.py:10-20 run"])

    def test_unknown_anchor_refuses_before_any_write(self):
        before = {p: p.read_bytes() for p in self.folder.iterdir()}
        with patch.object(integration, "CODE", {}), self.assertRaises(ValueError):
            self.refresh()
        self.assertEqual({p: p.read_bytes() for p in self.folder.iterdir()}, before)

    def test_dirty_source_cannot_be_labelled_as_current_commit(self):
        before = {p: p.read_bytes() for p in self.folder.iterdir()}
        self.fresh["source_state"] = "worktree_modified"
        with self.assertRaises(ValueError):
            self.refresh()
        self.assertEqual({p: p.read_bytes() for p in self.folder.iterdir()}, before)


if __name__ == "__main__":
    unittest.main()
