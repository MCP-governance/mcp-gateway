# LIB-C14 · StruQ: Defending Against Prompt Injection with Structured Queries

프롬프트의 명령 부분과 데이터 부분을 서로 다른 채널로 나누는 구조화된 질의를 제안한다. 프롬프트 채널의 지시만 따르도록 미세조정해 주입 공격에 강하게 만들면서 유틸리티 손실은 작다고 주장한다.

## 출처와 확인 수준

- 공식 출처: [StruQ: Defending Against Prompt Injection with Structured Queries](https://arxiv.org/abs/2402.06363)
- 유형: preprint · 2024년 · arxiv.org · `preprint`
- 저자·발행: Sizhe Chen, Julien Piet, Chawin Sitawarin, David Wagner
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 구조화 질의와 전용 미세조정으로 주입 공격에 대한 저항성이 크게 높아진다고 보고한다.
- 유틸리티 손실이 작다고 주장한다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이가 직접 학습할 수는 없으므로, 백엔드 모델 선정 시 명령과 데이터를 분리하도록 학습됐는지를 모델 점검 항목으로 쓴다.
- 구조화 질의 개념을 MCP 도구 응답의 필드 분리에 대응시켜, 명령으로 해석될 수 있는 필드와 순수 데이터 필드를 나누는 응답 스키마 설계를 검토한다.
- 이 방어는 모델 재학습이 필요하므로 게이트웨이 단독으로는 적용할 수 없고, 평가와 설계의 참고 자료로만 쓴다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

초록 요약만 확인했고 학습 세부와 적응형 공격 실험은 읽지 않았다. 게이트웨이 적용 방식은 추정이다. 후속 SecAlign과의 비교는 본문에서 확인이 필요하다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

arXiv non-exclusive distribution license 1.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
