"""Kit login and approved source transfer; device credentials stay in the service."""
import contextlib
import hashlib
import json
import os
import re
import socket
import ssl
import tempfile
import threading
import urllib.request
import urllib.error
from pathlib import Path

MAX_BYTES = 128 << 20
SLOTS = threading.BoundedSemaphore(2)


class LoginError(ValueError):
    def __init__(self, reason, retry=False):
        self.kit_reason, self.retry = reason, retry
        super().__init__(reason)


def reject_reason(exc):
    """The Gateway's own sentence for a refused account (disabled, locked, waiting for approval); never a credential."""
    try:
        detail = json.loads(exc.read(8192)).get("detail")
    except (ValueError, AttributeError, OSError):
        return ""
    return detail.strip() if isinstance(detail, str) and 0 < len(detail) <= 80 and detail.isprintable() else ""


def attempt(bundle, request, address, username, password):
    config = dict(bundle, gateway_url=address)
    try:
        grant = request(config, "/auth/kit-enrollment", {"email": username, "password": password}, credential=False)
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise LoginError("로그인: 아이디·비밀번호 확인 필요", retry=True) from None
        text = reject_reason(exc)
        reason = {403: "로그인: 계정 잠김·승인 확인 필요", 429: "로그인: 시도 제한"}.get(exc.code, "로그인: 연결 실패")
        raise LoginError(text or reason) from None
    except ValueError:
        raise LoginError("로그인: 게이트웨이 주소 확인 필요 (https://주소)", retry=True) from None
    except OSError as exc:
        cause = getattr(exc, "reason", exc)
        raise LoginError("로그인: 게이트웨이 인증서 확인 필요" if isinstance(cause, ssl.SSLError)
                         else "로그인: 게이트웨이 연결 실패 · 주소와 네트워크 확인 필요", retry=True) from None
    if not isinstance(grant, dict) or not isinstance(grant.get("enrollment_token"), str):
        raise ValueError("로그인 응답 확인 필요")
    return {**config, **{k: grant[k] for k in ("enrollment_token", "expires_at") if k in grant}}


def login(bundle, request, inputs, attempts=3):
    """Asks again after a mistake the employee can fix (password, address, network); a refused account or a
    throttled address ends it. The prompt gets the last reason so it can show it."""
    address, notice = bundle["gateway_url"], ""
    for _ in range(attempts):
        try:
            address, username, password = inputs(address, notice) if notice else inputs(address)
        except EOFError:
            # Ctrl-D at the prompt: the employee is at a terminal and chose to stop, same as Ctrl-C.
            raise KeyboardInterrupt from None
        except ValueError as exc:
            raise LoginError(str(exc)) from None
        address = address.strip().rstrip("/")
        if address and "://" not in address:
            address = "https://" + address
        try:
            if not username.strip() or not password:
                raise LoginError("로그인: 아이디·비밀번호 입력 필요", retry=True)
            return attempt(bundle, request, address, username.strip(), password)
        except LoginError as exc:
            if not exc.retry:
                raise
            error, notice = exc, exc.kit_reason
        finally:
            password = None
    raise error


def request_problem(server, source, purpose):
    """The request form's rules in words; None when the request can go."""
    if not 0 < len(server.strip()) <= 120 or not server.isprintable():
        return "서버 이름 확인 필요 (1~120자)"
    if source and (len(source) > 300 or not re.fullmatch(r"https://\S+", source)):
        return "소스 주소는 https:// 주소만"
    if not 10 <= len(purpose.strip()) <= 1000:
        return "사용 목적은 10자 이상"
    return None


def request_fields(command):
    """An employee's request from their own PC: a name, an optional https source and a purpose, nothing else."""
    server, source, purpose = command.get("server"), command.get("source_url", ""), command.get("purpose")
    if (set(command) - {"action", "server", "source_url", "purpose"} or not isinstance(server, str) or not isinstance(source, str)
            or not isinstance(purpose, str) or not 0 < len(server.strip()) <= 120 or not server.isprintable()
            or not 10 <= len(purpose.strip()) <= 1000 or len(source) > 300
            or (source and not re.fullmatch(r"https://\S+", source))):
        raise ValueError("도입 요청 확인 필요")
    return {"server": server.strip(), "source_url": source, "purpose": purpose.strip()}


def source_path(command):
    if not isinstance(command, dict):
        raise ValueError("소스 요청 확인 필요")
    if command == {"action": "list"}:
        return "/api/endpoint/approved-mcp"
    if command == {"action": "self"}:
        return "/api/endpoint/self?limit=100"
    if command.get("action") == "request":
        request_fields(command)
        return "/api/endpoint/self/requests"
    server, commit = command.get("server", ""), command.get("commit", "")
    if (command.get("action") != "download" or not isinstance(server, str) or not isinstance(commit, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", server)
            or not re.fullmatch(r"[0-9a-f]{40}", commit)):
        raise ValueError("승인된 소스 확인 필요")
    return f"/api/endpoint/approved-mcp/{server}/source?commit={commit}"


def serve_source(config, command, transport, send):
    """Only approved list/archive paths, bounded and verified before crossing the local broker."""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            raise ValueError("주소 변경 거부")
    try:
        path = source_path(command)
        context = transport(config)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                                            urllib.request.HTTPSHandler(context=context))
        body = json.dumps(request_fields(command)).encode() if command["action"] == "request" else None
        request = urllib.request.Request(config["gateway_url"] + path, data=body, method="POST" if body else "GET",
            headers={"X-Endpoint-Key": config["device_key"], "Accept-Encoding": "identity", "Content-Type": "application/json"})
        with SLOTS, tempfile.SpooledTemporaryFile(max_size=4 << 20) as spool:
            with opener.open(request, timeout=130) as response:
                digest, size = hashlib.sha256(), 0
                limit = MAX_BYTES if command["action"] == "download" else 1 << 20
                while block := response.read(64 << 10):
                    size += len(block)
                    if size > limit:
                        raise ValueError("소스 크기 상한 초과")
                    digest.update(block)
                    spool.write(block)
                sha = response.headers.get("X-Content-SHA256", "")
                if command["action"] == "download" and (not re.fullmatch(r"[0-9a-f]{64}", sha) or sha != digest.hexdigest()):
                    raise ValueError("소스 검증 실패")
            spool.seek(0)
            send((json.dumps({"size": size, "sha256": sha or digest.hexdigest()}) + "\n").encode())
            while block := spool.read(64 << 10):
                send(block)
    except (OSError, ValueError, KeyError, TypeError):
        send(b'{"error":"source unavailable"}\n')


@contextlib.contextmanager
def broker(address):
    if os.name == "nt":
        descriptor = os.open(address, os.O_RDWR | os.O_BINARY)
        with os.fdopen(descriptor, "r+b", buffering=0) as stream:
            yield stream
    else:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(140)
            connection.connect(address)
            with connection.makefile("rwb", buffering=0) as stream:
                yield stream


def receive(address, command, folder=None):
    source_path(command)
    with broker(address) as stream:
        payload = (json.dumps(command) + "\n").encode()
        # Raw named pipes and sockets may complete a write only partially.
        while payload:
            sent = stream.write(payload)
            if not sent:
                raise OSError("소스 연결 실패")
            payload = payload[sent:]
        header = json.loads(stream.readline(8192))
        size, sha = header.get("size"), header.get("sha256", "")
        if type(size) is not int or not 0 < size <= MAX_BYTES or not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise ValueError("승인된 MCP 확인 실패")
        if command["action"] != "download":
            if size > 1 << 20:
                raise ValueError("목록 크기 상한 초과")
            output = bytearray()
            while len(output) < size:
                block = stream.read(min(64 << 10, size - len(output)))
                if not block:
                    raise ValueError("목록 수신 실패")
                output.extend(block)
            if hashlib.sha256(output).hexdigest() != sha:
                raise ValueError("목록 검증 실패")
            document = json.loads(output)
            return document["servers"] if command["action"] == "list" else document
        folder = Path(folder) if folder else Path.home() / "MINT" / "소스"
        folder.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".mint-", dir=folder)
        try:
            digest, remaining = hashlib.sha256(), size
            with os.fdopen(descriptor, "wb") as output:
                while remaining:
                    block = stream.read(min(64 << 10, remaining))
                    if not block:
                        raise ValueError("소스 수신 실패")
                    remaining -= len(block)
                    digest.update(block)
                    output.write(block)
            if digest.hexdigest() != sha:
                raise ValueError("소스 검증 실패")
            target = folder / f"{command['server']}-{command['commit'][:12]}.zip"
            os.replace(temporary, target)
            return str(target)
        finally:
            Path(temporary).unlink(missing_ok=True)


# -- `mint <명령>`: one command table for the terminal and the local screen (`mint ui`) on every platform. The data is
# what the Gateway holds for this device, fetched through the service's broker; the employee holds no device key. --
PATHS = {"gateway": "게이트웨이", "connector": "커넥터", "local": "로컬"}
STATES = {"default": "기본 승인", "approved": "승인", "denied": "차단", "pending": "검토 중", "expired": "검토 기한 만료"}
HARNESSES = {"claude": "Claude Code", "codex": "Codex"}
REQUEST_STATES = {"OPEN": "검토 대기", "CLOSED": "처리됨"}
# The console's labels for an application (INTAKE_STATUS in console.js).
APPLICATION_STATES = {"HOLD": "검토 대기", "REMOTE_REVIEWED": "계약 검토 완료", "VALIDATION_QUEUED": "검증 대기", "VALIDATING": "검증 중",
                      "VALIDATED": "검증 완료", "APPROVED": "승인", "REJECTED": "거부", "FAILED": "검증 실패"}
LOGINS = {"claude": ["claude", "auth", "login"], "codex": ["codex", "login", "--device-auth"]}
# Console pages the terminal can open; consent and account connections are given only there, signed in (D-301).
CONSOLE_PAGES = {"logs": "activity", "consent": "consent", "requests": "intake", "connections": "connections"}
SUBCOMMANDS = ("servers", "logs", "requests", "request", "sources", "login", "ui", "console")
HELP = "명령: servers · logs [번호] · requests · request · sources [서버] · login · ui · console [페이지]  (mint <명령> -h)"


def unsent_calls():
    spool = Path.home() / ".mcpgw" / "tool-events.jsonl"
    try:
        with spool.open("rb") as handle:
            return sum(1 for _ in handle)
    except OSError:
        return 0


def short_time(value):
    """The Gateway's UTC time in this PC's local time, as the console shows it."""
    from datetime import datetime
    try:
        return datetime.fromisoformat(str(value)).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return str(value or "")[:19].replace("T", " ") or "—"


def sections(summary):
    """(제목, 열, 행) — the terminal prints them as text, the local screen as tables."""
    waiting = {c["name"] for c in summary.get("consents") or []}
    return [
        ("승인된 MCP 서버", ("서버", "경로", "상태"), [(s["name"], PATHS.get(s["path"], s["path"]),
                                                  "이 PC 미지원" if not s.get("available", True) else "동의 필요" if s["name"] in waiting
                                                  else "사용 가능")
                                                 for s in summary.get("servers", [])]),
        ("커넥터", ("이름", "하네스", "상태"),
         [(c["name"], HARNESSES.get(c["harness"], c["harness"]), STATES.get(c["state"], c["state"])) for c in summary.get("connectors", [])]),
        ("하네스 기능", ("기능", "하네스", "상태"),
         [(f["name"], HARNESSES.get(f["harness"], f["harness"]), STATES.get(f["state"], f["state"])) for f in summary.get("features", [])]),
        ("미등록 MCP", ("서버", "연결", "설정 파일"), [(u["name"], u["transport"], u["place"]) for u in summary.get("unregistered", [])]),
    ]


DECISIONS = {"Allow": "허용", "Alert": "경보", "Restrict": "제한", "Block": "차단"}


def call_verdict(call):
    """The Gateway's decision; a call that did not pass the Gateway (local, connector) has none."""
    return DECISIONS.get(call.get("decision"), "—")


def call_outcome(call):
    """What happened to the tool itself, apart from the decision: an alert can still fail, a block never ran."""
    if call.get("decision") == "Block":
        return "실행 안 함"
    return "실패" if call.get("failed") else "완료"


CALL_COLUMNS = ("시각", "하네스", "경로", "서버 · 도구", "판정", "결과")


def call_rows(summary, limit=None):
    return [(short_time(c["called_at"]), HARNESSES.get(c["harness"], c["harness"]) or "—", PATHS.get(c["path"], c["path"]),
             f'{c.get("server_name") or c["server"]} · {c["tool"]}', call_verdict(c), call_outcome(c))
            for c in summary.get("calls", [])[:limit]]


def size_text(value):
    value = int(value or 0)
    return f"{value:,} B" if value < 10240 else f"{value / 1024:,.1f} KB"


def call_detail(call, console_url=""):
    """One call as the console's detail drawer lists it: the PC's report beside the Gateway's decision."""
    pairs = [("호출 시각", short_time(call["called_at"])), ("하네스", HARNESSES.get(call["harness"], call["harness"])),
             ("PC 계정", call.get("account") or "—"), ("경로", PATHS.get(call["path"], call["path"])),
             ("서버", call.get("server_name") or call["server"]), ("도구", call["tool"]), ("판정", call_verdict(call)), ("결과", call_outcome(call)),
             ("정책", call.get("policy_id") or "—"), ("사유", call.get("reason") or "—"),
             ("입력", size_text(call.get("input_bytes"))), ("출력", size_text(call.get("output_bytes"))),
             ("판정 시각", short_time(call["decided_at"]) if call.get("decided_at") else "—"),
             ("판정 번호", str(call.get("decision_id") or "—"))]
    if call.get("decision_id") and console_url:
        pairs.append(("콘솔", f'{console_url}#/activity?d={call["decision_id"]}'))
    return pairs


def request_rows(summary):
    return [(r["name"], REQUEST_STATES.get(r["status"], r["status"]), short_time(r["created_at"])) for r in summary.get("requests", [])]


def application_rows(summary):
    # The console shows the status and, beside it, that the server is registered on the Gateway.
    return [(a["name"], APPLICATION_STATES.get(a["status"], a["status"]) + (" · 게이트웨이 등록" if a.get("registered_server_id") else ""),
             short_time(a["created_at"])) for a in summary.get("applications", [])]


def source_rows(servers):
    return [(s.get("display_name") or s["server_id"], (s.get("commit_sha") or "—")[:12],
             "받기 가능" if s.get("source_available") else "원격 · 게이트웨이 경유") for s in servers]


def can_open_browser():
    """A browser only where one can show: never over SSH, and on Linux only inside a desktop session (otherwise
    webbrowser falls back to a text browser that takes over the terminal)."""
    import sys
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"):
        return False
    return os.name == "nt" or sys.platform == "darwin" or bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def cells(text):
    """Terminal columns: Hangul and other wide characters take two (kit_screen.width)."""
    import unicodedata
    return sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in str(text))


def pad(text, room):
    return str(text) + " " * (room - cells(text))


def print_pairs(title, pairs):
    print(f"\n{title}")
    width = max(cells(a) for a, _ in pairs)
    for label, value in pairs:
        print(f"  {pad(label, width)}  {value}")


def terminal_columns():
    """The terminal's width; a pipe or a file has no width, so it gets the table as it is."""
    import shutil
    import sys
    return shutil.get_terminal_size((10 ** 4, 24)).columns if sys.stdout.isatty() else 10 ** 4


def print_table(title, columns, rows):
    print(f"\n{title} · {len(rows)}")
    if not rows:
        print("  —")
        return
    widths = [max(cells(col), *(cells(r[i]) for r in rows)) for i, col in enumerate(columns)]
    if 2 + sum(widths) + 2 * (len(widths) - 1) > terminal_columns():
        # Narrower than the table (an 80-column console, a phone over SSH): one line per row instead of columns that wrap.
        for row in rows:
            print("  " + " · ".join(str(cell) for cell in row))
        return
    for row in (columns, *rows):
        print(("  " + "  ".join(pad(cell, widths[i]) for i, cell in enumerate(row))).rstrip())


def print_json(document):
    import json
    print(json.dumps(document, ensure_ascii=False, indent=2, default=str))
    return 0


def mint_request(address, server, source_url, purpose):
    result = receive(address, {"action": "request", "server": server, "source_url": source_url or "", "purpose": purpose})
    # What happens next, in the employee's words: the administrator reviews it; an approval shows up in `mint servers`.
    return ("이미 요청함" if result.get("duplicate") else "요청함") + " · 관리자 검토 대기 · 승인되면 mint servers에 표시"


# argparse's own words (usage, errors, -h) for the employee: argparse looks its strings up through gettext at call time.
ARGPARSE_WORDS = {
    "usage: ": "사용법: ", "positional arguments": "인자", "options": "옵션", "show this help message and exit": "도움말",
    "%(prog)s: error: %(message)s\n": "%(prog)s: %(message)s\n", "argument %(argument_name)s: %(message)s": "%(argument_name)s: %(message)s",
    "invalid %(type)s value: %(value)r": "%(value)r 확인 필요 (숫자)", "invalid choice: %(value)r (choose from %(choices)s)": "%(value)r 없음 · 선택: %(choices)s",
    "the following arguments are required: %s": "필요한 값: %s", "unrecognized arguments: %s": "알 수 없는 인자: %s",
    "expected one argument": "값 필요",
}


def korean_argparse():
    import argparse
    import gettext
    argparse._ = lambda text: ARGPARSE_WORDS.get(text) or gettext.gettext(text)


def mint_command(argv, address, status_lines, check):
    """Returns the exit code. status_lines() -> [str]; check() -> [(label, value)]."""
    import argparse
    korean_argparse()
    parser = argparse.ArgumentParser(prog="mint", add_help=False, epilog=HELP, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-h", "--help", action="help", help="도움말")
    commands = parser.add_subparsers(dest="command", required=True, metavar="명령")
    machine = argparse.ArgumentParser(add_help=False)
    machine.add_argument("--json", action="store_true", help="JSON 출력")
    commands.add_parser("servers", help="MCP 서버·커넥터·하네스 기능·미등록 MCP", parents=[machine])
    logs = commands.add_parser("logs", help="MCP 호출 기록", parents=[machine])
    logs.add_argument("number", nargs="?", type=int, metavar="번호", help="호출 상세 (목록의 번호)")
    logs.add_argument("-n", type=int, default=30, metavar="건수", help="표시할 건수")
    commands.add_parser("requests", help="내 도입 요청·신청", parents=[machine])
    sources = commands.add_parser("sources", help="승인된 MCP 소스", parents=[machine])
    sources.add_argument("server", nargs="?", metavar="서버", help="받을 서버")
    sources.add_argument("--to", metavar="폴더", help="받을 폴더")
    request = commands.add_parser("request", help="MCP 도입 요청")
    request.add_argument("server", metavar="서버", help="서버 이름")
    request.add_argument("--source", default="", metavar="주소", help="소스 주소 (https://)")
    request.add_argument("--purpose", default="", metavar="목적", help="사용 목적")
    login = commands.add_parser("login", help="모델 로그인")
    login.add_argument("harness", choices=sorted(LOGINS), metavar="하네스", help="claude · codex")
    commands.add_parser("ui", help="화면 열기")
    console = commands.add_parser("console", help="웹 콘솔 열기")
    console.add_argument("page", nargs="?", choices=sorted(CONSOLE_PAGES), metavar="페이지", help="logs · consent · requests · connections")
    args = parser.parse_args(argv)
    try:
        if args.command == "login":
            import subprocess
            return subprocess.call(LOGINS[args.harness])
        if args.command == "ui":
            return serve_ui(address, status_lines, check)
        if args.command == "request":
            try:
                purpose = args.purpose or input("사용 목적: ")
            except (EOFError, KeyboardInterrupt):
                print('\n사용 목적 필요 · mint request <서버> --purpose "…"')
                return 2
            problem = request_problem(args.server, args.source, purpose)
            if problem:
                print(problem)
                return 2
            print(mint_request(address, args.server, args.source, purpose))
            return 0
        if args.command == "sources":
            servers = receive(address, {"action": "list"})
            if not args.server and args.json:
                return print_json(servers)
            if not args.server:
                print_table("승인된 MCP", ("서버", "커밋", "소스"), source_rows(servers))
                return 0
            found = [s for s in servers if args.server in (s["server_id"], s.get("display_name"))]
            if not found:
                print(f"승인된 MCP 아님 · {args.server} · mint sources")
                return 1
            if not found[0].get("source_available"):
                print(f"원격 MCP라 받을 소스 없음 · {args.server}")
                return 1
            print("받음 · " + receive(address, {"action": "download", "server": found[0]["server_id"],
                                              "commit": found[0]["commit_sha"]}, args.to))
            return 0
        summary = receive(address, {"action": "self"})
        if args.command == "console":
            if not summary.get("console_url"):
                print("콘솔 주소 확인 실패 · mint --check")
                return 1
            url = summary["console_url"] + (f"#/{CONSOLE_PAGES[args.page]}" if args.page else "")
            print(url)
            if can_open_browser():
                import webbrowser
                webbrowser.open(url)
            return 0
        if getattr(args, "json", False):
            keys = {"servers": ("servers", "connectors", "features", "unregistered", "consents"), "requests": ("requests", "applications"),
                    "logs": ("calls",)}[args.command]
            document = {key: summary.get(key, []) for key in keys}
            if args.command == "logs":
                document["calls"] = document["calls"][:max(1, args.n)] if args.number is None else document["calls"][args.number - 1:args.number]
            return print_json(document)
        if args.command == "requests":
            print_table("내 요청", ("서버", "상태", "시각"), request_rows(summary))
            print_table("도입 신청", ("서버", "상태", "시각"), application_rows(summary))
            return 0
        if args.command == "servers":
            for title, columns, rows in sections(summary):
                print_table(title, columns, rows)
            if summary.get("consents"):
                print_table("동의 대기", ("서버", "도구"), [(c["name"], c["tools"]) for c in summary["consents"]])
                if summary.get("consent_url"):
                    print(f"  콘솔에서 동의: {summary['consent_url']}")
        elif args.number is not None:
            calls = summary.get("calls", [])
            if not 1 <= args.number <= len(calls):
                print(f"호출 번호 확인 필요 · 1~{len(calls)}" if calls else "MCP 호출 기록 없음")
                return 1
            print_pairs("MCP 호출", call_detail(calls[args.number - 1], summary.get("console_url", "")))
        else:
            rows = [(n, *row) for n, row in enumerate(call_rows(summary, max(1, args.n)), 1)]
            print_table("MCP 호출", ("번호", *CALL_COLUMNS), rows)
            print(f"\n전송 대기 {unsent_calls()}건 · 상세: mint logs <번호>")
        return 0
    except (OSError, ValueError, KeyError, TypeError):
        print("엔드포인트 서비스 연결 실패 · mint --check")
        return 1


# The console's own tokens and components (console.css), so the local screen reads as the same product.
STYLE = (
    ":root{color-scheme:light;--bg:#f5f7fa;--panel:#fff;--panel-2:#f8fafc;--line:#e3e8ef;--line-2:#7c8ca1;--ink:#172337;--ink-2:#475569;"
    "--ink-3:#58677b;--brand:#244d8c;--brand-2:#245ca6;--brand-soft:#edf3fc;--allow:#17633e;--allow-bg:#eaf6ef;--alert:#805200;"
    "--alert-bg:#fff4d9;--restrict:#076773;--restrict-bg:#e6f5f7;--approval:#6342bb;--approval-bg:#f0ebfc;--block:#b42332;--block-bg:#fcecee;"
    "--radius:10px;--sans:'Noto Sans KR',-apple-system,BlinkMacSystemFont,'Segoe UI','Apple SD Gothic Neo','Malgun Gothic',sans-serif;"
    "--mono:ui-monospace,'SFMono-Regular',Consolas,monospace}"
    "@media (prefers-color-scheme:dark){:root{color-scheme:dark;--bg:#101722;--panel:#192331;--panel-2:#202d3d;--line:#324154;--line-2:#75869d;"
    "--ink:#edf2f9;--ink-2:#c1cddd;--ink-3:#a1b0c3;--brand:#a7c5ff;--brand-2:#b7d0ff;--brand-soft:#283d5c;--allow:#8be0ad;--allow-bg:#20392e;"
    "--alert:#f3ce79;--alert-bg:#3c3220;--restrict:#89dce6;--restrict-bg:#203a41;--approval:#cfb8ff;--approval-bg:#352e4b;--block:#ffa7af;--block-bg:#432b34}"
    ".btn.primary{color:#142438}}"
    "*{box-sizing:border-box}html,body{margin:0;min-height:100%}"
    "body{background:var(--bg);color:var(--ink);font:15.75px/1.78 var(--sans);-webkit-font-smoothing:antialiased}"
    "a{color:var(--brand-2);text-decoration:none}button,input,select,textarea{font:inherit;color:inherit}"
    ":focus-visible{outline:3px solid var(--brand-2);outline-offset:3px;border-radius:4px}"
    ".app-bar{height:60px;position:sticky;top:0;z-index:15;display:flex;align-items:center;gap:8px;padding:0 16px;background:var(--panel);border-bottom:1px solid var(--line)}"
    ".app-title{display:flex;align-items:center;gap:10px;margin:0 auto 0 4px;color:var(--ink);font-weight:750;font-size:18px;letter-spacing:-.02em}"
    ".app-title .mark{display:grid;place-items:center;width:30px;height:30px;border-radius:8px;background:var(--brand);color:var(--panel)}"
    ".app-title .mark svg{width:17px;height:17px}.app-identity{color:var(--ink-3);font-size:14.58px;margin-right:8px}"
    ".shell{display:grid;grid-template-columns:220px minmax(0,1fr);min-height:calc(100vh - 60px)}"
    ".side{position:sticky;top:60px;height:calc(100vh - 60px);background:var(--panel);border-right:1px solid var(--line)}"
    ".nav{padding:12px 10px 20px;display:flex;flex-direction:column;gap:2px}"
    ".nav a{display:flex;align-items:center;gap:11px;padding:8px 12px;min-height:38px;border-radius:7px;color:var(--ink-2);font-size:15.75px;font-weight:500}"
    ".nav a svg{width:18px;height:18px;flex:none}.nav a:hover{background:var(--panel-2);color:var(--ink)}"
    ".nav a[aria-current=page]{background:var(--brand-soft);color:var(--brand);font-weight:700}"
    ".nav .count{margin-left:auto;padding:0 7px;background:var(--block-bg);color:var(--block);font-size:12.42px;font-weight:750;border-radius:6px;line-height:20px}"
    ".main{min-width:0;width:100%;max-width:1600px;margin:0 auto;padding:28px 32px 64px}"
    ".page-head{display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin-bottom:22px}"
    ".page-head h1{margin:0;flex:1;font-size:29.25px;font-weight:750;line-height:1.3;letter-spacing:-.025em}"
    ".stack{display:flex;flex-direction:column;gap:20px}"
    ".kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:20px}"
    ".kpi{min-width:0;padding:10px 14px;background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);color:inherit}"
    "a.kpi:hover{border-color:var(--brand)}.kpi .label{font-size:12.6px;color:var(--ink-3);margin-bottom:2px}"
    ".kpi .value{font-size:22.5px;font-weight:750;line-height:1.2;letter-spacing:-.03em;font-variant-numeric:tabular-nums;color:var(--ink)}"
    ".kpi.allow .value{color:var(--allow)}.kpi.block .value{color:var(--block)}.kpi.alert .value{color:var(--alert)}"
    ".panel{min-width:0;background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);overflow:hidden}"
    ".panel>header{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:18px 20px 0}"
    ".panel>header h2{margin:0;font-size:16.92px;font-weight:700;letter-spacing:-.025em}.panel>header .sub{font-size:13.5px;color:var(--ink-3)}"
    ".panel>header .tools-end{margin-left:auto;display:flex;gap:8px}.panel>header form{margin:0}"
    ".panel .body{padding:16px 20px 20px}.panel .body.flush{padding:16px 0 0;overflow-x:auto}"
    "table.data{width:100%;border-collapse:collapse;font-size:14.58px}"
    "table.data th{padding:11px 16px;text-align:left;font-size:13.5px;font-weight:600;color:var(--ink-3);background:var(--panel-2);border-block:1px solid var(--line);white-space:nowrap}"
    "table.data td{padding:12px 16px;border-bottom:1px solid var(--line);vertical-align:middle;overflow-wrap:anywhere}table.data tr:last-child td{border-bottom:0}"
    "table.data td.t{font:13.5px var(--mono);color:var(--ink-3);white-space:nowrap}"
    ".kv{display:grid;grid-template-columns:140px minmax(0,1fr);font-size:14.58px;margin:0}"
    ".kv dt,.kv dd{padding:11px 0;border-bottom:1px solid var(--line)}.kv dt{color:var(--ink-3)}.kv dd{margin:0;overflow-wrap:anywhere;min-width:0}"
    ".kv dt:nth-last-child(2),.kv dd:last-child{border-bottom:0}"
    ".chip{display:inline-flex;align-items:center;gap:6px;font-size:13.5px;font-weight:600;line-height:20px;padding:3px 8px;border-radius:6px;background:var(--panel-2);color:var(--ink-2)}"
    ".chip{white-space:nowrap}.chip::before{content:'';width:6px;height:6px;border-radius:50%;background:currentColor}"
    ".chip.allow{color:var(--allow);background:var(--allow-bg)}.chip.alert{color:var(--alert);background:var(--alert-bg)}"
    ".chip.restrict{color:var(--restrict);background:var(--restrict-bg)}.chip.approval{color:var(--approval);background:var(--approval-bg)}"
    ".chip.block{color:var(--block);background:var(--block-bg)}.chip.brand{color:var(--brand);background:var(--brand-soft)}"
    ".btn{display:inline-flex;align-items:center;justify-content:center;gap:7px;border:1px solid var(--line-2);border-radius:7px;padding:8px 14px;min-height:40px;"
    "background:var(--panel);color:var(--ink-2);font-weight:550;font-size:14.58px;cursor:pointer}.btn:hover{background:var(--panel-2);color:var(--ink)}"
    ".btn.primary{background:var(--brand);border-color:var(--brand);color:var(--panel)}.btn.sm{padding:6px 10px;min-height:34px;font-size:13.5px}"
    ".form{display:grid;gap:16px;max-width:760px}.form label{display:flex;flex-direction:column;gap:7px;font-size:14.58px;font-weight:550}"
    ".form input,.form textarea{width:100%;min-height:42px;padding:10px 12px;background:var(--panel);border:1px solid var(--line-2);border-radius:7px}"
    ".form textarea{min-height:120px;resize:vertical}.form .row{display:flex;gap:8px}"
    ".note{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:0 0 16px;background:var(--allow-bg);border:1px solid var(--allow);border-radius:8px;padding:12px 16px;color:var(--ink);font-size:14.58px}"
    ".note.warn{background:var(--alert-bg);border-color:var(--alert)}.note .btn{margin-left:auto}"
    ".empty{padding:44px 24px;text-align:center;color:var(--ink-3);margin:0}"
    ".foot{margin:0;padding:12px 20px;color:var(--ink-3);font-size:13.5px;border-top:1px solid var(--line)}"
    "@media (max-width:900px){.shell{grid-template-columns:1fr}.side{position:static;height:auto;border-right:0;border-bottom:1px solid var(--line)}"
    ".nav{flex-direction:row;overflow-x:auto;padding:8px}.nav a{white-space:nowrap}.main{padding:20px 16px 48px}.kpis{grid-template-columns:repeat(2,minmax(0,1fr))}}"
    "@media (max-width:480px){html,body{overflow-x:hidden}.app-bar{padding:0 12px}.app-identity{display:none}.main{padding:16px 12px 40px}"
    ".page-head h1{font-size:22.5px}.kpis{gap:8px}.kpi .value{font-size:18px}.panel>header{padding:14px 14px 0}.panel .body{padding:12px 14px 14px}"
    ".kv{grid-template-columns:96px minmax(0,1fr)}.panel>header .tools-end{margin-left:0;flex-wrap:wrap}.note{flex-direction:column;align-items:flex-start}"
    ".note .btn{margin-left:0}.nav a{padding:6px 10px;min-height:34px}}"
)

ICONS = {
    "mark": '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
    "": '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
    "servers": '<rect x="3" y="4" width="18" height="7" rx="2"/><rect x="3" y="13" width="18" height="7" rx="2"/><path d="M7 7.5h.01M7 16.5h.01"/>',
    "logs": '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    "request": '<path d="M12 5v14M5 12h14"/>',
}
TABS = (("", "상태"), ("servers", "MCP 서버"), ("logs", "호출 기록"), ("request", "도입 요청"))
# Values coloured as the console colours them.
CHIPS = {"경보": "alert", "사용 가능": "allow", "이 PC 미지원": "alert", "승인": "allow", "승인 · 게이트웨이 등록": "allow", "기본 승인": "allow", "완료": "allow", "연결됨": "allow", "활성": "allow", "처리됨": "allow",
         "차단": "block", "실패": "block", "허용": "allow", "제한": "restrict", "연결 끊김": "block", "검토 중": "approval", "검토 대기": "approval",
         "검토 기한 만료": "alert", "게이트웨이 등록": "allow", "검증 실패": "alert", "거부": "block", "검증 대기": "approval",
         "검증 중": "approval", "검증 완료": "restrict", "계약 검토 완료": "approval", "게이트웨이": "brand", "커넥터": "restrict", "로컬": "alert"}
CHIP_COLUMNS = {"상태", "결과", "경로", "판정"}


def svg(name):
    return (f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            f'stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>')


def chip(value):
    import html
    return f'<span class="chip {CHIPS.get(value, "")}">{html.escape(str(value))}</span>'


def page(title, active, body, token, identity="", counts=None, refresh=0, console=""):
    import html
    counts = counts or {}
    nav = "".join(f'<a href="/{token}/{key}"{" aria-current=page" if key == active else ""}>{svg(key)}<span>{html.escape(label)}</span>'
                  + (f'<span class="count">{counts[key]}</span>' if counts.get(key) else "") + "</a>" for key, label in TABS)
    return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="color-scheme" content="light dark"><title>MINT · {html.escape(title)}</title>'
            + (f'<meta http-equiv="refresh" content="{int(refresh)}">' if refresh else "") +
            f'<link rel="stylesheet" href="/{token}/style.css"></head><body>'
            f'<header class="app-bar"><a class="app-title" href="/{token}/"><span class="mark">{svg("mark")}</span><strong>MINT</strong></a>'
            f'<span class="app-identity">{html.escape(identity)}</span>'
            + (f'<a class="btn sm" href="{html.escape(console)}" target="_blank" rel="noopener">웹 콘솔</a>' if console.startswith("https://") else "")
            + '</header>'
            f'<div class="shell"><aside class="side"><nav class="nav" aria-label="메뉴">{nav}</nav></aside>'
            f'<main class="main"><div class="page-head"><h1>{html.escape(title)}</h1></div>{body}</main></div></body></html>')


def table_html(title, columns, rows, foot="", actions=None):
    import html
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in columns) + ("<th></th>" if actions else "")
    body = "".join("<tr>" + "".join(('<td class="t">' if columns[i] == "시각" else "<td>")
                                    + (chip(cell) if columns[i] in CHIP_COLUMNS else html.escape(str(cell))) + "</td>"
                                    for i, cell in enumerate(row)) + (f'<td class="num">{actions[n]}</td>' if actions else "") + "</tr>"
                   for n, row in enumerate(rows))
    content = (f'<div class="body flush"><table class="data"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'
               if rows else '<p class="empty">없음</p>')
    return (f'<section class="panel"><header><h2>{html.escape(title)}</h2><span class="sub">{len(rows)}</span></header>{content}'
            + (f'<p class="foot">{html.escape(foot)}</p>' if foot else "") + "</section>")


def kv_html(title, pairs, tools=""):
    import html
    rows = "".join(f"<dt>{html.escape(a)}</dt><dd>{chip(b) if b in CHIPS else html.escape(b)}</dd>" for a, b in pairs)
    return (f'<section class="panel"><header><h2>{html.escape(title)}</h2><span class="tools-end">{tools}</span></header>'
            f'<div class="body"><dl class="kv">{rows}</dl></div></section>')


def serve_ui(address, status_lines, check, open_browser=True, idle=1800):
    """127.0.0.1 only, behind a random path token; closes after idle seconds without a request."""
    import html
    import http.server
    import secrets
    import socket
    import time
    import urllib.parse
    import webbrowser
    token = secrets.token_urlsafe(24)
    last = [time.monotonic()]

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, body, kind="text/html; charset=utf-8"):
            data = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'self'; form-action 'self'; frame-ancestors 'none'")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(data)

        def route(self):
            parts = self.path.split("?", 1)[0].strip("/").split("/")
            if not parts or not secrets.compare_digest(parts[0], token):
                self.reply(404, "")
                return None
            last[0] = time.monotonic()
            return parts[1] if len(parts) > 1 else ""

        def do_GET(self):
            name = self.route()
            if name is None:
                return
            if name == "style.css":
                return self.reply(200, STYLE, "text/css; charset=utf-8")
            try:
                summary = receive(address, {"action": "self"})
            except (OSError, ValueError, KeyError, TypeError):
                summary = None
            known = summary or {}
            counts = {"servers": len(known.get("unregistered", [])),
                      "request": sum(1 for r in known.get("requests", []) if r.get("status") == "OPEN")}
            notice = urllib.parse.parse_qs(self.path.partition("?")[2]).get("done", [""])[0]

            waiting = known.get("consents") or []
            if waiting and known.get("consent_url", "").startswith("https://"):
                banner = (f'<p class="note warn">동의 대기 {sum(c["tools"] for c in waiting)}건 · '
                          + ", ".join(html.escape(c["name"]) for c in waiting)
                          + f' <a class="btn sm primary" href="{html.escape(known["consent_url"])}" target="_blank" rel="noopener">콘솔에서 동의</a></p>')
            else:
                banner = ""

            def show(title, body, status=200):
                note = f'<p class="note">{html.escape(notice)}</p>' if notice else ""
                # Read-only pages follow the PC without a reload button; a page with a form or a check result does not.
                refresh = 60 if name in ("", "servers", "logs") and "check" not in self.path else 0
                self.reply(status, page(title, name, banner + note + body, token, socket.gethostname(), counts, refresh,
                                        known.get("console_url", "")))

            if name == "":
                pairs = [(a, b) for a, _, b in (line.partition(": ") for line in status_lines())]
                values = dict(pairs)
                calls = known.get("calls", [])
                cards = (("연결 상태", values.get("연결 상태", "—"), "allow" if values.get("연결 상태") == "연결됨" else "block", ""),
                         ("사용 가능 서버", sum(1 for s in known.get("servers", []) if s.get("available", True)), "", "servers"),
                         ("미등록 MCP", counts["servers"], "alert" if counts["servers"] else "", "servers"),
                         ("MCP 호출", len(calls), "block" if any(c.get("failed") or c.get("decision") == "Block" for c in calls) else "", "logs"))
                kpis = "".join((f'<a class="kpi {tone}" href="/{token}/{link}">' if link else f'<div class="kpi {tone}">')
                               + f'<div class="label">{html.escape(label)}</div><div class="value">{html.escape(str(value))}</div>'
                               + ("</a>" if link else "</div>") for label, value, tone, link in cards)
                button = (f'<form method="get" action="/{token}/"><input type="hidden" name="check" value="1">'
                          f'<button class="btn sm">연결 점검</button></form>')
                if os.name == "nt":
                    # A console window of its own for the device-code sign-in, as the tray did.
                    button += "".join(f'<form method="post" action="/{token}/login"><input type="hidden" name="harness" value="{key}">'
                                      f'<button class="btn sm">{label} 로그인</button></form>' for key, label in HARNESSES.items())
                body = f'<div class="kpis">{kpis}</div><div class="stack">{kv_html("엔드포인트", pairs, button)}'
                if "check" in self.path:
                    body += kv_html("연결 점검", list(check()))
                return show("상태", body + "</div>")
            if summary is None:
                return show("오류", '<section class="panel"><p class="empty">엔드포인트 서비스 연결 실패</p></section>', 502)
            if name == "servers":
                try:
                    local = [s for s in receive(address, {"action": "list"}) if s.get("source_available")]
                except (OSError, ValueError, KeyError, TypeError):
                    local = []
                sources = ""
                if local:
                    rows = "".join(
                        f'<tr><td>{html.escape(s.get("display_name") or s["server_id"])}</td><td class="t">{html.escape(s["commit_sha"][:12])}</td>'
                        f'<td><form method="post" action="/{token}/source"><input type="hidden" name="server" value="{html.escape(s["server_id"])}">'
                        f'<input type="hidden" name="commit" value="{html.escape(s["commit_sha"])}"><button class="btn sm">소스 받기</button></form></td></tr>'
                        for s in local)
                    sources = (f'<section class="panel"><header><h2>승인된 소스</h2><span class="sub">{len(local)}</span></header>'
                               f'<div class="body flush"><table class="data"><thead><tr><th>서버</th><th>커밋</th><th></th></tr></thead>'
                               f'<tbody>{rows}</tbody></table></div></section>')
                parts = sections(summary)
                links = [f'<a class="btn sm" href="/{token}/request?{urllib.parse.urlencode({"server": u["name"], "source": u.get("source") or ""})}">도입 요청</a>'
                         for u in summary.get("unregistered", [])]
                tables = [table_html(*part, actions=links if part[0] == "미등록 MCP" and links else None) for part in parts]
                return show("MCP 서버", '<div class="stack">' + "".join(tables) + sources + "</div>")
            if name == "logs":
                return show("호출 기록", table_html("MCP 호출", CALL_COLUMNS, call_rows(summary),
                                                f"전송 대기 {unsent_calls()}건"))
            if name == "request":
                options = "".join(f'<option value="{html.escape(u["name"])}">' for u in summary.get("unregistered", []))
                query = urllib.parse.parse_qs(self.path.partition("?")[2])
                asked = query.get("server", [""])[0][:120]
                source = query.get("source", [""])[0][:300]
                source = source if re.fullmatch(r"https://\S+", source) else ""
                form = ('<section class="panel"><header><h2>도입 요청</h2></header><div class="body">'
                        f'<form class="form" method="post" action="/{token}/request">'
                        f'<label>서버 이름<input name="server" list="unregistered" required maxlength="120" value="{html.escape(asked)}"></label>'
                        f'<datalist id="unregistered">{options}</datalist>'
                        f'<label>소스 주소<input name="source_url" type="url" pattern="https://.*" placeholder="https://" maxlength="300" value="{html.escape(source)}"></label>'
                        f'<label>사용 목적<textarea name="purpose" required minlength="10" maxlength="1000"></textarea></label>'
                        f'<div class="row"><button class="btn primary">요청</button></div></form></div></section>')
                mine = table_html("내 요청", ("서버", "상태", "시각"), request_rows(summary))
                applied = table_html("도입 신청", ("서버", "상태", "시각"), application_rows(summary))
                return show("도입 요청", f'<div class="stack">{form}{mine}{applied}</div>')
            return show("없는 화면", f'<section class="panel"><p class="empty"><a class="btn" href="/{token}/">상태로</a></p></section>', 404)

        def do_POST(self):
            name = self.route()
            if name not in ("request", "source", "login"):
                return None if name is None else self.reply(404, "")
            length = min(int(self.headers.get("Content-Length") or 0), 8192)
            form = {k: v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8", "replace")).items()}
            back = {"request": "request", "source": "servers", "login": ""}[name]
            try:
                if name == "request":
                    notice = mint_request(address, form.get("server", ""), form.get("source_url", ""), form.get("purpose", ""))
                elif name == "source":
                    notice = "받음 · " + receive(address, {"action": "download", "server": form.get("server", ""),
                                                          "commit": form.get("commit", "")})
                else:
                    harness = form.get("harness", "")
                    if os.name != "nt" or harness not in LOGINS:
                        raise ValueError(harness)
                    import shutil
                    import subprocess
                    if not shutil.which(harness):
                        notice = f"{HARNESSES[harness]} 설치 필요"
                    else:
                        subprocess.Popen(["cmd.exe", "/k", " ".join(LOGINS[harness])], creationflags=subprocess.CREATE_NEW_CONSOLE)
                        notice = f"{HARNESSES[harness]} 로그인 창을 열었습니다"
            except (OSError, ValueError, KeyError, TypeError):
                notice = {"request": "요청 실패 · 입력 확인", "source": "소스 받기 실패", "login": "로그인 실패"}[name]
            self.send_response(303)
            self.send_header("Location", f"/{token}/{back}?done={urllib.parse.quote(notice)}")
            self.end_headers()

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{server.server_address[1]}/{token}/"
    print(url, flush=True)
    if os.environ.get("SSH_CONNECTION"):
        import getpass
        port = server.server_address[1]
        print(f"다른 PC에서 열기: ssh -L {port}:127.0.0.1:{port} {getpass.getuser()}@{socket.gethostname()} → 위 주소", flush=True)
    if open_browser and can_open_browser():
        webbrowser.open(url)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        while time.monotonic() - last[0] < idle:
            time.sleep(5)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
    return 0
