# LIB-B15 · Securing GenAI Multi-Agent Systems Against Tool Squatting: A Zero Trust Registry-Based Approach

MCP와 A2A 같은 에이전트 상호운용 표준에서 도구를 사칭하거나 오해 소지 있게 등록하는 도구 스쿼팅을 위협으로 정의한다. 관리자 승인 등록, 중앙 탐색, 세분화된 접근 정책을 갖추고 버전과 알려진 취약점에 기반한 동적 신뢰 점수를 쓰는 제로 트러스트 도구 레지스트리를 제안한다.

## 출처와 확인 수준

- 공식 출처: [Securing GenAI Multi-Agent Systems Against Tool Squatting: A Zero Trust Registry-Based Approach](https://arxiv.org/abs/2504.19951)
- 유형: preprint · 2025년 · arxiv.org · `preprint`
- 저자·발행: Vineeth Sai Narajala, Ken Huang, Idan Habler
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 도구 스쿼팅이 레지스트리 관리 없이는 여러 경로로 발생할 수 있다고 주장한다.
- 중앙 관리형 등록과 세분화된 접근 정책으로 사칭 경로를 막는 아키텍처를 제시한다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이에 관리자 승인 기반 도구 레지스트리를 두고, 등록되지 않은 서버의 도구는 호출 경로에 올라오지 못하게 한다.
- 버전 이력과 알려진 취약점 정보로 신뢰 점수를 계산해 OPA 입력에 넣고, 점수가 떨어지면 승인 재요청을 요구한다.
- 단기 자격증명 발급(just-in-time) 개념을 게이트웨이의 OAuth 토큰 처리 설계에 참고한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv 초록 페이지를 열어 확인했다. 초록에 실험과 측정 결과가 없어 효과는 주장일 뿐이다. 설계 논문이라 구현과 평가는 확인하지 못했다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

CC BY 4.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
