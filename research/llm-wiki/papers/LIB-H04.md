# LIB-H04 · OWASP Top 10 for LLM Applications 2025: LLM02:2025 Sensitive Information Disclosure

LLM과 주변 애플리케이션이 개인정보나 기밀을 의도치 않게 노출하는 위험(LLM02:2025)을 정리한 OWASP 항목이다. 다른 사용자 데이터 노출, 우회 프롬프트에 의한 추출, 학습 데이터 유출을 공격 시나리오로 들고, 입력과 출력 정제, 최소 권한, 민감 데이터 패턴 탐지 등 완화책을 제시한다.

## 출처와 확인 수준

- 공식 출처: [OWASP Top 10 for LLM Applications 2025: LLM02:2025 Sensitive Information Disclosure](https://genai.owasp.org/llmrisk/llm022025-sensitive-information-disclosure/)
- 유형: 표준·규제 · 2025년 · OWASP GenAI Security Project · `official_publication`
- 저자·발행: OWASP Gen AI Security Project
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 완화책으로 입력과 출력의 정제, 최소 권한 접근, 민감 필드 필터링, 토큰화 후 패턴 매칭 기반 탐지를 든다.
- 공격 시나리오는 사용자 간 데이터 노출, 우회 프롬프트 주입, 학습 데이터 유출의 세 가지로 구성된다.
- 시스템 프롬프트에 반환 데이터 제한을 넣는 방법은 지켜지지 않거나 프롬프트 인젝션으로 우회될 수 있다고 주의한다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이의 출력 측 PII 검사 요구사항을 정리하는 체크리스트로 쓴다. 입력 정제, 출력 마스킹, 로그 필드 필터링을 각각 정책 항목에 대응시킨다.
- 다른 사용자의 데이터가 응답에 섞이는 시나리오를 세션 격리 테스트 케이스로 옮긴다.
- RAG와 MCP 리소스 접근에는 최소 권한 원칙을 적용하고, 데이터 민감도 등급을 도구 권한과 연결한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

OWASP 공식 페이지의 완화책과 공격 시나리오 요약만 열람했다. 페이지 전문과 참고 문헌은 정독하지 않았다. 2025년판 기준이며 이후 개정본은 확인하지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
