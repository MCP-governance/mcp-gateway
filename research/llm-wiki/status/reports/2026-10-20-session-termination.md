# 2026-10-20 활성 MCP 세션 종료와 재접근 차단 (G07.02)

- 작업자: Codex luna
- 코드 기준: 브랜치 `10/20-session-termination`, 시작 커밋 `f5f4eed` (미커밋). 작업 트리에서만 수정했다.
- 시작 근거: DEV-08, WBS G07.02, D-115·D-79, [2026-10-15 종료·전송 보고](2026-10-15-termination-dispatch.md), [TERMINATION_MODEL](../../../../docs/ai/TERMINATION_MODEL.md), D-146.
- 해결할 문제와 완료 조건: 하네스↔게이트웨이 세션, 게이트웨이↔상류 풀, Console 로그인·토큰을 각각 추적해 종료 후 재접근을 막고 실제 확인 범위를 구분한다.

## 결과

### 시작 시 코드 근거

| 경로 | 시작 전 코드 근거 | 판단 |
| --- | --- | --- |
| 주체 중지·삭제 | `authenticated_user()`는 비활성 주체를 매 요청 거부하고 OIDC `end_session()`을 호출했다. account endpoint는 상류 풀만 닫았고 `console_sessions`·전체 MCP 토큰 계열을 즉시 철회하지 않았다. | 상태가 비활성인 동안 거부되지만 재활성화 시 옛 액세스 토큰이 되살아날 수 있었고 Console 세션이 남았다. |
| 장치 철회 | `managed_failure()`는 폐기 장치의 다음 요청을 거부하고 토큰의 epoch를 검사한다. `revoke_device()`에는 상류 풀 종료 신호나 장치 토큰 철회가 없었다. | 요청은 막지만 풀·발급 토큰은 직접 폐기하지 않았다. |
| 관계 종료·서버 등록 해제 | `open_case()`는 서버 lifecycle을 TERMINATING으로 전환해 dispatch를 막고 상류 풀을 닫았다. `deregister_server()`는 등록 제거 후 풀을 닫았다. | 상류 세션은 닫지만 기존 downstream 세션 ID를 추적하거나 종료하지 않았다. |
| Console 로그인 | `oidc.validate_session()`은 매 Console 요청에서 계정·세션·외부 OIDC 상태를 확인한다. 계정 상태 변경 당시 세션은 즉시 삭제하지 않았다. | 다음 요청은 거부하지만 즉시 삭제·종료 기록이 없었다. 서버 한 곳 종료로 관리자 Console 세션은 닫지 않는다. |

### 구현

- 초기화 응답의 `Mcp-Session-Id` 원문 대신 SHA-256과 검증된 주체·토큰 `jti`·장치·개별 서버 경로를 `mcp_client_sessions`에 기록한다. 후속 세션 요청은 같은 주체·`jti`의 활성 결속이 없거나 종료됐으면 HTTP 410으로 거부한다. 클라이언트 DELETE도 종료 사건을 기록한다.
- `mcp_session_events`에 종료 사유·대상 범위·종료 세션 수를 append-only로 기록한다. 관계 종료·서버 해제는 해당 서버 경로 세션, 주체·장치 종료는 해당 소유 세션을 무효화한다.
- 주체 중지·삭제 시 Console 세션·OIDC 바인딩 세션·발급된 액세스 토큰 JTI와 리프레시 계열을 철회한다. 장치 철회 시 장치 토큰과 연결된 리프레시 계열을 폐기하고 세션·상류 풀을 닫는다.
- DB는 `v2_tables.sql` 끝에 두 개의 `CREATE TABLE IF NOT EXISTS`와 인덱스로 확장했다. 새 의존성·정책 ID는 없다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| AsyncMock 단위 | `python -X utf8 -m unittest discover -s full_stack_lab/tests -p session_termination_check.py -v` (Windows, 2026-10-20) | 2건 통과: 기존 세션 재사용 거부 상태, 다른 주체 보존, 서버별 범위, 종료 기록 | `full_stack_lab/tests/session_termination_check.py` |
| Python 구문 | `python -X utf8 -m py_compile full_stack_lab/gateway/app/agent_service.py full_stack_lab/gateway/app/core.py full_stack_lab/gateway/app/decommission.py full_stack_lab/gateway/app/endpoint_plane.py full_stack_lab/gateway/app/idp.py full_stack_lab/gateway/app/main.py full_stack_lab/gateway/app/mcp_sessions.py full_stack_lab/tests/session_termination_check.py` | 통과 | 실행 결과 |
| Diff 공백 | `git diff --check` | 오류 없음; `endpoint_plane.py` 줄바꿈 형식 정규화 경고 | 실행 결과 |
| 기존 회귀 | 미실행 | 미실행 | — |
| 실제 PostgreSQL·MCP SDK·상용/OSS MCP | 미실행 | 미확인 | — |
| 솔루션 기기 배포·PJ1 실제 하네스 | 미실행 | 미확인 | — |

## 실패·미완료·한계

- 새 검사는 DB 대역으로 실제 PostgreSQL·Starlette/Streamable HTTP SDK·MCP 서버를 확인하지 않았다.
- 게이트웨이 경계에서 종료된 ID 재사용을 거부하지만 원격 세션에 프로토콜 DELETE를 강제로 보내지 않는다. SDK 프로세스 내부 세션 객체가 즉시 제거됐다는 증거는 없다. 종료 이벤트는 C4 또는 자원 서버 거부 증거가 아니다.
- 집계 `/mcp/` 세션은 여러 서버가 공유하므로 한 서버 종료로 전체 세션을 끊지 않는다. 해당 서버 도구는 기존 목록·dispatch 경계에서 막힌다.
- 세션 표의 보존·정리 정책을 정하지 않았다. OIDC 외부 토큰 철회 실패는 기존 `end_session()` 동작처럼 경고만 남기지만 내부 세션·게이트웨이 토큰은 제거한다.
- 기존 시험 파일은 변경하지 않았다.

## 다음 작업

- 솔루션 기기에서 `python3 -m unittest discover -s tests -p session_termination_check.py -v`와 `python3 tests/termination_flow.py`를 실행한다. PostgreSQL DDL 및 실제 하네스에서 initialize → tools/list/call → 종료 → 같은 세션 재사용이 410인지, 다른 주체·다른 서버 세션이 유지되는지 확인한다.
- PJ1 실제 하네스 결과와 종료 사건 행을 보존한 뒤 DEV-08 상태를 갱신한다.

## 사용자에게 필요한 입력

없음.
