import importlib.util
import io
import os
import platform
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
WINDOWS_SOURCE = ROOT / "endpoint-agent" / "managed-windows.py"
LINUX_SOURCE = ROOT / "endpoint-agent" / "enforce-linux.py"


def load_windows_launcher():
    spec = importlib.util.spec_from_file_location("managed_windows_launcher_check", WINDOWS_SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LauncherPinCheck(unittest.TestCase):
    def test_windows_rejects_settings_overrides_and_pins_profile_environment(self):
        module = load_windows_launcher()
        profile = Path("C:/Managed Profile")
        for name, arguments, variable, suffix in (
            ("codex", ["-c", "notify=[]"], "CODEX_HOME", ".codex"),
            ("codex", ["--config", "notify=[]"], "CODEX_HOME", ".codex"),
            ("codex", ["--config=notify=[]"], "CODEX_HOME", ".codex"),
            ("codex", ["-cnotify=[]"], "CODEX_HOME", ".codex"),
            ("codex", ["-pcnotify=[]"], "CODEX_HOME", ".codex"),
            ("claude", ["--settings", "{}"], "CLAUDE_CONFIG_DIR", None),
            ("claude", ["--settings={}"], "CLAUDE_CONFIG_DIR", None),
        ):
            with self.subTest(name=name, arguments=arguments), patch.dict(os.environ, {variable: "user-value"}), \
                    patch("sys.stderr", new_callable=io.StringIO) as stderr:
                result = module.launch_harness(name, arguments, profile, Path("harness.exe"))
                self.assertEqual(result, 2)
                self.assertIn("관리 실행", stderr.getvalue())
                self.assertEqual(os.environ.get(variable), str(profile / suffix) if suffix else None)

    def test_windows_passes_regular_arguments_without_rewriting_them(self):
        module = load_windows_launcher()
        for name, arguments, variable, suffix in (
            ("codex", ["-p", "exec", "--model", "gpt"], "CODEX_HOME", ".codex"),
            ("claude", ["-p", "exec", "--model", "sonnet"], "CLAUDE_CONFIG_DIR", None),
        ):
            with self.subTest(name=name), patch.dict(os.environ, {variable: "user-value"}), \
                    patch.object(module.subprocess, "call", return_value=7) as call:
                self.assertEqual(module.launch_harness(name, arguments, "C:/Managed", "C:/Harness.exe"), 7)
                call.assert_called_once_with(["C:/Harness.exe", *arguments])
                self.assertEqual(os.environ.get(variable), str(Path("C:/Managed") / suffix) if suffix else None)

    def test_windows_creates_guarded_launchers_even_without_custom_ca(self):
        module = load_windows_launcher()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            module.PROGRAMS = root / "protected"
            module.PROGRAMS.mkdir()
            with patch.object(module, "lock_down", side_effect=lambda path: path.mkdir(parents=True, exist_ok=True)):
                launcher_folder, files = module.harness_launchers(
                    {"sid": "S-1-5-21", "profile": str(root / "profile")},
                    root / "native", {"claude.exe": "hash", "codex.exe": "hash"}, root / "python.exe")
            self.assertEqual({Path(name).as_posix() for name in files},
                             {"launchers/S-1-5-21/claude.cmd", "launchers/S-1-5-21/codex.cmd"})
            for name in ("claude", "codex"):
                script = (launcher_folder / f"{name}.cmd").read_text(encoding="utf-8")
                self.assertIn(f" launch ", script)
                self.assertIn(f" {name} -- %*", script)
                self.assertIn("--profile", script)
                self.assertIn("--native", script)
                self.assertIn("-- %*", script)

    def test_windows_cli_entry_rejects_launcher_arguments(self):
        module = load_windows_launcher()
        argv = [str(WINDOWS_SOURCE), "launch", "--profile", "C:/Managed", "--native",
                "C:/Harness.exe", "codex", "--", "--config=notify=[]"]
        with patch("sys.argv", argv), patch("sys.stderr", new_callable=io.StringIO) as stderr:
            with self.assertRaises(SystemExit) as result:
                module.main()
        self.assertEqual(result.exception.code, 2)
        self.assertIn("관리 실행", stderr.getvalue())

    @unittest.skipUnless(platform.system() == "Linux" and shutil.which("gcc"), "Linux gcc가 필요합니다")
    def test_linux_native_wrapper_rejects_overrides_and_passes_regular_arguments(self):
        spec = importlib.util.spec_from_file_location("enforce_linux_launcher_check", LINUX_SOURCE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        echo = Path(shutil.which("echo"))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for harness, rejected, allowed in (
                ("codex", [["-c", "notify=[]"], ["--config", "notify=[]"], ["--config=notify=[]"],
                            ["-cnotify=[]"], ["-pcnotify=[]"]], [["-p"], ["exec"], ["--model", "gpt"]]),
                ("claude", [["--settings", "{}"], ["--settings={}"]], [["-p"], ["exec"], ["--model", "sonnet"]]),
            ):
                wrapper = root / harness
                module.wrapper(wrapper, echo, folder, "managed", guard=harness)
                for arguments in rejected:
                    with self.subTest(harness=harness, arguments=arguments):
                        result = subprocess.run([wrapper, *arguments], capture_output=True, text=True)
                        self.assertEqual(result.returncode, 2)
                        self.assertIn("관리 실행", result.stderr)
                        self.assertEqual(result.stdout, "")
                for arguments in allowed:
                    with self.subTest(harness=harness, arguments=arguments):
                        result = subprocess.run([wrapper, *arguments], capture_output=True, text=True)
                        self.assertEqual(result.returncode, 0)
                        self.assertEqual(result.stdout.strip(), " ".join(arguments))


if __name__ == "__main__":
    unittest.main()
