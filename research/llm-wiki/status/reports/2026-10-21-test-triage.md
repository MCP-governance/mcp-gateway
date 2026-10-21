# 2026-10-21 시험 상태 분류

- 작업자: Claude Code
- 코드 기준: `origin/main` a88b62d에서 만든 브랜치 `10/21-test-triage`. 제품 코드와 기존 시험은 고치지 않았다. 추가 파일은 이 보고서와 `full_stack_lab/tests/run_local_suite.py` 두 개다.
- 시작 근거: 메인 회귀 비교에서 「통과 아님」으로 나온 29개 파일
- 해결할 문제와 완료 조건: 29개 각각을 venv로 직접 실행해 A~E로 분류하고, (D)의 도입 커밋을 찾고, 회귀 비교용 실행기를 main에 돌린다.

## 결과

### (D) 정말 깨짐: 2개

| 파일 | 실패 내용 | 도입 커밋 | 근거 |
| --- | --- | --- | --- |
| `endpoint_snapshot_check.py` | `test_observation_status_route_scopes_authorize_only_own_endpoint_and_channel`. 제품 호출부가 `observation_status`에 `buffer_event_uid=None, dropped_count=0, buffer_reason=None`을 추가로 넘기는데, 시험의 `assert_awaited_once_with`는 옛 인자 5개만 기대한다. | `22cf622` (2026-10-21, DEV-80 / D-182, 엔드포인트 오프라인 버퍼). `main.py` 호출부 9줄을 바꾸면서 이 시험을 갱신하지 않았다. 단언 자체는 `c357831`(10-15)부터 있다. | `AssertionError: expected await not found`, Ran 21, `FAILED (failures=1)` |
| `field_account_git_test.py` | `test_deletion_blocks_root_and_tombstones_other_accounts`. `agent_service.py:797`의 `row["token"]`에서 `KeyError: 'token'`. 시험의 DB 더블은 `{"email": "alice"}`만 돌려준다. | `38a12c9` (2026-10-15, feat(v2) durable dispatch intent). `RETURNING email, token`과 `release_pool(None, row["token"], ...)`를 넣었다. 시험 더블은 `e3e705e`(09-29)부터 그대로다. | `FAILED (errors=1)`, Ran 3 (unittest 실행 기준) |

추가 발견: `field_account_git_test.py`에는 `if __name__ == "__main__":` 블록이 없다. 그래서 `python field_account_git_test.py`는 아무 출력 없이 rc 0으로 끝나며 시험을 0개 실행한다. 종료 코드만 보면 거짓 통과가 된다. `python -m unittest`로 돌리면 실제 시험 3개가 돌고 1개가 실패한다. 실행기는 unittest 파일을 이 방식으로 돌린다.

### (E) 설계상 실패: 1개

- `threat_trace_mapping_check.py`: 4개 중 3개 실패, `FAILED (failures=65)`. 독립 검토의 고정 해시(`normalized_sha256`)가 현재 소스와 맞지 않고, `files_match_review`가 False이며, 증거 줄 검사도 실패한다. 독립 검토 기준은 `ed2e172`(10-20)다. 지시대로 다른 레인의 갱신을 기다리는 실패로 두었다.

### 분류별 개수

| 분류 | 개수 | 파일 |
| --- | --- | --- |
| A 실제로는 통과 | 5 | console_copy, contracts, experiments, replay, schema |
| B 실행 경로만 맞추면 통과 | 2 | injection_corpus, protocol_versions |
| C 외부 의존 | 19 | 아래 표 참고 |
| D 정말 깨짐 | 2 | endpoint_snapshot, field_account_git |
| E 설계상 실패 | 1 | threat_trace_mapping |
| 합계 | 29 | |

## 분류표

「기본」은 venv Python을 `full_stack_lab/tests`에서 `python <파일>`로 돌린 종료 코드이고, 「설정 후」는 아래 PYTHONPATH를 준 뒤 저장소 루트에서 돌린 종료 코드다. 설정 후 값이 없으면 기본과 같다. 모든 행은 venv `C:/Users/bobysg/bob/프로젝트/.venv-mcpgw/Scripts/python.exe`(Python 3.12.10)로 실행했다.

| 파일 | 분류 | 종료 코드 (기본 / 설정 후) | 근거 출력 (마지막 줄 위주) | 필요한 설정·의존 | 기기(Linux) 추정 |
| --- | --- | --- | --- | --- | --- |
| console_copy_check.py | A | 0 / - | `console copy check: 0 problem(s)` | 없음 | 가능 |
| contracts_check.py | A | 0 / - | `self-check ok` | 없음 | 가능 |
| experiments_check.py | A | 0 / - | `self-check ok` | 없음 | 가능 |
| replay_check.py | A | 0 / - | `self-check ok` | 없음 | 가능 |
| schema_check.py | A | 0 / - | `PASS` 줄(한국어, CHECK 제약 12개 확인) | 없음 | 가능 |
| injection_corpus_check.py | B | 1 / 0 | 기본: `No module named 'app'`. 설정 후: `seeds 32 · instruction injection 26 · detected 21 · missed 5` | PYTHONPATH. 기본 실행은 `raw.githubusercontent.com`의 고정 커밋 URL을 받으므로 인터넷이 필요하다(`--file`로 로컬 파일 지정 가능). 탐지 21은 임계값 21과 같아 경계에서 통과한다. | 가능(인터넷 허용 시) |
| protocol_versions_check.py | B | 1 / 0 | 기본: `No module named 'app'`. 설정 후: `protocol versions check OK: legacy 2025-11-25 and stateless 2026-07-28 both served ...` (줄 머리가 OK가 아니어서 메인 규칙에서는 통과로 세지 않았다) | PYTHONPATH | 가능 |
| adversarial_check.py | C | 1 / 1 | `WinError 10061` 연결 거부 (127.0.0.1:8080) | 게이트웨이 HTTP 8080, `DATABASE_URL` | 스택 기동 시 가능 |
| credential_binding_check.py | C | 1 / 1 | `CredentialUnavailable`. 시험이 `chmod 0600`을 준 파일의 `st_mode`가 Windows에서 `100666`이라 `& 0o077`이 0이 아니어서 `credential file permissions`에 걸린다. | POSIX 파일 권한 | 가능 추정 |
| field_release_check.py | C | 2 / - | argparse: `--url --server --expected-revision` 필수 | 운영 대상 URL·서버·리비전 | 인자를 주면 가능 추정 |
| flow_fingerprint_check.py | C | 1 / - | `FAILED (failures=1, errors=3)`. Windows `ProactorEventLoop`와 psycopg가 맞지 않고, 풀 타임아웃으로 `P-CONTROL-FAIL-CLOSED`가 난다. | PostgreSQL 풀, SelectorEventLoop. 시험이 `user_suspend.expire`(DEV-79)를 스텁하지 않아 실제 풀을 쓴다. 시험 결함 의심(확인 필요). | PG가 있는 게이트웨이 이미지에서 통과 가능성 높음(추정) |
| intake_validation_test.py | C | 1 / - | `OSError: [WinError 1314]` (심볼릭 링크 시험 2개, Ran 16, errors 2) | Windows 심볼릭 링크 권한(사용자 지정 C) | 가능 추정 |
| intake_worker_scanners_check.py | C | 1 / 1 | 기본: `No module named 'intake_worker'`. 설정 후: `KeyError: 'TRIVY_CACHE_DIR'` | `TRIVY_CACHE_DIR`(Trivy DB 캐시) | Trivy 설치 시 가능 추정 |
| managed_enforcement_check.py | C | 1 / - | `No module named 'grp'` (Ran 10, errors 10) | Linux 전용 모듈 `grp` | 가능 추정 |
| managed_enrollment_check.py | C | 1 / 1 | 기본: `No module named 'app'`. 설정 후: `URLError ... getaddrinfo failed` (`http://agent-service:8000`) | 게이트웨이 네트워크의 `agent-service`, `MOCK_SSO_PASSWORD` | 스택 안에서 가능 추정 |
| mcp_result_contract_check.py | C | 1 / - | `psycopg_pool.PoolTimeout: couldn't get a connection after 10.00 sec` (Ran 18, errors 1) | PostgreSQL | 가능 추정 |
| mcp_result_services_check.py | C | 1 / - | `FileNotFoundError: libmcpgw_gitleaks.so`, `getaddrinfo failed`, `InspectionUnavailable` (Ran 5, errors 4) | Linux `libmcpgw_gitleaks.so`(`/usr/local/lib`), PII 분석기 엔드포인트 | 가능 추정 |
| oss_audit_test.py | C | 1 / 1 | 기본: `No module named 'app'`. 설정 후: `FileNotFoundError: ... libmcpgw_gitleaks.so` (Ran 10, errors 1, 나머지 9개 통과) | Linux `libmcpgw_gitleaks.so` | 가능 추정 |
| pac_boundary_check.py | C | 1 / 1 | 설정 후: `FileNotFoundError ... \registry\capabilities.json` (`/registry/field`를 하드코딩). 파일 주석에 「Gateway image 안에서 실행」이라고 되어 있다. | 게이트웨이 이미지의 `/registry/field` | 이미지 안에서 가능 |
| policy_replay_lab_check.py | C | 1 / 1 | `RuntimeError: PostgreSQL did not become ready` | PostgreSQL | 가능 추정 |
| provenance_gitea_check.py | C | 1 / 1 | `KeyError: 'GITEA_USER'` | Gitea 서버, `GITEA_USER`·`GITEA_PASSWORD` | 기기에 Gitea가 있을 때만, 미확인 |
| real_warning_review_check.py | C | 2 / 2 | argparse: `--url --reviewed` 필수 | 운영 대상 URL과 검토 파일 | 인자를 주면 가능 추정 |
| reservation_effect_check.py | C | 1 / 1 | `FileNotFoundError [WinError 2]` (docker 실행 파일을 호출함) | docker compose, `corp-db`·`gateway` 컨테이너 | 기기 compose 스택에서 가능 추정 |
| secret_engine_parity_check.py | C | 1 / 1 | `FileNotFoundError [WinError 2]` | `docker exec` 게이트웨이 컨테이너 | 기기에서 가능 추정 |
| testbed_network_check.py | C | 2 / 2 | argparse: `--out` 필수 | 테스트베드 이미지, 출력 경로 | 인자와 이미지가 있으면 가능 추정 |
| textscan_parity_check.py | C | 1 / 1 | `{"error": "native engine not active"}` | 네이티브 확장 `mcpgw_textscan`(PCRE2)이 로드되지 않음 | 이미지에 확장이 있는지 미확인 |
| endpoint_snapshot_check.py | D | 1 / - | `AssertionError: expected await not found` | 없음 (코드 불일치) | 기기에서도 실패 |
| field_account_git_test.py | D | 0(시험 0개 실행) / unittest 1 | unittest: `KeyError: 'token'` | 없음 (코드 불일치) | 기기에서도 실패 |
| threat_trace_mapping_check.py | E | 1 / - | `FAILED (failures=65)`, 고정 해시 불일치 | 없음 (독립 검토 갱신 대기) | 기기에서도 실패 |

### 설정 (B)

PYTHONPATH는 저장소 루트 기준으로 다음 5개다. 실행기는 절대 경로로 같은 값을 쓴다.

```
full_stack_lab;full_stack_lab/gateway;full_stack_lab/supply_chain;full_stack_lab/runtime;full_stack_lab/gateway/app
```

작업 디렉터리는 저장소 루트여야 한다. 상대 경로 PYTHONPATH를 쓰면서 작업 디렉터리를 `tests`로 바꾸면 경로가 깨진다.

## 실행기

`full_stack_lab/tests/run_local_suite.py` (표준 라이브러리만 사용)

- 대상은 `*_check.py`와 `*_test.py` 중 `_pg_check`, `real_mcp`, `e2e`가 없는 104개 파일이다.
- 판정은 종료 코드 기준이다. unittest 모듈 파일은 `python -m unittest <모듈>`로 돌리고, 실행된 시험이 0개면 실패로 본다(위 거짓 통과 방지).
- 외부 의존 19개는 스크립트 안의 `EXTERNAL` 표에 사유와 함께 적고 실행하지 않는다. 상태는 「외부 의존 생략」이다.
- (D)·(E) 3개는 `KNOWN` 표로 note에 표시만 한다. 상태는 실패 그대로다.
- 출력은 파일별 JSON이다(`file, status, rc, seconds, ran, last_line, note`). `--out`으로 파일에 쓴다. 실패가 있으면 종료 코드 1을 낸다.

main(a88b62d)에서 실행한 결과(41초):

| 총계 | 통과 | 실패 | 외부 의존 생략 |
| --- | --- | --- | --- |
| 104 | 82 | 3 (endpoint_snapshot, field_account_git, threat_trace) | 19 |

## 실패·미완료·한계

- (C) 19개는 이 PC에서 실행하지 않았다. 기기에서 돌아갈지는 추정이며 확인하지 않았다.
- `injection_corpus_check`는 기본 실행에 인터넷이 필요하다. 인터넷이 없으면 실행기에서 실패로 나온다.
- `flow_fingerprint_check`의 시험 결함(`user_suspend.expire` 스텁 누락)은 근거만 확인하고 고치지 않았다.
- 기존 시험과 제품 코드는 고치지 않았다. (D) 2개와 (E) 1개는 그대로 실패로 둔다.
- 기기에서 실행기를 돌리지 않았다.
- 메인 규칙(출력 줄 머리 `OK`)과 실행기 규칙(종료 코드)이 다르다. 통과 82 중 자체 출력 형식 파일은 종료 코드만 본다.

## 다음 작업

- (D) `endpoint_snapshot_check`: `22cf622`의 새 인자가 의도된 것인지 확인한 뒤 시험 단언을 맞출지, 제품 호출부를 되돌릴지 정한다.
- (D) `field_account_git_test`: 시험 DB 더블에 `token`을 넣거나 제품 쪽 조회를 바꾸고, `if __name__ == "__main__"` 블록을 추가한다.
- (D·E) 외에 `flow_fingerprint_check`의 `user_suspend.expire` 스텁 누락을 확인한다.
- (E) `threat_trace_mapping_check`: 독립 검토 갱신 후 재실행한다.
- 기기에서 C 19개 중 「가능」 항목을 실행기로 다시 돌려 생략 목록을 줄인다.

## 사용자에게 필요한 입력

- (D) 2건 중 어느 쪽을 정본으로 할지 정해 주세요. 제품 쪽을 되돌릴지, 시험을 갱신할지에 따라 수정 범위가 달라집니다.
