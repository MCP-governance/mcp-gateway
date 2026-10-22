# LIB-N24 · Breaking the Protocol: Security Analysis of the Model Context Protocol Specification and Prompt Injection Vulnerabilities in Tool-Integrated LLM Agents

MCP 명세 자체를 분석해 능력 증명 부재, 방향 없는 sampling, 다중 서버 암묵 신뢰의 세 구조 취약점을 지적한다. 기능 확장 MCPSec이 공격 성공률을 52.8%에서 12.4%로 낮췄다고 보고한다.

## 출처와 확인 수준

- 공식 출처: [Breaking the Protocol: Security Analysis of the Model Context Protocol Specification and Prompt Injection Vulnerabilities in Tool-Integrated LLM Agents](https://arxiv.org/abs/2601.17549)
- 유형: preprint · 2026년 · arXiv preprint (제출 2026-01-24) · `preprint`
- 저자·발행: Narek Maloyan, Dmitry Namiot
- 확인일: 2026-10-23 / `arxiv_api_abstract_read`
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- MCP 구조 선택이 동등한 비MCP 통합보다 공격 성공률을 23~41% 키웠다고 주장한다.

## 우리 솔루션 개발에 사용할 곳

- 새 명세(2026-07-28)가 sampling을 폐기 예정으로 돌렸으므로 이 논문의 sampling 지적은 신규 배포 기준 영향이 줄었다는 점을 정정 메모로 남긴다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv API의 초록·서지만 읽었다. 본문·실험 조건(모델·서버 판본·반복·오탐·미탐)·재현은 확인하지 않았다. 수치는 저자 보고이며 우리 환경 값으로 쓰지 않는다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[출처 manifest](../analysis/refs-update-1023/refs-update-1023.sources.json) · [자료 확보 규칙](../methodology/source-protocol.md)
