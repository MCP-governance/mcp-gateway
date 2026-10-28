"""Offline Windows enrollment/removal regressions. Temporary profiles and OS/network doubles only."""
import argparse
import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "endpoint-agent" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Reinstall(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT, prefix=".winkit-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.m = load("windows_reinstall", "managed-windows.py")
        self.status = load("windows_install_status", "windows_status.py")
        self.profile = self.root / "employee"
        self.profile.mkdir()
        (self.profile / "NTUSER.DAT").touch()
        self.path = self.profile / ".codex/config.toml"
        self.path.parent.mkdir()
        self.person = {"sid": "S-1-5-21-1-2-3-1001", "profile": str(self.profile), "admin": False}
        self.folder = self.root / "state/employee"
        self.folder.mkdir(parents=True)
        self.config = {**self.person, "username": "employee", "gateway_url": "https://gateway.example", "mode": "simple"}
        (self.folder / "config.json").write_text(json.dumps(self.config), encoding="utf-8")
        self.enrollment = self.root / "enrollment.json"
        self.enrollment.write_text(json.dumps({"gateway_url": "https://gateway.example", "tailscale_node_id": "node",
                                               "enrollment_token": "PRIVATE-ONE-USE"}), encoding="utf-8")
        self.policy = {"tailscale_node_id": "node", "gateway_ips": ["100.64.0.1"], "gateway_port": 443,
                       "policy_hash": "policy", "files": {self.m.CODEX_BLOCK: ""}}
        self.args = argparse.Namespace(user="employee", enrollment=self.enrollment, isolated_account=False)
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.dict(sys.modules, {"windows_status": self.status}))
        self.wait = self.stack.enter_context(mock.patch.object(self.status.screen_module, "wait_summary",
                                                               return_value={"state": "active"}))
        self.stack.enter_context(mock.patch.multiple(self.m, PROGRAMS=self.root / "programs", STATE=self.root / "state",
                                                    PROGRAM_DATA=self.root / "data", FILES={}))
        self.stack.enter_context(mock.patch.object(self.m.ctypes, "windll", SimpleNamespace(
            shell32=SimpleNamespace(IsUserAnAdmin=lambda: True)), create=True))
        self.stack.enter_context(mock.patch.object(self.m, "account", return_value=self.person))
        self.stack.enter_context(mock.patch.object(self.m, "verify_transport"))
        self.stack.enter_context(mock.patch.object(self.m, "protected", return_value=True))
        self.ps = self.stack.enter_context(mock.patch.object(self.m, "powershell"))
        self.stack.enter_context(mock.patch.object(self.m, "broadcast_environment"))
        self.real_environment = self.m.set_user_environment
        self.env = self.stack.enter_context(mock.patch.object(self.m, "set_user_environment"))
        self.stack.enter_context(mock.patch("sys.stdout", io.StringIO()))

    def test_rejected_or_unreachable_registration_preserves_install_byte_for_byte(self):
        self.path.write_text('model="employee"\n', encoding="utf-8")
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        errors = [urllib.error.HTTPError("https://gateway.example", code, "used", {}, None)
                  for code in (401, 403, 409, 410)] + [urllib.error.URLError("offline")]
        for error in errors:
            with self.subTest(error=error), mock.patch.object(self.m, "request", side_effect=error), \
                    mock.patch.object(self.m, "rollback") as rollback, mock.patch.object(self.m, "lock_down") as lock:
                with self.assertRaises((ValueError, OSError)) as failure:
                    self.m.install(self.args)
                if isinstance(error, urllib.error.HTTPError):
                    self.assertEqual(str(failure.exception), "이미 연결되어 있습니다")
                rollback.assert_not_called()
                lock.assert_not_called()
                self.ps.assert_not_called()
                self.env.assert_not_called()
                self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_policy_failure_also_preserves_old_install(self):
        original = (self.folder / "config.json").read_bytes()
        with mock.patch.object(self.m, "request", side_effect=[{"endpoint_id": "new"}, OSError("offline")]):
            with self.assertRaises(OSError):
                self.m.install(self.args)
        self.assertEqual((self.folder / "config.json").read_bytes(), original)
        self.ps.assert_not_called()

    def test_success_enrolls_then_replaces_without_rolling_back_same_account(self):
        order = []
        harness = Path(self.person["profile"]) / ".local/bin/claude.exe"
        harness.parent.mkdir(parents=True)
        harness.touch()
        (self.folder / "config.toml.backup").write_text("original employee backup", encoding="utf-8")
        def request(config, path, *a, **kw):
            self.assertNotIn("endpoint_id", json.loads((self.folder / "config.json").read_text()))
            order.append(path)
            return {"endpoint_id": "new", "state": "pending"} if path == "/oauth/device-enroll" else self.policy
        self.ps.side_effect = lambda *a, **kw: order.append("task")
        with mock.patch.object(self.m, "request", side_effect=request), \
                mock.patch.object(self.m, "lock_down", side_effect=lambda p, **kw: p.mkdir(parents=True, exist_ok=True)), \
                mock.patch.object(self.m, "rollback") as rollback, mock.patch.object(self.m, "retire_companion"), \
                mock.patch.object(self.m, "apply_policy"), mock.patch.object(self.m, "ca_environment", return_value={}):
            self.m.install(self.args)
        self.assertEqual(order[:3], ["/oauth/device-enroll", "/api/endpoint/managed-policy", "task"])
        rollback.assert_not_called()
        self.assertEqual(json.loads((self.folder / "config.json").read_text())["endpoint_id"], "new")
        self.assertEqual(json.loads((self.folder / "config.json").read_text())["harness_paths"], [str(harness)])
        self.assertEqual((self.folder / "config.toml.backup").read_text(), "original employee backup")
        self.assertFalse(self.enrollment.exists())
        self.assertEqual(json.loads(sys.stdout.getvalue().splitlines()[0])["state"], "active")
        self.assertIn("since", self.wait.call_args.kwargs)

    def test_unprotected_receipt_is_rejected_before_read_or_change(self):
        self.args.registration = self.root / "missing-receipt.json"
        with mock.patch.object(self.m, "protected", return_value=False), mock.patch.object(self.m, "request") as request:
            with self.assertRaisesRegex(ValueError, "보호된 등록"):
                self.m.install(self.args)
        request.assert_not_called()
        self.ps.assert_not_called()

    def test_protected_preflight_receipt_is_used_without_redeeming_token_twice(self):
        receipt = {"employee": "employee", "config": {**self.config, "endpoint_id": "new", "device_key": "PRIVATE-KEY"},
                   "policy": self.policy, "enrolled": {"state": "active"}, "companion": False, "source_person": None}
        self.args.registration = self.root / "registration.json"
        self.args.registration.write_text(json.dumps(receipt), encoding="utf-8")
        with mock.patch.object(self.m, "request") as request, \
                mock.patch.object(self.m, "lock_down", side_effect=lambda p, **kw: p.mkdir(parents=True, exist_ok=True)), \
                mock.patch.object(self.m, "retire_companion"), mock.patch.object(self.m, "apply_policy"), \
                mock.patch.object(self.m, "ca_environment", return_value={}):
            self.m.install(self.args)
        request.assert_not_called()
        self.assertEqual(json.loads((self.folder / "config.json").read_text())["endpoint_id"], "new")

    def test_malformed_markers_are_backed_up_without_changing_employee_or_machine_files(self):
        variants = [self.m.BEGIN + "\r\nprivate=true\r\n", self.m.END + "\r\n", self.m.END + "\n" + self.m.BEGIN,
                    self.m.BEGIN + "\n" + self.m.BEGIN + "\n" + self.m.END + "\n",
                    self.m.BEGIN + '\n[mcp_servers.foreign]\nnote="""\n[mcp_servers.approved]\n"""\n' + self.m.END + "\n"]
        for value in variants:
            with self.subTest(value=value):
                original = value.encode("utf-8")
                self.path.write_bytes(original)
                with self.assertRaisesRegex(ValueError, "관리 구간"):
                    self.m.rollback(self.args)
                with mock.patch.object(self.m, "request") as request:
                    with self.assertRaisesRegex(ValueError, "관리 구간"):
                        self.m.install(self.args)
                    request.assert_not_called()
                self.assertEqual(self.path.read_bytes(), original)
                self.assertIn(original, [p.read_bytes() for p in self.path.parent.glob("*.backup")])
        self.ps.assert_not_called()
        self.env.assert_not_called()

    def test_markers_inside_values_are_not_delimiters(self):
        text = 'note = "' + self.m.BEGIN + '"\n'
        self.assertIsNone(self.m.codex_block(text))
        self.assertEqual(self.m.without_codex_block(text), text)

    def test_foreign_table_inside_pair_survives_replacement_and_removal(self):
        owned = '[mcp_servers.approved]\nurl="https://gateway.example/mcp/approved/"\nhttp_headers_helper="managed-windows.py header"\n'
        foreign = '[mcp_servers.node_repl]\ncommand="employee tool"\n'
        text = self.m.BEGIN + "\n" + owned + foreign + self.m.END + "\n"
        changed = self.m.with_codex_block(text, owned)
        self.assertEqual(changed.count(foreign), 1)
        self.assertEqual(changed.count(owned), 1)
        self.assertEqual(self.m.without_codex_block(text, owned), foreign)
        self.assertEqual(self.m.without_codex_block(text), foreign)  # legacy install without ownership cache

    def test_missing_config_removes_owned_traces_but_keeps_employee_settings(self):
        (self.folder / "config.json").unlink()
        self.path.write_text('model="employee"\n', encoding="utf-8")
        managed = self.root / "managed-mcp.json"
        managed.write_text('{"headersHelper":"managed-windows.py header"}', encoding="utf-8")
        unrelated = self.root / "unrelated.json"
        unrelated.write_text('{"employee":true}', encoding="utf-8")
        tray = self.m.PROGRAM_DATA / "MCPGatewayManagedTray" / self.person["sid"]
        tray.mkdir(parents=True)
        (tray / "settings.json").write_text("{}")
        status = load("windows_reinstall_status", "windows_status.py")
        publish = mock.Mock(wraps=status.publish)
        with mock.patch.object(self.m, "FILES", {"managed-mcp.json": managed, "unrelated": unrelated}), \
                mock.patch.dict(sys.modules, {"windows_status": SimpleNamespace(publish=publish)}):
            self.m.rollback(self.args)
        self.assertFalse(managed.exists())
        self.assertTrue(unrelated.exists())
        self.assertFalse(self.folder.exists())
        self.assertFalse(tray.exists())
        self.assertEqual(self.path.read_text(), 'model="employee"\n')
        publish.assert_called_once_with(tray / "status.json", False, management="제거됨", details={"state": "removed"})
        self.env.assert_called_once_with({**self.person, "username": "employee"}, {}, owned_only=True)
        tasks = [c.args[1]["name"] for c in self.ps.call_args_list]
        self.assertEqual(tasks, ["MCPGatewayManaged-employee", "MCPGatewayTray-" + self.person["sid"]])

    def test_owned_only_environment_cleanup_preserves_unrelated_ca_and_proxy(self):
        values = {"NODE_EXTRA_CA_CERTS": str(self.m.PROGRAMS / "launchers/root.crt"),
                  "CODEX_CA_CERTIFICATE": "employee-root.crt", "HTTPS_PROXY": "https://employee-proxy", "PATH": "employee-bin"}
        key = mock.MagicMock()
        key.__enter__.return_value = key
        registry = SimpleNamespace(HKEY_USERS=object(), KEY_SET_VALUE=1, KEY_QUERY_VALUE=2, REG_SZ=1, REG_EXPAND_SZ=2,
                                   OpenKey=mock.Mock(), CreateKeyEx=mock.Mock(return_value=key))
        def query(k, name):
            if name not in values:
                raise FileNotFoundError(name)
            return values[name], 1
        registry.QueryValueEx = query
        registry.DeleteValue = lambda k, name: values.pop(name)
        registry.SetValueEx = lambda k, name, reserved, kind, value: values.__setitem__(name, value)
        with mock.patch.dict(sys.modules, {"winreg": registry}):
            self.real_environment(self.config, {}, owned_only=True)
        self.assertNotIn("NODE_EXTRA_CA_CERTS", values)
        self.assertEqual(values["CODEX_CA_CERTIFICATE"], "employee-root.crt")
        self.assertEqual(values["HTTPS_PROXY"], "https://employee-proxy")


if __name__ == "__main__":
    unittest.main()
