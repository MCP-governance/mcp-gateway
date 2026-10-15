"""Build fixed-ID, source-bounded enterprise integration conditions; no runtime claims."""
import ast
import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[3]
out = Path(__file__).resolve().parents[1] / 'analysis'
observed = '2026-10-13'
base = 'ab6936c64f3578de8360b840f1928681714fa7bb'
litepin = '80b9556dd312d18c535ae06884faa97d1fdb8f46'
urls = {
 'config':'https://docs.litellm.ai/docs/mcp_config_reference',
 'mcp':'https://docs.litellm.ai/docs/mcp/',
 'grants':'https://docs.litellm.ai/docs/mcp_grant_access',
 'permissions':'https://docs.litellm.ai/docs/mcp_control',
 'oauth':'https://docs.litellm.ai/docs/mcp_oauth',
 'peruser':'https://docs.litellm.ai/docs/mcp_per_user_auth',
 'keys':'https://docs.litellm.ai/docs/proxy/virtual_keys',
 'harness':'https://docs.litellm.ai/docs/harness/gateway',
 'clients':'https://docs.litellm.ai/docs/proxy/client_setup/overview',
 'secrets':'https://docs.litellm.ai/docs/secret_managers/overview',
 'vault':'https://docs.litellm.ai/docs/secret_managers/hashicorp_vault',
 'bao':'https://openbao.org/docs/agent-and-proxy/agent/template/',
 'aws':'https://docs.aws.amazon.com/secretsmanager/latest/userguide/retrieving-secrets-python-sdk.html',
 'awsrotate':'https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotating-secrets.html',
 'azure':'https://learn.microsoft.com/en-us/azure/key-vault/secrets/quick-create-python',
 'gcp':'https://docs.cloud.google.com/secret-manager/docs/access-secret-version',
 'gcpdisable':'https://docs.cloud.google.com/secret-manager/docs/disable-secret-version',
 'eso':'https://external-secrets.io/latest/provider/hashicorp-vault/',
 'vaultagent':'https://developer.hashicorp.com/vault/docs/agent-and-proxy/agent/template',
}

integrations = [
 {'id':'INT-LITELLM','product':'LiteLLM','category':'LLM gateway and MCP gateway','version_or_commit':f'local config v1.102.1/d09bbae1c6df463e425558f60d460437193635da; reviewed release v1.105.0/{litepin}',
  'route':'A: official managed harness -> customer LiteLLM LLM API, separately -> our Gateway MCP; B: LiteLLM -> our Gateway MCP requires delegated transport identity, currently not_ready',
  'auth':'employee virtual key to LiteLLM; separately scoped managed employee MCP JWT to our Gateway; independent bound upstream SaaS credential',
  'capabilities':['OpenAI ChatCompletions','OpenAI Responses','Anthropic Messages','Gemini generation','MCP StreamableHTTP/SSE/stdio','key/team/tool permissions','OAuth and scoped upstream headers'],
  'our_code_evidence':['full_stack_lab/compose.yaml:299-328','full_stack_lab/llm/litellm.yaml:16-41','full_stack_lab/workstation/provision_keys.py:48-58','full_stack_lab/workstation/managed/render.py:45-100','full_stack_lab/gateway/app/mcp_facade.py:49-50','full_stack_lab/gateway/app/upstream.py:32-84','full_stack_lab/console.sh:246-295'],
  'compatibility_status':'partial_configured_not_active_in_field; delegated_MCP_not_ready','gap':'field default lacks llm profile; no mcp_servers; fixed bob-assistant and internal URLs; customer hostname absent from model proxy; no verified end-to-end LiteLLM tool evidence; streaming/cancellation/usage/rotation cases unrun',
  'source_url':[urls['config'],urls['harness'],urls['permissions'],urls['secrets'],f'https://github.com/BerriAI/litellm/tree/{litepin}'],
  'license':'MIT outside enterprise/; Enterprise license and activation apply to native secret-manager features','github_stars_observed':61115},
 {'id':'INT-OPENBAO','product':'OpenBao','category':'OSS secrets manager','version_or_commit':'c760347ffecea6b9baf33345b01ff125b28e73f5 (main metadata pin; docs 2.7.x)',
  'route':'official OpenBao Agent auto-auth + template -> protected rotating JSON file -> existing MCP_UPSTREAM_CREDENTIALS_FILE; prefer this to a custom provider implementation',
  'auth':'AppRole/Kubernetes/certificate or configured supported auto-auth; workload token with narrowly scoped secret path, not employee MCP JWT',
  'capabilities':['KV v2','leased secrets','official Agent renewal','template render to file','process supervisor'],
  'our_code_evidence':['full_stack_lab/gateway/app/upstream.py:32-78','full_stack_lab/compose.yaml:128','full_stack_lab/compose.yaml:163','full_stack_lab/tests/credential_binding_check.py:14-40'],
  'compatibility_status':'candidate_existing_file_contract_static_only','gap':'no Agent deployment/policy/template currently; must map actual lease end to expires_at>0 and enforce file freshness/revocation; no assumption of drop-in LiteLLM Vault provider support',
  'source_url':[urls['bao'],'https://openbao.org/docs/agent-and-proxy/agent/','https://github.com/openbao/openbao/blob/c760347ffecea6b9baf33345b01ff125b28e73f5/LICENSE'],
  'license':'MPL-2.0','github_stars_observed':8410},
 {'id':'INT-VAULT','product':'HashiCorp Vault','category':'source-available/commercial secrets manager','version_or_commit':'fdd82cfd09d5f905f29aa98d9fea6d2a77fd5eda (main metadata pin; runtime not provisioned)',
  'route':'official Vault Agent template -> protected existing file; or licensed LiteLLM native Vault integration for LLM provider keys',
  'auth':'Vault Agent supported workload auto-auth; LiteLLM native AppRole/TLS cert/token; optional Enterprise namespace',
  'capabilities':['KV v2','dynamic leased credentials','revocation','official Agent templates','LiteLLM native read/write virtual-key storage with Enterprise license'],
  'our_code_evidence':['full_stack_lab/gateway/app/upstream.py:32-78','full_stack_lab/compose.yaml:128','full_stack_lab/compose.yaml:163'],
  'compatibility_status':'candidate_static_only','gap':'no Vault provisioned; Vault >=1.15 uses BSL-1.1 rather than OSI OSS; native LiteLLM plugin Enterprise licensing; cache/revocation bounds must be measured',
  'source_url':[urls['vault'],urls['vaultagent'],'https://github.com/hashicorp/vault/blob/fdd82cfd09d5f905f29aa98d9fea6d2a77fd5eda/LICENSE'],
  'license':'BSL-1.1 for current Vault source; commercial Enterprise terms separate','github_stars_observed':36383},
 {'id':'INT-AWS-SECRETS','product':'AWS Secrets Manager','category':'managed enterprise secrets service','version_or_commit':'service API; boto3 f5581ba376ab8f3b077899ad7856810ed8a42a36 metadata pin; installed SDK not confirmed',
  'route':'official SDK boto3 or official ESO provider/workload identity -> existing protected credential file; native LiteLLM Enterprise alternative for LLM keys',
  'auth':'IAM role/IRSA or workload identity; secretsmanager:GetSecretValue and KMS decrypt only for approved resource',
  'capabilities':['versioned secret retrieval','AWSCURRENT/AWSPREVIOUS','rotation','client-side cache','CloudTrail audit'],
  'our_code_evidence':['full_stack_lab/gateway/app/upstream.py:32-78','full_stack_lab/compose.yaml:163'],
  'compatibility_status':'not_provisioned','gap':'no AWS tenant/role/SDK/provider connection; rotation must revoke actual downstream token, and cached old versions must expire within contract',
  'source_url':[urls['aws'],urls['awsrotate'],'https://github.com/boto/boto3/blob/f5581ba376ab8f3b077899ad7856810ed8a42a36/LICENSE'],
  'license':'AWS service terms; boto3 Apache-2.0','github_stars_observed':9909},
 {'id':'INT-AZURE-KEYVAULT','product':'Azure Key Vault','category':'managed enterprise secrets service','version_or_commit':'service API; Azure SDK 385e07bb742d6e8cea4ecad34d6d403d2387fb8b metadata pin; installed package not confirmed',
  'route':'official azure-keyvault-secrets + azure-identity, CSI/ESO file mount; licensed LiteLLM native provider alternative',
  'auth':'Managed Identity/Workload Identity with narrow RBAC and private-endpoint/network policy; production credential chain must be explicit',
  'capabilities':['versioned SecretClient.get_secret','enabled/disabled secret versions','RBAC','managed identity','audit integration'],
  'our_code_evidence':['full_stack_lab/gateway/app/upstream.py:32-78','full_stack_lab/compose.yaml:163'],
  'compatibility_status':'not_provisioned','gap':'tenant/vault/private endpoint/role missing; latest vs pinned version and disabled cached secret behavior untested',
  'source_url':[urls['azure'],'https://docs.litellm.ai/docs/secret_managers/azure_key_vault','https://github.com/Azure/azure-sdk-for-python/blob/385e07bb742d6e8cea4ecad34d6d403d2387fb8b/LICENSE.txt'],
  'license':'Azure service terms; official SDK MIT','github_stars_observed':5618},
 {'id':'INT-GCP-SECRETS','product':'Google Secret Manager','category':'managed enterprise secrets service','version_or_commit':'service API; google-cloud-python 1de2e3f0831fa0b24b2a458956b3d96739bd191c metadata pin; installed package not confirmed',
  'route':'official google-cloud-secret-manager SDK or ESO Workload Identity -> existing protected file; LiteLLM Enterprise native provider alternative',
  'auth':'ADC/Workload Identity Federation; secretmanager.versions.access on approved secret and version',
  'capabilities':['version access','version disable/destroy','IAM','CRC32C integrity checking','audit logs'],
  'our_code_evidence':['full_stack_lab/gateway/app/upstream.py:32-78','full_stack_lab/compose.yaml:163'],
  'compatibility_status':'not_provisioned','gap':'project/service account/identity federation missing; payload CRC32C/version/revocation propagation unverified',
  'source_url':[urls['gcp'],urls['gcpdisable'],'https://docs.litellm.ai/docs/secret_managers/google_secret_manager','https://github.com/googleapis/google-cloud-python/blob/1de2e3f0831fa0b24b2a458956b3d96739bd191c/LICENSE'],
  'license':'Google Cloud service terms; official SDK Apache-2.0','github_stars_observed':5408},
 {'id':'INT-ESO','product':'External Secrets Operator','category':'OSS Kubernetes integration controller','version_or_commit':'4aaa3159078da3550164e59de02e1438eea3af5f (main metadata pin; no chart installed)',
  'route':'official SecretStore/ExternalSecret provider -> Kubernetes Secret -> volume; compose appliance uses Agent/official SDK instead unless Kubernetes is actually selected',
  'auth':'provider workload identity; scoped SecretStore preferable to unrestricted ClusterSecretStore; RBAC for controller and workload',
  'capabilities':['AWS/Azure/GCP/Vault providers','refresh policies','template data mapping','status conditions','Kubernetes mounts'],
  'our_code_evidence':['full_stack_lab/compose.yaml:163','full_stack_lab/gateway/app/upstream.py:45-48'],
  'compatibility_status':'not_applicable_to_current_compose; candidate_for_kubernetes','gap':'Kubernetes projected secret default modes/owner must meet current 0600-or-0400-style owner-only permission check; refresh failure does not by itself erase a previously mounted secret',
  'source_url':[urls['eso'],'https://external-secrets.io/latest/introduction/','https://github.com/external-secrets/external-secrets/blob/4aaa3159078da3550164e59de02e1438eea3af5f/LICENSE'],
  'license':'Apache-2.0','github_stars_observed':6897},
]
for item in integrations:
 item['checked_at'] = observed
 item['analysis_base_commit'] = base
 item['runtime_evidence'] = []

# These names and IDs are the existing workbook links. New detail must not reorder them.
PRODUCT_ORDER = ['LiteLLM', 'HashiCorp Vault', 'OpenBao', 'AWS Secrets Manager',
                 'Azure Key Vault', 'Google Secret Manager', 'External Secrets Operator']
FEATURES = [
 'field profile','Chat normal','Responses normal','Messages normal','Chat streaming',
 'Responses streaming','Messages streaming','tool schema','tool result','structured-only',
 'route separation','key scope','tool ACL','MCP initialize','MCP list','MCP call',
 'aggregate identity','OAuth audience','OAuth expiry','OAuth refresh','server selection',
 'private DNS','TLS CA','CONNECT','rate/budget','cancellation','retries','timeout',
 'context limits','trace','logs','secrets license','failure fallback','version upgrade',
 'least privilege','workload auth','TLS','version pin','rotation','lease','revocation',
 'outage','mount','logs','audit','provider binding','Vault/AppRole','AWS STS','Azure MI','GCP/ESO'
]
urls.update({
 'release':'https://docs.litellm.ai/release_notes/v1.105.0/v1-105-0',
 'architecture':'https://docs.litellm.ai/docs/proxy/architecture',
 'budget':'https://docs.litellm.ai/docs/proxy/users',
 'logging':'https://docs.litellm.ai/docs/proxy/logging',
 'otel':'https://docs.litellm.ai/docs/observability/langfuse_otel_integration',
 'specauth':'https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization',
 'spectransport':'https://modelcontextprotocol.io/specification/2025-11-25/basic/transports',
 'spectools':'https://modelcontextprotocol.io/specification/2025-11-25/server/tools',
})
CODE = {
 'llm': ('full_stack_lab/llm/litellm.yaml','model_list',None),
 'compose': ('full_stack_lab/compose.yaml','llm-gateway service',r'^  llm-gateway:'),
 'gateway_config': ('full_stack_lab/compose.yaml','Gateway credential environment and readonly secret-volume mount',r'^  gateway:'),
 'field': ('full_stack_lab/console.sh','field_up',r'^field_up\(\)'),
 'keys': ('full_stack_lab/workstation/provision_keys.py','main',None),
 'claude': ('full_stack_lab/workstation/managed/claude-code/managed-settings.json','ANTHROPIC_BASE_URL',None),
 'codex': ('full_stack_lab/workstation/managed/codex/config.toml','model_providers.bob',None),
 'opencode': ('full_stack_lab/workstation/managed/opencode/opencode.json','provider.bob',None),
 'renderer': ('full_stack_lab/workstation/managed/render.py','GATEWAY/MODEL and generated harness routes',None),
 'proxyhosts': ('full_stack_lab/model-proxy/model-domains.txt','approved CONNECT destination regexes',None),
 'proxy': ('full_stack_lab/model-proxy/tinyproxy.conf','ConnectPort/FilterDefaultDeny',None),
 'caller': ('full_stack_lab/gateway/app/mcp_facade.py','_caller',None),
 'context': ('full_stack_lab/gateway/app/mcp_facade.py','_client_context',None),
 'list': ('full_stack_lab/gateway/app/mcp_facade.py','_approved_tools',None),
 'render': ('full_stack_lab/gateway/app/mcp_facade.py','_render',None),
 'build': ('full_stack_lab/gateway/app/mcp_facade.py','build_mcp',None),
 'identity': ('full_stack_lab/gateway/app/agent_contract.py','authenticated_user',None),
 'jwt': ('full_stack_lab/gateway/app/agent_contract.py','authenticate',None),
 'credentials': ('full_stack_lab/gateway/app/upstream.py','credential_headers',None),
 'upstream': ('full_stack_lab/gateway/app/upstream.py','session',None),
 'discover': ('full_stack_lab/gateway/app/upstream.py','discover',None),
 'payload': ('full_stack_lab/gateway/app/privacy.py','mask_payload',None),
 'core': ('full_stack_lab/gateway/app/core.py','execute_call',None),
 'guard': ('full_stack_lab/gateway/app/core.py','_guarded_result',None),
 'tracing': ('full_stack_lab/gateway/app/core.py','_configure_tracing',None),
 'catalog': ('full_stack_lab/gateway/app/core.py','refresh_catalog',None),
 'refresh': ('full_stack_lab/gateway/app/idp.py','token',None),
 'revoke': ('full_stack_lab/gateway/app/idp.py','_revoke_family',None),
 'manifest': ('full_stack_lab/integrations/litellm/preflight.py','validate_manifest',None),
 'probe': ('full_stack_lab/integrations/litellm/preflight.py','probe',None),
}


def code_evidence(key):
    path, symbol, pattern = CODE[key]
    raw = (root / path).read_bytes()
    text = raw.decode('utf-8-sig')
    lines = text.splitlines()
    start, end = 1, len(lines)
    if path.endswith('.py') and pattern is None:
        matches = [n for n in ast.walk(ast.parse(text))
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == symbol]
        if matches:
            node = min(matches, key=lambda n: n.lineno)
            start, end = node.lineno, node.end_lineno
        elif key != 'renderer':
            raise ValueError('Missing function: ' + path + ':' + symbol)
    elif pattern:
        found = [i for i, line in enumerate(lines, 1) if re.search(pattern, line)]
        if len(found) != 1:
            raise ValueError('Ambiguous source anchor: ' + path)
        start, end = found[0], min(len(lines), found[0] + (52 if key in {'field','gateway_config'} else 29))
    original = subprocess.run(['git', '-C', str(root), 'show', 'HEAD:'+path], capture_output=True)
    state = ('worktree_added' if original.returncode else 'worktree_modified'
             if raw.replace(b'\r\n',b'\n') != original.stdout.replace(b'\r\n',b'\n') else 'committed_source')
    return {'path':path,'symbol':symbol,'line_start':start,'line_end':end,
            'normalized_sha256':hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest(),
            'head_sha256': hashlib.sha256(original.stdout).hexdigest() if not original.returncode else None,
            'source_state':state,'scope':'local source inspection, not runtime proof'}


# Each condition has its own setup, operation, failure input and corrective boundary.
# Lists use | only as an authoring separator; generated JSON contains normal arrays.
DETAILS = {
 1: ('허용 모델·직원 key·고객 TLS origin 확정|실제 배치 image digest/버전 조회 권한',
     '활성 컨테이너·package version·이미지 digest와 tag commit을 대조|field 서비스 목록과 llm profile 활성 여부를 확인|모델 정상 응답은 IC-002~004에서 별도로 수집',
     'Compose 설정 존재와 활성 배포를 구분; 현재 field llm_gateway=false는 미활성 상태',
     '비활성 profile/다른 실행 이미지/health 200만으로 활성 호환 판정',
     '고객의 기존 LiteLLM 연결을 우선 구성; 자체 llm profile은 기기 자원·모델·망 검토 후 별도 배포',
     ['compose','field','llm'],['clients','release'],'configured_not_active_in_field'),
 2: ('Chat 지원 실제 모델과 별도 직원 virtual key|PJ1 공식 OpenCode 판본·관리 설정 고정',
     '새 관리형 OpenCode 세션에서 민감하지 않은 정상 질문|/v1/chat/completions 상태·choices.message·finish_reason·usage를 기록|등록되지 않은 model과 만료 key로 각각 재시도',
     '실제 non-empty 모델 답변과 정확한 오류 구분; MCP 도구 업무 성공은 별도 IC-016',
     'quota 응답/200+빈 content/허용되지 않은 alias/허위 모델 답변',
     'LiteLLM 공식 provider API capability와 model allowlist에 맞춰 관리형 base URL·모델·parameter 수정',
     ['llm','opencode','probe'],['harness','clients'],'configured_static_only'),
 3: ('Responses 지원 모델과 전용 virtual key|PJ1 공식 Codex wire_api=responses 설정',
     '새 관리형 Codex 세션에서 정상 질문|response id·output message/text·status·usage를 수집|다른 직원의 previous_response_id 사용과 unsupported 모델을 거부하는지 확인',
     '실제 output_text와 완료 상태; health/models 조회만으로 통과하지 않음',
     'health만 성공/empty output/타 직원 conversation ID 재사용',
     '공식 Responses native/bridge 지원을 고정 판본별로 검증하고 /v1 base·wire_api를 일치',
     ['llm','codex','probe'],['clients','harness','release'],'configured_static_only'),
 4: ('Messages 지원 모델·직원 virtual key|Claude 공식 판본·모델 슬롯·API base 확정',
     '새 Claude 관리형 세션에서 정상 질문|anthropic-version·content text·stop_reason·usage를 대조|잘못된 API version과 지원하지 않는 parameter를 각각 시도',
     'Anthropic 형식의 실제 모델 답변; tool/thinking 기능은 provider별 별도 확인',
     'API key 환경값이 virtual key를 가림/버전 누락/빈 content',
     'LiteLLM 공식 Claude 설정과 auth token/API key 우선순위를 적용하고 native/변환 provider를 별도 시험',
     ['llm','claude','probe'],['clients','harness','release'],'configured_static_only'),
 5: ('stream=true 지원 모델|SSE event 순서·client 종료를 기록할 수 있는 공식 SDK',
     '동일 정상 질문을 Chat 비스트리밍/스트리밍으로 실행|delta 조립·finish_reason·최종 usage를 비교|실제 provider 또는 승인된 proxy에서 연결을 끊어 truncated stream을 관찰',
     '완료된 delta만 정상 완료로 집계; 중간 실패를 성공 응답으로 세지 않음',
     '중복 delta/종료 누락/일부 텍스트 뒤 stream reset',
     'pinned LiteLLM의 공식 streaming/error 동작에 맞춰 하네스 parser·timeout·재시도 조건 수정',
     ['llm','opencode'],['harness','release'],'not_run_streaming'),
 6: ('Responses streaming 지원 provider|고정 Codex 버전·SSE event capture',
     '관리형 Codex로 텍스트와 공식 MCP 도구 요청을 각각 실행|response lifecycle·tool argument delta·completed 이벤트 순서를 비교|완료 전에 스트림을 중단하고 response.failed/불확실 상태를 대조',
     '완전한 argument JSON과 명시 완료 전 도구 실행으로 취급하지 않음',
     'incomplete argument 실행/중복 response 생성/response.completed 없이 성공',
     'LiteLLM 공식 Responses stream bridge와 SDK 버전별 lifecycle regression을 유지',
     ['llm','codex','build'],['harness','release'],'not_run_streaming'),
 7: ('Messages streaming 지원 모델|Claude content-block event 기록',
     'Claude에서 텍스트와 승인된 공식 MCP 읽기 도구 요청|block index·input_json_delta·message_stop·stop_reason을 대조|input delta가 끊긴 경우 도구 실행과 응답 결과를 독립 비교',
     'tool_use ID와 완전한 인자·content block 경계를 보존',
     'message_stop 조기 도착/부분 인자 실행/bridge 오류를 정상 종료로 처리',
     'pinned LiteLLM Messages 변환과 공식 Claude 기능표에 맞춰 event parser와 오류 처리를 수정',
     ['llm','claude','build'],['harness','release'],'not_run_streaming'),
 8: ('공식 MCP의 실제 승인 계약|직접 SDK discovery 결과와 모델로 전달한 schema 수집',
     '정상 도구의 이름·필수 인자·enum·nested schema를 직접/경유 경로에서 비교|승인 계약에서 벗어난 누락·추가·타입 오류 인자로 호출|schema drift 이후 discovery cache로 남은 도구를 재호출',
     '승인 name/inputSchema가 의미 손실 없이 모델에 전달되고 실행 직전 다시 검증',
     'schema truncation/essential parameter drop/승인되지 않은 outputSchema 자동 광고',
     '공식 SDK schema 직렬화를 사용하고 catalog 최신 관찰·사람 승인 lock을 유지; outputSchema 승인 저장은 별도 공백',
     ['list','catalog','core'],['permissions','spectools'],'input_schema_static_output_schema_gap'),
 9: ('실제 structuredContent를 주는 공식 MCP|합성 개인정보가 있는 격리 업무 데이터',
     '직접 SDK와 Gateway 결과의 text/structuredContent/isError/_meta를 비교|민감 값·키를 검사하고 masked 결과를 LiteLLM 경유 답변까지 대조|Block/Approval/withheld/unknown에서 잔존 payload 반환을 검사',
     '검사·마스킹된 payload만 released 경로로 전달; 차단·보류 raw 내용 누출 없음',
     'inspection 이전 structured JSON 전달/보류 payload 누출/provider 오류와 정책 차단 혼동',
     '공식 MCP SDK 직렬화와 Presidio 검사 결과를 사용; 비검사 rich content는 지원으로 광고하지 않음',
     ['render','guard','payload'],['spectools','config'],'local_patch_unit_only_no_integration_run'),
 10: ('structured-only 결과를 제공하는 공식 MCP|구형 text-only 소비자와 현재 SDK client',
      '정상 structured-only 객체를 직접/경유로 호출|text fallback을 JSON으로 파싱해 inspected structuredContent와 비교|mask/보류/빈 객체 결과에서 schema와 누출 여부를 비교',
      '안전한 JSON text fallback이 동일 inspected 객체를 전달; 빈 content 때문에 업무 결과를 숨기지 않음',
      'raw JSON fallback/구조가 list인데 object로 광고/보류에서도 fallback 반환',
      '공식 CallToolResult object 제약과 SDK wire round-trip 회귀를 유지하고 출력 계약 승인 범위를 별도 설계',
      ['render','guard'],['spectools'],'local_patch_unit_only_no_integration_run'),
 11: ('독립 LLM virtual key와 관리형 MCP JWT|자격 값을 노출하지 않는 Gateway/provider audit',
      '정상 병렬 LLM/MCP 경로를 호출|두 자격의 수신 서비스를 바꿔 오류·dispatch 여부를 확인|최종 SaaS에서 employee JWT와 LLM key가 전달되지 않았는지 provider 증거로 확인',
      'Gateway는 자기 issuer/audience/scope를 검증하고 최종 공급자는 별도 bound 자격만 수신',
      '동일 bearer 두 서비스 공유/Authorization 덮어쓰기/body user_id 신원 사용',
      '상위 admission과 서버별 upstream credentials를 분리; 직원 JWT의 최종 MCP passthrough 옵션 금지',
      ['identity','jwt','credentials','manifest'],['config','specauth'],'static_boundary_not_vendor_run'),
 12: ('LiteLLM key/team/org의 독립 허용 목록|다른 모델·MCP 서버·tool 권한 2개 이상',
      'key만 제한/team만 제한/양쪽 제한/org ceiling 조합에서 list+call|각 단계의 명시 none·빈 scope·no-mcp-servers를 대조|권한 변경 후 cache hit와 기존 session을 다시 실행',
      '활성 제한의 교집합만 호출되고 key opting-out은 전체 거부; open default를 제한으로 오인하지 않음',
      '빈 key grant가 넓은 팀 권한 상속/unknown 그룹·캐시로 범위 확대',
      '검토 LiteLLM 판본의 require_key_mcp_access_defined/object_permission을 명시하고 Gateway 자산 scope는 독립 유지',
      ['keys','list','identity'],['permissions','grants','keys'],'litellm_entitlements_not_configured'),
 13: ('공식 MCP의 read/write 도구|LiteLLM tool ACL과 우리 Gateway PAC 권한',
      '서버 allowlist 내 특정 tool만 허용한 key로 discovery|목록에서 숨긴 write 도구를 정확한 원래 이름으로 직접 호출|팀/키 tool 목록 변경 후 기존 캐시 세션으로 호출',
      'discovery와 실행 양쪽에서 최종 tool scope를 검증; 목록 필터만으로 통과하지 않음',
      '숨긴 tool direct-call 성공/namespace alias로 다른 도구 호출/권한 상속 확대',
      'LiteLLM 공식 tool permission 기능과 실행 재검증을 사용하며 우리 PAC action/resource 검증 유지',
      ['list','core'],['permissions','grants'],'gateway_static_litellm_acl_not_run'),
 14: ('등록된 공식 MCP 서버·승인 계약|공식 Inspector/SDK와 fresh managed endpoint',
      '정상 initialize에서 실제 protocol/capabilities/serverInfo 수집|지원되지 않는 protocol·재사용 Session-Id·잘못된 protocol header로 접근|session close/reconnect 후 후속 discovery를 확인',
      '공식 SDK의 협상과 session 규칙을 지키며 optional capability는 실제 지원한 것만 광고',
      'SDK pin만으로 전체 optional 지원 주장/잘못된 session 복원',
      '공식 MCP SDK transport/lifecycle를 재사용하고 자체 protocol fallback을 만들지 않음',
      ['build','discover','upstream'],['config','spectransport'],'sdk_static_not_litellm_handshake_run'),
 15: ('승인된 공식 MCP 2종|역할·principal별 다른 allowlist와 충분한 도구 목록',
      'SDK 직접 목록과 Gateway 승인 목록의 이름/schema 비교|aggregate와 per-server URL·pagination 결과를 비교|다른 principal·권한 철회·stale contract에서 다시 조회',
      '승인 도구만 전달되고 서버 namespace 충돌·의도하지 않은 pagination 누락 없음',
      'cached unauthorized tools/같은 alias 다른 도구/첫 페이지를 전체 목록으로 오인',
      'MCP SDK 목록 동작과 LiteLLM namespacing을 고정 판본별 검사; 승인 contract 밖 도구를 노출하지 않음',
      ['list','catalog','build'],['config','permissions'],'gateway_static_litellm_list_not_run'),
 16: ('실제 정상 데이터가 있는 공식 OSS filesystem/git MCP|fresh managed PJ1 공식 하네스·허용 모델·독립 효과 로그',
      '사용자가 승인 파일 읽기를 자연어로 지시|native model/tool ID→Gateway decision/trace→upstream 결과→최종 답변 연결|동일 업무에 비승인 데이터/권한 입력을 넣어 실제 수신·효과 0을 확인',
      '정상 내용 provenance와 실제 모델 선택 증거, 차단시 정확 policy_id 및 독립 효과 없음',
      '모델 추측 답변/discovery+무관 모델 응답을 E2E로 합침/quota 응답을 정상 업무 통과로 집계',
      '공식 provider tool capability와 현재 openai/Ollama route를 먼저 검증하고 각 업무 효과를 별도 증거화',
      ['build','core','llm'],['harness','config'],'not_run_managed_litellm_tool_e2e'),
 17: ('승인된 delegation 설계·issuer/audience|직원 2명과 다른 active managed endpoint',
      'LiteLLM Responses/Chat MCP 자동 실행 경로를 두 직원으로 요청|우리 Gateway가 검증한 principal/device/client/session을 원장과 대조|spoofable x-user-id/body metadata와 공유 service bearer를 거부하는지 확인',
      '검증된 transport 직원·현재 관리 상태·자산 권한을 보존; service token으로 employee를 대체하지 않음',
      'shared bearer+user header/body sub 사용/관리형 admission 생략',
      'RFC8693 또는 검증된 독립 caller assertion의 별도 설계와 인가 proof 필요; 현재 집계 위임은 not_ready',
      ['caller','identity','context','manifest'],['oauth','peruser','specauth'],'unsupported_delegation'),
 18: ('독립 IdP에서 정상/잘못된 resource token 발급|Gateway 공개 metadata와 allowed issuer/key 고정',
      '정상 issuer/audience/resource에 발급한 관리형 token으로 호출|wrong aud/issuer/resource·잘못된 서명·다른 tenant token을 각각 호출|MCP admission과 최종 provider 별도 token 경계를 확인',
      '우리 Gateway target audience만 수락하고 LiteLLM auth 성공을 직원 MCP 인가로 전이하지 않음',
      '다른 MCP resource bearer 수락/Authorization JWT를 최종 provider에 전달',
      '공식 MCP auth·resource metadata·token exchange를 우선 사용; 현재 issuer/audience 검증을 완화하지 않음',
      ['jwt','identity','credentials'],['oauth','specauth'],'gateway_static_litellm_oauth_not_run'),
 19: ('짧은 만료의 실제 Gateway/공급자 test token|실제 revoke API와 cache/replica 관측',
      '유효·만료 경계·revoked token으로 동일 도구를 호출|권한 철회 후 기존 session과 cache를 재사용|Gateway no-dispatch와 provider 기존 credential 거부를 구분해 수집',
      '만료·철회된 직원 token은 실행 전 거부; provider credential 회수는 별도 입증',
      'stale cached bearer/approval 시 오래된 token 허용/secret 파일 삭제만으로 provider revoke 주장',
      '현재 인증·revocation 재검증 유지; 승인 실행은 fresh requester 인증으로 설계하고 provider 회수 adapter 별도 검증',
      ['identity','jwt','revoke','credentials'],['oauth','specauth'],'gateway_static_provider_revocation_not_run'),
 20: ('실제 PostgreSQL 격리 schema와 테스트 OAuth family|공식 PJ1 helper의 serial refresh 동작',
      '만료 직전에 동일 family를 동시 refresh|재사용 token·중간 발급 오류·동시 revoke를 발생시켜 후손 발급·거부 검사|helper cache와 LiteLLM key rotation의 독립 lifecycle를 대조',
      'family 잠금·rotation·reuse revoke·transaction rollback 모두 일관; 동시 승자 late issuance 없음',
      'revoke 후 descendant 신규발급/refresh helper race/LLM key rotate를 OAuth family revoke로 치환',
      '기존 PostgreSQL advisory/row lock 회귀를 유지하고 vendor OAuth 회수 결과는 별도 연결',
      ['refresh','revoke','identity'],['oauth'],'gateway_pg_test_existing_litellm_integration_not_run'),
 21: ('공식 MCP 2종을 고정 alias/access group으로 LiteLLM 등록|key 범위를 명시 제한',
      'aggregate/per-server/x-mcp-servers/sentinel subset 경로를 각각 조회·호출|unknown alias·빈 값·group collision을 시도|계약·grant 변경 후 cache invalidation과 동일 범위 재호출',
      '명시 범위는 허용 범위를 좁히고 unknown selector가 전체 허용 서버로 넓어지지 않음',
      'unknown alias fallback 전체/서버 alias와 access group 충돌/expired scope cache 재사용',
      'LiteLLM 공식 server selector와 scoped credentials 기능을 고정 판본으로 사용; deprecated global x-mcp-auth는 신규 사용 금지',
      ['list','build','keys'],['config','grants','peruser'],'litellm_selectors_not_configured'),
 22: ('고객 private LiteLLM hostname·정확 DNS/port|관리형 PJ1 network 허용 변경 계획',
      '관리형 PC와 솔루션 기기에서 고객 origin 이름 해석 비교|DNS TTL 갱신·잘못된 IP·다른 host에서 model 요청|방화벽/proxy 거부와 모델 auth 오류를 구분',
      '승인된 고객 origin만 정상 접근; 현 provider-domain 목록으로 private host 지원 완료라 하지 않음',
      'DNS/hosts spoof/범위 밖 host/현재 public provider-only allowlist',
      '고객별 승인 hostname/IP·network boundary와 재렌더 계약 추가; 넓은 wildcard로 우회하지 않음',
      ['proxyhosts','proxy','manifest'],['clients','config'],'customer_private_dns_gap'),
 23: ('승인 고객 CA와 hostname·유효기간|개별 trust store를 관리할 기업 배치 환경',
      '유효 CA/hostname으로 실제 모델·MCP 연결|unknown CA·expired cert·hostname mismatch로 각각 호출|preflight trust_env=False가 SSL_CERT_FILE을 읽지 않는 점을 별도 확인',
      '실제 HTTPS CA 검증 유지; 현재 field HTTP443과 preflight 설정 통과는 TLS 완료 증거가 아님',
      'verify=False/환경 private CA가 적용됐다고 가정/HTTP tailnet을 기업 HTTPS로 표시',
      '공식 HTTP client의 명시 SSLContext/CA 경로 계약과 배치 trust store를 설계·검증',
      ['probe','manifest','upstream'],['clients','specauth'],'private_ca_explicit_configuration_gap'),
 24: ('고객 origin과 HTTPS 443만 허용한 관리형 proxy|직접 egress 거부 증거',
      '정상 승인 origin CONNECT로 실제 모델 응답|다른 port/host·직접 TCP·redirect origin으로 시도|proxy 로그·endpoint 집행·provider 수신을 시간대별 대조',
      '선정 고객 host/port만 접속; preflight trust_env=False가 HTTPS_PROXY를 사용하지 않음을 명시',
      'arbitrary host wildcard/HTTP_PROXY 환경에 의존/direct route fallback',
      '공식 client의 명시 proxy와 검토한 hostname allowlist를 연결; UID 방화벽/managed launcher 집행 유지',
      ['proxy','proxyhosts','probe'],['clients','config'],'explicit_proxy_and_allowlist_gap'),
 25: ('LiteLLM 실제 key/team budget·RPM/TPM/parallel limit|single/replica worker topology 확정',
      '한도 아래/정확 경계/초과에서 실제 모델 요청|shared counter·spend·429와 zero-cost model 예외를 확인|같은 업무 retry의 MCP effect count와 Gateway 예약을 독립 비교',
      'LLM 비용/요청 한도와 MCP 효과 중복 한도 모두 독립적으로 유효; 분산 worker에서 한도 배수 확대 없음',
      'process-local counter로 replica별 한도 제공/무료모델 budget예외를 실패로 오인/재시도 write중복',
      'LiteLLM 공식 Redis/shared limiter를 필요한 topology에서 사용하고 DB effect reservation은 유지',
      ['keys','core','llm'],['budget','architecture'],'rate_fields_static_budget_cluster_not_run'),
 26: ('공식 MCP read/write sandbox·독립 공급자 effect log|stream client 중단 수단',
      'tool dispatch 전/후와 결과 stream 중 각각 client disconnect|LLM cancellation status·Gateway ledger·provider effect count 비교|동일 업무 재시도 후 중복·불확실 상태를 대조',
      '취소는 반환 중단일 수 있으며 이미 실행한 효과 rollback을 의미하지 않음',
      '응답 취소를 upstream_executed=false로 표시/후속 retry로 효과 복제',
      'durable dispatch intent·불확실 상태·업무 idempotency를 구현하고 취소/결과보류/실행을 분리',
      ['core','render'],['release','architecture'],'durable_dispatch_uncertainty_gap'),
 27: ('LiteLLM primary/fallback provider 2개|격리된 공식 write MCP와 effect counter',
      '첫 provider 429/503와 dispatch 이후 응답 실패를 별도 유발|공식 router의 num_retries/fallback hops와 tool ID 변화 기록|최종 업무 효과·MCP ledger를 독립 비교하고 테스트 자원만 원복',
      '모델 fallback이 이미 실행한 write를 자동 재실행하지 않음; 불확실 효과는 수동 확인 대상으로 유지',
      'provider failover가 새 tool ID로 같은 쓰기를 반복/HTTP success로 중복 숨김',
      '공식 LiteLLM router retry budget을 명시하고 Gateway durable 예약·업무 idempotency를 결합',
      ['llm','core'],['architecture','release'],'retry_effect_integrity_not_run'),
 28: ('LLM/MCP/OPA/Presidio 단계별 실제 지연 조절|승인된 overall deadline과 error contract',
      '각 단계 timeout 경계와 전체 요청 시간을 따로 계측|순차 단계가 각각 limit 이하이나 전체 deadline을 초과하는 조건 시도|upstream dispatch 전/후 timeout의 audit/불확실 효과를 구분',
      '전체 호출 budget과 단계별 timeout이 명시되고 inspection 불능은 실패; 이미 dispatch된 효과는 거짓 미실행으로 기록하지 않음',
      '각 90초 timeout을 합산해 전체 SLA 초과/inspection timeouts allow/일부 stream 뒤 성공',
      'official client deadline/cancellation semantics를 사용하고 전체 request budget을 core에 별도 설계',
      ['llm','upstream','core','probe'],['release','architecture'],'total_deadline_gap'),
 29: ('공식 MCP의 큰 schema/result·합성 업무 입력|등록 모델 context limit와 MAX_RESULT_BYTES 확인',
      '크기 한도 바로 아래/동일/초과 인자·text/structured result 호출|LiteLLM drop_params와 provider의 tool schema/required argument 보존 비교|큰 결과보류 뒤 실제 effect·최종 error를 확인',
      '한도 오류를 정확히 반환; silent truncation이나 essential tool parameter drop을 정상 호환으로 세지 않음',
      'truncated argument JSON 실행/drop_params가 필수 semantics 제거/결과 보류를 효과 없음으로 표시',
      '공식 tokenizer/schema 검증과 명시 limit을 사용; parameter 호환은 provider capability로 선검토',
      ['llm','guard','core'],['spectools','release'],'size_guards_static_provider_context_not_run'),
 30: ('LiteLLM request/spend 로그·Gateway 원장·독립 receiver audit|비밀 본문 없는 trace export',
      '정상 1회·차단 1회 자연어 업무를 실행|native tool ID/LLM request ID→Gateway trace/decision→receiver effect를 연결|위조 traceparent/user metadata와 다른 직원 ID를 입력',
      'trace는 상관관계만 제공; transport-verified principal로 인가하며 원문 token/민감본문을 기록하지 않음',
      'vendor trace/user header를 검증된 직원 신원으로 사용/동일 trace 중복을 단일 effect로 오인',
      '공식 LiteLLM OTel integration과 기존 OTLP를 사용; privacy/no-content 설정을 판본별로 검사',
      ['tracing','context','core','keys'],['logging','otel'],'cross_gateway_trace_link_not_run'),
 31: ('식별 가능한 test-only provider key와 합성 민감 데이터|운영 trace/public 협업콘솔 export 범위',
      '정상·provider 오류·rotation·inspection 오류를 발생|model transcript/CLI stderr/OTLP/원장/Excel/public 콘솔을 값 기준 검색|최소 metadata와 redaction 정책을 판본별로 검증',
      'credential/token과 민감 raw prompt/result가 공개 로그·모델 입력·연구자료에 남지 않음',
      'provider error body 또는 debug header가 key/JWT를 echo/trace content 자동 capture',
      '공식 no-content/redaction callbacks와 중앙 collector filtering을 적용; provider error 본문은 공개 출력 금지',
      ['probe','credentials','tracing'],['logging','otel'],'log_surface_audit_not_run'),
 32: ('실행 LiteLLM edition·Enterprise license 상태|실제 native secret provider 설정 확인',
      '공식 core/enterprise LICENSE와 Secret Managers feature gate 대조|읽기·virtual-key 저장을 각각 실제 native provider로 시험|Enterprise 미활성·권한 없는 secret store에서 오류 확인',
      '공개 SDK 존재와 LiteLLM 유료 기능 활성화를 구분; 미확보 license를 호환 통과로 쓰지 않음',
      'MIT root license로 enterprise 코드를 복제/secret integration 문서만 보고 OSS에 지원 표시',
      'Enterprise native 기능은 유효 고객 license에서 사용; OSS 경로는 공식 Agent/SDK 파일 전달로 독립 평가',
      ['llm','credentials'],['secrets','vault'],'native_secret_managers_enterprise_not_active'),
 33: ('공식 MCP·PDP·secret manager 오류를 만들 격리 시험환경|정상 route와 사후 receiver audit',
      'MCP auth deny·PDP 불능·설정된 credential 파일 오류를 각각 발생|하네스가 direct MCP나 다른 endpoint로 fallback하는지 관찰|credential file 미설정·미매칭 endpoint를 별도로 검사',
      '필수 자격/PDP/계약 실패는 dispatch 전 거부; 공개 무인증 MCP의 의도된 경로는 명시 구분',
      'current credential_headers 미설정/미매칭={}를 secret-required 보장으로 오인/direct route fallback',
      '등록 계약 credential_required+exact binding과 누락시 deny를 설계; 현재 anonymous 지원을 전역 삭제하지 않음',
      ['credentials','core','identity'],['specauth','secrets'],'credential_required_registration_gap'),
 34: ('v1.102.1와v1.105.0 별도 고정 배치|동일 공식 MCP·모델·권한·업무 dataset',
      'API/MCP/auth/stream/negative suite를 두 판본에 동일하게 실행|image digest·tag commit·MCP SDK major/capabilities를 기록|migration 뒤 변경·철회·cache·fallback 결과를 대조',
      '버전별 독립 결과로 candidate 승격; SDK 1.x→2.x migration과 최신 기능 역투영 금지',
      'latest tag 자동 배포/1.105 docs 기능을 current1.102.1 통과로 집계',
      '공식 release notes와 pinned upstream source를 검토하고 동일 정상/음성 suite 이후만 upgrade',
      ['compose','llm','manifest'],['release','config'],'candidate_release_not_installed'),
 35: ('실제 secret store A/B namespace·읽기전용 test workload|provider가 발급한 실제 제한된 MCP 자격',
      'A workload로 승인 secret path/version만 읽기|B tenant·다른 secret·list/write/delete를 각각 시도|manager audit와 실제 provider 권한을 함께 대조',
      'secret manager와 MCP resource 권한 양쪽에서 최소 권한 충족',
      'root/list 전체 secret 권한/cross-tenant read/model arg로secret path선택',
      '공식 workload policy와 승인 mapping을 사용; Gateway credential endpoint/principal binding 독립 유지',
      ['credentials'],['vaultagent','bao','aws','azure','gcp'],'secret_store_policies_not_provisioned'),
 36: ('공식 Agent/SDK/ESO의 실제 workload auth|짧은 TTL role·bootstrap 전달/회수 계획',
      'workload identity로 정상 login·secret retrieval|bootstrap/secret-id/role TTL 만료와 재사용을 검사|다른 workload·developer login fallback을 시도',
      '실제 workload identity만 허용되고 employee MCP JWT나 장기 master key를 secret retrieval에 쓰지 않음',
      'root token/env static cloud access key 공유/PC employee JWT를manager auth로전달',
      'OpenBao/Vault 공식 auto-auth 또는 cloud Workload Identity와 최소권한 정책을 선택',
      ['credentials','identity'],['bao','vaultagent','aws','azure','gcp'],'official_workload_auth_not_deployed'),
 37: ('manager private CA·hostname·TLS endpoint|Agent/SDK 및 실제 provider 호출 경로',
      '정상 manager cert로 조회·갱신|unknown CA·expired cert·hostname mismatch에서 조회|Agent output stale 상태와 Gateway dispatch를 expiry 경계별로 확인',
      'TLS검증 오류를 무시하지 않고 미확보/expired 자격으로 실행하지 않음',
      'verify=False/privateCA설정 누락/managerTLS불능 뒤 무기한 oldfile 사용',
      '공식 Agent/SDK TLS CA 설정을 명시하고 bounded stale·필수 자격 계약을 연결',
      ['credentials','upstream'],['bao','vaultagent','azure'],'manager_tls_and_staleness_not_run'),
 38: ('secret version/stage와정확manager resource 고정|새/이전 자격을 구별할 provider audit',
      'AWS stage·Azure version·GCP version·KV v2 version 선택을 각각 명시|latest/current alias 변경 전후 파일과 실제 인증 결과 대조|unapproved 이전 version 또는 다른namespace 참조를 시도',
      '승인 version 정책과 실제 사용 version 추적; latest 변경을 자동 승인으로 세지 않음',
      'unreviewed latest substitution/다른tenantsecretcache 재사용',
      '공식 SDK의 version selector와 rotation plan을 사용하고 secret 값 없이 version ID·시각만 감사',
      ['credentials'],['aws','awsrotate','azure','gcp','vault'],'version_selector_delivery_not_deployed'),
 39: ('서로 구분되는 실제 old/new provider credential|공식 rotation과Agent/file 갱신',
      'provider 자격을 공식 절차로 rotate 후 secret version 변경|Gateway 기존/새 session의 인증 수신 version을 확인|old provider token을 별도로 재접근해 실제 회수 시점을 측정',
      '새 호출은 승인된 새 자격 사용; 이전 자격 수신/유효 기간은 승인 stale bound 이내',
      'secret 값만 변경하고 old provider credential 계속 유효/캐시무기한 유지',
      '공식 Agent/SDK refresh/rotation callback과 provider revoke를 연결; 파일 교체는 provider 폐기 증거와 별도',
      ['credentials','upstream'],['awsrotate','bao','vaultagent'],'per_request_file_read_static_rotation_not_run'),
 40: ('짧은 실제 lease·양수expires_at|manager/Agent 단절과마지막 render시각 관측',
      'lease 경계 전/후 동일 MCP 업무 실행|Agent renewal 성공·실패 뒤 old file로 호출|expires_at=0·expired timestamp·clock boundary를 별도 확인',
      '만료된 필수 자격은 dispatch 전 거부; 유한 lease와 최대 stale 값을 기업 계약으로 명시',
      '현재expires_at=0 무기한허용을 유한TTL보장으로 표시/Agent죽어도 oldfile 사용',
      '기업secret에expires_at>0·render freshness·bounded stale gate추가; officiallease renewal 동작을 측정',
      ['credentials'],['bao','vaultagent'],'zero_expiry_and_agent_freshness_gap'),
 41: ('실제 provider revoke API·secret read grant|기존 서버 session/cache와old credential 재접근 수단',
      'manager grant 철회와 실제 provider credential revoke를 각각 수행|기존 file/session/cache로 old credential 재접근|Gateway 거부와 provider 실제 거부를 별도 audit로 수집',
      'secret 조회 권한 철회와 이미 전달된 credential 폐기를 구분하고 완료 시한 이후 실제 접근 불가',
      '파일 삭제/secret version disable을이미발급한PAT회수로오인',
      '공식 provider revoke와session종료를 termination adapter로연결; 독립reaccess 증거필수',
      ['credentials','revoke','core'],['gcpdisable','vaultagent','awsrotate'],'provider_revocation_not_provisioned'),
 42: ('실제 manager 403/notfound/network timeout|설정된 credential file·미설정 경로 각각관측',
      'manager outage 뒤 officialAgent/SDK 오류·stale file 상태 확인|credential JSON 누락/권한오류/endpoint 미매칭으로 업무 호출|provider 수신과 public 오류로그에 비밀 노출이 없는지 확인',
      '자격 필수 서버는 실패시 no-dispatch; 일반 공개 MCP anonymous 경로와 분리',
      'currentfile환경없음/endpoint없음={} 반환 뒤anonymous 실행/expiredoldfilefallback',
      'credential_required 등록과deadline/stale한도를설계; currentanonymous지원에유한범위적용',
      ['credentials','core'],['aws','bao','secrets'],'credential_required_and_outage_stale_gap'),
 43: ('공식Agent/ESO의원자적render·LinuxcontainerUID|readonlymount의최종owner-only권한',
      '0400/0600정상file와0644·symlink·부분JSON을분리검사|secretrotation중동시실행으로partialdocument읽기확인|Kubernetesprojectedsecret/Composevolume의실제mode/owner를기록',
      '최종consumer의보호권한·완전한문서만수락; officialatomicrender를실제로확인',
      'ESO defaultworld-readablemode/rootowner를호환완료로표시/비원자적덮어쓰기',
      '공식Agenttemplate와mountdefaultMode/runAs/fsGroup의검토된조합사용; 기존parser실패는차단유지',
      ['credentials','gateway_config'],['bao','vaultagent','eso'],'owner_mode_check_static_atomic_delivery_not_run'),
 44: ('test-only 식별 가능한 manager/provider 자격|Agent/SDK stderr·audit·publicexport 접근',
      '정상read·403·parsefail·rotate를 각각 발생|secret값/key/JWT가로그·modeltranscript·trace·Excel에없는지검색|auditaccess/versionmetadata는비밀없이남는지확인',
      'secret조회 결과 값은모델토큰/공개로그/연구자료에없고최소resource/versionmetadata만남음',
      'SDK예제secret.value출력/providerexceptionbodyecho/headers debug공개',
      '공식SDKlogging/redaction설정을검사하고errors는sanitizedcode로기록;값본문출력금지',
      ['credentials','probe','tracing'],['aws','logging','secrets'],'secret_output_surface_not_run'),
 45: ('manager audit 활성·시간동기화|Gateway와provider 독립read/revoke 로그',
      'secret조회·rotation·grant철회·providerreaccess를실행|auditprincipal/resource/version/time과Gatewaydecision연결|controller/application자체보고와provideraudit를분리',
      '비밀값없이 실제manager/provider 관측으로조회·철회·후속거부입증',
      'Agent filemtime/application PASS문구만증거/일반CloudTrail등존재만으로활성주장',
      '공식manageraudit/export를명시활성화하고append-onlyGateway기록과수집시각·상관ID연결',
      ['credentials','tracing','core'],['aws','azure','gcp','vaultagent'],'independent_manager_audit_not_collected'),
 46: ('HTTPSendpoint A/B·transportprincipal A/B|서로 다른manager tenant와provider credential',
      '정상A endpoint/principal로credential사용|B principal·다른query/path·중복endpoint행·CRLFtoken 시도|미매칭{}반환후필수credential서버실행을별도로검사',
      'credential수신은정확endpoint/principal/tenant로제한;필수자격누락의no-dispatch는추가조건',
      'wildcardbinding/전직원sharedcredential/modelargtenant값인가/미매칭anonymous fallback',
      '현재exactbinding을유지하고credential_required 등록·managernamespacepolicy를별도강제',
      ['credentials','identity'],['config','vault','eso'],'binding_static_required_credential_gap'),
 47: ('Vault 또는OpenBao 실제판본·KVv2mount·AppRolepolicy|단기secret-id/roleTTL·officialAgent',
      'officialAgent AppRoleauto-auth로승인secret경로render|secret-id사용횟수·만료·다른mount/namespace접근실패확인|lease만료·renew/revoke후oldMCPcredential재접근',
      '실제role/mount/path/TTL최소권한충족;Vault/OpenBaoAPI유사성은drop-in보증으로쓰지않음',
      '장기root/AppRole토큰무기한공유/VaultBSL을OSS표시/LiteLLMEnterpriseVaultplugin무활성사용',
      'OpenBaoMPL공식Agent를OSS우선평가;고객Vault는BSL/Enterpriselicense와namespace지원별도검사',
      ['credentials'],['bao','vaultagent','vault','secrets'],'vault_openbao_auth_not_deployed'),
 48: ('실제AWSaccount/region·IAMrole/STSidentity|승인SecretARN·KMSkey·versionstage',
      'officialboto3또는ESOIRSA로GetSecretValue|다른ARN/region/KMS권한없음·STStoken만료를시도|AWSCURRENTrotation후cache와oldprovidercredential 재접근',
      '승인ARN/KMS만읽고short-livedrole사용;cache/version과actualprovider revoke를각각입증',
      'secretsmanager:* rootpolicy/SDK설치만통과/AccessKey를modelenv공유',
      'officialboto3credentialchain/ESOIRSA+resource조건사용;TTL/versionselector·provideraudit추가',
      ['credentials'],['aws','awsrotate'],'aws_workload_not_provisioned'),
 49: ('실제Azuretenant·Managed/WorkloadIdentity|privateVault·승인RBACscope·version',
      'officialSecretClient로승인version조회|다른Vault/tenant/disabledversion·잘못된CA접근|developerDefaultAzureCredentialfallback과staleversion 재접근확인',
      'productionworkloadidentity가명확하고최소RBAC/privateendpoint검증;disabledcachedsecret효과별도관측',
      '개발자login을ManagedIdentity로보고/versiondisable뒤cache무기한사용',
      '공식azureidentity명시credential선택·RBAC/privateendpoint·version/expiry갱신계약구성',
      ['credentials'],['azure','secrets'],'azure_workload_not_provisioned'),
 50: ('실제GCPproject/WIFserviceaccount·secretversion|ESO는실제Kubernetes선택시만설치',
      'officialGCPclient로versionaccess와CRC32C검증|disabledversion·다른project/IAMdeny후cache재접근|ESO선택시SecretStore/ExternalSecretReady·remote403·mountowner/mode와실제MCP효과비교',
      'GCPversion/state/IAM과ESO sync/mount를독립확인;controllerReady를provider회수완료로쓰지않음',
      'latestaliasversion혼합/CRC미검증/Compose에ESOyaml만넣고활성화주장',
      '공식google-cloud-secret-manager checksum/WIF를사용;Kubernetes선택시에만officialESOprovider를채택',
      ['credentials','gateway_config'],['gcp','gcpdisable','eso'],'gcp_workload_not_provisioned_eso_not_current_platform'),
}


def validate(records, cases):
    assert [r['id'] for r in records] == [f'INT-{n:02d}' for n in range(1, 8)]
    assert [r['product'] for r in records] == PRODUCT_ORDER
    assert [c['id'] for c in cases] == [f'IC-{n:03d}' for n in range(1, 51)]
    assert [c['feature'] for c in cases] == FEATURES
    assert len({tuple(c['procedure']) for c in cases}) == 50
    for row in records + cases:
        assert row['source_refs'] and all(u.startswith('https://') for u in row['source_refs'])
        assert row['code_evidence'] and isinstance(row['runtime_evidence'], list)
        for evidence in row['code_evidence']:
            p = (root / evidence['path']).resolve()
            assert p.is_relative_to(root) and p.is_file()
            assert 1 <= evidence['line_start'] <= evidence['line_end'] <= len(p.read_bytes().splitlines())
    for case in cases:
        assert isinstance(case['status'],str) and case['status'] and len(case['procedure']) >= 3
        assert len(case['prerequisites']) >= 2 and case['failure_fix'] and case['current_gap']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--seed', action='store_true', help='Create new datasets only; never replace existing files')
    mode.add_argument('--refresh-evidence', action='store_true', help='Refresh source analysis and preserve human execution records (default)')
    args = parser.parse_args()
    out.mkdir(parents=True, exist_ok=True)
    destinations = [out/'integrations.json',out/'integration-cases.json']
    if args.seed and any(p.exists() for p in destinations):
        parser.error('--seed refuses existing datasets; use --refresh-evidence to preserve accumulated results')
    before_hashes = {p:hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None for p in destinations}
    # Preserve additional caller-added links, e.g. feature/requirement IDs, on regeneration.
    old_cases = {}
    existing = out / 'integration-cases.json'
    if existing.exists():
        old_cases = {c['id']:c for c in json.loads(existing.read_text(encoding='utf-8-sig'))}
    old_products = {}
    if (out / 'integrations.json').exists():
        old_products = {r['id']:r for r in json.loads((out/'integrations.json').read_text(encoding='utf-8-sig'))}
    by_name = {p['product']:p for p in integrations}
    records = []
    for n, product in enumerate(PRODUCT_ORDER, 1):
        item = {**old_products.get(f'INT-{n:02d}',{}), **by_name[product]}
        item['id'] = f'INT-{n:02d}'
        item['source_refs'] = item['source_url']
        item['source_url'] = item['source_refs'][0]
        item['capabilities'] = '\n'.join(item['capabilities'])
        item['metadata_observed_at'] = '2026-10-13T16:48:00+09:00'
        code_keys = ['llm','compose','field','keys','identity','probe'] if n == 1 else ['credentials','upstream','gateway_config']
        item['code_evidence'] = [code_evidence(k) for k in code_keys]
        item['our_code_evidence'] = [f"{e['path']}:{e['line_start']}-{e['line_end']} {e['symbol']}" for e in item['code_evidence']]
        if n == 1:
            item['gap'] += '; preflight trust_env=False ignores HTTPS_PROXY/SSL_CERT_FILE; customer proxy/private CA require explicit configuration'
        else:
            item['gap'] += '; current missing credential-file configuration or unmatched endpoint returns anonymous headers; expires_at=0 permits indefinite credentials; required-credential registration/freshness gate not implemented'
        # Source compatibility is refreshed; measured runtime state remains human-owned.
        for key in ('runtime_evidence','result','test_evidence','status','last_run_at','execution_records','observations'):
            if key in old_products.get(item['id'],{}):
                item[key] = old_products[item['id']][key]
        records.append(item)
    cases = []
    for n, feature in enumerate(FEATURES, 1):
        prereq, procedure, expected, negative, fix, codes, sources, implementation = DETAILS[n]
        record = {**old_cases.get(f'IC-{n:03d}',{}), 'id':f'IC-{n:03d}',
                  'product':'LiteLLM' if n <= 34 else 'Secret managers','feature':feature,
                  'prerequisites':prereq.split('|'),'procedure':procedure.split('|'),
                  'expected':expected,'negative_case':negative,'failure_fix':fix,
                  'status':'not_run','implementation_status':implementation,
                  'current_gap':implementation + '; source-analysis status; separately preserved runtime records require independent review',
                  'source_refs':[urls[s] for s in sources],
                  'version_or_commit':records[0]['version_or_commit'] if n <= 34 else 'Per-provider pins and service/SDK deployment gaps: INT-02..INT-07',
                  'upstream_scope':'official documentation/current release source; not proof of installed runtime capability',
                  'checked_at':observed,'analysis_base_commit':base,'runtime_evidence':[],
                  'evidence':'미확보: '+'; '.join(procedure.split('|')) + '; 실제 native ID/decision/policy/trace와 독립 공급자 결과를 보존하고 자격 값은 기록하지 않음'}
        record['evidence_requirements'] = [
            '실제 native 모델/도구 ID와 Gateway decision/policy/trace 상관관계',
            '조건별 실제 공급자·독립 수신 또는 효과 관측 및 원복 결과; credential 값 제외']
        # Never erase an executed result when rerunning a source-maintenance tool.
        # Unknown extra fields were copied above so team-added links also survive.
        for key in ('status','runtime_evidence','evidence','result','test_evidence','last_run_at',
                    'execution_records','observations','owner','actual_environment','tested_version_or_commit'):
            if key in old_cases.get(record['id'],{}):
                record[key] = old_cases[record['id']][key]
        record['code_evidence'] = [code_evidence(k) for k in codes]
        record['our_code_evidence'] = [f"{e['path']}:{e['line_start']}-{e['line_end']} {e['symbol']}" for e in record['code_evidence']]
        cases.append(record)
    validate(records, cases)
    # Refuse a stale regeneration if somebody added a result while source hashes
    # were being collected; retry against their updated records instead.
    for p, expected_hash in before_hashes.items():
        current_hash = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
        if current_hash != expected_hash:
            raise RuntimeError('Dataset changed during refresh: '+p.name)
    for name, data in [('integrations.json',records),('integration-cases.json',cases)]:
        temporary = out/(name+'.tmp')
        temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8', newline='\n')
        os.replace(temporary,out/name)
    print(json.dumps({'integration_products':len(records),'conditions':len(cases),
                      'non_not_run_records':sum(c['status'] != 'not_run' for c in cases),
                      'runtime_evidence_records':sum(len(c['runtime_evidence']) for c in cases),
                      'mode':'seed' if args.seed else 'refresh-evidence','execution_records_preserved':True,
                      'unique_procedures':len({tuple(c['procedure']) for c in cases}),
                      'empty_sources':sum(not c['source_refs'] for c in cases)},ensure_ascii=False))


if __name__ == '__main__':
    main()

