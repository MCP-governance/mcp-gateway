# LIB-E04 · Identity Assertion JWT Authorization Grant

앱이 제3자 API의 액세스 토큰을 얻을 때 먼저 기업 신원 제공자(IdP)로부터 서명된 ID-JAG 어설션을 받아 인가 서버에 제시하는 방식을 정의한다. RFC 8693 토큰 교환과 RFC 7523 JWT 승인 부여를 기반으로 하며 통칭은 교차 앱 접근(XAA)이다.

## 출처와 확인 수준

- 공식 출처: [Identity Assertion JWT Authorization Grant](https://datatracker.ietf.org/doc/draft-ietf-oauth-identity-assertion-authz-grant/)
- 유형: 명세·제안 · 2026년 · IETF Internet-Draft · `ietf_internet_draft`
- 저자·발행: A. Parecki, K. McGuinness, B. Campbell
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 관리자(IdP)가 어떤 앱이 어떤 리소스에 접근할 수 있는지 결정하는 구조를 취한다.
- RFC 8693과 RFC 7523을 조합해 기존 토큰 교환 체계와 호환되도록 설계됐다.

## 우리 솔루션 개발에 사용할 곳

- 하네스가 사내 SaaS MCP 서버에 접근할 때 사용자별 동의 대신 IdP가 발급한 ID-JAG 존재를 게이트웨이 정책의 필수 조건으로 두면, 관리자가 앱 간 접근을 중앙에서 통제할 수 있다.
- ID-JAG의 발급자, 대상, 주체 클레임을 OPA 입력으로 넘겨 허용된 앱과 리소스 조합만 통과시키는 규칙을 작성한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

rev 04(2026-05-21) 문서의 앞부분 약 69%까지의 요약만 확인했다. 만료 예정일은 2026-11-22이고 의도된 RFC 상태는 미정이다. ID-JAG 클레임 세부는 읽지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
