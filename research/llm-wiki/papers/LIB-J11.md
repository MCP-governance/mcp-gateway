# LIB-J11 · in-toto: Providing farm-to-table guarantees for bits and bytes

소스 관리, 빌드 서버, CI/CD, 패키징 등 공급망의 한 단계를 공격자가 장악하더라도 최종 소프트웨어 변조를 숨기지 못하도록, 단계별 암호학적 증명을 쌓아 시작부터 배포까지 최종 사용자가 전체 체인을 검증하게 하는 in-toto 프레임워크를 제안한다. 한 단계만 뚫린 공격을 막는 것이 핵심이다.

## 출처와 확인 수준

- 공식 출처: [in-toto: Providing farm-to-table guarantees for bits and bytes](https://www.usenix.org/conference/usenixsecurity19/presentation/torres-arias)
- 유형: 논문 · 2019년 · USENIX Security 2019 (28th USENIX Security Symposium) · `venue_reported_unverified`
- 저자·발행: Santiago Torres-Arias, Hammad Afzali, Trishank Karthik Kuppusamy, Reza Curtmola, Justin Cappos
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 공격자가 공급망 단계 하나를 장악해도 변조를 숨길 수 없도록 단계별로 검증하는 구조를 제안한다고 발표 페이지 요약이 밝힌다(페이지 확인).
- 저자는 Torres-Arias, Afzali, Kuppusamy, Curtmola, Cappos 5인이며 USENIX Security 2019에 발표되었다(페이지 확인).

## 우리 솔루션 개발에 사용할 곳

- MCP 서버 배포 파이프라인을 레이아웃(허용된 단계와 서명 키)과 단계별 링크 증명으로 나눠, 한 단계가 뚫려도 게이트웨이의 최종 검증이 실패하도록 설계한다.
- 게이트웨이가 MCP 서버를 기동하기 전 단계별 증명 체인을 확인하고, 실패하면 기동을 거부하는 흐름을 정책으로 둔다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

USENIX 발표 페이지의 요약만 확인했고 본문과 평가 결과는 읽지 않았다. 구현 세부는 확인하지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
