# LIB-N15 · Persistent Billable State: Denial-of-Wallet Attacks and Defenses in Tool-Calling LLM Agents

도구 응답을 대화 기록으로 보존하면 공급자가 매번 다시 과금해, 침해된 도구가 피해자 비용을 키울 수 있는 「지갑 서비스 거부」를 체계화한다. 호스트 쪽 불변식 네 가지로 프롬프트 질량·문맥 증가·재귀·누적 비용을 묶는다.

## 출처와 확인 수준

- 공식 출처: [Persistent Billable State: Denial-of-Wallet Attacks and Defenses in Tool-Calling LLM Agents](https://arxiv.org/abs/2609.28585)
- 유형: preprint · 2026년 · arXiv preprint (제출 2026-09-23) · `preprint`
- 저자·발행: Jinqian Zhang, Haojun Xia, Shujiang Wu 외
- 확인일: 2026-10-23 / `arxiv_api_abstract_read`
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 세션 누적 입력이 첫 호출의 14,293배까지 늘었고, 코드에서 보이는 방어 장치를 가진 서버·전송 저장소는 3,830개 중 71개였다고 보고한다.

## 우리 솔루션 개발에 사용할 곳

- MINT의 응답 크기 상한과 멱등성 규칙(response-cap)이 비용 증폭 관점에서도 유효한지 점검 항목으로 쓴다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv API의 초록·서지만 읽었다. 본문·실험 조건(모델·서버 판본·반복·오탐·미탐)·재현은 확인하지 않았다. 수치는 저자 보고이며 우리 환경 값으로 쓰지 않는다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[출처 manifest](../analysis/refs-update-1023/refs-update-1023.sources.json) · [자료 확보 규칙](../methodology/source-protocol.md)
