# DEV-54·55 — 단일 조회 상한과 완료 변경의 재전송 차단

시작 코드 `fd904c24250b6029061283bb8a57fa4efe0b5b17`, 로컬 브랜치 `10/18-response-cap`.
요청 이름 `10/18-response-cap-idempotency` 생성은 공유 Git 디렉터리 쓰기 거부로 미완료다.
실제 작업일은 2026-10-18이며 보고서 파일의 10-17 날짜는 요청한 인계 경로다.

[D-125·126 정본](../../../../docs/ai/DECISIONS.md) · [원자 요구와 코드 지문](requirements.json) ·
[작업 보고·실행 명령](../../status/reports/2026-10-17-response-cap-idempotency.md).

## 영향 범위

- `classify.py`: 기존 pglast 파서 재사용, 전체 선택자·요청 건수 검사와 응답 건수 측정.
- `core.py`: 승인 스키마 뒤 사전 거부, 원문·마스킹 후 상한, 예약에서 완료 변경 이력 조회, 최종 중복 거부 변환.
- `dispatch.py`: 기존 intent와 주체별 잠금을 재사용한 최종 재전송 방지. 승인 소비와 서버/주체/lease 재검증 유지.
- `v2_tables.sql`: 기존 intent 조회 인덱스 하나. 행 삭제·감사 원장 변경 없음.
- OPA 규칙 문구·관리대장, 기존 DB/Gitea 시험과 공통 준비 코드, 새 오프라인 시험, 정책·데이터·검증 문서와 DEV-54·55 백로그.
  `upstream.py`·`destination.py`·계약 잠금·하네스 신원·토큰 전달·종료 판정 기준은 변경하지 않았다.

## 근거와 재사용 결정

| 자료 | 이번에 확인한 범위 | 적용·한계 |
| --- | --- | --- |
| [OWASP API4:2023](https://api-security.owasp.org/editions/2023/en/0xa4-unrestricted-resource-consumption/) | 공식 본문의 자원·한 응답 레코드 수 제한 | 페이지 크기·결과 건수/바이트 검사. 원격 서버의 자원 예산까지 보장하지 않는다 |
| [OWASP API3:2023](https://api-security.owasp.org/editions/2023/en/0xa3-broken-object-property-level-authorization/) | 공식 본문의 필요한 응답 속성 선택·스키마 검사 | 전체 응답을 무제한 공개하지 않는 근거. 필드별 인가는 이번 범위 밖 |
| [IETF 초안 -07 §2.2~2.7](https://www.ietf.org/archive/id/draft-ietf-httpapi-idempotency-key-header-07.txt) | 키·요청 지문·완료/진행 중 재전송·기한 정책 | fingerprint와 명시적 보존 기간만 적용. RFC가 아니며 결과 재생/HTTP 헤더 호환을 구현하지 않는다 |
| [MCP Python SDK v2.2.0](https://github.com/modelcontextprotocol/python-sdk/tree/v2.2.0) | 기존 [고정 소스 분석](../oss-deep/deps-sdk-authlib-opa.md) 재사용, 로컬 HEAD `9972c21aa42054fb1450c5fc614761ed11847ec6`·MIT LICENSE 재확인 | 기존 `mcp==2.2.0`만 사용. 새 SDK·MCP 서버를 만들지 않는다. 현재 유지보수 지원 기간은 미확인 |
| [anthropics/skills 검색 결과](https://github.com/anthropics/skills/blob/main/skills/claude-api/shared/managed-agents-api-reference.md) | 공개 스킬 후보의 검색 요약: 관리 에이전트 API 페이지 처리 | MCP/DB 멱등 정책에 직접 적용하지 않아 미채택. 커밋·라이선스는 미확인(API 조회 불가·LICENSE 주소 404). 외부 스크립트 실행·설치 없음 |

기존 [LIB-K26](../../papers/LIB-K26.md)·[LIB-K27](../../papers/LIB-K27.md)의 후보 상태를 보존하고 이 구현으로 연결한다.
OWASP·IETF 본문을 재배포하지 않고 자체 요약과 URL만 둔다. 기존 Gitea 프로젝트 MCP `1.7.0`·Gitea `1.27.3-rootless`와
실제 PostgreSQL/OPA/Presidio를 사용하는 격리 시험 설비를 확장했으며, 이 판본 이미지의 digest·라이선스·실행 효과 재확인은 메인 검수 대상이다.

## 동작과 한계

기본 상한은 전체 UTF-8 JSON 262144바이트와 1000건이다. structured의 중첩 배열 합과 text 표현의 JSON 배열 합/비어 있지 않은 줄 수,
content 블록 수 중 큰 값을 사용한다. 여러 text 블록은 합산하며 text/structured에 같은 결과를 중복 표현하면 표현별로 제한한다.
중첩 배열은 업무 행보다 보수적으로 많이 센다. 한 줄 평문·인코딩된 데이터는 의미상 레코드 수를 알 수 없으며 바이트 상한이 남는다.
SDK 수신 후 검사이므로 수신 버퍼·원격 SQL 처리량을 제한하는 기능은 아니다. 바이트/건수 초과는 응답을 전부 보류하고 정상 결과로 절단하지 않는다.

사전 차단은 지원 중인 파일/키 선택자와 고정 SQL LIMIT, 일반적인 건수 매개변수에 한정한다. 새 OSS 도구의 독자적인 선택자·필터 문법은
별도 매핑·정상/음성 회귀가 필요하다. SQL의 외부 함수·집계 값 안에 대량 데이터를 넣는 것은 LIMIT만으로 제어하지 못하므로 응답 상한도 적용한다.

멱등성 범위는 transport 주체별 canonical `(server, tool, arguments)` 지문이다. 완료 쓰기는 기본 24시간 차단하고 읽기는 완료 이력으로 막지 않는다.
실행 중/미확인 쓰기는 기간과 무관하게 관리자 확인까지 차단한다. 같은 업무를 다른 인자/주체로 보낸 경우나 보존 기간 뒤의 재시도는 중복으로 알 수 없다.
이것은 제한된 재전송 방지이며 분산 시스템의 exactly-once 보장이 아니다. 고의적인 동일 쓰기 반복도 기간 중 차단된다는 사용 변화가 있다.

## 검증 상태

오프라인 제품 함수 10개, 기존 경계 회귀 16개·세션 회귀 40개, 콘솔 상태 15개, JS 문법·무인증 경로 검사는 통과했다.
native pglast 문법·실제 암호 라이브러리로 격리 fixture 확인 각 1개, pyflakes, OPA, 실제 DB·Gitea·모델/하네스·배포는 미검증이다.
기존 운영·폐기 함수 회귀 23개도 대역 환경에서 통과했다. Python 3.10 오프라인 출력 검사 시험은
기한 컨텍스트를 대역으로 치환하며 실제 timeout 동작을 검증하지 않는다. 전체 위키 검사의 기존 누락 원문과 파생 매핑 상태는 작업 보고를 따른다.
