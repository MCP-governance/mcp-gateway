# DEV-43 최종 전송 재확인 — D-140

작업자 Codex sol, 2026-10-20. 브랜치 `10/20-dispatch-recheck`, 시작 `78deab0a056050c3da0a39a69b1cfc8d51eefa30`, 변경은 미커밋 작업 트리다. [RV-03](../review-2026-10-15/README.md)과 [10-18 적대 검토 5·6번](../controls-1018/codex-sol-adversarial.md)의 판정 이후 철회·열람 공백을 다룬다. [작업 보고](../../status/reports/2026-10-20-dispatch-recheck.md).

## 원자 요구사항과 증거 범위

| ID | 요구사항·반례 | 코드 심볼·행(이 작업 트리) | 새 시험 조건 | 관측·남은 증거 |
| --- | --- | --- | --- | --- |
| DR-01 | 서버 잠금 대기 동안 중지가 커밋되거나, 미커밋 중지의 주체 행을 기다렸으면 intent를 만들지 않는다 | `dispatch.py:63` `record`, `core.py:1438` `_call_upstream` | 중지 선커밋·dispatch 시작 후 서버 대기 중 커밋·주체 행 대기 후 커밋 | 대역 intent 0·`call_tool` 0·`upstream_attempted=false`, Block+P-INPUT-001. 실제 PG 미실행 |
| DR-02 | 동의 철회·만료·조건/등급 불일치를 과거 허용으로 덮지 않는다 | `consent.py:66` `for_dispatch`, `dispatch.py:47` `_INSERT` | 선철회·서버 대기 중 철회·행 공유 잠금 뒤 철회 대기·INSERT 시각 만료, 조건 해시·주체·도구·등급 SQL 바인딩 | 대역 Block+P-CONSENT-001·intent/호출 0. SQL 만료·조건 필터 자체는 PG 확인 필요 |
| DR-03 | 판정 이후 늘어난 중요정보 출처를 같은 주체별 잠금에서 찾는다 | `core.py:1154` `_flow_sources`, `core.py:1186` `_dispatch_flow_recheck`, `core.py:1754` `_record_decision` | advisory 대기 중 새 출처 커밋·열람 게시자의 잠금 대기·공급자 읽기·기존 출처·content 불일치·같은 출처의 새 비교 불가 읽기 | 출처 증가 시 대역 Block+P-FLOW-001·intent/호출 0, content의 무관한 읽기 허용 유지. 실제 본문 전달 미실행 |
| DR-04 | 잠금·동의·흐름 조회·INSERT·COMMIT 실패와 취소는 전송을 못 한다 | `dispatch.py:63` `record`, `core.py:1438` `_call_upstream` | 7단계 장애·취소, 롤백·모든 대역 잠금 해제 | 일반 오류 Block+P-CONTROL-FAIL-CLOSED·intent/호출 0. 취소는 재전파, 실제 연결 손실 미시험 |
| DR-05 | intent가 먼저 커밋된 호출은 철회 이전에 이미 승인된 전송 경계로 취급한다 | 같은 심볼 | intent INSERT 직전 중지/철회 writer를 시작해 커밋까지 대기시킨 뒤 다음 요청 | 선행 intent 1·호출 1, 변경 커밋 뒤 신규 intent/호출 0. 이전 외부 효과 취소를 주장하지 않음 |

행 기준은 저장소 루트 아래 `full_stack_lab/gateway/app/`다. 시험은 [dispatch_recheck_check.py](../../../../full_stack_lab/tests/dispatch_recheck_check.py)의 제품 함수 정의를 AST로 로드하며, DB는 AsyncMock·트랜잭션/잠금 대역이다. 실제 제품 SQL을 PostgreSQL이 실행한 증거가 아니다. 가짜 MCP 서버는 만들지 않았다. 기존 시험 파일·기대값은 그대로다.

## 잠금과 선형화 경계

`record`: 주체별 `pg_advisory_xact_lock(hashtext(user_token))` → 서버/도구 행 `FOR SHARE` → 주체 행 `FOR SHARE` → 동의 행 `FOR SHARE` → 승인 행 `FOR UPDATE` → 같은 연결의 흐름 조회 → intent INSERT/승인 소비 → commit. 서버/도구 잠금은 기존 쿼리를 유지한다. 주체 행은 그 대기가 끝난 뒤 따로 잠그므로 대기 중 완료된 계정 중지가 다음 INSERT 스냅샷에 보인다. 주체 상태만 고치는 UPDATE와도 충돌해야 하므로 `FOR KEY SHARE`는 쓰지 않는다. 동의는 현재 `scope_review`의 조건 해시와 예약된 데이터 등급 이상 GRANTED 한 행을 잠근다. 최종 INSERT에서 `clock_timestamp()`로 그 행의 만료를 한 번 더 확인한다. 없어졌거나 만료되면 요청을 새로 생성하지 않고 차단한다(초기 `missing`이 요청 생성을 담당).

열람 게시자는 주체별 advisory → `audit_chain` 행 잠금 → 판정 원장 append 순서다. 응답은 `_decision_payload`의 기록이 끝나야 반환되므로, 먼저 커밋된 열람은 최종 조회에 보이고 dispatch가 먼저 잠그면 해당 열람 응답은 intent 이후에 게시된다. 동의 결정은 동의 UPDATE만 잠그고, 계정 중지는 주체 UPDATE가 커밋된 뒤 세션·연결 정리를 한다. 이 둘은 원장 잠금이나 서버 잠금을 가진 채 advisory로 역진입하지 않는다. dispatch는 audit_chain을 잠그지 않고, `_decision_payload`의 원장 기록과 예약 해제는 별도 트랜잭션이어서 역순을 만들지 않는다. 기존 동의·승인 사건의 외래키 KEY SHARE는 주체 SHARE와 호환된다.

동의·주체 상태의 선형화는 최종 intent 커밋이다. 커밋 뒤 실제 `tools/call`까지의 간격에서 발생한 철회로 이 호출을 취소한다고 주장하지 않는다. 네트워크 호출 동안 잠금을 유지하지 않으며 재시도도 추가하지 않았다. 교착·DB 실패는 자동 재시도 없이 실패 차단한다. flow 출처가 늘면 수신 심사에 포함되더라도 이번 호출은 보수적으로 차단하고 사용자가 다시 요청했을 때 새 판정을 받는다. D-142의 coarse/content 모드와 원문 인자 기준을 유지한다.

## 공식 근거·OSS/공개 스킬 탐색

조회일 2026-10-20. 외부 파일·스크립트는 설치·실행·복사하지 않았다.

| 대상 | 판본·라이선스·commit 확인 | 확인 범위·실제 사용 |
| --- | --- | --- |
| [PostgreSQL 18 명시적 잠금](https://www.postgresql.org/docs/18/explicit-locking.html), [READ COMMITTED](https://www.postgresql.org/docs/18/transaction-iso.html) | 저장소 `compose.yaml`의 `postgres:18-alpine`, PostgreSQL License. 이미지 digest·소스 commit은 이번에 확인 안 함 | §13.3.2 SHARE가 상태 UPDATE와 충돌하고 KEY SHARE는 상태 UPDATE를 막지 못함, §13.3.4 일관 잠금 순서, §13.2.1 문장별 새 스냅샷을 대조. 구현의 잠금 모드 선택 근거 |
| [psycopg/psycopg 3.3.5](https://github.com/psycopg/psycopg/tree/3.3.5), [LICENSE](https://github.com/psycopg/psycopg/blob/3.3.5/LICENSE.txt) | 기존 requirements의 psycopg[binary] 3.3.5·psycopg-pool 3.3.1 유지. 주 패키지 LGPL-3.0 계열. 태그 페이지 확인, commit SHA API 조회 실패 | 공식 저장소·태그 존재 확인. 릴리스 간격/최신성·새 코드 전문 분석은 미실행. 기존 `db.transaction()`·connection.execute 사용, 새 의존성 없음 |
| [supabase/agent-skills](https://github.com/supabase/agent-skills), 공개 PostgreSQL 스킬 후보 | [MIT](https://github.com/supabase/agent-skills/blob/main/LICENSE), main. commit SHA API 조회 실패 | 공식 저장소 공개 후보와 라이선스 확인. 현재 commit 고정·전체 스킬 검토/실행은 하지 않아 채택하지 않음. 제품은 기존 psycopg/PG 잠금으로 충분 |

## 한계와 기기 검수

동일 서버 제외·10분 창·important/r/upstream_executed 출처 정의와 content 지문의 변형 미탐은 D-133/D-142 그대로다. 최종 정책 입력은 최초 판단의 재현 자료이고 새 출처 값으로 덮어쓰지 않는다. 추가 차단 사유는 최종 policy_id에 남는다. `dispatch.record`의 선택적 `recheck`는 유일한 제품 전송 호출부 `_call_upstream`이 항상 제공한다. 기존 저장소 시험의 직접 `record` 호출은 callback 없이 저장/승인 경계만 검사하며 흐름 통합 증거가 아니다.

기기에서는 보고서의 명령으로 기존 PG 시험을 실행하고, PJ1 실제 하네스·기존 OSS MCP에서 목록 조회 뒤 장벽을 둔 중지/철회/열람을 교차한다. intent 수·최종 decision/policy_id·upstream_attempted·독립 하위 시스템 효과를 같은 request_id로 대조해야 DEV-43을 검수 완료로 바꿀 수 있다.
