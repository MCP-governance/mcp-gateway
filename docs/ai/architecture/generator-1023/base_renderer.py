"""MINT 구성도 — 한 장면 정의에서 draw.io(편집용)와 SVG(미리보기·PNG)를 만든다.

python -X utf8 build_architecture.py [MMDDHHmm]
  → export/MINT_구성도_<stamp>.svg·png, MINT_구성도_역할설명_<stamp>.svg·png, MINT_구조도_<stamp>.drawio
아이콘: icons/raw/<key>.svg|png (출처 icons/sources.json). 원 안에 가두지 않고 아이콘 자체를 크게 쓴다.
PNG는 크롬 헤드리스(별도 --user-data-dir)로 찍는다.
"""
import base64, html, json, math, re, subprocess, sys, tempfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ICONS = ROOT / "icons" / "raw"
OUT = ROOT / "export"
FONT = "Noto Sans KR"
TEXT = "#1F3A5F"
MUTED = "#66727F"
RED = "#E5322D"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

W, H = 2000, 1297          # 구성도
PANEL_H = 764              # 역할 설명 쪽 아래 설명 패널


def esc(s):
    return html.escape(str(s), quote=True)


def tw(s, size):
    return sum(size if ord(c) > 0x2E80 else size * 0.58 for c in s)


def wrap(s, width, size):
    """영문·숫자 덩어리는 쪼개지 않고, 마침표·괄호 닫기는 앞 줄에 붙인다."""
    out, line = [], ""
    for tok in re.findall(r"[A-Za-z0-9_+\-/→]+|.", s):
        glue = tok in ".,)·"
        if not glue and tw(line + tok, size) > width and line.strip():
            out.append(line.strip())
            line = tok.lstrip()
        else:
            line += tok
    if line.strip():
        out.append(line.strip())
    return out


# ── 아이콘 ──────────────────────────────────────────────────────────────
def _clean_svg(raw):
    raw = re.sub(r"<\?xml[^>]*>|<!DOCTYPE[^>]*>", "", raw, flags=re.S)
    raw = re.sub(r"<(script|foreignObject)\b.*?</\1>", "", raw, flags=re.S | re.I)
    raw = re.sub(r"\son[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*')", "", raw, flags=re.I)
    raw = re.sub(r"(xlink:)?href\s*=\s*([\"'])(?!#|data:)[^\"']*\2", "", raw, flags=re.I)
    return raw.strip()


_ic = {}


def icon(key):
    if key in _ic:
        return _ic[key]
    out = None
    for ext, mime in (("svg", "image/svg+xml"), ("png", "image/png")):
        p = ICONS / f"{key}.{ext}"
        if p.exists():
            data = p.read_bytes()
            if ext == "svg":
                data = _clean_svg(data.decode("utf-8", "replace")).encode()
            out = (mime, base64.b64encode(data).decode())
            break
    _ic[key] = out
    return out


def credits():
    try:
        src = json.loads((ROOT / "icons" / "sources.json").read_text(encoding="utf-8"))
    except Exception:
        return ""
    names = {"iconify": "Iconify(svg-logos·icons8·Fluent, CC0·MIT)", "flaticon": "Flaticon(Freepik 외)",
             "github": "각 프로젝트 GitHub", "wikimedia": "Wikimedia Commons", "official": "공식 사이트",
             "namuwiki": "나무위키"}
    sites = sorted({s.get("site", "") for s in src if s.get("site")})
    return "아이콘: " + " · ".join(names.get(s, s) for s in sites) if sites else ""


# ── 장면 ────────────────────────────────────────────────────────────────
STATUS = {"시험용": ("시험", "#7B3FA0"), "시험 중": ("시험", "#7B3FA0"), "연동 시험": ("연동 시험", "#7B3FA0"),
          "도입 예정": ("예정", "#8A94A3"), "꺼짐": ("기본 꺼짐", "#8A94A3"), "Windows 시험": ("Windows 시험", "#7B3FA0")}


class Scene:
    def __init__(self, name):
        self.name = name
        self.zones, self.nodes, self.edges, self.dots = [], {}, [], []

    def zone(self, id, x, y, w, h, label, color, sub=False, dashed=False, icon_key=None, lab_at="c", note=""):
        self.zones.append(dict(id=id, x=x, y=y, w=w, h=h, label=label, color=color, sub=sub, dashed=dashed,
                               icon=icon_key, lab_at=lab_at, note=note))

    def node(self, id, label, icon_key, x, y, size=60, status="", cmp="", icon2=None):
        self.nodes[id] = dict(id=id, label=label, icon=icon_key, x=x, y=y, size=size, status=status, cmp=cmp, icon2=icon2)

    def edge(self, id, pts, color, width=3.0, label="", lab=None, dash=None, src=None, dst=None, both=False, tip="", arrow=True):
        self.edges.append(dict(id=id, pts=pts, color=color, width=width, dash=dash, label=label, lab=lab,
                               src=src, dst=dst, both=both, tip=tip, arrow=arrow))

    def bbox(self, id):
        if id in self.nodes:
            n = self.nodes[id]
            return n["x"] - n["size"] / 2, n["y"] - n["size"] / 2, n["size"], n["size"]
        z = next(z for z in self.zones if z["id"] == id)
        return z["x"], z["y"], z["w"], z["h"]


MCP, LLM, CTL, INT, OBS = "#E8A600", "#B0367C", "#3B7DD8", "#8A94A3", "#7B3FA0"
C_EMP, C_ADM, C_NET, C_SOL, C_EXT, C_ENT = "#EF7D22", "#C9962B", "#1E9E9A", "#2F6FD6", "#0F9D84", "#66727F"
C_POL, C_SUP, C_OBS, C_DAT, C_GW, C_MOD = "#D93A3A", "#5E9E2F", "#7B3FA0", "#2E4A6B", "#2F6FD6", "#B0367C"


def build_original():
    s = Scene("구성도")
    z, n, e = s.zone, s.node, s.edge
    TEAL = "#1E9E9A"

    # ── 영역(반투명 상자) ─────────────────────────────────────────────
    z("emp", 20, 100, 300, 784, "직원 PC", C_EMP, icon_key="flat-laptop", note="엔드포인트")
    z("kit", 40, 150, 260, 592, "엔드포인트 키트 · 관리 계정", C_EMP, sub=True, lab_at="tl")
    z("hn", 50, 180, 240, 246, "하네스", C_EMP, sub=True, lab_at="tl")
    z("loc", 50, 610, 240, 120, "로컬 MCP 격리 실행 (예정)", C_EMP, sub=True, dashed=True, lab_at="tl")
    z("usr", 40, 762, 260, 110, "사용자 계정", C_EMP, sub=True, lab_at="tl")
    z("adm", 20, 904, 300, 171, "관리자 PC", C_ADM, icon_key="flat-desktop")
    z("net", 340, 100, 80, 975, "사설망", C_NET)
    z("sol", 440, 100, 1035, 975, "솔루션 기기", C_SOL, icon_key="flat-server", lab_at="l")
    z("con", 555, 150, 180, 140, "관리 콘솔·인증", C_DAT, sub=True, lab_at="tl")
    z("sup", 759, 150, 374, 140, "공급망 검증", C_SUP, sub=True, lab_at="tl")
    z("run", 1157, 150, 306, 140, "격리 실행", C_SUP, sub=True, lab_at="tl")
    z("gw", 555, 395, 310, 250, "MCP 게이트웨이", C_GW, sub=True, lab_at="tl")
    z("pol", 555, 685, 405, 160, "정책 판정·검사", C_POL, sub=True, lab_at="tl")
    z("trc", 905, 545, 140, 125, "추적", C_OBS, sub=True, lab_at="tl")
    z("sg", 555, 885, 190, 165, "SIEM 전달", C_OBS, sub=True, lab_at="tl")
    z("llm", 1495, 110, 240, 170, "기업 LLM 게이트웨이", C_ENT, dashed=True, icon_key="flat-cloud")
    z("idp", 1495, 300, 240, 132, "조직 IdP", C_ENT, dashed=True)
    z("vault", 1495, 510, 240, 150, "비밀 저장소", C_ENT, dashed=True)
    z("siem", 1495, 890, 240, 172, "SIEM", C_ENT, dashed=True)
    z("prov", 1765, 110, 210, 170, "LLM 제공자", C_MOD)
    z("mcps", 1765, 380, 210, 252, "원격 MCP 서버", C_EXT)

    # ── 직원 PC ─────────────────────────────────────────────────────
    n("claude", "Claude Code", "logo-claude", 105, 252, 56, cmp="CMP-03")
    n("codex", "Codex CLI", "logo-codex", 235, 252, 56, cmp="CMP-04")
    n("gemini", "Gemini CLI", "logo-gemini", 105, 352, 56, "시험용", "CMP-05")
    n("opencode", "OpenCode", "logo-opencode", 235, 352, 56, "시험용", "CMP-06")
    n("apparmor", "AppArmor", "logo-apparmor", 82, 520, 44, cmp="CMP-12")
    n("nft", "nftables", "logo-nftables", 166, 520, 44, cmp="CMP-13")
    n("epprog", "엔드포인트\n프로그램", "logo-ubuntu", 246, 520, 44, "Windows 시험",
      "CMP-07 · CMP-08 · CMP-10 · CMP-11 · CMP-14 · CMP-74", icon2="logo-windows11")
    n("isoenv", "격리 환경", "flat-container", 105, 668, 40, "도입 예정")
    n("locmcp", "로컬 MCP", "logo-mcp", 235, 668, 40, "도입 예정")
    n("user", "직원", "flat-employee", 110, 818, 40)
    n("browser_e", "웹 콘솔", "flat-web", 230, 818, 40)
    # ── 관리자 PC ───────────────────────────────────────────────────
    n("admin", "보안 관리자", "flat-admin", 100, 998, 48, cmp="CMP-02")
    n("browser", "웹 콘솔", "flat-web", 230, 998, 48)
    # ── 사설망 ──────────────────────────────────────────────────────
    n("tail", "Tailscale", "logo-tailscale", 380, 262, 52, cmp="CMP-17")
    # ── 솔루션 기기 ─────────────────────────────────────────────────
    n("proxy", "모델 프록시\n(tinyproxy)", "flat-proxy", 490, 205, 52, cmp="CMP-19")
    n("caddy", "Caddy", "logo-caddy", 495, 470, 56, cmp="CMP-18")
    n("console", "관리 콘솔", "flat-dashboard", 603, 222, 48, cmp="CMP-21 · CMP-71")
    n("authlib", "Authlib", "logo-authlib", 683, 222, 48, cmp="CMP-24")
    for i, (k, lab, ic, c) in enumerate([("intake", "도입 신청", "flat-upload", "CMP-35"), ("syft", "Syft", "logo-syft", "CMP-36"),
                                         ("trivy", "Trivy", "logo-trivy", "CMP-37"), ("semgrep", "Semgrep", "logo-semgrep", "CMP-38"),
                                         ("gitea", "Gitea\n(자체 SQLite)", "logo-gitea", "CMP-39")]):
        n(k, lab, ic, 801 + i * 72, 222, 48, cmp=c)
    n("runner", "MCP 실행기", "flat-container", 1200, 222, 48, cmp="CMP-40")
    n("docker", "Docker", "logo-docker", 1272, 222, 48, cmp="CMP-41")
    n("markitdown", "MarkItDown\nMCP", "logo-markitdown", 1344, 222, 48, cmp="CMP-44")
    n("egress", "출구\n프록시", "flat-proxy", 1416, 222, 48, cmp="CMP-42")
    n("core", "MCP 게이트웨이", "flat-shield", 665, 470, 88, cmp="CMP-20")
    n("fastapi", "FastAPI", "logo-fastapi", 610, 590, 44, cmp="CMP-23")
    n("mcpsdk", "MCP SDK", "logo-mcp", 705, 590, 44, cmp="CMP-22")
    n("otel", "OpenTelemetry", "logo-opentelemetry", 800, 590, 44, cmp="CMP-32")
    n("rules", "룰셋 파일\n(Rego·PAC-15)", "flat-policy", 612, 750, 52, cmp="CMP-26")
    n("opa", "OPA", "logo-opa", 712, 750, 64, cmp="CMP-26")
    n("presidio", "Presidio", "logo-presidio", 808, 750, 56, cmp="CMP-28")
    n("gitleaks", "Gitleaks", "logo-gitleaks", 893, 750, 56, cmp="CMP-29")
    n("jaeger", "Jaeger\n(메모리 보관)", "logo-jaeger", 975, 600, 44, cmp="CMP-31")
    n("siemw", "SIEM 전달\n(OCSF)", "flat-queue", 650, 960, 56, "꺼짐", "CMP-33")
    # ── 기업 시스템(연동 대상) ───────────────────────────────────────
    n("litellm", "LiteLLM", "logo-litellm", 1615, 196, 56, "연동 시험", "CMP-49")
    n("keycloak", "Keycloak", "logo-keycloak", 1615, 368, 44, "시험용", "CMP-25")
    n("openbao", "OpenBao", "logo-openbao", 1615, 586, 48, "연동 시험", "CMP-52")
    n("vector", "Vector", "logo-vector", 1535, 985, 46, "연동 시험", "")
    n("opensearch", "OpenSearch", "logo-opensearch", 1615, 985, 46, "연동 시험", "")
    n("dashboards", "Dashboards", "logo-opensearch", 1695, 985, 46, "연동 시험", "")
    # ── 외부 ────────────────────────────────────────────────────────
    n("anthropic", "Anthropic", "logo-anthropic", 1820, 200, 52, cmp="CMP-51")
    n("openai", "OpenAI", "logo-openai", 1920, 200, 52, cmp="CMP-51")
    n("github", "GitHub MCP", "logo-github", 1820, 462, 52, cmp="CMP-45")
    n("context7", "Context7", "logo-context7", 1920, 462, 52, cmp="CMP-46")
    n("playwright", "Playwright\nMCP", "logo-playwright", 1820, 560, 44, "시험용", "CMP-48")
    n("labmcp", "랩 MCP\n10종", "logo-mcp", 1920, 560, 44, "시험용", "CMP-47")

    # ── 선: 위에서 아래로 한 흐름씩, 서로 가로지르지 않게 ───────────────────
    # 모델 호출(맨 위 줄)
    e("llm1", [(290, 205), (464, 205)], LLM, 3, src="hn", dst="proxy")
    e("llm2", [(490, 179), (490, 72), (1870, 72), (1870, 110)], LLM, 3, "모델 호출 · 허용 목적지만 (현재: 제공자 직접)", (1040, 56), src="proxy", dst="prov")
    e("llm2b", [(1615, 72), (1615, 110)], LLM, 2.5, "연동 시 LiteLLM 경유", (1712, 91), dash="7 5", dst="llm")
    e("llm3", [(1643, 196), (1765, 196)], LLM, 2.5, "모델 API", (1704, 180), dash="7 5", src="litellm", dst="prov")
    # 조직 로그인(솔루션 위쪽 띠로 돌아 IdP로)
    e("oidc", [(683, 150), (683, 122), (1485, 122), (1485, 366), (1495, 366)], INT, 2.5, "OIDC", (1100, 138), dash="7 5", src="con", dst="idp")
    # 사설망 안의 HTTPS 묶음: 하네스·키트·브라우저 접속이 한 줄로 모여 Caddy로
    e("b_h", [(290, 340), (392, 340)], MCP, 3.5, "MCP", (343, 324), src="hn", arrow=False)
    e("b_k", [(300, 520), (392, 520)], CTL, 2.5, "장치 보고", (346, 504), src="kit", arrow=False)
    e("b_u", [(300, 818), (392, 818)], CTL, 3, "웹 콘솔", (346, 802), src="usr", arrow=False)
    e("b_a", [(320, 998), (392, 998)], CTL, 3, "웹 콘솔", (356, 982), src="adm", arrow=False)
    e("coll", [(392, 340), (392, 998)], TEAL, 4, arrow=False)
    e("trunk", [(392, 470), (463, 470)], TEAL, 4, "HTTPS :443", (428, 454), dst="caddy")
    # Caddy에서 갈라짐: 게이트웨이(MCP·장치 보고) / 관리 콘솔(콘솔·인증)
    e("mcp2", [(523, 470), (621, 470)], MCP, 4, src="caddy", dst="core")
    e("c2c", [(495, 442), (495, 275), (555, 275)], CTL, 3, "콘솔·인증", (534, 402), src="caddy", dst="con")
    e("mcp3", [(709, 470), (1765, 470)], MCP, 4, "MCP · 직원 토큰 미전달 · 서버별 자격", (1100, 454), src="core", dst="mcps")
    e("mcp_run", [(1310, 470), (1310, 290)], MCP, 3, "MCP", (1336, 380), dst="run")
    e("pol", [(710, 645), (710, 685)], CTL, 2.5, "판정", (736, 665), src="gw", dst="pol", both=True)
    e("trace", [(822, 590), (905, 590)], OBS, 2.5, "추적(OTLP)", (872, 573), src="otel", dst="trc")
    # 도입: 콘솔 → 공급망 검증 → (승인) → 격리 실행
    e("p_con", [(735, 222), (759, 222)], CTL, 2.5, "도입 신청", (747, 196), src="con", dst="sup")
    for i, k in enumerate(["intake", "syft", "trivy", "semgrep", "gitea"][:-1]):
        nxt = ["syft", "trivy", "semgrep", "gitea"][i]
        e(f"pipe{i}", [(801 + i * 72 + 27, 222), (801 + (i + 1) * 72 - 27, 222)], MCP, 2, src=k, dst=nxt)
    e("p_sr", [(1133, 222), (1157, 222)], MCP, 2.5, "승인", (1145, 196), src="sup", dst="run")
    # 원장 → SIEM 전달 → SIEM
    e("ocsf", [(745, 960), (1495, 960)], OBS, 3, "OCSF", (1230, 944), src="sg", dst="siem")
    e("rule", [(640, 750), (680, 750)], C_POL, 2.5, src="rules", dst="opa")
    e("sv", [(1560, 985), (1590, 985)], OBS, 2, src="vector", dst="opensearch")
    e("so", [(1640, 985), (1670, 985)], OBS, 2, src="opensearch", dst="dashboards")
    s.dots.append((1310, 470, MCP))
    s.dots.append((1615, 72, LLM))
    DY = 60
    sh = lambda x, y: (x, y + DY) if (x >= 440 and y >= 380) else (x, y)
    for nd in s.nodes.values():
        nd["x"], nd["y"] = sh(nd["x"], nd["y"])
    for zz in s.zones:
        if zz["id"] in ("sol", "net"):
            zz["h"] += DY
        elif zz["x"] >= 440 and zz["y"] >= 380:
            zz["y"] += DY
    for ed in s.edges:
        ed["pts"] = [sh(*q) for q in ed["pts"]]
        if ed["lab"]:
            ed["lab"] = sh(*ed["lab"])
    s.dots = [(*sh(d[0], d[1]), d[2]) for d in s.dots]
    # 왼쪽 묶음 줄은 그대로 두고 Caddy 앞에서만 꺾는다
    for ed in s.edges:
        if ed["id"] == "trunk":
            ed["pts"] = [(392, 470), (430, 470), (430, 530), (463, 530)]
            ed["lab"] = (415, 454)
    # 원장(PostgreSQL): 콘솔과 게이트웨이 사이, 둘 다 짧은 선
    s.zone("led", 555, 320, 190, 115, "원장", C_DAT, sub=True, lab_at="tl")
    s.node("pg", "PostgreSQL", "logo-postgresql", 650, 372, 48, cmp="CMP-30")
    s.edge("db1", [(645, 290), (645, 320)], CTL, 2.5, "가입·도입 신청 저장", (770, 305), src="con", dst="led")
    s.edge("db2", [(645, 435), (645, 455)], CTL, 2.5, "판정 기록", (710, 445), src="led", dst="gw", both=True)
    return s


def build():
    s = build_original()
    zones = {z['id']: z for z in s.zones}
    zones['sol']['label'] = 'MINT 솔루션 전체'
    zones['gw'].update(x=555, y=475, w=310, h=285, label='호출 중계·실행 제어')
    zones['pol'].update(x=900, y=590, w=540, h=235, label='정책 엔진·입력·응답 검사')
    zones['led'].update(x=555, y=320, w=210, h=115, label='관리 DB·감사 원장')
    zones['trc'].update(x=905, y=900, w=200, h=175)
    zones['sg'].update(x=1180, y=900, w=245, h=175)
    s.zone('gitstore', 840, 320, 350, 115, 'Gitea 전용 볼륨 (corp_git_data)', C_DAT, sub=True, lab_at='tl')
    positions = {'core': (665, 530), 'fastapi': (610, 685), 'mcpsdk': (705, 685),
                 'otel': (800, 685), 'rules': (975, 685), 'opa': (1100, 685),
                 'presidio': (1225, 685), 'gitleaks': (1350, 685),
                 'jaeger': (1005, 975), 'siemw': (1300, 975), 'pg': (650, 372)}
    for key, (x, y) in positions.items():
        s.nodes[key].update(x=x, y=y)
    s.nodes['core'].update(icon='flat-gear', size=68, label='요청 처리·중계')
    s.nodes['gitea']['label'] = 'Gitea'
    s.nodes['rules'].update(size=48, label='Rego · PAC-15\n룰셋 파일')
    s.nodes['opa'].update(size=60, label='OPA\n별도 컨테이너')
    s.nodes['presidio']['size'] = 48
    s.nodes['gitleaks']['size'] = 48
    s.nodes['gitleaks']['label'] = 'Gitleaks\n내장 라이브러리'
    s.node('sqlite', 'SQLite\n메타데이터', 'flat-ledger', 925, 370, 34)
    s.node('gitfiles', 'Git 저장소\n파일·객체', 'flat-folder', 1080, 370, 34)
    s.notes = [(920, 780, 'policy.rego · pac15.rego · decision.rego · data.json 등', 12, MUTED),
               (920, 805, '정책 번들 /policy · 읽기 전용 마운트 · 구획은 기능 기준', 12, C_POL)]
    drop = {'pol', 'trace', 'rule', 'db1', 'db2', 'ocsf'}
    s.edges = [ed for ed in s.edges if ed['id'] not in drop]
    for ed in s.edges:
        if ed['id'] == 'mcp2':
            ed['pts'] = [(523, 530), (631, 530)]
        if ed['id'] == 'mcp3':
            ed['pts'][0] = (699, 530)
        if ed['id'] == 'oidc':
            ed.update(pts=[(735, 200), (747, 200), (747, 90), (1485, 90), (1485, 366), (1495, 366)], lab=(1100, 93))
    e = s.edge
    e('db1', [(645, 290), (645, 320)], CTL, 2.5, '회원가입·도입 신청 저장', (720, 305), src='con', dst='led')
    e('db2', [(730, 475), (730, 435)], CTL, 2.5, '계정·정책 조회 / 판정 기록', (670, 454), src='gw', dst='led', both=True)
    e('gitmeta', [(1089, 246), (1089, 306), (815, 306), (815, 370), (908, 370)], CTL, 2, src='gitea', dst='sqlite')
    e('gitdata', [(1089, 306), (1205, 306), (1205, 370), (1097, 370)], CTL, 2, dst='gitfiles')
    e('trace', [(822, 685), (875, 685), (875, 975), (905, 975)], OBS, 2.5, 'OTLP', (877, 914), src='otel', dst='trc')
    e('policy', [(865, 640), (1100, 640), (1100, 655)], CTL, 2.5, '판정 요청·결과', (985, 637), src='gw', dst='opa', both=True)
    e('rule', [(999, 685), (1070, 685)], C_POL, 2.5, src='rules', dst='opa')
    e('inspect', [(865, 730), (890, 730), (890, 853), (1410, 853), (1410, 650), (1350, 650), (1350, 661)], CTL, 2.5,
      '입력·응답 검사', (1160, 853), src='gw', dst='gitleaks', both=True)
    e('inspect_pii', [(1410, 650), (1225, 650), (1225, 661)], CTL, 2.5, dst='presidio')
    e('dbout', [(765, 375), (795, 375), (795, 455), (1455, 455), (1455, 876), (1300, 876), (1300, 900)],
      OBS, 2.5, 'siem_outbox · 대기열 조회 / 전송 상태 갱신', (1175, 453), dash='7 5', src='led', dst='sg', both=True)
    e('ocsf', [(1425, 975), (1495, 975)], OBS, 3, 'OCSF', (1455, 950), src='sg', dst='siem')
    s.dots.extend([(1089, 306, CTL), (1410, 650, CTL)])
    return s


# ── 빨간 설명 층 ────────────────────────────────────────────────────────
REDBOXES = [
    ("A", "직원 PC", (12, 92, 316, 800),
     "직원은 계정을 둘 쓴다. 관리 계정(엔드포인트 키트가 AppArmor·nftables로 실행·통신 통제)에서 하네스를, 일반 사용자 계정에서 웹 콘솔을 쓴다. 계정 연동 커넥터(claude.ai·ChatGPT 앱)는 게이트웨이를 거치지 않아 관리형 설정으로 제한한다."),
    ("B", "관리자 PC", (12, 896, 316, 187),
     "보안 관리자가 웹 콘솔로 도입 승인·계약 검토·장치 활성화·종료 판정을 한다. 사설망 안에서만 접속한다."),
    ("C", "사설망", (334, 92, 92, 1051),
     "Tailscale(WireGuard)로 PC와 솔루션 기기를 묶는다. 하네스·키트·브라우저의 HTTPS(443) 접속은 한 줄로 모여 Caddy로 들어간다."),
    ("D", "진입·게이트웨이", (462, 447, 412, 266),
     "Caddy가 사설 CA HTTPS를 종단해 MCP 호출·장치 보고는 게이트웨이로, 콘솔·인증은 관리 콘솔로 나눈다. 게이트웨이(FastAPI·MCP SDK, 계측은 OpenTelemetry)가 호출을 판정해 전달하고 직원 토큰은 MCP 서버로 넘기지 않는다."),
    ("E", "정책 판정·검사", (547, 737, 422, 176),
     "정책 엔진 OPA가 룰셋 파일(Rego 정책·PAC-15 룰셋·data.json 등, 읽기 전용)을 읽어 허용·차단·확인을 판정한다. Presidio(개인정보)·Gitleaks(비밀값)가 호출 전후를 검사한다. 엔진이 응답하지 않으면 차단한다."),
    ("F", "관리 콘솔·인증", (547, 142, 196, 156),
     "관리 콘솔과 인증·장치 서비스. 회원가입 신청·도입 신청·승인은 PostgreSQL에 저장한다. Authlib로 조직 로그인(OIDC)을 검증한다."),
    ("G", "공급망 검증·격리 실행", (751, 142, 720, 156),
     "도입 신청 소스를 Syft·Trivy·Semgrep로 검사해 Gitea에 반입하고, 승인 뒤 정해진 레시피로 이미지를 빌드해 Docker 격리 컨테이너로 실행한다. 출구 프록시가 외부 통신을 심사된 목적지로 제한한다."),
    ("H", "SIEM 전달", (547, 937, 206, 181),
     "원장에 쌓인 전달 대기열을 SIEM 전달 워커가 OCSF로 보낸다(대기열·재전송). 기본은 꺼져 있다."),
    ("I", "기업 시스템 연계", (1487, 102, 256, 1030),
     "기존 LLM 게이트웨이(LiteLLM)·조직 IdP·비밀 저장소(OpenBao)·SIEM(Vector→OpenSearch)과 표준 규격으로 이어진다. 빨간 미설정은 기본 배치에 없는 연동이다. 현장 스택은 LiteLLM을 띄우지 않고 OpenBao 연동 코드는 아직 없다."),
    ("J", "외부", (1757, 102, 226, 590),
     "원격 MCP 서버(GitHub MCP·Context7)와 LLM 제공자. 모델 호출은 모델 프록시(연동 시 LiteLLM), 도구 호출은 MINT 게이트웨이를 거친다."),
    ("K", "로컬 MCP 격리 실행(예정)", (42, 602, 256, 136),
     "개발 예정. 엔드포인트 키트가 관리하는 격리 구역에서 로컬 MCP를 실행한다. 지금은 미등록 로컬 MCP를 AppArmor·nftables가 막고, 승인된 서버는 솔루션 기기의 격리 실행을 쓴다."),
    ("L", "추적", (897, 597, 156, 141),
     "게이트웨이에 내장된 OpenTelemetry SDK가 호출을 스팬으로 만들어 OTLP/HTTP로 Jaeger에 직접 보낸다. Jaeger는 메모리에만 보관해 재시작하면 사라지고, 공식 기록은 PostgreSQL 원장이 맡는다."),
    ("M", "원장 (PostgreSQL)", (547, 312, 206, 131),
     "관리대장(가입·도입 신청·승인 이력)과 판정 원장(해시 사슬)을 보관한다. 콘솔과 게이트웨이가 같은 DB를 쓴다. Gitea는 이 DB가 아니라 자체 SQLite에 저장소를 둔다."),
]
_role_updates = {
    'D': ('진입·호출 중계', (462, 467, 412, 301),
          'Caddy가 HTTPS를 종단하고 요청을 콘솔 또는 호출 중계로 나눈다. 중계 코드는 FastAPI·MCP SDK를 사용하며 별도 OPA에 판정을 요청한다. 허용된 호출만 서버별 자격으로 전달하고 직원 토큰은 전달하지 않는다.'),
    'E': ('정책 엔진·검사', (892, 582, 556, 251),
          '별도 OPA 컨테이너가 Rego·PAC-15 룰셋과 JSON 데이터를 읽기 전용으로 받아 판정한다. Presidio는 별도 서비스, Gitleaks는 중계 프로세스에 내장된 라이브러리다. 입력·응답을 검사하며 OPA 장애 시 차단한다.'),
    'G': ('공급망·격리 실행·저장소', (751, 142, 720, 301),
          'Syft·Trivy·Semgrep 검사 후 승인된 소스를 Gitea로 반입하고 Docker로 격리 실행한다. Gitea는 전용 볼륨에 SQLite 메타데이터와 Git 파일·객체를 각각 보관한다. PostgreSQL을 저장소로 쓰지 않는다.'),
    'H': ('SIEM 전달', (1172, 892, 261, 191),
          'PostgreSQL의 siem_outbox를 조회해 감사 이벤트를 OCSF로 전달하고 성공·재시도 상태를 DB에 갱신한다. 이 DB 연결을 보라색 점선으로 표시했다. 워커는 siem 프로필을 켤 때 실행한다.'),
    'L': ('추적', (897, 892, 216, 191),
          '호출 중계에 내장된 OpenTelemetry SDK가 OTLP/HTTP로 Jaeger에 스팬을 보낸다. 현재 구성은 메모리 보관이다. 감사 원장과 SIEM 전달 대기열은 PostgreSQL에 둔다.'),
    'M': ('관리 DB·감사 원장', (547, 312, 226, 131),
          '콘솔의 회원가입·도입 신청·계정·승인 이력, 게이트웨이의 정책 조회·판정 기록, SIEM 전달 대기열을 같은 PostgreSQL에 둔다. Gitea의 SQLite와 실제 Git 저장소는 별도 전용 볼륨이다.'),
}
REDBOXES = [(k, *_role_updates[k]) if k in _role_updates else (k, t, box, desc)
            for k, t, box, desc in REDBOXES]
BADGE_POS = {"D": "tr", "F": "tr"}
UNSET = ["litellm", "openbao"]


def badge_x(k, x, w):
    return x + w - 28 if BADGE_POS.get(k) == "tr" else x - 4


def badge_y(k, y, hh):
    return y + hh - 14 if BADGE_POS.get(k) == "bl" else y - 14


STEPS = [  # (번호, x, y)
    (1, 318, 360), (2, 527, 507), (3, 1415, 790), (4, 890, 637), (5, 1745, 530), (6, 730, 385)]
FLOW = [("하네스 호출", "Claude Code · Codex CLI"), ("HTTPS 종단", "Tailscale → Caddy"), ("토큰·입력 검사", "토큰 검증 · Presidio · Gitleaks"), ("정책 판정", "OPA · Rego/PAC-15"), ("MCP 서버 전달", "직원 토큰 미전달"), ("응답 검사·기록", "검사 도구 · PostgreSQL 원장")]
STEP_TEXT = ("요청 흐름  ① 하네스가 도구 호출  ② Caddy가 HTTPS 종단  ③ OPA·Authlib가 신원·정책 판정  "
             "④ Presidio·Gitleaks가 개인정보·비밀값 검사  ⑤ 승인된 MCP 서버로 전달(직원 토큰 미전달)  ⑥ 응답 검사 뒤 PostgreSQL 원장에 기록")


# ── SVG ─────────────────────────────────────────────────────────────────
def rgba(hexc, a):
    h = hexc.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{a})"


def svg_scene(s, annotate=False):
    h = H + (PANEL_H if annotate else 0)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}" viewBox="0 0 {W} {h}" '
         f'font-family="{FONT}, Malgun Gothic, sans-serif">', '<rect width="100%" height="100%" fill="#FFFFFF"/>', "<defs>"]
    for c in sorted({ed["color"] for ed in s.edges}):
        k = c.lstrip("#")
        o.append(f'<marker id="m{k}" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="6.5" markerHeight="6.5" '
                 f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>')
    o.append('<marker id="mred" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="6" markerHeight="6" orient="auto">'
             f'<path d="M0,0 L10,5 L0,10 z" fill="{RED}"/></marker></defs>')
    # 제목
    o.append(f'<text x="24" y="52" font-size="30" font-weight="800" fill="{TEXT}">MINT 구성도'
             f'<tspan font-size="15" font-weight="500" fill="{MUTED}" dx="14">오픈소스 구성 · 직원 PC·관리자 PC·솔루션 기기·기업 시스템</tspan></text>')
    for zz in sorted(s.zones, key=lambda q: q["sub"]):
        col = zz["color"]
        fa, sa = (0.07, 0.45) if zz["sub"] else (0.13, 0.6)
        da = ' stroke-dasharray="9 6"' if zz["dashed"] else ""
        o.append(f'<rect x="{zz["x"]}" y="{zz["y"]}" width="{zz["w"]}" height="{zz["h"]}" rx="14" fill="{rgba(col, fa)}" '
                 f'stroke="{rgba(col, sa)}" stroke-width="2"{da}/>')
        if zz["sub"]:
            o.append(f'<text x="{zz["x"] + 14}" y="{zz["y"] + 23}" font-size="13" font-weight="700" fill="{col}">{esc(zz["label"])}</text>')
        elif zz["lab_at"] == "l":
            if zz["icon"] and icon(zz["icon"]):
                mime, data = icon(zz["icon"])
                o.append(f'<image x="{zz["x"] + 78}" y="{zz["y"] + 13}" width="26" height="26" href="data:{mime};base64,{data}"/>')
            o.append(f'<text x="{zz["x"] + 112}" y="{zz["y"] + 32}" font-size="17" font-weight="800" fill="{col}">{esc(zz["label"])}</text>')
        else:
            cx = zz["x"] + zz["w"] / 2
            lab = zz["label"]
            size = 17
            ix = 0
            if zz["icon"] and icon(zz["icon"]):
                ix = 17
            tx = cx + ix / 2
            note = (f'<tspan font-size="12" font-weight="500" fill="{MUTED}" dx="8">{esc(zz["note"])}</tspan>' if zz["note"] else "")
            o.append(f'<text x="{tx:.1f}" y="{zz["y"] + 32}" text-anchor="middle" font-size="{size}" font-weight="800" fill="{col}">{esc(lab)}{note}</text>')
            if ix:
                mime, data = icon(zz["icon"])
                wlab = tw(lab, size) + (tw(zz["note"], 12) + 8 if zz["note"] else 0)
                o.append(f'<image x="{cx - wlab / 2 - 15:.1f}" y="{zz["y"] + 13}" width="26" height="26" href="data:{mime};base64,{data}"/>')
    for ed in s.edges:
        pts = ed["pts"]
        d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        da = f' stroke-dasharray="{ed["dash"]}"' if ed["dash"] else ""
        mk = f' marker-end="url(#m{ed["color"].lstrip("#")})"' if ed["arrow"] else ""
        if ed["both"]:
            mk += f' marker-start="url(#m{ed["color"].lstrip("#")})"'
        o.append(f'<polyline points="{d}" fill="none" stroke="#FFFFFF" stroke-opacity="0.94" stroke-width="{ed["width"] + 4}" '
                 f'stroke-linejoin="round" stroke-linecap="round"/>')
        o.append(f'<polyline points="{d}" fill="none" stroke="{ed["color"]}" stroke-width="{ed["width"]}"{da}{mk} '
                 f'stroke-linejoin="round" stroke-linecap="round"/>')
    for x, y, c in s.dots:
        o.append(f'<circle cx="{x}" cy="{y}" r="5" fill="{c}"/>')
    for ed in s.edges:
        if ed["label"]:
            x, y = ed["lab"]
            w = tw(ed["label"], 11.5) + 12
            o.append(f'<rect x="{x - w / 2:.1f}" y="{y - 11}" width="{w:.1f}" height="19" rx="9" fill="#FFFFFF" fill-opacity="0.92"/>')
            o.append(f'<text x="{x}" y="{y + 3}" text-anchor="middle" font-size="11.5" font-weight="700" fill="{ed["color"]}">{esc(ed["label"])}</text>')
    for nd in s.nodes.values():
        sz = nd["size"]
        planned = nd["status"] == "도입 예정"
        op = ' opacity="0.55"' if planned else ""
        pairs = [(nd["icon"], nd["x"])]
        if nd.get("icon2"):
            pairs = [(nd["icon"], nd["x"] - sz * 0.28), (nd["icon2"], nd["x"] + sz * 0.28)]
        for key, cx in pairs:
            ic = icon(key)
            if ic:
                mime, data = ic
                o.append(f'<image x="{cx - sz / 2:.1f}" y="{nd["y"] - sz / 2:.1f}" width="{sz}" height="{sz}" '
                         f'href="data:{mime};base64,{data}" preserveAspectRatio="xMidYMid meet"{op}/>')
            else:
                o.append(f'<rect x="{cx - sz / 2}" y="{nd["y"] - sz / 2}" width="{sz}" height="{sz}" rx="10" fill="#E6EBF2"/>')
        lines = nd["label"].split("\n")
        y0 = nd["y"] + sz / 2 + 16
        for i, ln in enumerate(lines):
            o.append(f'<text x="{nd["x"]}" y="{y0 + i * 15}" text-anchor="middle" font-size="13" font-weight="700" fill="{TEXT}">{esc(ln)}</text>')
        if nd["status"] in STATUS:
            lab, col = STATUS[nd["status"]]
            pw = tw(lab, 10.5) + 12
            py = y0 + (len(lines) - 1) * 15 + 6
            o.append(f'<rect x="{nd["x"] - pw / 2:.1f}" y="{py}" width="{pw:.1f}" height="15" rx="7.5" fill="{rgba(col, 0.13)}" stroke="{col}" stroke-width="1"/>')
            o.append(f'<text x="{nd["x"]}" y="{py + 11}" text-anchor="middle" font-size="10.5" font-weight="700" fill="{col}">{lab}</text>')
    for x, y, note, size, color in getattr(s, 'notes', []):
        o.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}">{esc(note)}</text>')
    # 범례
    lg_y = H - 138
    o.append(f'<rect x="20" y="{lg_y}" width="1380" height="118" rx="14" fill="#FFFFFF" stroke="#C5D3E6" stroke-width="1.5"/>')
    items = [("MCP 호출", MCP, None, 4), ("모델 호출", LLM, None, 3), ("관리·판정·검사", CTL, None, 3),
             ("사설망 HTTPS 묶음", "#1E9E9A", None, 4), ("기업 연동", INT, "7 5", 2.5), ("SIEM 전달", OBS, None, 3)]
    o.append(f'<text x="40" y="{lg_y + 30}" font-size="13" font-weight="800" fill="{TEXT}">선</text>')
    for i, (lab, c, da, w) in enumerate(items):
        x = 90 + i * 165
        d = f' stroke-dasharray="{da}"' if da else ""
        o.append(f'<line x1="{x}" y1="{lg_y + 26}" x2="{x + 34}" y2="{lg_y + 26}" stroke="{c}" stroke-width="{w}"{d}/>'
                 f'<text x="{x + 42}" y="{lg_y + 31}" font-size="12.5" fill="{TEXT}">{lab}</text>')
    o.append(f'<text x="40" y="{lg_y + 66}" font-size="13" font-weight="800" fill="{TEXT}">상태</text>')
    o.append(f'<text x="90" y="{lg_y + 71}" font-size="12.5" fill="{TEXT}">표시 없음 = 사용 중</text>')
    for i, (lab, col) in enumerate((("시험", "#7B3FA0"), ("연동 시험", "#7B3FA0"), ("예정", "#8A94A3"))):
        x = 250 + i * 95
        pw = tw(lab, 10.5) + 12
        o.append(f'<rect x="{x}" y="{lg_y + 57}" width="{pw:.1f}" height="15" rx="7.5" fill="{rgba(col, 0.13)}" stroke="{col}"/>'
                 f'<text x="{x + pw / 2}" y="{lg_y + 68}" text-anchor="middle" font-size="10.5" font-weight="700" fill="{col}">{lab}</text>')
    o.append(f'<rect x="560" y="{lg_y + 56}" width="34" height="18" rx="6" fill="{rgba(C_ENT, 0.08)}" stroke="{rgba(C_ENT, 0.6)}" stroke-width="2" stroke-dasharray="6 4"/>'
             f'<text x="602" y="{lg_y + 70}" font-size="12.5" fill="{TEXT}">점선 상자 = 기업 시스템(연동 대상)</text>')
    o.append(f'<text x="40" y="{lg_y + 104}" font-size="11.5" fill="{MUTED}">파란 외곽 안 전체 = MINT 솔루션 구성요소 · 선 교차는 연결 아님(접점은 원 표시) · 상태 표기는 기존 도면 유지</text>')
    cr = credits()
    if cr:
        o.append(f'<text x="{W - 20}" y="{H - 8}" text-anchor="end" font-size="7" fill="#B8BFC8">{esc(cr)}</text>')
    stamp = datetime.now().strftime("%Y-%m-%d")
    o.append(f'<text x="{W - 24}" y="46" text-anchor="end" font-size="13" fill="{MUTED}">{stamp}</text>')

    if annotate:
        for k, title, (x, y, w, hh), _ in REDBOXES:
            o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{hh}" rx="12" fill="none" stroke="{RED}" stroke-width="3.2" stroke-dasharray="12 7"/>')
            bx, by = badge_x(k, x, w), badge_y(k, y, hh)
            o.append(f'<rect x="{bx}" y="{by}" width="28" height="28" rx="6" fill="{RED}"/>'
                     f'<text x="{bx + 14}" y="{by + 20}" text-anchor="middle" font-size="17" font-weight="800" fill="#FFFFFF">{k}</text>')
        for key in UNSET:
            nd = s.nodes[key]
            ux, uy = nd["x"] - nd["size"] / 2 - 56, nd["y"] - 9
            o.append(f'<rect x="{ux}" y="{uy}" width="50" height="19" rx="9.5" fill="{RED}"/>'
                     f'<text x="{ux + 25}" y="{uy + 14}" text-anchor="middle" font-size="12" font-weight="800" fill="#FFFFFF">미설정</text>')
        for num, x, y in STEPS:
            o.append(f'<circle cx="{x}" cy="{y}" r="13" fill="{RED}" stroke="#FFFFFF" stroke-width="2"/>'
                     f'<text x="{x}" y="{y + 5.5}" text-anchor="middle" font-size="15" font-weight="800" fill="#FFFFFF">{num}</text>')
        py = H + 8
        o.append(f'<text x="24" y="{py + 22}" font-size="20" font-weight="800" fill="{RED}">영역별 역할</text>')
        o.append(f'<text x="150" y="{py + 22}" font-size="12.5" fill="{MUTED}">빨간 점선 상자의 영문자 = 아래 설명, 빨간 원 번호 = 요청이 지나는 순서</text>')
        cols, cw, ch, gap = 6, 315, 190, 14
        cards = [(k, t, d) for k, t, _, d in REDBOXES]
        for i, (k, t, d) in enumerate(cards):
            cx = 20 + (i % cols) * (cw + gap)
            cy = py + 38 + (i // cols) * (ch + gap)
            o.append(f'<rect x="{cx}" y="{cy}" width="{cw}" height="{ch}" rx="12" fill="#FFF7F6" stroke="{RED}" stroke-width="1.8"/>')
            o.append(f'<rect x="{cx + 12}" y="{cy + 12}" width="26" height="26" rx="6" fill="{RED}"/>'
                     f'<text x="{cx + 25}" y="{cy + 31}" text-anchor="middle" font-size="16" font-weight="800" fill="#FFFFFF">{k}</text>')
            o.append(f'<text x="{cx + 48}" y="{cy + 32}" font-size="15" font-weight="800" fill="{TEXT}">{esc(t)}</text>')
            for j, ln in enumerate(wrap(d, cw - 28, 12.5)[:9]):
                o.append(f'<text x="{cx + 14}" y="{cy + 58 + j * 19}" font-size="12.5" fill="{TEXT}">{esc(ln)}</text>')
        # 요청 흐름 띠(빨간 화살표)
        fy = py + 38 + ((len(REDBOXES) + cols - 1) // cols) * (ch + gap) + 12
        fh = PANEL_H - (fy - H) - 14
        o.append(f'<text x="24" y="{fy + 4}" font-size="15" font-weight="800" fill="{RED}">요청 흐름</text>')
        n_ = len(FLOW)
        cw2, g2 = 270, (W - 40 - 6 * 270) / 5
        for i, (t1, t2) in enumerate(FLOW):
            x0 = 20 + i * (cw2 + g2)
            y0 = fy + 14
            o.append(f'<rect x="{x0}" y="{y0}" width="{cw2}" height="{fh - 14}" rx="12" fill="#FFF7F6" stroke="{RED}" stroke-width="1.8"/>')
            o.append(f'<circle cx="{x0 + 24}" cy="{y0 + (fh - 14) / 2}" r="13" fill="{RED}"/>'
                     f'<text x="{x0 + 24}" y="{y0 + (fh - 14) / 2 + 5.5}" text-anchor="middle" font-size="15" font-weight="800" fill="#FFFFFF">{i + 1}</text>')
            o.append(f'<text x="{x0 + 46}" y="{y0 + (fh - 14) / 2 - 3}" font-size="14" font-weight="800" fill="{TEXT}">{esc(t1)}</text>')
            o.append(f'<text x="{x0 + 46}" y="{y0 + (fh - 14) / 2 + 16}" font-size="12" fill="{MUTED}">{esc(t2)}</text>')
            if i < n_ - 1:
                ax = x0 + cw2
                ay = y0 + (fh - 14) / 2
                o.append(f'<line x1="{ax + 3}" y1="{ay}" x2="{ax + g2 - 3}" y2="{ay}" stroke="{RED}" stroke-width="3" marker-end="url(#mred)"/>')
    o.append("</svg>")
    return "\n".join(o)


# ── draw.io ─────────────────────────────────────────────────────────────
FS = (f"fontFamily={FONT};fontSource=https%3A%2F%2Ffonts.googleapis.com%2Fcss%3Ffamily%3DNoto%2BSans%2BKR;")


def drawio_page(s, pid, annotate=False):
    cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']

    def cid(x):
        return f"{pid}-{x}"

    cells.append(f'<mxCell id="{cid("title")}" value="MINT 구성도" style="text;html=1;fontSize=30;fontStyle=1;fontColor={TEXT};align=left;{FS}" '
                 f'vertex="1" parent="1"><mxGeometry x="24" y="22" width="400" height="44" as="geometry"/></mxCell>')
    for zz in sorted(s.zones, key=lambda q: q["sub"]):
        col = zz["color"]
        fo, so = (7, 45) if zz["sub"] else (13, 60)
        dash = "dashed=1;dashPattern=9 6;" if zz["dashed"] else ""
        if zz["lab_at"] == "l" and not zz["sub"]:
            pos = "verticalAlign=top;align=left;spacingLeft=112;spacingTop=6;fontSize=17;"
        elif zz["sub"]:
            pos = f"verticalAlign=top;align=left;spacingLeft=12;spacingTop=2;fontSize=13;"
        else:
            pos = f"verticalAlign=top;align=center;spacingTop=6;fontSize=17;"
        label = zz["label"] + (f"  {zz['note']}" if zz["note"] else "")
        cells.append(f'<mxCell id="{cid(zz["id"])}" value="{esc(label)}" style="rounded=1;arcSize=3;absoluteArcSize=0;fillColor={col};fillOpacity={fo};'
                     f'strokeColor={col};strokeOpacity={so};strokeWidth=2;{dash}{pos}fontStyle=1;fontColor={col};{FS}" vertex="1" parent="1">'
                     f'<mxGeometry x="{zz["x"]}" y="{zz["y"]}" width="{zz["w"]}" height="{zz["h"]}" as="geometry"/></mxCell>')
    for nd in s.nodes.values():
        sz = nd["size"]
        ic = icon(nd["icon"])
        label = nd["label"].replace("\n", "<br>")
        if nd["status"] in STATUS:
            label += f'<br><font style="font-size:10px" color="{STATUS[nd["status"]][1]}">[{STATUS[nd["status"]][0]}]</font>'
        img = f"image=data:{ic[0]},{ic[1]};" if ic else ""
        st = (f"shape=image;{img}imageAspect=1;aspect=fixed;html=1;verticalLabelPosition=bottom;verticalAlign=top;labelPosition=center;"
              f"align=center;spacingTop=-2;fontSize=13;fontStyle=1;fontColor={TEXT};{'opacity=55;' if nd['status'] == '도입 예정' else ''}{FS}")
        attrs = f'label="{esc(label)}"'
        if nd["status"]:
            attrs += f' 상태="{esc(nd["status"])}"'
        if nd["cmp"]:
            attrs += f' 구성요소="{esc(nd["cmp"])}"'
        if nd.get("icon2"):
            wd = sz * 1.56
            st2 = ("rounded=0;fillColor=none;strokeColor=none;html=1;verticalLabelPosition=bottom;verticalAlign=top;labelPosition=center;"
                   f"align=center;spacingTop=-2;fontSize=13;fontStyle=1;fontColor={TEXT};{FS}")
            cells.append(f'<object id="{cid(nd["id"])}" {attrs}><mxCell style="{st2}" vertex="1" parent="1">'
                         f'<mxGeometry x="{nd["x"] - wd / 2:.1f}" y="{nd["y"] - sz / 2:.1f}" width="{wd:.1f}" height="{sz}" as="geometry"/></mxCell></object>')
            for j, key in enumerate((nd["icon"], nd["icon2"])):
                icj = icon(key)
                imgj = f"image=data:{icj[0]},{icj[1]};" if icj else ""
                cells.append(f'<mxCell id="{cid(nd["id"])}-i{j}" value="" style="shape=image;{imgj}imageAspect=1;aspect=fixed;" vertex="1" parent="{cid(nd["id"])}">'
                             f'<mxGeometry x="{j * sz * 0.56:.1f}" y="0" width="{sz}" height="{sz}" as="geometry"/></mxCell>')
            continue
        cells.append(f'<object id="{cid(nd["id"])}" {attrs}><mxCell style="{st}" vertex="1" parent="1">'
                     f'<mxGeometry x="{nd["x"] - sz / 2:.1f}" y="{nd["y"] - sz / 2:.1f}" width="{sz}" height="{sz}" as="geometry"/></mxCell></object>')

    def rel(id, px, py):
        x, y, w, hh = s.bbox(id)
        return min(1, max(0, (px - x) / w)), min(1, max(0, (py - y) / hh))

    for i, ed in enumerate(s.edges):
        pts = ed["pts"]
        dash = f"dashed=1;dashPattern={ed['dash']};" if ed["dash"] else ""
        st = (f"edgeStyle=none;rounded=0;html=1;strokeColor={ed['color']};strokeWidth={ed['width']};{dash}"
              f"{'endArrow=blockThin;endFill=1;endSize=6;' if ed['arrow'] else 'endArrow=none;'}{'startArrow=blockThin;startFill=1;startSize=6;' if ed['both'] else 'startArrow=none;'}"
              f"fontSize=11.5;fontColor={ed['color']};fontStyle=1;labelBackgroundColor=#FFFFFF;{FS}")
        src = dst = ""
        if ed["src"]:
            ex, ey = rel(ed["src"], *pts[0])
            st += f"exitX={ex:.4f};exitY={ey:.4f};exitPerimeter=0;"
            src = f' source="{cid(ed["src"])}"'
        if ed["dst"]:
            nx, ny = rel(ed["dst"], *pts[-1])
            st += f"entryX={nx:.4f};entryY={ny:.4f};entryPerimeter=0;"
            dst = f' target="{cid(ed["dst"])}"'
        way = "".join(f'<mxPoint x="{x}" y="{y}"/>' for x, y in pts[1:-1])
        geo = '<mxGeometry relative="1" as="geometry">'
        if not ed["src"]:
            geo += f'<mxPoint x="{pts[0][0]}" y="{pts[0][1]}" as="sourcePoint"/>'
        if not ed["dst"]:
            geo += f'<mxPoint x="{pts[-1][0]}" y="{pts[-1][1]}" as="targetPoint"/>'
        if way:
            geo += f'<Array as="points">{way}</Array>'
        geo += "</mxGeometry>"
        cells.append(f'<mxCell id="{cid("e" + str(i))}" value="" style="{st}jumpStyle=arc;jumpSize=8;" edge="1" parent="1"{src}{dst}>{geo}</mxCell>')
        if ed['label']:
            lx, ly = ed['lab']
            lw = tw(ed['label'], 11.5) + 12
            cells.append(f'<mxCell id="{cid("el" + str(i))}" value="{esc(ed["label"])}" '
                         f'style="text;html=1;fillColor=#FFFFFF;strokeColor=none;align=center;verticalAlign=middle;fontSize=11.5;fontStyle=1;fontColor={ed["color"]};{FS}" vertex="1" parent="1">'
                         f'<mxGeometry x="{lx-lw/2}" y="{ly-11}" width="{lw}" height="19" as="geometry"/></mxCell>')
    for j, (x, y, note, size, color) in enumerate(getattr(s, 'notes', [])):
        cells.append(f'<mxCell id="{cid("note" + str(j))}" value="{esc(note)}" style="text;html=1;align=left;fontSize={size};fontColor={color};{FS}" vertex="1" parent="1">'
                     f'<mxGeometry x="{x}" y="{y-15}" width="500" height="22" as="geometry"/></mxCell>')
    for j, (x, y, c) in enumerate(s.dots):
        cells.append(f'<mxCell id="{cid("dot" + str(j))}" value="" style="ellipse;fillColor={c};strokeColor=none;" vertex="1" parent="1">'
                     f'<mxGeometry x="{x - 5}" y="{y - 5}" width="10" height="10" as="geometry"/></mxCell>')
    def text_cell(key, value, x, y, width, height=22, size=12.5, color=TEXT):
        cells.append(f'<mxCell id="{cid(key)}" value="{esc(value)}" style="text;html=1;align=left;verticalAlign=middle;fontSize={size};fontColor={color};{FS}" vertex="1" parent="1">'
                     f'<mxGeometry x="{x}" y="{y}" width="{width}" height="{height}" as="geometry"/></mxCell>')
    if s.name != '솔루션 기기 내부':
        text_cell('subtitle', '오픈소스 구성 · 직원 PC·관리자 PC·솔루션 기기·기업 시스템', 208, 27, 900, 28, 15, MUTED)
        text_cell('date', '2026-10-21', 1870, 27, 105, 28, 13, MUTED)
        ly = H - 138
        cells.append(f'<mxCell id="{cid("legend")}" value="" style="rounded=1;arcSize=10;fillColor=#FFFFFF;strokeColor=#C5D3E6;strokeWidth=1.5;" vertex="1" parent="1">'
                     f'<mxGeometry x="20" y="{ly}" width="1380" height="118" as="geometry"/></mxCell>')
        text_cell('legend_head', '선', 40, ly+15, 40, size=13)
        for j, (label, color) in enumerate([('MCP 호출', MCP), ('모델 호출', LLM), ('관리·판정·검사', CTL),
                                           ('사설망 HTTPS 묶음', C_NET), ('기업 연동(점선)', INT), ('SIEM 전달', OBS)]):
            x = 90 + j*165
            cells.append(f'<mxCell id="{cid("legend_line"+str(j))}" value="" style="strokeColor={color};strokeWidth=3;endArrow=none;{"dashed=1;" if j==4 else ""}" edge="1" parent="1">'
                         f'<mxGeometry relative="1" as="geometry"><mxPoint x="{x}" y="{ly+26}" as="sourcePoint"/><mxPoint x="{x+34}" y="{ly+26}" as="targetPoint"/></mxGeometry></mxCell>')
            text_cell('legend_text'+str(j), label, x+42, ly+15, 150)
        text_cell('legend_state', '상태  표시 없음 = 사용 중    [시험]    [연동 시험]    [예정]      점선 상자 = 기업 시스템(연동 대상)', 40, ly+50, 1300)
        text_cell('legend_scope', '파란 외곽 안 전체 = MINT 솔루션 구성요소 · 선 교차는 연결 아님(접점은 원 표시) · 상태 표기는 기존 도면 유지', 40, ly+88, 1300, size=11.5, color=MUTED)
    if annotate:
        for k, title, (x, y, w, hh), _ in REDBOXES:
            cells.append(f'<mxCell id="{cid("rb" + k)}" value="" style="rounded=1;arcSize=3;fillColor=none;strokeColor={RED};strokeWidth=3;dashed=1;dashPattern=12 7;" '
                         f'vertex="1" parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" height="{hh}" as="geometry"/></mxCell>')
            cells.append(f'<mxCell id="{cid("rk" + k)}" value="{k}" style="rounded=1;fillColor={RED};strokeColor=none;fontColor=#FFFFFF;fontSize=17;fontStyle=1;{FS}" '
                         f'vertex="1" parent="1"><mxGeometry x="{badge_x(k, x, w)}" y="{badge_y(k, y, hh)}" width="28" height="28" as="geometry"/></mxCell>')
        for key in UNSET:
            nd = s.nodes[key]
            cells.append(f'<mxCell id="{cid("un" + key)}" value="미설정" style="rounded=1;arcSize=50;fillColor={RED};strokeColor=none;fontColor=#FFFFFF;fontSize=12;fontStyle=1;{FS}" '
                         f'vertex="1" parent="1"><mxGeometry x="{nd["x"] - nd["size"] / 2 - 56}" y="{nd["y"] - 9}" width="50" height="19" as="geometry"/></mxCell>')
        for num, x, y in STEPS:
            cells.append(f'<mxCell id="{cid("st" + str(num))}" value="{num}" style="ellipse;fillColor={RED};strokeColor=#FFFFFF;strokeWidth=2;fontColor=#FFFFFF;fontSize=15;fontStyle=1;{FS}" '
                         f'vertex="1" parent="1"><mxGeometry x="{x - 13}" y="{y - 13}" width="26" height="26" as="geometry"/></mxCell>')
        py = H + 8
        cells.append(f'<mxCell id="{cid("ph")}" value="영역별 역할" style="text;html=1;fontSize=20;fontStyle=1;fontColor={RED};align=left;{FS}" vertex="1" parent="1">'
                     f'<mxGeometry x="24" y="{py + 6}" width="200" height="30" as="geometry"/></mxCell>')
        cols, cw, ch, gap = 6, 315, 190, 14
        for i, (k, t, _, d) in enumerate(REDBOXES):
            cx = 20 + (i % cols) * (cw + gap)
            cy = py + 38 + (i // cols) * (ch + gap)
            val = f"<b>{k}  {esc(t)}</b><br><br>{esc(d)}"
            cells.append(f'<mxCell id="{cid("cd" + k)}" value="{esc(val)}" style="rounded=1;arcSize=5;html=1;whiteSpace=wrap;fillColor=#FFF7F6;strokeColor={RED};'
                         f'strokeWidth=1.8;align=left;verticalAlign=top;spacing=12;fontSize=12;fontColor={TEXT};{FS}" vertex="1" parent="1">'
                         f'<mxGeometry x="{cx}" y="{cy}" width="{cw}" height="{ch}" as="geometry"/></mxCell>')
        fy = py + 38 + ((len(REDBOXES) + cols - 1) // cols) * (ch + gap) + 12
        fh = PANEL_H - (fy - H) - 14
        cells.append(f'<mxCell id="{cid("flowh")}" value="요청 흐름" style="text;html=1;fontSize=15;fontStyle=1;fontColor={RED};align=left;{FS}" vertex="1" parent="1">'
                     f'<mxGeometry x="24" y="{fy - 8}" width="200" height="24" as="geometry"/></mxCell>')
        cw2, g2 = 270, (W - 40 - 6 * 270) / 5
        for i, (t1, t2) in enumerate(FLOW):
            x0 = 20 + i * (cw2 + g2)
            val = f"<b>{i + 1}  {esc(t1)}</b><br><font style=\"font-size:12px\" color=\"{MUTED}\">{esc(t2)}</font>"
            cells.append(f'<mxCell id="{cid("fl" + str(i))}" value="{esc(val)}" style="rounded=1;arcSize=12;html=1;whiteSpace=wrap;fillColor=#FFF7F6;strokeColor={RED};'
                         f'strokeWidth=1.8;align=left;verticalAlign=middle;spacingLeft=14;fontSize=14;fontColor={TEXT};{FS}" vertex="1" parent="1">'
                         f'<mxGeometry x="{x0:.1f}" y="{fy + 14}" width="{cw2}" height="{fh - 14}" as="geometry"/></mxCell>')
            if i < len(FLOW) - 1:
                cells.append(f'<mxCell id="{cid("fa" + str(i))}" value="" style="edgeStyle=none;html=1;strokeColor={RED};strokeWidth=3;endArrow=blockThin;endFill=1;endSize=6;" '
                             f'edge="1" parent="1" source="{cid("fl" + str(i))}" target="{cid("fl" + str(i + 1))}"><mxGeometry relative="1" as="geometry"/></mxCell>')
    h = H + (PANEL_H if annotate else 0)
    model = (f'<mxGraphModel dx="1400" dy="900" grid="0" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" '
             f'page="1" pageScale="1" pageWidth="{W}" pageHeight="{h}" background="#FFFFFF" math="0" shadow="0"><root>{"".join(cells)}</root></mxGraphModel>')
    return f'<diagram id="p{pid}" name="{esc(s.name)}">{model}</diagram>'


# ── 솔루션 기기 내부만 보는 판 ─────────────────────────────────────────────
def build_internal():
    s = build()
    keep_nodes = {"proxy", "caddy", "console", "authlib", "intake", "syft", "trivy", "semgrep", "gitea", "sqlite", "gitfiles", "runner", "docker",
                  "markitdown", "egress", "core", "fastapi", "mcpsdk", "otel", "rules", "opa", "presidio", "gitleaks", "jaeger", "pg", "siemw"}
    keep_zones = {"sol", "con", "sup", "run", "gw", "pol", "trc", "led", "sg", "gitstore"}
    s.nodes = {k: v for k, v in s.nodes.items() if k in keep_nodes}
    s.zones = [z for z in s.zones if z["id"] in keep_zones]
    drop = {"llm1", "llm2", "llm2b", "llm3", "oidc", "b_h", "b_k", "b_u", "b_a", "coll", "trunk", "mcp3", "ocsf", "sv", "so"}
    s.edges = [ed for ed in s.edges if ed["id"] not in drop]
    s.dots = [d for d in s.dots if d[0] != 1615]
    TEAL = "#1E9E9A"
    e = s.edge
    e("in", [(395, 530), (463, 530)], TEAL, 4, "HTTPS :443 (사설망)", (415, 512), dst="caddy")
    e("pin", [(395, 205), (464, 205)], LLM, 3, "모델 호출", (428, 189), dst="proxy")
    e("pout", [(490, 179), (490, 70)], LLM, 3, "허용 목적지로 (모델 API)", (610, 84), src="proxy")
    e("oout", [(735, 200), (747, 200), (747, 70)], INT, 2.5, "조직 로그인 (OIDC)", (850, 84), dash="7 5", src="con")
    e("mout", [(699, 530), (1520, 530)], MCP, 4, "MCP 서버로 · 직원 토큰 미전달 · 서버별 자격", (1100, 514), src="core")
    e("sout", [(1425, 975), (1520, 975)], OBS, 3, "OCSF", (1472, 950), src="sg")
    return s


def make_internal(stamp):
    s = build_internal()
    s.name = "솔루션 기기 내부"
    svg = svg_scene(s, False)
    x0, y0, vw, vh = 330, 0, 1240, 1200
    svg = re.sub(r'width="\d+" height="\d+" viewBox="[^"]*"', f'width="{vw}" height="{vh}" viewBox="{x0} {y0} {vw} {vh}"', svg, count=1)
    svg = re.sub(r'<text x="24" y="52".*?</text>', '', svg, count=1, flags=re.S)
    svg = re.sub(r'<text x="\d+" y="46" text-anchor="end"[^>]*>[^<]*</text>', '', svg, count=1)
    title = (f'<text x="350" y="{vh - 22}" font-size="24" font-weight="800" fill="{TEXT}">MINT 구성도 · 솔루션 기기 내부'
             f'<tspan font-size="13" font-weight="500" fill="{MUTED}" dx="12">2026-10-21 · 파란 외곽 안 전체가 솔루션 구성요소</tspan></text>')
    cut = svg.index(f'<rect x="20" y="{H - 138}"')
    svg = svg[:cut] + title + '</svg>'
    sp = OUT / f"MINT_구성도_솔루션내부_{stamp}.svg"
    sp.write_text(svg, encoding="utf-8")
    to_png(sp, OUT / f"MINT_구성도_솔루션내부_{stamp}.png", vw, vh, 1.35)
    page = ET.fromstring(drawio_page(s, 'p1'))
    model = page.find('mxGraphModel')
    model.set('pageWidth', str(vw))
    model.set('pageHeight', str(vh))
    title_cell = model.find('.//mxCell[@id="p1-title"]')
    title_cell.set('value', 'MINT 구성도 · 솔루션 기기 내부')
    title_cell.find('mxGeometry').attrib.update(x='350', y=str(vh-52), width='950', height='42')
    for geom in model.iter('mxGeometry'):
        if 'x' in geom.attrib and geom.get('relative') != '1':
            geom.set('x', str(float(geom.get('x')) - x0))
    for point in model.iter('mxPoint'):
        if 'x' in point.attrib:
            point.set('x', str(float(point.get('x')) - x0))
    page = ET.tostring(page, encoding='unicode')
    (OUT / f"MINT_구조도_솔루션내부_{stamp}.drawio").write_text(
        '<mxfile host="app.diagrams.net" agent="MINT build_architecture.py" version="24.0.0">' + page + "</mxfile>", encoding="utf-8")




def to_png(svg_path, png_path, w, h, scale=1.0):
    ud = tempfile.mkdtemp(prefix="chrome-ud-")
    cmd = [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={ud}",
           f"--window-size={w},{h}", f"--force-device-scale-factor={scale}", "--default-background-color=FFFFFFFF",
           f"--screenshot={png_path}", svg_path.as_uri()]
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)


def main():
    stamp = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%m%d%H%M")
    OUT.mkdir(exist_ok=True)
    s = build()
    names = {False: "MINT_구성도", True: "MINT_구성도_역할설명"}
    for ann in (False, True):
        s.name = "구성도" if not ann else "역할 설명"
        svg = svg_scene(s, ann)
        sp = OUT / f"{names[ann]}_{stamp}.svg"
        sp.write_text(svg, encoding="utf-8")
        h = H + (PANEL_H if ann else 0)
        to_png(sp, OUT / f"{names[ann]}_{stamp}.png", W, h)
    pages = []
    for i, ann in enumerate((False, True)):
        s.name = "구성도" if not ann else "역할 설명"
        pages.append(drawio_page(s, f"p{i + 1}", ann))
    (OUT / f"MINT_구조도_{stamp}.drawio").write_text(
        '<mxfile host="app.diagrams.net" agent="MINT build_architecture.py" version="24.0.0">' + "".join(pages) + "</mxfile>",
        encoding="utf-8")
    make_internal(stamp)
    print("stamp", stamp)


if __name__ == "__main__":
    main()
