# 기업 비밀 저장소 연동

현재 Gateway [credential_headers](../../../full_stack_lab/gateway/app/upstream.py)는 operator-provisioned 공급자 자격을 정확한 HTTPS endpoint·허용 principal·기한에 바인딩한다. 직원 JWT를 upstream으로 넘기지 않는다. 범용 Vault/Cloud retrieval SDK가 이미 연결됐다는 의미는 아니다.

| 대상 | 우선 활용할 기존 구현 | 확인 조건 |
| --- | --- | --- |
| Vault | Vault Agent·공식 API·hvac | server BSL과 SDK Apache 라이선스 구분, AppRole/workload policy·KV v2·lease·revoke |
| OpenBao | 공식 Agent/API·호환 SDK의 고정 판본 | MPL 라이선스, Vault API 유사성과 실제 호환을 구분 |
| AWS Secrets Manager | boto3·STS/IAM workload role | KMS·version stage·rotation·CloudTrail·최소 권한 |
| Azure Key Vault | azure-identity·azure-keyvault-secrets | Managed/WorkloadIdentity·RBAC·tenant·expiry·disabled secret·developer credential fallback |
| Google Secret Manager | google-cloud-secret-manager·WorkloadIdentity | version enable/disable/destroy·IAM·audit·rotation |
| External Secrets Operator | 기존 controller·provider adapter | refresh·RBAC·Kubernetes Secret encryption·workload auth. sync 성공은 provider 철회 증거가 아님 |

공식 URL·라이선스·기능·현재 공백은 [연동 정본](../analysis/integrations.json)에 있다. [LiteLLM Secret Managers](https://docs.litellm.ai/docs/secret_managers/overview)의 native integration은 edition/Enterprise 조건을 따로 확인한다. 공개 SDK가 있다는 이유로 해당 LiteLLM 유료 기능이 OSS에서 활성이라고 쓰지 않는다.

조회기는 새로 만들기 전에 공식 SDK/Agent/ESO를 평가한다. 회전 파일을 기존 Gateway 자격 계약으로 전달하려면 readonly 권한·정확 endpoint/principal·TTL·atomic refresh·출력 금지·실행 직전 만료를 충족해야 한다. secret 조회 장애 후 anonymous fallback은 금지한다. 서버별 provider 재접근과 실제 철회를 독립 증거로 남긴다.

현재16개 secret 조건은 미실행이다. 고객 workload identity·tenant/project·시험 secret·경로/권한이 확정되기 전 여러 cloud SDK를 무조건 설치하거나 장기 master key를 공유하지 않는다. 자격 값 자체는 위키/Excel/콘솔에 넣지 않는다.
