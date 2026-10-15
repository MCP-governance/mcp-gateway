# LIB-B06 · Attractive Metadata Attack: Inducing LLM Agents to Invoke Malicious Tools

프롬프트 인젝션 없이 도구의 이름, 설명, 파라미터 스키마만 조작해 에이전트가 악성 도구를 고르게 만드는 블랙박스 공격 AMA를 제안한다. 이 공격은 프롬프트 수준 방어, 감사기 기반 탐지, MCP 같은 구조적 도구 선택 프로토콜에서도 여전히 통한다고 주장한다.

## 출처와 확인 수준

- 공식 출처: [Attractive Metadata Attack: Inducing LLM Agents to Invoke Malicious Tools](https://arxiv.org/abs/2508.02110)
- 유형: 논문 · 2025년 · NeurIPS 2025 · `venue_reported_unverified`
- 저자·발행: Kanghua Mo, Li Hu, Yucheng Long, Zhihao Li
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 여러 시뮬레이션 도구 사용 시나리오와 여러 에이전트에서 높은 공격 성공을 보고한다.
- 주된 작업 수행에는 큰 영향 없이 개인정보 유출이 발생한다고 보고한다.
- 방어를 실행 수준에서 설계해야 한다고 주장한다.

## 우리 솔루션 개발에 사용할 곳

- 도구 등록 시 이름·설명·스키마를 모두 점검 대상으로 삼고, 외부 서버가 보낸 메타데이터 변경을 계약 변경 탐지 이벤트로 기록한다.
- 모델 판단에 기대지 않고 실행 단계 정책(도구별 허용 인자, 개인정보 마스킹, 승인)으로 막는 구조를 유지한다. 논문이 프롬프트 수준과 감사기 탐지의 한계를 주장하기 때문이다.
- 악성 도구가 민감 데이터를 인자로 모으는 시나리오를 테스트 케이스로 추가하고, 게이트웨이 마스킹 단계에서 PII가 인자에 실리지 않는지 확인한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv 초록 페이지를 열어 확인했고 시뮬레이션 설정과 에이전트 목록은 읽지 않았다. 수치는 적지 않았다. 감사기 기반 탐지 평가는 개정판(v2) 요약에 의존한다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

arXiv non-exclusive 1.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
