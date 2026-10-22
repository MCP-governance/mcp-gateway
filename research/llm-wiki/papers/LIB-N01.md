# LIB-N01 · GatewayBench: Unified Capability and Security Evaluation Platform for MCP Gateways

MCP 게이트웨이를 평면형과 계층형 두 구조로 나누고, 작업 완료·도구 사용 효율·공격 저항을 함께 재는 첫 평가 틀이다. 524개 작업과 실제 도구 11,118개를 쓰고, 널리 쓰이는 게이트웨이 7종에 정상·적대 작업을 모두 돌렸다고 밝힌다.

## 출처와 확인 수준

- 공식 출처: [GatewayBench: Unified Capability and Security Evaluation Platform for MCP Gateways](https://arxiv.org/abs/2610.23449)
- 유형: preprint · 2026년 · arXiv preprint (제출 2026-10-16) · `preprint`
- 저자·발행: Yitian Zheng, Zhaorun Chen, Haoyu Li 외
- 확인일: 2026-10-23 / `arxiv_api_abstract_read`
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 게이트웨이 설계에 따라 작업 완료·효율·공격 저항에 큰 차이가 났고, 그 효과는 모델과 하네스에 따라 달라졌다고 보고한다.

## 우리 솔루션 개발에 사용할 곳

- MINT 게이트웨이 시험에 「도구 수가 늘어도 판정이 유지되는가」 축을 더할 때 작업·도구 구성 방식을 참고한다.
- 게이트웨이 구조(평면형/계층형)에 따라 효율과 보안이 달라진다는 주장을 우리 구조 설명에 쓰기 전에 직접 재현 범위를 정한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv API의 초록·서지만 읽었다. 본문·실험 조건(모델·서버 판본·반복·오탐·미탐)·재현은 확인하지 않았다. 수치는 저자 보고이며 우리 환경 값으로 쓰지 않는다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[출처 manifest](../analysis/refs-update-1023/refs-update-1023.sources.json) · [자료 확보 규칙](../methodology/source-protocol.md)
