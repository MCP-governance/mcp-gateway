# LIB-N14 · CreepScope: Measuring Post-Use Authorization Exposure in Tool-Using Agents

도구 호출 시점 인가만으로는 앞서 준 권한이 얼마나 오래 쓸 수 있는 채로 남는지 알 수 없다는 「권한 잔존」을 단계별 노출량 지표(CSE·RPD)로 측정한다. 단계마다 임대를 갱신하는 방식이 이론상 0임을 보인다.

## 출처와 확인 수준

- 공식 출처: [CreepScope: Measuring Post-Use Authorization Exposure in Tool-Using Agents](https://arxiv.org/abs/2610.15988)
- 유형: preprint · 2026년 · arXiv preprint (제출 2026-10-11) · `preprint`
- 저자·발행: Haoran Yu, Lifei Liu, Danping Zhang 외
- 확인일: 2026-10-23 / `arxiv_api_abstract_read`
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 12개 워크플로우 재생에서 정적 작업 범위와 단조 온디맨드 방식은 평균 CSE가 26과 13이었고, 단계 임대는 0이었다고 밝힌다. 소규모 모의 사례이며 교차 모델 일반화는 아니라고 스스로 한계를 적는다.

## 우리 솔루션 개발에 사용할 곳

- MINT 동의·목적 결속의 유효 기간을 「작업 단계 종료 뒤 남은 노출」 관점에서 측정하는 지표로 쓴다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv API의 초록·서지만 읽었다. 본문·실험 조건(모델·서버 판본·반복·오탐·미탐)·재현은 확인하지 않았다. 수치는 저자 보고이며 우리 환경 값으로 쓰지 않는다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[출처 manifest](../analysis/refs-update-1023/refs-update-1023.sources.json) · [자료 확보 규칙](../methodology/source-protocol.md)
