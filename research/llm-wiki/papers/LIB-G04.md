# LIB-G04 · A First Look at the Security Issues in the Model Context Protocol Ecosystem

여섯 개 공개 레지스트리의 MCP 서버 67,057개를 조사해, 등록 단계의 검증 부실과 통합 후 도구 메타데이터가 LLM 추론을 조종하는 두 단계 공격 표면을 보인다. 통합 전 검사 도구 MCPInspect를 만들어 코드 취약점과 오해 소지 있는 메타데이터를 함께 탐지한다.

## 출처와 확인 수준

- 공식 출처: [A First Look at the Security Issues in the Model Context Protocol Ecosystem](https://arxiv.org/abs/2510.16558)
- 유형: preprint · 2025년 · arXiv preprint · `preprint`
- 저자·발행: Xiaofan Li, Xing Gao
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 레지스트리의 검증과 소유권 확인이 약해, 적대적이거나 탈취된 서버가 호스트에 도달할 수 있다.
- 통합 후에는 공격자가 통제하는 도구 메타데이터가 LLM 추론에 영향을 줄 수 있다.
- MCPInspect가 취약 서버 833개와 의심스러운 설명 18개를 찾았다고 보고한다(초록 기준).

## 우리 솔루션 개발에 사용할 곳

- 서버 등록 시점 검사 게이트를 둔다. 레지스트리에서 가져온 서버의 도구 설명(지시문 패턴)과 코드 취약점을 연결 전에 검사하고, 실패하면 등록을 거부한다.
- 레지스트리 단계의 소유권·출처 검증이 약하다는 근거로, 게이트웨이 등록 시 패키지 출처와 발행자 정보를 기록하고 이름 유사 서버에 경고를 띄운다.
- 통합 후에도 도구 메타데이터 변경을 계약 변경으로 보고, 설명 속 지시문이 바뀌면 재심사로 보낸다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

초록 수준의 수치만 확인했다. 검색 요약에는 mcp.so 기준 취약 서버 377개와 수동 검증 41개라는 다른 수치가 있어 버전(v1, v2) 차이가 있을 수 있으니 전문에서 대조해야 한다. 전문은 미정독이다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

CC BY 4.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
