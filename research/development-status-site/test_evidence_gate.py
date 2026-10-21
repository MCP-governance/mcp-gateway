"""Focused regression checks for explicit WBS run selection and evidence validity."""

import json
import tempfile
import unittest
import uuid
from pathlib import Path

from evidence_gate import selected_current_runs, selected_legacy_runs, sha256


COMMIT = "a" * 40
IMAGE = "sha256:" + "b" * 64
ENVIRONMENT = "isolated-postgresql-18"


class EvidenceGateTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name)
        self.artifact = self.repo / "evidence.txt"
        self.artifact.write_bytes(b"first\r\nsecond\r\n")
        self.runs = self.repo / "runs.jsonl"

    def record(self, **changes):
        row = {
            "run_id": str(uuid.uuid4()), "test": "boundary.py", "rc": 0,
            "started_at": "2026-10-21T09:00:00Z", "finished_at": "2026-10-21T09:00:01Z",
            "checked": 2, "passed": 2, "failed": 0, "unknown": 0,
            "source_commit": COMMIT, "image_digest": IMAGE, "environment": ENVIRONMENT,
            "evidence": [{"path": "evidence.txt", "raw_sha256": sha256(self.artifact.read_bytes()),
                          "canonical_lf_sha256": sha256(b"first\nsecond\n"),
                          "transform": "CRLF->LF"}],
        }
        row.update(changes)
        return row

    def select(self, rows, selected):
        self.runs.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        manifest = {"schema_version": 2, "mode": "current", "runs_path": "runs.jsonl",
                    "runs_sha256": sha256(self.runs.read_bytes()),
                    "selected": {"boundary.py": selected}}
        return selected_current_runs(self.repo, manifest, COMMIT, IMAGE, ENVIRONMENT)["boundary.py"]

    def test_explicit_run_keeps_failure_and_corrected_rerun_separate(self):
        failed = self.record(rc=1, passed=1, failed=1)
        corrected = self.record()
        self.assertEqual(self.select([failed, corrected], failed["run_id"])["evidence_status"], "failed")
        self.assertEqual(self.select([failed, corrected], corrected["run_id"])["evidence_status"], "valid")

    def test_version_and_environment_drift_require_recheck(self):
        run = self.record()
        self.assertEqual(self.select([run], run["run_id"])["evidence_status"], "valid")
        for change in ({"source_commit": "c" * 40}, {"image_digest": "sha256:" + "d" * 64},
                       {"environment": "other"}):
            old = self.record(**change)
            self.assertEqual(self.select([old], old["run_id"])["evidence_status"], "recheck")

    def test_changed_or_missing_evidence_and_bad_counts_fail(self):
        run = self.record()
        self.artifact.write_bytes(b"first\nsecond\n")
        self.assertEqual(self.select([run], run["run_id"])["evidence_status"], "failed")
        self.artifact.write_bytes(b"changed\n")
        self.assertEqual(self.select([run], run["run_id"])["evidence_status"], "failed")
        self.artifact.write_bytes(b"first\r\nsecond\r\n")
        bad = self.record(unknown=1)
        self.assertEqual(self.select([bad], bad["run_id"])["evidence_status"], "failed")
        for change in ({"checked": 0, "passed": 0},
                       {"checked": 2, "passed": 1, "failed": 1},
                       {"checked": 2, "passed": 1, "unknown": 1}):
            incomplete = self.record(**change)
            self.assertEqual(self.select([incomplete], incomplete["run_id"])["evidence_status"], "failed")

    def test_rescore_rejects_nonvalid_selected_run(self):
        import rescore_1015
        from unittest.mock import patch

        for status in ("failed", "recheck"):
            with self.subTest(status=status), patch.object(
                    rescore_1015, "lab_results", return_value={
                        "intake_identity_pg_check.py": {"rc": 0, "evidence_status": status}}):
                with self.assertRaisesRegex(AssertionError, "lacks selected historical evidence"):
                    rescore_1015.build_after_wbs_1015(manifest_path=self.repo / "unused.json",
                                                       historical=True)

    def test_current_evidence_never_inherits_historical_stage_scores(self):
        import rescore_1015
        from unittest.mock import patch

        with self.assertRaisesRegex(ValueError, "historical replay only"):
            rescore_1015.build_after_wbs_1015(manifest_path=self.repo / "unused.json")
        selected = {"boundary.py": {"rc": 0, "evidence_status": "valid"},
                    "older.py": {"rc": 0, "evidence_status": "recheck"}}
        with patch.object(rescore_1015, "lab_results", return_value=selected):
            output = rescore_1015.current_evidence_summary(self.repo / "unused.json", IMAGE, ENVIRONMENT)
        self.assertEqual(output, {"evidence_mode": "current",
                                  "selected": {"boundary.py": "valid", "older.py": "recheck"}})
        self.assertNotIn("progress", output)

    def test_duplicate_run_id_rejected(self):
        run = self.record()
        with self.assertRaisesRegex(ValueError, "duplicate run ID"):
            self.select([run, run], run["run_id"])

    def test_current_manifest_requires_selected_runs(self):
        import rescore_1015
        from types import SimpleNamespace
        from unittest.mock import patch

        for selected in ({}, [], None, ""):
            with self.subTest(selected=selected):
                manifest_path = self.repo / "manifest.json"
                manifest_path.write_text(json.dumps({"schema_version": 2, "mode": "current",
                                                     "selected": selected}), encoding="utf-8")
                with patch.object(rescore_1015, "REPO", self.repo), patch.object(
                        rescore_1015, "git", side_effect=lambda *args: SimpleNamespace(
                            stdout=COMMIT if args[0] == "rev-parse" else "")):
                    with self.assertRaisesRegex(ValueError, "nonempty selected object"):
                        rescore_1015.current_evidence_summary(manifest_path, IMAGE, ENVIRONMENT)

    def test_legacy_row_is_pinned_and_only_historical(self):
        path = self.repo / "research/llm-wiki/analysis/wbs-1015/lab-results.jsonl"
        path.parent.mkdir(parents=True)
        first = b'{"test":"boundary.py","rc":1}\n'
        second = b'{"test":"boundary.py","rc":0}\n'
        path.write_bytes(first + second)
        manifest = {"schema_version": 1, "mode": "historical", "log_sha256": sha256(first + second),
                    "selected": {"boundary.py": {"line": 1, "row_sha256": sha256(first)}}}
        selected = selected_legacy_runs(self.repo, manifest)["boundary.py"]
        self.assertEqual((selected["rc"], selected["evidence_status"], selected["selected_line"]),
                         (1, "historical", 1))
        path.write_bytes(first + second + b'{}\n')
        with self.assertRaisesRegex(ValueError, "log changed"):
            selected_legacy_runs(self.repo, manifest)


if __name__ == "__main__":
    unittest.main()
