# LIB-C09 · DataSentinel: A Game-Theoretic Detection of Prompt Injection Attacks

오염된 입력을 가려내도록 LLM을 미세조정하되, 최소최대 최적화로 적응형 공격에도 견디도록 설계한 탐지기 DataSentinel을 제안한다. 기존 탐지기가 강한 공격과 적응형 공격에 약하다는 문제의식에서 출발한다.

## 출처와 확인 수준

- 공식 출처: [DataSentinel: A Game-Theoretic Detection of Prompt Injection Attacks](https://arxiv.org/abs/2504.11358)
- 유형: preprint · 2025년 · arxiv.org · `preprint`
- 저자·발행: Yupei Liu, Yuqi Jia, Jinyuan Jia, Dawn Song 외
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 기존 탐지기가 강한 공격과 적응형 공격에 취약하다고 보고하고, 이를 겨냥한 탐지기를 설계했다고 주장한다.
- 여러 벤치마크와 모델에서 기존 공격과 적응형 공격을 탐지했다고 보고한다(초록 기준).

## 우리 솔루션 개발에 사용할 곳

- 도구 응답 탐지기의 후보로 평가한다. 게이트웨이의 응답 필터 자리에 탐지 모델을 연결하고, 차단 임계값을 OPA 정책 파라미터로 노출한다.
- 학습형 탐지기는 학습과 운영 비용이 크므로, 1단계에서는 탐지기 호출 인터페이스만 두고 DataSentinel 같은 학습형 탐지는 평가 결과에 따라 도입한다.
- 탐지 점수와 판정 결과를 감사 원장에 기록해 임계값 조정 근거로 쓴다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

초록 요약만 확인했고 탐지 성능 수치, 학습 데이터 구성, 학습 비용은 확인하지 못했다. 적응형 공격 실험의 강도는 본문에서 확인이 필요하다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

CC BY 4.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
