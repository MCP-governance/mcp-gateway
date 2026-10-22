"""Render the dated comparison from explicit, independently scoped evidence axes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
WIKI = REPO / "research/llm-wiki"
BASELINE = "e30be961a9a00d7982dd8565e4412c7289e85f4d"
UNKNOWN = "미확인"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.run(["git", "-C", str(REPO), *args], check=True,
                          capture_output=True, encoding="utf-8").stdout.strip()


def build():
    sources = {}

    def source(key, path, kind, needle=None, span=1, **extra):
        raw = (REPO / path).read_bytes()
        content = raw.decode("utf-8-sig")
        record = dict(path=path, kind=kind, sha256=digest(raw),
                      normalized_sha256=digest(raw.replace(b"\r\n", b"\n")), **extra)
        if needle is not None:
            lines = content.splitlines()
            matches = [i for i, line in enumerate(lines) if needle in line]
            if len(matches) != 1:
                raise ValueError(f"Ambiguous evidence anchor: {key}: {matches}")
            record.update(line=matches[0] + 1, end_line=min(matches[0] + span, len(lines)),
                          anchor=lines[matches[0]])
            if kind == "mint-decision":
                following = next((i for i in range(matches[0] + 1, len(lines))
                                  if lines[i].startswith("## ")), len(lines))
                record["end_line"] = following
        if kind.startswith("mint-"):
            blob = subprocess.run(["git", "-C", str(REPO), "show", f"{BASELINE}:{path}"],
                                  check=True, capture_output=True).stdout
            if digest(blob.replace(b"\r\n", b"\n")) != record["normalized_sha256"]:
                raise ValueError(f"MINT evidence differs from baseline: {path}")
        sources[key] = record
        return key

    def local(key, path, kind="mint-code", needle=None, span=1):
        return source(key, path, kind, needle, span, commit=BASELINE)

    def wiki(key, path, needle=None):
        return source(key, "research/llm-wiki/" + path, "prior-analysis", needle)

    def primary(key, manifest, entry_id):
        path = "research/llm-wiki/analysis/" + manifest
        entries = json.loads((REPO / path).read_text(encoding="utf-8"))["sources"]
        entry = next(s for s in entries if s["id"] == entry_id)
        source(key, path, "primary-snapshot-metadata", source_id=entry_id,
               original=entry, reused=True,
               limitation="기존 manifest의 확보 시점·열람 범위를 이어받는다. 이번 브라우저 조회 바이트의 해시가 아니다.")

    inputs = [
        ("cloud", "cloud-control-benchmark-1023"), ("references", "references-1023"),
        ("regulation", "regulation-gap-1023"), ("refs", "refs-update-1023"),
        ("cases", "mcp-enterprise-cases-1023"), ("industry", "industry-trends-1023"),
        ("intervention", "litellm-intervention-1023"),
    ]
    for key, folder in inputs:
        wiki(key, f"analysis/{folder}/README.md")
    wiki("L-analysis", "analysis/oss-deep/litellm-mcp-path.md")
    wiki("L-update", "analysis/litellm-mint-opportunities-20261022.md")
    wiki("C-analysis", "analysis/oss-deep/contextforge-hooks.md")
    wiki("C-card", "solutions/ibm-contextforge.md")
    wiki("T-analysis", "analysis/oss-deep/toolhive-runtime.md")
    wiki("K-card", "solutions/kong-ai-gateway.md")
    wiki("F-card", "solutions/crowdstrike-falcon-guardian.md")
    wiki("releases", "solutions/oss-gateway-scanner-releases-1023.md")
    for suffix, entry in [("pin", "W1"), ("output", "W2"), ("intake", "W3"),
                          ("auth", "W4"), ("end", "W7")]:
        primary("L-" + suffix, "litellm-mint-opportunities-20261022.sources.json", entry)
    for key, entry in [("A-policy", "D3"), ("A-modes", "D12"), ("A-gateway", "D2"),
                       ("CF-portal", "G3"), ("K-acl", "H1"), ("audit-benchmark", "A1")]:
        primary(key, "cloud-control-benchmark-1023/cloud-control-benchmark-1023.sources.json", entry)
    primary("CF-case", "mcp-enterprise-cases-1023/mcp-enterprise-cases-1023.sources.json", "C03")
    primary("C-case", "mcp-enterprise-cases-1023/mcp-enterprise-cases-1023.sources.json", "C18")
    primary("D-governance", "industry-trends-1023/industry-trends-1023.sources.json", "T12")
    primary("F-announcement", "references-1023/sources.json", "C1")
    primary("F-blog", "references-1023/sources.json", "C2")

    code = "full_stack_lab/gateway/app/"
    local("M-review", code + "review.py", needle="async def intake_gate", span=55)
    local("M-intake-worker", "full_stack_lab/supply_chain/intake_worker.py", needle="def validate(", span=114)
    local("M-approve", code + "core.py", needle="async def approve_contract", span=83)
    local("M-contract", code + "core.py", needle="async def _call_upstream", span=201)
    local("M-output-pin", code + "output_contract.py", needle="def matches(", span=8)
    local("M-local-pin", "endpoint-agent/local-runner.py", needle="# Each fresh container", span=12)
    local("M-call", code + "core.py", needle="async def execute_call", span=375)
    local("M-policy", code + "core.py", needle="async def _policy(", span=12)
    local("M-result", code + "core.py", needle="def _guarded_result", span=46)
    local("M-mask", code + "privacy.py", needle="async def mask_payload", span=59)
    local("M-consent", code + "consent.py", needle="async def missing", span=123)
    local("M-linux", "endpoint-agent/enforce-linux.py", needle="def nft_rules", span=25)
    local("M-isolation", "endpoint-agent/local-runner.py", needle="def container_command", span=37)
    local("M-audit", code + "core.py", needle="async def _record_decision", span=92)
    local("M-audit-preview", code + "core.py", needle="def _audit_payload", span=15)
    local("M-enforcement", code + "core.py", needle="async def set_enforcement_mode", span=9)
    local("M-append", code + "agent_tables.sql", needle="CREATE OR REPLACE FUNCTION reject_decision_mutation", span=9)
    local("M-end", code + "decommission.py", needle="async def assess(", span=49)
    local("M-end-kinds", code + "decommission.py", needle="EVIDENCE_KINDS: dict", span=46)
    local("M-addon", code + "addon.py", needle="async def decide(", span=37)
    local("M-addon-generator", "addons/litellm/gen_mcp_servers.py", needle="def render(", span=9)
    local("M-addon-hook", "addons/litellm/mint_guardrail.py", needle="async def async_pre_call_hook", span=44)
    for number in [62, 183, 191, 192, 201, 202, 203, 205]:
        local(f"D-{number}", "docs/ai/DECISIONS.md", "mint-decision", f"## D-{number} ")
    local("M-real", "research/llm-wiki/status/reports/2026-10-23-real-usage-local-mcp.md",
          "mint-usage-report", "시나리오가 PJ1", span=49)

    rows = [
        ("intake", "도입 심사", "신규 MCP의 출처·검사·범위를 사람이 검토해 승인한다. 단순 등록/허용 목록은 부분 대응."),
        ("contract", "계약 고정", "승인한 도구 정의를 고정하고 변경을 처리한다. pin 노출·live 대조·출력 스키마를 구분."),
        ("precall", "호출 전 판정", "실제 도구 전송 전에 인증된 주체·권한·인자·정책을 평가한다. 목록 숨김만으로 충족하지 않음."),
        ("output", "출력 통제", "도구 실행 후 결과를 검사·마스킹·보류한다. 이미 발생한 부수효과 취소와 별개."),
        ("consent", "동의", "직원의 데이터 이용 조건 동의·철회와 호출 적용. OAuth 연결 동의·관리자 도입 승인과 구별."),
        ("endpoint", "엔드포인트 강제", "관리 PC의 승인 경로 밖 MCP·프로세스·망 접근을 OS/센서에서 제한한다. 정상 경유만으로 입증 안 됨."),
        ("isolation", "로컬 MCP 격리", "로컬 MCP 서버 프로세스의 파일·망·자격·자원 경계를 실행기에 적용한다. 에이전트 자체 격리와 구별."),
        ("audit", "감사 원장", "호출·조치의 주체/시점/판정/효과를 보존한다. 일반 로그와 append-only·체인·외부 앵커를 구별."),
        ("termination", "종료 판정", "중지 조치와 별개로 회수 대상·권한·전파·상태 증거에 따라 종료/부분 종료/판단 불가를 결정한다."),
        ("ai", "AI 게이트웨이 연동", "LLM 경로와 MCP 경로를 구분해 연결·판정·결과를 연계한다. 자사 AI 프록시 기능은 부분 대응."),
    ]
    products = [
        ("MINT", "MINT", "자체 구현", BASELINE, "이 저장소; 외부 제품 라이선스 판단 대상 아님", "M-real"),
        ("L", "LiteLLM", "OSS·상용 혼재", "코드 1.102.0 f8e456d105af921213267d0ef801ca08b8fdbc0b; 문서 10-22~23/종료 1.103.0 별도", "분석 코드 MIT; enterprise 별도 상용", "L-analysis"),
        ("C", "IBM ContextForge", "OSS", "5735c9db7f8f50cd5a55eb7fefe83ecde00b5324; 최신 릴리스 주장을 이 코드에 합치지 않음", "Apache-2.0; CPEX 별도 의존성", "C-card"),
        ("T", "ToolHive", "OSS", "v0.54.0 1ce13bbbbbe1ed9a3f40fea03ed1a42533f04cea; 10-14 릴리스 관측", "Apache-2.0; 외부 권한 구현 일부 미독", "T-analysis"),
        ("D", "Docker AI Governance", "상용 제품 설명", "2026-05-12 공식 발표의 4개 통제 표면", "상용 조건 미확인; OSS Docker MCP Gateway(MIT)와 별도", "D-governance"),
        ("A", "AWS AgentCore Policy·Gateway", "상용 관리형", "2026-10-23 확보 문서; 서비스 판본 번호 미표시", "상용; 비용·계정 조건 미확인", "A-policy"),
        ("CF", "Cloudflare MCP 포털·Gateway", "상용 관리형", "2026-10-23 확보 문서·자사 사례; 선택 Gateway 경유 포함", "상용; 플랜 조건 미확인", "CF-portal"),
        ("K", "Kong AI MCP Proxy", "상용 플러그인", "기존 3.x 문서; 도구별 ACL 3.13 이후; Konnect 레지스트리 기술 미리보기", "AI Gateway Enterprise; OSS Kong 전체 기능으로 확대 안 함", "K-card"),
        ("F", "CrowdStrike Falcon Guardian", "상용 엔드포인트", "2026-09-01 발표; 10-23 읽은 공식 글에서 AI Gateway pre-beta", "상용·코드 비공개; OS 지원 자료 불일치", "F-card"),
    ]
    cells = {(p[0], r[0]): dict(id=f"{p[0]}-{r[0]}", product=p[0], control=r[0],
             implementation=dict(status=UNKNOWN, evidence=[]), deployment=dict(status=UNKNOWN, evidence=[]),
             measurement=dict(status=UNKNOWN, evidence=[]), scope="근거를 확보하지 못함",
             limitation="검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.")
             for p in products for r in rows}

    def cell(p, r, status, refs, scope, limitation, deployed=False, measured=False):
        c = cells[p, r]
        c.update(scope=scope, limitation=limitation)
        c["implementation"] = dict(status=status, evidence=refs)
        if deployed:
            c["deployment"] = dict(status="부분·보고", evidence=["M-real"],
                                    scope="10-23 보고의 로컬 3종 경로; 현재 배포 전체를 재조회한 결과 아님")
        if measured:
            c["measurement"] = dict(status="부분·보고", evidence=["M-real"],
                                     scope=measured, observer="기존 리더 보고 재사용; 이번 재실행·원시 로그 재수집 없음")

    cell("MINT", "intake", "코드", ["M-review", "M-intake-worker", "M-approve", "D-192"],
         "검사 결과·출처·판본·위험 수용 gate와 사람의 계약 승인. 로컬 이미지는 digest 고정·서명.",
         "로컬 3종 도입·재승인 정상 경로만 보고됨. 4종 스캐너 실패·공급망/원격 SaaS 내부 검증 실측은 미확인.",
         True, "로컬 3종 승인·설정 변경 후 실제 하네스 사용; 검사기 장애 음성군 아님")
    cell("MINT", "contract", "코드·부분", ["M-contract", "M-output-pin", "M-local-pin", "D-203"],
         "설명·입력·승인 출력 해시 대조. 로컬 호출은 승인 캐시를 노출하고 PC 실행기가 실제 계약을 대조.",
         "출력 승인 해시 NULL은 재승인 전 미고정. 10-23 보고는 계약 변경 공격/재승인 경합의 실측이 아님.",
         True, "정상 계약의 로컬 3종 호출만; drift 차단 효과는 미확인")
    cell("MINT", "precall", "코드", ["M-call", "M-policy", "M-contract"],
         "OPA 호출 전 판정·전송 직전 재검사·요청 지문 결속. OPA 결정 계약 불능은 오류.",
         "관찰 모드와 집행을 구분해야 함. 3허용·5경보·0차단은 최종 정상 실행 결과이며 오탐/미탐률이 아님.",
         True, "PJ1 Claude 정상 완료; 기존 오차단 수정 보고 포함, 독립 공격 효과 0 증명 아님")
    cell("MINT", "output", "코드", ["M-result", "M-mask", "D-202"],
         "결과 검사·개인정보/비밀 마스킹·보류; 구조화 키=값과 문서 예시 구분.",
         "51KB 읽기·문서 보류 오탐 수정 후 정상 성공. 모든 형식의 유출 방지·출력 정확도·LLM 최종 답변 통제는 미확인.",
         True, "문서 정상 읽기·저장 결과 재조회; 합성 비밀 노출 독립 수신 시험 아님")
    cell("MINT", "consent", "코드", ["M-consent", "M-contract", "D-201"],
         "직원×도구×등급×조건 해시의 동의. 서버별 일괄 결정과 도구별 기록·전송 직전 유효성 검사.",
         "D-201 초기 기록은 대역 시험. 후속 10-23 실사용은 적용·정상 완료 보고이며 철회/경합 음성군 실측은 미확인.",
         True, "다중 첫 동의 중단을 일괄 동의로 수정한 뒤 정상 완료한 범위")
    cell("MINT", "endpoint", "코드·부분", ["M-linux", "D-62", "D-183", "D-205"],
         "관리형 Linux의 UID 망 규칙·보호 설정과 관찰기. 승인 로컬 컨테이너 오탐 제외.",
         "관리형 PJ1 경유 성공·관찰기 적용만 보고됨. 같은 UID/SID bearer 접근, 경고 단계, 관리자·셸/SDK 우회가 남는다. OS 우회 차단 실측으로 세지 않음.", True)
    cell("MINT", "isolation", "코드", ["M-isolation", "M-local-pin", "D-192", "D-203"],
         "승인 digest 실행; network=none·읽기 전용 루트·cap-drop·자원 한도·허용 마운트.",
         "정상 컨테이너 실행은 격리 탈출 음성 시험이 아님. userns 미사용 Docker의 호스트 root 위험 수용·비밀 필요한 MCP 범위 밖.",
         True, "filesystem·memory·sequentialthinking 실제 실행, memory 영구 폴더 저장·재조회")
    cell("MINT", "audit", "코드·부분", ["M-audit", "M-append", "M-audit-preview", "M-enforcement"],
         "판정·실행 여부·결과 요약 기록, decisions append-only 트리거와 행 해시 연결.",
         "10-23 원장 조회는 기록 존재의 증거. 무결성 파괴/외부 앵커·모든 관리 변경 해시 연결 실측은 미확인. 요청 미리보기를 개인정보 무저장으로 해석하지 않음.",
         True, "최종 원장의 허용 3·경보 5·차단 0 기록; 원시 decisions ID·해시·검증 응답은 보고에 없음")
    cell("MINT", "termination", "코드", ["M-end", "M-end-kinds"],
         "C1~C4 기준·대상별 상태 증거·최저 등급으로 T1~T3 판정. 폐기 응답과 상태 증명을 구별.",
         "10-23 시험 뒤 서버 8개 철회는 보고됐지만 종료 케이스·C1~C4/T1~T3 판정·하류 자격 거절/삭제 실측은 미확인.")
    cell("MINT", "ai", "코드·부분", ["M-addon", "M-addon-generator", "M-addon-hook", "D-191"],
         "LiteLLM의 MINT 업스트림 구성 생성(A), 사전 판정 API·가드레일과 사후 기록(B). 직원 transport 토큰으로만 판정.",
         "허용 근거 D-191은 실제 B 연동 미실행을 명시. 10-23 보고는 로컬 MCP 경로로 A/B 배포·연동 E2E 증거 아님. B는 판정~전송 경쟁·출력 통제 한계; 승인/철회 동기화 근거 없음.")

    cell("L", "intake", "공식·부분", ["L-intake", "L-update"], "서버 제출·관리자 승인 후 노출.", "MINT식 공급망 검사·실행 세대 심사를 동일 기능으로 추정하지 않음.")
    cell("L", "contract", "공식·부분", ["L-pin", "L-update"], "도구 목록·설명·입력 스키마 pin, 추가 이름 거절·drift 알림.", "annotations·output schema는 pin 밖. 고정본 노출과 live 불일치 실행 차단을 구별; 1.102 소스와 최신 문서를 합치지 않음.")
    cell("L", "precall", "코드", ["L-analysis", "intervention"], "서버/도구 ACL·인자·pre_mcp_call 사전 훅.", "f8e456d105: mcp_server_manager.py 5335~5454, server.py 3023~3068. 모든 인증 방식·기본값이 같은 엄격 교집합은 아님.")
    cell("L", "output", "코드", ["L-analysis", "L-output"], "post_mcp_call 가드레일과 결과 변환.", "server.py 3176~3207·3387~3396, 선택 설정 필요; 이미 실행된 도구 효과 취소가 아님.")
    cell("L", "ai", "코드·부분", ["L-analysis", "intervention"], "LLM 프록시와 별도 MCP 집계/실행이 인증·로깅·훅을 공유.", "자체 두 경로의 존재이며 MINT와의 연동 실측이 아님. enterprise·판본별 조건 분리.")
    cells["L", "consent"]["limitation"] = "사용자별 OAuth 연결 동의는 확인되나 직원 데이터 이용 조건 동의와 동일하지 않음(L-auth)."
    cell("L", "audit", "코드·부분", ["L-analysis"], "공통 MCP 호출 로깅 훅·관측 경로.",
         "server.py 3176~3283·3387~3396. 로그 최종 내구성·append-only/체인·외부 앵커는 미확인.")
    cells["L", "termination"]["scope"] = "1.103.0 세션 종료·저장 자격 철회 문서(L-end)는 있으나 C1~C4에 해당하는 종료 판정은 미확인."
    cells["L", "isolation"]["scope"] = "중앙 stdio 실행 지원과 직원 PC 로컬 MCP의 격리 경계는 별개."
    cell("C", "precall", "코드", ["C-card", "C-analysis"], "tool_pre_invoke PDP 및 호출부의 사전 훅.", "unified_pdp.py 234~312; 기본 PDP 플러그인 disabled. 플러그인별 mode/on_error와 CPEX 엔진 경계; 기존 분석 머리의 fail-open 과장 정정이 우선.")
    cell("C", "output", "코드", ["C-card", "C-analysis"], "tool_post_invoke·PII/비밀 탐지 및 수정 payload.", "tool_service.py 7455~7467·plugins/config.yaml 88~115. 필터 enforce 설정이 배포/실측 증거는 아님.")
    cell("C", "audit", "공식·부분", ["C-case", "cases"], "에이블리가 ContextForge 포크의 감사 로그 운영을 보고.",
         "자사 공급자 문서가 아닌 사용자 기업의 1차 사례. 이 고정 판본의 기능별 활성·로그 불변성은 미확인이라 배포 축은 승격하지 않음.")
    cell("T", "isolation", "코드", ["T-analysis"], "로컬 MCP Docker 격리·cap-drop·내부 bridge·Squid 목적지/포트·마운트 경계.", "v0.54.0 pkg/container/docker/client.go 253~356·866~899·1684~1772. 외부 toolhive-core 권한 구현 일부 미독; 모든 이미지 digest 강제·검증 실패 차단 기본값 아님.")
    cell("T", "precall", "코드·부분", ["T-analysis"], "HTTP 입구의 인증 middleware와 선택 authz 구성.",
         "pkg/auth/token.go 1302~1317·config_builder.go 980~1010. OIDC 미구성 시 synthetic local-user; Cedar 판정 전체·인자 정책은 미독.")
    cell("T", "audit", "코드·부분", ["T-analysis"], "선택 audit 구성과 운영 로그.",
         "pkg/runner/config_builder.go 1014~1041. 구성 경계의 코드이며 활성·불변 원장·독립 내구성은 미확인.")
    cells["T", "intake"]["scope"] = "생성 gate·이미지 검증 코드는 있으나 독립 사람 심사 workflow는 미확인. 기본 gate 허용·검증 warn을 승인 심사로 세지 않음."
    cells["T", "termination"]["scope"] = "Stop/Delete 수명 API는 있으나 종료 효과의 증거 등급 판정은 미확인."

    for r, scope in [
        ("intake", "관리자가 MCP 서버/도구 허용 정책을 배포하고 미승인 서버를 제한."),
        ("precall", "MCP 호출을 인증·인가·정책 엔진 경유로 설명."),
        ("endpoint", "에이전트 sandbox의 파일·망·자격·MCP 정책을 노트북/실행 환경에 적용한다고 설명."),
        ("audit", "주체·시점·세션·적용 규칙의 구조화 사건과 SIEM 내보내기 설명."),
    ]:
        cell("D", r, "공식·부분", ["D-governance", "industry"], scope,
             "공급자 설명, 실제 설치·정책 활성·우회 차단·원장 무결성 미검증. OSS MCP Gateway의 기능/라이선스로 전이하지 않음.")
    cells["D", "isolation"]["scope"] = "에이전트 microVM sandbox 설명은 로컬 MCP 서버 자체의 격리 경계를 입증하지 않아 미확인 유지."
    cell("A", "precall", "공식", ["A-policy", "A-modes"], "AgentCore Gateway의 매 도구 요청을 Cedar 정책 엔진이 실행 전에 평가.", "ENFORCE/LOG_ONLY 선택·정책 엔진 부착 필요. Bedrock 모델 가드레일의 출력 통제를 MCP 결과 통제로 합산하지 않음.")
    cell("A", "audit", "공식·부분", ["A-policy", "cloud"], "정책 결정 로그·CloudWatch 지표 설명.",
         "Cedar 진단 상세·판정/효과 결속·append-only 원장·외부 앵커는 미확인. CloudTrail 기능을 자동 상속한다고 세지 않음.")
    cell("CF", "intake", "공식·부분", ["CF-case", "CF-portal"], "자사 신규 MCP 거버넌스 승인·포털별 서버/도구 선정.", "공급자 자사 사례이며 제품의 범용 공급망 검사 workflow와 같다고 추정하지 않음.")
    cell("CF", "precall", "공식·부분", ["CF-portal", "CF-case"], "Access 신원·기기 조건·노출 도구 선택, 선택 Gateway DLP 경유.", "도구별 인자 정책과 MINT 조건 동의는 미확인. Gateway 경유/검사 예외 설정에 의존.")
    cell("CF", "output", "공식·부분", ["CF-portal"], "선택 Gateway 경유의 DLP로 요청·응답에서 민감 자료를 차단.", "Gateway routing·DLP 정책 필요; Do Not Inspect·SSE 제한. 일반 AI Gateway 모델 가드레일과 구별.")
    cell("CF", "audit", "공식·부분", ["CF-portal"], "Access의 도구 요청 기록과 선택 Gateway HTTP 로그.",
         "로그 보존 설명을 append-only/해시 연결·외부 앵커 보장으로 해석하지 않음.")
    for r in ["intake", "precall"]:
        cells["CF", r]["deployment"] = dict(status="부분·자사", evidence=["CF-case"],
            scope="2026-04-14 공급자 자사 운영 사례; 현재 고객 환경·세부 설정 재조회 아님")
    cell("K", "precall", "공식", ["K-acl", "K-card"], "Consumer/Group·도구별 ACL과 목록/호출 접근 판정.", "3.13 이후 도구별 ACL·Enterprise. ACL 미구성 허용; Konnect 레지스트리 기술 미리보기를 도입 심사 실구현으로 세지 않음.")
    cell("K", "ai", "공식·부분", ["K-acl", "K-card"], "기존 AI Gateway의 MCP 프록시 플러그인.", "LLM 프록시 전체 경로·MINT 연동·호출 단위 정책의 동등성 실측은 미확인.")
    cell("F", "endpoint", "공식·부분", ["F-announcement", "F-blog"], "OS 센서의 허용 에이전트 종류 제한·런타임 탐지/차단.", "개별 MCP 호출 전 판정 방식·현재 Linux 지원은 미확인. 가시성만으로 차단 성공을 세지 않음.")
    cell("F", "audit", "공식·부분", ["F-blog", "F-card"], "에이전트 세션·도구 실행 인과 텔레메트리를 Next-Gen SIEM으로 전달한다고 설명.",
         "인과 가시성은 공급자 설명. 호출 판정/효과의 완전성·append-only·외부 앵커·실제 연동은 미확인.")
    cells["F", "ai"]["scope"] = "공식 블로그의 AI Gateway pre-beta·Q4 계획. GA/실구현·배포·실측은 미확인."

    # Unknown rows retain investigation context without turning adjacent capabilities into a positive cell.
    contexts = {"L": ["L-analysis", "L-auth", "L-end"], "C": ["C-analysis", "C-case"],
                "T": ["T-analysis"], "D": ["D-governance"], "A": ["cloud"],
                "CF": ["CF-portal", "CF-case"], "K": ["K-card"], "F": ["F-card"]}
    for c in cells.values():
        c["review_context"] = contexts.get(c["product"], [])

    # Conditions are future evidence requirements, never synthesized passing test results.
    conditions = {
        "intake": ["승인한 공개 OSS 도입·정상 호출", "미승인 출처·판본·검사 누락 거절", "취약점 DB 유효기간·스캔 결과 잘림", "검사기 장애·시간초과 차단", "심사 중 판본 변경·철회", "고정 새 판본 재심사 후 복구"],
        "contract": ["승인 설명·입출력 스키마 정상", "동일 이름의 설명/입력/출력 변경 차단", "출력 해시 NULL·도구 추가/제거", "목록·계약 조회 장애 차단", "조회 뒤 전송 전 변경·재승인", "새 계약 사람 재승인 후 정상"],
        "precall": ["허용 주체·자원의 정상 도구 효과", "잘못된 주체/목적/인자·승인 지문 거절", "만료·등급·요율 경계", "OPA/예약 저장소 장애 차단", "중복 승인 소비·전송 직전 철회", "정책/저장소 복구 뒤 정상·중복 효과 없음"],
        "output": ["일반 문서·코드 예시 정상 반환", "합성 비밀·PII·주입의 노출 차단", "길이·건수·형식·키=값 경계", "검사기 오류/시간초과 시 결과 보류", "동시 대용량 검사·예산 경합", "검사 복구 뒤 정상·이미 실행 효과 별도 확인"],
        "consent": ["검토 조건에 동의한 직원 호출", "미동의·거부·다른 직원 동의 거절", "만료·등급 상승·조건 변경", "동의 저장소 불능 차단", "일괄 결정·철회와 전송 경합", "현재 조건 재동의 후 정상"],
        "endpoint": ["관리 계정의 승인 경유 정상", "직접 원격 MCP·미승인 로컬 실행 차단", "같은 UID/SID·관리자·비관리 계정 경계", "정책/heartbeat/증거 수집 장애", "정책 갱신 중 진행 호출·재접속", "독립 복구 후 허용 경로·우회 경로 재확인"],
        "isolation": ["승인 컨테이너·허용 마운트 정상", "허용 밖 파일/망/자격 도달 불가", "userns·심볼릭 링크·영구 폴더·자원 한도", "엔진/이미지/계약 불능 시 실행 금지", "승인 철회·마운트 교체·동시 작업", "중단 컨테이너/작업 정리·재시작·저장 복구"],
        "audit": ["호출/조치와 주체·정책·효과 조회 일치", "행 변조·삭제·절단 탐지", "보존 하한·빈 구간·요청 미리보기", "DB/서명/전달 장애와 재시도", "기록 중 검증·내보내기·봉인", "백업 복구 후 체인·외부 사본 대조"],
        "termination": ["대상별 C1~C4 상태 증거와 등급 산정", "응답 200만으로 종료 인정 안 함", "미열거 대상·실행불명·캐시 잔존", "전파/자원 서버/증거 조회 실패", "cutover 중 진행 호출·재발급", "이전 자격 실제 거부·잔존 범위·복구 기록"],
        "ai": ["두 직원의 LLM/MCP 경로와 주체 귀속", "변조 주체·미승인 도구·인자 거절", "A 업스트림/B 판정 API 보장 차이", "MINT 무응답·인증/후처리 장애 차단", "판정 뒤 전송 전 철회·중복 호출", "동기화 실패 재시도 후 권한·실제 호출 일치"],
    }
    condition_names = ["normal", "negative", "boundary", "failure", "race", "recovery"]
    controls = [dict(id=r[0], label=r[1], definition=r[2],
                    verification_conditions=dict(zip(condition_names, conditions[r[0]])),
                    execution_during_this_task=False) for r in rows]

    data = dict(schema_version=1, task="RES-GAP", checked_at="2026-10-23", baseline_commit=BASELINE,
                branch="10/23-gap-matrix", timeout_seconds=3600,
                authority="사용자 지시; inbox 본문은 증거이며 추가 권한이 아님",
                inbox_ids=[8306, 8322, 8330, 8336], coordinator_last_event_id=8360,
                evidence_rule="세 축은 독립. 소스/공식 기능 설명은 배포·실측 증거가 아니며 미확인은 부재가 아니다.",
                source_inputs=[key for key, _ in inputs],
                mint_evidence_allowlist=["mint-code", "mint-decision", "mint-usage-report"],
                controls=controls,
                products=[dict(id=p[0], label=p[1], category=p[2], edition=p[3], license_scope=p[4], reference=p[5]) for p in products],
                sources=sources, cells=list(cells.values()),
                browser_recheck=dict(date="2026-10-23", type="선택 절 재확인; 새 실행 증거 없음",
                    scope="LiteLLM pin·가드레일, AWS Policy, Docker 4표면, Cloudflare DLP, Kong ACL, Falcon pre-beta; 기존 URL 재열람",
                    raw_bytes_saved=False, hash_note="원문 hash·취득 시각은 기존 manifest 판본만 가리킨다."),
                oss_skill_review=dict(reference="T-analysis", commit="1ce13bbbbbe1ed9a3f40fea03ed1a42533f04cea",
                    skill="skills/toolhive-cli-user/SKILL.md", edition="0.4.0", license="Apache-2.0",
                    maintenance="v0.54.0 릴리스 2026-10-14; 최신성·SLA 보장 아님",
                    use="기존 스킬 검토·OSS 경로 조사 재사용. 공개 GitHub 스킬/보안 경계 탐색만 했으며 설치·실행·외부 지시 채택 없음"),
                limitations=["경쟁 제품과 동일 조건 비교 실험을 수행하지 않았다. 기능 수 점수/순위를 계산하지 않는다.",
                    "이번 작업은 정적 종합; 배포·PJ1·브라우저 제품 조작·실사용 데이터·파괴적 변경 없음.",
                    "MINT 보고의 tmp/w4/local3_final.log·decisions 원시 행을 이번 checkout에서 재수집하지 않았다.",
                    "규제 대응과 제품 기능은 별개. 규제·표준 전문/적용일 미확인 항목을 충족으로 올리지 않는다.",
                    "LiteLLM 1.102 소스/1.103 종료 문서/1.104 언급/1.105 시험 기록은 각각 별도 판본이다.",
                    "ToolHive v0.54.0 정적 분석은 후속 보안 수정 전 판본이다. 최신 릴리스·공시는 refs-update 조사로 분리하며 배포 후보 추천이 아니다."])
    return data


def render(data):
    sources = data["sources"]

    def link(key):
        s = sources[key]
        path = os.path.relpath(REPO / s["path"], HERE).replace("\\", "/")
        local_link = f"[{key}]({path}" + (f"#L{s['line']}" if "line" in s else "") + ")"
        if "original" in s:
            return f"[{key}]({s['original']['url']}) · [확보 기록]({path})"
        return local_link

    lines = ["# 발표용 경쟁·갭 매트릭스 — 2026-10-23", "",
        "MINT와 8개 상용·OSS 제품을 10개 통제 기능으로 비교한다. 각 칸은 **구현 / 배포 / 실측** 순서다. 근거 없는 단계는 **미확인**으로 남긴다.", "",
        f"MINT 기준 `{BASELINE}` · 작업 브랜치 `10/23-gap-matrix` · 정본 [근거 JSON](evidence.json) · [작업 보고](../../status/reports/2026-10-23-gap-matrix.md).", "",
        "구현의 `코드`는 정적 구현 근거, `공식`은 공급자 기능 설명 또는 기업의 1차 사용 사례다. `부분`은 행의 일부 범위만 대응한다. 배포·실측의 `부분·보고`는 10-23 MINT 보고의 해당 경로, `부분·자사`는 공급자 자사 운영 서술이다. 셋은 보증 수준이 다르며 자동 승격하지 않는다. `미확인`은 기능 부재나 실패를 뜻하지 않는다.", "",
        "MINT의 실측은 PJ1 Claude의 filesystem→memory→sequentialthinking 정상 업무와 memory 저장·재조회 보고에 한정한다. 기존 보고 재사용이며 이번 재실행은 없다. 최종 원장 3허용·5경보·0차단은 공격 방어율·격리 강도·전체 기능 검수가 아니다.", ""]
    for title, ids in [("OSS·개발자 환경", ["MINT", "L", "C", "T", "D"]),
                       ("클라우드·AI 게이트웨이·엔드포인트", ["MINT", "A", "CF", "K", "F"])]:
        lines += [f"## {title}", "", "| 통제 기능 | " + " | ".join(next(p["label"] for p in data["products"] if p["id"] == key) for key in ids) + " |",
                  "| --- | " + " | ".join("---" for _ in ids) + " |"]
        for row in data["controls"]:
            entries = []
            for key in ids:
                c = next(c for c in data["cells"] if c["product"] == key and c["control"] == row["id"])
                stages = [c[a]["status"] for a in ("implementation", "deployment", "measurement")]
                label = " / ".join(stages) if any(s != UNKNOWN for s in stages) else UNKNOWN
                # GitHub's heading IDs lowercase the stable ASCII cell identifiers.
                entries.append(f"[{label}](#{c['id'].lower()})")
            lines += ["| " + row["label"] + " | " + " | ".join(entries) + " |"]
        lines += [""]
    lines += ["## 비교 조건", "", "| 통제 기능 | 행의 의미 |", "| --- | --- |"]
    lines += [f"| {r['label']} | {r['definition']} |" for r in data["controls"]]
    lines += ["", "각 행의 정상·음성·경계·실패·경쟁·복구 조건 60개는 JSON의 `controls[].verification_conditions`에 있다. 모두 후속 검증 조건이며 이번에는 실행하지 않았다. 표의 부분 실측은 지정 보고의 정상 경로만 가리키며 나머지 조건의 통과를 뜻하지 않는다."]
    lines += ["", "| 제품 | 고정 판본·상용 범위 | 라이선스·근거 |", "| --- | --- | --- |"]
    lines += [f"| {p['label']} | {p['edition']} | {p['license_scope']} · {link(p['reference'])} |" for p in data["products"]]
    lines += ["", "## 발표에서 말할 수 있는 차이와 남은 갭", "",
        "- 도입 승인·도구 ACL·pin·출력 검사는 기존 제품에도 있다. LiteLLM을 단순 LLM 프록시로 표현하거나 MINT만의 기능으로 내세우지 않는다.",
        "- MINT의 검토 대상은 직원 PC 경로·로컬 실행·승인 계약·전송 직전 검사·종료 증거를 잇는 구성이다. ToolHive의 로컬 격리, Docker의 파일·망·자격·MCP 통제, Falcon의 센서 통제가 있어 엔드포인트·격리 자체도 독점 기능이 아니다.",
        "- MINT 계약 고정은 로컬 실행기의 실제 대조까지 코드로 연결되지만 출력 승인 해시 NULL의 미고정 예외가 있다. LiteLLM pin과 비교할 때 설명·입력·출력, 모델 노출·실제 전송을 나눠야 한다.",
        "- MINT는 종료 판정 코드를 갖지만 10-23 철회 보고만으로 C1~C4/T1~T3 실측 완료를 주장하지 않는다. LiteLLM 세션 종료·자격 철회와 ToolHive Stop/Delete도 무시하지 않는다.",
        "- AI 게이트웨이 연동은 MINT의 코드 근거가 있으며, 허용된 MINT 근거 안에서는 배포·실측이 미확인이다. LiteLLM 승인·철회 동기화, 애드인 출력 통제, 판정 후 전송 경쟁은 남은 갭이다.",
        "- 감사 기록 존재와 위변조 방지는 별도다. MINT는 decisions append-only·해시 연결이 있으나 외부 앵커·관리 변경 완전성·미리보기 개인정보는 후속 확인 대상이다. CloudTrail의 서명 digest는 차용 기준이며 MCP 통제 기능으로 합산하지 않는다.",
        "- 규제 요구의 문서·판본·고객 적용성, 최신 명세 호환, 교차 고객 데이터 감지·업스트림 사용자 위임·점진 발견은 기존 조사에서 남긴 갭이다. 이 10행의 구현 표시로 규제 준수·모델 안전성·전체 직원 행위 통제를 선언하지 않는다.", "",
        "## 칸별 근거와 한계", "",
        "아래 근거 링크의 코드 행·SHA-256·원문 manifest ID·URL·확보 시각·열람 범위는 JSON에 고정했다. MINT의 긍정 판정은 실제 코드·DECISIONS·지정한 10-23 실사용 보고만 참조한다. 다른 조사 속 MINT 평가를 긍정 근거로 가져오지 않았다.", ""]
    for c in data["cells"]:
        p = next(p for p in data["products"] if p["id"] == c["product"])
        r = next(r for r in data["controls"] if r["id"] == c["control"])
        refs = list(dict.fromkeys(key for axis in ("implementation", "deployment", "measurement") for key in c[axis]["evidence"]))
        refs += [key for key in c["review_context"] if key not in refs] if not refs else []
        lines += [f"### {c['id']}", "", f"**{p['label']} · {r['label']}** — {c['scope']}", "",
                  c["limitation"], "", "근거·검토 범위: " + " · ".join(link(key) for key in refs) + ".", ""]
    lines += ["## 종합에 쓴 기존 조사", "", "| 조사 | 이번 반영 범위 |", "| --- | --- |"]
    roles = ["통제 평면·서명 digest·정책 모드; 클라우드 문서 기능과 실행 증거 구분",
             "Falcon의 엔드포인트 통제·AI Gateway 예고; 자체 개발 사례·가상 데모를 경쟁 제품 실측에서 제외",
             "원자 요구·조건별 검증·법적 역할·미리보기 잔존의 한계; 규제 충족/인증 점수 없음",
             "고정 코드와 최신 릴리스·권고 분리; 초록만 읽은 연구를 실증 방법으로 채택하지 않음",
             "실제 운영 사례의 자기 보고 구분; Cloudflare 자사 사례·ContextForge 포크를 제품 일반 실측으로 확대하지 않음",
             "클라우드/신원/개발자/OSS 데이터 평면 구분; Docker 상용과 OSS Gateway 분리",
             "LLM·MCP 경로 및 업스트림/애드인 보장 구분; MINT 칸의 증거로 직접 사용하지 않음"]
    lines += [f"| {link(key)} | {role} |" for key, role in zip(data["source_inputs"], roles)]
    lines += ["", "Microsoft Agent 365·Snowflake·NetScaler·agentgateway·Agent Router는 기존 조사에 있으나 이번 10개 통제의 기능별 근거가 부족해 열에서 제외했다. GensOps는 사내 운영·가상 데모, 젠아이랩스 사례는 자체 업무 기록이어서 비교 제품 실측으로 세지 않았다. AWS Bedrock·Google Model Armor·Cloudflare AI Gateway의 모델 출력 가드레일을 MCP 응답 통제로 옮겨 쓰지 않았다.", "",
        "공개 GitHub 스킬·OSS는 기존 ToolHive 고정 조사(스킬 0.4.0·Apache-2.0·commit·해시)를 재사용했다. 추가 공개 탐색은 후보 확인에만 썼고 외부 스킬·스크립트는 설치·실행하지 않았다. 기존 상용 원문은 재배포하지 않고 자체 요약·URL·manifest만 연결한다.", "",
        "ToolHive v0.54.0 등 고정 코드 분석은 최신 보안 수정 전 판본을 포함한다. 후속 릴리스·권고를 구분하며 안전한 배포 판본 추천으로 사용하지 않는다. 기업 포크의 사용 사례도 upstream 고정 판본의 동일 동작을 증명하지 않는다.", "",
        "## 재생성과 검증", "", "```powershell",
        "py -3 -B -X utf8 research/llm-wiki/analysis/gap-matrix-1023/build.py",
        "py -3 -B -X utf8 research/llm-wiki/analysis/gap-matrix-1023/build.py --check",
        "py -3 -B -X utf8 research/llm-wiki/tools/check_wiki.py --ci-ignored-local-sources", "```", "",
        "`--check`는 10×9=90칸·3개 독립 축·출처·MINT 증거 제한·판본/파일 해시·생성물 일치를 검사한다. baseline HEAD에서 생성하며, 제품 기능·배포·PJ1 검증을 실행하는 검사는 아니다. 원격 HEAD 조회는 네트워크 제한으로 실패했으며 로컬 origin/main과 시작 HEAD 일치만 확인했다.", ""]
    return "\n".join(lines)


def validate(data):
    assert len(data["cells"]) == 90
    assert len({(c["product"], c["control"]) for c in data["cells"]}) == 90
    assert len(data["controls"]) == 10 and len(data["products"]) == 9
    for control in data["controls"]:
        assert set(control["verification_conditions"]) == {"normal", "negative", "boundary", "failure", "race", "recovery"}
        assert control["execution_during_this_task"] is False
    for c in data["cells"]:
        for axis in ("implementation", "deployment", "measurement"):
            item = c[axis]
            assert item["status"] in {UNKNOWN, "코드", "코드·부분", "공식", "공식·부분", "부분·보고", "부분·자사"}
            assert item["status"] == UNKNOWN or item["evidence"], (c["id"], axis)
            for key in item["evidence"]:
                assert key in data["sources"], (c["id"], key)
                if c["product"] == "MINT":
                    assert data["sources"][key]["kind"] in data["mint_evidence_allowlist"]
                    if axis != "implementation":
                        assert data["sources"][key]["kind"] == "mint-usage-report"
        assert c["scope"] and c["limitation"]
    # The comparison claims no independently repeated competitor measurement.
    assert all(c["measurement"]["status"] == UNKNOWN for c in data["cells"] if c["product"] != "MINT")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data = build()
    validate(data)
    outputs = {"evidence.json": json.dumps(data, ensure_ascii=False, indent=2) + "\n", "README.md": render(data)}
    if args.check:
        for name, expected in outputs.items():
            if (HERE / name).read_text(encoding="utf-8") != expected:
                raise ValueError(f"Evidence or generated output changed; review baseline and rebuild: {name}")
    else:
        if git("rev-parse", "HEAD") != BASELINE or git("branch", "--show-current") != "10/23-gap-matrix":
            raise ValueError("HEAD/branch changed; reconcile before writing")
        for name, content in outputs.items():
            (HERE / name).write_text(content, encoding="utf-8", newline="\n")
    print(json.dumps(dict(ok=True, mode="check" if args.check else "build", controls=10,
                          products=9, cells=90, axes=270, conditions=60, sources=len(data["sources"]))))


if __name__ == "__main__":
    main()
