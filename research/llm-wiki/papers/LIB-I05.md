# LIB-I05 · [Concept Paper] Accelerating the Adoption of Software and AI Agent Identity and Authorization

소프트웨어와 AI 에이전트의 식별·인가를 기존 신원 표준으로 다루는 NIST NCCoE 프로젝트의 개념 설명서(초안)다. 에이전트의 식별, 인가, 감사, 부인방지와 프롬프트 인젝션 통제에 대해 산업계 의견을 구한다.

## 출처와 확인 수준

- 공식 출처: [[Concept Paper] Accelerating the Adoption of Software and AI Agent Identity and Authorization](https://csrc.nist.gov/pubs/other/2026/02/05/accelerating-the-adoption-of-software-and-ai-agent/ipd)
- 유형: 보고서·권고 · 2026년 · NIST · `official_publication`
- 저자·발행: Harold Booth, William Fisher, Ryan Galluzzo, Joshua Roberts (NIST NCCoE)
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 의견 수렴 주제로 식별, 인가, 감사, 부인방지가 명시되어 있고, 프롬프트 인젝션 방지 통제도 별도 주제다.
- 페이지에는 적용 표준(OAuth, OIDC, SPIFFE 등)의 구체 목록이 없다. 2차 자료가 6개 표준을 언급하지만 이 조사에서는 확인하지 못했다.

## 우리 솔루션 개발에 사용할 곳

- 에이전트마다 고유 신원을 부여하고, 게이트웨이의 OAuth 토큰 검증 단계에서 에이전트 신원과 사용자 위임 주체를 구분해 기록한다.
- 감사 원장 이벤트에 에이전트 신원과 인가 판정 결과를 함께 저장해, 나중에 행위 주체를 증명하는 부인방지 요구에 대응한다.
- 의견 수렴 질문에 나온 프롬프트 인젝션 통제를 게이트웨이 정책 시험 항목에 추가한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

NIST 페이지의 개념 설명서 메타데이터와 주제 목록만 확인. PDF 전문은 미정독. 의견 수렴 마감(2026-04-02) 이후 후속 프로젝트 설명서는 확인하지 못함. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
