"""D-150 적대 회귀. 실패는 미수정 결함이며 실제 MCP/하네스 실행 증거가 아니다."""
import importlib.util
import io
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[2]


def load(relative, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WindowsLauncherAdversarialCheck(unittest.TestCase):
    def setUp(self):
        self.module = load("endpoint-agent/managed-windows.py", "launcher_adversarial_windows")
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)

    def assert_forwarded(self, name, arguments):
        with patch.object(self.module.subprocess, "call", return_value=7) as call, \
                patch("sys.stderr", new_callable=io.StringIO):
            result = self.module.launch_harness(name, ["--", *arguments], "C:/Managed", "C:/Native.exe")
        self.assertEqual(result, 7)
        call.assert_called_once_with(["C:/Native.exe", *arguments])

    def test_normal_prompt_cd_and_exec_model_are_forwarded(self):
        for arguments in (["explain -c without executing"], ["-C", "src"],
                          ["exec", "-m", "gpt", "explain -c"]):
            with self.subTest(arguments=arguments):
                self.assert_forwarded("codex", arguments)

    def test_codex_attached_option_values_are_not_config_options(self):
        for arguments in (["-Csrc"], ["exec", "-mgpt-codex", "hello"], ["-pconfig"]):
            with self.subTest(arguments=arguments):
                self.assert_forwarded("codex", arguments)

    def test_literal_config_text_after_double_dash_is_forwarded(self):
        for name, arguments in (("codex", ["--", "-c"]),
                                ("claude", ["--", "--settings"])):
            with self.subTest(name=name):
                self.assert_forwarded(name, arguments)

    def test_real_override_before_delimiter_is_still_blocked(self):
        for name, arguments in (("codex", ["-c", "notify=[]", "--", "hello"]),
                                ("codex", ["--config=notify=[]"]),
                                ("claude", ["--settings", "{}"]),
                                ("claude", ["--settings={}"])):
            with self.subTest(name=name, arguments=arguments), \
                    patch.object(self.module.subprocess, "call") as call, \
                    patch("sys.stderr", new_callable=io.StringIO):
                self.assertEqual(self.module.launch_harness(name, arguments, "C:/Managed", "C:/Native.exe"), 2)
                call.assert_not_called()

    def test_alternate_surfaces_are_forwarded_not_proven_bypasses(self):
        for name, arguments in (
                ("codex", ["--profile", "work"]),
                ("codex", ["--enable", "hooks", "--disable", "plugins"]),
                ("codex", ["--conf", "notify=[]"]),
                ("claude", ["--setting-sources", "user,project"]),
                ("claude", ["--mcp-config", "empty.json"]),
                ("claude", ["--plugin-dir", "plugins", "--add-dir", "workspace"]),
                ("claude", ["--sett", "{}"])):
            with self.subTest(name=name, arguments=arguments):
                self.assert_forwarded(name, arguments)

    def test_windows_child_wait_and_exit_code_with_a_process_fixture(self):
        # 통신/CLI 대역이 아니라 종료 코드·대기만 확인하는 표준 Python 자식이다.
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / "finished"
            script = Path(folder) / "child.py"
            script.write_text("from pathlib import Path\nimport sys, time\n"
                              "time.sleep(0.05)\nPath(sys.argv[1]).write_text('done')\nsys.exit(7)\n",
                              encoding="utf-8", newline="")
            result = self.module.launch_harness("codex", [str(script), str(marker)], folder, sys.executable)
            self.assertEqual(result, 7)
            self.assertEqual(marker.read_text(), "done")

    def test_first_interrupt_does_not_force_kill_a_child_that_handles_it(self):
        # 콘솔 신호를 보내지 않는다. CPython call의 예외 경로만 재현한다.
        with patch.object(self.module.subprocess, "Popen") as popen:
            child = popen.return_value.__enter__.return_value
            child.wait.side_effect = KeyboardInterrupt
            with self.assertRaises(KeyboardInterrupt):
                self.module.launch_harness("codex", [], "C:/Managed", "C:/Native.exe")
            child.kill.assert_not_called()

    def test_home_cleanup_does_not_clean_other_inherited_environment(self):
        os.environ.update(CODEX_HOME="caller-codex", CLAUDE_CONFIG_DIR="caller-claude",
                          HOME="caller-home", USERPROFILE="caller-profile",
                          CLAUDE_CODE_EXTRA_BODY="{}", CODEX_REVIEW_SENTINEL="synthetic")
        with patch.object(self.module.subprocess, "call", return_value=0):
            self.module.launch_harness("codex", [], "C:/Managed", "C:/Native.exe")
            self.assertEqual(os.environ["CODEX_HOME"], str(Path("C:/Managed") / ".codex"))
            self.module.launch_harness("claude", [], "C:/Managed", "C:/Native.exe")
        self.assertNotIn("CLAUDE_CONFIG_DIR", os.environ)
        # 이것은 상속 재현이다. 실제 Claude의 홈 선택·설정 실행 성공을 뜻하지 않는다.
        self.assertEqual(os.environ["USERPROFILE"], "caller-profile")
        self.assertEqual(os.environ["HOME"], "caller-home")
        self.assertEqual(os.environ["CLAUDE_CODE_EXTRA_BODY"], "{}")
        self.assertEqual(os.environ["CODEX_REVIEW_SENTINEL"], "synthetic")

    def test_launch_cli_rejects_an_unregistered_profile(self):
        arguments = ["managed-windows.py", "launch", "--profile", "C:/UnregisteredProfile",
                     "--native", "C:/Native.exe", "codex", "--", "exec", "hello"]
        with patch.object(sys, "argv", arguments), \
                patch("sys.stdout", new_callable=io.StringIO), \
                patch("sys.stderr", new_callable=io.StringIO), \
                patch.object(self.module.subprocess, "call", return_value=7) as call:
            with self.assertRaises(SystemExit):
                self.module.main()
            call.assert_not_called()

    def test_same_prefix_unrelated_path_is_preserved(self):
        programs = Path("C:/Program Files/MCPGatewayManaged")
        sibling = str(Path(str(programs) + "Tools"))
        launcher = str(programs / "launchers" / "SID")
        registry = MagicMock()
        registry.QueryValueEx.return_value = (sibling + ";C:/Other", 2)
        with patch.dict(sys.modules, {"winreg": registry}), \
                patch.object(self.module, "PROGRAMS", programs), \
                patch.object(self.module.os, "pathsep", ";"):
            self.module.set_user_environment({"sid": "SID", "profile": "C:/Managed"}, {"PATH_APPEND": launcher})
        paths = [call.args[4] for call in registry.SetValueEx.call_args_list if call.args[1] == "PATH"]
        self.assertEqual(paths, [launcher + ";" + sibling + ";C:/Other"])


@unittest.skipUnless(platform.system() == "Linux" and shutil.which("gcc"), "Linux gcc 필요")
class LinuxLauncherAdversarialCheck(unittest.TestCase):
    def setUp(self):
        self.module = load("endpoint-agent/enforce-linux.py", "launcher_adversarial_linux")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)

    def test_linux_attached_values_and_literal_arguments(self):
        for name, arguments in (("codex", ["-Csrc"]), ("codex", ["-mgpt-codex"]),
                                ("codex", ["-pconfig"]), ("codex", ["--", "-c"]),
                                ("claude", ["--", "--settings"])):
            with self.subTest(name=name, arguments=arguments):
                launcher = self.folder / name
                self.module.wrapper(launcher, Path(shutil.which("echo")), str(self.folder), "managed", guard=name)
                done = subprocess.run([str(launcher), *arguments], capture_output=True, text=True, check=False)
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(done.stdout.strip(), " ".join(arguments))

    def test_linux_clearenv_removes_caller_codex_and_claude_variables(self):
        launcher = self.folder / "codex"
        self.module.wrapper(launcher, Path(shutil.which("env")), str(self.folder), "managed", guard="codex",
                            environment={"HTTPS_PROXY": "http://127.0.0.1:9"})
        environment = dict(os.environ, CODEX_HOME="synthetic", CLAUDE_CONFIG_DIR="synthetic",
                           CODEX_REVIEW_SENTINEL="synthetic", CLAUDE_REVIEW_SENTINEL="synthetic")
        done = subprocess.run([str(launcher)], env=environment, capture_output=True, text=True, check=True)
        names = {line.split("=", 1)[0] for line in done.stdout.splitlines()}
        self.assertFalse(any(name.startswith(("CODEX_", "CLAUDE_")) for name in names))
        self.assertIn("https_proxy", names)


if __name__ == "__main__":
    unittest.main()
