# LiteLLM 연동 경계와 검증

공식 [MCP 문서](https://docs.litellm.ai/docs/mcp)는 모델 호출과 MCP 집계·실행·권한·수송을 다룬다. 공개 upstream 기능이 우리 배포의 활성화·호환성을 증명하지는 않는다.

## 현재 코드/배치

| 항목 | 확인 |
| --- | --- |
| 기존 고정 비교 코드 | 1.102.0, f8e456d105af921213267d0ef801ca08b8fdbc0b |
| Compose 이미지 | 1.102.1. `llm` profile로 선택 기동 |
| 신규 평가 후보 | 1.105.0. 자동 업그레이드/실기기 호환 검증하지 않음 |
| 모델 API | [litellm.yaml](../../../full_stack_lab/llm/litellm.yaml)의 Ollama OpenAI 경로, 관리 하네스별 API |
| MCP 경로 | 하네스→우리 Gateway 직접 호출. LiteLLM 설정에 `mcp_servers` 없음 |
| field 상태 | 현재 read-only readiness에서 llm_gateway=false. 배포 source에는 다른 작업의 미커밋 변경도 있어 판본+dirty를 구분 |
| private enterprise URL | [model-domains.txt](../../../full_stack_lab/model-proxy/model-domains.txt)의 제공자 도메인과 고객 LiteLLM host/CA/CONNECT 허용은 별도 |

## 이번 구현

공식 MCP SDK로 검사·마스킹된 structuredContent를 보존하고 구조화-only 결과에 안전한 JSON text fallback을 추가했다. Block/Approval/withheld/unknown의 잔존 payload는 반환하지 않는다. 결과 키의 개인정보는 공식 Presidio로 batch 검사하고 키를 바꾸는 대신 보류한다. outputSchema 승인·잠금, rich content·resources/prompts/sampling/tasks는 추가 검증 범위다.

[preflight.py](../../../full_stack_lab/integrations/litellm/preflight.py)는 **통합 시험 client**다. MCP 서버를 자체 구현하지 않는다. 정해진 판본·HTTPS·병렬 경로·API·서로 다른 자격 파일을 검증하며 `--validate-only`는 자격을 읽거나 통신하지 않는다. opt-in `--run`은 실제 모델 응답과 공식 SDK MCP initialize/list를 각각 검사하지만 자연어 도구 선택·업무 효과의 E2E 성공으로 세지 않는다. HTTP health는 모델 응답의 대체 증거가 아니다.

예제는 `.invalid` 주소와 경로만 포함한다. protected PJ1 하네스가 임의 client/interpreter를 실행할 수 있다고 가정하지 않는다. 운영자가 승인한 integration 실행 환경·신원·short-lived 자격 provisioning이 먼저 필요하다. PC 키트의 helper 보호를 우회하거나 직원 JWT를 설정/로그로 export해 예제를 채우지 않는다. 현재 field의 HTTP443은 기업 HTTPS/CA 완료 증거가 아니다.

## 우선 보강

1. 기업 LiteLLM host·HTTPS/CA·virtual key·허용 model·요금/범위를 확정한다.
2. Chat/Responses/Messages 및 streaming·완전한 tool arguments·error/retry/cancel·trace를 검증한다.
3. 병렬 하네스 경로의 fresh managed 자연어 turn→모델→실제 OSS MCP→원장→효과를 연결한다.
4. 집계 경로는 shared token으로 직원/device를 대체하지 않는다. 검증된 delegation/audience/권한 교집합·현재 관리 상태를 설계·검증하기 전 활성 지원이라고 하지 않는다.
5. 누락/빈/unknown 서버 scope·tool ACL·cache/revoke·budget·불확실한 쓰기의 retry를 음성 시험한다.

50조건 중 LiteLLM34조건은 모두 미실행이며, 이번 preflight 단위/설정 검사와 공식 SDK serialization 회귀를 이를 통과한 결과로 승격하지 않는다.
