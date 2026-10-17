"""Feature specification, development WBS and policy coverage workbook (2026-10-17).

Writes analysis/feature-spec-2026-10-17/feature-spec.json (structured record) and
feature-spec.xlsx (report workbook). Inputs are the WBS snapshot and the policy-50
workbook extract already kept in this wiki. Existing work takes its stage scores
from the snapshot; planned work and its schedule are proposals.
"""
import json
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter as L

WIKI = Path(__file__).resolve().parents[1]
OUTDIR = WIKI / "analysis" / "feature-spec-2026-10-17"
# The 40-task snapshot this record was built from; snapshot.json now holds the extended 57-task board.
SNAP = WIKI / "analysis" / "development-wbs" / "snapshot-before-wbs-1017.json"
POLICIES = WIKI / "threats" / "extracted" / "policies.json"
OUT = OUTDIR / "feature-spec.xlsx"
snap = {t["id"]: t for t in json.load(open(SNAP, encoding="utf-8"))["items"]}
record = {"title": "MCP 보안 거버넌스 솔루션 기능명세서·개발 WBS", "as_of": "2026-10-17",
          "code_basis": "10/15-wbs-implementation c0fbab3",
          "inputs": {"wbs_snapshot": SNAP.relative_to(WIKI).as_posix(), "policies": POLICIES.relative_to(WIKI).as_posix()}}
STAGES = ["implementation", "regression", "deployment", "real_device", "acceptance_complete"]

F = "맑은 고딕"
font = lambda **k: Font(name=F, size=k.pop("size", 10), **k)
fill = lambda c: PatternFill("solid", fgColor=c)
thin = Side(style="thin", color="BFBFBF")
box = Border(left=thin, right=thin, top=thin, bottom=thin)
HEAD, SUB = fill("1F3864"), fill("D9E1F2")
DONE, PART, PLAN, EXCL = fill("E2EFDA"), fill("FFF2CC"), fill("DDEBF7"), fill("EDEDED")
wrap = Alignment(wrap_text=True, vertical="center")
center = Alignment(horizontal="center", vertical="center", wrap_text=True)


def header(ws, row, names, widths=None):
    for i, n in enumerate(names, 1):
        c = ws.cell(row, i, n)
        c.font, c.fill, c.alignment, c.border = font(bold=True, color="FFFFFF"), HEAD, center, box
    if widths:
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[L(i)].width = w


def title(ws, text, sub, span):
    ws["A1"] = text
    ws["A1"].font = font(size=15, bold=True)
    ws["A2"] = sub
    ws["A2"].font = font(size=9, color="595959")
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=span)
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=span)


wb = Workbook()

# ───────────────────────── 1. 기능명세서 ─────────────────────────
ws = wb.active
ws.title = "기능명세서"
title(ws, "MCP 보안 거버넌스 솔루션 기능명세서",
      "기준: 개발 브랜치 10/15-wbs-implementation(c0fbab3) · 정책 기준: MCP_보안정책50 (본)정책 최종본 · 작성 2026-10-17", 8)
ws["A3"] = ("솔루션 구성: MCP 게이트웨이, 직원 PC의 엔드포인트 에이전트, 승인 소스 격리 실행기. "
            "자동화 범위: 서버와 Tool의 승인 상태, 사용자 신원과 권한, 입력값과 데이터 전송 범위, 실제 연결 주소, 응답 크기와 중복 실행, "
            "구성 변경과 이상 징후를 솔루션이 자동으로 검사하고 차단하며, 관리 PC의 우회 실행 제한, 운영 이미지 취약점 재검사, "
            "탐지 후 연결 중지, 복원 후 폐기 상태 대조와 판정 증적 기록을 자동화함. 에이전트 자체의 신원 증명과 위임 범위 판정, "
            "외부 제공자 측 자격·자원 데이터의 확인, 원격 서버 내부의 연결과 실행 결과는 솔루션이 관측할 수 없으므로 자동화 범위에서 제외하며, "
            "위임을 주장하는 요청은 거부함.")
ws["A3"].font, ws["A3"].alignment = font(size=10), wrap
ws.merge_cells("A3:H3")
ws.row_dimensions[3].height = 78
ws["A4"] = ("구현 완료(검수 전): 기능이 구현되어 기기에 배포된 상태이며, 실기기 확인과 최종 검수가 끝났다는 뜻이 아님(최종 검수 완료 0건). "
            "단계별 검증 상태는 '개발 WBS' 시트에서 확인함.")
ws["A4"].font, ws["A4"].alignment = font(size=9, color="C00000"), wrap
ws.merge_cells("A4:H4")
ws.row_dimensions[4].height = 28

# status summary (formulas)
ws["A5"], ws["A5"].font = "개발 상태", font(bold=True)
labels = ["구현 완료(검수 전)", "일부 구현", "개발 예정", "자동화 범위 제외"]
for i, s in enumerate(labels):
    ws.cell(5, 2 + i * 2 - 0, s).font = font(bold=True)
SPEC_FIRST = 8

spec = [
    # 대분류, 기능명, 기능 설명, 대응 정책, 구현 수단, 상태, 비고
    ("사용자·엔드포인트", "사용자 등록", "가입 신청, 역할 분리, 관리자 승인", "POL-19", "FastAPI · PostgreSQL", "개발 완료", "관리자 권한 자동 부여 금지"),
    ("사용자·엔드포인트", "조직 로그인", "조직 계정 로그인과 기존 사용자 연결, 관리 화면 세션 만료", "POL-19 · POL-21", "Keycloak · Authlib", "개발 완료", "운영 TLS 적용은 '전송 구간 암호화' 항목에서 진행"),
    ("사용자·엔드포인트", "PC 등록·활성화", "연결 키트 설치, 장치 키 발급, 관리 계정 활성화", "POL-12 · POL-19", "엔드포인트 에이전트 · PostgreSQL", "개발 완료", "Windows 실기기 확인 남음"),
    ("사용자·엔드포인트", "실행·통신 제한", "관리 계정의 미승인 실행, 게이트웨이 우회 연결, 로컬 서버 직접 실행 제한", "POL-12 · POL-17", "AppArmor · nftables · systemd", "일부 개발", "관리형 Linux 계정에 한정, 미인가 로컬 MCP 시험 진행 중"),
    ("사용자·엔드포인트", "상태 관측", "마지막 보고, 보호 상태, 통제 밖 계정, 발견된 MCP 설정 표시", "POL-12 · POL-42", "엔드포인트 에이전트", "개발 완료", "관측과 기기 전체 집행을 구분해 표시"),
    ("MCP 도입·검증", "도입 신청", "주소, 버전 또는 커밋, 용도, 사용 범위 접수", "POL-01 · POL-02", "FastAPI · PostgreSQL", "개발 완료", ""),
    ("MCP 도입·검증", "격리 검사", "승인 전 소스 수집과 검사를 게이트웨이와 분리된 워커에서 수행", "POL-01 · POL-05", "Docker · Git", "개발 완료", ""),
    ("MCP 도입·검증", "구성요소 분석", "SBOM 생성, 의존성·라이선스 식별", "POL-01 · POL-03", "Syft", "개발 완료", ""),
    ("MCP 도입·검증", "위험 검사", "취약점, 오구성, 코드 규칙, Tool 설명의 악성 지시 검사", "POL-03 · POL-04", "Trivy · Semgrep · 자체 규칙", "개발 완료", "검사 누락·실패는 통과로 처리하지 않음"),
    ("MCP 도입·검증", "Secret 검사", "소스 속 인증정보 탐지, 결과에서 민감 문자열 제거", "POL-14", "Gitleaks", "개발 완료", ""),
    ("MCP 도입·검증", "승인 소스 격리 실행", "승인된 커밋만 고정 방식으로 빌드해 전용 망에서 실행, 심사한 목적지만 외부 연결 허용", "POL-09 · POL-46", "Docker · 자체 실행기", "개발 완료", "등록 해제·승인 철회 시 정지 시험 남음"),
    ("MCP 도입·검증", "운영 이미지 재검사", "실행 중인 서버 이미지를 주기적으로 다시 검사하고 기한 내 미조치 시 격리", "POL-39", "Trivy · 자체 실행기", "개발 예정", ""),
    ("승인·카탈로그", "독립 승인", "신청자와 승인자 분리, 검토 근거와 승인 기록 보존", "POL-08 · POL-38", "PostgreSQL", "개발 완료", ""),
    ("승인·카탈로그", "사용 범위", "사용자, 도구, 자원, 데이터 등급, 기한 지정", "POL-02 · POL-11 · POL-23", "OPA · Rego · PostgreSQL", "개발 완료", ""),
    ("승인·카탈로그", "계약 잠금", "도구 이름·설명·입력 스키마·버전 해시를 고정하고 호출 직전 재대조", "POL-11 · POL-37", "MCP Python SDK · jsonschema", "개발 완료", "첫 관찰 자동 승인 금지"),
    ("승인·카탈로그", "승인 만료·재승인", "승인 기한 만료, 중지, 구성 변경 시 재승인 요구", "POL-08 · POL-37 · POL-40", "PostgreSQL · OPA", "개발 완료", ""),
    ("승인·카탈로그", "내부 소스 반입", "승인 저장소 보관, 검증 커밋 대조", "POL-01", "Gitea", "개발 완료", "저장소 반입만으로 승인 완료 아님"),
    ("승인·카탈로그", "하네스별 최소 설정 배포", "승인된 서버만 하네스 설정에 배포, 미승인 커넥터 비활성화", "POL-11 · POL-12", "엔드포인트 에이전트", "개발 완료", ""),
    ("승인·카탈로그", "데이터·기능 단위 사용자 동의", "사용자 동의를 데이터·기능 단위로 기록하고 호출마다 대조, 동의가 없으면 확인 요청", "POL-08", "PostgreSQL · OPA · MCP 확인 요청", "개발 예정", ""),
    ("호출·데이터 통제", "신원·상태 확인", "인증된 주체, 토큰 발급자·대상·기한·폐기 여부, 등록·중지 상태 확인", "POL-19 · POL-21", "FastAPI · PostgreSQL · Ed25519", "개발 완료", "도구 인자·클라이언트 보고값은 신원으로 쓰지 않음"),
    ("호출·데이터 통제", "인자·자원 분석", "스키마, 경로, URL, SQL, 수신자 분석과 실제 행위(조회·변경·실행) 판정", "POL-23 · POL-24", "jsonschema · pglast", "개발 완료", ""),
    ("호출·데이터 통제", "실행 전 정책", "권한, 계약, 데이터 등급, 민감정보 반출 조건 판정", "POL-22 · POL-25 · POL-26", "OPA · Rego · Presidio · Gitleaks", "개발 완료", "정책·분류·계약 오류는 차단"),
    ("호출·데이터 통제", "호출·응답 통제", "허용 호출만 전달, 응답 개인정보 마스킹, Secret·비신뢰 지시 포함 결과 보류", "POL-29 · POL-30", "MCP Python SDK · Presidio · Gitleaks", "개발 완료", ""),
    ("호출·데이터 통제", "고위험 건별 승인", "요청 내용에 묶인 1회용 승인, 자가 승인 금지, 10분 만료", "POL-27", "PostgreSQL · OPA", "개발 완료", ""),
    ("호출·데이터 통제", "호출량·동시 실행 제한", "호출량, 동시 실행, 실행 중 중복 호출을 원자적으로 예약·제한", "POL-28 · POL-36", "PostgreSQL", "개발 완료", ""),
    ("호출·데이터 통제", "MCP 접속 출처 검증", "게이트웨이 MCP 접속의 Host·Origin 허용 목록 검사", "POL-18", "MCP Python SDK", "개발 완료", ""),
    ("호출·데이터 통제", "서버별 인증정보 분리", "원격 서버 인증정보를 서버·주소·주체별로 결속하고 교차 사용 거부", "POL-15", "자체 구현", "개발 완료", ""),
    ("호출·데이터 통제", "실제 연결 주소 확인", "연결 직전 DNS 조회 결과로만 접속, OAuth 메타데이터 조회 대상 검사", "POL-10 · POL-40", "Python 표준 라이브러리 · httpx", "개발 예정", ""),
    ("호출·데이터 통제", "전송 구간 암호화", "하네스와 게이트웨이 사이 TLS 적용, 원격 MCP 평문 연결 차단", "POL-16", "Caddy · 내부 CA", "개발 예정", "원격 평문 연결 차단은 개발 완료"),
    ("호출·데이터 통제", "전송 목적 확인", "수신처, 데이터 등급, 목적이 승인된 조합과 일치할 때만 외부 전송 허용", "POL-26", "OPA · Rego", "개발 예정", ""),
    ("호출·데이터 통제", "입력 최소화", "도구별 허용 입력 항목만 전달, 입력 민감정보 마스킹", "POL-31", "Presidio · OPA", "개발 예정", ""),
    ("호출·데이터 통제", "서버 간 전달 경계", "세션 내 중요정보 표시 전파, 승인되지 않은 서버 간 전달 차단", "POL-33", "자체 구현 · OPA", "개발 예정", ""),
    ("호출·데이터 통제", "조회 범위 제한", "단일 조회의 반환 건수·크기 상한, 전체 폴더 조회 차단", "POL-35", "자체 구현", "개발 예정", ""),
    ("호출·데이터 통제", "중복 실행 방지", "변경 요청에 멱등 키를 부여해 재전송·재시도 중복 차단", "POL-36", "PostgreSQL", "개발 예정", "원격 서버 내부의 중복 실행은 제외"),
    ("호출·데이터 통제", "인증정보 노출 차단", "설정, 실행 인자, 오류 응답의 인증정보 원문 탐지·제거", "POL-14", "Gitleaks", "개발 예정", ""),
    ("운영·감사", "운영 현황", "승인 대기, 최근 차단, 서버·단말 상태, 처리 지연 조회", "POL-38 · POL-42", "Apache ECharts", "개발 완료", "관리 화면은 MCP를 직접 호출하지 않음"),
    ("운영·감사", "감사 원장", "판정·시도·실행·응답 상태를 변경 불가 해시 사슬로 저장, 민감 본문 제외", "POL-38", "PostgreSQL", "개발 완료", ""),
    ("운영·감사", "추적·내보내기", "호출 추적, 필터, 상세, 사슬 검증, 내보내기", "POL-38", "OpenTelemetry · Jaeger", "개발 완료", ""),
    ("운영·감사", "이상 징후 경보", "새 도구, 미승인 연결, 반복 차단, 중요정보 접근 집중 경보", "POL-42 · POL-43", "OPA · PostgreSQL", "개발 완료", ""),
    ("운영·감사", "단말 이벤트 상관", "MCP 요청, 게이트웨이 판정, 단말 이벤트 연결", "POL-38", "엔드포인트 에이전트", "일부 개발", "하네스 이벤트 시각 연결 남음"),
    ("운영·감사", "경보 자체 시험", "정책 배포 직후 합성 이벤트로 경보 동작 확인", "POL-42", "자체 구현", "개발 예정", ""),
    ("운영·감사", "탐지 시 자동 중지", "미승인 변경·이상 호출 탐지 시 해당 서버와 도구 자동 중지", "POL-43", "PostgreSQL · OPA", "개발 예정", ""),
    ("종료·권한 회수", "접근 중지", "만료·중지·철회된 관계의 후속 호출 즉시 거부", "POL-44", "OPA · PostgreSQL", "개발 완료", ""),
    ("종료·권한 회수", "장치·자격 회수", "사용자·장치 토큰과 갱신 토큰 일괄 폐기, 연결 풀 종료", "POL-44 · POL-45", "PostgreSQL · Keycloak", "개발 완료", ""),
    ("종료·권한 회수", "세션 종료", "활성 세션과 MCP 서버 세션 종료, 재접근 차단", "POL-44 · POL-46", "자체 구현", "일부 개발", "상태를 유지하는 서버의 세션 재접근 시험 남음"),
    ("종료·권한 회수", "종료 판정", "회수 대상, 권한, 연속성, 증거를 종합해 종료 완료 판정", "POL-44 · POL-45", "PostgreSQL", "개발 완료", ""),
    ("종료·권한 회수", "잔존 자료 확인", "설정·인증정보 제거 후 잔존 여부와 백업 복구 시험", "POL-48 · POL-50", "자체 구현", "일부 개발", "직원 PC 백업·캐시 복구 시험 남음"),
    ("종료·권한 회수", "복원 후 폐기 상태 대조", "폐기 목록을 서명해 DB 밖에 보관하고 복원 후 대조, 필요 시 서명키 교체", "POL-50", "cryptography · PostgreSQL", "개발 예정", ""),
    ("자동화 범위 제외", "에이전트 신원 증명", "하네스가 스스로 밝힌 정보를 검증할 수단이 없음", "POL-19", "—", "자동화 범위 제외", "사용자 신원만 토큰으로 확인"),
    ("자동화 범위 제외", "에이전트 위임 판정", "검증된 에이전트 주체가 없어 위임 범위를 판정할 수 없음", "POL-20", "—", "자동화 범위 제외", "위임을 주장하는 요청은 거부"),
    ("자동화 범위 제외", "외부 서비스 자원 등급 판정", "등급 정보가 제공자에게만 있음", "POL-25", "—", "자동화 범위 제외", "내부 자원만 등급 판정"),
    ("자동화 범위 제외", "제공자 측 인증정보 무효화 확인", "제공자 시스템 내부의 처리로 솔루션이 관측할 수 없음", "POL-41 · POL-45", "—", "자동화 범위 제외", "게이트웨이에서의 재사용 차단까지 수행"),
    ("자동화 범위 제외", "배포자 서명 검증", "서명이 없는 배포물은 검증 대상이 없음", "POL-01", "—", "자동화 범위 제외", "해시 고정과 도입 보류로 대체"),
    ("자동화 범위 제외", "원격 OAuth 인증 응답 대조", "솔루션이 원격 서버의 OAuth 인증 과정에 참여하지 않음", "POL-13", "—", "자동화 범위 제외", ""),
    ("자동화 범위 제외", "원격 서버 내부 동작 확인", "원격 서버 내부의 중복 실행과 연결 대상은 관측할 수 없음", "POL-36 · POL-40", "—", "자동화 범위 제외", "게이트웨이 경계까지 통제"),
    ("자동화 범위 제외", "도입 적절성·법적 요건·계약 검토", "도입 목적의 적절성, 법적 요건, 외부 제공자 계약 조건 판단", "POL-02 · POL-03 · POL-06 · POL-07", "—", "자동화 범위 제외", "검토 결과와 승인 근거는 솔루션에 기록"),
    ("자동화 범위 제외", "최종 승인 판단·실동작 시험", "운영 연결의 최종 승인 판단과 Tool 실제 동작 일치 시험", "POL-05 · POL-27", "—", "자동화 범위 제외", "승인 절차와 기록은 솔루션이 제공"),
    ("자동화 범위 제외", "에이전트 내부·외부 시스템 조치", "에이전트 컨텍스트 분리, 원본 문서 진위, 외부 저장소·제공자 측 정리", "POL-32 · POL-34 · POL-47 · POL-48 · POL-49", "—", "자동화 범위 제외", ""),
]
# ── 2026-10-17 리뷰 반영: 상태 이름, 누락 기능, 범위 설명 ──
RENAME = {"개발 완료": "구현 완료(검수 전)", "일부 개발": "일부 구현"}
spec = [(a, b, c, d, e, RENAME.get(s, s), n) for a, b, c, d, e, s, n in spec]
NOTE = {
    "계약 잠금": "변경 시 현재는 서버 전체를 차단, 영향 범위만 제한하는 기능은 '변경 영향 판정·선택적 제한'에서 개발",
    "승인 만료·재승인": "버전만 바뀐 경우와 사용 승인되지 않은 도구의 변경은 기록만 함",
    "추적·내보내기": "SIEM 전달은 'SIEM 전달' 항목에서 개발",
    "신원·상태 확인": "사용자 신원만 확인, 에이전트 신원은 자동화 범위 제외",
    "실행·통신 제한": "관리형 Linux 계정에 한정, 미인가 로컬 MCP 시험 진행 중. 게이트웨이 밖 엔드포인트 통제",
}
spec = [(a, b, c, d, e, s, NOTE.get(b, n)) for a, b, c, d, e, s, n in spec]
IMPL = "구현 완료(검수 전)"
INSERT_AFTER = {
    "고위험 건별 승인": [
        ("호출·데이터 통제", "MCP 요청·응답 중계",
         "initialize · ping · tools/list · tools/call 중계. tools/list는 승인된 스키마로 응답하고, 원격 서버 오류는 기록 후 오류로 반환. resources · prompts 등 중계하지 않는 요청은 거부",
         "POL-06 · POL-11", "MCP Python SDK", IMPL, "응답은 출력 검사를 거친 뒤 전달"),
        ("호출·데이터 통제", "정책 판정 결과 집행",
         "허용, 허용·경보 기록, 제한 실행, 승인 대기, 차단의 5가지 결과 집행. 성립한 정책을 모두 모은 뒤 정책 관리대장의 우선순위로 최종 결과 선택. "
         "관찰 모드는 실행하고 '막았을 결과'를 기록",
         "POL-22 · POL-27", "OPA · Rego", IMPL, "정책 엔진 오류·응답 누락은 차단. 허용·경보 기록은 실행을 허용하고 경고만 남김"),
    ],
    "승인 만료·재승인": [
        ("승인·카탈로그", "변경 영향 판정·선택적 제한",
         "변경된 도구와 그 도구를 쓰는 사용자·권한 범위를 판정해 해당 범위만 제한하고 나머지 도구는 계속 허용",
         "POL-37 · POL-43", "PostgreSQL · OPA", "개발 예정", "현재는 승인 도구의 설명·스키마 변경 시 서버 전체 차단"),
    ],
    "추적·내보내기": [
        ("운영·감사", "판정 증적 항목",
         "호출마다 추적 ID, 요청 ID, 정책 입력, 정책 ID와 버전, 판단 사유, 판정 결과, 제한 내용, 서버 전달 시도·실행 여부, 실행 환경, 이전 기록 해시 저장",
         "POL-38", "PostgreSQL", IMPL, "응답 본문은 저장하지 않고 해시·크기·처리 결과만 보관. 300자를 넘는 인자 값은 앞 120자와 해시만 보관"),
        ("운영·감사", "SIEM 전달",
         "판정·감사 이벤트를 SIEM 수집 형식(syslog·CEF 또는 OCSF)으로 전달하고, 전달 실패 시 재전송 대기열과 실패 기록 유지",
         "POL-38 · POL-42", "OpenTelemetry Collector", "개발 예정", "확장 범위. 현재는 호출 추적 전송과 해시가 붙은 감사 기록 내보내기만 지원"),
    ],
}
APPEND_BEFORE_EXCL = [
    ("효과 평가(제품 외)", "통제 적용 전후 효과 비교",
     "같은 시나리오를 통제 적용 전후로 실행해 결과를 비교하고 평가지표 6개를 산출하는 별도 평가 도구",
     "—", "자체 구현", "개발 예정", "제품 기능이 아닌 평가 도구. 평가지표 정의는 팀 평가계획을 따름(정의 확정 필요)"),
]
_new = []
for row in spec:
    if row[0] == "자동화 범위 제외" and APPEND_BEFORE_EXCL:
        _new += APPEND_BEFORE_EXCL
        APPEND_BEFORE_EXCL = []
    _new.append(row)
    _new += INSERT_AFTER.get(row[1], [])
spec = _new

SPEC_HEAD = ["번호", "대분류", "기능명", "기능 설명", "대응 정책", "구현 수단", "개발 상태", "비고"]
header(ws, SPEC_FIRST - 1, SPEC_HEAD, [6, 16, 24, 52, 22, 26, 14, 36])
status_fill = {"구현 완료(검수 전)": DONE, "일부 구현": PART, "개발 예정": PLAN, "자동화 범위 제외": EXCL}
for i, row in enumerate(spec):
    r = SPEC_FIRST + i
    vals = [i + 1, *row]
    for j, v in enumerate(vals, 1):
        c = ws.cell(r, j, v)
        c.font, c.border = font(), box
        c.alignment = center if j in (1, 7) else wrap
    ws.cell(r, 7).fill = status_fill[row[5]]
SPEC_LAST = SPEC_FIRST + len(spec) - 1
_start = SPEC_FIRST
for _i in range(1, len(spec) + 1):
    if _i == len(spec) or spec[_i][0] != spec[_start - SPEC_FIRST][0]:
        _end = SPEC_FIRST + _i - 1
        ws.cell(_start, 2).alignment = center
        if _end > _start:
            ws.merge_cells(start_row=_start, start_column=2, end_row=_end, end_column=2)
        _start = _end + 1
rng = f"$G${SPEC_FIRST}:$G${SPEC_LAST}"
for i, s in enumerate(labels):
    col = 2 + i * 2
    ws.cell(5, col).fill = status_fill[s]
    c = ws.cell(5, col + 1, f'=COUNTIF({rng},"{s}")')
    c.font, c.alignment = font(bold=True), center
ws["A5"].alignment = center
dv = DataValidation(type="list", formula1='"구현 완료(검수 전),일부 구현,개발 예정,자동화 범위 제외"', allow_blank=False)
ws.add_data_validation(dv)
dv.add(f"G{SPEC_FIRST}:G{SPEC_LAST}")
for s, f_ in status_fill.items():
    ws.conditional_formatting.add(f"G{SPEC_FIRST}:G{SPEC_LAST}", CellIsRule(operator="equal", formula=[f'"{s}"'], fill=f_))
ws.freeze_panes = f"C{SPEC_FIRST}"
ws.auto_filter.ref = f"A{SPEC_FIRST - 1}:H{SPEC_LAST}"

# ───────────────────────── 2. 개발 WBS ─────────────────────────
w2 = wb.create_sheet("개발 WBS")
title(w2, "MCP 보안 거버넌스 솔루션 개발 WBS",
      "단계 점수 0 = 미확인 · 0.5 = 부분 · 1 = 충족. 진척률 = 다섯 단계 점수의 평균. 현재 개발 작업의 점수는 10-15 검수 스냅샷(snapshot.json), "
      "G01.05는 10-15 밤 배포 결과로 작성. 추가 개발 일정은 제안안으로 팀 확정이 필요함. 2026-10-17 리뷰 반영(G02.06·G06.06·G10.05 추가).", 26)
POL = {
    "G01.01": "POL-01", "G01.02": "POL-01 · 03 · 39", "G01.03": "POL-02 · 23", "G01.04": "POL-38",
    "G02.01": "POL-08 · 38", "G02.02": "POL-11 · 37", "G02.03": "POL-37 · 40 · 44", "G02.04": "POL-11 · 12",
    "G03.01": "POL-19 · 21", "G03.02": "POL-20", "G03.03": "POL-22 · 23 · 24 · 25 · 26", "G03.04": "POL-27 · 28 · 36",
    "G04.01": "POL-24 · 29", "G04.02": "POL-30", "G04.03": "POL-04 · 29", "G04.04": "POL-22",
    "G05.01": "POL-12", "G05.02": "POL-12 · 17", "G05.03": "POL-12 · 42", "G05.04": "POL-12",
    "G06.01": "POL-38", "G06.02": "POL-38", "G06.03": "POL-42", "G06.04": "POL-38",
    "G07.01": "POL-44 · 45", "G07.02": "POL-44 · 46", "G07.03": "POL-41 · 45", "G07.04": "POL-48 · 50",
    "G08.01": "POL-19", "G08.02": "—", "G08.03": "POL-08 · 27", "G08.04": "—",
    "G09.01": "—", "G09.02": "—", "G09.03": "—", "G09.04": "—",
    "G10.01": "—", "G10.02": "—", "G10.03": "—", "G10.04": "—",
}
GOALS = {"G01": "도입·공급망 검증", "G02": "승인·계약 관리", "G03": "신원·호출 권한", "G04": "데이터·비신뢰 결과 보호",
         "G05": "엔드포인트 집행", "G06": "감사·로그 전달", "G07": "종료·폐기", "G08": "가입·설치·하네스 운영",
         "G09": "자원·연결 지표", "G10": "개발 협업·근거 관리"}
# 추가 개발: id, 작업, 완료 기준, 정책, 계획 주차(시작, 끝) — 주차 인덱스는 WEEKS 기준
NEW = [
    ("G01.06", "운영 서버 이미지 주기 재검사·기한 초과 격리", "실행 중 이미지 재검사 결과가 기한을 넘기면 자동 격리되고 기록된다", "POL-39", (4, 5)),
    ("G02.05", "데이터·기능 단위 사용자 동의 확인", "동의가 없는 데이터·기능 호출이 차단되고 확인 요청이 나간다", "POL-08", (2, 3)),
    ("G03.05", "연결 직전 DNS 확인·IP 고정 접속", "DNS 재바인딩·리디렉션·미승인 OAuth 조회 대상 반례가 모두 차단된다", "POL-10 · 40", (0, 1)),
    ("G03.06", "단일 조회 반환 건수·크기 상한", "상한 초과·전체 폴더 조회가 차단되고 정상 조회는 통과한다", "POL-35", (2, 3)),
    ("G03.07", "변경 요청 멱등 키", "같은 변경의 재전송·재시도가 한 번만 실행된다", "POL-36", (3, 3)),
    ("G03.08", "설정·실행 인자·오류 응답 인증정보 노출 차단", "인증정보 원문이 설정·인자·오류 응답에 남지 않는다", "POL-14", (1, 1)),
    ("G04.05", "외부 전송 목적 결속", "목적·수신처·등급 조합이 승인과 다르면 전송이 차단된다", "POL-26", (2, 3)),
    ("G04.06", "도구별 허용 입력 항목·입력 마스킹", "허용 밖 입력 항목과 민감정보가 전달되지 않는다", "POL-31", (2, 3)),
    ("G04.07", "세션 내 중요정보 표시 전파·서버 간 전달 경계", "승인 없는 서버 간 중요정보 전달이 차단된다", "POL-33", (3, 4)),
    ("G06.05", "정책 배포 후 경보 자체 시험", "배포 직후 합성 이벤트에 대한 경보 결과가 기록된다", "POL-42", (4, 5)),
    ("G07.05", "탐지 시 서버·도구 자동 중지", "미승인 변경·이상 호출 탐지 시 해당 서버·도구가 자동 중지된다", "POL-43", (4, 5)),
    ("G07.06", "서명된 폐기 목록과 복원 후 대조", "백업 복원 후 폐기된 연결·인증정보가 다시 허용되지 않는다", "POL-50", (5, 6)),
    ("G02.06", "변경 영향 판정·선택적 제한", "변경된 도구와 영향 받는 사용자·권한만 제한되고 나머지 도구 호출은 계속 허용된다", "POL-37 · 43", (5, 6)),
    ("G06.06", "SIEM 전달·전달 실패 재전송", "판정·감사 이벤트가 SIEM 형식으로 전달되고 수신 장애 뒤 누락 없이 재전송된다", "POL-38 · 42", (5, 6)),
    ("G10.05", "통제 적용 전후 효과 비교 평가 도구(제품 외)", "같은 시나리오의 적용 전후 결과와 평가지표 6개가 재현 가능하게 산출된다", "—", (6, 7)),
    ("G08.05", "하네스–게이트웨이 구간 TLS", "현장 배치의 하네스 연결이 TLS로만 동작하고 평문 접속은 거부된다", "POL-16", (0, 1)),
]
WEEKS = ["10월 4주", "10월 5주", "11월 1주", "11월 2주", "11월 3주", "11월 4주", "12월 1주", "12월 2주"]
VERIFY_WEEKS = (6, 7)  # 기존 작업의 남은 실기기 확인·완료 검수

H2 = ["WBS ID", "대분류", "작업", "완료 기준", "대응 정책", "구분", "구현", "회귀 시험", "기기 배포", "실기기 확인",
      "완료 검수", "진척률", "상태", "남은 작업"]
FIRST2 = 9
header(w2, FIRST2 - 1, H2, [9, 16, 36, 46, 18, 11, 7, 7, 7, 8, 7, 9, 11, 46])
gc0 = len(H2) + 1
w2.cell(FIRST2 - 2, gc0, "개발 계획(안)").font = font(bold=True)
w2.merge_cells(start_row=FIRST2 - 2, start_column=gc0, end_row=FIRST2 - 2, end_column=gc0 + len(WEEKS) - 1)
w2.cell(FIRST2 - 2, gc0).alignment = center
for k, wk in enumerate(WEEKS):
    c = w2.cell(FIRST2 - 1, gc0 + k, wk)
    c.font, c.fill, c.alignment, c.border = font(bold=True, color="FFFFFF", size=9), HEAD, center, box
    w2.column_dimensions[L(gc0 + k)].width = 7

rows = []
for tid, t in snap.items():
    sc = [(t.get("stage_scores") or t.get("scores"))[s] for s in STAGES]
    rows.append((tid, t["title"], t["completion_condition"], POL.get(tid, "—"), "현재 개발", sc, t["known_gap"], None))
rows.append(("G01.05", "승인 소스 MCP 격리 실행기", "승인된 커밋만 고정 방식으로 빌드·실행하고 심사 목적지만 허용하며, 철회·종료 시 정지한다",
             "POL-09 · 46", "현재 개발", [1, 1, 1, 0.5, 0], "등록 해제·종료·빌드 중 승인 철회의 실기기 정지 시험이 남았다.", None))
for tid, name, cond, pol, wk in NEW:
    rows.append((tid, name, cond, pol, "추가 개발", [0, 0, 0, 0, 0], "신규 개발", wk))
rows.sort(key=lambda x: x[0])

r = FIRST2
for tid, name, cond, pol, kind, sc, gap, wk in rows:
    goal = tid[:3]
    vals = [tid, f"{goal} {GOALS[goal]}", name, cond, pol, kind, *sc]
    for j, v in enumerate(vals, 1):
        c = w2.cell(r, j, v)
        c.font, c.border = font(color="0000FF" if 7 <= j <= 11 else "000000"), box
        c.alignment = center if j in (1, 6) or j >= 7 else wrap
    c = w2.cell(r, 12, f"=AVERAGE(G{r}:K{r})")
    c.number_format, c.font, c.alignment, c.border = "0%", font(), center, box
    c = w2.cell(r, 13, f'=IF(G{r}=0,"개발 예정",IF(G{r}<1,"일부 구현",IF(L{r}=1,"검수 완료","구현 완료(검수 전)")))')
    c.font, c.alignment, c.border = font(), center, box
    c = w2.cell(r, 14, gap)
    c.font, c.alignment, c.border = font(size=9), wrap, box
    span = wk if wk else (VERIFY_WEEKS if kind == "현재 개발" and sc[4] < 1 else None)
    for k in range(len(WEEKS)):
        c = w2.cell(r, gc0 + k)
        c.border = box
        if span and span[0] <= k <= span[1]:
            c.fill = fill("5B9BD5") if wk else fill("A9D08E")
    if kind == "추가 개발":
        for j in (1, 2, 3, 6):
            w2.cell(r, j).fill = PLAN
    r += 1
LAST2 = r - 1

# summary
labs = [("전체 작업", f"=COUNTA(A{FIRST2}:A{LAST2})"),
        ("현재 개발", f'=COUNTIF(F{FIRST2}:F{LAST2},"현재 개발")'),
        ("추가 개발", f'=COUNTIF(F{FIRST2}:F{LAST2},"추가 개발")'),
        ("구현 완료(검수 전)", f'=COUNTIF(M{FIRST2}:M{LAST2},"구현 완료(검수 전)")'),
        ("일부 구현", f'=COUNTIF(M{FIRST2}:M{LAST2},"일부 구현")'),
        ("개발 예정", f'=COUNTIF(M{FIRST2}:M{LAST2},"개발 예정")'),
        ("검수 완료", f'=COUNTIF(M{FIRST2}:M{LAST2},"검수 완료")'),
        ("현재 개발 진척률", f'=AVERAGEIF(F{FIRST2}:F{LAST2},"현재 개발",L{FIRST2}:L{LAST2})'),
        ("전체 진척률", f"=AVERAGE(L{FIRST2}:L{LAST2})")]
for i, (lab, fm) in enumerate(labs):
    rr, cc = 3 + i // 5, 1 + (i % 5) * 3
    a = w2.cell(rr, cc, lab)
    a.font, a.fill, a.alignment, a.border = font(bold=True), SUB, center, box
    w2.merge_cells(start_row=rr, start_column=cc, end_row=rr, end_column=cc + 1)
    b = w2.cell(rr, cc + 2, fm)
    b.font, b.alignment, b.border = font(bold=True, size=11), center, box
    if "진척률" in lab:
        b.number_format = "0.0%"
w2["A6"] = "범례:"
w2["A6"].font = font(bold=True, size=9)
w2["B6"], w2["B6"].fill = "추가 개발 작업", PLAN
w2["C6"], w2["C6"].fill = "계획: 신규 개발", fill("5B9BD5")
w2["D6"], w2["D6"].fill = "계획: 실기기 확인·완료 검수", fill("A9D08E")
w2["E6"] = "파란 숫자 = 단계 점수 입력값(0 / 0.5 / 1)"
for c in ("B6", "C6", "D6", "E6"):
    w2[c].font = font(size=9, color="0000FF" if c == "E6" else "000000")
sdv = DataValidation(type="list", formula1='"0,0.5,1"', allow_blank=False)
w2.add_data_validation(sdv)
sdv.add(f"G{FIRST2}:K{LAST2}")
mr = f"M{FIRST2}:M{LAST2}"
for s, f_ in [("구현 완료(검수 전)", DONE), ("일부 구현", PART), ("개발 예정", PLAN), ("검수 완료", fill("A9D08E"))]:
    w2.conditional_formatting.add(mr, CellIsRule(operator="equal", formula=[f'"{s}"'], fill=f_))
w2.freeze_panes = f"D{FIRST2}"
w2.auto_filter.ref = f"A{FIRST2 - 1}:N{LAST2}"

# ───────────────────────── 3. 정책 대응 ─────────────────────────
w3 = wb.create_sheet("정책 대응")
title(w3, "기술통제 정책 35개 대응 현황", "현재 = 개발 브랜치 c0fbab3 정적 판정 · 개발 후 = 개발 WBS 추가 개발 완료 시 · 분류는 팀 정책 커버리지 표 기준", 7)
CORE = [8, 10, 11, 16, 19, 20, 21, 22, 23, 25, 26, 29, 31, 35, 40]
PARTL = [1, 13, 14, 15, 18, 24, 27, 28, 30, 33, 36, 37, 38, 39, 41, 42, 43, 44, 45, 50]
FULL_NOW = {11, 21, 22, 23, 29, 15, 18, 24, 27, 28, 30, 37, 38, 44}
NONE_NOW = {50}
LIMIT = {19: "에이전트 신원 증명 불가", 20: "검증된 에이전트 주체 없음", 25: "외부 서비스 자원 등급은 제공자 보유",
         41: "제공자 측 무효화 관측 불가", 45: "제공자 측 회수 관측 불가", 1: "서명 없는 배포물은 검증 대상 없음",
         13: "원격 OAuth 인증 과정 미참여"}
WBS_OF = {8: "G02.05", 10: "G03.05", 40: "G03.05", 14: "G03.08", 16: "G08.05", 26: "G04.05", 31: "G04.06", 33: "G04.07",
          35: "G03.06", 36: "G03.07", 39: "G01.06", 42: "G06.05 · G06.06", 43: "G07.05 · G02.06", 50: "G07.06",
          37: "G02.06", 38: "G06.06"}
names = {int(p["source_id"][4:]): " ".join(p["fields"]["정책명"].split())
         for p in json.load(open(POLICIES, encoding="utf-8"))["policies"]
         if p["sheet"] == "(본)정책 최종본" and p["source_id"].startswith("POL-")}
header(w3, 5, ["정책 ID", "정책명", "자동화 분류", "현재", "개발 후", "관련 추가 개발", "자동화 한계"], [9, 34, 18, 11, 11, 14, 34])
r = 6
for n in sorted(CORE + PARTL):
    now = "구현" if n in FULL_NOW else "미구현" if n in NONE_NOW else "일부 구현"
    after = "일부 구현" if n in LIMIT else "구현"
    vals = [f"POL-{n:02d}", names[n], "핵심 자동화" if n in CORE else "일부 자동화", now, after, WBS_OF.get(n, ""), LIMIT.get(n, "")]
    for j, v in enumerate(vals, 1):
        c = w3.cell(r, j, v)
        c.font, c.border = font(), box
        c.alignment = wrap if j in (2, 7) else center
    r += 1
L3 = r - 1
for col in ("D", "E"):
    for s, f_ in [("구현", DONE), ("일부 구현", PART), ("미구현", fill("F8CBAD"))]:
        w3.conditional_formatting.add(f"{col}6:{col}{L3}", CellIsRule(operator="equal", formula=[f'"{s}"'], fill=f_))
# summary block to the right
w3["I5"], w3["J5"], w3["K5"] = "상태", "현재", "개발 후"
for c in ("I5", "J5", "K5"):
    w3[c].font, w3[c].fill, w3[c].alignment, w3[c].border = font(bold=True, color="FFFFFF"), HEAD, center, box
for i, s in enumerate(["구현", "일부 구현", "미구현"]):
    rr = 6 + i
    w3.cell(rr, 9, s)
    w3.cell(rr, 10, f'=COUNTIF($D$6:$D${L3},I{rr})')
    w3.cell(rr, 11, f'=COUNTIF($E$6:$E${L3},I{rr})')
w3.cell(9, 9, "구현 비율")
w3.cell(9, 10, f"=(J6+J7*0.5)/COUNTA($A$6:$A${L3})")
w3.cell(9, 11, f"=(K6+K7*0.5)/COUNTA($A$6:$A${L3})")
for rr in range(6, 10):
    for cc in (9, 10, 11):
        c = w3.cell(rr, cc)
        c.font, c.alignment, c.border = font(bold=(cc == 9)), center, box
        if rr == 9 and cc > 9:
            c.number_format = "0.0%"
w3.cell(10, 9, "구현 비율 = (구현 + 일부 구현 × 0.5) ÷ 35").font = font(size=9, color="595959")
w3.column_dimensions["I"].width = 12
w3.freeze_panes = "C6"

for sh in wb.worksheets:
    sh.sheet_view.showGridLines = False
    sh.page_setup.orientation = "landscape"
    sh.page_setup.fitToWidth = 1
    sh.sheet_properties.pageSetUpPr.fitToPage = True
    sh.page_setup.fitToHeight = 0
wb.calculation.fullCalcOnLoad = True
OUTDIR.mkdir(parents=True, exist_ok=True)
wb.save(OUT)
record["feature_spec"] = [dict(zip(["category", "feature", "description", "policies", "means", "status", "note"], r)) for r in spec]
record["wbs"] = [{"id": t[0], "task": t[1], "completion": t[2], "policies": t[3], "kind": t[4],
                  "scores": dict(zip(STAGES, t[5])), "remaining": t[6],
                  "planned_weeks": [WEEKS[t[7][0]], WEEKS[t[7][1]]] if t[7] else None} for t in rows]
record["policy_coverage"] = [{"policy": f"POL-{n:02d}", "name": names[n], "class": "핵심 자동화" if n in CORE else "일부 자동화",
                              "now": "구현" if n in FULL_NOW else "미구현" if n in NONE_NOW else "일부 구현",
                              "after": "일부 구현" if n in LIMIT else "구현", "planned": WBS_OF.get(n, ""),
                              "limit": LIMIT.get(n, "")} for n in sorted(CORE + PARTL)]
(OUTDIR / "feature-spec.json").write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print("rows spec", len(spec), "wbs", LAST2 - FIRST2 + 1, "pol", L3 - 5)
