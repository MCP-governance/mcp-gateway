"""S6 적대 검토 회귀. 저장소 루트에서 python -B -X utf8 full_stack_lab/tests/user_command_settings_review_check.py"""
import ast
import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_scan():
    source = (ROOT / "endpoint-agent/agent.py").read_text(encoding="utf-8")
    function = next(node for node in ast.parse(source).body
                    if isinstance(node, ast.FunctionDef) and node.name == "user_command_settings")
    namespace = {"Path": Path, "os": os, "json": json}
    exec(compile(ast.Module(body=[function], type_ignores=[]), source, "exec"), namespace)
    return namespace["user_command_settings"]


class HardLinkReview(unittest.TestCase):
    def test_settings_hardlink_is_rejected_without_reading_report_values(self):
        with tempfile.TemporaryDirectory(prefix="mint-s6-link-") as root:
            home = Path(root) / "home"
            private = Path(root) / "private.json"
            target = home / ".claude" / "settings.json"
            target.parent.mkdir(parents=True)
            private.write_text('{"apiKeyHelper":"PRIVATE_COMMAND_VALUE"}', encoding="utf-8")
            try:
                os.link(private, target)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"파일 시스템에서 hard link 생성 불가: {type(exc).__name__}")

            ok, findings = load_scan()(home)

        self.assertFalse(ok)
        self.assertEqual(findings, [{"file": ".claude/settings.json", "keys": []}])
        self.assertNotIn("PRIVATE_COMMAND_VALUE", json.dumps(findings))


class DirectorySwapReview(unittest.TestCase):
    def test_linked_settings_directory_is_not_followed(self):
        # The state a swap after a path check would leave: .claude points outside the home.
        with tempfile.TemporaryDirectory(prefix="mint-s6-swap-") as root:
            home = Path(root) / "home"
            outside = Path(root) / "outside"
            outside.mkdir()
            home.mkdir()
            (outside / "settings.json").write_text('{"apiKeyHelper":"PRIVATE_COMMAND_VALUE"}', encoding="utf-8")
            try:
                (home / ".claude").symlink_to(outside, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"링크 생성 불가: {type(exc).__name__}")
            ok, findings = load_scan()(home)
        self.assertFalse(ok)
        self.assertEqual(findings, [{"file": ".claude", "keys": []}])


if __name__ == "__main__":
    unittest.main(verbosity=2)
