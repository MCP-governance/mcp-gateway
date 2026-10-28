"""Offline reinstall regressions. All paths/HOME are temporary; OS and enrollment are doubles."""
import argparse
import importlib.util
import io
import json
import os
import shlex
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
                replies = [error] if failure_at == 0 else [{"endpoint_id": "new"}, error]
                old = self.root / "old-config.json"
                old.write_bytes(b"existing credential and settings")
                with patch.object(self.core, "verify_transport"), patch.object(self.core, "machine_id", return_value=None), \
                     patch.object(self.core, "request", side_effect=replies), patch.object(self.core, "diagnostic"), \
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

    def test_linux_policy_success_precedes_removal_and_install_receives_same_result(self):
        b, events = self.boot, []
        prepared = ({"device_key": "new-secret"}, self.policy, {"endpoint_id": "new"})
        core = SimpleNamespace(enroll=Mock(side_effect=lambda *a: events.append("policy") or prepared), diagnostic=Mock())
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
        core = SimpleNamespace(verify_transport=Mock(), enroll=Mock(side_effect=OSError("offline")), diagnostic=Mock())
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
            c.diagnostic("retry", None)
        log = (self.root / "setup.log").read_text(encoding="utf-8")
        self.assertIn("useful diagnostic", log)
        self.assertIn("retry", log)
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
