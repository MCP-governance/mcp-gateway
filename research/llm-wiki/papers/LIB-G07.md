# LIB-G07 · A First Measurement Study on Authentication Security in Real-World Remote MCP Servers

실사용 원격 MCP 서버 7,973개의 인증 실태를 측정하고, 인증 구현 결함을 4개 범주 9종으로 분류한 taxonomy를 만든다. 테스트 가능한 OAuth 서버 119개는 모두 최소 한 가지 결함이 있었다고 보고한다.

## 출처와 확인 수준

- 공식 출처: [A First Measurement Study on Authentication Security in Real-World Remote MCP Servers](https://arxiv.org/abs/2605.22333)
- 유형: preprint · 2026년 · arXiv preprint · `preprint`
- 저자·발행: Huijun Zhou, Xiaohan Zhang, Haozhe Zhang, Haoyang Zhang 외
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 원격 MCP 서버 7,973개 중 약 40.55%가 인증 없이 도구를 노출했다.
- 테스트 가능한 OAuth 서버 119개에서 총 325개의 결함이 발견되었고, 모든 서버에 최소 한 개 이상이 있었다.
- 동적 클라이언트 등록 관련 결함이 시험 서버의 96.6%에서 나타났고, 책임 있는 공개를 통해 CVE ID 9개가 발급되었다.

## 우리 솔루션 개발에 사용할 곳

- 논문의 9종 결함 taxonomy를 게이트웨이의 OAuth 토큰 검증과 클라이언트 등록 회귀 테스트 케이스로 옮긴다.
- 동적 클라이언트 등록(DCR) 결함이 대다수 서버에서 발견되었으므로, 게이트웨이에서 클라이언트 등록 경로를 허용하지 않거나 승인 기반으로만 열도록 정책화한다.
- 업스트림 MCP 서버의 무인증 노출 여부를 서버 심사 항목으로 기록하고, 무인증 서버는 게이트웨이 뒤에서만 쓰도록 강제한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

WebFetch로 확인한 초록 수치만 반영했다. OAuth 결함 수치는 테스트 가능했던 119개 서버에 한정된 값이라 전체 배포의 비율로 해석하면 안 된다. 전문은 미정독이며 2026년 5월 프리프린트다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

arXiv non-exclusive distribution license 1.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
