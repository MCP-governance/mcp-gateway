"""Re-score the WBS after the 2026-10-15 implementation, from evidence kept in the repository.

Only items with new evidence change. Every score that rises is backed by a file under
research/llm-wiki/analysis/wbs-1015 (lab results on the merged source, deploy records, appliance and
PJ1 queries) or a subagent work report, and the checks below fail the build when that evidence says
otherwise. Real-device scores stay where PJ1 did not exercise the condition (no harness run today).
"""
import json
import shutil
import subprocess
from datetime import datetime, timezone

from build_snapshot import REPO, WIKI, STAGES, digest, read, write_outputs

E = 'research/llm-wiki/analysis/wbs-1015/'
REPORTS = 'research/llm-wiki/status/reports/2026-10-15-'
R_MAIN, R_A, R_B, R_C = (REPORTS + 'wbs-implementation.md', REPORTS + 'endpoint-evidence.md',
                         REPORTS + 'intake-identity.md', REPORTS + 'termination-dispatch.md')
R_D = REPORTS + 'inspection-corpus.md'
LAB, DEPLOY, APPLIANCE = E + 'lab-results.jsonl', E + 'deploy.json', E + 'appliance-evidence.json'
MERGES = {'A': 'b0bfa2d', 'B': '8535c80', 'C': '9ee2fb3', 'D': 'e3e0b6f'}


def git(*args):
    return subprocess.run(['git', '-C', str(REPO), *args], capture_output=True, text=True)


def lab_results():
    rows = [json.loads(line) for line in (REPO / LAB).read_text(encoding='utf-8').splitlines() if line.strip()]
    return {row['test']: row for row in rows}


def item(scores, notes, gap, tests=(), evidence=(), workstream=None):
    return {'scores': dict(zip(STAGES, scores)), 'notes': dict(zip(STAGES, notes)), 'gap': gap,
            'tests': list(tests), 'evidence': list(evidence), 'workstream': workstream}


NO_ACCEPT = '완료 조건 전체의 검수 전이며 실기기 공백이 남아 0점.'
DEPLOYED = '통합 브랜치를 솔루션 기기에 field up으로 배포한 판본에 포함(배포 기록의 commit이 병합 commit을 포함).'

CONFIGS = {
    'G01.01': item((1, 1, 1, 0, 0), (
        '도입 승인마다 고정 커밋·파일 해시 목록·라이선스를 기록하고 내부 Git 보관본을 다시 해시해 대조, 누락·불일치는 보류. 제공자 운영 원격 서비스는 해시 대신 엔드포인트·광고 버전·계약 해시.',
        '병합 소스에서 격리 PostgreSQL+OPA 도입·신원 시험과 출처 단위 시험 통과.', DEPLOYED,
        '오늘 기기에서 실제 공개 MCP 저장소의 새 도입 승인을 수행하지 않았다.', NO_ACCEPT),
        '실제 도입 요청으로 보관본 해시 대조·보류를 기기에서 확인해야 한다. 패키지 레지스트리 도입물은 경로가 없다.',
        ('intake_identity_pg_check.py', 'provenance_check.py', 'intake_validation_test.py'), (R_B,), 'B'),
    'G01.02': item((1, 1, 1, 0.5, 0), (
        '검사기·판본·Trivy DB 갱신 시각을 보고서마다 저장, 검사 실패·누락·DB 7일 초과는 보류, 치명 발견은 다른 관리자의 기한부 위험 수용으로만 통과하고 만료 시 보류 복귀.',
        '병합 소스에서 격리 시험·단위 시험 통과.', DEPLOYED,
        '기기 도입 워커의 Trivy DB를 실제로 갱신(10-06→10-15)해 신선도 경로를 확인했다. 실제 도입 검사 실행은 하지 않았다.', NO_ACCEPT),
        '실제 도입 검사에서 신선도·치명 발견 보류를 확인해야 한다.',
        ('intake_identity_pg_check.py', 'provenance_check.py'), (R_B, APPLIANCE), 'B'),
    'G01.03': item((1, 1, 1, 0.5, 0), (
        '도구마다 사람이 적은 목적·자산·행위·외부 목적지, 범위 없는 도구는 tools/list 제외·호출 MCP-REGISTRY-002.',
        '병합 소스 격리 시험에서 목록·호출 양쪽 제외 확인.', DEPLOYED,
        '배포 직후 범위 없는 도구가 실제로 꺼졌고, 기존 신청 목적대로 범위를 기록한 4개 읽기 도구만 PJ1 SDK 호출에서 목록·실행됐다. 독립 효과 기반 범위 준수 시험은 하지 않았다.', NO_ACCEPT),
        '외부 목적지는 기록·표시만 하며 집행은 PAC 전송 검사에 맡긴다. 독립 효과로 범위 준수를 보는 시험이 남았다.',
        ('intake_identity_pg_check.py',), (R_B, R_MAIN, APPLIANCE), 'B'),
    'G01.04': item((1, 1, 1, 0.5, 0), (
        '공급자 원본(B 도입 해시)·설치 해시(하트비트)·수신 원본 해시·비밀 제거 projection 해시와 변환 이름·수집기를 기록하고 서버가 저장 필드로 재계산해 일치/불일치/미보고.',
        '병합 소스에서 격리 PostgreSQL 증거 시험·단위 시험 통과.', DEPLOYED,
        'PJ1 실데이터: 설정 4건·OS 이벤트 247건이 모두 서버 재계산 해시와 일치. 바이트 변조 탐지는 격리 시험에서만 확인.', NO_ACCEPT),
        '서버는 원본 바이트를 검증할 수 없다(침해된 root에는 증명이 아님). 설치 파일 해시 사슬의 실기기 대조가 남았다.',
        ('endpoint_evidence_pg_check.py', 'endpoint_evidence_check.py'), (R_A, APPLIANCE), 'A'),
    'G02.01': item((1, 1, 1, 0.5, 0), (
        '도입 승인·원격 계약 검토·위험 수용·도구 범위 심사·건별 호출 승인에서 신청자=승인자 거부와 시도 기록, append-only 승인 기록과 무효 주석.',
        '병합 소스 격리 시험에서 독립성 거부·append-only 트리거 확인.', DEPLOYED,
        '기기 원장: 범위 심사 3건이 신청자와 다른 root 명의로 기록, 에이전트 자가 승인 시험 58건(744–800·803)에 무효 주석.', NO_ACCEPT),
        '실제 운영에서 신청자=승인자 거부 화면 흐름은 확인하지 않았다.',
        ('intake_identity_pg_check.py', 'intake_identity_test.py'), (R_B, R_MAIN, APPLIANCE), 'B'),
    'G02.03': item((1, 1, 1, 0, 0), (
        '만료→P-APPROVAL-EXPIRY-001, 철회→MCP-REGISTRY-001+목록 제외, 계약 변경→MCP-CATALOG-001, 연장은 계약 일치·신청 승인·전 도구 범위 심사 때만.',
        '병합 소스 격리 시험 통과.', DEPLOYED,
        '실제 하네스에서 사용자 동의와 운영자 승인을 따로 기록하는 흐름은 하지 않았다(관리 계정 미로그인).', NO_ACCEPT),
        '실제 하네스 E2E가 남았다. 철회 뒤 같은 승인으로 다시 등록할 수 있는 기존 경로는 결정 대기.',
        ('intake_identity_pg_check.py',), (R_B,), 'B'),
    'G02.04': item((1, 1, 1, 0.5, 0), (
        '관리형 정책 파일의 서버 집합과 tools/list가 같은 판단(pac.servers_for)을 쓰고 허용 안 된 사용자·철회·범위 미심사 서버를 뺀다.',
        '병합 소스 격리 시험에서 렌더링 파일 직접 확인.', DEPLOYED,
        'PJ1 장치 정책이 사용자가 볼 수 있는 3개 서버만 담고 서버 계산 해시와 일치. 모델→MCP→판정 연결은 하지 않았다.', NO_ACCEPT),
        '하네스 모델 호출로 최소 집합을 확인해야 한다.',
        ('intake_identity_pg_check.py',), (R_B, APPLIANCE), 'B'),
    'G03.01': item((1, 1, 1, 0.5, 0), (
        '전송 계층 토큰만으로 주체를 정하고 발급자·대상·범위·만료·철회·장치 정책을 업스트림 전에 검사.',
        '병합 소스에서 refresh 계열 철회·경쟁(PostgreSQL)과 단위 시험 통과.', DEPLOYED,
        'PJ1 장치 토큰이 정책 불일치 동안 진입점에서 403(ENDPOINT-MANAGED-001)으로 거부되고 동기화 뒤 허용됨. 다른 발급자·대상 토큰의 실기기 시험은 하지 않았다.', NO_ACCEPT),
        '하네스 경로의 audience·scope 반례 실기기 시험이 남았다.',
        ('oauth_rotation_pg_check.py', 'token_revocation_pg_check.py', 'oauth_rotation_check.py'), (R_C, APPLIANCE), 'C'),
    'G03.02': item((1, 1, 1, 0, 0), (
        '신뢰할 에이전트 신원 확인 수단이 없으므로 act·may_act·on_behalf_of·위임 헤더로 대리 실행을 주장하는 호출을 PAC-05-DELEGATION-UNSUPPORTED로 거부(관찰 모드 포함)하고 Console 정책 목록에 "지원 안 함". clientInfo·User-Agent는 출처 미검증 기록만.',
        '병합 소스 Rego 91건(위임 4건)과 위임 단위·격리 시험 통과.', DEPLOYED,
        '실제 위임 시도는 하지 않았다.', NO_ACCEPT),
        '위임 활성화는 하지 않았다. 검증 가능한 에이전트 신원이 생기면 교집합 구현이 필요하다.',
        ('pac_delegation_check.py', 'intake_identity_pg_check.py'), (R_B,), 'B'),
    'G03.03': item((1, 1, 1, 0.5, 0), (
        '요청마다 행위·인자·자산·목적지를 다시 분류하고 실행 직전 재판정.',
        '병합 소스에서 보안 경계 시험과 실제 Gitea MCP 부수효과 시험(인자 변형 0건) 통과.', DEPLOYED,
        'PJ1 SDK 호출에서 승인 인자 밖 list_commits가 업스트림 전 PAC-01로 차단(전송 의도 기록 없음).', NO_ACCEPT),
        '하네스 경로와 쓰기 도구의 독립 효과 0건 실기기 확인이 남았다.',
        ('security_edges_check.py', 'dispatch_effect_lab.py'), (R_C, APPLIANCE), 'C'),
    'G03.04': item((1, 1, 1, 0.5, 0), (
        '예약 원자성, 전송 직전 durable intent(같은 문장에서 예약·주체·서버 재확인), 답 없는 쓰기의 자동 재시도 금지·중복 거부·관리자 확인, 승인은 승인한 요청에 1회.',
        '병합 소스: intent·예약 PostgreSQL 47건, 실제 Gitea MCP 부수효과 45건(동시 동일 12건→1, 프로세스 SIGKILL 후 미재시도) 통과.', DEPLOYED,
        'PJ1 실제 호출 8건의 전송 의도가 모두 resolved로 정산. 실기기 경쟁 시험은 하지 않았다.', NO_ACCEPT),
        '실기기 동시성·중단 시험과 상태 의존 서버(DEV-29)가 남았다.',
        ('dispatch_intent_pg_check.py', 'dispatch_effect_lab.py'), (R_C, APPLIANCE), 'C'),
    'G04.04': item((1, 1, 1, 0, 0), (
        '검사기·PDP·목록 누락과 형식 오류는 업스트림 전 차단. 네이티브 Gitleaks 실패는 예외(보류)로 처리하고 시간초과 검사는 슬롯을 끝까지 점유.',
        '병합 소스 보안 경계 시험 통과, 배포 이미지에서 Gitleaks 실패 입력·슬롯 회귀 확인.', DEPLOYED,
        '실기기에서 검사기 장애를 일으키는 시험은 하지 않았다.', NO_ACCEPT),
        '독립 수신 측에서 요청 0건을 보는 실기기 장애 시험이 남았다.',
        ('security_edges_check.py', 'oss_audit_test.py', 'mcp_result_services_check.py'), (R_MAIN, DEPLOY), None),
    'G05.03': item((1, 1, 1, 0.5, 0), (
        '자동·수동·OS 이벤트 출처 라벨, 원본 해시·시각, 7일 내 같은 원본 해시 중복 방지, 기존 채널 신선도·last success.',
        '병합 소스 격리 PostgreSQL 증거 시험과 엔드포인트 단위 시험 통과.', DEPLOYED,
        'PJ1 실데이터에서 자동 수집 설정 기록과 OS 이벤트가 라벨·해시 일치로 도착. 오프라인·중복 실기기 시험은 하지 않았다.', NO_ACCEPT),
        '실제 MCP 앱 프로세스 식별·다른 OS와 실기기 오프라인/중복 시험이 남았다. 출처 라벨은 장치 키 소유자의 자기 신고다.',
        ('endpoint_evidence_pg_check.py', 'endpoint_evidence_check.py', 'endpoint_inventory_check.py'), (R_A, APPLIANCE), 'A'),
    'G06.01': item((0.5, 0.5, 1, 0, 0), (
        '호출↔엔드포인트 기록 연관 API(장치·사용자 둘 다 일치, 시간 창), traceparent 형식 검증 기록. 하네스 이벤트·독립 수신기 시각은 연결하지 않는다.',
        '격리 PostgreSQL 시험이 연관 규칙을 확인.', DEPLOYED, '하네스 실행이 없어 실기기 연결 사례가 없다.', NO_ACCEPT),
        '하네스 이벤트와 독립 수신기 시각 연결이 남았다.',
        ('endpoint_evidence_pg_check.py',), (R_A,), 'A'),
    'G06.02': item((1, 1, 1, 0.5, 0), (
        '요청 전 차단·허용 후 실행·업스트림 오류·출력 보류·실행 확인 필요(전송 의도 미정산)를 따로 표시.',
        '병합 소스에서 실제 Gitea MCP 부수효과 수와 원장 시도·실행 표시 대조 통과.', DEPLOYED,
        '이전 실기기 표본 유지. 오늘 PJ1 호출의 실행·차단이 원장·전송 의도와 일치.', NO_ACCEPT),
        '독립 수신기 성공 효과를 화면에서 대조하는 실기기 시험이 남았다.',
        ('dispatch_effect_lab.py', 'security_edges_check.py'), (R_C, APPLIANCE), 'C'),
    'G06.03': item((1, 1, 1, 0.5, 0), (
        '목록마다 전체 건수·반환 창·커서, 일부 표시 표식, 채널 상태·last success·신선도, listener 상세.',
        '병합 소스 격리 PostgreSQL에서 450/260/230건을 200건 창으로 겹침·누락 없이 끝까지 확인.', DEPLOYED,
        'PJ1 실데이터는 200건을 넘지 않아 페이지 이동을 실기기로 보지 못했다.', NO_ACCEPT),
        '200건 초과 실기기 데이터의 페이지 이동 확인이 남았다.',
        ('endpoint_evidence_pg_check.py', 'endpoint_snapshot_check.py'), (R_A, APPLIANCE), 'A'),
    'G06.04': item((1, 1, 1, 0.5, 0), (
        '전달 자료마다 원본·projection 해시·변환 이름·수집기·수신 시각, 서버 재계산으로 일치/불일치/미보고.',
        '병합 소스 격리 시험에서 일치·변조 불일치·옛 보고 미보고 확인.', DEPLOYED,
        'PJ1 실데이터 251건 모두 일치. 실기기 변조 탐지는 하지 않았다.', NO_ACCEPT),
        '원본 바이트 자체는 서버가 검증할 수 없다.',
        ('endpoint_evidence_pg_check.py', 'endpoint_evidence_check.py'), (R_A, APPLIANCE), 'A'),
    'G07.01': item((1, 1, 1, 0, 0), (
        'refresh 계열 철회 시 파생 접근 토큰 거부, 회전 재사용 시 계열 폐기, 발급·철회 경쟁 원자성, 장치 회수 시 기존 장치 토큰 거부. 접근 토큰 하나의 폐기는 그 토큰만(D-99).',
        '병합 소스 토큰 폐기 PostgreSQL 22건·회전 3건·단위 시험 통과.', DEPLOYED,
        '오늘 실기기 폐기 시험은 하지 않았다.', NO_ACCEPT),
        '실기기 폐기·제공자 측 자원 자격은 G07.03에서 따로 본다.',
        ('token_revocation_pg_check.py', 'oauth_rotation_pg_check.py', 'oauth_rotation_check.py'), (R_C,), 'C'),
    'G07.02': item((0.5, 1, 1, 0, 0), (
        'DB 시각·서버 행 잠금으로 차단 시각을 정하고 전송 경계가 그 뒤 호출을 거부, 종료·계정 중지 시 따뜻한 연결을 닫고 다른 프로세스에 알림. MCP 세션은 호출마다 열고 닫아 상태 의존 서버의 세션 결속은 없다(DEV-29).',
        '병합 소스 종료 시험 38건과 240회 경쟁 시험 통과.', DEPLOYED,
        '실기기 종료 시험은 하지 않았다.', NO_ACCEPT),
        '상태 의존 서버(email·Playwright)의 오래된 세션 재접근 시험이 남았다.',
        ('termination_lab.py', 'dispatch_intent_pg_check.py'), (R_C,), 'C'),
    'G07.03': item((1, 1, 1, 0, 0), (
        '보호 자원이 이전 토큰을 실제로 거부하는지(resource-rejection) 증거로 제공자 측 폐기를 판정, 확인 못 하면 미확인·만료 시각만.',
        '병합 소스에서 실제 Gitea로 폐기 전 200·후 401과 운영자 표시만 한 토큰의 잔존 수락(T2) 확인.', DEPLOYED,
        '제품 스택에는 제공자 토큰 사본이 없어 provider_side=unverified로 남는다.', NO_ACCEPT),
        '조직이 제공자 토큰 사본을 보관할 위치에 대한 사용자 결정이 필요하다.',
        ('termination_lab.py',), (R_C,), 'C'),
    'G07.04': item((0.5, 0.5, 1, 0, 0), (
        '자격 파일 제거 후 헤더 없음, 풀에 남던 이전 자격 헤더를 닫음, 종료 기록·원장·전송 의도에 토큰 원문 없음.',
        '병합 소스 종료 시험의 게이트웨이 측 범위 통과. 엔드포인트 백업·캐시 복구 시험은 없다.', DEPLOYED,
        '실기기 시험은 하지 않았다.', NO_ACCEPT),
        '직원 PC의 task 백업·캐시·내보낸 파일에서의 복구 시험이 남았다.',
        ('termination_lab.py',), (R_C,), 'C'),
    'G02.02': item((1, 1, 1, 0, 0), (
        '등록·승인된 설명·입력 스키마 해시를 잠그고 실행 직전 tools/list로 다시 대조, B 변경은 전달 전 MCP-CATALOG-001, A 복귀 시 A 관찰.',
        '병합 소스에서 계약 A→B→A 회귀와 기동마다 재적용되는 CHECK 제약 일치 시험 통과.', DEPLOYED,
        '오늘 PJ1 실제 호출의 계약 재확인(list) 구간이 매 호출 실행됐다. 실제 서버의 B 변경 차단은 관찰하지 않았다.', NO_ACCEPT),
        '실서버 계약 변경 사례와 재시작 경계 확인이 남았다.',
        ('catalog_refresh_check.py', 'schema_check.py'), (R_MAIN, APPLIANCE), None),
    'G04.01': item((1, 1, 1, 0, 0), (
        '64 KiB 초과·형식 오류·__proto__·필수 누락은 P-INPUT-SCHEMA-001, 지시 표지는 쓰기·실행 승인/읽기 경보, U+0000 인자는 전송 전 차단하고 기록 경계에서 치환.',
        '병합 소스에서 실제 Gitea MCP 실험의 NUL 사례(인자 차단·효과 0·답 기록·해시 사슬)와 보안 경계 시험 통과. 코퍼스 게이트 측정(오탐·미탐·정책 식별자)은 D 실행 결과.', DEPLOYED,
        '실기기에서 입력 게이트 반례를 보내지 않았다.', NO_ACCEPT),
        '경로·인코딩 게이트의 실기기 반례 시험이 남았다.',
        ('dispatch_effect_lab.py', 'security_edges_check.py'), (R_D, R_MAIN), 'D'),
    'G04.02': item((1, 1, 1, 0, 0), (
        '한국어 조사가 붙은 식별자까지 18개 분류를 마스킹(라틴 문자·숫자 경계), 카드 Luhn 검증, 출력 보류·가림과 업스트림 시도·실행을 따로 표시.',
        '병합 소스에서 한국어 PII 평가(재빌드한 분석기)·결과 계약·실제 Presidio/Gitleaks 시험 통과.', DEPLOYED + ' 분석기 이미지도 이번 배포에서 저장소 Dockerfile로 다시 빌드.',
        '실기기 응답에 합성 식별자를 넣는 시험은 하지 않았다.', NO_ACCEPT),
        '합성 표본은 규칙을 읽은 같은 작성자가 썼다. 라벨 없는 사업자·계좌 번호는 가리지 않는다.',
        ('korean_pii_eval.py', 'mcp_result_contract_check.py', 'mcp_result_services_check.py'), (R_D,), 'D'),
    'G04.03': item((1, 1, 1, 0, 0), (
        '공개 코퍼스 9,463건(dev/held-out)으로 결과·인자·계약 규칙을 재고 정상 결과 오탐 91→0, 인코딩 변형을 풀어 다시 읽음. 결과 보류는 실행 방지가 아니라 응답 보류로 표기.',
        '배포 이미지에서 31개 규칙 모두 네이티브·원자/퍼징 차이 0, 규칙 자체 점검(선형 시간) 통과. 코퍼스 오탐·미탐 수치는 D 실행 결과.', DEPLOYED,
        '실기기 도구 결과로 주입 문장을 받은 사례는 없다.', NO_ACCEPT),
        '명령형 도구 응답·설득문·다국어 의역·rot13류는 다루지 않는다. 한국어 표본은 같은 작성자다.',
        ('self_checks',), (R_D, DEPLOY), 'D'),
    'G09.01': item((1, 1, 1, 0.5, 0), (
        'CPU 사용량 차이·MemTotal−MemAvailable를 단위·범위·시각·누락 상태와 함께, 셸·Docker 소켓 없이.',
        '병합 소스 지표 시험과 Console 상태 시험 통과.', DEPLOYED, '이전 실기기 표본 유지(오늘 Chrome 재확인 없음).', NO_ACCEPT),
        'Chrome 실표시 재확인이 남았다.', ('system_metrics_check.py',), (R_MAIN,), None),
    'G09.02': item((1, 1, 1, 0.5, 0), (
        '고정 Gateway의 DNS·TCP 시간(ms). 엔드포인트→게이트웨이 망 품질은 따로 표시하고 사용자 기기 왕복으로 부르지 않는다.',
        '병합 소스 지표 시험과 Console 상태 시험 통과.', DEPLOYED,
        'PJ1 망 품질 표본 22건(p50 147ms·최대 p95 554ms·지터 53ms·실패 0%)이 기기에 쌓였다. Console 표시는 오늘 재확인하지 않았다.', NO_ACCEPT),
        'Console 실표시 재확인이 남았다.', ('system_metrics_check.py',), (R_MAIN, APPLIANCE), None),
    'G09.03': item((1, 1, 1, 0.5, 0), (
        '첫 측정 전·30초 초과·시간 초과·알 수 없음·실제 0을 구분하고 오래된 값은 현재 값처럼 보이지 않음(망 품질은 fresh/stale/확인 불가).',
        '병합 소스 지표 시험과 Console 상태 시험 통과.', DEPLOYED, '이전 실기기 표본 유지.', NO_ACCEPT),
        'Chrome 실표시 재확인이 남았다.', ('system_metrics_check.py',), (R_MAIN,), None),
    'G10.02': item((1, 1, 0, 0, 0), (
        '실행마다 요청 모델·추론 강도, 제공자가 응답에 실어 온 모델만 응답 모델로 인정, 턴 오류·사용량 한도·작업 실패·모델 불일치·중단·도구 호출 0건·게이트웨이 기록 상태 구분, 원본은 비공개 runtime.',
        '병합 소스에서 협업 콘솔 시험 18건 통과(실제 캡처 CLI 출력 포함).', '협업 콘솔은 로컬 개발 화면이라 기기 배포 대상이 아니다.',
        '실제 한도 거부·성공한 codex exec --json 출력은 얻지 못했다.', NO_ACCEPT),
        '실제 한도 거부 스트림 확인이 남았다.', ('test_console.py',), (R_D,), 'D'),
    'G08.01': item((1, 0, 1, 0.5, 0), (
        '가입·등록 대기 거부·소유자 활성화·heartbeat 신선도.', '병합 소스에서 managed_enrollment_check를 돌리지 않았다(제품 계정에 시험 행을 만드는 시험).',
        DEPLOYED, '10-15 PJ1 Linux 재설치·관리자 활성화·heartbeat·정책 동기화 확인. Windows는 하지 않았다.', NO_ACCEPT),
        'Windows 실기기와 격리 환경 enrollment 회귀가 남았다.', (), (R_MAIN, APPLIANCE), None),
    'G08.03': item((1, 0.5, 1, 0, 0), (
        '신청자에게 승인 버튼 없음(서버도 거부), 요청 상세의 범위·출처·승인 기록(사용자 동의/운영자 승인 분리)·검사 기준·위험 수용, 등록 때 도구별 범위 입력. 자가 승인 시험 원장은 무효 주석.',
        '서버 측 거부는 격리 시험, 화면은 고정 응답 렌더링으로만 확인.', DEPLOYED,
        '실제 등록 요청 화면 흐름은 하지 않았다.', NO_ACCEPT),
        '실제 등록 요청을 사람 계정으로 처리하는 확인이 남았다.',
        ('intake_identity_pg_check.py',), (R_B, R_MAIN), 'B'),
}


FINDINGS = [
    ('DEV-35', 'P0', '관리 계정 루프백 허용 범위', '결정 대기',
     '관리 계정의 루프백 차단이 비인가 로컬 MCP를 막지만 하네스 로그인 콜백·내부 통신도 함께 막는다.',
     '기기 OS 이벤트에서 루프백 거부 포트·횟수를 집계.', '하네스 내부 통신만 허용하고 비인가 로컬 MCP 차단은 유지되는지 PJ1에서 확인.',
     APPLIANCE, ['G05.02', 'G08.01']),
    ('DEV-29', 'P1', 'MCP 업스트림 세션 재사용', '설계 비교',
     '호출마다 업스트림 연결·도구 목록을 다시 받아 원격 MCP 지연의 대부분을 차지한다.',
     '실제 SDK 호출의 구간별 처리 시간(연결·목록·호출).', '주체·서버 결속, TTL, 종료·철회 시 닫기를 지키는 재사용과 계약 재확인 방식 결정.',
     APPLIANCE, ['G07.02', 'G09.02']),
    ('DEV-31', 'P0', '헬퍼 토큰의 셸 자식 접근', 'PJ1 확인 필요',
     'bash 자식은 헬퍼·소켓이 없는 별도 프로필로 분리했다. 키트 재설치 뒤 실기기에서 확인한다.',
     '자체 점검·AppArmor 구문·교차 리뷰.', 'PJ1 키트 재설치 후 하네스 셸에서 헬퍼 실행이 거부되는지 확인.',
     R_MAIN, ['G05.01']),
    ('DEV-37', 'P2', 'Tailscale 직접 경로', '사용자 결정',
     '솔루션 기기의 Tailscale이 WSL2 NAT 안에 있어 DERP 중계로 통신한다.',
     'PJ1 망 품질 표본(RTT·지터).', 'WSL 미러 네트워킹 또는 호스트 Tailscale로 직접 경로 확인.',
     APPLIANCE, ['G09.02']),
    ('DEV-36', 'P2', '팀원 작업 반영 경로', '안내 필요',
     '기기 작업본을 직접 복사하면 통합 브랜치 변경이 지워진다.',
     '3-way 병합으로 기기 복사 5회를 반영.', '팀원 브랜치를 통합 브랜치 위로 옮기고 기기에는 브랜치만 배포.',
     R_MAIN, ['G10.03']),
]
STAGE_DETAIL = {
    'implementation': '코드·설정이 저장소에 있는가',
    'regression': '병합 소스에서 격리 시험이 통과했는가',
    'deployment': '솔루션 기기에 배포된 판본에 포함됐는가',
    'real_device': 'PJ1 실제 하네스·실제 MCP로 확인했는가',
    'acceptance_complete': '완료조건 전체를 검수했는가',
}


def page_sections(data, appliance, sample=None):
    """Sections of the status page that describe the current state rather than the 10-14 log diagnosis."""
    counts = data['summary']['stage_equivalent_counts']
    data['pipeline'] = [{'title': data['rubric']['stage_labels'][s], 'state': f'{counts[s]} / 40',
                         'detail': STAGE_DETAIL[s]} for s in STAGES]
    data['findings'] = [{'id': i, 'priority': p, 'title': t, 'state': st, 'detail': d, 'verification': v,
                         'next': n, 'evidence': e, 'tasks': tasks}
                        for i, p, t, st, d, v, n, e, tasks in FINDINGS]
    data['next_actions'] = [
        {'order': 1, 'title': '관리 하네스 자연어 E2E', 'tasks': 'G08.02 · G06.01',
         'done_when': 'PJ1 관리 계정의 실제 하네스가 등록된 실제 MCP를 자연어로 호출하고 원장·엔드포인트 기록이 같은 호출로 이어진다.'},
        {'order': 2, 'title': '루프백 허용 범위 결정', 'tasks': 'G05.02',
         'done_when': '하네스 내부 통신은 동작하고 비인가 로컬 MCP는 독립 효과 0으로 남는다.'},
        {'order': 3, 'title': '업스트림 세션 재사용', 'tasks': 'G07.02 · G09.02',
         'done_when': '재사용 세션이 주체·서버에 결속되고 종료·철회 시 닫히며 지연이 줄어든 것을 같은 호출로 측정한다.'},
        {'order': 4, 'title': '종료 후 잔존 접근 시험', 'tasks': 'G07.03 · G07.04',
         'done_when': '실제 원격 MCP의 자격 폐기 뒤 재접근 실패와 설정·백업 복구 시 재활성화 불가를 확인한다.'},
    ]
    if sample is None:
        call = appliance['sdk_calls'][-1]
        net = appliance['network_samples'][-1]
        t = call['timings']
        sample = {
            'title': f"{call['server_id']} · {call['tool_name']}",
            'scope': 'PJ1 관리형 단말에서 공식 MCP SDK로 호출한 실제 원격 MCP. 하네스 자연어 호출이 아니다.',
            'values': [['판정', call['decision']], ['정책', call['policy_id']],
                       ['업스트림 실행', '예' if call['upstream_executed'] else '아니오'],
                       ['전체', f"{t['total']} ms"], ['연결', f"{t['connect']} ms"], ['도구 목록', f"{t['list']} ms"],
                       ['도구 호출', f"{t['call']} ms"], ['PJ1 왕복 p50', f"{net['rtt_p50_ms']} ms"]],
            'hashes': [['원장 번호', str(call['id'])], ['기록 시각', call['created_at']],
                       ['근거 파일 SHA-256', digest(APPLIANCE)]],
        }
    data['live_sample'] = sample


def build_after_wbs_1015(extra=None, sample=None):
    """extra: further item configs (the inspection workstream adds its own after its merge)."""
    configs = {**CONFIGS, **(extra or {})}
    target = WIKI / 'analysis/development-wbs/snapshot.json'
    before = WIKI / 'analysis/development-wbs/snapshot-before-wbs-1015.json'
    if not before.exists():
        shutil.copyfile(target, before)
    data = read('research/llm-wiki/analysis/development-wbs/snapshot-before-wbs-1015.json')
    assert data['summary']['progress'] == 24.8, 'baseline must be the 10-14 snapshot'
    labs = lab_results()
    deploy = read(DEPLOY)
    appliance = read(APPLIANCE)
    head = git('rev-parse', 'HEAD').stdout.strip()
    deployed = deploy['commit']
    for stream, merge in {**MERGES, **deploy.get('merges', {})}.items():
        assert git('merge-base', '--is-ancestor', merge, deployed).returncode == 0, f'{stream} not in deployed {deployed}'
    assert deploy['field_up_rc'] == 0 and deploy['native_engines_present']
    assert sum(row['n'] for rows in appliance['provenance'].values() for row in rows if row['hash_state'] == 'match') >= 250
    assert not [row for rows in appliance['provenance'].values() for row in rows if row['hash_state'] == 'mismatch']
    assert len(appliance['tool_scope_reviews']) == 3 and all(r['actor'] != r['applicant'] for r in appliance['tool_scope_reviews'])
    assert [(a['first_id'], a['last_id']) for a in appliance['audit_annotations']] == [(744, 800), (803, 803)]
    assert all(i['state'] == 'resolved' for i in appliance['dispatch_intents'])
    for row in data['items']:
        cfg = configs.get(row['id'])
        if not cfg:
            continue
        for test in cfg['tests']:
            assert test in labs and labs[test]['rc'] == 0, f"{row['id']}: {test} did not pass on the merged source"
        for stage, score in cfg['scores'].items():
            assert score >= row['stage_scores'][stage], f"{row['id']}: {stage} would fall without a recorded reason"
        row['stage_scores'] = cfg['scores']
        row['stage_notes'] = cfg['notes']
        row['known_gap'] = cfg['gap']
        row['implementation_assessment'] = {1: 'complete', 0.5: 'partial_candidate', 0: 'not_implemented'}[cfg['scores']['implementation']]
        row['regression_test_candidates'] = list(dict.fromkeys(
            row.get('regression_test_candidates', []) + ['full_stack_lab/tests/' + t for t in cfg['tests']]))
        paths = list(dict.fromkeys([*cfg['evidence'], LAB, DEPLOY]))
        row['actual_evidence_paths'] = list(dict.fromkeys(row.get('actual_evidence_paths', []) + paths))
        row['evidence'] = [{'path': p, 'sha256': digest(p)} for p in paths]
        row['evidence_as_of'] = ['2026-10-15']
        row['progress'] = round(sum(row['stage_scores'].values()) * 20, 1)
        row['complete'] = all(score == 1 for score in row['stage_scores'].values())
    for goal in data['goals']:
        rows = [i for i in data['items'] if i['goal_id'] == goal['id']]
        goal['progress'] = round(sum(i['progress'] for i in rows) / 4, 1)
        goal['complete'] = sum(i['complete'] for i in rows)
    summary = data['summary']
    summary['progress'] = round(sum(i['progress'] for i in data['items']) / 40, 1)
    summary['complete'] = sum(i['complete'] for i in data['items'])
    summary['stage_equivalent_counts'] = {s: round(sum(i['stage_scores'][s] for i in data['items']), 1) for s in STAGES}
    summary['implementation_full'] = sum(i['stage_scores']['implementation'] == 1 for i in data['items'])
    summary['implementation_partial'] = sum(i['stage_scores']['implementation'] == 0.5 for i in data['items'])
    summary['implementation_missing'] = sum(i['stage_scores']['implementation'] == 0 for i in data['items'])
    data['source_snapshot'] = {'path': 'research/llm-wiki/analysis/development-wbs/snapshot-before-wbs-1015.json',
                               'as_of': data['as_of'], 'historical_progress': 24.8,
                               'note': '10-14 로그 수정 뒤 스냅샷을 이력으로 보존하고, 새 근거가 있는 작업만 다시 산정했다.'}
    data['as_of'] = datetime.now(timezone.utc).isoformat()
    data['audit_as_of'] = deploy.get('audited_at') or data['as_of']
    data['branch'] = '10/15-wbs-implementation'
    data['basis_head'] = head
    data['exclusions'] = list(dict.fromkeys(data.get('exclusions', []) + [
        '서브에이전트 브랜치의 시험 결과는 병합 소스에서 다시 돌린 결과(lab-results.jsonl)로만 회귀 점수에 반영했다.',
        'PJ1 공식 MCP SDK 호출은 프로토콜 증거이며 관리 하네스의 자연어 모델 호출이 아니다.',
        '관리 계정이 로그인되지 않아 하네스 E2E·키트 재설치 후 DEV-31 실기기 확인은 하지 않았다.',
        '10-15 범위 기록은 사용자가 허락한 root 권한으로 기존 신청 목적을 옮긴 것이며 새 도입 승인이 아니다.']))
    page_sections(data, appliance, sample)
    return write_outputs(data)


if __name__ == '__main__':
    build_after_wbs_1015()
