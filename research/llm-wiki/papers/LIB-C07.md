# LIB-C07 · MELON: Provable Defense Against Indirect Prompt Injection Attacks in AI Agents

사용자 입력을 마스킹한 상태로 에이전트 실행을 다시 돌려, 원래 실행과 도구 호출이 비슷하면 주입 공격으로 판단하는 탐지 방어 MELON을 제안한다. 프롬프트 증강 방어와 결합한 MELON-Aug도 함께 제시한다.

## 출처와 확인 수준

- 공식 출처: [MELON: Provable Defense Against Indirect Prompt Injection Attacks in AI Agents](https://arxiv.org/abs/2502.05174)
- 유형: preprint · 2025년 · arxiv.org · `preprint`
- 저자·발행: Kaijie Zhu, Xianjun Yang, Jindong Wang, Wenbo Guo 외
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- AgentDojo에서 기존 방어보다 공격 차단과 유틸리티 보존 양쪽에서 낫다고 보고한다.
- 원래 실행과 마스킹 재실행 사이의 도구 호출 유사성이 공격 판정의 신호라는 설계를 제시한다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이에서 사용자 입력 제거 재실행 비교를 고위험 도구 호출에만 적용하는 탐지기로 구현한다. 원래 세션의 도구 호출 시퀀스와 재실행 결과의 유사도를 계산해 플래그를 남기며, 재실행 비용이 크므로 적용 범위를 제한한다.
- 탐지 결과는 즉시 차단하지 않고 승인 대기나 감사 이벤트로 연결해 오탐 비용을 낮춘다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

초록 요약만 확인했고 본문과 증명 부분은 읽지 않았다. 제목의 provable 보장이 어느 범위인지는 원문으로 확인해야 한다. 학회(ICML 2025) 게재 정보는 검색 스니펫 기준이며 원문으로 확인하지 못했다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

CC BY 4.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
