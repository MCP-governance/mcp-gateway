# LIB-A03 · RFC 9728: OAuth 2.0 Protected Resource Metadata

보호 리소스가 인가 서버 목록, 스코프, 토큰 전달 방식 등을 JSON 메타데이터로 well-known 경로에 게시하는 형식을 정의한다. 클라이언트는 WWW-Authenticate 헤더나 well-known 경로로 이 메타데이터를 찾아 인가 서버를 발견한다.

## 출처와 확인 수준

- 공식 출처: [RFC 9728: OAuth 2.0 Protected Resource Metadata](https://www.rfc-editor.org/rfc/rfc9728)
- 유형: RFC · 2025년 · IETF RFC (Proposed Standard) · `ietf_rfc`
- 저자·발행: M.B. Jones, P. Hunt, A. Parecki
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 메타데이터는 리소스 식별자에서 파생된 well-known URL에 JSON으로 게시한다.
- 클라이언트는 WWW-Authenticate 헤더로 메타데이터 위치를 알게 되며, 메타데이터가 임퍼소네이션에 쓰이지 않도록 검증 방법을 규정한다.
- 리소스는 메타데이터를 서명된 JWT로도 제공할 수 있다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이를 보호 리소스로 보고 /.well-known/oauth-protected-resource에 authorization_servers, scopes_supported 등을 게시해 클라이언트가 인가 서버를 자동으로 찾게 한다.
- 토큰 없는 요청에 대한 401 응답의 WWW-Authenticate 헤더에 메타데이터 URL을 넣는 미들웨어를 구현한다.
- 메타데이터 위변조가 걱정되는 배포라면 JWT로 서명된 메타데이터 제공 옵션을 검토한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

RFC 본문 전체가 아니라 페이지 요약 도구로 정의 요지만 확인했다. 발행월은 페이지에 없어 저작권 연도 2025를 기재했다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
