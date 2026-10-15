# LIB-I15 · MITRE ATLAS (Adversarial Threat Landscape for AI Systems)

AI 시스템을 겨냥한 적대적 전술·기법·사례·완화를 정리한 MITRE의 공개 지식베이스다. 데이터는 GitHub mitre-atlas/atlas-data 저장소로 배포된다.

## 출처와 확인 수준

- 공식 출처: [MITRE ATLAS (Adversarial Threat Landscape for AI Systems)](https://atlas.mitre.org/)
- 유형: 도구 문서 · 2026년 · MITRE · `official_publication`
- 저자·발행: MITRE
- 확인일: 2026-10-14 / `page_fetched_title_manually_accepted` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- atlas-data 저장소는 ATLAS를 "AI 시스템을 겨냥한 적대자 TTP의 공개 지식베이스"로 소개하고 전술·기법·사례 데이터를 배포한다(README 기준).
- atlas.mitre.org 본 페이지는 스크립트로 렌더링되어 이번 조사에서 본문을 읽지 못했다. 에이전트 관련 신규 기법 목록은 확인하지 않았다.

## 우리 솔루션 개발에 사용할 곳

- 감사 원장의 이벤트 분류에 ATLAS 기법 ID를 태그로 붙여, 실제 사고 분석과 레드팀 결과를 같은 축에서 비교한다. ID는 공식 페이지 확인 후 붙인다.
- 'AI Agent 설정 변경(Modify AI Agent Configuration)' 계열 기법을 계약(스키마)·설정 변경 탐지 규칙의 시험 케이스로 쓴다.
- 'AI Agent 컨텍스트 포이즈닝(AI Agent Context Poisoning)' 계열 기법은 에이전트 컨텍스트에 들어가는 도구 응답 검사 항목의 근거로 쓴다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

atlas.mitre.org 본문이 로드되지 않아 기법 ID, 버전, 전체 개수를 확인하지 못함(fetched_ok=false). GitHub README와 Zenity 블로그만 열었음. 에이전트 기법 명칭은 2차 자료 기준이므로 공식 ID 확인 전에는 인용하지 말 것. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
