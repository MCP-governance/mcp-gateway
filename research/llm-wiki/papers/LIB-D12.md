# LIB-D12 · GuardAgent: Safeguard LLM Agents by a Guard Agent via Knowledge-Enabled Reasoning

사용자가 준 안전과 접근 규칙을 가드 에이전트가 작업 계획과 검사 코드로 번역하고, 그 코드를 실행해 대상 에이전트의 입력과 출력이 규칙을 만족하는지 판정하는 GuardAgent를 제안한다. 모델을 재학습하지 않고 도구 함수 목록을 확장해 쓰는 구조다.

## 출처와 확인 수준

- 공식 출처: [GuardAgent: Safeguard LLM Agents by a Guard Agent via Knowledge-Enabled Reasoning](https://arxiv.org/abs/2406.09187)
- 유형: 논문 · 2024년 · ICML 2025 (arXiv 코멘트 기준) · `venue_reported_unverified`
- 저자·발행: Zhen Xiang, Linzhi Zheng, Yanjie Li, Junyuan Hong 외
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 가드 에이전트가 대상 에이전트 행동을 규칙에 비추어 검사하고, 코드 실행으로 판정을 낸다고 설명한다(초록).
- 자체 제작 벤치마크에서 의료 접근 통제는 98% 넘는 정확도, 웹 에이전트 안전 정책은 약 83% 정확도를 보고한다(초록 수치).
- 대상 에이전트의 과제 수행 성능을 해치지 않았다고 보고한다(초록).

## 우리 솔루션 개발에 사용할 곳

- 자연어 접근 규칙을 검사 코드로 번역하는 파이프라인을 정책 작성 보조(자연어, Rego 초안, 사람 검토)에 참고한다. 생성 코드는 반드시 검토 후 적용한다.
- 검사에 쓰는 함수 목록을 게이트웨이의 OPA 내장 함수 또는 외부 데이터 조회 API로 등록하는 방식을 참고한다.
- 의료 접근 통제 벤치마크처럼 정책 유형별 시험 케이스 세트를 만들어 정책 변경 시 회귀 테스트에 쓴다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

초록과 소개만 확인했고 전문은 정독하지 못했다. 벤치마크가 저자 자체 제작이라 독립적인 재현 검증이 필요하다. 학회 게재본의 제목이 arXiv v1과 다를 수 있다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
