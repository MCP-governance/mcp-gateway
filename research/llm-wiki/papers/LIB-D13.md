# LIB-D13 · IsolateGPT: An Execution Isolation Architecture for LLM-Based Agentic Systems

LLM 기반 플랫폼의 서드파티 앱을 각자 격리된 실행 환경에서 돌려, 앱이 다른 앱이나 시스템 자원에 임의로 닿지 못하게 하는 실행 격리 아키텍처 IsolateGPT를 제안한다. 격리가 실현 가능하다는 것을 보이고 구현을 위한 청사진을 제공하는 것이 목적이다.

## 출처와 확인 수준

- 공식 출처: [IsolateGPT: An Execution Isolation Architecture for LLM-Based Agentic Systems](https://arxiv.org/abs/2403.04960)
- 유형: 논문 · 2024년 · NDSS 2025 · `venue_reported_unverified`
- 저자·발행: Yuhao Wu, Franziska Roesner, Tadayoshi Kohno, Ning Zhang 외
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 격리 구조가 많은 보안, 프라이버시, 안전 문제를 완화하면서 기능 손실이 없다고 보고한다(초록).
- 오버헤드가 주요 트레이드오프이며, 질의의 대부분에서 비용이 제한적이라고 밝힌다(초록 수치).
- 후속 연구 ACE가 이 설계에 대해 계획 조작 공격을 보였으므로, 격리만으로는 계획 단계 공격을 막지 못할 수 있다는 점을 함께 읽어야 한다(ACE 초록 기준).

## 우리 솔루션 개발에 사용할 곳

- MCP 서버를 각각 격리된 실행 경계로 두고 게이트웨이를 유일한 교환 지점으로 삼는 구조의 선행 설계로 인용한다.
- 앱끼리 직접 통신하지 않고 허브를 거치게 하는 원칙이 우리 게이트웨이의 라우팅 원칙과 같으므로 근거 문서로 쓴다.
- 격리 오버헤드를 질의 단위 분포로 보고한 방식을 게이트웨이 성능 측정 설계에 참고한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

초록과 메타데이터만 확인했고 전문은 정독하지 못했다. 구현 세부와 평가 공격 목록은 확인하지 못했다. 제3자 리뷰의 설명은 원문과 대조하지 않아 참조하지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
