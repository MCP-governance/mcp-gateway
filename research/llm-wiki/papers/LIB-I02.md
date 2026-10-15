# LIB-I02 · Technical Blog: Strengthening AI Agent Hijacking Evaluations

AI 에이전트 하이재킹을 간접 프롬프트 인젝션으로 보고, ETH Zurich의 AgentDojo 프레임워크(Workspace, Travel, Slack, Banking 환경)로 에이전트 평가 방법을 제시한다. 평가가 적응형 공격과 반복 시행을 반영해야 한다고 주장한다.

## 출처와 확인 수준

- 공식 출처: [Technical Blog: Strengthening AI Agent Hijacking Evaluations](https://www.nist.gov/node/1872381)
- 유형: 보고서·권고 · 2025년 · NIST · `official_publication`
- 저자·발행: NIST CAISI (Center for AI Standards and Innovation) 기술 스태프
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 기존 공격에 강한 모델도 적응형 레드팀 공격에는 뚫려, 공격 성공률이 11%에서 81%로 올라갔다고 보고한다.
- 다섯 과제의 평균 성공률은 57%였으나 과제별 편차가 커서, 평균만 보면 위험을 놓칠 수 있다고 주장한다.
- 같은 공격을 25회 반복하면 평균 성공률이 57%에서 80%로 올라, 1회 시행 평가는 위험을 과소평가할 수 있다고 제시한다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이 회귀 테스트에서 같은 주입 시나리오를 한 번이 아니라 여러 번 반복 실행해 성공률을 기록한다(블로그는 25회 반복 사례를 제시).
- 성공률을 과제(도구)별로 따로 집계하고, 송금·메일 발송·원격 코드 실행 같은 고영향 도구는 전체 평균과 무관하게 낮은 허용 임계값을 둔다. 블로그는 고영향 과제가 성공률이 낮아도 주의가 필요하다고 지적한다.
- 알려진 공격 세트만 통과하는 정책을 걸러내도록, 레드팀이 새로 만든 적응형 공격을 정책 검증 세트에 주기적으로 추가한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

블로그 본문만 읽음. 원 AgentDojo 논문과 후속 CAISI 보고서는 미정독. 평가에 쓰인 모델(Claude 3.5 Sonnet 계열)이 오래되어 수치는 당시 조건 기준이며 재계산하지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
