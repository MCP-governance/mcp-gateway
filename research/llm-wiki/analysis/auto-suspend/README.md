# DEV-74 반복 위반 사용자 자동 일시 중지

기준일: 2026-10-21 · 상태: 로컬 구현 및 정적 시험 완료 · 커밋/통합/배포/실기기 검증: 미완료

## 요구사항과 구현

| ID | 요구사항 | 구현 위치 | 확인 근거 |
| --- | --- | --- | --- |
| AS-01 | 직원×서버별 보안 위반을 설정 임계·관측 창으로 집계 | `core.AUTO_SUSPEND_POLICIES`, `AUTO_SUSPEND_THRESHOLD`, `AUTO_SUSPEND_WINDOW_SECONDS`; `automatic_suspend.suspend` | `tests/user_auto_suspend_check.py`: 임계 미달·창 밖 위반 제외 |
| AS-02 | 임계 도달을 만든 차단 결정과 자동 중지 행·원장 사건을 원자적으로 기록 | `core._record_decision` → `user_suspend.auto_suspend` → `automatic_suspend.suspend` | 같은 DB transaction 안에 decision, 기존 `user_server_suspensions`, `approval_events` 적재 |
| AS-03 | 다음 호출부터 기존 직원별 중지 정책으로 거부 | `core.execute_call`, 기존 `P-SUSPEND-001`, `dispatch.record` | 기존 D-181 시험 24건, 새 시험 상태·정책 경계 확인 |
| AS-04 | 중지 기간 만료 후 상태를 자동 해제하고 정상 호출을 허용 | `user_server_suspensions.expires_at`; `automatic_suspend.expire`; listing의 만료 상태 계산 | 만료 행의 `resumed_at=expires_at` 및 자동 재개 원장 사건; 최종 dispatch도 만료 시각을 검사 |
| AS-05 | 관리자 재개는 D-181 API·상태·원장을 재사용 | 기존 `/api/suspensions/{id}/resume` | 기존 D-181 시험의 재개 후 정상 호출 확인 |
| AS-06 | 집계/상태 조회 실패는 차단, 장애 자체는 위반에서 제외 | `core.execute_call`의 중지 상태 fail-closed, `_record_decision`의 원자 집계 | 신규 시험 집계 예외와 `P-CONTROL-FAIL-CLOSED` 경계 확인 |
| AS-07 | 동시 임계 도달에서 중지 행·사건은 하나 | 직원 advisory lock, `user_server_suspensions_active` 부분 유일 인덱스, `ON CONFLICT DO NOTHING` | 신규 시험 동시 삽입 모델; 실제 PostgreSQL 경쟁 시험은 미실행 |
| AS-08 | 화면에서 자동 여부·해제 예정 시각 표시 | `user_suspend.listing`, Console 「이용 중지」 표 | `automatic`은 「자동」, `expires_at`은 「해제 예정」으로 표시 |

## 위반 집계 정책 ID

실제 판정 원장에서 `decision='Block'`인 다음 다섯 정책만 센다. 집계 단위는 인증된 직원 principal과 현재 요청의 MCP 서버 조합이다.

| 정책 ID | 집계 이유 |
| --- | --- |
| `MCP-EGRESS-002` | 호출 인자의 내부 주소 SSRF 시도 |
| `MCP-DATA-EGRESS-001` | 중요정보 또는 탐지 개인정보의 외부 전송 시도 |
| `P-DLP-001` | 민감정보가 포함된 외부 전송 시도 |
| `P-CHAIN-001` | 중요정보 열람 뒤 외부 전송 연쇄 |
| `P-FLOW-001` | 승인되지 않은 서버 간 중요정보 흐름 |

고정 목록은 `full_stack_lab/gateway/app/core.py:AUTO_SUSPEND_POLICIES`다. `MCP-EGRESS-001`은 서버 등록 목적지 설정에서 비롯될 수 있어 제외했다. `PAC-09`~`PAC-12`는 승인·자산 범위 설정 누락과 사용자 행위를 판정만으로 구분하기 어려워 제외했다. `P-CONSENT-001`, 승인 대기/만료, 등록·카탈로그·분류 상태, 제한 실행량, 공급망·일시 격리, 계정/엔드포인트 상태, fail-closed 오류, `P-SUSPEND-001`도 세지 않는다. `P-UNTRUSTED-CONTENT-001`은 현재 승인 판정이고 `P-UNTRUSTED-CONTENT-002`는 경고여서 `Block` 집계에 포함되지 않는다.

## 설정·기록·복구

- Compose가 게이트웨이에 전달하는 설정: `AUTO_SUSPEND_THRESHOLD=5`, `AUTO_SUSPEND_WINDOW_SECONDS=600`, `AUTO_SUSPEND_DURATION_SECONDS=900`. 세 값은 모두 양수여야 하며, 1초 단위 창·중지 기간을 지원한다.
- 상태는 D-181의 `user_server_suspensions`를 재사용하고 열 하나 `expires_at`만 추가한다. 새 상태 테이블·새 판정 ID·별도 차단 경로는 없다.
- `approval_events`의 `user-server-suspend` 사건에는 `actor=automatic`, 사용자·서버, 임계, 집계 건수, 창(초), 정책 ID, 해제 예정 시각과 이미 진행 중인 호출 수를 넣는다. 자동 만료도 같은 원장의 `user-server-resume` 사건에 `actor=automatic`으로 남긴다.
- 임계에 도달한 거부 결정과 상태/원장 적재가 한 transaction이므로 집계 조회에 실패하면 transaction은 rollback되고 upstream 전송은 발생하지 않는다. 중지 상태 만료·조회 실패도 `P-CONTROL-FAIL-CLOSED`로 실행을 막는다. 해당 실패는 `AUTO_SUSPEND_POLICIES`에 없어 위반으로 누적되지 않는다.
- D-181의 직원 advisory lock과 부분 유일 인덱스가 자동/수동 삽입 및 최종 dispatch와 경쟁을 직렬화한다. 임계 도달 전에 dispatch transaction이 이미 통과한 호출은 취소되지 않는다.

## 근거와 한계

- 설계 원문: [방향 갱신 10-20, §3 DEV-74](../direction-1020/README.md#3-기술-목표)
- 규격 해석: [GB/T 45654—2025 6.5 a)](../../papers/LIB-M32.md). 표준은 생성형 AI 제공자의 입력 검출과 위법·불량 정보 반복 시 서비스 중지 규칙 공시를 다루는 권고성 국가표준이다. MINT는 그 내용을 다섯 MCP 호출 정책 ID의 자동 중지 규칙으로 한정해 적용한다.
- 상태·정책 재사용: [D-181](../../../../docs/ai/DECISIONS.md#d-181-직원별-mcp-서버-이용-중지재개는-계정을-두고-그-조합만-막는다-2026-10-21-dev-79), `P-SUSPEND-001`
- 신규 시험은 표준 라이브러리 기반 AST/상태 모형 시험이며 실제 PostgreSQL 트랜잭션·deadlock·멀티 replica 동작을 증명하지 않는다. 기존 D-181 회귀 또한 그 레인의 기존 검증 범위 그대로다.
- 임계는 서버별로 계산한다. 전체 MCP 서버를 하나의 사용자 총량으로 합산하지 않는다. 콘솔 표시 렌더링은 브라우저에서 확인하지 않았다.
- `map_threats.py`로 기존 `catalogs/threats.json`의 현재 코드 해시를 갱신했다. DEV-03 독립 검토는 과거 기준으로 유지되며, 해당 리뷰의 코드 참조 9개가 오래된 상태로 표시된다. 이 갱신은 독립 코드 리뷰가 아니다.
- `check_wiki.py --ci-ignored-local-sources`는 오류 0으로 통과했다. 경고 119건은 checkout에 없는 무시 대상 로컬 원문 자료다.
