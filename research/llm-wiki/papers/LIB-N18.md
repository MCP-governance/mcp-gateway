# LIB-N18 · Registry Descriptions Go Stale Unevenly: An 89-Day Measurement of Model Context Protocol Drift, and Why Drift-Ranked Re-Auditing Under-Covers It

공식 MCP 레지스트리 89일간 120회 관측으로 서버 설명이 얼마나 자주·고르게 바뀌는지 측정하고, 드리프트 순위로 재점검하면 효율이 낮다는 정책적 결론을 낸다. 내용 해시가 바뀌면 즉시 재검증하고 주기적 전수 점검을 병행하는 편이 맞다고 제안한다.

## 출처와 확인 수준

- 공식 출처: [Registry Descriptions Go Stale Unevenly: An 89-Day Measurement of Model Context Protocol Drift, and Why Drift-Ranked Re-Auditing Under-Covers It](https://arxiv.org/abs/2608.00997)
- 유형: preprint · 2026년 · arXiv preprint (제출 2026-08-02) · `preprint`
- 저자·발행: Gautam Bharti
- 확인일: 2026-10-23 / `arxiv_api_abstract_read`
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 서버의 8.6%만 설명을 고쳤고 변경의 절반 정도가 신규 등록에서 일어나 이력 순위로는 닿지 않는다고 한다.

## 우리 솔루션 개발에 사용할 곳

- MINT의 계약·설명 해시 변경 시 재승인 규칙(rug pull 대응)이 타당하다는 외부 근거로 쓴다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv API의 초록·서지만 읽었다. 본문·실험 조건(모델·서버 판본·반복·오탐·미탐)·재현은 확인하지 않았다. 수치는 저자 보고이며 우리 환경 값으로 쓰지 않는다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[출처 manifest](../analysis/refs-update-1023/refs-update-1023.sources.json) · [자료 확보 규칙](../methodology/source-protocol.md)
