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
LOGINS = {"claude": ["claude", "auth", "login"], "codex": ["codex", "login", "--device-auth"]}
SUBCOMMANDS = ("servers", "logs", "request", "login", "ui")


def unsent_calls():
    spool = Path.home() / ".mcpgw" / "tool-events.jsonl"
    try:
        with spool.open("rb") as handle:
            return sum(1 for _ in handle)
    except OSError:
        return 0


def short_time(value):
    return str(value or "")[:19].replace("T", " ") or "—"


def sections(summary):
    """(제목, 열, 행) — the terminal prints them as text, the local screen as tables."""
    return [
        ("승인된 MCP 서버", ("서버", "경로"), [(s["name"], PATHS.get(s["path"], s["path"])) for s in summary.get("servers", [])]),
        ("커넥터", ("이름", "하네스", "상태"),
         [(c["name"], HARNESSES.get(c["harness"], c["harness"]), STATES.get(c["state"], c["state"])) for c in summary.get("connectors", [])]),
        ("하네스 기능", ("기능", "하네스", "상태"),
         [(f["name"], HARNESSES.get(f["harness"], f["harness"]), STATES.get(f["state"], f["state"])) for f in summary.get("features", [])]),
        ("미등록 MCP", ("서버", "연결", "설정 파일"), [(u["name"], u["transport"], u["place"]) for u in summary.get("unregistered", [])]),
    ]


def call_rows(summary, limit=None):
    return [(short_time(c["called_at"]), HARNESSES.get(c["harness"], c["harness"]), PATHS.get(c["path"], c["path"]),
             f'{c["server"]} · {c["tool"]}', "실패" if c.get("failed") else "완료") for c in summary.get("calls", [])[:limit]]


def print_table(title, columns, rows):
    print(f"\n{title} · {len(rows)}")
    if not rows:
        print("  —")
        return
    widths = [max(len(str(col)), *(len(str(r[i])) for r in rows)) for i, col in enumerate(columns)]
    print("  " + "  ".join(str(col).ljust(widths[i]) for i, col in enumerate(columns)))
    for row in rows:
        print("  " + "  ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)))


def mint_request(address, server, source_url, purpose):
    result = receive(address, {"action": "request", "server": server, "source_url": source_url or "", "purpose": purpose})
    return "이미 요청함 · 검토 대기" if result.get("duplicate") else "요청함 · 검토 대기"


def mint_command(argv, address, status_lines, check):
    """Returns the exit code. status_lines() -> [str]; check() -> [(label, value)]."""
    import argparse
    parser = argparse.ArgumentParser(prog="mint", add_help=False)
    parser.add_argument("-h", "--help", action="help", help="도움말")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("servers", help="MCP 서버·커넥터·하네스 기능·미등록 MCP")
    logs = commands.add_parser("logs", help="MCP 호출 기록")
    logs.add_argument("-n", type=int, default=30, help="표시할 건수")
    request = commands.add_parser("request", help="MCP 도입 요청")
    request.add_argument("server", help="서버 이름")
    request.add_argument("--source", default="", help="소스 주소 (https://)")
    request.add_argument("--purpose", default="", help="사용 목적")
    login = commands.add_parser("login", help="모델 로그인")
    login.add_argument("harness", choices=sorted(LOGINS))
    commands.add_parser("ui", help="화면 열기")
    args = parser.parse_args(argv)
    try:
        if args.command == "login":
            import subprocess
            return subprocess.call(LOGINS[args.harness])
        if args.command == "ui":
            return serve_ui(address, status_lines, check)
        if args.command == "request":
            purpose = args.purpose or input("사용 목적: ")
            print(mint_request(address, args.server, args.source, purpose))
            return 0
        summary = receive(address, {"action": "self"})
        if args.command == "servers":
            for title, columns, rows in sections(summary):
                print_table(title, columns, rows)
        else:
            print_table("MCP 호출", ("시각", "하네스", "경로", "서버 · 도구", "결과"), call_rows(summary, max(1, args.n)))
            print(f"\n전송 대기 {unsent_calls()}건")
        return 0
    except (OSError, ValueError, KeyError, TypeError):
        print("엔드포인트 서비스 연결 실패 · mint --check")
        return 1


STYLE = ("body{font:15px/1.5 system-ui,'Malgun Gothic',sans-serif;margin:0;background:#0f1520;color:#e6edf6}"
         "header{display:flex;gap:16px;align-items:center;padding:14px 24px;border-bottom:1px solid #263244}"
         "header b{font-size:17px}nav a{color:#9fb3cc;margin-right:14px;text-decoration:none}nav a.on{color:#fff;font-weight:700}"
         "main{max-width:1080px;margin:0 auto;padding:20px 24px}section{background:#151d2b;border:1px solid #263244;border-radius:8px;margin:0 0 16px}"
         "h2{font-size:15px;margin:0;padding:12px 16px;border-bottom:1px solid #263244}h2 span{color:#8b9bb0;font-weight:400;margin-left:6px}"
         "table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:8px 16px;border-bottom:1px solid #1f2a3a;font-size:14px}"
         "th{color:#8b9bb0;font-weight:600}.kv td:first-child{color:#8b9bb0;width:160px}.empty{padding:12px 16px;color:#8b9bb0}"
         "form{display:grid;gap:10px;padding:16px}input,textarea{font:inherit;padding:8px;border-radius:6px;border:1px solid #33425a;background:#0f1520;color:#e6edf6}"
         "button{font:inherit;padding:8px 14px;border-radius:6px;border:1px solid #3b6fd6;background:#2554b8;color:#fff;cursor:pointer;justify-self:start}"
         ".note{padding:10px 16px;color:#7fd6a4}.bad{color:#f29b9b}")


def page(title, active, body, token):
    import html
    tabs = (("", "상태"), ("servers", "MCP"), ("logs", "호출 기록"), ("request", "도입 요청"))
    nav = "".join(f'<a href="/{token}/{key}" class="{"on" if key == active else ""}">{html.escape(label)}</a>' for key, label in tabs)
    return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>MINT · {html.escape(title)}</title><link rel="stylesheet" href="/{token}/style.css"></head><body>'
            f'<header><b>MINT</b><nav>{nav}</nav></header><main>{body}</main></body></html>')


def table_html(title, columns, rows):
    import html
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in columns)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(cell))}</td>" for cell in row) + "</tr>" for row in rows)
    content = f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>" if rows else '<p class="empty">—</p>'
    return f"<section><h2>{html.escape(title)}<span>{len(rows)}</span></h2>{content}</section>"


def serve_ui(address, status_lines, check, open_browser=True, idle=1800):
    """127.0.0.1 only, behind a random path token; closes after idle seconds without a request."""
    import html
    import http.server
    import secrets
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
                if name == "":
                    rows = "".join(f"<tr><td>{html.escape(a)}</td><td>{html.escape(b)}</td></tr>"
                                   for a, _, b in (line.partition(": ") for line in status_lines()))
                    checked = ""
                    if "check" in self.path:
                        checked = table_html("연결 점검", ("항목", "결과"), check())
                    form = f'<form method="get" action="/{token}/"><input type="hidden" name="check" value="1"><button>연결 점검</button></form>'
                    return self.reply(200, page("상태", "", f'<section><h2>상태</h2><table class="kv">{rows}</table>{form}</section>{checked}', token))
                summary = receive(address, {"action": "self"})
                if name == "servers":
                    return self.reply(200, page("MCP", name, "".join(table_html(*s) for s in sections(summary)), token))
                if name == "logs":
                    calls = table_html("MCP 호출", ("시각", "하네스", "경로", "서버 · 도구", "결과"), call_rows(summary))
                    return self.reply(200, page("호출 기록", name, calls + f'<p class="empty">전송 대기 {unsent_calls()}건</p>', token))
                if name == "request":
                    query = urllib.parse.parse_qs(self.path.partition("?")[2])
                    notice = query.get("done", [""])[0]
                    names = [u["name"] for u in summary.get("unregistered", [])]
                    options = "".join(f'<option value="{html.escape(n)}">' for n in names)
                    form = (f'<section><h2>도입 요청</h2>{f"<p class=note>{html.escape(notice)}</p>" if notice else ""}'
                            f'<form method="post" action="/{token}/request"><input name="server" list="unregistered" placeholder="서버 이름" required maxlength="120">'
                            f'<datalist id="unregistered">{options}</datalist><input name="source_url" placeholder="소스 주소 (https://)" maxlength="300">'
                            f'<textarea name="purpose" placeholder="사용 목적" required minlength="10" maxlength="1000"></textarea><button>요청</button></form></section>')
                    mine = table_html("내 요청", ("서버", "상태", "시각"),
                                      [(r["name"], REQUEST_STATES.get(r["status"], r["status"]), short_time(r["created_at"])) for r in summary.get("requests", [])])
                    return self.reply(200, page("도입 요청", name, form + mine, token))
                self.reply(404, "")
            except (OSError, ValueError, KeyError, TypeError):
                self.reply(502, page("오류", name, '<p class="empty bad">엔드포인트 서비스 연결 실패</p>', token))

        def do_POST(self):
            if self.route() != "request":
                return self.reply(404, "")
            length = min(int(self.headers.get("Content-Length") or 0), 8192)
            form = {k: v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8", "replace")).items()}
            try:
                notice = mint_request(address, form.get("server", ""), form.get("source_url", ""), form.get("purpose", ""))
            except (OSError, ValueError, KeyError, TypeError):
                notice = "요청 실패 · 입력 확인"
            self.send_response(303)
            self.send_header("Location", f"/{token}/request?done={urllib.parse.quote(notice)}")
            self.end_headers()

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{server.server_address[1]}/{token}/"
    print(url, flush=True)
    if open_browser:
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
