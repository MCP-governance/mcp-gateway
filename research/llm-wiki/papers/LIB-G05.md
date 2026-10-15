# LIB-G05 · Model Context Protocol (MCP) at First Glance: Studying the Security and Maintainability of MCP Servers

오픈소스 MCP 서버 1,899개(공식 목록 343개와 GitHub 1,556개)를 범용 정적 분석기와 MCP 전용 스캐너로 점검해 보안과 유지보수성 실태를 측정한다. 건강 지표는 좋아 보이지만 기존 소프트웨어에 없는 MCP 고유 취약점 여러 종이 있다고 주장한다.

## 출처와 확인 수준

- 공식 출처: [Model Context Protocol (MCP) at First Glance: Studying the Security and Maintainability of MCP Servers](https://arxiv.org/abs/2506.13538)
- 유형: preprint · 2025년 · arXiv preprint · `preprint`
- 저자·발행: Mohammed Mehedi Hasan, Hao Li, Emad Fallahzadeh, Gopi Krishnan Rajbahadur 외
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 여덟 종의 취약점 중 세 종만 기존 소프트웨어 취약점과 겹치고, 나머지는 MCP 고유 문제다.
- 서버의 약 7.2%에 일반 취약점이, 약 5.5%에 MCP 특유의 도구 포이즈닝 패턴이 있다.
- 서버의 66%에 코드 스멜이 있고 14.4%에는 기존 오픈소스와 겹치는 버그 패턴 열 종이 있다.

## 우리 솔루션 개발에 사용할 곳

- 서버 허용 목록 심사 항목을 나눈다. 일반 취약점과 MCP 특유의 도구 포이즈닝 패턴을 따로 체크한다.
- 범용 정적 분석기와 MCP 전용 규칙을 함께 돌리는 2단 구조를 게이트웨이 심사 파이프라인 설계 참고로 쓴다.
- 코드 스멜과 버그 패턴 같은 유지보수성 지표를 서버 등록 시 참고 정보로 기록한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

WebFetch로 확인한 초록 수치만 반영했다. 저장소 기반 정적 분석 결과라 실제 배포 환경의 위험과는 차이가 있을 수 있다. 여러 버전이 있어 수치가 버전마다 다를 수 있다. 전문은 미정독이다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

CC BY-NC-SA 4.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
