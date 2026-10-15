# LIB-E08 · RFC 7591: Dynamic Client Registration Protocol (OAuth 2.0)

클라이언트가 인가 서버에 프로그래밍 방식으로 등록하고 client_id를 받는 프로토콜과 공통 메타데이터 필드(redirect URI, 표시 이름 등)를 정의한다. 메타데이터는 직접 제시하거나 서명된 software statement 안에 담아 전달할 수 있다.

## 출처와 확인 수준

- 공식 출처: [RFC 7591: Dynamic Client Registration Protocol (OAuth 2.0)](https://www.rfc-editor.org/rfc/rfc7591)
- 유형: RFC · 2015년 · IETF RFC · `ietf_rfc`
- 저자·발행: J. Richer (Ed.), M. Jones, J. Bradley, M. Machulak, P. Hunt
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 클라이언트 메타데이터를 서명된 software statement로 전달해 등록 내용의 출처를 검증할 수 있게 한다.
- 등록은 클라이언트가 직접 하거나 개발자가 대신 할 수 있다고 정의한다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이가 하네스의 동적 등록을 받을 경우 software statement를 요구하고 그 발급자를 신뢰 목록으로 제한해, 아무 클라이언트나 등록되지 않게 한다.
- 등록 요청의 redirect_uris는 게이트웨이 허용 목록과 대조해, 허용되지 않은 콜백 주소를 거부한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

본문 약 98%까지 요약을 받았고 software statement 검증 세부는 읽지 않았다. 2015년 규격이라 최근 대안(예: CIMD)과의 비교는 포함하지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
