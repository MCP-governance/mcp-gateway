# LIB-J15 · Building an Open AIBOM Standard in the Wild

ISO/IEC 5962:2021 SPDX SBOM 표준을 확장해 데이터셋과 반복 학습 산출물 같은 AI 구성요소를 담는 AIBOM 명세를 만든 경험 보고서이다. 90명 이상의 기여자가 구조화된 실행 연구 사이클로 참여했고, 규제 정합 등 네 가지 방식으로 검증했다고 밝힌다.

## 출처와 확인 수준

- 공식 출처: [Building an Open AIBOM Standard in the Wild](https://arxiv.org/abs/2510.07070)
- 유형: preprint · 2025년 · arXiv preprint, 2025년 10월 제출 (v2 2026년 2월 개정) · `preprint`
- 저자·발행: Gopi Krishnan Rajbahadur, Keheliya Gallaba, Elyas Rashno, Arthit Suriyawongkul 외
- 확인일: 2026-10-14 / `page_fetched_title_manually_accepted` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- SPDX를 확장한 AIBOM 명세를 90명 이상의 기여자와 구조화된 실행 연구 사이클로 만들었다고 보고한다.
- 검증은 EU AI Act와 IEEE 7000 정합, 6개 산업 사용 사례 매핑, 실무자 반구조화 인터뷰, 산업 사례 연구의 네 가지 방식으로 이뤄졌다고 밝힌다.

## 우리 솔루션 개발에 사용할 곳

- MCP 서버 매니페스트에 AIBOM 필드를 얹을 때 SPDX 확장 구조의 데이터셋과 학습 산출물 항목을 참고해 필드 이름을 맞추면 외부 감사 도구와 호환하기 쉽다.
- 네 가지 검증 방식인 규제 정합, 사용 사례 6개 매핑, 실무자 인터뷰, 산업 사례 연구를 게이트웨이 AIBOM 명세의 검증 계획에 그대로 차용한다.
- AIBOM의 구성요소 목록을 승인 레코드의 필드 후보로 쓰면, 승인 시점에 어떤 구성요소가 있었는지 기록할 수 있다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

초록 수준 요약만 확인했고 전문은 정독하지 않았다. v1과 v2 사이의 내용 차이는 확인하지 못했다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
