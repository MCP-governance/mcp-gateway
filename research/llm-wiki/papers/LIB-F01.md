# LIB-F01 · LlamaFirewall: An open source guardrail system for building secure AI agents

웹페이지와 이메일 같은 외부 콘텐츠를 다루는 에이전트의 위험을 막기 위해, 실시간 최종 방어선 역할을 하는 오픈소스 가드레일 시스템 LlamaFirewall을 제안한다. 탈옥 탐지기 PromptGuard 2, 추론 과정을 점검하는 Agent Alignment Checks, 코딩 에이전트의 위험 코드를 잡는 CodeShield로 구성된다.

## 출처와 확인 수준

- 공식 출처: [LlamaFirewall: An open source guardrail system for building secure AI agents](https://arxiv.org/abs/2505.03574)
- 유형: preprint · 2025년 · arXiv · `preprint`
- 저자·발행: Sahana Chennabasappa, Cyrus Nikolaidis, Daniel Song, David Molnar 외
- 확인일: 2026-10-14 / `full_text_selected_sections_read` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 전문의 선별 절을 읽고 확인했다.
- 읽은 PDF: https://arxiv.org/pdf/2505.03574 · SHA-256 `8e5ce5dcf6fc4d2f18c436f7573d3e6427142f77363e23bf9e7ab3bc8e3fb3cc` (위키에는 보관하지 않음)
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 모델 미세조정이나 챗봇용 모더레이션만으로는 막기 어려운 에이전트 위험을 실시간 계층에서 다룬다고 주장한다.
- Agent Alignment Checks는 간접 인젝션 방어에서 기존 접근보다 낫다고 주장하지만, 저자 스스로 실험적이라고 밝힌다.
- PromptGuard 2는 탈옥 탐지에서 최고 수준이라고 주장하나, 초록에는 구체적 수치가 없다.

## 정독 메모

읽은 범위: 초록, 구조 설명, PromptGuard 2·AlignmentCheck·CodeShield 평가, 한계

- 구성: PromptGuard 2(BERT 계열 jailbreak 분류기, 86M·22M 두 크기), AlignmentCheck(에이전트 추론 과정을 감사하는 few-shot CoT 감사기, 저자가 실험적이라고 명시), CodeShield(Semgrep·정규식 규칙 기반 정적 분석, 8개 언어), 그리고 정규식·LLM 프롬프트로 만드는 사용자 정의 스캐너.
- PromptGuard 2는 범위를 명시적 jailbreak 탐지로 좁혀 오탐을 줄였다. 22M 모델은 영어에서는 효과적이나 다국어에서는 성능이 떨어진다고 저자가 밝힌다(한국어 입력에는 그대로 쓰기 어렵다는 뜻).
- AgentDojo 평가에서 방어 없는 기준은 공격 성공률 17.6%·효용 47.7%이고, PromptGuard 2(86M)만 쓰면 7.5%·47.0%다. AlignmentCheck(Llama 4 Maverick)는 공격 성공률을 2.89%까지 낮췄지만(기준 대비 84% 감소) 효용이 43.1%로 떨어지고 지연이 크다. PromptGuard와 결합하면 1.75%(90% 넘는 감소), 효용 42.7%다(저자 보고).
- CodeShield는 1단계 패턴 검사가 약 60ms, 필요 시 2단계 정밀 분석이 평균 약 300ms이고 내부 배포에서 입력의 약 90%가 1단계에서 끝난다고 한다. CyberSecEval3 표본에서 정밀도 96%·재현율 79%다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이의 도구 결과 검사 단계에 탈옥·간접 인젝션 탐지기를 붙이고, 탐지 결과를 OPA 입력 신호로 넘긴 뒤 차단 사유를 감사 원장에 함께 기록한다.
- Agent Alignment Checks는 저자가 실험적이라고 밝혔으므로 차단이 아니라 ‘경고 후 승인 요구’로만 연결해 오탐률을 먼저 측정한다.
- CodeShield식 정적 검사는 쓰기 계열 MCP 도구의 인자 검사 규칙으로 옮겨, 생성 코드가 도구 인자로 들어가는 경우를 막는다.
- 도구 응답 검사에 "저비용 1차 필터 + 고비용 2차 감사" 계층을 둘 때의 근거로 쓴다. 한국어 입력은 PromptGuard 22M을 그대로 쓰지 말고 별도 평가를 거친다(설계 제안).

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv 초록 페이지만 열람했고 본문과 벤치마크 표는 정독하지 않았다. 구성요소별 정량 결과는 초록에 없어 확인하지 못했다. 구현 저장소 위치는 검색 요약에서만 확인했다. 2026-10-14에 arXiv PDF의 초록, 구조 설명, PromptGuard 2·AlignmentCheck·CodeShield 평가, 한계을 읽고 확인했다(PDF는 위키에 보관하지 않고 SHA-256만 기록). 전문 전체 정독·재현은 하지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

CC BY 4.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
