# LIB-N11 · Agent Approval Laundering: Transitive Effects Beyond the Approved Invocation

코딩 에이전트의 승인 기록이 진입 호출만 적고 그 호출이 일으키는 전이 효과(설치 훅, 네트워크 권한 등)를 빠뜨리는 「승인 세탁」을 측정 가능한 실패로 정의한다. 효과 단위로 묶은 승인과 벤치마크를 제안한다.

## 출처와 확인 수준

- 공식 출처: [Agent Approval Laundering: Transitive Effects Beyond the Approved Invocation](https://arxiv.org/abs/2609.28586)
- 유형: preprint · 2026년 · arXiv preprint (제출 2026-09-23) · `preprint`
- 저자·발행: Jinqian Zhang, Haojun Xia, Shujiang Wu 외
- 확인일: 2026-10-23 / `arxiv_api_abstract_read`
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 효과 구분 승인 기록으로 잔여 효과가 40건에서 13건으로 줄었다고 보고한다.

## 우리 솔루션 개발에 사용할 곳

- MINT의 승인·원장 기록에 「호출」뿐 아니라 「예상 효과」를 같이 남기는 항목을 검토한다.
- MCP 호출 하나가 네트워크 권한을 행사할 수 있다는 점은 대상 서버 외부 연결 통제(목적지 고정)와 함께 설명한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv API의 초록·서지만 읽었다. 본문·실험 조건(모델·서버 판본·반복·오탐·미탐)·재현은 확인하지 않았다. 수치는 저자 보고이며 우리 환경 값으로 쓰지 않는다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[출처 manifest](../analysis/refs-update-1023/refs-update-1023.sources.json) · [자료 확보 규칙](../methodology/source-protocol.md)
