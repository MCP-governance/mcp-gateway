# LIB-A13 · RFC 9207: OAuth 2.0 Authorization Server Issuer Identification

인가 응답(오류 응답 포함)에 발급 서버 식별자 iss를 넣고, 클라이언트가 이를 기대 값과 비교해 불일치하면 거부하도록 하는 방식을 정의한다. 공격자가 클라이언트의 코드나 토큰을 엉뚱한 서버로 보내게 하는 mix-up 공격을 막는 것이 목적이다.

## 출처와 확인 수준

- 공식 출처: [RFC 9207: OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207)
- 유형: RFC · 2022년 · IETF RFC (Proposed Standard) · `ietf_rfc`
- 저자·발행: K. Meyer zu Selhausen, D. Fett
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- iss는 인가 응답과 오류 응답 모두에 포함되며, 클라이언트는 기대하는 발급자 식별자와 비교한다.
- 불일치하는 응답은 거부해야 하며, 이는 mix-up 공격을 막는 장치다.
- 공격자 통제 인가 서버가 코드나 토큰을 다른 쪽으로 보내게 하는 위험을 정의한다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이가 OAuth 클라이언트로 동작할 때 인가 응답의 iss를 검증하고, 불일치하면 코드 교환을 중단한다. SEP-2468 구현의 근거가 된다.
- 게이트웨이가 인가 서버 역할도 할 경우 응답에 iss를 넣고 메타데이터에 지원 여부를 광고한다.
- 다중 인가 서버 환경의 보안 테스트에 mix-up 시나리오를 포함한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

RFC 본문 전체가 아니라 페이지 요약 도구로 정의 요지만 확인했다. 발행월은 페이지에 없어 저작권 연도 2022를 기재했다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
