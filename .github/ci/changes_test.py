import unittest

from changes import docs_only


class ChangePathsTest(unittest.TestCase):
    def test_pure_docs(self):
        self.assertTrue(docs_only(["docs/ai/RUNBOOK.md", "research/notes/a b.md"]))

    def test_checks_cannot_hide_code_or_generated_files(self):
        for name in (
            "full_stack_lab/gateway/app/main.py", "docs/ai/architecture/icon.py",
            "research/notes/run.sh", "research/llm-wiki/analysis/code-hashes.json",
            "research/llm-wiki/analysis/code-hashes.md", "research/generated/trace.md",
            "docs/requirements.txt", "docs/constraints-dev.txt", "docs/CMakeLists.txt",
            ".github/workflows/verify.yml", "README.md",
        ):
            with self.subTest(name=name):
                self.assertFalse(docs_only(["docs/ai/RUNBOOK.md", name]))

    def test_empty_diff_runs_checks(self):
        self.assertFalse(docs_only([]))

    def test_rename_uses_both_paths(self):
        # git diff --no-renames emits both the deleted code and added document.
        self.assertFalse(docs_only(["docs/ai/check.py", "docs/ai/check.md"]))


if __name__ == "__main__":
    unittest.main()
