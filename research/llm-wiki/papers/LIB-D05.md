# LIB-D05 · Causality Laundering: Denial-Feedback Leakage in Tool-Calling LLM Agents

공격자가 차단된 행동의 거부 응답을 관찰해 정보를 얻고, 이후 무해해 보이는 도구 호출로 그 정보를 유출하는 '인과 세탁' 공격을 정의한다. 이를 막기 위해 거부된 행동도 출처 그래프에 반사실 간선으로 넣는 Agentic Reference Monitor(ARM)를 제안한다.

## 출처와 확인 수준

- 공식 출처: [Causality Laundering: Denial-Feedback Leakage in Tool-Calling LLM Agents](https://arxiv.org/abs/2604.04035)
- 유형: preprint · 2026년 · arXiv preprint (v1 2026-04-05) · `preprint`
- 저자·발행: Mohammad Hossein Chinaei
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 데이터 의존 기반의 평면 출처 추적은 거부 피드백을 통한 유출을 놓친다고 주장한다.
- 3개 대표 공격 시나리오의 통제 평가에서 ARM이 평면 기준선이 놓친 공격을 차단했다고 보고한다(정량 지표 없음).

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이 감사 원장에 거부된 호출도 기록하고 이후 호출의 출처 판단에 반영하면, 거부 응답이 정보 유출 경로가 되는 것을 막을 수 있다.
- 차단 응답에 상세한 거부 사유를 과도하게 실어 보내지 않는 것을 응답 정책 항목으로 추가한다. 거부 피드백이 공격 신호가 되지 않도록 하기 위함이다.
- 정책 평가 지연을 밀리초 미만으로 주장하므로, 게이트웨이 성능 목표를 정할 때 참고 수치로 쓴다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

초록만 확인했고 전문은 정독하지 못했다. 평가가 3개 시나리오로 좁고 정량 지표가 초록에 없어 일반화 근거가 약하다. 단독 저자 프리프린트이며 동료 심사 게재 여부는 확인하지 못했다. 검색 결과에서는 'Agentic Reference Monitor'가 제목처럼 보였으나 v1 제목은 'Causality Laundering'이다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
