# LIB-E03 · The OAuth 2.1 Authorization Framework

OAuth 2.0 핵심 명세(RFC 6749)와 Bearer 토큰 사용 명세(RFC 6750)를 하나로 묶어 대체하는 통합 기준 문서다. 현재 revision 16 인터넷 초안이며 아직 RFC로 발행되지 않았다.

## 출처와 확인 수준

- 공식 출처: [The OAuth 2.1 Authorization Framework](https://datatracker.ietf.org/doc/draft-ietf-oauth-v2-1/)
- 유형: 명세·제안 · 2026년 · IETF Internet-Draft · `ietf_internet_draft`
- 저자·발행: D. Hardt, A. Parecki, T. Lodderstedt
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 초록에 RFC 6749와 6750을 대체(obsoletes)한다고 명시되어 있다.
- PKCE는 1.8절에서 요구되지만 4.1.1절에서 7.5.1절 조건을 만족하면 예외가 허용된다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이 설계 문서에서 OAuth 기준 인용을 RFC 6749 대신 이 초안으로 잡되 WIP 표기를 붙이고, RFC 발행 시 갱신한다.
- PKCE 필수 규정(1.8절)과 4.1.1절의 예외 조건(7.5.1절)을 확인해 게이트웨이가 중개하는 인가 코드 흐름의 검사 규칙에 반영한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

rev 16(2026-09-03 날짜) 문서의 앞부분 약 41%만 확인했고, 예외 조건이 있는 7.5.1절은 잘려서 읽지 못했다. 초안이라 변경될 수 있다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
