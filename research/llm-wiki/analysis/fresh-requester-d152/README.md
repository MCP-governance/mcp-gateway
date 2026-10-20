# DEV-17 승인 실행 시 저장 요청자 토큰의 현재 유효성 재검증

2026-10-20 소유자의 범위 축소 지시로 아래 「이전 조사 이력」의 구현 중단 판단을 대체한다. 승인 즉시 실행을 유지하고 원 transport_claims의 현재 유효성을 재검사했다. 새 토큰으로 요청자가 재시도하는 모델은 미구현·결정 필요다. 기준 commit과 브랜치는 동일하며 기존 문서 초안에서 이어서 작업했다.

## 현재 구현·시험 연결

| 요구사항 | 제품 근거 (`full_stack_lab/gateway/app/`) | 새 시험 (`full_stack_lab/tests/fresh_requester_check.py`) | 증거·한계 |
| --- | --- | --- | --- |
| FR-CUR-01 원 요청자 jti의 현재 철회 | core._call_upstream의 승인 재확인 블록, disposal.blocked와 agent_revoked_tokens SELECT | test_jti_revoked_after_approval_before_dispatch, test_signed_disposal_blocks_without_database_revocation | 탐색 뒤 상태 변경·실행 0·P-INPUT-001·원장 호출 확인. 복원/서명 파일 검증 자체는 기존 disposal 구현 재사용, 미실행 |
| FR-CUR-02 엄격한 만료 | pac.build의 ns(nbf) <= now < ns(exp), 기존 최종 PAC/OPA 재판정 | test_expired_token_keeps_original_pac_denial, test_token_expires_during_discovery | 실제 builder의 auth.verified=false·만료 경계·실행 0. OPA는 HTTP 대역이 PAC-04를 반환하므로 실제 OPA의 우선순위 선택 증거가 아님 |
| FR-CUR-03 현재 장치 결속 | endpoint_plane.managed_failure, core.execute_call/_call_upstream | test_isolated_device_after_approval | 실제 managed_failure에 AsyncMock DB, 탐색 뒤 격리·ENDPOINT-MANAGED-001·실행 0 |
| FR-CUR-04 현재 주체 활성 | core.execute_call, 기존 dispatch.record/D-140 | test_subject_disabled_after_approval | 승인 사건 뒤 주체 중지·P-INPUT-001·실행 0. 기존 dispatch_recheck_check 15건은 별도 재실행, 실제 PG 잠금 증거 아님 |
| FR-CUR-05 실패 차단·원장·즉시 실행 유지 | core.DispatchRejected → execute_call → _decision_payload → approve_request | test_revocation_database_failure_is_fail_closed, test_disposal_read_exception_is_fail_closed, test_healthy_requester_executes_once_on_approval | 원장 append 함수 호출·요청자/승인 연결·NOT_EXECUTED/EXECUTED 상태·원본 payload 보존. 실제 원장 DB와 tools/call은 대역 |

core의 전송 직전 승인 블록만 13줄 추가했다. 신원은 기존 ingress가 검증해 저장한 transport_claims/user_token을 그대로 사용하며 승인자 신원이나 arguments로 대체하지 않는다. 직원 bearer 토큰은 MCP 호출 인자에 추가하지 않는다. 기존 시험·정책 ID·OPA·DB 스키마·콘솔·status/current.md는 변경하지 않았다.

기존 코드·의존성 재사용에 한정한 보강이며 새 OSS/SDK·외부 공개 스킬을 채택/실행하지 않았다. authenticated_user가 이미 사용하는 disposal.blocked와 동일한 철회 SQL을 재사용한다. 로컬 ponytail 스킬(MIT)은 최소 변경 검토에만 사용했다. 원격 HEAD 재조회는 github.com:443 연결 실패다. 현재 검사와 intent 커밋/송신 사이 경쟁 간격은 남으며 요청자 재시도의 같은 장치·새 jti 결속 문제를 해결했다고 주장하지 않는다.

## 이전 조사 이력 — 요청자 재시도 모델의 중단 근거(현재 범위와 구분)

2026-10-20, Codex sol. 브랜치 `10/20-fresh-requester`, 기준 commit `554307444dfc8dcb91c281c1a282427ee83e2efc`, 시작 작업 트리 clean. 아래 행은 이 commit 기준이다. 제품 구현·새 시험·배포는 하지 않았다.

## 실제 승인 실행 경로

1. `full_stack_lab/gateway/app/mcp_facade.py:44`의 `_caller`는 HTTP 요청의 Authorization을 `authenticated_user(..., require_mcp=True)`로 검증한다. `:241`에서 검증된 주체와 claims를 `execute_call`에 넘긴다. stdio의 정적 주체 경로는 claims가 비어 있어 새 transport 인증을 제공하지 않는다.
2. `core.py:2210`은 Approval일 때 서버·도구·인자·주체·클라이언트·**당시 transport_claims**와 PAC nonce/digest를 승인 payload로 저장한다. 승인 TTL은 10분(`core.py:49`), 관리형 장치 토큰 수명은 5분(`idp.py:202`)이다.
3. `main.py:670`의 승인 API는 `Depends(admin_caller)`로 **승인자의 Console 인증**을 받고 `approve_request`에는 승인자의 principal만 넘긴다. 새 요청자 토큰을 받지 않는다.
4. `core.py:2306`의 `approve_request`는 독립 승인자·설명 열람·기한을 확인하고 승인 사건을 기록한다. `:2345`에서 저장 payload를 읽고 무결성 지문을 검사한 뒤 `:2350`에서 곧바로 `execute_call(payload, approval_granted=True, approval_id=...)`을 실행한다. **요청자의 재시도 호출이 아니라 승인자 행위가 실행을 유발하며, 실행 신원은 저장된 요청자의 과거 claims다.**
5. `execute_call`은 현재 principal·관리형 장치·카탈로그·PAC·동의를 판정한다. `_call_upstream`의 `core.py:1536` 이후는 현재 principal/managed_failure·PAC/OPA를 다시 확인한다. `dispatch.record`는 주체·서버·도구·동의·승인을 잠그고, D-140의 흐름 재확인과 intent/승인 소비를 같은 트랜잭션에서 수행한다. 이 재확인들이 있어도 새로운 요청자 transport 인증이 생기지는 않는다.
6. `pac.py:196`은 원 claims의 주체·발급자·대상·jti 철회·`nbf <= now < exp`를 검사한다. 만료 토큰은 계속 거부된다. 후보 B2 보고의 원 토큰 수명 우회 제안은 이번 요구사항과 달라 채택할 수 없다. 해당 보고의 과거 실행 미재현 표시는 유지한다.

## 기존 결속과 남은 공백

- `core.py:2346`의 승인 payload 지문 검증, `high_impact.bound`의 서버·도구·인자·주체·심사 범위 검증, `dispatch.py:124` 이후의 실제 intent 주체/요청 지문 대조와 승인 1회 소비는 존재한다.
- `pac.digest`(`pac.py:151`)는 `facts.identity.session_id`, 즉 `jti`(`:199`)를 포함한다. 새 토큰으로 단순 교체하면 기존 `pac_digest`와 달라지므로, 새 인증과 승인 요청의 결속을 별도로 설계해야 한다. 저장 원본이나 감사 원장을 새 digest로 덮어써서는 안 된다.
- digest의 `connection.endpoint_id`는 요청자 장치가 아니라 `spec.endpoint`인 상위 MCP 주소(`pac.py:234`)다. 이름만 보고 같은 요청자 장치 결속으로 해석할 수 없다.
- `endpoint_plane.managed_failure`(`:939`)는 현재 claims의 device_id·소유자·epoch·정책·heartbeat를 확인하지만 **승인 당시 장치와 현재 장치를 비교하는 함수는 아니다.** 새 토큰의 다른 장치 소비를 이 함수만으로 막았다고 주장할 수 없다.
- D-140의 최종 intent 커밋 경계와 실제 송신 사이 간격은 남는다. 이번에는 신선한 인증·철회·권한 경합의 실기기 효과를 검증하지 않았다.

## 기존 시험 변경 필요

사용자 작업 규칙: **“기존 시험 파일의 기대값을 바꾸지 않는다. 바꿔야 하면 바꾸지 말고 '기존 시험 변경 필요' 절에 이유를 적어 멈춘다(사람이 적대 검증 후 결정).”**

| 기존 시험 | 현재 기대값 | 새 요구사항과 충돌 |
| --- | --- | --- |
| `full_stack_lab/tests/high_impact_check.py:139` | 승인자 principal만 받는 `approve_request` 반환에서 `upstream_executed=True`(`:145`) | 새 요청자 transport 인증 없이 승인 행위 자체가 실행해야 통과한다. 로컬에서 해당 시험 포함 기존 스위트 실행으로 확인했다. |
| `full_stack_lab/gateway/app/acceptance.py:271`의 `approval_runs_once` | `approve_request(id, admin)` 직후 실행됨(`:277`) | 승인 완료와 요청자 재인증 실행을 분리하면 깨진다. 소스 확인만 했고 실제 MCP 인수 시험은 미실행이다. |
| `full_stack_lab/tests/dispatch_effect_lab.py:166`의 `approval_reuse` | 6명의 승인 경쟁 중 1개가 즉시 실행되고 독립 하위 효과 1개가 존재(`:175` 이후) | 새 요청자 호출을 추가하지 않으면 실행 효과를 요구할 수 없다. 소스 확인만 했고 실제 MCP 시험은 미실행이다. |

새 요청자 인증이 없는 기존 호출에서 자동 실행을 유지하는 우회, 합성 계정 전용 예외, 저장 claims 재사용을 유지하는 호환 분기는 DEV-17 완료 조건을 충족하지 않는다. 따라서 제품 코드·기존 시험을 모두 보존하고 구현을 중단했다. 새 `fresh_requester_check.py`도 구현 전 중단으로 만들지 않았다.

## 재개 시 요구사항과 시험 설계 — 미구현

| 원자 요구사항 | 적용 후보 | 새 시험 조건 |
| --- | --- | --- |
| FR-01 승인과 실행 분리 | 승인 API는 APPROVED와 사건만 기록하고, 요청자의 실제 MCP 재시도로 실행 연결 | 승인만으로 execute_call/intent/tools/call 호출 0 |
| FR-02 현재 transport 인증 | 기존 `_caller`/`authenticated_user`, PAC 만료·철회, managed_failure 재사용 | 승인 뒤 만료 또는 철회 토큰은 차단, 승인 미소비, 외부 효과 0; 검사 장애도 차단 |
| FR-03 요청·주체·장치 결속 | 서버·도구·인자·principal·sub·device_id/epoch를 승인 원본과 비교; 새 jti는 현재 인증 사실로만 취급 | 다른 주체·다른 장치·다른 인자는 소비 불가; 같은 장치의 정상 재인증은 승인 TTL 안에서만 가능 |
| FR-04 현재 권한 재판정 | execute_call → _call_upstream의 기존 PAC/OPA·역할·관리형 장치 확인, dispatch.record의 동의·서버/도구·흐름 검사 | 승인 뒤 권한 축소·동의 철회·서버 중지·최종 검사 실패에서 decision와 policy_id, 전송 0 확인 |
| FR-05 일회 소비·경쟁·복구 | 기존 승인 FOR UPDATE·intent 트랜잭션·UNCONFIRMED 소비 유지 | 정상 새 인증 1회 실행, 동시 소비 1승, 재사용 거부, 실패 뒤 승인 상태·intent 원복/미확인 구분 |

재개 후 `full_stack_lab/tests/fresh_requester_check.py`에 표준 unittest/AsyncMock 대역으로 추가한다. 단위 DB/HTTP 대역만 사용하고 자체 MCP 서버를 만들지 않는다. 만료·철회·권한 축소·다른 장치·정상 재인증의 다섯 필수 사례를 포함한다. 실제 PG 잠금과 PJ1 하네스/OSS MCP 효과는 별도 검수다.

기존 의존성·재확인 함수를 재사용하는 방향이며 새 라이브러리·OPA ID·DB 변경은 선정하지 않았다. 구현 중단 단계이므로 외부 GitHub 스킬/OSS의 신규 조사·도입도 하지 않았다. 원격 HEAD 확인은 `git ls-remote --symref origin HEAD`의 github.com:443 연결 실패로 미확인이다.

결정: [D-152](../../../../docs/ai/DECISIONS.md). 결과·검증: [작업 보고](../../status/reports/2026-10-20-fresh-requester.md).
