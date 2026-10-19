# S5 (DEV-43, D-140) 전송 직전 재확인 적대 검토

- 검토자: Codex luna
- 기준: 브랜치 10/20-dispatch-recheck-review, HEAD 4f486596a3fe6c121e70bad82f4b6cbb13b291d1, 대상 커밋과 일치, 시작 트리 clean
- 범위: 소스·호출·잠금 순서 대조 및 기존 신규 대역 시험 실행. 제품 코드 변경 없음.
- 근거: [D-140 구현 지도](../dispatch-recheck-1020/README.md), [기존 작업 보고](../../status/reports/2026-10-20-dispatch-recheck.md), docs/ai/DECISIONS.md:1574-1582, research/llm-wiki/status/backlog.md:51.

## 판정 요약

네 공격 가설 중 현재 소스만으로 입증되는 교착, 입력 불일치, callback 우회, 취소 삼킴은 찾지 못했다. dispatch.record의 제품 송신 경로는 하나이며 callback을 항상 전달한다. 실제 PostgreSQL에서 잠금과 READ COMMITTED 동작을 검증한 것은 아니다.

가용성 한계: 중요 읽기의 결정 행이 _record_decision에서 먼저 commit되고 지문은 _remember_flow에서 별도 저장된다. 그 사이 content 모드 조회는 지문 없는 행을 “내용 확인 불가”로 취급해 서버를 출처로 보존한다. 정상이고 내용이 다른 호출도 보수적으로 차단될 수 있다. 이는 D-142 fail-closed 규칙과 D-140의 새 출처 차단에 맞는 경계다. 이 허용 동작을 약화하면 미지문 중요 읽기가 통과할 수 있으므로 수정하지 않았다.

| 항목 | 심각도 | 재현·반박 결과 | 수정 권고 |
| --- | --- | --- | --- |
| 잠금 순환·자기 교착 | 결함 미확인 | 선언된 경로별 잠금을 따라가도 역방향 대기 간선이 없고 dispatch와 원장 append는 서로 다른 시점의 transaction | 없음. 실 PG deadlock 시험은 유지 |
| 판정/재확인 입력 차이 | 결함 미확인 | 양쪽 모두 원본 arguments의 같은 leaf_text를 사용. observed 차이는 기록 map | 없음 |
| 원장 게시와 지문 저장 사이의 보수 차단 | 낮음, 가용성 | 중요 읽기 행 commit 후 fingerprint insert 전에 다른 content-mode dispatch가 오면 NULL 지문이 UNCHECKED source가 되어 불일치 내용도 차단될 수 있음 | 현 fail-closed 유지. 완화는 원자 게시 또는 명시적 지문 준비 상태를 설계한 뒤 검증 |
| 동의 없는 도구의 callback 누락 | 결함 미확인 | dispatch.record 제품 호출부 1곳이며 consent와 무관하게 callback 전달 | 없음 |
| 예외·취소 동작 변경 | 결함 미확인 | 일반 Exception은 control 차단, CancelledError는 BaseException 경로로 rollback 뒤 전파 | 없음 |

## 1. 교착 — 확인된 결함 없음

| 경로 | 획득 순서 | 근거 |
| --- | --- | --- |
| 최종 dispatch | 예약 조회(명시 잠금 없음) → 주체 advisory → 서버·도구 SHARE → 주체 SHARE → 동의 SHARE(필요 도구) → 승인 UPDATE(있을 때) → 흐름 조회 → intent INSERT/승인 소비 → commit | full_stack_lab/gateway/app/dispatch.py:73-137 |
| 계정 중지·삭제 | principals UPDATE 행 잠금 → 자동 commit → 세션·연결 회수 | agent_service.py:741-758, 771-783 |
| 동의 결정 | user_consents UPDATE 행 잠금 → approval_events INSERT → commit | consent.py:81-94, review.py:34-44 |
| 종료 시작 | mcp_servers FOR UPDATE → 케이스 INSERT → 서버 UPDATE → 관계 UPDATE → commit | decommission.py:241-258 |
| 종료 종결·재개 | 케이스 UPDATE → mcp_servers UPDATE → 관계 UPDATE(종결) | decommission.py:775-786, 796-803 |
| 예약 | 주체 advisory → 예약·결정 집계 SELECT → call_reservations INSERT → commit | core.py:1265-1315 |
| 원장 append | 중요 읽기만 주체 advisory → 전역 audit_chain FOR UPDATE → decisions INSERT/head UPDATE → commit. 기타 append는 chain만 | core.py:1793-1840 |

- 재현 시도: dispatch가 advisory를 잡고 서버 SHARE에서 대기해도 종료가 보유한 서버 UPDATE 이후 종료 경로는 advisory를 요청하지 않는다. 계정 UPDATE는 주체 SHARE에서만 충돌하고 서버를 요청하지 않는다. 동의 UPDATE도 동의 SHARE에서만 충돌한다. 확인한 경로끼리 순환 대기 없음.
- 자기 교착 반박: dispatch.record transaction은 _call_upstream이 MCP 응답을 받기 전에 끝난다(core.py:1548-1550, 1585-1593). _record_decision은 그 뒤 별도 transaction에서 advisory를 얻는다(core.py:1793-1798). 같은 요청이 advisory를 가진 채 원장 기록을 기다리지 않는다. 예약 transaction도 _reserve_call 반환 전 종료(core.py:1266-1315).
- 원장 append가 chain을 잠근 뒤 advisory를 역취득하는 경로는 없다. 동의 이벤트 기록은 approval_events INSERT이며 chain 잠금을 취하지 않는다.
- 권고: 코드 변경 없음. 실제 DB 교착 검증은 여전히 필요하다.

## 2. 흐름 오탐 — 입력 불일치 미확인; 비교 불가 구간은 낮은 가용성 영향

- 최초 흐름 계산은 execute_call의 원본 arguments를 leaf_text(arguments, keys=True)에 전달한다(core.py:1931, 2058-2060).
- 마스킹 outbound는 별도 값으로 만든다(core.py:2034-2047). 제한 적용 effective도 후속 단계(core.py:2172-2192). 최초 흐름 계산은 둘 다 쓰지 않는다.
- 재확인은 pac_payload["arguments"]를 같은 leaf_text(..., keys=True)에 전달한다(core.py:1545-1547, 1191-1193). pac_payload는 상위 입력 payload이고 그 arguments를 변경하지 않는다. 따라서 양쪽 지문 문자열은 동일한 원본 요청 인자다.
- 최초 observed map은 결과 기록용이며 policy_input.request.flow_observed에 저장된다(core.py:2058-2060, 2088-2092). 재확인에서 map을 전달하지 않지만 차단은 sources 집합 차이만 사용한다(core.py:1193). 관찰 map 누락은 판정 입력 불일치가 아니다.
- 동일 DB 행·설정이면 두 시점의 지문 계산 결과는 같다. 새로 커밋된 중요 읽기는 새로운 source라 차단하는 의도된 경쟁 결과다. 서로 다른 입력 때문에 정상 호출이 P-FLOW-001로 막히는 재현은 없다.
- 별도 시간 경계: _record_decision commit(core.py:1793-1840) 이후 _remember_flow 저장(core.py:2238-2241)은 별도 transaction이다. 그 틈의 LEFT JOIN은 NULL fingerprint를 반환(core.py:1171-1177). narrow는 NULL 지문을 UNCHECKED로 분류하고 source를 유지(flow_fingerprint.py:84-107). 그러므로 content 모드에서도 내용 불일치 여부를 확인할 수 없어 일시 차단할 수 있다.
- 수정 권고: 현 보안 판정은 유지하고 실제 PG에서 빈도·구간을 잰다. 완화가 필요하면 결정 행과 지문 게시 원자화 또는 “지문 생성 중” 상태를 별도 설계한다. 미지문 읽기의 차단을 약화하는 변경은 적대 검토가 필요하다.

## 3. 철회·중지·callback 우회 — 우회 미확인

- 계정 UPDATE가 주체 FOR SHARE보다 먼저면 dispatch가 대기한다. 다음 INSERT statement는 READ COMMITTED 새 snapshot으로 비활성 상태를 보고 0행이 된다(dispatch.py:92-94, 48-60, 117; 계정 UPDATE agent_service.py:741-745). dispatch SHARE가 먼저면 상태 UPDATE는 intent commit까지 기다린다.
- 동의 철회가 for_dispatch 전에 commit되면 GRANTED 조회가 비어 consent 거부가 된다(consent.py:66-75; dispatch.py:97-101). 조회 뒤 철회는 SHARE에 막혀 dispatch commit까지 기다린다. 만료는 INSERT의 clock_timestamp()에서 재검사하며 0행 시 만료 사유를 구분한다(dispatch.py:117-121).
- READ COMMITTED 새 statement snapshot은 소스상 기대와 맞지만 대역은 PostgreSQL의 실제 snapshot/EvalPlanQual를 구현하지 않는다.
- dispatch.record( 전체 검색 결과 제품 호출은 core.py:1549 한 곳이고 recheck=recheck를 전달한다(core.py:1545-1550). 동의 없는 도구도 같은 호출부를 통과한다. callback 인자는 정의상 optional이지만 제품 호출 경로에서 생략되지 않는다.
- 권고: 격리 PostgreSQL에서 writer 선/후행 경쟁과 statement snapshot을 검증한다.

## 4. 실패 처리 및 취소 — 변경 이상 미확인

- _Refused는 dispatch.record 내부에서 이유 코드로 바뀐다(dispatch.py:139-143). DB/transaction 일반 예외는 core.py:1551-1552에서 control로 매핑되고 1553-1555에서 P-CONTROL-FAIL-CLOSED Block이 된다.
- Python 3.10 asyncio.CancelledError는 Exception이 아닌 BaseException 계열이므로 except Exception에 잡히지 않는다. transaction 정리·rollback 뒤 취소가 전파되고 upstream 호출 지점 전에 끝난다(dispatch.py:72-138).
- 재현: 기존 dispatch_recheck_check.py의 lock/insert/commit 오류는 차단, intent 0, MCP 호출 0을 확인한다. 취소 사례도 CancelledError 전파와 rollback/잠금 해제를 확인한다. 모두 대역 결과다.
- 권고: broad catch의 fail-closed 동작 유지. 실제 DB connection loss 시험은 남는다.

## 검증

| 확인 | 명령 | 결과 |
| --- | --- | --- |
| 기존 D-140 대역 적대 시험 | python -B -X utf8 full_stack_lab/tests/dispatch_recheck_check.py | 15/15 통과 |
| Python 구문 | python -m py_compile full_stack_lab/gateway/app/dispatch.py full_stack_lab/gateway/app/consent.py full_stack_lab/gateway/app/core.py full_stack_lab/tests/dispatch_recheck_check.py | 통과 |
| 패치 공백 | git diff --check | 통과 |
| 실제 PostgreSQL·PJ1 | 미실행 | 미확인 |

확실한 제품 결함은 확인하지 못해 코드·새 시험은 추가하지 않았다. 기존 시험 기대값 변경도 없다. 결론은 코드 경로와 대역 시험에 한정되며 실 DB 잠금·snapshot은 별도 검수 대상이다.
