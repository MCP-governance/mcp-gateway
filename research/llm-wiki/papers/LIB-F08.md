# LIB-F08 · WildGuard: Open One-Stop Moderation Tools for Safety Risks, Jailbreaks, and Refusals of LLMs

사용자 프롬프트의 악성 의도, 모델 응답의 안전 위험, 모델의 거부 여부를 한 모델로 판정하는 오픈 모더레이션 도구 WildGuard를 소개한다. 학습과 평가에 쓰는 WildGuardMix 데이터셋(약 9만 2천 건)을 함께 공개했다.

## 출처와 확인 수준

- 공식 출처: [WildGuard: Open One-Stop Moderation Tools for Safety Risks, Jailbreaks, and Refusals of LLMs](https://arxiv.org/abs/2406.18495)
- 유형: 논문 · 2024년 · NeurIPS 2024 · `venue_reported_unverified`
- 저자·발행: Seungju Han, Kavel Rao, Allyson Ettinger, Liwei Jiang 외
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 세 과제를 한 모델로 처리하며, 모델 인터페이스에 적용한 배포 실험에서 탈옥 공격 성공률을 79.8%에서 2.4%로 낮췄다고 초록에서 보고한다(자체 보고).
- 프롬프트 위험 판정은 프롬프트된 GPT-4와 비슷하거나 넘고, 거부 탐지는 공개 모더레이션 모델 10종보다 낫다고 주장한다.
- WildGuardMix는 학습 데이터와 사람이 주석한 5천 건 테스트셋으로 나뉜다.

## 우리 솔루션 개발에 사용할 곳

- 도구 호출 인자의 의도 판정과 도구 결과의 위험 판정을 같은 모델로 처리하되, 결과는 OPA 입력 신호로만 쓰고 최종 결정은 정책 엔진에 둔다.
- 거부 탐지 기능은 에이전트가 정책 위반 요청을 거부했는지를 감사 원장에 남기는 용도로 쓸 수 있다.
- 탈옥 공격과 일반 프롬프트를 섞은 평가 세트를 게이트웨이 회귀 테스트에 넣어, 판정기 교체 전후의 재현율을 비교한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv 초록 페이지만 열람했고 본문과 평가 표는 정독하지 않았다. 검색 요약과 열람 요약의 세부 수치가 달라, 인용하려면 본문 표를 확인해야 한다. 수치는 저자 자체 보고다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

CC BY 4.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
