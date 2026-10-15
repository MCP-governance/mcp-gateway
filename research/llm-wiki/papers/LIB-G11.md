# LIB-G11 · Unsafe by Flow: Uncovering Bidirectional Data-Flow Risks in MCP Ecosystem

MCP 서버에서 요청자가 준 인자가 민감 연산으로 흐르는 방향과, 도구 출력이 외부로 새는 방향을 모두 보는 양방향 정적 분석 프레임워크 MCP-BiFlow를 제안한다. 대규모 저장소를 분석해 실제 취약 경로를 수동 검토로 확인했다고 보고한다.

## 출처와 확인 수준

- 공식 출처: [Unsafe by Flow: Uncovering Bidirectional Data-Flow Risks in MCP Ecosystem](https://arxiv.org/abs/2605.07836)
- 유형: preprint · 2026년 · arXiv preprint · `preprint`
- 저자·발행: Xinyi Hou, Yanjie Zhao, Haoyu Wang
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 자체 벤치마크 32건 중 30건을 찾아 재현율이 높다고 보고했으며, CodeQL, Semgrep, Snyk Code, MCPScan보다 우위라고 자가 보고했다.
- 15,452개 저장소를 분석해 87개 서버에서 118개의 취약 경로가 수동 검토로 확인되었다.
- 요청자 인자가 민감 연산으로 가는 흐름과 도구 출력이 외부로 나가는 흐름이 모두 위험이 될 수 있음을 보인다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이 PII 마스킹과 정책 검사의 적용 위치를 입력 방향뿐 아니라 도구 응답이 LLM 컨텍스트로 나가는 출력 방향까지 포함하도록 설계하는 근거로 쓴다.
- 서버 심사용 정적 분석 도구 후보로 평가하되, 저자 벤치마크 결과이므로 자체 샘플로 재측정한 뒤 도입한다.
- 도구 출력의 민감도 라벨을 OPA 정책 입력에 포함하는 설계의 근거로 삼는다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

WebFetch 요약으로 확인한 초록 수준만 반영했다. 비교 결과는 저자 벤치마크에 근거한 자가 보고다. 전문은 미정독이며 2026년 5월 프리프린트다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

arXiv non-exclusive distribution license 1.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
