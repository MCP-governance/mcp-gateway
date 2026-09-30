#!/usr/bin/env python3
"""실기기 배치(field deploy) 검사 — 표준 라이브러리만, 임시 HOME·CODEX_HOME만 쓴다.

    python3 tests/field_kit_check.py

확인하는 것:
  * field/pc/mcpgw_pc.py(직원 PC 키트): HTTPS 또는 Tailscale/loopback HTTP만 허용, 쓰기 전 충돌 확인,
    Claude Code·Codex 설정에 토큰 원문이 없고 헬퍼 명령만 있음, Codex 블록이 사용자 설정을 보존하고
    멱등, uninstall이 자기 것만 지우고 IdP에 폐기를 요청, 관리형 파일에 비밀이 없음.
  * 실제 IdP처럼 리프레시 토큰을 회전하고 재사용을 계열 폐기로 처리하는 가짜 IdP·Gateway에 대해:
    로그인 → 헬퍼 10개 동시 실행(하네스가 서버마다 부르는 모양)에서도 갱신은 직렬이고 재사용이 없다.
    Codex처럼 환경 변수를 비운 채 헬퍼를 실행해도 --home으로 토큰을 찾는다. doctor가 서버마다 200.
  * field/Caddyfile의 경로(접두어 보존, /api/health는 Gateway)와 compose.field.yaml의 게시 범위.

검사 도구 자신이 죽으면 실패로 센다(AGENTS.md) — 예외를 삼키지 않는다.
"""
from __future__ import annotations

import ast
import importlib.util
import io
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
import tomllib
import unittest
import urllib.parse
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

LAB = Path(__file__).resolve().parent.parent
KIT = LAB / "field" / "pc" / "mcpgw_pc.py"
SERVERS = sorted(tomllib.loads((LAB / "registry" / "catalog.toml").read_text(encoding="utf-8"))["servers"])


def load_kit():
    spec = importlib.util.spec_from_file_location("mcpgw_pc_under_test", KIT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeIdpGateway:
    """agent-service의 /oauth/token·/oauth/revoke(리프레시 회전, 재사용이면 계열 폐기 — idp.py와 같은 규칙)와
    Gateway의 /api/health·/mcp/<server>/(유효한 접근 토큰만 통과)."""

    def __init__(self, access_seconds: int = 600):
        self.access_seconds = access_seconds
        self.lock = threading.Lock()
        self.access, self.refresh, self.revoked, self.log = {}, {}, set(), []
        # /api/pc/inventory(D-51): 받은 보고와 돌려줄 결정. 결정은 테스트가 바꾼다.
        self.reports, self.denied = [], {"claude": [], "codex": []}
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
                self.reply(200, {"status": "ok"}) if self.path == "/api/health" else self.reply(404, {})

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                if self.path.startswith("/oauth/"):
                    form = {k: v[0] for k, v in urllib.parse.parse_qs(body.decode()).items()}
                    status, answer = fake.oauth(self.path, form)
                    return self.reply(status, answer)
                if self.path == "/api/pc/inventory":
                    token = self.headers.get("Authorization", "").removeprefix("Bearer ")
                    with fake.lock:
                        if fake.access.get(token, 0) < time.time():
                            return self.reply(401, {"detail": "token"})
                        report = json.loads(body)
                        fake.reports.append(report)
                    return self.reply(200, {"accepted": len(report["items"]), "review": [], "policy": {
                        "claude": {"deniedMcpServers": fake.denied["claude"], "allowAllClaudeAiMcps": True},
                        "codex": {"apps_disabled": fake.denied["codex"], "features_disabled": []}}})
                if self.path.startswith("/mcp/") and self.path.endswith("/"):
                    token = self.headers.get("Authorization", "").removeprefix("Bearer ")
                    with fake.lock:
                        valid = fake.access.get(token, 0) > time.time()
                    if not valid:
                        return self.reply(401, {"detail": "token"})
                    message = json.loads(body or b"{}")
                    return self.reply(200, {"jsonrpc": "2.0", "id": message.get("id"), "result": {
                        "protocolVersion": "2025-11-25", "capabilities": {}, "serverInfo": {"name": "fake"}}})
                self.reply(404, {})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def issue(self, client, family):
        access, refresh = "at_" + secrets.token_hex(8), "rt_" + secrets.token_hex(8)
        self.access[access] = time.time() + self.access_seconds
        self.refresh[refresh] = {"client": client, "family": family, "rotated": False}
        return {"access_token": access, "refresh_token": refresh, "expires_in": self.access_seconds, "token_type": "Bearer"}

    def oauth(self, path, form):
        with self.lock:
            if path == "/oauth/revoke":
                if form.get("token") in self.refresh:
                    self.revoked.add(self.refresh[form["token"]]["family"])
                    self.log.append("revoke")
                return 200, {}
            if form.get("grant_type") == "password":
                if (form.get("username"), form.get("password")) != ("ysg@bob.local", "test-password"):
                    return 401, {"error": "invalid_grant", "error_description": "합성 계정과 비밀번호를 확인하세요."}
                self.log.append("password")
                return 200, self.issue(form["client_id"], secrets.token_hex(4))
            stored = self.refresh.get(form.get("refresh_token"))
            if not stored or stored["client"] != form.get("client_id") or stored["family"] in self.revoked:
                return 400, {"error": "invalid_grant"}
            if stored["rotated"]:
                self.revoked.add(stored["family"])
                self.log.append("REUSE")
                return 400, {"error": "invalid_grant"}
            stored["rotated"] = True
            self.log.append("refresh")
            return 200, self.issue(form["client_id"], stored["family"])

    def close(self):
        self.server.shutdown()


class KitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="field kit "))  # 공백이 든 경로도 헬퍼가 한 인자로 받는지
        self.env = mock.patch.dict(os.environ, {"MCPGW_HOME": str(self.tmp / "home"), "CODEX_HOME": str(self.tmp / "codex"),
                                                "CLAUDE_CONFIG_DIR": str(self.tmp / "claude")})
        self.env.start()
        self.kit = load_kit()
        self.claude_calls, self.claude_servers = [], set()

        self.claude_list = ""  # `claude mcp list`가 찍을 내용

        def fake_run(command):
            self.claude_calls.append(command[1:])
            found = command[1:3] == ["mcp", "get"] and command[3] in self.claude_servers
            listing = self.claude_list if command[1:3] == ["mcp", "list"] else ""
            return subprocess.CompletedProcess(command, 0 if command[1:3] != ["mcp", "get"] or found else 1, listing, "")

        self.kit.run = fake_run
        self.which = mock.patch.object(self.kit.shutil, "which", lambda name: "claude" if name == "claude" else None)
        self.which.start()

    def tearDown(self):
        self.which.stop()
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def main(self, *argv, stdin=""):
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(stdin)), redirect_stdout(out):
            self.kit.main(list(argv))
        return out.getvalue()

    def setup_against(self, url, *extra):
        return self.main("setup", "--url", url, "--servers", ",".join(SERVERS), "--workstation", "ysg-laptop",
                         "--email", "ysg@bob.local", "--password-stdin", *extra, stdin="test-password\n")

    def test_address_rules(self):
        for bad in ("http://mcp-gw.internal", "http://192.168.0.10", "https://u:p@mcp-gw.internal", "https://mcp-gw.internal/?t=1"):
            with self.assertRaises(SystemExit):
                self.kit.gateway_url(bad)
        self.assertEqual(self.kit.gateway_url("https://mcp-gw.internal/"), "https://mcp-gw.internal")
        self.assertEqual(self.kit.gateway_url("http://127.0.0.1:8443"), "http://127.0.0.1:8443")
        self.assertEqual(self.kit.gateway_url("http://100.83.175.111:443"), "http://100.83.175.111:443")

    def test_setup_writes_helpers_keeps_user_config_and_is_idempotent(self):
        fake = FakeIdpGateway()
        self.addCleanup(fake.close)
        codex = self.tmp / "codex" / "config.toml"
        codex.parent.mkdir(parents=True)
        codex.write_text('model = "gpt-5"\n\n[profiles.fast]\nmodel = "gpt-5-mini"\n', encoding="utf-8")
        self.setup_against(fake.url)
        first = codex.read_text(encoding="utf-8")
        parsed = tomllib.loads(first)
        self.assertEqual(parsed["model"], "gpt-5")
        self.assertEqual(sorted(parsed["mcp_servers"]), SERVERS)
        helper = parsed["mcp_servers"]["filesystem"]["http_headers_helper"]
        self.assertTrue(helper.endswith(" header") and "--home" in helper)
        self.assertEqual(parsed["mcp_servers"]["filesystem"]["url"], f"{fake.url}/mcp/filesystem/")
        adds = [c for c in self.claude_calls if c[:2] == ["mcp", "add-json"]]
        self.assertEqual([c[4] for c in adds], SERVERS)
        entry = json.loads(adds[0][5])
        self.assertEqual((entry["type"], entry["headersHelper"]), ("http", helper))
        tokens = json.loads((self.tmp / "home" / "token.json").read_text(encoding="utf-8"))
        for secret in (tokens["access_token"], tokens["refresh_token"], "test-password"):
            self.assertNotIn(secret, first)
            self.assertFalse(any(secret in c[-1] for c in adds))
        # 같은 기기·같은 PC로 다시 실행하면 로그인을 이어 쓰고 블록만 바꾼다.
        self.claude_servers.update(SERVERS)
        self.main("setup", "--url", fake.url, "--servers", ",".join(SERVERS), "--workstation", "ysg-laptop")
        self.assertEqual(codex.read_text(encoding="utf-8"), first)
        self.assertEqual(fake.log.count("password"), 1)

    def test_conflicts_are_found_before_anything_is_written(self):
        self.claude_servers.add("git")
        with self.assertRaises(SystemExit):
            self.setup_against("https://mcp-gw.internal")
        self.assertFalse((self.tmp / "home").exists())
        self.assertFalse([c for c in self.claude_calls if c[:2] == ["mcp", "add-json"]])

    def test_concurrent_helpers_refresh_once_without_reuse(self):
        fake = FakeIdpGateway(access_seconds=61)  # 1초 뒤면 여유(60초) 안으로 들어와 갱신 대상이 된다
        self.addCleanup(fake.close)
        self.setup_against(fake.url, "--harness", "codex")
        time.sleep(1.5)
        home = os.environ["MCPGW_HOME"]
        env = {k: v for k, v in os.environ.items() if k != "MCPGW_HOME"}  # Codex는 환경을 비우고 헬퍼를 부른다
        helper = self.kit.helper_command()
        procs = [subprocess.Popen(helper, shell=True, env=env, stdout=subprocess.PIPE, text=True) for _ in SERVERS]
        headers = [json.loads(p.communicate(timeout=30)[0]) for p in procs]
        self.assertTrue(all(h["Authorization"].startswith("Bearer at_") for h in headers))
        self.assertNotIn("REUSE", fake.log)
        self.assertEqual(fake.log.count("refresh"), 1, fake.log)
        self.assertIn(str(Path(home)), helper)

    def test_doctor_and_uninstall_against_the_fake(self):
        fake = FakeIdpGateway()
        self.addCleanup(fake.close)
        codex = self.tmp / "codex" / "config.toml"
        self.setup_against(fake.url, "--harness", "codex")
        out = io.StringIO()  # 테스트 PATH에는 codex가 없어 그 한 줄만 FAIL
        with redirect_stdout(out), self.assertRaises(SystemExit):
            self.kit.main(["doctor"])
        lines = out.getvalue().splitlines()
        for server in SERVERS:
            self.assertIn(f"OK   MCP {server} initialize: HTTP 200", lines)
        self.assertIn("OK   헬퍼 명령(하네스가 실행하는 것)", lines)
        self.assertEqual([line for line in lines if line.startswith("FAIL")], ["FAIL Codex CLI 설치: npm install -g @openai/codex (0.148 이상)"])
        codex.write_text('model = "gpt-5"\n' + codex.read_text(encoding="utf-8"), encoding="utf-8")
        self.main("uninstall")
        self.assertEqual(codex.read_text(encoding="utf-8"), 'model = "gpt-5"\n')
        self.assertIn("revoke", fake.log)
        self.assertFalse(any((self.tmp / "home").iterdir()))

    def test_wrong_password_is_reported_and_nothing_is_registered(self):
        fake = FakeIdpGateway()
        self.addCleanup(fake.close)
        with self.assertRaises(SystemExit) as failed:
            self.main("setup", "--url", fake.url, "--servers", "git", "--email", "ysg@bob.local", "--password-stdin",
                      stdin="wrong\n")
        self.assertIn("합성 계정과 비밀번호", str(failed.exception.code))
        self.assertFalse([c for c in self.claude_calls if c[:2] == ["mcp", "add-json"]])

    def test_managed_files_carry_no_secret(self):
        out = self.tmp / "managed"
        self.main("managed", "--url", "https://mcp-gw.internal", "--servers", "git,filesystem", "--out", str(out),
                  "--python", "/usr/bin/python3", "--kit", "/opt/mcpgw/mcpgw_pc.py")
        claude = json.loads((out / "managed-mcp.json").read_text(encoding="utf-8"))
        self.assertEqual(claude["mcpServers"]["git"]["headersHelper"], '"/usr/bin/python3" "/opt/mcpgw/mcpgw_pc.py" header')
        requirements = tomllib.loads((out / "requirements.toml").read_text(encoding="utf-8"))
        self.assertEqual(requirements["mcp_servers"]["git"]["identity"], {"url": "https://mcp-gw.internal/mcp/git/"})

    def test_report_lists_vendor_connectors_and_applies_only_its_own_denies(self):
        fake = FakeIdpGateway()
        self.addCleanup(fake.close)
        # 실제 VM의 `claude mcp list` 모양(2.1.283). Gateway 서버 줄은 보고하지 않는다.
        self.claude_list = "\n".join([
            "Checking MCP server health…", "",
            "claude.ai Notion: https://mcp.notion.com/mcp - ✔ Connected",
            "claude.ai Claude Docs: https://api.anthropic.com/v1/pages/mcp - ✔ Connected",
            "plugin:engineering:slack: https://mcp.slack.com/mcp (HTTP) - ! Needs authentication",
            "plugin:engineering:gmail:  (HTTP) - - Not configured",
            "plugin:pdf-viewer:pdf: npx -y @modelcontextprotocol/server-pdf --stdio - ✔ Connected",
            "zapier: https://actions.zapier.com/mcp/sk-secret-path/sse (SSE) - ✘ Failed to connect",
            f"git: {fake.url}/mcp/git/ (HTTP) - ✔ Connected"])
        self.setup_against(fake.url, "--harness", "claude")
        items = {i["name"]: i for i in fake.reports[-1]["items"]}
        self.assertEqual(fake.reports[-1]["harnesses"], ["claude"])
        self.assertEqual(set(items), {"claude.ai Notion", "claude.ai Claude Docs", "plugin:engineering:slack",
                                      "plugin:engineering:gmail", "plugin:pdf-viewer:pdf", "zapier"})
        self.assertEqual((items["claude.ai Notion"]["kind"], items["claude.ai Notion"]["target"]), ("connector", "https://mcp.notion.com"))
        self.assertEqual((items["plugin:pdf-viewer:pdf"]["kind"], items["plugin:pdf-viewer:pdf"]["target"]), ("plugin", "stdio"))
        self.assertEqual((items["zapier"]["kind"], items["zapier"]["target"]), ("server", "https://actions.zapier.com"))
        self.assertNotIn("sk-secret", json.dumps(fake.reports[-1]))  # 경로에 든 키는 보내지 않는다
        # 거부가 오면 사용자 설정에 넣되, 직원이 직접 넣은 항목은 그대로 둔다.
        settings = self.tmp / "claude" / "settings.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps({"model": "sonnet", "deniedMcpServers": [{"serverName": "mine"}]}), encoding="utf-8")
        fake.denied["claude"] = [{"serverUrl": "*://mcp.notion.com/*"}, {"serverName": "claude.ai Notion"}]
        self.main("report")
        document = json.loads(settings.read_text(encoding="utf-8"))
        self.assertEqual(document["model"], "sonnet")
        self.assertEqual(document["deniedMcpServers"], [{"serverName": "mine"}] + fake.denied["claude"])
        fake.denied["claude"] = []  # 관리자가 되돌리면 이 도구가 넣은 것만 빠진다
        self.main("report")
        self.assertEqual(json.loads(settings.read_text(encoding="utf-8"))["deniedMcpServers"], [{"serverName": "mine"}])

    def test_codex_app_denies_live_in_the_block_and_leave_with_uninstall(self):
        codex = self.tmp / "codex" / "config.toml"
        self.kit.codex_config().parent.mkdir(parents=True)
        codex.write_text('model = "gpt-5"\n', encoding="utf-8")
        settings = {"url": "https://mcp-gw.internal", "servers": ["git"], "codex": True}
        self.kit.setup_codex(settings, False)
        self.assertIn("Codex 앱 끔 1건 · 기능 끔 1건", self.kit.apply_codex(settings, ["asdk_app_1", "bad id"], ["browser_use", "web_search"]))
        parsed = tomllib.loads(codex.read_text(encoding="utf-8"))
        self.assertEqual((parsed["model"], parsed["apps"]), ("gpt-5", {"asdk_app_1": {"enabled": False}}))
        self.assertEqual(parsed["features"], {"browser_use": False})  # 웹 검색은 루트 키라 블록에 두지 않는다
        # 직원이 [features]를 이미 쓰면 기능은 건너뛴다(TOML 중복 테이블 방지).
        codex.write_text('model = "gpt-5"\n[features]\nshell_tool = true\n', encoding="utf-8")
        self.assertIn("기능은 건너뜀", self.kit.apply_codex(settings, [], ["browser_use"]))
        self.assertEqual(tomllib.loads(codex.read_text(encoding="utf-8"))["features"], {"shell_tool": True})
        codex.write_text('model = "gpt-5"\n', encoding="utf-8")
        self.kit.remove_codex_block()
        self.assertEqual(codex.read_text(encoding="utf-8"), 'model = "gpt-5"\n')

    def test_header_starts_a_background_report_at_most_every_six_hours(self):
        (self.tmp / "home").mkdir(parents=True)
        spawned = []
        with mock.patch.object(self.kit.subprocess, "Popen", lambda command, **kw: spawned.append(command)):
            for _ in range(3):  # 하네스는 서버마다·연결마다 헬퍼를 부른다
                self.kit.report_in_background({"harnesses": ["claude"]})
            self.assertEqual(len(spawned), 1)
            self.assertEqual(spawned[0][-1], "report")
            stamp = self.tmp / "home" / "report.stamp"
            os.utime(stamp, (time.time() - self.kit.REPORT_EVERY - 1,) * 2)
            self.kit.report_in_background({"harnesses": ["claude"]})
            self.assertEqual(len(spawned), 2)

    def test_managed_files_take_the_console_connector_policy(self):
        policy = self.tmp / "connector-policy.json"
        policy.write_text(json.dumps({"claude": {"deniedMcpServers": [{"serverUrl": "*://mcp.notion.com/*"}], "allowAllClaudeAiMcps": True},
                                      "codex": {"apps_disabled": ["asdk_app_1"], "features_disabled": ["web_search", "browser_use"]}}),
                          encoding="utf-8")
        out = self.tmp / "managed"
        self.main("managed", "--url", "https://mcp-gw.internal", "--servers", "git", "--out", str(out),
                  "--python", "/usr/bin/python3", "--kit", "/opt/mcpgw/mcpgw_pc.py", "--connectors", str(policy))
        managed = json.loads((out / "managed-settings.json").read_text(encoding="utf-8"))
        self.assertEqual(managed["deniedMcpServers"], [{"serverUrl": "*://mcp.notion.com/*"}])
        self.assertIs(managed["allowAllClaudeAiMcps"], False)  # 이전의 관대한 정책도 강제 프로필을 넓히지 못한다.
        self.assertIs(managed["allowManagedMcpServersOnly"], True)
        self.assertEqual(managed["allowedMcpServers"], [{"serverUrl": "https://mcp-gw.internal/mcp/git/"}])
        self.assertEqual(managed["strictKnownMarketplaces"], [])
        requirements = tomllib.loads((out / "requirements.toml").read_text(encoding="utf-8"))
        self.assertEqual(requirements["allowed_web_search_modes"], ["disabled"])
        self.assertIs(requirements["allow_browser_and_computer_use"], False)
        self.assertEqual(requirements["features"], {"apps": False, "plugins": False, "browser_use": False, "computer_use": False})
        self.assertIs(requirements["marketplaces"]["restrict_to_allowed_sources"], True)
        self.assertEqual(requirements["apps"], {"asdk_app_1": {"enabled": False}})
        self.assertEqual(requirements["mcp_servers"]["git"]["identity"], {"url": "https://mcp-gw.internal/mcp/git/"})

    def test_kit_parses_as_python_3_9(self):
        ast.parse(KIT.read_text(encoding="utf-8"), feature_version=(3, 9))


class OverlayTest(unittest.TestCase):
    def test_caddyfile_routes(self):
        lines = (LAB / "field" / "Caddyfile").read_text(encoding="utf-8").splitlines()
        text = "\n".join(line for line in lines if not line.lstrip().startswith("#"))
        self.assertIn("http://:8080", text)
        self.assertNotIn("tls internal", text)
        self.assertIn("admin off", text)
        self.assertNotIn("handle_path", text)  # Gateway가 /mcp/<server>/ 경로 그대로에서 서버를 고른다
        self.assertRegex(text, r"handle /mcp/\* \{\s*reverse_proxy gateway:8080")
        self.assertRegex(text, r"handle /api/health \{\s*reverse_proxy gateway:8080")
        self.assertRegex(text, r"handle /oauth/\* \{\s*reverse_proxy agent-service:8000")
        # D-48: Gitea 페이지는 솔루션 로그인을 거친다. 순서가 곧 통제다 — 클라이언트가 보낸 신원 헤더를
        # 지우고, 인증하고, Authorization을 지운 뒤에야 Gitea로 간다.
        git = re.search(r"handle /git/\* \{\s*route \{(.*?)\n\t\t\}", text, re.S)
        self.assertIsNotNone(git, "/git/* 는 route 블록이어야 한다(적힌 순서대로 실행)")
        steps = [line.strip().split(" {")[0] for line in git.group(1).splitlines()
                 if line.startswith("\t\t\t") and not line.startswith("\t\t\t\t") and line.strip() not in {"", "}"}]
        self.assertEqual(steps, ["request_header -X-WEBAUTH-USER", "forward_auth agent-service:8000",
                                 "request_header -Authorization", "uri strip_prefix /git", "reverse_proxy corp-git:3000"])
        self.assertIn("uri /auth/gitea", git.group(1))
        self.assertIn("copy_headers X-WEBAUTH-USER", git.group(1))

    def test_mcp_facade_accepts_only_the_configured_public_host(self):
        # Caddy는 Host를 그대로 넘긴다. DNS 리바인딩 방어는 두고 배포자가 정한 공개 이름만 더한다(D-43).
        text = (LAB / "gateway" / "app" / "mcp_facade.py").read_text(encoding="utf-8")
        self.assertIn('urlsplit(os.getenv("GATEWAY_PUBLIC_MCP_URL", "")).hostname', text)
        self.assertIn('"gateway:*", "gateway-sse:*", "localhost:*", "127.0.0.1:*"', text)

    def test_experiments_use_the_internal_idp_address(self):
        text = (LAB / "gateway" / "app" / "experiments.py").read_text(encoding="utf-8")
        self.assertIn('os.getenv("IDP_INTERNAL_URL")', text)

    @unittest.skipUnless(shutil.which("docker"), "docker CLI 없음")
    def test_overlay_publishes_only_caddy_on_the_tailnet_address(self):
        env = {**os.environ, "APPLIANCE_BIND": "100.83.175.111",
               "AGENT_JWT_PRIVATE_KEY": "x", "AGENT_JWT_PUBLIC_KEY": "x", "LITELLM_MASTER_KEY": "x"}
        command = ["docker", "compose", "--project-directory", str(LAB), "-f", str(LAB / "compose.yaml"),
                   "-f", str(LAB / "compose.field.yaml"), "config", "--format", "json"]
        rendered = json.loads(subprocess.run(command, env=env, capture_output=True, encoding="utf-8", check=True).stdout)
        services = rendered["services"]
        published = {(name, p.get("host_ip")) for name, svc in services.items() for p in svc.get("ports", [])}
        self.assertIn(("caddy", "100.83.175.111"), published)
        self.assertEqual({ip for name, ip in published if name != "caddy"}, {"127.0.0.1"})
        self.assertFalse([name for name in services if name.startswith("ws-")])  # 실제 PC가 대신한다
        self.assertEqual(services["gateway"]["environment"]["IDP_INTERNAL_URL"], "http://agent-service:8000")
        # D-48: Gitea가 믿는 프록시는 Caddy의 고정 주소 하나뿐이고, 모르는 사용자를 자동으로 만들지 않는다.
        caddy_ip = services["caddy"]["networks"]["edge"]["ipv4_address"]
        gitea = services["corp-git"]["environment"]
        self.assertEqual(gitea["GITEA__security__REVERSE_PROXY_TRUSTED_PROXIES"], caddy_ip + "/32")
        self.assertEqual(gitea["GITEA__service__ENABLE_REVERSE_PROXY_AUTO_REGISTRATION"], "false")
        self.assertEqual(gitea["GITEA__service__REQUIRE_SIGNIN_VIEW"], "true")
        missing = {k: v for k, v in env.items() if k != "APPLIANCE_BIND"}
        self.assertNotEqual(subprocess.run(command, env=missing, capture_output=True).returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
