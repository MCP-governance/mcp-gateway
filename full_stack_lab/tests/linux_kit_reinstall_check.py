"""Offline reinstall regressions. All paths/HOME are temporary; OS and enrollment are doubles."""
import argparse
import importlib.util
import io
import json
import os
import shlex
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

KIT = Path(__file__).resolve().parents[2] / "endpoint-agent"


def load(name, path=None):
    stubs = {n: ModuleType(n) for n in ("pwd", "grp") if n not in sys.modules}
    with patch.dict(sys.modules, stubs):
        spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path or KIT / (name + ".py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


class Reinstall(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {"HOME": str(self.root), "CODEX_HOME": str(self.root / ".codex"),
                                           "MCPGW_HOME": str(self.root / "legacy")})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.core, self.boot, self.mac = [load(n) for n in ("managed-linux", "bootstrap", "managed-macos")]
        self.bundle = {"gateway_url": "https://gw.example", "tailscale_node_id": "node", "enrollment_token": "enroll-secret"}
        self.enrollment = self.root / "enrollment.json"
        self.enrollment.write_text(json.dumps(self.bundle))
        self.person = SimpleNamespace(pw_uid=1001, pw_gid=1001, pw_dir="/home/emp", pw_name="emp", pw_shell="/bin/bash")
        self.policy = {"tailscale_node_id": "node", "gateway_ips": ["127.0.0.1"], "gateway_port": 443,
                       "policy_hash": "p", "files": dict.fromkeys(self.core.FILES, "managed")}

    def test_consumed_linux_kit_reports_existing_employee_or_companion_without_reenrollment(self):
        b = self.boot
        self.enrollment.unlink()
        for account in ("emp", "managed-emp"):
            config = self.root / account / "config.json"
            config.parent.mkdir()
            config.write_text('{}')
            with self.subTest(account=account), patch.object(b, "STATE", self.root), \
                 patch.object(b, "employee_account", return_value="emp"), patch.object(b, "check_python"), \
                 patch.object(b, "os", SimpleNamespace(name="posix", geteuid=lambda: 0)), \
                 patch.dict(sys.modules, {"pwd": ModuleType("pwd"), "grp": ModuleType("grp")}), \
                 patch.object(b, "connect") as connect, patch.object(b, "rollback") as remove, \
                 patch.object(sys, "argv", ["bootstrap.py", "--enrollment", str(self.enrollment)]), \
                 redirect_stdout(io.StringIO()) as output:
                self.assertEqual(b.main(), 0)
            self.assertIn("이미 설치됨", output.getvalue())
            self.assertIn("mcpgw-status --check", output.getvalue())
            self.assertIn("콘솔에서 새 키트", output.getvalue())
            connect.assert_not_called()
            remove.assert_not_called()
            self.assertFalse(self.enrollment.exists())
            config.unlink()

    def linux_install_flow(self, model_detail="", harness="claude", binary=None):
        """Real bootstrap/installer/check/JSON; only OS, enrollment and model transport are doubles."""
        b, c = self.boot, self.core
        programs = self.root / "programs"
        report = programs / "status-emp.json"
        config = {"device_key": "synthetic", "gateway_url": "https://gw.example", "tailscale_node_id": "node"}
        prepared = (config, self.policy, {"endpoint_id": "new", "state": "pending-organization-activation"})
        observer = SimpleNamespace(MODEL_PROMPT="OK", model_check=Mock(return_value={
            "ok": not model_detail, "seconds": 1, "detail": model_detail}))
        installed = []
        install_managed = b.install_managed
        subprocess_run = subprocess.run
        def capture_install(*args, **kwargs):
            result = install_managed(*args, **kwargs)
            installed.append(dict(result))
            return result
        def run(argv, **kwargs):
            if argv[0] == shutil.which("node"):
                return subprocess_run(argv, **kwargs)
            if argv[:3] == ["systemctl", "enable", "--now"]:
                c.private_write(report, json.dumps({"user": "emp", "state": "active", "updated": c.time.time(), "connected": True,
                                                   "names": ["memory"]}))
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        def local_path(*parts):
            path = Path(*parts)
            if str(parts[0]).startswith("/etc/systemd/"):
                path = self.root / "systemd" / path.name
                path.parent.mkdir(exist_ok=True)
            return path
        screen = Mock(summary={})
        with ExitStack() as stack:
            for name in ("ensure_packages", "remove_shims", "remove_companion"):
                stack.enter_context(patch.object(b, name))
            stack.enter_context(patch.object(b, "installed", return_value=False))
            stack.enter_context(patch.object(b, "find_clients", return_value={harness: binary or "/usr/bin/" + harness}))
            stack.enter_context(patch.object(b, "STATE", self.root / "state"))
            stack.enter_context(patch.object(b, "SCREEN", screen))
            stack.enter_context(patch.object(b, "install_managed", side_effect=capture_install))
            stack.enter_context(patch.object(b, "pwd", SimpleNamespace(getpwnam=lambda n: self.person)))
            # Keep the actual imported install function, while allowing temporary OS paths.
            stack.enter_context(patch.object(b.importlib.util, "spec_from_file_location", return_value=SimpleNamespace(
                loader=SimpleNamespace(exec_module=lambda module: None))))
            stack.enter_context(patch.object(b.importlib.util, "module_from_spec", return_value=c))
            for name, value in {"PROGRAMS": programs, "STATE": b.STATE,
                                "FILES": {name: self.root / "settings" / name for name in c.FILES},
                                "ENVIRONMENT": self.root / "environment", "Path": local_path,
                                "pwd": SimpleNamespace(getpwnam=lambda n: self.person),
                                "grp": SimpleNamespace(getgrgid=lambda n: SimpleNamespace(gr_name="users"))}.items():
                stack.enter_context(patch.object(c, name, value))
            for name in ("verify_transport", "forget_stale_sign_in", "write_helper", "write_status_shim", "diagnostic"):
                stack.enter_context(patch.object(c, name))
            stack.enter_context(patch.object(c, "protected", return_value=True))
            stack.enter_context(patch.object(c.os, "geteuid", return_value=0, create=True))
            stack.enter_context(patch.object(c.os, "getgrouplist", return_value=[], create=True))
            stack.enter_context(patch.object(c, "enroll", return_value=prepared))
            stack.enter_context(patch.object(c.subprocess, "run", side_effect=run))
            stack.enter_context(patch.object(c, "load_module", return_value=observer))
            stack.enter_context(patch.object(c, "check_connection", return_value={
                "initialized": ["memory"], "failed": {}, "tools": 2}))
            # An existing credentials file is deliberately expired at the provider.
            home = self.root / "home"
            credential = home / b.LOGINS[harness][0]
            credential.parent.mkdir(parents=True)
            credential.write_text('{}')
            stack.enter_context(patch.object(b, "pwd", SimpleNamespace(getpwnam=lambda n: SimpleNamespace(
                pw_uid=1001, pw_dir=str(home)))))
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(b.connect(c, "emp", False, SimpleNamespace(
                    enrollment=self.enrollment, skip_login=False), 0), 0)
        result = json.loads(output.getvalue().splitlines()[-1])
        with patch.object(c, "PROGRAMS", programs):
            summary = c.model_status(json.loads(report.read_text()))
            with patch.object(c, "Screen", return_value=SimpleNamespace(window=None)), \
                 patch.object(c, "check_connection", return_value={"initialized": ["memory"], "tools": 2}), \
                 redirect_stdout(io.StringIO()) as status_output:
                c.status(SimpleNamespace(user="emp", check=True))
        self.assertEqual(summary["model_signed_in"], result["model_signed_in"])
        if summary["model_signed_in"].get(harness) is False:
            self.assertIn(b.LOGINS[harness][1], status_output.getvalue())
        self.assertFalse(self.enrollment.exists())
        self.assertEqual(installed[0]["state"], "active")
        self.assertEqual(result["state"], "active")
        self.assertEqual(screen.summary["state"], "active")
        self.assertIn(binary or "/usr/bin/" + harness,
                      json.loads((self.root / "state/emp/config.json").read_text())["harness_paths"])
        return result, screen

    def npm_codex_entry(self, platform_package=True):
        entry = self.root / "npm space/node_modules/@openai/codex/bin/codex.js"
        entry.parent.mkdir(parents=True)
        entry.write_text("// synthetic npm entry; must not be executed\n")
        # Use the real Node platform and module resolver, but never execute a harness.
        target = subprocess.run([shutil.which("node"), "-p", "JSON.stringify([process.platform, process.arch])"],
                                capture_output=True, text=True, check=True)
        system, arch = json.loads(target.stdout)
        machine = {"x64": "x86_64", "arm64": "aarch64"}[arch]
        suffix = {"linux": "unknown-linux-musl", "darwin": "apple-darwin", "win32": "pc-windows-msvc"}[system]
        package = entry.parents[2] / ("codex-" + system + "-" + arch) if platform_package else entry.parents[1]
        package.mkdir(exist_ok=True)
        if platform_package:
            (package / "package.json").write_text('{}')
        native = package / "vendor" / (machine + "-" + suffix) / "bin" / ("codex.exe" if system == "win32" else "codex")
        native.parent.mkdir(parents=True)
        native.touch()
        return entry, native

    @unittest.skipUnless(shutil.which("node"), "Node.js is needed for npm entry resolution")
    def test_npm_codex_install_registers_only_the_resolved_native_child(self):
        entry, native = self.npm_codex_entry()
        unrelated = native.parent / "server-fastmcp"
        unrelated.touch()
        self.linux_install_flow(harness="codex", binary=str(entry))
        paths = json.loads((self.root / "state/emp/config.json").read_text())["harness_paths"]
        self.assertEqual(paths, [str(entry), str(native.resolve())])
        observer = load("npm_observer", KIT / "agent.py")
        with patch.object(observer, "CONFIG", {"ENDPOINT_HARNESS_PATHS": paths}):
            self.assertTrue(observer.harness_process(f'"{native}" exec "fastmcp"'))
            self.assertFalse(observer.harness_process(f'"{unrelated}" -m fastmcp run server.py'))
            with patch.object(observer.platform, "system", return_value="Windows"), \
                 patch.object(observer, "_windows_processes", return_value={"123": ("codex", f'"{native}" exec fastmcp')}):
                self.assertEqual(observer.stdio_processes(), [])
            row = {"address": "127.0.0.1", "port": 54321, "command_line": f'"{native}" exec fastmcp'}
            with patch.object(observer, "local_listeners", return_value=[row]), \
                 patch.object(observer, "probe_mcp", return_value=None):
                self.assertEqual(observer.listener_findings({"probe_mcp": False}), [])
            with patch.object(observer, "local_listeners", return_value=[row]), \
                 patch.object(observer, "probe_mcp", return_value={"server_name": "synthetic"}):
                self.assertEqual(observer.listener_findings({})[0]["mcp_evidence"], "confirmed")

    @unittest.skipUnless(shutil.which("node"), "Node.js is needed for npm entry resolution")
    def test_npm_codex_vendor_fallback_missing_binary_and_resolver_failure(self):
        entry, native = self.npm_codex_entry(platform_package=False)
        binaries = {"codex": str(entry)}
        with patch.dict(os.environ, {"NODE_OPTIONS": "--require=/unapproved/injection.js", "NODE_PATH": "/unapproved"}):
            self.assertEqual(self.core.harness_paths(binaries), [str(entry), str(native.resolve())])
        native.unlink()
        self.assertEqual(self.core.harness_paths(binaries), [str(entry)])
        for error in (OSError("node unavailable"), subprocess.TimeoutExpired("node", 5),
                      subprocess.CalledProcessError(1, "node")):
            with self.subTest(error=type(error).__name__), patch.object(self.core.subprocess, "run", side_effect=error):
                self.assertEqual(self.core.harness_paths(binaries), [str(entry)])
        with patch.object(self.core.shutil, "which", return_value=None):
            self.assertEqual(self.core.harness_paths(binaries), [str(entry)])
        other = self.root / "unregistered/codex.js"
        other.parent.mkdir()
        other.touch()
        with patch.object(self.core.subprocess, "run") as run:
            self.assertEqual(self.core.harness_paths({"codex": str(other)}), [str(other)])
            run.assert_not_called()

    def test_linux_install_check_and_final_json_use_service_activation(self):
        result, screen = self.linux_install_flow()
        self.assertEqual(result["checks"]["도구"], "2개 (서버 1/1)")
        self.assertIs(result["model_signed_in"]["claude"], True)
        self.assertIn("claude 또는 codex", screen.result.call_args.args[1])

    def test_linux_service_passes_installed_entries_to_observer(self):
        c = self.core
        config_path = self.root / "config.json"
        config_path.write_text(json.dumps({"username": "emp", "uid": 1001, "gateway_url": "https://gw.example",
                                          "device_key": "synthetic", "endpoint_id": "new", "tailscale_node_id": "node",
                                          "socket": str(self.root / "header.sock"), "harness_paths": ["/opt/approved/claude"]}))
        write = c.private_write
        def stop_after_write(path, text):
            write(path, text)
            raise StopIteration("observer config captured")
        def bind(address, handler):
            Path(address).touch()
            return Mock()
        with patch.object(c.os, "geteuid", return_value=0, create=True), \
             patch.object(c, "protected", return_value=True), patch.object(c, "verify_transport"), \
             patch.object(c, "pwd", SimpleNamespace(getpwnam=lambda n: self.person)), \
             patch.object(c, "load_module"), patch.object(c.threading, "Thread"), \
             patch.object(c.socketserver, "ThreadingUnixStreamServer", side_effect=bind, create=True), \
             patch.object(c.os, "chown", create=True), patch.object(c, "private_write", side_effect=stop_after_write), \
             self.assertRaises(StopIteration):
            c.serve(SimpleNamespace(config=config_path))
        observer = json.loads((self.root / "observer.json").read_text())
        self.assertEqual(observer["ENDPOINT_HARNESS_PATHS"], ["/opt/approved/claude"])

    def test_expired_model_auth_overrides_existing_credentials_in_final_json(self):
        result, screen = self.linux_install_flow("Failed to authenticate: OAuth session expired and could not be refreshed")
        self.assertIs(result["model_signed_in"]["claude"], False)
        self.assertIn("로그인", result["checks"]["모델 응답"])
        self.assertIn("claude auth login", screen.result.call_args.args[1])

    def test_model_transport_failure_does_not_claim_credentials_expired(self):
        result, screen = self.linux_install_flow("Connection timeout")
        self.assertIs(result["model_signed_in"]["claude"], True)
        self.assertNotIn("모델 로그인", screen.result.call_args.args[1])

    def test_login_shell_permission_error_is_execution_failure_not_model_auth(self):
        result, screen = self.linux_install_flow(
            "runuser: failed to execute /usr/local/lib/mcpgw-enforcement/mcpgw-emp/login-shell: Permission denied")
        self.assertIs(result["model_signed_in"]["claude"], True)
        self.assertIn("실행 장애", result["checks"]["모델 응답"])
        self.assertNotIn("로그인 필요", result["checks"]["모델 응답"])
        self.assertNotIn("모델 로그인", screen.result.call_args.args[1])
        self.assertIn("실행 권한", screen.result.call_args.args[1])

    def test_login_path_is_not_a_login_request_but_login_command_is(self):
        for message, failed in (("Cannot read /opt/login/config.json", False),
                                ("Please run /login to authenticate", True), ("Please log in", True)):
            signed = {"claude": True}
            observer = SimpleNamespace(MODEL_PROMPT="OK", model_check=lambda argv: {
                "ok": False, "seconds": 1, "detail": message})
            with self.subTest(message=message), patch.object(self.core, "load_module", return_value=observer):
                _, text = self.boot.model_cell(self.core, "emp", ["claude"], False, signed)
            self.assertEqual(signed["claude"], not failed)
            self.assertEqual("로그인 필요" in text, failed)

    def test_codex_refresh_failures_override_credentials_and_request_login(self):
        messages = [
            "Your access token could not be refreshed because your refresh token has expired. Please log out and sign in again.",
            "Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.",
            "Your access token could not be refreshed because your refresh token was revoked. Please log out and sign in again.",
            "Your access token could not be refreshed. Please log out and sign in again.",
            "Your access token could not be refreshed because you have since logged out or signed in to another account. Please sign in again.",
        ]
        for message in messages:
            # Each install consumes its enrollment and writes credentials in a temporary HOME.
            with self.subTest(message=message), tempfile.TemporaryDirectory() as folder, \
                 patch.object(self, "root", Path(folder)), patch.object(self, "enrollment", Path(folder) / "enrollment.json"):
                self.enrollment.write_text(json.dumps(self.bundle))
                result, screen = self.linux_install_flow(message, harness="codex")
                self.assertIs(result["model_signed_in"]["codex"], False)
                self.assertIn("로그인 필요", result["checks"]["모델 응답"])
                self.assertIn("codex login --device-auth", screen.result.call_args.args[1])

    def test_codex_auth_failure_names_the_checked_harness(self):
        result, screen = self.linux_install_flow("401 Unauthorized", harness="codex")
        self.assertIs(result["model_signed_in"]["codex"], False)
        self.assertIn("codex login --device-auth", screen.result.call_args.args[1])

    def test_consumed_linux_kit_cannot_use_another_employee_or_partial_install(self):
        b = self.boot
        self.enrollment.unlink()
        (self.root / "other").mkdir()
        (self.root / "other/config.json").write_text('{}')
        (self.root / "emp").mkdir()
        with patch.object(b, "STATE", self.root), patch.object(b, "employee_account", return_value="emp"), \
             patch.object(b, "check_python"), patch.object(b, "os", SimpleNamespace(name="posix", geteuid=lambda: 0)), \
             patch.dict(sys.modules, {"pwd": ModuleType("pwd"), "grp": ModuleType("grp")}), \
             patch.object(b, "connect") as connect, \
             patch.object(sys, "argv", ["bootstrap.py", "--enrollment", str(self.enrollment)]), \
             patch("sys.stderr", new_callable=io.StringIO) as error:
            self.assertEqual(b.main(), 1)
        self.assertIn("콘솔에서 새 키트", error.getvalue())
        connect.assert_not_called()

    def test_macos_completion_text_matches_reported_state(self):
        m = self.mac
        for state, label in (("active", "활성"), ("pending", "활성화 대기"), ("unknown", "확인 필요")):
            with self.subTest(state=state), patch.object(sys, "argv", ["managed-macos.py", "--user", "emp", "--enrollment", str(self.enrollment)]), \
                 patch.object(sys, "platform", "darwin"), patch.object(m.os, "geteuid", return_value=0, create=True), \
                 patch.object(m, "core_module", return_value=self.core), \
                 patch.object(m, "install", return_value={"state": state}), \
                 redirect_stdout(io.StringIO()) as output:
                m.main()
            self.assertIn("연결 상태: " + label + "\n", output.getvalue())
            if state == "active":
                self.assertNotIn("활성화 대기", output.getvalue())

    def test_macos_real_install_and_completion_use_service_activation(self):
        m, c = self.mac, self.core
        programs, state, launchd = (self.root / name for name in ("programs", "state", "launchd"))
        launchd.mkdir()
        homes = self.root / "homes"
        homes.mkdir()
        files = {name: self.root / "settings" / name for name in c.FILES}
        report = programs / "status-managed-emp.json"
        config = {"device_key": "synthetic", "gateway_url": "https://gw.example", "tailscale_node_id": "node"}
        prepared = (config, self.policy, {"endpoint_id": "new", "state": "pending-organization-activation"})
        boot = SimpleNamespace(place_harnesses=Mock(return_value={"claude": {"path": str(programs / "approved/claude")}}))
        def person(name):
            if name == "emp":
                return self.person
            raise KeyError(name)
        def local_path(*parts):
            if str(parts[0]) == "/Users":
                return homes.joinpath(*parts[1:])
            return Path(*parts)
        def run(*argv, **kwargs):
            if argv[:2] == ("/bin/launchctl", "bootstrap"):
                c.private_write(report, json.dumps({"state": "active", "updated": c.time.time()}))
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        with ExitStack() as stack:
            for module in (m, c):
                stack.enter_context(patch.multiple(module, PROGRAMS=programs, STATE=state, FILES=files))
            stack.enter_context(patch.multiple(m, LAUNCHD=launchd, Path=local_path,
                                               pwd=SimpleNamespace(getpwnam=person, getpwall=lambda: [self.person])))
            stack.enter_context(patch.object(m, "core_module", return_value=c))
            stack.enter_context(patch.object(m, "configure_bootstrap", return_value=boot))
            stack.enter_context(patch.object(m, "run", side_effect=run))
            stack.enter_context(patch.object(m, "apply_pf"))
            stack.enter_context(patch.object(m, "write_wrappers"))
            stack.enter_context(patch.object(m.os, "chown", create=True))
            stack.enter_context(patch.object(m.os, "geteuid", return_value=0, create=True))
            stack.enter_context(patch.object(c, "verify_transport"))
            stack.enter_context(patch.object(c, "protected", return_value=True))
            stack.enter_context(patch.object(c, "diagnostic"))
            stack.enter_context(patch.object(c, "enroll", return_value=prepared))
            stack.enter_context(patch.object(sys, "platform", "darwin"))
            stack.enter_context(patch.object(sys, "argv", ["managed-macos.py", "--user", "emp",
                                                          "--enrollment", str(self.enrollment)]))
            with redirect_stdout(io.StringIO()) as output:
                m.main()
        result = json.loads(output.getvalue().splitlines()[0])
        self.assertEqual(result["state"], "active")
        self.assertIn("연결 상태: 활성\n", output.getvalue())
        self.assertNotIn("활성화 대기", output.getvalue())
        self.assertFalse(self.enrollment.exists())
        saved = json.loads((state / "managed-emp/config.json").read_text())
        self.assertEqual(saved["harness_paths"], [str(programs / "approved/claude")])

    def test_consumed_macos_kit_reports_existing_install_without_using_token(self):
        m = self.mac
        self.enrollment.unlink()
        folder = self.root / "managed-emp"
        folder.mkdir()
        (folder / 'config.json').write_text('{}')
        with patch.object(m, "STATE", self.root), patch.object(m, "account_name", return_value="managed-emp"), \
             patch.object(sys, "argv", ["managed-macos.py", "--enrollment", str(self.enrollment)]), \
             patch.object(sys, "platform", "darwin"), patch.object(m.os, "geteuid", return_value=0, create=True), \
             patch.object(m, "install") as install, redirect_stdout(io.StringIO()) as output:
            m.main()
        self.assertIn("이미 설치됨", output.getvalue())
        self.assertIn("콘솔에서 새 키트", output.getvalue())
        install.assert_not_called()

    def test_expired_kit_is_refused_before_anything_changes(self):
        bootstrap = load("bootstrap")
        self.assertTrue(bootstrap.expired({"expires_at": "2026-10-23T11:23:33.649135+00:00"}, now=1792999999))
        self.assertFalse(bootstrap.expired({"expires_at": "2026-10-23T11:23:33+00:00"}, now=1761200000))
        self.assertFalse(bootstrap.expired({}))
        self.assertFalse(bootstrap.expired({"expires_at": "not a date"}))
        source = (KIT / "bootstrap.py").read_text(encoding="utf-8")
        # 만료 검사는 계정·설치를 건드리는 connect보다 앞에 있어야 한다.
        self.assertLess(source.index("if expired(bundle):"), source.index("return connect(managed"))

    def test_isolated_employee_check_requires_admin_without_running_helper_as_employee(self):
        c = self.core
        summary = {"user": "managed-emp", "mode": "isolated", "state": "active"}
        with patch.object(c.os, "geteuid", return_value=1000, create=True), \
             patch.object(c, "pwd", SimpleNamespace(getpwnam=lambda n: self.person)), \
             patch.object(c.subprocess, "run", return_value=SimpleNamespace(
                 stdout='{"Authorization":"Bearer endpoint-not-active"}', returncode=0)) as run, \
             self.assertRaisesRegex(ValueError, "sudo mcpgw-status --check"):
            c.account_header(summary)
        run.assert_not_called()

    def test_header_check_keeps_root_managed_account_and_simple_mode_paths(self):
        c = self.core
        helper = str(c.ENFORCEMENT / "mcpgw-emp/header-helper")
        token = "Bearer synthetic-unit-token"
        for uid, mode in ((0, "isolated"), (1001, "isolated"), (1001, "simple")):
            with self.subTest(uid=uid, mode=mode), \
                 patch.object(c.os, "geteuid", return_value=uid, create=True), \
                 patch.object(c, "pwd", SimpleNamespace(getpwnam=lambda n: self.person)), \
                 patch.object(c.subprocess, "run", return_value=SimpleNamespace(
                     stdout=json.dumps({"Authorization": token}), returncode=0)) as run:
                self.assertEqual(c.account_header({"user": "emp", "mode": mode}), token)
                expected = (["setpriv", "--reuid", "1001", "--regid", "1001", "--clear-groups", "--", helper]
                            if uid == 0 else [helper])
                self.assertEqual(run.call_args.args[0], expected)
                self.assertEqual(run.call_args.kwargs["env"], {"PATH": "/usr/bin:/bin"})

    def test_inactive_header_and_helper_failure_remain_failures(self):
        c = self.core
        with patch.object(c.os, "geteuid", return_value=1001, create=True), \
             patch.object(c, "pwd", SimpleNamespace(getpwnam=lambda n: self.person)), \
             patch.object(c.subprocess, "run", return_value=SimpleNamespace(
                 stdout='{"Authorization":"Bearer endpoint-not-active"}', returncode=0)), \
             self.assertRaisesRegex(ValueError, "활성화 전"):
            c.account_header({"user": "emp", "mode": "isolated"})
        with patch.object(c.os, "geteuid", return_value=1001, create=True), \
             patch.object(c.subprocess, "run", side_effect=subprocess.TimeoutExpired("helper", 20)), \
             self.assertRaises(subprocess.TimeoutExpired):
            c.account_header({"user": "emp", "mode": "simple"})

    def test_model_check_uses_fixed_entry_in_isolated_mode_and_employee_path_in_simple_mode(self):
        b, c = self.boot, self.core
        account = self.root / "emp"
        account.mkdir()
        (account / "config.json").write_text('{"uid":1001}')
        observer = SimpleNamespace(MODEL_PROMPT="reply 'OK' only", model_check=Mock())
        for simple in (False, True):
            for harness in ("claude", "codex"):
                for ok in (True, False):
                    with self.subTest(simple=simple, harness=harness, ok=ok):
                        observer.model_check.return_value = {"ok": ok, "seconds": 1.2, "detail": "denied"}
                        with patch.object(b, "STATE", self.root), patch.object(c, "load_module", return_value=observer):
                            label, value = b.model_cell(c, "emp", [harness], simple)
                        self.assertEqual(label, "모델 응답")
                        self.assertIn("정상" if ok else "실패 · denied", value)
                        argv = observer.model_check.call_args.args[0]
                        entry = c.ENFORCEMENT / "mcpgw-emp"
                        expected = harness if simple else str(entry / harness)
                        arguments = "-p" if harness == "claude" else "exec --skip-git-repo-check"
                        self.assertEqual(argv[-1], f"{shlex.quote(expected)} {arguments} {shlex.quote(observer.MODEL_PROMPT)}")
                        self.assertEqual(argv[:-1], ["runuser", "-l", "emp", "-c"] if simple else
                                         ["runuser", "-u", "emp", "--", str(entry / "login-shell"), "-c"])

    def test_linux_refused_enrollment_or_policy_never_removes_old_install(self):
        b = self.boot
        for failure_at in (0, 1):
            for code in (401, 403, 409, 410, None):
                error = urllib.error.HTTPError("https://gw.example", code, "refused", {}, None) if code else OSError("network")
                replies = [error] if failure_at == 0 else [{"endpoint_id": "new"}, error, error, error]
                old = self.root / "old-config.json"
                old.write_bytes(b"existing credential and settings")
                with patch.object(self.core, "verify_transport"), patch.object(self.core, "machine_id", return_value=None), \
                     patch.object(self.core, "request", side_effect=replies), patch.object(self.core, "diagnostic"), \
                     patch.object(self.core.time, "sleep"), \
                     patch.object(b, "ensure_packages"), patch.object(b, "installed", return_value=True), \
                     patch.object(b, "rollback") as remove, patch.object(b, "find_clients") as find, \
                     patch.object(b, "remove_shims") as shims, patch.object(b, "install_managed") as install, \
                     patch.object(b, "pwd", SimpleNamespace(getpwnam=lambda n: self.person)), \
                     self.assertRaises(b.Failed):
                    b.connect(self.core, "emp", False, SimpleNamespace(enrollment=self.enrollment), 0)
                self.assertEqual(old.read_bytes(), b"existing credential and settings")
                for operation in (remove, find, shims, install):
                    operation.assert_not_called()
                self.assertTrue(self.enrollment.exists())

    def test_enrollment_retries_connection_refused_and_policy_retries_without_consuming_again(self):
        c = self.core
        refused = urllib.error.URLError(ConnectionRefusedError("synthetic-secret"))
        unavailable = urllib.error.HTTPError("https://gw.example/secret", 503, "synthetic-secret", {}, None)
        with patch.object(c, "verify_transport"), patch.object(c, "machine_id", return_value=None), \
             patch.object(c.time, "sleep") as sleep, patch.object(c, "request", side_effect=[
                 refused, {"endpoint_id": "new"}, unavailable, TimeoutError(), self.policy]) as request:
            config, policy, enrolled = c.enroll(self.bundle, "emp", 1001, "simple")
        self.assertEqual((config["endpoint_id"], enrolled["endpoint_id"]), ("new", "new"))
        self.assertIs(policy, self.policy)
        self.assertEqual([call.args[1] for call in request.call_args_list],
                         ["/oauth/device-enroll"] * 2 + ["/api/endpoint/managed-policy"] * 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 1, 2])
        first, second = request.call_args_list[:2]
        self.assertEqual(first, second)  # the same device key, not a new enrollment identity

    def test_preparation_retry_is_bounded_and_never_replays_an_ambiguous_enrollment(self):
        c = self.core
        for path, body, error, count in (
            ("/oauth/device-enroll", {}, urllib.error.URLError(ConnectionRefusedError()), 3),
            ("/oauth/device-enroll", {}, TimeoutError(), 1),
            ("/oauth/device-enroll", {}, urllib.error.URLError(ConnectionResetError()), 1),
            ("/oauth/device-enroll", {}, urllib.error.HTTPError("https://gw", 503, "busy", {}, None), 1),
            ("/api/endpoint/managed-policy", None, urllib.error.HTTPError("https://gw", 502, "busy", {}, None), 3),
            ("/api/endpoint/managed-policy", None, urllib.error.HTTPError("https://gw", 401, "denied", {}, None), 1),
            ("/api/endpoint/managed-policy", None, urllib.error.URLError(ssl.SSLCertVerificationError()), 1),
            ("/oauth/device-enroll", {}, urllib.error.URLError(socket.gaierror(socket.EAI_AGAIN, "temporary")), 3),
        ):
            with self.subTest(path=path, error=error), patch.object(c, "request", side_effect=error) as request, \
                 patch.object(c.time, "sleep") as sleep, self.assertRaises(type(error)):
                c.preparation_request(self.bundle, path, body)
            self.assertEqual(request.call_count, count)
            self.assertEqual(sleep.call_count, count - 1)

    def test_final_preparation_failure_explains_cause_without_url_or_credentials(self):
        b, c = self.boot, self.core
        error = urllib.error.HTTPError("https://gw.example/?token=synthetic-secret", 503, "synthetic-secret", {}, None)
        with patch.object(b, "ensure_packages"), patch.object(b, "pwd", SimpleNamespace(getpwnam=lambda n: self.person)), \
             patch.object(c, "enroll", side_effect=error), patch.object(c, "diagnostic") as diagnostic, \
             patch.object(b, "rollback") as rollback, self.assertRaises(b.Failed) as caught:
            b.connect(c, "emp", False, SimpleNamespace(enrollment=self.enrollment), 0)
        self.assertIn("HTTP 503", str(caught.exception))
        self.assertNotIn("synthetic-secret", str(caught.exception))
        self.assertNotIn("https://", str(caught.exception))
        diagnostic.assert_called_once()
        rollback.assert_not_called()

    def test_linux_policy_success_precedes_removal_and_install_receives_same_result(self):
        b, events = self.boot, []
        prepared = ({"device_key": "new-secret"}, self.policy, {"endpoint_id": "new"})
        core = SimpleNamespace(enroll=Mock(side_effect=lambda *a: events.append("policy") or prepared), diagnostic=Mock(),
                               private_write=self.core.private_write, PROGRAMS=self.root)
        with ExitStack() as stack:
            for name in ("ensure_packages", "remove_shims", "remove_companion"):
                stack.enter_context(patch.object(b, name))
            stack.enter_context(patch.object(b, "pwd", SimpleNamespace(getpwnam=lambda n: self.person)))
            stack.enter_context(patch.object(b, "installed", return_value=True))
            stack.enter_context(patch.object(b, "rollback", side_effect=lambda n: events.append("remove")))
            stack.enter_context(patch.object(b, "find_clients", return_value={}))
            install = stack.enter_context(patch.object(b, "install_managed", side_effect=lambda *a, **k: events.append("install") or {}))
            stack.enter_context(patch.object(b, "install_check", return_value=([], "")))
            stack.enter_context(patch.object(b, "SCREEN", Mock(summary={})))
            stack.enter_context(redirect_stdout(io.StringIO()))
            self.assertEqual(b.connect(core, "emp", False, SimpleNamespace(enrollment=self.enrollment, skip_login=True), 0), 0)
        self.assertEqual(events, ["policy", "remove", "remove", "install"])
        self.assertIs(install.call_args.kwargs["prepared"], prepared)

    def test_direct_linux_install_does_not_copy_programs_before_policy(self):
        c = self.core
        args = argparse.Namespace(user="emp", enrollment=self.enrollment, mode="simple", client=[])
        with patch.object(c.os, "geteuid", return_value=0, create=True), patch.object(c, "verify_transport"), \
             patch.object(c, "pwd", SimpleNamespace(getpwnam=lambda n: self.person)), \
             patch.object(c.os, "getgrouplist", return_value=[], create=True), \
             patch.object(c, "enroll", side_effect=OSError("offline")), patch.object(c, "rollback") as remove, \
             patch.object(c, "private_write") as write, self.assertRaises(OSError):
            c.install(args)
        write.assert_not_called()
        remove.assert_not_called()

    def test_macos_existing_install_survives_registration_failure(self):
        m = self.mac
        folder = self.root / "state/managed-emp"
        folder.mkdir(parents=True)
        (folder / "installer.json").write_text(json.dumps({"created": True, "employee": "emp", "home_created": True}))
        config = folder / "config.json"
        config.write_bytes(b"old config")
        core = SimpleNamespace(verify_transport=Mock(), enroll=Mock(side_effect=OSError("offline")), diagnostic=Mock(),
                               preparation_error=self.core.preparation_error)
        with patch.object(m, "STATE", folder.parent), patch.object(m, "core_module", return_value=core), \
             patch.object(m, "account_name", return_value="managed-emp"), \
             patch.object(m, "pwd", SimpleNamespace(getpwnam=lambda n: self.person)), \
             patch.object(m, "rollback") as remove, patch.object(m, "run") as run, self.assertRaises(ValueError):
            m.install("emp", self.enrollment)
        remove.assert_not_called()
        run.assert_not_called()
        self.assertEqual(config.read_bytes(), b"old config")

    def test_partial_linux_install_is_detected_without_config(self):
        (self.root / "emp").mkdir()
        with patch.object(self.boot, "STATE", self.root):
            self.assertTrue(self.boot.installed("emp"))

    def test_linux_partial_removal_restores_backups_and_preserves_unowned_settings(self):
        c = self.core
        folder = self.root / "state/emp"
        folder.mkdir(parents=True)
        programs = self.root / "programs"
        programs.mkdir()
        model = programs / "model-emp.json"
        model.write_text('{"claude": false}')
        settings = self.root / "managed-settings.json"
        settings.write_text("old managed settings")
        (folder / (settings.name + ".backup")).write_text("employee original")
        foreign = self.root / "requirements.toml"
        foreign.write_text("organization original")
        def local_path(*parts):
            if str(parts[0]).startswith(("/etc/", "/run/", "/usr/")):
                return self.root / "system" / Path(*parts).as_posix().lstrip("/")
            return Path(*parts)
        with patch.object(c, "STATE", folder.parent), patch.object(c, "PROGRAMS", programs), \
             patch.object(c, "ENFORCEMENT", self.root / "enforcement"), patch.object(c, "Path", local_path), \
             patch.object(c, "FILES", {settings.name: settings, foreign.name: foreign}), \
             patch.object(c, "STATUS_SHIM", self.root / "shim"), patch.object(c, "edit_environment"), \
             patch.object(c.os, "geteuid", return_value=0, create=True), \
             patch.object(c, "pwd", SimpleNamespace(getpwnam=lambda n: self.person)), \
             patch.object(c.subprocess, "run"), redirect_stdout(io.StringIO()):
            c.rollback(SimpleNamespace(user="emp"))
        self.assertEqual(settings.read_text(), "employee original")
        self.assertEqual(foreign.read_text(), "organization original")
        self.assertFalse(folder.exists())
        self.assertFalse(model.exists())

    def test_macos_removal_without_config_or_journal_clears_known_tasks_but_keeps_account(self):
        m = self.mac
        folder = self.root / "state/managed-emp"
        folder.mkdir(parents=True)
        settings = self.root / "settings.json"
        settings.write_text("managed")
        (folder / "settings.json.backup").write_text("original")
        launchd = self.root / "launchd"
        launchd.mkdir()
        plist = launchd / "org.mcpgw.managed.managed-emp.plist"
        plist.touch()
        def write(path, text):
            path.write_text(text)
        core = SimpleNamespace(private_write=write)
        def local_path(*parts):
            if str(parts[0]).startswith("/var/run/"):
                return self.root / "sockets" / Path(parts[0]).name
            return Path(*parts)
        with patch.object(m, "STATE", folder.parent), patch.object(m, "PROGRAMS", self.root / "programs"), \
             patch.object(m, "LAUNCHD", launchd), patch.object(m, "FILES", {"settings.json": settings}), \
             patch.object(m, "Path", local_path), \
             patch.object(m, "core_module", return_value=core), patch.object(m, "configure_bootstrap", return_value=Mock()), \
             patch.object(m, "run", return_value=SimpleNamespace(stdout="boot")) as run:
            m.rollback("managed-emp")
        self.assertFalse(plist.exists())
        self.assertFalse(folder.exists())
        self.assertEqual(settings.read_text(), "original")
        self.assertTrue(any("-F" in call.args for call in run.call_args_list))
        self.assertFalse(any("-delete" in call.args for call in run.call_args_list))

    def test_failed_removal_is_not_reported_as_success_or_removes_shims(self):
        b = self.boot
        with patch.object(b.subprocess, "run", return_value=SimpleNamespace(returncode=1, stderr="permission denied")), \
             patch.object(b, "remove_shims") as shims, self.assertRaises(subprocess.CalledProcessError) as caught:
            b.rollback("emp")
        self.assertEqual(caught.exception.stderr, "permission denied")
        shims.assert_not_called()

    def test_append_log_keeps_stderr_and_removes_secrets(self):
        c = self.core
        # Windows cannot prove POSIX ownership; file contents and append semantics are still exercised.
        with patch.object(c, "STATE", self.root), patch.object(c, "protected", return_value=True), \
             patch.object(c.os, "O_NOFOLLOW", getattr(c.os, "O_NOFOLLOW", 0), create=True), patch.object(c.os, "fchmod", create=True):
            error = subprocess.CalledProcessError(1, ["never-log-argv"], stderr="useful diagnostic\nenroll-secret\nnew-secret\nBearer abc\npassword=pwd\ndevice_key=abc")
            c.diagnostic("install", error, ("enroll-secret", "new-secret"))
            c.diagnostic("enroll", urllib.error.HTTPError("https://secret", 503, "secret-body", {}, None))
            c.diagnostic("retry", None)
        log = (self.root / "setup.log").read_text(encoding="utf-8")
        self.assertIn("useful diagnostic", log)
        self.assertIn("retry", log)
        self.assertIn("HTTP 503", log)
        self.assertNotIn("https://secret", log)
        self.assertNotIn("secret-body", log)
        for secret in ("enroll-secret", "new-secret", "Bearer", "password", "device_key", "never-log-argv"):
            self.assertNotIn(secret, log)

    def test_bootstrap_preserves_child_stderr_for_append_logger(self):
        b, messages = self.boot, []
        with patch.object(b, "DIAGNOSTIC", side_effect=lambda stage, error: messages.append((stage, error.stderr))):
            done = b.run(sys.executable, "-c", "import sys; print('diagnostic from child', file=sys.stderr); sys.exit(3)",
                         check=False, quiet=True, stderr=subprocess.DEVNULL)
        self.assertEqual(done.returncode, 3)
        self.assertEqual(messages[0][1].strip(), "diagnostic from child")

    def test_linux_missing_restore_metadata_keeps_original_backups(self):
        c = self.core
        folder = self.root / "state/emp/home-launchers"
        folder.mkdir(parents=True)
        backup = folder / "original"
        backup.write_bytes(b"employee launcher")
        with patch.object(c, "STATE", folder.parent.parent), patch.object(c.os, "geteuid", return_value=0, create=True), \
             patch.object(c, "pwd", SimpleNamespace(getpwnam=lambda n: self.person)), \
             patch.object(c.subprocess, "run") as run, self.assertRaises(ValueError):
            c.rollback(SimpleNamespace(user="emp"))
        run.assert_not_called()
        self.assertEqual(backup.read_bytes(), b"employee launcher")

    def test_user_codex_tables_are_never_edited_by_unix_installers(self):
        config = self.root / ".codex/config.toml"
        config.parent.mkdir()
        original = b'# >>> mcp-gateway managed >>>\r\n[mcp_servers.node_repl]\r\ncommand="employee"\r\n# <<< mcp-gateway managed <<<\r\n'
        config.write_bytes(original)
        for name in ("managed-linux.py", "managed-macos.py", "bootstrap.py", "install.py", "enforce-linux.py"):
            text = (KIT / name).read_text(encoding="utf-8")
            self.assertNotIn("mcp-gateway managed >>>", text)
            self.assertNotIn('".codex/config.toml"', text)
        self.assertEqual(config.read_bytes(), original)

    def legacy(self):
        return load("legacy_kit", KIT.parent / "full_stack_lab/field/pc/mcpgw_pc.py")

    def test_bundled_helper_clean_markers_remove_only_recorded_block_and_keep_crlf_tables(self):
        helper = self.legacy()
        settings = {"url": "https://gw.example", "servers": ["git"], "codex": True}
        block = helper.codex_block(settings)
        path = helper.codex_config()
        path.parent.mkdir()
        before = b'model="employee"\r\n'
        after = b'[mcp_servers.node_repl]\r\ncommand="employee"\r\n'
        path.write_bytes(before + block.replace("\n", "\r\n").encode() + after)
        helper.write_private(helper.home() / "codex-block.txt", block)
        helper.remove_codex_block()
        self.assertEqual(path.read_bytes(), before + after)

    def test_bundled_helper_ambiguous_markers_and_inserted_staff_tables_back_up_and_fail(self):
        helper = self.legacy()
        block = helper.codex_block({"url": "https://gw.example", "servers": ["git"]})
        helper.write_private(helper.home() / "codex-block.txt", block)
        path = helper.codex_config()
        path.parent.mkdir()
        variants = [helper.BEGIN + "\n", helper.END + "\n" + block, block + block,
                    block.replace(helper.END, '[mcp_servers.node_repl]\ncommand="employee"\n' + helper.END),
                    'value="""\n' + block + '"""\n']
        for text in variants:
            original = text.replace("\n", "\r\n").encode()
            path.write_bytes(original)
            previous = set(path.parent.glob("*.backup"))
            with self.assertRaises(SystemExit):
                helper.remove_codex_block()
            backups = set(path.parent.glob("*.backup")) - previous
            self.assertEqual(len(backups), 1)
            self.assertEqual(next(iter(backups)).read_bytes(), original)
            self.assertEqual(path.read_bytes(), original)

    def test_bundled_helper_setup_and_policy_update_keep_employee_tables(self):
        helper = self.legacy()
        path = helper.codex_config()
        path.parent.mkdir()
        staff = '[mcp_servers.node_repl]\ncommand="employee"\n'
        path.write_text(staff)
        settings = {"url": "https://gw.example", "servers": ["git"], "codex": True}
        helper.setup_codex(settings, False)
        helper.apply_codex(settings, ["asdk_app_1"], ["browser_use"])
        helper.remove_codex_block()
        self.assertTrue(path.read_text().startswith(staff))

    def test_bundled_helper_marker_strings_are_not_marker_lines_and_legacy_clean_block_is_recognized(self):
        helper = self.legacy()
        quoted = 'value = "' + helper.BEGIN + '"\n'
        self.assertEqual(helper.without_block(quoted), quoted)
        settings = {"url": "https://gw.example", "servers": ["git"]}
        helper.write_private(helper.home() / "config.json", json.dumps(settings))
        self.assertEqual(helper.without_block(helper.codex_block(settings)), "")

    def test_observer_failure_keeps_installed_program_and_config_and_appends_safe_diagnostics(self):
        installer = load("install")
        target = self.root / "observer"
        target.mkdir()
        config, agent = target / "config.json", target / "agent.py"
        config.write_bytes(b"original config")
        agent.write_bytes(b"original program")
        key = self.root / "key"
        key.write_text("synthetic-device-key-long-enough")
        key.chmod(0o600)
        argv = ["install.py", "--gateway-url", "https://gw.example", "--endpoint-id", "endpoint-unit",
                "--scan-path", str(self.root), "--key-file", str(key), "--windows-wrapper"]
        def failed(command, **kwargs):
            candidate = Path(command[command.index("--config") + 1])
            self.assertEqual(json.loads(candidate.read_text())["ENDPOINT_DEVICE_KEY"], key.read_text())
            self.assertEqual(config.read_bytes(), b"original config")
            self.assertEqual(agent.read_bytes(), b"original program")
            return SimpleNamespace(returncode=7, stdout="safe stdout\n", stderr="safe stderr\n" + key.read_text() + "\nBearer secret\npassword=hidden")
        with patch.object(sys, "argv", argv), patch.object(installer, "install_dir", return_value=target), \
             patch.object(installer, "config_dir", return_value=target), patch.object(installer.subprocess, "run", side_effect=failed):
            self.assertEqual(installer.main(), 7)
            self.assertEqual(installer.main(), 7)
        self.assertEqual(config.read_bytes(), b"original config")
        self.assertEqual(agent.read_bytes(), b"original program")
        text = (target / "install.log").read_text(encoding="utf-8")
        self.assertEqual(text.count("safe stderr"), 2)
        for value in (key.read_text(), "Bearer", "password"):
            self.assertNotIn(value, text)


if __name__ == "__main__":
    unittest.main()
