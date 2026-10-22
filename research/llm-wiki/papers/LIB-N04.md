# LIB-N04 · Hybrid Semantic Tool Discovery for Enterprise MCP Gateway: Architecture and Implementation

게이트웨이 뒤 도구가 2,000개 이상이면 모델 문맥이 도구 설명으로 차 버리는 문제를, 도구 검색 메타 도구 두 개(검색·실행)로 바꾸는 SCOUT 구조로 푼 논문이다. PayPal 운영 환경에서 도구 토큰이 140.2k에서 1.3k로 줄었다고 저자가 보고한다.

## 출처와 확인 수준

- 공식 출처: [Hybrid Semantic Tool Discovery for Enterprise MCP Gateway: Architecture and Implementation](https://arxiv.org/abs/2608.23992)
- 유형: preprint · 2026년 · arXiv preprint (제출 2026-08-25) · `preprint`
- 저자·발행: Olympia Saha, Amy Wang, Srinivasan Manoharan
- 확인일: 2026-10-23 / `arxiv_api_abstract_read`
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- BM25와 밀집 벡터 검색을 합쳐 상위 k개 도구만 보여 주며 클라이언트 수정이 필요 없다고 밝힌다. 99% 감소는 저자가 보고한 PayPal 운영 수치다.

## 우리 솔루션 개발에 사용할 곳

- MINT 서버별 엔드포인트 구조에서 도구 수가 많은 서버를 점진 노출할 때, 검색 도구도 정책 판정 대상에 넣어야 한다는 설계 요구로 쓴다.
- 토큰 절감 수치는 저자 측정이므로 우리 환경 수치로 쓰지 않는다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv API의 초록·서지만 읽었다. 본문·실험 조건(모델·서버 판본·반복·오탐·미탐)·재현은 확인하지 않았다. 수치는 저자 보고이며 우리 환경 값으로 쓰지 않는다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[출처 manifest](../analysis/refs-update-1023/refs-update-1023.sources.json) · [자료 확보 규칙](../methodology/source-protocol.md)
