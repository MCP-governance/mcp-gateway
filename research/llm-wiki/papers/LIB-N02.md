# LIB-N02 · Zero-Trust Authorization and Discovery for Enterprise MCP

공식 SDK 6종의 인증·인가 기본 기능을 기업 제로트러스트 관점에서 점검하고, 한 서버가 사람(SSO)과 자동 에이전트(서비스 계정)를 함께 받을 때의 빈틈을 FastMCP 확장으로 메운 논문이다. 허용되지 않은 도구를 목록에서 가리는 방식과 호출 때 막는 방식을 함께 쓰면 노출률이 0으로 내려갔다고 보고한다.

## 출처와 확인 수준

- 공식 출처: [Zero-Trust Authorization and Discovery for Enterprise MCP](https://arxiv.org/abs/2609.22573)
- 유형: preprint · 2026년 · arXiv preprint (제출 2026-09-18) · `preprint`
- 저자·발행: Huan Li, Yuwei Wang, Srinivasan Manoharan
- 확인일: 2026-10-23 / `arxiv_api_abstract_read`
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 본문 검사만 둔 서버는 4개 모델·2,160회 시도에서 금지 도구가 21.1% 노출됐고, 권한 인식 목록 노출을 더하면 0이었다고 밝힌다. 목록만 거른 경우는 스크립트 클라이언트가 우회할 수 있었다고 한다.

## 우리 솔루션 개발에 사용할 곳

- MINT가 도구 목록(`tools/list`)을 주체별로 거르는 방식과 호출 시 판정이 같은 규칙에서 나오는지 점검 항목으로 쓴다.
- 목록 숨김만으로는 스크립트 클라이언트가 우회할 수 있다는 결과를 「목록 필터는 보조, 집행은 호출 판정」 원칙의 근거로 인용한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv API의 초록·서지만 읽었다. 본문·실험 조건(모델·서버 판본·반복·오탐·미탐)·재현은 확인하지 않았다. 수치는 저자 보고이며 우리 환경 값으로 쓰지 않는다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[출처 manifest](../analysis/refs-update-1023/refs-update-1023.sources.json) · [자료 확보 규칙](../methodology/source-protocol.md)
