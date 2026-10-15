# LIB-C04 · Adaptive Attacks Break Defenses Against Indirect Prompt Injection Attacks on LLM Agents

도구를 쓰는 LLM 에이전트를 대상으로 한 간접 주입 방어 8종을 평가하고, 이들이 적응형 공격에 취약함을 보인다. 방어가 공격자의 적응을 고려하지 않은 채 검증되면 신뢰하기 어렵다고 주장한다.

## 출처와 확인 수준

- 공식 출처: [Adaptive Attacks Break Defenses Against Indirect Prompt Injection Attacks on LLM Agents](https://arxiv.org/abs/2503.00061)
- 유형: preprint · 2025년 · arxiv.org · `preprint`
- 저자·발행: Qiusi Zhan, Richard Fang, Henil Shalin Panchal, Daniel Kang
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 평가한 방어 8종을 적응형 공격으로 우회할 수 있었다고 보고한다.
- 방어 논문들이 고정 공격 세트로 주장을 내는 관행을 문제로 보고, 방어 설계 시 적응형 평가가 필수라고 주장한다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이 방어(출력 필터, 탐지기, 프롬프트 기반 가드)를 도입하기 전에, 방어를 아는 공격자 시나리오인 적응형 공격을 평가 하네스에 넣는 기준으로 쓴다.
- 방어 평가에서 고정된 공격 문자열 세트만으로 통과를 판정하지 않고, 공격 최적화를 붙인 재시험을 릴리스 게이트 조건으로 둔다.
- 정책(OPA)이 차단한 호출과 탐지기가 놓친 호출을 구분해 기록하면, 적응형 공격에서 어느 계층이 뚫렸는지 분석할 수 있다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

초록 요약만 확인했고 8종 방어의 목록과 공격 세부는 본문에서 확인하지 못했다. 학회 게재 정보(NAACL Findings 2025)는 검색 스니펫 기준이며 원문으로 확인하지 못했다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

CC BY 4.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
