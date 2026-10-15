# LIB-E07 · OAuth Client ID Metadata Document

클라이언트가 사전 등록 없이 자신을 식별하도록 client_id를 HTTPS URL로 두고, 그 URL이 메타데이터 JSON을 제공하는 방식을 정의한다. 인가 서버는 이 문서를 필요할 때 가져와 캐싱하며, 자격 증명 제한과 SSRF 방어 규칙을 따라야 한다.

## 출처와 확인 수준

- 공식 출처: [OAuth Client ID Metadata Document](https://datatracker.ietf.org/doc/draft-ietf-oauth-client-id-metadata-document/)
- 유형: 명세·제안 · 2026년 · IETF Internet-Draft · `ietf_internet_draft`
- 저자·발행: A. Parecki, E. Smith
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- client_id 자체가 HTTPS URL이며, 그 URL이 클라이언트 메타데이터를 제공한다.
- 인가 서버는 메타데이터를 가져올 때 자격 증명 제한과 SSRF 보호를 지켜야 한다고 명시한다.

## 우리 솔루션 개발에 사용할 곳

- 하네스 클라이언트가 동적 등록 없이 접속하는 경로를 열 경우, 게이트웨이의 메타데이터 가져오기는 내부망 주소와 리다이렉트를 차단하는 SSRF 안전 페처로 구현하고 허용 도메인 목록을 둔다.
- CIMD로 받은 redirect_uri 등 메타데이터를 게이트웨이 정책 입력으로 써서, 등록되지 않은 콜백 주소를 거부한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

rev 02(2026-07-06) 요약만 확인했고 본문은 정독하지 않았다. 아직 RFC가 아니며, MCP 측 채택 여부는 확인하지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
