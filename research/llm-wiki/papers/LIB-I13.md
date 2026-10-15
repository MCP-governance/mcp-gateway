# LIB-I13 · Securing Agentic AI: A Comprehensive Threat Model and Mitigation Framework for Generative AI Agents

생성형 AI 에이전트의 위협 모델을 제안하는 논문이다. 추론, 기억, 행동을 사람의 감독 없이 수행하는 에이전트의 특성에서 9개 주요 위협을 도출하고, 이를 5개 영역(인지 구조, 시간적 지속성, 운영 실행, 신뢰 경계 위반, 거버넌스 우회)으로 묶는다. 위협 분류 체계 ATFAA와 완화 전략 SHIELD를 함께 제시한다.

## 출처와 확인 수준

- 공식 출처: [Securing Agentic AI: A Comprehensive Threat Model and Mitigation Framework for Generative AI Agents](https://arxiv.org/abs/2504.19956)
- 유형: preprint · 2025년 · arxiv.org · `preprint`
- 저자·발행: Vineeth Sai Narajala, Om Narayan
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 9개 주요 위협을 5개 영역으로 묶는다(초록 기준).
- 에이전트는 기존 LLM과 달리 추론, 기억, 행동을 제한된 사람의 감독 아래 수행하므로 위협 모델이 달라야 한다고 주장한다.

## 우리 솔루션 개발에 사용할 곳

- 5개 영역을 게이트웨이 통제 지도의 열로 쓴다. '신뢰 경계 위반'은 도구 출력 검증 지점, '거버넌스 우회'는 정책 우회 탐지 지점에 대응시킨다.
- '시간적 지속성'(기억 오염)을 근거로, 세션 간 컨텍스트 저장소에 쓰기 권한을 제한하고 쓰기 기록을 감사 원장에 남긴다.
- SHIELD의 완화 전략 목록을 게이트웨이 기능 백로그와 대조해 빠진 통제를 찾는다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

초록과 arXiv 메타데이터만 확인하고 본문은 미정독. 9개 위협의 세부 정의와 SHIELD 완화 항목은 확인하지 못함. 저자 제안 프레임워크이며 독립 평가는 확인하지 못했다. 확인한 최신 버전은 v2(2025-05-02). 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
