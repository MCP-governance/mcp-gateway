# LIB-A05 · GHSA-6qxp-vccf-f47h (CVE-2026-104850): MCP TypeScript SDK: OAuth client could send credentials to an authorization server chosen by the MCP server

MCP TypeScript SDK의 OAuth 클라이언트가 자격증명을 보낼 인가 서버를 MCP 서버가 고를 수 있었던 취약점 권고다. 1.31.0(sdk)과 2.2.0(client)에서 수정되었다.

## 출처와 확인 수준

- 공식 출처: [GHSA-6qxp-vccf-f47h (CVE-2026-104850): MCP TypeScript SDK: OAuth client could send credentials to an authorization server chosen by the MCP server](https://github.com/advisories/GHSA-6qxp-vccf-f47h)
- 유형: 보고서·권고 · 2026년 · GitHub Advisory Database · `security_advisory`
- 저자·발행: 미상 (GitHub Security Advisory)
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 영향 범위는 @modelcontextprotocol/sdk 1.12.0~1.30.1과 @modelcontextprotocol/client 2.0.0~2.1.0(특정 구성)이다.
- 악성 또는 침해된 MCP 서버가 자기 인가 서버를 지정하면, 사용자 상호작용 없이 저장된 refresh token과 client secret을 넘길 수 있었다.
- CWE-345, CWE-522이며 CVSS v3.1 기준 7.5(High)다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이가 SDK의 OAuth 클라이언트를 쓰면 sdk 1.31.0 이상 또는 client 2.2.0 이상으로 올린다. 자체 OAuth 구현이라면 refresh token과 client secret을 발급 issuer에 바인딩해 다른 인가 서버로 보내지 않게 한다.
- 업스트림 MCP 서버가 지정한 인가 서버 URL은 신뢰하지 않고, 사전에 등록된 issuer 허용 목록과 대조한다.
- 인가 서버 목적지가 바뀌는 이벤트를 감사 원장에 기록하고 토큰 교환 목적지 변경에 알림을 건다(설계 제안).

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

GitHub advisory 페이지 요약을 확인했다. CVE 번호 형식이 드물어 NVD에서 재확인하는 것이 좋다. 검색 결과의 GitLab 영향 범위는 서로 달라 쓰지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
