# 2026-10-21 DEV-78 실행기 이전 승인 판본 되돌리기

- 작업자: Codex
- 코드 기준: 시작 commit `512c30b38a587a1751c57c7e93f5689ddf487827`, 현재 `main`, 미커밋. 원격 HEAD 조회는 네트워크 차단으로 실패했고 `.git` 쓰기 거부로 새 브랜치 생성도 실패했다. 새 worktree/clone은 만들지 않았다.
- 변경: `full_stack_lab/gateway/app/agent_service.py`, `full_stack_lab/gateway/app/agent_static/console.js`, `full_stack_lab/gateway/app/v2_tables.sql`, `full_stack_lab/runtime/worker.py`, `full_stack_lab/tests/runtime_rollback_check.py`, `docs/ai/DATA_MODEL.md`, `docs/ai/DECISIONS.md`, 위키 현황·백로그, [근거](../../analysis/runtime-rollback/README.md).
- 시작 근거: [방향 갱신 10-20 §3 DEV-78](../../analysis/direction-1020/README.md), TC260 6.1.10, D-114·D-144·D-149·D-154.
- 완료 조건: 사람 승인 이력이 있는 실행 판본만 선택하고, 되돌린 뒤 당시 계약 해시와 실행 이미지가 복구되며 이력·경합·차단 조건을 시험으로 고정한다. 솔루션 기기·PJ1 검증은 이번 범위에서 미실행한다.

## 결과

실행이 ACTIVE가 될 때 도구별 승인 설명·입력 스키마·출력 스키마 해시, 서버 판본, 합성 계약 SHA-256, 마지막 사람 승인자·시각을 `runtime-active` append-only 승인 이벤트에 기록한다. 정적 `registry/contracts.lock.json`은 기준 잠금이지 운영 세대의 승인 이력이 아니므로 사용하지 않는다. 과거 이벤트에 스냅샷이 없는 세대는 후보에서 제외한다.

관리자 상세 화면에 승인 시각·승인자·계약 해시가 있는 이전 세대만 표시한다. 한 줄 사유로 되돌리기를 요청하면 API가 세대·계약 이력, 서버 상태, 종료/중지 상태, 관리자 권한을 확인해 현재 ACTIVE를 STOPPING으로 표시하고 요청자를 원장에 추가한다. 실행기 worker는 컨테이너/망 제거 뒤 동일 DB 전환에서 대상 이미지·계약 이력을 재검사하고 해시를 검증한다. 계약 승인값을 이전 값으로 되돌리고 과거 이미지의 새 실행 세대를 예약한다. 부분 유일 색인이 동시 실행을 막고, 활성화 후 호출은 기존 D-149 전송 직전 계약 판정을 거친다.

이전 실행 이미지가 남아 있고 고정 레시피의 현재 판본이 동일할 때만 진행한다. 승인 이력 누락, 해시 변조, 도구 구성 변화, 철회·종료·공급망 중지, 중지된 이용 관계는 거부한다.

## 검증

| 확인 종류 | 명령·환경 | 결과 | 범위 |
| --- | --- | --- | --- |
| Python 구문 | Python 3.10, gateway/app·runtime·tests 169개 파일 `py_compile` | 통과 | 실행 정합성/DB 동작 증거는 아님 |
| JavaScript 구문 | `node --check gateway/app/agent_static/console.js` | 통과 | 브라우저 렌더 확인은 아님 |
| 무인증 라우트 | `python tests/open_endpoints.py` | 통과: 보호 84개, 허용 무인증 8개 | 로컬 소스 검사 |
| DEV-78 신규 회귀 | `python tests/runtime_rollback_check.py` | 7/7 통과 | 합성 fake DB, 상태 전환 SQL 순서·인덱스 검사 |
| 계약 잠금 회귀 | `python tests/contracts_check.py` | 자기 확인 통과 | 실제 MCP 재발견 아님 |
| 콘솔 상태 회귀 | `node --test tests/console-state.test.mjs` | 15/15 통과 | UI 브라우저 렌더 미확인 |
| 위키 생성·검사 | `build_wiki.py`, `map_threats.py`, `check_wiki.py` | Markdown 목록 615개 생성, 코드 매핑 갱신. 전체 검사는 ignored `local-sources/compliance`의 기존 provenance 29개 파일 누락으로 실패 | 독립 검토의 8개 과거 근거 파일은 stale로 표시 |
| 기존 실행기 회귀 | `python tests/runtime_worker_check.py` | 미실행. Python 3.10 환경에 `tomllib`, `psycopg`가 없음 | 실행기 이미지의 Python 3.12와 다름 |
| 판본별 MCP 회귀 | `python tests/protocol_versions_check.py` | 미실행. `httpx` 미설치 | 네트워크/프로토콜 미확인 |
| 추가 lint | `python -m pyflakes ...` | 미실행. `pyflakes` 미설치 | 별도 의존성 추가 안 함 |
| 기기·PJ1 | 실행하지 않음 | 미실행 | 지시 준수 |

`git diff --check`는 공백 오류 없이 통과했다. 원격 HEAD를 조회할 수 없고 새 브랜치 생성 권한이 없어 변경을 현재 `main` 워킹 트리에 미커밋으로 남긴다.

## 실패·미완료·한계

- 신규 경합 시험은 실제 PostgreSQL 동시 트랜잭션 시험이 아니라 SQL 잠금·STOPPED→QUEUED 순서·유일 인덱스를 정적으로 확인한다. 멀티 worker와 DB 장애/복구는 미확인이다.
- 실제 이미지 재기동, 실행 종료 중 worker 경쟁, SDK 협상 판본별 호출·복원 효과, 관리자 브라우저 렌더링은 미실행이다.
- 이 기능 이후 새로 저장된 `runtime-active` 계약 스냅샷만 되돌릴 수 있다. 이미 쌓인 과거 원장에 계약 정보를 채워 넣지 않았다.
- 업데이트를 위한 추가 의존성이나 실행 스택 기동은 없었다.

## 다음 작업

1. Python 3.12 실행기 의존성이 있는 환경에서 기존 실행기·프로토콜 회귀를 실행한다.
2. 승인 이력이 있는 서로 다른 세대 두 개를 준비해 PostgreSQL 동시 되돌리기/재조정, 계약 해시 일치, 복원 뒤 실제 MCP 호출 판정을 검증한다.
3. 사용자 지시가 있을 때만 솔루션 기기와 PJ1에서 전체 시나리오를 확인한다. 이번에는 요청대로 미실행이다.

## 사용자에게 필요한 입력

없음. 새 스냅샷을 쌓을 실 서버/격리 시험 데이터와 Python 3.12 의존성 환경이 다음 실증에 필요하지만, 이번 로컬 구현을 위해 추가 입력은 없다.
