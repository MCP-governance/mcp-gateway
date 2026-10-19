# 2026-10-20 D-140 실제 PostgreSQL 경합 검사

- 작업자: Codex luna
- 코드 기준: 시작 commit `89c5ae592c2f56228f69139d5fedaeb68eb57ae2`, 시작 트리 clean. 변경 파일: `full_stack_lab/tests/dispatch_recheck_pg_check.py`, `research/llm-wiki/status/backlog.md`, 본 보고서.
- 시작 근거: DEV-43, D-140, [적대 검토 S5](../../analysis/review-1020/s5-dispatch-recheck.md), [원자 요구사항·코드 지도](../../analysis/dispatch-recheck-1020/README.md).
- 해결할 문제와 완료 조건: AsyncMock 대역만으로 확인했던 D-140의 실제 PostgreSQL 잠금 충돌·READ COMMITTED 스냅샷 경계를 격리 실험실에서 검사한다. 두 연결 이상과 명시적 잠금 대기로 계정 중지·동의 철회·중요 읽기 게시의 선후 순서를 각각 확인하고, 30회 무작위 순서 반복에서 교착·미종료가 없는지 확인한다.

## 결과

새 `dispatch_recheck_pg_check.py`는 제품 `dispatch.record`, `consent.decide`, `core._record_decision` 및 흐름 재확인 callback을 실제 psycopg 연결과 격리 PostgreSQL에서 호출한다. 최초 솔루션 기기 실행(사람 실행, 267초)에서 account/consent/flow dispatch-first 세 사례가 모두 `INSERT INTO dispatch_intents` 잠금 대기를 관찰하지 못해 실패했다. 원인은 `dispatch_intents` ACCESS EXCLUSIVE 잠금이 `dispatch.record`의 앞선 중복 확인 SELECT를 막아, 주체·동의 SHARE와 callback 진입 전에 정지시킨 것이었다. account/consent/flow dispatch-first 장벽을 제품 콜백으로 옮기고, callback 진입 후 writer의 실제 대기문을 `pg_stat_activity`·미승인 `pg_locks`로 확인하도록 고쳤다.

- 계정 중지: dispatch 콜백에서 멈춘 동안 `UPDATE principals`가 주체 SHARE를 기다리는 것을 확인한 뒤 callback을 풀고, intent 1건과 그 뒤의 계정 변경을 확인한다. 계정 UPDATE 선행 사례는 기존처럼 중지 commit 뒤 `principal` 거부와 intent 0건을 확인한다.
- 동의 철회: dispatch 콜백에서 멈춘 동안 `consent.decide(revoke)`의 `UPDATE user_consents` 대기를 확인한 뒤 intent commit과 철회를 확인한다. 철회 선행 사례는 기존처럼 `consent` 거부와 intent 0건을 확인한다.
- 중요 읽기 게시: dispatch 콜백에서 멈춘 동안 `_record_decision`의 advisory 잠금 대기를 확인한 뒤 intent commit과 원장 게시를 확인한다. 읽기 게시 선행 사례는 `audit_chain` 행 잠금으로 publisher를 먼저 advisory 보유 상태에 두고, dispatch callback의 실제 `_dispatch_flow_recheck`가 `flow`로 거부하는지 확인한다.
- 위 여섯 순서를 무작위화한 30회 반복에서 각 태스크를 완료까지 기다리고 테스트 DB의 deadlock 카운터 변화를 확인한다. 이 수정 뒤의 기기 재실행은 대기 중이다.
- 제품 코드·기존 시험 기대값은 수정하지 않았다. 새 장벽 코드의 `py_compile`은 통과했으며, 실제 PostgreSQL 결과는 재실행 전까지 확인되지 않았다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 정적 검사 | `python -m py_compile full_stack_lab/tests/dispatch_recheck_pg_check.py` — 2026-10-20, 로컬 | 통과 | 종료 코드 0 |
| 실제 PostgreSQL 최초 실행 | 솔루션 기기 격리 실험실, 사람 실행, 267초 | account/consent/flow dispatch-first 실패(INSERT 대기 관찰 실패); 나머지 세 선후 사례 통과; 30회 failed_rounds 30, deadlocks 0 | 사용자 제공 실행 결과 |
| 실제 PostgreSQL 수정본 재실행(콜백 장벽) | 솔루션 기기 격리 실험실, Claude 실행 | 계정·동의 dispatch-first 통과. flow dispatch-first는 실패(result=flow): 앞 반복에서 게시한 중요 읽기가 10분 창에 남아 새 출처로 보임 — 시험 격리 결함 | 제품 결함 아님 |
| 흐름 사례 격리 수정 후 재실행 2회 | 같은 실험실, 반복마다 고유 출처 서버·판정 시점 출처를 기준값으로 | 280/280 통과(12.4초·11.8초), 실패 0, 교착 0 | Claude 수정(메인) |
| 프로토콜·실제 MCP·upstream 효과 | 범위 밖; 시험은 PostgreSQL DDL/DML·제품 dispatch 기록만 사용 | 미실행·미확인 | 외부 MCP 도구 호출 없음 |
| 배포·정책 해시·PJ1 | 미실행 | 미실행 | — |

## 실패·미완료·한계

- 원장에 넣는 중요 읽기는 `_record_decision`의 합성 시험 이벤트다. 공개/상용 MCP의 실제 읽기나 downstream 효과를 증명하지 않는다.
- 무작위 30회 검사는 같은 격리 DB 안에서 여섯 강제 순서를 섞는다. 다중 게이트웨이 인스턴스, 네트워크 단절, 커밋 결과 불명, 부하 시험은 포함하지 않는다.
- 최초 실행의 실패는 잘못된 table gate가 SHARE 잠금 획득 전 중복 조회를 막은 장벽 오류로 판단했다. 수정본 재실행에서 다시 실패하면 실패 JSON과 PostgreSQL lock/deadlock 관측을 첨부해 원인을 조사한다.

## 다음 작업

수정본의 DEV-43 솔루션 기기 격리 시험을 실행한다: `cd full_stack_lab && ./tests/termination_dispatch_lab.sh up && ./tests/termination_dispatch_lab.sh run dispatch_recheck_pg_check.py`. 종료 뒤 `./tests/termination_dispatch_lab.sh down`을 실행한다. 성공 JSON, 30회 deadlock 값, 종료 코드를 이 보고서에 보충한다. 이후 별도 PJ1 검수와 실제 하네스·기존 MCP 경로의 독립 효과는 기존 DEV-43 완료 조건에 따라 진행한다.

## 사용자에게 필요한 입력

없음. 기기 시험은 사람이 솔루션 기기에서 실행한다.
