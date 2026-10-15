# LIB-E11 · OAuth 2.0 Attestation-Based Client Authentication

클라이언트 인스턴스가 키에 묶인 증명(attestation)을 제시하고, 증명 PoP JWT 또는 결합된 DPoP 증명으로 그 키를 가지고 있음을 입증하는 방식을 정의한다. 클라이언트 인증 방식으로도 추가 보안 신호로도 쓸 수 있으며, 증명 발급자에게 대상 인가 서버 정보가 노출되지 않도록 설계됐다.

## 출처와 확인 수준

- 공식 출처: [OAuth 2.0 Attestation-Based Client Authentication](https://datatracker.ietf.org/doc/draft-ietf-oauth-attestation-based-client-auth/)
- 유형: 명세·제안 · 2026년 · IETF Internet-Draft · `ietf_internet_draft`
- 저자·발행: T. Looker, P. Bastian, C. Bormann
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 증명은 클라이언트 인스턴스 단위로 발급되며 사용자 신원과는 별도의 계층이라고 정의한다.
- 증명 발급자에게 대상 인가 서버 정보가 드러나지 않도록 설계됐다고 요약된다.

## 우리 솔루션 개발에 사용할 곳

- 고위험 도구 호출에는 하네스 인스턴스 증명을 요구하는 정책을 두고, 증명 유효성과 키 보유 검증 결과를 OPA 입력 신호로 넣는다.
- 증명 발급자를 신뢰 목록으로 관리하고, 게이트웨이 감사 원장에 발급자 식별자를 기록한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

rev 12 본문 앞부분 약 83%의 요약만 확인했다. 워킹그룹 최종 검토(WGLC) 단계이며 RFC는 아직 발행되지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
