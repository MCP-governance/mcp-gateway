# 기업 연동

[연동7개 제품](../analysis/integrations.json)과 [독립 시험50조건](../analysis/integration-cases.json)을 기준으로 관리한다. 현재 운영 연결을 분석표만으로 완료 처리하지 않는다. [LiteLLM](litellm.md), [비밀 저장소](secrets.md)를 먼저 읽는다.

SSO는 기존 Authlib OIDC 경로, 관측은 기존 OpenTelemetry/Jaeger와 원장, 정책은 기존 OPA·PostgreSQL을 활용한다. 고객 환경의 IdP/secret/CA/LLM Gateway 판본·배포 범위가 확정되면 같은 조건 ID에 제품별 결과를 추가한다. 특정 업체의 시장 점유율이나 보편적 채택을 근거 없이 수치화하지 않는다.
