"""A managed header helper that cannot get a credential still prints a fixed, rejected one.

Without an Authorization header Claude Code falls back to OAuth and caches the server as
needing sign-in, so it stays unusable after the device is reactivated (D-148 PJ1 run)."""
import ast
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
UNAVAILABLE = {"Authorization": "Bearer endpoint-not-active"}


class ManagedHelperUnavailable(unittest.TestCase):
    @unittest.skipUnless(hasattr(__import__("socket"), "AF_UNIX") and os.name == "posix", "Linux 소켓 필요")
    def test_linux_helper_without_service_prints_rejected_credential(self):
        with tempfile.TemporaryDirectory() as raw:
            run = subprocess.run([sys.executable, str(ROOT / "endpoint-agent/managed-linux.py"), "header",
                                  "--socket", str(Path(raw) / "missing.sock")], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout), UNAVAILABLE)

    def test_windows_helper_without_broker_prints_rejected_credential(self):
        source = (ROOT / "endpoint-agent/managed-windows.py").read_text(encoding="utf-8")
        node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "header")
        namespace = {"os": SimpleNamespace(open=lambda *a: (_ for _ in ()).throw(OSError("busy")),
                                           O_RDONLY=0, O_BINARY=0),
                     "time": SimpleNamespace(sleep=lambda s: None), "json": json, "sys": sys,
                     "pipe_name": lambda user: "pipe"}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "managed-windows.py", "exec"), namespace)
        with patch("builtins.print") as printed:
            namespace["header"](None)
        self.assertEqual(json.loads(printed.call_args_list[-1].args[0]), UNAVAILABLE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
