# LIB-G08 · Characterizing Network Centralization and Observability in the Remote MCP Ecosystem

두 공개 레지스트리에서 층화 추출한 원격 MCP 엔드포인트 179개의 호스팅 집중도, 인증 방식, 관측 가능성을 측정한다. 인증 방식은 운영자 설정보다 호스팅 플랫폼 기본값에 더 좌우되며, 플랫폼 수준 인증이 자동화된 취약점 점검을 어렵게 만드는 보안-관측성 상충이 있다고 주장한다.

## 출처와 확인 수준

- 공식 출처: [Characterizing Network Centralization and Observability in the Remote MCP Ecosystem](https://arxiv.org/abs/2609.19100)
- 유형: preprint · 2026년 · arXiv preprint · `preprint`
- 저자·발행: Muhammad Abdullah Sohail
- 확인일: 2026-10-14 / `arxiv_api_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 179개 엔드포인트의 ASN 분포 허핀달 지수가 0.736으로 매우 집중되어 있었다.
- 상용 PaaS에 호스팅된 서버의 95%가 게이트웨이 수준에서 OAuth 2.1과 PKCE를 강제했다.
- 플랫폼 인증은 대부분의 서버를 보호하지만 외부에서 도구 포이즈닝 위험을 점검하기 어렵게 만든다는 보안-관측성 상충을 제시한다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이는 외부 점검이 막힌 서버의 도구 호출과 응답을 볼 수 있는 유일한 관측 지점이므로, 도구 호출·응답 로그를 확보하는 위치로 배치하는 근거로 쓴다.
- 호스팅 플랫폼별 인증 기본값을 서버 심사 메타데이터로 기록해, 같은 플랫폼의 서버 위험을 묶어 관리한다.
- ASN 기준 호스팅 집중도를 공급망 리스크 지표로 포함한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

179개 표본의 단일 저자 프리프린트라 일반화에 한계가 있다. WebFetch로 확인한 초록 수준만 반영했고 전문은 미정독이다. 검색 요약 일부에 측정 시점이 다르게 적혀 있으므로 날짜는 전문에서 대조해야 한다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

CC BY 4.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
