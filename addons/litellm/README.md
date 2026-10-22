# LiteLLM 애드온

LiteLLM이 MCP를 중앙에서 연결하는 기업도 MINT의 통제를 받게 하는 두 가지 방법이다. 둘 다 LiteLLM 1.105.0 이미지에서 확인했다
(확인 범위는 맨 아래 「확인한 것과 하지 않은 것」).

| | A. 업스트림 방식 (권장) | B. 플러그인 방식 |
| --- | --- | --- |
| 쓰는 경우 | LiteLLM의 MCP 서버가 MINT를 가리킨다 | MCP 서버를 LiteLLM에 직접 등록해 둔 채로 두어야 한다 |
| 실제 호출 | LiteLLM → MINT `/mcp/<서버>/` → MCP 서버 | LiteLLM → MCP 서버 |
| MINT가 보장하는 것 | 판정, 전송 직전 재검사, 승인, 출력 통제, 기록 전부 | 호출 직전 판정과 사후 기록. 판정과 전송 사이 경쟁은 막지 못한다 |
| 직원 신원 | 직원마다 자기 MINT 토큰을 보낸다 | 같다 |
| 파일 | `gen_mcp_servers.py` | `mint_guardrail.py` |

공통 전제: **LiteLLM에 공유 서비스 키를 넣지 않는다.** 직원이 자기 MINT 토큰(직원 PC 키트가 발급)을 LiteLLM 호출에 실어 보낸다.
LiteLLM이 주장하는 사용자·팀은 MINT가 기록만 하고 판정에 쓰지 않는다.

## A. 업스트림 방식 — 설치 3단계

1. **목록 만들기** (MINT 관리자 콘솔 토큰이 필요하다. 토큰은 환경 변수로만 준다)
   ```bash
   MINT_ADMIN_TOKEN=<콘솔 로그인 토큰> python gen_mcp_servers.py \
     --gateway https://<콘솔 주소> --api-prefix /gw --base-url https://<게이트웨이 주소> > mcp_servers.yaml
   ```
   콘솔 토큰을 쓰기 싫으면 콘솔에서 `GET /api/registry` 응답을 파일로 저장해 `--registry-file`로 넘긴다.
   운영 중인 서버만 나오고, 서버 ID의 `-`는 LiteLLM 별칭 규칙 때문에 `_`로 바뀐다(`my-docs` → `my_docs`).
2. **LiteLLM 설정에 붙이기**: `mcp_servers.yaml`의 내용을 LiteLLM `config.yaml`의 `mcp_servers:`로 옮기고 다른 MCP 서버는 등록하지 않는다.
   `llm/standalone/`(망이 닫힌 구성)을 쓰면 `litellm.yaml`의 같은 자리에 넣고 `docker compose up -d`로 다시 띄운다.
3. **직원 호출**: LiteLLM 키는 `x-litellm-api-key`, MINT 토큰은 서버별 헤더로 보낸다.
   ```text
   x-litellm-api-key: <LiteLLM 가상 키>
   x-mcp-context7-authorization: Bearer <본인 MINT 토큰>
   ```
   LiteLLM은 이 토큰을 그대로 MINT에 넘기고(`oauth_delegate`) 보관하지 않는다.

관측한 동작: MINT가 승인하지 않은 계정의 토큰으로 호출하면 LiteLLM의 도구 목록이 비고, 도구를 불러도 LiteLLM이 「Tool not found」로 막는다.

## B. 플러그인 방식 — 설치 3단계

1. `mint_guardrail.py`를 LiteLLM `config.yaml`과 같은 폴더에 두고 환경 변수를 준다.
   `MINT_GATEWAY_URL=https://<게이트웨이 주소>` (사설 인증서면 `MINT_CA_FILE=<PEM 경로>`, 응답 제한은 `MINT_TIMEOUT_SECONDS`, 기본 10초).
2. `config.yaml`에 등록한다. **LiteLLM 서버 별칭은 MINT 서버 ID와 같아야** 한다.
   ```yaml
   guardrails:
     - guardrail_name: mint
       litellm_params:
         guardrail: mint_guardrail.MintGuardrail
         mode: pre_mcp_call
         default_on: true
   ```
   LiteLLM이 MINT에 닿아야 하므로 `/api/addon/v1/*` 경로를 열어 둔다(`llm/standalone/Caddyfile`의 출구에는 이미 추가했다).
   게이트웨이 앞단은 `full_stack_lab/field/Caddyfile`에 같은 경로를 추가했고, **적용하려면 제품 스택을 다시 띄워야 한다.**
3. **직원 호출**: MINT 토큰을 `Authorization`, LiteLLM 키를 `x-litellm-api-key`로 보낸다.
   ```text
   x-litellm-api-key: <LiteLLM 가상 키>
   Authorization: Bearer <본인 MINT 토큰>
   ```
   가드레일은 LiteLLM이 넘기는 `incoming_bearer_token`으로 이 토큰을 읽는다. 서버를 `extra_headers` 없이 등록하면
   이 토큰은 MCP 서버로 전달되지 않는다(기기 시험에서 확인).

동작: 도구 호출 직전에 MINT `POST /api/addon/v1/mcp-decision`을 부른다. 허용·경보·제한 실행이면 진행(제한 실행은 MINT가 준 인자로 바꿔 보냄),
그 밖의 판정·토큰 없음·MINT 응답 없음·오류는 모두 차단한다. 호출이 끝나면 결과의 SHA-256과 크기, 오류 여부를 MINT에 남긴다
(`POST /api/addon/v1/mcp-result`, 실패하면 LiteLLM 로그에만 남는다).

### 한계

- 판정과 실제 전송 사이는 LiteLLM이 한다. 그 사이 상태가 바뀌어도 MINT는 막지 못한다(A 방식은 전송 직전에 다시 검사한다).
- 사람 승인이 필요한 판정은 이 경로에서 차단으로만 끝난다. 승인 대기 건을 만들면 승인 뒤 MINT가 같은 호출을 한 번 더 보내기 때문이다. 승인이 필요한 도구는 A 방식으로 쓴다.
- 결과 본문은 MINT를 거치지 않는다. 출력 검사·마스킹은 하지 않는다(해시와 크기만 기록).
- LiteLLM에 직접 등록한 MCP 서버를 LiteLLM 관리자가 바꾸면 MINT의 계약 확인(도구 설명·스키마 고정)도 적용되지 않는다.
- 직원 토큰을 보내지 못하는 호출(서비스 계정 등)은 차단된다.

## 확인한 것과 하지 않은 것

LiteLLM 1.105.0 이미지(`ghcr.io/berriai/litellm-database:v1.105.0`), 솔루션 기기, 시험 후 컨테이너 제거. 자세한 값은
`research/llm-wiki/status/reports/2026-10-22-ai-gateway-addon.md`.

- A: 생성한 YAML로 LiteLLM이 기동하고, 직원 토큰이 서버별로 MINT까지 그대로 전달되며(토큰마다 MINT 쪽 세션이 따로 기록됨),
  변조한 토큰은 MINT가 401로 거절했다. MINT가 승인한 계정이 관리형 PC 계정뿐이라 **도구 호출 판정 행은 만들지 못했다**.
- B: 실제 LiteLLM에서 가드레일 로드, 직원 토큰 수신, 차단·제한 실행·사후 기록·판정 서버 중단 시 차단을 확인했다.
  **MINT 판정 API는 대역**(제품에 아직 배포되지 않음)이고 실제 MCP 서버는 context7이다.
