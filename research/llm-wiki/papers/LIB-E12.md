# LIB-E12 · AI Identity Management System

AI 에이전트의 인증과 인가 상호작용에 대한 모범 사례를 WIMSE 아키텍처와 OAuth 2.0 계열 위에서 정리하며, 새 프로토콜은 정의하지 않는다. 식별자, 자격 증명, 프로비저닝, 인증, 인가, 모니터링과 교정, 정책, 컴플라이언스를 포괄하는 개념적 스택으로 에이전트 신원 관리 체계를 설명한다.

## 출처와 확인 수준

- 공식 출처: [AI Identity Management System](https://datatracker.ietf.org/doc/draft-ietf-wimse-aims/)
- 유형: 명세·제안 · 2026년 · IETF Internet-Draft · `ietf_internet_draft`
- 저자·발행: P. Kasselman, J. Lombardo, Y. Rosomakho, B. Campbell, N. Steele, A. Parecki
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 정책 형식과 컴플라이언스 기준은 범위에서 제외되어 있다.
- 앞선 초안 draft-klrc-aiagent-auth-03은 이 문서로 대체됐다고 해당 페이지에 표시되어 있다.

## 우리 솔루션 개발에 사용할 곳

- 이 개념 스택을 게이트웨이 기능 맵의 체크리스트로 쓴다. 인가는 OPA, 모니터링은 감사 원장, 교정은 승인 워크플로가 맡는지 계층별 대응표를 만든다.
- 초안이 정책 형식과 컴플라이언스 기준을 범위 밖으로 둔 만큼, 게이트웨이의 정책 스키마는 자체 정의가 필요하다고 로드맵에 명시한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

rev 00(2026-09-15)으로 매우 새로운 초안이다. 데이터트래커 요약만 확인했고 본문의 세부 요구사항은 읽지 않았다. 의도된 RFC 상태는 미정이다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
