# LIB-D02 · AgentSpec: Customizable Runtime Enforcement for Safe and Reliable LLM Agents

에이전트 실행 중 발생하는 이벤트에 조건 검사와 집행 동작을 붙이는 경량 도메인 특화 언어 AgentSpec으로 런타임 규칙을 정의하고 집행하는 방식을 제안한다. 코드 실행, 임바디드 에이전트, 자율주행 세 영역에 적용해 안전 경계 안에 머무르게 하는 효과를 보였다.

## 출처와 확인 수준

- 공식 출처: [AgentSpec: Customizable Runtime Enforcement for Safe and Reliable LLM Agents](https://arxiv.org/abs/2503.18666)
- 유형: 논문 · 2025년 · ICSE 2026 (Proc. ICSE'26, pp. 2938-2950) · `venue_reported_unverified`
- 저자·발행: Haoyu Wang, Christopher M. Poskitt, Jun Sun
- 확인일: 2026-10-14 / `full_text_selected_sections_read` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 전문의 선별 절을 읽고 확인했다.
- 읽은 PDF: https://arxiv.org/pdf/2503.18666 · SHA-256 `a8ef39247392eb49e275768c19aca11a111c997e432225dcbcf74dfbf31abae7` (위키에는 보관하지 않음)
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 코드 에이전트에서 안전하지 않은 실행의 90% 넘게를 막았다고 보고한다(초록).
- 임바디드 과제에서 위험 행동을 모두 제거했다고 주장한다(초록).
- LLM이 생성한 규칙은 정밀도 95.56%, 재현율 70.96%로, 재현율이 1에 못 미쳐 누락 가능성이 남는다(초록 수치, 임바디드 사례).

## 정독 메모

읽은 범위: 서론, 3장(DSL 문법·의미론), 평가(코드·임바디드·자율주행), 오버헤드

- 규칙은 `rule 식별자 / trigger / check / enforce / end` 다섯 부분이다. trigger는 `before_action`(행동 실행 직전), `state_change`(환경 상태 변화), `agent_finish`(작업 종료) 세 종류이고, check는 술어의 논리곱(예 `is_destructive_cmd`, `contains_sensitive_info`)이다.
- enforce는 `user_inspection`(사용자 확인), `llm_self_examine`(LLM 자기 점검), `invoke_action`(지정 동작 실행), `stop`(궤적 종료) 네 가지다. 예시 규칙은 가족이 아닌 대상으로의 송금 직전에 사용자 확인을 요구한다.
- 오버헤드: 규칙 파싱 평균 1.42ms, 술어 평가 평균 2.83ms(코드)·1.11ms(임바디드). `user_inspection`은 사용자 응답 시간, `llm_self_examine`은 LLM 지연에 좌우된다.
- 임바디드 과제에서 안전한 과제의 성공 비율은 규칙 적용 후 58.62%에서 54.26%로 줄었다(저자 보고).
- LLM(o1)이 생성한 규칙은 임바디드에서 정밀도 95.56%·재현율 70.96%, 자율주행 8개 시나리오 중 5개에서 위반을 막았다. 저자도 수작업 규칙보다 거칠고 누락이 있다고 인정한다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이 정책을 '이벤트, 조건, 집행 동작' 3요소 규칙으로 적는 방식을 OPA(Rego) 정책 설계의 용어 기준으로 삼는다.
- LLM이 규칙 초안을 쓰고 사람이 검수하는 흐름의 근거로 쓸 수 있다. 초록은 LLM 생성 규칙의 정밀도와 재현율을 함께 보고했다.
- 밀리초 단위 오버헤드 주장은 게이트웨이 지연 예산을 잡을 때 실측 기준으로 삼는다.
- 게이트웨이 정책의 (이벤트, 조건, 결정) 3요소를 이 trigger–check–enforce 구조와 맞춰 규칙 스키마를 점검한다(설계 제안). 결정 값은 허용/승인 보류/차단으로 두고 `llm_self_examine`은 결정론이 깨지므로 정책 경로에서 제외한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv 초록과 소개부만 확인했고 전문은 정독하지 못했다. 언어 문법과 전체 실험 설정은 확인하지 못했다. 초록에 한계 절이 없다. 적용 영역(코드, 임바디드, 자율주행)이 MCP 도구 호출과 직접 대응하지 않는다. 2026-10-14에 arXiv PDF의 서론, 3장(DSL 문법·의미론), 평가(코드·임바디드·자율주행), 오버헤드을 읽고 확인했다(PDF는 위키에 보관하지 않고 SHA-256만 기록). 전문 전체 정독·재현은 하지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
