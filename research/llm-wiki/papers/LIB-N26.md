# LIB-N26 · AI Agents May Always Fall for Prompt Injections

데이터와 지시를 엄격히 분리하는 방어가 문맥 조작형 공격을 못 잡고 정당한 행동을 해친다고 보이고, 문맥적 무결성(CI) 이론으로 프롬프트 주입을 다시 설명한다. 공격자가 정당한 흐름처럼 보이게 만들거나, 방어자가 규범을 조이면 정당한 흐름까지 막는 딜레마를 제시한다.

## 출처와 확인 수준

- 공식 출처: [AI Agents May Always Fall for Prompt Injections](https://arxiv.org/abs/2605.17634)
- 유형: preprint · 2026년 · arXiv preprint (제출 2026-05-17) · `preprint`
- 저자·발행: Sahar Abdelnabi, Eugene Bagdasarian
- 확인일: 2026-10-23 / `arxiv_api_abstract_read`
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 현재 연구가 다루는 공격 면이 앞으로 줄어든다고 주장한다. 초록 기준이다.

## 우리 솔루션 개발에 사용할 곳

- 프롬프트 주입 완전 방어를 약속하지 않고 「결정적 정책으로 피해 범위를 제한」한다는 MINT 제품 주장의 한계 설명에 인용한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv API의 초록·서지만 읽었다. 본문·실험 조건(모델·서버 판본·반복·오탐·미탐)·재현은 확인하지 않았다. 수치는 저자 보고이며 우리 환경 값으로 쓰지 않는다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[출처 manifest](../analysis/refs-update-1023/refs-update-1023.sources.json) · [자료 확보 규칙](../methodology/source-protocol.md)
