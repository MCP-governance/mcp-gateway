# LIB-E13 · AIP: Agent Identity Protocol for Verifiable Delegation Across MCP and A2A

AI 에이전트가 MCP로 도구를 호출하고 A2A로 다른 에이전트에 위임할 때 신원이 검증되지 않는다고 지적하고, 이를 위한 호출 바인딩 능력 토큰(IBCT)을 제안한다. 토큰은 신원, 감쇠된 권한, 출처를 추가 전용 체인에 담으며, 단일 홉은 서명 JWT, 다중 홉은 Datalog 정책 기반 Biscuit 형식을 쓴다.

## 출처와 확인 수준

- 공식 출처: [AIP: Agent Identity Protocol for Verifiable Delegation Across MCP and A2A](https://arxiv.org/abs/2603.24775)
- 유형: preprint · 2026년 · arXiv preprint (cs.CR, cs.AI 교차 분류) · `preprint`
- 저자·발행: Sunil Prakash
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 초록은 MCP와 A2A 모두 에이전트 신원을 검증하지 않는다고 주장한다.
- 제안 토큰은 신원, 권한 감쇠, 출처를 하나의 체인에 결합한다고 설명한다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이 단일 홉 검증은 서명 JWT 방식을, 다단계 위임 체인은 추가 전용 체인 구조를 참고해 감사 원장의 해시 체인 설계와 비교 검토한다.
- 저자의 MCP 서버 인증 부재 주장은 도입 근거 후보로 보되 조사 방법이 초록에만 있으므로 원문 확인 후에 인용한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

단독 저자 preprint이며 초록만 확인했다. 평가 결과와 보유자 측 권한 감쇠의 작동 방식은 본문에서 확인하지 않았고, 성능 수치는 기록하지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
