# LIB-J01 · RFC 9943: An Architecture for Trustworthy and Transparent Digital Supply Chains

공급원이 발행한 단일 발행자 서명 statement를 투명성 서비스가 등록 정책에 따라 검사하고, append-only 검증 가능 자료구조에 기록한 뒤 receipt를 돌려주는 SCITT 아키텍처를 정의한다. 기본 메시지 형식은 CBOR과 COSE 기반이다.

## 출처와 확인 수준

- 공식 출처: [RFC 9943: An Architecture for Trustworthy and Transparent Digital Supply Chains](https://www.rfc-editor.org/rfc/rfc9943)
- 유형: RFC · 2026년 · IETF RFC 9943 (Proposed Standard, SCITT 아키텍처) · `ietf_rfc`
- 저자·발행: H. Birkholz, A. Delignat-Lavaud, C. Fournet, Y. Deshpande, S. Lasker
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 기록된 statement는 append-only 구조에 들어가고, 등록 사실은 receipt로 증명할 수 있다는 구조를 명세가 정의한다(rfc-editor 페이지 요약에서 확인).
- 문서 상태는 Proposed Standard이며 발행 연도는 2026으로 표기된다(페이지 확인).

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이가 MCP 서버 매니페스트와 승인된 도구 계약(스키마)에 대한 승인 기록을 COSE 서명 statement로 만들어 투명성 서비스에 등록하고, 받은 receipt를 감사 원장과 함께 보관하면 현재 계약이 승인된 계약과 같은지를 제3자가 검증할 수 있다.
- 발행자(MCP 서버 개발사)의 서명과 게이트웨이의 등록 기록을 역할 분리하는 설계의 표준 근거로 쓸 수 있다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

rfc-editor 페이지의 발행 요약만 확인했고 전문은 정독하지 않았다. 구현 예시와 성능 관련 내용은 확인하지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
