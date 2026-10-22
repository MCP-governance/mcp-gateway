# LIB-N25 · MCP Security Bench (MSB): Benchmarking Attacks Against Model Context Protocol in LLM Agents

MCP 파이프라인 전 단계(계획·호출·응답)의 공격 12종을 실제 도구로 실행해 재는 MSB 벤치마크다. 9개 모델·10개 영역·도구 405개, 공격 인스턴스 2,000개이며 보안과 성능의 균형 지표 NRP를 제안한다.

## 출처와 확인 수준

- 공식 출처: [MCP Security Bench (MSB): Benchmarking Attacks Against Model Context Protocol in LLM Agents](https://arxiv.org/abs/2510.15994)
- 유형: preprint · 2025년 · arXiv preprint (제출 2025-10-14); ICLR 2026 채택(arXiv 주석 기준, 논문집 판본 미확인) · `preprint`
- 저자·발행: Dongsen Zhang, Zekun Li, Xu Luo 외
- 확인일: 2026-10-23 / `arxiv_api_abstract_read`
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 성능이 높은 모델일수록 공격에 더 취약하다고 보고한다.

## 우리 솔루션 개발에 사용할 곳

- MINT가 이미 보유한 MCPSecBench 계열 벤치마크와 보완적으로 쓸 수 있는 실행형 공격 시험 목록이다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv API의 초록·서지만 읽었다. 본문·실험 조건(모델·서버 판본·반복·오탐·미탐)·재현은 확인하지 않았다. 수치는 저자 보고이며 우리 환경 값으로 쓰지 않는다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[출처 manifest](../analysis/refs-update-1023/refs-update-1023.sources.json) · [자료 확보 규칙](../methodology/source-protocol.md)
