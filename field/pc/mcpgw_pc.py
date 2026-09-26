#!/usr/bin/env python3
"""mcpgw_pc: 직원 PC의 Claude Code·Codex CLI를 솔루션 기기의 MCP 프록시에 연결한다.

    python mcpgw_pc.py setup --url https://mcp-gw.internal --servers demo --ca mcp-gw-root.crt
    python mcpgw_pc.py doctor        # 이름 해석·TLS·키·서버별 연결·하네스 설정을 한 줄씩 확인
    python mcpgw_pc.py key           # 키를 다시 입력(관리자가 새 키를 발급했을 때)
    python mcpgw_pc.py uninstall     # 이 도구가 쓴 설정만 지운다
    python mcpgw_pc.py managed --out DIR --url ... --servers ...   # 관리자 강제 배포용 파일 생성

두 하네스 모두 연결할 때마다 이 도구의 `header`를 실행해 키를 받는다(Claude Code `headersHelper`,
Codex CLI 0.148+ `http_headers_helper`). 키 원문은 ~/.mcpgw/key 한 곳에만 있고 하네스 설정 파일·환경
변수에는 들어가지 않는다. 표준 라이브러리만 쓴다(Python 3.9+).
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
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TOOL = "mcpgw_pc.py"
# 프록시 라우트 이름과 같은 규칙(mcp_gateway/config.py SERVER_NAME).
SERVER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
KEY_ENV = "MCPGW_PROXY_KEY"
BEGIN = "# >>> mcp-gateway proxy (mcpgw_pc.py) >>>"
END = "# <<< mcp-gateway proxy (mcpgw_pc.py) <<<"


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
        fail("--servers는 프록시 설정의 서버 이름을 쉼표로: demo,filesystem")
    return sorted(set(names))


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


def read_key() -> str:
    path = home() / "key"
    if not path.exists():
        fail(f"키가 없다({path}). `python {TOOL} key`로 관리자가 준 키를 입력한다")
    return path.read_text(encoding="utf-8").strip()


def ask_key(from_stdin: bool) -> str:
    key = sys.stdin.readline() if from_stdin else getpass.getpass(
        "관리자가 발급한 프록시 키(mcpp_..., 입력은 화면에 보이지 않음): ")
    key = key.strip()
    if not key or any(c.isspace() for c in key):
        fail("키가 비어 있거나 공백이 들어 있다")
    return key


def helper_command() -> str:
    """두 하네스가 셸(Windows cmd /C, 그 밖 sh -c)로 실행하는 한 줄.

    Codex는 헬퍼를 환경 변수를 비우고 실행하므로(MCP 서버와 같은 허용 목록만 넘김) 키가 있는 폴더를
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
        # 사용자가 직접 만든 같은 이름의 서버를 말없이 덮어쓰지 않는다.
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
    """블록 밖에서 사용자가 이미 정의한 같은 이름 - 그대로 두면 TOML 중복 테이블이 된다."""
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


# -- 명령 -----------------------------------------------------------------------

def cmd_setup(args) -> None:
    settings = {"url": gateway_url(args.url), "servers": server_names(args.servers),
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
        if args.key_stdin or not (root / "key").exists():
            write_private(root / "key", ask_key(args.key_stdin) + "\n")
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


def cmd_key(args) -> None:
    write_private(home() / "key", ask_key(args.stdin) + "\n")
    print("키를 바꿨다. 두 하네스 모두 다음 연결부터 새 키를 쓴다")


def cmd_token(args) -> None:
    print(read_key())


def cmd_header(args) -> None:
    print(json.dumps({"Authorization": f"Bearer {read_key()}"}))


def tls_context(settings: dict) -> ssl.SSLContext | None:
    if not settings["url"].startswith("https://"):
        return None
    context = ssl.create_default_context()
    if settings.get("ca"):
        context.load_verify_locations(cafile=settings["ca"])
    return context


def request(settings: dict, url: str, *, data: bytes | None = None, headers: dict | None = None,
            method: str | None = None) -> tuple[int, bytes, dict]:
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    # 시스템 프록시를 거치지 않는다 - 사내망 기기에 곧바로 붙어야 한다.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                         urllib.request.HTTPSHandler(context=tls_context(settings)))
    try:
        with opener.open(req, timeout=15) as response:
            return response.status, response.read(4096), dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, error.read(4096), dict(error.headers)


INITIALIZE = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
    "protocolVersion": "2025-11-25", "capabilities": {},
    "clientInfo": {"name": "mcpgw-pc-doctor", "version": "1"}}}).encode()
HINTS = {401: "키가 없거나 중지·만료됨. 관리자에게 키 상태를 묻는다",
         403: "이 키에 허용되지 않은 서버. 관리자가 키의 서버 권한을 고친다",
         404: "프록시에 없는 서버 이름", 429: "분당 한도 초과", 502: "기기에서 upstream MCP 서버에 닿지 못함"}


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
        report(status == 200, "TLS와 프록시 생존(/api/health)", f"HTTP {status}")
    except (urllib.error.URLError, OSError) as error:
        reason = getattr(error, "reason", error)
        if isinstance(reason, ssl.SSLError):
            report(False, "TLS", f"{getattr(reason, 'reason', None) or reason}. 기기의 루트 인증서를 setup --ca로 지정한다")
        else:
            report(False, "프록시 도달", f"{reason}. 기기의 443 방화벽과 게시 주소(APPLIANCE_BIND)를 확인한다")
        sys.exit(1)
    try:
        key = read_key()
    except SystemExit as error:
        report(False, "키", str(error.code))
        key = ""
    for server in settings["servers"] if key else []:
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream"}
        status, body, response_headers = request(settings, endpoint(settings, server), data=INITIALIZE, headers=headers)
        report(status == 200 and b"jsonrpc" in body, f"MCP {server} initialize", f"HTTP {status} {HINTS.get(status, '')}".strip())
        session = {k.lower(): v for k, v in response_headers.items()}.get("mcp-session-id")
        if status == 200 and session:
            # 2025-11-25 이전 방식 서버: 확인용 세션을 닫는다. 실패해도 문제 삼지 않는다.
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
    helper = subprocess.run(helper_command(), shell=True, capture_output=True, text=True, timeout=10)
    try:
        report(helper.returncode == 0 and "Authorization" in json.loads(helper.stdout), "헬퍼 명령(하네스가 실행하는 것)")
    except ValueError:
        report(False, "헬퍼 명령(하네스가 실행하는 것)", f"종료 코드 {helper.returncode}")
    sys.exit(1 if failures else 0)


def remove_codex_block() -> None:
    config = codex_config()
    if config.exists() and BEGIN in config.read_text(encoding="utf-8"):
        config.write_text(without_block(config.read_text(encoding="utf-8")), encoding="utf-8")
        print(f"블록 지움: {config}")


def cmd_uninstall(args) -> None:
    root = home()
    settings = json.loads((root / "config.json").read_text(encoding="utf-8")) if (root / "config.json").exists() else {}
    claude = shutil.which("claude")
    for server in settings.get("claude_servers", []):
        if claude:
            result = run([claude, "mcp", "remove", "--scope", "user", server])
            print(f"Claude Code {server}: {'지움' if result.returncode == 0 else '이미 없음'}")
    remove_codex_block()
    for name in ("key", "ca.crt", "config.json", TOOL):
        if (root / name).exists():
            (root / name).unlink()
    print(f"지움: {root} 의 키·CA·설정. OS 인증서 저장소의 CA와 hosts 항목은 README 절차대로 따로 지운다")


def cmd_managed(args) -> None:
    """MDM·그룹 정책으로 PC에 둘 관리형 파일. 사용자는 목록 밖의 서버를 더하지 못한다."""
    settings = {"url": gateway_url(args.url), "servers": server_names(args.servers)}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    # 모든 사용자가 읽는 파일이라 키를 넣지 않는다. 각 사용자의 환경 변수에서 확장된다(공식 문서의 권장 방식).
    claude = {"mcpServers": {s: {"type": "http", "url": endpoint(settings, s),
                                 "headers": {"Authorization": f"Bearer ${{{KEY_ENV}}}"}} for s in settings["servers"]}}
    (out / "managed-mcp.json").write_text(json.dumps(claude, indent=2) + "\n", encoding="utf-8")
    lines = ["# Codex requirements.toml: 목록에 없는 MCP 서버는 켜지지 않는다(이름과 URL이 모두 맞아야 함)."]
    for server in settings["servers"]:
        lines += ["", f"[mcp_servers.{server}]", f'identity = {{ url = "{endpoint(settings, server)}" }}']
    (out / "requirements.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{out / 'managed-mcp.json'} -> macOS /Library/Application Support/ClaudeCode/, "
          "Linux /etc/claude-code/, Windows C:\\Program Files\\ClaudeCode\\")
    print(f"{out / 'requirements.toml'} -> Unix /etc/codex/, Windows %ProgramData%\\OpenAI\\Codex\\")
    print(f"Claude Code는 각 사용자의 {KEY_ENV} 환경 변수로 키를 받는다. Codex는 setup --harness codex 그대로")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog=TOOL, description=__doc__.split("\n")[0])
    parser.add_argument("--home", help=argparse.SUPPRESS)  # 헬퍼 명령이 키 폴더를 알려 줄 때
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("setup", help="하네스 설정 기록과 키 저장")
    setup.add_argument("--url", required=True, help="솔루션 기기 주소, 예: https://mcp-gw.internal")
    setup.add_argument("--servers", required=True, help="쓸 서버 이름, 쉼표로")
    setup.add_argument("--ca", help="관리자가 준 루트 인증서(PEM)")
    setup.add_argument("--harness", default="claude,codex", help="claude,codex 중 연결할 것")
    setup.add_argument("--key-stdin", action="store_true", help="키를 표준 입력 첫 줄에서 읽는다")
    setup.add_argument("--replace", action="store_true", help="Claude Code의 같은 이름 서버를 덮어쓴다")
    setup.add_argument("--dry-run", action="store_true", help="쓸 내용만 보여 준다")
    setup.set_defaults(run=cmd_setup)
    key = commands.add_parser("key", help="키를 다시 입력")
    key.add_argument("--stdin", action="store_true")
    key.set_defaults(run=cmd_key)
    commands.add_parser("token", help="키 원문(다른 클라이언트에 넣을 때)").set_defaults(run=cmd_token)
    commands.add_parser("header", help="하네스 헤더 헬퍼 출력").set_defaults(run=cmd_header)
    commands.add_parser("doctor", help="연결 점검").set_defaults(run=cmd_doctor)
    commands.add_parser("uninstall", help="이 도구가 쓴 설정 제거").set_defaults(run=cmd_uninstall)
    managed = commands.add_parser("managed", help="관리자 강제 배포 파일 생성")
    managed.add_argument("--url", required=True)
    managed.add_argument("--servers", required=True)
    managed.add_argument("--out", required=True)
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
