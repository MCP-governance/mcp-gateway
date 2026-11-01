"""Shared, credential-free terminal view of the kit's existing status snapshots."""
import atexit
import json
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
from pathlib import Path

ENTER = "\x1b[?1049h\x1b[?25l"
LEAVE = "\x1b[0m\x1b[?25h\x1b[?1049l"
STATES = {"active": "활성", "pending": "활성화 대기", "quarantined": "격리됨",
          "revoked": "등록 해제됨", "removed": "제거됨", "unknown": "확인 필요"}


def wait_summary(path, since=0, seconds=60):
    """Installation output uses the service report, never the earlier enrollment response."""
    deadline = time.monotonic() + seconds
    while True:
        summary = {}
        try:
            candidate = Path(path).read_text(encoding="utf-8")
            candidate = json.loads(candidate)
            updated = candidate.get("updated") if isinstance(candidate, dict) else None
            state = candidate.get("state") if isinstance(candidate, dict) else None
            now = time.time()
            if (type(updated) in (int, float) and since <= updated <= now
                    and now - updated <= 180 and isinstance(state, str) and state in STATES):
                summary = candidate
        except (OSError, ValueError):
            pass
        if summary.get("state") in ("active", "quarantined", "revoked") or time.monotonic() >= deadline:
            return summary
        time.sleep(2)


TEXT_EN = {
    "MCP 연결 관리": "MCP connection management", "로그인": "Sign in", "상태 확인": "Status",
    "승인된 MCP": "Approved MCP", "장치": "Device", "게이트웨이": "Gateway",
    "MINT 엔드포인트": "MINT endpoint", "엔드포인트에서 차단": "Blocked at endpoint",
    "연결 상태": "Connection", "연결됨": "Connected", "연결 끊김": "Disconnected",
    "관리 상태": "Management", "상태": "Status", "연결 방식": "Mode", "간편 모드": "Simple mode",
    "게이트웨이 판정": "Gateway decision", "격리 계정": "Isolated account",
    "활성화 대기": "Waiting for activation", "서비스 중지": "Service stopped", "활성": "Active", "격리됨": "Quarantined",
    "등록 해제됨": "Unregistered", "철회됨": "Revoked", "제거됨": "Removed", "확인 필요": "Needs attention",
    "승인 서버": "Approved servers", "승인 MCP 서버": "Approved MCP servers", "로컬 MCP 준비": "Local MCP ready", "직원 문서 폴더": "Document folders", "새로 반영": "Newly added", "Enter 돌아가기": "Enter to go back", "설치 진행 중": "Installing", "설치됨": "installed", "열린 하네스는 다시 시작": "restart open harnesses",
    "하네스 판본": "Harness versions", "하네스 응답": "Harness response", "하네스": "Harnesses",
    "최근 보고": "Last report", "최근 엔드포인트 차단": "Recent endpoint blocks",
    "게이트웨이 MCP 목록": "Gateway MCP list", "MCP 목록": "MCP list", "관리 설정": "Managed settings", "엔드포인트 · MCP 연결 관리": "Endpoint · MCP connection management",
    "연결": "Connection", "점검": "Checks", "닫기": "Close", "창을 넓혀 주세요": "Widen the window", "로그인 필요": "Sign-in needed", "게이트웨이 응답 정상": "Gateway answers",
    "설치 단계": "Installation steps", "설치 확인": "Installation checks", "설치 중": "Installing",
    "설치 완료": "Installed", "설치 실패": "Installation failed", "차단 발생": "Blocked",
    "관리 설정 적용": "Managed settings applied", "서버 연결": "Server connection", "서버": "Servers",
    "일부 실패": "Some failed", "로그인됨": "Signed in", "모델 로그인": "Model sign-in", "승인 MCP": "Approved MCP", "응답": "responding", "진행 중": "In progress", "완료": "Done", "실패": "Failed", "도구": "Tools",
    "관리자 활성화 대기": "Waiting for an administrator", "관리자에게 격리 해제 요청": "Ask an administrator to release",
    "새 키트로 다시 설치": "Reinstall with a new kit", "하네스 실행": "Run a harness",
    "게이트웨이 연결 점검": "Check gateway connection", "다음 할 일": "Next step",
    "종료": "Quit", "지금 점검": "Check now", "새로고침": "Refresh", "점검 설정 없음": "No check settings",
}


# ── 표시 계층 ────────────────────────────────────────────────────────────────────────────────
# 색은 의미가 있을 때만 쓴다(clig.dev). 값은 웹 콘솔·로컬 화면의 어두운 테마 토큰(console.css)과 같다: 브랜드 남색 강조,
# 회색 라벨, 허용 초록·경보 노랑·차단 빨강. 표시 장치가 못 그리는 단계로 내려간다
# (Lip Gloss와 같은 truecolor → 256 → 16 → 없음, NO_COLOR·TERM=dumb·파이프면 색 없음).
ROLES = {
    "accent": ((167, 197, 255), 153, 94), "accent2": ((183, 208, 255), 153, 94), "title": ((237, 242, 249), 255, 97),
    "dim": ((161, 176, 195), 248, 90), "border": ((117, 134, 157), 244, 90), "ok": ((139, 224, 173), 115, 32),
    "warn": ((243, 206, 121), 222, 33), "err": ((255, 167, 175), 217, 31),
}
UTF = {"tl": "╭", "tr": "╮", "bl": "╰", "br": "╯", "h": "─", "v": "│", "ok": "✓", "err": "✗", "warn": "!",
       "dot": "●", "none": "·", "next": "▸", "spin": "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"}
ASCII = {"tl": "+", "tr": "+", "bl": "+", "br": "+", "h": "-", "v": "|", "ok": "v", "err": "x", "warn": "!",
         "dot": "*", "none": "-", "next": ">", "spin": "|/-\\"}
KEYS = "q 종료 · c 지금 점검 · r 새로고침 · s 승인된 MCP"
KEY_ITEMS = (("q", "종료"), ("c", "지금 점검"), ("r", "새로고침"), ("s", "승인된 MCP"))
FINISH_ITEMS = (("Enter", "닫기"),)
TITLE = "엔드포인트 · MCP 연결 관리"


def color_profile(stream=None):
    """'none' | '16' | '256' | 'true' for this output."""
    stream = stream or sys.stdout
    try:
        tty = stream.isatty()
    except (AttributeError, ValueError):
        tty = False
    if not tty or os.environ.get("NO_COLOR") or os.environ.get("TERM", "") == "dumb":
        return "none"
    if os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit") or os.environ.get("WT_SESSION"):
        return "true"
    if "256color" in os.environ.get("TERM", "") or os.name == "nt":
        return "256"
    return "16"


def glyphs_for(stream=None):
    encoding = getattr(stream or sys.stdout, "encoding", "") or ""
    return UTF if "utf" in encoding.lower() else ASCII


def paint(text, role, profile, bold=False, reverse=False):
    if profile == "none" or not text:
        return text
    codes = ["1"] if bold else []
    if reverse:
        codes.append("7")
    if role:
        rgb, c256, c16 = ROLES[role]
        codes.append("38;2;%d;%d;%d" % rgb if profile == "true" else f"38;5;{c256}" if profile == "256" else str(c16))
    return "\x1b[" + ";".join(codes) + "m" + text + "\x1b[0m" if codes else text


def app_mark(profile):
    """The console's app-bar mark: MINT on a brand tile (reverse video keeps it legible on any terminal background)."""
    return paint(" MINT ", "accent", profile, bold=True, reverse=True) if profile != "none" else "MINT"


def banner(ascii_only=False):
    return ["MINT  " + TITLE]


def strip_ansi(text):
    return re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text)


class Line:
    """A rendered line plus its display width; colour codes never count towards width."""
    __slots__ = ("text", "cells")

    def __init__(self, text="", cells=None):
        self.text, self.cells = text, width(strip_ansi(text)) if cells is None else cells


def fit(text, room):
    text = clean(text)
    return text if width(text) <= room else clip(text, max(0, room - 1)) + "…"


def chunks(text, room):
    """칸 폭으로 나눈 줄들. 띄어쓰기에서 나누고, 한 낱말이 한 줄보다 길 때만 낱말 안에서 나눈다."""
    lines = []
    for word in re.split(r"(?<= )", text):
        if lines and width(lines[-1] + word.rstrip()) <= room:
            lines[-1] += word
            continue
        while width(word.rstrip()) > room:
            cut = clip(word, room, trusted=True) or word[:1]  # 걸러 내기는 부른 쪽에서 이미 했다
            lines.append(cut)
            word = word[len(cut):]
        if word:
            lines.append(word)
    return [line.rstrip() for line in lines]


def card(title, rows, inner, profile, g, role="border", title_role="title"):
    """Rounded box with the title in the top border (Lip Gloss RoundedBorder); rows are Lines no wider than inner
    (a row may be a list of Lines: a wrapped value)."""
    rows = [x for r in rows for x in (r if isinstance(r, list) else [r])]
    b = lambda text: paint(text, role, profile)
    title = fit(title, max(1, inner - 4))
    top = (b(g["tl"] + g["h"]) + " " + paint(title, title_role, profile, bold=True) + " " +
           b(g["h"] * max(0, inner - width(title) - 1) + g["tr"]))
    body = [b(g["v"]) + " " + r.text + " " * max(0, inner - r.cells) + " " + b(g["v"]) for r in rows]
    return [Line(top, inner + 4), *[Line(x, inner + 4) for x in body], Line(b(g["bl"] + g["h"] * (inner + 2) + g["br"]), inner + 4)]


def mark_for(value, profile, g, spin=0):
    text = str(value)
    if "진행 중" in text or "In progress" in text:
        return paint(g["spin"][spin % len(g["spin"])], "warn", profile), "warn"
    if "로그인 필요" in text or "대기" in text or "Waiting" in text:
        return paint(g["warn"], "warn", profile, bold=True), "warn"
    if "실패" in text or "Failed" in text or "중지" in text or "stopped" in text or "끊김" in text:
        return paint(g["err"], "err", profile, bold=True), "err"
    if "완료" in text or "Done" in text or "적용" in text or "로그인됨" in text or "Signed in" in text or text.startswith("활성") or "Active" in text:
        return paint(g["ok"], "ok", profile, bold=True), "ok"
    return paint(g["none"], "dim", profile), None


def kv(label, value, inner, profile, g, label_width=10, role=None, marked=False, spin=0, indent=False, wrap=False):
    """라벨(회색·고정 폭)과 값. marked면 결과 기호를 앞에 붙이고 값 색을 결과에 맞춘다. indent는 기호 칸만 비운다.
    wrap이면 긴 값을 자르지 않고 값 칸 아래로 이어 쓴다(Line 목록을 돌려준다)."""
    lead, lead_cells = ("  ", 2) if indent else ("", 0)
    if marked:
        symbol, role = mark_for(value, profile, g, spin)
        lead, lead_cells = symbol + " ", 2
    label = fit(label, label_width)
    room = max(1, inner - lead_cells - label_width - 2)
    bold = role in ("ok", "err", "warn")
    if wrap and width(clean(value)) > room:
        first, *rest = chunks(clean(value), room)
        pad = " " * (lead_cells + label_width + 2)
        head = lead + paint(label, "dim", profile) + " " * (label_width - width(label) + 2) + paint(first, role, profile, bold=bold)
        return [Line(head, len(pad) + width(first))] + [Line(pad + paint(x, role, profile, bold=bold), len(pad) + width(x)) for x in rest]
    value = fit(value, room)
    text = (lead + paint(label, "dim", profile) + " " * (label_width - width(label) + 2) +
            paint(value, role, profile, bold=bold))
    return Line(text, lead_cells + label_width + 2 + width(value))


def keybar(items, profile, language="ko", room=999):
    """키 안내 한 줄. 폭이 모자라면 뒤쪽 항목을 통째로 뺀다(단어 중간에서 줄이 넘어가지 않게)."""
    plain = profile == "none"
    parts, cells = [], 0
    for key, label in items:
        label = translate(label, language)
        need = width(key) + 1 + width(label) + (0 if plain else 2)
        gap = (3 if plain else 3) if parts else 0
        if cells + gap + need > room:
            break
        parts.append(f"{key} {label}" if plain else
                     paint(f" {key} ", "accent", profile, bold=True, reverse=True) + " " + paint(label, "dim", profile))
        cells += gap + need
    return Line((" · " if plain else "   ").join(parts), cells)


def notice_line(text, role, inner, profile, g):
    symbol = mark_for("실패" if role == "err" else "로그인 필요" if role == "warn" else "완료", profile, g)[0]
    text = fit(text, inner - 2)
    return Line(symbol + " " + paint(text, role, profile, bold=True), 2 + width(text))


def login_inputs(address, notice=""):
    import getpass
    import warnings
    if not sys.stdin.isatty():
        # 파이프·리다이렉트 실행은 비밀번호를 칠 수 없다. 빈 입력으로 죽기 전에 화면 없이 멈춘다.
        raise ValueError("로그인: 터미널 입력 필요")
    terminal = sys.stdout.isatty()
    restore = enable_vt(sys.stdout) if terminal else None
    profile = color_profile(sys.stdout) if restore else "none"
    g = glyphs_for(sys.stdout)
    columns = shutil.get_terminal_size((80, 24)).columns
    inner = max(24, min(60, columns - 8))
    try:
        if restore:
            print("\x1b[?1049h\x1b[2J\x1b[H", end="")
        print()
        print("  " + app_mark(profile) + "  " + paint(TITLE, "dim", profile))
        print()
        rows = [kv("게이트웨이", address, inner, profile, g, 10)]
        if notice:
            rows += [Line(""), notice_line(notice, "err", inner, profile, g)]
        for line in card("로그인", rows, inner, profile, g):
            print("  " + line.text)
        print()
        arrow = paint(g["next"], "accent", profile, bold=True)
        selected = input(f"  {arrow} " + paint("게이트웨이 ", "dim", profile) + paint(f"[Enter {fit(address, 40)}] ", "dim", profile)).strip() or address
        username = input(f"  {arrow} " + paint("아이디     ", "dim", profile)).strip()
        # getpass's stdin fallback echoes a secret; fail instead when a secure terminal is unavailable.
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            try:
                password = getpass.getpass(f"  {arrow} " + paint("비밀번호   ", "dim", profile))
            except getpass.GetPassWarning:
                raise ValueError("로그인: 보안 입력 필요") from None
        return selected, username, password
    finally:
        if restore:
            print(LEAVE, end="", flush=True)
            restore()


def source_menu(address):
    """승인된 MCP 메뉴. 읽을 결과를 남겼으면 True, 그냥 닫았으면 None."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("kit_access", Path(__file__).with_name("kit_access.py"))
    access = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(access)
    profile, g = color_profile(sys.stdout), glyphs_for(sys.stdout)
    inner = max(30, min(70, shutil.get_terminal_size((80, 24)).columns - 8))

    def show(title, rows):
        print()
        for line in card(title, rows, inner, profile, g):
            print("  " + line.text)

    try:
        servers = access.receive(address, {"action": "list"})
    except (OSError, ValueError, KeyError, TypeError):
        show("승인된 MCP", [notice_line("목록을 받지 못했습니다", "err", inner, profile, g)])
        return True
    if not servers:
        show("승인된 MCP", [Line(paint("—", "dim", profile), 1)])
        return True
    rows = []
    for i, server in enumerate(servers, 1):
        kind = "소스 받기" if server.get("source_available") else "원격 연결"
        key = paint(f" {i} ", "accent", profile, bold=True, reverse=True) if profile != "none" else f"[{i}]"
        key_cells = width(str(i)) + 2
        name = fit(server.get("display_name") or server.get("server_id", "—"), max(4, inner - key_cells - width(kind) - 3))
        gap = max(1, inner - key_cells - 1 - width(name) - width(kind))
        rows.append(Line(key + " " + name + " " * gap + paint(kind, "accent" if server.get("source_available") else "dim", profile),
                         key_cells + 1 + width(name) + gap + width(kind)))
    show(f"승인된 MCP · {len(servers)}", rows)
    try:
        selected = input("\n  " + paint(g["next"], "accent", profile, bold=True) + " " + paint("번호 (Enter 닫기) ", "dim", profile)).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return
    if not selected:
        return
    if not selected.isdigit() or not 1 <= int(selected) <= len(servers):
        show("소스 받기", [notice_line("번호 확인 필요", "warn", inner, profile, g)])
        return True
    server = servers[int(selected) - 1]
    name = server.get("display_name") or server.get("server_id", "—")
    if not server.get("source_available"):
        show("소스 받기", [kv("서버", name, inner, profile, g, 6), kv("소스", "원격 연결 서버", inner, profile, g, 6, "dim")])
        return True
    print("\n  " + paint(g["spin"][0], "warn", profile) + " " + paint("받는 중", "dim", profile), flush=True)
    try:
        target = access.receive(address, {"action": "download", "server": server["server_id"], "commit": server["commit_sha"]})
    except (OSError, ValueError, KeyError, TypeError):
        show("소스 받기", [kv("서버", name, inner, profile, g, 6), kv("결과", "실패", inner, profile, g, 6, "err")])
        return True
    show("소스 받기", [kv("서버", name, inner, profile, g, 6), kv("결과", "완료", inner, profile, g, 6, "ok"),
                     kv("파일", str(target), inner, profile, g, 6, "accent")])
    return True


def translate(value, language="ko"):
    if language != "en":
        return value
    text = re.sub("|".join(map(re.escape, sorted(TEXT_EN, key=len, reverse=True))),
                  lambda match: TEXT_EN[match[0]], value)
    text = re.sub(r"(\d+(?:\.\d+)?)초", r"\1s", text)
    return re.sub(r"(\d+)개", r"\1", text)


def clean(value, trusted=False):
    # Never print arbitrary errors, terminal controls or credential-shaped text from a probe.
    # trusted: a sentence the kit wrote itself (a path in a command is not a token); only controls go.
    text = str(value)
    if not trusted and re.search(r"(?i)bearer|token|password|secret|authorization|eyJ[A-Za-z0-9_-]+\.|[A-Za-z0-9_+/=-]{32,}", text):
        return "—"
    return "".join(c for c in text if not unicodedata.category(c).startswith("C"))


def width(text):
    return sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def clip(text, room, trusted=False):
    out, used = "", 0
    for c in clean(text, trusted):
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
    if "로그인 필요" in text:
        return "로그인 필요"
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


def _badge(summary, rows, now, stale):
    connected = summary.get("connected") and 0 <= now - (summary.get("updated") or 0) <= stale
    badge, role = ("연결됨", "ok") if connected else ("연결 끊김", "err")
    if rows and not summary:
        badge, role = ("설치 중", "warn") if any(row[2] is None for row in rows) else ("설치 완료", "ok")
    if any(row[3] == "✗" for row in rows):
        badge, role = "설치 실패", "err"
    blocks = summary.get("blocks") or []
    if connected and blocks:
        try:
            age = now - datetime.fromisoformat(blocks[-1]["at"].replace("Z", "+00:00")).timestamp()
            if 0 <= age <= 300:
                badge, role = "차단 발생", "warn"
        except (ValueError, KeyError, TypeError, AttributeError):
            pass
    return badge, role, connected


def _server_names(summary):
    names = summary.get("server_names")
    if isinstance(names, dict):
        return [str(v) for v in names.values()]
    if isinstance(names, list):
        return [str(v) for v in names]
    servers = summary.get("names") or summary.get("servers")
    return [str(v) for v in servers] if isinstance(servers, list) else []


def _ago(seconds, language="ko"):
    seconds = max(0, int(seconds))
    unit, value = ("s", seconds) if seconds < 60 else ("m", seconds // 60) if seconds < 3600 else ("h", seconds // 3600)
    if language == "en":
        return f"{value}{unit} ago"
    return f"{value}" + {"s": "초", "m": "분", "h": "시간"}[unit] + " 전"


def layout(summary, rows=(), cells=(), next_line="", columns=80, lines=30, now=None, stale=180, language="ko",
           profile="none", g=UTF, keys=KEY_ITEMS, spin=0, tabs=None):
    """화면 한 장을 Line 목록으로 만든다. 표시 높이를 넘으면 덜 중요한 카드부터 줄인다."""
    now = time.time() if now is None else now
    t = lambda text: translate(text, language)
    if columns < 44 or lines < 12:
        message = t("창을 넓혀 주세요") + " (44×12)"
        return [Line(fit(message, max(0, columns - 1)))][: max(0, lines - 1)]
    badge, badge_role, connected = _badge(summary, rows, now, stale)
    wide = columns >= 100
    total = min(columns - 2, 132)
    col = (total - 3) // 2 if wide else total
    inner = col - 4
    lab = lambda *names: min(20, max(width(t(n)) for n in names))  # 카드마다 가장 긴 라벨에 맞춘다

    # 연결
    state = STATES.get(summary.get("state"), "—")
    lw = lab("관리 상태", "연결 방식", "장치", "게이트웨이", "최근 보고")
    state_role = {"활성": "ok", "활성화 대기": "warn", "격리됨": "err", "등록 해제됨": "err", "제거됨": "err"}.get(state)
    connection = [kv(t("관리 상태"), t(state), inner, profile, g, lw, state_role),
                  kv(t("연결 방식"), t({"simple": "간편 모드", "isolated": "격리 계정"}.get(summary.get("mode"), "—")), inner, profile, g, lw),
                  kv(t("장치"), clean(summary.get("user") or summary.get("endpoint_id") or "—"), inner, profile, g, lw),
                  kv(t("게이트웨이"), clean(summary.get("gateway") or "—"), inner, profile, g, lw, "accent")]
    if summary.get("updated"):
        report = time.strftime("%H:%M:%S", time.localtime(summary["updated"])) + " · " + _ago(now - summary["updated"], language)
    else:
        report = "—"
    connection.append(kv(t("최근 보고"), report, inner, profile, g, lw))

    # 점검
    values = dict(cells)
    answer = values.get("하네스 응답", legacy_cell(values.get("모델 응답", "—")))
    signed = summary.get("model_signed_in") if isinstance(summary.get("model_signed_in"), dict) else {}
    # 하네스마다 로그인 상태(서비스가 30초마다 읽음). 응답 확인은 실제로 재 본 경우에만 따로 보인다.
    logins = " · ".join(f"{name} " + ("로그인됨" if signed[name] else "로그인 필요")
                        for name in ("claude", "codex") if type(signed.get(name)) is bool)
    tools = values.get("게이트웨이 MCP 목록", legacy_cell(values.get("도구", "—")))
    # Linux 점검의 「10개 (서버 2/2)」는 승인 MCP 2개 중 2개가 응답했고 도구가 10개라는 뜻이다. 그 말 그대로 보인다.
    counted = re.fullmatch(r"(\d+)개 \(서버 (\d+)/(\d+)\)", clean(values.get("도구", "")))
    if counted:
        found, answered, approved = map(int, counted.groups())
        tools = (f"완료 · 승인 MCP {approved}개 응답" if answered == approved
                 else f"일부 실패 · 승인 MCP {answered}/{approved}개 응답") + f" · 도구 {found}개"
    if values.get("서버 연결") and legacy_cell(values["서버 연결"]) != "완료":
        tools += " · " + t("서버 연결") + " " + legacy_cell(values["서버 연결"])
    versions = summary.get("harnesses") or {}
    version_text = " · ".join(f"{name} {clean(version) if version else t('설치됨')}" for name, version in sorted(versions.items())
                              if name in {"claude", "codex", "gemini", "opencode"}) or "—"
    lw = lab("모델 로그인", "하네스 응답", "MCP 목록", "관리 설정", "하네스 판본")
    checks = ([kv(t("모델 로그인"), t(logins), inner, profile, g, lw, marked=True, wrap=True)] if logins else []) + [
              *([kv(t("하네스 응답"), t(clean(answer)), inner, profile, g, lw, marked=True, spin=spin, wrap=True)]
                if answer != "—" or not logins else []),
              kv(t("MCP 목록"), t(clean(tools)), inner, profile, g, lw, marked=True, spin=spin, wrap=True),
              kv(t("관리 설정"), t(result_label(summary.get("protected_configs"))), inner, profile, g, lw, marked=True),
              kv(t("하네스 판본"), version_text, inner, profile, g, lw, indent=True, wrap=True)]

    # 설치 단계
    steps = []
    for label, started, seconds, mark in rows:
        spent = seconds if seconds is not None else max(0, int(time.monotonic() - started))
        status = "진행 중" if seconds is None else "실패" if mark == "✗" else "완료"
        symbol = mark_for(status, profile, g, spin)[0]
        label_text = fit(t(label), max(4, inner - 10))
        right = t(f"{spent}초")
        steps.append(Line(symbol + " " + label_text + " " * max(1, inner - 2 - width(label_text) - width(right)) +
                          paint(right, "dim", profile), inner))

    # 승인된 MCP
    names = _server_names(summary)
    count = summary.get("servers")
    count = len(count) if isinstance(count, list) else count if type(count) is int else len(names) if names else None
    local = summary.get("local") if isinstance(summary.get("local"), dict) else {}
    lw = lab("승인 MCP 서버", *(("로컬 MCP 준비", "직원 문서 폴더") if local.get("total") else ()))
    servers = [kv(t("승인 MCP 서버"), t(f"{count}개") if type(count) is int else "—", inner, profile, g, lw)]
    if local.get("total"):
        ready = f"{local.get('ready', 0)}/{local['total']}"
        servers.append(kv(t("로컬 MCP 준비"), ready + (" · " + t(clean(local["note"])) if local.get("note") else ""), inner,
                          profile, g, lw, "ok" if local.get("ready") == local["total"] else "warn", wrap=True))
        servers.append(kv(t("직원 문서 폴더"), ", ".join(clean(d) for d in local.get("documents") or []) or "—",
                          inner, profile, g, lw, wrap=True))
    if names:
        joined = ", ".join(clean(n) for n in names)
        servers.append([Line(paint(x, "title", profile), width(x)) for x in chunks(joined, inner)])
    added = summary.get("added") if isinstance(summary.get("added"), dict) else {}
    fresh = [clean(s) for s in added.get("servers") or [] if s in (summary.get("names") or [])]
    if fresh and isinstance(added.get("at"), (int, float)) and 0 <= now - added["at"] < 3600:
        # 이미 열려 있는 하네스는 새 서버를 모른다(재시작해야 보인다).
        text = t("새로 반영") + "  " + ", ".join(fresh) + " · " + t("열린 하네스는 다시 시작")
        servers.append([Line(paint(x, "warn", profile), width(x)) for x in chunks(text, inner)])

    # 최근 엔드포인트 차단
    blocks = summary.get("blocks") or []
    block_rows = [Line(paint(fit(clean(row.get("at", "—"))[11:19] or "—", 8), "dim", profile) + "  " +
                       paint(t("엔드포인트에서 차단"), "warn", profile), 10 + width(t("엔드포인트에서 차단")))
                  for row in blocks[-5:] if isinstance(row, dict)] or [Line(paint("—", "dim", profile), 1)]

    # 다음 할 일
    if not next_line and rows and rows[-1][2] is None:
        next_line = "설치 진행 중"
    if not next_line:
        next_line = {"pending": "관리자 활성화 대기", "quarantined": "관리자에게 격리 해제 요청",
                     "revoked": "새 키트로 다시 설치"}.get(summary.get("state"), "하네스 실행" if connected else "게이트웨이 연결 점검")
    label, _, command = clean(t(next_line), trusted=True).partition(": ")
    arrow = paint(g["next"], "accent", profile, bold=True)
    room = total - 6  # 다음 할 일 카드 안쪽 폭
    label = fit(label, room - 2)
    head = arrow + " " + paint(label, "title", profile, bold=True)
    if command and width(label) + 5 + width(command) <= room:
        nxt = [Line(head + "   " + paint(command, "accent", profile, bold=True), width(label) + 5 + width(command))]
    else:
        # 복사해 붙일 명령은 자르지 않고 줄을 나눠 전부 보인다.
        nxt = [Line(head, 2 + width(label))]
        nxt += [Line("  " + paint(part, "accent", profile, bold=True), 2 + width(part)) for part in chunks(command, room - 2)]

    # 높이가 모자라면 덜 중요한 카드를 통째로 뺀다(카드를 중간에서 자르지 않는다). 다음 할 일·키 안내는 늘 남는다.
    def assemble(big_logo, step_limit, show_versions, dropped, compact):
        out = [] if compact else [Line("")]
        # The console's app bar: the mark, the product line and the connection state; no block-letter logo.
        title = t(TITLE)
        tile = 4 if profile == "none" else 6
        head = app_mark(profile) + "  " + paint(title, "dim", profile)
        head_cells = tile + 2 + width(title)
        pill_text = g["dot"] + " " + t(badge)
        if head_cells + 2 + width(pill_text) > total:
            head, head_cells = app_mark(profile), tile
        gap = max(2, total - head_cells - width(pill_text))
        out.append(Line(" " + head + " " * gap + paint(pill_text, badge_role, profile, bold=True), 1 + head_cells + gap + width(pill_text)))
        if tabs is not None:
            out.append(Line(" " + tabs.text, 1 + tabs.cells))
        if not compact:
            out.append(Line(" " + paint(g["h"] * total, "border", profile), 1 + total))
        cards = []
        if "connection" not in dropped:
            cards.append(card(t("연결"), connection, inner, profile, g))
        if "checks" not in dropped:
            check_rows = checks if show_versions else checks[:-1]  # 마지막 줄이 하네스 판본
            cards.append(card(t("점검") if cells else t("설치 확인") if rows else t("점검"), check_rows, inner, profile, g))
        if rows and step_limit:
            cards.append(card(t("설치 단계"), steps[-step_limit:], inner, profile, g))
        if "servers" not in dropped:
            cards.append(card(t("승인된 MCP"), servers, inner, profile, g))
        # 간편 모드는 커널 차단이 없다: 기록이 없으면 늘 비어 있을 카드를 그리지 않는다.
        if "blocks" not in dropped and (blocks or summary.get("mode") != "simple"):
            cards.append(card(t("최근 엔드포인트 차단"), block_rows, inner, profile, g))
        if wide:
            columns_ = [[], []]
            for c in cards:
                columns_[0 if len(columns_[0]) <= len(columns_[1]) else 1] += c
            for i in range(max(len(columns_[0]), len(columns_[1]))):
                a = columns_[0][i] if i < len(columns_[0]) else Line(" " * col, col)
                b = columns_[1][i] if i < len(columns_[1]) else Line("", 0)
                out.append(Line(" " + a.text + " " * max(0, col - a.cells) + "  " + b.text, 1 + col + 2 + b.cells))
        else:
            for c in cards:
                out += [Line(" " + x.text, 1 + x.cells) for x in c]
        out += [Line(" " + x.text, 1 + x.cells) for x in card(t("다음 할 일"), nxt, total - 4, profile, g, "accent", "accent")]
        if keys:
            bar = keybar(keys, profile, language, total)
            out.append(Line(" " + bar.text, 1 + bar.cells))
        return out

    height = max(0, lines - 1)
    # 설치 중에는 진행 단계가, 평소에는 점검·연결이 오래 남는다.
    drop_order = ["blocks", "servers", "connection", "checks"]
    empty = ("blocks", "servers", "connection") if rows and not summary else ()
    attempts = [(columns >= 60, 99, True, empty, False), (False, 99, True, empty, False)]
    for limit in (6, 4, 3):
        attempts.append((False, limit, True, empty, False))
    attempts.append((False, 3, False, empty, False))
    for n in range(1, len(drop_order) + 1):
        for limit in (3, 2, 1):
            attempts.append((False, limit, False, tuple(drop_order[:n]), False))
    attempts += [(False, 1, False, tuple(drop_order), True), (False, 0, False, tuple(drop_order), True)]
    for attempt in attempts:
        result = assemble(*attempt)
        if len(result) <= height:
            return result
    message = t("창을 넓혀 주세요") + " (44×12)"
    return [Line(fit(message, max(0, columns - 1)))][:height]


PAGES = ("상태", "MCP 서버", "호출 기록", "도입 요청")
# The console's chip colours for the values the tables show.
VALUE_ROLES = {"허용": "ok", "완료": "ok", "사용 가능": "ok", "승인": "ok", "기본 승인": "ok", "처리됨": "ok", "활성": "ok", "연결됨": "ok",
               "경보": "warn", "제한": "warn", "검토 대기": "warn", "검토 중": "warn", "이 PC 미지원": "warn", "동의 필요": "warn",
               "로컬": "warn", "검토 기한 만료": "warn", "검증 대기": "warn", "검증 중": "warn", "실행 안 함": "dim",
               "차단": "err", "실패": "err", "거부": "err", "검증 실패": "err", "연결 끊김": "err", "게이트웨이": "accent", "커넥터": "accent"}


def value_role(value):
    text = str(value)
    return VALUE_ROLES.get(text) or VALUE_ROLES.get(text.split(" · ")[0])


def tab_bar(active, profile, total, data=None):
    """The local screen's menu as one line; the open page is a brand tile, a waiting count rides on its tab."""
    data = data or {}
    counts = {1: len(data.get("unregistered") or []) + len(data.get("consents") or []),
              3: sum(1 for r in data.get("requests") or [] if r.get("status") == "OPEN")}
    parts, cells = [], 0
    for i, name in enumerate(PAGES):
        label = f"{i + 1} {name}" + (f" {counts[i]}" if counts.get(i) else "")
        if cells + width(label) + 3 > total:
            break
        parts.append(paint(f" {label} ", "accent", profile, bold=True, reverse=True) if i == active
                     else (f"[{label}]" if profile == "none" and i == active else " " + paint(label, "dim", profile) + " "))
        cells += width(label) + 2 + (1 if parts[:-1] else 0)
    return Line(" ".join(parts), cells)


def table_rows(columns, rows, room, profile, selected=None):
    """Columns sized to their values, the widest one shortened until the table fits; values coloured as the console's chips."""
    widths = [max(width(str(c)), *(width(str(r[i])) for r in rows)) if rows else width(str(c)) for i, c in enumerate(columns)]
    while sum(widths) + 2 * (len(widths) - 1) > room and max(widths) > 6:
        widest = widths.index(max(widths))
        widths[widest] -= 1
    cell = lambda value, i: fit(str(value), widths[i]) + " " * max(0, widths[i] - width(fit(str(value), widths[i])))
    head = "  ".join(cell(c, i) for i, c in enumerate(columns))
    out = [Line(paint(head, "dim", profile, bold=True), width(head))]
    for n, row in enumerate(rows):
        plain = "  ".join(cell(v, i) for i, v in enumerate(row))
        if n == selected:
            out.append(Line(paint(plain, "accent", profile, bold=True, reverse=True) if profile != "none" else "> " + plain, width(plain)))
            continue
        text = "  ".join(paint(cell(v, i), value_role(v), profile, bold=bool(value_role(v))) for i, v in enumerate(row))
        out.append(Line(text, width(plain)))
    return out


def console_page(screen, columns, lines, profile, g, tabs):
    """MCP 서버 · 호출 기록 · 도입 요청 with the same app bar and tab bar as the status page."""
    access, data, language = screen.access, screen.data or {}, screen.language
    t = lambda text: translate(text, language)
    if columns < 44 or lines < 12:
        return [Line(fit(t("창을 넓혀 주세요") + " (44×12)", max(0, columns - 1)))][: max(0, lines - 1)]
    total = min(columns - 2, 132)
    inner = total - 4
    badge, badge_role, _ = _badge(screen.summary, (), time.time(), 180)
    title, tile = t(TITLE), 4 if profile == "none" else 6
    pill = g["dot"] + " " + t(badge)
    head_cells = tile + 2 + width(title)
    gap = max(2, total - head_cells - width(pill))
    out = [Line(""), Line(" " + app_mark(profile) + "  " + paint(title, "dim", profile) + " " * gap + paint(pill, badge_role, profile, bold=True),
                          1 + head_cells + gap + width(pill)),
           Line(" " + tabs.text, 1 + tabs.cells), Line(" " + paint(g["h"] * total, "border", profile), 1 + total)]
    cards = []
    if screen.page == 1:
        for name, cols, rows in access.sections(data):
            cards.append((f"{name} · {len(rows)}", table_rows(cols, rows, inner, profile) if rows else [Line(paint("—", "dim", profile), 1)]))
        if data.get("consents"):
            rows = [(c["name"], f'{c["tools"]}개') for c in data["consents"]]
            cards.append((f"동의 대기 · {len(rows)}", table_rows(("서버", "도구"), rows, inner, profile)))
        rows = access.source_rows(screen.sources or [])
        cards.append((f"승인된 소스 · {len(rows)}", table_rows(("서버", "커밋", "소스"), rows, inner, profile) if rows else [Line(paint("—", "dim", profile), 1)]))
    elif screen.page == 2 and screen.detail is not None:
        call = data.get("calls", [])[screen.detail]
        pairs = access.call_detail(call, data.get("console_url", ""))
        lw = min(12, max(width(a) for a, _ in pairs))
        cards.append((f"호출 {screen.detail + 1}", [kv(a, b, inner, profile, g, lw, value_role(b) or ("accent" if a == "콘솔" else None), wrap=True)
                                                 for a, b in pairs]))
    elif screen.page == 2:
        calls = data.get("calls", [])
        rows = [(n, *row) for n, row in enumerate(access.call_rows(data), 1)]
        room = max(3, lines - 9)
        first = max(0, min(screen.sel - room // 2, len(rows) - room))
        body = table_rows(("번호", *access.CALL_COLUMNS), rows[first:first + room], inner, profile,
                          screen.sel - first if calls else None) if rows else [Line(paint("—", "dim", profile), 1)]
        cards.append((f"MCP 호출 · {len(rows)}", body))
    elif screen.page == 3:
        for name, rows in (("내 요청", access.request_rows(data)), ("도입 신청", access.application_rows(data))):
            cards.append((f"{name} · {len(rows)}", table_rows(("서버", "상태", "시각"), rows, inner, profile) if rows else [Line(paint("—", "dim", profile), 1)]))
    room = max(1, lines - 1 - len(out) - 2)
    for name, rows in cards:
        box = card(name, rows, inner, profile, g)
        if len(box) > room:
            if room < 4:
                break
            box = card(name, rows[:room - 3] + [Line(paint("…", "dim", profile), 1)], inner, profile, g)
        out += [Line(" " + x.text, 1 + x.cells) for x in box]
        room -= len(box)
    if screen.notice:
        note = fit(screen.notice, total - 2)
        out.append(Line(" " + paint(g["next"], "accent", profile, bold=True) + " " + paint(note, "accent", profile), 3 + width(note)))
    if screen.keys:
        bar = keybar(screen.keys, profile, language, total)
        out.append(Line(" " + bar.text, 1 + bar.cells))
    return out[: max(0, lines - 1)]


def page_keys(screen, check, sources):
    keys = [("q", "종료"), ("1-4", "화면")]
    if screen.page == 0:
        keys += [("c", "지금 점검")] if check else []
    if screen.page == 1 and sources:
        keys.append(("s", "소스 받기"))
    if screen.page == 2:
        keys += [("Esc", "목록")] if screen.detail is not None else [("↑↓", "선택"), ("Enter", "상세")]
    if screen.page == 3:
        keys.append(("n", "도입 요청"))
    return tuple(keys + [("o", "웹 콘솔"), ("r", "새로고침")])


def open_console(screen):
    """The console page that matches what is on screen; the address always shows, a browser only on a desktop."""
    data = screen.data or {}
    base = data.get("console_url") or ""
    if not base.startswith("https://"):
        return "콘솔 주소 확인 실패"
    calls = data.get("calls", [])
    target = (base + "#/consent" if screen.page == 1 and data.get("consents") else
              base + f'#/activity?d={calls[screen.detail]["decision_id"]}' if screen.page == 2 and screen.detail is not None
              and calls[screen.detail].get("decision_id") else
              base + "#/activity" if screen.page == 2 else base + "#/intake" if screen.page == 3 else base)
    if screen.access.can_open_browser():
        import webbrowser
        webbrowser.open(target)
    return target


def new_request(access, address):
    """The local screen's request form as three questions; the same checks as the form, said before sending."""
    profile, g = color_profile(sys.stdout), glyphs_for(sys.stdout)
    arrow = paint(g["next"], "accent", profile, bold=True)
    print("\n  " + app_mark(profile) + "  " + paint("도입 요청", "title", profile, bold=True) + "\n")
    server = input(f"  {arrow} " + paint("서버 이름 ", "dim", profile)).strip()
    source = input(f"  {arrow} " + paint("소스 주소 (https://, 없으면 Enter) ", "dim", profile)).strip()
    purpose = input(f"  {arrow} " + paint("사용 목적 (10자 이상) ", "dim", profile)).strip()
    problem = access.request_problem(server, source, purpose)
    try:
        message = problem or access.mint_request(address, server, source, purpose)
    except (OSError, ValueError, KeyError, TypeError):
        message = "엔드포인트 서비스 연결 실패"
    print("\n  " + paint(message, "err" if problem else "ok", profile, bold=True))
    input("\n  " + paint("Enter 돌아가기", "dim", profile) + " ")


def frame(summary, rows=(), cells=(), next_line="", columns=80, lines=30, now=None, stale=180, language="ko"):
    """색 없는 한 장(자동화·시험·로그용). 실제 화면과 같은 배치다."""
    out = layout(summary, rows, cells, next_line, columns, lines, now, stale, language)
    return "\n".join(clip(strip_ansi(line.text), max(0, columns - 1)) for line in out)


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
        self.keys, self.spin = (), 0  # 키를 실제로 받는 화면(live·finish)만 안내를 단다
        # The local screen's pages (mint ui) in the terminal; page 0 is the status cards, the rest need the console data.
        self.page, self.data, self.sources, self.sel, self.detail, self.notice, self.access = 0, None, [], 0, None, "", None
        self._restore_vt = self._terminal = None
        self._handlers = {}
        self._size = None
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
        if callable(previous) and previous is not signal.default_int_handler:
            previous(sig, context)
        else:
            raise SystemExit(128 + sig)

    def stop(self):
        try:
            if self.window is not None:
                self.output.write(LEAVE)
                self.output.flush()
        except (OSError, ValueError):
            pass
        finally:
            self.window = None
            if self._terminal is not None:
                try:
                    import termios
                    termios.tcsetattr(self.input.fileno(), termios.TCSADRAIN, self._terminal)
                except (OSError, ValueError):
                    pass
                self._terminal = None
            if self._restore_vt is not None:
                self._restore_vt()
                self._restore_vt = None
            for sig, handler in self._handlers.items():
                signal.signal(sig, handler)
            self._handlers.clear()
            atexit.unregister(self.stop)

    pause = stop

    def lines(self, height=None):
        size = shutil.get_terminal_size((80, 30))
        profile = color_profile(self.output)
        lines = size.lines if height is None else height
        if self.access is None:
            return layout(self.summary, self.rows, self.cells, self.next, size.columns, lines, language=self.language,
                          profile=profile, g=glyphs_for(self.output), keys=self.keys, spin=self.spin)
        total = min(size.columns - 2, 132)
        tabs = tab_bar(self.page, profile, total, self.data)
        if self.page == 0:
            return layout(self.summary, self.rows, self.cells, self.next, size.columns, lines, language=self.language,
                          profile=profile, g=glyphs_for(self.output), keys=self.keys, spin=self.spin, tabs=tabs)
        return console_page(self, size.columns, lines, profile, glyphs_for(self.output), tabs)

    def text(self, height=None):
        """화면을 닫은 뒤 스크롤백에 남기는 한 장: 같은 배치·같은 색, 높이 제한 없음."""
        try:
            return "\n".join(line.text for line in self.lines(1000 if height is None else height))
        except Exception:
            return frame(self.summary, self.rows, self.cells, self.next)

    def draw(self, extra=()):
        if self.window is None:
            return
        try:
            self.spin += 1
            body = "\r\n".join(line.text for line in self.lines())
        except Exception:
            # 표시 자체가 실패해도 키 안내는 남겨 빠져나갈 수 있게 한다.
            body = "\r\n" + translate("화면을 그리지 못했습니다", self.language) + "\r\n" + translate(KEYS, self.language)
        self.output.write("\x1b[H\x1b[2J" + body)
        self.output.flush()

    def resized(self):
        size = tuple(shutil.get_terminal_size((80, 30)))
        changed, self._size = size != self._size, size
        return changed

    def read_key(self, timeout=2):
        deadline = time.monotonic() + timeout
        while self.window is not None:
            if os.name == "nt":
                import msvcrt
                if msvcrt.kbhit():
                    key = msvcrt.getwch()
                    if key in ("\x00", "\xe0"):
                        return {"H": "up", "P": "down", "K": "left", "M": "right"}.get(msvcrt.getwch(), "")
                    return "enter" if key in ("\r", "\n") else "back" if key == "\x08" else key.lower()
                time.sleep(min(.05, max(0, deadline - time.monotonic())))
            else:
                import select
                try:
                    ready = select.select([self.input], [], [], min(.25, max(0, deadline - time.monotonic())))[0]
                except (OSError, ValueError, InterruptedError):
                    ready = []
                if ready:
                    data = os.read(self.input.fileno(), 8)
                    if data.startswith(b"\x1b") and len(data) > 1:
                        return {b"A": "up", b"B": "down", b"C": "right", b"D": "left"}.get(data[2:3], "")
                    if data[:1] in (b"\r", b"\n"):
                        return "enter"
                    if data[:1] in (b"\x7f", b"\x08"):
                        return "back"
                    return data[:1].decode("ascii", errors="ignore").lower()
            if self.resized():
                self.draw()
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

    def finish(self, wait=None):
        """설치 끝 화면은 사람이 닫을 때까지 남긴다(wait=None). 닫으면 터미널에는 결과 한 줄만 남는다."""
        if self.window is None:
            return
        try:
            self.keys = FINISH_ITEMS
            self.draw()
            if wait is None:
                while self.window is not None and self.read_key(1) not in ("\r", "\n", "q", "\x1b", " "):
                    pass
            elif wait:
                self.read_key(wait)
        except (KeyboardInterrupt, OSError, ValueError):
            pass
        finally:
            self.stop()
        self.keys = ()
        badge = _badge(self.summary, self.rows, time.time(), 180)[0]
        line = "MINT " + translate(badge, self.language) + (" · " + translate(clean(self.next, trusted=True), self.language) if self.next else "")
        print(line, file=self.output, flush=True)


def live(read, check=None, screen=None, sources=None, address=None):
    """Read snapshots afresh; an interrupted read never keeps a stale success on screen. With the service's broker
    address the screen also has the local screen's pages (MCP 서버 · 호출 기록 · 도입 요청)."""
    screen = screen or Screen()
    results = queue.Queue()
    checking = False
    fetched = [0.0]
    if address:
        import importlib.util
        spec = importlib.util.spec_from_file_location("kit_access", Path(__file__).with_name("kit_access.py"))
        screen.access = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(screen.access)

    def fetch():
        # Every 30 seconds or on r: one Gateway round trip per refresh, not per key.
        fetched[0] = time.monotonic()
        try:
            screen.data = screen.access.receive(address, {"action": "self"})
            screen.sources = screen.access.receive(address, {"action": "list"})
        except (OSError, ValueError, KeyError, TypeError):
            screen.data = screen.data if isinstance(screen.data, dict) else {}
            screen.notice = "엔드포인트 서비스 연결 실패"

    def measure(summary):
        try:
            results.put(check(summary))
        except Exception:
            # Exceptions can contain credentials from a header helper; show only the failed result.
            results.put([("하네스 응답", "실패"), ("게이트웨이 MCP 목록", "실패")])

    # 이 화면에서 실제로 동작하는 키만 안내한다.
    screen.keys = tuple(item for item in KEY_ITEMS if item[0] not in ("c", "s") or (check if item[0] == "c" else sources))
    try:
        while True:
            screen.next = ""
            if screen.access is not None:
                if time.monotonic() - fetched[0] > 30:
                    fetch()
                screen.keys = page_keys(screen, check, sources)
            try:
                screen.summary = read()
                if not isinstance(screen.summary, dict):
                    raise ValueError("invalid snapshot")
            except (OSError, ValueError, TypeError, KeyError):
                screen.summary = {}
            # After read(): the Linux reader sets its own next step, and a waiting consent comes first.
            if (screen.data or {}).get("consents"):
                screen.next = "이용 동의 필요: mint console consent"
            try:
                screen.cells = results.get_nowait()
                checking = False
            except queue.Empty:
                pass
            screen.draw()
            if screen.window is None:
                print(screen.text(), file=screen.output)
                break
            key = screen.read_key(.5 if checking else 2)
            if screen.access is not None and key:
                if key not in ("o",):
                    screen.notice = ""
                if screen.detail is not None and key in ("\x1b", "back", "left", "enter"):
                    screen.detail = None
                    continue
                if key in ("1", "2", "3", "4"):
                    screen.page, screen.detail = int(key) - 1, None
                    continue
                if key in ("left", "right"):
                    screen.page, screen.detail = (screen.page + (1 if key == "right" else -1)) % len(PAGES), None
                    continue
                calls = (screen.data or {}).get("calls", [])
                if screen.page == 2 and key in ("up", "down", "j", "k") and calls:
                    screen.sel = max(0, min(len(calls) - 1, screen.sel + (1 if key in ("down", "j") else -1)))
                    continue
                if screen.page == 2 and key == "enter" and calls:
                    screen.detail = min(screen.sel, len(calls) - 1)
                    continue
                if key == "r":
                    fetch()
                    continue
                if key == "o":
                    screen.notice = open_console(screen)
                    continue
                if key == "n" and screen.page == 3:
                    screen.pause()
                    try:
                        new_request(screen.access, address)
                    except (EOFError, KeyboardInterrupt):
                        pass
                    finally:
                        screen.resume()
                    fetch()
                    continue
            if key in ("q", "\x1b"):
                break
            if key == "s" and sources:
                screen.pause()
                try:
                    if sources():
                        input("\n  " + translate("Enter 돌아가기", screen.language) + " ")
                except (EOFError, KeyboardInterrupt):
                    pass
                finally:
                    screen.resume()
            if key == "c" and check and not checking:
                checking = True
                screen.cells = [("하네스 응답", "진행 중"), ("게이트웨이 MCP 목록", "진행 중")]
                screen.draw()
                threading.Thread(target=measure, args=(screen.summary,), daemon=True).start()
    except KeyboardInterrupt:
        pass
    finally:
        screen.stop()
