# LIB-G03 · An Empirical Study of Model Context Protocol Applications

GitHub에서 수집한 MCP 애플리케이션(호스트 앱) 1,723개를 분석해 서버 설정 방식, 공식 SDK 사용, 사람 감독 장치(로그, 활성화 토글, 실행 전 승인)가 얼마나 쓰이는지 측정한다. 대부분의 앱에서 LLM이 활성화된 도구를 승인 없이 호출할 수 있는 구조라고 주장한다.

## 출처와 확인 수준

- 공식 출처: [An Empirical Study of Model Context Protocol Applications](https://arxiv.org/abs/2607.25635)
- 유형: preprint · 2026년 · arXiv preprint · `preprint`
- 저자·발행: Muhammad Hamza Arshad Majeed, May Mahmoud, Sarah Nadi
- 확인일: 2026-10-14 / `arxiv_api_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 분석한 앱의 약 85%가 서버 설정을 파일로 관리하고, 약 81%가 공식 SDK로 서버와 통신한다.
- 로깅(90.8%)과 활성·비활성 토글(77.2%)은 흔하지만, 실행 전 차단형 승인은 37.2%에 그쳐 대부분의 앱에서 LLM이 승인 없이 활성 도구를 호출할 수 있다.
- 설정 파일 이름에 공통 규칙이 생기지 않았다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이 정책의 승인 강제(require_approval)를 호스트 설정에 맡기지 않고 게이트웨이에서 직접 집행한다. 측정상 차단형 승인을 두는 앱이 약 37%에 그쳐 호스트 측 통제에 기대기 어렵다.
- 호스트마다 설정 파일이 흩어져 있고 명명 규칙이 없으므로, 게이트웨이의 서버 등록 목록을 단일 출처로 두는 근거로 쓴다.
- 로그는 대부분 앱에 있으므로, 게이트웨이 감사 원장에는 도구 호출 단위로 승인 여부와 승인자를 함께 남기는 설계가 필요하다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

WebFetch로 확인한 초록 수준의 수치만 반영했다. 전문은 미정독이며 호스트별(Claude Desktop, Cursor 등) 세부 결과는 확인하지 못했다. 2026년 7월 프리프린트다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

CC BY 4.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
