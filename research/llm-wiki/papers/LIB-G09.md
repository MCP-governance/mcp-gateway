# LIB-G09 · FlowGuard: From Signals to Evidence for MCP Security Detection

MCP 보안 탐지기 FlowGuard를 제안하며, 의미 기반 위험 후보를 먼저 찾은 뒤 스키마에 맞는 프로브를 실제로 실행해 실행 증거로 위험을 확정한다. 자체 구축한 실행형 벤치마크와 실제 서버 평가에서 기존 동적 스캐너보다 지연 시간이 짧고 실행 관련 위험 탐지가 높다고 보고한다.

## 출처와 확인 수준

- 공식 출처: [FlowGuard: From Signals to Evidence for MCP Security Detection](https://arxiv.org/abs/2607.14754)
- 유형: preprint · 2026년 · arXiv preprint · `preprint`
- 저자·발행: Baichao An, Pei Chen, Geng Hong, Yueyue Chen 외
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 명령 주입과 파일 시스템 접근 범주에서 자체 벤치마크 기준 F1이 높게 보고되었다(자가 보고).
- 실제 서버 평가에서 326개 서버에 대해 523건의 탐지 결과를 보고했다.
- 의미 기반 신호만으로는 위험을 확정하기 어렵다는 문제를 제기하고, 실행 증거로 확정하는 접근을 제안한다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이 서버 심사를 두 단계로 나눈다. 정적 의미 경고는 의심으로만 기록하고, 샌드박스에서 실행 증거가 확인된 경우에만 차단한다.
- 명령 주입과 파일 접근 같은 실행성 위험은 샌드박스 프로브를 게이트웨이 회귀 테스트에 편입한다.
- 실행 증거(입력, 출력, 실행 로그)를 감사 원장 항목으로 저장해 차단 사유를 설명할 수 있게 한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

자체 구축한 벤치마크 결과이므로 외부 검증이 없다. WebFetch 요약으로 확인한 초록 수준 내용만 반영했고 전문은 미정독이다. 2026년 7월 프리프린트다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

CC BY-NC-ND 4.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
