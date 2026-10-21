# DEV-75 미사용 도구 자동 비활성·재심사

## 범위와 근거

- 방향 정본: [`direction-1020/README.md` §3 DEV-75](../direction-1020/README.md), 완료 조건은 기한 도달 도구가 목록·호출에서 빠지고 자동 연장 조건에 사용 이력이 반영되는 것이다.
- 표준 근거: TC260 AI Safety Governance Framework 2.0 4.2.1(b) 및 4.2.3(a), 기존 위키 등록 [`LIB-M31`](../../papers/LIB-M31.md). 이 프레임워크는 권고·참고이고, 2026-10-17 확인 시 3.0 발표 후 최신판이 아니었다. 3.0 원문은 읽지 않았다.
- 기존 설계: `review.normalize_tool_reviews`, runtime `tool_reviews.*.reviewed_at`, `decisions(server_id, tool_name, created_at)`, `approval_events`, `mcp_facade._approved_tools`, `core.execute_call`, 기존 `P-APPROVAL-EXPIRY-001`.

## 결정

| 요구 | 구현·근거 |
| --- | --- |
| 사용 집계 | 새 집계 테이블 없이 `decisions`에서 `upstream_executed=true`인 서버·도구별 가장 최근 호출을 구한다. 차단 시도와 연결 이벤트는 사용으로 세지 않는다. |
| 설정 | `TOOL_SUNSET_IDLE_DAYS=90`, `TOOL_SUNSET_OBSERVATION_DAYS=30`, `TOOL_SUNSET_GRACE_DAYS=30`. compose 환경에서 덮어쓸 수 있다. 최종 비활성 기한은 마지막 사용(없으면 범위 심사 시각)+유휴기한+유예다. |
| 자료 공백 | `gateway_settings.ledger_retention` 하한이 유휴기한+유예보다 짧거나, audit-chain 봉인 구간이 확인 창과 겹치거나, 집계 조회가 실패하면 `자료 없음`으로 남긴다. 비활성 사건은 만들지 않는다. 설정/상태 조회 오류는 `tool-sunset-check` 실패 사건으로 남긴다. |
| 목록·호출 | 목록은 비활성 도구를 빼고, 직접 호출은 `P-APPROVAL-EXPIRY-001` 차단을 기록한다. 자동 정지 확인 자체가 실패하면 별도 통제 장애로 막되 비활성 상태로 저장하지 않는다. |
| 연장 | 기존 등록 승인 자동 연장은 관측창 안 `decisions` 사용이 최소 하나 있을 때만 진행한다. 기존 계약·공급망·신청 승인 검사는 그대로 유지하고 범위는 넓히지 않는다. 도구 사용·관측 창·마지막 사용·이전/새 기한을 `approval_events`에 남긴다. |
| 복구 | 다른 관리자가 기존 도구 범위 심사 API로 재심사·재승인하면 `tool-sunset-review`를 append하고 정상 사용으로 복귀한다. 자동 비활성 사건은 갱신·삭제하지 않는다. |
| 제품 화면 | 서버 도구 상세에서 마지막 사용, 비활성 기한, 이용 상태를 표시한다. 값이 없으면 `—`. |

## 요구사항·증거 연결

| 요구 ID | 조건 | 구현 위치 | 새 격리 시험 |
| --- | --- | --- | --- |
| TS-01 | 승인 도구의 원장 마지막 사용 조회·연장 기록 | `gateway/app/tool_sunset.py`, `core.renew_approvals` | `test_recent_window_appends_extension` |
| TS-02 | 기한 도달 도구가 목록에서 빠짐 | `gateway/app/mcp_facade.py::_approved_tools` | `test_list_and_call_use_sunset_state_and_existing_policy`의 목록 경로 결속 확인 |
| TS-03 | 직접 호출 차단, 정책 ID 확인 | `gateway/app/core.py::execute_call`, `P-APPROVAL-EXPIRY-001` | 같은 시험의 호출 경로 결속 확인 |
| TS-04 | 보존 창이 부족하면 미사용 판정 금지 | `tool_sunset._coverage` | `test_missing_retention_window_is_not_counted_as_unused` |
| TS-05 | 집계 실패 시 비활성 금지·실패 사건 | `tool_sunset.check` | `test_aggregation_failure_does_not_deactivate` |
| TS-06 | 자동 비활성·연장·재심사 사건 append | `tool_sunset.check`, `tool_sunset.approve_review` | `test_expired_tool_appends_automatic_sunset`, `test_recent_window_appends_extension`, `test_reapproval_is_an_append_only_human_event` |

## 한계와 방향 제안

- 이번 구현은 `reviewed_at`이 있는 Console 도입의 사람 심사 도구에만 자동 비활성을 적용한다. 정적 catalog/lock 도구에는 도구별 사람 승인 시각이 없어 `generated_at`을 승인 시각으로 추정하지 않는다. 이 도구들의 자동 비활성 범위를 넓히려면 contracts lock의 도구별 승인시각을 사람 승인 절차에서 관리하는 설계가 필요하다.
- 실행 시각은 tools/list, tools/call, Console 등록부 조회 시점이다. 트래픽이 없어도 기한에 맞춰 백그라운드 사건을 생성하는 스케줄러는 추가하지 않았다. 각 요청 경로에서 즉시 재평가하므로 만료 후 호출은 차단된다.
- 시험은 로컬 표준 라이브러리 격리 시험이다. 실제 PostgreSQL 원장·동시 호출, 콘솔 브라우저 렌더링, 배포/PJ1 효과는 미검증이다.
