"""Offline D-119 checks. No kernel rules, credentials, network or MCP server are used."""
import importlib.util
import io
import json
import os
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock

REPO = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, REPO / "endpoint-agent" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    # Windows lacks these imports; no account lookup is used without an explicit test double.
    missing = {key: ModuleType(key) for key in ("pwd", "grp")} if os.name == "nt" else {}
    with mock.patch.dict(sys.modules, missing):
        spec.loader.exec_module(module)
    return module


def with_managed_stubs(**stubs):
    """managed-linux.py를 실제로 불러온 뒤 네트워크·루트 단계만 대역으로 바꾸는 spec 로더."""
    real_spec = importlib.util.spec_from_file_location

    def spec(name, path):
        found = real_spec(name, path)
        original = found.loader.exec_module

        def exec_module(module):
            original(module)
            for key, value in stubs.items():
                setattr(module, key, value)
        found.loader.exec_module = exec_module
        return found
    return spec


class OwnerReplies(unittest.TestCase):
    def setUp(self):
        self.enforcer = load("enforce-linux")

    def rules(self, owner=1000):
        return self.enforcer.nft_rules(1001, ["192.0.2.10", "2001:db8::10"], 443, 3128, owner)

    def test_only_owner_original_new_marks_and_managed_reply_accepts(self):
        lines = self.rules().splitlines()
        mark = 'oifname "lo" ct direction original ct state new meta skuid 1000 ct mark set ct mark or 0x00000100'
        reply = 'meta skuid 1001 oifname "lo" ct direction reply ct mark and 0x00000100 == 0x00000100 accept'
        self.assertIn(mark, lines)
        self.assertIn(reply, lines)
        self.assertLess(lines.index(mark), lines.index(reply))
        log = next(i for i, line in enumerate(lines) if 'log prefix "MCPGW_DENY' in line)
        self.assertLess(lines.index(reply), log)
        self.assertEqual([line for line in lines if line.endswith(" accept")], [
            reply,
            'meta skuid 1001 ip daddr 192.0.2.10 tcp dport { 443, 3128 } accept',
            'meta skuid 1001 ip6 daddr 2001:db8::10 tcp dport { 443, 3128 } accept'])
        self.assertIn("meta skuid 1001 counter reject with icmpx type admin-prohibited", lines)
        self.assertNotIn("1455", self.rules())
        self.assertNotIn("1457", self.rules())

    def test_mark_is_one_bit_and_preserves_tailscale_and_other_bits(self):
        mark = int(re.search(r"ct mark set ct mark or (0x[0-9a-f]+)", self.rules())[1], 16)
        self.assertEqual(mark, 0x100)
        self.assertEqual(mark & (mark - 1), 0)
        self.assertEqual(mark & 0xff0000, 0)
        for before in (0, 0x40000, 0xff0000, 0xffffffff, 0x80000001):
            self.assertEqual((before | mark) & ~mark, before & ~mark)
            self.assertEqual((before | mark) & 0xff0000, before & 0xff0000)
        self.assertEqual(self.rules().count("ct mark set"), 1)

    def test_no_owner_keeps_complete_loopback_denial(self):
        rules = self.rules(None)
        self.assertNotIn("ct mark", rules)
        self.assertNotIn('oifname "lo"', rules)
        self.assertIn("meta skuid 1001 counter reject", rules)

    def test_invalid_or_managed_owner_is_rejected(self):
        for owner in (0, -1, 999, 1001, 2**32 - 1, 2**32, True, "1000"):
            with self.subTest(owner=owner), self.assertRaises(ValueError):
                self.rules(owner)


class Installer(unittest.TestCase):
    def setUp(self):
        self.bootstrap = load("bootstrap")

    def test_owner_uid_is_forwarded_without_ambient_sudo_identity(self):
        received = []

        def install(arguments, prepared=None):
            received.append(arguments)
            print('{"endpoint_id":"unit"}')
        with mock.patch.object(self.bootstrap, "close_sessions"), \
             mock.patch.object(self.bootstrap.importlib.util, "spec_from_file_location", with_managed_stubs(install=install)), \
             mock.patch.dict(os.environ, {"SUDO_UID": "1002"}):
            self.bootstrap.install_managed("managed", {}, Path("enrollment.json"), 1000)
            self.bootstrap.install_managed("managed", {}, Path("enrollment.json"))
        self.assertEqual([a.owner_uid for a in received], [1000, None])

    def test_bootstrap_selects_employee_uid_only_for_a_separate_managed_account(self):
        b = self.bootstrap
        with tempfile.TemporaryDirectory() as folder, \
             mock.patch.object(b.importlib.util, "spec_from_file_location", with_managed_stubs(  # 등록·정책 수신은 설치 전에 한 번 일어난다(prepared). 이 시험은 계정 선택만 본다.
                 enroll=lambda bundle, *args, **kwargs: ({"device_key": "unit-device"}, {}, {}),
                 diagnostic=lambda *args, **kwargs: None)):
            enrollment = Path(folder) / "enrollment.json"
            enrollment.write_text('{"gateway_url":"https://gateway.example","enrollment_token":"unit-grant"}', encoding="utf-8")
            for companion in (True, False):
                with self.subTest(companion=companion), \
                     mock.patch.object(sys, "argv", ["bootstrap.py", "--isolated", "--skip-login", "--enrollment", str(enrollment)]), \
                     mock.patch.object(b, "install_check", return_value=([], "")), \
                     mock.patch.object(b, "os", SimpleNamespace(name="posix", geteuid=lambda: 0)), \
                     mock.patch.object(b, "employee_account", return_value="owner"), \
                     mock.patch.object(b, "managed_account", return_value=("managed", companion)), \
                     mock.patch.dict(sys.modules, {"pwd": b.pwd, "grp": b.grp}), \
                     mock.patch.object(b.pwd, "getpwnam", side_effect=lambda name:
                                       SimpleNamespace(pw_uid={"owner": 1000, "managed": 1001}[name]),
                                       create=True) as getpwnam, \
                     mock.patch.object(b, "check_python"), mock.patch.object(b, "ensure_packages"), mock.patch.object(b, "place_harnesses", return_value={}), \
                     mock.patch.object(b, "installed", return_value=False), mock.patch.object(b, "write_shims", return_value=[]), \
                     mock.patch.object(b, "install_managed", return_value={}) as install, redirect_stdout(io.StringIO()):
                    self.assertEqual(b.main(), 0)
                    install.assert_called_once()
                    # (account, harnesses, enrollment, owner UID, mode): the owner only for a separate managed account.
                    self.assertEqual(install.call_args.args[3:], (1000 if companion else None, "isolated"))
                    # 관리 계정은 등록 때 UID를 조회하고, 평소 계정은 별도 관리 계정일 때만 조회한다.
                    self.assertEqual([c.args[0] for c in getpwnam.call_args_list], ["managed", "owner"] if companion else ["managed"])

    def test_device_code_command_on_success_failure_and_interrupt(self):
        with tempfile.TemporaryDirectory() as folder:
            person = SimpleNamespace(pw_dir=folder)
            for outcome in (SimpleNamespace(returncode=0), SimpleNamespace(returncode=1), KeyboardInterrupt()):
                with self.subTest(outcome=type(outcome).__name__), \
                     mock.patch.object(self.bootstrap.pwd, "getpwnam", return_value=person, create=True), \
                     mock.patch.object(self.bootstrap.sys.stdin, "isatty", return_value=True), \
                     mock.patch.object(self.bootstrap.subprocess, "run") as run, redirect_stdout(io.StringIO()):
                    if isinstance(outcome, BaseException):
                        run.side_effect = outcome
                    else:
                        run.return_value = outcome
                    signed = self.bootstrap.harness_login("managed", ["codex"])
                    self.assertEqual(run.call_count, 1)
                    self.assertEqual(run.call_args.args[0][-1], "codex login --device-auth")
                    self.assertEqual(signed["codex"], getattr(outcome, "returncode", 1) == 0)

    def test_noninteractive_install_does_not_wait_for_device_code(self):
        with tempfile.TemporaryDirectory() as folder, \
             mock.patch.object(self.bootstrap.pwd, "getpwnam", return_value=SimpleNamespace(pw_dir=folder), create=True), \
             mock.patch.object(self.bootstrap.sys.stdin, "isatty", return_value=False), \
             mock.patch.object(self.bootstrap.subprocess, "run") as run:
            self.assertEqual(self.bootstrap.harness_login("managed", ["codex"]), {"codex": False})
        run.assert_not_called()

    def test_invalid_owner_fails_before_enrollment(self):
        managed = load("managed-linux")
        enforcer = load("enforce-linux")
        modules = {"enforcer": enforcer, "transport_observer": load("agent")}
        bundle = {"gateway_url": "https://gateway.example", "enrollment_token": "unit-enrollment"}
        person = SimpleNamespace(pw_uid=1001, pw_gid=1001, pw_dir="/home/managed", pw_name="managed")
        for owner in (0, 1001, 2**32, 1002):
            with self.subTest(owner=owner), \
                 mock.patch.object(managed.os, "geteuid", return_value=0, create=True), \
                 mock.patch.object(managed.os, "getgrouplist", return_value=[], create=True), \
                 mock.patch.object(managed.pwd, "getpwnam", return_value=person, create=True), \
                 mock.patch.object(managed.pwd, "getpwuid", side_effect=KeyError(owner), create=True) as getpwuid, \
                 mock.patch.object(managed.subprocess, "run", return_value=SimpleNamespace(returncode=1)), \
                 mock.patch.object(managed.shutil, "which", return_value="/installed"), \
                 mock.patch.object(Path, "read_text", return_value="Y"), \
                 mock.patch.object(managed, "load_module", side_effect=lambda name, path: modules[name]), \
                 mock.patch.object(managed, "verify_transport", wraps=managed.verify_transport) as verify_transport, \
                 mock.patch.object(enforcer, "nft_rules", wraps=enforcer.nft_rules) as nft_rules, \
                 mock.patch.object(enforcer, "trusted_binary", side_effect=AssertionError("owner check was bypassed")), \
                 mock.patch.object(managed, "request", side_effect=AssertionError("enrollment was reached")) as request, \
                 self.assertRaises(KeyError if owner == 1002 else ValueError):
                try:
                    managed.install(SimpleNamespace(
                        user="managed", owner_uid=owner, client=[],
                        enrollment=SimpleNamespace(read_text=lambda: json.dumps(bundle))))
                finally:
                    request.assert_not_called()
                    verify_transport.assert_called_once_with(bundle)
                    nft_rules.assert_called_once_with(1001, [], 443, owner_uid=owner)
                    if owner == 1002:
                        getpwuid.assert_called_once_with(owner)
                    else:
                        getpwuid.assert_not_called()


class Observer(unittest.TestCase):
    def test_only_logged_denials_are_classified(self):
        observer = load("os-observer")
        observer._AGENT = SimpleNamespace(seal_os_event=lambda found, *args: found)
        record = {"_BOOT_ID": "unit", "__CURSOR": "one", "__REALTIME_TIMESTAMP": "1700000000000000"}
        packet = "OUT=lo SRC=127.0.0.1 DST=127.0.0.1 PROTO=TCP SPT=1455 DPT=40000 ACK SYN"
        self.assertIsNone(observer.event({**record, "MESSAGE": packet}, 1001, "mcpgw-managed"))
        denied = {**record, "MESSAGE": "MCPGW_DENY uid=1001 " + packet}
        found = observer.event(denied, 1001, "mcpgw-managed")
        self.assertEqual(found["denial_class"], "listener_reply")
        self.assertEqual(found["details"]["source_port"], "1455")
        self.assertEqual(found["details"]["tcp_flags"], "ACK SYN")
        denied["MESSAGE"] = denied["MESSAGE"].replace("ACK SYN", "SYN")
        self.assertEqual(observer.event(denied, 1001, "mcpgw-managed")["denial_class"], "blocked_attempt")
        self.assertIsNone(observer.event(denied, 1002, "mcpgw-managed"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
