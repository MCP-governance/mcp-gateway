# LIB-I12 · Principles for Secure-by-Design Agentic Systems

CoSAI가 2025년 7월 16일 발표한 에이전트 시스템 설계 원칙이다. 사람의 거버넌스와 공동 책임, 제한되고 복원력 있는 설계, 실행의 투명성과 검증 가능한 무결성의 세 원칙을 제시하며, 에이전트 개발자, 도입 조직, 보안 엔지니어를 대상으로 한다.

## 출처와 확인 수준

- 공식 출처: [Principles for Secure-by-Design Agentic Systems](https://www.coalitionforsecureai.org/announcing-the-cosai-principles-for-secure-by-design-agentic-systems/)
- 유형: 보고서·권고 · 2025년 · CoSAI · `official_publication`
- 저자·발행: Coalition for Secure AI (CoSAI), OASIS Open Project
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 세 원칙은 "Human-governed and Accountable", "Bounded and Resilient", "Transparent and Verifiable"이다(발표 페이지 기준).
- 대상은 에이전트 개발자, 도입 조직, 보안 엔지니어다. 발표 페이지에서는 원칙별 세부 요구사항을 확인하지 못했다.

## 우리 솔루션 개발에 사용할 곳

- 두 번째 원칙(영향 범위 최소화)을 에이전트별 도구 허용 목록과 권한 범위 설계 요구로 옮기고, 한 에이전트의 침해가 다른 에이전트 자격증명으로 번지지 않게 격리한다.
- 세 번째 원칙(검증 가능한 무결성)을 감사 원장의 해시 체인과 스키마 해시 기록으로 구현하고, 원장 검증 기능을 둔다.
- 첫 번째 원칙(사람의 거버넌스)은 승인 흐름과 긴급 정지 요건으로 반영한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

발표 페이지만 확인. 원칙 문서 본문과 세부 요구사항은 미정독. 2025년 7월 발표 이후 개정 여부는 확인하지 못함. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
