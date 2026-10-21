# 10-21 병합 기능의 완료 조건 대비 증거 감사

- 성격: 읽기 전용 감사. 제품 코드, 기존 보고서, 백로그, DECISIONS를 고치지 않았다.
- 기준: `origin/main` 517d3b7, 브랜치 `10/21-criteria-audit`.
- 완료 조건 출처: 감사 요청의 표를 쓰고 백로그 행과 대조했다. DEV-77·78·79·80은 백로그 행 문구와 같다. D-188은 백로그에 행이 없어 DECISIONS.md 본문과 요청 문구를 썼다.
- 판정 기준
  - 충족(대역): 대응 시험이 이번에 통과했고, 가짜 DB나 가짜 응답으로 로직을 확인한다. 실제 DB·컨테이너·기기 증거는 없다.
  - 부분: 문구의 일부에만 시험이 있거나, 시험이 소스 문자열 검사뿐이거나, 실행하지 못한 시험에만 기댄다.
  - 시험 없음: 그 문구를 고정하는 시험이 없다.
- 표기: 「실행 못 함」은 돌리지 못한 시험이다. 통과로 세지 않았다.

## 1. 항목별 결과

### DEV-79 / D-181 직원별 MCP 중지·재개

| 완료 조건 문구 | 고정하는 시험 (파일:시험) | 이번 실행 결과 | 대역/실제 | 판정 |
| --- | --- | --- | --- | --- |
| 중지 다음 호출부터 거부 | `tests/user_server_suspend_check.py`: `GateChecks.test_suspended_pair_is_blocked_with_its_own_policy_before_anything_runs`, `GateChecks.test_observation_mode_does_not_relax_it`, `DispatchChecks.test_stop_committed_before_dispatch_refuses_the_send`, `DispatchChecks.test_stop_waits_for_a_dispatch_already_inside_and_refuses_the_next` | 통과 (exit 0, 24건 중) | 대역. 가짜 DB(`Store`, `recheck.Database`)와 가짜 MCP 클라이언트. 중지 SQL은 문자열 대조만 하고 실행하지 않는다 | 충족(대역) |
| 재개 후 정상 | `GateChecks.test_resume_lets_the_next_call_through`, `DispatchChecks.test_after_resume_the_send_goes_out` | 통과 | 대역 | 충족(대역) |

- 부가: `tests/user_suspend_all_check.py`(일괄 중지·재개, 13건)도 통과했다. 완료 조건 밖의 보강이다.

### DEV-80 / D-182 엔드포인트 오프라인 관측 버퍼

| 완료 조건 문구 | 고정하는 시험 (파일:시험) | 이번 실행 결과 | 대역/실제 | 판정 |
| --- | --- | --- | --- | --- |
| 끊김 동안 기록이 쌓임 | `tests/endpoint_offline_buffer_check.py`: `test_offline_enqueue_reconnect_has_no_loss_or_duplicate` (`ConnectionError` 주입 후 적재 7건 유지), `test_process_restart_reloads_pending_rows` | 통과 (exit 0, 10건 중) | 대역. 파일은 임시 디렉터리의 실제 파일, 전송은 콜백. 게이트웨이 없음 | 충족(대역) |
| 재연결 후 누락 없이 | 위와 같은 시험. 송신 개수 `count == 7`, 재투입 뒤 pending 0 | 통과 | 대역. 송신 측까지만 확인 | 충족(대역, 송신 측) |
| 재연결 후 중복 없이 (송신 측) | 위와 같은 시험. 같은 행을 다시 넣어도 uid 기준으로 7건 유지 | 통과 | 대역 | 충족(대역) |
| 중복 없이 (게이트웨이 측) | `tests/endpoint_evidence_pg_check.py`: `check_dedupe` (같은 raw 해시는 창 안에서 중복, 같은 event_id는 무시) | 실행 못 함 (PostgreSQL 없음) | 실제 PG 대상으로 작성됨 | 시험 있음, 증거 없음 |
| 재연결 후 게이트웨이 도착 (ACK 커서 포함) | 없음 | - | - | 시험 없음 |
| 송신 뒤 ACK 전에 끊기면 재전송 중복 | 없음. 게이트웨이 중복 제거에만 기댄다 | - | - | 시험 없음 |
| 폐기 건수 보고 (용량·7일 만료) | 로컬 카운트: `test_capacity_stops_collection_and_records_drop_count`, `test_retention_expiry_is_counted_and_not_silent` (통과). 게이트웨이 `endpoint_buffer_events` 기록과 `agent.report_status` 전달 경로는 시험 없음 | 로컬 통과 | 대역 | 부분 |

- 주의: `test_offline_enqueue_reconnect_has_no_loss_or_duplicate`의 `received`는 해시 키 dict에 `setdefault`로 담는다. 그래서 수신 측 중복을 가린다. 중복 판정은 송신 개수 `count`에 의존한다.
- 주의: `tests/endpoint_evidence_check.py`(24건 통과)는 게이트웨이 `ingest_os_events`를 `Recorder` 대역으로만 호출한다. 중복 판정은 하지 않는다.

### DEV-78 / D-180 실행기 이전 승인 판본 되돌리기

| 완료 조건 문구 | 고정하는 시험 (파일:시험) | 이번 실행 결과 | 대역/실제 | 판정 |
| --- | --- | --- | --- | --- |
| 되돌린 뒤 계약 해시가 직전 승인값과 같음 (복원 값) | `tests/runtime_rollback_check.py`: `test_restore_uses_the_exact_prior_d149_hashes_including_output_hash`, `test_modified_snapshot_or_changed_tool_set_is_refused` | 통과 (exit 0, 7건 중) | 대역. 인메모리 `ContractConnection`. 실제 `mcp_tools` 아님 | 부분 |
| 같음 (되돌림 분기 전체) | 없음. `runtime/worker.py` `reconcile`의 롤백 블록(목표 판본 조회, sha256 비교, `restore_contract`, 큐잉)을 실행하는 시험이 없다. `resource_residual_check.py`의 `Executor`는 종료 경로만 실행한다. `test_reconcile_stops_before_it_queues_the_prior_image_and_contract`는 소스 순서 문자열 검사다 | - | - | 시험 없음 |
| 이력이 남음 (활성 전환 시 계약 스냅샷) | `test_active_runtime_history_appends_a_contract_snapshot` | 통과 | 대역 | 충족(대역) |
| 이력이 남음 (되돌림 큐잉·거부 이벤트) | 없음. `runtime-rollback-queued`(scope의 `contract_sha256`)와 `runtime-rollback-refused` 기록을 확인하는 시험이 없다 | - | - | 시험 없음 |
| 이력의 변경 불가 | 문자열 검사 `approval_events_append_only` 존재(같은 시험 마지막 줄) | 통과 | 문자열 검사만 | 부분 |

### DEV-77 / D-179 출처 서명 검증

| 완료 조건 문구 | 고정하는 시험 (파일:시험) | 이번 실행 결과 | 대역/실제 | 판정 |
| --- | --- | --- | --- | --- |
| 서명 불일치 차단 (worker 경로) | `tests/provenance_verify_check.py`: `test_bad_signature_blocks_with_supply_policy_id`, `test_startup_expected_digest_is_the_recorded_digest` (digest 불일치는 `worker.Refused`), `test_verifier_failure_is_distinct_from_missing_and_blocks`, `test_missing_trust_key_never_learns_key_from_attestation` | 통과 (exit 0, 6건 중) | 대역. 시험 안에서 Ed25519 키를 만들어 서명한다. 외부 빌더의 실제 증명은 아님 | 충족(대역) |
| 서명 불일치 차단 (게이트웨이 도입 승인 경로) | 없음. `gateway/app/agent_service.py` 승인 경로(약 1626~1640행, `hold_intake(kind="provenance-mismatch")`)를 서명 기준으로 검증하는 시험이 없다. `intake_identity_pg_check.py`의 provenance-mismatch는 사본 해시 불일치 시험이다 | - | - | 시험 없음 |
| 미제공은 표시만 (worker 경로) | `test_absent_attestation_is_visible_but_allowed`, `test_startup_expected_digest_is_the_recorded_digest` (MISSING 반환, Refused 아님) | 통과 | 대역 | 충족(대역) |
| 미제공은 표시만 (게이트웨이 경로) | 없음 | - | - | 시험 없음 |

- 백로그도 이 항목을 「부분 구현」으로 적고 있다. OCI proof 자동 조회는 완료 조건 밖의 남은 일이다.

### D-188 root 단독 운영 모드

| 완료 조건 문구 | 고정하는 시험 (파일:시험) | 이번 실행 결과 | 대역/실제 | 판정 |
| --- | --- | --- | --- | --- |
| 독립 승인 규칙 유지 (신청자와 승인자가 다름) | `tests/root_solo_check.py`: `test_self_approval_guard_is_independent_of_solo_mode`. `review.require_independent`를 소스 문자열로만 본다 | 통과 (문자열 검사) | 행위 시험 없음 | 시험 없음 (행위) |
| 독립 승인 규칙 (승인자 수를 부풀리지 않음) | `test_solo_mode_does_not_change_actual_approver_count`. 소스 문자열만 본다 | 통과 (문자열 검사) | 행위 시험 없음 | 시험 없음 (행위) |
| 높음 등급의 2차 승인 요건 | `test_risk_tier_still_requires_second_approver_where_required`. `risk_tier.decide`를 직접 호출한다. 현재 기대값은 「높음 + 사유, 1명 → approve」 | 통과 | 대역(순수 함수) | 부분. 아래 3절 충돌 참조 |
| 모드·전환이 원장에 남음 (기동 관측) | `tests/solo_mode_ledger_check.py` 8건: 첫 기동 1행, 같은 값 재기동 무기록, 전환 1행, 불리언만 저장, 원장 쓰기 실패 전파, 기동 시 try로 감싸기 | 통과 (exit 0, 8건 전부) | 대역. 실제 `review.record_solo_mode_observation` 코드를 실행하고, 원장은 메모리 목록, psycopg는 가짜 모듈 | 충족(대역) |
| 모드·전환이 원장에 남음 (승인 건별 `solo_mode`·`solo_operator`) | `root_solo_check.py`: `test_mode_is_preserved_in_ledger_and_shown_in_console`. 소스 문자열만 본다 | 통과 (문자열 검사) | 행위 시험 없음 | 시험 없음 (행위) |
| 모드 판정 함수 | `root_solo_check.py`: `test_mode_is_exact_opt_in_and_only_marks_root_admin`. 본문이 `os.getenv`를 직접 검사하고 `solo_mode_enabled`·`solo_operator`는 호출하지 않는다 | 통과 | 사실상 동어반복 | 부분 (약함) |

- 백로그에는 D-188 행이 없다. 기동 사이의 설정 전환은 기록되지 않는 공백으로 DECISIONS.md에 한계로 적혀 있다.

## 2. 「시험 없음」 완료 조건 문구

문구 전체가 「시험 없음」으로 판정된 항목은 없다. 모든 문구에 최소 한 개의 시험이 있다. 다만 문구의 아래 절은 시험이 없다.

1. DEV-80 「끊김 동안 기록이 재연결 후 누락·중복 없이 도착」 중 「재연결 후 도착」(게이트웨이 도착과 ACK 커서), 그리고 「ACK 전 중단 시 재전송 중복」.
2. DEV-78 「되돌린 뒤 계약 해시가 직전 승인값과 같고 이력이 남음」 중 「직전 승인값과 같음」의 되돌림 분기 전체(reconcile 롤백 블록), 그리고 「이력이 남음」 중 되돌림 큐잉·거부 이벤트.
3. DEV-77 「서명 불일치 차단, 미제공은 표시만」 중 게이트웨이 도입 승인 경로의 서명 차단과 미제공 표시.
4. D-188 「root 단독 모드에서 독립 승인 규칙 유지, 모드·전환이 원장에 남음」 중 「독립 승인 규칙 유지」(행위 시험 없음, 문자열 검사만), 그리고 「승인 건별 모드 표식」(문자열 검사만).

## 3. 기준 자체의 충돌 (판단 필요, 수정하지 않음)

- D-189 판단(`research/llm-wiki/analysis/review-1020/d189-approval-method.md`, `current.md`)은 「높음: 다른 관리자 2명 필수, D-143의 1명 + 서면 사유 대안 폐지」다.
- 코드는 아직 그렇지 않다. `gateway/app/risk_tier.py` `APPROVAL["high"]`는 `reason: "alternative"`이다.
- `root_solo_check.py`의 시험은 「높음 + 사유, 1명 → approve」를 고정하고 있어 통과한다. 이 기대값은 D-189 판단과 반대다.
- 시험이 통과하는 것을 「충족」으로 세지 않았다. 어느 쪽이 맞는지는 판단이 필요하다.

## 4. 증거 없는 부분

1. PostgreSQL 실행 증거 없음. `user_server_suspensions`의 부분 유일 인덱스, 직원별 advisory lock 직렬화, 최종 dispatch의 `NOT EXISTS` 조건을 실제 DB에서 확인하지 않았다.
2. 중지 후 호출 거부의 end-to-end 증거 없음. 실제 게이트웨이와 실제 MCP 서버를 쓰지 않았다.
3. DEV-80 게이트웨이 중복 판정(`check_dedupe`)을 실행하지 못했다.
4. DEV-80 재연결 루프 증거 없음. `endpoint-agent/os-observer.py`, `os-observer-windows.py`의 끊김 → 재연결 → ACK 경로를 시험하지 않았다.
5. DEV-80 폐기 건수의 게이트웨이 기록(`endpoint_buffer_events`)과 전달 경로 시험 없음.
6. DEV-78 실제 Docker 이미지 롤백 증거 없음. reconcile 롤백 분기와 큐잉 이벤트의 시험 없음.
7. DEV-77 게이트웨이 도입 승인 경로의 서명 검사 시험 없음. 외부 빌더가 만든 실제 SLSA 증명으로 검증하지 않았다.
8. D-188 행위 시험 없음(require_independent, 승인 건별 표식). 콘솔 표시를 실제로 본 증거도 없다.
9. D-189 기준과 코드 불일치(3절). 판단이 나야 시험 기대값을 고칠 수 있다.
10. 기기·PJ1·pj3 실 하네스 증거 없음. 이번 감사에서 실기기 시험은 하나도 돌리지 않았다.

## 5. 실행한 명령과 종료 코드

공통: 작업 디렉터리 `C:/Users/bobysg/bob/프로젝트/mcp-gw-claude-t2`. 파이썬은 `C:/Users/bobysg/bob/프로젝트/.venv-mcpgw/Scripts/python.exe` (Python 3.12.10). 시험 실행 시 `PYTHONIOENCODING=utf-8`, `PYTHONPATH=runtime;gateway/app;supply_chain`(full_stack_lab 기준)을 주었다.

| 명령 | 종료 코드 | 비고 |
| --- | --- | --- |
| `git fetch origin main` | 성공 (출력 확인, 코드 미기록) | |
| `git checkout -B 10/21-criteria-audit origin/main` | 성공 (출력 확인, 코드 미기록) | |
| 파이썬 `import cryptography` / `import psycopg, fastapi` / `import tomllib` | 0 / 0 / 0 | 의존성 확인 |
| `python tests/user_suspend_all_check.py` | 0 | 13건 |
| `python tests/user_server_suspend_check.py` | 0 | 24건 |
| `python tests/endpoint_offline_buffer_check.py` | 0 | 10건 |
| `python tests/runtime_rollback_check.py` | 0 | 7건 |
| `python tests/provenance_verify_check.py` | 0 | 6건 |
| `python tests/root_solo_check.py` | 0 | 6건 |
| `python tests/solo_mode_ledger_check.py` | 0 | 8건 |
| `python tests/endpoint_evidence_check.py` | 0 | 24건 (게이트웨이 ingest, 대역) |
| `python tests/windows_os_observer_check.py` | 0 | 7건 |
| `python tests/resource_residual_check.py` | 0 | 13건 (reconcile 종료 경로) |

## 6. 돌리지 못한 시험과 이유

실행 못 한 시험은 3개다.

| 시험 | 이유 | 관련 항목 |
| --- | --- | --- |
| `tests/endpoint_evidence_pg_check.py` | PostgreSQL이 없다. Docker, psql, 로컬 PG 설치가 없고 `DATABASE_URL`도 없다 | DEV-80 게이트웨이 중복 판정 |
| `tests/intake_identity_pg_check.py` | 같은 이유 | DEV-77 도입 승인 경로 |
| `research/llm-wiki/analysis/user-server-suspend/local-pg-probe.py` | `pgserver`가 설치돼 있지 않다. 공유 venv(`.venv-mcpgw`)에 설치하면 다른 작업에 영향을 주므로 설치하지 않았다 | DEV-79 중지 SQL의 실제 실행 |

기기·PJ1·pj3 실 하네스 시험은 이 감사 범위 밖이라 실행하지 않았다.

## 7. 백로그 상태와의 차이 (수정하지 않음)

- 백로그 DEV-79, DEV-80 행은 아직 「미착수」다. 두 기능은 main에 병합돼 있다.
- 백로그 DEV-78 행은 「미커밋」으로 남아 있다. 병합돼 있다.
- D-188은 백로그 행이 없다.

## 6-A. DEV-80 도착·중복 시험 추가

- 작업 브랜치: `10/21-dev80-arrival-tests`, 기준 `origin/main` ce1000d. 제품 코드는 고치지 않았다. push하지 않았다.
- 새 시험: `full_stack_lab/tests/endpoint_offline_arrival_check.py` 8건, 전부 통과. 기존 `endpoint_offline_buffer_check.py` 10건은 파일을 고치지 않았고 그대로 통과했다.
- 대상 공백: 위 2절의 DEV-80 「재연결 후 도착」(게이트웨이 도착과 ACK 커서), 「ACK 전 중단 시 재전송 중복」, 「폐기 건수 보고 경로」.

### 시험 구성과 대역 범위

장치 쪽은 실제 `os-observer.main()`을 그대로 실행한다. 실제 버퍼 파일과 커서 파일을 쓰고, 실제 `offline_buffer`를 쓴다. 게이트웨이 쪽은 실제 `main.endpoint_os_report`, `main.endpoint_observation_status`, `endpoint_plane.ingest_os_events`를 호출한다. 다음은 대역이다.

| 대역 | 대체 대상 | 이유 |
| --- | --- | --- |
| 인메모리 저장소 `Store` | PostgreSQL | DB 없이 두 중복 키를 확인. INSERT 문장에 `NOT EXISTS (... raw_sha256=%s)`와 `ON CONFLICT(endpoint_id,event_id)`가 남아 있는지 문장 대조. 실제 PostgreSQL 증거가 아니다 |
| `subprocess.run` | `journalctl` | 실제 journal 줄 형식의 JSON을 주고 `--after-cursor`를 흉내 |
| `AGENT.call` | HTTP·TLS·장치 키 | 라우트 함수를 직접 호출. 인증·HTTP 계층 없음 |
| `Path.stat`·`os.geteuid` | root 소유 검사 | 이 실행 환경은 Windows 사용자. 검사가 보는 소유자·권한 비트만 흉내 |

### 시험 목록과 판정 키

| 시험 | 확인하는 것 | 판정 키 |
| --- | --- | --- |
| `test_offline_events_all_arrive_after_reconnect_and_the_ack_cursor_moves_last` | 230건 적재 → 503 실패 → 재연결 뒤 전부 도착(배치 100), 커서는 마지막에만 | 도착 확인 후 커서 |
| `test_a_gateway_error_never_moves_the_ack_cursor_and_each_retry_delivers_once` | 500·503에서 커서 전진 없음, 재시도 뒤 한 번씩 도착 | 2xx 응답만 확인으로 인정 |
| `test_a_device_stop_after_the_gateway_stored_resends_and_the_gateway_keeps_one_copy` | 저장 후 ACK 전 장치 중단 → 재시작 → 중복 0 | `raw_sha256`(7일) |
| `test_a_lost_answer_after_the_gateway_stored_is_resent_and_stored_once` | 저장 후 응답 유실 → 재전송 → 중복 0 | `raw_sha256`(7일) |
| `test_the_gateway_keys_are_the_raw_hash_inside_seven_days_and_the_event_id` | 같은 raw·다른 event_id, 같은 event_id·다른 raw, 8일 뒤 같은 raw | `raw_sha256`(7일) 그리고 `(endpoint_id, event_id)` 각각 |
| `test_a_buffer_overflow_is_reported_once_with_its_count_and_reason` | 상한 초과 → 같은 실행에서 건수 5, 사유 `capacity`, 커서 전진 없음 | 보고 행 `endpoint_buffer_events` |
| `test_a_drop_count_survives_a_gateway_outage_and_is_reported_after_reconnect` | 보고 실패 시 건수 유지 → 재연결 뒤 한 번 보고 | 같은 `drop_uid`로 한 행 |
| `test_entries_expired_from_the_buffer_are_reported_as_retention` | 7일 만료 2건 → `retention` 보고, 나머지 3건 도착 | 보고 행 사유 `retention` |

raw 키와 event_id 키는 journal에서 거의 같은 사건을 가리킨다. journal 원문에 `__CURSOR`가 들어 있어 raw 해시가 cursor마다 달라지기 때문이다. raw 키는 event_id 규칙이 바뀌거나 cursor가 다시 쓰일 때만 추가로 막는다.

### 민감도 확인 (제품 코드 일시 변경 후 원복, 5건)

| 변경 | 실패한 시험 | 결과 |
| --- | --- | --- |
| M1 `os-observer.py`: 커서 조건에서 `delivery_ok and not pending` 제거 | 3건 | 원복, git diff 없음 |
| M2 `offline_buffer.py` `flush`: `acknowledge`를 `send` 앞으로 | 4건 | 원복 |
| M3 `endpoint_plane.py`: `RAW_DEDUPE_DAYS = 0` | 2건 | 원복 |
| M4 `os-observer.py`: 보고에서 `drop_report()` 제외 | 3건 | 원복 |
| M5 `offline_buffer.py`: `drop_fingerprint` 확인 제거 | 1건 | 원복 |

모든 변경에서 최소 1건이 실패했다. 원복 뒤 `git status`에는 새 시험 파일만 남았다.

### 제품 결함 후보 → 수정됨 (아래 「수정 결과」 참조)

**후보 1 → 수정됨. 폐기 건수가 같은 미적재 건을 실행마다 다시 센다 (재현됨, 연결 정상 상태에서도 발생)**
- 재현: 버퍼 상한 3, journal 줄 1~5 → 실행 1 보고 5. 이어서 줄 6~7 추가 → 실행 2 보고 7. 줄 1~7은 모두 미적재 상태이고 서로 다른 7건이다. 게이트웨이 합계는 12.
- 원인: `endpoint-agent/offline_buffer.py:183-184`의 `_record_drop(meta, max(1, len(rejected)), "capacity", ...)`. `rejected`는 이번 호출의 전체 추가분이다. 이전 실행에서 이미 보고된 줄도 들어간다. `drop_fingerprint` 확인(`:129`)은 같은 집합의 재시도만 막는다. 집합이 조금이라도 달라지면 전부 다시 센다.
- 의미: journal 줄은 커서가 전진하지 않아 계속 남아 있고, 버퍼가 비면 나중에 도착한다. "폐기"라는 보고 문구와 실제 상태가 어긋난다. 건수는 "시점별 미적재 건수의 합"이 되어 실제 고유 건수와 다르다.
- 권고: 보고 건수를 고유 uid 기준(예: 버퍼 밖 미적재 건을 uid 집합으로 관리)으로 정하거나, 실행마다 덮어쓰기 값으로 바꾼다.

**후보 2 → 수정됨. 같은 `drop_uid`의 재보고 건수 증가를 게이트웨이가 버린다 (재현됨, 응답 유실 조건)**
- 재현: 상한 3, 줄 1~5 → 실행 1에서 보고 5가 게이트웨이에 커밋되었으나 응답이 유실되어 장치는 실패로 기록. `drop_uid`와 건수 5가 장치에 남는다. 이어서 줄 6~8 추가 → 실행 2 보고 13(같은 uid). 게이트웨이 행은 5로 남는다.
- 원인: `full_stack_lab/gateway/app/endpoint_plane.py:274-275`의 `ON CONFLICT(endpoint_id,event_uid) DO NOTHING`. 같은 uid의 나중 보고를 갱신하지 않는다. 장치 쪽은 `offline_buffer.py:133`에서 실패 시 uid를 유지하고 `os-observer.py:184-186`에서 보고 성공 뒤에만 비운다.
- 권고: 후보 1을 고치면 같은 uid에 건수를 누적하는 일이 줄어든다. 그래도 `DO NOTHING`은 재보고가 같은 값이 아닐 때 조용히 버린다. 갱신 조건(`dropped_count` 증가 시 `GREATEST`)을 명시하는 것을 검토한다.

**관찰 (결함으로 적지 않음)**
- 장치가 `flush` 뒤·`enqueue` 전에 죽으면, 재시작 때 커서 없이 journal을 다시 읽어 같은 줄을 같은 실행에서 두 번 보낸다. 게이트웨이 raw 키가 전부 막았다(시험 `test_a_device_stop...`이 확인). 중복 방지가 게이트웨이에만 의존한다는 뜻이다.
- 4xx 응답(예: 300자 초과 필드)이 배치 하나에 고정되면 큐가 그 배치에서 멈춘다. 현재 수집기 값으로는 300자·12키 제한에 닿지 않아 도달성이 낮다. 규정 밖이라 시험을 쓰지 않았다.
- `os-observer-windows.py`는 채널별 커서(`*.os-cursor.json`)를 쓰는 다른 흐름이다. 이번 시험은 Linux `os-observer.py`만 덮는다. Windows 쪽 도착·커서 시험은 없다.

### 남은 공백

- 실제 PostgreSQL 중복 판정(`endpoint_evidence_pg_check.check_dedupe`)은 실행하지 않았다. PG 없음. 이번 시험의 중복 키는 SQL 문장 대조와 인메모리 대역이다.
- 실제 journalctl, 실제 HTTP·TLS, 실제 root 소유 검사는 대역이다. 실기기 시험은 하지 않았다.
- 후보 1·2는 시험 파일이 없다. 메인이 판단해 고친 뒤 시험을 추가한다. 시험 조건은 위 재현 절차를 그대로 쓴다.
- 브랜치를 `git checkout -B ... origin/main`으로 만들어 upstream이 `origin/main`에 걸려 있다. 올릴 때 `git push origin 10/21-dev80-arrival-tests`처럼 이름을 명시한다. 그냥 `git push`를 쓰면 `origin/main`으로 갈 수 있다.

### 수정 결과 (브랜치 `10/21-dev80-dropcount`, 기준 `origin/main` 4c22360)

- 결함 1 (장치, `endpoint-agent/offline_buffer.py` `enqueue`): 거부한 줄의 uid를 메타 `refused_uids`에 저장한다(재시작 뒤에도 유지). 다음 호출은 이미 기록된 uid를 건수에서 뺀다. 적재되면 그 uid를 목록에서 뺀다. 기존 `max(1, len(rejected))`는 새 건이 0이어도 1을 세던 것이어서 `len(fresh)`로 바꿨다.
- 결함 2 (게이트웨이, `full_stack_lab/gateway/app/endpoint_plane.py` `observation_status`): 삽입 SQL을 `ON CONFLICT(endpoint_id,event_uid) DO UPDATE SET dropped_count, reason, reported_at WHERE EXCLUDED.dropped_count > endpoint_buffer_events.dropped_count`로 바꿨다. 더 큰 건수만 반영하고 작거나 같은 값은 버린다. 행은 늘지 않는다.
- 감사 원장(`approval_events`·`decisions`) 미변경. 새 테이블·새 의존성·새 정책 ID 없음. DB 열 추가 없음(기존 `endpoint_buffer_events` 열만 씀).

| 시험 상황 | 수정 전 | 수정 후 |
| --- | --- | --- |
| 결함 1: 줄 1~5 보고(실행 1), 줄 6~7 추가 보고(실행 2), 고유 7건의 게이트웨이 합계 | 12 (실행 2 보고 7) | 7 (실행 1 보고 5, 실행 2 보고 2) |
| 결함 2: 줄 1~5 응답 유실 뒤 줄 6~13 추가, 같은 uid 재보고 | 게이트웨이 행 5 (장치 보고 18, 중복 집계) | 게이트웨이 행 13 (장치 보고 13) |
| 결함 2 보조: 같은 uid에 작은 값 4 재보고 | — | 행 13 유지(후퇴 없음) |

- 새 시험 2건 (`endpoint_offline_arrival_check.py`): `test_seven_unique_refused_events_are_counted_seven_times_across_two_runs`, `test_a_lost_drop_report_is_raised_to_the_larger_count_and_never_lowered`. 둘 다 통과.
- 기존 시험: `endpoint_offline_arrival_check.py` 8건과 `endpoint_offline_buffer_check.py` 10건 모두 통과. 후자 파일은 무변경.
- 정적 검사: `py_compile`, `pyflakes`(변경 3파일) 무출력 통과. `full_stack_lab && python tests/open_endpoints.py` PASS.
- 민감도 (수정본을 `git show HEAD:`로 되돌려 실행한 뒤 수정본을 복원, 바이트 비교 일치, `git diff`로 확인):
  - 장치 수정만 되돌림: 시험 1 실패 `12 != 7`, 시험 2 실패 `18 != 13`.
  - 게이트웨이 수정만 되돌림: 시험 2 실패 `5 != 13`. 시험 1은 게이트웨이와 무관하므로 통과.
  - 둘 다 되돌림: 두 시험 실패, 위와 같은 값.
- 시험 대역 변경: 인메모리 `Store`가 `endpoint_buffer_events` 삽입을 SQL 절에 따라 모델링한다(`DO NOTHING`이면 갱신 없음, 새 `DO UPDATE ... WHERE` 절이면 더 큰 값만 갱신). `Gateway`에 `lose_status_answer`(상태 보고 저장 뒤 응답 유실)를 추가했다. PostgreSQL 실행은 없다. SQL 절 대조와 인메모리 모델이다.
- 남은 공백과 판단 필요:
  1. **의미 확인 필요.** 건수는 "커서 창 안에서 한 번이라도 버퍼에 들어가지 못한 고유 건수"다. 거부된 줄이 나중에 버퍼가 비어 적재·전달되어도 이미 보고된 건수는 줄지 않는다. "폐기"라는 문구를 "미적재 시점 건수"로 낮출지, 적재 시 정정을 설계할지는 메인이 정한다. 정정은 게이트웨이의 단조 증가 규칙과 충돌한다.
  2. `refused_uids` 크기는 거부됐지만 아직 적재되지 않은 줄 수에 비례한다(uid 64자 hex). 저널에서 사라져 다시 읽히지 않는 줄은 목록에 남을 수 있다. 재집계는 일어나지 않는다.
  3. `os-observer-windows.py`도 같은 `offline_buffer.py`를 쓰므로 같은 수정을 받는다. Windows 시험은 없다.
  4. 실제 PostgreSQL 시험과 기기 시험은 하지 않았다.
- 커밋: `fix(v2): 폐기 건수 중복 집계와 재보고 버림 수정 (D-182)`.
