"""Employee-PC kit (field/pc/mcpgw_pc.py) against a fake Keycloak and Agent Service.

The fake implements what the kit relies on: the device authorization grant (RFC 8628, with a pending
poll first), refresh, revocation (RFC 7009), the realm's OpenID configuration, and /mcp/demo that only
accepts a live access token. Homes are temporary directories and the `claude` CLI is a recorder, so
this machine's real Claude Code and Codex configuration is never touched.
"""
import ast
import importlib.util
import io
import json
import os
import secrets
import subprocess
import threading
import time
import tomllib
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
KIT_PATH = ROOT / "field" / "pc" / "mcpgw_pc.py"


class FakeKeycloak:
    def __init__(self, access_seconds=300, deny=False):
        self.access_seconds, self.deny = access_seconds, deny
        self.lock = threading.Lock()
        self.devices, self.access, self.refresh, self.log = {}, {}, {}, []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, status, body=None):
                data = json.dumps(body).encode() if body is not None else b""
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.path == "/realms/mcp/.well-known/openid-configuration":
                    return self.reply(200, {"issuer": f"{fake.url}/realms/mcp"})
                self.reply(404, {})

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                if self.path == "/mcp/demo":
                    token = self.headers.get("Authorization", "").removeprefix("Bearer ")
                    with fake.lock:
                        valid = fake.access.get(token, 0) > time.time()
                    if not valid:
                        return self.reply(401, {"detail": "Invalid or expired Keycloak token"})
                    message = json.loads(body or b"{}")
                    return self.reply(200, {"jsonrpc": "2.0", "id": message.get("id"), "result": {"capabilities": {}}})
                form = {k: v[0] for k, v in urllib.parse.parse_qs(body.decode()).items()}
                status, answer = fake.oidc(self.path.removeprefix("/realms/mcp/protocol/openid-connect/"), form)
                self.reply(status, answer)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def issue(self):
        access, refresh = "at_" + secrets.token_hex(8), "rt_" + secrets.token_hex(8)
        self.access[access] = time.time() + self.access_seconds
        self.refresh[refresh] = True
        return {"access_token": access, "refresh_token": refresh, "expires_in": self.access_seconds,
                "refresh_expires_in": 28800, "token_type": "Bearer"}

    def oidc(self, path, form):
        with self.lock:
            if path == "auth/device":
                if form.get("client_id") != "mcp-cli":
                    return 401, {"error": "unauthorized_client"}
                code = secrets.token_hex(6)
                self.devices[code] = 0
                return 200, {"device_code": code, "user_code": "WXYZ-1234", "verification_uri": f"{self.url}/realms/mcp/device",
                             "verification_uri_complete": f"{self.url}/realms/mcp/device?user_code=WXYZ-1234",
                             "expires_in": 60, "interval": 0.05}
            if path == "revoke":
                if self.refresh.pop(form.get("token"), None):
                    self.log.append("revoke")
                return 200, {}
            grant = form.get("grant_type")
            if grant == "urn:ietf:params:oauth:grant-type:device_code":
                self.devices[form["device_code"]] += 1
                if self.devices[form["device_code"]] < 2:  # the person is still typing the code
                    return 400, {"error": "authorization_pending"}
                if self.deny:
                    return 400, {"error": "access_denied"}
                self.log.append("device")
                return 200, self.issue()
            if grant == "refresh_token":
                if not self.refresh.get(form.get("refresh_token")):
                    return 400, {"error": "invalid_grant", "error_description": "Session not active"}
                self.log.append("refresh")
                return 200, self.issue()
            if grant == "password" and form.get("client_id") == "mcp-gateway":
                if (form.get("username"), form.get("password")) != ("user", "pw"):
                    return 401, {"error": "invalid_grant", "error_description": "Invalid user credentials"}
                self.log.append("password")
                return 200, self.issue()
            return 400, {"error": "unauthorized_client"}

    def close(self):
        self.server.shutdown()


@pytest.fixture
def keycloak():
    fakes = []

    def start(**options):
        fakes.append(FakeKeycloak(**options))
        return fakes[-1]

    yield start
    for fake in fakes:
        fake.close()


@pytest.fixture
def kit(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("mcpgw_pc_under_test", KIT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("MCPGW_HOME", str(tmp_path / "kit home"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    module.claude_calls, module.claude_servers = [], set()

    def fake_run(command):
        module.claude_calls.append(command[1:])
        found = command[1:3] == ["mcp", "get"] and command[3] in module.claude_servers
        return subprocess.CompletedProcess(command, 0 if command[1:3] != ["mcp", "get"] or found else 1, "", "")

    monkeypatch.setattr(module, "run", fake_run)
    monkeypatch.setattr(module.shutil, "which", lambda name: "claude" if name == "claude" else None)
    monkeypatch.setattr(module.webbrowser, "open", lambda url: False)
    return module


def main(kit, monkeypatch, *argv, stdin=""):
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    kit.main(list(argv))


@pytest.mark.parametrize("url", ["http://mcp-gw.internal", "https://u:p@mcp-gw.internal", "https://mcp-gw.internal/?t=1"])
def test_kit_refuses_plaintext_and_credentials_in_the_address(kit, url):
    with pytest.raises(SystemExit):
        kit.gateway_url(url)


def test_device_login_then_helpers_only_in_harness_configs(kit, keycloak, tmp_path, monkeypatch, capsys):
    fake = keycloak()
    codex = tmp_path / "codex" / "config.toml"
    codex.parent.mkdir()
    codex.write_text('model = "gpt-5"\n', encoding="utf-8")
    main(kit, monkeypatch, "setup", "--url", fake.url, "--no-browser")
    out = capsys.readouterr().out
    assert "WXYZ-1234" in out and "device?user_code=WXYZ-1234" in out
    assert fake.log == ["device"]
    text = codex.read_text(encoding="utf-8")
    parsed = tomllib.loads(text)
    assert parsed["model"] == "gpt-5"
    demo = parsed["mcp_servers"]["demo"]
    # Agent Service's route has no trailing slash; a slash would redirect and lose the POST.
    assert demo["url"] == f"{fake.url}/mcp/demo"
    assert demo["http_headers_helper"].endswith(" header") and "--home" in demo["http_headers_helper"]
    add = [c for c in kit.claude_calls if c[:2] == ["mcp", "add-json"]]
    assert [c[4] for c in add] == ["demo"]
    entry = json.loads(add[0][5])
    assert entry["url"] == f"{fake.url}/mcp/demo" and entry["headersHelper"] == demo["http_headers_helper"]
    tokens = json.loads((tmp_path / "kit home" / "token.json").read_text(encoding="utf-8"))
    for secret in (tokens["access_token"], tokens["refresh_token"]):
        assert secret not in text and secret not in add[0][5]
    if os.name != "nt":
        assert (tmp_path / "kit home" / "token.json").stat().st_mode & 0o077 == 0
    # Running setup again keeps the session and replaces only the marked block.
    kit.claude_servers.add("demo")
    main(kit, monkeypatch, "setup", "--url", fake.url, "--no-browser")
    assert codex.read_text(encoding="utf-8") == text and fake.log == ["device"]


def test_helper_refreshes_with_a_cleared_environment(kit, keycloak, tmp_path, monkeypatch):
    fake = keycloak(access_seconds=61)  # inside the 60 s leeway after a second
    main(kit, monkeypatch, "setup", "--url", fake.url, "--no-browser", "--harness", "codex")
    time.sleep(1.2)
    env = {k: v for k, v in os.environ.items() if k != "MCPGW_HOME"}  # Codex clears the helper's environment
    procs = [subprocess.Popen(kit.helper_command(), shell=True, env=env, stdout=subprocess.PIPE, text=True) for _ in range(4)]
    headers = [json.loads(p.communicate(timeout=30)[0]) for p in procs]
    assert all(h["Authorization"].startswith("Bearer at_") for h in headers)
    assert fake.log.count("refresh") == 1


def test_denied_login_writes_no_harness_config(kit, keycloak, tmp_path, monkeypatch):
    fake = keycloak(deny=True)
    with pytest.raises(SystemExit, match="access_denied"):
        main(kit, monkeypatch, "setup", "--url", fake.url, "--no-browser")
    assert not [c for c in kit.claude_calls if c[:2] == ["mcp", "add-json"]]
    assert not (tmp_path / "codex" / "config.toml").exists()


def test_conflicts_are_found_before_anything_is_written(kit, tmp_path, monkeypatch):
    kit.claude_servers.add("demo")
    with pytest.raises(SystemExit, match="이미 'demo'"):
        main(kit, monkeypatch, "setup", "--url", "https://mcp-gw.internal", "--no-browser")
    assert not (tmp_path / "kit home").exists()


def test_password_grant_is_for_automation_with_another_client(kit, keycloak, monkeypatch):
    fake = keycloak()
    main(kit, monkeypatch, "setup", "--url", fake.url, "--client", "mcp-gateway", "--username", "user",
         "--password-stdin", stdin="pw\n")
    assert fake.log == ["password"]


def test_admin_pc_can_log_in_without_any_harness(kit, keycloak, tmp_path, monkeypatch, capsys):
    fake = keycloak()
    main(kit, monkeypatch, "setup", "--url", fake.url, "--no-browser", "--harness", "none")
    assert not kit.claude_calls and not (tmp_path / "codex" / "config.toml").exists()
    capsys.readouterr()
    kit.main(["token"])
    assert capsys.readouterr().out.startswith("at_")


def test_doctor_and_uninstall(kit, keycloak, tmp_path, monkeypatch, capsys):
    fake = keycloak()
    main(kit, monkeypatch, "setup", "--url", fake.url, "--no-browser", "--harness", "codex")
    capsys.readouterr()
    with pytest.raises(SystemExit):  # codex is not on the test PATH: that one line fails
        kit.main(["doctor"])
    lines = capsys.readouterr().out.splitlines()
    assert f"OK   TLS와 Keycloak issuer: {fake.url}/realms/mcp" in lines
    assert "OK   MCP demo initialize: HTTP 200" in lines
    assert "OK   헬퍼 명령(하네스가 실행하는 것)" in lines
    assert [line for line in lines if line.startswith("FAIL")] == ["FAIL Codex CLI 설치: npm install -g @openai/codex (0.148 이상)"]
    kit.main(["uninstall"])
    assert "revoke" in fake.log
    assert "mcp-gateway" not in (tmp_path / "codex" / "config.toml").read_text(encoding="utf-8")
    assert not any((tmp_path / "kit home").iterdir())


def test_managed_files_carry_no_secret(kit, tmp_path):
    out = tmp_path / "managed"
    kit.main(["managed", "--url", "https://mcp-gw.internal", "--out", str(out),
              "--python", "/usr/bin/python3", "--kit", "/opt/mcpgw/mcpgw_pc.py"])
    claude = json.loads((out / "managed-mcp.json").read_text(encoding="utf-8"))
    assert claude["mcpServers"]["demo"] == {"type": "http", "url": "https://mcp-gw.internal/mcp/demo",
                                            "headersHelper": '"/usr/bin/python3" "/opt/mcpgw/mcpgw_pc.py" header',
                                            "timeout": 300000}
    requirements = tomllib.loads((out / "requirements.toml").read_text(encoding="utf-8"))
    assert requirements["mcp_servers"]["demo"]["identity"] == {"url": "https://mcp-gw.internal/mcp/demo"}


def test_kit_parses_as_python_3_9():
    ast.parse(KIT_PATH.read_text(encoding="utf-8"), feature_version=(3, 9))
