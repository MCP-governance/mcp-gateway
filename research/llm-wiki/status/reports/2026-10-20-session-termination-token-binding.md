# 2026-10-20 세션 종료 토큰 교체 회귀 수정

- 작업자: Codex luna
- 코드 기준: `95b117c`, 작업 트리 수정 중(미커밋). 변경: `full_stack_lab/gateway/app/mcp_sessions.py`, `full_stack_lab/gateway/app/upstream.py`, `full_stack_lab/gateway/app/main.py`, `full_stack_lab/tests/session_termination_check.py`, `docs/ai/DECISIONS.md`, `research/llm-wiki/status/backlog.md`, 본 보고서.
- 시작 근거: G07.02 / DEV-08, D-146, D-115, D-79, `docs/ai/TERMINATION_MODEL.md`, `research/llm-wiki/status/reports/2026-10-15-termination-dispatch.md`, 솔루션 이미지 검토 결함 2건.
- 해결할 문제와 완료 조건: 매 5분 토큰 교체로 활성 세션이 410 처리되는 문제를 고치고, 다른 주체·장치가 같은 ID를 재사용하지 못하게 한다. AST 대역의 기존 상류 세션 시험에서 발생한 `mcp_sessions` 미정의 오류를 기존 시험 파일을 바꾸지 않고 제품 코드에서 해소한다.

## 결과

세션의 활성 확인은 ID 해시·전송 토큰에서 검증된 주체·장치·서버 경로 및 미종료 상태로 한다. 발급 당시 `token_jti`는 감사 맥락으로 계속 저장하지만 세션 허가 조건에서는 제외했다. 같은 주체·장치의 새 유효 토큰은 같은 경로의 기존 세션을 유지하며, 다른 주체·장치·경로는 거부된다. `RequireBearer`는 `upstream.active_downstream`/`register_downstream`을 호출하고, `mcp_sessions`를 AST 추출 네임스페이스에 직접 요구하지 않는다. 성공한 DELETE 폐기는 `upstream.close_downstream`에서 DB 종료 기록 후 로컬 상류 세션을 닫는다.

종료 경로 코드 대조:

| 사건 | 하네스↔게이트웨이 MCP 세션 | 게이트웨이↔업스트림 풀 | 콘솔 로그인·전송 토큰 |
| --- | --- | --- | --- |
| 주체 중지·삭제 | `mcp_sessions.terminate`로 주체 세션 종료 | `release_pool` 신호 | 콘솔 세션·OIDC 세션 제거, 주체 액세스 토큰·리프레시 계열 폐기 |
| 장치 철회 | 장치 ID 결속 세션 종료 | 소유 주체 풀 `release_pool` | 장치 ID 결속 액세스 토큰·리프레시 계열 폐기; 콘솔 로그인은 영향받지 않음 |
| 이용 관계·서버 종료 | 서버 경로 세션 종료 | `release_pool` 신호 | 콘솔 로그인은 영향받지 않음; 각 요청에서 종료된 서버 경로 접근 차단 |
| 개별 토큰 철회 | 폐기 토큰 요청은 인증 단계에서 401; 같은 주체·장치의 새 유효 토큰은 세션 재사용 가능 | 토큰 철회 자체가 풀을 닫지는 않음 | 토큰/JTI 폐기 검증 유지; 콘솔 로그인 세션은 별도 수명 |

종료 판정 모델(C1~C4/T1~T3)은 바꾸지 않았다. 기존 `tests/termination_flow.py`는 손대지 않았다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 정적/단위 시험 | `python -m unittest discover -s full_stack_lab/tests -p session_termination_check.py -v` (2026-10-20) | 통과, 4건 | 콘솔 출력 |
| 회귀 시험 | `python -m unittest discover -s full_stack_lab/tests -p upstream_session_reuse_test.py -v` (2026-10-20) | 통과, 40건; 기존 시험 파일 무변경 | 콘솔 출력 |
| 컴파일·전체 정적 검사 | 미실행 | 미실행 | |
| PostgreSQL·MCP 실기기·솔루션 배포·PJ1 | 미실행 | 미실행 | |

## 실패·미완료·한계

토큰 철회는 유효한 요청을 인증 단계에서 차단하지만 그 `jti`만을 이유로 세션 행 자체를 종료 표시하지 않는다. 이는 새 `jti`의 정상 교체 사용을 허용하기 위한 분리이며, 기존 토큰은 매 요청 인증에서 거부된다. DB 동작은 AsyncMock 대역만 확인했다. 프로토콜 DELETE를 원격에 강제하거나 SDK 메모리 세션 제거를 증명하지 않는다. 종료 사건 기록·종료가 여러 프로세스·실제 DB에서 경합하지 않는지는 솔루션 기기 검증이 필요하다.

## 다음 작업

DEV-08에 남은 PostgreSQL·실제 SDK·솔루션 배포·PJ1 검증을 수행한다. 동일 주체·장치의 토큰 교체, 다른 주체·장치의 동일 세션 ID 거부, 종료 경계 및 원장 기록을 실제 배포 환경에서 확인한다.

## 사용자에게 필요한 입력

없음.
