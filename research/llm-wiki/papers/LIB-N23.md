# LIB-N23 · Invisible Threats from Model Context Protocol: Generating Stealthy Injection Payload via Tree-based Adaptive Search

도구 응답에 숨기는 간접 주입 페이로드를 트리 기반 적응 탐색으로 만들어 방어를 우회하는 공격 TIP을 제시한다. 방어 없는 환경에서 95% 이상, 대표 방어 4종 앞에서도 50% 이상 성공했다고 보고한다.

## 출처와 확인 수준

- 공식 출처: [Invisible Threats from Model Context Protocol: Generating Stealthy Injection Payload via Tree-based Adaptive Search](https://arxiv.org/abs/2603.24203)
- 유형: preprint · 2026년 · arXiv preprint (제출 2026-03-25) · `preprint`
- 저자·발행: Yulin Shen, Xudong Pan, Geng Hong 외
- 확인일: 2026-10-23 / `arxiv_api_abstract_read`
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 실제 MCP 시스템에 구현해 공격이 통했다고 밝힌다. 모델·서버 판본은 초록에 없다.

## 우리 솔루션 개발에 사용할 곳

- MINT 응답 검사 시험에 적응형 페이로드를 쓸 때 방어를 학습하는 공격자를 가정해야 하며, 결정적 정책이 그 뒤를 받치는 구조라는 점을 보고에 명시한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv API의 초록·서지만 읽었다. 본문·실험 조건(모델·서버 판본·반복·오탐·미탐)·재현은 확인하지 않았다. 수치는 저자 보고이며 우리 환경 값으로 쓰지 않는다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[출처 manifest](../analysis/refs-update-1023/refs-update-1023.sources.json) · [자료 확보 규칙](../methodology/source-protocol.md)
