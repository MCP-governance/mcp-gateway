"""D-150 정정: Linux argv 가드와 Windows 기존 CA 런처 계약. 실제 MCP 시험 아님."""
import ast
import hashlib
import importlib.util
import io
import json
import mmap
import os
import platform
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[2]
WINDOWS_SOURCE = ROOT / "endpoint-agent" / "managed-windows.py"
LINUX_SOURCE = ROOT / "endpoint-agent" / "enforce-linux.py"


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WindowsLauncherRollbackCheck(unittest.TestCase):
    def setUp(self):
        self.module = load_module(WINDOWS_SOURCE, "managed_windows_launcher_check")

    def test_without_ca_returns_native_directory_without_creating_launchers(self):
        native = Path("C:/Managed/harness")
        with patch.object(self.module, "lock_down") as lock, \
                patch.object(self.module, "verify_transport") as verify:
            self.assertEqual(self.module.harness_launchers({}, native, {}), (native, {}))
        lock.assert_not_called()
        verify.assert_not_called()

    def test_ca_launchers_execute_native_with_child_scoped_trust(self):
        module = self.module
        before = dict(os.environ)
        with tempfile.TemporaryDirectory() as folder:
            programs = Path(folder)
            native = programs / "harness"
            native.mkdir()
            with patch.object(module, "PROGRAMS", programs), \
                    patch.object(module, "lock_down", side_effect=lambda p: p.mkdir(parents=True, exist_ok=True)), \
                    patch.object(module, "verify_transport") as verify:
                config = {"sid": "SID", "ca_certificate": "synthetic CA fixture"}
                launchers, owned = module.harness_launchers(
                    config, native, {"claude.exe": "fixture", "codex.exe": "fixture"})
            verify.assert_called_once_with(config)
            self.assertEqual(len(owned), 3)
            for name, variable in (("claude", "NODE_EXTRA_CA_CERTS"), ("codex", "CODEX_CA_CERTIFICATE")):
                script = (launchers / (name + ".cmd")).read_text(encoding="utf-8")
                executable = Path(os.path.relpath(native, launchers)) / (name + ".exe")
                self.assertEqual(script, f'@echo off\nsetlocal\nset "{variable}=%~dp0root.crt"\n'
                                 f'"%~dp0{executable}" %*\nexit /b %errorlevel%\n')
            for path, digest in owned.items():
                self.assertEqual(hashlib.sha256((programs / path).read_bytes()).hexdigest(), digest)
        self.assertEqual(os.environ, before)

    def test_launch_cli_and_python_harness_entry_are_removed(self):
        self.assertFalse(hasattr(self.module, "launch_harness"))
        with patch("sys.argv", [str(WINDOWS_SOURCE), "launch"]), \
                patch("sys.stderr", new_callable=io.StringIO), \
                patch.object(self.module.subprocess, "call") as call:
            with self.assertRaises(SystemExit) as result:
                self.module.main()
        self.assertEqual(result.exception.code, 2)
        call.assert_not_called()

    def test_user_path_is_appended_and_alternate_homes_are_untouched(self):
        registry = MagicMock()
        registry.QueryValueEx.return_value = ("C:/Other;C:/UserTools", 2)
        launcher = "C:/Managed/launchers/SID"
        with patch.dict("sys.modules", {"winreg": registry}), \
                patch.object(self.module.os, "pathsep", ";"):
            self.module.set_user_environment({"sid": "SID"}, {"PATH_APPEND": launcher})
        paths = [call.args[4] for call in registry.SetValueEx.call_args_list if call.args[1] == "PATH"]
        self.assertEqual(paths, ["C:/Other;C:/UserTools;" + launcher])
        deleted = {call.args[1] for call in registry.DeleteValue.call_args_list}
        self.assertTrue(deleted.isdisjoint({"CODEX_HOME", "CLAUDE_CONFIG_DIR"}))


class LinuxLauncherRendering(unittest.TestCase):
    def test_only_managed_codex_gets_fixed_sandbox_override(self):
        tree = ast.parse(LINUX_SOURCE.read_text(encoding="utf-8"))
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {"fixed_options", "wrapper"}]
        main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
        loop = next(n for n in main.body if isinstance(n, ast.For) and ast.unparse(n.iter) == "binaries.items()")
        rendered = {}

        def compile_wrapper(*args):
            rendered[Path(args[-1]).name] = Path(args[-3]).read_text(encoding="utf-8")
            Path(args[-1]).touch()  # Only capture generated C; no compiler or Linux policy is invoked.

        namespace = {"Path": Path, "mmap": mmap, "json": json, "tempfile": tempfile, "run": compile_wrapper}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(LINUX_SOURCE), "exec"), namespace)
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            binary = folder / "release"
            namespace.update(folder=folder, binaries={"codex": binary, "claude": binary}, proxy_env={}, ca=None,
                             person=SimpleNamespace(pw_dir="/home/managed-unit"))
            for daemon in (False, True):
                binary.write_bytes(b"ELF --no-daemon" if daemon else b"ELF older build")
                for managed in (False, True):
                    namespace["args"] = SimpleNamespace(user="managed-unit", managed_agent="/managed.py" if managed else None)
                    exec(compile(ast.Module(body=[loop], type_ignores=[]), str(LINUX_SOURCE), "exec"), namespace)
                    for key in ("codex", "claude"):
                        with self.subTest(daemon=daemon, managed=managed, harness=key):
                            source = rendered[key]
                            expected = (["--no-daemon"] if daemon else []) if key == "codex" else []
                            if managed and key == "codex":
                                expected += ["-c", 'sandbox_mode="danger-full-access"']
                            for i, value in enumerate(expected, 1):
                                self.assertIn(f"args[{i}] = {json.dumps(value)};", source)
                            self.assertEqual('sandbox_mode=\\"danger-full-access\\"' in source, managed and key == "codex")
                            self.assertIn(f"args[i+{len(expected)}]=argv[i]", source)
                            self.assertIn("if (blocked(argc, argv))", source)
                            self.assertNotIn("approval_policy", source)
                            self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", source)


@unittest.skipUnless(platform.system() == "Linux" and shutil.which("gcc"), "Linux gcc가 필요합니다")
class LinuxLauncherPinCheck(unittest.TestCase):
    def setUp(self):
        module = load_module(LINUX_SOURCE, "enforce_linux_launcher_check")
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.launchers = {}
        binary = Path(folder.name) / "release"
        binary.write_bytes(b"ELF --no-daemon")
        for name in ("codex", "claude"):
            launcher = Path(folder.name) / name
            module.wrapper(launcher, Path(shutil.which("echo")), folder.name, "managed", guard=name,
                           options=module.fixed_options(name, binary, managed=True))
            self.launchers[name] = launcher

    def assert_result(self, name, arguments, blocked=False):
        result = subprocess.run([str(self.launchers[name]), *arguments], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2 if blocked else 0, result.stderr)
        if blocked:
            self.assertIn("관리 실행", result.stderr)
            self.assertEqual(result.stdout, "")
        else:
            prefix = ["--no-daemon", "-c", 'sandbox_mode="danger-full-access"'] if name == "codex" else []
            self.assertEqual(result.stdout.strip(), " ".join([*prefix, *arguments]))
            self.assertEqual(result.stderr, "")

    def test_real_config_options_and_clusters_are_rejected(self):
        for arguments in (["-c", "notify=[]"], ["-cX"], ["--config"], ["--config=notify=[]"],
                          ["-hcX"], ["-xcX"], ["--unknown", "-c"], ["--search", "-c"],
                          ["--no-daemon", "-c"], ["--json", "-c"], ["--strict-config", "-c"],
                          ["-pconfig", "-cX"], ["--model=-c", "-cX"],
                          ["exec", "--ignore-user-config", "-cX"]):
            with self.subTest(arguments=arguments):
                self.assert_result("codex", arguments, blocked=True)

    def test_short_value_options_consume_attached_and_separate_values(self):
        for option in "impsCao":
            for arguments in ([f"-{option}config"], [f"-h{option}config"], [f"-{option}"]):
                with self.subTest(arguments=arguments):
                    self.assert_result("codex", arguments)
            # clap takes no hyphen-led value ("a value is required for '--model <MODEL>'",
            # codex-cli 0.153.4 and 0.163.0-alpha, 2026-10-20), so the next token is an option.
            for arguments in ([f"-{option}", "value", "-cX"], [f"-{option}", "-c"], [f"-h{option}", "--config"]):
                with self.subTest(arguments=arguments):
                    self.assert_result("codex", arguments, blocked=True)
        for arguments in (["-Csrc"], ["-mgpt"], ["-pconfig"], ["-pcnotify=[]"],
                          ["exec", "-mgpt-codex", "hello"], ["explain -c without executing"]):
            with self.subTest(arguments=arguments):
                self.assert_result("codex", arguments)

    def test_long_value_options_do_not_hide_a_later_override(self):
        for option in ("image", "model", "profile", "sandbox", "cd", "local-provider", "add-dir",
                       "ask-for-approval", "thread-source", "output-schema", "color", "output-last-message",
                       "base", "commit", "title", "enable", "disable", "remote", "remote-auth-token-env"):
            for arguments in ([f"--{option}=--config"], [f"--{option}"]):
                with self.subTest(arguments=arguments):
                    self.assert_result("codex", arguments)
            for arguments in ([f"--{option}", "value", "--config=X"], [f"--{option}=value", "-cX"],
                              [f"--{option}", "-c"]):
                with self.subTest(arguments=arguments):
                    self.assert_result("codex", arguments, blocked=True)

    def test_delimiters_and_exact_claude_settings_matching(self):
        # "--model --": clap refuses ("a value is required"), so Codex never starts either way.
        for name, arguments in (("codex", ["--model", "--", "-cX"]), ("codex", ["-m", "--", "-cX"]),
                                ("codex", ["--", "-c"]), ("codex", ["--model", "gpt", "--", "--config"]),
                                ("codex", ["--", "--", "-cX"]), ("claude", ["--", "--settings"]),
                                ("claude", ["--", "--settings={}"]), ("claude", ["--sett", "{}"]),
                                ("claude", ["--settings-extra", "{}"]), ("claude", ["--setting-sources", "user"]),
                                ("codex", ["--conf", "notify=[]"]), ("codex", ["-"]), ("codex", [])):
            with self.subTest(name=name, arguments=arguments):
                self.assert_result(name, arguments)
        for arguments in (["--settings", "{}"], ["--settings={}"], ["--settings"],
                          ["--settings", "{}", "--", "hello"]):
            with self.subTest(arguments=arguments):
                self.assert_result("claude", arguments, blocked=True)


if __name__ == "__main__":
    unittest.main()
