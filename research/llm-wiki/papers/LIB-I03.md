# LIB-I03 · Security Challenges in AI Agent Deployment: Insights from a Large Scale Public Competition

전문가 대규모 공개 레드팀 대회 데이터를 분석한 논문이다. 22개 최신 LLM 기반 에이전트, 44개 배포 시나리오에서 약 180만 건의 프롬프트 인젝션 시도 중 6만 건 이상이 정책 위반을 일으켰다고 보고한다. 강한 공격을 모아 ART 벤치마크를 만들어 19개 모델에 적용했다.

## 출처와 확인 수준

- 공식 출처: [Security Challenges in AI Agent Deployment: Insights from a Large Scale Public Competition](https://arxiv.org/abs/2507.20526)
- 유형: preprint · 2025년 · NeurIPS 2025 Datasets and Benchmarks Track · `venue_reported_unverified`
- 저자·발행: Andy Zou, Maxwell Lin, Eliot Jones, Micha Nowak 외
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 180만 건의 프롬프트 인젝션 시도 중 6만 건 이상이 문서화된 정책 위반을 일으켰다(초록).
- ART 벤치마크에서 대부분의 에이전트가 대부분의 행동에서 10~100회 질의 안에 정책을 위반했다(초록).
- 정책 위반 유형으로 무단 데이터 접근, 불법 금융 행위, 규제 위반을 든다.

## 우리 솔루션 개발에 사용할 곳

- 정책 위반 유형(무단 데이터 접근, 불법 금융 행위, 규제 위반)을 OPA 정책 카테고리로 나누고, 감사 원장 이벤트를 같은 분류 체계로 기록한다.
- 초록의 '대부분의 에이전트가 10~100회 질의 안에 정책 위반'이라는 결과를 근거로, 세션당 질의 한도와 연속 거부 이후 차단 임계값을 설계한다.
- ART 같은 고빈도 공격 세트를 게이트웨이 CI 회귀 테스트에 넣는다. 벤치마크 데이터의 공개 여부는 확인하지 못했으므로 재현 전에 확인한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

초록과 arXiv 메타데이터만 확인하고 본문은 미정독. 참가자 수는 초록에 없어 미기재. NIST/CAISI 공동 저자 여부와 CAISI 블로그와의 관계는 확인하지 못함. NeurIPS 게재는 검색 결과 기준. 결과 수치의 측정 정의는 버전마다 달라 인용 시 주의. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
