# LIB-A15 · Model Context Protocol (MCP): Landscape, Security Threats, and Future Research Directions

MCP를 아키텍처와 보안 관점에서 분석하고, 서버 수명주기 4단계와 위협 분류 체계를 제시한 논문이다. 위협 시나리오를 실제 사례로 점검하고, 표준화와 신뢰 경계에 관한 연구 과제를 제안한다. [REF-J01](REF-J01.md)(TOSEM 게재본)의 arXiv 판본이며 두 판본의 내용 차이는 확인하지 않았다.

## 출처와 확인 수준

- 공식 출처: [Model Context Protocol (MCP): Landscape, Security Threats, and Future Research Directions](https://arxiv.org/abs/2503.23278)
- 유형: preprint · 2025년 · arXiv (cs.CR, cross-listed cs.AI) · `preprint`
- 저자·발행: Xinyi Hou, Yanjie Zhao, Shenao Wang, Haoyu Wang
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 서버 수명주기 4단계(생성, 배포, 운영, 유지보수)와 핵심 활동 16개를 정의한다.
- 공격자 4유형과 위협 시나리오 16개로 위협을 분류하고, 실제 사례로 점검한다.
- 수명주기 단계별 보호 조치를 제안하며, 표준화, 신뢰 경계, 생태계 성장을 향후 연구 과제로 제시한다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이 위협 모델을 수명주기 단계(생성, 배포, 운영, 유지보수)별로 나누어, 각 단계에서 어떤 정책과 통제를 걸지 매핑하는 틀로 쓴다.
- 4개 공격자 유형(악성 개발자, 외부 공격자, 악성 사용자, 보안 결함)을 위협 카탈로그의 상위 분류로 쓰고, 각 위협에 OPA 규칙, 승인, 감사 통제를 연결한다.
- 신뢰 경계에 관한 논의를 게이트웨이의 서버 등록 승인 설계 근거로 인용한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv 초록 페이지를 도구가 요약한 내용만 확인했고 전문은 정독하지 않았다. v3(2025-10-07) 기준이며, 사례 연구의 세부와 동료심사 여부는 확인하지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
