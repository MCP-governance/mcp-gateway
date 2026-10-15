# LIB-B16 · MCP Safety Audit: LLMs with the Model Context Protocol Allow Major Security Exploits

주요 LLM이 MCP 도구를 사용해 개발자 시스템에서 악성 코드 실행, 원격 제어, 자격증명 탈취를 수행하도록 유도될 수 있음을 보인다. 이에 맞춰 에이전트 기반으로 MCP 서버의 적대적 테스트 케이스를 만들고 보안 보고서를 내는 점검 도구 MCPSafetyScanner를 소개한다.

## 출처와 확인 수준

- 공식 출처: [MCP Safety Audit: LLMs with the Model Context Protocol Allow Major Security Exploits](https://arxiv.org/abs/2504.03767)
- 유형: preprint · 2025년 · arxiv.org · `preprint`
- 저자·발행: Brandon Radosevich, John Halloran
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 주요 LLM이 MCP 도구를 통해 악성 코드 실행이나 자격증명 탈취를 수행하도록 유도될 수 있다고 보고한다.
- MCP의 설계가 최종 사용자에게 넓은 위험을 만든다고 주장한다.
- 서버 등록 전 점검용 에이전트 도구 MCPSafetyScanner를 공개했다고 밝힌다.

## 우리 솔루션 개발에 사용할 곳

- MCPSafetyScanner 방식의 서버 등록 전 점검을 게이트웨이 승인 절차의 한 단계로 넣고, 점검 결과를 승인 근거로 감사 원장에 기록한다.
- 논문이 보인 공격 유형(악성 코드 실행, 자격증명 탈취)을 OPA 정책 테스트 케이스로 옮겨, 셸 실행과 자격증명 파일 접근 도구를 기본 거부한다.
- 점검 도구가 생성한 적대적 테스트를 게이트웨이 회귀 테스트에 재사용한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv 초록 페이지를 열어 확인했고 실험 대상 모델과 성공률은 읽지 않았다. 2025년 4월 공개 프리프린트라 최신 모델 동작과 다를 수 있다. 저장소 링크가 판본과 인용처마다 다르게 보여 원문에서 다시 확인해야 한다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

CC BY 4.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
