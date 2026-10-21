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

## 6-B. DEV-78 되돌림 분기·거부 이벤트 시험 추가

2026-10-21, 브랜치 `10/21-dev78-tests`(기준 `origin/main` ce1000d). 제품 코드는 고치지 않았다. 새 파일 `full_stack_lab/tests/runtime_rollback_reconcile_check.py` 하나만 추가했고 기존 시험 파일은 바꾸지 않았다.

### 결과

| 확인 | 결과 |
| --- | --- |
| 새 시험 `runtime_rollback_reconcile_check.py` | 25건 통과 (Python 3.12, psycopg·fastapi 설치 환경). 설치가 없으면 요청 쪽 8건은 건너뛰고 17건만 돈다 |
| 기존 `runtime_rollback_check.py` / `runtime_worker_check.py` / `provenance_verify_check.py` | 7건 / 7건 / 6건 그대로 통과 (세 파일 무변경) |
| `py_compile`, `pyflakes` (새 파일) | 통과 / 경고 없음 |
| `python tests/open_endpoints.py` | 통과 (무인증 1개, 인증 필요 89개) |
| 민감도 확인 | 제품 코드를 일시적으로 되돌린 변이 20개 모두 새 시험이 실패했고 원복 뒤 `git diff` 비어 있음. `import uuid`를 주입한 상태에서도 20개 모두 실패 |

### 완료 조건 대비

| 완료 조건 문구 | 새 시험 | 대역/실제 | 판정 |
| --- | --- | --- | --- |
| 거부(승인 이력 누락·이력 해시 불일치·계약 변조·도구 구성 변화)가 원장에 남음 | `RollbackRefusal` 12건: 거부 사건 1건(`outcome=refused`, 실행기 행위자, 세대·실행 ID, 사유)과 커밋, 새 세대 없음, 승인값 불변을 항목별로 확인 | 인메모리 원장. 실제 PostgreSQL 아님 | 충족(대역) |
| 철회·종료·공급망 중지 판본으로 되돌리지 않음 | 판본 표식 3종(`runtime-revoked`·`runtime-terminated`·`runtime-supply-chain-stop`)과 서버 상태 5종(DISABLED·BLOCKED_SUPPLY_CHAIN·TERMINATING·TERMINATED·RETIRED)·중지·이용 관계 종료를 각각 따로. 요청 쪽(`RollbackRequest`)에서도 같은 항목 | 대역 | 충족(대역). 단 표식을 쓰는 코드가 없다 (결함 후보 4) |
| 계약 변조 거부 | 옛 해시를 둔 채 값만 바꾼 스냅샷은 `restore_contract`가 거부(사유에 「해시」), 해시를 다시 계산한 스냅샷은 승인 이력 대조가 거부, 도구 집합 변화는 사유에 「도구 구성」 | 대역 | 충족(대역) |
| 되돌리기 요청이 들어가고 전이가 기록됨 | `RollbackRequest`: ACTIVE가 STOPPING으로 바뀌고 `rollback_target_generation`·계약 스냅샷이 같은 갱신에 실리며, `runtime-rollback` 사건(요청자·한 줄 사유·from/to 세대·계약 해시)이 같은 트랜잭션에 남는다. 원장 쓰기가 실패하면 중지 표시도 함께 되돌아간다. 관리자만 가능, 여러 줄 사유 거부, 요청 쪽 거부 18개 경우는 상태를 바꾸지 않음 | 대역(비동기 가짜 트랜잭션). 실제 DB 아님 | 충족(대역) |
| 되돌림 경로에서 증명을 새로 검증하지 않고 이전 세대 증거를 씀 | `ActiveRollbackGeneration`: 되돌린 세대가 ACTIVE일 때 `verify_source_provenance`가 받는 인자가 그 세대가 이어받은 증거와 같고 이전 세대 증거(해시·증명서·검증 기록)와 일치, `fetch_source`·`build`·`start` 미호출. 이어받은 증거가 검증을 통과하지 못하면 세대를 멈춤. `JobBranchShape`: `run_job` 되돌림 분기에 `fetch_source`·`verify_source_provenance`·`build` 호출이 없고 새 빌드 분기에는 있음 (소스 구조 검사) | 대역 + 소스 구조 검사 | 부분. `run_job` 실행 자체는 결함 후보 2 때문에 시험할 수 없다 |
| 되돌린 뒤 계약 해시가 직전 승인값과 바이트 단위로 같음 | **시험 불가** (결함 후보 1). 해당 시험 5건은 파일에 넣지 않고 아래 보류 시험으로 둔다 | - | 시험 없음 (결함 때문) |
| 되돌림 큐잉(이전 이미지로 새 세대 QUEUED, 빌드 없음) | **시험 불가** (결함 후보 1) | - | 시험 없음 (결함 때문) |

### 제품 결함 후보 (수정하지 않음, 메인 판단 필요)

1. **되돌림 큐잉이 항상 `NameError`로 죽는다.** `runtime/worker.py`가 `uuid`를 가져오지 않는데 705행 `uuid.uuid4()`를 쓴다 (모듈 상단 import 목록에 `uuid` 없음). 재현: `Ledger`에 STOPPING + `rollback_target_generation` 세대를 두고 `worker.reconcile`을 부르면 큐잉 INSERT 직전에 `NameError: name 'uuid' is not defined`. `main()`의 바깥 `except`는 `psycopg.Error`·`RuntimeError`·`OSError`만 잡으므로 작업자가 종료되고, 트랜잭션이 되돌려져 세대는 STOPPING에 남아 재시작마다 같은 곳에서 죽는다. 기존 `runtime_rollback_check.py`는 이 줄을 실행하지 않아 못 잡았다. 한 줄(`import uuid`)이면 해결되고, 그러면 보류 시험 5건이 통과한다 (`--fixed` 확인).
2. **`run_job` 되돌림 분기가 `KeyError`로 죽는다.** 574행에서 `source = {}`로 두고 581행에서 `source["source_archive_sha256"]`를 읽는다. 되돌림 세대(QUEUED→BUILDING)는 항상 이 줄에서 `KeyError: 'source_archive_sha256'`. `run_job`의 `except`는 `Refused`·`RuntimeError`·`OSError`·`SubprocessError`만 잡아 예외가 `main()`까지 올라가 작업자가 종료된다. 결함 1을 고쳐도 되돌림 세대는 ACTIVE에 도달하지 못한다. 재현: 원장 대역에 BUILDING 상태의 되돌림 세대를 두고 `inspect`·`fetch_source`·`build`를 대체한 채 `worker.run_job`을 부르면 `advance` 호출에 닿기 전에 예외가 난다 (커밋하지 않은 임시 스크립트로 확인). 이어받은 증거는 `built`에 이미 있으므로 `built["source_archive_sha256"]`를 쓰면 될 것으로 보이나 고치지 않았다.
3. **되돌림으로 만든 세대가 어떤 이유로든 멈추면 같은 대상으로 다시 되돌림이 큐잉된다.** 큐잉된 행이 `rollback_target_generation`을 그대로 갖고 있어 (`worker.py` 662행 이하 분기가 `done.get("rollback_target_generation")`만 본다) 이어받은 증거의 출처 검증 실패(`MCP-SUPPLY-001`)로 멈춘 경우에도 같은 목표로 새 세대가 QUEUED된다. 재현(원장 대역, `uuid` 주입): ACTIVE 3세대(되돌림, 증거에 `source_verification_error`) → 3세대 STOPPED(사유 `MCP-SUPPLY-001`) → 4세대 QUEUED(`rollback_target_generation=1`), `runtime-rollback-queued` 사건 기록. 목표 세대의 증거가 신뢰 키 교체 등으로 검증에 실패하는 상황이면 멈춤과 재큐잉이 반복될 수 있다. 의도한 자가 복구인지 판단이 필요하다.
4. **판본 철회 표식을 쓰는 코드가 없다.** `runtime-revoked`·`runtime-terminated`·`runtime-supply-chain-stop`은 `agent_service.py` 1286·1338행, `worker.py` 356·668행에서 읽기만 하고 저장소 어디에서도 기록하지 않는다 (`grep` 결과 읽는 곳 4곳뿐). 표식 검사는 시험에서 표식을 직접 넣어야만 작동한다. 현재는 서버 상태·생애주기 검사가 실제 차단을 맡는다.
5. **`runtime-rollback-queued` 사건의 `scope.runtime`이 새 세대가 아니라 멈춘 세대의 ID다.** `worker.py` 708행이 `{**runtime, "generation": queued["generation"]}`로 세대 번호만 바꾸고 ID는 그대로 둔다. `scope.generation`(새 세대)과 `scope.runtime`(이전 세대 행)이 서로 다른 행을 가리킨다. 영향은 사건 조회 시 혼동 정도로 작아 시험에서는 이 값을 확인하지 않았다.
6. **요청 쪽 거부(409)는 원장에 남지 않는다.** `agent_service.py` 1313~1362행의 거부는 `HTTPException`만 던지고 `record_event`를 부르지 않는다. 원장에 남는 거부는 실행기 쪽(`runtime-rollback-refused`)뿐이다. 완료 조건이 요청 쪽 거부의 기록까지 요구하는지 확인이 필요하다. 시험은 요청 쪽 거부에서 상태가 바뀌지 않는 것만 확인하고 원장 무기록은 고정하지 않았다.

### 보류 시험 (파일에 넣지 않음)

결함 1 때문에 통과하지 못하는 5건: 이전 이미지가 빌드 없이 새 세대로 QUEUED됨(이미지·레시피·커밋·`rollback_contract` 확인, `fetch_source`·`build`·`verify_source_provenance` 미호출), 복원 뒤 `mcp_tools` 계약 바이트와 sha256이 직전 승인값과 같고 `approved_contract` 재계산도 같음, 전이 순서(STOPPED → 계약 복원 → QUEUED → 커밋)와 `runtime-stopped`·`runtime-rollback-queued` 사건 내용, 활성 전환 때 저장된 스냅샷을 그대로 다시 기록, 다른 세대의 철회 표식은 막지 않음. 커밋하지 않은 임시 파일로 보관했고, 작업 보고에 경로를 적었다. `import uuid`를 주입하면 통과한다. 결함 1이 고쳐지면 `RollbackQueue` 클래스로 새 파일에 옮기면 된다.

### 한계

- 모든 확인은 인메모리 원장 대역이다. 실제 PostgreSQL의 잠금·트랜잭션 경합, 실제 컨테이너·이미지 재기동, 부분 유일 색인, 실제 MCP 호출 판정은 확인하지 않았다.
- `run_job` 되돌림 분기는 소스 구조 검사다. 실행 검증은 결함 2 때문에 불가능하다.
- 요청 쪽 시험은 `app.agent_service`를 가져올 수 있는 환경(fastapi 등)에서만 돈다.
- 기기·PJ1 시험은 하지 않았다.

### 수정 결과 (2026-10-21, 브랜치 `10/21-dev78-fix`, 코드 커밋 `b79f92f`)

메인의 [처리 판단](../../analysis/runtime-rollback/defects-1021.md)대로 결함 1~3·5·6을 고쳤고 4는 문서로 정정했다. 새 시험은 `full_stack_lab/tests/runtime_rollback_queue_check.py`다.

| 결함 | 수정 전 | 수정 후 |
| --- | --- | --- |
| 1 `uuid` 누락 | 되돌림 큐잉 INSERT 직전 `NameError`로 실행기 종료, 재시작해도 같은 곳에서 종료 | `import uuid` 추가. 보류했던 5건이 주입 없이 통과 |
| 2 소스 지문 `KeyError` | `source = {}` 뒤 `source["source_archive_sha256"]`에서 종료 | 두 분기 모두 `evidence`에서 읽는다. 지문이 없거나 비면 `Refused`로 세대를 FAILED 처리(조용히 비우지 않음). `runtime-built` 사건은 있는 키만 담고 빠진 키를 `scope.missing`에 남긴다 |
| 3 무한 되돌림 | 되돌림 세대가 어떤 이유로든 멈추면 같은 대상으로 QUEUED. 출처 검증 실패(`MCP-SUPPLY-001`)도 반복 | 거부·차단(승인 문제·출처 검증·재검사 결과·이미지 불일치)으로 멈추는 세대에 `evidence.stop_refused`를 남기고, 표식이 있으면 큐잉하지 않고 STOPPED로 둔 채 `runtime-rollback-refused` 사건(사유 포함)을 기록한다. 컨테이너가 사라진 중단과 관리자 요청으로 멈춘 세대는 기존대로 큐잉한다 |
| 4 사건 기반 가드 | 가드가 동작한다고 읽힘 | 코드 변경 없음. D-180과 [DEV-78 보고서](2026-10-21-runtime-rollback.md)에 「동작하지 않고 실제 차단은 서버 상태 검사」를 정정으로 적음 |
| 5 사건의 세대 ID | `runtime-rollback-queued`의 `scope.runtime`이 멈춘 세대 행 ID | 새 세대 행 ID |
| 6 요청 쪽 거부 | 409가 원장에 남지 않음 | 409마다 `runtime-rollback-request-refused`(outcome `refused`, 요청자, 사유, 대상 판본, 사유 메모)를 새 트랜잭션에 append. 실행기 쪽 `runtime-rollback-refused`와 종류가 다르고 원장을 고치는 코드는 없다. 콘솔 사건 이름표 추가 |

| 확인 | 결과 |
| --- | --- |
| 새 `runtime_rollback_queue_check.py` | 19건 통과(보류 5건 포함: 큐잉, 계약 바이트·sha256, 전이 순서·사건, 활성 전환 스냅샷, 다른 세대 표식). 요청 쪽 4건은 fastapi·psycopg가 없으면 건너뛴다 |
| 기존 4개 파일 | `runtime_rollback_check` 7건, `runtime_rollback_reconcile_check` 25건, `runtime_worker_check` 7건, `provenance_verify_check` 6건 그대로 통과(파일 무변경) |
| 민감도 | 수정 6건에 대한 변이 13개(수정 일부를 일시적으로 되돌림)에서 모두 새 시험이 실패했고 원복 뒤 시험 전부 재통과 |
| 정적 검사 | `py_compile`·`pyflakes`(worker, agent_service, 새 시험) 통과, `node --check` 통과, `open_endpoints.py` 통과 |

한계: 모든 확인은 인메모리 원장·함수 대역이다. `stop_refused` 표식은 이 수정 이후 멈춘 세대에만 붙으므로 배포 전에 이미 STOPPING인 되돌림 세대는 기존처럼 큐잉된다. 기기 재배포와 되돌리기 1회 실행은 메인이 한다.

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
  1. **의미 확인 필요.** 건수는 "커서 창 안에서 한 번이라도 버퍼에 들어가지 못한 고유 건수"다. 거부된 줄이 나중에 버퍼가 비어 적재·전달되어도 이미 보고된 건수는 줄지 않는다. "폐기"라는 문구를 "미적재 시점 건수"로 낮출지, 적재 시 정정을 설계할지는 메인이 정한다. 정정은 게이트웨이의 단조 증가 규칙과 충돌한다. → 메인 판단(10-21): 정정하지 않는다. 라벨은 「미적재·만료 건수」로 바꾸고 건수 계산은 그대로 둔다(브랜치 `10/21-dropcount-wording`).
  2. `refused_uids` 크기는 거부됐지만 아직 적재되지 않은 줄 수에 비례한다(uid 64자 hex). 저널에서 사라져 다시 읽히지 않는 줄은 목록에 남을 수 있다. 재집계는 일어나지 않는다.
  3. `os-observer-windows.py`도 같은 `offline_buffer.py`를 쓰므로 같은 수정을 받는다. Windows 시험은 없다.
  4. 실제 PostgreSQL 시험과 기기 시험은 하지 않았다.
- 커밋: `fix(v2): 폐기 건수 중복 집계와 재보고 버림 수정 (D-182)`.

## 8. 2회차 감사 (D-176·D-177·D-178·D-189)

- 성격: 읽기 전용 감사. 제품 코드, 시험, 기존 문서를 고치지 않았다. 새 시험을 만들지 않았다. 이 절만 덧붙였다.
- 기준: `origin/main` be09c97, 브랜치 `10/21-criteria-audit-2`. 1회차 이후 main에 들어온 변경: D-176 `e6684c0`, D-177 시험 보정 `ff629e5`, D-189 `882c390`·`e870a2b`, D-182 정정 `ee4470b`·`097f27e`.
- 완료 조건 출처: `research/llm-wiki/status/backlog.md` 85~87행(DEV-74·75·76). D-189는 `research/llm-wiki/analysis/review-1020/d189-approval-method.md`의 결론 1~3과 추가 판단 1~3.
- 판정 기준: 1회차와 같다. 「실행 못 함」은 돌리지 못한 시험이며 통과로 세지 않았다. 「경로 누락」은 시험이 실행하지 않는 분기다.

### 8.1 항목별 결과

#### DEV-74 / D-176 반복 위반 자동 일시 중지

| 완료 조건 문구 | 고정하는 시험 (파일:시험) | 이번 실행 결과 | 대역/실제 | 판정 |
| --- | --- | --- | --- | --- |
| 임계 도달 다음 호출부터 중지 | `user_auto_suspend_check.py`: `test_threshold_creates_one_d181_state_row_and_complete_automatic_record`(행 1건, 원장 1건). 「다음 호출 차단」은 `user_server_suspend_check.py`의 관리자 행 시험으로 대신함 | 두 파일 통과 (10건, 24건) | 대역(`FakeConnection`). 자동 행이 실제 Block 기록에서 만들어진 뒤 차단되는 연결은 실행 안 됨 | 부분 |
| 임계 판정이 실제 Block 기록에서 일어남 | `dest_pin_credential_redaction_check.py:289-304` (`core._record_decision` 추출) | **실패 (exit 1)**: `NameError: name 'AUTO_SUSPEND_POLICIES' is not defined` (`core.py:1927`). 16건 중 1건 ERROR | 실행 0회 | **실행 실패** |
| 해제 후 정상 | `user_auto_suspend_check.py:test_expiry_releases_state_and_records_automatic_resume` | 통과 | 대역. `_expire_locked`만 호출. `execute_call`의 만료 처리(`core.py:2076-2081`)는 미실행 | 부분 |
| 임계·기간 설정값 | `user_auto_suspend_check.py:test_threshold_window_and_duration_are_environment_settings` | 통과 | 문자열 검사(`os.getenv("AUTO_SUSPEND_THRESHOLD"` 포함 여부)뿐 | 부분 |
| (보강) 동시 임계에서 삽입 1회 | `user_auto_suspend_check.py:test_concurrent_threshold_has_one_insert_and_one_event` | 통과 | 대역(`asyncio.Lock`). 실제 직렬화는 `pg_advisory_xact_lock` 문자열 검사(`:182`) | 부분 |

- PostgreSQL 시험 없음. `auto_suspend_pg_check.py`는 D-122 서버 단위 시험(머리말 1~2행)이며 D-176의 직원×서버 조합을 다루지 않는다.
- 종합: **부분**. 임계 판정 기록 경로는 한 번도 실행되지 않았다.

#### DEV-75 / D-177 미사용 도구 자동 비활성

| 완료 조건 문구 | 고정하는 시험 (파일:시험) | 이번 실행 결과 | 대역/실제 | 판정 |
| --- | --- | --- | --- | --- |
| 기한 도달 도구가 목록에서 빠짐 | `tool_sunset_check.py:test_expired_tool_appends_automatic_sunset`(규칙과 `active=False` 사건). `:test_list_and_call_use_sunset_state_and_existing_policy`의 168행(`listable` 사전 입력) | 통과 | 대역 저장소. `mcp_facade.py:144-146` 목록 루프는 실행 안 됨. 165행은 문자열 | 부분 |
| 기한 도달 도구가 호출에서 빠짐 | 같은 시험의 169~170행(`call_verdict` 사전 입력), 167행(문자열) | 통과 | `core.py:2133-2136` 실제 경로는 실행 안 됨. `fresh_requester_check.py:125`와 `user_server_suspend_check.py:241`은 `tool_sunset`을 `check→{}`, `call_verdict→None`으로 대역해 판정이 한 번도 실제로 돌지 않음 | 부분 |
| 자동 연장에 사용 이력 반영 | `tool_sunset_check.py:test_recent_window_appends_extension`(연장 사건). 서버 승인 기한 연장 `core.py:893-948`의 `recently_used` 연결은 `intake_identity_pg_check.py:294-318`(PG)뿐 | 연장 사건 통과. PG는 실행 못 함 | 대역 | 부분 |
| 재심사 승인 후 복귀 | `tool_sunset_check.py:test_reapproval_is_an_append_only_human_event` | 통과 | 대역. 재심사 뒤 목록·호출 복귀는 실행 안 됨 | 부분 |

- 종합: **부분**. 목록과 호출 두 경로는 모두 사전 입력 대역 또는 문자열 검사로만 덮인다.
- 백로그 DEV-75 행은 「미착수」지만 판정 규칙과 시험은 main에 있다(8.6).

#### DEV-76 / D-178 SBOM 영향 조회

| 완료 조건 문구 | 고정하는 시험 (파일:시험) | 이번 실행 결과 | 대역/실제 | 판정 |
| --- | --- | --- | --- | --- |
| 합성 취약 판본의 영향 서버 목록이 SBOM과 일치 | `sbom_impact_check.py:test_query_separates_affected_unaffected_unknown_and_missing`(행 6건 주입), `:test_semver_range_boundaries_and_unknown_versions` | 통과 | 대역. `db.fetch_all` 주입. `sbom_impact.py:79-99`의 SQL은 실행 안 됨 | 부분 |
| 차단 조작이 원장에 남음 | `sbom_impact_check.py:test_existing_server_stop_writes_batch_on_append_only_event`(`ops_response.suspend`를 AST로 추출, 가짜 연결) | 통과 | 대역. 신규 중지 행에 대해서만 | 충족(대역). 건너뜀의 원장은 시험 없음 |
| 일괄 중지의 부분 실패 격리 | `sbom_impact_check.py:test_stop_deduplicates_server_and_reports_partial_failure_with_batch` | 통과 | 대역(`ops_response.suspend` 교체). 건너뜀 0건을 고정(121행) | 부분 (건너뜀 분기 미시험) |

- 종합: **부분**. 「자료 없음」 분기 일부와 건너뜀 분기가 시험되지 않았다(8.2).

#### D-189 도입 위험 등급 승인 방식

| 완료 조건 문구 | 고정하는 시험 (파일:시험) | 이번 실행 결과 | 대역/실제 | 판정 |
| --- | --- | --- | --- | --- |
| 결론 1·2: high는 2명, reason 대안 폐지, very_high는 2명과 사유 | `intake_d189_check.py:TableCheck`, `:test_a_reason_never_replaces_an_approver`; `intake_risk_tier_check.py:test_approval_method_per_tier` | 통과 | 순수 함수 대역 | 충족(대역) |
| 적용 1: `risk_tier_gate`(`/approve`) 2명·사유 | `intake_risk_tier_check.py:211`, `:228`, `:235`, `:242` (`approve_mcp_request`를 실제 호출, DB만 교체) | 통과 (25건 중 4건이 이 경로) | 대역 | 충족(대역) |
| 적용 2: `approve_and_register` 2명·사유 | `intake_d189_check.py:OneClickVeryHighCheck` 5건 | 통과 (skip 0) | 대역 | 충족(대역) |
| 적용 3: `core.register_server` 2명·사유 | 행위 시험 없음. 문자열 검사만 `intake_d189_check.py:56-60` | 통과 (문자열) | 실행 시험 없음 | **시험 없음 (행위)** |
| 결론 3: 치명적 발견 수용은 `accept_risk`로 별도 | 전용 시험을 찾지 못함. `accept_risk`는 `intake_one_click_ast_check.py:84` 대역 이름과 `intake_identity_test.py:112` patch뿐 | — | — | 시험 없음 (확인 미완) |
| 표시 방식 = 강제 방식 | `intake_d189_check.py:test_the_displayed_method_is_the_enforced_one` | 통과 | 대역 | 충족(대역) |
| 추가 판단 1: root_solo 기대값을 `cosign`으로 | `root_solo_check.py:test_risk_tier_still_requires_second_approver_where_required` 56~58행 | 통과 | 순수 함수 | 충족(대역). 1회차 3절 충돌 해소 |
| 추가 판단 2: 근거 없는 신청은 보류, 목록 칩도 보류 | `intake_blocked_proposal_check.py`(AST 추출 `with_risk`), `intake_risk_tier_check.py:test_request_without_stated_input_is_held`, `intake_d189_ui_check.mjs` 4건 | 통과 (node 4/4) | 대역 | 충족(대역) |
| 추가 판단 3: 공급자 선택 입력, 받지 못한 항목은 「확인 안 됨」 | `supplier_assurance_check.py:test_items_not_received_are_named_unconfirmed_and_never_recorded_as_provided`(88행), `intake_d189_ui_check.mjs:63` | 통과 | 대역 | 충족(대역) |

- 종합: **부분**. 두 경로(`risk_tier_gate`, `approve_and_register`)는 행위 시험이 있다. `core.register_server`의 2명·사유 강제와 결론 3은 시험이 없다.

### 8.2 경로 누락 (시험이 실행하지 않는 분기, 가장 위험해 보이는 순)

| 순위 | 기능 | 분기 (파일:행) | 조건 | 실행하는 시험 | 판정 |
| --- | --- | --- | --- | --- | --- |
| 1 | D-176 | `core.py:1926-1931`, `:1976-1978` | Block이고 목록 정책이며 신원이 unknown이 아닐 때 임계 판정 | 없음. `dest_pin_credential_redaction_check.py:304`에서 NameError로 중단 | 실행 0회 |
| 2 | D-176 | `core.py:1976-1978` → `automatic_suspend.py:43-51` → `core.py:2407`(보호 없음) → `mcp_facade.py:251-252` | 임계 판정의 집계 SELECT 실패, 또는 설정값 `threshold<1`(`automatic_suspend.py:43-44`) | `user_auto_suspend_check.py:147-152`는 예외 전파만 확인. 판정 행 롤백, `P-CONTROL-FAIL-CLOSED` 기록, 응답 형태는 시험 없음(`:152`는 문자열) | 시험 없음. 코드 독해: Block 판정 행이 같은 트랜잭션에서 롤백되고 호출자는 일반 오류를 받음(미재현) |
| 3 | D-189 | `core.py:682`, `:685-686`, `:687-688` | 승인자에 신청자 포함 / 승인자 2명 미만 / very_high인데 사유 기록 없음 | 행위 시험 없음. `intake_d189_check.py:56-60` 문자열만 | 시험 없음 (최종 관문) |
| 4 | D-189 | `core.py:675` | 승인 때 입력 해시와 현재 입력 해시가 다름 | 없음. 「승인 때 확인한 영향평가 입력」 시험 0건 | 시험 없음 |
| 5 | D-177 | `tool_sunset.py:99-102` | 재심사 전에 `held` 사건이 있으면 다음 `check()`도 비활성이어야 함 | 없음. `test_reapproval...`(150~158행)은 승인 뒤에만 다시 확인 | 시험 없음 |
| 6 | D-177 | `tool_sunset.py:24-27` → `mcp_facade.py:145`, `:226-231` | `available=False`이면 `listable`이 RuntimeError, tools/list 전체 실패 | 없음. 168행은 `available=True`만 | 시험 없음 (가용성) |
| 7 | D-177 | `tool_sunset.py:72-81` | 원장 봉인 구간과 관측 창 겹침, 원장 건수 불일치 | 없음. `Connection`은 entries=0, retained=0 고정(`:38-39`), `current_seal`은 None 고정(`:80`) | 시험 없음 |
| 8 | D-177 | `core.py:913-915` → `tool_sunset.py:170-191` | 보존 구간 부족 또는 봉인 겹침이면 recently_used가 None이어서 자동 연장 금지 | 없음 (PG 시험뿐, 실행 못 함) | 시험 없음 |
| 9 | D-178 | `sbom_impact.py:143` + `ops_response.py:74-75` | 이미 중지된 서버를 다시 중지하면 skipped인데 `status_reason`과 상태가 덮어써짐 | 시험은 `skipped` 0건으로 고정(`sbom_impact_check.py:121`) | 시험 없음. 「건너뛰고」 문구와 어긋날 수 있음(코드 독해) |
| 10 | D-178 | `sbom_impact.py:103-105` | 세대는 있는데 커밋 불일치, 검사 상태가 DONE 아님, 세대 없음 | 없음. `row()` 헬퍼는 항상 `source_match=True`, `scan_status=DONE`, 세대 지정(`sbom_impact_check.py:42-47`) | 시험 없음 |
| 11 | D-176 | `automatic_suspend.py:61-62` | 이미 활성 중지(관리자 중지 또는 이전 자동 중지)가 있을 때 임계 도달 → 원장 없이 False | 없음 | 시험 없음 |
| 12 | D-176 | `core.py:2107-2111` | 만료 처리(`expire`) 실패 → P-CONTROL-FAIL-CLOSED | 없음. `user_server_suspend_check.py:391-393`은 디스패치 시점 상태 읽기 실패 | 시험 없음 |
| 13 | D-176 | `dispatch.py:153` | 자동 행의 `expires_at`이 지났는데 만료 처리 전 | 문자열만(`user_auto_suspend_check.py:155-156`) | 부분 |
| 14 | D-189 | `agent_service.py:2069-2070` | 위험 등급 산정 실패(tier 없음) → 409 | 없음. 「산정하지 못했습니다」 시험 0건 | 시험 없음 |
| 15 | D-177 | `tool_sunset.py:106-112`, `:133-134` | 같은 관측 창 「자료 없음」 사건 중복 방지, 같은 기한 연장 중복 방지 | 없음 | 시험 없음 (낮음) |
| 16 | D-176 | `automatic_suspend.py:26-34` | 전역 `expire()`(사용자·서버 없음) | 시험 없음. 호출자도 없음(`user_suspend.py:19`은 쌍 단위만 호출) | 죽은 분기 |
| 17 | D-178 | `sbom_impact.py:46-50` | 범위 토큰 4개 초과, 빈 토큰 | `latest`, `1.2.3,`만 시험 | 낮음 |

- 덮인 분기(참고): `risk_tier_gate` 보류 1555행(`intake_risk_tier_check.py:196`), 같은 관리자 재클릭 중복 기록 방지(`agent_service.py:1576`, `intake_risk_tier_check.py:222`), D-178 판단 불가·자료 없음 구분(`sbom_impact_check.py:97-99`).

### 8.3 AST(함수 추출) 시험 이름공간 점검

- 명령: `git grep -l -E "exec\(compile\(|production\("` 결과 27개 파일을 각각 `python tests/<파일>`로 실행하고 `NameError` 개수를 셌다.
- exit 0: 26개. 그중 skip이 있는 파일은 `high_impact_check.py`(7, gateway image 필요), `incident_pack_check.py`(1), `managed_helper_unavailable_check.py`(1), `user_command_settings_check.py`(1), `user_command_settings_review_check.py`(1).
- exit 1: `dest_pin_credential_redaction_check.py`. `NameError: name 'AUTO_SUSPEND_POLICIES' is not defined`. 도입 커밋은 `e6684c0`(D-176)다. 이 시험의 `_record_decision` 추출 이름공간(`:289-298`)에 `AUTO_SUSPEND_POLICIES`와 `user_suspend`가 없다. 시험 16건 중 15건은 통과했다.
- D-177 `tool_sunset` NameError는 남아 있지 않다. `fresh_requester_check.py`와 `user_server_suspend_check.py`는 통과했다. 다만 두 시험 모두 `tool_sunset`을 대역해 실제 판정을 타지 않는다(8.2 5번·6번 근거).
- `outcome_axes_check.py:137`도 `_record_decision`을 추출하지만 입력이 기본 `Allow`(`:33-36`)라 같은 결함이 가려져 있다.

### 8.4 실행 못 한 시험과 증거 없는 부분

- PostgreSQL 필요 시험은 실행 못 함. 이유: `DATABASE_URL` 미설정, docker와 psql 없음. 대상: `intake_identity_pg_check.py`(승인·등록·`renew_approvals` DB 경로), `auto_suspend_pg_check.py`(D-122이며 D-176 아님). D-176 전용 PG 시험은 존재하지 않는다.
- gateway image 필요: `high_impact_check.py` 7건 skip.
- 기기·PJ1: 실행 안 함. 감사 범위 밖.
- 대역 한계: 집계 SQL(`automatic_suspend.py:46-51`), 중지 SQL(`automatic_suspend.py:55-61`), `impact()` SQL(`sbom_impact.py:79-99`)은 전부 실행되지 않았다.
- 기존 실패: `intake_identity_test.py` 19건 중 7건 ERROR. `KeyError: 'high_count'`. 픽스처 `reports()`에 `high_count`가 없고 `review.py:174`가 `report["high_count"]`를 직접 읽는다. 제품 결함인지 픽스처 누락인지는 메인이 판단한다. 이 시험은 도입 게이트(`review.intake_gate`) 시험이다.

### 8.5 실행한 명령과 종료 코드

공통: 작업 디렉터리 `full_stack_lab`. `PY=C:/Users/bobysg/bob/프로젝트/.venv-mcpgw/Scripts/python.exe`(Python 3.12.10). `PYTHONIOENCODING=utf-8`, `PYTHONPATH=runtime;gateway/app;supply_chain`. 의존성 확인 `"$PY" -c "import fastapi, psycopg, cryptography, pydantic"` 종료 0.

| 명령 | 종료 코드 | 건수 |
| --- | --- | --- |
| `git fetch origin main` | 0 (f5fa6fd..be09c97) | — |
| `git checkout -B 10/21-criteria-audit-2 origin/main` | 0 | — |
| `"$PY" tests/user_auto_suspend_check.py` | 0 | 10 |
| `"$PY" tests/user_server_suspend_check.py` | 0 | 24 |
| `"$PY" tests/user_suspend_all_check.py` | 0 | 13 |
| `"$PY" tests/tool_sunset_check.py` | 0 | 7 |
| `"$PY" tests/fresh_requester_check.py` | 0 | 10 |
| `"$PY" tests/sbom_impact_check.py` | 0 | 5 |
| `"$PY" tests/intake_d189_check.py` | 0 | 9 (OneClick 5 포함, skip 0) |
| `"$PY" tests/root_solo_check.py` | 0 | 6 |
| `"$PY" tests/intake_risk_tier_check.py` | 0 | 25 |
| `"$PY" tests/intake_one_click_check.py` | 0 | 19 |
| `"$PY" tests/intake_one_click_ast_check.py` | 0 | 11 |
| `"$PY" tests/supplier_assurance_check.py` | 0 | 8 |
| `"$PY" tests/solo_mode_ledger_check.py` | 0 | 8 |
| `"$PY" tests/high_impact_check.py` | 0 | 24 (7 skip) |
| `"$PY" tests/intake_identity_test.py` | 1 | 19 (7 ERROR, KeyError high_count) |
| `node --test tests/intake_d189_ui_check.mjs` | 0 | 4 |
| 8.3의 추출 시험 27개 (`"$PY" tests/<파일>`, timeout 180초) | 26개 0, `dest_pin_credential_redaction_check.py` 1 | 해당 파일 16건 중 1 ERROR |
| `"$PY" tests/intake_blocked_proposal_check.py` (추출 배치 안) | 0 | — |

### 8.6 판단 필요 (수정하지 않음)

- 백로그와 main 불일치: DEV-74 행은 「미커밋·미통합」인데 `e6684c0`이 main에 있다. DEV-75 행은 「미착수(D-177 예약)」인데 판정 규칙과 시험이 main에 있다. D-178 행은 「로컬 구현」인데 `sbom_impact.py`와 시험이 main에 있다.
- 1회차 3절 충돌은 해소됐다. `root_solo_check.py:56-58`이 `cosign`으로 바뀌어 통과한다.
- `ff629e5`는 D-177 회귀 2건(`fresh_requester_check.py`, `user_server_suspend_check.py`)을 고쳤다. 같은 종류(이름공간 누락)의 D-176 회귀(`dest_pin_credential_redaction_check.py`)는 남아 있다.
- D-189 결론 3(치명적 발견 수용 분리)과 `core.register_server`의 2명·사유 강제는 실행 시험이 없다. 이 둘을 시험으로 고정하려면 메인이 시험 추가 여부를 정해야 한다.
- 8.2 1번과 2번은 시험 실행 실패와 집계 실패 롤백이 겹친 것이다. 롤백 결과는 코드 독해이며 재현하지 않았다.

## 6-C. D-188 행위 시험·DEV-77 게이트웨이 경로 시험

2026-10-21, 브랜치 `10/21-approval-gap-tests`(기준 `origin/main` be09c97). 제품 코드는 고치지 않았다. 새 파일 둘만 추가했고 기존 시험 파일은 바꾸지 않았다.

- `full_stack_lab/tests/root_solo_behavior_check.py`: 승인 함수를 실제로 호출하는 단독 모드 행위 시험.
- `full_stack_lab/tests/provenance_gateway_check.py`: 게이트웨이 도입 승인 경로의 출처 증명 검사 시험.

### 결과

| 확인 | 결과 |
| --- | --- |
| 새 `root_solo_behavior_check.py` | 47건 통과, 생략 0건 (Python 3.12, fastapi·psycopg 설치 환경). 경로 1 개별 승인 13건, 경로 2 한 화면 승인 7건, 경로 3 등록 7건, 그리고 경로 1·2를 단독 모드 꺼짐으로 다시 돌린 13건·7건(승인 규칙은 모드와 무관하다는 확인, 표식 값은 시험 안에서 모드별로 따로 지정) |
| 새 `provenance_gateway_check.py` | 11건 통과, 생략 0건 |
| 기존 `root_solo_check.py` / `solo_mode_ledger_check.py` / `intake_risk_tier_check.py` / `intake_d189_check.py` / `provenance_verify_check.py` | 6건 / 8건 / 25건 / 9건 / 6건 그대로 통과 (다섯 파일 무변경). 같은 대역을 빌려 쓰는 `intake_one_click_check.py` 19건도 통과 |
| `py_compile`, `pyflakes` (새 파일 둘) | 통과 / 경고 없음 |
| `python tests/open_endpoints.py` | 통과 (무인증 1개, 인증 필요 90개) |
| 민감도 확인 | 제품 동작을 항목별로 일시적으로 되돌린 변이 35개(D-188 쪽 21개, DEV-77 쪽 14개). 처음엔 33개를 잡고 2개(원격 서비스 승인 기록의 `solo_mode`, 증명이 붙인 키 이름이 설정에 없을 때)가 살아남아 시험 2건을 더한 뒤 35개 모두 새 시험이 실패했다. 매번 원복했고 최종 `git diff`는 비어 있다 |

### 세 승인 경로를 각각 행위로 확인했는가

| 경로 | 호출한 함수 | 확인한 행위 |
| --- | --- | --- |
| 1 개별 승인 | `agent_service.approve_mcp_request`(안에서 `risk_tier_gate`), 그리고 `risk_tier_gate` 직접 호출 | 단독 모드 켜짐: 낮음·보통은 root가 혼자 완료, 높음·매우 높음은 대기(`intake-cosign` 1건, 게시·승인 없음). 같은 root가 두 번, 다른 토큰으로 눌러도 승인자 1명. 신청자 본인(같은 토큰, 같은 사람의 다른 토큰, 신청자가 root인 경우 포함)은 403과 거부 사건. 두 번째 관리자가 오면 높음 완료, 매우 높음은 사유 없으면 거부·있으면 완료. 승인 사건 `scope`의 `solo_mode`·`solo_operator`가 모드(`1`·`0`·`true`·빈 값·미설정)와 승인자(root 여부)대로 남음. 원격 서비스 승인 분기의 기록도 확인 |
| 2 한 화면 승인 | `agent_service.approve_and_register`(미리보기 포함) | 위와 같은 규칙: 낮음·보통 혼자 완료, 높음·매우 높음 대기(`one_click_pending.approvers`가 1명), 같은 사람의 다른 토큰은 1명, 신청자 403, 두 번째 관리자로 완료, 매우 높음은 두 번째 클릭에도 사유 필요. **모드 표식은 확인하지 못했다 (결함 후보 1)** |
| 3 등록 | `core.register_server` | 정상 승인으로 만든 요청의 승인 증거를 바꿔 가며 호출: 높음에서 한 명·같은 사람 두 토큰·중복·빈 목록·신청자 포함은 거부(`solo_mode`·`solo_operator` 값과 무관), 두 다른 관리자는 등록, 매우 높음은 기록된 사유가 없으면 거부, 승인 증거의 표식(참·거짓·없음)이 등록 서버의 `risk_assessment`로 그대로 옮겨짐 |

### 완료 조건 대비

| 완료 조건 문구 | 새 시험 | 판정 |
| --- | --- | --- |
| D-188 독립 승인 규칙 유지 (신청자≠승인자, 승인자 수 불변) | 위 세 경로의 행위 시험 | 충족(대역). 앞 절의 「소스 문자열 검사뿐」은 해소 |
| D-188 승인 건별 모드 표식 | 경로 1은 첫 승인(`intake-cosign`)·최종 승인(`intake-approve`, 저장소·원격)의 `scope`를, 경로 3은 등록 서버의 `risk_assessment`를 값 그대로 확인 | 부분. 경로 2(한 화면 승인)는 표식이 남지 않는다 (결함 후보 1) |
| D-179 서명 불일치 차단 (게이트웨이 경로) | `provenance_gateway_check.py`: 신뢰 키가 아닌 키의 서명, 증명 대상 digest 불일치, 페이로드 변조, 허용 builder 밖, 설정에 없는 키 이름은 모두 409·`HOLD`·`MCP-SUPPLY-001`·`provenance-mismatch` 사건·게시 없음 | 충족(대역). 단 한 화면 승인 경로는 검사 자체가 없다 (결함 후보 2) |
| D-179 미제공은 표시만 (게이트웨이 경로) | 증명이 없으면 승인·게시가 진행되고 저장된 상태가 `확인 안 됨`. 이때는 신뢰 키 파일이 깨져 있어도 읽지 않는다 | 충족(대역) |
| D-179 검증 불가와 미제공의 구분 | 형식 오류·확인 경로 실패·신뢰 키 설정 오류(목록·값 형식·JSON 아님·빈 파일·파일 없음)는 차단, 메시지에 `검증 불가`가 있고 `확인 안 됨`은 없다 | 충족(대역) |
| D-179 처음 본 키를 믿지 않음 | 신뢰 키 파일이 `{}`이거나 설정이 없을 때 형식·digest·서명이 모두 맞는 증명도 차단, 신뢰 키 파일 바이트 불변, 다시 시도해도 차단 | 충족(대역) |

### 제품 결함 후보 (수정하지 않음, 메인 판단 필요)

1. **한 화면 승인(`approve_and_register`)은 승인 건별 모드 표식을 남기지 않는다.** `agent_service.py` 2079행(첫 승인 `pending`/`intake-one-click`·`recorded`), 2095~2096행(`risk_record`), 2124~2127행(`intake-one-click`·`approved` 사건 `scope`)에 `solo_mode`·`solo_operator`가 없다. 개별 승인 경로는 1568·1580·1586·1662·1730행에서 남긴다. 재현: `ROOT_SOLO_APPROVAL=1`, 높음 등급 원격 신청을 root, 다른 관리자 순서로 한 화면 승인하면 `approval_events`의 `intake-one-click` 두 건과 `evidence.risk_assessment`에 표식 키가 없다. 결과로 `core.py` 727행이 등록 서버에 `solo_mode: None`을 옮기고, 콘솔 1200행은 이를 「—」로 보여 준다. D-188(「위험 평가와 승인 사건에는 `solo_mode`·`solo_operator`를 기록」)과 D-189(「세 경로가 같은 표를 쓴다」)가 한 화면 승인 경로에는 적용되지 않은 것으로 보인다. 승인자 수에는 영향이 없다(표식만 빠짐). 이 사실을 고정하는 시험은 파일에 넣지 않았다.
2. **한 화면 승인 경로는 출처 증명 서명을 검사하지 않는다.** `artifact_provenance.verify_source_attestation`의 호출은 `agent_service.py` 1696행(개별 승인) 한 곳뿐이다. `approve_and_register`의 저장소 분기(2113~2117행)는 `publish_internal_repo`만 부른다. 재현: 저장소 신청의 `provenance.verification.attestation`에 신뢰 키가 아닌 키로 서명한 증명을 두고 미리보기(`blockers` 빈 목록) 뒤 `approve_and_register`를 누르면 보류 없이 `APPROVED`가 되고 게이트웨이 등록 호출까지 나간다(`MCP-SUPPLY-001`·`provenance-mismatch` 사건 없음). D-179의 「승인 때 확인」이 한 화면 승인에는 없다. 단 실행기는 시작·재조정 때 자기 증거로 다시 검증하므로(`runtime/worker.py` 579행) 실행 단계에서 막힐 수 있다. 이 연결은 확인하지 않았다. 이 사실을 고정하는 시험은 파일에 넣지 않았다.
3. (결함은 아니며 앞 절 정정) 이 문서 3절의 「기준 자체의 충돌」은 현재 `origin/main`에서 해소돼 있다. `risk_tier.APPROVAL["high"]`는 2명·사유 대안 없음이고 `root_solo_check.py`도 「높음 + 사유, 1명 → cosign」을 기대한다. 3절은 감사 시점 `517d3b7` 기준 기록이다.

### 대역과 실제의 구분

- 대역: 데이터베이스(`FakeLedger`가 `approval_events`·도입 신청·`principals`를 메모리에 두고 승인 경로가 보내는 문장만 이해하며 모르는 문장이면 시험이 실패한다), 게이트웨이 HTTP(`gateway_proxy`), 저장소 게시(`publish_internal_repo`), 경로 3의 `registry` 파일 쓰기·업스트림 MCP 탐색·카탈로그 갱신, 스캐너 보고서 조회.
- 실제 코드: `review.require_independent`·`same_person`·`record_event`·`transition`, `risk_tier`, `solo_mode_enabled`·`solo_operator`, 세 경로의 함수 본문, `core.register_server`의 승인 증거 재확인, `artifact_provenance` 전체(실제 Ed25519 서명·검증, 신뢰 키 파일 읽기), `review.intake_gate`(스캐너 보고서만 대역).
- 증명은 시험 안에서 만든 키로 서명했다. 외부 빌더의 실제 SLSA 증명이 아니다.

### 한계

- 실제 PostgreSQL(원장의 append-only 보장, 어드바이저리 잠금, 동시 클릭 경합)은 확인하지 않았다. 한 화면 승인의 직렬화 잠금은 대역이다.
- 경로 3의 서버 등록 사건(`server-register`)의 `scope`에는 모드 표식이 없고 표식은 등록 서버의 `risk_assessment`에만 있다. 의도인지 판단이 필요하며 시험은 후자만 고정했다.
- 콘솔에서 「승인 방식」이 어떻게 보이는지는 확인하지 않았다(화면 확인 없음). 기기·PJ1 시험은 하지 않았다.
- 한 화면 승인의 저장소 분기(게시 포함)는 낮음 등급 승인만 돌렸다. 높음 이상의 한 화면 승인은 원격 서비스 신청으로 확인했다.

- 8.2 1번과 2번은 시험 실행 실패와 집계 실패 롤백이 겹친 것이다. 롤백 결과는 코드 독해이며 재현하지 않았다. → 8-A에서 재현·수정했다.

## 8-A. D-176 기록 경로

브랜치 `10/21-d176-record-path`, 기준 `origin/main` 81263e4.

### 재현 (수정 전)

- 시험: `full_stack_lab/tests/auto_suspend_record_path_check.py`(PostgreSQL 없는 대역, `_record_decision`·`automatic_suspend.suspend`를 AST로 추출, 트랜잭션은 저장점 규칙 모사).
- 입력: 임계 2, `P-DLP-001` Block을 한 번 기록해 정상 기록, 두 번째 호출에서 집계 SELECT만 실패(`OSError`).
- 결과: 호출자가 `OSError`를 받았고 원장에는 첫 번째 행(`req-1`)만 남았다. 두 번째 Block 행(`req-2`)은 롤백됐다. 8.2 1번·2번의 코드 독해가 맞았다.
- 원인: `_record_decision`의 `db.transaction()` 안에서 판정 INSERT·체인 갱신 뒤에 `user_suspend.auto_suspend`를 같은 연결로 호출한다. 그 예외가 바깥 트랜잭션을 롤백한다.

### 수정 (수정 후)

- `core.py` `_record_decision`: 자동 중지 호출을 `connection.transaction()`(SAVEPOINT)으로 감싸고, 예외를 잡아 `logging` 오류 로그(`automatic suspension check failed; decision N stays Block`)만 남긴다. 판정 행과 체인 갱신은 저장점 밖이라 남는다.
- 판정은 바뀌지 않는다. 자동 중지 대상은 이미 `Block`인 호출뿐이고, 집계 실패는 Block을 Allow로 바꾸거나 다른 오류로 덮지 않는다.
- 다음 호출은 같은 집계를 다시 한다. 실패한 행도 `decisions`에 있어 다음 집계에 포함되고, 임계에 도달하면 중지가 이어진다(시험 `test_failed_check_is_retried_and_the_kept_row_counts_on_the_next_call`: 1건 정상·1건 실패·1건 정상 → 세 건 집계, 중지 1건).
- 판정 행에 「자동 중지 집계 실패」 표식은 붙이지 않았다(제한 참고). 원장 행 수정·삭제 코드 없음, 새 열·테이블·정책 ID 없음.

### 시험 결과

- 새 시험 7건 전부 통과: 정상 경로 행 기록, 임계 도달 시 행과 중지 기록, 비집계 Block은 집계 미호출, 집계 실패 시 행 유지·예외 없음·중지 없음, 실패 오류 로그, 재시도 후 집계 이어짐, 정책 목록 고정.
- 기존 시험(파일 무변경): `user_auto_suspend_check` 10, `user_server_suspend_check` 24, `user_suspend_all_check` 13, `dest_pin_credential_redaction_check` 16, `fresh_requester_check` 10, `dispatch_recheck_check` 15, `outcome_axes_check` 8, `security_edges_check` 6 모두 통과.
- 민감도: 수정을 origin/main의 core.py로 되돌리면 새 시험 3건(행 유지, 로그, 재시도)이 실패(ERROR)했다. 수정본을 복원했다.
- `py_compile`·`pyflakes` 변경 파일 통과, `tests/open_endpoints.py` PASS.
- 미해결 기존 실패(이번 변경과 무관): `intake_validation_test.py` 2건 ERROR, 원인은 Windows 심볼릭 링크 권한(WinError 1314)이다.
- 미실행: PostgreSQL 시험(`auto_suspend_pg_check.py`), 기기·PJ1. 대역으로는 실제 SQL 롤백 의미를 흉내 낼 뿐이며, 실제 PostgreSQL에서 SAVEPOINT 동작은 확인하지 못했다.

### 제한

- 판정 행 표식 미구현: 행이 이미 INSERT된 뒤라 같은 행을 고칠 수 없다(원장 수정 금지). 표식을 행에 넣으려면 판정 행을 집계보다 먼저 쓰는 구조 변경이 필요하고, 기존 JSON 필드 중 소비자에 영향 없는 자리가 없다(`timings`는 단계 통계 SQL이, `sequence_flags`는 연쇄 탐지 표시가, `conflicts`는 정책 충돌 스키마가 쓴다). 실패 사실은 오류 로그에만 남는다. 원장에 남기려면 승인 사건 종류를 새로 정해야 한다(메인 판단).
- 설정 오류(`AUTO_SUSPEND_THRESHOLD<1` 등)도 이제 Block 호출을 막지 않고 로그만 남긴다. 기동 시 검증이 없으므로 운영 전 확인이 필요하다.
### 후속 처리 (2026-10-21, 브랜치 `10/21-oneclick-markers`, 기준 `origin/main` 180f323)

결함 후보 1은 고쳤다. `approve_and_register`가 개별 승인 경로(`risk_tier_gate`·`approve_mcp_request`)와 같은 방식으로 `review.solo_mode_enabled()`·`review.solo_operator(user)`를 한 번 읽어 첫 승인(`intake-one-click`·`recorded`) 사건, 최종 승인(`approved`) 사건 `scope`, `risk_assessment`에 실제 값으로 남긴다. 승인자 수 계산은 바꾸지 않았다. 등록 서버의 `risk_assessment`가 `solo_mode: None` 대신 실제 값을 받아 콘솔 「승인 방식」이 「—」 대신 「단독 운영」·「일반 운영」을 보인다(값은 시험으로, 문구는 `console.js` 1200행 식으로 확인했고 화면은 보지 않았다). 결함 후보 2는 D-179 보강(`approve_and_register`의 출처 증명 재검증, 409)이 이미 들어와 있어 고칠 것이 없었고 그 동작을 고정하는 시험만 더했다. 새 시험은 `full_stack_lab/tests/oneclick_markers_provenance_check.py` 10건(모드 켜짐·꺼짐·`0`, root·다른 관리자, 낮음·보통·높음·매우 높음 표식 4건 / 신뢰 키가 아닌 키의 서명, 화면을 연 뒤 신뢰 키 교체, 저장된 제안의 증명 바꿔치기, 신뢰 키 설정 읽기 실패, 미제공 진행, 유효 서명 진행 6건)이며 모두 통과한다. 기존 103건(47·11·19·11·9·6)과 `ast.parse`로 함수를 추출하는 다른 시험 파일 7개는 그대로 통과한다. 민감도는 표식 수정을 되돌리면 13건, 출처 재검증을 지우면 4건이 실패했고 둘 다 원복했다. 한 가지 예외로 `intake_one_click_ast_check.py`는 함수 추출 목록에 `review.solo_mode_enabled`·`solo_operator`와 `os`를 더해야 했다(수정 전에는 `AttributeError`로 5건 실패, 시험 11건은 그대로). 새 결함 후보: 한 화면 승인의 저장소 분기는 `record["verification"]`을 `{**checked, ...}`로 덮어써 미리보기가 계산한 `provenance_status`·`provenance_keyid`·증명 본문이 승인 기록에 남지 않는다(개별 승인 경로는 `{**기존, **checked}`로 합친다). 서명이 검증된 신청도 콘솔 「서명·빌드 증명」에 `확인 안 됨`으로 보일 수 있다(`console.js` 1838행). 수정하지 않았고 메인 판단이 필요하다.
