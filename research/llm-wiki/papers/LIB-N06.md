# LIB-N06 · Runtime Authorization Consistency Checking for MCP-based Agentic Workflows

호출 하나씩은 허용되지만 이어 붙이면 세션의 권한 경계를 넘는 「인가 표류」를, 컨트롤러 쪽 호출 경계에서 이미 수락된 단계의 계보와 비교해 막는 RAC를 제안한다. 1,248개 워크플로우 벤치마크에서 놓친 차단이 없었다고 보고한다.

## 출처와 확인 수준

- 공식 출처: [Runtime Authorization Consistency Checking for MCP-based Agentic Workflows](https://arxiv.org/abs/2609.23498)
- 유형: preprint · 2026년 · arXiv preprint (제출 2026-09-20) · `preprint`
- 저자·발행: Aiyao Zhang, Xiaodong Lee, Zhixian Zhuang 외
- 확인일: 2026-10-23 / `arxiv_api_abstract_read`
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 가장 강한 정적+이력 기준선은 차단해야 할 1,008개 중 509개를 놓쳤고 RAC는 놓침이 없었다고 한다. 실제 MCP 파일시스템 재생에서 안전하지 않은 이어가기 9건을 서버 실행 전에 막았고 p99 지연이 1ms 미만이라고 보고한다.

## 우리 솔루션 개발에 사용할 곳

- MINT의 호출 순서 정책(P-CHAIN-001·P-FLOW-001)이 「직전 수락 단계보다 더 넓은 권한」을 막는지 시험 시나리오를 추가한다.
- 거부된 단계를 계보에서 빼는 규칙은 우리 호출 원장 설계와 직접 대응하므로 비교 대상으로 둔다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv API의 초록·서지만 읽었다. 본문·실험 조건(모델·서버 판본·반복·오탐·미탐)·재현은 확인하지 않았다. 수치는 저자 보고이며 우리 환경 값으로 쓰지 않는다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[출처 manifest](../analysis/refs-update-1023/refs-update-1023.sources.json) · [자료 확보 규칙](../methodology/source-protocol.md)
