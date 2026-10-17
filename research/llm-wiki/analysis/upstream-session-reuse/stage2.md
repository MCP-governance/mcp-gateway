# DEV-29 2단계 구현과 시험 대응 — D-115

2026-10-17 · 시작 commit `9537c0b494a0c4d45c615caa4797674f273d270f` · 로컬 작업 트리 구현.
[설계 비교](README.md)의 제안을 사용자 채택 범위(2단계까지)에 맞춰 구현했다.
[D-115](../../../../docs/ai/DECISIONS.md) · [보고서](../../status/reports/2026-10-17-upstream-session-reuse-stage2.md).
단위 대역 결과이며 실제 SDK·MCP·DB·기기 효과·배포 검증은 아니다.

## 메인 리뷰 및 A 통합 정정

관계 사전 검사는 foreground session에서 제거했고 background 폐기에만 사용한다. 종료 판정/감사 정책 ID는 기존 core/dispatch 경로가 결정한다. 시작 시 커서는 같은 잠금 아래 max(id)로 초기화하고 모든 dispatch가 이 초기화 뒤에만 열린다. 초기화 실패는 새 연결을 거부한다. `Pool.borrow` 대기는 호출자의 dispatch_budget으로 제한한다. A의 내부망 판별값도 키에 추가하고 고정 transport에 전달한다. 이전 T11 첫 이벤트 재생 시험은 아래 시험으로 대체했다: `test_T11_initial_cursor_skips_prestart_events_before_any_session`, `test_T11_initialization_failure_refuses_to_open`, `test_T11_first_dispatches_wait_for_initial_cursor_then_apply_new_event`.
실제 git merge/commit은 공용 .git 쓰기 거부로 실행하지 못했고, e53e229 파일 내용을 3-way 통합했다. 상세 결과는 작업 보고의 메인 리뷰 후속 절을 따른다.

## 키와 수명

| 요소 | 코드의 출처 | 필요한 이유 |
| --- | --- | --- |
| 주체 | `mcp_facade._caller`의 검증한 `user.principal` → `core._call_upstream` | 다른 직원의 상태 공유 방지. 도구 인자/자기 신고 신원은 사용하지 않음 |
| 다운스트림 세션 | SDK가 허용한 구형 HTTP 요청의 `Mcp-Session-Id`, `mcp_facade._conversation` | 같은 직원의 다른 대화 분리. ContextForge #4205 반례 |
| 검증한 토큰 `jti` (추가) | `authenticated_user`의 claims → ContextVar | 같은 직원의 다른 로그인/하네스가 세션 ID를 재생해도 업스트림 상태를 공유하지 못함. 원본 Bearer는 저장/전달하지 않음 |
| 서버 ID | 등록 서버 경로 또는 도구 접두사 → `_call_upstream` | 동일 목적지라도 서로 다른 등록/권한 범위는 별도 상태 |
| 자격 해시 | `credential_headers`의 운영자 공급자 자격만 SHA-256 | 자격 교체/제거/바인딩 변경 뒤 옛 세션을 사용하지 않음 |
| endpoint (추가) | `registry.server` | 등록 주소 변경 뒤 같은 ID의 이전 목적지 세션 사용 금지 |
| 승인 프로토콜 판 (추가) | `registry.pinned_protocol` | 다른 연결 세대/판의 옛 세션 사용 금지 |
| timeout (추가) | 호출부 연결 설정 | SDK 세션/HTTP 클라이언트에 고정된 시간 제한을 바꾼 뒤 옛 설정 사용 금지 |

개별 `approval_id`·도구·인자·조직/자산 권한은 세션의 권한으로 저장하지 않는다. 매 호출 정책/계약/승인을 재확인한다.
바인딩은 ContextVar에만 두고 일반 `execute_call` payload나 저장된 승인 payload에서 복원하지 않는다.
따라서 Console 승인 후 재실행은 새 MCP 세션이며, 원래 대화의 탭 유지에 의존하는 승인 업무는 실기기 검수가 필요하다.

키당 1개 세션, 호출 전체 직렬화, 전체 `UPSTREAM_POOL_SIZE`(기본 32), 유휴 60초·최대 600초.
설계 제안의 키당 최대 4개 동시 세션은 한 대화의 상태를 여러 세션으로 갈라놓으므로 채택하지 않았다.
다른 키는 병렬, 상한에서는 유휴 LRU를 닫고 모두 사용 중이면 대기한다. 폐기와 겹친 대기 호출은 보수적으로 거부한다.
전용 소유 태스크가 SDK context를 열고 닫아 AnyIO cancel scope의 태스크 일치를 지킨다.
신형(`2026-07-28`)·미확인 판·세션 없음·`jti` 없음은 MCP 세션 재사용을 하지 않는다. HTTP 연결 풀은 기존 동작을 유지한다.

## 원자 요구사항과 코드/시험

| ID | 요구·정상/음성/경계/실패/복구 조건 | 제품 코드 심볼 | 단위 증거 |
| --- | --- | --- | --- |
| SR2-01 | 20회 연속 호출은 초기화 1번; 주체/대화/로그인/서버 분리 | `upstream_sessions.Key`, `Pool.borrow`, `mcp_facade._conversation` | `PoolTests.test_T1_reuse_without_reopening`, `test_T2_T3_every_key_boundary_is_separate`, `WiringTests.test_conversation_uses_transport_session_and_verified_jti` |
| SR2-02 | 구형만 재사용; 신형/미확인/무세션/메타데이터/승인 재실행은 호출별 | `upstream.session`, `connect_mode` | `test_legacy_only_reuse_and_no_downstream_fallback`, `test_T12_pinned_generation_and_unknown_version` |
| SR2-03 | 매 페이지 목록 요청은 SDK TTL과 무관하게 새 요청, 매 호출 정책·마지막 전송 확인 | `upstream._session`, `list_all_tools`, `core._call_upstream` | `test_T1_T7_sdk_cache_none_and_operator_headers_only`, `test_T7_every_page_bypasses_positive_ttl_cache`, `test_T4_policy_rechecked_every_call_on_same_connection` |
| SR2-04 | 주체 중지·서버 종료·승인 거부는 전송 0/세션 폐기; 계약 불일치·OPA 장애도 차단 | `close_pool`, `release_pool`, `_dispatch_allowed`, `core.reject_request`, `deregister_server`, `_call_upstream` | `test_T4_T5_close_active_and_refuse_waiter`, `test_T4_T5_final_cutover_and_approval_revoke_prevent_send`, `test_T4_policy_failure_remains_fail_closed`, `test_T7_changed_contract_closes_and_never_sends` |
| SR2-05 | 자격·주소·판·시간 제한 변경은 옛 세션 폐기; 전송 직전 자격 교체도 거부 | `Pool.borrow`, `Lease._client`, `credential_hash` | `test_T6_rotation_retires_all_old_conversations`, `test_configuration_change_retires_old_session`, `test_T6_rotation_during_borrow_prevents_send` |
| SR2-06 | 같은 키 동시 10회는 1세션/직렬; 응답은 인자와 1:1, 상한·유휴 LRU | `Pool.borrow` | `test_T9_ten_concurrent_calls_serialize_one_session`, `test_capacity_evicts_idle_not_active` |
| SR2-07 | 무호출 상태에도 유휴/최대 수명·자격/주체/등록/도입 승인/기한 감시 | `Pool.prune`, `upstream.maintain_pool`, `_dispatch_allowed`, `main.lifespan` | `test_expiry_idle_and_maximum_lifetime`, `test_maintenance_closes_rotation_revocation_and_expiry_without_new_call` |
| SR2-08 | 시작 중 폐기/대기 중 중지/자격 교체 정리 중 중지/취소는 재개하지 않음 | `Lease.discard`, `Pool.prune/borrow/close` | `test_close_while_opening_unblocks_borrower`, `test_revocation_during_rotation_cleanup_prevents_reopen`, `test_T10_error_and_cancellation_discard` |
| SR2-09 | 목록 단계의 정확한 SDK 세션 404만 1회 재연결, 실행 뒤 재시도 0/시도됨 유지 | `session_terminated`, `core._call_upstream` | `test_T10_only_exact_sdk_session_404_is_retryable`, `test_T10_list_expiry_retries_once_before_intent`, `test_T10_second_list_failure_stops_and_call_failure_never_retries` |
| SR2-10 | 프로세스 시작 전 이벤트와 이후 새 세션의 세대 구분, 실패 후 커서 전진 금지, DELETE 성공만 대화 폐기 | `_sweep`, `close_downstream`, `main.RequireBearer` | `test_T11_initial_cursor_skips_prestart_events_before_any_session`, `test_T11_failed_close_does_not_advance_cursor`, `test_T11_downstream_event_only_closes_matching_conversation`, `test_successful_delete_closes_and_failed_delete_preserves_session` |
| SR2-11 | SDK 시작/도구 오류도 폐기; 종료는 SDK context와 같은 태스크 | `Lease._own/call_tool`, `Pool._finish` | `test_opening_failure_is_closed_not_success`, `test_tool_error_is_definite_response_but_session_is_discarded`, 모든 pool factory의 같은 태스크 assert |
| SR2-12 | 시간 구간 집계 호환, 재사용 불리언은 시간값과 분리, 원장 append-only 유지 | `core._call_upstream`, `_record_decision`의 기존 client 저장 | 풀 첫/재사용 `reused` 확인; 콘솔 상태 시험의 latency 단위/누락값 회귀. 실제 원장·API는 미실행 |

단위 시험은 `full_stack_lab/tests/upstream_session_reuse_test.py`의 제품 모듈 및 AST로 선택한 제품 함수 본문을 실행한다.
SDK·DB·OPA·MCP 응답은 모의 객체이며 `mcp_result_contract_check.py`의 페이지 대역도 새 bypass 인자를 받도록 바꿨다.
이 방식은 로컬 Python 3.10에서 동작하지만 제품 전체 import/실제 SDK cancel scope/SQL 실행을 검증하지 못한다.
코드 판본·행·해시는 [code-evidence.json](code-evidence.json)에 별도 기록한다. 옛 실험의 해시를 새 통과 근거로 대체하지 않는다.

## 기기에서 메인이 실행할 T1–T12

| 시험 | 로컬 확인 / 남은 실제 시험 |
| --- | --- |
| T1 | 풀 연속 대여 단위 통과. 실제 **구형** 승인 OSS 20회, `client.upstream_session_reused`, initialize/DELETE 수·직원 토큰 미전달·`decisions.timings`/`GET /api/latency` 전후와 독립 효과를 비교. Gitea 2026-07-28은 재사용 대조군이지 세션 재사용 성공 대상이 아님 |
| T2·T3 | 키 분리 단위 통과. 공개 OSS Playwright의 주체별/동일 주체 다른 대화 탭 분리와 한 대화 상태 유지, 이메일 상태 의존성·토큰 refresh 시 `jti` 변경 효과를 확인 |
| T4 | 대역 마지막 `dispatch.record` 거부/OPA 실패 단위 통과. PJ1 실제 호출을 예약~전송 사이 붙잡고 주체 중지, 원장 `decision/policy_id`, 업스트림 효과 0, 활성 세션 폐기 확인 |
| T5 | 폐기·대기·DELETE 단위 통과. 실제 서버 종료/등록 해제/승인 철회/기한 만료, `MCP-DECOMM-001` 차단, 신규 initialize/도구 호출 0, 기존 서버측 세션 0을 독립 확인 |
| T6 | 자격 변경·전송 직전 거부 단위 통과. 실제 운영자 자격 파일 교체/제거/만료/허용 주체 변경 뒤 옛 토큰 수신 0, 새 세션/정상 복구 확인. 중간에 이미 전송된 호출은 되돌릴 수 없음 |
| T7 | 모든 페이지 bypass·Client cache=None·계약 변경 차단 단위 통과. 실제 SDK 2.2.0과 구형 재사용/신형 양쪽에서 양의 `ttlMs`·2페이지 이후 변경을 주고 다음 호출 차단/목록 요청 도달을 확인 |
| T8 | **미채택·미구현**, 읽기 목록 캐시/TOCTOU 창 시험하지 않음 |
| T9 | 10개 동일 키 대여 직렬·응답 대응 단위 통과. 실제 SDK 요청 ID/취소/통신 장애 경합·다른 키 병렬·전체 상한/대기 예산·세션 1개를 확인. 직렬화로 같은 대화 동시 호출 지연이 늘 수 있음 |
| T10 | 목록 단계만 정확한 세션 404 재연결 1회, 두 번째 실패 차단/실행 뒤 재시도 0 단위 통과. 실제 OSS 재시작·응답 유실·DELETE 미지원·5초 정리 취소에서 실행 여부 불명/쓰기 중복 없음/재접속 복구 확인 |
| T11 | 시작 커서 초기화·동시 초기화·이후 이벤트/커서 보존·대화 선택 폐기 단위 통과. Gateway 2프로세스에서 주체/등록/승인 철회/대화 DELETE 전파를 실측. 유휴 상태 폐기·실패 시 커서 재처리·감시 종료/프로세스 재기동 확인. 2초는 감시 간격이며 DB/DELETE 지연 포함 실제 상한은 미검증 |
| T12 | 고정판/미확인판 분기 단위 통과. D-110 구현은 판 변경 시 실패 후 카탈로그 재검토이며, 설계 당시 `auto` 1회 자동 재협상 제안은 이번에 추가하지 않음. 실제 판 변경 실패·재승인 후 복구를 확인; 원래 T12의 자동 복구 성공 조건은 충족했다고 보고하지 않음 |

시험 대상은 이미 사람이 승인한 상용/OSS MCP만 쓴다. 새 mock MCP나 에이전트 자가 승인은 만들지 않는다.
배포 전 메인이 제품 Python/SDK가 있는 환경에서 pyflakes·기존 SDK result/protocol 시험도 실행해야 한다.
종료 판정 C1~C4/T1~T3 규칙은 바꾸지 않았으며 세션 폐기를 서비스 자격 회수 증거로 세지 않는다.

## 근거와 통합 주의

- 기존 고정 근거: MCP 규격 `86f6e0c`, ContextForge `5735c9d`(Apache-2.0), Microsoft `3594c4e`(MIT), MCPX `7193eab`(MIT). 세션별 결속/직렬화/축출만 설계 근거로 쓰고 외부 구현을 복사하지 않았다([원 비교의 행 링크](README.md#2-근거-고정-판본)).
- MCP Python SDK: 로컬 읽기 전용 `../ref-src/mcp-python-sdk`, commit `9972c21aa42054fb1450c5fc614761ed11847ec6`, tag v2.2.0, MIT(파일 확인). `client.py`의 `cache=None`/`cache_mode`와 `streamable_http.py`의 세션 404 변환, 서버 `context.py`/manager의 admitted legacy HTTP 요청 경로를 대조했다. SDK 2.2.0 채택은 기존 의존성 그대로다.
- 공개 GitHub 스킬 탐색(10-17, `site:github.com SKILL.md MCP session reuse cache`)은 수행했으나 채택/실행한 외부 스킬은 없다. 일반 MCP/스킬 제공 스킬은 이 제품의 승인·전송 의도·폐기 경계를 구현하지 않는다. 기존 고정 OSS와 SDK를 재사용했다. 새 의존성 없음.
- 작업 A 통합 충돌 후보: `upstream.py`의 import, `_dispatch_client`(이벤트 sweep을 바깥 `session`으로 이동), 기존 `session`을 `_session`으로 분리한 영역과 `Client(cache=None)`. `_client`/`streamable_http_client`의 DNS·IP·transport 설정은 변경하지 않았다. A의 승인 목적지 transport는 `_session`이 생성하는 최초 연결에도 적용되어야 한다.
- 한계: 논리 폐기는 즉시지만 이미 전송한 호출/서버측 자격 회수는 별도다. 다른 프로세스·외부 자격 파일 변경은 감시/다음 대여/SDK 전송 전 검증에서 관찰한다. HTTP 풀의 자격 보관 수명은 기존 구현이며 MCP 세션 최대 수명과 동일한 전역 비밀 보관 상한으로 해석하지 않는다. 재사용 연결의 DNS/IP 재검증 시점은 작업 A와 통합 검토한다.
