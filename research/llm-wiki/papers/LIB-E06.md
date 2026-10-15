# LIB-E06 · Identity Management for Agentic AI: The new frontier of authorization, authentication, and security for an AI agent world

AI 에이전트 시대의 인증, 인가, 신원 과제를 정리하려고 OpenID 재단이 낸 백서로, 현재 에이전트를 보호하는 기존 자원을 조사하고 향후 자율 에이전트를 위한 전략적 의제를 제시한다. 초록 기준으로 MCP 같은 에이전트 중심 프로토콜의 인증, 인가 모범 사례가 아직 명확하지 않다고 지적한다.

## 출처와 확인 수준

- 공식 출처: [Identity Management for Agentic AI: The new frontier of authorization, authentication, and security for an AI agent world](https://arxiv.org/abs/2510.25819)
- 유형: preprint · 2025년 · OpenID Foundation Whitepaper (arXiv cs.CR) · `preprint`
- 저자·발행: Tobin South, Subramanya Nagabhushanaradhya, Ayesha Dissanayaka, Sarah Cecchetti 외
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 초록은 MCP 같은 에이전트 중심 프로토콜의 인증, 인가 모범 사례가 부족하다고 적는다.
- 초록은 향후 과제로 에이전트 중심 신원, 워크로드 구분, 위임 권한 등을 든다.

## 우리 솔루션 개발에 사용할 곳

- 논문이 꼽은 공백(에이전트 중심 신원, 위임 권한, 확장 가능한 접근 제어, AI 워크로드 구분)을 게이트웨이 로드맵 항목과 대응시켜 근거 문서로 인용한다.
- 위임 권한 공백은 게이트웨이의 사용자와 에이전트 분리 기록(on-behalf-of 기록) 설계의 근거로 쓴다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv 초록만 확인하고 백서 본문은 열지 않았다. 구체적 권고안은 초록에 없어 본문 확인 전까지 기록하지 않았다. 2차 요약 기사의 강한 주장은 검증하지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
