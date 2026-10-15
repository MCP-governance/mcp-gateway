# LIB-B04 · MPMA: Preference Manipulation Attack Against Model Context Protocol

공격자가 변조한 MCP 서버를 두어 LLM이 경쟁 서버보다 그 서버의 도구를 우선 고르도록 만드는 선호 조작 공격(MPMA)을 정의한다. 이름과 설명에 유도 문구를 넣는 DPMA와, 유전 알고리즘으로 설명을 다듬어 은밀성을 높인 GAPMA 두 방법을 제안한다.

## 출처와 확인 수준

- 공식 출처: [MPMA: Preference Manipulation Attack Against Model Context Protocol](https://arxiv.org/abs/2505.11154)
- 유형: 논문 · 2025년 · AAAI-26 · `venue_reported_unverified`
- 저자·발행: Zihan Wang, Rui Zhang, Yu Liu, Wenshu Fan 외
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 직접 삽입형 DPMA는 효과는 있으나 사용자에게 쉽게 드러난다는 한계를, GAPMA는 효과와 은밀성의 균형을 보인다고 초록이 밝힌다.
- 공격 동기로 경제적 이득을 명시한다.
- 공격 표면이 실행 코드가 아니라 도구 이름과 설명 같은 메타데이터라고 밝힌다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이의 도구 추천과 정렬에 설명 문구 점수를 쓰지 않고, 관리자가 승인한 서버와 도구만 노출하는 허용 목록을 기본값으로 둔다.
- 설명에 '최고', '우선 사용' 같은 우선순위 문구가 있는 신규 도구는 등록 시 경고 플래그를 달고 승인 큐로 보낸다. DPMA 유형을 잡기 위한 규칙이다.
- 경제적 동기를 고려해 유료 MCP 서버 연계 시 호출 빈도와 선택 편향을 감사 원장에 남기고, 주기적으로 사후 점검한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv 초록과 AAAI 페이지를 열어 제목·저자·DOI를 확인했다. 초록 수준만 읽었고 GAPMA의 정량 결과와 실험 세부는 확인하지 못했다. 초록에도 수치가 없어 수치는 적지 않았다. arXiv 판본(2025)과 학회판(2026) 본문 차이는 확인하지 못했다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

arXiv non-exclusive 1.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
