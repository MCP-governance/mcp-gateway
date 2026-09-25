# v2 아키텍처 — 사내망 직원 에이전트와 실제 MCP 서버

> 다음 AI 작업자에게: 이 문서가 v2의 **정본 설계**다. 코드와 이 문서가 다르면 코드를
> 읽고 이 문서를 고친다. 결정의 이유는 [DECISIONS.md](DECISIONS.md)에 있다.
> 그림으로 보려면 [architecture.html](architecture.html)(archify로 생성)을 연다.

## 1. 한 문장 요약

사내망(`office`)의 **직원 워크스테이션 컨테이너**가 직원별 **LiteLLM 가상 키**로 로컬 LLM을
쓰는 AI 에이전트를 돌리고, 그 에이전트는 **Gateway의 MCP 엔드포인트(`/mcp/`) 하나**만 볼 수
있다. Gateway가 모든 도구 호출을 신원·계약·자원 분류·OPA 정책으로 판정한 뒤, 내부 `tools`
망의 **실제 MCP 서버 10종** 중 하나로 전달한다. 웹 Console은 관제·승인·계약 검토·종료 판정만
하고 **MCP를 호출하지 않는다.**

## 2. 구성도

```text
                 host loopback (127.0.0.1, 포트는 .env로 바꿀 수 있음)
   :CONSOLE_PORT(8000) Console·IdP   :GATEWAY_PORT(8080) Gateway API
   :JAEGER_PORT(16686) Jaeger        :GITEA_PORT(3000) 회사 Gitea(제공자 콘솔 역할)
             │                     │
┌────────────┼─────────── office (internal) ──────────────────────────────┐
│  ws-ysg  ws-jwj  ws-pse  ws-nkk   ← 직원 워크스테이션(office-agent + endpoint-agent)
│     │  ① OAuth 토큰(IdP)   ② LLM 호출(LiteLLM 가상 키)   ③ MCP 호출(Gateway /mcp/)
│     ▼                         ▼                           ▼
│  agent-service(IdP·Console)  llm-gateway(LiteLLM) ──model──► ollama(bob-assistant)
│                               gateway ──policy──► opa
└───────────────────────────────┼──────────────────────────────────────────┘
                                │ tools (internal) — 직원 PC와 Console은 이 망에 없다
   mcp-filesystem mcp-git mcp-fetch mcp-memory mcp-desktop mcp-postgres
   mcp-redis mcp-email mcp-gitea mcp-playwright
                                │ corp (internal) — 회사 시스템
   corp-db(PostgreSQL) corp-redis corp-mail(GreenMail) corp-git(Gitea) intranet(nginx)
                                │ internet (internal, 모사) — external-web
```

| 망 | 붙는 서비스 | 의미 |
| --- | --- | --- |
| `edge` | agent-service, gateway, jaeger, corp-git | 호스트 loopback 게시 전용 |
| `office` | 워크스테이션, agent-service, gateway, gateway-sse, llm-gateway | 직원 PC가 닿는 유일한 망 |
| `tools` | gateway, gateway-sse, mcp-* | **Gateway만** MCP 서버에 닿는다 |
| `corp` | mcp-email·gitea·postgres·redis·fetch·playwright, corp-*, intranet, corp-seed | MCP 서버의 하위 시스템 |
| `ops` | gateway, corp-git | 종료 판정 증거 수집(Gitea 관리 API) |
| `internet` | external-web, mcp-fetch, mcp-playwright | 외부 인터넷 모사(유출 목적지) |
| `model` | ollama, llm-gateway, intake-worker, agent-service | 추론 |
| `data` | db, gateway, agent-service, intake-worker, llm-gateway | Gateway DB(판정·감사·LiteLLM) |
| `policy` / `telemetry` | opa / jaeger | |
| `scanner` | intake-worker, ollama-pull | 외부 다운로드(유일한 egress) |

`internal: true`가 아닌 망은 `edge`와 `scanner`뿐이다. `tests/security_regression.sh`가
"직원 PC에서 MCP 서버·회사 DB·OPA에 닿지 않는다"를 실제 소켓 연결로 확인한다.

## 3. 호출 한 건의 흐름

1. 워크스테이션의 `office-agent`가 IdP(`agent-service`)의 `/oauth/token`에서 직원 토큰을 받는다
   (password grant + refresh, `client_id` = 워크스테이션 id). 접근 토큰은 Ed25519 JWT, 수명 10분
   (`ACCESS_TOKEN_MINUTES`), refresh 8시간.
2. 같은 에이전트가 `llm-gateway`(LiteLLM)에 직원 가상 키로 채팅 완성을 요청한다. LiteLLM이
   키를 검증하고 사용량을 직원 단위로 남긴 뒤 Ollama `/v1`로 넘긴다(`openai/` 경로 — [DECISIONS.md](DECISIONS.md) D-07).
3. 모델이 도구 호출을 제안하면 에이전트는 Gateway `/mcp/`에 `tools/call`을 보낸다.
   도구 이름은 `<server>__<tool>`(예: `filesystem__read_text_file`).
4. `/mcp/`는 HTTP 단계에서 Bearer 토큰을 먼저 확인한다. 없거나 틀리면 `401` +
   `WWW-Authenticate: Bearer resource_metadata="…/.well-known/oauth-protected-resource"`(RFC 9728,
   MCP 인가 명세). 신원은 **transport의 토큰**으로만 정한다. 인자 안의 신원은 무시한다.
5. `classify.py`가 인자에서 **자원**(경로·URL·SQL 테이블·저장소·수신자·명령·키)을 뽑아 등급
   (public/nonimportant/important)과 **실효 행위**(r/w/x)를 정한다. 예: `execute_sql`의
   `SELECT`는 r, `UPDATE`는 w, `DROP`은 x. 외부 수신 메일·외부 목적지는 x로 승격.
6. 인자를 승인된 입력 스키마로 검사한다(`P-INPUT-SCHEMA-001`).
7. OPA가 판정한다: Allow / Alert / Restrict / Approval / Block (→ [POLICY.md](POLICY.md)).
8. 실행이면 **같은 연결에서** upstream의 `tools/list`를 다시 받아 설명·스키마 해시를 승인본과
   대조한 뒤 호출한다(`core._call_upstream`). 달라졌으면 실행하지 않고 `MCP-CATALOG-001`.
9. 결과는 크기 제한·주입 표지 검사를 거쳐 돌려준다. 도구 출력이 앞, Gateway 메모가 뒤다
   (작은 모델이 메모를 거절로 읽는 문제 — D-09). 판정은 해시 체인 감사 원장(`decisions`)에 남는다.

## 4. MCP 서버 10종

| id | 패키지·버전 | 전송 | 하위 시스템 | 대표 위험 |
| --- | --- | --- | --- | --- |
| filesystem | @modelcontextprotocol/server-filesystem 2026.8.31 | mcp-proxy | 공유 드라이브 `/shared` | 기밀 파일 열람·변조 |
| git | mcp-server-git 2026.8.18 | mcp-proxy | 로컬 저장소 `/repos` | 비밀 저장소 열람, 커밋 변조 |
| fetch | mcp-server-fetch 2026.8.18 | mcp-proxy | 인트라넷·외부 웹 | SSRF, URL 쿼리로 유출 |
| memory | @modelcontextprotocol/server-memory 2026.8.31 | mcp-proxy | 지식 그래프 파일 | 기억 오염 |
| desktop | @wonderwhy-er/desktop-commander 0.2.51 | mcp-proxy | 개발 샌드박스 `/workspace` | 셸 실행(x) |
| postgres | postgres-mcp 0.3.0 (unrestricted) | mcp-proxy | 회사 DB `corp-db` | 인사 테이블 열람, 파괴적 SQL |
| redis | redis-mcp-server 0.5.1 | mcp-proxy | `corp-redis` | 세션 키 열람·삭제 |
| email | mcp-email-server 1.9.1 | 네이티브 HTTP | `corp-mail`(GreenMail) | 외부 수신자로 유출 |
| gitea | gitea-mcp-server 1.7.0 | 네이티브 HTTP(stateless) | `corp-git`(Gitea) | **서버 보유 자격(PAT)** — 논문 E3 |
| playwright | @playwright/mcp 0.0.82 | 네이티브 HTTP | 인트라넷 웹 | 간접 프롬프트 주입, 외부 전송 |

stdio 전용 서버는 `mcp-proxy`(0.12.0, `--stateless`)가 Streamable HTTP로 바꿔 준다. 버전은
이미지 빌드 시점에 고정하고, 계약 해시는 `registry/contracts.lock.json`에 커밋한다
(→ [MCP_SERVERS.md](MCP_SERVERS.md)).

## 5. 자원 분류와 정책 입력

정책은 도구 이름이 아니라 **자원**을 본다. OPA 입력의 핵심 필드:

```json
{
  "principal": {"role": "employee", "department": "플랫폼개발팀", "shadow_endpoints": 0},
  "tool": {"server": "filesystem", "name": "read_text_file", "action": "r", "base_action": "r"},
  "resource": {"kind": "path", "id": "/shared/confidential/hr/salary-2026.csv", "data_class": "important"},
  "resources": [ ... ],
  "destinations": [{"kind": "email", "value": "x@gmail.com", "external": true}],
  "request": {"untrusted_markers": [], "dlp": ["kr-rrn"]},
  "contract": { ... }, "context": { ... }, "approval": {"granted": false}
}
```

분류 규칙은 `registry/catalog.toml`에 데이터로 둔다(경로 접두사, 테이블, 저장소, 키 패턴,
사내 도메인). 규칙에 없는 자원은 **important**로 본다(fail-safe).

## 6. 신원

| 주체 | 자격 | 발급·검증 |
| --- | --- | --- |
| 직원(워크스테이션) | OAuth 접근 토큰(JWT) + refresh | IdP `/oauth/token`, Gateway가 서명·폐기목록·관리대장으로 검증 |
| 직원의 LLM 사용 | LiteLLM 가상 키 `sk-...` | LiteLLM이 검증, 사용량은 LiteLLM DB |
| Console 사용자 | 로그인 세션 JWT(30분) | `/auth/mock-login`, 로그아웃은 즉시 폐기목록 |
| 워크스테이션 장치 | 엔드포인트 장치 키 | 엔드포인트 평면(인벤토리·리스너 보고만) |
| Gateway → upstream | 없음(망 격리) | MCP 명세대로 **직원 토큰을 upstream에 전달하지 않는다** |
| MCP 서버 → 하위 시스템 | 서버 보유 자격 | email: 메일 계정, gitea: PAT, postgres/redis: 접속 문자열 |

IdP는 RFC 8414 메타데이터, RFC 7009 폐기, RFC 7662 조사를 제공하고 Gateway는 RFC 9728
보호 자원 메타데이터를 낸다. 종료 판정의 증거 수집과 E1 실험이 이 표준 엔드포인트를 그대로 쓴다.

## 7. Console

- `agent-service`가 정적 파일(`gateway/app/agent_static/`)과 IdP를 같이 서빙한다. CSP는
  same-origin만 허용(인라인 스크립트·스타일 없음).
- 브라우저는 Gateway API를 `/gw/<path>` 프록시로 부른다. 프록시는 사용자의 토큰을 그대로
  넘기고, **관리자가 아니면 `activity`·`health`만** 통과시킨다(Gateway의 일부 읽기 API는 인증된
  누구에게나 열려 있어서 역할 경계를 여기서 한 번 더 긋는다).
- 화면 구조와 확장 방법은 [CONSOLE_UI.md](CONSOLE_UI.md).

## 8. 종료·폐기 (논문 구현)

→ [TERMINATION_MODEL.md](TERMINATION_MODEL.md). 요점만:

- 분석 단위는 **이용 관계**(조직·목적·제공자·허용 자원)다. 서버 하나에 이용 관계가 여럿일 수 있다.
- 케이스를 여는 순간 Gateway가 그 관계의 모든 호출을 거부한다(`MCP-DECOMM-001`). 차단이 회수보다 먼저다.
- 회수 대상마다 C1~C4를 따로 판정하고 등급을 매긴다. 전체 등급은 **가장 낮은 등급**이다.
- C4는 증거가 **대상의 상태**를 특정해야 충족된다. RFC 7009의 200 응답만으로는 충족되지 않는다.
- C3은 상태 비저장 토큰의 **만료 시각까지**를 공백 구간으로 본다(E1).
- gitea-mcp의 PAT는 게이트웨이 차단 후에도 Gitea에 유효하다(E3). 조직이 Gitea 관리자로서 폐기·확인할
  수 있으면 증거가 자동 수집되어 T1까지 오를 수 있고, 고지가 없는 email은 T3에 머문다.

## 9. 디렉터리

| 경로 | 내용 |
| --- | --- |
| `full_stack_lab/console.sh` | 단일 진입점(up·workday·test·experiment·restore …) → [RUNBOOK.md](RUNBOOK.md) |
| `full_stack_lab/compose.yaml` | 전체 스택(프로필: `llm`, `llm-download`, `supply-chain`, `llm-stub`) |
| `full_stack_lab/gateway/app/` | Gateway(FastAPI)·IdP·Console API·Console 정적 파일 |
| `…/core.py` | 강제 경로(`execute_call`), 정책 입력 조립, 계약 확인, 감사 체인 |
| `…/classify.py` | 자원 추출·분류·DLP (`python -m app.classify`로 self-check) |
| `…/upstream.py` | 등록 서버로의 Streamable HTTP 연결 |
| `…/registry.py` | `catalog.toml`·잠금 파일 읽기, DB 동기화, `python -m app.registry lock` |
| `…/mcp_facade.py` | `/mcp/` MCP 서버(저수준 SDK), 역할별 도구 목록 |
| `…/idp.py` | OAuth 2.0 토큰·폐기·조사 |
| `…/decommission.py` | 종료 케이스·회수 대상·증거·판정·판정서 |
| `…/experiments.py` | 논문 E1·E2·E3 재현 (`python -m app.experiments e1`) |
| `…/activity.py` | 감사 행 → 사람이 읽는 문장 (Console·`watch` 공용) |
| `…/acceptance.py` | Gateway 인수 시험 (`python -m app.acceptance`) |
| `full_stack_lab/registry/` | `catalog.toml`(서버·분류·이용 관계), `contracts.lock.json` |
| `full_stack_lab/opa/` | Rego 정책·테스트·관리대장·예외 |
| `full_stack_lab/mcp/` | MCP 런타임 이미지와 서버별 실행 스크립트 |
| `full_stack_lab/corp/` | 회사 시드 데이터(파일·저장소·DB·인트라넷·메일·Gitea) |
| `full_stack_lab/workstation/` | 직원 워크스테이션 이미지, `office_agent.py`, 시나리오(TOML) |
| `full_stack_lab/llm/` | LiteLLM 설정 |
| `full_stack_lab/endpoint/` | 단말 에이전트(설정 인벤토리·리스너 탐지) |
| `full_stack_lab/supply_chain/` | 도입 신청 격리 검증 워커(SBOM·SCA·SAST) |
| `full_stack_lab/tests/` | 보안 회귀·종료 판정 흐름·검사기 |
| `docs/ai/` | 다음 작업자를 위한 문서(이 폴더) |
| `docs/design/` | v1 시기의 설계 배경(통제 평면·망 경계) — 여전히 유효한 근거만 참고 |
