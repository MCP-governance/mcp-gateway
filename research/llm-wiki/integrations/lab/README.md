# LiteLLM 실제 연동 환경 — 구축안

이 폴더는 사용자가 고객 환경이 없으므로 직접 구축하라고 요청한 **독립 실험 환경**의 구성안이다. 기존 field 제품 프로젝트·DB·계정·CA·팀원의 미커밋 파일을 재사용하지 않는다. 배포는 솔루션 기기 `100.83.175.111`의 `/home/user/mcpgw-interop-lab-20261013`에서 root 작업자가 취합한 Compose로 한다. 이 문서를 작성한 시점의 배포·모델 호출·MCP 실행 상태는 미실행이다.

## 실제 upstream과 고정 값

| 구성 | 고정 값 | 목적 |
| --- | --- | --- |
| LiteLLM | 공식 `ghcr.io/berriai/litellm-database:v1.105.0`, digest 고정 | 실제 Chat/Responses/Messages·native MCP·제한 virtual key 시험 |
| 모델 서버 | 공식 `ollama/ollama:0.40.3`, 안정 release와 digest 확인 | 자체 응답 구현을 사용하지 않는 실제 추론 |
| 모델 | 공식 `qwen3:0.6b`, 약 523MB model layer, Apache-2.0 | 저자원 API·도구 호환 baseline. 기업 품질·보안 효과 대표성이 아님 |
| DB | 공식 `postgres:18.4-alpine`, 독립 volume | LiteLLM 실제 virtual-key/사용량 상태 |
| TLS | 공식 `caddy:2.11.7-alpine`, 독립 internal CA | Tailnet IPv4 `:8448` LiteLLM / `:8449` OpenBao |
| 실제 MCP | Microsoft Learn 공식 Streamable HTTP | 공개 문서 read-only native MCP 시험; 인증이 필요한 직원 업무와 별개 |

판본·registry index/amd64 digest·source commit·라이선스·공식 문서는 [provenance.json](provenance.json)에 있다. digest는 registry에서 직접 확인했다. LiteLLM OCI `org.opencontainers.image.revision`은 release commit과 일치한다. 서명/attestation 검증과 실제 실행 판본 확인은 별도 조건이다. [LiteLLM release](https://github.com/BerriAI/litellm/releases/tag/v1.105.0), [Ollama release](https://github.com/ollama/ollama/releases/tag/v0.40.3), [Ollama 모델](https://ollama.com/library/qwen3:0.6b).

## 파일과 취합 조건

`compose.yaml`은 LiteLLM/Ollama/PostgreSQL/Caddy 네 서비스를 제안한다. OpenBao 서비스·초기화·AppRole 정책은 별도 담당의 구성과 합친다. `Caddyfile`의 `openbao:8200` 이름과 `secret_edge` network를 일치시켜야 `:8449` 경로가 동작한다. 취합 전 이 경로를 활성 기능으로 보고하지 않는다.

모든 실제 실행에서 `docker compose -p mcpgw-interop-20261013`을 명시한다. 일반 field `console.sh`나 기존 Compose override에 이 파일을 얹지 않는다. root가 기기 자원을 확인한 뒤 단계별로 기동한다. 설정에 기본 credential 값은 없다. `${INTEROP_BIND}`는 기기의 실제 Tailscale IPv4, `${INTEROP_SECRET_DIR}`는 Git 밖의 보호 디렉터리다. 아래 세 파일은 새 난수 값으로 생성해 owner-only 권한으로 보존하고 stdout·명령 인자·연구자료에 출력하지 않는다.

- `postgres_password`
- `litellm_master_key` — 공식 형식 `sk-` prefix
- `litellm_salt_key` — 독립 salt, 기존 제품 salt와 공유하지 않음

`litellm-entrypoint.sh`는 파일을 읽고 공식 entrypoint로 실행한다. 비밀번호는 URI 인코딩하며 shell tracing을 사용하지 않는다. DB/관리 자격은 직원 virtual key와 다르다. 시험 key는 root 권한으로 공식 `/key/generate`에서 제한 발급한 뒤 보호 파일·OpenBao에 보존한다. 모델 API는 이 제한 key로 호출하며 master key로 정상 직원 요청을 대체하지 않는다. 기존 IdP 직원 JWT를 lab이나 최종 MCP로 전달하지 않는다.

## 망·모델 다운로드·TLS

런타임 Ollama는 내부 `model` network에만 붙고 host port를 게시하지 않는다. DB도 내부 network에만 있다. 모델 weights를 최초 확보할 때만 `compose.download.yaml`을 추가해 **이 lab Ollama만** 다운로드 network에 붙인다. `ollama pull qwen3:0.6b` 뒤 실제 모델 manifest SHA-256을 `provenance.json`의 `7df6b6e0…` 전체 값과 대조한다. 이후 기본 Compose만으로 이 lab Ollama를 재생성해 다운로드 망을 제거하고 volume은 유지한다. 모델 tag의 다른 바이트로 원본을 조용히 덮어쓰지 않는다.

LiteLLM의 `mcp_egress`는 공식 Microsoft Learn 공개 endpoint를 호출하기 위한 lab outbound다. 이를 목적지별 기업 egress 통제라고 주장하지 않는다. Caddy host 게시 두 개는 `${INTEROP_BIND}:8448/8449`로만 제한한다. wildcard host binding·모델/DB port 게시는 없다. container 내부 Ollama bind `0.0.0.0`는 내부 Docker network listener이며 host 게시와 구분한다.

TLS는 [Caddy `tls internal`](https://caddyserver.com/docs/caddyfile/directives/tls)을 사용하며 [자동 trust 설치](https://caddyserver.com/docs/automatic-https)를 끈다. 공개 root certificate만 별도 복사해 fingerprint를 기록한다. private key나 전체 CA data volume을 client에 공유하지 않는다. preflight optional `ca_file`은 보호된 구성에서 명시한 public PEM CA만 읽고 공식 Python SSLContext에 추가한다. chain과 hostname 검증은 유지한다. 환경 `SSL_CERT_FILE`이나 `HTTPS_PROXY`에 의존하지 않으며, 명시 proxy 지원은 아직 없다.

기존 PJ1 managed UID와 model proxy는 `:8448` 연결을 자동 승인하지 않는다. 기존 firewall·launcher·helper를 완화해서 접속하지 않는다. 초기 lab에서 API/SDK로 받은 증거는 프로토콜·제품 연동 층이며, 실제 새 관리형 하네스→우리 Gateway 직원 인가→MCP 업무 효과 증거와 구분한다.

## 실제 모델·도구 시험

`litellm.yaml`은 공식 Ollama OpenAI endpoint를 쓰고 자동 retry를 0으로 한다. `reasoning_effort: none`은 [Ollama 공식 호환 API](https://docs.ollama.com/api/openai-compatibility)의 thinking-off 값이다. 실제 `/api/show` capability와 실제 모델 답변으로 다시 확인한다. 작은 모델이 tool selection/arguments를 틀리면 실패로 기록하며 scripted tool call을 모델 성공으로 대체하지 않는다.

Microsoft Learn alias `microsoft_learn`은 이 lab 설정 이름이다. 실제 [공식 endpoint와 tool 이름](https://learn.microsoft.com/en-us/training/support/mcp-developer-reference)은 매 초기화 시 `tools/list`로 다시 수집한다. 문서에 설명된 도구는 `microsoft_docs_search`, `microsoft_docs_fetch`, `microsoft_code_sample_search`이고 문서상 [공개·무인증 read-only](https://learn.microsoft.com/en-us/training/support/mcp) 서비스다. 내부 직원·자산·OAuth 보호를 증명하는 대상은 아니다.

권한 설정은 [LiteLLM 공식 grant](https://docs.litellm.ai/docs/mcp_grant_access)에 따라 제한 virtual key에 `object_permission.mcp_servers=["microsoft_learn"]`와 실제 허용 tool 목록을 둔다. `require_key_mcp_access_defined=true`를 유지한다. [MCP 설정 기준](https://docs.litellm.ai/docs/mcp_config_reference)에 따라 직접 MCP client는 `/{server_alias}/mcp`, 모델 API native MCP는 `server_url="litellm_proxy/mcp/microsoft_learn"`를 사용한다. 이 경로는 기존 enterprise Gateway의 employee/device identity를 보존한 지원 경로가 아니다.

검증 순서는 다음과 같다.

1. 실행 image digest·package version·network·게시 port·CA fingerprint·실제 모델 manifest/capability 확인.
2. 제한 key로 실제 Chat/Responses/Messages 정상 모델 답변. `health`·model 목록 조회와 구분.
3. 각 API stream의 정상 완료·끊김·빈 결과·wrong model/invalid key를 검사.
4. 공식 SDK로 Microsoft Learn initialize/list/read를 실제 호출해 실제 tool/schema/결과를 저장.
5. 작은 실제 모델이 공개 문서 질의를 위해 native MCP 도구를 선택·호출한 request/tool/result ID를 별도 확인. 단순 최종 답변만 성공으로 세지 않음.
6. 제한 없는 key·알 수 없는 alias·허용하지 않은 tool 직접 호출·권한 철회 후 session/cache를 음성 검사.
7. OpenBao AppRole·least privilege·TLS·rotation·TTL·outage와 secret 값 비노출을 별도로 시험.

일반 API/SDK 단계가 통과해도 [50조건](../../analysis/integration-cases.json) 전부를 통과 처리하지 않는다. 해당 조건 ID·실행 판본·관측 범위에만 실제 결과를 추가한다.
