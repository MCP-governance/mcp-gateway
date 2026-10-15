# LIB-J02 · RFC 9162: Certificate Transparency Version 2.0

인증서 투명성 프로토콜 2.0 버전으로, 각 로그를 이진 Merkle 트리로 구성하고 포함 증명과 일관성 증명을 만들고 검증하는 절차를 정의한다. 상태는 Experimental이다.

## 출처와 확인 수준

- 공식 출처: [RFC 9162: Certificate Transparency Version 2.0](https://www.rfc-editor.org/rfc/rfc9162)
- 유형: RFC · 2021년 · IETF RFC 9162 (Experimental) · `ietf_rfc`
- 저자·발행: B. Laurie, E. Messeri, R. Stradling
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 버전 2.0은 로그마다 이진 Merkle 트리를 사용하고, 포함 증명과 일관성 증명을 구성하고 검증하는 방법을 명세한다고 페이지 요약에서 확인했다.
- 저자는 B. Laurie, E. Messeri, R. Stradling이며 저작권 표기 연도는 2021이다(페이지 확인).

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이 감사 원장을 Merkle 트리로 구성해 특정 기록이 원장에 들어 있음을 보이는 포함 증명과, 원장이 과거 기록을 바꾸지 않고 이어졌음을 보이는 일관성 증명을 제공하도록 설계하는 기준으로 쓴다.
- 원장의 루트 해시를 주기적으로 외부에 게시해 두면 게이트웨이 운영자도 과거 기록을 몰래 다시 쓰기 어렵게 만들 수 있다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

페이지 앞부분 요약만 확인했고, 해시 도메인 분리나 리프 형식 같은 세부 규칙은 본문을 읽지 않았다. 구현 성능은 확인하지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
