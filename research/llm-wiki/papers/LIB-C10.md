# LIB-C10 · Bypassing LLM Guardrails: An Empirical Analysis of Evasion Attacks against Prompt Injection and Jailbreak Detection Systems

프롬프트 주입과 탈옥을 탐지하는 가드레일이 문자 수준 주입과 적대적 기계학습 기법으로 회피될 수 있음을 실증한다. 상용 Prompt Shield와 Prompt Guard 등 여섯 개 보호 시스템을 대상으로 했다고 밝힌다.

## 출처와 확인 수준

- 공식 출처: [Bypassing LLM Guardrails: An Empirical Analysis of Evasion Attacks against Prompt Injection and Jailbreak Detection Systems](https://arxiv.org/abs/2504.11168)
- 유형: preprint · 2025년 · arxiv.org · `preprint`
- 저자·발행: William Hackett, Lewis Birch, Stefan Trawicki, Neeraj Suri 외
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 문자 수준 주입과 알고리즘 기반 적대적 기법으로 여러 보호 시스템을 우회할 수 있다고 보고한다.
- 일부 설정에서 회피 성공률이 매우 높았다고 보고하며, 더 견고한 가드레일 시스템이 필요하다고 주장한다.

## 우리 솔루션 개발에 사용할 곳

- 탐지 모델 도입 시 문자 변형 같은 회피 공격으로 재시험하는 항목을 평가 체크리스트에 넣고, 탐지기 단독 차단에 의존하지 않도록 정책을 설계한다.
- 탐지기 앞단에 입력 정규화(유니코드 정규화, 문자 변형 복원)를 두는 방안을 평가 후보로 둔다. 이는 논문 결과에서 직접 도출된 것이 아니라 엔지니어링상의 제안이다.
- 탐지기 우회가 쉽다는 전제에서, 권한 기반 차단(호출 자체의 금지)이 최후 방어선이라는 점을 설계 문서에 명시한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

초록 요약만 확인했고 실험 대상 시스템의 버전과 설정은 확인하지 못했다. 발행 시점 버전 기준이므로 현재 제품 버전에서 재확인이 필요하다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

CC BY 4.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
