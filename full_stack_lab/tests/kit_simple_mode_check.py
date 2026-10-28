"""D-239 오프라인 검사: 간편 모드(기본)는 직원 계정을 그대로 두고, 격리 모드만 관리 계정·커널 격리를 쓴다.

- bootstrap: 간편 모드는 관리 계정·하네스 복사·shim을 만들지 않고 `--mode simple`로 설치, 격리는 지금 경로 그대로
- managed-linux: /etc/environment의 CA 블록(조직 값 우선·제거 시 원문 복원), 간편 점검 한 항목, 자기 렌더링 백업 금지
- agent: 설치 확인 initialize·tools/list(세션 헤더·SSE·실패 사유), 모델 응답 측정(자격 파일 존재가 아니라 실행 결과)
- broker_binding: 간편 모드는 UID만, 다른 UID는 거부
실제 sudo·systemd·게이트웨이·모델은 쓰지 않는다(pj2 실측은 보고서). 저장소 루트:
python -B -X utf8 full_stack_lab/tests/kit_simple_mode_check.py
"""
import importlib.util
import io
import json
import struct
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock

KIT = Path(__file__).resolve().parents[2] / "endpoint-agent"


def load(name, path):
    # pwd·grp exist only on POSIX; the code under test never reaches them through these doubles.
    stubs = {module: ModuleType(module) for module in ("pwd", "grp") if module not in sys.modules}
    with mock.patch.dict(sys.modules, stubs):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class Bootstrap(unittest.TestCase):
    def setUp(self):
        self.b = load("bootstrap_simple", KIT / "bootstrap.py")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.enrollment = Path(self.temp.name) / "enrollment.json"
        self.enrollment.write_text('{"enrollment_token":"synthetic-existing-grant"}')

    def connect(self, isolated, state="active"):
        b = self.b
        calls = {}
        args = SimpleNamespace(enrollment=self.enrollment, skip_login=True)
        names = ("ensure_packages", "installed", "rollback", "managed_account", "place_harnesses", "find_clients",
                 "remove_shims", "remove_companion", "install_managed", "write_shims", "install_check")
        doubles = {name: mock.Mock(name=name) for name in names}
        doubles["installed"].return_value = False
        doubles["managed_account"].return_value = ("managed-emp", True)
        doubles["place_harnesses"].return_value = {"claude": {"path": "/opt/mcpgw-approved/claude", "digests": {"claude": "d"}}}
        doubles["find_clients"].return_value = {"claude": "/home/emp/.local/bin/claude"}
        doubles["write_shims"].return_value = ["/usr/local/bin/claude"]
        doubles["install_managed"].return_value = {"state": "pending-organization-activation"}
        doubles["install_check"].return_value = ([("모델 응답", "claude 정상 · 2.0초"), ("도구", "4개 (서버 1/1)"),
                                                  ("서버 연결", "learn 연결 정상")], "새 터미널에서 claude 또는 codex를 실행하세요")
        screen = mock.Mock()
        screen.summary = {"state": state, "connected": True}
        with mock.patch.multiple(b, **doubles), mock.patch.object(b, "SCREEN", screen), \
                mock.patch.object(b, "pwd", SimpleNamespace(getpwnam=lambda name: SimpleNamespace(pw_uid=1000))), \
                redirect_stdout(io.StringIO()) as out:
            core = SimpleNamespace(enroll=mock.Mock(return_value=({"device_key": "synthetic"}, {}, {})), diagnostic=mock.Mock(),
                                   private_write=lambda path, text: path.write_text(text), PROGRAMS=Path(self.temp.name))
            code = b.connect(core, "emp", isolated, args, 0.0)
        calls.update(doubles)
        return code, calls, json.loads(out.getvalue().strip().splitlines()[-1]), screen

    def test_simple_mode_leaves_the_employee_account_as_it_is(self):
        code, calls, result, screen = self.connect(isolated=False)
        self.assertEqual(code, 0)
        calls["managed_account"].assert_not_called()
        calls["place_harnesses"].assert_not_called()
        calls["write_shims"].assert_not_called()
        calls["remove_companion"].assert_called_once_with("emp")  # an earlier isolated companion goes
        account, placed, _, owner, mode = calls["install_managed"].call_args.args
        self.assertEqual((account, owner, mode), ("emp", None, "simple"))
        self.assertEqual(placed, {"claude": {"path": "/home/emp/.local/bin/claude"}})
        calls["ensure_packages"].assert_called_once_with(False)
        self.assertEqual((result["mode"], result["managed_account"]), ("simple", "emp"))
        self.assertEqual(result["checks"]["서버 연결"], "learn 연결 정상")
        self.assertEqual(result["state"], "active")
        screen.result.assert_called_once()  # the three cells and the next step reach the screen

    def test_isolated_mode_is_the_earlier_install(self):
        code, calls, result, _ = self.connect(isolated=True)
        self.assertEqual(code, 0)
        calls["managed_account"].assert_called_once_with("emp")
        calls["place_harnesses"].assert_called_once_with("emp")
        calls["find_clients"].assert_not_called()
        self.assertEqual(calls["install_managed"].call_args.args[3:], (1000, "isolated"))
        calls["write_shims"].assert_called_once()
        calls["ensure_packages"].assert_called_once_with(True)
        self.assertEqual(result["mode"], "isolated")

    def test_pending_quarantine_revocation_and_unknown_are_not_reported_as_active(self):
        for state in ("pending", "quarantined", "revoked", "unknown"):
            with self.subTest(state=state):
                _, _, result, _ = self.connect(isolated=False, state=state)
                self.assertEqual(result["state"], state)

    def test_isolated_install_does_not_name_a_harness_the_pc_lacks(self):
        b = self.b
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "codex"
            source.mkdir()
            for item in ("codex", "codex-code-mode-host"):
                (source / item).write_bytes(b"ELF")
            screen = mock.Mock()
            with mock.patch.object(b, "APPROVED", Path(folder) / "approved"), mock.patch.object(b, "SCREEN", screen),                     mock.patch.object(b.os, "chown", create=True), mock.patch.object(b, "native", return_value=True),                     mock.patch.object(b, "native_claude", return_value=None),                     mock.patch.object(b, "release_directory", side_effect=lambda _, name: source if name == "codex" else None):
                placed = b.place_harnesses("emp")
        self.assertEqual(list(placed), ["codex"])
        screen.say.assert_not_called()

    def test_simple_packages_are_tried_never_required(self):
        b = self.b
        with mock.patch.object(b.shutil, "which", side_effect=lambda tool: None if tool in ("openssl", "apt-get", "dnf", "pacman") else "/x"), \
                mock.patch.object(b, "has_engine", return_value=True), mock.patch.object(b, "start_engine"), \
                mock.patch.object(b, "ensure_toml"), redirect_stdout(io.StringIO()):
            b.ensure_packages(False)  # no package manager, openssl missing: still no Failed
            with self.assertRaises(b.Failed):
                b.ensure_packages(True)
        self.assertNotIn("gcc", b.OPTIONAL)


class ManagedLinux(unittest.TestCase):
    def setUp(self):
        self.m = load("managed_simple", KIT / "managed-linux.py")
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)

    def test_the_ca_lines_are_ours_alone_and_leave_the_file_as_found(self):
        environment = self.root / "environment"
        original = 'PATH="/usr/local/sbin:/usr/bin"\n'
        environment.write_text(original)
        values = {"NODE_EXTRA_CA_CERTS": "/usr/local/lib/mcpgw-managed/ca-1000.crt",
                  "CODEX_CA_CERTIFICATE": "/usr/local/lib/mcpgw-managed/ca-1000.crt"}
        with mock.patch.object(self.m, "ENVIRONMENT", environment):
            self.m.edit_environment(values)
            self.m.edit_environment(values)
            text = environment.read_text()
            self.assertEqual(text.count(self.m.CA_BEGIN), 1)
            self.assertTrue(text.startswith(original) and 'NODE_EXTRA_CA_CERTS="/usr/local/lib/mcpgw-managed/ca-1000.crt"' in text)
            self.m.edit_environment({})
            self.assertEqual(environment.read_text(), original)
            # A value the organization set already wins; ours is not added beside it.
            environment.write_text(original + "NODE_EXTRA_CA_CERTS=/etc/ssl/corp.pem\n")
            self.m.edit_environment(values)
            text = environment.read_text()
            self.assertNotIn("ca-1000.crt\"\nCODEX", text.split(self.m.CA_BEGIN)[0])
            self.assertIn('CODEX_CA_CERTIFICATE="', text)
            self.assertEqual(text.count("NODE_EXTRA_CA_CERTS"), 1)

    def test_simple_checks_report_only_the_protected_files(self):
        files = {}
        for name in ("managed-mcp.json", "managed-settings.json", "requirements.toml", "managed_config.toml"):
            files[name] = self.root / name
            files[name].write_text("rendered " + name)
        account = SimpleNamespace(pw_dir=str(self.root), pw_name="emp", pw_gid=1000, pw_uid=1000, pw_shell="/bin/bash")
        with mock.patch.object(self.m, "FILES", files), mock.patch.object(self.m, "protected", return_value=True), \
                mock.patch.object(self.m, "pwd", SimpleNamespace(getpwnam=lambda name: account)), \
                mock.patch.object(Path, "stat", lambda path, **kw: SimpleNamespace(st_mode=0o100644, st_uid=0)):
            hashes, health = self.m.checks({"uid": 1000, "username": "emp", "mode": "simple"}, {}, findings=[])
        self.assertEqual(health, {"protected_configs": True})
        self.assertEqual(set(hashes), set(files))

    def test_a_rendering_of_ours_is_never_kept_as_the_employee_original(self):
        self.assertTrue(self.m.ours('{"mcpServers": {"x": {"url": "https://gw.example/mcp/x/"}}}', "https://gw.example"))
        self.assertTrue(self.m.ours('{\n  "allowManagedHooksOnly": true\n}', "https://gw.example"))
        self.assertFalse(self.m.ours('{"theme": "dark"}', "https://gw.example"))

    def test_the_cells_say_what_was_measured(self):
        cells = self.m.connection_cells({"initialized": ["learn", "deepwiki"], "failed": {}, "tools": 7}, 2)
        self.assertEqual(cells, [("도구", "7개 (서버 2/2)"), ("서버 연결", "learn 연결 정상")])
        cells = self.m.connection_cells({"initialized": [], "failed": {"learn": "HTTP 403"}, "tools": 0}, 1)
        self.assertEqual(cells, [("도구", "—"), ("서버 연결", "실패 · learn HTTP 403")])


class Gateway(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.headers.get("Authorization") != "Bearer good" or self.path == "/mcp/closed/":
            self.send_response(403)
            self.end_headers()
            return
        if body.get("method") == "notifications/initialized":
            self.send_response(202)
            self.end_headers()
            return
        if body["method"] == "initialize":
            payload = {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-06-18", "serverInfo": {"name": "s"}}}
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Mcp-Session-Id", "session-1")
            self.end_headers()
            self.wfile.write(("event: message\ndata: " + json.dumps(payload) + "\n\n").encode())
            return
        if self.headers.get("Mcp-Session-Id") != "session-1":
            self.send_response(400)
            self.end_headers()
            return
        payload = {"jsonrpc": "2.0", "id": 2, "result": {"tools": [{"name": "a"}, {"name": "b"}, {"name": "c"}]}}
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)


class InstallCheck(unittest.TestCase):
    def setUp(self):
        self.agent = load("agent_simple", KIT / "agent.py")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Gateway)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def test_initialize_and_tools_list_with_the_harness_header(self):
        found = self.agent.connection_check(self.url, self.agent.ssl.create_default_context(), "Bearer good", ["learn", "closed"])
        self.assertEqual(found, {"initialized": ["learn"], "failed": {"closed": "HTTP 403"}, "tools": 3})
        refused = self.agent.connection_check(self.url, self.agent.ssl.create_default_context(), "Bearer other", ["learn"])
        self.assertEqual((refused["initialized"], refused["tools"]), ([], 0))

    def test_a_model_answer_is_a_run_not_a_file(self):
        ok = self.agent.model_check([sys.executable, "-c", "print('OK')"])
        self.assertTrue(ok["ok"])
        silent = self.agent.model_check([sys.executable, "-c", "pass"])
        self.assertFalse(silent["ok"])
        failed = self.agent.model_check([sys.executable, "-c", "import sys; print('401 Unauthorized', file=sys.stderr); sys.exit(1)"])
        self.assertEqual((failed["ok"], failed["detail"]), (False, "401 Unauthorized"))
        missing = self.agent.model_check([str(Path(self.server.server_address[0]) / "no-such-harness")])
        self.assertFalse(missing["ok"])


class HarnessCommandLine(unittest.TestCase):
    """S4-03: the employee's prompt is in the harness's argv; the harness itself is not a stdio MCP server."""

    def test_harnesses_are_not_stdio_servers_but_the_servers_still_are(self):
        agent = load("agent_markers", KIT / "agent.py")
        claude = str(Path(tempfile.gettempdir()) / "harness path/claude.exe")
        codex = str(Path(tempfile.gettempdir()) / "harness path/codex.exe")
        harnesses = [
            '/home/pj2/.local/bin/claude -p "modelcontextprotocol/python-sdk 위키 목차"',
            f'"{claude}" -p "modelcontextprotocol"',
            "/usr/bin/node /usr/lib/node_modules/@anthropic-ai/claude-code/cli.js -p fastmcp",
            'codex exec "mcp-server 예제를 보여줘"',
            f'"{codex}" exec "fastmcp"',
        ]
        servers = ["npx -y @modelcontextprotocol/server-filesystem /tmp", "node /home/u/mcp-server/index.js",
                   "python -m mcp_server_git", "/usr/bin/node /opt/claude-mcp/server.js modelcontextprotocol"]
        for line in harnesses:
            self.assertTrue(agent.PROCESS_MARKERS.search(line), line)  # the marker matches: that was the false alarm
            with mock.patch.object(agent, "CONFIG", {"ENDPOINT_HARNESS_PATHS": [
                    "/home/pj2/.local/bin/claude", "/usr/bin/codex", claude, codex]}), \
                 mock.patch.object(agent.shutil, "which", side_effect=lambda p: "/usr/bin/codex" if p == "codex" else None):
                self.assertTrue(agent.harness_process(line), line)
        for line in servers:
            self.assertFalse(agent.harness_process(line), line)


class Broker(unittest.TestCase):
    def test_simple_mode_answers_the_account_uid_only(self):
        binding = load("broker_simple", KIT / "broker_binding.py")
        fake_socket = SimpleNamespace(SOL_SOCKET=1, SO_PEERCRED=17, SO_PEERSEC=31)

        def peer(uid):
            return SimpleNamespace(getsockopt=lambda level, option, size: struct.pack("3i", 42, uid, uid))
        with mock.patch.object(binding, "socket", fake_socket), redirect_stdout(io.StringIO()):
            self.assertTrue(binding.authorize_peer(peer(1000), {"uid": 1000, "username": "emp", "broker_binding": "uid"}))
            self.assertFalse(binding.authorize_peer(peer(1001), {"uid": 1000, "username": "emp", "broker_binding": "uid"}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
