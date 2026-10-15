# LIB-E02 · RFC 9449: OAuth 2.0 Demonstrating Proof of Possession (DPoP)

클라이언트가 자신의 개인키로 HTTP 요청마다 서명한 JWT(DPoP 증명)를 함께 보내, 발급된 토큰이 그 키에 묶이도록 하는 송신자 제약 메커니즘이다. 증명은 HTTP 메서드, 대상 URI, 시각, 고유 식별자, 선택적 서버 nonce, 액세스 토큰 해시를 서명한다.

## 출처와 확인 수준

- 공식 출처: [RFC 9449: OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- 유형: RFC · 2023년 · IETF RFC · `ietf_rfc`
- 저자·발행: D. Fett, B. Campbell, J. Bradley, T. Lodderstedt, M. Jones, D. Waite
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 증명이 HTTP 메서드와 URI를 서명해 특정 요청에만 쓰이도록 묶는다.
- 액세스 토큰이 있으면 그 해시(ath)를 증명에 넣어 토큰과 증명의 결합을 검증할 수 있게 한다.

## 우리 솔루션 개발에 사용할 곳

- 하네스에서 빼낸 액세스 토큰을 다른 호스트에서 재사용하는 공격을 막기 위해, 게이트웨이가 모든 호출에서 DPoP 증명의 htm, htu, ath를 검증하고 jti 재사용 캐시로 리플레이를 차단한다.
- DPoP 키는 클라이언트 키일 뿐 사람이나 에이전트의 신원이 아니므로(해석), 감사 원장에는 키 지문과 사용자·에이전트 신원 매핑을 따로 기록한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

본문 앞부분 약 92%까지의 요약만 확인했고 뒷부분과 nonce 처리 세부는 읽지 않았다. 발행 월은 확인하지 못했다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
