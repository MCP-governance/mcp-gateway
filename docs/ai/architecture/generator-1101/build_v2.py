"""MINT 구조도 11-01 2판 — 다른 팀 발표(AP-EYE·SOC)의 구조도 문법으로 다시 그린다.

표기: 오픈소스는 흰 타일 위 로고, MINT 기능은 검은 선 아이콘, 데이터·설정은 주황 상자, 외부 제품은 로고만.
쪽: 전체 구성도 → 영역 구분 → 영역 확대 → 기능 집중(로컬 MCP·기본 커넥터·장치 토큰)
    → 시나리오마다 역할별 흐름(서비스 블루프린트)과 전체에서 보기(번호 + 단계 목록).

사용: python build_v2.py [MMDDHHmm] [쪽,쪽]
"""
import base64
import subprocess
import sys
import tempfile
from datetime import datetime
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ICONS = ROOT.parent / "icons" / "raw"  # the repository's icon set and its sources.json
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
FONT = "'Noto Sans KR','Malgun Gothic',sans-serif"
SW, SH = 1920, 1080
ACCENT = "#3145FD"                                   # AP-EYE 강조색
INK, TEXT2, MUTED, FAINT = "#111111", "#404040", "#7F7F7F", "#BFBFBF"
L_MCP, L_CTL, L_VEN, L_LLM, L_OBS = ACCENT, "#4A4F57", "#8A8F98", "#8E44AD", "#6B7280"
DATA_FILL, DATA_STROKE, DATA_INK = "#FFE6CC", "#D79B00", "#4A3000"   # SOC 데이터 상자(draw.io 주황)
BLOCK = "#D93A3A"


# ── 기본 도형 ────────────────────────────────────────────────────────────────
def tw(s, size):
    w = 0.0
    for ch in s:
        o = ord(ch)
        if 0xAC00 <= o <= 0xD7A3:
            w += 0.94
        elif ch in " ·.,":
            w += 0.3
        elif ch.isupper() or ch.isdigit():
            w += 0.64
        else:
            w += 0.54
    return w * size


def icon_uri(name, color=None, _cache={}):
    key = (name, color)
    if key not in _cache:
        path = next(ICONS.glob(name + ".*"))
        data = path.read_bytes()
        if color and path.suffix == ".svg":
            data = data.replace(b"#111111", color.encode())
        mime = "image/svg+xml" if path.suffix == ".svg" else "image/png"
        _cache[key] = f"data:{mime};base64," + base64.b64encode(data).decode()
    return _cache[key]


def img(name, x, y, size, color=None):
    return f'<image href="{icon_uri(name, color)}" x="{x}" y="{y}" width="{size}" height="{size}"/>'


def text(x, y, s, size=13, weight=400, color=INK, anchor="middle", halo=None):
    style = f' style="paint-order:stroke;stroke:{halo};stroke-width:5px;stroke-linejoin:round"' if halo else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" fill="{color}" '
            f'text-anchor="{anchor}" font-family="{FONT}"{style}>{escape(s)}</text>')


def rich(x, y, s, size, weight=800, anchor="start"):
    """[대괄호] 안은 강조색: AP-EYE 제목 문장 형식."""
    parts, accent, buf = [], False, ""
    for ch in s:
        if ch in "[]":
            if buf:
                parts.append((buf, accent))
            buf, accent = "", ch == "["
        else:
            buf += ch
    if buf:
        parts.append((buf, accent))
    spans = "".join(f'<tspan fill="{ACCENT if a else INK}">{escape(t)}</tspan>' for t, a in parts)
    return (f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" '
            f'font-family="{FONT}">{spans}</text>')


def markers(colors):
    return "".join(
        f'<marker id="a{c.lstrip("#")}" viewBox="0 0 10 10" refX="8.6" refY="5" markerUnits="userSpaceOnUse" '
        f'markerWidth="11" markerHeight="11" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>'
        for c in sorted(set(colors)))


def place(x, y, w, h, view, inner):
    return f'<svg x="{x}" y="{y}" width="{w}" height="{h}" viewBox="{view}" preserveAspectRatio="xMidYMid meet">{inner}</svg>'


# ── 장면 ────────────────────────────────────────────────────────────────────
class Scene:
    def __init__(self, w, h, legend=None, fs=1.0):
        self.w, self.h, self.legend, self.fs = w, h, legend, fs
        self.zones, self.nodes, self.edges = [], {}, {}

    def zone(self, id, x, y, w, h, title, kind="inner", color="#555555", fill="#F0F0F0", icon=None):
        self.zones.append(dict(id=id, x=x, y=y, w=w, h=h, title=title, kind=kind, color=color, fill=fill, icon=icon))

    def node(self, id, x, y, kind, icon, label, sub="", size=36, w=None):
        self.nodes[id] = dict(x=x, y=y, kind=kind, icon=icon, label=label, sub=sub, size=size, w=w)

    def edge(self, id, pts, color=L_CTL, dashed=False, both=False, label="", at=None, width=2.2, hidden=False):
        """hidden: 전체도에는 그리지 않고 흐름 쪽에서 강조할 때만 그린다."""
        self.edges[id] = dict(pts=pts, color=color, dashed=dashed, both=both, label=label, at=at, width=width,
                              hidden=hidden)

    def zone_rect(self, id):
        z = next(z for z in self.zones if z["id"] == id)
        return z["x"], z["y"], z["w"], z["h"]


def render_zone(z):
    x, y, w, h = z["x"], z["y"], z["w"], z["h"]
    if z["kind"] == "outer":
        s = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="#FBFBFC" stroke="#C3C8CF" stroke-width="1.5"/>']
        tx = x + 16
        if z["icon"]:
            s.append(img(z["icon"], x + 14, y + 12, 22, "#2B2B2B"))
            tx = x + 42
        s.append(text(tx, y + 30, z["title"], 18, 800, "#2B2B2B", "start"))
        return "".join(s)
    if z["kind"] == "dash":
        return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="none" stroke="{z["color"]}" '
                f'stroke-width="1.3" stroke-dasharray="5 4"/>' + text(x + 10, y + 16, z["title"], 12.5, 700, z["color"], "start"))
    s = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{z["fill"]}"/>',
         f'<rect x="{x + 10}" y="{y + 9}" width="22" height="22" rx="5" fill="{z["color"]}"/>']
    if z["icon"]:
        s.append(img(z["icon"], x + 13, y + 12, 16, "#FFFFFF"))
    s.append(text(x + 40, y + 26, z["title"], 15, 800, z["color"], "start"))
    return "".join(s)


def data_box(n, fs=1.0):
    w = n["w"] or (max(tw(n["label"], 13.5), tw(n["sub"], 11)) + 46) * fs
    h = (46 if n["sub"] else 34) * fs
    return w, h


def render_node(n, sub=True, ring=None, fs=1.0):
    x, y, size, kind = n["x"], n["y"], n["size"], n["kind"]
    s = []
    if kind in ("data", "blocked"):
        w, h = data_box(n, fs)
        left, top = x - w / 2, y - h / 2
        if ring:
            s.append(f'<rect x="{left - 5}" y="{top - 5}" width="{w + 10}" height="{h + 10}" rx="10" fill="none" '
                     f'stroke="{ring}" stroke-width="3"/>')
        if kind == "data":
            s.append(f'<rect x="{left}" y="{top}" width="{w}" height="{h}" rx="7" fill="{DATA_FILL}" stroke="{DATA_STROKE}" stroke-width="1.4"/>')
            s.append(img("tb-file-text", left + 9, y - 9 * fs, 18 * fs, "#9A6A00"))
            color, sub_color = DATA_INK, "#80601C"
        else:
            s.append(f'<rect x="{left}" y="{top}" width="{w}" height="{h}" rx="7" fill="#FFFFFF" stroke="{BLOCK}" '
                     f'stroke-width="1.6" stroke-dasharray="5 3"/>')
            s.append(img("tb-ban", left + 9, y - 9 * fs, 18 * fs, BLOCK))
            color, sub_color = "#7A1F1F", "#A33A3A"
        tx = left + 12 + 21 * fs
        if n["sub"] and sub:
            s.append(text(tx, y - 2 * fs, n["label"], 13.5 * fs, 800, color, "start"))
            s.append(text(tx, y + 14 * fs, n["sub"], 11 * fs, 600, sub_color, "start"))
        else:
            s.append(text(tx, y + 5 * fs, n["label"], 13.5 * fs, 800, color, "start"))
        return "".join(s)
    pad = 6 if kind == "oss" else 0
    if ring:
        r = size / 2 + pad + 7
        s.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="none" stroke="{ring}" stroke-width="3"/>')
    if kind == "oss":
        s.append(f'<rect x="{x - size / 2 - pad}" y="{y - size / 2 - pad}" width="{size + 2 * pad}" height="{size + 2 * pad}" '
                 f'rx="9" fill="#FFFFFF" stroke="#C9CED6" stroke-width="1.2"/>')
    s.append(img(n["icon"], x - size / 2, y - size / 2, size))
    ly = y + size / 2 + pad + 17 * fs
    s.append(text(x, ly, n["label"], (14 if size >= 28 else 12.5) * fs, 700, INK))
    if n["sub"] and sub:
        for i, line in enumerate(n["sub"].split("\n")):
            s.append(text(x, ly + (15 + 14 * i) * fs, line, 11.5 * fs, 500, "#5F6670"))
    return "".join(s)


def path_d(pts):
    return "M" + " L".join(f"{x},{y}" for x, y in pts)


def render_edge(e, color=None, width=None, labels=True, fs=1.0):
    color = color or e["color"]
    k = color.lstrip("#")
    dash = ' stroke-dasharray="7 5"' if e["dashed"] else ""
    start = f' marker-start="url(#a{k})"' if e["both"] else ""
    s = (f'<path d="{path_d(e["pts"])}" fill="none" stroke="{color}" stroke-width="{width or e["width"]}" '
         f'stroke-linejoin="round"{dash} marker-end="url(#a{k})"{start}/>')
    if labels and e["label"]:
        at = e["at"] or midpoint(e["pts"])
        w = tw(e["label"], 12.5 * fs) + 12
        s += (f'<rect x="{at[0] - w / 2:.1f}" y="{at[1] - 9 * fs:.1f}" width="{w:.1f}" height="{18 * fs:.1f}" rx="4" fill="#FFFFFF"/>'
              + text(at[0], at[1] + 4.5 * fs, e["label"], 12.5 * fs, 700, "#262626"))
    return s


def midpoint(pts):
    best = max(zip(pts, pts[1:]), key=lambda seg: abs(seg[0][0] - seg[1][0]) + abs(seg[0][1] - seg[1][1]))
    (x1, y1), (x2, y2) = best
    return (x1 + x2) / 2, (y1 + y2) / 2


LEGEND_ROWS = [("oss", "오픈소스"), ("fn", "MINT 기능"), ("data", "데이터 · 설정"), ("ext", "외부 제품 · 서비스")]
LEGEND_LINES = [("MCP 호출", L_MCP, False), ("관리 · 보고", L_CTL, False), ("벤더 직접", L_VEN, True), ("모델", L_LLM, True)]


def render_legend(x, y, w, h):
    s = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="#FFFFFF" stroke="#C3C8CF" stroke-width="1.3"/>']
    for i, (kind, name) in enumerate(LEGEND_ROWS):
        cx, cy = x + 34 + (i % 2) * (w / 2), y + 34 + (i // 2) * 46
        if kind == "oss":
            s.append(f'<rect x="{cx - 15}" y="{cy - 15}" width="30" height="30" rx="7" fill="#fff" stroke="#C9CED6"/>'
                     + img("logo-opa", cx - 10, cy - 10, 20))
        elif kind == "fn":
            s.append(img("tb-settings-cog", cx - 13, cy - 13, 26))
        elif kind == "data":
            s.append(f'<rect x="{cx - 18}" y="{cy - 12}" width="36" height="24" rx="5" fill="{DATA_FILL}" stroke="{DATA_STROKE}"/>')
        else:
            s.append(img("logo-github", cx - 12, cy - 12, 24))
        s.append(text(cx + 28, cy + 5, name, 13.5, 700, INK, "start"))
    for i, (name, color, dashed) in enumerate(LEGEND_LINES):
        cx, cy = x + 20 + (i % 2) * (w / 2), y + 132 + (i // 2) * 26
        dash = ' stroke-dasharray="7 5"' if dashed else ""
        s.append(f'<line x1="{cx}" y1="{cy}" x2="{cx + 36}" y2="{cy}" stroke="{color}" stroke-width="2.6"{dash} '
                 f'marker-end="url(#a{color.lstrip("#")})"/>')
        s.append(text(cx + 46, cy + 4.5, name, 13, 600, INK, "start"))
    return "".join(s)


def draw(sc, sub=True):
    colors = [e["color"] for e in sc.edges.values()] + [ACCENT, BLOCK, L_CTL, L_VEN, L_LLM, "#262626"]
    out = [f"<defs>{markers(colors)}</defs>"]
    out += [render_zone(z) for z in sc.zones]
    out += [render_edge(e, fs=sc.fs) for e in sc.edges.values() if not e["hidden"]]
    out += [render_node(n, sub, fs=sc.fs) for n in sc.nodes.values()]
    if sc.legend:
        out.append(render_legend(*sc.legend))
    return "".join(out)


# ── 전체 구성도 ──────────────────────────────────────────────────────────────
M = Scene(1880, 888, legend=(1512, 706, 358, 182))
BLUE, PURPLE, PINK, TEAL, ORANGE, GRAY, LAV, GREEN = (
    ("#2F5DA8", "#D9E6F7"), ("#7B3FA0", "#EADDEE"), ("#C0392B", "#FADBD9"), ("#138D75", "#DDF1EC"),
    ("#C8641E", "#FFE9D6"), ("#555555", "#EDEDED"), ("#5B4CB0", "#E8E4F7"), ("#4D8B31", "#D5E8D4"))


def inner(id, x, y, w, h, title, palette, icon):
    M.zone(id, x, y, w, h, title, "inner", palette[0], palette[1], icon)


# 직원 PC
M.zone("pc", 10, 44, 430, 740, "직원 PC", "outer", icon="tb-device-laptop")
M.node("emp", 70, 119, "fn", "tb-user", "직원")
M.node("emp_web", 400, 119, "fn", "tb-browser", "직원 콘솔", "동의 · 내 연결")
inner("hn", 22, 184, 406, 140, "하네스", BLUE, "tb-apps")
M.node("claude", 70, 238, "ext", "logo-claude", "Claude Code")
M.node("codex", 150, 238, "ext", "logo-codex", "Codex")
M.node("hook", 230, 238, "fn", "tb-webhook", "관리형 훅", "PostToolUse")
M.node("builtin", 355, 238, "fn", "tb-world-search", "기본 기능 · 커넥터", "웹 검색 · 앱")
inner("kit", 22, 339, 406, 235, "관리형 통제 · 키트", PURPLE, "tb-shield-lock")
M.node("mset", 95, 398, "data", None, "관리형 설정", "MCP · 기능 · 커넥터", w=140)
M.node("inv", 95, 504, "fn", "tb-zoom-scan", "인벤토리 · 관찰", "설정 · 프로세스")
M.node("svc", 230, 448, "fn", "tb-settings-cog", "키트 서비스", "정책 · 보고", 44)
M.node("helper", 365, 398, "fn", "tb-key", "헤더 도우미", "장치 토큰")
M.node("mint", 365, 504, "fn", "tb-terminal-2", "mint · 트레이", "상태 · 요청")
inner("local", 22, 589, 406, 185, "로컬 MCP", PINK, "tb-box")
M.node("blocked", 92, 652, "blocked", None, "미등록 MCP", "로드 차단", w=124)
M.node("lmcp", 215, 645, "fn", "tb-server-2", "승인 로컬 MCP", "이미지 · 승인 소스", 34)
M.node("runner", 365, 645, "fn", "tb-box", "로컬 실행기", "Linux")
M.node("docker", 330, 738, "oss", "logo-docker", "Docker", size=20)
M.node("podman", 395, 738, "oss", "lg-podman", "Podman", size=20)
M.zone("admpc", 10, 796, 430, 92, "관리자 PC", "outer", icon="tb-device-desktop")
M.node("admin", 230, 836, "fn", "tb-user-shield", "관리자", size=30)
M.node("adm_web", 345, 836, "fn", "tb-browser", "관리자 콘솔", size=30)
# 사설망
M.zone("net", 452, 44, 106, 844, "사설망", "outer", icon="tb-topology-star-3")
M.node("ts", 527, 836, "oss", "logo-tailscale", "Tailscale", size=22)
# 솔루션
M.zone("sol", 570, 44, 924, 844, "MINT 솔루션", "outer", icon="tb-server")
inner("proxy", 582, 78, 120, 120, "모델 프록시", GRAY, "tb-brain")
M.node("tiny", 642, 134, "oss", "tb-server-2", "tinyproxy", "목적지 제한", 28)
inner("ing", 582, 214, 120, 659, "진입", TEAL, "tb-lock-access")
M.node("caddy", 642, 450, "oss", "logo-caddy", "Caddy", "HTTPS 진입", 44)
inner("relay", 716, 78, 280, 220, "요청 중계", BLUE, "tb-route")
M.node("gwcore", 856, 140, "fn", "tb-route", "요청 중계", "MCP 프로토콜", 44)
M.node("fastapi", 771, 247, "oss", "logo-fastapi", "FastAPI", size=22)
M.node("mcpsdk", 856, 247, "oss", "logo-mcp", "MCP SDK", size=22)
M.node("otel", 941, 247, "oss", "logo-opentelemetry", "OpenTelemetry", size=22)
inner("judge", 1008, 78, 280, 220, "판정", PINK, "tb-shield-check")
M.node("opa", 1056, 134, "oss", "logo-opa", "OPA", "정책 판정", 30)
M.node("presidio", 1148, 134, "oss", "logo-presidio", "Presidio", "개인정보 마스킹", 30)
M.node("gitleaks", 1240, 134, "oss", "logo-gitleaks", "Gitleaks", "비밀 검사 · 내장", 30)
M.node("consent", 1100, 247, "fn", "tb-checkbox", "동의 확인", size=26)
M.node("scope", 1205, 247, "fn", "tb-adjustments-horizontal", "도구 · 인자 범위", size=26)
inner("epm", 716, 312, 380, 250, "엔드포인트 관리", PURPLE, "tb-device-laptop")
M.node("deploy", 760, 372, "fn", "tb-cloud-download", "정책 제공", size=32)
M.node("report", 850, 372, "fn", "tb-heart-rate-monitor", "장치 보고", "하트비트", 32)
M.node("token", 940, 372, "fn", "tb-ticket", "장치 토큰", "5분 · 장치 결속", 32)
M.node("ljob", 1040, 372, "fn", "tb-subtask", "로컬 작업", "작업 큐", 32)
M.node("quar", 760, 488, "fn", "tb-ban", "장치 격리", "MCP 접근 중단", 32)
M.node("devpol", 885, 488, "data", None, "장치 정책", "제어 해시", w=112)
M.node("calls", 1018, 488, "data", None, "호출 기록", "훅 · 경로", w=112)
inner("alert", 1108, 312, 186, 250, "경보 · 대응", ORANGE, "tb-alert-triangle")
M.node("alerts", 1155, 372, "fn", "tb-bell", "경보", "미등록 · 격리", 32)
M.node("suspend", 1247, 372, "fn", "tb-clock-pause", "서버 자동 중지", "계약 변동", 32)
M.node("callappr", 1200, 488, "fn", "tb-user-check", "호출 승인", "고위험 도구", 32)
inner("store", 1306, 78, 182, 484, "원장 · 추적", GRAY, "tb-database")
M.node("pg", 1397, 136, "oss", "logo-postgresql", "PostgreSQL", size=34)
M.node("ledger", 1397, 222, "data", None, "감사 원장", "추가만 · 상태", w=130)
M.node("jaeger", 1397, 368, "oss", "logo-jaeger", "Jaeger", "호출 추적", 34)
inner("con", 716, 576, 380, 297, "콘솔 · 계정", LAV, "tb-layout-dashboard")
M.node("console", 770, 636, "fn", "tb-layout-dashboard", "콘솔 서비스", "직원 · 관리자", 32)
M.node("identity", 862, 636, "fn", "tb-id-badge-2", "계정 · 토큰", "로그인 · 장치 등록", 32)
M.node("epreq", 952, 636, "fn", "tb-mail-forward", "직원 요청", "엔드포인트", 32)
M.node("intake", 1045, 636, "fn", "tb-clipboard-check", "도입 승인", "범위 · 기한", 32)
M.node("term", 770, 770, "fn", "tb-trash", "종료 · 폐기", "이용 관계", 30)
M.node("authlib", 862, 770, "oss", "logo-authlib", "Authlib", "OIDC · 선택", 24)
inner("sup", 1108, 576, 380, 297, "도입 검증", GREEN, "tb-file-search")
M.node("worker", 1162, 636, "fn", "tb-file-search", "검증 워커", size=32)
M.node("gitea", 1280, 636, "oss", "logo-gitea", "Gitea", size=30)
M.node("src", 1412, 636, "data", None, "승인 소스", "검증 커밋", w=118)
M.zone("scan", 1124, 724, 348, 132, "검사 도구", "dash", "#4D8B31")
M.node("syft", 1170, 780, "oss", "logo-syft", "Syft", size=24)
M.node("trivy", 1250, 780, "oss", "logo-trivy", "Trivy", size=24)
M.node("semgrep", 1330, 780, "oss", "logo-semgrep", "Semgrep", size=24)
M.node("gitleaks2", 1410, 780, "oss", "logo-gitleaks", "Gitleaks", size=24)
# 외부
M.zone("ext", 1512, 44, 358, 650, "외부 연동", "outer", icon="tb-world")
inner("vend", 1524, 78, 334, 215, "벤더 클라우드", GRAY, "tb-cloud")
M.node("claudeai", 1610, 132, "ext", "logo-claude", "claude.ai", "기본 기능 · 커넥터", 34)
M.node("chatgpt", 1770, 132, "ext", "logo-openai", "ChatGPT", "기본 기능 · 앱", 34)
M.zone("saas", 1540, 196, 302, 88, "업무 서비스", "dash", "#777777")
M.node("gmail", 1600, 236, "ext", "lg-google-gmail", "Gmail", size=20)
M.node("gdrive", 1665, 236, "ext", "logo-google-drive", "Drive", size=20)
M.node("notion", 1730, 236, "ext", "lg-notion-icon", "Notion", size=20)
M.node("slack", 1795, 236, "ext", "lg-slack-icon", "Slack", size=20)
inner("llm", 1524, 308, 334, 120, "LLM 제공자", GRAY, "tb-brain")
M.node("anthropic", 1610, 362, "ext", "logo-anthropic", "Anthropic", size=32)
M.node("openai", 1770, 362, "ext", "logo-openai", "OpenAI", size=32)
inner("rmcp", 1524, 443, 334, 251, "원격 MCP 서버", GRAY, "tb-server-2")
M.node("github", 1610, 503, "ext", "logo-github", "GitHub", size=34)
M.node("hf", 1770, 503, "ext", "logo-huggingface", "Hugging Face", size=34)
M.node("ctx7", 1610, 620, "ext", "logo-context7", "Context7", size=34)
M.node("mslearn", 1770, 620, "ext", "logo-microsoft", "Microsoft Learn", size=34)

# 위쪽 띠: 벤더 직접·모델·원격 MCP는 솔루션 위로 돌아 외부로 나간다(서로 겹치지 않는 순서).
M.edge("vendor", [(355, 216), (355, 12), (1508, 12), (1508, 132), (1590, 132)], L_VEN, True, label="벤더 직접 연결", at=(440, 12))
M.edge("model_out", [(428, 204), (532, 204), (532, 134), (618, 134)], L_LLM, True, label="모델", at=(482, 204))
M.edge("model_up", [(666, 134), (722, 134), (722, 24), (1503, 24), (1503, 362), (1590, 362)], L_LLM, True,
       label="허용 목적지만", at=(770, 24))
M.edge("mcp_up", [(856, 116), (856, 36), (1498, 36), (1498, 503), (1590, 503)], L_MCP, both=True, width=2.6,
       label="서비스 자격 · 직원 토큰 미전달", at=(1180, 36))
# 직원 PC → Caddy (모든 HTTPS는 Caddy 하나로 들어온다)
M.edge("web_emp", [(420, 119), (510, 119), (510, 360), (612, 360)], L_CTL, both=True, label="직원 콘솔", at=(560, 360))
M.edge("mcp_in", [(428, 262), (486, 262), (486, 388), (612, 388)], L_MCP, both=True, width=2.6, label="MCP · 장치 토큰", at=(560, 388))
M.edge("dev_in", [(230, 508), (230, 566), (462, 566), (462, 416), (612, 416)], L_CTL, both=True, label="정책 · 보고 · 토큰", at=(558, 416))
M.edge("local_in", [(384, 645), (474, 645), (474, 444), (612, 444)], L_CTL, True, both=True, label="로컬 작업", at=(556, 444))
M.edge("web_adm", [(362, 836), (498, 836), (498, 472), (612, 472)], L_CTL, both=True, label="관리자 콘솔", at=(556, 472))
# 직원 PC 안
M.edge("mset_hn", [(95, 373), (95, 327)], L_CTL)
M.edge("harness_helper", [(365, 327), (365, 376)], L_CTL, both=True)
M.edge("hook_svc", [(230, 292), (230, 423)], L_CTL, label="호출 보고", at=(230, 322))
M.edge("svc_mset", [(206, 438), (184, 438), (184, 398), (167, 398)], L_CTL)
M.edge("inv_svc", [(115, 504), (176, 504), (176, 458), (206, 458)], L_CTL)
M.edge("helper_svc", [(345, 398), (276, 398), (276, 438), (254, 438)], L_CTL, both=True, label="토큰", at=(310, 398))
M.edge("mint_svc", [(345, 504), (284, 504), (284, 458), (254, 458)], L_CTL, both=True)
M.edge("runner_mcp", [(345, 645), (234, 645)], L_CTL, label="실행", at=(290, 645))
M.edge("obs", [(146, 626), (146, 562)], L_CTL, True)
# 솔루션 안
M.edge("mcp_core", [(672, 440), (709, 440), (709, 140), (832, 140)], L_MCP, both=True, width=2.6)
M.edge("dev_plane", [(672, 458), (714, 458)], L_CTL, both=True)
M.edge("web_back", [(672, 474), (702, 474), (702, 636), (752, 636)], L_CTL, both=True)
M.edge("judge", [(880, 130), (1034, 130)], L_MCP, both=True, label="판정", at=(957, 130))
M.edge("local_plane", [(880, 152), (1002, 152), (1002, 372), (1022, 372)], L_MCP, True, both=True, label="로컬 MCP 호출", at=(1002, 334))
M.edge("otlp", [(941, 285), (941, 305), (1300, 305), (1300, 368), (1376, 368)], L_OBS, True, width=1.8, label="추적", at=(1150, 305))
M.edge("epm_alert", [(1096, 352), (1137, 352)], L_CTL)
M.edge("gw_pg", [(1264, 130), (1374, 130)], L_CTL, label="판정 기록", at=(1286, 148))
M.edge("con_gw", [(1045, 616), (1045, 580), (885, 580), (885, 513)], L_CTL, label="승인 반영", at=(965, 580))
M.edge("intake_sup", [(1063, 636), (1144, 636)], L_CTL, label="검사 요청", at=(1104, 622))
M.edge("worker_gitea", [(1180, 636), (1256, 636)], L_CTL, label="보관", at=(1218, 622))
M.edge("gitea_src", [(1302, 636), (1350, 636)], L_CTL)
M.edge("worker_scan", [(1162, 676), (1162, 722)], L_CTL)
M.edge("saas_link", [(1690, 166), (1690, 194)], L_VEN, True)
# 흐름 쪽에서만: Caddy 다음 실제 처리 기능까지 잇는다.
M.edge("policy_plane", [(672, 450), (760, 450), (760, 414)], L_CTL, hidden=True)
M.edge("report_plane", [(672, 450), (850, 450), (850, 428)], L_CTL, hidden=True)
M.edge("token_plane", [(672, 450), (940, 450), (940, 428)], L_CTL, hidden=True)
M.edge("calls_plane", [(672, 450), (1018, 450), (1018, 463)], L_CTL, hidden=True)
M.edge("request_plane", [(672, 466), (694, 466), (694, 700), (952, 700), (952, 692)], L_CTL, hidden=True)
M.edge("register_plane", [(1045, 616), (1045, 568), (992, 568), (992, 212), (884, 212)], L_CTL, hidden=True)

MARKS = {1: (424, 62), 2: (1274, 92), 3: (1280, 326), 4: (1474, 590), 5: (1474, 92), 6: (1852, 62),
         7: (412, 603), 8: (403, 200), 9: (412, 356)}


def mark(n, x, y, r=15):
    return f'<circle cx="{x}" cy="{y}" r="{r}" fill="{ACCENT}"/>' + text(x, y + r * 0.36, str(n), r * 1.05, 800, "#FFFFFF")


# ── 슬라이드 틀 (AP-EYE: 경로 머리글 + 회색 선 + 쪽 번호, 엷은 보라·파랑 배경) ──────────
BG = ('<defs><radialGradient id="bg1" gradientUnits="userSpaceOnUse" cx="0" cy="0" r="980">'
      '<stop offset="0" stop-color="#DCD8F8"/><stop offset="1" stop-color="#DCD8F8" stop-opacity="0"/></radialGradient>'
      '<radialGradient id="bg2" gradientUnits="userSpaceOnUse" cx="1920" cy="1080" r="1100">'
      '<stop offset="0" stop-color="#AFC4FB"/><stop offset="1" stop-color="#AFC4FB" stop-opacity="0"/></radialGradient></defs>'
      f'<rect width="{SW}" height="{SH}" fill="#FFFFFF"/><rect width="{SW}" height="{SH}" fill="url(#bg1)"/>'
      f'<rect width="{SW}" height="{SH}" fill="url(#bg2)" opacity="0.75"/>')


def slide(section, body, page, headline=None, sub=None):
    head = (f'<text x="60" y="72" font-size="32" font-weight="600" font-family="{FONT}">'
            f'<tspan fill="{MUTED}">아키텍처 | </tspan><tspan fill="{TEXT2}">{escape(section)}</tspan></text>'
            + text(SW - 60, 72, "MINT · MCP 거버넌스 게이트웨이", 24, 600, FAINT, "end")
            + f'<line x1="46" y1="98" x2="{SW - 46}" y2="98" stroke="{MUTED}" stroke-width="3"/>')
    if headline:
        head += rich(60, 190, headline, 64)
    if sub:
        head += text(60, 226, sub, 30, 600, MUTED, "start")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{SW}" height="{SH}" viewBox="0 0 {SW} {SH}">'
            + BG + head + body + text(SW - 46, SH - 26, str(page), 22, 600, "#0D0D0D", "end") + "</svg>")


def overview(page):
    inner_svg = draw(M) + "".join(mark(n, x, y) for n, (x, y) in MARKS.items())
    return slide("전체 구성도", place(20, 112, 1880, 944, f"0 0 {M.w} {M.h}", inner_svg), page)


# SOC 22쪽: 영역마다 색 틀과 큰 이름을 얹는다.
AREAS = [((10, 44, 430, 545), "직원 PC", "#E8711A", (225, 168)),
         ((10, 589, 430, 196), "로컬 MCP", "#C0392B", (300, 720)),
         ((578, 74, 714, 230), "호출 통제", ACCENT, (850, 290)),
         ((712, 308, 586, 258), "장치 관리 · 경보", "#7B3FA0", (1004, 545)),
         ((712, 572, 780, 305), "도입 승인 · 검증", "#2E8B57", (1100, 860)),
         ((1302, 74, 190, 492), "원장 · 추적", "#555555", (1397, 300)),
         ((1512, 44, 358, 650), "외부 연동", "#7F7F7F", (1690, 430))]


def area_map(page):
    over = ['<rect x="-20" y="-20" width="2000" height="1000" fill="rgba(255,255,255,0.55)"/>']
    for (x, y, w, h), name, color, (lx, ly) in AREAS:
        dash = ' stroke-dasharray="14 9"' if color == "#7F7F7F" else ""
        over.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="none" stroke="{color}" stroke-width="4.5"{dash}/>')
    for (x, y, w, h), name, color, (lx, ly) in AREAS:
        over.append(text(lx, ly, name, 38, 800, color, halo="#FFFFFF"))
    return slide("영역 구분", place(20, 112, 1880, 944, f"0 0 {M.w} {M.h}", draw(M) + "".join(over)), page)


# ── 영역 확대 (AP-EYE 17·18쪽) ───────────────────────────────────────────────
def bbox(rects):
    x0, y0 = min(r[0] for r in rects), min(r[1] for r in rects)
    return x0, y0, max(r[0] + r[2] for r in rects) - x0, max(r[1] + r[3] for r in rects) - y0


def shade(rects, alpha=0.45):
    holes = "".join(f"M{x},{y} h{w} v{h} h{-w} Z " for x, y, w, h in rects)
    return f'<path fill-rule="evenodd" fill="rgba(0,0,0,{alpha})" d="M-3000,-3000 H6000 V6000 H-3000 Z {holes}"/>'


def crop_view(rects, margin, aspect=None, sc=M):
    x, y, w, h = bbox(rects)
    vx, vy, vw, vh = x - margin, y - margin, w + 2 * margin, h + 2 * margin
    if aspect:
        if vw / vh < aspect:
            grow = vh * aspect - vw
            vx, vw = vx - grow / 2, vw + grow
        else:
            grow = vw / aspect - vh
            vy, vh = vy - grow / 2, vh + grow
    vx, vy = max(vx, -10), max(vy, -10)
    vx, vy = min(vx, sc.w + 10 - vw), min(vy, sc.h + 10 - vh)
    return vx, vy, vw, vh


def framed(x, y, w, h, view, inner_svg):
    return (place(x, y, w, h, view, inner_svg)
            + f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="#000000" stroke-width="1.5"/>')


def items_right(x, y0, items, gap=230):
    s = []
    for i, (head, lines) in enumerate(items):
        t = y0 + i * gap
        s.append(text(x, t + 56, f"{i + 1:02d}", 72, 800, ACCENT, "start"))
        s.append(text(x + 150, t + 30, head, 36, 700, "#000000", "start"))
        for j, line in enumerate(lines):
            s.append(text(x + 150, t + 78 + j * 44, line, 32, 400, TEXT2, "start"))
    return "".join(s)


def items_below(x0, x1, y, items):
    col = (x1 - x0) / len(items)
    s = []
    for i, (head, lines) in enumerate(items):
        cx = x0 + col * (i + 0.5)
        s.append(text(cx, y, head, 36, 700, "#000000"))
        for j, line in enumerate(lines):
            s.append(text(cx, y + 46 + j * 40, line, 28, 400, TEXT2))
    return "".join(s)


def legend_strip(right=1830, y=1050):
    """확대·집중 쪽 아래 오른쪽: 전체도 범례의 네 가지 표기."""
    parts = [("oss", "오픈소스"), ("fn", "MINT 기능"), ("data", "데이터 · 설정"), ("ext", "외부 제품")]
    widths = [40 + tw(name, 17) + 30 for _, name in parts]
    x = right - sum(widths)
    s = []
    for (kind, name), w in zip(parts, widths):
        cx = x + 14
        if kind == "oss":
            s.append(f'<rect x="{cx - 13}" y="{y - 21}" width="26" height="26" rx="6" fill="#fff" stroke="#C9CED6"/>'
                     + img("logo-opa", cx - 9, y - 17, 18))
        elif kind == "fn":
            s.append(img("tb-settings-cog", cx - 12, y - 20, 24))
        elif kind == "data":
            s.append(f'<rect x="{cx - 15}" y="{y - 18}" width="30" height="20" rx="4" fill="{DATA_FILL}" stroke="{DATA_STROKE}"/>')
        else:
            s.append(img("logo-github", cx - 11, y - 19, 22))
        s.append(text(cx + 24, y - 2, name, 17, 600, TEXT2, "start"))
        x += w
    return "".join(s)


def zoom(page, num, section, headline, rects, items):
    x, y, w, h = bbox(rects)
    if w / h > 1.8:   # 가로로 긴 영역: 위에 넓게, 아래 3단 (AP-EYE 18쪽)
        aspect = max(w / h, 2.2)
        bw = min(1760, 560 * aspect)
        bh = bw / aspect
        view = crop_view(rects, 34, bw / bh)
        bx = (SW - bw) / 2
        body = framed(bx, 236, bw, bh, " ".join(f"{v:.1f}" for v in view), draw(M) + shade(rects))
        body += mark(num, bx, 236, 24)
        body += items_below(bx, bx + bw, 236 + bh + 62, items)
    else:              # 세로이거나 정사각에 가까운 영역: 왼쪽 확대, 오른쪽 01~03 (AP-EYE 17쪽)
        margin = 36 if h > 400 else 60
        view = crop_view(rects, margin, None)
        bh = 790
        bw = min(880, bh * view[2] / view[3])
        bh = min(bh, bw * view[3] / view[2])
        view = crop_view(rects, margin, bw / bh)
        top = 236 + (790 - bh) / 2
        body = framed(80, top, bw, bh, " ".join(f"{v:.1f}" for v in view), draw(M) + shade(rects))
        body += mark(num, 80, top, 24)
        body += items_right(80 + bw + 80, 296, items)
    return slide(section, body + legend_strip(), page, headline)


ZOOMS = {
    1: ("직원 PC", "직원 PC는 [관리형 설정]이 하네스를 묶습니다", [(10, 44, 430, 530)], [
        ("하네스 · 관리형 설정", ["허용된 MCP · 기능 · 커넥터만 올라가고", "바꾸면 변조로 감지합니다"]),
        ("키트 서비스", ["정책을 받아 설정을 만들고", "훅 · 인벤토리 결과를 보고합니다"]),
        ("헤더 도우미 · mint", ["장치 토큰을 하네스에 건네고", "직원은 mint로 상태를 봅니다"])]),
    2: ("진입 · 호출 통제", "[관리형 MCP 호출]은 게이트웨이 판정 뒤 중계됩니다",
        [(582, 340, 120, 200), (716, 78, 572, 220)], [
        ("단일 진입", ["Caddy가 MCP · 장치 보고 ·", "웹 콘솔을 HTTPS로 받습니다"]),
        ("판정", ["OPA · Presidio · 비밀 검사와", "동의 · 도구 · 인자 범위"]),
        ("중계", ["실행 직전에 다시 확인하고", "서비스 자격으로 연결합니다"])]),
    3: ("엔드포인트 관리 · 경보", "엔드포인트 보고로 [장치 상태]를 판단합니다", [(716, 312, 578, 250)], [
        ("정책 · 장치 토큰", ["장치 정책을 내려주고", "정상 장치에만 5분 토큰을 줍니다"]),
        ("보고 · 호출 기록", ["하트비트 · 무결성 · 훅 이벤트를", "경로별로 기록합니다"]),
        ("격리 · 경보", ["변조 · 미등록 MCP · 계약 변동은", "격리 · 경보 · 서버 중지로"])]),
    4: ("콘솔 · 도입 검증", "도입은 [검증과 사람의 승인]을 거쳐 등록됩니다", [(716, 576, 772, 297)], [
        ("콘솔 · 계정", ["직원 · 관리자 화면과", "로그인 · 장치 등록"]),
        ("도입 승인", ["직원 요청으로 신청서를 만들어", "범위 · 대상 · 기한을 정합니다"]),
        ("도입 검증", ["소스 MCP는 검사 도구 4종 뒤", "승인 소스로 보관합니다"])]),
    6: ("외부 연동", "외부로 나가는 길은 [세 갈래]입니다", [(1512, 44, 358, 650)], [
        ("벤더 클라우드", ["기본 기능 · 커넥터는 벤더로 직접,", "관리형 설정으로 제한합니다"]),
        ("LLM 제공자", ["모델 요청은 tinyproxy가", "허용 목적지로만 보냅니다"]),
        ("원격 MCP", ["게이트웨이가 서비스 자격으로 연결,", "직원 토큰은 넘기지 않습니다"])]),
}


# ── 기능 집중: 위치·구조를 바꿔 한 기능만 그린다 ───────────────────────────
def focus_store():
    s = Scene(1800, 560, fs=1.15)
    s.zone("mint", 20, 40, 1180, 500, "MINT 솔루션", "inner", *BLUE, "tb-server")
    s.zone("src", 40, 90, 400, 230, "기록하는 기능", "dash", "#2F5DA8")
    s.node("gwcore", 120, 185, "fn", "tb-route", "요청 중계", "판정 · 중계", 42)
    s.node("console", 240, 185, "fn", "tb-layout-dashboard", "콘솔 서비스", "동의 · 승인", 42)
    s.node("report", 360, 185, "fn", "tb-heart-rate-monitor", "장치 보고", "하트비트 · 훅", 42)
    s.node("pg", 640, 205, "oss", "logo-postgresql", "PostgreSQL", size=56)
    s.node("ledger", 960, 150, "data", None, "감사 원장", "판정 기록 · 추가만", w=230)
    s.node("state", 960, 262, "data", None, "상태", "장치 · 동의 · 승인 · 서버", w=230)
    s.edge("w1", [(440, 205), (600, 205)], L_CTL, label="기록", width=2.6)
    s.edge("w2", [(682, 195), (760, 195), (760, 150), (843, 150)], L_CTL)
    s.edge("w3", [(682, 215), (760, 215), (760, 262), (843, 262)], L_CTL)
    s.node("gw2", 120, 440, "fn", "tb-route", "요청 중계", "호출 구간", 42)
    s.node("otel", 420, 440, "oss", "logo-opentelemetry", "OpenTelemetry", "계측", 40)
    s.node("jaeger", 760, 440, "oss", "logo-jaeger", "Jaeger", "호출 추적", 44)
    s.edge("t1", [(144, 440), (388, 440)], L_OBS, True, label="추적 데이터")
    s.edge("t2", [(452, 440), (722, 440)], L_OBS, True)
    s.zone("adm", 1220, 40, 560, 500, "관리자 PC", "inner", *GRAY, "tb-device-desktop")
    s.node("adm_web", 1500, 205, "fn", "tb-browser", "관리자 콘솔", "호출 기록 · 상세", 46)
    s.edge("r1", [(1077, 150), (1160, 150), (1160, 205), (1474, 205)], L_CTL, label="조회", at=(1320, 205))
    s.edge("r2", [(1077, 262), (1160, 262), (1160, 210)], L_CTL)
    return s


def focus_local():
    s = Scene(1800, 560, fs=1.15)
    s.zone("pcA", 20, 40, 240, 236, "직원 PC", "inner", *ORANGE, "tb-device-laptop")
    s.zone("mintA", 280, 40, 680, 236, "MINT 게이트웨이", "inner", *BLUE, "tb-route")
    s.zone("pcB", 980, 40, 800, 236, "직원 PC · 로컬 실행 (Linux)", "inner", *PINK, "tb-box")
    s.node("claude", 80, 140, "ext", "logo-claude", "Claude Code", size=40)
    s.node("codex", 168, 140, "ext", "logo-codex", "Codex", size=40)
    s.node("caddy", 350, 140, "oss", "logo-caddy", "Caddy", "HTTPS 진입", 40)
    s.node("gwcore", 510, 140, "fn", "tb-route", "요청 중계", "실행 직전 재확인", 44)
    s.node("opa", 680, 140, "oss", "logo-opa", "OPA", "같은 정책", 34)
    s.node("ljob", 860, 140, "fn", "tb-subtask", "로컬 작업", "장치 결속 · 서명", 40)
    s.edge("a1", [(194, 140), (318, 140)], L_MCP, both=True, label="MCP · 장치 토큰", width=2.8)
    s.edge("a2", [(382, 140), (486, 140)], L_MCP, both=True, width=2.8)
    s.edge("a3", [(534, 140), (653, 140)], L_MCP, both=True, label="판정", width=2.8)
    s.edge("a4", [(510, 214), (510, 250), (860, 250), (860, 212)], L_MCP, label="작업 등록", at=(690, 250), width=2.8)
    s.node("runner", 1060, 140, "fn", "tb-box", "로컬 실행기", "작업 조회 · 결과", 42)
    s.edge("a5", [(882, 140), (1037, 140)], L_CTL, True, both=True, label="작업 조회 · 결과", at=(958, 132), width=2.4)
    s.zone("eng", 1210, 58, 176, 104, "컨테이너 엔진", "dash", "#C0392B")
    s.node("docker", 1252, 104, "oss", "logo-docker", "Docker", size=28)
    s.node("podman", 1342, 104, "oss", "lg-podman", "Podman", size=28)
    s.node("proc", 1295, 210, "fn", "tb-terminal-2", "직원 계정 프로세스", size=30)
    s.node("lmcp", 1610, 150, "fn", "tb-server-2", "승인 로컬 MCP", "이미지 · 승인 소스", 42)
    s.edge("a6", [(1083, 130), (1170, 130), (1170, 104), (1208, 104)], L_CTL, label="이미지", at=(1170, 117))
    s.edge("a7", [(1083, 152), (1170, 152), (1170, 210), (1276, 210)], L_CTL, label="승인 소스", at=(1170, 186))
    s.edge("a8", [(1388, 104), (1480, 104), (1480, 140), (1586, 140)], L_CTL, label="컨테이너", at=(1434, 104))
    s.edge("a9", [(1314, 210), (1480, 210), (1480, 160), (1586, 160)], L_CTL, label="프로세스", at=(1420, 210))
    s.zone("pcC", 20, 300, 760, 240, "직원 PC · 미등록 MCP", "inner", *PINK, "tb-ban")
    s.zone("mintC", 800, 300, 560, 240, "MINT 게이트웨이", "inner", *PURPLE, "tb-device-laptop")
    s.zone("admC", 1380, 300, 400, 240, "관리자 PC", "inner", *GRAY, "tb-device-desktop")
    s.node("emp", 90, 400, "fn", "tb-user", "직원", size=40)
    s.node("blocked", 290, 400, "blocked", None, "미등록 MCP", "직원이 추가", w=150)
    s.node("mset", 290, 494, "data", None, "관리형 설정", "허용 목록 밖은 로드 안 함", w=236)
    s.node("inv", 470, 400, "fn", "tb-zoom-scan", "인벤토리 · 관찰", "설정 · 프로세스", 40)
    s.node("svc", 670, 400, "fn", "tb-settings-cog", "키트 서비스", "장치 보고", 42)
    s.node("report", 900, 400, "fn", "tb-heart-rate-monitor", "장치 보고", "미등록 항목", 40)
    s.node("alerts", 1100, 400, "fn", "tb-bell", "미등록 MCP 경보", size=40)
    s.node("adm_web", 1500, 400, "fn", "tb-browser", "관리자 콘솔", "경보 확인", 42)
    s.node("admin", 1680, 400, "fn", "tb-user-shield", "관리자", size=40)
    s.edge("b1", [(112, 400), (213, 400)], L_CTL, label="직접 추가")
    s.edge("b2", [(290, 466), (290, 429)], BLOCK, label="로드 안 함", at=(350, 448))
    s.edge("b3", [(367, 400), (446, 400)], L_CTL, True, label="관찰")
    s.edge("b4", [(494, 400), (645, 400)], L_CTL)
    s.edge("b5", [(695, 400), (876, 400)], L_CTL, label="장치 보고")
    s.edge("b6", [(924, 400), (1076, 400)], L_CTL, label="미등록 판정")
    s.edge("b7", [(1124, 400), (1475, 400)], L_CTL, label="경보")
    s.edge("b9", [(1525, 400), (1656, 400)], L_CTL, both=True)
    return s


def focus_connector():
    s = Scene(1800, 560, fs=1.15)
    s.zone("pc", 20, 50, 620, 220, "직원 PC · 하네스", "inner", *BLUE, "tb-apps")
    s.zone("gw", 660, 140, 210, 130, "MINT 게이트웨이", "inner", *GRAY, "tb-route")
    s.zone("vend", 890, 50, 890, 220, "벤더 클라우드", "inner", *GRAY, "tb-cloud")
    s.node("claude", 90, 160, "ext", "logo-claude", "Claude Code", size=40)
    s.node("codex", 190, 160, "ext", "logo-codex", "Codex", size=40)
    s.node("builtin", 350, 160, "fn", "tb-world-search", "기본 기능", "웹 검색 · 브라우저 · 컴퓨터 조작", 42)
    s.node("conn", 540, 160, "fn", "tb-plug-connected", "기본 커넥터", "claude.ai 커넥터 · ChatGPT 앱", 42)
    s.node("gwcore", 765, 200, "fn", "tb-route", "요청 중계", "거치지 않음", 36)
    s.node("claudeai", 990, 160, "ext", "logo-claude", "claude.ai", "커넥터 · 기능", 40)
    s.node("chatgpt", 1120, 160, "ext", "logo-openai", "ChatGPT", "앱 · 기능", 40)
    s.zone("saas", 1220, 90, 540, 150, "업무 서비스", "dash", "#777777")
    s.node("gmail", 1310, 165, "ext", "lg-google-gmail", "Gmail", size=34)
    s.node("gdrive", 1430, 165, "ext", "logo-google-drive", "Google Drive", size=34)
    s.node("notion", 1550, 165, "ext", "lg-notion-icon", "Notion", size=34)
    s.node("slack", 1670, 165, "ext", "lg-slack-icon", "Slack", size=34)
    s.edge("u1", [(600, 120), (940, 120)], L_VEN, True, label="벤더 직접 연결", width=2.6)
    s.edge("u2", [(1160, 160), (1236, 160)], L_VEN, True)
    s.zone("adm", 20, 310, 220, 230, "관리자 PC", "inner", *GRAY, "tb-device-desktop")
    s.zone("mint", 260, 310, 520, 230, "MINT 솔루션", "inner", *PURPLE, "tb-server")
    s.zone("pc2", 800, 310, 980, 230, "직원 PC", "inner", *ORANGE, "tb-device-laptop")
    s.node("adm_web", 130, 410, "fn", "tb-browser", "관리자 콘솔", "정책 > 하네스 기능\nMCP 서버 > 커넥터", 42)
    s.node("console", 360, 410, "fn", "tb-layout-dashboard", "콘솔 서비스", "결정 기록", 40)
    s.node("devpol", 560, 410, "data", None, "장치 정책", "차단 항목", w=140)
    s.node("calls", 560, 500, "data", None, "호출 기록", "경로: 커넥터", w=140)
    s.node("svc", 880, 410, "fn", "tb-settings-cog", "키트 서비스", "정책 조회", 42)
    s.node("mset", 1110, 410, "data", None, "관리형 설정", "permissions.deny · 커넥터 끔 · features", w=310)
    s.node("claude2", 1395, 410, "ext", "logo-claude", "Claude Code", size=38)
    s.node("codex2", 1500, 410, "ext", "logo-codex", "Codex", size=38)
    s.node("hook", 1680, 410, "fn", "tb-webhook", "관리형 훅", "PostToolUse 수집분", 40)
    s.edge("c1", [(155, 410), (336, 410)], L_CTL, label="항목별 차단")
    s.edge("c2", [(384, 410), (488, 410)], L_CTL)
    s.edge("c3", [(632, 410), (855, 410)], L_CTL, label="정책 조회")
    s.edge("c4", [(905, 410), (953, 410)], L_CTL)
    s.edge("c5", [(1267, 410), (1370, 410)], L_CTL, label="다음 조회 때")
    s.edge("c6", [(1680, 448), (1680, 506), (632, 506)], L_CTL, True, label="훅 보고 · 수집분만", at=(1150, 506))
    return s


def focus_token():
    s = Scene(1800, 560, fs=1.15)
    s.zone("pc", 20, 50, 1300, 220, "직원 PC", "inner", *ORANGE, "tb-device-laptop")
    s.node("svc", 120, 160, "fn", "tb-settings-cog", "키트 서비스", "장치 키 보관", 46)
    s.node("tok", 380, 160, "data", None, "장치 토큰", "5분 유효 · 3분 캐시", w=170)
    s.node("pipe", 620, 160, "fn", "tb-arrows-exchange", "로컬 통로", "같은 사용자만", 42)
    s.node("helper", 840, 160, "fn", "tb-key", "헤더 도우미", "Authorization 헤더", 42)
    s.node("claude", 1080, 160, "ext", "logo-claude", "Claude Code", size=40)
    s.node("codex", 1200, 160, "ext", "logo-codex", "Codex", size=40)
    s.edge("t2", [(465, 160), (596, 160)], L_CTL)
    s.edge("t3", [(644, 160), (816, 160)], L_CTL)
    s.edge("t4", [(864, 160), (1057, 160)], L_CTL, label="설정 · 환경 변수에 쓰지 않음")
    s.zone("mint", 20, 310, 1300, 230, "MINT 솔루션", "inner", *BLUE, "tb-server")
    s.node("issue", 120, 420, "fn", "tb-ticket", "장치 토큰 발급", "활성 · 정책 일치 장치만", 44)
    s.node("gwcore", 1140, 420, "fn", "tb-route", "요청 중계", "장치 · 정책 해시 · 하트비트 확인", 46)
    s.node("bad1", 560, 395, "blocked", None, "직원 로그인 토큰 · 고정 Bearer", "장치 결속 없음", w=250)
    s.node("bad2", 560, 475, "blocked", None, "격리 · 보고 만료 장치", "발급 · 호출 거부", w=250)
    s.edge("t1", [(120, 186), (120, 396)], L_CTL, label="장치 키", at=(160, 300))
    s.edge("t1b", [(144, 420), (240, 420), (240, 220), (380, 220), (380, 185)], L_CTL, label="5분 토큰", at=(310, 220))
    s.edge("t5", [(1140, 200), (1140, 396)], L_MCP, both=True, width=2.8, label="Bearer 장치 토큰", at=(1205, 300))
    s.edge("x1", [(686, 395), (1116, 410)], BLOCK, True, label="거부", at=(900, 398))
    s.edge("x2", [(434, 475), (200, 475), (200, 440), (144, 440)], BLOCK, True, label="거부", at=(300, 475))
    s.zone("ext", 1340, 50, 440, 490, "원격 MCP", "inner", *GRAY, "tb-server-2")
    s.node("github", 1480, 300, "ext", "logo-github", "GitHub", size=40)
    s.node("hf", 1640, 300, "ext", "logo-huggingface", "Hugging Face", size=40)
    s.edge("t6", [(1164, 420), (1480, 420), (1480, 345)], L_MCP, label="서비스 자격 · 직원 토큰 미전달", at=(1310, 420))
    return s


FOCUS = {
    5: ("원장 · 추적", "판정과 상태는 [PostgreSQL 원장]에 남습니다", focus_store, [
        ("상태 · 감사 원장", ["장치 · 동의 · 승인 · 판정을", "PostgreSQL에 저장합니다"]),
        ("추가만", ["판정 기록은 추가만 하고", "고치지 않습니다"]),
        ("호출 추적", ["게이트웨이 호출 구간을", "Jaeger로 추적합니다"])]),
    7: ("로컬 MCP", "[승인 로컬 MCP]도 게이트웨이 판정 뒤 PC에서 실행됩니다", focus_local, [
        ("승인 로컬 MCP", ["게이트웨이가 판정한 작업만", "Linux PC 실행기가 실행합니다"]),
        ("두 실행 방식", ["이미지는 Docker · Podman 컨테이너,", "승인 소스는 직원 계정 프로세스"]),
        ("미등록 로컬 MCP", ["관리형 하네스는 로드하지 않고", "인벤토리 보고로 경보를 냅니다"])]),
    8: ("기본 기능 · 기본 커넥터", "기본 기능 · 커넥터는 [기본 승인, 항목별 차단]입니다", focus_connector, [
        ("기본 승인", ["관리자 결정이 없으면", "기본 기능 · 커넥터를 씁니다"]),
        ("항목별 차단", ["정책 > 하네스 기능 / MCP 서버 > 커넥터", "에서 막으면 다음 정책 조회 때 적용"]),
        ("게이트웨이 밖 경로", ["벤더가 직접 처리해 판정은 없고", "훅이 수집한 호출만 기록합니다"])]),
    9: ("장치 토큰", "관리형 MCP 연결에는 [장치에 묶인 5분 토큰]만 쓰입니다", focus_token, [
        ("장치 키로 발급", ["키트 서비스가 정상 보고 뒤", "5분 장치 토큰을 받습니다"]),
        ("헤더 도우미로 전달", ["파일 · 환경 변수에 쓰지 않고", "같은 사용자 통로로만 건넵니다"]),
        ("장치 결속 없는 토큰 거부", ["직원 로그인 토큰 · 고정 Bearer와", "격리 장치 요청은 거부합니다"])]),
}


def focus(page, num, section, headline, build, items):
    sc = build()
    body = place(60, 236, 1800, 560, f"0 0 {sc.w} {sc.h}", draw(sc)) + mark(num, 66, 240, 24)
    body += items_below(60, 1860, 236 + 560 + 72, items)
    return slide(section, body + legend_strip(), page, headline)


# ── 시나리오: 역할별 흐름(수영 레인)과 전체에서 보기(단계군별) ───────────────
LANES = {
    "emp": ("직원", "tb-user", "사람", "#FFFFFF"),
    "empui": ("직원 화면", "tb-apps", "하네스 · mint · 직원 콘솔", "#EEF1FF"),
    "kit": ("엔드포인트 키트", "tb-shield-lock", "키트 서비스 · 실행기", "#F4F4F5"),
    "gw": ("게이트웨이", "tb-route", "판정 · 중계 · 장치 관리", "#F4F4F5"),
    "con": ("콘솔 서비스", "tb-layout-dashboard", "계정 · 도입 승인", "#F4F4F5"),
    "sup": ("도입 검증", "tb-file-search", "검사 도구 · Gitea", "#F4F4F5"),
    "ext": ("외부", "tb-world", "원격 MCP · 벤더", "#FFFFFF"),
    "admui": ("관리자 화면", "tb-browser", "관리자 콘솔", "#EEF1FF"),
}
LANE_ORDER = list(LANES)


def st(n, lane, col, title, detail="", cond="", edges=(), nodes=(), badge=None):
    return dict(n=n, lane=lane, col=col, title=title, detail=detail, cond=cond, edges=list(edges), nodes=list(nodes),
                badge=badge)


WEB_ADM = ["web_adm", "web_back"]
MCP = ["mcp_in", "mcp_core"]

SCENARIOS = [
    dict(key="도입", title="MCP 도입",
         headline="도입은 [직원 요청]에서 시작해 [관리자 승인] 뒤 PC 설정으로 돌아옵니다",
         flow_headline="도입 요청은 [키트 → 콘솔 → 게이트웨이 → 키트]로 돕니다",
         steps=[
             st("1", "empui", 0, "도입 요청", "mint request", edges=["mint_svc"], nodes=["mint", "svc"]),
             st("2", "kit", 0, "요청 전달", "장치 인증 · 신청자는 직원", edges=["dev_in", "request_plane"], nodes=["caddy", "epreq"]),
             st("3", "con", 1, "직원 요청 접수", "엔드포인트 요청 저장", nodes=["epreq"]),
             st("4", "admui", 1, "신청서 작성 · 제출", "직원 요청에서 도입 신청", edges=WEB_ADM, nodes=["adm_web", "intake"]),
             st("5a", "gw", 2, "원격 계약 관찰", "도구 목록 · 설명", "원격 MCP", ["mcp_up"], ["gwcore", "github"], (1498, 280)),
             st("5b", "sup", 2, "검사 · PC 계약 관찰", "Syft · Trivy · Semgrep · Gitleaks", "소스 MCP",
                ["intake_sup", "worker_scan"], ["worker", "syft", "trivy", "semgrep", "gitleaks2"]),
             st("6", "admui", 3, "범위 · 기한 지정 승인", "대상 직원 · 도구 · 기한", edges=WEB_ADM, nodes=["adm_web", "intake"]),
             st("7", "gw", 4, "등록 · 계약 잠금", "승인한 계약만 중계", edges=["register_plane"], nodes=["intake", "gwcore"]),
             st("7b", "sup", 4, "승인 소스 보관", "Gitea", "소스 MCP", ["worker_gitea", "gitea_src"], ["gitea", "src"]),
             st("8", "kit", 5, "정책 조회 · 설정 갱신", "관리형 설정 다시 쓰기", edges=["dev_in", "policy_plane", "svc_mset"],
                nodes=["deploy", "mset"]),
             st("9", "empui", 5, "하네스에 표시", "승인 MCP 사용", edges=["mset_hn"], nodes=["claude", "codex"]),
         ],
         arrows=[("1", "2"), ("2", "3"), ("3", "4"), ("4", "5a"), ("4", "5b"), ("5a", "6"), ("5b", "6"), ("6", "7"),
                 ("6", "7b"), ("7", "8"), ("8", "9")],
         phases=[("요청 · 신청", ["1", "2", "3", "4"]), ("검증 · 승인", ["5a", "5b", "6"]),
                 ("등록 · 적용", ["7", "7b", "8", "9"])]),
    dict(key="호출", title="MCP 호출 · 동의 · 승인",
         headline="호출은 [판정 → 재확인 → 중계 → 출력 검사]를 거쳐 돌아옵니다",
         flow_headline="호출은 [장치 토큰]으로 들어와 [서비스 자격]으로 나갑니다",
         steps=[
             st("1", "empui", 0, "도구 호출", "Bearer 장치 토큰 첨부", edges=["harness_helper"] + MCP,
                nodes=["claude", "codex", "helper", "caddy"]),
             st("2", "gw", 1, "신원 · 장치 · 입력 판정", "OPA · Presidio · 범위", edges=["judge"],
                nodes=["gwcore", "opa", "presidio", "scope"]),
             st("3a", "empui", 2, "동의 결정 · 재호출", "직원 콘솔", "동의 필요", ["web_emp", "web_back"],
                ["emp_web", "consent", "console"]),
             st("3b", "admui", 2, "호출 승인", "관리자 콘솔", "고위험 도구", WEB_ADM, ["adm_web", "callappr"]),
             st("4", "gw", 3, "실행 직전 재확인 · 중계", "서비스 자격 · 토큰 미전달", edges=["mcp_up"],
                nodes=["gwcore"], badge=(1498, 280)),
             st("5", "ext", 3, "원격 MCP 실행", "GitHub · Hugging Face", nodes=["github", "hf"]),
             st("6", "gw", 4, "출력 검사", "실패하면 응답 보류", nodes=["presidio", "gitleaks"]),
             st("7", "empui", 5, "결과 수신", "통과한 응답", edges=MCP, nodes=["claude", "codex"], badge=(486, 320)),
             st("8", "kit", 5, "훅 보고", "PostToolUse 수집분", edges=["hook_svc", "dev_in", "calls_plane"],
                nodes=["hook", "calls"], badge=(1092, 488)),
             st("9", "admui", 5, "기록 조회", "호출 기록 · 상세", edges=WEB_ADM, nodes=["console", "ledger"]),
         ],
         arrows=[("1", "2"), ("2", "3a", "동의 필요"), ("3a", "2", "재호출"), ("2", "3b", "승인 필요"),
                 ("3b", "4", "동의 · 승인 유효 시"), ("2", "4", "필요 동의 · 승인 충족"), ("4", "5"), ("5", "6"),
                 ("6", "7", "통과"), ("7", "8", "", "aux"), ("6", "9", "판정 기록")],
         phases=[("호출 · 판정", ["1", "2", "3a", "3b"]), ("중계 · 응답 · 기록", ["4", "5", "6", "7", "8", "9"])]),
    dict(key="미등록", title="미등록 MCP 탐지",
         headline="관리형 하네스는 [미등록 MCP를 로드하지 않고] 경보로 알립니다",
         flow_headline="미등록 MCP는 [인벤토리 → 장치 보고 → 경보]로 드러납니다",
         steps=[
             st("1", "emp", 0, "MCP 직접 추가", "설정 파일 · stdio 서버", nodes=["blocked"]),
             st("2", "empui", 0, "로드 안 함", "관리형 허용 목록 밖", edges=["mset_hn"], nodes=["mset", "claude", "codex"]),
             st("3", "kit", 1, "관찰 · 미등록 보고", "인벤토리 → 장치 보고", edges=["obs", "inv_svc", "dev_in", "report_plane"],
                nodes=["inv", "svc", "report"]),
             st("4", "gw", 2, "미등록 MCP 경보", "관리자 경보 목록", edges=["epm_alert"], nodes=["alerts"]),
             st("5", "admui", 3, "경보 확인", "관리자 콘솔 · 경보", edges=WEB_ADM, nodes=["adm_web"]),
             st("5b", "empui", 3, "미등록 항목 확인", "mint servers", "직원이 볼 때", ["mint_svc"], ["mint"]),
             st("6", "empui", 4, "도입 요청", "MCP 도입 흐름으로", "직원이 쓰려면", ["dev_in", "request_plane"], ["epreq"]),
         ],
         arrows=[("1", "2"), ("2", "3"), ("3", "4"), ("4", "5"), ("4", "5b"), ("5b", "6")],
         phases=[("차단 · 관찰 · 경보", ["1", "2", "3", "4"]), ("확인 · 요청", ["5", "5b", "6"])]),
    dict(key="로컬", title="승인 로컬 MCP 호출",
         headline="승인 로컬 MCP는 [게이트웨이가 판정한 작업]만 PC에서 실행합니다",
         flow_headline="로컬 MCP 호출은 [게이트웨이를 거쳐] 같은 PC의 실행기로 돌아옵니다",
         steps=[
             st("1", "empui", 0, "도구 호출", "게이트웨이 경로 · 장치 토큰", edges=MCP, nodes=["claude", "codex", "caddy"]),
             st("2", "gw", 1, "판정 · 로컬 작업 등록", "같은 정책 · 장치 결속 작업", edges=["judge", "local_plane"],
                nodes=["gwcore", "opa", "ljob"]),
             st("3", "kit", 2, "작업 받기 · 실행", "이미지: 컨테이너 / 소스: 프로세스", edges=["local_in", "runner_mcp"],
                nodes=["runner", "lmcp", "docker", "podman"]),
             st("4", "gw", 3, "결과 받기 · 출력 검사", "마스킹 · 비밀 검사", nodes=["presidio", "gitleaks"]),
             st("5", "empui", 4, "결과 수신", "통과한 응답", edges=MCP, nodes=["claude", "codex"], badge=(486, 320)),
         ],
         arrows=[("1", "2"), ("2", "3", "작업 조회"), ("3", "4", "결과"), ("4", "5", "통과")],
         phases=[("로컬 호출", ["1", "2", "3", "4", "5"])]),
    dict(key="커넥터", title="기본 기능 · 커넥터 차단",
         headline="기본 커넥터는 [벤더로 직접] 가고, 차단은 [관리형 설정]으로 겁니다",
         flow_headline="차단은 [관리자 콘솔 → 장치 정책 → 관리형 설정]으로 내려갑니다",
         steps=[
             st("1", "empui", 0, "기본 커넥터 사용", "claude.ai 커넥터 · ChatGPT 앱", edges=["vendor"],
                nodes=["builtin", "claudeai", "chatgpt"], badge=(900, 12)),
             st("2", "ext", 0, "벤더 클라우드 처리", "게이트웨이 거치지 않음", edges=["saas_link"],
                nodes=["gmail", "gdrive", "notion", "slack"]),
             st("3", "kit", 1, "훅 이벤트 보고", "PostToolUse 수집분", edges=["hook_svc", "dev_in", "calls_plane"],
                nodes=["hook", "calls"], badge=(1092, 488)),
             st("4", "admui", 2, "항목별 차단", "정책 > 하네스 기능 · MCP 서버 > 커넥터", edges=WEB_ADM, nodes=["adm_web", "console"]),
             st("5", "gw", 3, "장치 정책 갱신", "제어 해시 변경", nodes=["devpol", "deploy"]),
             st("6", "kit", 4, "관리형 설정 갱신", "다음 정책 조회 후", edges=["dev_in", "policy_plane", "svc_mset"],
                nodes=["svc", "mset"]),
             st("7", "empui", 4, "차단 설정 적용", "하네스에서 해당 항목 끔", edges=["mset_hn"],
                nodes=["claude", "codex", "builtin"]),
             st("8", "admui", 5, "차단 해제", "되돌리기", "다시 허용할 때", nodes=["adm_web"]),
         ],
         arrows=[("1", "2"), ("2", "3", "", "aux"), ("4", "5"), ("5", "6"), ("6", "7"), ("7", "8")],
         phases=[("사용 · 기록", ["1", "2", "3"]), ("차단 · 적용", ["4", "5", "6", "7", "8"])]),
    dict(key="격리", title="변조 감지 · 격리 · 복구",
         headline="보호 설정이 바뀌면 [장치를 격리]하고, [사람이 확인]해야 풀립니다",
         flow_headline="격리와 복구는 [장치 보고]와 [관리자 콘솔] 사이에서 오갑니다",
         steps=[
             st("1", "kit", 0, "무결성 이상 감지 · 보고", "관리형 설정 해시 불일치", edges=["dev_in", "report_plane"],
                nodes=["svc", "mset", "report"]),
             st("2", "gw", 1, "장치 격리", "MCP 호출 · 토큰 발급 거부", nodes=["quar", "token"], badge=(728, 482)),
             st("3", "admui", 2, "격리 경보", "관리자 콘솔", edges=["epm_alert"] + WEB_ADM, nodes=["alerts", "adm_web"]),
             st("3b", "empui", 2, "연결 불가 표시", "mint · 하네스", nodes=["mint"]),
             st("4", "kit", 3, "설정 복구 · 정상 보고", "검사 통과 하트비트", "사람이 복구", ["dev_in", "report_plane"],
                ["mset", "report"]),
             st("5", "admui", 4, "재활성화", "180초 안 정상 보고 · 정책 일치", edges=WEB_ADM, nodes=["adm_web"]),
             st("6", "kit", 5, "장치 토큰 발급", "장치 키 → 5분 토큰", edges=["dev_in", "token_plane"], nodes=["token", "svc"]),
             st("7", "empui", 5, "MCP 다시 사용", "헤더 도우미로 토큰 전달", edges=["helper_svc", "harness_helper"],
                nodes=["helper", "claude", "codex"]),
         ],
         arrows=[("1", "2"), ("2", "3"), ("2", "3b"), ("3", "4"), ("4", "5"), ("5", "6"), ("6", "7")],
         phases=[("감지 · 격리", ["1", "2", "3", "3b"]), ("복구 · 재사용", ["4", "5", "6", "7"])]),
]


def wrap(s, size, width):
    words, lines, cur = s.split(" "), [], ""
    for wd in words:
        trial = (cur + " " + wd).strip()
        if cur and tw(trial, size) > width:
            lines.append(cur)
            cur = wd
        else:
            cur = trial
    lines.append(cur)
    return lines


def badge(x, y, n, cond=False, r=17, gray=False):
    if gray:
        fill, stroke, color = "#B7BCC4", "#B7BCC4", "#FFFFFF"
    elif cond:
        fill, stroke, color = "#FFFFFF", ACCENT, ACCENT
    else:
        fill, stroke, color = ACCENT, ACCENT, "#FFFFFF"
    size = r * (0.9 if len(n) < 2 else 0.76)
    return (f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="2.5"/>'
            + text(x, y + size * 0.36, n, size, 800, color))


def arrow_label(x, y, s):
    w = tw(s, 14) + 14
    return (f'<rect x="{x - w / 2:.1f}" y="{y - 11}" width="{w:.1f}" height="22" rx="5" fill="#FFFFFF" stroke="#D5D9DF"/>'
            + text(x, y + 5, s, 14, 700, "#4A4F57"))


def blueprint(page, sc):
    steps = sc["steps"]
    lanes = [k for k in LANE_ORDER if any(s["lane"] == k for s in steps)]
    top, bottom = 236, 1040
    lh = (bottom - top) / len(lanes)
    x0, x1 = 300, SW - 50
    ncol = max(s["col"] for s in steps) + 1
    colw = (x1 - x0) / ncol
    cw, ch = min(250, colw - 30), min(112, lh - 24)
    out = [f"<defs>{markers([L_CTL, '#9AA0A6'])}</defs>"]
    ly = {}
    for i, k in enumerate(lanes):
        name, ic, sub, fill = LANES[k]
        y = top + i * lh
        ly[k] = y + lh / 2
        out.append(f'<rect x="50" y="{y}" width="{SW - 100}" height="{lh}" fill="{fill}" stroke="#D5D9DF" stroke-width="1"/>')
        out.append(f'<rect x="50" y="{y}" width="236" height="{lh}" fill="rgba(0,0,0,0.035)"/>')
        out.append(img(ic, 64, ly[k] - 17, 34))
        out.append(text(108, ly[k] + 2, name, 22, 800, INK, "start"))
        out.append(text(108, ly[k] + 26, sub, 14, 500, MUTED, "start"))
    pos = {s["n"]: (x0 + colw * (s["col"] + 0.5), ly[s["lane"]]) for s in steps}
    by_n = {s["n"]: s for s in steps}
    k = L_CTL.lstrip("#")
    labels = []
    for a, b, *lab in sc["arrows"]:
        (ax, ay), (bx, by_) = pos[a], pos[b]
        aux = lab[1:] == ["aux"]
        cond = by_n[a]["cond"] or by_n[b]["cond"] or aux
        dash = ' stroke-dasharray="7 5"' if cond else ""
        color = "#9AA0A6" if aux else L_CTL
        if abs(ax - bx) < 1:                                  # 같은 열: 위아래로
            d = 1 if by_ > ay else -1
            pts = [(ax, ay + d * ch / 2), (bx, by_ - d * (ch / 2 + 3))]
        elif bx < ax:                                         # 되돌아가기: 카드 위로 돌아간다
            ry = min(ay, by_) - ch / 2 - 30
            pts = [(ax, ay - ch / 2 - (12 if by_n[a]["cond"] else 0)), (ax, ry), (bx, ry), (bx, by_ - ch / 2 - 3)]
        elif abs(ay - by_) < 1:
            pts = [(ax + cw / 2, ay), (bx - cw / 2 - 3, by_)]
        else:
            mx = (ax + cw / 2 + bx - cw / 2) / 2
            pts = [(ax + cw / 2, ay), (mx, ay), (mx, by_), (bx - cw / 2 - 3, by_)]
        out.append(f'<path d="{path_d(pts)}" fill="none" stroke="{color}" stroke-width="2.2"{dash} '
                   f'stroke-linejoin="round" marker-end="url(#a{color.lstrip("#")})"/>')
        if lab and lab[0]:
            lx, lyy = midpoint(pts)
            if len(pts) == 4 and pts[0][1] == pts[1][1]:   # 꺾인 선: 출발 카드 옆 여백에 둔다
                d = 1 if pts[2][1] > pts[1][1] else -1
                lx, lyy = pts[1][0], pts[1][1] + d * (ch / 2 + 16)
            labels.append(arrow_label(lx, lyy, lab[0]))
    for s in steps:
        cx, cy = pos[s["n"]]
        left, topc = cx - cw / 2, cy - ch / 2
        dash = ' stroke-dasharray="6 4"' if s["cond"] else ""
        out.append(f'<rect x="{left}" y="{topc}" width="{cw}" height="{ch}" rx="12" fill="#FFFFFF" '
                   f'stroke="{"#8C96F8" if s["cond"] else ACCENT}" stroke-width="2"{dash}/>')
        tl = wrap(s["title"], 24, cw - 36)
        dl = wrap(s["detail"], 18, cw - 22) if s["detail"] else []
        block = len(tl) * 29 + len(dl) * 22
        y = cy - block / 2 + 22
        for line in tl:
            out.append(text(cx + 6, y, line, 24, 800, INK))
            y += 29
        for line in dl:
            out.append(text(cx + 6, y - 3, line, 18, 500, "#5F6670"))
            y += 22
        out.append(badge(left + 4, topc + 4, s["n"], bool(s["cond"]), 17))
        if s["cond"]:
            w = tw(s["cond"], 13.5) + 22
            out.append(f'<rect x="{cx - w / 2}" y="{topc - 12}" width="{w}" height="23" rx="11.5" fill="#E9EBF0" stroke="#C9CED6"/>'
                       + text(cx, topc + 4.5, s["cond"], 13.5, 700, "#4A4F57"))
    return slide(f"{sc['title']} · 역할별 흐름", "".join(out + labels), page, sc["headline"])


def anchor_of(s):
    if s["badge"]:
        return s["badge"], s["badge"]
    if s["edges"]:
        e = s["edges"][-1]
        if e.endswith("_plane"):   # 같은 Caddy 버스를 쓰므로 끝(처리 기능) 옆에 둔다
            ex, ey = M.edges[e]["pts"][-1]
            return (ex + 22, ey + 8), e
        return midpoint(M.edges[e]["pts"]), e
    n = M.nodes[s["nodes"][0]]
    return (n["x"] + n["size"] / 2 + 14, n["y"] - n["size"] / 2 - 12), s["nodes"][0]


def chips(names, current, y=236):
    out, x = [], 40
    for i, name in enumerate(names):
        w = tw(name, 24) + 56
        on = i == current
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="50" rx="10" fill="{ACCENT if on else "#FFFFFF"}" '
                   f'stroke="{ACCENT if on else "#D9DDE6"}" stroke-width="1.5"/>'
                   + text(x + w / 2, y + 34, name, 24, 800, "#FFFFFF" if on else INK))
        x += w
        if i < len(names) - 1:
            out.append(f'<path d="M{x + 12},{y + 13} l18,12 l-18,12 z" fill="#A6CAEC"/>')
            x += 42
    return "".join(out)


def flow(page, sc, pi):
    names = [p[0] for p in sc["phases"]]
    by_n = {s["n"]: s for s in sc["steps"]}
    cur = [by_n[n] for n in sc["phases"][pi][1]]
    prev = [by_n[n] for _, ns in sc["phases"][:pi] for n in ns]
    cur_e, cur_n, prev_e = [], [], []
    for s in cur:
        cur_e += [e for e in s["edges"] if e not in cur_e]
        cur_n += [n for n in s["nodes"] if n not in cur_n]
    for s in prev:
        prev_e += [e for e in s["edges"] if e not in prev_e and e not in cur_e]
    every = sc["steps"]
    pts = [p for s in every for e in s["edges"] for p in M.edges[e]["pts"]]
    pts += [(M.nodes[n]["x"], M.nodes[n]["y"]) for s in every for n in s["nodes"]]
    pts += [anchor_of(s)[0] for s in every]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    w, h = max(max(xs) - min(xs) + 160, 760), max(max(ys) - min(ys) + 150, 420)
    box_x, box_y, box_w, box_h = 40, 306, 1400, 734
    view = crop_view([(cx - w / 2, cy - h / 2, w, h)], 0, box_w / box_h)
    over = ['<defs><filter id="blur" x="-2%" y="-2%" width="104%" height="104%"><feGaussianBlur stdDeviation="2.2"/></filter></defs>',
            f'<g filter="url(#blur)">{draw(M)}</g>',
            f'<rect x="-50" y="-50" width="{M.w + 100}" height="{M.h + 100}" fill="rgba(255,255,255,0.55)"/>',
            f"<defs>{markers([ACCENT, '#9AA0A6'])}</defs>"]
    over += [render_edge(M.edges[e], "#9AA0A6", 3.2, labels=False) for e in prev_e]
    over += [render_edge(M.edges[e], ACCENT, 4.6) for e in cur_e]
    over += [render_node(M.nodes[n]) for n in cur_n]
    taken = {}
    for group, gray in ((prev, True), (cur, False)):
        for s in group:
            (x, y), key = anchor_of(s)
            shift = taken.get(key, 0)
            taken[key] = shift + 1
            over.append(badge(x + shift * 34, y, s["n"], bool(s["cond"]), 16, gray))
    body = [chips(names, pi) if len(names) > 1 else "",
            f'<rect x="{box_x}" y="{box_y}" width="{box_w}" height="{box_h}" fill="#FFFFFF"/>',
            framed(box_x, box_y, box_w, box_h, " ".join(f"{v:.1f}" for v in view), "".join(over))]
    px = box_x + box_w + 36
    row = min(118, (box_h - 20) / len(cur))
    for i, s in enumerate(cur):
        y = box_y + 34 + i * row
        body.append(badge(px + 20, y, s["n"], bool(s["cond"]), 20))
        body.append(text(px + 54, y + 9, s["title"], 25, 800, INK, "start"))
        dy = y + 42
        if s["cond"]:
            cw_ = tw(s["cond"], 14) + 20
            body.append(f'<rect x="{px + 54}" y="{dy - 17}" width="{cw_}" height="23" rx="11.5" fill="#E9EBF0"/>'
                        + text(px + 54 + cw_ / 2, dy, s["cond"], 14, 700, "#4A4F57"))
            dy += 30
        for line in wrap(s["detail"], 19, SW - 60 - px - 54)[:2]:
            body.append(text(px + 54, dy, line, 19, 500, TEXT2, "start"))
            dy += 25
    section = f"{sc['title']} · 전체에서 보기"
    return slide(section, "".join(body), page, sc["flow_headline"])


# ── 출력 ─────────────────────────────────────────────────────────────────────
def to_png(svg_path, png_path, scale=2):
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={profile}",
                        f"--window-size={SW},{SH}", f"--force-device-scale-factor={scale}",
                        f"--screenshot={png_path}", svg_path.as_uri()], check=True, capture_output=True, timeout=180)


def check():
    for sc in SCENARIOS:
        ns = [s["n"] for s in sc["steps"]]
        for s in sc["steps"]:
            assert all(e in M.edges for e in s["edges"]), (sc["key"], s["n"], s["edges"])
            assert all(n in M.nodes for n in s["nodes"]), (sc["key"], s["n"], s["nodes"])
            assert s["lane"] in LANES, (sc["key"], s["n"])
            assert s["badge"] or s["edges"] or s["nodes"], (sc["key"], s["n"], "전체도에 번호 자리가 없다")
        assert all(a in ns and b in ns for a, b, *_ in sc["arrows"]), sc["key"]
        cells = [(s["lane"], s["col"]) for s in sc["steps"]]
        assert len(cells) == len(set(cells)), (sc["key"], "같은 칸에 두 단계")
        assert max(s["col"] for s in sc["steps"]) < 6, (sc["key"], "6열 초과")
        assert sorted(n for _, p in sc["phases"] for n in p) == sorted(ns), (sc["key"], "단계군 누락")


def build_pages():
    pages = [overview, area_map]
    for num in sorted({**ZOOMS, **FOCUS}):
        if num in ZOOMS:
            pages.append(lambda p, num=num: zoom(p, num, *ZOOMS[num]))
        else:
            pages.append(lambda p, num=num: focus(p, num, *FOCUS[num]))
    for sc in SCENARIOS:
        pages.append(lambda p, sc=sc: blueprint(p, sc))
        for pi in range(len(sc["phases"])):
            pages.append(lambda p, sc=sc, pi=pi: flow(p, sc, pi))
    return [make(i) for i, make in enumerate(pages, 1)]


def main():
    check()
    stamp = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%m%d%H%M")
    out = ROOT / "export" / f"MINT_구조도_{stamp}"
    out.mkdir(parents=True, exist_ok=True)
    pages = build_pages()
    only = {int(p) for p in sys.argv[2].split(",")} if len(sys.argv) > 2 else None
    pngs = []
    for i, svg in enumerate(pages, 1):
        svg_path = out / f"p{i:02d}.svg"
        svg_path.write_text(svg, encoding="utf-8")
        png = out / f"p{i:02d}.png"
        if only is None or i in only:
            to_png(svg_path, png)
        pngs.append(png)
    if only is None:
        from PIL import Image
        jpgs = []
        for png in pngs:
            jpg = png.with_suffix(".jpg")
            Image.open(png).convert("RGB").save(jpg, quality=90, optimize=True)
            jpgs.append(jpg)
        import fitz
        pdf = fitz.open()
        for jpg in jpgs:
            page = pdf.new_page(width=SW * 0.5, height=SH * 0.5)
            page.insert_image(page.rect, filename=str(jpg))
        pdf.save(out.parent / f"MINT_구조도_{stamp}.pdf")
        from pptx import Presentation
        from pptx.util import Emu
        deck = Presentation()
        deck.slide_width, deck.slide_height = Emu(12192000), Emu(6858000)
        for jpg in jpgs:
            s = deck.slides.add_slide(deck.slide_layouts[6])
            s.shapes.add_picture(str(jpg), 0, 0, deck.slide_width, deck.slide_height)
        deck.save(out.parent / f"MINT_구조도_{stamp}.pptx")
    print(out, len(pages))


if __name__ == "__main__":
    main()
