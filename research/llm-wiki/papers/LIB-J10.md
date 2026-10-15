# LIB-J10 · in-toto Attestation Framework Specification

공급망 아티팩트에 대한 인증된 메타데이터를 표준화하며, 아티팩트에 attestation을 묶는 Statement, 타입별 스키마를 갖는 Predicate, 인증과 직렬화를 맡는 Envelope, 여러 attestation을 묶는 Bundle 계층으로 구성된다. 자동화된 정책 엔진이 소비하는 것을 목적으로 한다.

## 출처와 확인 수준

- 공식 출처: [in-toto Attestation Framework Specification](https://github.com/in-toto/attestation/blob/main/spec/README.md)
- 유형: 명세·제안 · 2025년 · in-toto attestation 명세 v1.2 (최신 표기) · `official_publication`
- 저자·발행: in-toto 프로젝트 (명세 저장소 기준, 개별 저자 표기 없음)
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- Statement는 attestation을 특정 subject 아티팩트에 묶고, Predicate 타입이 메타데이터 스키마를 정한다고 명세가 설명한다(페이지 확인).
- 명세의 목적으로 in-toto-verify와 Binary Authorization 같은 정책 엔진을 소비자로 명시한다(페이지 확인).

## 우리 솔루션 개발에 사용할 곳

- MCP 서버 릴리스마다 빌드 출처와 승인된 스키마 해시를 Predicate로 담은 Statement를 만들고, 게이트웨이가 로드 시점에 이를 정책 입력으로 검증하도록 설계한다.
- 승인된 도구 계약의 해시를 Statement의 subject 다이제스트로 쓰면, 계약 변경 탐지를 해시 불일치면 거부하는 단순한 규칙으로 만들 수 있다.
- SBOM과 provenance 같은 여러 attestation을 Bundle 계층으로 한 묶음에 전달하는 형식을 따른다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

GitHub 명세 README 한 페이지만 확인했다. Envelope의 인증 방식 세부는 페이지에 DSSE 명칭 없이 설명되어 있어 별도 확인이 필요하다. 발행 연도는 페이지에 없어 2025는 추정치이다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
