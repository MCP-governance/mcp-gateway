# LIB-A09 · GHSA-6xpm-ggf7-wc3p (CVE-2025-6514): mcp-remote exposed to OS command injection via untrusted MCP server connections

mcp-remote가 신뢰되지 않은 MCP 서버에 연결할 때, 서버가 돌려준 OAuth authorization_endpoint 값이 OS 명령 주입으로 이어지는 취약점 권고다. 0.1.16에서 수정되었다.

## 출처와 확인 수준

- 공식 출처: [GHSA-6xpm-ggf7-wc3p (CVE-2025-6514): mcp-remote exposed to OS command injection via untrusted MCP server connections](https://github.com/advisories/GHSA-6xpm-ggf7-wc3p)
- 유형: 보고서·권고 · 2025년 · GitHub Advisory Database · `security_advisory`
- 저자·발행: 미상 (GitHub Security Advisory)
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 영향 범위는 mcp-remote 0.0.5 이상 0.1.16 미만이다.
- 공격 입력은 신뢰되지 않은 MCP 서버가 OAuth 흐름에서 돌려준 authorization_endpoint 응답 URL이다.
- CWE-78(OS 명령 주입)이며 CVSS v3.1 기준 9.6(Critical)이다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이가 업스트림 MCP 서버의 OAuth 메타데이터를 받을 때, OS 호출 전에 URL 스킴과 형식을 검증하고 셸을 거치는 실행을 금지한다(설계 제안).
- 게이트웨이 정책으로 연결 대상 MCP 서버를 허용 목록으로 통제해, 신뢰되지 않은 서버에 개발자 PC가 직접 연결되지 않게 한다.
- 사내 개발자 PC에 설치된 mcp-remote 버전을 점검하는 항목을 게이트웨이 도입 체크리스트에 넣는다(0.1.16 이상).

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

GHSA 페이지 요약 기준이다. 실제 호출되는 OS 함수(sink)는 페이지에 명시되어 있지 않아 확인하지 못했다. 검색 결과의 NVD 상태와 EPSS 수치는 서로 달라 쓰지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
