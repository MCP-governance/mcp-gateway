# LIB-B05 · From Component Manipulation to System Compromise: Understanding and Detecting Malicious MCP Servers

악성 MCP 서버를 구성 요소 단위로 나눠, 공격 성공에 영향을 주는 구성 요소 위치와 여러 구성 요소에 악성 로직을 나눈 공격을 분석한다. 실행 전에 도구의 의도를 추출하고 실행 중 행동이 그 의도에서 벗어나는지 보는 두 단계 탐지기 Connor를 제안한다.

## 출처와 확인 수준

- 공식 출처: [From Component Manipulation to System Compromise: Understanding and Detecting Malicious MCP Servers](https://arxiv.org/abs/2604.01905)
- 유형: preprint · 2026년 · arxiv.org · `preprint`
- 저자·발행: Yiheng Huang, Zhijia Zhao, Bihuan Chen, Susheng Wu 외
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 구성 요소의 위치에 따라 공격 성공률이 달라지고, 악성 로직을 여러 구성 요소에 나눈 공격이 단일 구성 요소 공격보다 효과적인 경우가 많다고 보고한다.
- 기존 보호 기법은 다중 구성 요소 공격과 새로운 악성 행위에 효과가 떨어진다고 주장한다.
- 실환경 탐지에서 악성 서버 두 개를 찾았다고 보고한다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이에서 도구의 선언된 의도(설명과 스키마)와 실제 호출 인자·응답 패턴을 비교하는 이탈 탐지 로직을 설계한다. 실행 전 단계는 셸 명령 같은 위험 인자의 정적 검사로 시작한다.
- 여러 구성 요소에 걸친 공격을 막기 위해 한 도구의 응답이 다음 호출의 인자로 이어지는 흐름을 세션 단위로 추적하고, 그 흐름을 OPA 정책으로 평가한다.
- 논문의 PoC 악성 서버 데이터셋 구성을 참고해 게이트웨이 회귀 테스트 케이스를 만든다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv 초록 페이지만 열어 확인했다. 데이터셋 구성과 실험 설정은 본문에서 확인하지 못했다. 탐지 성능 수치는 적지 않았다. 검색 스니펫의 학술지 게재 언급은 확인하지 못했다. 평가가 두 MCP 호스트와 다섯 LLM 설정에 한정되어 일반화 범위는 본문 확인이 필요하다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

CC BY-NC-ND 4.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
