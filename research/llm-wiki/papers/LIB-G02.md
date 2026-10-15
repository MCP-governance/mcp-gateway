# LIB-G02 · Unicode TAG-Block Concealment of Tool-Metadata Payloads in the Model Context Protocol: An Approval-View Fidelity Gap Across Three Independent Server Implementations

MCP 도구 메타데이터에 유니코드 TAG 블록 문자를 숨기면 사용자가 승인 대화상자에서는 보지 못한 채 모델에는 그대로 전달된다는 승인 화면 충실도 격차를 여러 기법으로 보인다. 프로토콜 차원에서 이 중 어떤 기법에도 재승인이 요구되지 않았다고 보고한다.

## 출처와 확인 수준

- 공식 출처: [Unicode TAG-Block Concealment of Tool-Metadata Payloads in the Model Context Protocol: An Approval-View Fidelity Gap Across Three Independent Server Implementations](https://arxiv.org/abs/2607.05744)
- 유형: preprint · 2026년 · arXiv preprint · `preprint`
- 저자·발행: Mohammadreza Rashidi
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 다섯 개 MCP 메타데이터 표면에서 여덟 가지 기법을 시험했고, 모든 기법이 공격 페이로드를 모델 컨텍스트까지 전달했다.
- 여덟 기법 중 TAG 블록 인코딩만 승인 화면에서는 보이지 않으면서 모델에는 변형 없이 도달했다.
- 기준 문자열 매칭 검사기는 여덟 기법 중 네 가지를 놓쳤고, 정상 설명 25개에서는 오탐이 없었다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이 승인 화면은 도구 설명을 보여주기 전에 유니코드 TAG 블록(U+E0000 to U+E007F)과 제어 문자를 제거하거나 가시화하고, 모델에 전달될 원문을 함께 표시한다.
- 도구 메타데이터 해시가 승인 시점과 달라지면 승인을 무효화하고 재승인을 요구해, 승인 시점과 실제 전달 시점의 불일치(TOCTOU 러그풀)를 게이트웨이에서 막는다.
- 문자열 매칭 검사는 우회되므로 정규화 후 검사를 기본으로 하고, 이 기법 카탈로그를 게이트웨이 회귀 테스트 케이스에 포함한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

WebFetch로 열어 확인한 초록 수준 내용만 반영했다. 단일 저자의 2026년 7월 프리프린트이며 전문과 재현 코드는 미정독이다. 시험 대상이 Python MCP 서버 라이브러리 세 종으로 범위가 좁다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

CC BY 4.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
