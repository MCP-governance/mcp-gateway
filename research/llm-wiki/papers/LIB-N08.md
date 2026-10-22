# LIB-N08 · TrustShiftProbe: Characterizing, Benchmarking, and Defending Staged Trust Attacks on MCP Servers

처음에는 정상으로 행동해 신뢰를 쌓다가 어느 시점부터 악성으로 바뀌는 MCP 서버(TrustShift)를 정의하고, 배포 전 정적 분석이 놓치는 이유를 설명한다. 청정 구간에서 배운 행동 기준선과 서버 응답을 비교하는 전송 경계 방어 SHIELD를 제안한다.

## 출처와 확인 수준

- 공식 출처: [TrustShiftProbe: Characterizing, Benchmarking, and Defending Staged Trust Attacks on MCP Servers](https://arxiv.org/abs/2608.23763)
- 유형: preprint · 2026년 · arXiv preprint (제출 2026-08-24) · `preprint`
- 저자·발행: Mehrdad Rostamzadeh, Sidhant Narula, Mohammad Ghasemigol 외
- 확인일: 2026-10-23 / `arxiv_api_abstract_read`
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 9가지 TrustShift 변형(구조 위반·의미 훼손·범위 확대)과 세 목적(교란·유출 등)을 분류했다고 밝힌다.

## 우리 솔루션 개발에 사용할 곳

- MINT의 계약 해시 재승인은 정의가 바뀔 때만 잡는다는 한계를 명시하고, 응답 형태·크기 기준선 이탈 탐지를 후속 검토 항목으로 둔다.
- 스키마를 지키는 조작은 런타임 필터를 통과할 수 있다는 점을 응답 검사 시험 설계에 반영한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv API의 초록·서지만 읽었다. 본문·실험 조건(모델·서버 판본·반복·오탐·미탐)·재현은 확인하지 않았다. 수치는 저자 보고이며 우리 환경 값으로 쓰지 않는다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[출처 manifest](../analysis/refs-update-1023/refs-update-1023.sources.json) · [자료 확보 규칙](../methodology/source-protocol.md)
