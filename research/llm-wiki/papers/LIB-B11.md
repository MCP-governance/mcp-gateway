# LIB-B11 · MCP-ITP: An Automated Framework for Implicit Tool Poisoning in MCP

악성 도구는 한 번도 호출되지 않고, 메타데이터 지시가 에이전트를 권한이 높은 정상 도구로 유도하는 암묵적 도구 오염(implicit tool poisoning)을 정의한다. 탐지 LLM과 평가 LLM의 피드백을 쓰는 블랙박스 자동화 프레임워크 MCP-ITP를 제안하며, 탐지를 피하면서 공격 성공을 높인다고 주장한다.

## 출처와 확인 수준

- 공식 출처: [MCP-ITP: An Automated Framework for Implicit Tool Poisoning in MCP](https://arxiv.org/abs/2601.07395)
- 유형: preprint · 2026년 · arxiv.org · `preprint`
- 저자·발행: Ruiqi Li, Zhiqiang Wang, Yunhao Yao, Xiang-Yang Li
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 악성 도구가 호출되지 않아도 메타데이터 지시가 고권한 정상 도구의 악용으로 이어질 수 있다고 주장한다.
- MCPTox 데이터셋 실험에서 수동 작성 기준선보다 우수하다고 보고한다.
- 탐지 LLM을 회피하면서 공격 성공을 높이도록 최적화된다고 밝힌다.

## 우리 솔루션 개발에 사용할 곳

- 도구 목록 점검에서 설명 안에 다른 고권한 도구 이름이나 기능을 지시하는 문구를 탐지 규칙으로 추가한다.
- 파일 쓰기, 결제, 외부 전송 같은 고권한 도구는 호출 주체와 무관하게 OPA에서 사용자 승인 조건을 걸어, 간접 유도로 호출되어도 막히게 한다.
- 악성 도구가 호출되지 않아도 피해가 날 수 있으므로, 실행 로그에 더해 도구 목록 변경과 고권한 호출의 연쇄를 함께 기록한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv 초록 페이지를 열어 확인했고 실험 대상 모델 수와 수치는 읽지 않았다. 수치는 적지 않았다. 학회 게재 여부는 확인하지 못했다. 이 논문은 MCPTox 데이터셋을 쓰므로, MCPTox 자체는 이 목록에서 제외했다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

arXiv non-exclusive 1.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
