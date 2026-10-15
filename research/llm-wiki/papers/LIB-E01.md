# LIB-E01 · RFC 9068: JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens

OAuth 2.0 액세스 토큰을 JWT 형식으로 발급할 때의 표준 레이아웃을 정의해 서로 다른 벤더의 인가 서버와 리소스 서버가 상호운용되도록 한다. 필수 클레임(iss, exp, aud, sub, client_id, iat, jti)과 JWT 헤더의 typ 값(at+jwt)을 규정한다.

## 출처와 확인 수준

- 공식 출처: [RFC 9068: JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- 유형: RFC · 2021년 · IETF RFC · `ietf_rfc`
- 저자·발행: V. Bertocci
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 리소스 서버는 aud에 자신의 리소스 식별자가 없는 토큰을 거부해야 한다고 요구한다.
- client_id와 sub가 모두 필수 클레임이라 클라이언트와 주체를 토큰 안에서 함께 기록할 수 있다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이 토큰 검증기는 typ=at+jwt 헤더와 필수 클레임 존재 여부를 먼저 확인하고, ID 토큰을 액세스 토큰으로 받지 않도록 거부한다.
- aud에 게이트웨이의 정식 리소스 식별자가 없으면 거부하는 규칙을 두고, 거부 사유를 감사 원장에 함께 남긴다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

데이터 요약 도구가 가져온 본문 요약만 확인했고, 검증 절차의 세부 조항은 직접 정독하지 않았다. 발행 월은 페이지에 없어 연도만 기록했다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
