# LIB-G12 · When MCP Servers Attack: Taxonomy, Feasibility, and Mitigation

악성 MCP 서버의 공격을 구성 요소 기준 12개 범주로 분류하고, 범주마다 개념 증명용 악성 서버를 만들어 실제 호스트-LLM 환경에서 가능성을 시험한다. 공격자가 거의 비용 없이 악성 서버를 대량으로 만들 수 있으며 기존 탐지 방식은 불충분하다고 주장한다.

## 출처와 확인 수준

- 공식 출처: [When MCP Servers Attack: Taxonomy, Feasibility, and Mitigation](https://arxiv.org/abs/2509.24272)
- 유형: preprint · 2025년 · arXiv preprint · `preprint`
- 저자·발행: Weibo Zhao, Jiahao Liu, Bonan Ruan, Shaofei Li 외
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 구성 요소 기준의 12개 공격 범주 taxonomy를 제시하고, 범주별로 개념 증명 악성 서버를 구현했다.
- 여러 실제 호스트-LLM 환경에서 공격이 가능함을 보였다고 보고한다.
- 기존 탐지 접근법이 충분하지 않다고 결론짓고, 특정 방어책보다는 관계자 공동 대응을 촉구한다.

## 우리 솔루션 개발에 사용할 곳

- 12개 공격 범주를 게이트웨이 정책과 탐지 회귀 테스트 케이스로 옮기고, 범주마다 차단 규칙이 있는지 검증하는 매트릭스를 만든다.
- 대량 생성이 쉽다는 근거로 서버 등록을 출처 서명과 심사 통과가 있는 경우로 제한하는 정책 근거로 쓴다.
- 기존 탐지가 불충분하다는 결론에 따라 정적 탐지에만 의존하지 않고, 런타임 정책(OPA)과 승인을 함께 두는 설계 근거로 쓴다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

WebFetch 요약으로 확인한 초록 수준만 반영했다. 초록에는 구체적인 방어 기법이 없다. 전문은 미정독이며 PoC 세부는 확인하지 못했다. 2025년 9월 프리프린트다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

CC BY 4.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
