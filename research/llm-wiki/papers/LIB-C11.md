# LIB-C11 · Agent Security Bench (ASB): Formalizing and Benchmarking Attacks and Defenses in LLM-based Agents

10개 시나리오, 10개 에이전트, 400개 이상의 도구를 포함해 LLM 에이전트의 공격과 방어를 형식화하고 벤치마크하는 프레임워크 ASB를 제안한다. 여러 백본 모델에서 현재 방어의 효과가 제한적이라고 보고하고, 유틸리티와 보안을 함께 보는 지표를 제안한다.

## 출처와 확인 수준

- 공식 출처: [Agent Security Bench (ASB): Formalizing and Benchmarking Attacks and Defenses in LLM-based Agents](https://arxiv.org/abs/2410.02644)
- 유형: preprint · 2024년 · arxiv.org · `preprint`
- 저자·발행: Hanrong Zhang, Jingyuan Huang, Kai Mei, Yifei Yao 외
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 여러 백본 모델을 비교한 결과 현재 방어가 제한적으로만 효과적이라고 보고한다.
- 에이전트 동작의 여러 단계에서 취약점이 나타난다고 보고한다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이 회귀 테스트 세트로 ASB의 시나리오 형식(도구 정의, 공격 주입 위치, 성공 판정 기준)을 차용하고, 우리 MCP 도구 목록에 맞춘 시나리오를 만든다.
- 유틸리티와 보안을 함께 보는 지표를 게이트웨이 릴리스 리포트에 넣어, 차단률만 높이고 정상 작업을 깨는 정책 변경을 걸러낸다.
- ASB의 공격과 방어 방법 목록을 기준 비교표로 쓰되, 입력, 출력, 정책 계층별로 분류해 방어 공백을 찾는다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

초록 요약만 확인했고 벤치마크의 공격 목록과 시나리오 세부는 읽지 않았다. 학회 게재 정보는 확인하지 못했다. 수치는 생략했다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

arXiv non-exclusive distribution license 1.0 (페이지 링크 기준, 본문 명시 없음)

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
