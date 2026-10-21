미커밋

# DEV-75 미사용 도구 자동 비활성·재심사

## 결과

`decisions` 원장에서 서버·도구별 실제 실행 이력을 읽어 미사용 승인 도구를 기한에 따라 비활성화하도록 구현했다. 새 사용 집계 테이블이나 정책 ID는 추가하지 않았다. 상태 변화와 자동 실패는 append-only `approval_events`에 기록한다.

- `tools/list`는 기한 만료 도구를 제외한다. 직접 호출은 기존 `P-APPROVAL-EXPIRY-001`로 차단한다.
- 관측 창 안에 실행 이력이 있는 경우 자동 연장한다. 기존 계약·승인 범위는 그대로 두고, 연장 사건에 마지막 사용·관측 창·이전/새 기한을 기록한다.
- 다른 관리자의 도구 범위 재심사·재승인 사건으로 자동 비활성에서 되돌아온다.
- 기본 설정은 유휴 90일, 사용 관측 30일, 재심사 유예 30일이다. Gateway 환경 설정으로 변경할 수 있다.
- 원장 보존 설정이 판정 구간보다 짧거나 봉인 구간과 겹치는 경우, 원장 조회가 실패한 경우는 자료 없음으로 기록하고 비활성하지 않는다. 상태 조회 자체가 실패하면 호출은 기존 `P-CONTROL-FAIL-CLOSED`로 거부한다.
- 콘솔 서버 상세에 도구별 마지막 사용·기한·이용 상태를 추가했다. 빈 값은 `—`로 표시한다.

## 근거와 변경

- 기준: [`direction-1020/README.md` §3 DEV-75](../../analysis/direction-1020/README.md), TC260 4.2.1(b), 4.2.3(a), [`POLICY.md`](../../../../docs/ai/POLICY.md), D-149·D-172·D-176.
- 원장 사용: `decisions.server_id`, `tool_name`, `created_at`, `upstream_executed`, `client.event_kind`. 차단 시도와 MCP 연결 사건은 실제 사용으로 세지 않는다.
- 상태·감사: `approval_events`를 비활성·연장·재심사·집계 실패 사건의 append-only 기록으로 재사용했다. D-176의 `automatic` 행위자 표기를 따랐다.
- 구현: `full_stack_lab/gateway/app/tool_sunset.py`, `mcp_facade.py`, `core.py`, `main.py`, `agent_static/console.js`, `compose.yaml`.
- 시험: 새 `full_stack_lab/tests/tool_sunset_check.py` 7개 통과. 기한 비활성 사건, 연장, 자료 없음, 집계 실패, 재승인 복구, 목록/호출 정책 연결을 확인한다.
- 문서: D-177 및 정책 설명 추가. `status/current.md`와 백로그는 공통 규칙에 따라 메인 통합자가 갱신하도록 두었다.

## 검증

2026-10-21 로컬 실행:

| 명령 | 결과 |
| --- | --- |
| `python -B -X utf8 tests/tool_sunset_check.py` | 통과 7/7 |
| `node --check gateway/app/agent_static/console.js` | 통과 |
| `node --test tests/console-state.test.mjs` | 통과 15/15 |
| `python -B -X utf8 tests/open_endpoints.py` | 통과, 무인증 1개·인증 필요 89개가 문서와 일치 |
| 변경된 Python 5개 `compile()` 구문 확인 | 통과 |
| `git diff --check` | 통과 |
| `pyflakes gateway/app/*.py tests/*.py` | 미실행: 이 환경에 `pyflakes` 명령이 없음 |

새 시험은 표준 라이브러리와 가짜 DB 포트로 격리 실행했다. 실제 PostgreSQL, 경합, 브라우저 렌더링, 기기 배포, PJ1 시험은 하지 않았다. 저장소 기본 Python 3.12가 아닌 로컬 Python 3.10만 있어, 애플리케이션 전체 import 기반 시험 대신 변경 Python 파일을 메모리 컴파일했다.

시작 기준은 `47cc09a2a7c41d5474067e06abe101cec1917327` (`main`, 로컬 `origin/main`). 원격 조회는 네트워크 차단으로 실패했고 로컬 `origin/HEAD`는 `origin/main`을 가리켰다. 레인 브랜치 생성 시 격리 환경이 `.git/refs` 쓰기를 거부했다. 보조 체크아웃을 만들지 않았고 커밋도 시도하지 않아 변경을 현재 작업 트리에 미커밋으로 남겼다.

## 방향 제안

현재 자동 비활성 대상은 `reviewed_at`이 있는 Console 도입 도구다. 정적 catalog/lock 도구는 도구별 사람 승인 시각이 없어 `contracts.lock.json.generated_at`을 승인 시각으로 추정하지 않았다. 정적 catalog까지 같은 자동 비활성을 적용하려면 사람이 계약을 승인하는 시점에 도구별 승인 시각을 남기는 설계를 별도 검토할 수 있다.
