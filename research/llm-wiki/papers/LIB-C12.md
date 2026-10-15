# LIB-C12 · Your Agent is More Brittle Than You Think: Uncovering Indirect Injection Vulnerabilities in Agentic LLMs

다단계 도구 사용 에이전트가 제3자 콘텐츠에 숨은 간접 주입에 단일 턴 벤치마크보다 더 취약하다고 주장한다. 여섯 방어, 네 공격 유형, 아홉 백본 모델을 동적 환경에서 시험하고, 도구 입력 위치의 은닉 상태를 읽어 승인되지 않은 행동을 막는 표현 공학 기반 서킷 브레이커를 제안한다.

## 출처와 확인 수준

- 공식 출처: [Your Agent is More Brittle Than You Think: Uncovering Indirect Injection Vulnerabilities in Agentic LLMs](https://arxiv.org/abs/2604.03870)
- 유형: preprint · 2026년 · arxiv.org · `preprint`
- 저자·발행: Wenhui Zhu, Xuanzhao Dong, Xiwen Chen, Rui Cai 외
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 고급 간접 주입이 평가한 방어 대부분을 우회한다고 보고한다.
- 모델 내부 의사결정의 불확실성이 높은데도 에이전트가 주입 지시를 거의 즉시 실행한다고 관찰한다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이의 도구 호출 직전 훅에서 승인되지 않은 행동을 막는 서킷 브레이커 개념을 참고하되, 은닉 상태 접근은 게이트웨이가 모델 내부에 닿을 수 없으므로 적용할 수 없다. 대신 호출 인자와 출력에 기반한 신호로 대체한다.
- 하네스에 다단계 세션 단위 평가를 넣는다. 단발 호출이 아니라 여러 턴의 도구 호출 시퀀스에서 주입 성공 여부를 판정한다.
- 에이전트가 주입 지시를 거의 즉시 실행한다는 관찰을 근거로, 도구 응답을 받은 뒤가 아니라 실제 도구 호출이 커밋되기 직전에 정책 검사를 강제하는 위치를 설계에 반영한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

초록 요약만 확인했다. 2026년 4월 제출된 프리프린트로 동료 심사 여부를 확인하지 못했다. 정량 결과와 실험 세부는 읽지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

arXiv non-exclusive distribution license 1.0 (페이지 링크 기준)

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
