# LIB-G01 · Rethinking MCP Security: A Large-Scale Study of Runtime MCP Servers and Security Scanner Reliability

MCP 서버 64,611개(MCPZoo)를 모아 여러 보안 스캐너를 대규모로 돌려 본 실증 연구다. 스캐너들이 서버의 약 97%를 위험으로 판정했지만, 수동 검증에서는 샘플 경고의 50% 미만만 실제 취약점이었고 스캐너 간 결과도 일관되지 않았다고 주장한다.

## 출처와 확인 수준

- 공식 출처: [Rethinking MCP Security: A Large-Scale Study of Runtime MCP Servers and Security Scanner Reliability](https://arxiv.org/abs/2607.11086)
- 유형: preprint · 2026년 · arXiv preprint · `preprint`
- 저자·발행: Pei Chen, Baichao An, Mengying Wu, Binwang Wan 외
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 조사된 서버의 약 97%가 스캐너에 의해 위험으로 판정되었지만, 수동 검증에서 샘플 경고의 50% 미만만 실제 위험이었다.
- 스캐너 간 판정이 일관되지 않아 단일 스캐너 결과를 신뢰 기준으로 쓰기 어렵다고 결론짓는다.
- MCPZoo는 고유 서버 64,611개(전체 113,927개) 규모이며, 그중 37,288개 이상이 동적 분석이 가능하다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이가 외부 스캐너 결과를 곧바로 자동 차단 규칙으로 쓰지 않도록 설계하고, 스캐너 판정은 의심 등급으로만 받아 승인 단계의 사람 검토 입력으로 연결한다.
- 여러 스캐너의 결과 일치율을 서버 심사 지표로 기록해 감사 원장에 남기고, 단일 스캐너 판정에 의존하지 않도록 한다.
- 서버 등록 심사를 정적 경고 후 실행 증거 확인의 2단계로 나누는 근거로 인용한다(FlowGuard와 조합).

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

WebFetch로 열어 제목·저자·날짜·ID를 확인했고 초록 수준의 수치만 반영했다. 초록에 평가한 스캐너 개수가 없어 확인하지 못했다. 전문은 미정독이며 2026년 7월 프리프린트로 동료 심사 전 자료다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

CC BY-NC-ND 4.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
