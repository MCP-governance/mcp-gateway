# LIB-B13 · Machine Learning-Based Detection of MCP Attacks

악성 MCP 도구 설명을 찾기 위해 전통 ML과 딥러닝 분류기를 학습시켜 규칙 기반 기준선과 비교하는 연구다. 악성 여부를 가르는 이진 분류와 공격 유형을 가르는 다중 분류를 모두 다루며, 실행 전에 안전하지 않은 도구를 막는 미들웨어를 함께 제안한다.

## 출처와 확인 수준

- 공식 출처: [Machine Learning-Based Detection of MCP Attacks](https://arxiv.org/abs/2604.10534)
- 유형: preprint · 2026년 · arxiv.org · `preprint`
- 저자·발행: Tobias Mattsson, Samuel Nyberg, Anton Borg, Ricardo Britto
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 규칙 기반 방식보다 ML 모델이 악성 도구 탐지에서 낫다고 주장한다.
- 실행 전에 도구를 점검하고 안전하지 않은 도구를 차단하는 미들웨어 구조를 제시한다.
- 악성 여부 판별과 공격 유형 분류를 모두 평가 과제로 둔다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이 도구 등록 파이프라인에 설명 분류기를 경고용 단계로 넣고, 규칙 기반 점검 결과와 나란히 기록해 비교한다.
- 실행 전 차단 미들웨어는 게이트웨이의 호출 전 정책 판정 지점과 같은 위치이므로, 설명 분류 점수를 OPA 입력으로 넘기는 인터페이스를 설계한다.
- 다중 분류의 공격 유형 라벨 체계를 감사 원장의 위험 사유 코드로 재사용한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv 초록 페이지만 열어 확인했다. 초록에 데이터셋이나 벤치마크 이름이 없어 재현 근거가 약하다. 공격 범주 목록과 수치는 확인하지 못해 적지 않았다. 학회 게재 여부는 확인하지 못했다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

arXiv non-exclusive 1.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
