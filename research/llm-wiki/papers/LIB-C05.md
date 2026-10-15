# LIB-C05 · The Attacker Moves Second: Stronger Adaptive Attacks Bypass Defenses Against Llm Jailbreaks and Prompt Injections

탈옥과 프롬프트 주입에 대한 방어들이 고정된 공격 문자열이나 약한 최적화 공격으로만 검증되고 있다고 비판한다. 경사 하강, 강화학습, 랜덤 서치, 사람 주도 탐색 같은 일반 최적화 방법을 조정해 최근 방어 12종을 우회했다고 주장한다.

## 출처와 확인 수준

- 공식 출처: [The Attacker Moves Second: Stronger Adaptive Attacks Bypass Defenses Against Llm Jailbreaks and Prompt Injections](https://arxiv.org/abs/2510.09023)
- 유형: preprint · 2025년 · arxiv.org · `preprint`
- 저자·발행: Milad Nasr, Nicholas Carlini, Chawin Sitawarin, Sander V. Schulhoff 외
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 근사 0 수준의 공격 성공률을 보고했던 방어 다수가 적응형 공격에서는 높은 성공률로 뚫린다고 주장한다.
- 고정 공격 세트나 약한 공격으로 방어를 평가하는 관행이 방어 과대평가의 원인이라고 지적한다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이 방어의 릴리스 기준으로, 탐지와 필터 계층을 최적화 기반 공격 도구로 재시험하는 단계를 CI 게이트에 넣는다.
- 방어 논문이 근사 0의 공격 성공률을 보고하더라도 채택 근거로 삼지 않고, 적응형 평가 결과를 함께 요구하는 정책을 설계 문서에 명시한다.
- 사람 주도 탐색(red team)에서 찾은 우회 패턴을 감사 원장과 연결해, OPA 규칙 보강으로 되돌리는 절차를 둔다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

초록 요약만 확인했고 본문의 공격 방법과 우회한 방어 목록은 읽지 않았다. 우회 성공률 수치는 기재하지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

CC BY 4.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
