# LIB-B10 · Model Context Protocol Threat Modeling and Analyzing Vulnerabilities to Prompt Injection with Tool Poisoning

STRIDE와 DREAD로 MCP의 다섯 구성 요소(호스트·클라이언트, LLM, 서버, 외부 데이터 저장소, 인가 서버)를 위협 모델링하고, 도구 메타데이터에 숨긴 지시를 가장 흔하고 영향이 큰 클라이언트 측 취약점으로 본다. 주요 MCP 클라이언트 일곱 종의 검증과 방어를 비교하고 다층 방어안을 제안한다.

## 출처와 확인 수준

- 공식 출처: [Model Context Protocol Threat Modeling and Analyzing Vulnerabilities to Prompt Injection with Tool Poisoning](https://arxiv.org/abs/2603.22489)
- 유형: preprint · 2026년 · arxiv.org · `preprint`
- 저자·발행: Charoes Huang, Xin Huang, Ngoc Phu Tran, Amin Milani Fard
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 도구 메타데이터에 심은 악성 지시를 클라이언트 측에서 가장 흔하고 영향이 큰 취약점으로 규정한다.
- 비교 대상 클라이언트 대부분이 약한 정적 검증과 제한된 파라미터 가시성 때문에 중대한 보안 문제를 보였다고 초록이 밝힌다.
- 정적 메타데이터 분석, 모델 결정 경로 추적, 행동 이상 탐지, 사용자 투명성을 묶은 다층 방어를 제안한다.

## 우리 솔루션 개발에 사용할 곳

- 클라이언트별 검증 격차를 게이트웨이 보안 요구사항 체크리스트로 쓰고, 클라이언트가 약한 정적 메타데이터 분석을 게이트웨이가 대신 맡는 항목을 정한다.
- 논문의 사용자 투명성 항목을 승인 화면에 반영해, 도구 설명 전문과 변경 이력을 사람이 보고 승인하도록 한다.
- STRIDE와 DREAD 매핑을 위협 모델 문서의 도구 메타데이터 오염 항목에 연결한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv 초록 페이지를 열어 확인했고 테스트 방법과 클라이언트별 결과는 읽지 않았다. 2차 자료들이 '대부분'과 '전부'를 다르게 말해, 그 표현은 쓰지 않았다. 본문에서 확인이 필요하다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

CC BY 4.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
