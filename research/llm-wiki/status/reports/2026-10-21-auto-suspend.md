미커밋
# 2026-10-21 DEV-74 반복 위반 사용자 자동 일시 중지

- 작업자: Codex luna A
- 코드 기준: `859f4d63db9cab5714f25e5d3cc4607077959e13`, 시작 시 작업 트리 깨끗함, `main`. `git fetch origin`은 `.git/FETCH_HEAD` 권한 거부로 실패했고 `git ls-remote --symref origin HEAD`는 네트워크 접근 실패로 끝나 로컬 `origin/main` 스냅샷을 기준으로 삼았다. 전용 브랜치 생성은 `.git/refs` 쓰기 권한 거부로 실패했다. 커밋·통합 없음.
- 시작 근거: DEV-74, 예약 D-176, [방향 갱신 10-20 §3](../../analysis/direction-1020/README.md#3-기술-목표), GB/T 45654—2025 6.5 a), D-181·D-172·D-122, `P-SUSPEND-001`
- 완료 조건: 임계 다음 호출부터 차단, 만료 후 정상, 임계·관측 창·중지 기간 설정값, 지정 위반 정책 ID 고정, 자동 사건 원장 기록, 집계 실패 fail-closed, 중복 사건 없는 경합 처리, D-181 수동 재개 재사용, 콘솔의 자동 여부/해제 예정 시각 표시.

## 결과

- D-181 `user_server_suspensions`와 `P-SUSPEND-001`을 재사용했다. `expires_at` 열을 기존 상태 테이블에 추가했으며 새 테이블이나 판정 ID, 새 최종 차단 경로는 만들지 않았다. 만료된 상태는 직원 잠금 아래 재개 원장을 남기고 다음 호출부터 정상 경로로 돌아간다.
- 사용자·서버별 위반은 실제 원장의 `decision='Block'`이며 아래 5개 정책만 집계한다: `MCP-EGRESS-002`, `MCP-DATA-EGRESS-001`, `P-DLP-001`, `P-CHAIN-001`, `P-FLOW-001`.
- 제외한 정책과 이유: `MCP-EGRESS-001`(서버 목적지 설정에서 비롯될 수 있음), `PAC-09`~`PAC-12`(업무 승인/자산 범위 누락과 사용자 행위를 정책 ID만으로 구분하기 어려움), `P-CONSENT-001`(동의 요청), 승인 대기·만료, 분류·카탈로그·등록 상태, 제한 실행량, 상태 격리, 계정/엔드포인트 상태, `P-CONTROL-FAIL-CLOSED`, `P-SUSPEND-001`. `P-UNTRUSTED-CONTENT-001`은 승인, `P-UNTRUSTED-CONTENT-002`는 경고라 Block 위반 목록에 들지 않는다.
- 임계 도달 결정과 자동 중지 행·`approval_events` 사건을 한 transaction으로 기록한다. 사건은 자동 행위자, 직원·서버, 정책 ID, 임계·집계 건수·관측 창·만료 시각, 진행 중 호출 수를 포함한다. 집계가 실패하면 해당 차단 호출은 upstream으로 가지 않으며 transaction이 rollback된다. 상태 조회/만료 실패는 `P-CONTROL-FAIL-CLOSED`로 차단되고 위반 집계에 포함되지 않는다.
- 기본 설정은 임계 5건, 관측 창 600초, 중지 900초이며 Compose·`.env.example`에서 조정할 수 있다.
- 기존 D-181 단일·일괄 관리자 재개 경로는 변경하지 않았다. 콘솔 이용 중지 표에 자동 행위자와 해제 예정 시각을 연결했다.
- 근거 정본은 [분석](../../analysis/auto-suspend/README.md)과 [검사 기록](../../analysis/auto-suspend/checks.json)에 있다.
- 기존 코드 후보 추적의 해시를 새 로컬 소스 상태로 갱신했다. 독립 검토의 과거 기준은 보존하고 9개 낡은 소스 참조로 표시했다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 신규 로컬 시험 | `python -B tests/user_auto_suspend_check.py` · Python 3.10 · 2026-10-21 | 10/10 통과: 임계 미달, 정책 경계, 만료, 창 밖 거부 제외, 원장 필드, 경쟁 삽입 모델, 실패, 설정, UI/재개 배선 | [checks.json](../../analysis/auto-suspend/checks.json) |
| 기존 D-181 회귀 | `python -B tests/user_server_suspend_check.py` · Python 3.10 | 24/24 통과, 시험 파일 미변경 | [checks.json](../../analysis/auto-suspend/checks.json) |
| 기존 일괄 회귀 | `python -B tests/user_suspend_all_check.py` · Python 3.10 | 13/13 통과, 시험 파일 미변경 | [checks.json](../../analysis/auto-suspend/checks.json) |
| JavaScript 구문/상태 시험 | `node --check .../console.js`; `node --test tests/console-state.test.mjs` | 구문 통과, 15/15 통과 | [checks.json](../../analysis/auto-suspend/checks.json) |
| 인증 경로·Python 구문·diff | `tests/open_endpoints.py`; `py_compile` 변경 Python 5개; `git diff --check` | 통과 | [checks.json](../../analysis/auto-suspend/checks.json) |
| pyflakes | `pyflakes gateway/app/*.py tests/*.py` | 미실행: 도구 미설치 | [checks.json](../../analysis/auto-suspend/checks.json) |
| 위키 코드 추적·정합성 | `map_threats.py`; `check_wiki.py --ci-ignored-local-sources` | 추적 생성 통과, 위키 오류 0·경고 119(이 checkout에 없는 ignored local source) | [checks.json](../../analysis/auto-suspend/checks.json) |
| OPA·기기·하네스 | OPA one-off, 솔루션 기기, PJ1 | 미실행(요청 범위) | — |

## 실패·미완료·한계

- `.git` ref lock 권한 때문에 `10/21-dev74-auto-suspend` 브랜치를 만들 수 없었다. 다른 checkout은 만들지 않았다. 현재 변경은 `main` 작업 트리에 미커밋으로 남아 있다.
- GitHub 원격 HEAD 확인은 네트워크 차단, fetch는 `.git/FETCH_HEAD` 권한으로 실패했다. 시작 commit과 로컬 `origin/main` 추적 스냅샷을 기준으로 삼았다.
- pyflakes가 설치되지 않아 해당 정적 검사는 미완료다. 실제 PostgreSQL 동시 경합, 콘솔 렌더링, device/PJ1 통합 시험은 수행하지 않았다. 신규 경쟁 시험은 부분 유일 인덱스와 advisory-lock 소스 경계를 확인하는 로컬 상태 모델이다.
- 독립 threat-trace 검토의 과거 코드 해시는 9개 참조에서 현재와 다르다. 생성된 카탈로그는 새 작업 트리 해시를 표시하고 과거 리뷰 불일치를 보존한다. 새 DEV-74 설계의 독립 적대 검토는 하지 않았다.
- 구현은 직원 전체가 아니라 위반이 발생한 직원×서버 조합을 중지한다. 이미 dispatch transaction을 통과한 호출은 취소되지 않는다.

## 다음 작업

- 메인이 이 변경을 전용 작업 브랜치로 옮기거나 통합한 뒤, 제품 회귀와 로컬 정적 검사를 재실행한다. 이후 별도 승인된 기기·PJ1 작업에서 실제 PostgreSQL 동시 임계, expiry, 사용자 호출의 `P-SUSPEND-001` 및 upstream 무효과를 확인한다.

## 사용자에게 필요한 입력

없음.
