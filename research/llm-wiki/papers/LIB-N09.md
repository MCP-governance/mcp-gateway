# LIB-N09 · Local Allow, Global Deny: Why Per-Action Authorization Does Not Compose in LLM Agents

호출 단위 인가가 여럿 합쳐져도 전체 정책(의도·목적·출처·동의·위임)을 지킨다는 보장이 없음을 「구성적 인가 실패」로 정의하고, 목적 위반이 2-safety 초성질이어서 호출별 감시기로는 원리상 못 잡는다는 불가능 결과를 증명한다.

## 출처와 확인 수준

- 공식 출처: [Local Allow, Global Deny: Why Per-Action Authorization Does Not Compose in LLM Agents](https://arxiv.org/abs/2610.27620)
- 유형: preprint · 2026년 · arXiv preprint (제출 2026-10-20); IEEE TPS 채택본의 확장판(arXiv 주석 기준, 학회지 판본 미확인) · `preprint`
- 저자·발행: Anmol Pandey, Aditya Jain, Liang Chen 외
- 확인일: 2026-10-23 / `arxiv_api_abstract_read`
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 합성한 최소 반례를 호출별로 보면 9개 LLM 판정기가 거의 모두 승인했고, 두 실행을 함께 보여 주면 같은 모델이 경고했다고 보고한다.

## 우리 솔루션 개발에 사용할 곳

- MINT가 호출마다 판정하는 구조(OPA)의 이론적 한계 근거로 인용하고, 원장 기반 교차 실행 감시(목적·출처 비교)를 후속 과제로 둔다.
- 「한 호출씩 허용」 통과율만으로 안전을 주장하지 않는 보고 원칙의 근거로 쓴다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv API의 초록·서지만 읽었다. 본문·실험 조건(모델·서버 판본·반복·오탐·미탐)·재현은 확인하지 않았다. 수치는 저자 보고이며 우리 환경 값으로 쓰지 않는다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[출처 manifest](../analysis/refs-update-1023/refs-update-1023.sources.json) · [자료 확보 규칙](../methodology/source-protocol.md)
