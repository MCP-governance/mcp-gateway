# LIB-G06 · Exposed by Design: A Dynamic Security Assessment of Internet-Facing MCP Servers at Scale

공개 인터넷에 노출된 MCP 서버 인스턴스를 탐지하고 확인된 운영 서버 일부를 동적으로 점검해 취약점과 인증 누락을 측정한다. 원격 MCP 서버가 로컬 stdio용으로 설계된 프로토콜에 HTTP를 얹으면서 보안 기본값이 따라오지 못했다고 주장한다.

## 출처와 확인 수준

- 공식 출처: [Exposed by Design: A Dynamic Security Assessment of Internet-Facing MCP Servers at Scale](https://arxiv.org/abs/2608.00150)
- 유형: preprint · 2026년 · arXiv preprint · `preprint`
- 저자·발행: Nicolás Padilla
- 확인일: 2026-10-14 / `arxiv_api_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 약 2만 1천 개의 MCP 서버 인스턴스가 공개 인터넷에서 탐지되었고, 운영 서버 640개가 확인되었다.
- 동적 감사를 받은 서버의 91.8%에 OAuth 인증이 없었고, 확인된 서버들의 도구 687개가 접근 제어 없이 셸 실행을 노출했다.
- SQL 주입, 클라우드 메타데이터 대상 SSRF, 프롬프트 템플릿 주입, 경로 순회 등 68건의 보고 가능한 취약점이 확인되었다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이를 거치지 않고 외부에 노출된 MCP 엔드포인트를 주기적으로 찾아 게이트웨이 경유 강제 정책과 대조하는 인벤토리 점검을 둔다.
- SQL 주입, 클라우드 메타데이터 SSRF, 경로 순회, 셸 실행 도구 접근 제어를 게이트웨이 서버 심사 체크리스트와 회귀 테스트에 포함한다.
- 측정 대상의 상당수가 며칠 안에 사라졌으므로, 한 번의 점검 결과를 영구 상태로 보지 않고 주기적으로 재점검한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

단독 저자(독립 연구자)의 2026년 7월 프리프린트로 동료 심사를 거치지 않았다. WebFetch로 확인한 초록 수치만 반영했고 전문은 읽지 않았다. 공개 인터넷 탐지의 윤리·법적 측면은 확인하지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

CC BY 4.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
