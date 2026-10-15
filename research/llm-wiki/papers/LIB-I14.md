# LIB-I14 · Agentic AI Threat Modeling Framework: MAESTRO

CSA 게시글로 소개된 에이전트 AI 위협 모델링 틀이다. MAESTRO는 Multi-Agent Environment, Security, Threat, Risk, and Outcome의 약자이며, 아키텍처를 7개 계층(기반 모델, 데이터 운영, 에이전트 프레임워크, 배포·인프라, 평가·관측, 보안·컴플라이언스, 에이전트 생태계)으로 나눠 계층별 및 교차 계층 위협을 분석한다.

## 출처와 확인 수준

- 공식 출처: [Agentic AI Threat Modeling Framework: MAESTRO](https://www.cloudsecurityalliance.org/blog/2025/02/06/agentic-ai-threat-modeling-framework-maestro)
- 유형: 보고서·권고 · 2025년 · Cloud Security Alliance 블로그 · `official_publication`
- 저자·발행: Ken Huang (CSA AI Safety Initiative)
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 저자는 STRIDE와 PASTA가 AI 고유 위협(적대적 ML, 데이터 포이즈닝, 목표 불일치, 에이전트 간 상호작용)을 충분히 다루지 못한다고 주장한다.
- 7계층 구조와 교차 계층 분석을 제안하며, 보안·컴플라이언스 계층은 수직으로 다른 계층 전체에 걸친다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이 위협 모델을 계층별로 나눈다. 에이전트 생태계(MCP 서버, 외부 도구)와 에이전트 프레임워크(클라이언트 측 호출)의 신뢰 경계를 따로 그린다.
- '보안·컴플라이언스'가 수직 계층이라는 점을 이용해 감사 원장, PII 마스킹, 정책 검사를 모든 계층에 걸친 공통 통제로 배치한다.
- 계층 간 교차 위협(예: 평가·관측 계층의 결과가 정책 계층의 판단을 바꾸는 경우)을 시험 시나리오에 포함한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

블로그 글 한 편만 읽음(2025-02-06). 독립 평가와 공식 명세는 확인하지 못함. 최신 저장소 버전의 계층 정의 변경 여부 미확인. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
