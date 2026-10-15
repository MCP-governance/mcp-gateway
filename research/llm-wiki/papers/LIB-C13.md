# LIB-C13 · Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection

LLM 통합 애플리케이션이 데이터와 명령의 경계를 흐려, 모델이 검색하는 외부 데이터에 공격자가 명령을 심을 수 있음을 보인다. 실제 시스템과 GPT-4 기반 앱에서 데이터 탈취와 자가 전파 같은 위험을 시연하고, 효과적인 완화책이 부족하다고 지적한다.

## 출처와 확인 수준

- 공식 출처: [Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection](https://arxiv.org/abs/2302.12173)
- 유형: preprint · 2023년 · arxiv.org · `preprint`
- 저자·발행: Kai Greshake, Sahar Abdelnabi, Shailesh Mishra, Christoph Endres 외
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 간접 주입이 실제 통합 앱에서 데이터 탈취와 자가 전파를 일으킬 수 있음을 시연했다고 보고한다.
- 당시 기준으로 효과적인 완화책이 부족하다고 결론짓는다.
- 공격이 모델에 검색되는 외부 데이터를 통해 원격으로 이루어진다는 위협 모델을 제시한다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이 위협 모델의 출발점으로 쓴다. 웹, 파일, 이슈 등 외부 데이터가 도구 응답으로 들어오는 모든 경로를 신뢰되지 않은 입력으로 분류한다.
- 자가 전파 시나리오를 평가 케이스로 추가한다. 도구 응답 속 주입이 다음 도구 호출의 인자로 복사되는지 감사 원장에서 추적하는 시험을 만든다.
- 데이터 탈취 시나리오는 PII 마스킹과 외부 전송 도구의 OPA 정책 조합으로 검증한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

초록 요약만 확인했고 본문은 읽지 않았다. 2023년 초 발표 자료라 이후의 방어 발전은 반영되지 않았다. 학회 게재 정보는 확인하지 못했다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

arXiv non-exclusive distribution license 1.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
