"""Shared, credential-free terminal view of the kit's existing status snapshots."""
import atexit
import os
import queue
import re
import shutil
import signal
import sys
import threading
import time
import unicodedata
from datetime import datetime

ENTER = "\x1b[?1049h\x1b[?25l"
LEAVE = "\x1b[0m\x1b[?25h\x1b[?1049l"
KEYS = "q 종료 · c 지금 점검 · r 새로고침"
STATES = {"active": "활성", "pending": "활성화 대기", "quarantined": "격리됨",
          "revoked": "등록 해제됨", "removed": "제거됨", "unknown": "확인 필요"}
TEXT_EN = {
    "MINT 엔드포인트": "MINT endpoint", "엔드포인트에서 차단": "Blocked at endpoint",
    "연결 상태": "Connection", "연결됨": "Connected", "연결 끊김": "Disconnected",
    "관리 상태": "Management", "상태": "Status", "연결 방식": "Mode", "간편 모드": "Simple mode",
    "게이트웨이 판정": "Gateway decision", "격리 계정": "Isolated account",
    "활성화 대기": "Waiting for activation", "서비스 중지": "Service stopped", "활성": "Active", "격리됨": "Quarantined",
    "등록 해제됨": "Unregistered", "철회됨": "Revoked", "제거됨": "Removed", "확인 필요": "Needs attention",
    "승인 서버": "Approved servers", "승인 MCP 서버": "Approved MCP servers",
    "하네스 판본": "Harness versions", "하네스 응답": "Harness response", "하네스": "Harnesses",
    "최근 보고": "Last report", "최근 엔드포인트 차단": "Recent endpoint blocks",
    "게이트웨이 MCP 목록": "Gateway MCP list", "게이트웨이 응답 정상": "Gateway answers",
    "설치 단계": "Installation steps", "설치 확인": "Installation checks", "설치 중": "Installing",
    "설치 완료": "Installed", "설치 실패": "Installation failed", "차단 발생": "Blocked",
    "관리 설정 적용": "Managed settings applied", "서버 연결": "Server connection", "서버": "Servers",
    "일부 실패": "Some failed", "진행 중": "In progress", "완료": "Done", "실패": "Failed", "도구": "Tools",
    "관리자 활성화 대기": "Waiting for an administrator", "관리자에게 격리 해제 요청": "Ask an administrator to release",
    "새 키트로 다시 설치": "Reinstall with a new kit", "하네스 실행": "Run a harness",
    "게이트웨이 연결 점검": "Check gateway connection", "다음 할 일": "Next step",
    "종료": "Quit", "지금 점검": "Check now", "새로고침": "Refresh", "점검 설정 없음": "No check settings",
}


def translate(value, language="ko"):
    if language != "en":
        return value
    text = re.sub("|".join(map(re.escape, sorted(TEXT_EN, key=len, reverse=True))),
                  lambda match: TEXT_EN[match[0]], value)
    text = re.sub(r"(\d+(?:\.\d+)?)초", r"\1s", text)
    return re.sub(r"(\d+)개", r"\1", text)


def clean(value):
    # Never print arbitrary errors, terminal controls or credential-shaped text from a probe.
    text = str(value)
    if re.search(r"(?i)bearer|token|password|secret|authorization|eyJ[A-Za-z0-9_-]+\.|[A-Za-z0-9_+/=-]{32,}", text):
        return "—"
    return "".join(c for c in text if not unicodedata.category(c).startswith("C"))


def width(text):
    return sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def clip(text, room):
    out, used = "", 0
    for c in clean(text):
        used += width(c)
        if used > room:
            break
        out += c
    return out


def result_label(value):
    if value is True:
        return "완료"
    if value is False:
        return "실패"
    return "—"


def legacy_cell(value):
    """Old Linux checks carry raw failure details; the terminal only needs their result."""
    text = clean(value)
    if "실패" in text:
        return "실패"
    if "대기" in text:
        return "활성화 대기"
    if "정상" in text:
        seconds = re.search(r"\d+(?:\.\d+)?초", text)
        return "완료" + (" · " + seconds[0] if seconds else "")
    if re.fullmatch(r"\d+개 \(서버 \d+/\d+\)", text):
        return "완료 · " + text
    return "—"


def check_cells(probe):
    """Only measured results, never the model's answer or a subprocess error."""
    model, connection = probe.get("model") or {}, probe.get("connection") or {}
    answer = result_label(model.get("ok"))
    if isinstance(model.get("seconds"), (int, float)):
        answer += f" · {model['seconds']:.1f}초"
    tools = "—"
    if connection.get("service"):
        tools = "서비스 중지"
    elif connection.get("waiting"):
        tools = "활성화 대기"
    elif connection.get("initialized"):
        tools = f"완료 · 도구 {int(connection.get('tools') or 0)}개"
        if connection.get("failed"):
            tools += " · 일부 실패"
    elif connection.get("failed"):
        tools = "실패"
    return [("하네스 응답", answer), ("게이트웨이 MCP 목록", tools)]


def frame(summary, rows=(), cells=(), next_line="", columns=80, lines=30, now=None, stale=180, language="ko"):
    now = time.time() if now is None else now
    connected = summary.get("connected") and 0 <= now - (summary.get("updated") or 0) <= stale
    badge = "연결됨" if connected else "연결 끊김"
    if rows and not summary:
        badge = "설치 중" if any(row[2] is None for row in rows) else "설치 완료"
    if any(row[3] == "✗" for row in rows):
        badge = "설치 실패"
    blocks = summary.get("blocks") or []
    if connected and blocks:
        try:
            age = now - datetime.fromisoformat(blocks[-1]["at"].replace("Z", "+00:00")).timestamp()
            if 0 <= age <= 300:
                badge = "차단 발생"
        except (ValueError, KeyError, TypeError):
            pass
    height = max(0, lines - 1)
    shown = max(1, height - 13 - max(1, len(blocks[-5:])))
    body = ["MINT 엔드포인트", f"상태  [{badge}]",
            "관리 상태  " + STATES.get(summary.get("state"), "—") + " · 연결 방식  " +
            {"simple": "간편 모드", "isolated": "격리 계정"}.get(summary.get("mode"), "—"), "설치 단계"]
    for label, started, seconds, mark in rows[-shown:]:
        spent = seconds if seconds is not None else max(0, int(time.monotonic() - started))
        state = "진행 중" if seconds is None else "실패" if mark == "✗" else "완료"
        body.append(f"  {clean(label)}  {state} · {spent}초")
    if not rows:
        body.append("  —")
    values = dict(cells)
    answer = values.get("하네스 응답", legacy_cell(values.get("모델 응답", "—")))
    tools = values.get("게이트웨이 MCP 목록", legacy_cell(values.get("도구", "—")))
    # Old installation checks also include one server's initialize; keep it with the MCP result.
    if values.get("서버 연결"):
        tools += " · 서버 연결 " + legacy_cell(values["서버 연결"])
    settings = result_label(summary.get("protected_configs"))
    body += ["설치 확인", f"  하네스 응답  {clean(answer)}", f"  게이트웨이 MCP 목록  {clean(tools)}",
             f"  관리 설정 적용  {settings}"]
    servers = summary.get("servers")
    count = len(servers) if isinstance(servers, list) else servers
    body += ["승인 MCP 서버  " + (f"{count}개" if type(count) is int else "—")]
    body = [translate(line, language) for line in body]
    versions = summary.get("harnesses") or {}
    body.append(translate("하네스 판본  ", language) + (" · ".join(f"{name} {clean(version)}" for name, version in sorted(versions.items())
                                              if name in {"claude", "codex", "gemini", "opencode"}) or "—"))
    body += [translate("최근 엔드포인트 차단", language)]
    body += [f"  {clean(row.get('at', '—'))}  " + translate("엔드포인트에서 차단", language) for row in blocks[-5:]] or ["  —"]
    if not next_line:
        next_line = {"pending": "관리자 활성화 대기", "quarantined": "관리자에게 격리 해제 요청",
                     "revoked": "새 키트로 다시 설치"}.get(summary.get("state"),
                         "하네스 실행" if connected else "게이트웨이 연결 점검")
    footer = [translate("다음 할 일  " + clean(next_line), language), translate(KEYS, language)]
    content = (body[:max(0, height - 2)] + footer[-height:]) if height else []
    return "\n".join(clip(line, max(0, columns - 1)) for line in content)


def enable_vt(stream):
    """Return a restoration callback, or None when the console cannot do VT."""
    if os.name != "nt":
        return (lambda: None) if os.environ.get("TERM", "dumb") not in ("", "dumb") else None
    import ctypes
    import msvcrt
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    handle, mode = msvcrt.get_osfhandle(stream.fileno()), wintypes.DWORD()
    if not kernel.GetConsoleMode(handle, ctypes.byref(mode)) or not kernel.SetConsoleMode(handle, mode.value | 0x0004):
        return None
    return lambda: kernel.SetConsoleMode(handle, mode.value)


class Screen:
    def __init__(self, title="MINT 엔드포인트", output=None, input=None, language="ko"):
        self.output, self.input = output or sys.stdout, input or sys.stdin
        self.title, self.rows, self.cells, self.next, self.notes = title, [], [], "", []
        self.language = language
        self.summary, self.window = {}, None
        self._restore_vt = self._terminal = None
        self._handlers = {}
        self.resume()

    def resume(self):
        if self.window is not None or os.environ.get("MCPGW_PLAIN") or not (self.input.isatty() and self.output.isatty()):
            return
        try:
            self._restore_vt = enable_vt(self.output)
            if self._restore_vt is None:
                return
            if os.name != "nt":
                import termios
                import tty
                self._terminal = termios.tcgetattr(self.input.fileno())
                tty.setcbreak(self.input.fileno())
            self.window = self
            for name in ("SIGINT", "SIGTERM", "SIGHUP"):
                sig = getattr(signal, name, None)
                if sig is not None:
                    self._handlers[sig] = signal.getsignal(sig)
                    signal.signal(sig, self._signal)
            atexit.register(self.stop)
            self.output.write(ENTER)
            self.output.flush()
        except (OSError, ValueError, AttributeError):
            self.stop()

    def _signal(self, sig, context):
        previous = self._handlers.get(sig)
        self.stop()
        if callable(previous):
            previous(sig, context)
        else:
            raise SystemExit(128 + sig)

    def stop(self):
        try:
            if self.window is not None:
                self.output.write(LEAVE)
                self.output.flush()
        finally:
            self.window = None
            if self._terminal is not None:
                import termios
                termios.tcsetattr(self.input.fileno(), termios.TCSADRAIN, self._terminal)
                self._terminal = None
            if self._restore_vt is not None:
                self._restore_vt()
                self._restore_vt = None
            for sig, handler in self._handlers.items():
                signal.signal(sig, handler)
            self._handlers.clear()
            atexit.unregister(self.stop)

    pause = stop

    def text(self):
        size = shutil.get_terminal_size((80, 30))
        return frame(self.summary, self.rows, self.cells, self.next, size.columns, size.lines, language=self.language)

    def draw(self, extra=()):
        if self.window is not None:
            self.output.write("\x1b[H\x1b[2J" + self.text().replace("\n", "\r\n"))
            self.output.flush()

    def read_key(self, timeout=2):
        deadline = time.monotonic() + timeout
        while self.window is not None:
            if os.name == "nt":
                import msvcrt
                if msvcrt.kbhit():
                    key = msvcrt.getwch()
                    if key in ("\x00", "\xe0"):
                        msvcrt.getwch()
                    else:
                        return key.lower()
                time.sleep(min(.05, max(0, deadline - time.monotonic())))
            else:
                import select
                if select.select([self.input], [], [], max(0, deadline - time.monotonic()))[0]:
                    return os.read(self.input.fileno(), 1).decode("ascii", errors="ignore").lower()
            if time.monotonic() >= deadline:
                break
        return ""

    def step(self, label):
        self.close_step()
        self.rows.append([label, time.monotonic(), None, "…"])
        if self.window is None:
            print(f"[{clean(label)}]", file=self.output, flush=True)
        self.draw()

    def close_step(self, mark="✓"):
        if self.rows and self.rows[-1][2] is None:
            self.rows[-1][2] = round(time.monotonic() - self.rows[-1][1])
            self.rows[-1][3] = mark
        self.draw()

    def say(self, text):
        self.notes.append(text)
        if self.window is None:
            print(clean(text), file=self.output, flush=True)

    def result(self, cells, next_line):
        self.cells, self.next = cells, next_line
        if self.window is None:
            for name, value in cells:
                print(f"{clean(name)}: {clean(value)}", file=self.output, flush=True)
            print("다음 할 일: " + clean(next_line), file=self.output, flush=True)
        self.draw()

    def finish(self, wait=8):
        if self.window is None:
            return
        try:
            self.draw()
            self.read_key(wait)
        finally:
            self.stop()
        print(self.text(), file=self.output, flush=True)


def live(read, check=None, screen=None):
    """Read snapshots afresh; an interrupted read never keeps a stale success on screen."""
    screen = screen or Screen()
    results = queue.Queue()
    checking = False

    def measure(summary):
        try:
            results.put(check(summary))
        except Exception:
            # Exceptions can contain credentials from a header helper; show only the failed result.
            results.put([("하네스 응답", "실패"), ("게이트웨이 MCP 목록", "실패")])

    try:
        while True:
            screen.next = ""
            try:
                screen.summary = read()
                if not isinstance(screen.summary, dict):
                    raise ValueError("invalid snapshot")
            except (OSError, ValueError, TypeError):
                screen.summary = {}
            try:
                screen.cells = results.get_nowait()
                checking = False
            except queue.Empty:
                pass
            screen.draw()
            if screen.window is None:
                print(screen.text(), file=screen.output)
                break
            key = screen.read_key(2)
            if key in ("q", "\x1b"):
                break
            if key == "c" and check and not checking:
                checking = True
                screen.cells = [("하네스 응답", "진행 중"), ("게이트웨이 MCP 목록", "진행 중")]
                screen.draw()
                threading.Thread(target=measure, args=(screen.summary,), daemon=True).start()
    finally:
        screen.stop()
