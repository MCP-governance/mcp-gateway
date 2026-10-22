# LIB-N27 · ClawMMU: Protection-Coherent Virtual Memory for Stateful LLM Agents

에이전트 장기 기억의 각 조각에 소유자·범위·출처·권한 라벨을 붙이고 문맥 진입·저장·복원·행동 시점에 검사하는 ClawMMU를 제안한다. 가져온 웹 페이지의 숨은 지시가 사용자 지시로 취급되는 문제를 의미 분류 대신 보호 위반으로 바꾸는 접근이다.

## 출처와 확인 수준

- 공식 출처: [ClawMMU: Protection-Coherent Virtual Memory for Stateful LLM Agents](https://arxiv.org/abs/2610.28093)
- 유형: preprint · 2026년 · arXiv preprint (제출 2026-10-20); NeurIPS 2026 AgenticOS 워크숍(비아카이브) 채택(arXiv 주석 기준) · `preprint`
- 저자·발행: Jinhao Hu, Bardia Mohammadi, Mofasshara Binte Rafique 외
- 확인일: 2026-10-23 / `arxiv_api_abstract_read`
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- NeurIPS 2026 AgenticOS 워크숍 채택(비아카이브)이라고 arXiv 주석에 적었다. 정량 결과는 초록에서 확인하지 않았다.

## 우리 솔루션 개발에 사용할 곳

- MINT의 출처 표시(provenance)와 목적 결속을 도구 응답 → 후속 호출 경로의 라벨 전파로 확장할지 검토하는 참조다(비채택 포함 판단은 소유자).

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv API의 초록·서지만 읽었다. 본문·실험 조건(모델·서버 판본·반복·오탐·미탐)·재현은 확인하지 않았다. 수치는 저자 보고이며 우리 환경 값으로 쓰지 않는다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[출처 manifest](../analysis/refs-update-1023/refs-update-1023.sources.json) · [자료 확보 규칙](../methodology/source-protocol.md)
