# DEV-79 직원별 MCP 서버 이용 중지·재개 — 원자 요구사항과 근거

결정은 [D-181](../../../../docs/ai/DECISIONS.md), 작업 보고는 [2026-10-21-user-server-suspend](../../status/reports/2026-10-21-user-server-suspend.md)이다.
기준 commit `d3238dc`(브랜치 `10/21-dev79-stop`). 구현·로컬 대역 시험·로컬 일회성 PostgreSQL 확인까지이며 기기 배포·PJ1 실제 하네스 시험은 하지 않았다.

## 근거 출처

| 출처 | 읽은 범위 | 이 작업에서 쓴 내용 |
| --- | --- | --- |
| [방향 갱신 10-20](../direction-1020/README.md) 3장 DEV-79(72행) | 해당 행 전문 | 원문: 「콘솔 계정은 살리고 **그 직원·장치**의 MCP 호출만 즉시 중지·재개」, 완료 조건 「중지 다음 호출부터 거부, 재개 후 정상, **진행 중 호출 처리 기록**」, 위험 「기존 계정 중지·세션 종료(G07.02)와 상태 구분」 |
| [통제 검토](../direction-1020/control-review.md) 11·105·115행 | 해당 행 | DEV-79 유지. 근거는 REQ-M31-07(TC260 4.2.3(b)-(c)), REQ-M05-03(**제2항**; README의 「제3항」은 표준 체계 조항이라 정정). DEV-74는 「경보 + DEV-79 중지 제안」이 기본이고 같은 상태 값을 재사용 |
| [요구사항 정본](../compliance/requirements.json) | REQ-M05-03, REQ-M31-07 | M05 제2항: 비준수 행동을 발견·개입·차단·복구하는 능력(권고). TC260 4.2.3(b)-(c): 극단 상황에서 빠르게 개입해 손실을 막는 서킷 브레이커·원클릭 통제(권고, 운영자 의무, 고도 자율 기능 도입 시). 둘 다 비구속 |
| `docs/ai/DECISIONS.md` D-122 | 전문 | 서버 단위 자동 중지 구조(`ops_suspensions`: 복귀 필드를 채우는 상태 행 + `approval_events`)와 「이미 전송된 호출은 취소하지 않는다」 한계 |
| D-134·D-140 | 해당 항 | 사용자×서버×도구 단위 상태(`user_consents`)와 최종 dispatch 트랜잭션의 주체 advisory lock → 서버/도구 → 주체 행 → 동의 순서 |
| D-172 | 전문 | 장치 단위는 이미 일시 격리(180초)+`재활성화 필요` 표시가 있고 영구 격리는 채택하지 않음 — 장치 차단은 이 기능과 별개로 존재 |

## 원자 요구사항

| ID | 요구 | 코드 심볼 | 시험 |
| --- | --- | --- | --- |
| R01 | 중지 단위는 직원×MCP 서버 조합이며 활성 행은 조합당 1개 | `user_server_suspensions`, `user_server_suspensions_active`(`ops_tables.sql`), `user_suspend.suspend` | `LedgerChecks.test_second_suspend_*`, `WiringChecks.test_table_*`, 로컬 PG 확인 |
| R02 | 콘솔 계정은 그대로(계정 상태·토큰·세션을 건드리지 않음) | `user_suspend.py`가 `principals`를 읽기만 함, `set_account_status` 불변 | `LedgerChecks.test_no_code_edits_the_ledger`(쓰기 문 1종), 코드 검토 |
| R03 | 중지 다음 호출부터 거부 | `core.execute_call` 신원 조회(`server_suspended`)와 `P-SUSPEND-001` 분기, 호출 예약 전 | `GateChecks.test_suspended_pair_is_blocked_*`, `test_state_is_read_with_the_identity_row_for_this_pair` |
| R04 | 예약 뒤·전송 직전 경쟁에서도 거부 | `dispatch._INSERT`의 `NOT EXISTS user_server_suspensions`, `dispatch.record` 사유 `user-suspended`, `core._call_upstream` 매핑 | `DispatchChecks.*`, 로컬 PG의 `record()` 4건 |
| R05 | 판정 결과·정책 ID로 다른 차단과 구분 | `P-SUSPEND-001`(priority 2014, `policy_ledger.json`) — `P-INPUT-001`(계정)·`MCP-REGISTRY-002`(서버 자동 중지)·`ENDPOINT-MANAGED-001`(엔드포인트)와 별개 | `GateChecks`(정책 ID·이름·우선순위), `WiringChecks.test_ledger_entry_*` |
| R06 | 관찰 모드에서도 집행 | 분기가 `enforcement_mode` 조회 앞에서 반환 | `GateChecks.test_observation_mode_does_not_relax_it` |
| R07 | 재개 후 정상 | `user_suspend.resume`, 활성 행이 없으면 플래그 거짓 | `GateChecks.test_resume_lets_the_next_call_through`, `DispatchChecks.test_after_resume_*` |
| R08 | 다른 직원·다른 서버 영향 없음 | 조회 조건 `u.user_token=p.token AND u.server_id=%s` | `GateChecks.test_other_employee_and_other_server_pass_the_gate`, 로컬 PG |
| R09 | 관리자만 조작 | `GET·POST /api/suspensions`, `POST /api/suspensions/{id}/resume`가 `Depends(admin_caller)`, 콘솔 중계 접두 `suspensions` | `WiringChecks.test_routes_are_admin_only_*`, `open_endpoints.py` |
| R10 | 조작자·직원·서버·시각이 append-only 원장에 남음 | `review.record_event("user-server-suspend"/"user-server-resume", …, connection=connection)` 같은 트랜잭션, 시각은 `approval_events.created_at` | `LedgerChecks.test_suspend_records_*`, `test_state_and_record_commit_together_*`, 로컬 PG(트리거로 수정 불가 확인) |
| R11 | 중복 중지·중복 재개는 거부하고 기록을 늘리지 않음 | `ON CONFLICT … DO NOTHING`→`ValueError`(409), `UPDATE … WHERE resumed_at IS NULL` | `LedgerChecks.test_second_suspend_*`, `test_resume_records_the_actor_and_second_resume_*` |
| R12 | 상태를 읽지 못하면 실행하지 않음 | 신원 조회와 같은 문장이라 실패 시 예외로 호출 중단, 전송 직전은 `dispatch.record` 예외→`P-CONTROL-FAIL-CLOSED` | `GateChecks.test_unreadable_state_runs_nothing`, `DispatchChecks.test_unreadable_state_at_dispatch_*` |
| R13 | 진행 중 호출 처리 기록 | 중지 시점의 전송 전 예약 수(`unsent`)와 전송했으나 미응답 수(`sent`)를 사건 `scope`에 기록. 취소는 하지 않음 | `LedgerChecks.test_calls_in_flight_are_counted_in_the_record`, 로컬 PG |
| R14 | 중지와 이후 호출 사이의 경쟁을 직렬화 | `suspend`가 최종 dispatch와 같은 `pg_advisory_xact_lock(hashtext(user_token))`를 첫 문장으로 잡음 | `LedgerChecks.test_the_pair_is_locked_first_*`, `DispatchChecks.test_stop_waits_*`, 로컬 PG(잠금 대기 확인) |
| R15 | 관리자가 읽고 누르게: 사용자 행 「MCP 이용 중지」(서버 선택, 사유 제안값), 「이용 중지」 탭의 「재개」(메모 제안값) | `console.js`의 `suspend-open`·`suspend-resume`, `ROUTES.people` 탭 | `node --check`, `console_copy_check.py`. **화면 렌더링은 미확인** |
| R16 | 원장 수정 코드를 쓰지 않음 | `user_suspend.py`는 `approval_events`에 `review.record_event`의 INSERT만 사용 | `LedgerChecks.test_no_code_edits_the_ledger` |

## 무엇을 재사용했나

- D-122 `ops_suspensions`와 같은 모양의 상태 행(복귀 필드 채움) + `approval_events` 사건. 새 원장·새 해시 체인 없음.
- D-140의 최종 dispatch 트랜잭션(`dispatch._INSERT`)에 조건 한 줄과 사유 분류 한 갈래만 추가. 새 잠금 순서 없음(같은 advisory 키를 `suspend`가 먼저 잡을 뿐).
- 새 의존성 없음. 새 정책 ID는 `P-SUSPEND-001` 하나(R05 이유). Rego는 바꾸지 않음(게이트웨이 로컬 판정, `P-CONSENT-001`·`P-HIGH-IMPACT-001`과 같은 방식).

## 한계

- 이미 전송된 호출(`sent`)은 취소하지 않는다. 기록만 남긴다(D-122와 같은 한계).
- `tools/list`는 그대로 보이고 호출만 거부한다. 업스트림 세션 풀은 비우지 않는다(다음 호출이 판정에서 막힘).
- 재개에 독립 승인은 요구하지 않는다(관리자 1명 운영). 사유·메모는 필수 4자 이상이며 콘솔은 제안값을 채운다.
- 원문의 「직원·장치」 중 장치 단위는 구현하지 않았다. 장치 차단은 기존 엔드포인트 격리·`재활성화 필요`(D-172)가 맡는다.
- 한 직원의 모든 서버를 한 번에 멈추는 조작은 없다(서버마다 눌러야 함). 보고서 「방향 제안」 참조.
- 정책 목록 데이터(`policy_ledger.json`)를 바꿨으므로 기기 배포 때 OPA 재시작이 필요하다. 그 전에는 `P-SUSPEND-001` 판정의 정책 이름·버전이 비어 나온다.
- 로컬 확인은 `local-pg-probe.py`로 실제 PostgreSQL 16.2(pgserver, pgcrypto 없음)에서 실제 SQL을 돌린 것이며 제품 PostgreSQL(기기)·PJ1·실제 MCP 실행 증거가 아니다. 원본 출력은 [`local-pg-probe.out.txt`](local-pg-probe.out.txt).
