#!/usr/bin/env python3
"""mcpgw_pc: 직원 PC의 Claude Code·Codex CLI를 솔루션 기기의 거버넌스 Gateway에 연결한다.

    python mcpgw_pc.py setup --url http://100.83.175.111:443 --servers filesystem,git
    python mcpgw_pc.py login         # 다시 로그인(리프레시 토큰이 만료·폐기됐을 때)
    python mcpgw_pc.py doctor        # 이름 해석·TLS·로그인·서버별 연결·하네스 설정을 한 줄씩 확인
    python mcpgw_pc.py report        # 하네스 기본 커넥터·기능을 보고하고 관리자가 거부한 것을 끈다(D-51)
    python mcpgw_pc.py uninstall     # 이 도구가 쓴 설정만 지우고 IdP의 리프레시 토큰을 폐기
    python mcpgw_pc.py managed --url ... --servers ... --out DIR [--connectors connector-policy.json]

랩 컨테이너의 `workstation/bin/bob-sso`와 같은 일을 실제 PC에서 한다: 회사 IdP(`/oauth/token`)에 password grant로
한 번 로그인하고, 리프레시 토큰으로 10분짜리 접근 토큰을 갱신한다. 두 하네스는 연결할 때마다 이 도구의 `header`를
실행하고(Claude Code `headersHelper`, Codex CLI 0.148+ `http_headers_helper`), 401을 받으면 다시 부른다. 비밀번호와
토큰은 하네스 설정 파일에 들어가지 않는다. bob-sso는 fcntl을 써서 Windows에서 돌지 않으므로 잠금을 따로 둔다.
표준 라이브러리만 쓴다(Python 3.9+).
"""
from __future__ import annotations

import argparse
import getpass
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
from pathlib import Path

TOOL = "mcpgw_pc.py"
# 레지스트리 서버 이름 규칙(registry/catalog.toml의 테이블 이름).
SERVER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
BEGIN = "# >>> mcp-gateway (mcpgw_pc.py) >>>"
END = "# <<< mcp-gateway (mcpgw_pc.py) <<<"
# IdP의 접근 토큰은 10분. 만료 1분 전부터 새로 받는다(bob-sso와 같음).
LEEWAY_SECONDS = 60


def home() -> Path:
    return Path(os.environ.get("MCPGW_HOME") or Path.home() / ".mcpgw")


def codex_config() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "config.toml"


def fail(message: str) -> None:
    sys.exit(f"{TOOL}: {message}")


# -- 입력 검증 -----------------------------------------------------------------

def gateway_url(value: str) -> str:
    """HTTPS 또는 Tailscale/loopback의 HTTP만 받는다."""
    parts = urllib.parse.urlsplit(value.strip())
    if parts.username or parts.password or parts.query or parts.fragment or not parts.hostname:
        fail("주소에는 호스트만 적는다(자격·쿼리·조각 금지): http://100.x.y.z:443")
    if parts.scheme != "https":
        loopback = parts.hostname == "localhost"
        tailnet = False
        try:
            address = ipaddress.ip_address(parts.hostname)
            loopback = loopback or address.is_loopback
            tailnet = address in ipaddress.ip_network("100.64.0.0/10")
        except ValueError:
            pass
        if parts.scheme != "http" or not (loopback or tailnet):
            fail("HTTP는 Tailscale IP(100.64.0.0/10) 또는 이 PC의 loopback 주소에서만 허용한다")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def server_names(value: str) -> list[str]:
    names = [name.strip() for name in value.split(",") if name.strip()]
    if not names or any(not SERVER_NAME.fullmatch(name) for name in names):
        fail("--servers는 레지스트리의 서버 이름을 쉼표로: filesystem,git,fetch")
    return sorted(set(names))


def workstation_name(value: str | None) -> str:
    # IdP의 client_id. 리프레시 토큰 계열을 이 PC에 묶는 이름표다(IdP가 허용 목록으로 검증하지는 않는다).
    name = (value or socket.gethostname()).strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", name):
        fail("--workstation은 영문·숫자·.-_ 64자 이내(예: ysg-laptop)")
    return name


def endpoint(settings: dict, server: str) -> str:
    return f"{settings['url']}/mcp/{server}/"


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
    """하네스는 서버마다 헬퍼를 동시에 부른다(서버 10개면 10번). IdP는 리프레시 토큰을 한 번 쓰면 바꾸므로,
    동시에 갱신하면 옛 토큰을 다시 쓴 것이 되어 계열 전체가 폐기된다. 한 번에 한 프로세스만 갱신한다."""

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


def grant(settings: dict, fields: dict) -> dict | None:
    body = urllib.parse.urlencode({**fields, "client_id": settings["workstation"]}).encode()
    status, data, _ = request(settings, settings["url"] + "/oauth/token", data=body,
                              headers={"Content-Type": "application/x-www-form-urlencoded"})
    if status == 200:
        return json.loads(data)
    if fields["grant_type"] == "refresh_token":
        return None  # 만료·폐기: 다시 로그인해야 한다
    try:
        detail = json.loads(data or b"{}").get("error_description") or status
    except ValueError:
        detail = status
    fail(f"로그인 실패({detail})")


def save_tokens(data: dict, previous: dict) -> dict:
    tokens = {"access_token": data["access_token"],
              "refresh_token": data.get("refresh_token") or previous.get("refresh_token"),
              "expires_at": time.time() + int(data.get("expires_in", 600))}
    write_private(home() / "token.json", json.dumps(tokens))
    return tokens


def cached_tokens() -> dict:
    path = home() / "token.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except ValueError:
        return {}


def ask_credentials(email: str | None, password_stdin: bool) -> tuple[str, str]:
    email = email or input("회사 계정(이메일): ").strip()
    password = sys.stdin.readline().rstrip("\r\n") if password_stdin else getpass.getpass("비밀번호(화면에 보이지 않음): ")
    if not email or not password:
        fail("계정과 비밀번호가 필요하다")
    return email, password


def login(settings: dict, email: str | None = None, password_stdin: bool = False) -> None:
    email, password = ask_credentials(email, password_stdin)
    with Lock(home() / "token.lock"):
        data = grant(settings, {"grant_type": "password", "username": email, "password": password})
        save_tokens(data, {})
    print(f"로그인했다: {email} (이 PC: {settings['workstation']}). 비밀번호는 저장하지 않았다")


def access_token(settings: dict) -> str:
    """헬퍼용: 절대 묻지 않는다(하네스는 10초 안에 헤더를 받아야 하고 입력 창이 없다)."""
    with Lock(home() / "token.lock"):
        tokens = cached_tokens()
        if tokens.get("access_token") and time.time() < tokens.get("expires_at", 0) - LEEWAY_SECONDS:
            return tokens["access_token"]
        data = grant(settings, {"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]}) \
            if tokens.get("refresh_token") else None
        if data is None:
            fail(f"로그인이 필요하다: python \"{home() / TOOL}\" login")
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
    for app in settings.get("codex_apps_disabled", []):
        lines += ["", "# 관리자가 거부한 ChatGPT 앱(report가 쓴다)", f"[apps.{app}]", "enabled = false"]
    if settings.get("codex_features_disabled"):
        lines += ["", "# 관리자가 거부한 기본 기능(report가 쓴다)", "[features]"]
        lines += [f"{name} = false" for name in settings["codex_features_disabled"]]
    return "\n".join(lines + [END]) + "\n"


def codex_conflicts(text: str, servers: list[str], table: str = "mcp_servers") -> list[str]:
    """블록 밖에서 직원이 이미 정의한 같은 이름 - 그대로 두면 TOML 중복 테이블이 된다."""
    try:
        import tomllib
        existing = tomllib.loads(text).get(table, {})
        return [s for s in servers if s in existing]
    except ImportError:  # Python 3.10 이하
        return [s for s in servers if re.search(rf"^\s*\[{table}\.(\"?)" + re.escape(s) + r"\1\]", text, re.M)]


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
                "workstation": workstation_name(args.workstation),
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
    # report가 넣은 거부 항목을 이어받는다. setup을 다시 해도 이전에 끈 커넥터가 되살아나지 않게.
    for key in ("claude_denied", "codex_apps_disabled", "codex_features_disabled"):
        settings[key] = previous.get(key, [])
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
        # 하네스 설정을 쓰기 전에 로그인이 되는지 먼저 본다. 같은 PC·같은 기기면 이전 로그인을 이어 쓴다.
        same = previous.get("url") == settings["url"] and previous.get("workstation") == settings["workstation"]
        if not (same and cached_tokens().get("refresh_token")) or args.email or args.password_stdin:
            login(settings, args.email, args.password_stdin)
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
        try:
            print(f"하네스 커넥터: {report_and_apply(settings)}")
        except SystemExit as error:  # 연결은 끝났다. 보고는 doctor·report가 다시 한다
            print(f"하네스 커넥터 보고 못 함: {error.code}")
        print(f"완료. 확인: python \"{root / TOOL}\" doctor")


def cmd_login(args) -> None:
    login(load_settings(), args.email, args.password_stdin)


def cmd_token(args) -> None:
    print(access_token(load_settings()))


def cmd_header(args) -> None:
    settings = load_settings()
    print(json.dumps({"Authorization": f"Bearer {access_token(settings)}"}), flush=True)
    try:  # 헤더는 이미 나갔다. 무엇이 실패해도 하네스 연결에는 영향이 없다
        report_in_background(settings)
    except OSError:
        pass


REPORT_EVERY = 6 * 3600


def report_in_background(settings: dict) -> None:
    """하네스가 연결할 때마다 이 헬퍼를 부르므로, 따로 예약 작업을 깔지 않고 6시간에 한 번 report를 떼어 낸다.
    도장을 먼저 찍는다 - report가 부르는 `claude mcp list`가 이 헬퍼를 다시 부른다."""
    stamp = home() / "report.stamp"
    if not settings.get("harnesses") or (stamp.exists() and time.time() - stamp.stat().st_mtime < REPORT_EVERY):
        return
    stamp.touch()
    detach = {"creationflags": 0x00000008 | 0x00000200} if os.name == "nt" else {"start_new_session": True}
    with open(home() / "report.log", "w", encoding="utf-8") as log:  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen([sys.executable, str(home() / TOOL), "--home", str(home()), "report"],
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log, **detach)


# -- 하네스 기본 커넥터·기능(D-51): 보고하고, 관리자가 거부한 것을 하네스 스스로 끄게 한다 --------------

# `claude mcp list`의 한 줄: "claude.ai Notion: https://mcp.notion.com/mcp - ✔ Connected",
# "plugin:engineering:slack: https://mcp.slack.com/mcp (HTTP) - ! Needs authentication",
# "plugin:pdf-viewer:pdf: npx -y @modelcontextprotocol/server-pdf --stdio - ✔ Connected". JSON 출력이 없어 줄을 읽는다.
CLAUDE_LINE = re.compile(r"^(?P<name>.+?): (?P<target>.*?)(?: \((?:HTTP|SSE)\))? - (?P<status>[✔✓√✘✗×!-] .*)$")
# 보고하는 Codex 기본 기능: 켜져 있으면 데이터가 회사 밖(웹·앱·다른 프로그램)으로 나가는 것들.
CODEX_FEATURES = ("apps", "plugins", "browser_use", "computer_use", "image_generation", "memories")
APP_ID = re.compile(r"^[A-Za-z0-9_-]{1,120}$")


def origin(url: str) -> str:
    """scheme://host[:port]만 보낸다. MCP URL의 경로·쿼리에 키를 넣는 서비스가 있다."""
    try:
        parts = urllib.parse.urlsplit(url)
        port = f":{parts.port}" if parts.port else ""
    except ValueError:
        return ""
    return f"{parts.scheme}://{parts.hostname}{port}" if parts.scheme in ("http", "https") and parts.hostname else ""


def claude_items(settings: dict) -> list[dict] | None:
    claude = shutil.which("claude")
    if not claude:
        return None
    result = run([claude, "mcp", "list"])  # 서버마다 연결을 확인하므로 느리다(run의 한도 120초)
    if result.returncode != 0:
        return None
    items = []
    for line in result.stdout.splitlines():
        match = CLAUDE_LINE.match(line.strip())
        if not match or match["target"].startswith(settings["url"] + "/mcp/"):
            continue  # Gateway를 거치는 서버는 Gateway가 이미 본다
        name, target = match["name"], match["target"].strip()
        kind = "connector" if name.startswith("claude.ai ") else "plugin" if name.startswith("plugin:") else "server"
        items.append({"harness": "claude", "kind": kind, "name": name[:200],
                      "target": origin(target) or ("stdio" if target else ""), "status": match["status"][:120]})
    return items


def codex_rpc(codex: str, method: str, params: dict, timeout: float = 60) -> dict | None:
    """`codex app-server`에 JSON-RPC 한 번. stdin을 닫으면 답하기 전에 끝나므로 답을 받을 때까지 열어 둔다."""
    import queue
    import threading
    try:
        process = subprocess.Popen([codex, "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace")
    except OSError:
        return None
    lines: queue.Queue = queue.Queue()
    threading.Thread(target=lambda: [lines.put(line) for line in process.stdout], daemon=True).start()
    try:
        for message in ({"id": 1, "method": "initialize", "params": {"clientInfo": {"name": TOOL, "version": "1"}}},
                        {"method": "initialized"}, {"id": 2, "method": method, "params": params}):
            process.stdin.write(json.dumps({"jsonrpc": "2.0", **message}) + "\n")
        process.stdin.flush()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                reply = json.loads(lines.get(timeout=max(0.1, deadline - time.monotonic())))
            except (queue.Empty, ValueError):
                continue
            if isinstance(reply, dict) and reply.get("id") == 2:
                return reply.get("result")
        return None
    except OSError:
        return None
    finally:
        process.kill()


def codex_items(settings: dict) -> list[dict] | None:
    codex = shutil.which("codex")
    if not codex:
        return None
    listed = run([codex, "mcp", "list", "--json"])
    if listed.returncode != 0:
        return None
    items = []
    try:
        servers = json.loads(listed.stdout or "[]")
    except ValueError:
        servers = []
    for server in servers:
        transport = server.get("transport") or {}
        url = transport.get("url") or ""
        if url.startswith(settings["url"] + "/mcp/"):
            continue
        items.append({"harness": "codex", "kind": "server", "name": str(server.get("name"))[:200],
                      "target": origin(url) or "stdio", "status": "enabled" if server.get("enabled") else "disabled",
                      "active": bool(server.get("enabled"))})
    # ChatGPT 계정에 연결한 앱(커넥터). app/list는 앱 디렉터리 전체라 설치된 것만 읽는다.
    for app in (codex_rpc(codex, "app/installed", {}) or {}).get("apps", []):
        if APP_ID.match(str(app.get("id", ""))):
            items.append({"harness": "codex", "kind": "app", "name": str(app.get("runtimeName") or app["id"])[:200],
                          "target": app["id"], "status": "enabled" if app.get("enabled") else "disabled",
                          "active": bool(app.get("enabled"))})
    features = run([codex, "features", "list"])
    for line in features.stdout.splitlines() if features.returncode == 0 else []:
        cells = line.split()
        if len(cells) >= 3 and cells[0] in CODEX_FEATURES and cells[-1] == "true":
            items.append({"harness": "codex", "kind": "feature", "name": cells[0], "target": "on", "status": "on"})
    mode = "cached"  # Codex 기본값(WebSearchMode::Cached)
    try:
        import tomllib
        mode = str(tomllib.loads(codex_config().read_text(encoding="utf-8")).get("web_search", mode))
    except (ImportError, OSError, ValueError):
        pass
    if mode != "disabled":
        items.append({"harness": "codex", "kind": "feature", "name": "web_search", "target": mode, "status": mode})
    return items


def claude_settings_path() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "settings.json"


def apply_claude(settings: dict, denied: list[dict]) -> str:
    """사용자 설정의 deniedMcpServers에 거부 항목을 둔다. 이 도구가 넣은 것만 기억해 두고 바꾼다 — 직원이 직접 넣은
    항목은 건드리지 않는다. 사용자 범위라 직원이 지울 수 있고, 지우면 다음 보고에서 '위반'으로 보인다."""
    path = claude_settings_path()
    try:
        document = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError):
        return f"{path}을 읽지 못해 거부 목록을 넣지 않았다(JSON 확인)"
    if not isinstance(document, dict):
        return f"{path}이 JSON 객체가 아니라 거부 목록을 넣지 않았다"
    previous = settings.get("claude_denied", [])
    theirs = [entry for entry in document.get("deniedMcpServers", []) if entry not in previous]
    ours = [entry for entry in denied if entry not in theirs]
    if theirs + ours:
        document["deniedMcpServers"] = theirs + ours
    else:
        document.pop("deniedMcpServers", None)
    if ours != previous:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    settings["claude_denied"] = ours
    return f"Claude Code 거부 {len(ours)}건({path})"


def apply_codex(settings: dict, apps: list[str], features: list[str] = ()) -> str:
    """거부한 앱은 [apps.<id>], 기능은 [features]로 블록에 둔다. 직원이 같은 테이블을 이미 쓰면 TOML 중복이라 건너뛴다.
    웹 검색은 루트 키(web_search)라 파일 끝의 블록에 둘 수 없다 - 관리형 requirements.toml로만 끈다."""
    path = codex_config()
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    wanted = [a for a in apps if APP_ID.match(a)]
    clash = codex_conflicts(without_block(current), wanted, "apps")
    settings["codex_apps_disabled"] = [a for a in wanted if a not in clash]
    features = [f for f in features if f != "web_search" and re.fullmatch(r"[a-z0-9_]+", f)]
    own_features = bool(features) and bool(codex_conflicts(without_block(current), ["features"], "features") or
                                            re.search(r"^\s*\[features\]", without_block(current), re.M))
    settings["codex_features_disabled"] = [] if own_features else features
    if settings.get("codex"):
        path.write_text(with_block(current, codex_block(settings)), encoding="utf-8")
    skipped = f", 직접 정의한 [apps.{clash[0]}]가 있어 건너뜀" if clash else ""
    skipped += ", 직접 정의한 [features]가 있어 기능은 건너뜀" if own_features else ""
    return f"Codex 앱 끔 {len(settings['codex_apps_disabled'])}건 · 기능 끔 {len(settings['codex_features_disabled'])}건{skipped}"


STATE_LABEL = {"pending": "검토 대기", "denied": "거부", "expired": "검토 기한 지나 거부"}


def report_and_apply(settings: dict) -> str:
    inventories = {}
    for harness, collect in (("claude", claude_items), ("codex", codex_items)):
        if harness in settings.get("harnesses", []):
            try:
                found = collect(settings)
            except (OSError, subprocess.TimeoutExpired):
                found = None
            if found is not None:
                inventories[harness] = found
    if not inventories:
        return "보고할 하네스 없음(설치 또는 목록 명령 실패)"
    body = json.dumps({"workstation": settings["workstation"], "harnesses": sorted(inventories),
                       "items": [item for found in inventories.values() for item in found]}).encode()
    status, data, _ = request(settings, settings["url"] + "/api/pc/inventory", data=body, timeout=30, headers={
        "Authorization": f"Bearer {access_token(settings)}", "Content-Type": "application/json"})
    if status != 200:
        return f"보고 실패 HTTP {status}"
    (home() / "report.stamp").touch()
    answer = json.loads(data)
    applied = []
    if "claude" in inventories:
        applied.append(apply_claude(settings, answer["policy"]["claude"]["deniedMcpServers"]))
    if "codex" in inventories:
        applied.append(apply_codex(settings, answer["policy"]["codex"]["apps_disabled"], answer["policy"]["codex"]["features_disabled"]))
    (home() / "config.json").write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for item in answer.get("review", []):
        note = f" — {item['note']}" if item.get("note") else ""
        print(f"  {STATE_LABEL.get(item['state'], item['state'])}: {', '.join(item['names'])}{note}")
    return f"{answer['accepted']}건 보고 · " + " · ".join(applied)


def cmd_report(args) -> None:
    print(report_and_apply(load_settings()))


INITIALIZE = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
    "protocolVersion": "2025-11-25", "capabilities": {},
    "clientInfo": {"name": "mcpgw-pc-doctor", "version": "1"}}}).encode()
HINTS = {401: "토큰이 거부됨. login으로 다시 로그인한다",
         403: "이 계정에 허용되지 않은 서버(권한 번들·협력사 숨김). 관리자에게 묻는다",
         404: "Gateway에 없는 서버 이름", 429: "호출 한도 초과", 502: "Gateway가 MCP 서버에 닿지 못함"}


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
        status, _, _ = request(settings, settings["url"] + "/api/health")
        report(status == 200, "Gateway 생존(/api/health)", f"HTTP {status}")
    except (urllib.error.URLError, OSError) as error:
        reason = getattr(error, "reason", error)
        if isinstance(reason, ssl.SSLError):
            report(False, "TLS", f"{getattr(reason, 'reason', None) or reason}. 기기의 루트 인증서를 setup --ca로 지정한다")
        else:
            report(False, "Gateway 도달", f"{reason}. 기기의 443 방화벽과 게시 주소(APPLIANCE_BIND)를 확인한다")
        sys.exit(1)
    try:
        token = access_token(settings)
        report(True, "로그인(접근 토큰)", f"이 PC: {settings['workstation']}")
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
    try:  # 연결 점검이 아니라 알림이다. 실패해도 doctor 결과를 바꾸지 않는다
        print(f"INFO 하네스 커넥터: {report_and_apply(settings)}")
    except SystemExit as error:
        print(f"INFO 하네스 커넥터 보고 못 함: {error.code}")
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
    if settings.get("claude_denied"):
        print(apply_claude(settings, []))
    refresh = cached_tokens().get("refresh_token")
    if settings.get("url") and refresh:
        # 종료 판정(TERMINATION_MODEL)의 회수 대상: 이 PC의 리프레시 토큰 계열을 IdP에서 폐기한다.
        # RFC 7009 응답(200)은 처리 사실만 뜻하므로 결과를 단정하지 않고 관리자 확인을 안내한다.
        try:
            status, _, _ = request(settings, settings["url"] + "/oauth/revoke",
                                   data=urllib.parse.urlencode({"token": refresh}).encode(),
                                   headers={"Content-Type": "application/x-www-form-urlencoded"})
            print(f"IdP 리프레시 토큰 폐기 요청: HTTP {status} (회수 확인은 관리자 Console의 종료·폐기에서)")
        except OSError as error:
            print(f"IdP에 닿지 못해 폐기 요청을 못 했다({error}). 관리자에게 이 PC({settings.get('workstation')})의 회수를 요청한다")
    for name in ("token.json", "token.lock", "ca.crt", "config.json", "report.stamp", "report.log", TOOL):
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
    root, tables = [], []
    if args.connectors:
        # Console의 하네스 커넥터 결정(D-51). 거부한 것만 담긴다 - 검토 대기는 아직 켜 둔다.
        policy = json.loads(Path(args.connectors).read_text(encoding="utf-8"))
        denied = {"deniedMcpServers": policy["claude"]["deniedMcpServers"]}
        if policy["claude"].get("allowAllClaudeAiMcps"):
            # managed-mcp.json이 있으면 claude.ai 커넥터가 모두 꺼진다. 승인한 것이 있으면 다시 켜고 거부 목록으로 뺀다.
            denied["allowAllClaudeAiMcps"] = True
        (out / "managed-settings.json").write_text(json.dumps(denied, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        features = [f for f in policy["codex"]["features_disabled"] if re.fullmatch(r"[a-z0-9_]+", f)]
        if "web_search" in features:
            root.append('allowed_web_search_modes = ["disabled"]')
        if {"browser_use", "computer_use"} & set(features):
            root.append("allow_browser_and_computer_use = false")
        if [f for f in features if f != "web_search"]:
            tables += ["", "[features]"] + [f"{f} = false" for f in features if f != "web_search"]
        for app in policy["codex"]["apps_disabled"]:
            if APP_ID.match(app):
                tables += ["", f"[apps.{app}]", "enabled = false"]
    # TOML은 루트 키가 첫 테이블보다 앞에 있어야 한다.
    lines = ["# Codex requirements.toml: 목록에 없는 MCP 서버는 켜지지 않는다(이름과 URL이 모두 맞아야 함)."] + root
    for server in settings["servers"]:
        lines += ["", f"[mcp_servers.{server}]", f'identity = {{ url = "{endpoint(settings, server)}" }}']
    (out / "requirements.toml").write_text("\n".join(lines + tables) + "\n", encoding="utf-8")
    print(f"{out / 'managed-mcp.json'} -> macOS /Library/Application Support/ClaudeCode/, "
          "Linux /etc/claude-code/, Windows C:\\Program Files\\ClaudeCode\\")
    if args.connectors:
        print(f"{out / 'managed-settings.json'} -> managed-mcp.json과 같은 폴더")
    print(f"{out / 'requirements.toml'} -> Unix /etc/codex/, Windows %ProgramData%\\OpenAI\\Codex\\")
    print(f"각 PC에 키트를 {args.kit}에 두고, 직원은 setup --harness codex로 로그인·Codex 설정을 한다")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog=TOOL, description=__doc__.split("\n")[0])
    parser.add_argument("--home", help=argparse.SUPPRESS)  # 헬퍼 명령이 토큰 폴더를 알려 줄 때
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("setup", help="로그인하고 하네스 설정을 기록")
    setup.add_argument("--url", required=True, help="솔루션 기기 Tailscale 주소, 예: http://100.x.y.z:443")
    setup.add_argument("--servers", required=True, help="쓸 서버 이름, 쉼표로(관리자가 알려 줌)")
    setup.add_argument("--workstation", help="이 PC의 이름(IdP client_id). 기본: 호스트 이름")
    setup.add_argument("--ca", help="관리자가 준 루트 인증서(PEM)")
    setup.add_argument("--harness", default="claude,codex", help="claude,codex 중 연결할 것")
    setup.add_argument("--email", help="회사 계정. 없으면 묻는다")
    setup.add_argument("--password-stdin", action="store_true", help="비밀번호를 표준 입력 첫 줄에서 읽는다")
    setup.add_argument("--replace", action="store_true", help="Claude Code의 같은 이름 서버를 덮어쓴다")
    setup.add_argument("--dry-run", action="store_true", help="쓸 내용만 보여 준다")
    setup.set_defaults(run=cmd_setup)
    login_parser = commands.add_parser("login", help="다시 로그인")
    login_parser.add_argument("--email")
    login_parser.add_argument("--password-stdin", action="store_true")
    login_parser.set_defaults(run=cmd_login)
    commands.add_parser("token", help="접근 토큰(다른 클라이언트에 넣을 때)").set_defaults(run=cmd_token)
    commands.add_parser("header", help="하네스 헤더 헬퍼 출력").set_defaults(run=cmd_header)
    commands.add_parser("doctor", help="연결 점검").set_defaults(run=cmd_doctor)
    commands.add_parser("report", help="하네스 기본 커넥터·기능 보고와 거부 적용").set_defaults(run=cmd_report)
    commands.add_parser("uninstall", help="이 도구가 쓴 설정 제거와 토큰 폐기").set_defaults(run=cmd_uninstall)
    managed = commands.add_parser("managed", help="관리자 강제 배포 파일 생성")
    managed.add_argument("--url", required=True)
    managed.add_argument("--servers", required=True)
    managed.add_argument("--out", required=True)
    managed.add_argument("--python", required=True, help="모든 PC에서 같은 파이썬 경로")
    managed.add_argument("--kit", required=True, help="모든 PC에서 같은 이 키트의 경로")
    managed.add_argument("--connectors", help="Console에서 받은 connector-policy.json(하네스 커넥터 거부)")
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
