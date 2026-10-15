# LIB-F10 · SentinelAgent: Graph-based Anomaly Detection in Multi-Agent Systems

다중 에이전트 실행을 동적 실행 그래프로 모델링해 노드, 간선, 경로 수준에서 이상을 찾는 방법을 제안한다. 보안 정책에 따라 실행에 개입할 수 있는 LLM 기반 감시 에이전트 SentinelAgent를 함께 제시한다.

## 출처와 확인 수준

- 공식 출처: [SentinelAgent: Graph-based Anomaly Detection in Multi-Agent Systems](https://arxiv.org/abs/2505.24201)
- 유형: preprint · 2025년 · arXiv · `preprint`
- 저자·발행: Xu He, Di Wu, Yan Zhai, Kun Sun
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 노드, 간선, 경로 수준의 이상 탐지를 한 틀로 묶어 위험한 통신과 의도치 않은 제어 흐름을 잡는다고 주장한다.
- 감시 에이전트가 실행에 개입할 수 있다고 주장하며, 이메일 비서와 Magentic-One을 두 사례 연구로 든다.
- 초록에는 정량 결과가 없다.

## 우리 솔루션 개발에 사용할 곳

- 여러 에이전트나 세션이 MCP 도구를 공유할 때 호출 관계를 그래프로 쌓아, 여러 단계에 걸친 위험 연쇄 경로를 찾는 감사 뷰의 설계 참고로 쓴다.
- 그래프 경로 기반 알림은 단일 호출 판정(OPA)이 놓치는 연쇄 위험의 탐지 후보로 두고, 차단 결정은 정책 엔진에 남긴다.
- 감시 에이전트가 LLM이라 지연과 비용이 크므로, 그래프 갱신은 규칙 기반으로 하고 의심 경로만 LLM 감시로 넘기는 구성을 검토한다(설계 판단).

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv 초록(v1)만 열람했고 본문과 정량 평가는 확인하지 않았다. 사례 연구가 두 개뿐이라 대표성이 불명확하며, 노드와 간선 상태 정의의 세부는 초록에 없어 확인하지 못했다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

arXiv non-exclusive distribution license v1.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
