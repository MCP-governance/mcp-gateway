# LIB-K27 · OWASP API Security Top 10 – 2023

API 위험 상위 10개(API1 객체 수준 권한, API2 인증, API3 객체 속성 수준 권한, API4 무제한 리소스 소비, API5 기능 수준 권한, API6 민감한 비즈니스 흐름의 무제한 접근, API7 SSRF, API8 설정 오류, API9 부적절한 자산 관리, API10 안전하지 않은 API 소비)를 설명한다.

## 출처와 확인 수준

- 공식 출처: [OWASP API Security Top 10 – 2023](https://owasp.org/API-Security/editions/2023/en/0x11-t10/)
- 관련 출처: <https://owasp.org/API-Security/editions/2023/en/0xa4-unrestricted-resource-consumption/>
- 관련 출처: <https://github.com/OWASP/API-Security>
- 유형: 지침 · 2023년 · OWASP API Security Project, 2023년판 (공식 사이트는 api-security.owasp.org로 이동) · `official_publication`
- 저자·발행: OWASP API Security Project
- 판본: 2023년판. 요청한 owasp.org 주소가 api-security.owasp.org/editions/2023/로 리디렉션됨(2026-10-17)
- 확인일: 2026-10-17 / `full_text_selected_sections_read` — 원문의 지정 절·조문을 직접 읽었다. 읽은 범위: 2023 위험 목록 페이지, API4:2023 본문 전체(취약 조건·예방), 저장소 LICENSE.
- 요약 검토: 지정한 절을 원문에서 직접 읽고 요약했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- API4:2023은 요청 처리에 대역폭·CPU·메모리·저장소가 들며, 실행 시간 제한, 최대 메모리, 파일 디스크립터·프로세스 수, 업로드 크기, 단일 클라이언트 요청의 작업 수, 한 응답의 페이지당 레코드 수, 외부 서비스 지출 한도 중 하나라도 없거나 부적절하면 취약하다고 정의한다.
- 예방책에는 입력 매개변수·페이로드의 최대 크기, 호출 빈도 제한, 한 작업의 반복 실행 횟수 제한, 반환 레코드 수를 정하는 매개변수의 서버 측 검증, 제공자 지출 한도·알림이 포함된다.
- 목록 페이지에 API7:2023 SSRF(검증 없는 URI 가져오기로 의도치 않은 대상에 요청을 보내게 됨)와 API3(객체 속성 수준 권한)이 있다. 라이선스는 CC BY-SA 4.0이다.

## 메우는 정책50 공백

| 정책 | 공백 |
| --- | --- |
| POL-35 | 대량 조회·호출량 |
| POL-28 | 대량 조회·호출량 |
| POL-10 | 목적지 DNS·서버 outbound |
| POL-25 | 데이터 등급 |

## 우리 솔루션 개발에 사용할 곳

- **POL-35**: '승인되지 않은 대량 조회와 전체 폴더 조회 금지'의 근거다. 도구별 최대 반환 건수·크기를 서버(게이트웨이)가 검증하고, 요청이 건수 매개변수를 키우거나 페이지 크기를 바꿔도 상한을 넘지 못하게 하는 시험을 둔다(DEV-41).
- **POL-28**: 호출 빈도·동시 실행·실행 시간·외부 서비스 지출 한도를 API4 항목 목록과 대조해 빠진 한도를 식별한다.
- **POL-10·POL-25**: API7 SSRF를 POL-10 시험의 위험 근거로, API1·API3의 객체·속성 수준 권한을 POL-25의 자산·필드 단위 검사 근거로 연결한다(API1·API3 본문은 읽지 않았다).

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다. 이 자료를 읽었다는 사실이 해당 정책의 구현·검수 완료를 뜻하지 않는다.

## 한계와 사용 조건

목록 페이지와 API4:2023 전체 본문만 읽었다. API1·API3·API6·API7의 본문은 읽지 않았다. MCP·LLM 도구 호출에 특화되지 않은 일반 웹 API 지침이다.

CC BY-SA 4.0 (OWASP/API-Security 저장소 LICENSE 파일). 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[검증 기록](../analysis/evidence/references/policy50-gap-fill-2026-10-17.json) · [정책50 공백 지도](policy50-gap-references.md) · [자료 확보 규칙](../methodology/source-protocol.md)
