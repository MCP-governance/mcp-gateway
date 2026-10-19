# DEV-44 / RV-05 출력 계약 승인과 판본별 결과

- 기준: `f6c3071535e5f49231cff5b43e140182779700ac`, `10/20-output-contract`, Codex sol, 2026-10-20.
- 결정: [D-149](../../../../docs/ai/DECISIONS.md). [종전 검토](../review-2026-10-15/README.md)의 RV-05와 D-109 정정을 구현한다.
- [출처·SDK 파일 해시](sources.json), [실행 검사 기록](validation.json), [작업 보고](../../status/reports/2026-10-20-output-contract.md).

## 판본 근거

| 판본 | 출력 스키마 / 구조화 결과 | 적용 |
| --- | --- | --- |
| [2025-06-18](https://modelcontextprotocol.io/specification/2025-06-18/server/tools#structured-content) | 출력 스키마 도입, structuredContent는 객체. 스키마가 있으면 결과가 일치해야 하며 text JSON 병기도 권고한다. | 객체 보존. 현대 서버의 비객체 결과는 검사 후 JSON text로 보존한다. |
| [2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/server/tools#structured-content) | 객체형 출력 계약 유지. | 객체 보존. 비객체 출력 계약은 이 판본의 도구 목록에 광고하지 않는다. |
| [2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/server/tools#structured-content) | 배열·문자열·숫자·불리언·null을 포함한 JSON 값과 이에 맞는 출력 스키마 허용. | 검사·마스킹 후 값과 타입, 명시적 null의 필드 존재까지 보존한다. |
| 이전/미확인 판본 | 위 신형 규칙을 추정 적용하지 않는다. | 알려진 이전 판본은 text로 변환한다. 판본 없는 기존 내부 호출은 기존 객체형 동작을 유지한다. |

게이트웨이의 고정 의존성은 `mcp==2.2.0`, `jsonschema==4.26.0`이다. 로컬 공식 SDK 사본을 read-only로 확인했다(commit `9972c21aa42054fb1450c5fc614761ed11847ec6`, MIT, Git 작업 트리 변경 없음). `mcp-types`도 SDK pyproject에서 같은 판본으로 고정한다. 로컬 사본은 런타임에 설치된 SDK 증거와 구분한다.

SDK `src/mcp/client/session.py:1052-1183`의 `call_tool`은 수신 뒤 광고 스키마를 검증한다. `validate_tool_result`는 `None`을 미반환으로 취급하며 내부 해시는 사람의 승인 잠금이 아니다. `send_request:540-600`은 협상 판본의 wire 검증과 요청 헤더 처리를 유지한다. 이를 공식 타입과 함께 호출해 수신 상태를 먼저 확보하고 MINT가 별도의 승인 출력 계약을 검증한다. 입력 추가 요청·확장 해석에 따른 자동 재시도는 허용하지 않는다. SDK의 private 캐시나 검증 함수를 수정하지 않는다.

SDK `mcp_types/_types.py:1424-1429,1474-1478`과 `version.py`는 객체/일반 JSON 값 경계를 명시한다. SDK runner의 `_dump_result:110-124`는 `exclude_none=True`를 쓰므로 명시적 null에 한해 기존 Pydantic serializer 확장으로 필드 삭제를 막는다. 실제 SDK 직렬화 시험은 게이트웨이 이미지에서 실행해야 한다.

관련 공개 스킬 `anthropics/skills`의 `mcp-builder`도 검색·본문 확인했다. 새 MCP 서버 작성에 초점이 있고 기존 게이트웨이의 승인 전환을 제공하지 않아 코드는 채택하지 않았다. commit과 라이선스 본문은 미확정으로 기록했다. 스크립트 실행·설치는 하지 않았다. 유지보수되는 공식 SDK와 기존 JSON Schema 검증기를 사용하며 새 의존성은 없다. `referencing.Registry`는 기존 JSON Schema/SDK 의존성으로, 빈 레지스트리를 써 외부 스키마를 가져오지 않는다.

## 승인과 전환

입력 해시는 유지하고 출력 전용 `output_schema_sha256`(잠금 파일), `approved_output_schema_hash`·`observed_output_schema_hash`·`output_schema`(DB)를 추가했다. 출력 스키마 추가·수정·삭제 모두 계약 변경이다. 활성 도구만 선택적으로 제한하며 카탈로그는 DRIFT를 기록한다. 판정의 기존 `schema_hash_match`는 입력과 출력 해시가 모두 맞아야 참이다. 최종 전송 SQL과 같은 연결의 목록 재확인도 출력 계약을 비교한다.

초기 구현 문구는 기존 잠금/DB의 출력 해시 부재를 `SHA256(canonical null)`과 동등한 고정 계약으로 설명했다. 이 해석은 2026-10-20 배포에서 기존 MarkItDown·GitHub 도구를 DRIFT 처리해 약 10분간 목록에서 사라지게 한 뒤 정정되었다. D-149 전환 정정에 따라 출력 해시가 없는 기존 잠금·DB 승인·poisoning 심사는 **미고정**이다. 목록·정책 계약·전송 직전 재확인·응답 검증·하네스 광고에서 출력 스키마로 제한하지 않으며, 관측값은 승인에 채택하지 않는다. 사람이 `approve_contract`로 재승인하면 관측 해시가 기록되고 이후 변경은 DRIFT가 된다. 새 등록은 승인된 도입 계약의 출력 해시를 기록한다. 이 전환은 기존 도구의 출력 변경을 재승인 전까지 탐지하지 않는 한계가 있다.

정정 이력: 최초 구현 시의 “canonical null은 출력 스키마 없음” 해석은 위 배포 사고 후 대체되었다. 상세 반박 경로와 근거는 [D-149 전환 적대 검토](../review-1020/d149-transition.md)를 참조한다.

사람의 재승인은 관측 출력 해시를 승인 열에 복사하고 기존 승인 이벤트에 이전/이후 출력 해시를 추가한다. 파일 잠금 생성·비교 도구에도 출력 해시를 포함했다. 이 작업은 두 `registry/**/contracts.lock.json`을 수정하지 않는다. 실제 서버 확인 후 사람이 diff를 읽고 커밋해야 한다.

## 응답 통제와 한계

해시가 확인된 동일 연결의 출력 스키마로 원본 structuredContent를 검사한다. 누락·불일치·유효하지 않은 스키마·미지원 dialect·외부 참조 해석 실패는 `MCP-OUTPUT-001`로 결과를 보류한다. 마스킹 후에도 검증하여 형식이 깨진 결과를 승인 스키마와 함께 반환하지 않는다. 도구 오류 결과도 승인 스키마가 있으면 검사한다(오류 결과를 검사에서 제외하는 SDK 기본 호출보다 엄격하다).

상위 연결의 판본은 수신 검증에, SDK 요청 문맥의 하위 판본은 목록·응답 표현에 사용하며 감사 client 문맥에도 기록한다. 이는 하네스의 자기신고나 신원 판정 값이 아니다. 현대 서버→구형 하네스는 마스킹된 값을 JSON text로 옮기고 표현 크기·주입 검사도 다시 수행한다. 도구 실행 효과를 되돌리지 않으며 감사 원장을 수정하지 않는다.

| 원자 요구사항 | 구현 심볼 | 시험·현재 증거 |
| --- | --- | --- |
| OC-01 출력 변경 잠금·사람 승인 | `upstream.tool_view`, `registry.tool_hashes/sync/build_lock`, `core.refresh_catalog/approve_contract` | 새 시험의 카탈로그 DB AsyncMock, 추가/변경/삭제→DRIFT·재승인→READY, 로컬 통과 |
| OC-02 전송 전 계약 재확인 | `core._contract/_call_upstream`, `dispatch.CATALOG_OK`, `selective.restricted_tools` | 실행 직전 출력 변경→Block/MCP-CATALOG-001·SDK 미호출, 로컬 통과. 실제 PostgreSQL 경쟁은 미실행 |
| OC-03 불일치 결과 보류 | `ContractClient.call_tool`, `core._validate_output/_upstream_failure/execute_call` | 스키마 누락/형식/참조/dialect/마스킹 불일치·정책 ID, 이미지 시험 미실행 |
| OC-04 판본별 보존 | `output_contract.for_protocol`, `mcp_facade._approved_tools/_render`, `_NullStructuredResult` | 객체/배열/스칼라/null 순수 변환 로컬 통과. SDK runner 직렬화·실제 하네스 미실행 |
| OC-05 기존 승인 전환 | `output_contract.approved_hash/observed_matches`, SQL 추가 열, `registry.review_matches` | 기존 null 승인 유지·새 스키마 자동 승인 없음·오프라인 잠금 비교, 로컬 통과. 기존 운영 DB 전환 미실행 |

자체 MCP 서버·mock MCP는 만들지 않았다. 단위 대역과 소스 확인을 실제 MCP 호출·배포·독립 효과로 세지 않는다. 규모·반복·오탐/미탐·실기기 복구는 이번 로컬 검증 범위에 없다.
