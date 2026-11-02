# LiteLLM 애드온

LiteLLM이 MCP 서버를 중앙에서 연결하는 조직에서, LiteLLM을 거치는 MCP 호출을 MINT가 판정하고 기록하게 하는 애드온입니다. 이미 LiteLLM을 운영하는 관리자를 위한 안내이며, MINT 서버는 [deploy/README.md](../../deploy/README.md)에 따라 설치되어 있어야 합니다.

대상 LiteLLM 판본은 1.105.0입니다. 다른 판본은 확인하지 않았습니다.

## 하는 일

LiteLLM이 MCP를 집계해 직원 하네스에 노출하면 직원 PC의 호출이 MINT를 거치지 않습니다. 이 애드온은 두 가지를 제공합니다.

| 기능 | 내용 |
| --- | --- |
| 승인·철회 동기화 | MINT에서 승인·등록한 MCP 서버와 승인된 도구를 LiteLLM 관리 API에 반영합니다. 철회·중지·기한 만료 때 서버와 권한을 지웁니다. |
| 호출 경로 | LiteLLM의 MCP 호출을 MINT가 판정합니다. 경로는 `MINT_LITELLM_ROUTE`로 고릅니다. |

호출 경로는 둘 중 하나입니다.

| | A. MINT 경유 (`mint`, 기본·권장) | B. 직접 + 가드레일 (`direct`) |
| --- | --- | --- |
| 실제 호출 | LiteLLM → MINT `/mcp/<서버>/` → MCP 서버 | LiteLLM → MCP 서버 |
| LiteLLM에 등록되는 서버 | MINT 주소, `auth_type: oauth_delegate` | 원래 주소, `auth_type: none` |
| MINT가 맡는 것 | 판정, 전송 직전 재검사, 사람 승인, 출력 통제, 기록 | 호출 직전 판정, 사후 기록 |
| 직원이 보내는 헤더 | `x-litellm-api-key`, `x-mcp-<서버>-authorization: Bearer <본인 MINT 토큰>` | `x-litellm-api-key`, `Authorization: Bearer <본인 MINT 토큰>` |
| LiteLLM 설정 | `config/litellm-mint.yaml` | `config/litellm-plugin.yaml`, `mint_guardrail.py` |

공통 원칙은 다음과 같습니다.

- LiteLLM에 공유 직원 토큰을 넣지 않습니다. 직원이 자기 MINT 토큰을 보내고, MINT는 그 토큰으로만 신원을 정합니다.
- LiteLLM이 주장하는 사용자·팀은 기록만 하며 판정에 쓰지 않습니다.
- A의 `oauth_delegate`는 받은 토큰을 MINT에 그대로 넘기고 보관하지 않습니다. B는 직원 토큰을 MCP 서버로 보내지 않습니다.
- 이 애드온은 LiteLLM의 MCP 호출만 다룹니다. 직원 PC 하네스의 자체 커넥터와 기본 기능은 대상이 아닙니다.

## 들어 있는 파일

| 파일 | 역할 |
| --- | --- |
| `config/litellm-mint.yaml` | A 경로용 LiteLLM `config.yaml` 견본입니다. MCP 서버는 적지 않으며 동기화가 등록합니다. |
| `config/litellm-plugin.yaml` | B 경로용 견본입니다. 가드레일 `mint_guardrail.MintGuardrail`을 `pre_mcp_call`로 항상 적용합니다. |
| `mint_guardrail.py` | B 경로의 LiteLLM 커스텀 가드레일입니다. 도구 호출 직전에 MINT 판정을 받고 호출 뒤 결과를 기록합니다. |
| `gen_mcp_servers.py` | MINT가 운영 중인 서버 목록에서 LiteLLM `mcp_servers` YAML을 만듭니다. 동기화를 쓰지 않는 설치용입니다. |
| `sync-bindings.example.json` | 동기화 매핑 파일 견본입니다. |

두 견본 모두 `require_key_mcp_access_defined: true`(키에 MCP 권한이 명시되지 않으면 MCP를 쓸 수 없음)와 `store_prompts_in_spend_logs: false`(프롬프트·응답을 지출 로그에 저장하지 않음)를 포함합니다. `DATABASE_URL`과 `LITELLM_MASTER_KEY`는 환경 변수로 줍니다.

## 설치

### 1. LiteLLM 설정

고른 경로의 견본을 LiteLLM `config.yaml`로 사용합니다.

- A: LiteLLM이 MINT의 사설 루트 인증서를 신뢰해야 합니다. MINT 서버에서 `./mint.sh ca`를 실행하면 `deploy/ca/root.crt`가 만들어집니다. 이 인증서를 공인 CA 묶음과 합쳐 LiteLLM의 `SSL_CERT_FILE`로 지정합니다.
- B: `mint_guardrail.py`를 설정 파일과 같은 폴더에 두고 LiteLLM에 다음 환경 변수를 줍니다.

| 변수 | 설명 |
| --- | --- |
| `MINT_GATEWAY_URL` | MINT 주소입니다. 예: `https://<MINT 주소>`. 필수이며 없으면 LiteLLM 기동이 실패합니다. |
| `MINT_CA_FILE` | MINT 루트 인증서 PEM 경로입니다. 사설 CA일 때 지정합니다. |
| `MINT_TIMEOUT_SECONDS` | MINT 응답 대기 시간입니다. 기본 10초입니다. |

LiteLLM이 MINT의 `/api/addon/v1/*`에 닿을 수 있어야 합니다(B).

### 2. 매핑 파일 작성

`sync-bindings.example.json` 형식으로 매핑 파일을 만듭니다. 비밀 값은 넣지 않습니다.

| 필드 | 내용 |
| --- | --- |
| `users[].mint_user_id` | MINT 계정 아이디입니다. |
| `users[].litellm_user_id` | 대응하는 LiteLLM 사용자입니다. |
| `users[].key_hashes` | 그 사용자 가상 키의 SHA-256 값 목록입니다. |
| `teams[].team_id`, `mint_user_ids` | LiteLLM 팀과 그 팀의 MINT 구성원입니다. 팀을 쓰지 않으면 비워 둡니다. |
| `workers` | 각 LiteLLM 워커에 직접 연결되는 origin 전체입니다. 로드밸런서 주소 하나로는 워커별 세션 종료를 확인할 수 없습니다. |

견본의 `0`으로 채운 해시는 형식 예시입니다. 매핑은 운영자가 명시한 연결이며, 호출자의 주장으로 만들어지지 않습니다.

### 3. 동기화 켜기

LiteLLM 관리자 키(proxy admin)를 파일에 한 줄로 저장하고 MINT 서버의 `deploy` 폴더에서 실행합니다.

```bash
cd deploy
./mint.sh litellm enable --url https://<LiteLLM 관리 주소> --bindings 매핑.json --route mint < 관리-키-파일
./mint.sh litellm status
```

| 명령 | 설명 |
| --- | --- |
| `./mint.sh litellm enable --url <관리 origin> --bindings <매핑.json> [--ca <PEM>] [--route mint\|direct] < 관리 키 파일` | 동기화를 켭니다. `--url`은 경로·쿼리 없는 `https://호스트:포트`입니다. `--ca`는 LiteLLM 관리 주소의 사설 CA PEM입니다. `--route` 기본값은 `mint`입니다. |
| `./mint.sh litellm check` | 쓰기 없는 점검을 실행합니다. |
| `./mint.sh litellm status` | 점검 결과와 서버별 동기화 상태를 보여 줍니다. |
| `./mint.sh litellm rotate-key < 새 키 파일` | 관리 키를 바꿉니다. 재기동하지 않습니다. |
| `./mint.sh litellm disable` | 동기화를 끕니다. |

`enable`의 동작은 다음과 같습니다.

- 매핑을 `deploy/litellm/`에 두고, 관리 키는 게이트웨이만 읽을 수 있는 파일로 저장합니다. 관리 키는 명령줄, `.env`, 로그에 남지 않습니다.
- 점검(매핑 형식, 관리 키, 각 워커 응답, 팀 매핑이 있을 때의 명시적 키 접근 설정)이 통과해야 게이트웨이를 다시 만들어 적용합니다. 실패하면 적용하지 않지만 `.env`는 바뀌어 있을 수 있으니 원인을 고치고 다시 실행합니다.
- 관리 주소는 MINT 게이트웨이에서 닿을 수 있어야 합니다.

`.env`의 관련 값은 `enable`이 채웁니다. 직접 적을 필요는 없습니다.

| 변수 | 설명 |
| --- | --- |
| `MINT_LITELLM_SYNC_URL` | LiteLLM 관리 origin입니다. 비어 있으면 동기화가 꺼집니다. |
| `MINT_LITELLM_SYNC_KEY_FILE` | 관리 키 파일 경로입니다. |
| `MINT_LITELLM_SYNC_CA_FILE` | 관리 origin을 검증할 사설 CA 경로입니다. |
| `MINT_LITELLM_ROUTE` | `mint`(기본) 또는 `direct`입니다. 바꾸면 다음 주기에 같은 서버의 주소와 인증이 다시 반영됩니다. |
| `MINT_LITELLM_SYNC_RECHECK_SECONDS` | LiteLLM 상태 재조회 주기입니다. 기본 300초, 최소 30초입니다. |
| `MINT_LITELLM_KEY_ACCESS_CONFIRMED` | 아래 팀 매핑 항목을 참고하세요. |

**팀 매핑을 쓰는 경우.** LiteLLM이 `require_key_mcp_access_defined` 값을 API로 보여 주지 않으면 MINT는 서버를 만들지 않습니다. 설정 파일에 `require_key_mcp_access_defined: true`가 있는지 확인한 뒤 `.env`에 `MINT_LITELLM_KEY_ACCESS_CONFIRMED=1`을 넣고 `./mint.sh up`으로 다시 기동합니다. 팀 매핑이 없으면 MINT가 키에만 권한을 직접 부여하므로 이 값이 필요하지 않습니다. 애드온은 이 설정을 바꾸지 않습니다.

### 4. 직원 계정

직원 PC 키트 없이 LiteLLM으로만 MCP를 쓰는 직원은 다음 명령으로 만듭니다.

```bash
./mint.sh add-account <아이디> --role 직원 --ai-gateway
```

직원은 MINT의 토큰 엔드포인트(`/.well-known/oauth-authorization-server`의 `token_endpoint`)에서 자기 MCP 토큰을 받아 위 표의 헤더에 넣습니다. 사용 대상으로 승인된 직원에게만 도구가 보입니다.

## 동작

- MINT에서 도입 승인과 등록이 끝나면 LiteLLM에 서버가 생기고, 매핑된 키·팀에 승인된 도구만 부여됩니다.
- 등록 해제, 중지, 폐기, 기한 만료 때는 서버와 키·팀 권한, 저장된 자격, 해당 사용자의 LiteLLM 세션을 지우고 다시 읽어 확인합니다. 집계 세션은 서버별로 구분되지 않아 그 사용자의 다른 MCP 세션도 함께 종료될 수 있습니다.
- 완료 뒤에도 재조회 주기마다 LiteLLM 상태를 읽습니다. LiteLLM 쪽에서 서버, 도구, 키 권한, 팀 구성원이 바뀌었으면 MINT 상태로 되돌립니다.
- 키 또는 팀 하나의 매핑이 맞지 않으면 그 대상만 권한을 받지 못하고, 다른 직원은 계속 사용할 수 있습니다.
- 콘솔의 서버 등록부에 동기화 상태(`동기화 대기`, `동기화 실패`, `동기화 완료`)가 표시됩니다. 동기화를 켜지 않은 설치에는 표시되지 않습니다.
- B의 가드레일은 판정이 허용, 경보, 제한이고 원장에 기록되었을 때만 호출을 진행합니다. 제한이면 MINT가 돌려준 인자로 바꿔 보냅니다. MINT가 답하지 않거나 토큰이 없거나 그 밖의 판정이면 호출을 막습니다. 호출 뒤에는 결과의 SHA-256과 크기, 오류 여부를 MINT에 기록합니다. MINT가 기록을 거절하면 LiteLLM 로그에 경고를 남깁니다.

### 정적 YAML 생성

동기화를 쓰지 않는 설치에서는 `gen_mcp_servers.py`로 서버 목록 YAML을 만들어 LiteLLM 설정에 넣을 수 있습니다. 동기화를 켰다면 쓰지 않습니다.

```bash
MINT_ADMIN_TOKEN=<콘솔 로그인 토큰> python gen_mcp_servers.py \
  --gateway https://<콘솔 주소> --api-prefix /gw --base-url https://<MINT 주소> > mcp_servers.yaml
python gen_mcp_servers.py --registry-file registry.json --base-url https://<MINT 주소> > mcp_servers.yaml
```

| 옵션 | 설명 |
| --- | --- |
| `--gateway` | 서버 목록을 읽을 MINT 관리 API 주소입니다. 환경 변수 `MINT_ADMIN_TOKEN`이 필요합니다. |
| `--api-prefix` | 관리 API 경로 접두어입니다. 기본 `/api`이며 콘솔 주소로 읽을 때는 `/gw`입니다. |
| `--registry-file` | 서버 목록 응답을 저장한 JSON 파일입니다. `--gateway` 대신 씁니다. |
| `--base-url` | LiteLLM이 접속할 MINT MCP 주소입니다. 기본값은 `--gateway`입니다. |
| `--ca-file` | 사설 CA 인증서(PEM)입니다. |

운영 중인 서버만 `oauth_delegate`로 나열합니다. LiteLLM이 헤더 `x-mcp-<별칭>-authorization`을 첫 `-`에서 나누어 읽으므로, 서버 ID의 `-`는 별칭에서 `_`로 바꿉니다. 운영 중인 서버가 없으면 YAML을 만들지 않습니다.

## 한계

- B는 판정과 실제 전송 사이를 LiteLLM이 수행합니다. 판정 뒤 승인이 철회되어도 이미 진행한 호출은 막지 못합니다. 사람 승인이 필요한 판정은 차단으로만 끝나고, 결과 본문이 MINT를 거치지 않아 출력 검사와 마스킹, 도구 설명 계약 확인이 적용되지 않습니다. 최종 전송 검사가 필요하면 A를 사용합니다.
- LiteLLM 관리자가 등록 서버를 직접 바꾸면 B에서는 계약 확인이 적용되지 않습니다. 동기화 대상 서버는 재조회 때 되돌립니다.
- `direct`로 자동 등록되는 서버는 자격이 필요 없는 HTTP 서버뿐입니다. 자격이 필요한 서버는 `mint` 경로로 등록합니다.
- 직원 PC에서 실행하는 로컬 MCP 서버는 두 경로 모두 LiteLLM에 등록하지 않습니다.
- 동기화는 설정된 LiteLLM 관리 상태와 `workers`에 적은 워커, 열거한 사용자 범위를 확인합니다. 외부 제공자가 발급한 토큰의 원격 폐기, 이미 전송된 호출의 취소, 열거하지 않은 워커는 확인하지 않습니다.
- 여러 독립 MINT가 같은 서버 ID를 함께 관리하는 구성은 지원하지 않습니다. 단일 LiteLLM 워커에서 검증했으며, 여러 워커와 분산 캐시는 확인하지 않았습니다.
- LiteLLM 관리자의 동시 권한 편집과 읽기 이후의 외부 변경을 원자적으로 막지 않습니다.
- 직원 하네스의 헤더 자동 구성은 제공하지 않습니다. 직원이 토큰을 받아 헤더에 넣습니다.
- `./mint.sh litellm disable` 뒤에도 LiteLLM에 이미 반영된 서버와 권한은 남습니다. LiteLLM 관리자가 정리합니다.
- 백업에는 매핑과 CA가 포함되고 관리 키는 포함되지 않습니다. 복구 뒤 `rotate-key`로 키를 다시 넣습니다.
