# LIB-D11 · ShieldAgent: Shielding Agents via Verifiable Safety Policy Reasoning

다른 에이전트의 행동 궤적을 안전 정책에 비추어 검사하는 가드레일 에이전트 ShieldAgent를 제안한다. 정책 문서에서 규칙 회로를 만들고 검증 가능한 코드로 차단 계획을 세우며, 에이전트 가드레일 벤치마크 ShieldAgent-Bench도 함께 공개한다.

## 출처와 확인 수준

- 공식 출처: [ShieldAgent: Shielding Agents via Verifiable Safety Policy Reasoning](https://arxiv.org/abs/2503.22738)
- 유형: preprint · 2025년 · arXiv preprint (v2 2025-11-27; ICML 2025 목록은 mlanthology 기준) · `venue_reported_unverified`
- 저자·발행: Zhaorun Chen, Mintong Kang, Bo Li
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- ShieldAgent-Bench(6개 웹 환경·7개 위험 범주에서 수집한 지시–행동 궤적 쌍 3천 개)를 함께 공개한다.
- 자체 벤치마크와 기존 벤치마크 3종에서 이전 방법보다 평균 11.3% 높고 재현율 90.1%이며, API 질의를 64.7%, 추론 시간을 58.2% 줄였다고 보고한다(저자 보고).

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이 정책 검사 단위를 단일 호출에서 호출 시퀀스로 넓힐 때 설계를 참고한다. 행동 유형별로 규칙을 묶는 방식이 정책 그룹화 기준이 된다.
- LLM 기반 가드는 확률적이므로, 결정론적 OPA 집행을 최종 판정으로 두고 이런 가드는 감사와 경고용 보조 탐지기로 배치하는 구성의 근거로 쓴다.
- ShieldAgent-Bench의 시나리오 구성 방식을 정책 회귀 테스트 입력 설계에 참고한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

초록만 확인했고 전문은 정독하지 못했다. v2 수치가 바뀌었는지 확인하지 못했다. 벤치마크가 웹 환경 중심이라 MCP 도구 호출 환경과 차이가 있을 수 있다. 학회 게재 정보는 arXiv 페이지에 없고 제3자 목록에만 있다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
