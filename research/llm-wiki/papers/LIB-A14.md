# LIB-A14 · GHSA-345p-7cg4-v4c7 (CVE-2026-25536): @modelcontextprotocol/sdk has cross-client data leak via shared server/transport instance reuse

하나의 SDK 서버나 transport 인스턴스를 여러 클라이언트가 공유하면 응답과 서버 발신 요청이 엉뚱한 클라이언트로 라우팅될 수 있었던 교차 클라이언트 데이터 누출 취약점 권고다. 1.26.0에서 수정되었다.

## 출처와 확인 수준

- 공식 출처: [GHSA-345p-7cg4-v4c7 (CVE-2026-25536): @modelcontextprotocol/sdk has cross-client data leak via shared server/transport instance reuse](https://github.com/advisories/GHSA-345p-7cg4-v4c7)
- 유형: 보고서·권고 · 2026년 · GitHub Advisory Database · `security_advisory`
- 저자·발행: 미상 (GitHub Security Advisory)
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 하나의 StreamableHTTPServerTransport를 여러 클라이언트가 쓰면 같은 JSON-RPC id가 서로 덮어써져 응답이 잘못된 클라이언트로 갈 수 있다.
- 하나의 McpServer나 Server를 여러 transport에 연결하면 transport 참조가 덮어써져 알림과 샘플링, elicitation 요청이 잘못 라우팅된다.
- 1.26.0은 잘못된 라우팅 대신 오류를 던지는 런타임 가드를 추가했고, 우회책은 요청이나 세션마다 새 인스턴스를 만드는 것이다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이는 클라이언트나 세션마다 server와 transport 인스턴스를 분리해 만들고, 인스턴스 공유를 금지하는 것을 아키텍처 원칙으로 둔다.
- 여러 세션을 동시에 처리하는 부하 테스트에 JSON-RPC id 충돌로 응답이 다른 세션에 가는지 확인하는 교차 세션 테스트를 넣는다.
- SDK를 1.26.0 이상으로 올리고, SDK가 던지는 가드 오류를 게이트웨이 경보와 연결한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

GHSA 페이지 요약을 확인했다. 영향 버전은 1.10.0~1.25.3이며, 검색 결과와 교차 확인은 하지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
