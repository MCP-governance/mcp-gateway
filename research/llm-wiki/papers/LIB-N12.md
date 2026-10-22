# LIB-N12 · Runtime Authorization for Resources Acquired by AI Agents

에이전트가 계산 자원·자격·계정·다른 에이전트를 획득할 때 반환된 자원이 곧바로 권한으로 쓰이는 「이행 후 활성화 간극」을 다룬다. 획득물을 격리하고 공급자 증거로 실제 능력을 해석한 뒤 활성화 트랜잭션에서만 쓰게 하는 런타임 인가 구조를 제안한다.

## 출처와 확인 수준

- 공식 출처: [Runtime Authorization for Resources Acquired by AI Agents](https://arxiv.org/abs/2609.14744)
- 유형: preprint · 2026년 · arXiv preprint (제출 2026-09-13) · `preprint`
- 저자·발행: Genliang Zhu, Chu Wang
- 확인일: 2026-10-23 / `arxiv_api_abstract_read`
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 8가지 안전 성질을 증명하고, 5개 자원 종류에서 안전하지 않은 흔적 40건을 모두 거부했다고 보고한다.

## 우리 솔루션 개발에 사용할 곳

- MINT가 도구 응답으로 받은 자격·토큰·URL을 후속 호출에 쓰지 못하게 하는 규칙(자격 재사용 차단)의 이론 근거로 쓴다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv API의 초록·서지만 읽었다. 본문·실험 조건(모델·서버 판본·반복·오탐·미탐)·재현은 확인하지 않았다. 수치는 저자 보고이며 우리 환경 값으로 쓰지 않는다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[출처 manifest](../analysis/refs-update-1023/refs-update-1023.sources.json) · [자료 확보 규칙](../methodology/source-protocol.md)
