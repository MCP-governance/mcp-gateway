"""D-217 오프라인 검사: 키트 재설치 연속성, 활성화 대기 사유, 직원용 상태 명령, 키트 판본, 로그 잡음.

DB·소켓·AppArmor는 대역이며 집행 증거가 아니다. 저장소 루트: python -B -X utf8 full_stack_lab/tests/kit_continuity_check.py
"""
import ast
import hashlib
import importlib.util
import json
import os
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / "full_stack_lab"
KIT = ROOT / "endpoint-agent"


def extract(path, names, namespace):
    """Only the named top-level functions and constants of a file, run in `namespace`."""
    nodes = [n for n in ast.parse(path.read_text(encoding="utf-8")).body
             if getattr(n, "name", None) in names
             or isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in n.targets)]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return SimpleNamespace(**namespace)


def load_module(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), KIT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── 1. 재설치가 활성화를 잃지 않는다 ─────────────────────────────────────────────

class FakeConnection:
    def __init__(self, earlier, stopped):
        self.earlier, self.stopped, self.inserts, self.events = earlier, stopped, [], []

    async def execute(self, sql, params=()):
        answer = SimpleNamespace(fetchone=AsyncMock(return_value=None), fetchall=AsyncMock(return_value=[]))
        if "UPDATE endpoint_enrollment_tokens SET consumed_at" in sql:
            answer.fetchone = AsyncMock(return_value={"owner_token": "emp-1"})
        elif "FROM endpoint_agents" in sql:
            answer.fetchall = AsyncMock(return_value=self.earlier)
        elif "FROM local_run_stops" in sql:
            answer.fetchone = AsyncMock(return_value={"?column?": 1} if self.stopped else None)
        elif sql.lstrip().startswith("INSERT INTO endpoint_agents"):
            self.inserts.append(params)
        elif "INTO endpoint_managed_events" in sql:
            self.events.append((sql, params))
        return answer


def device(endpoint_id, hostname, state="active", machine=None, activated_by="admin-1", platform="Linux 6.8.0", detail=None):
    return {"endpoint_id": endpoint_id, "hostname": hostname, "managed_state": state, "activated_by": activated_by,
            "activated_at": "2026-10-23T09:00:00+00:00",
            "detail": {**({"machine_id": machine} if machine else {}), **(detail or {})}, "platform": platform}


class Reinstall(unittest.IsolatedAsyncioTestCase):
    async def enroll(self, earlier, *, stopped=False, hostname="pc-1", machine="a" * 64, platform="linux", sid=None,
                     username="emp"):
        connection = FakeConnection(earlier, stopped)

        class Transaction:
            async def __aenter__(inner):
                return connection

            async def __aexit__(inner, *args):
                return False
        db = SimpleNamespace(transaction=Transaction, execute=AsyncMock(),
                             fetch_one=AsyncMock(return_value={"endpoint_id": "new"}))
        revoke = AsyncMock()
        plane = extract(LAB / "gateway/app/endpoint_plane.py",
                        {"_same_pc", "consume_enrollment", "managed_platform", "_hash_key", "DEVICE_SCOPES"},
                        {"__name__": "continuity_under_test", "db": db, "uuid": uuid, "hashlib": hashlib, "os": os,
                         "Jsonb": lambda value: value, "revoke_device": revoke})
        await plane.consume_enrollment("t" * 43, "k" * 43, hostname, username, 1001, platform=platform,
                                       local_sid=sid, machine_id=machine)
        self.db, self.revoke, self.connection = db, revoke, connection
        insert = connection.inserts[0]
        return {"state": insert[8], "activated_by": insert[12], "detail": insert[14]}

    async def test_same_pc_reinstall_continues_the_activation_and_replaces_the_old_device(self):
        new = await self.enroll([device("old", "pc-1", machine="a" * 64)])
        self.assertEqual((new["state"], new["activated_by"]), ("active", "admin-1"))
        self.assertEqual(new["detail"]["inherited_from"], "old")
        self.revoke.assert_awaited_once_with("old", "reinstall")
        self.assertIn("superseded_by", self.db.execute.await_args.args[1][0])
        activated = [params[2] for sql, params in self.connection.events if "'activated'" in sql]
        self.assertEqual([item["inherited_from"] for item in activated], ["old"])
        self.assertEqual(activated[0]["actor"], "admin-1")

    async def test_ghosts_with_a_rewritten_platform_column_are_found(self):
        # The observer's own enroll report rewrites `platform` to "Linux 6.8…"; matching on it left every ghost active.
        earlier = [device("a", "pc-1", machine="a" * 64, platform="Linux 6.8.0"),
                   device("b", "pc-1", state="pending", platform="Linux 6.8.0")]
        await self.enroll(earlier)
        self.assertEqual([c.args[0] for c in self.revoke.await_args_list], ["a", "b"])

    async def test_a_quarantined_device_is_not_continued_but_is_still_replaced(self):
        new = await self.enroll([device("old", "pc-1", state="quarantined", machine="a" * 64)])
        self.assertEqual((new["state"], new["activated_by"]), ("pending", None))
        self.assertNotIn("inherited_from", new["detail"])
        self.revoke.assert_awaited_once_with("old", "reinstall")

    async def test_an_unactivated_device_does_not_become_active(self):
        new = await self.enroll([device("old", "pc-1", state="pending", activated_by=None)])
        self.assertEqual(new["state"], "pending")

    async def test_administrator_stopped_local_runs_are_not_lifted_by_reinstall(self):
        new = await self.enroll([device("old", "pc-1", machine="a" * 64)], stopped=True)
        self.assertEqual(new["state"], "pending")

    async def test_another_pc_stays_pending_and_the_other_device_is_left_alone(self):
        # Same employee, same account name, same host name, a different machine id: a copy, not a reinstall.
        new = await self.enroll([device("old", "pc-1", machine="b" * 64)])
        self.assertEqual(new["state"], "pending")
        self.revoke.assert_not_awaited()
        new = await self.enroll([device("old", "pc-1", machine="a" * 64)], hostname="pc-2", machine="c" * 64)
        self.assertEqual(new["state"], "pending")
        self.revoke.assert_not_awaited()

    async def test_a_kit_before_the_machine_id_is_recognised_by_host_name(self):
        new = await self.enroll([device("old", "pc-1")])
        self.assertEqual(new["state"], "active")
        new = await self.enroll([device("old", "pc-1")], hostname="pc-2")
        self.assertEqual(new["state"], "pending")

    async def test_the_newest_device_decides_not_an_older_active_one(self):
        # Newest first: a quarantined latest device holds, whatever an older record says.
        new = await self.enroll([device("newer", "pc-1", state="quarantined"), device("older", "pc-1")])
        self.assertEqual(new["state"], "pending")

    async def test_windows_matches_the_account_sid(self):
        sid = "S-1-5-21-1-2-3-1001"
        win = {"local_sid": sid, "helper_command": "x"}
        new = await self.enroll([device("old", "pc-1", platform="Windows 10", detail=win)], platform="windows", sid=sid, machine=None)
        self.assertEqual(new["state"], "active")
        new = await self.enroll([device("old", "pc-1", platform="Windows 10", detail=win)], platform="windows",
                                sid="S-1-5-21-9-9-9-1001", machine=None)
        self.assertEqual(new["state"], "pending")
        # A Linux device is never the earlier device of a Windows install.
        new = await self.enroll([device("old", "pc-1")], platform="windows", sid=sid, machine=None)
        self.assertEqual(new["state"], "pending")


# ── 2. 활성화 대기 사유가 하네스의 401 줄에 보인다 ─────────────────────────────────

class PendingReason(unittest.TestCase):
    def authenticate(self, header):
        class Refused(Exception):
            def __init__(self, status, detail):
                self.status_code, self.detail = status, detail
        contract = extract(LAB / "gateway/app/agent_contract.py", {"PLACEHOLDER_REASON", "authenticate"},
                           {"HTTPException": Refused, "jwt": SimpleNamespace(PyJWTError=Exception, decode=lambda *a, **k: {}),
                            "public_key": lambda: "", "ALGORITHM": "", "AUDIENCE": "", "ISSUER": ""})
        try:
            contract.authenticate(header)
        except Refused as refused:
            return refused.status_code, refused.detail
        self.fail("the placeholder must be refused")

    def test_each_placeholder_names_its_reason(self):
        self.assertIn("활성화를 기다리는 중", self.authenticate("Bearer endpoint-not-active.pending")[1])
        self.assertIn("격리", self.authenticate("Bearer endpoint-not-active.quarantined")[1])
        status, detail = self.authenticate("Bearer endpoint-not-active")
        self.assertEqual(status, 401)
        self.assertIn("활성 상태가 아니거나", detail)

    @unittest.skipUnless(os.name == "posix", "Linux 소켓 필요")
    def test_helper_prints_the_state_the_service_reports(self):
        with tempfile.TemporaryDirectory() as raw:
            sock = str(Path(raw) / "broker.sock")

            class Answer(socketserver.BaseRequestHandler):
                def handle(inner):
                    inner.request.sendall(json.dumps({"error": "x", "state": inner.server.state}).encode())
            server = socketserver.UnixStreamServer(sock, Answer)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                for state, expected in (("pending", "Bearer endpoint-not-active.pending"),
                                        ("quarantined", "Bearer endpoint-not-active.quarantined"),
                                        ("", "Bearer endpoint-not-active"), ("anything-else", "Bearer endpoint-not-active")):
                    server.state = state
                    run = subprocess.run([sys.executable, str(KIT / "managed-linux.py"), "header", "--socket", sock],
                                         capture_output=True, text=True)
                    self.assertEqual(json.loads(run.stdout), {"Authorization": expected}, run.stderr)
            finally:
                server.shutdown()


# ── 3·4. 직원용 상태 명령과 키트 판본 ──────────────────────────────────────────────

class StatusCommand(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.linux = extract(KIT / "managed-linux.py",
                             {"STATE_LABEL", "STATUS_STALE_SECONDS", "status_path", "render_status", "publish_status",
                              "private_write", "kit_version", "PROGRAM_FILES", "machine_id"},
                             {"__name__": "status_under_test", "Path": Path, "PROGRAMS": Path(self.folder.name), "time": time,
                              "json": json, "os": os, "tempfile": tempfile, "hashlib": hashlib})

    def summary(self, **fields):
        return {"user": "emp", "state": "active", "connected": True, "last_report": time.time() - 12, "servers": 3,
                "kit": "0123456789abcdef", "updated": time.time(), **fields}

    def test_states_in_korean_with_the_five_facts(self):
        text = self.linux.render_status(self.summary(), time.time())
        for expected in ("장치 상태: 활성", "게이트웨이: 연결됨", "마지막 보고: ", "초 전)", "승인 서버: 3개", "키트 판본: 0123456789ab"):
            self.assertIn(expected, text)
        pending = self.linux.render_status(self.summary(state="pending", servers=0), time.time())
        self.assertIn("장치 상태: 활성화 대기", pending)
        self.assertIn("승인 서버: 0개", pending)
        self.assertIn("활성화하면 자동으로 연결됩니다", pending)
        self.assertIn("중지 (점검에서 격리됨)", self.linux.render_status(self.summary(state="quarantined"), time.time()))
        self.assertIn("중지 (등록 해제됨)", self.linux.render_status(self.summary(state="revoked", connected=False), time.time()))

    def test_empty_values_are_dashes_and_a_silent_service_is_not_shown_as_active(self):
        text = self.linux.render_status(self.summary(last_report=None, servers=None, kit=None, state="unknown", connected=False),
                                        time.time())
        self.assertIn("마지막 보고: —", text)
        self.assertIn("승인 서버: —", text)
        self.assertIn("키트 판본: —", text)
        stale = self.linux.render_status(self.summary(updated=time.time() - 600), time.time())
        self.assertIn("장치 상태: 확인 안 됨", stale)
        self.assertIn("게이트웨이: 연결 안 됨", stale)
        self.assertIn("응답하지 않습니다", stale)

    def test_published_files_hold_only_the_summary(self):
        self.linux.publish_status(self.summary())
        stored = json.loads((Path(self.folder.name) / "status-emp.json").read_text())
        self.assertEqual(set(stored), {"user", "state", "connected", "last_report", "servers", "kit", "updated"})
        self.assertIn("장치 상태: 활성", (Path(self.folder.name) / "status-emp.txt").read_text(encoding="utf-8"))
        if os.name == "posix":
            self.assertEqual((Path(self.folder.name) / "status-emp.json").stat().st_mode & 0o777, 0o644)

    @unittest.skipUnless(os.name == "posix", "Linux 계정 모듈 필요")
    def test_status_command_reads_the_published_summary(self):
        module = load_module("managed-linux")
        with patch.object(module, "PROGRAMS", Path(self.folder.name)):
            module.publish_status(self.summary(state="pending"))
            with patch("builtins.print") as printed:
                module.status(SimpleNamespace(user="emp"))
                module.status(SimpleNamespace(user=None))  # an administrator's account finds the only summary
            for call in printed.call_args_list:
                self.assertIn("활성화 대기", call.args[0])
            with self.assertRaises(ValueError):
                module.status(SimpleNamespace(user="nobody"))

    def test_kit_version_is_the_same_on_the_pc_and_in_health(self):
        listed = extract(LAB / "gateway/app/release.py", {"KIT_PROGRAMS"}, {}).KIT_PROGRAMS
        self.assertEqual(tuple(listed), tuple(self.linux.PROGRAM_FILES))
        self.assertEqual(len(set(listed)), len(listed))
        release = extract(LAB / "gateway/app/release.py", {"KIT_PROGRAMS", "kit_sha256", "_code_info", "build_info"},
                          {"__file__": str(LAB / "gateway/app/release.py"), "os": os, "hashlib": hashlib, "Path": Path,
                           "lru_cache": __import__("functools").lru_cache})
        with patch.dict(os.environ, {"ENDPOINT_KIT_DIR": str(KIT)}):
            health = release.build_info()["pc_kit_sha256"]
        self.assertRegex(health, r"^[0-9a-f]{64}$")
        self.assertEqual(health, self.linux.kit_version(KIT))
        with patch.dict(os.environ, {"ENDPOINT_KIT_DIR": str(Path(self.folder.name) / "none")}):
            self.assertIsNone(release.kit_sha256())

    def test_the_gateway_container_can_read_the_kit(self):
        compose = (LAB / "compose.field.yaml").read_text(encoding="utf-8")
        gateway = compose[compose.index("\n  gateway:"):compose.index("\n  gateway-sse:")]
        self.assertIn("../endpoint-agent:/endpoint-kit:ro", gateway)

    def test_machine_id_is_a_hash_not_the_raw_id(self):
        with patch.object(Path, "read_text", return_value="0123456789abcdef0123456789abcdef\n"):
            value = self.linux.machine_id()
        self.assertEqual(len(value), 64)
        self.assertNotIn("0123456789abcdef", value)


# ── 5. 로그 잡음 ────────────────────────────────────────────────────────────────

class Refused(Exception):
    code = 409


class LogNoise(unittest.TestCase):
    def run_runner(self, failures, then):
        runner = load_module("local-runner")
        sleeps, logged, calls = [], [], []

        def request(config, path, body=None):
            calls.append(path)
            if len(calls) <= failures:
                raise Refused("pending")
            if len(calls) > failures + then:
                raise KeyboardInterrupt
            return {"job": None}
        with patch.object(runner, "recover", lambda config, request: None), \
                patch.object(runner.time, "sleep", sleeps.append), \
                patch.dict(sys.modules, {"pwd": SimpleNamespace(getpwnam=lambda name: object())}):
            with self.assertRaises(KeyboardInterrupt):
                runner.run({"username": "u"}, request, logged.append)
        return logged, sleeps

    def test_waiting_is_said_once_and_the_interval_grows(self):
        logged, sleeps = self.run_runner(failures=8, then=2)
        self.assertEqual(logged, [{"local_runner": "waiting", "status": 409}, {"local_runner": "ready"}])
        self.assertEqual(sleeps, sorted(sleeps))
        self.assertGreaterEqual(sleeps[-1], 16)
        self.assertLessEqual(sleeps[-1], 30)

    def test_other_failures_are_logged_once_per_change_with_the_short_pause(self):
        runner = load_module("local-runner")
        sleeps, logged, calls = [], [], []

        def request(config, path, body=None):
            calls.append(path)
            if len(calls) > 4:
                raise KeyboardInterrupt
            raise OSError("down")
        with patch.object(runner, "recover", lambda config, request: None), patch.object(runner.time, "sleep", sleeps.append), \
                patch.dict(sys.modules, {"pwd": SimpleNamespace(getpwnam=lambda name: object())}):
            with self.assertRaises(KeyboardInterrupt):
                runner.run({"username": "u"}, request, logged.append)
        self.assertEqual(logged, [{"local_runner": "error", "error": "OSError"}])
        self.assertEqual(set(sleeps), {1})

    def test_binding_check_asks_for_the_profiles_of_the_installed_stage(self):
        binding = load_module("broker_binding")
        enforcer = extract(KIT / "enforce-linux.py", {"profile", "bound_profile", "TOOLS"},
                           {"Path": Path, "BASE": PurePosixPath("/usr/local/lib/mcpgw-enforcement")})
        clients = {"codex": Path("/opt/a/codex"), "claude": Path("/opt/a/claude")}
        for mode in ("warn", "enforce"):
            text = enforcer.profile("mcpgw-unit", Path("/x/login-shell"), "/home/unit", clients, True, True, {}, mode)
            declared = {line.split()[1] for line in text.splitlines() if line.startswith("profile ")}
            self.assertLessEqual(binding.enforcing_profiles("unit", mode=mode), declared, mode)
        self.assertNotIn("mcpgw-unit-bound-credential", binding.enforcing_profiles("unit", mode="warn"))

        def ready(mode, profiles):
            files = {"/sys/module/apparmor/parameters/enabled": "Y\n",
                     "/sys/kernel/security/apparmor/profiles": "\n".join(p + " (enforce)" for p in profiles),
                     "/sys/kernel/security/apparmor/features/network/af_unix": "yes\n",
                     "/sys/kernel/security/apparmor/features/ptrace/mask": "read trace\n"}
            with patch.object(Path, "read_text", lambda path, *a, **k: files[path.as_posix()]):
                return binding.kernel_ready("unit", mode=mode)
        # The warning stage loads only the legacy profiles; asking for the bound ones was the false warning.
        self.assertEqual(ready("warn", binding.enforcing_profiles("unit", mode="warn")), "")
        self.assertEqual(ready("enforce", binding.enforcing_profiles("unit", mode="warn")), "profiles-not-enforcing")
        self.assertEqual(ready("warn", []), "profiles-not-enforcing")


if __name__ == "__main__":
    unittest.main(verbosity=2)
