# LIB-C15 · SecAlign: Defending Against Prompt Injection with Preference Optimization

정당한 명령을 수행한 안전한 응답과 주입된 명령을 수행한 불안전한 응답의 쌍을 선호 최적화로 학습시키는 방어 SecAlign을 제안한다. 학습 중 보지 못한 더 강한 공격에도 주입 성공률을 낮게 유지하면서 유틸리티를 보존한다고 주장한다.

## 출처와 확인 수준

- 공식 출처: [SecAlign: Defending Against Prompt Injection with Preference Optimization](https://arxiv.org/abs/2410.05451)
- 유형: preprint · 2024년 · arxiv.org · `preprint`
- 저자·발행: Sizhe Chen, Arman Zharmagambetov, Saeed Mahloujifar, Kamalika Chaudhuri 외
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 학습 중 보지 못한 더 강한 공격에도 주입 성공률을 낮게 유지한다고 보고한다.
- 선호 최적화로 공격 성공률을 낮추면서 원래 모델의 유틸리티에 가깝게 유지한다고 주장한다.

## 우리 솔루션 개발에 사용할 곳

- StruQ와 함께 모델 측 방어의 평가 기준으로 쓴다. 다만 게이트웨이에서는 모델 방어를 1차 방어로 간주하지 않고, 모델 방어가 있어도 정책 차단을 완화하지 않는 원칙을 둔다.
- 안전 응답과 불안전 응답의 쌍 구성 방식을 게이트웨이 회귀 테스트 생성에 차용한다. 주입 시도가 있을 때 정상 동작과 공격 동작을 쌍으로 기록한다.
- 사내 모델을 SecAlign 계열로 미세조정할 계획이 있다면, 유틸리티 손실을 MCP 작업 세트로 측정하는 항목을 함께 넣는다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

초록 요약만 확인했고 학습 데이터와 평가 공격 세부는 읽지 않았다. 같은 저자들의 후속 Meta-SecAlign 초록(arXiv 2507.02735, 직접 확인함)은 규모를 키우면 SecAlign의 유틸리티 손실이 커진다고 지적하므로, 두 주장을 함께 보아야 한다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

CC BY 4.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
