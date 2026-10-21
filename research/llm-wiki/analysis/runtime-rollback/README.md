# DEV-78 실행기 이전 승인 판본 되돌리기

- 기준: 2026-10-21 현재 체크아웃 `main`, 원격 HEAD 조회 실패, 작업 트리 변경 상태. 브랜치 생성은 `.git` 쓰기 차단으로 거부되어 변경은 미커밋.
- 요청 근거: [방향 갱신 10-20 §3 DEV-78](../direction-1020/README.md), TC260 6.1.10. 설계 대조: [D-114 실행기 보고](../../status/reports/2026-10-15-dev38-runtime.md), `registry/contracts.lock.json`, [데이터 모델](../../../../docs/ai/DATA_MODEL.md), [D-149 출력 계약](../output-contract-d149/README.md), D-144·D-154.

## 요구사항과 구현

| ID | 동작 | 구현·근거 |
| --- | --- | --- |
| RR-01 | 사람 승인 이력에서만 선택 | worker가 `runtime-active` 추가 전용 `approval_events`에 당시 승인 계약 스냅샷을 기록한다. 스냅샷 없는 기존 이벤트는 후보에 올리지 않으며 파일 잠금에서 추정하지 않는다. |
| RR-02 | 바이트 동일 계약 해시 복원 | 승인 설명·입력·출력 스키마 해시와 서버 판본을 키 정렬 UTF-8 JSON으로 SHA-256 한다. 되돌림은 해시를 재검증하고 저장값을 그대로 `mcp_tools.approved_*`에 쓴다. D-149의 NULL 출력 해시도 보존한다. |
| RR-03 | 철회·종료·공급망 중지 우선 | 서버 상태, 종료 생명주기, 진행 중 운영 중지, 종료된 이용 관계, 세대별 거부/중지 사건을 요청·worker 전환 시 재검사한다. |
| RR-04 | 원장과 실패 처리 | 관리자의 요청자·현재/목표 세대·계약 해시·한 줄 사유를 `approval_events`에 추가한다. 승인 이벤트는 기존 UPDATE/DELETE 차단 트리거를 따른다. worker도 완료·거부 전환을 추가한다. |
| RR-05 | 실행 세대 경합 | 요청은 활성 행을 STOPPING으로 전환한다. worker가 자원을 제거한 뒤 같은 DB 트랜잭션에서 이전 승인 계약을 복구하고 새 세대를 QUEUED로 삽입한다. 기존 부분 유일 인덱스가 살아 있는 세대 중복을 거부한다. |
| RR-06 | 이후 호출 계약 판정 | 복원한 D-149 승인 해시와 현재 관측 해시가 dispatch의 전송 직전 SQL에서 비교된다. 이미지가 이전 세대의 승인을 내더라도 출력 스키마 검증은 복원된 출력 해시를 따른다. |

## 검증 기록

새 `full_stack_lab/tests/runtime_rollback_check.py`는 계약 필드/출력 해시 보존, 스냅샷 변조 및 도구 구성 차단, 승인 이력 없는 세대·철회/종료/공급망 차단, append-only 스냅샷, STOPPED→QUEUED 전환 순서, dispatch 계약 재확인을 확인한다. DB·Docker 없는 정적/단위 확인이며 실제 PostgreSQL 경합 시험은 아니다.

| 확인 | 결과 |
| --- | --- |
| Python 구문 | gateway/app·runtime·tests의 169개 `.py` 파일 `py_compile` 통과 |
| JavaScript 구문 | `node --check gateway/app/agent_static/console.js` 통과 |
| 무인증 라우트 | `python tests/open_endpoints.py` 통과: 보호 84개, 허용 무인증 8개 |
| DEV-78 신규 시험 | 7/7 통과 |
| 승인 계약 잠금 | `python tests/contracts_check.py` 자기 확인 통과 |
| 콘솔 회귀 | `node --test tests/console-state.test.mjs` 15/15 통과 |
| 위키 목록 | `build_wiki.py` 615개 Markdown 목록 생성 |
| 위키 전체 검사 | `check_wiki.py` 실패: ignored `local-sources/compliance` provenance 29개 파일 누락. 이번 코드 매핑 오류는 `map_threats.py` 실행으로 해소했고 독립 검토의 과거 근거 파일 8개는 변경으로 stale 표시됐다. |
| 기존 실행기/판본 회귀 | `runtime_worker_check.py`는 Python 3.10의 `tomllib`·`psycopg` 부재로 실행 불가. `protocol_versions_check.py`는 `httpx` 부재로 실행 불가 |
| 추가 정적 검사 | `pyflakes` 모듈 미설치 |
| 기기·PJ1 | 사용자 지시대로 미실행 |

## 한계와 후속 검증

- 기존 `runtime-active` 행은 계약 전체를 보존하지 않았으므로 과거 이력을 자동 보충하지 않는다. 새 스냅샷이 쌓인 세대만 표시된다.
- 로컬 실행 이미지가 남아 있고 같은 고정 레시피 판본을 사용할 때만 되돌린다. worker는 이미지 존재, 승인 스냅샷, 계약 구성과 중지 상태를 다시 확인한다.
- 동시성 보호는 트랜잭션 경계와 부분 유일 인덱스에 의존한다. 실제 PostgreSQL 다중 요청/worker 경쟁 시험, image pull/build 변동과 컨테이너 전환, 하네스 호출·효과, 콘솔 브라우저 렌더링은 미실행이다.
- `registry/contracts.lock.json`은 정적 기준 잠금이라 운영 서버의 승인 이력으로 재사용하거나 수정하지 않았다. D-149의 출력 승인 해시는 DB 승인 상태에 보존했다.
