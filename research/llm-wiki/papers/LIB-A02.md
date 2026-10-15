# LIB-A02 · RFC 8707: Resource Indicators for OAuth 2.0

OAuth 요청에 resource 파라미터를 넣어 토큰이 쓰일 대상 리소스를 지정하고, 인가 서버가 토큰 audience를 그 리소스로 제한하도록 하는 표준이다. 다른 리소스용 토큰을 잘못 쓰는 상황을 줄이는 것이 목적이다.

## 출처와 확인 수준

- 공식 출처: [RFC 8707: Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- 유형: RFC · 2020년 · IETF RFC (Proposed Standard) · `ietf_rfc`
- 저자·발행: B. Campbell, J. Bradley, H. Tschofenig
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- resource 파라미터로 클라이언트가 토큰의 대상 리소스를 명시하고, AS는 그 값으로 audience를 제한할 수 있다.
- resource 값이 없거나 알 수 없거나 형식이 잘못된 경우를 위해 invalid_target 오류 코드를 정의한다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이가 업스트림 MCP 서버용 토큰을 받을 때 resource에 해당 서버 식별자를 명시하고, 받은 토큰의 audience가 그 서버와 일치하는지 확인한다. 이렇게 하면 토큰 passthrough와 다른 서버 토큰 재사용을 막을 수 있다.
- 게이트웨이 자신이 보호 리소스일 때 들어온 토큰의 audience가 게이트웨이 식별자와 같은지 검사하고, 다르면 401로 거부한다.
- resource 값이 허용 목록에 없거나 invalid_target 오류가 나면 감사 원장에 기록하고 테스트 케이스로 남긴다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

RFC 본문 전체가 아니라 페이지 요약 도구로 정의 요지만 확인했다. 발행월은 페이지에 없어 저작권 연도 2020을 기재했다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
