"""pj3 10-28: the service's observer thread died on its first pass and Codex was missing from the harnesses."""
import importlib.util
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

AGENT = Path(__file__).resolve().parents[1]


def managed():
    spec = importlib.util.spec_from_file_location("managed_windows", AGENT / "managed-windows.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WindowsService(unittest.TestCase):
    def test_collector_output_is_utf8_and_no_failure_ends_the_thread(self):
        text = (AGENT / "managed-windows.py").read_text(encoding="utf-8")
        observe = text[text.index("    def observe():"):text.index("threading.Thread(target=observe")]
        self.assertEqual(observe.count('"-X", "utf8"'), 2)
        self.assertEqual(len(re.findall(r"except Exception as exc", observe)), 2)
        # The child's Korean progress line decodes as UTF-8 under -X utf8 even when the ANSI code page is not UTF-8.
        done = subprocess.run([sys.executable, "-B", "-I", "-S", "-X", "utf8", "-c", "print('[endpoint-agent] 수집 완료')"],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
        self.assertIn("수집 완료", done.stdout)

    def test_codex_without_version_resource_is_reported_installed(self):
        module = managed()
        with tempfile.TemporaryDirectory() as profile:
            exe = Path(profile, "AppData/Local/Programs/OpenAI/Codex/bin/codex.exe")
            exe.parent.mkdir(parents=True)
            exe.write_bytes(b"MZ")
            self.assertEqual(module.harness_versions(profile), {"codex": ""})


if __name__ == "__main__":
    unittest.main()
