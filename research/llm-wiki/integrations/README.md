# 기업 연동의 경로와 검수

[연동7개 제품](../analysis/integrations.json)과 [시험50조건](../analysis/integration-cases.json)을 기준으로 관리한다. 제품·SDK·edition·배포 경로를 확정하고 실제 결과를 같은 조건 ID에 연결한다. 분석표·이미지 설치·health 응답만으로 연동 완료를 선언하지 않는다.

| 경로 | 먼저 읽을 자료 | 확인할 경계 |
| --- | --- | --- |
| 하네스→LLM Gateway→모델 | [LiteLLM](litellm.md), [격리 랩](lab/README.md) | 실제 모델 응답·스트림·도구 선택, 사용량·취소·quota·인증 오류 |
| 하네스→MINT→실제 MCP | [MCP 검토](../analysis/review-2026-10-15/README.md) | 직원 transport 신원·승인 계약·독립 upstream 자격·도구 효과 |
| LLM Gateway의 MCP 집계→MINT | [연동 조건](../analysis/integration-cases.json) | 호출 주체·자산 권한·위임 교집합. 공유 토큰으로 신원을 대신하지 않음 |
| 비밀 저장소→upstream 자격 파일 | [비밀 저장소](secrets.md) | 공식 Agent/SDK·읽기 권한·회전·철회·stale·장애와 원문 노출 |
| 승인 소스→호스팅 MCP | [DEV-38 설계](../analysis/review-2026-10-15/dev38-runtime-plan.md), [ToolHive 후보](../solutions/toolhive-runtime.md) | 빌드 권한·image digest·내부 endpoint·승인 만료·종료 |
| SSO·정책·관측 | [증거 계약](../methodology/evidence-contract.md) | 기존 Authlib/OPA/OpenTelemetry 활용, 현재 상태·감사·비밀 최소화 |

각 경로의 정상군과 audience/scope 불일치, 권한 부족, 자격 회전·철회, timeout·응답 유실, 재시작·복구를 분리한다. LLM 응답 성공과 MCP 호출 성공, 정책 허용과 도구 업무 성공을 혼합하지 않는다. 실제 환경의 실행은 [현재 상태](../status/current.md)와 날짜가 있는 보고서를 확인한다.

고객 IdP/secret/CA/LLM Gateway의 판본·배포 범위가 정해지면 기존 조건에 결과를 누적한다. 새 비밀 저장소·SSO·관측 서비스를 직접 복제하지 않는다. 특정 업체의 시장 점유율이나 라이선스 적합성을 근거 없이 일반화하지 않는다.
