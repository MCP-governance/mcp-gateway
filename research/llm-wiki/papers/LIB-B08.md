# LIB-B08 · Same Name, Different Server: A Security Census of Silent Drift in the Model Context Protocol Ecosystem

공개 MCP 레지스트리의 서버 버전 이력을 조사해, 같은 등록 ID에서 클라이언트에 알리지 않은 채 광고 내용이나 원격 엔드포인트 호스트가 바뀌는 조용한 표류(silent drift)를 측정한다. 자동 스캐너 결과를 정밀도로 보정하면 고위험 발견의 추정 빈도가 낮아진다고 보고한다.

## 출처와 확인 수준

- 공식 출처: [Same Name, Different Server: A Security Census of Silent Drift in the Model Context Protocol Ecosystem](https://arxiv.org/abs/2609.14119)
- 유형: preprint · 2026년 · arxiv.org · `preprint`
- 저자·발행: Obada Kraishan
- 확인일: 2026-10-14 / `arxiv_api_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 다중 버전 서버 대부분이 릴리스 사이에 광고 내용을 바꿨고, 그중 대부분은 공지가 없었다고 보고한다.
- 조용한 표류가 있는 서버는 고위험 발견과 연관성이 크다고 보고한다.
- 일부 서버는 원격 엔드포인트를 다른 호스트로 옮겼다고 보고한다.

## 우리 솔루션 개발에 사용할 곳

- 계약 변경 탐지에서 광고 내용이 바뀌었는데 공지가 없는 조합을 높은 위험 신호로 두고, 자동 차단 대신 승인 재요청을 띄운다.
- 원격 엔드포인트 호스트 변경을 별도 이벤트로 감시하고, 등록된 도메인 허용 목록을 벗어나면 OAuth 토큰 전달을 막는다.
- 별점과 인기도를 서버 승인 기준에서 빼도록 정책을 정한다. 논문이 인기도는 안전의 약한 지표라고 결론 내리기 때문이다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv 초록 페이지를 열어 확인했고 표본 수집과 스캐너 세부는 읽지 않았다. 단독 저자의 최신 프리프린트(2026-09 제출)라 동료 심사 여부는 확인하지 못했다. 수치는 적지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

arXiv non-exclusive 1.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
