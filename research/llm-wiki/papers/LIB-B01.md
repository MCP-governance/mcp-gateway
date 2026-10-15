# LIB-B01 · MCP Security Notification: Tool Poisoning Attacks

MCP 도구 설명에 사용자에게는 보이지 않고 모델에게만 보이는 숨은 지시를 넣어 데이터를 빼내는 Tool Poisoning을 시연한 보안 공지다. 같은 글에서 승인 뒤 설명을 바꾸는 rug pull과, 한 서버의 설명이 신뢰된 다른 서버 도구의 사용 방식을 바꾸는 tool shadowing도 다룬다.

## 출처와 확인 수준

- 공식 출처: [MCP Security Notification: Tool Poisoning Attacks](https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks)
- 유형: 도구 문서 · 2025년 · Invariant Labs 블로그 · `official_publication`
- 저자·발행: Luca Beurer-Kellner, Marc Fischer (Invariant Labs)
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 도구 설명에 숨긴 지시가 모델에는 보이고 사용자에게는 보이지 않아, 설치자가 목록을 승인해도 파일 읽기 후 인자로 유출하는 시나리오를 보였다.
- rug pull은 승인 뒤 tools/list 변경 알림으로 설명이 바뀌는 형태로 설명하며, 버전과 해시 고정을 완화책으로 든다.
- shadowing은 악성 서버 설명이 신뢰된 이메일 도구의 동작을 바꿔 수신자를 공격자 쪽으로 돌리는 예시로 설명한다.

## 우리 솔루션 개발에 사용할 곳

- tools/list 응답의 이름·설명·스키마를 해시로 고정하고, 승인 시점과 달라지면 차단하거나 재승인을 요구하도록 게이트웨이의 계약 변경 탐지에 넣는다. 글이 권장하는 버전·해시 고정과 같은 방향이다.
- 도구 설명 전문과 변경 이력을 감사 원장에 남겨, 사람이 보지 못한 숨은 지시가 어떤 호출에 영향을 줬는지 사후에 추적할 수 있게 한다.
- 서버 간 데이터 흐름 제한(한 서버 결과를 다른 서버 도구의 송신 인자로 넘기는 경로)을 OPA 정책 입력으로 설계한다. 글이 강화를 권장한 항목이다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

공지 페이지를 열어 제목·게시일(2025-04-01)·주요 내용을 확인했고, 본문 전체를 원문으로 대조하지는 않았다. 블로그 글이라 동료 심사 자료는 아니다. 2차 자료 일부가 shadowing 공개 날짜를 다르게 말하지만 확인하지 못했다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
