# LIB-N13 · Kairos: Transactional Security Enforcement at the System Boundary for LLM Agents

에이전트 격리 경계에 두는 참조 모니터 Kairos를 제안한다. 신뢰하는 출처를 선언한 정책이 대부분 결정하고 나머지는 보류해 두었다가 모델이나 사람이 사후 추적을 보고 풀어 준다.

## 출처와 확인 수준

- 공식 출처: [Kairos: Transactional Security Enforcement at the System Boundary for LLM Agents](https://arxiv.org/abs/2610.18457)
- 유형: preprint · 2026년 · arXiv preprint (제출 2026-10-13) · `preprint`
- 저자·발행: Kristoffer Hempel, Nils Loose, Lorenzo Cavallaro 외
- 확인일: 2026-10-23 / `arxiv_api_abstract_read`
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- AgentDojo에서 공격 성공률을 47.0%에서 2.7%로 낮추면서 정상 유용성은 방어 없는 에이전트 수준을 유지했다고 보고한다.

## 우리 솔루션 개발에 사용할 곳

- MINT의 허용·차단 이분 판정에 「보류 후 증거로 해제」 상태를 둘지 검토하는 비교 자료로 쓴다(관찰 모드와의 관계 명시).

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv API의 초록·서지만 읽었다. 본문·실험 조건(모델·서버 판본·반복·오탐·미탐)·재현은 확인하지 않았다. 수치는 저자 보고이며 우리 환경 값으로 쓰지 않는다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[출처 manifest](../analysis/refs-update-1023/refs-update-1023.sources.json) · [자료 확보 규칙](../methodology/source-protocol.md)
