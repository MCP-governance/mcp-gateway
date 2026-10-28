"""D-225~D-228 오프라인 검사: 설치 한 번에 패키지·컨테이너 엔진을 갖추고, 승인된 로컬 MCP의 폴더·이미지를 첫 호출 전에 준비한다.

패키지 관리자·엔진·systemd·DB는 대역이며 실기기 증거가 아니다. 저장소 루트: python -B -X utf8 full_stack_lab/tests/kit_install_upfront_check.py
"""
import importlib.util
import io
import os
import shutil
import sys
import tempfile
import time
import unittest
from contextlib import asynccontextmanager, redirect_stdout
from datetime import datetime, timedelta, timezone
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from dev73_rework_check import APP, G, load_functions, manifest, runner
from kit_continuity_check import KIT, extract
from open_endpoints import route_auth

POSIX = os.name == "posix"


def load_bootstrap():
    spec = importlib.util.spec_from_file_location("bootstrap_under_test", KIT / "bootstrap.py")
    module = importlib.util.module_from_spec(spec)
    # Windows lacks these imports; no account lookup is used without an explicit test double.
    stubs = {key: ModuleType(key) for key in ("pwd", "grp")} if os.name == "nt" else {}
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module


# ── 1. 설치 한 번에 패키지와 엔진 ────────────────────────────────────────────────

class FakeHost:
    """없는 도구를 가진 PC. 설치 명령이 오면 그 패키지의 도구가 생긴다."""
    TOOL_OF = {"gcc": "gcc", "nftables": "nft", "apparmor-utils": "apparmor_parser", "apparmor": "apparmor_parser",
               "curl": "curl", "openssl": "openssl"}

    def __init__(self, bootstrap, *, absent=("gcc", "curl", "openssl"), manager="apt-get", engine=False, fail=()):
        self.bootstrap, self.commands, self.fail = bootstrap, [], set(fail)
        self.tools = ({"gcc", "nft", "apparmor_parser", "curl", "openssl", "systemctl"} - set(absent)) | {manager}
        self.engine = engine
        self.files = {"/usr/bin/docker": False, "/usr/bin/podman": engine == "podman"}

    def which(self, name):
        return "/usr/bin/" + name if name in self.tools else None

    def run(self, *command, check=True, quiet=False, **kwargs):
        self.commands.append(list(command))
        installing = command[0] in ("apt-get", "dnf", "pacman") and "install" in command or command[:2] == ("pacman", "-S")
        if command[:2] == ("apt-get", "update") and "update" in self.fail:
            return SimpleNamespace(returncode=100)
        if installing:
            names = [n for n in command if n in self.TOOL_OF or n in ("docker.io", "podman", "docker")]
            if self.fail & set(names):
                return SimpleNamespace(returncode=100)
            for name in names:
                if name in self.TOOL_OF:
                    self.tools.add(self.TOOL_OF[name])
                else:
                    self.files["/usr/bin/" + ("docker" if name != "podman" else "podman")] = True
        return SimpleNamespace(returncode=0)

    def is_file(self, path):
        return self.files.get(str(path).replace("\\", "/"), False)

    def ensure(self):
        b = self.bootstrap
        with patch.object(b.shutil, "which", self.which), patch.object(b, "run", self.run), \
                patch.object(b.Path, "is_file", lambda path: self.is_file(path)), redirect_stdout(io.StringIO()) as printed:
            b.ensure_packages()
        return printed.getvalue()


class Packages(unittest.TestCase):
    def setUp(self):
        self.bootstrap = load_bootstrap()

    def test_missing_tools_and_the_engine_come_in_one_refresh_and_two_installs(self):
        host = FakeHost(self.bootstrap)
        host.ensure()
        refreshes = [c for c in host.commands if c[:2] == ["apt-get", "update"]]
        installs = [c for c in host.commands if c[:2] == ["apt-get", "install"]]
        self.assertEqual(len(refreshes), 1)
        self.assertEqual([c[-3:] for c in installs[:1]], [["gcc", "curl", "openssl"]])
        self.assertEqual(installs[1][-1], "docker.io")
        self.assertEqual(host.commands[-1], ["systemctl", "enable", "--now", "docker"])

    def test_openssl_and_curl_are_required_tools(self):
        self.assertTrue({"gcc", "nft", "apparmor_parser", "curl", "openssl"} <= set(self.bootstrap.REQUIRED))
        host = FakeHost(self.bootstrap, absent=("openssl",), engine="podman")
        host.ensure()
        self.assertIn("openssl", host.commands[1])

    def test_a_complete_pc_runs_no_package_manager(self):
        host = FakeHost(self.bootstrap, absent=(), engine="podman")
        self.assertEqual(host.ensure(), "")
        self.assertEqual(host.commands, [])

    def test_an_installed_but_stopped_docker_is_enabled_without_installing_anything(self):
        host = FakeHost(self.bootstrap, absent=())
        host.files["/usr/bin/docker"] = True
        host.ensure()
        self.assertEqual(host.commands, [["systemctl", "enable", "--now", "docker"]])

    def test_engine_failure_never_stops_the_install(self):
        host = FakeHost(self.bootstrap, absent=(), fail={"docker.io"})
        said = host.ensure()
        self.assertIn("로컬 MCP는 엔진 설치 뒤 사용할 수 있습니다", said)
        self.assertIn("sudo apt-get install docker.io", said)
        self.assertNotIn(["systemctl", "enable", "--now", "docker"], host.commands)

    def test_refresh_failure_without_required_tools_is_only_a_notice(self):
        host = FakeHost(self.bootstrap, absent=(), fail={"update"})
        self.assertIn("엔진 설치 뒤", host.ensure())
        self.assertFalse([c for c in host.commands if c[:2] == ["apt-get", "install"]])

    def test_a_required_tool_that_cannot_be_installed_stops_before_any_engine_attempt(self):
        host = FakeHost(self.bootstrap, fail={"curl"})
        with self.assertRaises(self.bootstrap.Failed), patch.object(self.bootstrap.shutil, "which", host.which), \
                patch.object(self.bootstrap, "run", host.run):
            self.bootstrap.ensure_packages()
        self.assertFalse([c for c in host.commands if c[-1] == "docker.io"])
        refresh_failed = FakeHost(self.bootstrap, fail={"update"})
        with self.assertRaises(self.bootstrap.Failed), patch.object(self.bootstrap.shutil, "which", refresh_failed.which), \
                patch.object(self.bootstrap, "run", refresh_failed.run):
            self.bootstrap.ensure_packages()

    def test_other_package_managers_use_their_own_names_and_engine(self):
        pacman = FakeHost(self.bootstrap, absent=("apparmor_parser",), manager="pacman", engine="podman")
        pacman.ensure()
        self.assertEqual(pacman.commands[0][-1], "apparmor")
        dnf = FakeHost(self.bootstrap, absent=(), manager="dnf")
        dnf.ensure()
        self.assertEqual(dnf.commands[0][-1], "podman")
        self.assertNotIn(["systemctl", "enable", "--now", "docker"], dnf.commands)  # podman has no daemon

    def test_python_versions_are_checked_for_the_installer_and_for_the_service(self):
        b = self.bootstrap
        with patch.object(b.sys, "version_info", (3, 7, 3)), self.assertRaises(b.Failed):
            b.check_python()
        with patch.object(b.Path, "is_file", lambda path: True), patch.object(b, "out", lambda *c: "3.6"), \
                self.assertRaises(b.Failed):
            b.check_python()
        with patch.object(b.Path, "is_file", lambda path: True), patch.object(b, "out", lambda *c: "3.12"):
            b.check_python()
        with patch.object(b.Path, "is_file", lambda path: False), self.assertRaises(b.Failed):
            b.check_python()

    def test_step_times_are_collected_without_the_login_wait(self):
        # The installer's screen (D-239) times each step; off a terminal it prints one line per step as before.
        spec = importlib.util.spec_from_file_location("kit_screen_test", KIT / "kit_screen.py")
        linux = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(linux)
        clock = iter([0, 5, 5, 7])
        with patch.object(time, "monotonic", lambda: next(clock)), redirect_stdout(io.StringIO()) as out:
            screen = linux.Screen("내 PC 연결")
            screen.step("필수 구성요소 설치")
            screen.step("관리형 연결 설치: u")
            screen.close_step()
            screen.result([("모델 응답", "claude 정상 · 3.1초")], "새 터미널에서 claude를 실행하세요")
        self.assertIsNone(screen.window)
        self.assertEqual([(row[0], row[2], row[3]) for row in screen.rows],
                         [("필수 구성요소 설치", 5, "✓"), ("관리형 연결 설치: u", 2, "✓")])
        self.assertEqual(out.getvalue().splitlines(), ["[필수 구성요소 설치]", "[관리형 연결 설치: u]",
                                                       "모델 응답: claude 정상 · 3.1초", "다음 할 일: 새 터미널에서 claude를 실행하세요"])

    def test_the_install_end_message_points_at_the_status_command(self):
        source = (KIT / "bootstrap.py").read_text(encoding="utf-8")
        self.assertIn("mint", source[source.index("로컬 MCP 준비(폴더 만들기"):][:200])


# ── 2. 첫 호출 전에 폴더와 이미지를 준비 ─────────────────────────────────────────

def entry(**change):
    body = {**manifest(), "mounts": [{"path": "mcp-docs", "mode": "ro"}]}
    return {"server_id": body["server_id"], "manifest": body, "signature": "signature",
            "manifest_sha256": runner_digest(body), **change}


def runner_digest(body):
    import hashlib
    return hashlib.sha256(runner.canonical(body)).hexdigest()


class PrepareLoop(unittest.TestCase):
    def setUp(self):
        runner.preparation.update(ready=None, total=None, note="", documents=[])
        self.logged, self.memory = [], (set(), {}, {})
        self.account = SimpleNamespace(pw_dir="/home/managed", pw_uid=2001, pw_gid=2001)
        self.config = {"uid": 2001, "username": "managed", "local_engine": {"engine": "docker"}}
        self.listing = {"servers": [entry()]}
        self.patches = [patch.object(runner, "signed", return_value=True),
                        patch.object(runner, "ensure_mounts", return_value=["/home/emp/mcp-docs"]),
                        patch.object(runner, "engine_configuration", return_value=(["docker"], "host"))]
        self.signed, self.mounts, self.engine = [p.start() for p in self.patches]
        for p in self.patches:
            self.addCleanup(p.stop)

    def once(self, request=None):
        return runner.prepare_once(self.config, request or (lambda config, path: self.listing), self.logged.append,
                                   self.account, *self.memory)

    def test_an_approved_server_gets_its_folders_and_a_long_image_budget_before_any_call(self):
        self.assertEqual(self.once(), runner.PREPARE_EVERY)
        self.mounts.assert_called_once()
        self.assertEqual(self.engine.call_args.kwargs, {"seconds": runner.PREFETCH_SECONDS})
        self.assertGreater(runner.PREFETCH_SECONDS, runner.PREPARE_SECONDS)
        self.assertEqual(runner.preparation, {"ready": 1, "total": 1, "note": "", "documents": ["/home/emp/mcp-docs"]})
        self.assertEqual(self.logged, [{"local_runner": "prepared", "server": "local-files"}])

    def test_a_prepared_server_is_not_opened_again_and_a_withdrawn_one_is_forgotten(self):
        self.once()
        self.once()
        self.assertEqual((self.mounts.call_count, self.engine.call_count), (1, 1))
        self.listing = {"servers": []}
        self.once()
        self.assertEqual(runner.preparation["total"], 0)
        self.assertEqual((self.memory[0], self.memory[1]), (set(), {}))
        self.assertEqual(runner.preparation["documents"], [])

    def test_a_manifest_the_pinned_key_does_not_vouch_for_creates_nothing(self):
        self.signed.return_value = False
        self.once()
        self.mounts.assert_not_called()
        self.engine.assert_not_called()
        self.assertEqual((runner.preparation["ready"], runner.preparation["note"]), (0, "승인 매니페스트 서명이 아닙니다"))
        tampered = entry(manifest_sha256="0" * 64)
        self.signed.return_value = True
        self.listing = {"servers": [tampered]}
        self.once()
        self.mounts.assert_not_called()
        self.assertEqual(runner.preparation["note"], "승인 매니페스트가 아닙니다")

    def test_an_expired_approval_is_not_prepared(self):
        old = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        body = manifest()
        body["approval"]["expires_at"] = old
        self.listing = {"servers": [entry(manifest=body, manifest_sha256=runner_digest(body))]}
        self.once()
        self.engine.assert_not_called()
        self.assertEqual(runner.preparation["note"], "승인 기한이 지났습니다")

    def test_an_engine_failure_is_shown_once_and_retried_later_without_blocking_other_servers(self):
        other = manifest()
        other["server_id"] = "memory"
        other_entry = entry(manifest=other, server_id="memory", manifest_sha256=runner_digest(other))
        self.listing = {"servers": [entry(), other_entry]}
        self.engine.side_effect = [ValueError("컨테이너 엔진이 없습니다"), (["docker"], "host")]
        self.once()
        self.assertEqual(runner.preparation["ready"], 1)
        self.assertEqual((runner.preparation["total"], runner.preparation["note"]), (2, "컨테이너 엔진이 없습니다"))
        self.assertEqual([i for i in self.logged if i["local_runner"] == "prepare_failed"],
                         [{"local_runner": "prepare_failed", "server": "local-files", "reason": "컨테이너 엔진이 없습니다"}])
        self.engine.side_effect = None
        self.once()
        self.assertEqual(self.engine.call_count, 2)  # 재시도 간격 안에서는 다시 받지 않는다
        with patch.object(runner.time, "monotonic", return_value=time.monotonic() + runner.PREPARE_RETRY + 1):
            self.once()
        self.assertEqual((runner.preparation["ready"], runner.preparation["note"]), (2, ""))
        self.assertEqual(len([i for i in self.logged if i["local_runner"] == "prepare_failed"]), 1)

    def test_pending_devices_wait_and_older_gateways_are_not_an_error(self):
        for status, wait in ((409, runner.PREPARE_WAITING), (401, runner.PREPARE_WAITING), (404, runner.PREPARE_EVERY)):
            error = Mock(code=status)

            def refuse(config, path, error=error):
                raise type("Refused", (Exception,), {"code": error.code})("refused")
            self.assertEqual(self.once(refuse), wait)
        self.assertEqual(self.logged, [])
        self.assertEqual((runner.preparation["ready"], runner.preparation["total"]), (None, None))

        def broken(config, path):
            raise OSError("down")
        self.once(broken)
        self.assertEqual(self.logged, [{"local_runner": "prepare_error", "error": "OSError"}])

    def test_the_gateway_route_is_the_device_route_and_the_service_runs_both_loops(self):
        routes = route_auth(__import__("ast").parse((APP / "main.py").read_text(encoding="utf-8")))
        self.assertEqual(routes[("get", "/api/endpoint/local-manifests")], "device")
        source = (KIT / "managed-linux.py").read_text(encoding="utf-8")
        self.assertIn("(local.run, local.prepare)", source)

    def test_job_and_preparation_verify_manifests_with_one_function(self):
        body = manifest()
        runner.verify_manifest({}, body, "s", runner_digest(body), body["server_id"])
        for digest, server, ok in (("0" * 64, body["server_id"], False), (runner_digest(body), "other", False)):
            with self.subTest(digest=digest[:4], server=server), self.assertRaises(ValueError):
                runner.verify_manifest({}, body, "s", digest, server)
        self.signed.return_value = False
        with self.assertRaises(ValueError):
            runner.verify_manifest({}, body, "s", runner_digest(body), body["server_id"])


@unittest.skipUnless(POSIX, "POSIX 경로 규칙")
class Folders(unittest.TestCase):
    def test_read_only_folders_come_from_the_employee_home_and_writable_ones_stay_in_the_managed_home(self):
        managed, employee = tempfile.mkdtemp(), tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, managed)
        self.addCleanup(shutil.rmtree, employee)
        body = {**manifest(), "mounts": [{"path": "mcp-docs", "mode": "ro"}, {"path": "mcp-memory", "mode": "rw"}]}
        account = SimpleNamespace(pw_dir=managed, pw_uid=os.getuid(), pw_gid=os.getgid())
        documents = (employee, os.getuid(), os.getgid())
        self.assertEqual(runner.ensure_mounts(body, account, documents), [os.path.join(employee, "mcp-docs")])
        self.assertEqual(os.stat(os.path.join(employee, "mcp-docs")).st_mode & 0o777, 0o755)
        self.assertEqual(os.stat(os.path.join(managed, "mcp-memory")).st_mode & 0o777, 0o700)
        self.assertFalse(os.path.exists(os.path.join(managed, "mcp-docs")))
        # 같은 계정이면 읽기 전용 폴더도 그 홈에 있다. 두 번째 호출은 같은 결과(멱등).
        self.assertEqual(runner.ensure_mounts(body, account, None), [os.path.join(managed, "mcp-docs")])
        self.assertEqual(runner.ensure_mounts(body, account, documents), [os.path.join(employee, "mcp-docs")])

    def test_a_link_where_the_folder_should_be_is_refused_not_followed(self):
        managed = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, managed)
        os.symlink("/etc", os.path.join(managed, "mcp-docs"))
        account = SimpleNamespace(pw_dir=managed, pw_uid=os.getuid(), pw_gid=os.getgid())
        with self.assertRaises(ValueError):
            runner.ensure_mounts({**manifest(), "mounts": [{"path": "mcp-docs", "mode": "ro"}]}, account, None)


@unittest.skipUnless(POSIX and shutil.which("openssl"), "openssl과 POSIX 경로 필요")
class SignedEndToEnd(unittest.TestCase):
    """승인 키로 실제 서명한 매니페스트를 장치가 openssl로 확인하고, 폴더를 만든 뒤 엔진에 이미지를 맡긴다."""

    def test_signed_manifest_creates_the_document_folder_and_a_forged_one_does_not(self):
        import base64
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        key = Ed25519PrivateKey.generate()
        pem = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        managed, employee = tempfile.mkdtemp(), tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, managed)
        self.addCleanup(shutil.rmtree, employee)
        body = {**manifest(), "mounts": [{"path": "mcp-docs", "mode": "ro"}]}
        good = entry(manifest=body, manifest_sha256=runner_digest(body),
                     signature=base64.b64encode(key.sign(runner.canonical(body))).decode())
        forged = entry(manifest=body, manifest_sha256=runner_digest(body),
                       signature=base64.b64encode(Ed25519PrivateKey.generate().sign(runner.canonical(body))).decode())
        config = {"uid": os.getuid(), "username": "managed", "manifest_pubkey": pem, "owner_uid": os.getuid()}
        account = SimpleNamespace(pw_dir=managed, pw_uid=os.getuid(), pw_gid=os.getgid())
        runner.preparation.update(ready=None, total=None, note="", documents=[])
        with patch.object(runner, "engine_configuration", return_value=(["docker"], "host")) as engine,                 patch("pwd.getpwuid", return_value=SimpleNamespace(pw_dir=employee, pw_uid=os.getuid(), pw_gid=os.getgid())):
            runner.prepare_once(config, lambda c, path: {"servers": [forged]}, lambda item: None, account, set(), {}, {})
            self.assertFalse(os.path.exists(os.path.join(employee, "mcp-docs")))
            engine.assert_not_called()
            runner.prepare_once(config, lambda c, path: {"servers": [good]}, lambda item: None, account, set(), {}, {})
        self.assertEqual(os.stat(os.path.join(employee, "mcp-docs")).st_mode & 0o777, 0o755)
        engine.assert_called_once()
        self.assertEqual(runner.preparation["documents"], [os.path.join(employee, "mcp-docs")])
        self.assertEqual((runner.preparation["ready"], runner.preparation["total"]), (1, 1))


class SharedEngineHelpers(unittest.TestCase):
    CONFIG = {"local_engine": {"engine": "docker", "namespace": "host", "version": "29.8.1",
                               "accepted_risk": "탈출 시 호스트 root", "mirrors": ["mirror.corp/mcp"]}}

    def test_engine_commands_are_built_in_one_place(self):
        self.assertEqual(runner.engine_argv("docker"), ["/usr/bin/docker", "--host", "unix:///var/run/docker.sock"])
        self.assertEqual(runner.engine_argv("podman"), ["/usr/bin/podman", "--remote=false"])

    def test_the_prefetch_budget_replaces_only_the_pull_deadline(self):
        child = Mock(returncode=0)
        child.poll.side_effect = [None, 0, 0]
        with patch.object(runner.subprocess, "run", side_effect=[SimpleNamespace(stdout=b"29.8.1"), SimpleNamespace(returncode=1),
                                                                 SimpleNamespace(stdout=b"null")]), \
                patch.object(runner.subprocess, "Popen", return_value=child), patch.object(runner.time, "sleep"), \
                patch.object(runner.time, "monotonic", side_effect=[0, runner.PREPARE_SECONDS + 60, runner.PREPARE_SECONDS + 61]):
            runner.engine_configuration(self.CONFIG, manifest(), Mock(), seconds=runner.PREFETCH_SECONDS)
        child.kill.assert_not_called()
        slow = Mock(returncode=None)
        slow.poll.return_value = None
        with patch.object(runner.subprocess, "run", side_effect=[SimpleNamespace(stdout=b"29.8.1"), SimpleNamespace(returncode=1)]), \
                patch.object(runner.subprocess, "Popen", return_value=slow), \
                patch.object(runner.time, "monotonic", side_effect=[0, runner.PREPARE_SECONDS + 1]), self.assertRaises(TimeoutError):
            runner.engine_configuration(self.CONFIG, manifest(), Mock())  # 첫 호출 한도는 그대로
        slow.kill.assert_called_once()


# ── 3. mcpgw-status 두 줄 ────────────────────────────────────────────────────────

class StatusLines(unittest.TestCase):
    def setUp(self):
        self.linux = extract(KIT / "managed-linux.py", {"STATE_LABEL", "MODE_LABEL", "next_step", "STATUS_STALE_SECONDS", "render_status"},
                             {"__name__": "status_under_test", "time": time, "os": os})

    def summary(self, **fields):
        return {"user": "emp", "state": "active", "connected": True, "last_report": time.time() - 3, "servers": 2,
                "kit": "0123456789abcdef", "updated": time.time(), **fields}

    def test_progress_and_the_document_folder_are_shown(self):
        local = {"ready": 1, "total": 2, "note": "이미지 받는 중: memory", "documents": ["/home/emp/mcp-docs"]}
        text = self.linux.render_status(self.summary(local=local), time.time())
        self.assertIn("로컬 MCP 준비: 1/2 (이미지 받는 중: memory)\n", text)
        self.assertIn("직원 문서 폴더: /home/emp/mcp-docs\n", text)
        done = self.linux.render_status(self.summary(local={**local, "ready": 2, "note": ""}), time.time())
        self.assertIn("로컬 MCP 준비: 2/2\n", done)

    def test_no_approved_local_server_or_no_list_yet_is_a_dash(self):
        for local in (None, {}, {"ready": 0, "total": 0, "note": "", "documents": []},
                      {"ready": None, "total": None, "note": "", "documents": []}):
            text = self.linux.render_status(self.summary(local=local), time.time())
            self.assertIn("로컬 MCP 준비: —\n", text)
            self.assertIn("직원 문서 폴더: —\n", text)

    def test_the_status_summary_is_the_only_thing_the_service_publishes_about_it(self):
        source = (KIT / "managed-linux.py").read_text(encoding="utf-8")
        self.assertIn('summary["local"] = dict(local.preparation)', source)
        self.assertEqual(set(self.summary(local={"ready": 1, "total": 1, "note": "", "documents": []})["local"]),
                         {"ready", "total", "note", "documents"})


# ── 4. 게이트웨이가 장치에 내주는 목록 ───────────────────────────────────────────

PACKAGE = "gateway_install_upfront_package"


class DeviceManifests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        @asynccontextmanager
        async def transaction():
            yield "connection"
        self.local = {"manifest": {"server_id": "a"}, "signature": "sig-a", "manifest_sha256": "a" * 64, "observer_device": "d"}
        servers = {"a": {"local": self.local}, "b": {"local": {**self.local, "manifest_sha256": "b" * 64}}, "remote": {}}
        self.package = ModuleType(PACKAGE)
        self.package.pac = SimpleNamespace(servers_for=Mock(return_value=["remote", "b", "a", "gone"]))
        self.package.registry = SimpleNamespace(server=lambda name: servers.get(name))
        self.authorized = AsyncMock(side_effect=lambda connection, device, server, digest, method: {"a"} >= {server} or None)
        self.device = {"endpoint_id": "dev", "owner_token": "owner"}
        self.env = {**G, "__package__": PACKAGE, "__name__": PACKAGE + ".jobs", "_device": AsyncMock(return_value=self.device),
                    "authorized": self.authorized,
                    "db": SimpleNamespace(transaction=transaction, fetch_one=AsyncMock(return_value={"token": "owner"}))}
        self.functions = load_functions(APP / "local_jobs.py", {"device_manifests"}, self.env)

    async def test_only_servers_that_pass_the_job_authorization_are_listed_with_their_signed_manifest(self):
        with patch.dict(sys.modules, {PACKAGE: self.package}):
            listed = await self.functions.device_manifests(self.device)
        self.assertEqual(listed, [{"server_id": "a", "manifest": {"server_id": "a"}, "signature": "sig-a",
                                   "manifest_sha256": "a" * 64}])
        asked = [(call.args[2], call.args[3], call.args[4]) for call in self.authorized.await_args_list]
        self.assertEqual(asked, [("a", "a" * 64, "tools/call"), ("b", "b" * 64, "tools/call")])  # 관찰 단계 승인은 제외된다
        self.package.pac.servers_for.assert_called_once_with({"token": "owner"})

    async def test_an_unknown_owner_gets_nothing(self):
        self.env["db"].fetch_one = AsyncMock(return_value=None)
        with patch.dict(sys.modules, {PACKAGE: self.package}):
            self.assertEqual(await self.functions.device_manifests(self.device), [])
        self.authorized.assert_not_awaited()

    async def test_a_device_that_is_not_active_is_refused_before_anything_is_read(self):
        self.env["_device"].side_effect = ConnectionError("not active")
        with patch.dict(sys.modules, {PACKAGE: self.package}), self.assertRaises(ConnectionError):
            await self.functions.device_manifests(self.device)
        self.authorized.assert_not_awaited()


@unittest.skipUnless(sys.platform.startswith("linux"), "dir_fd·O_NOFOLLOW 파일 연산은 Linux 전용")
class HomeLaunchers(unittest.TestCase):
    """설치 전에 열린 터미널의 PATH가 먼저 찾는 ~/.local/bin 런처를 관리 런처로 바꾸고, 업데이트가 되돌리면 다시, 제거 때 원래대로(D-228)."""

    def test_replace_heal_restore(self):
        spec = importlib.util.spec_from_file_location("managed_linux_hl", KIT / "managed-linux.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)
        home = os.path.join(root, "home")
        os.makedirs(os.path.join(home, ".local", "bin"))
        version = os.path.join(root, "claude-2.1")
        open(version, "w").close()
        launcher = os.path.join(home, ".local", "bin", "claude")
        os.symlink(version, launcher)
        person = SimpleNamespace(pw_dir=home, pw_uid=os.getuid(), pw_gid=os.getgid())
        config = {"owner_uid": os.getuid(), "username": "managed-u", "harnesses": ["claude"]}
        with patch.object(module, "STATE", module.Path(root) / "state"),              patch.object(module.pwd, "getpwuid", return_value=person):
            self.assertEqual(module.home_launchers(config), ["~/.local/bin/claude"])
            self.assertFalse(os.path.islink(launcher))
            self.assertIn("exec /usr/local/bin/claude", open(launcher).read())
            self.assertEqual(module.home_launchers(config), [])
            os.unlink(launcher)
            os.symlink(version, launcher)
            self.assertEqual(module.home_launchers(config), ["~/.local/bin/claude"])
            module.restore_home_launchers(config)
            self.assertEqual(os.readlink(launcher), version)
            self.assertEqual(module.home_launchers({**config, "owner_uid": None}), [])


if __name__ == "__main__":
    unittest.main()
