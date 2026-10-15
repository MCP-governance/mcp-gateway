# LIB-F03 · NeMo Guardrails: A Toolkit for Controllable and Safe LLM Applications with Programmable Rails

LLM 기반 대화 시스템에 프로그래머블 레일(규칙)을 붙여 주제, 대화 경로, 말투를 실행 시점에 통제하는 오픈소스 툴킷을 소개한다. 학습 단계의 정렬에 기대지 않고, 모델과 독립적이며 해석 가능한 규칙을 정의하는 방식을 제안한다.

## 출처와 확인 수준

- 공식 출처: [NeMo Guardrails: A Toolkit for Controllable and Safe LLM Applications with Programmable Rails](https://arxiv.org/abs/2310.10501)
- 유형: 논문 · 2023년 · EMNLP 2023 (Demo track) · `preprint`
- 저자·발행: Traian Rebedea, Razvan Dinu, Makesh Sreedhar, Christopher Parisien 외
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 가드레일을 학습 단계 정렬이 아니라 대화 관리처럼 실행 시점에 붙이는 설계를 제안한다.
- 규칙이 LLM과 독립적이고 해석 가능하다고 주장하며, 여러 LLM 제공자에서 초기 결과가 있다고 밝힌다.
- 초록에는 정량 비교 수치가 없다.

## 우리 솔루션 개발에 사용할 곳

- 애플리케이션과 모델 사이에서 프록시처럼 끼어 규칙을 집행하는 구조가 게이트웨이의 위치와 같으므로, 게이트웨이 내부 규칙 실행 계층의 설계 참고로 쓴다.
- 규칙을 코드와 분리해 운영자가 선언적으로 고치는 방식은 OPA 정책 파일 운영 흐름과 비슷하므로, 규칙 변경 이력을 감사 원장과 묶는 설계에 참고한다.
- 규칙이 LLM과 독립적이라는 원칙을 근거로, 하네스(Codex, Claude Code 등)가 바뀌어도 정책 계층을 그대로 두는 구조를 검증하는 근거로 쓴다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv 초록 페이지와 EMNLP 2023 데모 트랙 채택 표기만 확인했고 본문은 정독하지 않았다. 규칙 언어의 문법 세부와 저자의 사용 권고는 검색 요약에서만 봤기 때문에 근거로 쓰지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

arXiv non-exclusive distribution license v1.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
