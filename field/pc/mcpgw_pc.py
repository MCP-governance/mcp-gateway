#!/usr/bin/env python3
"""mcpgw_pc: 직원 PC의 Claude Code·Codex CLI를 솔루션 기기의 Agent Service(MCP)에 연결한다.

    python mcpgw_pc.py setup --url https://mcp-gw.internal --ca mcp-gw-root.crt
    python mcpgw_pc.py login         # 다시 로그인(브라우저에서 코드 확인 - OAuth 2.0 Device Authorization Grant)
    python mcpgw_pc.py doctor        # 이름 해석·TLS·로그인·서버별 연결·하네스 설정을 한 줄씩 확인
    python mcpgw_pc.py uninstall     # 이 도구가 쓴 설정만 지우고 Keycloak의 리프레시 토큰을 폐기
    python mcpgw_pc.py managed --url ... --out DIR --python ... --kit ...   # 관리자 강제 배포용 파일 생성

직원은 Keycloak에 브라우저로 로그인하고(device flow - 비밀번호가 이 도구를 거치지 않는다), 이 도구는
리프레시 토큰으로 짧은 접근 토큰을 갱신한다. 두 하네스는 연결할 때마다 이 도구의 `header`를 실행하고
(Claude Code `headersHelper`, Codex CLI 0.148+ `http_headers_helper`), 401을 받으면 다시 부른다. 토큰은 하네스
설정 파일에 들어가지 않는다. 표준 라이브러리만 쓴다(Python 3.9+).
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

TOOL = "mcpgw_pc.py"
# Agent Service의 MCP 경로 이름(/mcp/<이름>).
SERVER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
BEGIN = "# >>> mcp-gateway (mcpgw_pc.py) >>>"
END = "# <<< mcp-gateway (mcpgw_pc.py) <<<"
# Keycloak 접근 토큰은 기본 5분. 만료 1분 전부터 새로 받는다.
LEEWAY_SECONDS = 60


def home() -> Path:
    return Path(os.environ.get("MCPGW_HOME") or Path.home() / ".mcpgw")


def codex_config() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "config.toml"


def fail(message: str) -> None:
    sys.exit(f"{TOOL}: {message}")


# -- 입력 검증 -----------------------------------------------------------------

def gateway_url(value: str) -> str:
    """https만 받는다. 예외는 SSH 포트 포워딩(ssh -L)으로 연 loopback 주소뿐이다."""
    parts = urllib.parse.urlsplit(value.strip())
    if parts.username or parts.password or parts.query or parts.fragment or not parts.hostname:
        fail("주소에는 호스트만 적는다(자격·쿼리·조각 금지): https://mcp-gw.internal")
    if parts.scheme != "https":
        loopback = parts.hostname == "localhost"
        try:
            loopback = loopback or ipaddress.ip_address(parts.hostname).is_loopback
        except ValueError:
            pass
        if parts.scheme != "http" or not loopback:
            fail("사내망 주소는 https:// 만 쓴다. 평문 http는 SSH 포트 포워딩한 127.0.0.1에서만 허용한다")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def server_names(value: str) -> list[str]:
    names = [name.strip() for name in value.split(",") if name.strip()]
    if not names or any(not SERVER_NAME.fullmatch(name) for name in names):
        fail("--servers는 Agent Service의 MCP 경로 이름을 쉼표로(기본 demo)")
    return sorted(set(names))


def endpoint(settings: dict, server: str) -> str:
    # Agent Service의 라우트는 끝에 /가 없다(/mcp/demo). /를 붙이면 리다이렉트가 되어 POST가 이어지지 않는다.
    return f"{settings['url']}/mcp/{server}"


def oidc(settings: dict, path: str) -> str:
    return f"{settings['url']}/realms/{settings['realm']}/protocol/openid-connect/{path}"


def pem_fingerprint(path: Path) -> str:
    """관리자가 README 절차대로 알려준 지문과 대조하라고 보여 준다(SHA-256, DER 기준)."""
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    blocks = re.findall(r"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----", text, re.S)
    if not blocks:
        fail(f"{path}: PEM 인증서가 아니다(-----BEGIN CERTIFICATE----- 없음)")
    digest = hashlib.sha256(ssl.PEM_cert_to_DER_cert(blocks[0])).hexdigest().upper()
    return ":".join(digest[i:i + 2] for i in range(0, len(digest), 2))


# -- 상태 파일(~/.mcpgw) --------------------------------------------------------

def load_settings() -> dict:
    path = home() / "config.json"
    if not path.exists():
        fail("설정이 없다. 먼저 setup을 실행한다")
    return json.loads(path.read_text(encoding="utf-8"))


def write_private(path: Path, text: str) -> None:
    # POSIX는 0600. Windows는 사용자 프로필 폴더의 기본 ACL(본인·SYSTEM·Administrators)을 따른다.
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(text)
    if os.name != "nt":
        os.chmod(path, 0o600)


class Lock:
    """하네스는 서버마다 헬퍼를 동시에 부른다. Keycloak에 리프레시 토큰 회전·재사용 폐기(Revoke Refresh
    Token)가 켜져 있으면 동시에 갱신한 쪽이 옛 토큰을 다시 쓴 것이 되므로, 한 번에 한 프로세스만 갱신한다."""

    def __init__(self, path: Path, timeout: float = 8.0):
        self.path, self.timeout, self.handle = path, timeout, None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = open(self.path, "a+b")
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    self.handle.seek(0)
                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except OSError:
                if time.monotonic() > deadline:
                    self.handle.close()
                    fail("다른 하네스가 토큰을 갱신하는 중에 시간이 넘었다. 다시 시도한다")
                time.sleep(0.05)

    def __exit__(self, *exc):
        try:
            if os.name == "nt":
                import msvcrt
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle, fcntl.LOCK_UN)
        finally:
            self.handle.close()


# -- IdP -------------------------------------------------------------------------

def tls_context(settings: dict) -> ssl.SSLContext | None:
    if not settings["url"].startswith("https://"):
        return None
    context = ssl.create_default_context()
    if settings.get("ca"):
        context.load_verify_locations(cafile=settings["ca"])
    return context


def request(settings: dict, url: str, *, data: bytes | None = None, headers: dict | None = None,
            method: str | None = None, timeout: float = 8) -> tuple[int, bytes, dict]:
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    # 시스템 프록시를 거치지 않는다 - 사내망 기기에 곧바로 붙어야 한다.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                         urllib.request.HTTPSHandler(context=tls_context(settings)))
    try:
        with opener.open(req, timeout=timeout) as response:
            return response.status, response.read(65536), dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, error.read(65536), dict(error.headers)


def post_form(settings: dict, url: str, fields: dict) -> tuple[int, dict]:
    body = urllib.parse.urlencode(fields).encode()
    status, data, _ = request(settings, url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        return status, json.loads(data or b"{}")
    except ValueError:
        return status, {}


def save_tokens(data: dict, previous: dict) -> dict:
    now = time.time()
    tokens = {"access_token": data["access_token"],
              "refresh_token": data.get("refresh_token") or previous.get("refresh_token"),
              "expires_at": now + int(data.get("expires_in", 300))}
    if data.get("refresh_expires_in"):
        tokens["refresh_expires_at"] = now + int(data["refresh_expires_in"])
    write_private(home() / "token.json", json.dumps(tokens))
    return tokens


def cached_tokens() -> dict:
    path = home() / "token.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except ValueError:
        return {}


def device_login(settings: dict, open_browser: bool) -> dict:
    """RFC 8628. 직원은 브라우저에서 Keycloak에 로그인하고 코드를 확인한다(임시 비밀번호 변경도 거기서)."""
    status, auth = post_form(settings, oidc(settings, "auth/device"), {"client_id": settings["client"]})
    if status != 200 or "device_code" not in auth:
        fail(f"장치 코드를 받지 못했다(HTTP {status} {auth.get('error_description') or auth.get('error') or ''}). "
             f"realm의 {settings['client']} 클라이언트에 Device Authorization Grant가 켜져 있는지 관리자에게 묻는다")
    link = auth.get("verification_uri_complete") or auth["verification_uri"]
    print(f"브라우저에서 이 주소를 열고 회사 계정으로 로그인한다: {link}")
    print(f"  화면의 코드가 {auth['user_code']} 인지 확인한다")
    if open_browser:
        webbrowser.open(link)
    interval = float(auth.get("interval", 5))
    deadline = time.monotonic() + float(auth.get("expires_in", 600))
    while time.monotonic() < deadline:
        time.sleep(interval)
        status, data = post_form(settings, oidc(settings, "token"), {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": auth["device_code"], "client_id": settings["client"]})
        if status == 200 and "access_token" in data:
            return data
        if data.get("error") == "authorization_pending":
            continue
        if data.get("error") == "slow_down":
            interval += 5
            continue
        fail(f"로그인하지 못했다({data.get('error_description') or data.get('error') or status})")
    fail("로그인 코드가 만료됐다. login을 다시 실행한다")


def password_login(settings: dict, username: str | None) -> dict:
    """자동화(CI) 전용: 그 클라이언트에 Direct Access Grants가 켜져 있어야 한다. 직원 PC는 device flow를 쓴다."""
    username = username or input("사용자 이름: ").strip()
    password = sys.stdin.readline().rstrip("\r\n")
    status, data = post_form(settings, oidc(settings, "token"), {
        "grant_type": "password", "client_id": settings["client"], "username": username, "password": password})
    if status != 200 or "access_token" not in data:
        fail(f"로그인하지 못했다({data.get('error_description') or data.get('error') or status})")
    return data


def login(settings: dict, username: str | None = None, password_stdin: bool = False, open_browser: bool = True) -> None:
    data = password_login(settings, username) if password_stdin else device_login(settings, open_browser)
    with Lock(home() / "token.lock"):
        save_tokens(data, {})
    print(f"로그인했다(realm {settings['realm']}, 클라이언트 {settings['client']}). 비밀번호는 이 PC에 저장하지 않았다")


def access_token(settings: dict) -> str:
    """헬퍼용: 절대 묻지 않는다(하네스는 10초 안에 헤더를 받아야 하고 입력 창이 없다)."""
    with Lock(home() / "token.lock"):
        tokens = cached_tokens()
        if tokens.get("access_token") and time.time() < tokens.get("expires_at", 0) - LEEWAY_SECONDS:
            return tokens["access_token"]
        data = None
        if tokens.get("refresh_token"):
            status, data = post_form(settings, oidc(settings, "token"), {
                "grant_type": "refresh_token", "refresh_token": tokens["refresh_token"], "client_id": settings["client"]})
            data = data if status == 200 and "access_token" in data else None
        if data is None:
            fail(f"로그인이 필요하다(세션 만료 등): python \"{home() / TOOL}\" login")
        return save_tokens(data, tokens)["access_token"]


def helper_command() -> str:
    """두 하네스가 셸(Windows cmd /C, 그 밖 sh -c)로 실행하는 한 줄.

    Codex는 헬퍼를 환경 변수를 비우고 실행하므로(MCP 서버와 같은 허용 목록만 넘김) 토큰이 있는 폴더를
    --home으로 명령에 싣는다. 경로마다 따옴표를 쳐서 공백·한글 경로도 한 인자로 간다.
    """
    return f'"{sys.executable}" "{home() / TOOL}" --home "{home()}" header'


# -- Claude Code: 공식 CLI로 사용자 범위에 추가 --------------------------------

def claude_entry(settings: dict, server: str) -> dict:
    return {"type": "http", "url": endpoint(settings, server), "headersHelper": helper_command(), "timeout": 300000}


def run(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)


def claude_exists(claude: str, server: str) -> bool:
    return run([claude, "mcp", "get", server]).returncode == 0


def preflight(settings: dict, previous: list[str], replace: bool) -> None:
    """무엇이든 쓰기 전에 충돌을 모두 본다. 중간에 멈춰 반쯤 쓴 상태를 남기지 않게."""
    claude = shutil.which("claude")
    if "claude" in settings["harnesses"] and claude and not replace:
        # 직원이 직접 만든 같은 이름의 서버를 말없이 덮어쓰지 않는다.
        mine = [s for s in settings["servers"] if s not in previous and claude_exists(claude, s)]
        if mine:
            fail(f"Claude Code에 이미 '{mine[0]}' 서버가 있다. 지우거나 --replace로 덮어쓴다")
    if "codex" in settings["harnesses"]:
        path = codex_config()
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        clash = codex_conflicts(without_block(current), settings["servers"])
        if clash:
            fail(f"{path}에 이미 [mcp_servers.{clash[0]}]가 있다. 그 테이블을 지우고 다시 실행한다")


def setup_claude(settings: dict, dry_run: bool) -> list[str]:
    claude = shutil.which("claude")
    commands = [["claude", "mcp", "add-json", "--scope", "user", s, json.dumps(claude_entry(settings, s))]
                for s in settings["servers"]]
    if dry_run or not claude:
        if not claude and not dry_run:
            print("  Claude Code가 PATH에 없다. 설치한 뒤 setup을 다시 실행한다. 쓸 명령:")
        for command in commands:
            print("  " + subprocess.list2cmdline(command))
        return []
    added = []
    for server, command in zip(settings["servers"], commands):
        if claude_exists(claude, server):
            run([claude, "mcp", "remove", "--scope", "user", server])
        result = run([claude] + command[1:])
        if result.returncode != 0:
            fail(f"claude mcp add-json {server} 실패: {(result.stderr or result.stdout).strip()}")
        added.append(server)
        print(f"  Claude Code(user): {server} -> {endpoint(settings, server)}")
    return added


# -- Codex CLI: config.toml 끝의 표식 블록만 관리 -------------------------------

def without_block(text: str) -> str:
    pattern = re.compile(r"\n?" + re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", re.S)
    kept = pattern.sub("\n", text).rstrip("\n")
    return kept + "\n" if kept.strip() else ""


def with_block(text: str, block: str) -> str:
    # 블록은 항상 파일 끝에 둔다. TOML에서 앞에 두면 뒤따르는 사용자의 루트 키가 우리 테이블 안으로 들어간다.
    rest = without_block(text)
    return rest + ("\n" if rest else "") + block


def codex_block(settings: dict) -> str:
    lines = [BEGIN, f"# {TOOL} setup이 다시 쓴다. 이 블록 아래에 루트 키(model = ... 등)를 두지 않는다."]
    for server in settings["servers"]:
        # JSON 문자열은 TOML 기본 문자열로도 유효하다(따옴표·역슬래시 이스케이프가 같다).
        lines += ["", f"[mcp_servers.{server}]", f'url = "{endpoint(settings, server)}"',
                  f"http_headers_helper = {json.dumps(helper_command(), ensure_ascii=False)}",
                  "startup_timeout_sec = 30", "tool_timeout_sec = 300"]
    return "\n".join(lines + [END]) + "\n"


def codex_conflicts(text: str, servers: list[str]) -> list[str]:
    """블록 밖에서 직원이 이미 정의한 같은 이름 - 그대로 두면 TOML 중복 테이블이 된다."""
    try:
        import tomllib
        existing = tomllib.loads(text).get("mcp_servers", {})
        return [s for s in servers if s in existing]
    except ImportError:  # Python 3.10 이하
        return [s for s in servers if re.search(r"^\s*\[mcp_servers\.(\"?)" + re.escape(s) + r"\1\]", text, re.M)]


def setup_codex(settings: dict, dry_run: bool) -> bool:
    path = codex_config()
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if dry_run:
        print(f"  --- {path} 끝에 둘 블록 ---\n{codex_block(settings)}")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(with_block(current, codex_block(settings)), encoding="utf-8")
    print(f"  Codex CLI: {path} ({', '.join(settings['servers'])})")
    return True


def remove_codex_block() -> None:
    config = codex_config()
    if config.exists() and BEGIN in config.read_text(encoding="utf-8"):
        config.write_text(without_block(config.read_text(encoding="utf-8")), encoding="utf-8")
        print(f"블록 지움: {config}")


# -- 명령 -----------------------------------------------------------------------

def cmd_setup(args) -> None:
    settings = {"url": gateway_url(args.url), "servers": server_names(args.servers),
                "realm": args.realm, "client": args.client,
                "harnesses": sorted({h.strip() for h in args.harness.split(",") if h.strip()})}
    unknown = set(settings["harnesses"]) - {"claude", "codex"}
    if unknown:
        fail(f"--harness는 claude,codex 중에서: {', '.join(sorted(unknown))}")
    root = home()
    previous = {}
    if (root / "config.json").exists():
        previous = json.loads((root / "config.json").read_text(encoding="utf-8"))
    if args.ca:
        print(f"CA 지문(SHA-256): {pem_fingerprint(Path(args.ca))}")
        print("  관리자가 알려 준 지문과 같은지 확인한다. 다르면 멈추고 관리자에게 묻는다")
        settings["ca"] = str(root / "ca.crt")
    elif previous.get("ca"):
        settings["ca"] = previous["ca"]
    preflight(settings, previous.get("claude_servers", []), args.replace)
    if args.dry_run:
        print("[dry-run] 아무 것도 쓰지 않는다")
    else:
        root.mkdir(parents=True, exist_ok=True)
        if args.ca and Path(args.ca).resolve() != (root / "ca.crt").resolve():
            shutil.copyfile(args.ca, root / "ca.crt")
        # 헬퍼가 가리킬 고정 위치(내려받은 폴더를 지워도 동작하게).
        if Path(__file__).resolve() != (root / TOOL).resolve():
            shutil.copyfile(__file__, root / TOOL)
        (root / "config.json").write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # 하네스 설정을 쓰기 전에 로그인이 되는지 먼저 본다. 같은 기기·realm이면 이전 로그인을 이어 쓴다.
        same = all(previous.get(k) == settings[k] for k in ("url", "realm", "client"))
        if not (same and cached_tokens().get("refresh_token")) or args.password_stdin:
            login(settings, args.username, args.password_stdin, not args.no_browser)
    if "claude" in settings["harnesses"]:
        settings["claude_servers"] = setup_claude(settings, args.dry_run)
    if "codex" in settings["harnesses"]:
        settings["codex"] = setup_codex(settings, args.dry_run)
    elif previous.get("codex") and not args.dry_run:
        remove_codex_block()
    if not args.dry_run:
        # 이전 setup에만 있던 Claude 서버는 지운다(서버 목록을 줄였을 때).
        stale = set(previous.get("claude_servers", [])) - set(settings.get("claude_servers", []))
        claude = shutil.which("claude")
        for server in sorted(stale):
            if claude:
                run([claude, "mcp", "remove", "--scope", "user", server])
        (root / "config.json").write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"완료. 확인: python \"{root / TOOL}\" doctor")


def cmd_login(args) -> None:
    login(load_settings(), args.username, args.password_stdin, not args.no_browser)


def cmd_token(args) -> None:
    print(access_token(load_settings()))


def cmd_header(args) -> None:
    print(json.dumps({"Authorization": f"Bearer {access_token(load_settings())}"}))


INITIALIZE = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
    "protocolVersion": "2025-11-25", "capabilities": {},
    "clientInfo": {"name": "mcpgw-pc-doctor", "version": "1"}}}).encode()
HINTS = {401: "토큰이 거부됨(issuer·audience 불일치 또는 만료). login으로 다시 로그인하고 안 되면 관리자에게",
         403: "역할이 부족함. 관리자에게 묻는다", 404: "Agent Service에 없는 MCP 경로",
         502: "Agent Service가 MCP Gateway·서버에 닿지 못함"}


def cmd_doctor(args) -> None:
    settings = load_settings()
    failures = 0

    def report(ok: bool, what: str, detail: str = "") -> None:
        nonlocal failures
        failures += not ok
        print(f"{'OK  ' if ok else 'FAIL'} {what}{': ' + detail if detail else ''}")

    parts = urllib.parse.urlsplit(settings["url"])
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        addresses = sorted({info[4][0] for info in socket.getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)})
        report(True, f"이름 해석 {parts.hostname}", ", ".join(addresses))
    except OSError as error:
        report(False, f"이름 해석 {parts.hostname}", f"{error}. 사내 DNS 또는 hosts 파일에 기기 IP를 적는다")
        sys.exit(1)
    if settings.get("ca"):
        report(Path(settings["ca"]).exists(), "CA 파일", f"{settings['ca']} {pem_fingerprint(Path(settings['ca']))}")
    try:
        status, body, _ = request(settings, f"{settings['url']}/realms/{settings['realm']}/.well-known/openid-configuration")
        issuer = json.loads(body).get("issuer") if status == 200 else None
        expected = f"{settings['url']}/realms/{settings['realm']}"
        report(issuer == expected, "TLS와 Keycloak issuer", (issuer or f"HTTP {status}")
               + ("" if issuer in (None, expected) else f" (기대값 {expected}: 기기의 KC_HOSTNAME·APPLIANCE_HOST 확인)"))
    except (urllib.error.URLError, OSError) as error:
        reason = getattr(error, "reason", error)
        if isinstance(reason, ssl.SSLError):
            report(False, "TLS", f"{getattr(reason, 'reason', None) or reason}. 기기의 루트 인증서를 setup --ca로 지정한다")
        else:
            report(False, "솔루션 기기 도달", f"{reason}. 기기의 443 방화벽과 게시 주소(APPLIANCE_BIND)를 확인한다")
        sys.exit(1)
    try:
        token = access_token(settings)
        report(True, "로그인(접근 토큰)", f"realm {settings['realm']}")
    except SystemExit as error:
        report(False, "로그인(접근 토큰)", str(error.code))
        token = ""
    for server in settings["servers"] if token else []:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream"}
        status, body, response_headers = request(settings, endpoint(settings, server), data=INITIALIZE, headers=headers,
                                                 timeout=30)
        report(status == 200 and b"jsonrpc" in body, f"MCP {server} initialize", f"HTTP {status} {HINTS.get(status, '')}".strip())
        session = {k.lower(): v for k, v in response_headers.items()}.get("mcp-session-id")
        if status == 200 and session:
            # 확인용 세션을 닫는다. 실패해도 문제 삼지 않는다.
            try:
                request(settings, endpoint(settings, server), method="DELETE",
                        headers={"Authorization": headers["Authorization"], "Mcp-Session-Id": session})
            except OSError:
                pass
    if "claude" in settings.get("harnesses", []):
        claude = shutil.which("claude")
        report(bool(claude), "Claude Code 설치", claude or "https://code.claude.com/docs 의 설치 명령")
        for server in settings.get("claude_servers", []) if claude else []:
            report(claude_exists(claude, server), f"Claude Code 설정 {server}", "claude mcp get " + server)
    if "codex" in settings.get("harnesses", []):
        codex = shutil.which("codex")
        report(bool(codex), "Codex CLI 설치", codex or "npm install -g @openai/codex (0.148 이상)")
        text = codex_config().read_text(encoding="utf-8") if codex_config().exists() else ""
        report(BEGIN in text, "Codex 설정 블록", str(codex_config()))
    helper = subprocess.run(helper_command(), shell=True, capture_output=True, text=True, timeout=15)
    try:
        report(helper.returncode == 0 and "Authorization" in json.loads(helper.stdout), "헬퍼 명령(하네스가 실행하는 것)")
    except ValueError:
        report(False, "헬퍼 명령(하네스가 실행하는 것)", f"종료 코드 {helper.returncode}")
    sys.exit(1 if failures else 0)


def cmd_uninstall(args) -> None:
    root = home()
    settings = json.loads((root / "config.json").read_text(encoding="utf-8")) if (root / "config.json").exists() else {}
    claude = shutil.which("claude")
    for server in settings.get("claude_servers", []):
        if claude:
            result = run([claude, "mcp", "remove", "--scope", "user", server])
            print(f"Claude Code {server}: {'지움' if result.returncode == 0 else '이미 없음'}")
    remove_codex_block()
    refresh = cached_tokens().get("refresh_token")
    if settings.get("url") and refresh:
        # RFC 7009: 이 PC의 Keycloak 세션을 끝낸다. 200은 처리 사실만 뜻하므로 결과를 단정하지 않는다.
        try:
            status, _ = post_form(settings, oidc(settings, "revoke"),
                                  {"token": refresh, "token_type_hint": "refresh_token", "client_id": settings["client"]})
            print(f"Keycloak 리프레시 토큰 폐기 요청: HTTP {status}")
        except OSError as error:
            print(f"Keycloak에 닿지 못해 폐기 요청을 못 했다({error}). 관리자가 Keycloak에서 이 사용자의 세션을 끝낸다")
    for name in ("token.json", "token.lock", "ca.crt", "config.json", TOOL):
        if (root / name).exists():
            (root / name).unlink()
    print(f"지움: {root} 의 토큰·CA·설정. OS 인증서 저장소의 CA와 hosts 항목은 README 절차대로 따로 지운다")


def cmd_managed(args) -> None:
    """MDM·그룹 정책으로 PC에 둘 관리형 파일. 직원은 목록 밖의 서버를 더하지 못한다.

    모든 사용자가 읽는 파일이라 토큰을 넣지 않고, 각 사용자가 자기 홈의 토큰을 쓰도록 헬퍼를 가리킨다.
    그래서 키트와 파이썬이 모든 PC에서 같은 경로에 있어야 한다(--kit, --python).
    """
    settings = {"url": gateway_url(args.url), "servers": server_names(args.servers)}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    helper = f'"{args.python}" "{args.kit}" header'
    claude = {"mcpServers": {s: {"type": "http", "url": endpoint(settings, s), "headersHelper": helper, "timeout": 300000}
                             for s in settings["servers"]}}
    (out / "managed-mcp.json").write_text(json.dumps(claude, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Codex requirements.toml: 목록에 없는 MCP 서버는 켜지지 않는다(이름과 URL이 모두 맞아야 함)."]
    for server in settings["servers"]:
        lines += ["", f"[mcp_servers.{server}]", f'identity = {{ url = "{endpoint(settings, server)}" }}']
    (out / "requirements.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{out / 'managed-mcp.json'} -> macOS /Library/Application Support/ClaudeCode/, "
          "Linux /etc/claude-code/, Windows C:\\Program Files\\ClaudeCode\\")
    print(f"{out / 'requirements.toml'} -> Unix /etc/codex/, Windows %ProgramData%\\OpenAI\\Codex\\")
    print(f"각 PC에 키트를 {args.kit}에 두고, 직원은 setup --harness codex로 로그인·Codex 설정을 한다")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog=TOOL, description=__doc__.split("\n")[0])
    parser.add_argument("--home", help=argparse.SUPPRESS)  # 헬퍼 명령이 토큰 폴더를 알려 줄 때
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("setup", help="브라우저로 로그인하고 하네스 설정을 기록")
    setup.add_argument("--url", required=True, help="솔루션 기기 주소, 예: https://mcp-gw.internal")
    setup.add_argument("--servers", default="demo", help="MCP 경로 이름, 쉼표로(기본 demo)")
    setup.add_argument("--realm", default="mcp", help="Keycloak realm(기본 mcp)")
    setup.add_argument("--client", default="mcp-cli", help="Keycloak 클라이언트(기본 mcp-cli, device flow)")
    setup.add_argument("--ca", help="관리자가 준 루트 인증서(PEM)")
    setup.add_argument("--harness", default="claude,codex", help="claude,codex 중 연결할 것")
    setup.add_argument("--no-browser", action="store_true", help="로그인 주소를 브라우저로 열지 않는다")
    setup.add_argument("--username", help=argparse.SUPPRESS)  # 자동화 전용(--password-stdin과 함께)
    setup.add_argument("--password-stdin", action="store_true", help=argparse.SUPPRESS)
    setup.add_argument("--replace", action="store_true", help="Claude Code의 같은 이름 서버를 덮어쓴다")
    setup.add_argument("--dry-run", action="store_true", help="쓸 내용만 보여 준다")
    setup.set_defaults(run=cmd_setup)
    login_parser = commands.add_parser("login", help="다시 로그인(브라우저)")
    login_parser.add_argument("--no-browser", action="store_true")
    login_parser.add_argument("--username", help=argparse.SUPPRESS)
    login_parser.add_argument("--password-stdin", action="store_true", help=argparse.SUPPRESS)
    login_parser.set_defaults(run=cmd_login)
    commands.add_parser("token", help="접근 토큰(다른 클라이언트에 넣을 때)").set_defaults(run=cmd_token)
    commands.add_parser("header", help="하네스 헤더 헬퍼 출력").set_defaults(run=cmd_header)
    commands.add_parser("doctor", help="연결 점검").set_defaults(run=cmd_doctor)
    commands.add_parser("uninstall", help="이 도구가 쓴 설정 제거와 세션 폐기").set_defaults(run=cmd_uninstall)
    managed = commands.add_parser("managed", help="관리자 강제 배포 파일 생성")
    managed.add_argument("--url", required=True)
    managed.add_argument("--servers", default="demo")
    managed.add_argument("--out", required=True)
    managed.add_argument("--python", required=True, help="모든 PC에서 같은 파이썬 경로")
    managed.add_argument("--kit", required=True, help="모든 PC에서 같은 이 키트의 경로")
    managed.set_defaults(run=cmd_managed)
    # 파이프로 받으면 Windows는 로캘 인코딩(CP949 등)으로 쓴다. 표시 못 하는 글자 때문에 점검이 죽지 않게.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    args = parser.parse_args(argv)
    if args.home:
        os.environ["MCPGW_HOME"] = args.home
    args.run(args)


if __name__ == "__main__":
    main()
