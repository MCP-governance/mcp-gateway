"""MINT 구성도 10-28판(10-23판 배치 유지) — 요청 흐름 순서 배치, 양방향 상호작용, 오픈소스 목적, 한/영.

사용: python build_architecture.py [MMDDHHmm]
출력: export/ 아래 구성도·역할 설명 SVG·PNG(한/영)와 draw.io(한/영).
아이콘·draw.io 변환은 10-21판 생성기(build_architecture_codex.py)를 그대로 쓴다.
"""
import importlib.util
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# 저장소 사본: 10-21판 렌더러(base_renderer.py)를 옆에 두고 아이콘은 docs/ai/architecture/icons를 쓴다.
_spec = importlib.util.spec_from_file_location("cx", ROOT / "base_renderer.py")
cx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cx)
cx.ROOT, cx.ICONS = ROOT.parent, ROOT.parent / "icons" / "raw"
esc, tw, wrap, icon, rgba, Scene, to_png = cx.esc, cx.tw, cx.wrap, cx.icon, cx.rgba, cx.Scene, cx.to_png
FONT, TEXT, MUTED, RED = cx.FONT, cx.TEXT, cx.MUTED, cx.RED
OUT = ROOT / "export"

W, H = 2280, 1200
PANEL_H = 690
MCP, LLM, CTL, INT, OBS = "#E8A600", "#B0367C", "#3B7DD8", "#8A94A3", "#7B3FA0"
C_EMP, C_ADM, C_NET, C_SOL, C_EXT, C_ENT = "#EF7D22", "#C9962B", "#1E9E9A", "#2F6FD6", "#0F9D84", "#66727F"
C_POL, C_SUP, C_OBS, C_DAT, C_GW, C_MOD = "#D93A3A", "#5E9E2F", "#7B3FA0", "#2E4A6B", "#2F6FD6", "#B0367C"
TEAL = "#1E9E9A"

# 상태 표지: 키 → (한국어, 영어, 색)
STATUS = {"test": ("시험", "Pilot", "#7B3FA0"), "int": ("연동 시험", "Integration pilot", "#7B3FA0"),
          "off": ("기본 꺼짐", "Off by default", "#8A94A3"), "unset": ("미설정", "Not configured", "#C0392B"),
          "os": ("Windows·macOS 시험", "Windows/macOS pilot", "#7B3FA0"),
          "iso": ("격리 모드", "Isolated mode", "#8A94A3")}
VENDOR = "#0F9D84"  # 기본 기능·계정 커넥터: 게이트웨이 밖 벤더 직접(관리형 설정으로 차단)


class Scene2(Scene):
    def __init__(self, name, lang):
        super().__init__(name)
        self.lang = lang
        self.purpose = {}
        self.notes = []

    def n(self, id, label, purpose, icon_key, x, y, size=44, status="", icon2=None):
        self.node(id, label, icon_key, x, y, size, status, "", icon2)
        self.purpose[id] = purpose


def build(lang="ko"):
    T = (lambda ko, en: ko) if lang == "ko" else (lambda ko, en: en)
    s = Scene2("구성도", lang)
    z, n, e = s.zone, s.n, s.edge

    # ── 영역: 왼쪽에서 오른쪽으로 요청이 지나는 순서 ─────────────────────────
    z("emp", 20, 80, 330, 790, T("직원 PC", "Employee PC"), C_EMP, icon_key="flat-laptop", note=T("엔드포인트", "endpoint"))
    z("usr", 40, 122, 290, 118, T("사용자 계정", "User account"), C_EMP, sub=True, lab_at="tl")
    z("kit", 40, 258, 290, 596, T("엔드포인트 키트 · 간편 모드(기본)", "Endpoint kit · simple mode (default)"), C_EMP, sub=True, lab_at="tl")
    z("hn", 50, 290, 270, 222, T("하네스 (AI 코딩 에이전트)", "Harness (AI coding agents)"), C_EMP, sub=True, lab_at="tl")
    z("loc", 50, 662, 270, 180, T("로컬 MCP 격리 실행", "Local MCP isolation"), C_EMP, sub=True, lab_at="tl")
    z("adm", 20, 890, 330, 160, T("관리자 PC", "Admin PC"), C_ADM, icon_key="flat-desktop")
    z("net", 370, 80, 90, 970, T("사설망", "Network"), C_NET)
    z("sol", 480, 80, 1250, 970, T("MINT 솔루션", "MINT solution"), C_SOL, icon_key="flat-server", lab_at="l")
    z("prx", 495, 300, 110, 98, T("모델 프록시", "Model proxy"), C_MOD, sub=True, lab_at="tl")
    z("ing", 495, 442, 110, 588, T("진입", "Ingress"), C_GW, sub=True, lab_at="tl")
    z("con", 630, 280, 240, 140, T("관리 콘솔·인증", "Console · sign-in"), C_DAT, sub=True, lab_at="tl")
    z("sup", 890, 280, 440, 140, T("공급망 검증", "Supply-chain review"), C_SUP, sub=True, lab_at="tl")
    z("run", 1350, 280, 370, 140, T("승인 후 격리 실행 (솔루션)", "Approved runtime (solution)"), C_SUP, sub=True, lab_at="tl")
    z("gw", 630, 435, 260, 335, T("호출 중계", "Call relay"), C_GW, sub=True, lab_at="tl")
    z("pol", 910, 435, 505, 285, T("입력 검사 · 정책 판정", "Input checks · policy decision"), C_POL, sub=True, lab_at="tl")
    z("led", 630, 800, 260, 150, T("관리 DB·감사 원장", "Admin DB · audit ledger"), C_DAT, sub=True, lab_at="tl")
    z("trc", 910, 800, 170, 150, T("추적", "Tracing"), C_OBS, sub=True, lab_at="tl")
    z("lsy", 1100, 800, 180, 150, T("LiteLLM 동기화", "LiteLLM sync"), C_OBS, sub=True, lab_at="tl")
    z("sgw", 1300, 800, 170, 150, T("SIEM 전달", "SIEM export"), C_OBS, sub=True, lab_at="tl")
    z("lgw", 1755, 80, 220, 150, T("기업 LLM 게이트웨이", "Enterprise LLM gateway"), C_ENT, dashed=True)
    z("idp", 1755, 255, 220, 150, T("조직 IdP", "Org IdP"), C_ENT, dashed=True)
    z("vault", 1755, 520, 220, 150, T("비밀 저장소", "Secrets store"), C_ENT, dashed=True)
    z("siem", 1755, 780, 220, 270, "SIEM", C_ENT, dashed=True)
    z("prov", 2015, 80, 245, 150, T("LLM 제공자", "LLM providers"), C_MOD)
    z("mcps", 2015, 420, 245, 330, T("원격 MCP 서버", "Remote MCP servers"), C_EXT)

    # ── 직원 PC: 사용자 계정이 위, 키트가 관리하는 관리 계정이 아래 ─────────────
    n("employee", T("직원", "Employee"), "", "flat-employee", 110, 175, 40)
    n("webcon_e", T("웹 콘솔", "Web console"), T("도입 신청·동의", "Requests · consent"), "flat-web", 250, 175, 40)
    n("claude", "Claude Code", "", "logo-claude", 110, 345, 46)
    n("codex", "Codex CLI", "", "logo-codex", 250, 345, 46)
    n("gemini", "Gemini CLI", "", "logo-gemini", 110, 440, 46, "test")
    n("opencode", "OpenCode", "", "logo-opencode", 250, 440, 46, "test")
    n("apparmor", "AppArmor", T("실행·파일 제한", "Exec & file limits"), "logo-apparmor", 85, 572, 40, "iso")
    n("nft", "nftables", T("통신 경로 강제", "Forces net path"), "logo-nftables", 175, 572, 40, "iso")
    n("epprog", T("엔드포인트\n프로그램", "Endpoint\nagent"), T("로그인·관리형 설정·상태", "Sign-in · settings · status"), "logo-ubuntu", 268, 572, 40, "os",
      icon2="logo-windows11")
    n("lrunner", T("로컬 실행기", "Local runner"), T("서명 확인·기동", "Verify · launch"), "flat-container", 95, 725, 38)
    n("ldocker", "Docker", T("컨테이너 격리", "Container isolation"), "logo-docker", 185, 725, 38)
    n("lmcp", T("공식 MCP", "Official MCPs"), T("filesystem 등", "filesystem…"), "logo-mcp", 272, 725, 38)
    n("admin", T("보안 관리자", "Security admin"), "", "flat-admin", 110, 965, 44)
    n("webcon_a", T("웹 콘솔", "Web console"), T("승인·현황", "Approve · monitor"), "flat-web", 250, 965, 44)
    n("tail", "Tailscale", T("WireGuard\n사설망", "WireGuard\nnetwork"), "logo-tailscale", 405, 650, 44)

    # ── 솔루션 ─────────────────────────────────────────────────────────
    n("proxy", "tinyproxy", T("모델 목적지 제한", "Model host allow-list"), "flat-proxy", 550, 348, 36)
    n("caddy", "Caddy", T("HTTPS 종단·분기", "TLS · routing"), "logo-caddy", 550, 640, 50)
    n("console", T("관리 콘솔", "Console"), T("신청·승인·현황", "Requests · status"), "flat-dashboard", 690, 320, 40)
    n("authlib", "Authlib", T("조직 로그인", "Org sign-in"), "logo-authlib", 810, 320, 40)
    for i, (k, lab, pur, ic) in enumerate([
            ("intake", T("도입 신청", "Intake"), T("소스 반입", "Source import"), "flat-upload"),
            ("syft", "Syft", T("SBOM 생성", "SBOM"), "logo-syft"),
            ("trivy", "Trivy", T("취약점 검사", "Vuln scan"), "logo-trivy"),
            ("semgrep", "Semgrep", T("코드 검사", "Code scan"), "logo-semgrep"),
            ("gitea", "Gitea", T("내부 저장소\n콘솔·키트로만", "Internal Git\nconsole & kit only"), "logo-gitea")]):
        n(k, lab, pur, ic, 940 + i * 87, 320, 38)
    n("runner", T("MCP 실행기", "MCP runner"), T("승인 서버 기동", "Runs approved"), "flat-container", 1398, 320, 38)
    n("docker", "Docker", T("컨테이너 엔진", "Containers"), "logo-docker", 1482, 320, 38)
    n("markitdown", "MarkItDown", T("문서 변환 MCP", "Doc conversion"), "logo-markitdown", 1566, 320, 38)
    n("egress", T("출구 프록시", "Egress proxy"), T("외부 통신 제한", "Egress allow-list"), "flat-proxy", 1660, 320, 38)
    n("core", T("요청 처리·중계", "Decide · relay"), "", "flat-gear", 760, 470, 54)
    n("fastapi", "FastAPI", T("웹 API", "Web API"), "logo-fastapi", 678, 640, 38)
    n("mcpsdk", "MCP SDK", T("MCP 프로토콜", "MCP protocol"), "logo-mcp", 762, 640, 38)
    n("otel", "OpenTelemetry", T("호출 추적", "Call tracing"), "logo-opentelemetry", 848, 640, 38)
    n("presidio", "Presidio", T("개인정보 탐지·가림", "PII detect · mask"), "logo-presidio", 985, 590, 44)
    n("gitleaks", "Gitleaks", T("비밀 정보 탐지", "Secret detection"), "logo-gitleaks", 1110, 590, 44)
    n("rules", T("Rego·PAC-15", "Rego · PAC-15"), T("정책 규칙", "Policy rules"), "flat-policy", 1240, 590, 40)
    n("opa", "OPA", T("허용·차단 판정", "Allow/deny"), "logo-opa", 1365, 590, 48)
    n("pg", "PostgreSQL", T("판정·승인 원장", "Decision ledger"), "logo-postgresql", 760, 865, 44)
    n("jaeger", "Jaeger", T("추적 조회", "Trace viewer"), "logo-jaeger", 995, 865, 40)
    n("sync", T("동기화 워커", "Sync worker"), T("승인·철회 전파", "Push approvals"), "flat-sync", 1190, 865, 40, "off")
    n("siemw", T("OCSF 워커", "OCSF worker"), T("감사 사건 전송", "Ship audit events"), "flat-queue", 1385, 865, 40, "off")

    # ── 기업 시스템(점선) · 외부 ─────────────────────────────────────────
    n("litellm", "LiteLLM", T("LLM·MCP 게이트웨이", "LLM/MCP gateway"), "logo-litellm", 1865, 150, 42, "int")
    n("keycloak", "Keycloak", T("조직 로그인(OIDC)", "Sign-in (OIDC)"), "logo-keycloak", 1865, 320, 40, "test")
    n("openbao", "OpenBao", T("서버별 자격 보관", "Per-server secrets"), "logo-openbao", 1865, 590, 40, "unset")
    n("vector", "Vector", T("수집", "Ship"), "logo-vector", 1800, 870, 36, "int")
    n("opensearch", "OpenSearch", T("저장·검색", "Store · search"), "logo-opensearch", 1925, 870, 36, "int")
    n("dashboards", "Dashboards", T("시각화", "Visualize"), "logo-opensearch", 1925, 985, 36, "int")
    n("anthropic", "Anthropic", "", "logo-anthropic", 2080, 150, 44)
    n("openai", "OpenAI", "", "logo-openai", 2195, 150, 44)
    n("github", "GitHub", "", "logo-github", 2080, 485, 42)
    n("context7", "Context7", "", "logo-context7", 2195, 485, 42)
    n("mslearn", "Microsoft Learn", "", "logo-microsoft", 2080, 615, 40)
    n("others", T("DeepWiki · HF\nCloudflare · AWS", "DeepWiki · HF\nCloudflare · AWS"), "", "flat-internet", 2195, 615, 40)

    # ── 상호작용(양방향은 both=True) ─────────────────────────────────────
    # 직원 PC ⇄ 솔루션: 사설망을 지나 진입(Caddy)으로
    e("mcp_pc", [(320, 470), (733, 470)], MCP, 4, T("MCP 요청 ⇄ 응답", "MCP ⇄"), (400, 454), src="hn", dst="core", both=True)
    e("model_pc", [(320, 345), (495, 345)], LLM, 3, T("모델 요청 ⇄ 응답", "Model ⇄"), (408, 329), src="hn", dst="prx", both=True)
    e("kit_pc", [(330, 572), (630, 572)], CTL, 2.5, T("정책 ⇄ 장치 보고 · 승인 소스", "Policy ⇄ report · approved source"), (418, 556), src="kit", dst="gw", both=True)
    e("loc_pc", [(320, 750), (630, 750)], MCP, 3, T("실행 작업 ⇄ 결과", "Job ⇄ result"), (400, 734), src="loc", dst="gw", both=True)
    e("web_e", [(330, 175), (448, 175), (448, 430)], CTL, 3, src="usr", both=False, arrow=False)
    e("web_a", [(350, 965), (448, 965), (448, 430)], CTL, 3, src="adm", arrow=False)
    e("web_in", [(448, 430), (617, 430), (617, 395), (630, 395)], CTL, 3, T("웹 콘솔", "Web console"), (471, 414), dst="con", both=True)
    s.dots.append((448, 430, CTL))
    # 진입(Caddy) → 관리 콘솔 / 호출 중계
    # 모델 프록시 ⇄ LLM 제공자(현재 직접), 연동 시 LiteLLM 경유
    e("model_out", [(550, 300), (550, 243), (2137, 243), (2137, 230)], LLM, 3,
      T("모델 요청 ⇄ 응답 · 허용 목적지만 (현재 제공자 직접)", "Model traffic · allow-listed hosts (direct to provider today)"),
      (1000, 243), src="prx", dst="prov", both=True)
    e("model_lgw", [(1865, 243), (1865, 230)], LLM, 2.5, "", None, dash="6 4", dst="lgw")
    e("lgw_prov", [(1975, 150), (2015, 150)], LLM, 2.5, "", None, dash="6 4", src="lgw", dst="prov", both=True)
    s.dots.append((1865, 243, LLM))
    # 하네스 기본 기능(웹 검색 등)·계정 커넥터(claude.ai 커넥터·ChatGPT 앱): 벤더 직접, 기본 승인 · 관리자 차단(D-298)
    e("vendor_direct", [(305, 290), (305, 64), (2240, 64), (2240, 80)], VENDOR, 2.5,
      T("기본 기능·계정 커넥터 ⇄ 벤더 · 게이트웨이 외부 · 기본 승인, 관리자 차단(관리형 설정)",
        "Built-in features · account connectors ⇄ vendor · outside the gateway · allowed by default, admin can block"),
      (1180, 64), dash="8 4", src="hn", dst="prov", both=True)
    # 조직 로그인
    e("oidc", [(810, 280), (810, 262), (1735, 262), (1735, 320), (1755, 320)], INT, 2.5, "OIDC", (1500, 262), dash="7 5",
      src="con", dst="idp", both=True)
    # 도입 → 검증 → 승인 → 격리 실행
    e("p_con", [(870, 320), (890, 320)], CTL, 2.5, src="con", dst="sup")
    for i, (a, b) in enumerate([("intake", "syft"), ("syft", "trivy"), ("trivy", "semgrep"), ("semgrep", "gitea")]):
        x0 = 940 + i * 87
        e(f"pipe{i}", [(x0 + 22, 320), (x0 + 87 - 22, 320)], MCP, 2, src=a, dst=b)
    e("p_run", [(1330, 320), (1350, 320)], MCP, 2.5, src="sup", dst="run")
    # 호출 중계 ⇄ 검사·판정 ⇄ MCP 서버(직원 토큰은 넘기지 않음)
    e("lane", [(787, 470), (2015, 470)], MCP, 4, T("MCP 요청 ⇄ 응답 · 직원 토큰 미전달", "MCP request ⇄ response · no employee token"),
      (1640, 454), src="core", dst="mcps", both=True)
    for k, x in (("presidio", 985), ("gitleaks", 1110), ("opa", 1365)):
        e(f"chk_{k}", [(x, 470), (x, 590 - s.nodes[k]["size"] / 2 - 3)], CTL, 2.5, src=None, dst=k, both=True)
        s.dots.append((x, 470, CTL))
    e("rule", [(1262, 590), (1339, 590)], C_POL, 2.5, src="rules", dst="opa")
    e("lane_run", [(1450, 470), (1450, 420)], MCP, 3, "", None, dst="run", both=True)
    s.dots.append((1450, 470, MCP))
    # 원장·추적·전달
    e("db", [(760, 770), (760, 800)], CTL, 2.5, T("판정 기록 ⇄ 조회", "Record ⇄ read"), (830, 785), src="gw", dst="led", both=True)
    e("con_db", [(870, 395), (900, 395), (900, 875), (890, 875)], CTL, 2.5, T("가입·신청 저장", "Requests"), (900, 742),
      src="con", dst="led", both=True)
    e("trace", [(867, 640), (882, 640), (882, 785), (995, 785), (995, 800)], OBS, 2.5, "OTLP", (950, 785), src="otel", dst="trc")
    e("outbox", [(760, 950), (760, 985), (1385, 985), (1385, 950)], OBS, 2.5, "siem_outbox", (1100, 985), dash="7 5",
      src="led", dst="sgw", both=True)
    e("ocsf", [(1470, 870), (1755, 870)], OBS, 3, "OCSF", (1612, 854), src="sgw", dst="siem")
    e("sync", [(1190, 800), (1190, 788), (1746, 788), (1746, 165), (1755, 165)], OBS, 2.5,
      T("승인·철회 반영 ⇄ 재조회", "Push approvals ⇄ re-read"), (1460, 788), dash="7 5", src="lsy", dst="lgw", both=True)
    e("sv", [(1822, 870), (1903, 870)], OBS, 2, src="vector", dst="opensearch")
    e("so", [(1925, 935), (1925, 963)], OBS, 2, src="opensearch", dst="dashboards")
    return s


# ── 역할 설명(빨간 층): 읽는 순서 = 배치 순서 ─────────────────────────────
def roles(lang):
    T = (lambda ko, en: ko) if lang == "ko" else (lambda ko, en: en)
    return [
        ("A", T("직원 PC", "Employee PC"), (14, 74, 342, 802),
         T("키트는 MINT 계정으로 로그인해 설치되고(간편 모드: 직원 계정·하네스 그대로), 관리형 설정으로 하네스가 승인 MCP만 게이트웨이로 쓰게 한다. mint 명령·트레이로 상태를 보고, 승인 MCP 소스도 키트로 받는다. 격리 모드는 AppArmor·nftables를 더한다. 승인된 로컬 MCP는 서명 확인 뒤 Docker 격리로 띄운다.",
           "The kit installs after a MINT sign-in (simple mode keeps the employee's account and harness) and uses managed settings so harnesses reach approved MCPs only through the gateway. Status shows in `mint` and the tray; approved MCP sources download through the kit. Isolated mode adds AppArmor and nftables. Approved local MCPs start in Docker isolation after a signature check.")),
        ("B", T("관리자 PC", "Admin PC"), (14, 884, 342, 172),
         T("보안 관리자가 웹 콘솔로 도입 승인·도구 분류·계약 검토·장치 활성화·종료 판정을 하고, 하네스 기본 기능·계정 커넥터를 항목별로 차단한다.",
           "Security admins approve intakes, set tool classes, review contracts, activate devices, decide terminations and block harness built-in features or account connectors item by item.")),
        ("C", T("사설망", "Private network"), (364, 74, 102, 982),
         T("Tailscale(WireGuard)로 PC와 솔루션을 잇는다. 하네스·키트·브라우저의 HTTPS가 이 망 안에서만 오간다.",
           "Tailscale (WireGuard) links PCs and the solution; harness, kit and browser HTTPS stays inside it.")),
        ("D", T("진입", "Ingress"), (489, 294, 122, 742),
         T("Caddy가 HTTPS를 끝내고 콘솔·호출 중계·장치 API로 나눈다. 모델 호출은 별도 프록시가 허용된 목적지로만 보낸다.",
           "Caddy terminates HTTPS and routes to the console, call relay and device API. Model calls go through a proxy that only reaches allow-listed hosts.")),
        ("E", T("관리 콘솔·인증", "Console · sign-in"), (624, 274, 252, 152),
         T("가입·도입 신청·승인·동의를 처리한다. Authlib로 조직 로그인(OIDC)을 검증한다.",
           "Handles sign-up, intake, approval and consent; Authlib verifies org sign-in (OIDC).")),
        ("F", T("공급망 검증 · 격리 실행", "Supply chain · runtime"), (884, 274, 842, 152),
         T("신청한 소스를 반입해 Syft·Trivy·Semgrep으로 검사하고 Gitea에 보관한다(직원은 콘솔·키트로만 받는다). 승인된 서버만 솔루션의 격리 실행으로 띄우고 출구 프록시로 외부 통신을 제한한다.",
           "Imported sources are scanned by Syft, Trivy and Semgrep and stored in Gitea. Only approved servers run in the solution's isolated runtime behind an egress proxy.")),
        ("G", T("호출 중계", "Call relay"), (624, 429, 272, 347),
         T("FastAPI·MCP SDK로 만든 게이트웨이가 모든 도구 호출을 받아 판정을 받은 뒤 MCP 서버로 중계하고 응답을 돌려준다. 직원 토큰은 넘기지 않는다.",
           "The FastAPI/MCP SDK gateway receives every tool call, gets a decision, relays to the MCP server and returns the response. Employee tokens are never forwarded.")),
        ("H", T("입력 검사 · 정책 판정", "Checks · policy"), (904, 429, 517, 297),
         T("Presidio가 개인정보를, Gitleaks가 비밀 정보를 찾고, OPA가 Rego·PAC-15 규칙으로 허용·차단을 판정한다. 검사 도구가 멈추면 차단한다.",
           "Presidio finds personal data, Gitleaks finds secrets, and OPA decides allow/deny with Rego and PAC-15 rules. If a checker fails, the call is blocked.")),
        ("I", T("원장 · 추적 · 전달", "Ledger · tracing · export"), (624, 794, 852, 162),
         T("모든 판정·승인을 PostgreSQL 원장에 남긴다. OpenTelemetry 추적은 Jaeger로, 감사 사건은 OCSF로 SIEM에, 승인·철회는 LiteLLM으로 보낸다(전달·동기화는 기본 꺼짐).",
           "Every decision and approval lands in the PostgreSQL ledger. Traces go to Jaeger, audit events to the SIEM as OCSF, and approvals to LiteLLM (export and sync are off by default).")),
        ("J", T("기업 시스템", "Enterprise systems"), (1749, 74, 232, 982),
         T("이미 쓰는 LLM 게이트웨이·IdP·비밀 저장소·SIEM과 이어진다. 점선은 고객 환경에 따라 켜는 연동이다.",
           "Connects to the LLM gateway, IdP, secrets store and SIEM the company already runs. Dashed boxes are integrations enabled per customer.")),
        ("K", T("외부", "External"), (2009, 74, 257, 682),
         T("LLM 제공자와 원격 MCP 서버. 승인 MCP 호출은 게이트웨이를 거쳐서만 나간다. 하네스 기본 기능·계정 커넥터는 벤더로 바로 가고 관리형 설정으로 막는다.",
           "LLM providers and remote MCP servers. Tool calls leave only through the gateway.")),
    ]


def flow(lang):
    T = (lambda ko, en: ko) if lang == "ko" else (lambda ko, en: en)
    return [(T("하네스 호출", "Harness call"), "Claude Code · Codex CLI", (345, 492)),
            (T("HTTPS 진입", "HTTPS ingress"), "Tailscale → Caddy", (588, 612)),
            (T("입력 검사", "Input checks"), "Presidio · Gitleaks", (1048, 520)),
            (T("정책 판정", "Policy decision"), "OPA · Rego/PAC-15", (1365, 520)),
            (T("MCP 서버 전달", "Relay to MCP server"), T("직원 토큰 미전달", "No employee token"), (1995, 495)),
            (T("응답 검사·기록", "Response check · record"), T("검사 · PostgreSQL 원장", "Checks · PostgreSQL ledger"), (800, 820))]


def svg(s, annotate=False):
    lang = s.lang
    T = (lambda ko, en: ko) if lang == "ko" else (lambda ko, en: en)
    h = H + (PANEL_H if annotate else 0)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}" viewBox="0 0 {W} {h}" '
         f'font-family="{FONT}, Malgun Gothic, sans-serif">', '<rect width="100%" height="100%" fill="#FFFFFF"/>', "<defs>"]
    for c in sorted({ed["color"] for ed in s.edges}):
        k = c.lstrip("#")
        o.append(f'<marker id="m{k}" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="6.5" markerHeight="6.5" '
                 f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>')
    o.append(f'<marker id="mred" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="6" markerHeight="6" orient="auto">'
             f'<path d="M0,0 L10,5 L0,10 z" fill="{RED}"/></marker></defs>')
    title = T("MINT 구성도", "MINT Architecture")
    sub = T("MCP 거버넌스 게이트웨이 · 직원 PC · 솔루션 · 기업 시스템", "MCP governance gateway · employee PC · solution · enterprise systems")
    o.append(f'<text x="24" y="52" font-size="30" font-weight="800" fill="{TEXT}">{esc(title)}'
             f'<tspan font-size="15" font-weight="500" fill="{MUTED}" dx="14">{esc(sub)}</tspan></text>')
    o.append(f'<text x="{W - 24}" y="46" text-anchor="end" font-size="13" fill="{MUTED}">{datetime.now():%Y-%m-%d}</text>')
    for zz in sorted(s.zones, key=lambda q: q["sub"]):
        col = zz["color"]
        fa, sa = (0.07, 0.45) if zz["sub"] else (0.12, 0.6)
        da = ' stroke-dasharray="9 6"' if zz["dashed"] else ""
        o.append(f'<rect x="{zz["x"]}" y="{zz["y"]}" width="{zz["w"]}" height="{zz["h"]}" rx="14" fill="{rgba(col, fa)}" '
                 f'stroke="{rgba(col, sa)}" stroke-width="2"{da}/>')
        if zz["sub"]:
            o.append(f'<text x="{zz["x"] + 12}" y="{zz["y"] + 21}" font-size="12.5" font-weight="700" fill="{col}">{esc(zz["label"])}</text>')
            continue
        lab, size = zz["label"], 17
        if zz["lab_at"] == "l":
            x0 = zz["x"] + 16
            if zz["icon"] and icon(zz["icon"]):
                mime, data = icon(zz["icon"])
                o.append(f'<image x="{x0}" y="{zz["y"] + 12}" width="26" height="26" href="data:{mime};base64,{data}"/>')
                x0 += 34
            o.append(f'<text x="{x0}" y="{zz["y"] + 32}" font-size="{size}" font-weight="800" fill="{col}">{esc(lab)}</text>')
            continue
        cx_ = zz["x"] + zz["w"] / 2
        note = (f'<tspan font-size="12" font-weight="500" fill="{MUTED}" dx="8">{esc(zz["note"])}</tspan>' if zz["note"] else "")
        ix = 17 if zz["icon"] and icon(zz["icon"]) else 0
        o.append(f'<text x="{cx_ + ix / 2:.1f}" y="{zz["y"] + 30}" text-anchor="middle" font-size="{size}" font-weight="800" fill="{col}">{esc(lab)}{note}</text>')
        if ix:
            mime, data = icon(zz["icon"])
            wlab = tw(lab, size) + (tw(zz["note"], 12) + 8 if zz["note"] else 0)
            o.append(f'<image x="{cx_ - wlab / 2 - 15:.1f}" y="{zz["y"] + 11}" width="26" height="26" href="data:{mime};base64,{data}"/>')
    for ed in s.edges:
        d = " ".join(f"{x:.1f},{y:.1f}" for x, y in ed["pts"])
        da = f' stroke-dasharray="{ed["dash"]}"' if ed["dash"] else ""
        mk = f' marker-end="url(#m{ed["color"].lstrip("#")})"' if ed["arrow"] else ""
        if ed["both"]:
            mk += f' marker-start="url(#m{ed["color"].lstrip("#")})"'
        o.append(f'<polyline points="{d}" fill="none" stroke="#FFFFFF" stroke-opacity="0.94" stroke-width="{ed["width"] + 4}" stroke-linejoin="round"/>')
        o.append(f'<polyline points="{d}" fill="none" stroke="{ed["color"]}" stroke-width="{ed["width"]}"{da}{mk} stroke-linejoin="round"/>')
    for x, y, c in s.dots:
        o.append(f'<circle cx="{x}" cy="{y}" r="4.5" fill="{c}"/>')
    for ed in s.edges:
        if ed["label"]:
            x, y = ed["lab"]
            w = tw(ed["label"], 11.5) + 12
            o.append(f'<rect x="{x - w / 2:.1f}" y="{y - 11}" width="{w:.1f}" height="19" rx="9" fill="#FFFFFF" fill-opacity="0.95"/>')
            o.append(f'<text x="{x}" y="{y + 3}" text-anchor="middle" font-size="11.5" font-weight="700" fill="{ed["color"]}">{esc(ed["label"])}</text>')
    for nd in s.nodes.values():
        sz = nd["size"]
        pairs = [(nd["icon"], nd["x"])] if not nd.get("icon2") else [(nd["icon"], nd["x"] - sz * 0.28), (nd["icon2"], nd["x"] + sz * 0.28)]
        for key, cx_ in pairs:
            ic = icon(key)
            if ic:
                o.append(f'<image x="{cx_ - sz / 2:.1f}" y="{nd["y"] - sz / 2:.1f}" width="{sz}" height="{sz}" '
                         f'href="data:{ic[0]};base64,{ic[1]}" preserveAspectRatio="xMidYMid meet"/>')
        y = nd["y"] + sz / 2 + 15
        for ln in nd["label"].split("\n"):
            o.append(f'<text x="{nd["x"]}" y="{y}" text-anchor="middle" font-size="12.5" font-weight="700" fill="{TEXT}">{esc(ln)}</text>')
            y += 14
        for ln in (s.purpose.get(nd["id"]) or "").split("\n"):
            if ln:
                o.append(f'<text x="{nd["x"]}" y="{y}" text-anchor="middle" font-size="10.5" fill="{MUTED}">{esc(ln)}</text>')
                y += 13
        if nd["status"] in STATUS:
            ko, en, col = STATUS[nd["status"]]
            lab = ko if lang == "ko" else en
            pw = tw(lab, 10) + 12
            o.append(f'<rect x="{nd["x"] - pw / 2:.1f}" y="{y - 9}" width="{pw:.1f}" height="14" rx="7" fill="{rgba(col, 0.13)}" stroke="{col}" stroke-width="1"/>'
                     f'<text x="{nd["x"]}" y="{y + 1.5}" text-anchor="middle" font-size="10" font-weight="700" fill="{col}">{esc(lab)}</text>')
    # 범례
    ly = H - 122
    o.append(f'<rect x="20" y="{ly}" width="1710" height="104" rx="14" fill="#FFFFFF" stroke="#C5D3E6" stroke-width="1.5"/>')
    items = [(T("MCP 호출", "MCP calls"), MCP, None, 4), (T("모델 호출", "Model calls"), LLM, None, 3),
             (T("관리·판정·검사", "Admin · decisions · checks"), CTL, None, 3), (T("기업 연동", "Enterprise link"), INT, "7 5", 2.5),
             (T("감사·추적 전달", "Audit · trace export"), OBS, None, 3),
             (T("게이트웨이 외부(벤더 직접)", "Outside the gateway"), VENDOR, "8 4", 2.5)]
    o.append(f'<text x="40" y="{ly + 30}" font-size="13" font-weight="800" fill="{TEXT}">{T("선", "Lines")}</text>')
    x = 100
    for lab, c, da, w in items:
        d = f' stroke-dasharray="{da}"' if da else ""
        o.append(f'<line x1="{x}" y1="{ly + 26}" x2="{x + 34}" y2="{ly + 26}" stroke="{c}" stroke-width="{w}"{d}/>'
                 f'<text x="{x + 42}" y="{ly + 31}" font-size="12.5" fill="{TEXT}">{esc(lab)}</text>')
        x += 60 + tw(lab, 12.5) + 30
    o.append(f'<line x1="{x}" y1="{ly + 26}" x2="{x + 40}" y2="{ly + 26}" stroke="{TEXT}" stroke-width="2.5" '
             f'marker-start="url(#m{CTL.lstrip("#")})" marker-end="url(#m{CTL.lstrip("#")})"/>'
             f'<text x="{x + 50}" y="{ly + 31}" font-size="12.5" fill="{TEXT}">{T("양방향 = 요청과 응답이 오감", "Two-way = request and response")}</text>')
    o.append(f'<text x="40" y="{ly + 66}" font-size="13" font-weight="800" fill="{TEXT}">{T("상태", "Status")}</text>')
    o.append(f'<text x="100" y="{ly + 71}" font-size="12.5" fill="{TEXT}">{T("표시 없음 = 사용 중", "No tag = in use")}</text>')
    x = 100 + tw(T("표시 없음 = 사용 중", "No tag = in use"), 12.5) + 24
    for key in ("test", "int", "os", "off", "unset"):
        ko, en, col = STATUS[key]
        lab = ko if lang == "ko" else en
        pw = tw(lab, 10) + 12
        o.append(f'<rect x="{x}" y="{ly + 57}" width="{pw:.1f}" height="15" rx="7.5" fill="{rgba(col, 0.13)}" stroke="{col}"/>'
                 f'<text x="{x + pw / 2}" y="{ly + 68}" text-anchor="middle" font-size="10" font-weight="700" fill="{col}">{esc(lab)}</text>')
        x += pw + 16
    o.append(f'<rect x="{x + 10}" y="{ly + 56}" width="34" height="18" rx="6" fill="{rgba(C_ENT, 0.08)}" stroke="{rgba(C_ENT, 0.6)}" stroke-width="2" stroke-dasharray="6 4"/>'
             f'<text x="{x + 52}" y="{ly + 70}" font-size="12.5" fill="{TEXT}">{T("점선 상자 = 기업 시스템(고객 환경에 따라 연동)", "Dashed box = enterprise system (integrated per customer)")}</text>')
    o.append(f'<text x="40" y="{ly + 94}" font-size="11.5" fill="{MUTED}">'
             f'{T("이름 아래 회색 글자 = 그 도구가 맡는 일 · 선 교차는 연결 아님(접점은 원 표시)", "Grey text under a name = what the tool does · crossings are not connections (junctions are dots)")}</text>')
    cr = cx.credits()
    if cr:
        o.append(f'<text x="{W - 20}" y="{H - 8}" text-anchor="end" font-size="7" fill="#B8BFC8">{esc(cr if lang == "ko" else cr.replace("아이콘", "Icons").replace("각 프로젝트", "each project"))}</text>')

    if annotate:
        rb = roles(lang)
        for k, t, (x, y, w, hh), _ in rb:
            o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{hh}" rx="12" fill="none" stroke="{RED}" stroke-width="3" stroke-dasharray="12 7"/>')
            o.append(f'<rect x="{x - 12}" y="{y - 12}" width="24" height="24" rx="6" fill="{RED}" stroke="#FFFFFF" stroke-width="1.5"/>'
                     f'<text x="{x}" y="{y + 5.5}" text-anchor="middle" font-size="15" font-weight="800" fill="#FFFFFF">{k}</text>')
        for i, (_, _, (x, y)) in enumerate(flow(lang)):
            o.append(f'<circle cx="{x}" cy="{y}" r="13" fill="{RED}" stroke="#FFFFFF" stroke-width="2"/>'
                     f'<text x="{x}" y="{y + 5.5}" text-anchor="middle" font-size="15" font-weight="800" fill="#FFFFFF">{i + 1}</text>')
        py = H + 10
        o.append(f'<text x="24" y="{py + 22}" font-size="20" font-weight="800" fill="{RED}">{T("영역별 역할", "What each area does")}</text>')
        o.append(f'<text x="{24 + tw(T("영역별 역할", "What each area does"), 20) + 14}" y="{py + 22}" font-size="12.5" fill="{MUTED}">'
                 f'{T("영문자 = 왼쪽 위부터 읽는 순서, 빨간 원 번호 = 도구 호출이 지나는 순서", "Letters follow reading order from top-left; red numbers follow a tool call")}</text>')
        cols, gap = 4, 14
        cw = (W - 40 - gap * (cols - 1)) / cols
        ch = 128
        size = 13
        for i, (k, t, _, d) in enumerate(rb):
            x0 = 20 + (i % cols) * (cw + gap)
            y0 = py + 40 + (i // cols) * (ch + gap)
            o.append(f'<rect x="{x0:.1f}" y="{y0}" width="{cw:.1f}" height="{ch}" rx="12" fill="#FFF7F6" stroke="{RED}" stroke-width="1.6"/>')
            o.append(f'<rect x="{x0 + 12:.1f}" y="{y0 + 12}" width="26" height="26" rx="6" fill="{RED}"/>'
                     f'<text x="{x0 + 25:.1f}" y="{y0 + 31}" text-anchor="middle" font-size="16" font-weight="800" fill="#FFFFFF">{k}</text>')
            o.append(f'<text x="{x0 + 48:.1f}" y="{y0 + 31}" font-size="15" font-weight="800" fill="{TEXT}">{esc(t)}</text>')
            for j, ln in enumerate(wrap(d, cw - 30, size)[:4]):
                o.append(f'<text x="{x0 + 14:.1f}" y="{y0 + 58 + j * 19}" font-size="{size}" fill="{TEXT}">{esc(ln)}</text>')
        fy = py + 40 + ((len(rb) + cols - 1) // cols) * (ch + gap) + 10
        o.append(f'<text x="24" y="{fy + 4}" font-size="15" font-weight="800" fill="{RED}">{T("도구 호출 흐름", "Tool call flow")}</text>')
        fl = flow(lang)
        cw2 = 300
        g2 = (W - 40 - len(fl) * cw2) / (len(fl) - 1)
        for i, (t1, t2, _) in enumerate(fl):
            x0 = 20 + i * (cw2 + g2)
            y0 = fy + 16
            o.append(f'<rect x="{x0:.1f}" y="{y0}" width="{cw2}" height="70" rx="12" fill="#FFF7F6" stroke="{RED}" stroke-width="1.6"/>')
            o.append(f'<circle cx="{x0 + 26:.1f}" cy="{y0 + 35}" r="13" fill="{RED}"/>'
                     f'<text x="{x0 + 26:.1f}" y="{y0 + 40.5}" text-anchor="middle" font-size="15" font-weight="800" fill="#FFFFFF">{i + 1}</text>')
            o.append(f'<text x="{x0 + 48:.1f}" y="{y0 + 31}" font-size="14" font-weight="800" fill="{TEXT}">{esc(t1)}</text>')
            o.append(f'<text x="{x0 + 48:.1f}" y="{y0 + 51}" font-size="12" fill="{MUTED}">{esc(t2)}</text>')
            if i < len(fl) - 1:
                ax = x0 + cw2
                o.append(f'<line x1="{ax + 3:.1f}" y1="{y0 + 35}" x2="{ax + g2 - 3:.1f}" y2="{y0 + 35}" stroke="{RED}" stroke-width="3" marker-end="url(#mred)"/>')
    o.append("</svg>")
    return "\n".join(o)


def drawio(s):
    """10-21판 변환기로 편집용 draw.io를 만든다. 목적 문구는 이름 아래 작은 회색 글자로 붙인다."""
    keep = {k: dict(v) for k, v in s.nodes.items()}
    cx.STATUS = {k: (v[0] if s.lang == "ko" else v[1], v[2]) for k, v in STATUS.items()}
    for k, nd in s.nodes.items():
        p = s.purpose.get(k)
        if p:
            nd["label"] = nd["label"] + "\n" + p
    page = cx.drawio_page(s, "p1")
    s.nodes = keep
    if s.lang != "ko":
        page = page.replace('value="MINT 구성도"', 'value="MINT Architecture"')
    return '<mxfile host="app.diagrams.net" agent="MINT build_architecture.py (10-28)" version="24.0.0">' + page + "</mxfile>"


def main():
    stamp = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%m%d%H%M")
    OUT.mkdir(exist_ok=True)
    cx.W, cx.H = W, H
    names = {("ko", False): "MINT_구성도", ("ko", True): "MINT_구성도_역할설명",
             ("en", False): "MINT_architecture_en", ("en", True): "MINT_architecture_roles_en"}
    for lang in ("ko", "en"):
        s = build(lang)
        for ann in (False, True):
            p = OUT / f"{names[(lang, ann)]}_{stamp}.svg"
            p.write_text(svg(s, ann), encoding="utf-8")
            to_png(p, p.with_suffix(".png"), W, H + (PANEL_H if ann else 0))
        (OUT / f"{names[(lang, False)]}_{stamp}.drawio").write_text(drawio(s), encoding="utf-8")
    print("stamp", stamp)


if __name__ == "__main__":
    main()
