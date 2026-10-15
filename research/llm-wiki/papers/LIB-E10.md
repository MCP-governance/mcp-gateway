# LIB-E10 · OAuth SPIFFE Client Authentication

SPIFFE의 워크로드 신원(SVID)을 OAuth 클라이언트 자격 증명으로 쓰는 방법을 정의한다. JWT-SVID는 RFC 7523 어설션으로, X.509-SVID는 RFC 8705 상호 TLS 인증으로 제시하며, 인가 서버가 클라이언트 비밀 없이 신뢰 도메인 키로 검증한다.

## 출처와 확인 수준

- 공식 출처: [OAuth SPIFFE Client Authentication](https://datatracker.ietf.org/doc/draft-ietf-oauth-spiffe-client-auth/)
- 유형: 명세·제안 · 2026년 · IETF Internet-Draft · `ietf_internet_draft`
- 저자·발행: A. Schwenkschuster, P. Kasselman, S. Rose, S. Thorgersen, N. Cam-Winget
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- JWT-SVID의 sub 클레임에 SPIFFE ID를 넣어 등록된 클라이언트와 대응시키는 방식을 정의한다.
- 검증 키는 신뢰 도메인의 번들에서 가져오며 클라이언트 비밀은 필요 없다고 규정한다.

## 우리 솔루션 개발에 사용할 곳

- 하네스 워크로드가 SPIFFE ID를 가지면 게이트웨이 등록 클라이언트를 SPIFFE ID에 매핑해 공유 클라이언트 비밀을 없애고, OPA 정책 입력에 워크로드 신원을 넣는다.
- X.509-SVID 경로에서는 게이트웨이 TLS 종단이 URI SAN을 정확히 하나만 갖는지 검사하는 로직을 추가한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

rev 02(2026-06-15) 요약만 확인했다. 워킹그룹 초안이라 RFC 상태는 미정이다. SPIFFE 원 명세(spiffe.io, GitHub)는 열지 않아 SVID 정의는 초안 요약에 의존한다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
