# LIB-N07 · ACLE-MCP: Attested Capability Leases for Execution-Time Trust in Remote LLM Tool Use

원격 MCP에서 OAuth 승인만으로는 나중 호출을 처리하는 서버 쪽 워크로드가 처음 신뢰한 대상인지 보장하지 못하는 「승인 후 실행 신뢰 간극」을 다룬다. 호출 단위의 짧은 수명·송신자 제약 임대와 서버 쪽 실행 관문을 제안한다.

## 출처와 확인 수준

- 공식 출처: [ACLE-MCP: Attested Capability Leases for Execution-Time Trust in Remote LLM Tool Use](https://arxiv.org/abs/2609.02690)
- 유형: preprint · 2026년 · arXiv preprint (제출 2026-09-02) · `preprint`
- 저자·발행: Zhiyang Ding, Yang Luo, Guangpu Chen 외
- 확인일: 2026-10-23 / `arxiv_api_abstract_read`
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- Keycloak·MCP Python SDK·vTPM 인용 검증 프로토타입에서 평가한 공격군을 모두 막았고 정상 작업 p95 지연이 OAuth 단독 대비 25.7% 늘었다고 밝힌다.

## 우리 솔루션 개발에 사용할 곳

- MINT가 직접 운영하지 않는 외부 원격 MCP를 업스트림으로 쓸 때 남는 신뢰 한계를 문서화하는 근거로 쓴다.
- 온프레미스 우선 정책에서는 원격 MCP 자체를 제한하는 편이 먼저이며 이 구조는 고객 선택 기능 후보로만 둔다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv API의 초록·서지만 읽었다. 본문·실험 조건(모델·서버 판본·반복·오탐·미탐)·재현은 확인하지 않았다. 수치는 저자 보고이며 우리 환경 값으로 쓰지 않는다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[출처 manifest](../analysis/refs-update-1023/refs-update-1023.sources.json) · [자료 확보 규칙](../methodology/source-protocol.md)
