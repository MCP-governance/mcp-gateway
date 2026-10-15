# LIB-A07 · SEP-1036: URL Mode Elicitation for secure out-of-band interactions

elicitation에 url 모드를 추가해, 자격증명 수집·3자 OAuth·결제처럼 MCP 클라이언트를 거치면 안 되는 민감한 상호작용을 사용자 브라우저로 넘기는 방식을 정의한다. 클라이언트는 민감 데이터를 보지 않고 사용자에게 URL의 맥락만 제공한다.

## 출처와 확인 수준

- 공식 출처: [SEP-1036: URL Mode Elicitation for secure out-of-band interactions](https://modelcontextprotocol.io/seps/1036)
- 유형: 명세·제안 · 2025년 · MCP SEP (Final, Standards Track) · `mcp_sep`
- 저자·발행: Nate Barbettini, Wils Dawson
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- URL은 url 모드에서만 허용되며, 폼 모드에서 URL을 쓰는 것은 금지되어 클라이언트가 URL을 하이퍼링크로 그리지 않도록 할 근거가 된다.
- 서버는 세션에 바인딩하고 시작과 종료 시점에 사용자 신원을 확인해야 하며, 클라이언트는 완료 알림을 무기한 기다리면 안 된다.
- 실패한 요청에 URLElicitationRequiredError(-32042)를 돌려줄 수 있고, 이는 elicitation/create와 동등하게 취급된다.

## 우리 솔루션 개발에 사용할 곳

- 자격증명·결제·3자 OAuth가 필요한 도구는 폼 모드 대신 URL 모드로 우회시키는 정책 규칙을 둔다. 폼 모드 응답에 URL이 들어오면 차단한다.
- URL 모드 응답 accept는 사용자 동의로 보고 감사 원장에 남긴다. 완료 여부는 elicitationId로 게이트웨이가 자체 추적하고, 완료 알림이 오지 않을 때를 대비해 수동 재개 UI를 둔다.
- URL은 HTTPS만 허용하고 SSRF 검사와 대상 도메인 표시를 게이트웨이 렌더링 정책에 반영한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

SEP 본문 전체를 확인했다. Final 상태이며, 2026-07-28 개정에서 완료 알림이 제거되었다는 2차 자료가 있으나 공식 changelog는 확인하지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
