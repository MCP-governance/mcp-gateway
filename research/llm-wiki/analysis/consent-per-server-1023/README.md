# 서버별 동의 요청·결정 분석 — 2026-10-23

W15-CONSENT-UX, D-200. 기준 `0f57d0c9c0994faf849544616c6e66939b113fd8` 위의 미커밋 변경이다.
사용자가 제공한 PJ1 Claude 실사용 사실(원격 5·로컬 3 MCP, filesystem 도구별 최초 호출 6회 중단)을 입력 증거로 삼았다.
이 작업에서 원장 원문·기기 상태를 독립 확인하지 않았다. [작업 보고](../../status/reports/2026-10-23-consent-per-server.md).

## 원자 요구와 증거

정확한 파일 SHA-256·심볼·행·실행 명령·종료 코드·출력은 [evidence.json](evidence.json)에 기록한다.
제품 코드 경로는 `full_stack_lab/gateway/app/` 기준이다. 모든 새 시험은 기존 제품 함수와 DB/브라우저 API 대역을 쓰며 실제 MCP 구현을 새로 만들지 않는다.

| ID | 요구 | 코드 | 시험·조건 | 효과·한계 |
| --- | --- | --- | --- | --- |
| C1 | 첫 동의 부족에서 승인된 서버 도구 전체 대기 | `consent.py:missing/request_server/_request`, `core.py:execute_call` | six-tool, concurrent-request, only-permitted, no-other-principal | 현재 호출 등급으로 6행 PENDING, 묵시적 GRANTED 0; 서버 승인·도구 심사·PAC visible 필터 |
| C2 | 서버별 1회 허용·거부 | `agent_service.py:decide_server_consent`, `consent.py:decide_server`, `console.js:ROUTES.consent` | six-tool UI, one-grant-six-calls, deny-all, >200 | 버튼 한 번으로 표시 ID만 처리, 기존 200행 절단 제거; 실제 DOM/HTTP는 미검증 |
| C3 | 도구별 감사·원자 처리 | `consent.py:decide_server` | per-tool-events, audit-failure, cancellation | 6도구→6사건, 실패/취소→행·사건 원복; PostgreSQL 자체 효과는 미검증 |
| C4 | 신원·서버·상태 경계 | 같은 함수·API `current_identity` | wrong-owner/server/stale/duplicate/empty, API principal, conflicting-decisions, unseen-new-request | 잘못된 집합 전체 거부; 클릭 후 생긴 도구 자동 승인 없음 |
| C5 | 동의 통제 불변 | `missing/_request/for_dispatch`, core 동의 gate | legacy ConsentTest 4건, deny, higher-grant, terms/grade/expiry/revoke, dispatch 15건 | 동의 없으면 Block/P-CONSENT-001; 과거 거부·유효 상위등급 동의 보존, 새 조건·상위 등급은 재동의 |
| C6 | 실패·복구에도 기본 차단 | core 동의 gate, `_request` transaction | request-failure, storage-recovery, actual-core-gate | 요청 저장 실패 Block/P-CONTROL-FAIL-CLOSED; 복구 후 PENDING부터 시작 |
| C7 | 제품 화면·이스케이프 | `console.js` 이용 동의·bulk handler | HTML injection, unknown enums, encoded-path, server groups/history | 서버·도구·목적·목적지·입력 이스케이프, 상태 한글·결측 `—`, 배지는 서버 수 |

## 설계 선택과 한계

권한 출처는 기존 transport 신원이 조회한 principal 및 레지스트리/PAC다. 서버 동의는 도구 실행 권한이 아니다.
`tool_reviews.consent`가 참이고 서버 승인·도구 심사·직원 PAC 노출 범위에 들어오는 도구에만 요청한다.
이후 각 호출은 기존 OPA·인자·자원·계약·서버 상태·전송 직전 동의 검증을 다시 통과해야 한다.
원격/로컬 transport를 분기하지 않으므로 두 경로에 같은 정책을 적용하지만 실제 8개 MCP 실행을 검증한 것은 아니다.

도구별 데이터 자원은 호출 인자에 따라 달라진다. 미래의 최고 등급을 추정해 동의 범위를 올리지 않고 현재 차단된 호출 등급으로 묶는다.
공개 등급에 동의한 뒤 중요 등급 자원을 쓰거나, 심사 목적/입력/목적지가 바뀌면 새 동의를 요구한다.
기존에 거부한 도구는 다시 PENDING으로 바꾸지 않는다. 기존 유효 동의·동일 대기 요청도 중복 생성하지 않는다.
철회·만료 뒤 실제 재사용 요청에서 다시 대기하는 기존 동작은 유지한다.

결정 대상은 화면에 나타난 도구별 요청 ID 집합이다. 서버 ID만 받아 나중에 추가된 요청까지 허용하는 방식은 버렸다.
본인·서버·처리 가능 상태가 전부 맞는지 행 잠금 후 검증하며, 하나라도 다르면 전체 실패한다.
감사 사건 추가 실패·취소도 트랜잭션 원복 대상이다. 행 잠금 순서는 도구명→등급→조건 해시→ID로 고정한다.
기존 `for_dispatch`의 공유 잠금·벽시계 만료 검사와 개별 결정 API는 변경하지 않았다.
DB 대역의 직렬화는 PostgreSQL MVCC/잠금 시험이 아니다. 실제 경쟁·상태 변경·원장 append-only 효과 검증은 남아 있다.

## 공개 스킬·OSS·공식 문서 검토

변경 전에 GitHub 공개 스킬/OSS를 검색했다. 외부 스킬의 스크립트·설치·자격 명령은 실행하지 않았다.
새 의존성을 들이지 않고 기존 정책 연동과 psycopg 트랜잭션만 사용한다.

| 자료·판본 | 확인 범위·라이선스·유지보수 | 실제 적용·한계 |
| --- | --- | --- |
| [MCP ext-apps authorization](https://github.com/modelcontextprotocol/ext-apps/blob/main/docs/authorization.md), main, 10-23 열람 | 서버별·도구별 OAuth 패턴 본문 확인. [라이선스](https://github.com/modelcontextprotocol/ext-apps/blob/main/LICENSE)는 Apache-2.0 전환·일부 MIT 잔존, 문서는 CC-BY-4.0 명시. SHA·최근 유지보수 commit은 확인 못함 | 사용자 동의 UI와 transport 인가의 차이를 비교한 참고. 코드를 가져오거나 해당 OAuth 패턴을 MINT 동의 정책으로 치환하지 않음 |
| [paldom/mcp-server-skills](https://github.com/paldom/mcp-server-skills) `mcp-server-security` 후보 | 검색 결과 후보만 발견; 원문 fetch cache miss. commit·라이선스·유지보수 미확인 | 미채택·설치/실행 없음; 근거로 사용하지 않음 |
| 기존 `psycopg[binary]==3.3.5`, pool 3.3.1 | `gateway/requirements.txt` 고정판. [3.3.5 라이선스](https://github.com/psycopg/psycopg/blob/3.3.5/LICENSE.txt) LGPLv3 본문 확인. 별도 commit SHA 미확인. [공식 transaction 문서](https://www.psycopg.org/psycopg3/docs/basic/transactions.html)는 열람 시 3.3.7.dev1 | 기존 `db.transaction()` 재사용. 예외 시 rollback 근거와 현 고정판 구분; 로컬 실제 SDK 부재로 실행 효과는 미검증 |
| [PostgreSQL 18 explicit locking](https://www.postgresql.org/docs/18/explicit-locking.html) | 행 잠금 충돌·트랜잭션 종료까지 유지·일관된 잠금 순서 공식 설명 확인. 문서 참고, 소스 도입 없음 | `FOR UPDATE`와 기존 `FOR SHARE`의 호환성 판단. 현재 배포 DB 판본·실측 대체 아님 |

외부 원문 전문을 저장·재배포하지 않았고 위 표는 자체 요약이다. 공개 검색/문서 확인을 고정 OSS 코드 실행 검증으로 세지 않는다.

## 남은 검증

실제 PostgreSQL에서 동시 첫 요청·허용/거부·철회와 dispatch SHARE의 경쟁, 감사 저장 실패 원복을 확인해야 한다.
PJ1 Claude 동일 승인 서버의 6개 도구가 한 동의 뒤 정상 이용되고 거부 시 전부 P-CONSENT-001로 차단되는지,
원격 5·로컬 3 MCP와 콘솔 브라우저에서 확인해야 한다. 이번에는 사용자 금지에 따라 기기 접속·배포·커밋을 하지 않았다.
