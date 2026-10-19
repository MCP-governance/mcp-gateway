"""D-151 오프라인 검사. 가짜 winreg·임시 HOME만 사용하며 실제 레지스트리/OS 집행 증거가 아니다.

저장소 루트: python -B -X utf8 full_stack_lab/tests/windows_config_env_check.py
"""
import ast
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Literal
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / "full_stack_lab"
HAS_PYDANTIC = importlib.util.find_spec("pydantic") is not None
MARK = "PRIVATE_CONFIG_HOME"  # json.dumps가 역슬래시를 바꾸므로 경로 대신 표식 문자열로 누출을 확인한다
SECRET = "C:/Users/unit/" + MARK


def selected(path, names, namespace=None):
    nodes = [n for n in ast.parse(path.read_text(encoding="utf-8")).body
             if getattr(n, "name", None) in names
             or isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in n.targets)]
    namespace = dict(namespace or {})
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return SimpleNamespace(**namespace)


class FakeRegistry:
    """`checks`가 쓰는 winreg 부분만. 없는 값·키는 실제처럼 FileNotFoundError."""
    HKEY_USERS = object()

    def __init__(self, values=None, open_error=None, query_error=None):
        self.values, self.open_error, self.query_error = values, open_error, query_error
        self.opened = []

    def OpenKey(self, root, path):
        self.opened.append((root, path))
        if self.open_error:
            raise self.open_error
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def QueryValueEx(self, key, name):
        if self.query_error:
            raise self.query_error
        if name not in self.values:
            raise FileNotFoundError(2, "value not found")
        return self.values[name], 1


class EnvironmentCheck(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mint-config-env-")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve()
        self.config = {"username": "unit", "profile": str(self.home), "sid": "S-1-5-21-1-2-3-1001",
                       "firewall_baseline": str(self.home / "baseline.json")}
        target = self.home / "managed-settings.json"
        target.write_text("{}", encoding="utf-8")
        (self.home / "baseline.json").write_text("{}", encoding="utf-8")
        self.windows = selected(ROOT / "endpoint-agent/managed-windows.py", {"checks"}, {
            "__file__": str(ROOT / "endpoint-agent/managed-windows.py"), "Path": Path, "json": json, "sys": sys,
            "hashlib": __import__("hashlib"), "PROGRAMS": self.home, "FILES": {"managed-settings.json": target},
            "CODEX_BLOCK": "codex-config.toml", "protected": lambda *args: True,
            "codex_config": lambda config: self.home / "nonexistent.toml", "codex_block": lambda text: None,
            "account": lambda name: {"sid": self.config["sid"], "profile": str(self.home), "admin": False},
            "rule_state": lambda config: {}, "firewall_enforcing": lambda *args: True})

    def run_checks(self, registry):
        findings = []
        with patch.dict(sys.modules, {"winreg": registry}), patch.object(sys, "argv", ["check"]):
            _, checks = self.windows.checks(self.config, {}, findings=findings)
        self.assertNotIn(MARK, json.dumps(findings))
        return checks["user_command_helpers"], findings

    def test_neither_variable_is_clean_and_reads_the_account_hive(self):
        registry = FakeRegistry({"HTTPS_PROXY": SECRET, "PATH": SECRET})
        self.assertEqual(self.run_checks(registry), (True, []))
        self.assertEqual(registry.opened, [(FakeRegistry.HKEY_USERS, self.config["sid"] + "\\Environment")])

    def test_codex_home_and_claude_config_dir_are_findings_without_values(self):
        for values, labels in (({"CODEX_HOME": SECRET}, ["env:CODEX_HOME"]),
                               ({"CLAUDE_CONFIG_DIR": SECRET}, ["env:CLAUDE_CONFIG_DIR"]),
                               ({"CLAUDE_CONFIG_DIR": SECRET, "CODEX_HOME": SECRET},
                                ["env:CODEX_HOME", "env:CLAUDE_CONFIG_DIR"])):
            with self.subTest(values=list(values)):
                self.assertEqual(self.run_checks(FakeRegistry(values)),
                                 (False, [{"file": label, "keys": []} for label in labels]))

    def test_empty_value_still_counts(self):
        self.assertEqual(self.run_checks(FakeRegistry({"CLAUDE_CONFIG_DIR": ""})),
                         (False, [{"file": "env:CLAUDE_CONFIG_DIR", "keys": []}]))

    def test_signed_out_account_has_no_hive_and_no_environment_key(self):
        self.assertEqual(self.run_checks(FakeRegistry(open_error=FileNotFoundError(2, "key not found"))), (True, []))

    def test_other_registry_errors_fail_closed_with_fixed_label(self):
        for registry in (FakeRegistry(open_error=PermissionError(5, SECRET)),
                         FakeRegistry({}, query_error=PermissionError(5, SECRET)),
                         FakeRegistry({}, query_error=OSError(1450, SECRET)),
                         None):  # winreg를 가져올 수 없는 호스트
            with self.subTest(registry=registry):
                self.assertEqual(self.run_checks(registry), (False, [{"file": "env", "keys": []}]))

    def test_error_after_a_hit_reports_only_env(self):
        class HalfBroken(FakeRegistry):
            def QueryValueEx(self, key, name):
                if name == "CODEX_HOME":
                    return SECRET, 1
                raise PermissionError(5, SECRET)

        self.assertEqual(self.run_checks(HalfBroken({})), (False, [{"file": "env", "keys": []}]))

    def test_file_findings_are_kept_and_environment_comes_after(self):
        settings = self.home / ".claude/settings.json"
        settings.parent.mkdir()
        settings.write_text(json.dumps({"apiKeyHelper": SECRET}), encoding="utf-8")
        self.assertEqual(self.run_checks(FakeRegistry({"CODEX_HOME": SECRET})),
                         (False, [{"file": ".claude/settings.json", "keys": ["apiKeyHelper"]},
                                  {"file": "env:CODEX_HOME", "keys": []}]))


@unittest.skipUnless(HAS_PYDANTIC, "Pydantic 2 필요")
class HeartbeatInput(unittest.TestCase):
    def test_gateway_accepts_only_the_fixed_environment_labels(self):
        from pydantic import BaseModel, ConfigDict, Field, ValidationError

        schemas = selected(LAB / "gateway/app/main.py", {"StrictModel", "UserCommandSetting", "ManagedHeartbeat"},
                           {"__name__": __name__, "BaseModel": BaseModel, "ConfigDict": ConfigDict,
                            "Field": Field, "Literal": Literal, "HostReport": BaseModel})
        for label in ("env:CODEX_HOME", "env:CLAUDE_CONFIG_DIR", "env", ".codex/config.toml"):
            with self.subTest(label=label):
                self.assertEqual(schemas.UserCommandSetting.model_validate({"file": label, "keys": []}).file, label)
        body = {"policy_hash": "a" * 64, "configuration_hashes": {}, "checks": dict.fromkeys("abcde", True),
                "user_command_settings": [{"file": "env:CODEX_HOME", "keys": []}]}
        self.assertEqual(len(schemas.ManagedHeartbeat.model_validate(body).user_command_settings), 1)
        for label in ("env:HOME", "env:codex_home", "env:CODEX_HOME=" + SECRET, "env:CODEX_HOME ", "ENV", "",
                      "env:CODEX_HOME/x"):
            with self.subTest(label=label), self.assertRaises(ValidationError):
                schemas.UserCommandSetting.model_validate({"file": label, "keys": []})
        with self.assertRaises(ValidationError):
            schemas.UserCommandSetting.model_validate({"file": "env:CODEX_HOME", "keys": [], "value": SECRET})


if __name__ == "__main__":
    unittest.main(verbosity=2)
