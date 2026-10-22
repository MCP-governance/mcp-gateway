# LIB-N19 · What a Random Draw from the MCP Registry Contains, and What Tool-Use Benchmarks Contain Instead

레지스트리 전수 24,135개 중 npm/stdio 400개를 무작위로 뽑아 실제로 연결해 보니 초기화에 성공한 서버가 48.8%뿐이었고, 도구 안전 주석 누락률도 선별 표본보다 높았다. 도구 사용 벤치마크는 실제 MCP 도구와 분포가 다르다고도 보인다.

## 출처와 확인 수준

- 공식 출처: [What a Random Draw from the MCP Registry Contains, and What Tool-Use Benchmarks Contain Instead](https://arxiv.org/abs/2609.10962)
- 유형: preprint · 2026년 · arXiv preprint (제출 2026-09-10) · `preprint`
- 저자·발행: Haseeb Mohammed Afsar
- 확인일: 2026-10-23 / `arxiv_api_abstract_read`
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 도구 수준 안전 주석 누락률이 무작위 표본 58.8%, 선별 표본 41.5%였다고 보고한다.

## 우리 솔루션 개발에 사용할 곳

- MINT 도입 심사가 「아예 기동하지 않는 서버」와 안전 주석 누락을 정상 경로의 실패로 다루는지 확인한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv API의 초록·서지만 읽었다. 본문·실험 조건(모델·서버 판본·반복·오탐·미탐)·재현은 확인하지 않았다. 수치는 저자 보고이며 우리 환경 값으로 쓰지 않는다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[출처 manifest](../analysis/refs-update-1023/refs-update-1023.sources.json) · [자료 확보 규칙](../methodology/source-protocol.md)
