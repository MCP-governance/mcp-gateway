# v3 아키텍처 — 직원 PC의 AI 하네스와 MCP 게이트웨이

> 다음 AI 작업자에게: 이 문서가 **정본 설계**다. 코드와 이 문서가 다르면 코드를 읽고 이 문서를 고친다.
> 결정의 이유는 [DECISIONS.md](DECISIONS.md)(v3는 D-30~D-35)에, 그림은 [architecture.html](architecture.html)
> (archify로 생성)에 있다.

## 1. 한 문장 요약

직원은 **자기 PC에서 Claude Code·Codex CLI·Gemini CLI·OpenCode 같은 AI 하네스를 평소처럼** 쓰고, 하네스가
MCP 서버를 부르는 통신은 회사가 배포한 **관리형 설정**에 따라 전부 **Gateway의 서버별 MCP 엔드포인트
(`/mcp/<server>/`)**로 간다. Gateway는 모든 도구 호출을 신원·계약·자원 분류·개인정보·OPA 정책으로 **실행 전에**
판정하고, 허용된 호출만 내부 `tools` 망의 **실제 MCP 서버 10종**으로 전달한다. 하네스가 쓰는 LLM은 회사 LLM
게이트웨이(LiteLLM, 직원별 가상 키) 뒤의 로컬 모델이다. 웹 Console은 관제·승인·계약 검토·종료 판정만 하고
**MCP를 호출하지 않는다.**

v2와의 차이: v2는 PC에 손으로 짠 에이전트(`office_agent.py`)가 있었다. v3는 그것을 지우고 **공식 배포판 하네스를
그대로** 설치했다. 하네스를 고치지 않고, 회사가 하는 일은 실제 IT 부서가 하는 일(관리형 설정 배포, SSO 자격
도우미, 단말 에이전트)로 한정한다(D-30).

## 2. 구성도

```text
                    host loopback (127.0.0.1, 포트는 .env로 바꿀 수 있음)
     :CONSOLE_PORT Console·IdP   :GATEWAY_PORT Gateway API   :GITEA_PORT 회사 Gitea
                │                          │
┌───────────────┼──────────────── office (internal) ─────────────────────────────────────────────┐
│  ws-ysg Claude Code   ws-jwj Codex CLI   ws-pse Gemini CLI   ws-nkk OpenCode(+섀도 설정)          │
│  (네 PC 모두 하네스 4종 설치 · /etc/* 관리형 설정 · bob-sso · 단말 에이전트)                        │
│     │ ① SSO 토큰(IdP)      │ ② LLM(LiteLLM 가상 키)             │ ③ MCP(/mcp/<server>/)           │
│     ▼                     ▼                                    ▼                                │
│  agent-service(IdP·Console)   llm-gateway(LiteLLM) ──model──► ollama     gateway ──policy──► opa  │
└───────────────────────────────────────────────────────────────┼─────────── privacy ──► presidio ─┘
                                                                │ tools (internal) — PC·Console은 이 망에 없다
      mcp-filesystem mcp-git mcp-fetch mcp-memory mcp-desktop mcp-postgres mcp-redis mcp-email mcp-gitea mcp-playwright
                                                                │ corp (internal) — 회사 시스템
      corp-db(PostgreSQL) corp-redis corp-mail(GreenMail) corp-git(Gitea) intranet(nginx)
                                                                │ internet (internal, 모사) — external-web
```

| 망 | 붙는 서비스 | 의미 |
| --- | --- | --- |
| `edge` | agent-service, gateway, corp-git | 호스트 loopback 게시 전용 |
| `office` | 직원 PC 4대, agent-service, gateway, gateway-sse, llm-gateway | 직원 PC가 닿는 유일한 망 |
| `tools` | gateway, gateway-sse, mcp-* | **Gateway만** MCP 서버에 닿는다 |
| `corp` | mcp-email·gitea·postgres·redis·fetch·playwright, corp-*, intranet, corp-seed | MCP 서버의 하위 시스템 |
| `ops` | gateway, corp-git | 종료 판정 증거 수집(Gitea 관리 API) |
| `internet` | external-web, mcp-fetch, mcp-playwright | 외부 인터넷 모사(유출 목적지) |
| `model` | ollama, llm-gateway, intake-worker, agent-service | 추론 |
| `data` | db, gateway, agent-service, intake-worker, llm-gateway | Gateway DB(판정·감사·LiteLLM) |
| `policy` | gateway, gateway-sse, opa, (opa-candidate) | 정책 판정 |
| `privacy` | gateway, gateway-sse, presidio-analyzer·anonymizer | 개인정보 검사·마스킹(D-24) |
| `telemetry` | gateway, gateway-sse, agent-service, intake-worker, OTel Collector | 애플리케이션은 Collector에만 OTLP를 보내고, Collector는 민감 속성을 제거한 뒤 내부 Audit API로 전달 |
| `scanner` | intake-worker, ollama-pull | 외부 다운로드(유일한 egress) |

모든 망은 `.env`의 `MCP_NET_PREFIX` 아래 명시 `/24`(D-24). `internal: true`가 아닌 망은 `edge`와 `scanner`뿐이다.
직원 PC는 인터넷에 나갈 수 없어서 하네스의 텔레메트리·자동 업데이트·모델 카탈로그 조회도 망에서 막히고, 설정으로도 끈다.

운영 추적 경로는 `서비스 SDK → OTel Collector → Audit API → runtime_evidence`다. 토큰·MCP 인자·결과·HTTP 본문은
trace에 넣지 않고 감사 DB에만 둔다. Collector와 Audit API가 허용 목록으로 민감 attribute를 이중 제거한다(D-42).
A.I.G `mcp-scan`은 Gateway 요청
경로 안에서 실행하지 않는다. 격리된 `intake-worker`가 고정 commit 또는 등록 endpoint를 검사하고 SARIF 결과를 DB에
저장하며, Console의 **AI 보안 검사** 화면은 그 작업을 조회·실행·취소·재시도한다.

## 3. 직원 PC — 하네스와 관리형 설정

이미지 `mcpgw/workstation:3.0`(`full_stack_lab/workstation/Dockerfile`)은 `node:22-bookworm-slim`에 하네스를
**공식 npm 패키지·고정 버전**으로 설치한다.

| 하네스 | 버전 | 이 랩의 주 사용자 | 헤드리스 실행 | LLM 형식(→ LiteLLM) | MCP clientInfo |
| --- | --- | --- | --- | --- | --- |
| Claude Code | 2.1.282 | ws-ysg 양승권 | `claude -p … --output-format stream-json` | Anthropic `/v1/messages` | `claude-code` |
| Codex CLI | 0.157.0 | ws-jwj 정원재 | `codex exec --json` | OpenAI `/v1/responses` | `codex-mcp-client` |
| Gemini CLI | 0.61.0 | ws-pse 박소은 | `gemini -p … --output-format stream-json` | Gemini `/v1beta/models/*:generateContent` | `gemini-cli-mcp-client` |
| OpenCode | 1.18.32 | ws-nkk 권노경(협력사) | `opencode run --format json` | OpenAI `/v1/chat/completions` | `opencode` |
| MCP Inspector CLI | 2.8.0 | (스크립트 모드) | `mcp-inspector --cli` | — | `inspector-cli` |

Antigravity는 GUI 앱이라 랩에서 실행하지 않는다. 같은 Gateway URL을 Antigravity의 `mcp_config.json`(원격 서버 키는
`serverUrl`)에 넣으면 되고, 단말 에이전트는 그 파일도 인벤토리한다.

### 3.1 관리형 설정은 레지스트리에서 생성

`workstation/managed/render.py`가 **이미지 빌드 때** `registry/catalog.toml`의 서버 목록으로 네 하네스의 설정을 만든다.
서버 하나에 URL 하나(`http://gateway:8080/mcp/<server>/`)이고, 네 형식이 서로 어긋날 수 없다. 서버를 추가·폐기하면
카탈로그를 고치고 PC 이미지를 다시 빌드한다(MDM 재배포와 같은 자리). CI가 네 파일의 서버 목록을 레지스트리와 대조한다.

| 하네스 | 파일(시스템 관리형 위치) | 서버 항목 | 토큰 | 하네스 안의 도구 승인 |
| --- | --- | --- | --- | --- |
| Claude Code | `/etc/claude-code/managed-mcp.json`(배타적) + `managed-settings.json` | `type:"http"`, `url` | `headersHelper: bob-sso header` | `permissions.allow: mcp__<server>` |
| Codex CLI | `/etc/codex/managed_config.toml` | `[mcp_servers.<s>] url` | `bearer_token_env_var = "BOB_SSO_TOKEN"` | `default_tools_approval_mode = "approve"` |
| Gemini CLI | `/etc/gemini-cli/settings.json`(시스템 설정, 최우선) | `httpUrl` | `headers.Authorization = "Bearer $BOB_SSO_TOKEN"` | `trust: true` |
| OpenCode | `/etc/opencode/opencode.json`(`OPENCODE_CONFIG`) | `type:"remote"`, `url` | `headers … {env:BOB_SSO_TOKEN}` | 기본 허용 |

하네스 안의 도구 승인은 IT가 회사 도구를 **사전 승인**한 것이다. 사람에게 되묻지 않을 뿐 판정은 Gateway가 한다 —
하네스 쪽 승인을 끄면 차단이 두 군데로 나뉘어 어느 쪽이 막았는지 흐려진다.

LLM 연결도 관리형 설정이 정한다: Claude `ANTHROPIC_BASE_URL=http://llm-gateway:4000`(모든 모델 슬롯 `bob-assistant`),
Codex `model_provider=bob`(`wire_api="responses"`, `env_key="BOB_LLM_KEY"`, `requires_openai_auth=false`), Gemini
`GOOGLE_GEMINI_BASE_URL`(`/etc/profile.d/bob-harness.sh`), OpenCode `@ai-sdk/openai-compatible` 공급자. 직원의 LiteLLM
가상 키는 `BOB_LLM_KEY` 하나이고 profile 스크립트가 하네스별 이름(`ANTHROPIC_AUTH_TOKEN`, `GEMINI_API_KEY`)으로 내어 준다.

### 3.2 PC에 회사가 더한 것

| 파일 | 역할 |
| --- | --- |
| `bin/bob-sso` | SSO 자격 도우미. IdP `/oauth/token`(password grant, `client_id`=워크스테이션 — SSO 로그인의 대역)으로 로그인하고 refresh로 갱신, `~/.cache/bob-sso/token.json`(flock, 0600). `token` / `header` |
| `bin/bob-ask` | 직원이 하네스에 입력하는 한 번의 지시를 헤드리스로 실행. `--servers`로 작업에 필요한 서버만 켠다(하네스 고유 스위치). 원본 이벤트는 `~/transcripts/` |
| `bin/workday` | 시나리오(`scenarios/<ws>.toml`) 실행. `llm`=하네스에 자연어 지시, `scripted`=MCP Inspector CLI가 같은 URL·토큰으로 정해진 호출. 판정은 직원 토큰으로 Gateway `/api/activity`에서 읽는다 |
| `bin/harness-check` | 하네스 4종이 관리형 서버 전부에 Gateway로 붙는지 **모델 없이** 확인(`mcp list`, Codex는 app-server `mcpServerStatus/list`) |
| `managed/harness-prompt.md` | 소형 CPU 모델용 짧은 시스템 프롬프트(컴팩트 모드) |
| `shadow/opencode.json` | 협력사 PC(ws-nkk)에 사람이 직접 추가한 설정: Gateway 우회 직결(`mcp-filesystem:8000`)과 개인 stdio 서버 |
| `endpoint_agent.py` | 저장소 루트 `endpoint-agent/`(D-29). 하네스 설정 파일 인벤토리와 리스너 관측 |

**컴팩트 모드**(`BOB_HARNESS_COMPACT=1`, 기본): CPU의 소형 모델은 코딩 에이전트의 수만 토큰 프롬프트를 쓸 만한 시간에
읽지 못한다. 그래서 하네스의 시스템 프롬프트를 짧게 바꾸고 내장 도구(셸·편집·웹·이미지·서브에이전트)를 끈다 —
Claude `--tools "" --system-prompt-file`, Codex `model_instructions_file` + `--disable shell_tool …`, Gemini `GEMINI_SYSTEM_MD`,
OpenCode `--agent bob`. **MCP 경로는 그대로**다: 도구 목록 조회와 호출은 하네스의 MCP 클라이언트가 한다. LiteLLM 뒤에
클라우드 모델을 붙이면 `0`으로 하네스 본래 프롬프트를 쓴다.

## 4. 호출 한 건의 흐름

1. 직원이 하네스에 지시한다(랩에서는 `bob-ask` 또는 `workday`가 대신 입력).
2. 하네스가 관리형 설정의 MCP 서버마다 `initialize` → `tools/list`를 `/mcp/<server>/`로 보낸다. 토큰은 `bob-sso`가 준다.
   토큰이 없거나 틀리면 `401` + `WWW-Authenticate: Bearer resource_metadata=…`(RFC 9728).
3. `main.ServerPath`가 URL의 서버 이름을 떼어 `scope["mcp_server"]`에 넣고 같은 MCP 앱으로 넘긴다. 등록되지 않은 이름은
   404(집계 엔드포인트로 새지 않는다). `tools/list`는 **승인된 스키마**를 그 서버의 **고유 도구 이름**으로 돌려준다
   (협력사에게는 읽기 도구만).
4. 하네스가 LiteLLM에 모델 요청을 보낸다(가상 키). LiteLLM이 하네스 형식을 번역해 Ollama `/v1`로 넘긴다(D-31).
5. 모델이 도구를 고르면 하네스가 `tools/call`을 보낸다. Gateway는 신원을 **transport의 토큰**으로만 정하고, 하네스가
   말한 자기 정보(`initialize`의 clientInfo, User-Agent)와 PC(토큰의 `client_id`)는 **기록만** 한다.
6. `classify.py`가 인자에서 자원(경로·URL·SQL 테이블·저장소·수신자·명령·키)을 뽑아 등급과 실효 행위(r/w/x)를 정한다.
7. 승인 스키마 검증(`P-INPUT-SCHEMA-001`) → 쓰기·실행·외부 목적지면 **Presidio**가 나가는 인자의 개인정보를 찾는다
   (불능이면 `P-DATA-INSPECTION-001`). 최근 10분 중요정보 열람 뒤 외부 전송이면 연쇄 표지.
8. OPA가 판정한다: Allow / Alert / Restrict / Approval / Block(→ [POLICY.md](POLICY.md)). 단말 에이전트가 섀도 설정을
   보고한 PC의 호출은 `MCP-SHADOW-001` 경보가 붙는다.
9. 실행이면 같은 연결에서 upstream `tools/list`를 다시 받아 계약 해시를 대조한 뒤 호출(`core._call_upstream`), 달라졌으면
   `MCP-CATALOG-001`.
10. 결과는 크기 제한·주입 표지 검사 뒤 Presidio가 개인정보를 가린다. 판정·정책 입력·클라이언트 정보가 해시 체인 감사
    원장(`decisions`)에 남는다. 하네스는 결과(또는 `[MCP Gateway · 차단 …]` 문장)를 모델에 넘기고, 모델이 직원에게 답한다.

## 5. Gateway의 MCP 입구

| 경로 | 도구 이름 | 쓰는 쪽 |
| --- | --- | --- |
| `/mcp/<server>/` | 서버 고유 이름(`read_text_file`) | 하네스 관리형 설정(v3 기본) |
| `/mcp/` | `<server>__<tool>`(`filesystem__read_text_file`) | URL 하나만 받는 클라이언트, acceptance |
| `gateway-sse :8081 /sse` | `<server>__<tool>` | SSE만 되는 구형 클라이언트 |
| stdio(`app.stdio_entry`) | `<server>__<tool>` | 스폰 시 `GATEWAY_STDIO_PRINCIPAL`로 신원 고정 |

모두 같은 `mcp_facade.build_mcp()`와 `core.execute_call()`을 지난다. 감사 행의 `client`에는
`harness{name, version, user_agent}`와 `endpoint`(서버 id 또는 `aggregate`)가 남아 Console이 "어느 하네스가 어느 서버를
불렀는가"를 그린다(개요 → 하네스·서버).

## 6. LLM 경로

| 하네스 | 요청 | LiteLLM이 받는 곳 |
| --- | --- | --- |
| Claude Code | Anthropic Messages | `/v1/messages` |
| Codex CLI | OpenAI Responses(유일한 wire_api) | `/v1/responses` |
| Gemini CLI | Gemini generateContent | `/v1beta/models/bob-assistant:generateContent` |
| OpenCode | OpenAI Chat Completions | `/v1/chat/completions` |

LiteLLM(`llm/litellm.yaml`)은 네 형식을 모두 `bob-assistant` → Ollama `/v1`(`openai/` 공급자)로 보낸다.
`reasoning_effort: none`으로 qwen3.5의 생각 모드를 끈다(실측 70초 → 1.3초). Ollama는 모델 하나·요청 하나만 올린다
(`OLLAMA_MAX_LOADED_MODELS=1`, `NUM_PARALLEL=1`, KV 캐시 q8). 기본 모델은 `qwen3.5:2b-q4_K_M`(적재 1.7GB, 12K 컨텍스트),
품질이 필요하면 `LOCAL_LLM_MODEL=qwen3.5:4b`(D-32). 가상 키는 `llm-provision`이 직원 이메일에 묶어 발급하고 사용량은
LiteLLM DB에 직원 단위로 남는다.

## 7. 자원 분류와 정책 입력

정책은 도구 이름이 아니라 **자원**을 본다. OPA 입력의 핵심 필드:

```json
{
  "principal": {"role": "employee", "department": "플랫폼개발팀", "shadow_endpoints": 0},
  "tool": {"server": "filesystem", "name": "read_text_file", "action": "r", "base_action": "r"},
  "resource": {"kind": "path", "id": "/shared/confidential/hr/salary-2026.csv", "data_class": "important"},
  "resources": [ ... ],
  "destinations": [{"kind": "email", "value": "x@gmail.com", "external": true}],
  "relationship": {"defined": true, "ids": ["UR-FS-SHARED"], "in_scope": false, "outside": ["/workspace/notes.md"]},
  "request": {"untrusted_markers": [], "dlp": ["kr-rrn"]},
  "contract": { ... }, "context": { ... }, "approval": {"granted": false}
}
```

`relationship`은 그 서버의 ACTIVE 이용 관계가 허용한 자원(`[[usage_relationships]] allowed_resources`)과 이번 호출의
경로·저장소·테이블·메일함 자원을 대조한 결과다(`classify.outside_scope`, D-39). 범위 밖이면 `P-SCOPE-001` 경보.

분류 규칙은 `registry/catalog.toml`에 데이터로 둔다. 규칙에 없는 자원은 **important**로 본다(fail-safe). 하네스
정보는 입력에 넣지 않는다 — 하네스가 스스로 이름을 대기 때문이다.

## 8. 신원

| 주체 | 자격 | 발급·검증 |
| --- | --- | --- |
| 직원의 하네스(MCP) | OAuth 접근 토큰(Ed25519 JWT, 10분) + refresh(8시간) | IdP `/oauth/token`(`bob-sso`), Gateway가 서명·폐기목록·관리대장으로 검증 |
| 직원의 하네스(LLM) | LiteLLM 가상 키 `sk-…`(`BOB_LLM_KEY`) | LiteLLM이 검증, 사용량은 LiteLLM DB |
| Console 사용자 | 로그인 세션 JWT(30분) | `/auth/mock-login`, 로그아웃은 즉시 폐기목록 |
| PC의 단말 에이전트 | 장치 키 | 엔드포인트 평면(인벤토리·리스너 보고만) |
| Gateway → upstream | 없음(망 격리) | MCP 명세대로 **직원 토큰을 upstream에 넘기지 않는다** |
| MCP 서버 → 하위 시스템 | 서버 보유 자격 | email: 메일 계정, gitea: PAT, postgres/redis: 접속 문자열 |

IdP는 RFC 8414 메타데이터, RFC 7009 폐기, RFC 7662 조사를 제공하고 Gateway는 RFC 9728 보호 자원 메타데이터를 낸다.
하네스가 MCP OAuth 인가 코드 흐름을 직접 하지 않고 `bob-sso`를 쓰는 것은 헤드리스 컨테이너에 브라우저가 없어서다
(실제 PC라면 하네스의 OAuth 로그인 — ROADMAP).

## 9. 섀도 MCP와 단말

강제 경로 밖의 MCP는 두 겹으로 다룬다. **망**: 직원 PC의 `office` 망에서는 MCP 서버·회사 DB·인터넷에 닿지 않는다
(`tests/security_regression.sh`가 실제 소켓으로 확인). **관측**: 단말 에이전트(3.0.0)가 하네스 설정 파일을 읽어 보고한다 —
`~/.claude.json`(`projects.<dir>.mcpServers` 포함), `.mcp.json`, `/etc/claude-code/managed-mcp.json`, `~/.codex/config.toml`,
`/etc/codex/managed_config.toml`, `~/.gemini/settings.json`·`/etc/gemini-cli/settings.json`, `opencode.json`,
Antigravity `mcp_config.json`, Cursor·VS Code·Claude Desktop 설정. Gateway 아래 URL(`/mcp/…`)을 가리키는 항목은 Gateway 경유,
등록 서버를 직접 가리키면 섀도, 폐기 서버를 가리키면 폐기 잔존(종료 판정 C1). ws-nkk의 개인 설정이 섀도로 보고되고,
그 PC의 호출에는 `MCP-SHADOW-001` 경보가 붙는다.

## 10. Console

- `agent-service`가 정적 파일과 IdP를 같이 서빙한다. CSP same-origin(인라인 스크립트·스타일 없음). 브라우저는 Gateway API를
  `/gw/<path>` 프록시로 부르고, 관리자가 아니면 `activity`·`health`만 통과한다.
- v3 화면은 머리·KPI 스트립·**페이지 내 탭**·차트가 앞선 패널로 나뉜다. 차트는 내장한 Apache ECharts
  (`agent_static/vendor/echarts.min.js`), 툴팁은 캔버스(richText)라 감사 로그의 문자열이 HTML로 들어가지 않는다.
  사용법·의의 설명은 UI에 두지 않는다(팀 가이드라인 문서 몫) → [CONSOLE_UI.md](CONSOLE_UI.md), D-33.

## 11. 종료·폐기 (논문 구현)

→ [TERMINATION_MODEL.md](TERMINATION_MODEL.md). 요점만:

- 분석 단위는 **이용 관계**(조직·목적·제공자·허용 자원)다. 서버 하나에 이용 관계가 여럿일 수 있다.
- 케이스를 여는 순간 Gateway가 그 관계의 모든 호출을 거부한다(`MCP-DECOMM-001`). 차단이 회수보다 먼저다.
- 회수 대상마다 C1~C4를 따로 판정하고, 전체 등급은 **가장 낮은 등급**이다. C4는 증거가 **대상의 상태**를 특정해야 충족된다.
- 하네스 설정에 폐기 서버가 남아 있으면 단말 에이전트가 폐기 잔존으로 보고해 C1 모집단에 들어간다.

## 12. 자원 예산 (참조 노트북: WSL VM 7.6GB, CPU 전용)

| 구성 | 메모리 |
| --- | --- |
| 스택(모델 제외, Presidio 소형 모델) | 약 3.0GB |
| `qwen3.5:2b-q4_K_M` @12K | +1.7GB |
| `qwen3.5:4b` @16K (선택) | +3.4GB |
| 하네스 한 번 실행 | 0.1~0.3GB |

4B 모델·16K·Codex를 함께 돌렸을 때 WSL VM이 응답을 멈춘 적이 있어(D-32) 기본값을 2B로 두었다. 첫 턴(프롬프트+도구 스키마)은
CPU에서 수십 초~2분 걸린다. 하네스 LLM 실측 결과는 DECISIONS D-31·D-32에 있다.

## 13. 디렉터리

| 경로 | 내용 |
| --- | --- |
| `full_stack_lab/console.sh` | 단일 진입점(up·workday·ask·harnesses·test·experiment·restore …) → [RUNBOOK.md](RUNBOOK.md) |
| `full_stack_lab/compose.yaml` | 전체 스택(프로필: `llm`, `llm-download`, `supply-chain`, `llm-stub`, `replay`) |
| `full_stack_lab/workstation/` | 직원 PC 이미지: `Dockerfile`, `managed/`(관리형 설정 원본·`render.py`), `bin/`(bob-sso·bob-ask·workday·harness-check), `scenarios/`, `shadow/` |
| `full_stack_lab/gateway/app/` | Gateway(FastAPI)·IdP·Console API·Console 정적 파일 |
| `…/mcp_facade.py` | MCP 서버(저수준 SDK): 서버별·집계 도구 목록, 하네스 식별 기록 |
| `…/main.py` | API, `/mcp` 마운트(`RequireBearer` → `ServerPath`) |
| `…/core.py` | 강제 경로(`execute_call`), 정책 입력 조립(이용 관계 범위 포함), 계약 확인, 감사 체인, 연결 확인(`check_server`) |
| `…/contract.py` | 순수 계약 모듈: `canonical_hash`, OPA 결과 스키마, 감사 체인 열 집합·fingerprint(D-41) |
| `…/classify.py` | 자원 추출·분류·DLP (`python -m app.classify`로 self-check) |
| `…/endpoint_plane.py` | 단말 인벤토리 분류(Gateway 경유·섀도·폐기 잔존) |
| `…/decommission.py` | 종료 케이스·회수 대상·증거·판정·판정서 |
| `…/privacy.py` | Presidio 분석·마스킹 호출 |
| `…/agent_static/` | Console(`console.js`, `charts.mjs`, `console-state.mjs`, `console.css`, `vendor/echarts.min.js`) |
| `full_stack_lab/privacy/` | Presidio analyzer 파생 이미지(spaCy 소형 모델, D-32) |
| `full_stack_lab/llm/litellm.yaml` | LLM 게이트웨이 설정 |
| `full_stack_lab/registry/` | `catalog.toml`(서버·분류·이용 관계 — 하네스 설정의 원본이기도 하다), `contracts.lock.json` |
| `full_stack_lab/opa/` | Rego 정책·테스트·관리대장·예외 |
| `full_stack_lab/mcp/` | MCP 런타임 이미지와 서버별 실행 스크립트 |
| `full_stack_lab/corp/` | 회사 시드 데이터 |
| `endpoint-agent/` | 단말 에이전트와 실제 PC 설치기(D-29) |
| `full_stack_lab/tests/` | 보안 회귀·종료 판정 흐름·콘솔 상태·검사기 |
