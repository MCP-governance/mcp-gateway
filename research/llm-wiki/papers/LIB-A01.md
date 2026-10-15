# LIB-A01 · SEP-2468: Recommend Issuer (iss) Parameter in MCP Auth Responses

MCP 인가 응답에 RFC 9207의 iss 파라미터를 권장하고, 클라이언트가 받은 iss를 기대 발급자와 비교해 불일치하면 인가 흐름을 중단하도록 규정한 SEP다. 다중 IdP 환경에서 mix-up 공격을 MCP 수준에서 막기 위한 근거를 정리한다.

## 출처와 확인 수준

- 공식 출처: [SEP-2468: Recommend Issuer (iss) Parameter in MCP Auth Responses](https://modelcontextprotocol.io/seps/2468)
- 유형: 명세·제안 · 2026년 · MCP SEP (Final, Standards Track) · `mcp_sep`
- 저자·발행: Emily Lauber (sponsor: @pcarleton)
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 클라이언트는 응답에 iss가 있으면 반드시 검증(MUST)하고, 불일치 시 응답을 무효로 보고 흐름을 중단해야 한다.
- AS는 iss를 권장(SHOULD)하며, 지원 여부를 메타데이터에 광고해야 한다.
- iss 부재 시 거부 여부는 AS 광고 여부에 따라 달라지도록 설계되었다. 광고하지 않는 AS는 영향을 받지 않는다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이 OAuth 콜백 핸들러에서 iss를 추출하고, 인가 요청 전에 기록해 둔 기대 발급자와 정확 문자열로 비교한다. 불일치하면 코드 교환을 중단하고 감사 원장에 기록한다.
- AS가 authorization_response_iss_parameter_supported를 광고하면 iss가 없는 응답도 거부하는 정책을 적용한다. SEP 레퍼런스 구현도 같은 방식이다.
- SDK 콜백 시그니처를 확장할 때 기존 호출부 호환을 위해 optional iss 인자를 추가하라는 SEP 권고를 게이트웨이 어댑터에도 그대로 적용한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

SEP 페이지 본문 전체를 확인했다. Final 상태이며 이후 개정은 반영되지 않는다. 링크된 Go·TypeScript SDK 구현 PR은 열어보지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
