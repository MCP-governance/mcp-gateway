# LIB-F07 · Trajectory Guard -- A Lightweight, Sequence-Aware Model for Real-Time Anomaly Detection in Agentic AI

작업 계획과 실제 궤적이 맞는지(과제 정렬)와 계획 구조가 유효한지(순차 타당성)를 함께 학습하는 경량 Siamese 순환 오토인코더로 실시간 이상을 탐지하는 모델을 제안한다. 대형 LLM 판정기보다 훨씬 빠르게 동작한다고 주장한다.

## 출처와 확인 수준

- 공식 출처: [Trajectory Guard -- A Lightweight, Sequence-Aware Model for Real-Time Anomaly Detection in Agentic AI](https://arxiv.org/abs/2601.00516)
- 유형: preprint · 2026년 · arXiv · `preprint`
- 저자·발행: Laksh Advani
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 균형 세트에서 F1 0.88~0.94, 불균형 외부 벤치마크에서 재현율 0.86~0.92를 보고한다(자체 보고).
- 추론 지연이 32ms이고 LLM 판정기 기준선보다 17~27배 빠르다고 보고한다.
- 비지도 기법을 사전학습 임베딩에 적용하면 F1이 최대 0.69에 그친다는 비교를 제시한다.

## 우리 솔루션 개발에 사용할 곳

- LLM 판정기 호출 없이 밀리초 단위로 돌아가는 1차 필터로 쓴다. 계획과 다른 도구 호출 순서를 상시 감시하고, 의심 세션만 LLM 판정이나 사람 검토로 넘긴다.
- 정상 세션 기록을 기준선으로 쌓아 두는 감사 원장 설계와 맞물려, 학습 데이터의 기준 분포를 게이트웨이 로그에서 얻는 방향을 검토한다.
- 학습 자원이 필요하므로 도입 초기에는 규칙 기반 시퀀스 검사로 시작하고, 데이터가 충분히 쌓인 뒤 이 모델을 붙인다(설계 판단).

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv 초록 페이지만 열람했다. 1인 저자 프리프린트이며, 검색 요약이 언급한 워크숍 채택은 확인하지 못해 적지 않았다. 합성 교란 데이터에 기대므로 실제 MCP 트래픽에서의 성능은 검증되지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

arXiv non-exclusive distribution license v1.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
