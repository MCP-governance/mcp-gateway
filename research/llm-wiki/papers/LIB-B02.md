# LIB-B02 · ETDI: Mitigating Tool Squatting and Rug Pull Attacks in Model Context Protocol (MCP) by using OAuth-Enhanced Tool Definitions and Policy-Based Access Control

MCP 표준에는 도구 정의의 신원과 버전을 검증하는 수단이 부족해 Tool Poisoning과 rug pull이 가능하다고 주장한다. 서명된 도구 정의, 불변 버전, OAuth 기반 권한과 런타임 정책 엔진을 결합한 ETDI 확장을 제안한다.

## 출처와 확인 수준

- 공식 출처: [ETDI: Mitigating Tool Squatting and Rug Pull Attacks in Model Context Protocol (MCP) by using OAuth-Enhanced Tool Definitions and Policy-Based Access Control](https://arxiv.org/abs/2506.01333)
- 유형: preprint · 2025년 · arxiv.org · `preprint`
- 저자·발행: Manish Bhatt, Vineeth Sai Narajala, Idan Habler
- 확인일: 2026-10-14 / `full_text_selected_sections_read` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 전문의 선별 절을 읽고 확인했다.
- 읽은 PDF: https://arxiv.org/pdf/2506.01333 · SHA-256 `dac92180371101714e141160cb822a7ec86ca3fb7ee849e49930a206c6abf46a` (위키에는 보관하지 않음)
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- rug pull과 Tool Poisoning을 MCP 표준의 구조적 약점으로 규정한다.
- 서명 검증에 실패한 도구는 숨기거나, 경고를 띄우거나, 실행을 막을 수 있다는 처리 방식을 제시한다.
- 초록은 squatting을 제목에 두지만 구체 설명은 하지 않는다.

## 정독 메모

읽은 범위: 초록, MCP 구조·취약점 분석, ETDI 설계, 서명 검증 의사코드

- ETDI의 요소: (1) 공급자 공개키로 검증하는 도구 정의의 암호학적 신원·진본성, (2) 정의가 바뀔 때마다 새 서명 버전을 요구하는 불변·버전 정의, (3) 정의에 선언된 OAuth 범위 등 명시적 권한.
- 의사코드는 서명 검증 실패 시 도구를 거부하고, 승인된 버전과 같은 버전인데 내용이 다르면 변조로 보며, 새 버전이면 사용자 재승인을 요구한다.
- 정책 엔진(Cedar·OPA 언급) 기반 세밀한 접근 통제로 확장하는 제안을 덧붙인다. 본문에서 정량 성능 평가는 확인하지 못했다(선별 읽기).

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이가 도구 정의(이름·설명·스키마·버전)를 정규화해 해시나 서명과 함께 기록하고, 값이 바뀌면 계약 변경 탐지와 같은 흐름에서 승인 재요청을 띄운다.
- OPA 정책 입력에 도구의 출처 서버 ID와 버전을 넣어, 같은 이름이라도 등록되지 않은 서버의 도구는 호출을 거부하게 한다.
- 정책 엔진 개념을 참고해 도구 권한을 OAuth 스코프만이 아니라 호출 맥락(사용자, 인자, 직전 호출)으로 평가하는 규칙을 설계한다.
- 계약(도구 정의) 변경 탐지와 재승인 흐름의 개념 근거로 쓴다. 공급자 서명 인프라가 없는 공개 MCP 서버에는 그대로 적용할 수 없으므로 게이트웨이의 정의 해시 비교(A→B→A 일관성, DEV-12)가 현실적 대안인지 별도로 판단한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv 초록 페이지만 열어 확인했고 본문의 구현과 평가는 읽지 않았다. 검색 결과에서 본 PR이나 구현체 정보는 2차 자료라 검증하지 않았다. 도구 사칭(squatting) 세부 절은 확인하지 못했다. 2026-10-14에 arXiv PDF의 초록, MCP 구조·취약점 분석, ETDI 설계, 서명 검증 의사코드을 읽고 확인했다(PDF는 위키에 보관하지 않고 SHA-256만 기록). 전문 전체 정독·재현은 하지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

CC BY 4.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
