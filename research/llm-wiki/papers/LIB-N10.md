# LIB-N10 · Approve What, Exactly? Effect Binding and Trusted Rendering for Agent Step-Up Authorization

에이전트가 돈을 보내거나 파일을 지우기 전에 받는 사람 승인이 진짜 제2요소가 되려면 에이전트가 만들 수 없고 정확히 무엇을 승인하는지 드러나야 한다고 보고, 승인 경로 공격 12가지를 정의해 AP2·Microsoft 방식·MCP elicitation에 적용한다. 승인 카드를 게이트웨이가 정규 효과 기술자로 만들고 패스키로 서명하는 ASU를 제안한다.

## 출처와 확인 수준

- 공식 출처: [Approve What, Exactly? Effect Binding and Trusted Rendering for Agent Step-Up Authorization](https://arxiv.org/abs/2610.21063)
- 유형: preprint · 2026년 · arXiv preprint (제출 2026-10-15) · `preprint`
- 저자·발행: Sai Varun Kodathala, Prashanth Pollishetty, Jaylen Cargill
- 확인일: 2026-10-23 / `arxiv_api_abstract_read`
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 에이전트 런타임 10종 감사에서 제3자가 검증할 승인 기록이 없었고, 측정 가능했던 8종 중 4종에서 승인 뒤 인자 변경이 있었다고 한다. 신뢰 카드가 공격 포착률을 0.30에서 0.98로 올렸다고 보고한다.

## 우리 솔루션 개발에 사용할 곳

- MINT의 동의·승인 화면이 호출 인자(수신자·금액 등)를 정규화해 보여 주고 승인 후 인자 변경을 막는지 점검 항목으로 쓴다.
- 승인 홍수·자동 승인 모델이 쉽게 속는다는 결과를 승인 UI 설계(요약·일괄 처리)의 위험 근거로 쓴다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv API의 초록·서지만 읽었다. 본문·실험 조건(모델·서버 판본·반복·오탐·미탐)·재현은 확인하지 않았다. 수치는 저자 보고이며 우리 환경 값으로 쓰지 않는다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[출처 manifest](../analysis/refs-update-1023/refs-update-1023.sources.json) · [자료 확보 규칙](../methodology/source-protocol.md)
