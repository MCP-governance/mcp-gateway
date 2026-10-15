# LIB-B14 · MCPXKIT: The Unified Toolkit for Analyzing Model Context Protocol Security

MCP 보안 위험을 분석하는 통합 툴킷으로, 직접 도구 주입, 간접 도구 주입, 악의적 사용자 공격, LLM 고유 공격의 네 범주에 걸친 31개 공격 방법을 구현하고 효과를 정량 측정한다고 밝힌다. 에이전트가 도구 설명에 크게 의존한다는 등의 결과를 보고한다.

## 출처와 확인 수준

- 공식 출처: [MCPXKIT: The Unified Toolkit for Analyzing Model Context Protocol Security](https://arxiv.org/abs/2508.12538)
- 유형: preprint · 2025년 · arxiv.org · `preprint`
- 저자·발행: Yongjian Guo, Puzhuo Liu, Wanlun Ma, Zehang Deng 외
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 에이전트가 도구 설명에 크게 의존한다고 보고한다.
- 파일 기반 공격에 민감하고, 공유 컨텍스트를 이용한 연쇄 공격이 가능하다고 보고한다.
- 외부 데이터와 실행 가능한 명령을 에이전트가 구분하기 어렵다고 보고한다.

## 우리 솔루션 개발에 사용할 곳

- 31개 공격 구현을 게이트웨이 보안 회귀 테스트 스위트의 공격 목록 출발점으로 쓴다. 코드 라이선스와 사용 조건은 저장소에서 따로 확인해야 한다.
- 간접 도구 주입(파일 기반 공격) 항목을 외부 데이터 경로 테스트에 넣어, 도구 결과물에 숨은 지시가 승인 없는 후속 호출로 이어지는지 확인한다.
- 네 가지 공격 범주를 게이트웨이 위협 분류 축으로 채택한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv 초록 페이지를 열어 확인했고 공격별 세부 결과와 실험 설정은 읽지 않았다. 초록에는 도구 선호 조작 공격이 명시되지 않아 그 주제의 근거로는 쓰지 않았다. 검색 스니펫의 표 값은 본문에서 확인하지 못해 인용하지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

arXiv non-exclusive 1.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
