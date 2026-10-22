# LIB-N17 · KedgeFlow: A Programmable Control Plane for Enterprise AI Agents

승인과 자원 실행이 계약을 공유하지 않아 생기는 변조·동시 재사용·재시도 문제를, 승인 서명·1회 소비 허용량·대상 측 조건·결과 기록으로 묶는 제어 평면 KedgeFlow로 푼다. MCP로 노출하는 참조 구현이 있다.

## 출처와 확인 수준

- 공식 출처: [KedgeFlow: A Programmable Control Plane for Enterprise AI Agents](https://arxiv.org/abs/2610.14810)
- 유형: preprint · 2026년 · arXiv preprint (제출 2026-10-10) · `preprint`
- 저자·발행: Jun He, Deying Yu
- 확인일: 2026-10-23 / `arxiv_api_abstract_read`
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 6,560회 동시 소비 시도에서 82개 허용량이 각각 정확히 한 번만 소비됐고 32호출 경쟁에서 효과가 한 번만 반영됐다고 보고한다. 단일 호스트·모의 대상 평가다.

## 우리 솔루션 개발에 사용할 곳

- MINT 승인된 호출이 정확히 한 번만 소비되는지(재시도·경쟁)를 시험하는 동시성 시나리오의 참조로 쓴다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv API의 초록·서지만 읽었다. 본문·실험 조건(모델·서버 판본·반복·오탐·미탐)·재현은 확인하지 않았다. 수치는 저자 보고이며 우리 환경 값으로 쓰지 않는다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[출처 manifest](../analysis/refs-update-1023/refs-update-1023.sources.json) · [자료 확보 규칙](../methodology/source-protocol.md)
