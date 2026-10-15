# LIB-E09 · RFC 7523: JSON Web Token (JWT) Profile for OAuth 2.0 Client Authentication and Authorization Grants

기존 신뢰 관계가 있을 때 JWT 베어러 어설션으로 액세스 토큰을 요청하는 방식과, 클라이언트 인증에 JWT를 자격 증명으로 쓰는 방식을 정의한다. 인가 서버가 적용해야 할 JWT 검증 규칙도 함께 규정한다.

## 출처와 확인 수준

- 공식 출처: [RFC 7523: JSON Web Token (JWT) Profile for OAuth 2.0 Client Authentication and Authorization Grants](https://www.rfc-editor.org/rfc/rfc7523)
- 유형: RFC · 2015년 · IETF RFC · `ietf_rfc`
- 저자·발행: M. Jones, B. Campbell, C. Mortimore
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- JWT 베어러 어설션이 기존 신뢰 관계 아래에서 사용자 승인 단계 없이 액세스 토큰을 얻는 근거가 될 수 있다고 정의한다.
- JWT로 클라이언트를 인증하는 방식과 인가 서버가 지켜야 할 검증 규칙을 함께 규정한다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이가 상위 인가 서버에 자기 자신을 증명할 때 클라이언트 비밀 대신 짧은 수명의 서명 JWT 어설션을 쓰고, 이 규격의 검증 규칙을 게이트웨이 어설션 검증기의 체크리스트로 삼는다.
- SPIFFE 기반 클라이언트 인증 초안과 ID-JAG 초안이 모두 이 규격을 기반으로 하므로, 어설션 검증 모듈을 하나로 공통화할 수 있다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

요약 수준만 확인했다. 2015년 5월 규격이며 에이전트 특화 규정은 포함하지 않는다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
