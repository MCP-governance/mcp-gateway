# LIB-C06 · RTBAS: Defending LLM Agents Against Prompt Injection and Privacy Leakage

도구 호출을 정보 흐름 제어와 두 개의 의존성 검사기로 분석해, 안전이 확인된 호출은 자동 실행하고 확인되지 않을 때만 사용자 승인을 요청하는 방어 RTBAS를 제안한다. 모든 호출에 확인을 요구하는 기존 방어의 사용자 부담을 줄이는 것이 목표이다.

## 출처와 확인 수준

- 공식 출처: [RTBAS: Defending LLM Agents Against Prompt Injection and Privacy Leakage](https://arxiv.org/abs/2502.08966)
- 유형: preprint · 2025년 · arxiv.org · `preprint`
- 저자·발행: Peter Yong Zhong, Siyuan Chen, Ruiqi Wang, McKenna McCall 외
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 대상 공격을 AgentDojo에서 차단하면서 공격 상황에서의 유틸리티 손실이 작다고 보고한다.
- 기존 방어가 모든 도구 호출에 확인을 요구해 사용자 부담이 크다는 문제를 제기하고, 확인이 필요한 경우만 묻는 방식을 제안한다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이의 승인 흐름을 모든 호출 승인에서 정책 판정 결과에 따른 자동 통과 또는 승인 대기로 나누는 설계 근거로 쓴다.
- 의존성 검사 개념을 OPA 입력에 넣는다. 호출 인자가 신뢰되지 않은 출처에서 왔는지, 민감 데이터가 외부 도구로 흘러가는지를 정책 입력 필드로 전달한다.
- 승인 요청에는 어떤 출처의 데이터가 호출에 영향을 주었는지 설명을 붙이고, 이를 감사 원장과 승인 화면에 함께 기록한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

초록 요약만 확인했고 의존성 검사기의 구체 규칙과 실험 설정은 읽지 않았다. 차단 성능은 AgentDojo 범위 안의 주장이다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

CC BY 4.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
