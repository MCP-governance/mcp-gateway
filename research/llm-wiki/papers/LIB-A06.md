# LIB-A06 · SEP-2260: Require Server requests to be associated with a Client request.

roots/list, sampling/createMessage, elicitation/create 같은 서버 발신 요청을 원인이 되는 클라이언트 요청과 연결된 경우에만 허용하도록 규정한 SEP다. 독립 스트림에서 서버가 임의로 보내는 요청은 금지된다.

## 출처와 확인 수준

- 공식 출처: [SEP-2260: Require Server requests to be associated with a Client request.](https://modelcontextprotocol.io/seps/2260)
- 유형: 명세·제안 · 2026년 · MCP SEP (Final, Standards Track) · `mcp_sep`
- 저자·발행: MCP Transports Working Group (sponsor: Caitie McCaffrey)
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 이 세 가지 서버 발신 요청은 클라이언트 요청 맥락 안에서만 허용되며, 독립 스트림에서 보내는 것은 금지(MUST NOT)된다. ping은 예외다.
- GitHub 조사에서 기존 구현 대부분이 이미 이 패턴을 따르고 있었고, 예외는 한 저장소뿐이었다.
- 클라이언트는 연결된 요청이 없는 서버 요청에 -32602(Invalid Params)로 응답하도록 권장된다(SHOULD).

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이 라우팅에서 서버 발신 요청을 진행 중인 tools/call, resources/read, prompts/get과 연결하고, 연결되지 않은 요청은 차단한 뒤 감사 원장에 기록한다.
- 연결되지 않은 서버 요청에 -32602로 응답하라는 SEP 권고를 게이트웨이의 거부 응답 규칙으로 재사용한다.
- 사람 입력을 기다리는 시간이 길어질 수 있으므로 게이트웨이와 로드밸런서의 타임아웃, SSE keepalive 설정을 배포 점검 항목에 넣는다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

SEP 본문 전체를 확인했다. Final 상태이며 현행 스펙에 그대로 반영되었는지는 확인하지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
