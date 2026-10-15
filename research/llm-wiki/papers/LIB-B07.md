# LIB-B07 · MindGuard: Intrinsic Decision Inspection for Securing LLM Agents Against Metadata Poisoning

도구 메타데이터 오염은 도구가 실행되지 않아도 피해를 낼 수 있어 행동 기반 감시로는 잡기 어렵다고 주장한다. 모델 어텐션으로 결정 의존 그래프를 만들어 이상 호출을 탐지하고 오염 출처를 추적하는 MindGuard를 제안한다.

## 출처와 확인 수준

- 공식 출처: [MindGuard: Intrinsic Decision Inspection for Securing LLM Agents Against Metadata Poisoning](https://arxiv.org/abs/2508.20412)
- 유형: preprint · 2025년 · arxiv.org · `preprint`
- 저자·발행: Zhiqiang Wang, Haohua Du, Guanquan Shi, Junyang Zhang 외
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 행동 기반 방어는 실행 흔적이 없는 메타데이터 오염에 취약하다는 문제를 제기한다.
- 결정 의존 그래프와 이상 탐지로 오염 호출을 찾고 출처를 추적할 수 있다고 주장한다.
- 추가 토큰 비용 없이 실시간에 가깝게 동작한다고 보고한다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이는 모델 내부 어텐션에 접근할 수 없어 MindGuard를 그대로 쓸 수 없다. 설명 문구가 호출 인자에 그대로 나타나는지 같은 외부 근사 신호로 줄일 수 있는지 검증 과제로 둔다.
- 오염된 호출을 출처 도구와 서버 ID와 함께 감사 원장에 남기는 출처 귀속 필드 설계에 참고한다.
- 도구 선택에 쓰인 설명 근거를 호출 단위 로그로 모아, 사후 분석에서 어떤 설명이 결정에 기여했는지 재구성할 수 있게 한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv 초록 페이지를 열어 확인했고 본문 방법은 읽지 않았다. 버전마다 정밀도 수치가 달라 수치는 적지 않았다. 모델 내부 접근을 전제하므로 외부 게이트웨이 적용 가능성은 별도 검토가 필요하다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

arXiv non-exclusive 1.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
