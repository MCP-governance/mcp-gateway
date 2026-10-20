# S9b·S10-B 요청자 재검증 및 시험 대역 적대 검토

- 검토자: Codex luna, 2026-10-20.
- 기준: 브랜치 `10/20-fresh-requester-review`, 시작 HEAD `4a79f39ebe70d6df656accc5555a8411f4584155` (S10-B); S9b `e19cabaf6570378ff8faf26e382d77d7bbb0a584`.
- 시작 작업 트리: 깨끗함. 검토 대상은 `git show HEAD -- full_stack_lab/tests/upstream_session_reuse_test.py`의 3개 hunk, S9b의 `_call_upstream` 변경과 `fresh_requester_check.py`, D-152이다.
- 기준 문서: 위키 README/AGENTS/current/backlog, `docs/ai/ARCHITECTURE.md`, `SECURITY_BOUNDARIES.md`, `POLICY.md`, `DECISIONS.md`, D-152 분석과 2026-10-20 작업 보고. 실제 DB·기기·PJ1 효과는 본 검토에서 확인하지 않았다.

## S10-B 시험 hunk 판정

| Hunk | 판정 | 판단 |
| --- | --- | --- |
| `@@ -554,6 +554,8 @@` — `agent_revoked_tokens` 쿼리에 `None` 응답 추가 | **A — 채택** | `_call_upstream`의 실제 SQL에 나타나는 표 이름을 기준으로 정상 fixture의 “철회 행 없음”을 돌려준다. 기존 `principals` 조회의 활성 사용자 응답과 철회 조회를 섞지 않는다. 기존 기대값·검사 범위를 줄이지 않는다. |
| `@@ -575,6 +577,7 @@` — AST 이름공간에 `disposal.blocked` 대역 추가 | **A — 채택** | `core.py`는 `from . import disposal`로 실제 `disposal` 모듈을 참조하고 `blocked(jti=...)`를 호출한다. AST 시험은 모듈 import를 생략하므로 이 이름을 주입하는 것은 맞다. 대역은 언제나 false지만 이 시험의 목적은 upstream 세션 재사용·재탐색·정책 재검사다. 토큰 폐기 의미를 검증하지 않으며 S9b 전용 `fresh_requester_check.py`가 해당 동작을 별도로 다루므로 이번 목적과 무관하다. |
| `@@ -594,7 +597,7 @@` — 합성 `transport_claims.jti` 추가 | **A — 채택** | 실행 시 저장 claims에서 읽는 입력을 제공한다. 테스트 대상 코드가 실제로 조회하는 키와 맞고 사용자 인자/헤더를 신원으로 사용하게 하지 않는다. 기존 arguments·approval ID·assert를 유지한다. |

두 번째 hunk의 항상 통과 대역은 이름만으로 보면 철회 통제를 숨기지만, 세션 재사용 시험은 원래 철회 기능의 회귀 시험이 아니다. 해당 시험은 정상 실행·재시도 경로의 fixture로만 사용되고, 철회 정책은 독립 시험에서 확인된다. 따라서 이번 시험의 의미를 속이지는 않는다. 반면 이 대역을 철회 동작 증거로 인용해서는 안 된다.

## S9b 제품 경로 반박 검토

### jti가 없는 claims / stdio

저장 claims에 `jti`가 없으면 새 코드는 `disposal.blocked(jti=None)`와 `agent_revoked_tokens`의 `jti=NULL` 조회를 수행한다. 그 조회만으로 허용되는 것은 아니다. 이어지는 실제 `pac.build`는 `bool(claims.get("jti"))`를 `auth_ok` 조건에 요구하고, OPA 입력의 인증 사실이 유효하지 않아 차단한다. 지원 ingress의 `authenticated_user` 역시 서명된 bearer token의 `claims["jti"]`를 먼저 검사한다. 따라서 jti-less 입력은 통과 경로가 아니다. 다만 저장된 비정상/구형 claims의 철회 조회는 불필요한 NULL 조회를 하고 최종 거부 정책은 기존 PAC/OPA에 의존한다. stdio 클라이언트가 유효한 jti 없는 Gateway 인증을 받는다는 증거는 없다.

### 관리형 엔드포인트 토큰

관리형 토큰도 transport JWT의 jti로 DB·서명 목록을 조회한다. 살아 있는 토큰이면 뒤의 `managed_failure`가 관리형 등록 상태·소유자·epoch·heartbeat·정책을 재검사하고, PAC가 `nbf <= now < exp`와 발급자·대상·주체를 확인한다. 장치 철회가 DB나 서명 목록 중 어느 한쪽에 남아 있으면 차단된다. 기존 `fresh_requester_check.py`는 격리·철회·만료를 대역 시험하지만 실제 JWT/DB/서명 파일 증거는 아니다.

### 승인 TTL 내 요청자 토큰 만료

승인 행이 아직 유효해도 저장 요청자 JWT 만료를 우회하지 않는다. `_call_upstream`은 승인 상태/만료를 먼저 확인한 뒤 PAC를 다시 만들며, 만료 claims는 `auth_ok=False`가 되어 OPA 차단을 받는다. 관리형 단기 토큰이 승인 TTL보다 먼저 만료되면 실행이 막히는 것은 D-152의 의도된 가용성 한계다. 승인 TTL 재확인 자체는 이 만료와 별도 검사다.

### 철회 DB 표와 서명 목록 불일치

두 조회는 OR로 결합되어 어느 한쪽에 jti가 있으면 `P-INPUT-001`로 차단한다. 서명 목록이 정상이고 jti가 없을 때 DB 조회 장애/예외는 `P-CONTROL-FAIL-CLOSED`로 간다. 서명 목록에 이미 jti가 있으면 단락 평가로 DB를 조회하지 않지만, 이미 확인한 폐기 사실만으로 차단은 안전하다. 과거 DB 복원으로 두 원본 모두에서 폐기 사실이 사라지는 경우는 두 조회만으로 탐지할 수 없으며 D-152도 이를 보장한다고 주장하지 않는다.

**확정 결함:** 실제 `disposal.blocked()`는 서명/파일 무결성 또는 읽기 오류를 내부에서 잡아 `True`를 반환한다. 따라서 S9b의 기존 호출은 “폐기 목록 확인 불가”를 예외 분기로 보내지 않고 `revoked=True`로 처리하여 `P-INPUT-001`을 기록한다. 요구된 `P-CONTROL-FAIL-CLOSED`와 실제 결과가 불일치하며 S9b 신규 시험의 `test_disposal_read_exception_is_fail_closed`는 `blocked` 대역이 예외를 직접 던져 실제 함수의 동작을 검증하지 않았다.

## 수정

- `disposal.blocked(..., raise_errors=True)`를 추가했다. 기본 동작은 기존 호출자와 호환되게 오류 시 `True`로 fail-closed이며, 옵션을 준 호출자만 `IntegrityError`/`OSError`를 받는다.
- 승인 dispatch의 새 검사는 옵션을 켜서 목록 장애를 예외 경로로 보내 `P-CONTROL-FAIL-CLOSED`로 기록한다. 실제 폐기 기록과 DB 철회 행은 계속 `P-INPUT-001`이다.
- 새 단위 사례는 `disposal.blocked`의 기본 fail-closed 호환과 예외 전파 옵션을 실제 AST 정의로 확인하고, 요청자 경로가 장애를 control-fail-closed로 매핑함을 확인한다.
- 기존 S10-B의 3개 hunk는 채택했다. 기존 assert/기대값은 고치거나 약화하지 않았다.

## 검증 범위와 한계

로컬 실행 결과는 작업 보고에 기록한다. AST 기반 대역 검사는 함수 로직과 정책 매핑의 단위 증거다. 게이트웨이 이미지 import, 실제 서명 폐기 파일의 무결성 오류, PostgreSQL 복원/경쟁, 실제 MCP·PJ1·배포 효과는 별도다. 파일 폐기와 DB 철회 사이의 불일치·한쪽 장애의 단위 시험은 명시적으로 구분하고 실제 운영 저장소의 복구/수렴은 입증하지 않는다.
