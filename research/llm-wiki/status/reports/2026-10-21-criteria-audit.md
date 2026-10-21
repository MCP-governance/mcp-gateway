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
