"""D-148 오프라인 검사. 임시 HOME·DB 대역만 사용하며 MCP/OS 집행 증거가 아니다.

저장소 루트: python -B -X utf8 full_stack_lab/tests/user_command_settings_check.py
기기 이미지: 저장소를 /repo:ro로 마운트하고 같은 상대 경로로 실행한다.
"""
import ast
import asyncio
import builtins
import copy
import hashlib
import importlib.util
import ipaddress
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from typing import Literal
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / "full_stack_lab"
HAS_TOML = importlib.util.find_spec("tomllib") is not None
HAS_PYDANTIC = importlib.util.find_spec("pydantic") is not None


def selected(path, names, namespace=None):
    nodes = [n for n in ast.parse(path.read_text(encoding="utf-8")).body
             if getattr(n, "name", None) in names
             or isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in n.targets)]
    namespace = dict(namespace or {})
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return SimpleNamespace(**namespace)


class UserSettings(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mint-user-commands-")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve()
        self.patch_home = patch.dict(os.environ, {"HOME": str(self.home), "CODEX_HOME": str(self.home / ".codex")})
        self.patch_home.start()
        self.addCleanup(self.patch_home.stop)
        self.scan = selected(ROOT / "endpoint-agent/agent.py", {"user_command_settings", "toml_loads"},
                             {"Path": Path, "os": os, "json": json}).user_command_settings

    def write(self, name, value):
        path = self.home / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8", newline="\n")
        return path

    def test_missing_files_and_normal_json(self):
        self.assertEqual(self.scan(self.home), (True, []))
        self.write(".claude/settings.json", '{"permissions": {"allow": []}}')
        self.write(".claude/settings.local.json", '{}')
        self.assertEqual(self.scan(self.home), (True, []))

    def test_each_claude_key_in_both_files_and_empty_values(self):
        for file in ("settings.json", "settings.local.json"):
            for key in ("apiKeyHelper", "otelHeadersHelper", "awsCredentialExport", "awsAuthRefresh"):
                for value in ("PRIVATE_COMMAND_VALUE", "", None, False):
                    with self.subTest(file=file, key=key, value=value):
                        path = self.write(".claude/" + file, json.dumps({key: value}))
                        self.assertEqual(self.scan(self.home),
                                         (False, [{"file": ".claude/" + file, "keys": [key]}]))
                        path.unlink()

    def test_all_keys_report_only_file_and_names(self):
        keys = ["apiKeyHelper", "otelHeadersHelper", "awsCredentialExport", "awsAuthRefresh"]
        self.write(".claude/settings.json", json.dumps(dict.fromkeys(keys, "PRIVATE_COMMAND_VALUE")))
        ok, findings = self.scan(self.home)
        self.assertFalse(ok)
        self.assertEqual(findings, [{"file": ".claude/settings.json", "keys": sorted(keys)}])
        self.assertNotIn("PRIVATE_COMMAND_VALUE", json.dumps(findings))

    @unittest.skipUnless(HAS_TOML, "Python 3.11+ tomllib 필요")
    def test_normal_toml_and_comments_are_not_keys(self):
        self.write(".codex/config.toml", '# notify = ["comment"]\nmodel = "approved"\n[profiles.work]\nmodel = "approved"\n')
        self.write(".codex/work.config.toml", 'model = "approved"\n')
        self.write(".claude/settings.json", '{"env": {"apiKeyHelper": "not a setting"}}')
        self.assertEqual(self.scan(self.home), (True, []))

    @unittest.skipUnless(HAS_TOML, "Python 3.11+ tomllib 필요")
    def test_notify_in_config_and_profile_files(self):
        for file in ("config.toml", "work.config.toml", "other.config.toml", "UPPER.CONFIG.TOML"):
            for text in ('notify = ["PRIVATE_COMMAND_VALUE"]\n', 'notify = []\n',
                         '[profiles.work]\nnotify = ["PRIVATE_COMMAND_VALUE"]\n',
                         'profiles.work.notify = []\n', '"notify" = []\n'):
                with self.subTest(file=file, text=text):
                    path = self.write(".codex/" + file, text)
                    # Profile file names are the employee's choice: only a fixed label is reported.
                    label = ".codex/config.toml" if file == "config.toml" else ".codex/*.config.toml"
                    self.assertEqual(self.scan(self.home), (False, [{"file": label, "keys": ["notify"]}]))
                    path.unlink()

    def test_invalid_json_toml_encoding_and_shape_fail_without_values(self):
        for file, text in ((".claude/settings.json", '{"apiKeyHelper": "PRIVATE_COMMAND_VALUE",'),
                           (".claude/settings.local.json", '[]'),
                           (".claude/settings.json", '{"other": NaN}'),
                           (".codex/config.toml", 'notify = ["PRIVATE_COMMAND_VALUE"'),
                           (".codex/work.config.toml", 'invalid = [')):
            with self.subTest(file=file):
                path = self.write(file, text)
                label = ".codex/*.config.toml" if file.endswith(".config.toml") else file
                self.assertEqual(self.scan(self.home), (False, [{"file": label, "keys": []}]))
                path.write_bytes(b"\xff")
                self.assertEqual(self.scan(self.home), (False, [{"file": label, "keys": []}]))
                path.unlink()

    def test_unreadable_file_and_directory_fail_closed(self):
        self.write(".claude/settings.json", '{}')
        with patch.object(os, "open", side_effect=PermissionError("PRIVATE_COMMAND_VALUE")):
            self.assertEqual(self.scan(self.home), (False, [{"file": ".claude/settings.json", "keys": []}]))
        self.write(".codex/config.toml", '')
        # POSIX lists the opened directory handle; Windows lists the path.
        with patch.object(Path, "iterdir", side_effect=PermissionError("PRIVATE_COMMAND_VALUE")), \
             patch("os.listdir", side_effect=PermissionError("PRIVATE_COMMAND_VALUE")):
            ok, findings = self.scan(self.home)
            self.assertFalse(ok)
            self.assertIn({"file": ".codex", "keys": []}, findings)

    def test_missing_parser_is_failure(self):
        self.write(".codex/config.toml", '')
        original = builtins.__import__

        def no_toml(name, *args, **kwargs):
            if name in ("tomllib", "tomli", "toml"):  # no TOML parser at all (D-232 fallbacks too)
                raise ImportError("PRIVATE_COMMAND_VALUE")
            return original(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=no_toml):
            self.assertEqual(self.scan(self.home), (False, [{"file": ".codex/config.toml", "keys": []}]))

    def test_special_path_oversize_and_recovery(self):
        path = self.home / ".claude/settings.json"
        path.mkdir(parents=True)
        self.assertEqual(self.scan(self.home), (False, [{"file": ".claude/settings.json", "keys": []}]))
        path.rmdir()
        self.write(".claude/settings.json", " " * (1024 * 1024 + 1))
        self.assertFalse(self.scan(self.home)[0])
        self.write(".claude/settings.json", '{}')
        self.assertEqual(self.scan(self.home), (True, []))
        self.assertFalse(self.scan(Path("relative"))[0])

    def test_symlink_and_broken_link_fail_closed(self):
        outside = self.write("outside.json", '{}')
        link = self.home / ".claude/settings.json"
        link.parent.mkdir()
        try:
            link.symlink_to(outside)
        except OSError:
            self.skipTest("링크 생성 권한 없음")
        self.assertFalse(self.scan(self.home)[0])
        outside.unlink()
        self.assertFalse(self.scan(self.home)[0])

    def test_platform_checks_use_enrolled_home_not_service_home(self):
        self.write(".claude/settings.json", '{"apiKeyHelper": "PRIVATE_COMMAND_VALUE"}')
        target = self.write("managed-settings.json", '{}')
        baseline = self.write("baseline.json", '{}')
        config = {"username": "unit", "uid": 1234, "profile": str(self.home), "sid": "SID",
                  "nft_baseline": str(baseline), "firewall_baseline": str(baseline)}
        person = SimpleNamespace(pw_name="unit", pw_uid=1234, pw_gid=1234, pw_dir=str(self.home),
                                 pw_shell="/usr/local/lib/mcpgw-enforcement/mcpgw-unit/login-shell")
        real_text = Path.read_text

        def read_text(path, *args, **kwargs):
            if path.as_posix() == "/sys/kernel/security/apparmor/profiles":
                return "\n".join("mcpgw-unit" + suffix + " (enforce)" for suffix in ("", "-codex", "-claude", "-credential"))
            return real_text(path, *args, **kwargs)

        common = {"Path": Path, "hashlib": hashlib, "json": json, "sys": sys, "PROGRAMS": self.home,
                  "FILES": {"managed-settings.json": target}, "protected": lambda *args: True}
        linux = selected(ROOT / "endpoint-agent/managed-linux.py", {"checks"}, {
            **common, "__file__": str(ROOT / "endpoint-agent/managed-linux.py"),
            "pwd": SimpleNamespace(getpwnam=lambda name: person), "PRIVILEGED": set(),
            "os": SimpleNamespace(getgrouplist=lambda *args: []),
            "subprocess": SimpleNamespace(run=lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="{}")),
            "load_module": lambda *args: SimpleNamespace(user_command_settings=self.scan)})
        windows = selected(ROOT / "endpoint-agent/managed-windows.py", {"checks"}, {
            **common, "__file__": str(ROOT / "endpoint-agent/managed-windows.py"), "CODEX_BLOCK": "codex-config.toml",
            "codex_config": lambda config: self.home / "nonexistent.toml", "codex_block": lambda text: None,
            "account": lambda name: {"sid": "SID", "profile": str(self.home), "admin": False},
            "rule_state": lambda config: {}, "firewall_enforcing": lambda *args: True})
        def no_variable(*args):
            raise FileNotFoundError()

        # D-151: Windows `checks` reads the account's registry environment; Linux has no winreg.
        registry = SimpleNamespace(HKEY_USERS=0, OpenKey=no_variable)
        with patch.object(Path, "read_text", read_text), patch.dict(sys.modules, {"winreg": registry}), \
             patch.dict(os.environ, {"HOME": str(self.home / "service")}), patch.object(sys, "argv", ["check"]):
            for module in (linux, windows):
                findings = []
                _, checks = module.checks(config, {}, findings=findings)
                self.assertFalse(checks["user_command_helpers"])
                self.assertEqual(findings, [{"file": ".claude/settings.json", "keys": ["apiKeyHelper"]}])
            path = self.write(".codex/config.toml", '')
            path.write_bytes(b"\xff")
            windows.checks.__globals__["codex_config"] = lambda config: path
            findings = []
            _, checks = windows.checks(config, {}, findings=findings)
            self.assertFalse(checks["user_command_helpers"])
            self.assertIn({"file": ".codex/config.toml", "keys": []}, findings)


@unittest.skipUnless(HAS_PYDANTIC, "Pydantic 2 필요")
class HeartbeatInput(unittest.TestCase):
    def test_five_checks_findings_and_reject_command_values(self):
        from pydantic import BaseModel, ConfigDict, Field, ValidationError

        schemas = selected(LAB / "gateway/app/main.py", {"StrictModel", "UserCommandSetting", "ManagedHeartbeat"},
                           {"__name__": __name__, "BaseModel": BaseModel, "ConfigDict": ConfigDict,
                            "Field": Field, "Literal": Literal, "HostReport": BaseModel})
        body = {"policy_hash": "a" * 64, "configuration_hashes": {}, "checks": dict.fromkeys("abcde", True),
                "user_command_settings": [{"file": ".codex/*.config.toml", "keys": ["notify"]}]}
        request = schemas.ManagedHeartbeat.model_validate(body)
        self.assertEqual(len(request.checks), 5)
        with self.assertRaises(ValidationError):
            schemas.UserCommandSetting.model_validate({"file": ".codex/secret-value.config.toml", "keys": ["notify"]})
        endpoint = SimpleNamespace(heartbeat=AsyncMock(return_value={"compliant": False}))
        route = selected(LAB / "gateway/app/main.py", {"endpoint_heartbeat"}, {
            "app": SimpleNamespace(post=lambda *args: lambda fn: fn), "Depends": lambda fn: None,
            "endpoint_device": lambda scope: None, "ManagedHeartbeat": schemas.ManagedHeartbeat,
            "endpoint_plane": endpoint}).endpoint_heartbeat
        asyncio.run(route(request, {"endpoint_id": "managed"}))
        self.assertEqual(endpoint.heartbeat.call_args.kwargs["user_command_settings"], body["user_command_settings"])

        async def previous_signature(device, policy_hash, hashes, checks, host, quality):
            return {"compliant": True}

        endpoint.heartbeat = previous_signature
        request = schemas.ManagedHeartbeat.model_validate({**body, "user_command_settings": []})
        self.assertTrue(asyncio.run(route(request, {"endpoint_id": "managed"}))["compliant"])
        for changed in ({**body, "checks": dict.fromkeys("abcdef", True)},
                        {**body, "user_command_settings": [{"file": ".codex/config.toml", "keys": ["PRIVATE_COMMAND_VALUE"]}]},
                        {**body, "user_command_settings": [{"file": "/etc/private", "keys": []}]},
                        {**body, "user_command_settings": [{"file": ".codex/config.toml", "keys": [], "value": "PRIVATE_COMMAND_VALUE"}]}):
            with self.assertRaises(ValidationError):
                schemas.ManagedHeartbeat.model_validate(changed)


class ManagedFlow(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.connection = SimpleNamespace(execute=AsyncMock())
        cursor = SimpleNamespace(fetchone=AsyncMock(return_value={"managed_state": "active"}))
        self.connection.execute.return_value = cursor
        # Special methods must be on a type for async with.
        class Transaction:
            async def __aenter__(inner):
                return self.connection

            async def __aexit__(inner, *args):
                return False

        self.policy = {"policy_hash": "new", "configuration_hashes": {"settings": "digest"}}
        self.device = {"endpoint_id": "managed-check", "owner_token": "owner", "managed_state": "active", "detail": {}}
        self.plane = selected(LAB / "gateway/app/endpoint_plane.py",
                              {"MANAGED_CHECKS", "MANAGED_CHECKS_BY_PLATFORM", "managed_platform", "managed_checks", "heartbeat", "_held_policy"},
                              {"managed_policy": AsyncMock(return_value=self.policy), "Jsonb": lambda value: value,
                               "datetime": datetime, "UTC": timezone.utc,
                               "db": SimpleNamespace(transaction=Transaction)})

    async def beat(self, checks, findings=None, policy_hash="new"):
        self.connection.execute.reset_mock()
        result = await self.plane.heartbeat(self.device, policy_hash, self.policy["configuration_hashes"], checks,
                                             user_command_settings=findings)
        update = self.connection.execute.call_args_list[0].args[1]
        self.assertIs(update[4], result["compliant"])
        return result, update

    async def test_both_platforms_healthy_missing_false_wrong_hash_and_recovery(self):
        for platform in ("linux", "windows"):
            self.device["detail"] = {"local_sid": "SID"} if platform == "windows" else {}
            # An agent from before the scan is not quarantined on deploy (rollout).
            old = dict.fromkeys(self.plane.managed_checks(self.device), True)
            self.assertNotIn("user_command_helpers", old)
            result, update = await self.beat(old)
            self.assertTrue(result["compliant"])
            self.assertNotIn("command_settings_checked", update[3])
            checks = {**old, "user_command_helpers": True}
            result, update = await self.beat(checks)
            self.assertTrue(result["compliant"])
            self.assertIs(update[3]["command_settings_checked"], True)
            # Once reported, the scan stays required: an older kit cannot drop it.
            self.device["detail"]["command_settings_checked"] = True
            self.assertIn("user_command_helpers", self.plane.managed_checks(self.device))
            self.assertFalse((await self.beat(old))[0]["compliant"])
            self.assertFalse((await self.beat({**checks, "user_command_helpers": False}))[0]["compliant"])
            self.assertFalse((await self.beat(checks, policy_hash="old"))[0]["compliant"])
            self.assertTrue((await self.beat(checks))[0]["compliant"])
            self.device["managed_state"] = "quarantined"
            await self.beat(checks)
            self.assertIn("THEN managed_state ELSE 'quarantined'", self.connection.execute.call_args_list[0].args[0])
            self.device["managed_state"] = "active"

    async def test_findings_persisted_and_inconsistent_true_does_not_pass(self):
        findings = [{"file": ".codex/config.toml", "keys": ["notify"]}]
        checks = dict.fromkeys(self.plane.managed_checks(self.device), True)
        result, update = await self.beat(checks, findings)
        self.assertFalse(result["compliant"])
        self.assertFalse(update[2]["user_command_helpers"])
        self.assertEqual(update[3]["user_command_settings"], findings)
        event = self.connection.execute.call_args_list[-1].args
        self.assertIn("INSERT INTO endpoint_managed_events", event[0])
        self.assertEqual(event[1][2]["user_command_settings"], findings)
        _, update = await self.beat(checks, [])
        self.assertEqual(update[3]["user_command_settings"], [])

    async def test_policy_revision_changes_hash_without_configuration_drift(self):
        path = LAB / "gateway/app/endpoint_plane.py"
        package = ModuleType("user_commands_policy")
        package.pac = SimpleNamespace(servers_for=lambda owner: ["git"], harness_guidance=lambda owner, servers: "")
        namespace = {"__name__": "policy_under_test", "__package__": package.__name__, "os": os,
                     "urlsplit": urlsplit, "ipaddress": ipaddress, "hashlib": hashlib,
                     "HEARTBEAT_INTERVAL": 60, "HEARTBEAT_SECONDS": 180,
                     "db": SimpleNamespace(fetch_all=AsyncMock(return_value=[{"id": "git"}]), fetch_one=AsyncMock(return_value={}))}
        policy_module = selected(path, {"managed_policy", "managed_platform", "json_document"}, namespace)
        device = {**self.device, "device_epoch": "epoch", "local_username": "unit", "local_uid": 1000}
        with patch.dict(sys.modules, {package.__name__: package}), \
             patch.dict(os.environ, {"IDP_ISSUER": "https://gateway.example", "ENDPOINT_GATEWAY_IPS": "100.64.0.2"}):
            policy = await policy_module.managed_policy(device)
        self.assertEqual(policy["version"], 2)
        old = copy.deepcopy(policy)
        old.pop("policy_hash")
        old["version"] = 1
        old_hash = hashlib.sha256(policy_module.json_document(old).encode()).hexdigest()
        self.assertNotEqual(old_hash, policy["policy_hash"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
