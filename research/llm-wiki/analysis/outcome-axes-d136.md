# DEV-48 결과 네 축 — D-136

기준: `c002fbd5fcf5f928e5ad68c57fa05edb1f76b1a6`, 브랜치 `10/20-result-outcomes`, 2026-10-20, Codex sol.
구현과 로컬 검증만 기록한다. 기존 시험 대역 변경이 필요하여 중단했으며 배포·검수 완료가 아니다.

## 요구사항과 코드·시험 연결

| 요구 | 코드 심볼 | 새 시험의 조건·효과 | 한계 |
| --- | --- | --- | --- |
| 연결과 전송 분리 | `core._call_upstream`, `outcomes.outcome_axes` | 미시도·연결 실패·연결 성공, 연결 후 계약 변경 | 과거 행은 연결 세부 증거 없음 |
| 정책 거부와 장애 분리 | `outcomes.outcome_axes` | 정상, 범위 거부, Presidio, OPA, 계약 변경, 관리대장·입력·번들 불능 | 같은 정책 ID의 상세 원인은 새로 추론하지 않음 |
| 관찰 판정 분리 | `outcomes.outcome_axes` | `would_decision=Block`이어도 실효 허용 유지 | 기존 would 필드 보존 |
| 업무 결과 분리 | `outcomes.outcome_axes` | `is_error`, Context7 월 할당량 접두어, 401·403·429, 일반 문서의 반례 | 알려지지 않은 공급자 문구는 임의 분류하지 않음 |
| 검사기 출력 장애 | `core.execute_call` | `control_failure=True`, 통제 장애 차단+응답 보류 | 실제 Presidio 장애 주입 미실행 |
| HTTP 증거 보존 | `core._upstream_failure` | 중첩 원인에서 상태 코드만 추출, 원문 제거 후 분류 유지 | SDK가 감춘 HTTP 상태는 복원 불가 |
| 응답 보류 분리 | `outcomes.outcome_axes` | `MCP-OUTPUT-001`, 실행은 확인돼도 답변 보류 | 독립 효과는 미확인 |
| 독립 효과 분리 | `recorded_outcome`, 조회의 `dispatch_intents` 상태 투영 | pending·uncertain·resolved는 미확인, confirmed 두 값만 반영 | 관리자 확인의 정확성은 이 구현이 독립 검증하지 않음 |
| append-only 유지 | `core._record_decision`, `v2_tables.sql` | AsyncMock INSERT의 열·인자 개수, 해시 대상 확인, UPDATE 없음 | 실제 PostgreSQL 마이그레이션·재시작 미실행 |
| 과거 기록 호환 | `recorded_outcome`, `activity.describe`, `audit.with_outcome` | 원본 불변, 정보 부족은 업무 미확인, 저장 스냅샷 우선 | 이전에 버린 is_error·문구는 복원 못 함 |
| 체인 호환 | `contract.AUDIT_COLUMN_SETS`, `audit_fingerprint` | 8판 outcome 변경 검출, 1~7판 지문 불변 | 실제 혼합 체인 전체 검증 미실행 |
| 화면·비밀 경계 | `outcomeChips`, `audit.with_outcome` | 네 라벨·누락값, 실제 html 이스케이프, 내부 오류 응답 제외 | 브라우저 시각 검증 미실행 |

시험 정본: [outcome_axes_check.py](../../../full_stack_lab/tests/outcome_axes_check.py), [화면 렌더 함수 시험](../../../full_stack_lab/tests/outcome-console.test.mjs).
Python 순수 시험 8건, 대표 사례 17개를 포함한다. `--gateway`에서 실제 모듈 import·조회 투영 대역 시험 1건을 더 실행한다.

## 근거와 적용 범위

- 기존 [재설계](oss-deep/redesign-2026-10-15.md), [ContextForge 분석](oss-deep/contextforge-hooks.md)의 **상단 정정**을 적용했다. ContextForge 전체가 fail-open이라는 본문 일반화는 채택하지 않았다.
- ContextForge `5735c9db7f8f50cd5a55eb7fefe83ecde00b5324`, CPEX 플러그인 `ae26938128cb438a268e7f3217603bc39b9dd18f`, Apache-2.0: 기존 고정 분석에서 정책 위반과 검사기 오류의 분리만 참고. 코드 복사·의존성 추가·실행 없음. 현재 유지보수 상태는 재확인하지 못했다.
- GitHub 공개 스킬 탐색: [Context7 find-docs](https://github.com/upstash/context7/blob/master/skills/find-docs/SKILL.md)의 오류 처리 절을 자료로 읽었다. `Monthly quota reached`와 할당량 초과 구분에만 사용했다. 저장소 [MIT 라이선스](https://github.com/upstash/context7/blob/master/LICENSE) 확인. 원격 API commit 조회 실패로 이 스킬의 commit 고정은 미완료이며 운영 코드·외부 명령은 도입하지 않았다. 공개 문서가 조회되는 사실만 확인했고 유지보수 SLA를 추정하지 않았다.
- [Context7 자체 이슈 2145](https://github.com/upstash/context7/issues/2145)의 월 할당량 오류 문구와 기존 MINT의 실제 관측을 대조했다. 문서 본문 임의 위치의 `quota`·`rate`·`unauthorized` 단어는 분류하지 않는다. 접두어를 그대로 인용하는 정상 문서는 오탐할 수 있다.
- [MCP 2025-06-18 Tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools): 도구 오류 플래그와 프로토콜 오류 구별. MCP 성공 응답을 독립 효과 성공으로 승격하지 않는다.
- [RFC 9110 §15.5.2·§15.5.4](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.2), [RFC 6585 §4](https://www.rfc-editor.org/rfc/rfc6585.html#section-4): 실제 HTTP 예외의 401·403·429만 공급자 한도·인증 실패로 묶는다. 응답 본문에서 HTTP 숫자를 추측하지 않는다.
- 적용 스킬: 로컬 ponytail 5.3.2(MIT), 기존 의존성과 표준 라이브러리 우선. 외부 스킬 스크립트는 실행하지 않았다.

## 조회와 지문의 경계

`decisions.outcome`은 기록 당시 값이며 체인 8판이 보호한다. `outcome_axes`는 화면용 투영으로, NULL 과거 행은 순수 함수로 계산하고 관리자 확인이 있는 경우 독립 효과만 최신 `dispatch_intents` 상태에서 읽는다.
감사 API는 저장 스냅샷 `outcome`과 조회 투영 `outcome_axes`를 함께 반환한다. 조회값을 체인의 저장값이라고 주장하지 않는다. 기존 행·정책 판정·효과 확인 기록을 재작성하지 않는다.

## 기존 시험 변경 필요

`tests/dest_pin_credential_redaction_check.py` 실행: 16건 중 14건 통과, 2건 오류. 기존 기대값은 바꾸지 않았다.

- `CredentialRedaction.test_audit_and_returned_payload_share_redacted_error_before_hash`: AST로 추출한 `_record_decision`의 namespace에 `outcome_axes`가 없어 NameError.
- `DestinationPin.test_egress_failure_has_correct_decision_even_in_cause`: AST로 추출한 `_upstream_failure`의 namespace에 `httpx`가 없어 NameError.

기존 함수 본문의 새 의존성을 기존 시험 대역에 주입하는 변경이 필요하다. 정상 모듈 import는 해당 의존성을 제공하지만 이 시험은 import를 생략한다. 소유자가 적대 검증 후 결정하도록 시험 파일은 수정하지 않고 구현 작업을 중단했다. 새로운 시험의 해당 대역에는 이 의존성을 명시적으로 주입했다. 전체 회귀 통과나 DEV-48 검수 완료로 기록하지 않는다.
