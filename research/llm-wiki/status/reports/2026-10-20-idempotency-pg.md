# 2026-10-20 변경 요청 멱등 PostgreSQL 경합 시험

- 작업자: Codex luna
- 코드 기준: `b1feb8b` (`10/20-idempotency-pg`), 시작 시 clean. 제품 코드 변경 없음. 추가 파일 `full_stack_lab/tests/dispatch_idempotency_pg_check.py`, 결정 `시험만(D-번호 없음)`, DEV-55 마지막 상태 칸 갱신.
- 시작 근거: DEV-55 / WBS G03.07 / POL-36 / D-126, `dispatch.py`의 `record`, `REPLAY`, `IDEMPOTENCY_TTL_SECONDS`.
- 해결할 문제와 완료 조건: 실제 격리 PostgreSQL에서 제품 함수를 사용해 같은 주체·지문 경합, TTL 완료 이력, 미확인 상태와 확인 뒤 재시도, 주체·인자·읽기 독립성을 검사할 새 시험을 추가한다. 제품 결함이 확인되면 최소 수정하되 기존 시험 기대값은 변경하지 않는다.

## 결과

새 `dispatch_idempotency_pg_check.py`는 기존 실험실의 격리 PostgreSQL과 합성 DB fixture를 사용한다. `dispatch.record`에 같은 주체·지문의 쓰기 8건을 동시에 보내는 라운드를 10회 수행하고, 매 라운드 intent 정확히 1건·나머지 `duplicate`와 PostgreSQL deadlock 카운터 증가 0을 확인한다. 완료 `confirmed_executed` 후 TTL 안 재전송 거부, `resolved_at`을 TTL보다 과거로 바꾼 뒤 허용, 오래된 `pending` 및 `uncertain`의 지속 차단, `confirmed_not_executed` 확인 뒤 허용도 검사한다. 다른 주체·인자 지문·읽기 요청의 독립성도 검사한다.

외부 MCP 호출을 하도록 만들지 않았다. PostgreSQL 시험은 미실행이므로 제품 결함 판정은 하지 않았고 제품 코드도 수정하지 않았다. 기존 시험 파일과 기대값은 바꾸지 않았다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 정적 검사 | `python -m py_compile full_stack_lab/tests/dispatch_idempotency_pg_check.py` (작업 PC, 2026-10-20) | 통과 | 명령 종료 코드 0 |
| 패치 형식 | `git diff --check` (작업 PC, 2026-10-20) | 통과 | 명령 종료 코드 0 |
| 실제 PostgreSQL | 미실행 | 기기 시험 대기 | 없음 |
| 실제 MCP·Gitea 효과 | 미실행 | 범위 외/미검증 | 없음 |
| 배포·PJ1 | 미실행 | 미검증 | 없음 |

## 실패·미완료·한계

새 PostgreSQL 시험 본문은 기기에서 실행되지 않았다. 실제 교착 수치·동시 DB 결과·완료 및 확인 상태는 아직 통과 증거가 아니다. 이 시험은 게이트웨이 DB 멱등 판정만 확인하며, Gitea가 실제 변경을 한 번만 적용하는지, 제품 배포, 게이트웨이 우회, MCP 공통 멱등 키 또는 정확히 한 번 실행을 보장하지 않는다.

## 다음 작업

DEV-55 기기 시험:

```bash
cd full_stack_lab
tests/termination_dispatch_lab.sh up
tests/termination_dispatch_lab.sh run dispatch_idempotency_pg_check.py
tests/termination_dispatch_lab.sh down
```

시험 JSON 결과에서 10개 경합 라운드 각각 intent 1·중복 7, deadlock 증가 0 및 TTL/확인 후 분기 전체 통과를 확인한다. 이어 실제 Gitea 독립 효과와 배포는 별도 시험으로 남긴다.

## 사용자에게 필요한 입력

없음. 실제 실험실 명령은 솔루션 기기에서 실행해야 한다.
