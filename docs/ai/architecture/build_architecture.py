"""MINT 아키텍처 구조도 — 한 배치 정의에서 draw.io(편집용)와 SVG(미리보기·Claude Design)를 만든다.

python -X utf8 build_architecture.py            → MINT_아키텍처.drawio, preview/page-N.svg
아이콘: icons/raw/<key>.svg|png (출처 icons/sources.json). 없는 아이콘은 분류 색 원으로 대신한다.
"""
import base64, html, json, math, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ICONS = ROOT / "icons" / "raw"
FONT = "Noto Sans KR"

# 분류 → 색 (범례 순서)
CAT = {
    "사용자": "#C9962B", "하네스": "#E8A600", "엔드포인트": "#EF7D22", "망·진입": "#1E9E9A",
    "게이트웨이": "#2F6FD6", "정책·검사": "#D93A3A", "데이터·감사": "#2E4A6B", "관측·연동": "#7B3FA0",
    "공급망·실행": "#5E9E2F", "MCP 서버": "#0F9D84", "모델": "#B0367C", "외부·기업": "#66727F",
    "거버넌스": "#3D4E66", "차단": "#D93A3A",
}
EDGE = {  # 종류 → (색, 대시, 굵기)
    "mcp": ("#E8A600", None, 2.2), "ctl": ("#3B7DD8", None, 1.6), "llm": ("#B0367C", None, 1.8),
    "plan": ("#8A94A3", "6 4", 1.5), "blk": ("#D93A3A", "5 4", 1.8), "net": ("#1E9E9A", "2 3", 1.6),
}
EDGE_NAME = {"mcp": "MCP 호출", "ctl": "제어·데이터", "llm": "모델 호출", "net": "Tailscale 연결",
             "plan": "개발 예정·연동 대상", "blk": "차단"}
COLUMN_BLUE = "#3B7DD8"
TEXT = "#1F3A5F"


# ── 아이콘 ────────────────────────────────────────────────────────────────
def _clean_svg(raw: str) -> str:
    raw = re.sub(r"<\?xml[^>]*>|<!DOCTYPE[^>]*>", "", raw, flags=re.S)
    raw = re.sub(r"<(script|foreignObject)\b.*?</\1>", "", raw, flags=re.S | re.I)
    raw = re.sub(r"\son[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*')", "", raw, flags=re.I)
    raw = re.sub(r"(xlink:)?href\s*=\s*([\"'])(?!#|data:)[^\"']*\2", "", raw, flags=re.I)
    return raw.strip()


_icon_cache = {}


def icon(key):
    """(mime, base64) 또는 None"""
    if key in _icon_cache:
        return _icon_cache[key]
    out = None
    for ext, mime in (("svg", "image/svg+xml"), ("png", "image/png")):
        p = ICONS / f"{key}.{ext}"
        if p.exists():
            data = p.read_bytes()
            if ext == "svg":
                data = _clean_svg(data.decode("utf-8", "replace")).encode()
            out = (mime, base64.b64encode(data).decode())
            break
    _icon_cache[key] = out
    return out


# ── 배치 정의 ────────────────────────────────────────────────────────────
class Page:
    def __init__(self, name, w, h):
        self.name, self.w, self.h = name, w, h
        self.boxes, self.nodes, self.edges, self.texts = [], {}, [], []

    def box(self, id, label, x, y, w, h, kind="grp", color=None, icon_key=None, la="l"):
        self.boxes.append(dict(id=id, label=label, x=x, y=y, w=w, h=h, kind=kind, color=color, icon=icon_key, la=la))

    def node(self, id, label, icon_key, x, y, cat, size=52, status="", cmp="", tip="", lp="b"):
        self.nodes[id] = dict(id=id, label=label, icon=icon_key, x=x, y=y, cat=cat, size=size,
                              status=status, cmp=cmp, tip=tip, lp=lp)

    def edge(self, a, b, kind="ctl", label="", pts=(), lab_at=None):
        self.edges.append(dict(a=a, b=b, kind=kind, label=label, pts=list(pts), lab_at=lab_at))

    def text(self, s, x, y, size=11, color=TEXT, bold=False, anchor="start", opacity=1.0):
        self.texts.append(dict(s=s, x=x, y=y, size=size, color=color, bold=bold, anchor=anchor, opacity=opacity))

    # 끝점: 노드는 원, 상자는 사각형
    def shape(self, id):
        if id in self.nodes:
            n = self.nodes[id]
            return ("c", n["x"], n["y"], n["size"] / 2 + 3)
        b = next(b for b in self.boxes if b["id"] == id)
        return ("r", b["x"], b["y"], b["w"], b["h"])


def clip(shape, px, py, qx, qy, ortho=False):
    """shape 경계에서 (px,py)→(qx,qy) 방향으로 나가는 점. ortho면 꺾임점과 같은 x/y 직선으로 붙인다"""
    if shape[0] == "c":
        _, cx, cy, r = shape
        if ortho and abs(qy - cy) < r and abs(qx - cx) >= r:
            return cx + math.copysign(math.sqrt(r * r - (qy - cy) ** 2), qx - cx), qy
        if ortho and abs(qx - cx) < r and abs(qy - cy) >= r:
            return qx, cy + math.copysign(math.sqrt(r * r - (qx - cx) ** 2), qy - cy)
        dx, dy = qx - cx, qy - cy
        d = math.hypot(dx, dy) or 1
        return cx + dx / d * r, cy + dy / d * r
    _, x, y, w, h = shape
    cx, cy = px, py
    dx, dy = qx - cx, qy - cy
    ts = []
    if dx: ts += [((x - cx) / dx), ((x + w - cx) / dx)]
    if dy: ts += [((y - cy) / dy), ((y + h - cy) / dy)]
    ts = [t for t in ts if t > 0]
    for t in sorted(ts):
        ex, ey = cx + dx * t, cy + dy * t
        if x - 0.5 <= ex <= x + w + 0.5 and y - 0.5 <= ey <= y + h + 0.5:
            return ex, ey
    return px, py


def _box_attach(rect, tx, ty):
    """상자 테두리에서 (tx, ty) 쪽으로 수평·수직으로 나가는 점"""
    x, y, w, h = rect
    if x <= tx <= x + w:
        return tx, (y + h if ty > y + h else y)
    if y <= ty <= y + h:
        return (x + w if tx > x + w else x), ty
    cx, cy = x + w / 2, y + h / 2
    return clip(("r", x, y, w, h), cx, cy, tx, ty)


def route(page, e):
    """노드·상자 경계를 잘라낸 꺾은선 좌표 (draw.io에도 같은 접속점을 넘긴다)"""
    sa, sb = page.shape(e["a"]), page.shape(e["b"])
    pts = e["pts"]
    ca = (sa[1], sa[2]) if sa[0] == "c" else None
    cb = (sb[1], sb[2]) if sb[0] == "c" else None
    if pts:
        first, last = pts[0], pts[-1]
        start = clip(sa, *ca, *first, ortho=True) if ca else _box_attach(sa[1:], *first)
        end = clip(sb, *cb, *last, ortho=True) if cb else _box_attach(sb[1:], *last)
    elif ca and cb:
        start, end = clip(sa, *ca, *cb), clip(sb, *cb, *ca)
    elif ca:  # 노드 → 상자
        end = _box_attach(sb[1:], *ca)
        start = clip(sa, *ca, *end, ortho=True)
    elif cb:  # 상자 → 노드
        start = _box_attach(sa[1:], *cb)
        end = clip(sb, *cb, *start, ortho=True)
    else:
        start = _box_attach(sa[1:], sb[1] + sb[3] / 2, sb[2] + sb[4] / 2)
        end = _box_attach(sb[1:], *start)
    return [start, *pts, end]


# ── 페이지 1: 전체 아키텍처 ─────────────────────────────────────────────
def page1():
    p = Page("1 전체 아키텍처", 1820, 1140)
    cols = [("사용자", 10, 150), ("직원 PC", 160, 340), ("사설망", 500, 100), ("솔루션 기기", 600, 780),
            ("MCP 서버", 1380, 210), ("기업·외부", 1590, 220)]
    for i, (t, x, w) in enumerate(cols):
        p.box(f"col{i}", t, x, 10, w, 895, kind="col")
    p.box("acct", "관리 계정", 185, 75, 305, 355)
    p.box("kit", "엔드포인트 키트", 185, 450, 305, 230)
    p.box("ingress", "진입", 615, 75, 150, 485)
    p.box("gw", "게이트웨이 판정", 780, 240, 360, 315)
    p.box("obs", "관측", 1155, 440, 210, 115)
    p.box("mgmt", "관리·데이터", 615, 610, 265, 280)
    p.box("supply", "공급망·실행", 900, 610, 465, 280)
    p.box("scan", "검사 도구", 905, 765, 190, 115, kind="sub")
    p.box("iso", "격리 실행망", 1180, 740, 175, 140, kind="sub", la="r")
    p.box("mcp", "등록 MCP", 1395, 300, 180, 260)
    p.box("llm", "LLM 제공자", 1605, 75, 190, 130)
    p.box("sso", "조직 SSO", 1605, 245, 190, 145)
    p.box("lab", "연동 시험", 1605, 650, 190, 240, kind="lab")
    p.box("gov", "보안·거버넌스", 20, 920, 580, 205)
    p.box("plan", "개발 예정", 615, 920, 750, 205, kind="lab")
    p.box("legend", "", 1380, 920, 430, 205, kind="legend")

    n = p.node
    n("user", "직원", "flat-employee", 85, 150, "사용자", 56, cmp="CMP-01")
    n("admin", "보안 관리자", "flat-admin", 85, 715, "사용자", 56, cmp="CMP-02")
    for x, (id, lab, ic, st, c) in zip((225, 300, 375, 450), [
        ("claude", "Claude Code", "logo-claude", "", "CMP-03"), ("codex", "Codex CLI", "logo-openai", "", "CMP-04"),
        ("gemini", "Gemini CLI", "logo-gemini", "시험용", "CMP-05"), ("opencode", "OpenCode", "logo-opencode", "시험용", "CMP-06")]):
        n(id, lab, ic, x, 150, "하네스", 48, st, c)
    n("shim", "진입 래퍼", "flat-terminal", 240, 300, "엔드포인트", 46, cmp="CMP-08")
    n("cfg", "관리형 설정", "flat-gear", 340, 300, "엔드포인트", 46, cmp="CMP-09")
    n("helper", "헤더 헬퍼", "flat-key", 440, 300, "엔드포인트", 46, cmp="CMP-10")
    n("apparmor", "AppArmor", "logo-apparmor", 225, 520, "엔드포인트", 44, cmp="CMP-12")
    n("nft", "nftables", "logo-nftables", 300, 520, "엔드포인트", 44, cmp="CMP-13")
    n("winfw", "Windows 방화벽", "flat-firewall", 375, 520, "엔드포인트", 44, "시험 중", "CMP-16")
    n("observer", "OS 관측기", "flat-eye", 450, 520, "엔드포인트", 44, cmp="CMP-11")
    n("installer", "키트 설치기", "flat-installer", 265, 625, "엔드포인트", 44, cmp="CMP-07")
    n("wizard", "마법사·트레이", "flat-wizard", 395, 625, "엔드포인트", 44, "시험 중", "CMP-14")
    n("localmcp", "비인가 로컬 MCP", "logo-mcp", 340, 820, "차단", 46, "차단")
    n("tailscale", "Tailscale", "logo-tailscale", 550, 380, "망·진입", 60, cmp="CMP-17")
    n("mproxy", "모델 프록시", "flat-proxy", 690, 140, "망·진입", 50, cmp="CMP-19")
    n("caddy", "Caddy", "logo-caddy", 690, 380, "망·진입", 52, cmp="CMP-18", lp="t")
    n("gateway", "MCP 게이트웨이", "flat-shield", 960, 380, "게이트웨이", 78, cmp="CMP-20")
    n("authlib", "Authlib", "logo-authlib", 850, 300, "정책·검사", 46, cmp="CMP-24")
    n("opa", "OPA", "logo-opa", 1070, 300, "정책·검사", 46, cmp="CMP-26")
    n("presidio", "Presidio", "logo-presidio", 850, 470, "정책·검사", 46, cmp="CMP-28")
    n("gitleaks", "Gitleaks", "logo-gitleaks", 1070, 470, "정책·검사", 46, cmp="CMP-29")
    n("jaeger", "Jaeger", "logo-jaeger", 1215, 500, "관측·연동", 44, cmp="CMP-31")
    n("siemw", "SIEM 전달", "logo-ocsf", 1310, 500, "관측·연동", 44, cmp="CMP-33", lp="t")
    n("console", "관리 콘솔", "flat-dashboard", 690, 700, "게이트웨이", 52, cmp="CMP-21")
    n("pg", "PostgreSQL", "logo-postgresql", 830, 700, "데이터·감사", 52, cmp="CMP-30")
    n("intake", "도입 검증", "flat-scan", 960, 690, "공급망·실행", 48, cmp="CMP-35")
    n("gitea", "내부 Git", "logo-gitea", 1060, 690, "공급망·실행", 48, cmp="CMP-39")
    n("runtime", "MCP 실행기", "flat-container", 1160, 690, "공급망·실행", 48, cmp="CMP-40", lp="t")
    n("syft", "Syft", "logo-syft", 945, 815, "공급망·실행", 36, cmp="CMP-36")
    n("trivy", "Trivy", "logo-trivy", 1000, 815, "공급망·실행", 36, cmp="CMP-37")
    n("semgrep", "Semgrep", "logo-semgrep", 1055, 815, "공급망·실행", 36, cmp="CMP-38")
    n("toolhive", "ToolHive", "logo-toolhive", 1135, 815, "공급망·실행", 38, "재검토", "CMP-43")
    n("markitdown", "MarkItDown", "logo-markitdown", 1225, 810, "MCP 서버", 42, cmp="CMP-44")
    n("egress", "출구 프록시", "flat-proxy", 1310, 810, "망·진입", 40, cmp="CMP-42")
    n("githubmcp", "GitHub", "logo-github", 1440, 370, "MCP 서버", 46, cmp="CMP-45")
    n("context7", "Context7", "logo-context7", 1530, 370, "MCP 서버", 46, cmp="CMP-46")
    n("labmcp", "랩 MCP 10종", "logo-mcp", 1440, 490, "MCP 서버", 46, "시험용", "CMP-47")
    n("playwright", "Playwright", "logo-playwright", 1530, 490, "MCP 서버", 46, "시험용", "CMP-48")
    n("anthropic", "Anthropic", "logo-anthropic", 1655, 140, "모델", 48, cmp="CMP-51")
    n("openai", "OpenAI", "logo-openai", 1745, 140, "모델", 48, cmp="CMP-51")
    n("idp", "고객 IdP", "flat-id-card", 1655, 315, "외부·기업", 46, "연동 대상", "CMP-55")
    n("keycloak", "Keycloak", "logo-keycloak", 1745, 315, "외부·기업", 46, "시험용", "CMP-25")
    n("siem", "고객 SIEM", "flat-alert", 1700, 585, "관측·연동", 46, "도입 예정", "CMP-56")
    n("openbao", "OpenBao", "logo-openbao", 1655, 715, "외부·기업", 44, "연동 시험", "CMP-52")
    n("litellm", "LiteLLM", "logo-litellm", 1745, 715, "모델", 44, "연동 시험", "CMP-49", lp="t")
    n("corp", "회사 시스템", "flat-web", 1655, 830, "외부·기업", 44, "시험용", "CMP-57")
    n("ollama", "Ollama", "logo-ollama", 1745, 830, "모델", 44, "연동 시험", "CMP-50")
    for x, (id, lab, ic) in zip((95, 215, 335, 455, 545), [
        ("pol", "보안 정책 50", "flat-policy"), ("reg", "규제 근거", "flat-scale"), ("ledger", "감사 원장", "flat-ledger"),
        ("revoke", "종료·폐기", "flat-trash"), ("sheet", "통합 시트", "logo-google-sheets")]):
        n(id, lab, ic, x, 1010, "거버넌스", 50)
    for x, (id, lab, ic, tip) in zip((690, 800, 910, 1020, 1130, 1240), [
        ("consent", "사용자 동의", "flat-handshake", "G02.05"), ("purpose", "전송 목적 결속", "flat-tag", "G04.05"),
        ("inmask", "입력 마스킹", "flat-mask", "G04.06"), ("taint", "중요정보 전파", "flat-chain", "G04.07"),
        ("compare", "효과 비교 평가", "logo-pyrit", "G10.05"), ("incident", "사고 증빙·기한", "flat-timer", "DEV-66")]):
        n(id, lab, ic, x, 985, "거버넌스", 42, "도입 예정", tip=tip)
    for x, (id, lab, ic, tip) in zip((745, 855, 965, 1075, 1185), [
        ("retain", "원장 보존", "flat-archive", "DEV-67"), ("supplier", "공급자 보증", "flat-certificate", "DEV-68"),
        ("border", "국외 이전 규칙", "flat-passport", "DEV-69"), ("human", "인적 개입", "flat-scale", "DEV-70"),
        ("risk", "위험 등급", "flat-gauge", "DEV-71")]):
        n(id, lab, ic, x, 1075, "거버넌스", 42, "도입 예정", tip=tip)

    e = p.edge
    e("user", "acct", "mcp")
    e("acct", "tailscale", "mcp")
    e("tailscale", "caddy", "mcp", "HTTPS")
    e("tailscale", "mproxy", "llm", "LLM", pts=[(550, 140)])
    e("caddy", "gateway", "mcp")
    for s in ("authlib", "opa", "presidio", "gitleaks"):
        e("gateway", s, "ctl")
    e("gateway", "mcp", "mcp", "MCP")
    e("mproxy", "llm", "llm")
    e("authlib", "sso", "ctl", "OIDC", pts=[(850, 225), (1700, 225)], lab_at=1)
    e("gw", "jaeger", "ctl")
    e("siemw", "siem", "plan", "OCSF", pts=[(1310, 585)])
    e("gw", "markitdown", "mcp", pts=[(1010, 590), (1225, 590)])
    e("gw", "pg", "ctl", "원장", pts=[(830, 600)])
    e("caddy", "console", "ctl")
    e("console", "pg", "ctl")
    e("admin", "console", "mcp", "HTTPS", pts=[(640, 715)])
    e("mgmt", "intake", "ctl", pts=[(890, 690)])
    e("intake", "gitea", "ctl")
    e("gitea", "runtime", "ctl")
    e("runtime", "markitdown", "ctl", pts=[(1160, 810)])
    e("markitdown", "egress", "ctl")
    e("acct", "localmcp", "blk", pts=[(172, 400), (172, 820)])
    e("observer", "console", "ctl", "이벤트", pts=[(575, 520), (575, 688)], lab_at=1)
    e("litellm", "ollama", "llm")
    return p


# ── 페이지 2: 망·배치 ────────────────────────────────────────────────────
def page2():
    p = Page("2 망·배치", 1640, 1190)
    p.box("ext", "인터넷", 30, 20, 1580, 170)
    p.box("laptop", "개발 노트북 · Windows 11", 30, 250, 400, 360, icon_key="logo-windows11")
    p.box("wsl", "WSL · Kali", 210, 310, 200, 280, kind="sub", icon_key="logo-kali")
    p.box("appl", "솔루션 기기 · Windows + WSL2", 1150, 250, 460, 560, icon_key="logo-docker")
    p.box("field", "현장 스택", 1170, 310, 420, 250, kind="sub")
    p.box("rtnet", "실행 격리망", 1170, 580, 200, 210, kind="sub")
    p.box("interop", "연동 랩", 1390, 580, 200, 210, kind="lab")
    p.box("pj1", "PJ1 · Ubuntu", 30, 650, 400, 360, icon_key="logo-ubuntu")
    p.box("pj3", "pj3 · Windows 11", 470, 780, 300, 230, icon_key="logo-windows11")
    p.box("pj2", "pj2 · Ubuntu", 790, 780, 140, 230, kind="lab", icon_key="logo-ubuntu")
    p.box("team", "팀원 장치", 960, 860, 650, 150)
    p.box("legend", "", 30, 1040, 1580, 130, kind="legend")

    n = p.node
    n("gsheet", "통합 시트", "logo-google-sheets", 150, 100, "외부·기업", 50, cmp="CMP-63", lp="t")
    n("github", "GitHub", "logo-github", 560, 100, "외부·기업", 50, cmp="CMP-64", lp="t")
    n("remote", "원격 MCP", "logo-mcp", 1250, 100, "MCP 서버", 50, lp="t")
    n("llmp", "LLM 제공자", "logo-anthropic", 1360, 100, "모델", 50, cmp="CMP-51", lp="t")
    n("registry", "이미지 저장소", "logo-docker", 1470, 100, "외부·기업", 50, lp="t")
    n("agents", "Claude · Codex", "flat-robot", 110, 380, "외부·기업", 52, cmp="CMP-65")
    n("collab", "협업 콘솔", "flat-chat", 110, 510, "외부·기업", 52, cmp="CMP-62")
    n("ssh", "SSH · 시험", "flat-terminal", 310, 450, "엔드포인트", 48)
    n("tailnet", "Tailscale", "logo-tailscale", 790, 470, "망·진입", 96, cmp="CMP-17", lp="t")
    n("derp", "DERP 중계", "flat-relay", 1000, 470, "망·진입", 46, lp="t")
    for i, (id, lab, ic, cat) in enumerate([
        ("caddy", "Caddy", "logo-caddy", "망·진입"), ("gw", "게이트웨이", "flat-shield", "게이트웨이"),
        ("console", "관리 콘솔", "flat-dashboard", "게이트웨이"), ("opa", "OPA", "logo-opa", "정책·검사"),
        ("presidio", "Presidio", "logo-presidio", "정책·검사"), ("pg", "PostgreSQL", "logo-postgresql", "데이터·감사"),
        ("mproxy", "모델 프록시", "flat-proxy", "망·진입"), ("jaeger", "Jaeger", "logo-jaeger", "관측·연동"),
        ("gitea", "내부 Git", "logo-gitea", "공급망·실행"), ("rt", "MCP 실행기", "flat-container", "공급망·실행")]):
        n(id, lab, ic, 1215 + (i % 5) * 82, 405 + (i // 5) * 100, cat, 42)
    n("markitdown", "MarkItDown", "logo-markitdown", 1225, 680, "MCP 서버", 44)
    n("egress", "출구 프록시", "flat-proxy", 1315, 680, "망·진입", 44)
    n("litellm", "LiteLLM", "logo-litellm", 1440, 660, "모델", 40, "연동 시험")
    n("ollama", "Ollama", "logo-ollama", 1540, 660, "모델", 40, "연동 시험")
    n("openbao", "OpenBao", "logo-openbao", 1490, 745, "외부·기업", 36, "연동 시험")
    n("pj1user", "직원 계정", "flat-employee", 100, 750, "사용자", 48)
    n("pj1managed", "관리 계정", "flat-id-card", 210, 750, "엔드포인트", 48)
    n("pj1claude", "Claude Code", "logo-claude", 320, 750, "하네스", 46)
    n("pj1codex", "Codex", "logo-openai", 395, 750, "하네스", 40)
    n("pj1aa", "AppArmor", "logo-apparmor", 100, 900, "엔드포인트", 44)
    n("pj1nft", "nftables", "logo-nftables", 210, 900, "엔드포인트", 44)
    n("pj1obs", "OS 관측기", "flat-eye", 320, 900, "엔드포인트", 44)
    n("pj3wiz", "마법사·트레이", "flat-wizard", 535, 860, "엔드포인트", 44, "시험 중")
    n("pj3fw", "방화벽 규칙", "flat-firewall", 620, 860, "엔드포인트", 44, "시험 중")
    n("pj3obs", "OS 관측기", "flat-eye", 705, 860, "엔드포인트", 44)
    n("pj3claude", "Claude Code", "logo-claude", 580, 955, "하네스", 38)
    n("pj3codex", "Codex", "logo-openai", 670, 955, "하네스", 38)
    n("pj2vm", "꺼짐", "flat-vm", 860, 890, "외부·기업", 46, "꺼짐")
    n("kuku", "팀원 PC", "logo-windows11", 1060, 935, "사용자", 46)
    n("mac", "팀원 Mac", "flat-laptop", 1190, 935, "사용자", 46, "꺼짐")
    n("miso", "팀원 Linux", "logo-linux", 1320, 935, "사용자", 46, "꺼짐")

    e = p.edge
    e("laptop", "tailnet", "net")
    e("appl", "derp", "net")
    e("derp", "tailnet", "net")
    e("pj1", "tailnet", "net", pts=[(745, 700)])
    e("pj3", "tailnet", "net", pts=[(760, 600)])
    e("pj2", "tailnet", "plan", pts=[(805, 600)])
    e("team", "tailnet", "net", pts=[(1000, 600), (835, 600)])
    e("laptop", "gsheet", "mcp", pts=[(150, 200)])
    e("laptop", "github", "mcp", "push", pts=[(540, 280)], lab_at=0)
    e("appl", "github", "ctl", "fetch", pts=[(580, 300)], lab_at=0)
    e("appl", "remote", "mcp", pts=[(1250, 200)])
    e("appl", "llmp", "llm", pts=[(1360, 200)])
    e("appl", "registry", "ctl", pts=[(1470, 200)])
    e("markitdown", "egress", "ctl")
    e("litellm", "ollama", "llm")
    return p


# ── 페이지 3: 엔드포인트 키트 ─────────────────────────────────────────────
def page3():
    p = Page("3 엔드포인트 키트", 1640, 1180)
    p.box("flow", "연결 절차", 30, 20, 1580, 170)
    p.box("linux", "Linux · PJ1", 30, 220, 610, 780, icon_key="logo-ubuntu")
    p.box("emp", "직원 계정", 50, 270, 150, 450, kind="sub")
    p.box("managed", "관리 계정", 220, 270, 250, 450, kind="sub")
    p.box("lsys", "시스템", 490, 500, 140, 120, kind="sub")
    p.box("los", "OS 통제", 50, 750, 580, 235, kind="sub")
    p.box("appl", "솔루션 기기", 680, 220, 280, 780)
    p.box("win", "Windows · pj3", 1000, 220, 610, 780, icon_key="logo-windows11")
    p.box("wsys", "시스템", 1010, 500, 140, 120, kind="sub")
    p.box("wmanaged", "관리형 하네스", 1170, 270, 250, 450, kind="sub")
    p.box("wkit", "키트", 1440, 270, 150, 450, kind="sub")
    p.box("wos", "OS 통제", 1010, 750, 580, 235, kind="sub")
    p.box("legend", "", 30, 1030, 1580, 130, kind="legend")

    n = p.node
    for i, (id, lab, ic, cat) in enumerate([
        ("s1", "관리자", "flat-admin", "사용자"), ("s2", "키트 발급", "flat-dashboard", "게이트웨이"),
        ("s3", "키트 받기", "flat-installer", "엔드포인트"), ("s4", "설치 · sudo 1회", "logo-bash", "엔드포인트"),
        ("s5", "점검", "flat-check", "엔드포인트"), ("s6", "장치 활성화", "flat-shield-check", "게이트웨이"),
        ("s7", "하네스 사용", "flat-robot", "하네스")]):
        n(id, lab, ic, 130 + i * 230, 100, cat, 56)
    n("emp_user", "직원", "flat-employee", 125, 400, "사용자", 52, lp="t")
    n("launcher", "진입 래퍼", "flat-terminal", 125, 560, "엔드포인트", 48, cmp="CMP-08")
    n("m_claude", "Claude Code", "logo-claude", 290, 430, "하네스", 50, cmp="CMP-03")
    n("m_codex", "Codex CLI", "logo-openai", 400, 430, "하네스", 50, cmp="CMP-04")
    n("m_cfg", "관리형 설정", "flat-gear", 290, 570, "엔드포인트", 46, cmp="CMP-09")
    n("m_helper", "헤더 헬퍼", "flat-key", 400, 570, "엔드포인트", 46, cmp="CMP-10")
    n("m_ca", "사설 CA", "flat-certificate", 345, 670, "망·진입", 42)
    n("obs", "OS 관측기", "flat-eye", 560, 560, "엔드포인트", 48, cmp="CMP-11")
    n("aa", "AppArmor", "logo-apparmor", 130, 830, "엔드포인트", 50, cmp="CMP-12")
    n("nft", "nftables", "logo-nftables", 260, 830, "엔드포인트", 50, cmp="CMP-13")
    n("loop", "루프백 규칙", "flat-stop", 390, 830, "엔드포인트", 50)
    n("localmcp", "비인가 로컬 MCP", "logo-mcp", 540, 930, "차단", 44, "차단")
    n("a_gw", "MCP 게이트웨이", "flat-shield", 790, 320, "게이트웨이", 60, lp="t")
    n("a_pg", "원장", "logo-postgresql", 900, 320, "데이터·감사", 44)
    n("a_caddy", "Caddy", "logo-caddy", 790, 430, "망·진입", 52)
    n("a_api", "엔드포인트 API", "flat-dashboard", 790, 560, "게이트웨이", 52)
    n("a_proxy", "모델 프록시", "flat-proxy", 790, 700, "망·진입", 52, lp="t")
    n("a_llm", "LLM 제공자", "logo-anthropic", 790, 860, "모델", 52)
    n("w_obs", "OS 관측기", "flat-eye", 1080, 560, "엔드포인트", 48, cmp="CMP-11")
    n("w_claude", "Claude Code", "logo-claude", 1240, 430, "하네스", 50)
    n("w_codex", "Codex CLI", "logo-openai", 1350, 430, "하네스", 50)
    n("w_cfg", "관리형 설정", "flat-gear", 1240, 570, "엔드포인트", 46)
    n("w_ca", "사설 CA 신뢰", "flat-certificate", 1350, 570, "망·진입", 46)
    n("w_wizard", "설치 마법사", "flat-wizard", 1515, 380, "엔드포인트", 48, "시험 중", "CMP-14")
    n("w_py", "Python", "logo-python", 1515, 500, "엔드포인트", 44, "시험 중", "CMP-15")
    n("w_tray", "트레이", "flat-tray", 1515, 620, "엔드포인트", 48, "시험 중", "CMP-14")
    n("w_fw", "방화벽 규칙", "flat-firewall", 1150, 830, "엔드포인트", 50, "시험 중", "CMP-16")
    n("w_local", "비인가 로컬 MCP", "logo-mcp", 1450, 930, "차단", 44, "차단")

    e = p.edge
    for i in range(1, 7):
        e(f"s{i}", f"s{i + 1}", "ctl")
    e("emp_user", "launcher", "mcp")
    e("launcher", "managed", "mcp")
    e("managed", "a_caddy", "mcp", "MCP · HTTPS")
    e("managed", "a_proxy", "llm", "LLM")
    e("obs", "a_api", "ctl", "이벤트")
    e("managed", "localmcp", "blk", pts=[(440, 930)])
    e("a_caddy", "a_gw", "mcp")
    e("a_gw", "a_pg", "ctl")
    e("a_proxy", "a_llm", "llm")
    e("wmanaged", "a_caddy", "mcp", "MCP · HTTPS")
    e("wmanaged", "a_proxy", "llm", "LLM")
    e("w_obs", "a_api", "ctl", "이벤트")
    e("wmanaged", "w_local", "blk", pts=[(1390, 930)])
    return p


# ── 범례·출처 ───────────────────────────────────────────────────────────
def legend_items(page):
    used_cats, used_edges = [], []
    for nd in page.nodes.values():
        if nd["cat"] not in used_cats:
            used_cats.append(nd["cat"])
    for ed in page.edges:
        if ed["kind"] not in used_edges:
            used_edges.append(ed["kind"])
    cats = [c for c in CAT if c in used_cats]
    return cats, [k for k in EDGE if k in used_edges]


def credits():
    try:
        src = json.loads((ROOT / "icons" / "sources.json").read_text(encoding="utf-8"))
    except Exception:
        src = []
    sites = sorted({s.get("site", "") for s in src if s.get("site")})
    names = {"iconify": "Iconify(svg-logos·icons8·Fluent, CC0·MIT)", "flaticon": "Flaticon(Freepik 외)",
             "github": "각 프로젝트 GitHub", "wikimedia": "Wikimedia Commons", "official": "공식 사이트",
             "namuwiki": "나무위키"}
    return "아이콘: " + " · ".join(names.get(s, s) for s in sites) if sites else ""


# ── draw.io ─────────────────────────────────────────────────────────────
def esc(s):
    return html.escape(str(s), quote=True)


def node_ring(nd):
    planned = nd["status"] in ("도입 예정", "재검토", "연동 대상", "꺼짐")
    trial = nd["status"] in ("시험용", "시험 중", "연동 시험")
    color = CAT[nd["cat"]]
    dash = "dashed=1;dashPattern=6 4;" if planned else ("dashed=1;dashPattern=2 2;" if trial else "")
    if nd["status"] == "차단":
        dash = "dashed=1;dashPattern=5 4;"
    return color, dash, planned


def drawio_page(page, pid):
    cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']
    fs = f"fontFamily={FONT};fontSource=https%3A%2F%2Ffonts.googleapis.com%2Fcss%3Ffamily%3DNoto%2BSans%2BKR;"

    def cid(x):
        return f"{pid}-{x}"

    for b in page.boxes:
        if b["kind"] == "legend":
            continue
        if b["kind"] == "col":
            st = (f"rounded=0;fillColor=none;strokeColor={COLUMN_BLUE};strokeWidth=2;verticalAlign=top;align=center;"
                  f"spacingTop=10;fontSize=15;fontStyle=1;fontColor={COLUMN_BLUE};{fs}")
        else:
            fill = {"grp": "#F4F8FD", "sub": "#FFFFFF", "lab": "#FBFBFC"}[b["kind"]]
            stroke = {"grp": "#9DB8DE", "sub": "#C5D3E6", "lab": "#A7B0BC"}[b["kind"]]
            dash = "dashed=1;dashPattern=6 4;" if b["kind"] == "lab" else ""
            st = (f"rounded=1;arcSize=4;absoluteArcSize=1;fillColor={fill};strokeColor={stroke};{dash}"
                  f"verticalAlign=top;align={'right' if b['la'] == 'r' else 'left'};spacingLeft={30 if b['icon'] else 10};"
                  f"spacingRight=10;spacingTop=4;fontSize=12;fontStyle=1;"
                  f"fontColor={TEXT};{fs}")
        cells.append(f'<mxCell id="{cid(b["id"])}" value="{esc(b["label"])}" style="{st}" vertex="1" parent="1">'
                     f'<mxGeometry x="{b["x"]}" y="{b["y"]}" width="{b["w"]}" height="{b["h"]}" as="geometry"/></mxCell>')
        if b["icon"] and icon(b["icon"]):
            mime, data = icon(b["icon"])
            cells.append(f'<mxCell id="{cid(b["id"])}-ic" value="" style="shape=image;image=data:{mime},{data};'
                         f'imageAspect=1;aspect=fixed;" vertex="1" parent="1">'
                         f'<mxGeometry x="{b["x"] + 8}" y="{b["y"] + 4}" width="18" height="18" as="geometry"/></mxCell>')
    for nd in page.nodes.values():
        color, dash, planned = node_ring(nd)
        s = nd["size"]
        x, y = nd["x"] - s / 2, nd["y"] - s / 2
        lpos = {"b": "verticalLabelPosition=bottom;verticalAlign=top;labelPosition=center;align=center;spacingTop=-1;",
                "t": "verticalLabelPosition=top;verticalAlign=bottom;labelPosition=center;align=center;spacingBottom=-1;",
                "l": "labelPosition=left;align=right;verticalLabelPosition=middle;verticalAlign=middle;spacingRight=4;",
                "r": "labelPosition=right;align=left;verticalLabelPosition=middle;verticalAlign=middle;spacingLeft=4;"}[nd["lp"]]
        st = (f"ellipse;aspect=fixed;html=1;fillColor=#FFFFFF;strokeColor={color};strokeWidth=3;{dash}"
              f"{lpos}"
              f"fontSize=11;fontStyle=1;fontColor={TEXT};container=1;collapsible=0;recursiveResize=0;"
              f"{'opacity=80;' if planned else ''}{fs}")
        tip = " · ".join(v for v in (nd["status"], nd["cmp"], nd["tip"]) if v)
        attrs = f'label="{esc(nd["label"])}" 분류="{esc(nd["cat"])}"'
        if nd["status"]: attrs += f' 상태="{esc(nd["status"])}"'
        if nd["cmp"]: attrs += f' 구성요소="{esc(nd["cmp"])}"'
        if nd["tip"]: attrs += f' 작업="{esc(nd["tip"])}"'
        if tip: attrs += f' tooltip="{esc(tip)}"'
        cells.append(f'<object id="{cid(nd["id"])}" {attrs}><mxCell style="{st}" vertex="1" parent="1">'
                     f'<mxGeometry x="{x:.1f}" y="{y:.1f}" width="{s}" height="{s}" as="geometry"/></mxCell></object>')
        ic = icon(nd["icon"])
        if ic:
            mime, data = ic
            k = s * 0.62
            cells.append(f'<mxCell id="{cid(nd["id"])}-ic" value="" style="shape=image;image=data:{mime},{data};'
                         f'imageAspect=1;aspect=fixed;{"opacity=70;" if planned else ""}" vertex="1" '
                         f'parent="{cid(nd["id"])}"><mxGeometry x="{(s - k) / 2:.1f}" y="{(s - k) / 2:.1f}" '
                         f'width="{k:.1f}" height="{k:.1f}" as="geometry"/></mxCell>')
    def bbox(id):
        if id in page.nodes:
            nd = page.nodes[id]
            return nd["x"] - nd["size"] / 2, nd["y"] - nd["size"] / 2, nd["size"], nd["size"]
        b = next(b for b in page.boxes if b["id"] == id)
        return b["x"], b["y"], b["w"], b["h"]

    def rel(id, px, py):
        x, y, w, h = bbox(id)
        return f"{(px - x) / w:.4f}", f"{(py - y) / h:.4f}"

    for i, ed in enumerate(page.edges):
        color, dash, w = EDGE[ed["kind"]]
        path = route(page, ed)
        ex, ey = rel(ed["a"], *path[0])
        nx, ny = rel(ed["b"], *path[-1])
        end = "endArrow=cross;endSize=8;" if ed["kind"] == "blk" else "endArrow=blockThin;endFill=1;endSize=5;"
        st = (f"edgeStyle=none;rounded=1;arcSize=10;html=1;strokeColor={color};strokeWidth={w};"
              f"{'dashed=1;dashPattern=' + dash + ';' if dash else ''}{end}startArrow=none;"
              f"exitX={ex};exitY={ey};exitPerimeter=0;entryX={nx};entryY={ny};entryPerimeter=0;"
              f"fontSize=10;fontColor={color};fontStyle=1;labelBackgroundColor=#FFFFFF;{fs}")
        pts = "".join(f'<mxPoint x="{x}" y="{y}"/>' for x, y in ed["pts"])
        lx = 0
        if ed["label"]:
            segs = list(zip(path, path[1:]))
            lens = [math.dist(a, b) for a, b in segs]
            k = ed["lab_at"] if ed["lab_at"] is not None else max(range(len(segs)), key=lambda q: lens[q])
            k = min(k, len(segs) - 1)
            frac = (sum(lens[:k]) + lens[k] / 2) / (sum(lens) or 1)
            lx = 2 * frac - 1
        geo = (f'<mxGeometry x="{lx:.3f}" relative="1" as="geometry">' + (f'<Array as="points">{pts}</Array>' if pts else "")
               + "</mxGeometry>")
        cells.append(f'<mxCell id="{cid("e" + str(i))}" value="{esc(ed["label"])}" style="{st}" edge="1" parent="1" '
                     f'source="{cid(ed["a"])}" target="{cid(ed["b"])}">{geo}</mxCell>')
    # 범례
    lb = next((b for b in page.boxes if b["kind"] == "legend"), None)
    if lb:
        cells += legend_drawio(page, lb, cid, fs)
    for j, t in enumerate(page.texts):
        cells.append(f'<mxCell id="{cid("t" + str(j))}" value="{esc(t["s"])}" style="text;html=1;fontSize={t["size"]};'
                     f'fontColor={t["color"]};{"fontStyle=1;" if t["bold"] else ""}align=left;verticalAlign=middle;{fs}" '
                     f'vertex="1" parent="1"><mxGeometry x="{t["x"]}" y="{t["y"] - 10}" width="400" height="20" '
                     f'as="geometry"/></mxCell>')
    model = (f'<mxGraphModel dx="1200" dy="800" grid="0" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" '
             f'fold="1" page="1" pageScale="1" pageWidth="{page.w}" pageHeight="{page.h}" background="#FFFFFF" math="0" '
             f'shadow="0"><root>{"".join(cells)}</root></mxGraphModel>')
    return f'<diagram id="p{pid}" name="{esc(page.name)}">{model}</diagram>'


def legend_layout(page, lb):
    cats, kinds = legend_items(page)
    x0, y0 = lb["x"] + 16, lb["y"] + 16
    rows = []
    rows.append(("title", "MINT 아키텍처", x0, y0 + 6))
    rows.append(("sub", page.name.split(" ", 1)[1] + " · 2026-10-18", x0 + 150, y0 + 6))
    nc = max(4, int((lb["w"] - 32) // 110))
    cw = (lb["w"] - 32) / nc
    for i, c in enumerate(cats):
        rows.append(("cat", c, x0 + (i % nc) * cw, y0 + 34 + (i // nc) * 20))
    yl = y0 + 34 + ((len(cats) + nc - 1) // nc) * 20 + 6
    ne = max(3, int((lb["w"] - 32) // 180))
    ew = (lb["w"] - 32) / ne
    for i, k in enumerate(kinds):
        rows.append(("edge", k, x0 + (i % ne) * ew, yl + (i // ne) * 20))
    yr = yl + ((len(kinds) + ne - 1) // ne) * 20 + 4
    rows.append(("ring", "", x0, yr))
    return rows


def legend_drawio(page, lb, cid, fs):
    out = [f'<mxCell id="{cid("legend")}" value="" style="rounded=1;arcSize=4;absoluteArcSize=1;fillColor=#FFFFFF;'
           f'strokeColor={COLUMN_BLUE};strokeWidth=1.5;" vertex="1" parent="1"><mxGeometry x="{lb["x"]}" y="{lb["y"]}" '
           f'width="{lb["w"]}" height="{lb["h"]}" as="geometry"/></mxCell>']
    for j, (kind, s, x, y) in enumerate(legend_layout(page, lb)):
        k = cid(f"lg{j}")
        if kind == "title":
            out.append(f'<mxCell id="{k}" value="{esc(s)}" style="text;fontSize=15;fontStyle=1;fontColor={COLUMN_BLUE};'
                       f'{fs}" vertex="1" parent="1"><mxGeometry x="{x}" y="{y - 10}" width="150" height="20" as="geometry"/></mxCell>')
        elif kind == "sub":
            out.append(f'<mxCell id="{k}" value="{esc(s)}" style="text;fontSize=11;fontColor=#66727F;{fs}" vertex="1" '
                       f'parent="1"><mxGeometry x="{x}" y="{y - 10}" width="250" height="20" as="geometry"/></mxCell>')
        elif kind == "cat":
            out.append(f'<mxCell id="{k}" value="{esc(s)}" style="text;fontSize=11;fontColor={TEXT};spacingLeft=18;{fs}" '
                       f'vertex="1" parent="1"><mxGeometry x="{x}" y="{y - 9}" width="130" height="18" as="geometry"/></mxCell>')
            out.append(f'<mxCell id="{k}d" value="" style="ellipse;fillColor={CAT[s]};strokeColor=none;" vertex="1" '
                       f'parent="1"><mxGeometry x="{x + 2}" y="{y - 5}" width="10" height="10" as="geometry"/></mxCell>')
        elif kind == "edge":
            color, dash, w = EDGE[s]
            out.append(f'<mxCell id="{k}" value="{esc(EDGE_NAME[s])}" style="text;fontSize=11;fontColor={TEXT};'
                       f'spacingLeft=30;{fs}" vertex="1" parent="1"><mxGeometry x="{x}" y="{y - 9}" width="140" height="18" '
                       f'as="geometry"/></mxCell>')
            out.append(f'<mxCell id="{k}l" value="" style="endArrow=none;html=1;strokeColor={color};strokeWidth={w};'
                       f'{"dashed=1;dashPattern=" + dash + ";" if dash else ""}" edge="1" parent="1"><mxGeometry '
                       f'relative="1" as="geometry"><mxPoint x="{x}" y="{y}" as="sourcePoint"/><mxPoint x="{x + 24}" '
                       f'y="{y}" as="targetPoint"/></mxGeometry></mxCell>')
        elif kind == "ring":
            for i, (lab, dsh) in enumerate((("사용 중", ""), ("시험·연동", "dashed=1;dashPattern=2 2;"),
                                            ("개발 예정·재검토", "dashed=1;dashPattern=6 4;"))):
                xx = x + i * 125
                out.append(f'<mxCell id="{k}r{i}" value="" style="ellipse;fillColor=#FFFFFF;strokeColor=#66727F;'
                           f'strokeWidth=2;{dsh}" vertex="1" parent="1"><mxGeometry x="{xx}" y="{y - 7}" width="14" '
                           f'height="14" as="geometry"/></mxCell>')
                out.append(f'<mxCell id="{k}t{i}" value="{lab}" style="text;fontSize=11;fontColor={TEXT};{fs}" '
                           f'vertex="1" parent="1"><mxGeometry x="{xx + 18}" y="{y - 9}" width="110" height="18" '
                           f'as="geometry"/></mxCell>')
    cr = credits()
    if cr:
        out.append(f'<mxCell id="{cid("credit")}" value="{esc(cr)}" style="text;fontSize=6;fontColor=#C5CBD3;align=right;'
                   f'{fs}" vertex="1" parent="1"><mxGeometry x="{lb["x"] + lb["w"] - 410}" y="{lb["y"] + lb["h"] - 13}" '
                   f'width="402" height="11" as="geometry"/></mxCell>')
    return out


# ── SVG ─────────────────────────────────────────────────────────────────
def svg_page(page):
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{page.w}" height="{page.h}" viewBox="0 0 {page.w} {page.h}" '
         f'font-family="{FONT}, Malgun Gothic, sans-serif">', f'<rect width="100%" height="100%" fill="#FFFFFF"/>',
         "<defs>"]
    for k, (color, _, _) in EDGE.items():
        o.append(f'<marker id="m-{k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
                 f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{color}"/></marker>')
    o.append("</defs>")
    for b in page.boxes:
        if b["kind"] == "legend":
            continue
        if b["kind"] == "col":
            o.append(f'<rect x="{b["x"]}" y="{b["y"]}" width="{b["w"]}" height="{b["h"]}" fill="none" '
                     f'stroke="{COLUMN_BLUE}" stroke-width="2"/>')
            o.append(f'<text x="{b["x"] + b["w"] / 2}" y="{b["y"] + 27}" text-anchor="middle" font-size="15" '
                     f'font-weight="700" fill="{COLUMN_BLUE}">{esc(b["label"])}</text>')
            continue
        fill = {"grp": "#F4F8FD", "sub": "#FFFFFF", "lab": "#FBFBFC"}[b["kind"]]
        stroke = {"grp": "#9DB8DE", "sub": "#C5D3E6", "lab": "#A7B0BC"}[b["kind"]]
        dash = ' stroke-dasharray="6 4"' if b["kind"] == "lab" else ""
        o.append(f'<rect x="{b["x"]}" y="{b["y"]}" width="{b["w"]}" height="{b["h"]}" rx="4" fill="{fill}" '
                 f'stroke="{stroke}"{dash}/>')
        tx = b["x"] + b["w"] - 10 if b["la"] == "r" else b["x"] + (30 if b["icon"] else 10)
        if b["icon"] and icon(b["icon"]):
            mime, data = icon(b["icon"])
            o.append(f'<image x="{b["x"] + 8}" y="{b["y"] + 4}" width="18" height="18" href="data:{mime};base64,{data}"/>')
        o.append(f'<text x="{tx}" y="{b["y"] + 18}" font-size="12" font-weight="700" fill="{TEXT}"'
                 f'{" text-anchor=\"end\"" if b["la"] == "r" else ""}>{esc(b["label"])}</text>')
    for ed in page.edges:
        color, dash, w = EDGE[ed["kind"]]
        pts = route(page, ed)
        d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        da = f' stroke-dasharray="{dash}"' if dash else ""
        mk = "" if ed["kind"] == "blk" else f' marker-end="url(#m-{ed["kind"]})"'
        o.append(f'<polyline points="{d}" fill="none" stroke="{color}" stroke-width="{w}"{da}{mk} '
                 f'stroke-linejoin="round"/>')
        if ed["kind"] == "blk":
            ex, ey = pts[-1]
            o.append(f'<path d="M{ex - 6},{ey - 6} L{ex + 6},{ey + 6} M{ex + 6},{ey - 6} L{ex - 6},{ey + 6}" '
                     f'stroke="{color}" stroke-width="2.4"/>')
        if ed["label"]:
            segs = list(zip(pts, pts[1:]))
            i = ed["lab_at"] if ed["lab_at"] is not None else max(range(len(segs)), key=lambda k: math.dist(*segs[k]))
            (x1, y1), (x2, y2) = segs[min(i, len(segs) - 1)]
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            tw = 7 * len(ed["label"]) + 8
            o.append(f'<rect x="{mx - tw / 2}" y="{my - 8}" width="{tw}" height="16" rx="3" fill="#FFFFFF"/>')
            o.append(f'<text x="{mx}" y="{my + 4}" text-anchor="middle" font-size="10" font-weight="700" '
                     f'fill="{color}">{esc(ed["label"])}</text>')
    for nd in page.nodes.values():
        color, dash, planned = node_ring(nd)
        r = nd["size"] / 2
        da = ""
        if "dashPattern=6 4" in dash or "dashPattern=5 4" in dash:
            da = ' stroke-dasharray="6 4"'
        elif dash:
            da = ' stroke-dasharray="2 2"'
        op = ' opacity="0.8"' if planned else ""
        o.append(f'<g{op}><circle cx="{nd["x"]}" cy="{nd["y"]}" r="{r}" fill="#FFFFFF" stroke="{color}" '
                 f'stroke-width="3"{da}/>')
        ic = icon(nd["icon"])
        k = nd["size"] * 0.62
        if ic:
            mime, data = ic
            o.append(f'<image x="{nd["x"] - k / 2:.1f}" y="{nd["y"] - k / 2:.1f}" width="{k:.1f}" height="{k:.1f}" '
                     f'href="data:{mime};base64,{data}" preserveAspectRatio="xMidYMid meet"/>')
        else:
            o.append(f'<circle cx="{nd["x"]}" cy="{nd["y"]}" r="{k / 2:.1f}" fill="{color}" opacity="0.25"/>')
        tx, ty, ta = {"b": (nd["x"], nd["y"] + r + 15, "middle"), "t": (nd["x"], nd["y"] - r - 7, "middle"),
                      "l": (nd["x"] - r - 6, nd["y"] + 4, "end"), "r": (nd["x"] + r + 6, nd["y"] + 4, "start")}[nd["lp"]]
        o.append(f'<text x="{tx}" y="{ty}" text-anchor="{ta}" font-size="11" font-weight="700" '
                 f'fill="{TEXT}">{esc(nd["label"])}</text></g>')
    lb = next((b for b in page.boxes if b["kind"] == "legend"), None)
    if lb:
        o.append(f'<rect x="{lb["x"]}" y="{lb["y"]}" width="{lb["w"]}" height="{lb["h"]}" rx="4" fill="#FFFFFF" '
                 f'stroke="{COLUMN_BLUE}" stroke-width="1.5"/>')
        for kind, s, x, y in legend_layout(page, lb):
            if kind == "title":
                o.append(f'<text x="{x}" y="{y + 5}" font-size="15" font-weight="700" fill="{COLUMN_BLUE}">{esc(s)}</text>')
            elif kind == "sub":
                o.append(f'<text x="{x}" y="{y + 4}" font-size="11" fill="#66727F">{esc(s)}</text>')
            elif kind == "cat":
                o.append(f'<circle cx="{x + 7}" cy="{y}" r="5" fill="{CAT[s]}"/><text x="{x + 18}" y="{y + 4}" '
                         f'font-size="11" fill="{TEXT}">{esc(s)}</text>')
            elif kind == "edge":
                color, dash, w = EDGE[s]
                da = f' stroke-dasharray="{dash}"' if dash else ""
                o.append(f'<line x1="{x}" y1="{y}" x2="{x + 24}" y2="{y}" stroke="{color}" stroke-width="{w}"{da}/>'
                         f'<text x="{x + 30}" y="{y + 4}" font-size="11" fill="{TEXT}">{esc(EDGE_NAME[s])}</text>')
            elif kind == "ring":
                for i, (lab, da) in enumerate((("사용 중", ""), ("시험·연동", ' stroke-dasharray="2 2"'),
                                               ("개발 예정·재검토", ' stroke-dasharray="6 4"'))):
                    xx = x + i * 125
                    o.append(f'<circle cx="{xx + 7}" cy="{y}" r="7" fill="#FFFFFF" stroke="#66727F" stroke-width="2"{da}/>'
                             f'<text x="{xx + 18}" y="{y + 4}" font-size="11" fill="{TEXT}">{lab}</text>')
        cr = credits()
        if cr:
            o.append(f'<text x="{lb["x"] + lb["w"] - 8}" y="{lb["y"] + lb["h"] - 4}" text-anchor="end" font-size="6" '
                     f'fill="#C5CBD3">{esc(cr)}</text>')
    for t in page.texts:
        o.append(f'<text x="{t["x"]}" y="{t["y"]}" font-size="{t["size"]}" fill="{t["color"]}" '
                 f'{"font-weight=\"700\" " if t["bold"] else ""}text-anchor="{t["anchor"]}">{esc(t["s"])}</text>')
    o.append("</svg>")
    return "\n".join(o)


def main():
    pages = [page1(), page2(), page3()]
    missing = sorted({nd["icon"] for p in pages for nd in p.nodes.values() if not icon(nd["icon"])})
    xml = ('<mxfile host="Electron" agent="MINT build_architecture.py" version="24.7.17">'
           + "".join(drawio_page(p, i + 1) for i, p in enumerate(pages)) + "</mxfile>")
    (ROOT / "MINT_아키텍처.drawio").write_text(xml, encoding="utf-8")
    prev = ROOT / "preview"
    prev.mkdir(exist_ok=True)
    for i, p in enumerate(pages, 1):
        (prev / f"page-{i}.svg").write_text(svg_page(p), encoding="utf-8")
    print(f"pages={len(pages)} nodes={sum(len(p.nodes) for p in pages)} edges={sum(len(p.edges) for p in pages)} "
          f"drawio={len(xml) // 1024}KB missing_icons={missing}")


if __name__ == "__main__":
    main()
