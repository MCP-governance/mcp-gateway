# 외부 레퍼런스 조사 — MCP 규격·게이트웨이 아키텍처·정책 엔진·Python 성능·설치 관행·2026 연구 (2026-10-25)

작성: 2026-10-25 · 용도: [리팩토링·최적화 제안서](README.md)의 근거 · 확인 수준: **공식 페이지 열람**(WebFetch로 원문을 연 것만 기록, 110개 URL). 원본 파일은 저장하지 않았으므로 `sources.json`·SHA-256은 없다. 각 불릿 끝의 URL과 확인일이 출처다. 페이지 본문은 요약기를 거쳐 읽었으므로 **수치를 다른 문서에 옮길 때는 원문을 다시 연다**. 「시사점」으로 표시한 단락은 조사자의 해석이며 사실이 아니다. 이미 10-23까지 위키가 다룬 제품(ContextForge·CPEX·MS Gateway·Wassette·LiteLLM·Kong·BeyondTrust·MCPX·ToolHive v0.54·Falcon Guardian·클라우드 통제 평면·agentgateway/Agent Router/Docker 릴리스 노트)은 그 이후 변화와 아키텍처·성능·설치 관점만 더했다. 기존 카드는 [제품 분석](../../solutions/README.md), [10-23 릴리스·공시](../../solutions/oss-gateway-scanner-releases-1023.md), [10-23 레퍼런스 갱신](../refs-update-1023/README.md).

제안서가 이 조사에서 가져다 쓴 핵심: ① MCP 2026-07-28판은 세션·`initialize` 제거, `Mcp-Method`/`Mcp-Name` 헤더 라우팅, DCR 폐기·CIMD 우선, 기업 관리형 인가(ID-JAG) Stable — 「키트 없는 연결」과 무상태 게이트웨이의 규격 근거. ② OSS 데이터 평면은 Rust(agentgateway)·Go(Agent Router·ToolHive·Docker·Obot)가 다수, 정책은 CEL·Cedar, 모두 `tools/list`를 같은 규칙으로 필터 — 3단계 선택지의 후보와 비교 기준. ③ OPA 엔진 자체 평가는 수십 µs 수준이고 사이드카 HTTP 왕복과의 공식 비교는 없음, Python용 Wasm·Regorus 바인딩은 소규모·비공식 — 인프로세스 정책은 측정 뒤 결정. ④ psycopg_pool 기본값(고정 크기·대기열 무제한·30초)과 FastAPI의 이벤트 루프 차단 경고, Granian 벤치의 「긴 I/O에서 서버 간 차이 수렴」 — 성능 작업의 순서(풀·루프 차단 먼저, 서버 교체는 나중) 근거. ⑤ 한 줄 설치·일회용 등록 토큰·MDM 30분 폴링·Watchtower 보관 — 설치·업그레이드 설계의 비교 사례. ⑥ GatewayBench(평면형 vs 계층형)·ShieldMCP(120ms)·OWASP MCP Top 10 베타 — 평가 축과 인용 조건.

---

---

## 1. MCP 규격 최신 상태

### 판본과 일정
- 현재(Current) 규격은 「2026-07-28」입니다. 판본 식별자는 `YYYY-MM-DD`이며 하위 호환이 깨진 마지막 날짜를 뜻합니다. Draft/Current/Final 3단계가 있습니다. [출처](https://modelcontextprotocol.io/specification/versioning) · 확인 2026-10-25
- 규격 저장소 릴리스 순서: 2026-07-28(7/28, Latest) > 2026-07-28 RC(5/29) > 2025-11-25(11/25) > 2025-11-25-RC(11/15) > 2025-06-18 > 2025-03-26 > 2024-11-05. 페이지에 연도가 없어 릴리스 이름으로 연도를 읽었습니다. [출처](https://github.com/modelcontextprotocol/modelcontextprotocol/releases) · 확인 2026-10-25
- draft 변경 기록은 비어 있습니다("Changes since the most recent release will accumulate here"). 즉 2026-10-25 현재 2026-07-28 이후로 쌓인 초안 변경이 없습니다. [출처](https://modelcontextprotocol.io/specification/draft/changelog) · 확인 2026-10-25
- 공식 블로그 최신 글은 2026-08-22 「The New MCP Roadmap」, 2026-07-28 「The 2026-07-28 Specification」, 2026-07-27 Ruby SDK 1.0 순입니다. [출처](https://blog.modelcontextprotocol.io/) · 확인 2026-10-25
- 로드맵(2026-08-22, 저자 David Soria Parra·Den Delimarsky)의 우선순위 5개: ① 에이전트 메시징 기본형(서버 시작 이벤트, Tasks 확장을 규격 본문으로 이동 검토) ② HTTP 중심 전송 통일·강화(stdio 로컬 서버까지 Streamable HTTP 확장) ③ 에이전트 신원·기업 보안(DPoP, Workload Identity Federation 기반 위임, ID-JAG, 표준 토큰 교환) ④ 개선된 기본형(`tools/call` 결과 계약 단일화, 점진적 도구 노출) ⑤ SDK 개발 경험. 다음 규격 일정은 글에 없고, 게이트웨이·레지스트리는 언급이 없습니다. [출처](https://blog.modelcontextprotocol.io/posts/mcp-roadmap/) · 확인 2026-10-25

### 2026-07-28판이 2025-11-25 대비 바꾼 것 (게이트웨이 영향 큰 순)
- 프로토콜 세션 제거: `Mcp-Session-Id` 헤더가 Streamable HTTP에서 사라지고, `tools/list`·`resources/list`·`prompts/list`는 연결별로 달라지지 않습니다. 상태가 필요한 서버는 서버가 발급한 명시적 핸들을 도구 인자로 주고받습니다(SEP-2567). [출처](https://modelcontextprotocol.io/specification/2026-07-28/changelog) · 확인 2026-10-25
- 무상태화: `initialize`/`notifications/initialized` 핸드셰이크 삭제. 모든 요청의 `_meta`에 `io.modelcontextprotocol/protocolVersion`, `clientCapabilities`(그리고 SHOULD로 `clientInfo`)를 싣고, 서버는 결과 `_meta`에 `serverInfo`를 싣습니다. 버전 불일치는 `UnsupportedProtocolVersionError`(SEP-2575). [출처](https://modelcontextprotocol.io/specification/2026-07-28/changelog) · 확인 2026-10-25
- `server/discover` RPC가 서버 필수 구현이 되었고 지원 버전·기능·신원을 알려 줍니다. 클라이언트는 선택적으로 먼저 호출합니다. [출처](https://modelcontextprotocol.io/specification/2026-07-28/changelog) · 확인 2026-10-25
- HTTP GET 엔드포인트와 `resources/subscribe`가 `subscriptions/listen`(오래 열린 POST 응답 스트림 하나)으로 대체되었습니다. `ping`, `logging/setLevel`, `notifications/roots/list_changed`는 삭제, 로그 수준은 요청별 `_meta`로 전달합니다. SSE 재개(`Last-Event-ID`)·재전송도 삭제되어 끊긴 스트림은 새 요청 ID로 다시 보내야 합니다. [출처](https://modelcontextprotocol.io/specification/2026-07-28/changelog) · 확인 2026-10-25
- 서버가 클라이언트에 먼저 보내던 요청(`sampling/createMessage`, `elicitation/create`, `roots/list`)은 Multi Round-Trip Requests(MRTR)로 바뀝니다. 서버가 `resultType: "input_required"` + `inputRequests`를 돌려주고 클라이언트가 `inputResponses`와 함께 원 요청을 재전송하며, 재전송은 JSON-RPC `id`가 달라야 합니다(SEP-2322). 모든 결과에 `resultType`(`complete`/`input_required`)이 필수입니다. [출처](https://modelcontextprotocol.io/specification/2026-07-28/changelog) · 확인 2026-10-25
- Tasks는 코어에서 빠져 공식 확장 `io.modelcontextprotocol/tasks`가 되었고, 블로킹 `tasks/result` 대신 `tasks/get` 폴링 + `tasks/update`, `tasks/list` 삭제(SEP-2663). [출처](https://modelcontextprotocol.io/specification/2026-07-28/changelog) · 확인 2026-10-25
- 작은 변경: `extensions` 필드 추가, `_meta`에 OpenTelemetry 전파 키(`traceparent`·`tracestate`·`baggage`) 규약 문서화(SEP-414), `tools/list` 결정적 순서 SHOULD, `ttlMs`·`cacheScope`("public"/"private") 필수화(SEP-2549), 리소스 없음 오류 코드 `-32002`→`-32602`, 오류 코드 `-32020`~`-32099`를 규격 예약(`HeaderMismatch -32020`, `MissingRequiredClientCapability -32021`, `UnsupportedProtocolVersion -32022`). [출처](https://modelcontextprotocol.io/specification/2026-07-28/changelog) · 확인 2026-10-25
- 폐기(Deprecated, 최소 12개월 유지): Roots·Sampling·Logging, HTTP+SSE 전송, `includeContext`의 `thisServer`/`allServers`, 그리고 OAuth 동적 클라이언트 등록(DCR, RFC 7591) — Client ID Metadata Documents(CIMD)로 대체(PR #2858). [출처](https://modelcontextprotocol.io/specification/2026-07-28/changelog) · 확인 2026-10-25
- 공식 릴리스 글: Tier 1 SDK(TypeScript·Python·Go·C#)가 출시 시점에 2026-07-28 지원, Rust SDK는 베타. SDK 월 다운로드가 "거의 5억 건"이라고 서술. [출처](https://blog.modelcontextprotocol.io/posts/2026-07-28/) · 확인 2026-10-25

### Streamable HTTP (2026-07-28)
- 서버는 POST만 받는 단일 MCP 엔드포인트를 노출합니다. 구버전 클라이언트의 GET/DELETE는 405, `Mcp-Session-Id`·`Last-Event-ID`는 무시하고 세션 ID를 만들거나 되돌려 주지 않습니다. 응답은 단일 JSON 또는 요청 범위 SSE 스트림이고, 스트림을 닫는 것이 취소 신호입니다. [출처](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http) · 확인 2026-10-25
- 중간자(게이트웨이)가 본문 파싱 없이 라우팅하도록 헤더가 필수화되었습니다: `MCP-Protocol-Version`(본문 `_meta`와 일치해야 하며 불일치는 400 + `HeaderMismatch`), `Mcp-Method`(모든 요청), `Mcp-Name`(`tools/call`·`resources/read`·`prompts/get`). ASCII로 안전하지 않은 값은 `=?base64?...?=` 형식입니다. [출처](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http) · 확인 2026-10-25
- 서버가 도구 인자를 `Mcp-Param-{Name}` 헤더로 노출하려면 `inputSchema` 속성에 `x-mcp-header`를 붙입니다(문자열·정수·불리언만, `properties` 체인으로만 도달 가능). 비밀값에 쓰지 말라는 경고가 있고, 클라이언트는 위반 정의를 `tools/list`에서 제외해야 합니다. [출처](https://modelcontextprotocol.io/specification/2026-07-28/server/tools) · 확인 2026-10-25
- 정책을 헤더 기준으로 강제하는 중간자는 `MCP-Protocol-Version`이 헤더-본문 검증을 요구하는 버전인지 확인하고, 구버전이거나 헤더가 없으면 신뢰하지 말고 거부하라고 규정합니다(SHOULD). `Origin` 검증(불일치 403)은 MUST, SSE 시작 시 `X-Accel-Buffering: no` SHOULD. [출처](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http) · 확인 2026-10-25

### 인가
- OAuth 2.1 초안(draft-ietf-oauth-v2-1-13) 기반. MCP 서버는 RFC 9728(Protected Resource Metadata)을 MUST 구현하고 클라이언트는 이를 인가 서버 탐색에 MUST 사용합니다. 인가 서버 메타데이터는 RFC 8414 또는 OIDC Discovery 중 하나 이상, 클라이언트는 둘 다 지원해야 합니다. [출처](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization) · 확인 2026-10-25
- 클라이언트 등록 우선순위: CIMD(HTTPS URL을 `client_id`로 사용)를 SHOULD, 사전 등록, DCR는 MAY이며 폐기 예정으로 표기. [출처](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization) · 확인 2026-10-25
- `resource` 파라미터(RFC 8707)는 인가·토큰 요청 모두에 MUST. 서버는 토큰이 자신을 대상(audience)으로 발급되었는지 MUST 검증하고 "다른 토큰을 받거나 전달(transit)하지 말 것"(MUST NOT)이라 명시합니다 — 토큰 패스스루 금지. [출처](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization) · 확인 2026-10-25
- RFC 9207 `iss` 검증: 인가 서버 SHOULD 포함, 클라이언트는 존재하면 기록된 issuer와 MUST 비교(차기 판에서 서버 쪽 MUST로 올릴 예정). 클라이언트 자격은 발급한 인가 서버에 묶이며 다른 서버에 재사용 불가(SEP-2352), DCR 시 `application_type` 필수(SEP-837). [출처](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization) · 확인 2026-10-25
- 권한 부족은 403 + `WWW-Authenticate: Bearer error="insufficient_scope", scope="...", resource_metadata="..."`, 클라이언트는 이전 scope와의 합집합으로 step-up 재인가하고 재시도 횟수를 제한합니다. 서버는 한 번의 챌린지에 필요한 scope를 모두 담아야 합니다(SHOULD). [출처](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization) · 확인 2026-10-25
- 인가 확장 저장소에는 「Enterprise-Managed Authorization」과 「OAuth Client Credentials」 두 개가 Stable(2026-07-28)로 올라 있습니다. [출처](https://github.com/modelcontextprotocol/ext-auth) · 확인 2026-10-25
- Enterprise-Managed Authorization(확장 ID `io.modelcontextprotocol/enterprise-managed-authorization`): 기업 IdP가 정책을 평가해 ID-JAG(Identity Assertion JWT Authorization Grant)를 발급하고, 클라이언트가 이를 MCP 인가 서버에서 액세스 토큰으로 교환합니다. MCP 인가 서버는 IdP JWKS로 서명, audience·issuer·만료를 검증하고, `sub`를 안정 식별자로, `email`을 기존 계정 매칭의 보조로 쓰라고 안내합니다. 원안은 SEP-990. [출처](https://modelcontextprotocol.io/extensions/auth/enterprise-managed-authorization) · 확인 2026-10-25

### 도구·elicitation·Tasks
- 도구 `annotations`는 "신뢰된 서버에서 온 것이 아니면 클라이언트는 신뢰하지 않는 것으로 취급해야 한다(MUST)". 여러 서버를 모으는 프록시는 이름 충돌에 대비해 서버 식별자 접두 등 구분 전략을 쓰라(SHOULD)고 되어 있고, 서버 `name`은 유일성이 보장되지 않아 의존 금지. `tools/list`는 인가 정보에 따라 달라질 수 있으나 연결·다른 요청의 부수효과로 달라지면 안 됩니다. [출처](https://modelcontextprotocol.io/specification/2026-07-28/server/tools) · 확인 2026-10-25
- 도구 보안: 서버는 입력 검증·접근 통제·호출 속도 제한·출력 정제를 MUST, 클라이언트는 민감 작업 확인·입력 표시·결과 검증·타임아웃·감사 로그를 SHOULD. 사람 개입(human in the loop) 거부 가능성을 SHOULD. [출처](https://modelcontextprotocol.io/specification/2026-07-28/server/tools) · 확인 2026-10-25
- Elicitation: 별도 요청 대신 MRTR의 `inputRequests` 안에 `elicitation/create`가 실려 오며, `notifications/elicitation/complete`와 URL 모드의 `elicitationId`는 삭제되었습니다(결과는 원 요청 재시도로 확인, 상관관계는 `requestState`). [출처](https://modelcontextprotocol.io/specification/2026-07-28/changelog) · 확인 2026-10-25
- Tasks 확장: 서버가 요청별로 `CreateTaskResult`(`resultType: "task"`, `taskId`, `ttlMs`, `pollIntervalMs`)를 돌려주고, 상태는 `working`·`input_required`·`completed`·`failed`·`cancelled`. 클라이언트가 확장 능력을 선언하지 않았으면 서버는 태스크를 돌려주면 안 됩니다. `tasks/get`·`tasks/update`·`tasks/cancel`(협조적 취소). [출처](https://modelcontextprotocol.io/extensions/tasks/overview) · 확인 2026-10-25

### 레지스트리
- 공식 MCP Registry는 문서상 여전히 "preview"(중대한 변경·데이터 초기화 가능, GA 시기 미정). 이름 공간은 역DNS(`io.github.user/server`)이며 GitHub 계정 또는 도메인(DNS·HTTP 챌린지) 소유 검증으로 보호합니다. 보안 스캔은 하위 패키지 레지스트리(npm·PyPI·Docker Hub)와 하위 마켓플레이스에 위임, 수동 삭제 정책이 있습니다. [출처](https://modelcontextprotocol.io/registry/about) · 확인 2026-10-25
- 공식 레지스트리는 비공개 서버를 지원하지 않으며(사설 서버는 자체 사설 레지스트리 권장), 사설 레지스트리가 구현할 수 있는 OpenAPI 명세를 제공하고, 공식 코드베이스는 자체 호스팅용으로 설계되지 않았다고 명시합니다. 호스트 앱은 공식 레지스트리를 직접 소비하지 말고 하위 마켓플레이스를 쓰라는 구조입니다. [출처](https://modelcontextprotocol.io/registry/about) · 확인 2026-10-25
- 레지스트리 저장소: 별 7.4k, API v0.1은 2025-10-24 API 동결(freeze), 발행자 신원은 GitHub OAuth·GitHub OIDC·DNS/HTTP 도메인 검증. 해당 화면에서 서명·Sigstore·증명(attestation) 언급은 없었고 라이선스 종류도 화면에 명시되지 않았습니다(LICENSE 파일 링크만). 이미지는 `ghcr.io/modelcontextprotocol/registry:latest`, PostgreSQL은 `MCP_REGISTRY_DATABASE_URL`로 별도 공급. [출처](https://github.com/modelcontextprotocol/registry) · 확인 2026-10-25

### 시사점(조사원 해석 — 사실 아님)
- 2026-07-28판은 "게이트웨이를 쉽게 만드는 방향"입니다. 세션 고정(affinity)이 없어졌고 `Mcp-Method`/`Mcp-Name` 헤더만으로 1차 라우팅·속도 제한·거친 인가가 가능합니다. 단 헤더-본문 일치 검증(HeaderMismatch)과 구버전 클라이언트(헤더 없음)는 게이트웨이가 직접 처리해야 합니다.
- `tools/list`의 인가별 필터링, 이름 충돌 접두, `ttlMs`/`cacheScope` 존중(공유 중간자는 `private` 결과를 캐시하면 안 됨)이 규격에 명시되어 있어 MINT 정책 설계의 근거로 인용할 수 있습니다.
- DCR 폐기·CIMD 우선, ID-JAG 기반 기업 관리형 인가(Stable)는 「관리자 승인 + SSO」 구조의 표준 근거입니다. 공식 MCP Registry는 비공개 서버를 받지 않으므로 사내 서버 승인 목록은 MINT 자체 레지스트리가 맞습니다.

---

## 2. 오픈소스 MCP 게이트웨이의 아키텍처 선택

### agentgateway
- Linux Foundation 프로젝트(README), Apache-2.0, 별 5.6k·포크 985. 언어 칸은 비어 있었으나 공식 문서가 "built in Rust"라고 서술합니다. 두 배포 방식: 평면 YAML 설정의 standalone, 내장 컨트롤러 + Gateway API의 Kubernetes. 내장 UI, OpenTelemetry 메트릭·로그·트레이싱, 가드레일(정규식·OpenAI moderation·AWS Bedrock Guardrails·Google Model Armor·사용자 웹훅). [출처](https://github.com/agentgateway/agentgateway) · 확인 2026-10-25
- 거버넌스: 2025년 Linux Foundation에 기증, 2026년 Agentic AI Foundation(AAIF) 프로젝트로 수락(문서 서술). CNCF 언급은 없음. [출처](https://agentgateway.dev/docs/standalone/latest/) · 확인 2026-10-25
- 정책: CEL 정책 엔진 기반 RBAC. MCP 인가는 `mcpAuthorization.rules`에 CEL 문자열을 둡니다(예: `jwt.sub == "test-user" && mcp.tool.name == "add"`). 규칙 변수는 `mcp.tool.name`·`mcp.tool.target`·`mcp.prompt.name`·`mcp.resource.name`·`mcp.methodName`·`jwt.<claim>`. 허용되지 않은 도구는 `tools/list` 응답에서 제거됩니다. `mcp.tool.arguments`는 인가 시점에 사용할 수 없고 인자 필터는 라우트 수준 `authorization` 정책을 써야 합니다. 규칙 미일치 기본 동작은 화면에 명시되지 않았습니다(미확인). [출처](https://agentgateway.dev/docs/standalone/latest/documentation/configuration/security/mcp-authz/) · 확인 2026-10-25
- 설치: `curl -sL https://agentgateway.dev/install | bash`(버전 고정은 `-s -- --version v1.6.0`), 첫 실행 시 `~/.config/agentgateway/config.yaml`을 자동 생성, UI·채팅 엔드포인트는 4000번 포트. 단일 바이너리 형태이며 Docker 설명은 그 페이지에 없음. [출처](https://agentgateway.dev/docs/standalone/latest/quickstart/llm/) · 확인 2026-10-25
- 최신 판본: v1.6.0(10/2, 안정) 및 v1.7.0-alpha.1(10/21, 사전 릴리스). v1.6.0-rc.1에서 `list/*` 결과를 CEL에 노출·MCP list 커서 지원, v1.6.0-alpha.2에서 OpenID AuthZEN MCP 예시 추가, v1.7.0-alpha.1에서 MCP 가드레일 쿠버네티스 지원·CEL 프로세서. (릴리스 노트 수준은 위키가 이미 다룸 — 변경 방향 참고용) [출처](https://github.com/agentgateway/agentgateway/releases) · 확인 2026-10-25

### Agent Router (구 Envoy AI Gateway)
- `envoyproxy/ai-gateway`는 `theagentrouter/agent-router`로 이전·개칭(v1.2.0 노트: "Envoy AI Gateway is now Agent Router", 같은 코드·메인테이너·라이선스). Go, Apache-2.0, 별 2.3k. Envoy Gateway 위에 구축, 2계층 게이트웨이 패턴. [출처](https://github.com/envoyproxy/ai-gateway) · 확인 2026-10-25
- 릴리스: v1.2.0(10/7), v1.1.0(8/21), v1.0.0(6/23). v1.0.0에서 MCP 게이트웨이(여러 서버를 한 엔드포인트로 집계)와 CEL 기반 도구별 인가(`tools/list`에도 같은 규칙 적용), v1.1.0에서 `MCPRoute.spec.hostnames`·`backendSelector` CEL(initialize 시 평가, 기본 Deny), v1.2.0에서 `prefixMode: Never`·`injectionPolicy: IfNotPresent`·`authorizationServerMetadataUrl`. v1.2.0은 "MCP 세션 암호화 시드 변경으로 업그레이드 시 활성 세션 종료". [출처](https://github.com/envoyproxy/ai-gateway/releases) · 확인 2026-10-25
- MCP 게이트웨이는 "Agent Router 사이드카 안의 경량 프록시 컴포넌트"입니다. Streamable HTTP(2025-06 규격 기준), 여러 백엔드 세션 ID를 하나의 통합 세션으로 인코딩, 여러 서버의 SSE를 한 스트림으로 병합, 도구 이름에 백엔드 접두(`github__issue_read`). 인가는 OAuth(PKCE)·JWT 스코프/클레임, 도구 인가는 순서 있는 규칙(소스 JWT·대상 백엔드/도구·선택적 CEL, 첫 일치 적용, `defaultAction`). 관측은 OpenTelemetry 트레이싱 + Prometheus. CRD는 `MCPRoute`(aigateway.envoyproxy.io/v1beta1), `Backend`. 예시는 원격 HTTPS 서버만이고 stdio 서버 언급은 없음. [출처](https://theagentrouter.ai/docs/capabilities/mcp/) · 확인 2026-10-25

### Docker MCP Gateway
- Go, MIT, 별 1.6k. Docker Desktop 4.59+의 MCP Toolkit에 포함되거나 `make docker-mcp`로 CLI 플러그인 설치, `DOCKER_MCP_IN_CONTAINER=1`로 Desktop 없이 실행. 프로필(서버 묶음, OCI 레지스트리로 push/pull), OCI 카탈로그(`mcp/docker-mcp-catalog` 기본), `docker mcp secret`·`docker mcp oauth`, "내장 로깅·호출 추적". 정책은 프로필별 도구 허용/비활성 목록이 전부이며 인터셉터·OpenTelemetry는 이 화면에 없음(미확인). 각 서버는 격리된 컨테이너에서 실행. [출처](https://github.com/docker/mcp-gateway) · 확인 2026-10-25

### Obot
- MIT, 별 1.1k, 커밋 4,096. 화면에 언어 표기는 없고 Go 파일과 JS UI 폴더가 보입니다. MCP 게이트웨이·LLM 게이트웨이·MCP/스킬 레지스트리·호스팅 서버·기기 에이전트 "Obot Sentry"를 묶은 AI 거버넌스 플랫폼. 설치는 `docker run`(`ghcr.io/obot-platform/obot:latest`, 8080, `/data` 볼륨) 또는 Kubernetes(운영 권장), 외부 PostgreSQL은 선택. 접근 제어는 vMCP 프로파일(사용자·IdP 그룹별 서버·도구), 모델 접근 정책, Okta SCIM, 상관된 감사 로그(MCP·LLM 요청/응답·토큰·추정 비용). 내장 DB 여부는 미확인. [출처](https://github.com/obot-platform/obot) · 확인 2026-10-25

### Stacklok ToolHive
- 최신 판본 v0.56.0(2026-10-22). 직전 v0.55.2(10/19)는 보안 수정(루트리스 Podman에서 이그레스 프록시를 통해 호스트 서비스에 접근 가능했던 문제 차단), v0.55.1에서 `thv` Homebrew cask 게시, v0.56.0은 미사용 DCR 클라이언트 상한(24시간 만료)·업스트림 토큰 없는 세션 401·Redis 업스트림 토큰 행 소유권 검사·vMCP 인증 서버 TLS. 최근 6개 릴리스에는 Cedar·텔레메트리·레지스트리 서버 언급이 없음. [출처](https://github.com/stacklok/toolhive/releases) · 확인 2026-10-25
- Apache-2.0, 별 2.3k, Go(go.mod 확인). 구성요소: CLI(`thv`), Kubernetes 오퍼레이터, 레지스트리 서버(별도 저장소), 게이트웨이(가상 MCP), 런타임. OpenTelemetry 트레이스 + Prometheus 메트릭. [출처](https://github.com/stacklok/toolhive) · 확인 2026-10-25
- 정책은 Cedar: 프록시가 모든 요청을 평가하며 `forbid`가 `permit`을 이기고 일치 규칙이 없으면 거부. 주체는 토큰 `sub`, 액션은 `call_tool`·`get_prompt`·`read_resource`, 리소스는 `Tool::"..."`. JWT 클레임은 `claim_` 접두, 도구 인자는 `arg_` 접두. 도구 힌트(`readOnlyHint`·`destructiveHint`)로 정책을 쓸 수 있으나 속성 부재 시 평가 오류가 거부로 처리되므로 `has` 선검사가 필요. 목록 조회(`tools/list` 등)는 요청 단계 검사를 건너뛰고 결과를 필터링. 성능 수치는 문서에 없음. [출처](https://docs.stacklok.com/toolhive/concepts/cedar-policies) · 확인 2026-10-25
- 출처 검증: 컨테이너 이미지의 Sigstore 서명·GitHub Attestations을 확인하고 정책 모드는 `--image-verification` `disabled`/`warn`(기본)/`enabled`(운영 권장, 실패 시 배포 차단). 게시 2025-06-03, 수정 2026-01-09. [출처](https://stacklok.com/blog/from-unknown-to-verified-solving-the-mcp-server-trust-problem/) · 확인 2026-10-25

### IBM ContextForge (MCP Context Forge)
- Apache-2.0, 별 약 4.7k. 코어는 Python(FastAPI + SQLAlchemy + Pydantic), 운영 DB PostgreSQL(`psycopg`)·개발 SQLite, Redis(캐시·세션·연합), Gunicorn(운영)/Uvicorn(개발), Nginx 캐시 리버스 프록시, HTMX+Alpine.js 관리 UI, 플러그인 프레임워크("40+ plugins"). Rust 워크스페이스 크레이트 `crates/mcp_runtime`(PyO3/maturin) 존재. OTLP로 Phoenix·Jaeger·Zipkin·Tempo·Datadog·New Relic 지원. 설치: PyPI `mcp-contextforge-gateway`(`uvx`/pip, Python 3.11+), Docker/Podman Compose(PostgreSQL·Redis·복제본·Nginx), `charts/mcp-stack` Helm(저장소 URL은 "when available"). OPA/Cedar 언급 없음, 성능 벤치마크 결과는 화면에 없음. [출처](https://github.com/IBM/mcp-context-forge) · 확인 2026-10-25
- v1.1.0(2026-10-20): MCP 현대 협상이 기본 `auto`(바깥쪽 연결은 2026-07-28을 먼저 탐지하고 `initialize`로 폴백), 연합 `completion/complete`, 카탈로그 페이지네이션 기본 100건(`nextCursor`를 무시하는 클라이언트는 첫 쪽만 받음, 다중 쪽 직접 프록시 목록은 Redis 필요), `x-mcp-header` 검증(잘못된 주석은 HTTP 422), 도구 이름 충돌 등록 거부, 아웃바운드 URL 검증 강화(`SSRF_PROTECTION_ENABLED=false`여도 실행). "Rust MCP 설정 표면"과 "Python의 Rust 런타임 프록시 연동"을 제거했고 Rust는 CPEX 패키지(출력 길이 가드)에 남음. `anyio` 패치 제거(`anyio>=4.15.0` 요구). [출처](https://github.com/IBM/mcp-context-forge/releases/tag/v1.1.0) · 확인 2026-10-25
- 직전 릴리스: v1.0.11(2026-09-28) MCP Python SDK 2.x(`mcp>=2.0.0`) 이전·SSO 연결 fail-closed·stdio 래퍼 제거, v1.0.10(9/7) 인증을 켜면 기본 비밀번호를 거부, v1.0.9(9/1) 인바운드 mTLS 클라이언트 인증·Vault 토큰 저장. [출처](https://github.com/IBM/mcp-context-forge/releases) · 확인 2026-10-25

### Lasso Security MCP Gateway
- Python, MIT, 별 395. 플러그인 방식: `basic`(비밀 마스킹), `presidio`(PII 마스킹, `pip install mcp-gateway[presidio]`), `lasso`(상용 API 키 필요), `xetrack`(호출 추적, SQLite/DuckDB). `pip install mcp-gateway`, Docker는 직접 빌드, `--scan` 보안 스캐너. 커밋 40건뿐이고 마지막 활동 일자는 화면에 없음(유지보수 상태 미확인). [출처](https://github.com/lasso-security/mcp-gateway) · 확인 2026-10-25

### Pomerium · Teleport
- Pomerium: 정책 언어 PPL의 `mcp_tool` 기준(정확한 이름·접두·접미·목록)으로 도구별 허용/차단을 하고 ID 기반 정책과 결합. 다운스트림은 OAuth 2.1, 업스트림 OAuth(토큰 획득·캐시·갱신·주입)를 대신 처리해 클라이언트가 업스트림 자격을 보지 못하게 하며 RFC 9728 자동 탐색 지원. 도구 호출별 메서드·도구명·매개변수를 감사 기록. 구현 언어·OTel·배포 방식·라이선스는 이 페이지에 없음(미확인). [출처](https://www.pomerium.com/docs/capabilities/mcp) · 확인 2026-10-25
- Teleport: 애플리케이션 서비스로 MCP 서버를 등록하고 역할(role)로 접근 제어. 스트리머블 HTTP·stdio·SSE 가이드, Teleport CA가 서명한 JWT로 MCP 서버에 사용자 신원·역할을 전달, 동적 등록 지원. [출처](https://goteleport.com/docs/enroll-resources/mcp-access/) · 확인 2026-10-25
- Teleport 도구 RBAC: `spec.allow.mcp.tools`(리터럴·glob·`^...$` 정규식·`*`), `spec.deny.mcp.tools`가 allow를 이김, 서버 범위는 `app_labels`/`app_labels_expression`, SSO 트레이트 템플릿 `{{external.xyz}}`. 감사 이벤트·세션 녹화는 그 페이지에서 미확인. [출처](https://goteleport.com/docs/enroll-resources/mcp-access/rbac/) · 확인 2026-10-25

### Cloudflare
- MCP 서버 포털: 하나의 HTTP 엔드포인트로 여러 MCP 서버를 묶음(포털당 최대 80개). 서버별·포털별 Access 정책, 도구·프롬프트 개별 비활성화 또는 허용목록 반전(`default_disabled`), 별칭·설명 재작성. 주의: 차단된 사용자도 서버 직접 URL로 서버 정책을 우회할 수 있고, 포털 경유 서버에는 독립 MFA·목적 입력·임시 인증이 적용되지 않음. 로그 필드는 시각·상태·서버·기능(도구)·소요시간, Logpush는 Enterprise만. 기기 인증 미지원. [출처](https://developers.cloudflare.com/cloudflare-one/access-controls/ai-controls/mcp-portals/) · 확인 2026-10-25
- Workers 기반 원격 MCP 서버 개요 페이지: 원격은 Streamable HTTP + OAuth, 로컬은 stdio. 상세(Agents SDK, workers-oauth-provider 등)는 그 페이지에 없음(미확인). [출처](https://developers.cloudflare.com/agents/model-context-protocol/) · 확인 2026-10-25

### Azure API Management (Apigee는 미확인)
- APIM의 MCP 기능은 Developer·Basic·Standard·Premium 및 v2 계층(Basic v2·Standard v2·Premium v2)과 자체 호스팅 게이트웨이에서 제공. 두 방식: REST API를 MCP 서버로 노출, 기존 MCP 서버를 프록시. 지원 전송 Streamable HTTP(`/mcp`)와 폐기 예정 SSE. 정책(속도 제한·쿼터, JWT 검증, IP 필터링, 캐싱)은 "MCP 서버로 노출된 모든 API 오퍼레이션(도구)에 일괄 적용"됩니다. 도구만 지원하고 리소스·프롬프트는 미지원, 워크스페이스에서는 미지원. 모니터링은 Azure Monitor·Application Insights, 검색은 Azure API Center. 문서 갱신 2026-10-20(페이지 메타 updated_at). [출처](https://learn.microsoft.com/en-us/azure/api-management/mcp-server-overview) · 확인 2026-10-25
- Apigee MCP 문서(`cloud.google.com/apigee/docs/api-platform/apigee-mcp/overview`)는 두 번 모두 404로 열리지 않아 미확인입니다.

### 시사점(조사원 해석 — 사실 아님)
- 정책 표현이 CEL(agentgateway·Agent Router)과 Cedar(ToolHive)로 갈리고, 둘 다 `tools/list` 결과를 같은 규칙으로 필터링합니다. MINT가 OPA를 유지한다면 「목록 필터링」과 「호출 거부」가 같은 규칙에서 나오도록 보장하는 점이 비교 포인트입니다.
- 데이터 평면은 Rust(agentgateway)·Go(Agent Router/Envoy, Docker, Obot, ToolHive)가 다수이고 Python은 ContextForge·Lasso뿐입니다. ContextForge가 Rust 런타임 연동 설정을 v1.1.0에서 다시 뺐다는 점(사실)은 「Python 단일 구현 + 필요한 부분만 네이티브」 방향의 참고 사례입니다.
- 관측은 거의 전부 OpenTelemetry 지향이고(규격도 `_meta` 트레이스 전파 규약을 추가함), 온보딩 비교 기준은 agentgateway의 `curl | bash` 단일 바이너리 + 첫 실행 자동 설정, Obot의 단일 `docker run`입니다.

---

## 3. 정책 엔진 비교 (게이트웨이 내장 관점)

### OPA (Rego)
- 공식 성능 문서의 샘플 RBAC 정책을 `opa bench`로 측정하면 약 45µs/연산(45,032 ns/op), 중앙값 약 36µs, 99백분위 약 134µs. 단일 프로파일 평가는 약 237µs. 문서는 마이크로서비스 인가 결정의 예산을 "1ms 수준"으로 예시합니다. [출처](https://www.openpolicyagent.org/docs/policy-performance) · 확인 2026-10-25
- 같은 문서: 규칙 인덱싱은 등식·`in`·`glob.match`(`**` 없음)·`startswith`/`endswith`가 대상이고 부정식·변수 캡처·키가 다른 변수에 의존하는 참조는 제외. `opa build -O=1` 권장. 평가는 단일 스레드이고 서버가 코어에 걸쳐 요청을 동시 처리(`GOMAXPROCS`). 메모리: JSON 데이터는 약 20배(8MB→약 160MB), ACL식 규칙 1만 개 약 130MB·10만 개 약 1.1GB, 컨테이너에서는 `GOMEMLIMIT`. 측정 도구 `opa eval --profile`, `opa bench`, `opa test --bench`, benchstat용 `--format gobench`. [출처](https://www.openpolicyagent.org/docs/policy-performance) · 확인 2026-10-25
- 사이드카 HTTP 호출 대 라이브러리(임베딩) 지연을 직접 비교한 공식 수치는 열어 본 페이지에서 찾지 못했습니다(미확인). 위 수치는 엔진 내부 평가 시간만이며 네트워크 왕복은 포함되지 않습니다.
- 최신 판본 v1.21.4(2026-10-23, Go 1.27.3로 재빌드), v1.21.3(10/19) 번들 서명 검증 우회 보안 수정(GHSA-g2pf-6v5v-qcc8), v1.21.2(10/12), v1.21.1(9/29), v1.21.0(9/24). v1.21.0에서 규칙 인덱서가 `startswith`/`endswith`/`strings.any_prefix_match`·`any_suffix_match`와 기본 데이터 조회·지역 변수 기반 참조까지 확장, YAML을 1.2 코어 스키마로 파싱(`yes`/`no`/`on`/`off`는 문자열), 빈 리터럴 타입 변경, 재귀 검사 완화. IR/Wasm 타깃은 재귀 검사 완화 반영이 안 되어 오류를 냅니다. 릴리스 5건 중 Wasm 전용 변경은 없음. [출처](https://github.com/open-policy-agent/opa/releases) · 확인 2026-10-25
- Rego v1(OPA 1.0) 변경: 규칙 머리에 `if`·`contains` 필수(단일값이 기본), 본문 없는 단독 참조(`p`, `p.a`) 컴파일 오류, `every`·`in`·`if`·`contains` 내장화(`future.keywords` 임포트는 no-op), 서로 가리는 중복 import 금지, `input`·`data` 이름 예약, 제거된 내장 함수(`any`, `all`, `re_match`, `net.cidr_overlap`, `set_diff`, `cast_*`), 번들 `rego_version` 속성(v0.64.0부터), `opa build --v1-compatible`/`--v0-compatible`, `opa run --server` 기본 바인딩이 모든 인터페이스에서 localhost로 변경, Go 임포트가 `/v1/` 경로로 이동(v0 패키지는 1.0 수명 동안 유지·폐기 표시). [출처](https://openpolicyagent.org/docs/v0-upgrade) · 확인 2026-10-25

### OPA Wasm (opa-wasm)
- `opa build -t wasm -e <entrypoint>`로 번들에 담긴 Wasm 모듈 생성. 핵심 언어는 완전 지원이나 `http.send` 같은 일부 내장 함수는 지원되지 않고 호스트가 구현해야 합니다. 문서가 권장하는 SDK는 JavaScript(npm-opa-wasm)이며 "다른 언어 커뮤니티 SDK 8개"는 이름이 나오지 않아 Go·Python·Rust 지원은 이 문서로 확인되지 않습니다. 성능 주장은 없고 ABI 1.0~1.3 변천(1.3: 평가 사이 데이터 갱신 가능)을 기술합니다. [출처](https://www.openpolicyagent.org/docs/wasm) · 확인 2026-10-25
- npm-opa-wasm: Apache-2.0, README가 "Work in Progress"로 표기, 커밋 318건, 지원 ABI 미명시. Go·Python·Rust SDK 언급 없음. [출처](https://github.com/open-policy-agent/npm-opa-wasm) · 확인 2026-10-25
- Python용 `opa-wasm`(a2d24/python-opa-wasm): MIT, 별 13, 커밋 6건, wasmer-python 기반(`opa-wasm[cranelift]`/`[llvm]` 선택), 릴리스·최근 커밋 일자·Python 지원 버전은 화면에 없음(미확인). 사용: `OPAPolicy('./policy.wasm')` → `set_data` → `evaluate(input)`. [출처](https://github.com/a2d24/python-opa-wasm) · 확인 2026-10-25

### Regorus (Rust, Microsoft)
- 별 361·포크 78·커밋 559. 라이선스 종류는 화면에 명시가 없고 LICENSE 파일 링크만 있어 미확인입니다. 바인딩: C, C++, C#, Go(CGo), Python(pyo3, maturin 빌드), Java(jni-rs), JavaScript/WASM(wasm-pack), Ruby(magnus). README는 "운영 부담을 피하려고 바인딩을 패키지 저장소에 게시하지 않는다"고 하므로 Python은 직접 빌드가 필요합니다(`pip install regorus` 경로는 확인 못 함 — `pypi.org/project/regorus/`는 404였음). [출처](https://github.com/microsoft/regorus) · 확인 2026-10-25
- Rego v1을 기본으로 하며 "OPA v1.2.0과 대체로 호환", 내장 함수 부재(JWT·net CIDR·graphql 위주)로 23개 테스트 스위트 실패. 공식 최신은 OPA v1.21.4이므로 적합성 기준 판본이 상당히 뒤처져 있음. 성능: ACI 정책 테스트가 건당 약 3.6~5ms이며 hyperfine 평균 Regorus 4.6ms 대 OPA 45.2ms(약 10배)라고 서술 — hyperfine은 CLI 실행 시간 측정 도구이므로 프로세스 기동 시간을 포함할 수 있어 임베딩 호출 지연과 같은 값이 아닙니다(해석). `no_std` 지원, 스트립한 예제 바이너리 6.3MB(기본 기능 끄면 1.9MB). Azure/Kata 사용 사례는 화면에 없음. [출처](https://github.com/microsoft/regorus) · 확인 2026-10-25

### Cedar (cedar-policy)
- Apache-2.0, Rust, 별 1.8k. 저장소 설명에 공식 언어 바인딩은 WebAssembly(`cedar-wasm`, JS/TS)만 보이고 Python·Java 언급은 없습니다. `cedar-policy-cli`의 `authorize` 명령, `cedar-policy-symcc`(정책 속성 검증, 반례 제시), 검증기(스키마 대조). "bounded latency" 주장이 있으나 벤치마크 수치는 README에 없음. [출처](https://github.com/cedar-policy/cedar) · 확인 2026-10-25
- Python 바인딩: `cedarpy` 4.12.2(2026-10-14), Cedar 엔진 4.12.0 대응, Python 3.10 이상, 휠 CPython 3.10~3.15·PyPy 3.11, 유지관리자 k9security-devops 1인. "AWS 또는 Cedar 정책 팀의 공식 지원이 아니다"라고 명시. 기능: 인가 요청 검사·스키마 대조 정책 검증·포맷. 라이선스 표기는 해당 페이지에 없음. [출처](https://pypi.org/project/cedarpy/) · 확인 2026-10-25
- 논문 arXiv 2403.04651(2024-03-07 제출; Cutler, Disselkoen, …, Torlak 등): 서론 기준 Cedar 인가기가 OpenFGA 대비 28.7×~35.2×, Rego 대비 42.8×~80.8× 빠르다고 서술, 정책 슬라이싱(템플릿 기반 인코딩)으로 평균 10.0×~18.0× 추가 가속. 벤치마크는 예제 앱 3개와 무작위 입력이며 실험 설정·절대 지연 값(5.2절)은 읽지 못했습니다. 저자 자신의 구현 비교이므로 중립 벤치마크는 아닙니다. [출처](https://arxiv.org/html/2403.04651v2) · 확인 2026-10-25
- 같은 논문 초록 페이지: 읽기 쉽고(readable)·빠르고(fast)·안전하고(safe)·분석 가능한(analyzable) 인가 언어, RBAC·ABAC·관계 기반을 아우르는 문법, Lean으로 설계 성질을 증명, Rust 오픈소스 구현. [출처](https://arxiv.org/abs/2403.04651) · 확인 2026-10-25
- Cedar 문서: 요청은 principal·action·resource·context, 정책 효과 permit/forbid + `when`/`unless`, 스키마 검증(타입 불일치 조기 탐지), 엔터티 부모 관계와 `in`, 정책 템플릿. 성능·임베딩 서술은 이 페이지에 없음. [출처](https://docs.cedarpolicy.com/overview/terminology.html) · 확인 2026-10-25

### CEL
- cel-python(cloud-custodian): Apache-2.0, 별 173, 순수 Python, `pip install cel-python`(0.4.0부터 Google RE2 모듈 포함). README는 "minimal dependencies, runs quickly"라고만 하고 벤치마크 수치는 없음(`benches` 디렉터리는 존재). 타입 사전 검사·자동 형 변환 없음, 정수 나눗셈 의미가 CEL(0 방향)과 Python(`//`, 음의 무한대 방향)이 다름. 최신 판본·릴리스 일자는 화면에 없음. [출처](https://github.com/cloud-custodian/cel-python) · 확인 2026-10-25
- cel-go: Apache-2.0. `google/cel-go`는 읽기 전용 호환 미러이고 정식 저장소는 `github.com/cel-expr/cel-go`(`cel.dev/cel-go`)로 이전되었다고 README가 밝힙니다. 파싱→검사→평가 단계, 매크로(`all`·`exists`·`filter`·`map`·`has`), 부분 평가(잔여 식). 성능 수치는 없음. [출처](https://github.com/google/cel-go) · 확인 2026-10-25
- cel.dev: "성능이 중요한 경로에서 나노초~마이크로초 단위 평가", 비튜링 완전, 호스트가 준 데이터만 접근, 자주 평가되고 드물게 바뀌는 식에 적합. 구현 언어 목록과 채택 사례는 그 페이지에 없음. [출처](https://cel.dev/) · 확인 2026-10-25
- 실제 채택: agentgateway는 CEL을 MCP 인가에 사용(2절), Agent Router도 도구 인가에 CEL(2절). Cedar는 ToolHive가 사용(2절).

### 정책 테스트·검증 도구 요약
- OPA: `opa test`(+`--bench`), `opa eval --profile`, `opa bench` — 열어 본 공식 성능 문서에서 확인. [출처](https://www.openpolicyagent.org/docs/policy-performance) · 확인 2026-10-25
- Cedar: CLI `authorize`, 스키마 검증기, `cedar-policy-symcc` 기호 검증 — 저장소 README에서 확인. 단위 테스트 전용 명령은 README에 언급 없음(미확인). [출처](https://github.com/cedar-policy/cedar) · 확인 2026-10-25
- CEL/Regorus: 열어 본 페이지에서 정책 테스트 도구는 확인되지 않음(미확인).

### 시사점(조사원 해석 — 사실 아님)
- Python 서비스가 Rego를 쓰는 길은 ① OPA 사이드카 HTTP ② Wasm(Python 공식 SDK 없음, 커뮤니티 wasmer 바인딩은 소규모 저장소) ③ Regorus(Python은 직접 빌드, OPA 적합성 판본이 뒤처짐) 중 하나인데, ②③은 모두 지원 부담이 있어 사이드카 유지 + 호출 지연·연결 재사용을 측정하는 쪽이 근거가 가장 탄탄합니다.
- Cedar는 `cedarpy` 4.12.2가 최신이지만 비공식입니다. CEL(cel-python)은 순수 Python이라 설치 부담은 작지만 벤치마크 근거가 없어 도입 시 직접 측정이 필요합니다.
- OPA 1.x 기준 정책 작성(`if`/`contains`, `rego.v1`)과 최신 보안 수정(v1.21.3 번들 서명 검증)을 제안서의 「업그레이드 대상」으로 적을 만합니다.

---

## 4. Python 비동기 게이트웨이 성능 관행

### 이벤트 루프·스레드 풀·연결 풀
- FastAPI: `await` 가능한 라이브러리면 `async def`, 블로킹 라이브러리(대부분의 DB 드라이버)면 일반 `def`(외부 스레드풀에서 실행·await). `async def` 안의 블로킹 I/O는 이벤트 루프를 멈춰 모든 요청이 영향을 받습니다. 의존성도 동일. 확신이 없으면 `def`. [출처](https://fastapi.tiangolo.com/async/) · 확인 2026-10-25
- AnyIO 기본 스레드 리미터 용량은 40 토큰("has a value of 40"), `to_thread.current_default_thread_limiter().total_tokens = 60`처럼 조정. asyncio 기본 스레드 풀 실행기에는 영향이 없음. [출처](https://anyio.readthedocs.io/en/stable/threads.html) · 확인 2026-10-25
- httpx 연결 풀 기본값: `max_connections=100`, `max_keepalive_connections=20`, `keepalive_expiry=5`초. 해당 페이지에는 타임아웃 기본값이나 클라이언트 재사용 권고가 없음(미확인). [출처](https://www.python-httpx.org/advanced/resource-limits/) · 확인 2026-10-25
- psycopg_pool 생성자 기본값(`ConnectionPool`·`AsyncConnectionPool` 공통): `min_size=4`, `max_size=None`(None이면 풀이 늘거나 줄지 않음), `timeout=30.0`초, `max_waiting=0`(대기열 무제한), `max_lifetime=3600.0`, `max_idle=600.0`, `reconnect_timeout=300.0`, `num_workers=3`. `get_stats()`·`pop_stats()` 제공. [출처](https://www.psycopg.org/psycopg3/docs/api/pool.html) · 확인 2026-10-25
- psycopg_pool 사용 지침: 비동기 풀은 생성자에서 여는 것이 deprecated이므로 `await pool.open()` 또는 `async with`, 시작 점검에 `pool.wait()`(미충족 시 `PoolTimeout`), 연결 건강 검사는 `check` 콜백(`ConnectionPool.check_connection` 제공), 풀 크기는 "생각보다 작은 것이 맞을 가능성이 높다"며 `get_stats()`로 조정하고 `resize()`로 런타임 변경. 이 페이지에 교착(deadlock) 경고는 없음(미확인). [출처](https://www.psycopg.org/psycopg3/docs/advanced/pool.html) · 확인 2026-10-25

### 서버 비교 수치
- Granian 프로젝트 자체 벤치마크(2026-08-05, AMD Ryzen 7 5700X 16 CPU, Gentoo Linux 6.18.41, Python 3.13, Granian 2.8.1, 부하 도구 `oha`, 모든 비동기 서버 uvloop): ASGI GET 10KB 동시성 128 — Granian 125,539 RPS(평균 1.016ms), Uvicorn(httptools) 51,051(2.499ms), Gunicorn 34,532(3.693ms), Uvicorn(h11) 14,501(8.791ms), Hypercorn 9,318(13.718ms). [출처](https://github.com/emmett-framework/granian/blob/master/benchmarks/vs.md) · 확인 2026-10-25
- 같은 파일의 긴 I/O 시험(ASGI, 동시성 512): 10ms 지연에서 Granian 45,859·Uvicorn(httptools) 43,903·Gunicorn ASGI 38,275·Hypercorn 8,854 RPS, 100ms 지연에서는 모두 약 5,000 RPS로 수렴(Granian 5,067, Uvicorn 5,053, Hypercorn 4,977, Gunicorn 4,898). 한계: 단일 장비·단일 실행, 다른 서버들의 설정은 미기재, 분산·반복 측정 없음, Granian 프로젝트가 직접 측정. [출처](https://github.com/emmett-framework/granian/blob/master/benchmarks/vs.md) · 확인 2026-10-25
- Granian 단독 시험: RSGI 10B 평문 응답 동시성 64에서 146,427 RPS(평균 0.435ms), ASGI GET 1KB 동시성 128에서 140,814 RPS, ASGI echo 1KB 102,467 RPS. 최대 지연은 수십 ms. [출처](https://github.com/emmett-framework/granian/blob/master/benchmarks/README.md) · 확인 2026-10-25
- uvicorn 기본값: `--loop auto`, `--http auto`, `--workers 1`(또는 `$WEB_CONCURRENCY`), `--backlog 2048`, `--timeout-keep-alive 5`초. `--limit-concurrency` 등은 기본값 표기 없음. [출처](https://uvicorn.dev/settings/) · 확인 2026-10-25
- uvicorn 배포 지침: `--workers`는 `--reload`와 동시에 쓸 수 없음, 내장 프로세스 관리자는 죽은 자식을 재시작하고 `SIGHUP`(우아한 재시작)·`SIGTTIN`(워커 +1)·`SIGTTOU`(워커 -1), Gunicorn 사용은 `uvicorn.workers`가 deprecated되어 `uvicorn-worker` 패키지로 이동, `--limit-concurrency`는 Gunicorn 하에서 미지원. [출처](https://uvicorn.dev/deployment/) · 확인 2026-10-25

### Python 판본·free-threading
- 최신 안정 Python 3.15.1(2026-10-21 릴리스 목록), 3.15 최초 릴리스일 2026-10-09(지원 종료 2031-10), 3.16은 사전 릴리스(최초 릴리스 예정 2027-10-06). [출처](https://www.python.org/downloads/) · 확인 2026-10-25
- PEP 779(상태 Final, Python 3.14): free-threaded 빌드를 「공식 지원이나 선택 사항」(Phase II)으로 올리는 기준 — pyperformance 기준 GIL 빌드 대비 속도 저하 상한 15%(당시 측정 대부분 플랫폼 약 10%, macOS 약 3%), 메모리 증가 목표 20%(당시 약 15~20%). Phase III(기본값화)는 기준을 정하지 않고 미래 PEP로 미룸. [출처](https://peps.python.org/pep-0779/) · 확인 2026-10-25
- 파이썬 공식 free-threading 안내: 3.13부터 macOS·Windows 공식 설치본이 선택적으로 free-threaded 바이너리를 포함, 단일 스레드 오버헤드 평균 약 1%(macOS aarch64)~8%(x86-64 Linux), free-threading 안전 표시가 없는 C 확장을 import하면 GIL이 자동으로 다시 켜지고 경고, `sysconfig.get_config_var("Py_GIL_DISABLED")`·`sys._is_gil_enabled()`로 확인. 메모리: 비-GC 객체 헤더 증가(`None` 32B 대 16B), interned 문자열 불멸화, mimalloc 사용. 확장 호환 추적 페이지로 py-free-threading.github.io/tracking, hugovk.github.io/free-threaded-wheels를 안내. [출처](https://docs.python.org/3/howto/free-threading-python.html) · 확인 2026-10-25
- FastAPI·uvicorn·psycopg·spaCy(Presidio) 각각의 free-threading 준비 상태는 열어 본 페이지에서 확인하지 못했습니다(미확인).

### PostgreSQL 원장(append-only) 파티셔닝·BRIN (18.6 문서)
- BRIN: 물리적 위치와 상관관계가 높은 대형 테이블(예: 추가 전용 테이블의 날짜 열)에 적합. 범위당 요약 1개만 저장해 B-tree보다 매우 작고, 손실형(lossy) 비트맵 스캔 후 튜플 재검사. `pages_per_range` 기본 128(CREATE INDEX 참조), 100만 페이지 테이블은 약 7,813개 항목. 새로 채워진 범위는 요약되기 전까지 비요약 상태이며 `autosummarize`는 기본 꺼짐(켜면 autovacuum이 요약), 수동은 `brin_summarize_new_values(regclass)`; 요약 요청 큐가 가득 차면 로그를 남기고 요청이 버려짐. 연산자 클래스 `minmax`(기본)·`minmax-multi`(`values_per_range` 기본 32, 8~256)·`inclusion`·`bloom`(`false_positive_rate` 기본 0.01). 행이 순서 밖으로 삽입·갱신되면 상관관계가 깨져 효율이 떨어집니다. [출처](https://www.postgresql.org/docs/current/brin.html) · 확인 2026-10-25
- 선언적 파티셔닝: 시계열은 RANGE 키(하한 포함·상한 제외), 대응 파티션이 없는 INSERT는 오류이므로 파티션을 미리 만들어야 함. 파티션 가지치기(`enable_partition_pruning` 기본 on)는 계획·실행 시 모두 동작. 오래된 데이터는 `DELETE`가 아니라 `DROP`/`DETACH PARTITION`(`CONCURRENTLY`로 락 수준 완화)으로 제거. 새 파티션은 별도 생성 후 `ATTACH PARTITION`(CHECK 제약을 미리 두면 검증 스캔 생략). 고유·기본키 제약은 모든 파티션 키 열을 포함해야 하고 파티션 키에 표현식·함수 불가. 플래너는 가지치기 후 남는 파티션이 적으면 수천 개 파티션도 무난. 모범 사례: WHERE 절에 자주 쓰는 열로 파티셔닝, 제거 단위로 설계, 파티션 수 신중히 선택, 현실적 워크로드로 시험. [출처](https://www.postgresql.org/docs/current/ddl-partitioning.html) · 확인 2026-10-25

### Presidio 분석기 지연과 경량 대안
- Presidio는 `data-privacy-stack` 조직으로 이전했고 문서 도메인이 `presidio.dataprivacystack.org`로 옮겨졌습니다(옛 `microsoft.github.io/presidio`는 이전 안내만 표시). 저장소 MIT, 별 11.5k. [출처](https://github.com/microsoft/presidio) · 확인 2026-10-25
- 분석기 구조: `AnalyzerEngine` + `RecognizerRegistry` + `NlpEngine` + `ContextAwareEnhancer`. NLP 엔진은 spaCy·Stanza·Hugging Face 트랜스포머를 지원하고 NER 모델을 별도 `EntityRecognizer`로 추가할 수도 있음. `NlpEngine`은 배치 모드(`process_batch`)를 지원해 대량 작업 속도를 높입니다. 공식 분석기 페이지에는 지연·처리량 수치나 구체적 성능 지침이 없음(미확인). [출처](https://presidio.dataprivacystack.org/analyzer/) · 확인 2026-10-25
- 모델 선택: 기본은 `en_core_web_lg`, 트랜스포머 모델(`en_core_web_trf`)은 "일반적으로 기본 `en_core_web_lg`보다 느리다"고 서술. 정확도 비교 수치는 없음. 예제 코드에서 `en_core_web_sm`을 로드하는 부분이 있으나 지연 비교는 없음. [출처](https://presidio.dataprivacystack.org/analyzer/nlp_engines/spacy_stanza/) · 확인 2026-10-25
- FAQ에는 성능·지연·메모리·소형 모델 관련 항목이 없고, 정확도 평가용 `presidio-research` 저장소만 안내합니다. 사이드바에 「GPU Acceleration」·「Presidio with Kubernetes」·「Presidio with Spark」 페이지가 있으나 본문은 열어 보지 못했습니다(미확인). [출처](https://presidio.dataprivacystack.org/faq/) · 확인 2026-10-25
- Lasso MCP 게이트웨이는 PII 마스킹을 Presidio 플러그인(선택 설치)과 별도 경량 `basic` 플러그인(비밀 패턴 마스킹, PII 미지원)으로 나눠 제공합니다. [출처](https://github.com/lasso-security/mcp-gateway) · 확인 2026-10-25

### 실제 Python 게이트웨이의 교훈 (ContextForge v1.1.0)
- `anyio` 패치 제거로 `anyio>=4.15.0` 요구, `ANYIO_CANCEL_DELIVERY_*`·`SSE_TASK_GROUP_CLEANUP_TIMEOUT` 설정 삭제, 다중 쪽 목록은 Redis와 워커 간 공유 `AUTH_ENCRYPTION_SECRET`이 필요, 풀링된 업스트림 MCP 세션이 리다이렉트를 따르지 않도록 변경(업스트림 `/sse` 307 → `/sse/`가 실패). [출처](https://github.com/IBM/mcp-context-forge/releases/tag/v1.1.0) · 확인 2026-10-25

### 시사점(조사원 해석 — 사실 아님)
- 프록시형 Python 게이트웨이의 상한은 서버 선택보다 「이벤트 루프 안의 동기 호출」과 「풀 크기·타임아웃」이 더 크게 좌우한다는 것이 문서 근거입니다. 긴 I/O가 있으면 서버 간 차이가 약 5,000 RPS 근처로 수렴한다는 Granian 자체 수치도 같은 방향입니다(단 제조사 자체 측정).
- psycopg_pool은 기본값이 `max_size=None`(고정 크기)·대기열 무제한·대기 30초이므로, 요청 폭주 시 대기열이 길어지는 구조입니다. `max_waiting`과 `timeout`을 명시하고 `get_stats()`를 관측 지표로 노출하는 제안이 근거가 있습니다.
- 원장 테이블은 시간 순서 삽입이라 BRIN과 월/일 단위 RANGE 파티션이 문서상 정석이며, 고유 키에 파티션 키가 들어가야 한다는 제약이 해시 체인 `prev_hash`/`seq` 설계에 영향을 줍니다.
- Presidio는 공식 문서만으로는 지연 수치 근거를 만들 수 없으므로 MINT 환경에서 직접 측정해야 합니다.

---

## 5. 설치·온보딩 편의성 관행 (온프레미스 보안 제품 기준)

### 한 줄 설치와 서명·검증 관행
- Tailscale 공식 한 줄: `curl -fsSL https://tailscale.com/install.sh | sh`(apt·yum·zypper 등 패키지 관리자 기반 배포판용 자동화 스크립트). 문서는 "파이프로 실행이 싫으면 수동 설치(안정 패키지 저장소 pkgs.tailscale.com)를 쓰라"고 안내하며 서명·체크섬 검증은 그 페이지에서 다루지 않음. 이후 `sudo tailscale up`으로 URL 인증, 머신 페이지에서 장치 확인(4단계). [출처](https://tailscale.com/docs/install/linux) · 확인 2026-10-25
- K3s: `curl -sfL https://get.k3s.io | sh -`가 systemd/openrc 서비스로 설치하고 `kubectl`·`crictl`·`ctr`·`k3s-killall.sh`·`k3s-uninstall.sh`와 kubeconfig를 만든다. 에이전트 합류는 `K3S_URL`+`K3S_TOKEN` 환경변수. 체크섬 검증은 그 페이지에 서술 없음(미확인). [출처](https://docs.k3s.io/quick-start) · 확인 2026-10-25
- Coolify: `curl -fsSL https://cdn.coollabs.io/coolify/install.sh | bash`(루트 또는 sudo). 요구 2 CPU·2GB RAM·10GB 디스크, amd64/arm64 Linux 전용. 설치기가 비밀을 `/data/coolify/source/.env`에 만들고(`APP_KEY` 포함, 백업 필수) 첫 접속 `http://<server-ip>:8000`에서 관리자 계정을 즉시 만들라고 경고(먼저 접속한 사람이 관리자가 됨). 설치 전 `ROOT_USERNAME`·`ROOT_USER_EMAIL`·`ROOT_USER_PASSWORD`로 관리자 선생성 가능. [출처](https://coolify.io/docs/get-started/installation) · 확인 2026-10-25
- NetBird 자체 호스팅: 한 줄 명령이 최신 릴리스의 `getting-started.sh`를 내려받아 실행, 리버스 프록시 종류 등을 묻고 배포 파일을 생성. 전제: Linux VM 1 CPU·2GB, TCP 80/443·UDP 3478, 공인 도메인, Docker Compose, `jq`·`curl`. 기본 Traefik이 Let's Encrypt로 TLS 자동 처리, 결합 서버(관리·시그널·릴레이·STUN), 내장 Dex IdP, `/setup`에서 관리자 생성(3단계), 무인 설치용 환경변수는 v0.77.1 이상. 문서 일자 2026-10-14. [출처](https://docs.netbird.io/selfhosted/selfhosted-quickstart) · 확인 2026-10-25
- Portainer CE: `docker volume create portainer_data` 후 `docker run ... portainer/portainer-ce:lts`(포트 8000 Edge 터널, 9443 HTTPS), 기본은 자체 서명 인증서, 새 인스턴스는 설정 토큰(setup token)이 필요(시작 플래그로 생략·사용자 지정). [출처](https://docs.portainer.io/start/install-ce/server/docker/linux) · 확인 2026-10-25
- Gitea 바이너리 설치: 단일 바이너리에 SQLite·MySQL·PostgreSQL 지원과 자산 내장, GPG `.asc` 서명 검증(`gpg --verify`), v1.27부터 Sigstore 서명도 제공(`cosign verify-blob`, `.sigstore.json` 번들). 웹 설치 마법사가 `app.ini`를 쓰고 설치 후 `chmod 640` 권고, `INSTALL_LOCK`·DB·비밀키를 직접 지정하면 마법사 생략. 업그레이드는 백업 → 중지 → `/usr/local/bin/gitea` 교체 → 재시작. [출처](https://docs.gitea.com/installation/install-from-binary) · 확인 2026-10-25
- Headscale: BSD-3-Clause, Go, 별 45.0k. 개발 빌드는 main 브랜치에서 컨테이너·바이너리로 제공(안정 설치 방법은 headscale.net 문서로 위임). 화면에서 DB 기본값·사전 인증 키는 미확인. [출처](https://github.com/juanfont/headscale) · 확인 2026-10-25

### 자동 TLS
- Caddy: IP·로컬/내부 이름(`localhost`, `.local`, `.internal`, `.home.arpa`)은 Smallstep 라이브러리 기반 자체 CA(루트→중간→리프, 데이터 디렉터리 `pki/authorities/local`)로 인증서를 발급하고 첫 사용 시 시스템 신뢰 저장소에 루트를 설치 시도(암호 요구 가능, `caddy trust`/`untrust`). 컨테이너·비특권 서비스에서는 설치가 보장되지 않아 관리자가 신뢰를 직접 처리해야 함. 공인 이름은 기본 Let's Encrypt, 실패 시 ZeroSSL 폴백. DNS 챌린지는 공급자 플러그인과 자격이 필요하고 와일드카드는 DNS 챌린지가 필수. 실패 시 재시도 후 지수 백오프(최대 하루 간격, 30일). `.ts.net` 도메인은 로컬 Tailscale에서 가져옴. [출처](https://caddyserver.com/docs/automatic-https) · 확인 2026-10-25
- Tailscale HTTPS: MagicDNS 활성 후 관리 콘솔에서 HTTPS 켜고 `tailscale cert`가 Let's Encrypt에 요청(`*.ts.net` TXT 레코드로 DNS-01), 개인키·ACME 계정키는 로컬 생성(Tailscale이 보지 못함), 인증서 90일, `tailscale cert`는 직접 갱신(Caddy 연동은 자동 갱신), 인증서가 공개 CT 로그에 기록되므로 장치 이름이 노출됨(민감 이름이면 먼저 변경). [출처](https://tailscale.com/kb/1153/enabling-https) · 확인 2026-10-25
- step-ca: `step ca init`(`--acme`로 ACME 공급자 추가), `step-ca $(step path)/config/ca.json` 실행, 루트 지문(fingerprint)을 기록해 두고 새 클라이언트는 `step ca bootstrap`, `step certificate install`로 시스템 신뢰 저장소에 루트 추가. 24시간 기본 수명·Apache-2.0 라이선스·brew/apt 설치는 이 페이지에 없음(미확인). [출처](https://smallstep.com/docs/step-ca/getting-started/) · 확인 2026-10-25

### 엔드포인트 자동 등록(토큰·승인 관행)
- Tailscale 인증 키: 일회용(one-off, 한 기기 연결 후 자동 폐기)·재사용(reusable, "매우 조심하라"), 임시(ephemeral, 오프라인 시 제거)·사전 승인(pre-approved, 장치 승인 기능 사용 시 자동 승인)·태그 부여. 만료 1~90일(기본·최대 90일), 노드 키는 기본 180일, 태그된 기기는 키 만료 기본 해제, 키 폐기가 이미 등록된 노드를 해제하지는 않음. CLI `tailscale up --auth-key=...`, MDM으로 모바일에 `AuthKey` 정책 배포 가능, OAuth 클라이언트로 키를 프로그램 방식으로 생성 가능. [출처](https://tailscale.com/kb/1085/auth-keys) · 확인 2026-10-25
- NetBird 설정 키(setup key): `netbird up --setup-key <KEY>`로 SSO 없이 등록. 일회용·재사용(횟수 제한), 만료 입력칸 기본 7일(비우면 무기한), 자동 그룹 부여(v0.9.2+), 임시 피어는 10분 이상 오프라인이면 자동 제거, 폐기해도 이미 등록된 기기는 연결 유지. 빠른 「Generate Key」는 24시간 일회용 키. 일회용 권장·재사용 키는 횟수 제한 권장. [출처](https://docs.netbird.io/manage/peers/register-machines-using-setup-keys) · 확인 2026-10-25
- Claude Code 관리형 설정 배포 경로(MINT 키트의 직접 비교 대상): 서버 관리형(claude.ai 관리 콘솔 또는 자체 호스팅 Claude apps gateway, 시작 시 가져오고 매시간 폴링), MDM/OS 정책(macOS 구성 프로파일 도메인 `com.anthropic.claudecode`, Windows `HKLM\SOFTWARE\Policies\ClaudeCode`의 `Settings` 값, 시작 시 읽고 30분마다 변경 확인), 파일 기반(`/Library/Application Support/ClaudeCode/managed-settings.json`, `/etc/claude-code/managed-settings.json`, `C:\Program Files\ClaudeCode\managed-settings.json`, 선택적 `managed-settings.d/` 드롭인, 파일 변경 시 재로드). 우선순위: 원격 > MDM/OS 정책 > 관리형 설정 파일 > HKCU 레지스트리. 레거시 `C:\ProgramData\ClaudeCode\managed-settings.json`은 읽지 않음. Jamf·Iru·Intune·그룹 정책용 시작 템플릿 저장소 제공. 로컬 관리자 권한이 있는 개발자는 관리형 소스를 직접 고칠 수 있어 MDM이 프로파일·파일을 주기적으로 재배포하는 이유가 됩니다. [출처](https://code.claude.com/docs/en/managed-settings.md) · 확인 2026-10-25
- Claude Code 관리형 MCP: `managed-mcp.json`(위와 같은 시스템 경로)을 두면 해당 서버 집합만 로드하는 배타 제어, `managedMcpServers`(HTTPS URL의 원격 서버만, `command`·`args`·`env`·`headersHelper` 금지, `${VAR}` 확장 안 함)로 서버를 추가 제공, `allowedMcpServers`/`deniedMcpServers`는 `serverUrl`(와일드카드)·`serverCommand`(명령 전체 정확 일치)·`serverName`(정확 일치, 보안 통제로 부적합하다고 경고)로 매칭하고 거부 목록이 항상 우선, `allowManagedMcpServersOnly: true`로 허용목록을 관리 소스에 고정. Claude Code는 내장 MCP 레지스트리가 없다고 명시. [출처](https://code.claude.com/docs/en/managed-mcp.md) · 확인 2026-10-25
- Claude apps gateway(자체 호스팅): Bedrock·Claude Platform on AWS·Google Cloud·Microsoft Foundry 뒤에서 SSO 로그인, 그룹별 모델 접근, OTLP 텔레메트리를 제공하는 게이트웨이이고, 게이트웨이 세션은 claude.ai 서버 관리형 설정을 가져오지 않으므로 게이트웨이의 `managed` 블록으로 설정을 전달해야 합니다. 도입 첫 화면만 확인했으며 세부 구성은 미확인. [출처](https://code.claude.com/docs/en/claude-apps-gateway) · 확인 2026-10-25
- Codex CLI 관리형 설정(`requirements.toml`/`managed_config.toml`)의 경로·MDM 도메인은 확인하지 못했습니다(미확인). `learn.chatgpt.com/docs/security`는 코드 취약점 스캔 제품(Codex Security) 설명이었고 관리형 설정 내용이 없었으며 `learn.chatgpt.com/docs/managed-configuration`은 404였습니다. [출처](https://learn.chatgpt.com/docs/security) · 확인 2026-10-25

### Windows·macOS 배포
- Intune Win32 앱: `.intunewin` 형식(Win32 Content Prep Tool로 변환), 앱 크기 상한 30GB, 무인(silent) 설치 필수·대화형 설치 미지원, 배포는 Intune Management Extension이 하며 새 할당을 매시간 점검, PowerShell 설치 스크립트 지원(50KB 제한), 탐지 규칙·종속성·요구 사항·대체(supersedence), Intune 등록 해제 시 설치된 Win32 앱이 자동 제거되지 않음. 문서 메타 갱신 2026-07-01. [출처](https://learn.microsoft.com/en-us/intune/intune-service/apps/apps-win32-app-management) · 확인 2026-10-25
- WinGet: App Installer 구성요소로 제공(Windows 10 1809 이상), 지원 설치 형식 EXE·MSI·MSIX·APPX·ZIP·PORTABLE 등, 명령 `install`·`upgrade`·`hash`(설치 파일 SHA256 계산)·`validate`·`configure`·`download`·`pin`. 이 페이지에는 사설 원본(private source)·기업 정책 제한이 없음(미확인). 문서 일자 2026-07-19. [출처](https://learn.microsoft.com/en-us/windows/package-manager/winget/) · 확인 2026-10-25
- Homebrew cask: macOS 앱은 Gatekeeper 점검 통과, SIP·Gatekeeper 비활성화를 요구하면 안 됨, 개발자가 직접 배포하거나 공개 승인한 배포처의 다운로드만 허용, 지원 종료된 버전 라인은 부적합. 페이지에 서명·공증이라는 단어는 없음. ToolHive는 v0.55.1에서 `thv` Homebrew cask 게시를 시작(2절). [출처](https://docs.brew.sh/Acceptable-Casks) · 확인 2026-10-25

### 업그레이드 자동화
- Watchtower(컨테이너 자동 갱신)는 2025-12-17 소유자가 보관(archived)하여 "더 이상 유지보수되지 않음"이고, README가 상용·운영 환경 사용을 권장하지 않으며 Kubernetes(작은 환경은 MicroK8s·k3s)를 대안으로 제시합니다. 별 24.6k, Apache-2.0. [출처](https://github.com/containrrr/watchtower) · 확인 2026-10-25
- Tailscale 클라이언트: 기기별 선택 사항 `tailscale set --auto-update`(Linux), 관리 콘솔 「Auto-update new devices」, 릴리스 약 1주 뒤 시작(보안 업데이트는 더 빠를 수 있음), 일정 지정 불가, 설치 때 쓴 방식(패키지 관리자 등)으로 갱신, 기업은 MDM 정책으로 강제, Arch 계열·Synology는 미지원. [출처](https://tailscale.com/kb/1067/update) · 확인 2026-10-25
- Gitea: 바이너리 교체 후 재시작(파일명을 `gitea`로 유지해야 Git hook이 깨지지 않음), 백업 선행. (위 Gitea 항목과 동일 출처) [출처](https://docs.gitea.com/installation/install-from-binary) · 확인 2026-10-25

### 첫 실행 마법사 패턴
- Gitea 웹 설치 마법사(→ `app.ini` 생성, 이후 읽기 전용화 권고), Coolify 첫 접속 관리자 생성(선점 위험 경고, 환경변수로 선생성 가능), NetBird `/setup` 3단계(설정 페이지 → 관리자 생성 → 로그인), Portainer 설정 토큰 필요. [출처](https://docs.netbird.io/selfhosted/selfhosted-quickstart) · 확인 2026-10-25

### 시사점(조사원 해석 — 사실 아님)
- 한 줄 설치는 업계 표준(Tailscale·K3s·Coolify·NetBird·agentgateway)이지만 공식 문서가 서명 검증 절차를 같이 보여 주는 곳은 Gitea(GPG, v1.27부터 Sigstore) 정도로, 「한 줄 설치 + 서명된 수동 경로」를 같이 제공하면 보안 제품으로서 차별점이 됩니다.
- 첫 관리자 선점 위험을 Coolify가 공식 경고로 명시하고 환경변수 선생성을 제공하는 점은 MINT 첫 실행 마법사(초기 비밀번호 한 번만, 설치 토큰)의 비교 사례입니다.
- 직원 PC 키트는 「설치 토큰(일회용·만료·자동 그룹)」 방식(Tailscale·NetBird)과 「관리형 설정 파일/MDM 정책」 방식(Claude Code의 3종 경로 + 30분 폴링)의 조합이 가장 잘 알려진 형태입니다. Watchtower가 보관된 점은 컨테이너 자동 갱신을 설계할 때 다른 수단(자체 updater, 고정 태그 + 점검형 갱신)을 고려할 근거입니다.

---

## 6. 2026년 MCP 보안·거버넌스 최신 연구·표준

### OWASP
- OWASP MCP Top 10: 현재 베타(로드맵 3단계 「Beta Release and Pilot Testing」에 "We are here"), 프로젝트 리더 Vandana Verma Sehgal, 라이선스 CC BY-NC-SA 4.0(비영리 조건), 항목 번호는 「2025」로 표기. 10개: MCP01 토큰 관리 부실·비밀 노출, MCP02 스코프 확대에 의한 권한 상승, MCP03 도구 포이즈닝, MCP04 소프트웨어 공급망 공격·의존성 변조, MCP05 명령 주입·실행, MCP06 맥락 페이로드를 통한 프롬프트 인젝션, MCP07 불충분한 인증·인가, MCP08 감사·텔레메트리 부재, MCP09 섀도 MCP 서버, MCP10 컨텍스트 주입·과다 공유. 갱신 일자는 페이지에 없음. [출처](https://owasp.org/www-project-mcp-top-10/) · 확인 2026-10-25
- OWASP Top 10 for Agentic Applications for 2026: 페이지에 2025-12-09 날짜가 보이나 그것이 공식 릴리스 일자인지와 10개 항목(ASI01~ASI10)의 제목은 페이지에서 확인되지 않았습니다(다운로드 문서 안에 있음). MCP/도구 오용 언급 확인 불가. [출처](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/) · 확인 2026-10-25

### 정부·표준 기관
- NIST CAISI 「AI Agent Standards Initiative」: 페이지 생성 2026-02-17, 최근 갱신 2026-08-14. 3개 축 — ① 업계 주도 표준(기술 컨벤닝·격차 분석→자발적 지침) ② 커뮤니티 주도 프로토콜(NSF의 오픈소스 에이전트 프로토콜 생태계 지원) ③ 에이전트 인증·신원 인프라 연구와 보안 평가. AI 에이전트 보안 RFI 마감 3월 9일, NCCoE 초안 개념 문서 「Accelerating the Adoption of Software and AI Agent Identity and Authorization」 의견 마감 4월 2일, 의료·금융·교육 청취 세션 등록 마감 3월 20일. 이 페이지에는 번호가 붙은 발간물 목록과 MCP 언급이 없습니다. [출처](https://www.nist.gov/caisi/ai-agent-standards-initiative) · 확인 2026-10-25
- 미국 CISA·NSA와 호주 ASD ACSC·캐나다 Cyber Centre·뉴질랜드 NCSC·영국 NCSC의 공동 지침 「Careful Adoption of Agentic Artificial Intelligence (AI) Services」 — CISA 보도 2026-05-01. 핵심 권고: 에이전트 위험 관리를 기존 사이버보안 프레임워크와 정렬, 에이전트에게 민감 데이터·핵심 시스템에 대한 "광범위하거나 무제한의 접근"을 주지 않기(자율성 제한), 계층 방어·강한 신원 관리·감독, 위협 모델링·지속 모니터링·정기 평가. 권한 상승·창발 행동·책임 공백을 위험으로 꼽음. 보도 자료에 MCP·도구 프로토콜 언급은 없음. [출처](https://content.govdelivery.com/accounts/USDHSCISA/bulletins/41544ff) · 확인 2026-10-25
- 캐나다 Cyber Centre 페이지: 수정일 2026-05-01, 호주 ASD ACSC가 공개를 주도했다고 서술, 지침 구성은 안전한 에이전트 설계·개발, 안전한 배포, 안전한 운영, 미래 위험 대응. MCP 언급 없음, 위험 범주 상세 목록도 페이지에 없음. [출처](https://cyber.gc.ca/en/news-events/joint-guidance-careful-adoption-agentic-artificial-intelligence-services) · 확인 2026-10-25
- ENISA의 2026년 AI 에이전트 전용 보고서는 열어 본 1차 출처에서 확인하지 못했습니다(미확인). 검색에서 ENISA Threat Landscape 2026(2026-09-22 발간이라는 2차 서술)이 보였으나 원문을 열지 않아 기록하지 않습니다.

### 2026년 arXiv·학회 논문 (MCP 게이트웨이·도구 호출 통제·도구 포이즈닝)
- GatewayBench: Unified Capability and Security Evaluation Platform for MCP Gateways — Yitian Zheng, Zhaorun Chen, Haoyu Li, Bo Li, arXiv 2610.23449, 2026-10-16. 524개 작업·6개 도메인, 251개 실제 MCP 서버의 도구 11,118개 풀, 무관 도구를 주입해 대규모 환경 모사. 7개 게이트웨이를 「평면형(flattened)」agentcore·agentgateway·litellm·lunar, 「계층형(hierarchical)」enkrypt·strata·bifrost로 분류. [출처](https://arxiv.org/abs/2610.23449) · 확인 2026-10-25
- GatewayBench 본문 수치(소형 요약기 경유): 간접 공격 성공률(ASRind) 평균이 평면형 60.5 / 47.2 / 42.5%(세 설정), 계층형 19.6 / 30.9 / 15.6%. 평면형 작업 성공률(TSR) 평균 75.3 / 87.2 / 86.7%, 계층형 47.5 / 85.1 / 71.8%. 도구 1,500개 주입 시 작업 시간 평면형 64.1초 대 계층형 38.7초(주입 없을 때 20.8초 대 30.1초). 평면형은 도구 수가 늘면 턴당 토큰이 8.3k→233.3k로 급증하고 계층형은 9.1k~12.6k. 도구 호출 지연은 평면형 약 0.6초(도구 수와 무관), strata 약 0.2초, bifrost 약 0.1초, enkrypt 2.6→5.4초(부록 A.3). 직접 주입은 GPT-5.4 기준 구조 간 차이 없음(44.7% 대 44.2%), 간접 공격 격차는 주로 도구 주입에서 발생. [출처](https://arxiv.org/html/2610.23449) · 확인 2026-10-25
- From Tool Connection to Execution Control: Benchmarking Security Invariants in MCP-Style Agent Runtimes — Ting Liu(1인), arXiv 2606.29073, 2026-06-27(cs.CR, 16쪽). 8개 보안 불변식(메타데이터 비권위, 승인 근거 기반, 정규화된 리소스, 주체 결속, 범위 한정 호출, 출발지-목적지 데이터 흐름 인가, 거부 경로 감사, 명시적 프로토콜 상태). 모델링한 공격 10건: 순진한 연결 계층 런타임 10/10 허용, 완화 기준선(메타데이터 린팅·세션 검사·호출별 승인) 6/10 허용, 제안한 HCP 0/10. 지연은 로컬 메모리 내 마이크로벤치에서 "서브밀리초"라고만 제시. [출처](https://arxiv.org/abs/2606.29073) · 확인 2026-10-25
- Scalable LLM Agent Tool Access in the Cloud — Mingxin Li 외, arXiv 2607.15593, 2026-07-17(cs.DC). 클라우드 규모 MCP 게이트웨이: 레거시 서비스 통합, 호환되지 않는 MCP 변종 통합, 접근 제어, 하이브리드 검색 기반 도구 추천, 상태 있는 백엔드로의 세션 인지 라우팅. 수치: Top-15 재현율 98%, 도구 3,000개 이상 규모, 도구 선택 시간 8.9× 감소, 토큰 사용 23.8× 감소. P50/P99 지연·처리량은 확인한 초록에 없음. [출처](https://arxiv.org/abs/2607.15593) · 확인 2026-10-25
- SMCP: Secure Model Context Protocol — Xinyi Hou, Shenao Wang, 외, arXiv 2602.01129, 2026-02-01(cs.CR). MCP에 신원 관리·상호 인증·보안 컨텍스트 전파·세밀한 정책 집행·감사 로깅을 얹는 프로토콜 확장 제안. 초록에 평가 수치 없음. [출처](https://arxiv.org/abs/2602.01129) · 확인 2026-10-25
- From Component Manipulation to System Compromise: Understanding and Detecting Malicious MCP Servers — Yiheng Huang 외, arXiv 2604.01905, 2026-04-02(v2 2026-05-19, cs.CR). 악성 MCP 서버 114개 데이터셋, 호스트 2종·LLM 5종, 탐지기 Connor F1 94.6%, 기존 최고 대비 8.9%~59.6% 우위, 실제 환경에서 악성 서버 2개 식별. 구성요소 위치가 공격 성공률을 좌우하고 다중 구성요소 공격이 단일 구성요소보다 강하다는 정성 결과. [출처](https://arxiv.org/abs/2604.01905) · 확인 2026-10-25
- Governed MCP: Kernel-Level Tool Governance for AI Agents via Logit-Based Safety Primitives — Daeyeon Son, arXiv 2604.16870, 2026-04-18(v2 2026-07-06, cs.CR). 6계층 파이프라인(스키마 검증→신뢰 등급→속도 제한→적대적 사전 필터→의미 게이트 ProbeLogits→헌법적 정책 매칭)과 Blake3 해시 체인 감사. 비추론 5개 계층 + 감사 추가가 호출당 11.3µs, ProbeLogits 분류 332~556ms(Llama Guard 3 대비 2.4~3.4배 빠름), 해당 계층 제거 시 F1 0.789→0.357. 구현은 베어메탈 x86-64 커널(Rust 약 28.6만 줄)이라 일반 게이트웨이와 환경이 다릅니다. [출처](https://arxiv.org/abs/2604.16870) · 확인 2026-10-25
- Securing the Tool Layer: A Threat Taxonomy and Runtime Defense Framework for Model Context Protocol Deployments (ShieldMCP) — Saurabh Yergattikar(1인), ACL 2026 Industry Track pp. 865–871(2026년 7월, arXiv 번호 없음). SAFE-MCP의 80여 개 공격 기법을 14개 전술 범주로 분류, 호출·응답을 가로채 구조 분석 + 의미 의도 검증을 결합. 5개 LLM 백엔드 레드팀 시험에서 도구 포이즈닝 성공률 74%→9% 미만, 도구 응답을 통한 간접 프롬프트 인젝션 47%→6% 미만, 도구 호출당 중앙값 120ms 미만의 지연. 표준 벤치마크 이름은 제시되지 않음. [출처](https://aclanthology.org/2026.acl-industry.58/) · 확인 2026-10-25
- 검색 단계에서 이름만 보인 논문(MCPTox, MCPSecBench, 2511.20920 서베이 등)은 원문을 열지 않아 수치를 기록하지 않았습니다(미확인).

### MCP 레지스트리 보안·서명 동향
- 공식 레지스트리: 이름 공간 소유 검증(GitHub OAuth/OIDC, DNS/HTTP), 보안 스캔은 패키지 레지스트리·하위 마켓플레이스에 위임, 비공개 서버 미지원. 열어 본 문서·저장소 화면에서는 서명·Sigstore·증명 필드 언급이 없습니다(1절 레지스트리 항목). [출처](https://modelcontextprotocol.io/registry/about) · 확인 2026-10-25
- 다운스트림 구현 사례: ToolHive는 이미지의 Sigstore 서명과 GitHub Attestations을 검증하고 정책 모드(`disabled`/`warn`/`enabled`)로 배포 차단 여부를 결정(2절). Gitea는 v1.27부터 릴리스 바이너리에 Sigstore 서명을 제공(5절). [출처](https://stacklok.com/blog/from-unknown-to-verified-solving-the-mcp-server-trust-problem/) · 확인 2026-10-25

### 시사점(조사원 해석 — 사실 아님)
- OWASP MCP Top 10의 MCP08(감사·텔레메트리 부재), MCP09(섀도 서버), MCP02(권한 범위 확대)는 MINT의 감사 원장·승인 목록·scope 통제에 바로 대응합니다. 다만 아직 베타이고 CC BY-NC-SA 4.0이라 제안서에 인용할 때 출처 표기와 비영리 조건을 주의해야 합니다.
- GatewayBench는 「평면형 vs 계층형」 구조에 따른 보안·토큰 비용 차이를 실측한 최초의 게이트웨이 벤치마크라 제안서 근거로 가치가 큽니다. 다만 평가한 7개 중 MINT와 같은 방식(정책 엔진 + 승인 기반 게이트웨이)은 없고, 수치는 소형 요약기를 거친 값이라 인용 전 원문 확인이 필요합니다.
- ShieldMCP는 의미 검증을 켜면 호출당 120ms급 지연이 드는 반면 Governed MCP의 비추론 계층은 11.3µs라, 「규칙 기반 계층은 마이크로초, 의미 검사는 수백 ms」라는 지연 구도를 설명하는 근거로 쓸 수 있습니다(서로 다른 환경의 수치).
- NIST·CISA 문서는 MCP를 직접 언급하지 않으므로 「에이전트 자율성 제한·신원 관리·감독」 같은 일반 원칙으로만 인용하는 편이 정확합니다.

---

## 열어 본 URL 전체 목록

종류 칸의 「공식 문서」는 라이선스 표기가 페이지에 없는 문서 사이트입니다. 날짜 칸은 페이지에 표기된 게시·갱신·릴리스 일자이며 없으면 「표기 없음」입니다.

| URL | 제목 | 게시/갱신일 | 라이선스/종류 |
|---|---|---|---|
| https://modelcontextprotocol.io/specification/versioning | Versioning | 표기 없음 | 공식 문서 |
| https://modelcontextprotocol.io/specification/draft/changelog | Changelog (draft) | 표기 없음 | 공식 문서 |
| https://github.com/modelcontextprotocol/modelcontextprotocol/releases | MCP 규격 저장소 릴리스 | 2026-07-28 릴리스 | GitHub 저장소(라이선스 미확인) |
| https://blog.modelcontextprotocol.io/ | MCP 공식 블로그 목록 | 최신 글 2026-08-22 | 공식 블로그 |
| https://modelcontextprotocol.io/specification/2026-07-28/changelog | Key Changes (2026-07-28) | 2026-07-28판 | 공식 문서 |
| https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization | Authorization (2026-07-28) | 2026-07-28판 | 공식 문서 |
| https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http | Streamable HTTP (2026-07-28) | 2026-07-28판 | 공식 문서 |
| https://modelcontextprotocol.io/specification/2026-07-28/server/tools | Tools (2026-07-28) | 2026-07-28판 | 공식 문서 |
| https://blog.modelcontextprotocol.io/posts/mcp-roadmap/ | The New MCP Roadmap | 2026-08-22 | 공식 블로그 |
| https://blog.modelcontextprotocol.io/posts/2026-07-28/ | The 2026-07-28 Specification | 2026-07-28 | 공식 블로그 |
| https://blog.modelcontextprotocol.io/tags/working-groups/ | 블로그 태그 목록 | 표기 없음 | 공식 블로그(보조) |
| https://github.com/modelcontextprotocol/ext-auth | MCP Authorization Extensions | 표기 없음 | GitHub 저장소(라이선스 미확인) |
| https://modelcontextprotocol.io/extensions/auth/enterprise-managed-authorization | Enterprise-Managed Authorization | 표기 없음 | 공식 문서 |
| https://modelcontextprotocol.io/extensions/tasks/overview | Tasks | 표기 없음 | 공식 문서 |
| https://modelcontextprotocol.io/registry/about | The MCP Registry | 표기 없음 | 공식 문서 |
| https://github.com/modelcontextprotocol/registry | MCP Registry 저장소 | API 동결 2025-10-24 | GitHub 저장소(라이선스 종류 화면 미표기) |
| https://github.com/agentgateway/agentgateway | agentgateway | 표기 없음 | Apache-2.0 |
| https://github.com/agentgateway/agentgateway/releases | agentgateway 릴리스 | v1.7.0-alpha.1 10/21 | Apache-2.0 |
| https://agentgateway.dev/docs/standalone/latest/ | agentgateway 문서 홈 | 표기 없음 | 공식 문서 |
| https://agentgateway.dev/docs/standalone/latest/quickstart/ | agentgateway 퀵스타트 목차 | 표기 없음 | 공식 문서(내용 적음) |
| https://agentgateway.dev/docs/standalone/latest/quickstart/llm/ | agentgateway LLM 퀵스타트 | 표기 없음 | 공식 문서 |
| https://agentgateway.dev/docs/standalone/latest/mcp/mcp-authz/ | agentgateway MCP 인가 개요 | 표기 없음 | 공식 문서 |
| https://agentgateway.dev/docs/standalone/latest/documentation/configuration/security/mcp-authz/ | agentgateway MCP 인가 정책 | 표기 없음 | 공식 문서 |
| https://github.com/envoyproxy/ai-gateway | (theagentrouter/agent-router로 이전) Agent Router | 표기 없음 | Apache-2.0 |
| https://github.com/envoyproxy/ai-gateway/releases | Agent Router 릴리스 | v1.2.0 10/7 | Apache-2.0 |
| https://theagentrouter.ai/docs/capabilities/mcp/ | Agent Router MCP | 표기 없음 | 공식 문서 |
| https://github.com/docker/mcp-gateway | Docker MCP Gateway | 표기 없음 | MIT |
| https://github.com/obot-platform/obot | Obot | 표기 없음 | MIT |
| https://github.com/stacklok/toolhive | ToolHive | 표기 없음 | Apache-2.0 |
| https://github.com/stacklok/toolhive/releases | ToolHive 릴리스 | v0.56.0 2026-10-22 | Apache-2.0 |
| https://docs.stacklok.com/toolhive/concepts/cedar-policies | ToolHive Cedar 정책 | 표기 없음 | 공식 문서 |
| https://stacklok.com/blog/from-unknown-to-verified-solving-the-mcp-server-trust-problem/ | From unknown to verified | 2025-06-03(수정 2026-01-09) | 벤더 블로그 |
| https://github.com/IBM/mcp-context-forge | IBM ContextForge | 표기 없음 | Apache-2.0 |
| https://github.com/IBM/mcp-context-forge/releases | ContextForge 릴리스 | v1.1.0 2026-10-20 | Apache-2.0 |
| https://github.com/IBM/mcp-context-forge/releases/tag/v1.1.0 | ContextForge v1.1.0 | 2026-10-20 | Apache-2.0 |
| https://github.com/lasso-security/mcp-gateway | Lasso MCP Gateway | 표기 없음 | MIT |
| https://www.pomerium.com/docs/capabilities/mcp | Pomerium MCP | 표기 없음 | 공식 문서 |
| https://goteleport.com/docs/enroll-resources/mcp-access/ | Teleport MCP 접근 | 표기 없음 | 공식 문서 |
| https://goteleport.com/docs/enroll-resources/mcp-access/rbac/ | Teleport MCP RBAC | 표기 없음 | 공식 문서 |
| https://developers.cloudflare.com/agents/model-context-protocol/ | Cloudflare MCP 개요 | 표기 없음 | 공식 문서 |
| https://developers.cloudflare.com/cloudflare-one/access-controls/ai-controls/mcp-portals/ | Cloudflare MCP 서버 포털 | 표기 없음 | 공식 문서 |
| https://learn.microsoft.com/en-us/azure/api-management/mcp-server-overview | Azure APIM MCP 개요 | 2026-09-11(메타 갱신 2026-10-20) | 공식 문서 |
| https://www.openpolicyagent.org/docs/policy-performance | OPA Policy Performance | 표기 없음 | 공식 문서 |
| https://www.openpolicyagent.org/docs/wasm | OPA WebAssembly | 표기 없음 | 공식 문서 |
| https://openpolicyagent.org/docs/v0-upgrade | Upgrading to v1.0 | 표기 없음 | 공식 문서 |
| https://github.com/open-policy-agent/opa/releases | OPA 릴리스 | v1.21.4 10/23 | 화면 미표기 |
| https://github.com/open-policy-agent/npm-opa-wasm | npm-opa-wasm | 표기 없음 | Apache-2.0 |
| https://github.com/a2d24/python-opa-wasm | python-opa-wasm | 표기 없음 | MIT |
| https://github.com/microsoft/regorus | Regorus | 표기 없음 | 화면 미표기(LICENSE 파일만) |
| https://github.com/cedar-policy/cedar | Cedar | 표기 없음 | Apache-2.0 |
| https://pypi.org/project/cedarpy/ | cedarpy 4.12.2 | 2026-10-14 | 페이지 미표기(비공식 바인딩) |
| https://docs.cedarpolicy.com/overview/terminology.html | Cedar Terminology | 표기 없음 | 공식 문서 |
| https://arxiv.org/abs/2403.04651 | Cedar 논문(초록) | 2024-03-07 | arXiv |
| https://arxiv.org/html/2403.04651v2 | Cedar 논문(본문 HTML, 서론까지 읽음) | 2024-03-08(v2) | arXiv |
| https://github.com/cloud-custodian/cel-python | cel-python | 표기 없음 | Apache-2.0 |
| https://github.com/google/cel-go | cel-go(읽기 전용 미러) | 표기 없음 | Apache-2.0 |
| https://cel.dev/ | Common Expression Language | 표기 없음 | 공식 사이트 |
| https://fastapi.tiangolo.com/async/ | FastAPI Concurrency and async/await | 표기 없음 | 공식 문서 |
| https://anyio.readthedocs.io/en/stable/threads.html | AnyIO Working with threads | 표기 없음 | 공식 문서 |
| https://www.python-httpx.org/advanced/resource-limits/ | httpx Resource Limits | 표기 없음 | 공식 문서 |
| https://www.psycopg.org/psycopg3/docs/advanced/pool.html | psycopg Connection pools | 표기 없음 | 공식 문서 |
| https://www.psycopg.org/psycopg3/docs/api/pool.html | psycopg_pool API | 표기 없음 | 공식 문서 |
| https://github.com/emmett-framework/granian/blob/master/benchmarks/README.md | Granian 벤치마크 | 2026-08-05 실행 | 프로젝트 자체 측정 |
| https://github.com/emmett-framework/granian/blob/master/benchmarks/vs.md | Granian vs 다른 서버 | 2026-08-05 실행 | 프로젝트 자체 측정 |
| https://uvicorn.dev/deployment/ | Uvicorn Deployment | 표기 없음 | 공식 문서 |
| https://uvicorn.dev/settings/ | Uvicorn Settings | 표기 없음 | 공식 문서 |
| https://docs.python.org/3/howto/free-threading-python.html | Python free-threading HOWTO | 표기 없음 | 공식 문서 |
| https://peps.python.org/pep-0779/ | PEP 779 | Final(3.14) | 공식 PEP |
| https://www.python.org/downloads/ | Python Releases | 3.15.1 2026-10-21 | 공식 사이트 |
| https://www.postgresql.org/docs/current/brin.html | PostgreSQL BRIN | 18.6 문서 | 공식 문서 |
| https://www.postgresql.org/docs/current/ddl-partitioning.html | PostgreSQL 파티셔닝 | 18 문서 | 공식 문서 |
| https://github.com/microsoft/presidio | Presidio | 표기 없음 | MIT |
| https://presidio.dataprivacystack.org/analyzer/ | Presidio Analyzer | 표기 없음 | 공식 문서 |
| https://presidio.dataprivacystack.org/analyzer/nlp_engines/spacy_stanza/ | Presidio spaCy/Stanza | 표기 없음 | 공식 문서 |
| https://presidio.dataprivacystack.org/faq/ | Presidio FAQ | 표기 없음 | 공식 문서 |
| https://tailscale.com/docs/install/linux | Tailscale Linux 설치 | 표기 없음 | 공식 문서 |
| https://tailscale.com/kb/1085/auth-keys | Tailscale Auth keys | 표기 없음 | 공식 문서 |
| https://tailscale.com/kb/1153/enabling-https | Tailscale HTTPS | 표기 없음 | 공식 문서 |
| https://tailscale.com/kb/1067/update | Tailscale 클라이언트 업데이트 | 표기 없음 | 공식 문서 |
| https://caddyserver.com/docs/automatic-https | Caddy Automatic HTTPS | 표기 없음 | 공식 문서 |
| https://smallstep.com/docs/step-ca/getting-started/ | step-ca Getting Started | 표기 없음 | 공식 문서 |
| https://docs.netbird.io/selfhosted/selfhosted-quickstart | NetBird 자체 호스팅 퀵스타트 | 2026-10-14 | 공식 문서 |
| https://docs.netbird.io/manage/peers/register-machines-using-setup-keys | NetBird 설정 키 | 표기 없음 | 공식 문서 |
| https://coolify.io/docs/get-started/installation | Coolify 설치 | 표기 없음 | 공식 문서 |
| https://docs.portainer.io/start/install-ce/server/docker/linux | Portainer CE 설치 | 표기 없음 | 공식 문서 |
| https://docs.k3s.io/quick-start | K3s Quick-Start | 표기 없음 | 공식 문서 |
| https://docs.gitea.com/installation/install-from-binary | Gitea 바이너리 설치 | 표기 없음 | 공식 문서 |
| https://github.com/juanfont/headscale | Headscale | 표기 없음 | BSD-3-Clause |
| https://github.com/containrrr/watchtower | Watchtower(보관됨) | 보관 2025-12-17 | Apache-2.0 |
| https://learn.microsoft.com/en-us/intune/intune-service/apps/apps-win32-app-management | Intune Win32 앱 관리 | 메타 2026-07-01 | 공식 문서 |
| https://learn.microsoft.com/en-us/windows/package-manager/winget/ | WinGet | 2026-07-19 | 공식 문서 |
| https://docs.brew.sh/Acceptable-Casks | Homebrew Acceptable Casks | 표기 없음 | 공식 문서 |
| https://code.claude.com/docs/en/settings | Claude Code 설정 파일·우선순위 | 표기 없음 | 공식 문서 |
| https://code.claude.com/docs/en/managed-settings.md | Claude Code 관리형 설정 배포 | 표기 없음 | 공식 문서 |
| https://code.claude.com/docs/en/managed-mcp.md | Claude Code 관리형 MCP | 표기 없음 | 공식 문서 |
| https://code.claude.com/docs/en/claude-apps-gateway | Claude apps gateway | 표기 없음 | 공식 문서(첫 화면만 확인) |
| https://learn.chatgpt.com/docs/security | Codex Security(코드 스캔 제품, 관리형 설정 내용 없음) | 표기 없음 | 공식 문서(관련성 낮음) |
| https://owasp.org/www-project-mcp-top-10/ | OWASP MCP Top 10 | 표기 없음(© 2026) | CC BY-NC-SA 4.0 |
| https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/ | OWASP Top 10 for Agentic Applications 2026 | 2025-12-09 표기 | OWASP 문서(항목 목록 미확인) |
| https://www.nist.gov/caisi/ai-agent-standards-initiative | NIST AI Agent Standards Initiative | 생성 2026-02-17, 갱신 2026-08-14 | 정부 문서 |
| https://content.govdelivery.com/accounts/USDHSCISA/bulletins/41544ff | CISA 보도: Adopting Agentic AI Services | 2026-05-01 | 정부 공지 |
| https://cyber.gc.ca/en/news-events/joint-guidance-careful-adoption-agentic-artificial-intelligence-services | Joint guidance on careful adoption of agentic AI services | 수정 2026-05-01 | 정부 공지 |
| https://arxiv.org/abs/2610.23449 | GatewayBench (초록) | 2026-10-16 | arXiv |
| https://arxiv.org/html/2610.23449 | GatewayBench (본문 HTML) | 2026-10-16 | arXiv |
| https://arxiv.org/abs/2606.29073 | From Tool Connection to Execution Control | 2026-06-27 | arXiv |
| https://arxiv.org/abs/2607.15593 | Scalable LLM Agent Tool Access in the Cloud | 2026-07-17 | arXiv |
| https://arxiv.org/abs/2602.01129 | SMCP: Secure Model Context Protocol | 2026-02-01 | arXiv |
| https://arxiv.org/abs/2604.01905 | From Component Manipulation to System Compromise | 2026-04-02(v2 05-19) | arXiv |
| https://arxiv.org/abs/2604.16870 | Governed MCP | 2026-04-18(v2 07-06) | arXiv |
| https://aclanthology.org/2026.acl-industry.58/ | Securing the Tool Layer (ShieldMCP), ACL 2026 Industry | 2026-07 | ACL Anthology |

## 열지 못한 것(404·접속 실패·내용 없음) — 위 표에는 넣지 않았습니다
- Apigee MCP 개요: `cloud.google.com/apigee/docs/api-platform/apigee-mcp/overview`(301 이후 `docs.cloud.google.com/...`도 404).
- `pypi.org/project/regorus/` 404, `crates.io/crates/regorus`는 내용 없음, `arxiv.org/pdf/2403.04651`은 PDF 압축 스트림이라 텍스트 추출 불가.
- Codex CLI 관리형 설정 문서: `learn.chatgpt.com/docs/managed-configuration` 404.
- `genai.owasp.org/resource/owasp-mcp-top-10/` 404, `preview.aclanthology.org/ingest-acl/...` 404(대체 `aclanthology.org`는 열림).
- Jamf Pro 사용자 개시 등록 문서(`docs.jamf.com`)는 인증서 만료 오류, Dokploy 설치 문서(`dokploy.com/docs/core/installation`) 404, `www.uvicorn.org` DNS 오류(`uvicorn.dev`로 대체), `openpolicyagent.org/docs/v0-to-v1` 404(대체 `v0-upgrade`는 열림).
- 검색 결과 요약으로만 이름을 본 것(원문 미열람이라 사실 기록에서 제외): ENISA Threat Landscape 2026, MCPTox(arXiv 2508.14925), MCPSecBench(2508.13220), 보안 서베이 2511.20920, regopy.
