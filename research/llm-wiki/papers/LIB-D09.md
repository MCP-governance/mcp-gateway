# LIB-D09 · AgentArmor: Enforcing Program Analysis on Agent Runtime Trace to Defend Against Prompt Injection

에이전트 실행 궤적을 제어 흐름, 데이터 흐름, 프로그램 의존 그래프로 바꿔 프로그램처럼 분석하고, 타입 시스템으로 보안 정책을 검사해 위험한 연산을 실행 전에 막는 방어 기법을 제안한다. 프롬프트 인젝션을 실행 흐름 관점에서 다룬다는 점이 특징이다.

## 출처와 확인 수준

- 공식 출처: [AgentArmor: Enforcing Program Analysis on Agent Runtime Trace to Defend Against Prompt Injection](https://arxiv.org/abs/2508.01249)
- 유형: preprint · 2025년 · arXiv preprint (v1 2025-08-02, v3 2025-11-18) · `preprint`
- 저자·발행: Peiran Wang, Yang Liu, Yunfei Lu, Yifeng Cai 외
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- AgentDojo에서 공격 성공률을 크게 낮추면서 효용 손실은 작다고 보고한다(초록). 버전마다 수치 표현이 다르다.
- 정보 흐름과 신뢰 경계 위반을 함께 다루는 정책 검사를 실행 전 단계에 둔다.

## 우리 솔루션 개발에 사용할 곳

- 도구 호출 궤적을 데이터 흐름 그래프로 저장하는 감사 원장 스키마를 설계할 때 참고한다. 민감 출처에서 외부 전송으로 가는 경로를 사후에 질의할 수 있다.
- 도구의 보안 속성(민감도, 신뢰 수준)을 MCP 서버 등록 메타데이터로 두는 구조가 이 논문의 속성 레지스트리 개념과 맞는다.
- 그래프 분석 전체를 게이트웨이 안에 넣는 것은 무거우므로, 단순 출처 라벨 규칙을 OPA로 먼저 구현하고 그래프 분석은 감사 단계에 두는 단계적 도입을 검토한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

초록과 검색 발췌만 확인했고 전문은 정독하지 못했다. 제목과 효용 비용 표기가 버전별로 달라 인용 전 최신판을 확인해야 한다. 검색 발췌 기준으로 'taint tracking'이라는 용어는 본문에서 확인되지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
