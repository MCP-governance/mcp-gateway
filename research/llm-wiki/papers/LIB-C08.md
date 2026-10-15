# LIB-C08 · PromptArmor: Simple yet Effective Prompt Injection Defenses

범용 LLM을 가드레일로 두고 에이전트 입력(도구 응답 포함)에서 주입 프롬프트를 탐지해 제거하는 방어 PromptArmor를 제안한다. 추가 학습 없이 기존 모델을 필터로 쓰는 것이 핵심 아이디어이다.

## 출처와 확인 수준

- 공식 출처: [PromptArmor: Simple yet Effective Prompt Injection Defenses](https://arxiv.org/abs/2507.15219)
- 유형: preprint · 2025년 · arxiv.org · `preprint`
- 저자·발행: Tianneng Shi, Kaijie Zhu, Zhun Wang, Yuqi Jia 외
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- AgentDojo에서 오탐률과 미탐률이 모두 낮고, 정화 후 공격 성공률이 매우 낮다고 보고한다(수치 생략).
- 적응형 공격에도 효과적이라고 주장하며, 새로운 주입 방어의 표준 기준선으로 쓰자고 제안한다.

## 우리 솔루션 개발에 사용할 곳

- 도구 응답 정화 단계에 가드레일 LLM 호출을 선택 기능으로 넣고, 지연과 비용 때문에 고위험 응답 유형에만 적용하도록 OPA 정책으로 설정한다.
- 가드레일 모델을 백엔드 모델과 다르게 둘 수 있다는 점을 활용해, 같은 계열 모델이 필터와 본체를 함께 뚫는 상관 위험을 줄이는 구성을 검토한다.
- 제거 전후 결과를 감사 원장에 남겨 오탐 검토와 임계값 조정 근거로 쓴다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

초록 요약만 확인했고 적응형 공격 실험 방법은 본문에서 확인하지 못했다. 결과가 주로 하나의 벤치마크(AgentDojo)에 기반하며, 적응형 평가 방법론이 강한지는 Attacker Moves Second 같은 연구와 비교해 재확인이 필요하다. 저자 목록은 일부만 기재했다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

arXiv non-exclusive distribution license 1.0 (페이지 링크 기준)

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
