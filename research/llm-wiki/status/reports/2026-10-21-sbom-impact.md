미커밋
# 2026-10-21 SBOM 영향 조회·서버 대응

- 작업자: Codex luna B
- 코드 기준: `859f4d63db9cab5714f25e5d3cc4607077959e13`, 시작 트리 clean, 현재 checkout `main`; 원격 확인은 네트워크 제한으로 실패했다. 공용 `.git`이 읽기 전용이라 작업 브랜치·커밋을 만들지 못했다.
- 변경: `full_stack_lab/gateway/app/sbom_impact.py`, `gateway/app/agent_service.py`, `gateway/app/ops_response.py`, `gateway/app/agent_static/console.js`, `full_stack_lab/tests/sbom_impact_check.py`, `docs/ai/DATA_MODEL.md`, `docs/ai/DECISIONS.md`, `research/llm-wiki/catalogs/threats.json`(위협 맵 재생성), 저장소 코드 스냅샷, 위키 backlog, 이 보고서와 `analysis/sbom-impact/README.md`.
- 시작 근거: 방향 갱신 10-20 §3 DEV-76, M05 제9항, MCP fleet incident. 세부 분석은 [SBOM 영향 조회 분석](../../analysis/sbom-impact/README.md).
- 해결할 문제와 완료 조건: 저장 SBOM에서 패키지·판본 영향을 서버·실행 세대별로 조회하고, 영향 서버를 기존 서버 중지 경로로 일괄 대응하면서 배치별 원장과 부분 실패를 남긴다.

## 결과

- 관리자 전용 `POST /api/supply-chain/impact`와 `/impact/stop`을 추가했다. 판본 범위는 SemVer 세 자리와 `<`, `<=`, `=`, `>=`, `>`의 AND 조건으로 제한하고, 비 SemVer 값과 200개 요약에서 찾지 못한 항목은 `판단 불가`, 연결되거나 저장된 SBOM이 없는 서버는 `자료 없음`으로 구별한다.
- 영향 행마다 서버·세대·SBOM 구성요소 이름/판본/purl/보고서 행 ID가 반환된다. Console 화면은 조회 4개 수치와 중지 3개 수치만 보여 준다.
- 영향 서버마다 `ops_response.suspend`를 재사용한다. 기존 서버 비활성화와 관련 실행 세대 중지에 `automatic-suspension` 원장 행을 쓰며 `scope.batch` UUID로 일괄 요청을 묶는다. 이미 중지된 서버는 건너뜀, 예외는 실패로 계속 보고한다.
- 데이터 범위: Syft 원본 CycloneDX는 `intake_reports` named volume에 있다. `supply_chain_reports.summary.inventory`에는 앞 200개 구성요소만 있고 `truncated`가 기록된다. `workspace` import는 구성요소 수만 저장해 intake/서버/실행 세대에 연결되지 않으므로 조회에서 제외한다. 빌드 이미지 SBOM·사용자/엔드포인트 영향·SBOM 파일 자체 SHA-256 저장은 기존 자료에서 확인되지 않았다. 상세 범위와 판본 한계는 분석 문서에 기록했다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 새 합성 단위 시험 | `python -B -X utf8 tests/sbom_impact_check.py` (Windows Python 3.10) | 5건 통과: SemVer·영향 분류·잘림/자료 없음·부분 실패·서버별 중지·배치 원장·관리자 라우트 | 실행 출력 `Ran 5 tests … OK` |
| 기존 직원 중지 회귀 | `python -B -X utf8 tests/user_server_suspend_check.py` | 24건 통과 | 실행 출력 `Ran 24 tests … OK` |
| 기존 일괄 중지 회귀 | `python -B -X utf8 tests/user_suspend_all_check.py` | 13건 통과 | 실행 출력 `Ran 13 tests … OK` |
| 인증 경계 | `python -B -X utf8 tests/open_endpoints.py` | PASS, 인증 필요 API 89개 | 실행 출력 |
| Console 정적 검사 | `node --check gateway/app/agent_static/console.js`; `python -B -X utf8 tests/console_copy_check.py` | PASS; 금칙 문구 문제 0 | 실행 출력 |
| 기존 Console 상태 검사 | `node --test tests/console-state.test.mjs` | 15건 통과 | Node 출력 |
| Python 구문 | `python -B -X utf8 -m py_compile gateway/app/sbom_impact.py gateway/app/ops_response.py gateway/app/agent_service.py tests/sbom_impact_check.py` | 통과 | 종료 코드 0 |
| Pyflakes | `pyflakes gateway/app/*.py tests/*.py runtime/*.py supply_chain/*.py` | 미실행: 명령 없음 | PowerShell `pyflakes` not found |
| 위키 정본 | `capture_status.py`, `build_wiki.py`, `map_threats.py`, `check_wiki.py --ci-ignored-local-sources` | 최종 검사 `ok=true`, 오류 0. 무시된 로컬 원본 누락 경고는 기존 항목. threat 맵은 현재 코드 기준으로 갱신했고 과거 검토와 다른 파일 9개를 표시함 | capture: HEAD `859f4d6`, build: 623 Markdown; check 출력 |
| 기존 공급망·D-179·D-180 회귀 | `provenance_check.py`, `intake_identity_test.py`, `intake_validation_test.py`, `provenance_verify_check.py`, `runtime_rollback_check.py` | 이번 로컬 환경에서 완료 확인 불가: HTTPX·cryptography 미설치, Python 3.10의 `datetime.UTC` 부재. Kali WSL 진입도 `E_ACCESSDENIED` | 개별 실행 오류; 관련 시험 파일은 수정하지 않음 |
| 프로토콜·upstream·배포·현장 | 미실행 | 미실행 | 솔루션 기기와 PJ1 시험 금지 지시 준수 |

## 실패·미완료·한계

- 로컬 정적 범위의 pyflakes와 기존 공급망 전체 회귀 통과를 확인하지 못했다. 의존성 설치나 서비스 기동은 하지 않았다. 위 시험의 오류는 제품 코드 실패가 아니라 현재 Python 3.10 및 의존성 없는 실행 환경에서 발생했지만, 기존 회귀 결과를 통과로 표시하지 않는다.
- 실제 Syft 파일·PostgreSQL 보고 행이 서로 일치하는지, 여러 worker/동시 운영자에서 서버 중지 경합, 기존 중지 원장과 재개, 실제 `MCP-REGISTRY-002` 판정은 미검증이다.
- Syft source-tree SBOM을 실행 세대에 연결하나 실제 실행 이미지 SBOM을 보증하지 않는다. DB summary 200개 제한, SemVer만 비교, package namespace 미분리, 사용자·엔드포인트 연결 부재는 알려진 한계다.
- 브랜치와 커밋은 공용 `.git` 읽기 전용으로 만들지 못해 변경은 미커밋이다. 원격 GitHub HEAD 확인도 네트워크에서 실패해 로컬 `origin/main` 스냅샷을 기준으로 삼았다.

## 다음 작업

메인이 변경을 검토·병합하기 전에 Python 3.12 및 기존 고정 의존성이 있는 정적 환경에서 공급망 회귀와 pyflakes를 다시 실행한다. 실제 PostgreSQL·원본 SBOM volume 대조와 서버 단위 운영 효과는 별도 승인된 솔루션 기기/PJ1 검증 단계다.

## 사용자에게 필요한 입력

없음.

## 방향 제안

이미 원본 SBOM volume이 있으므로 전체 inventory를 DB에 복제하는 대신, 현재 200개 DB summary 제한과 원본 파일 보존·백업/복원 확인을 분리해 판단하는 방안을 메인이 검토할 수 있다. 더 긴급하게 이미지를 정확히 대응해야 한다면 실행 이미지 빌드 결과를 대상으로 한 별도 SBOM 저장/세대 결속이 필요하지만, 이는 새 자료 흐름·보존 범위·성능·기존 승인 절차에 영향을 준다. 이번 변경에서는 채택하지 않았다.
