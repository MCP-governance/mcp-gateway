# 게이트웨이·통제 제품 재조사 (2026-09-29)

`BENCHMARK_LITELLM.md`(LiteLLM 1.89.4, 2026-09-26)에 없는 것만 적는다. 소스가 공개된 제품은 **받아서 코드로** 읽었고
(`파일:줄`), 소스가 없는 제품은 공식 문서로 정리했다(**문서 근거**). 받은 커밋: LiteLLM `118ce3c`(1.104.0), IBM
mcp-context-forge `077071b`(1.0.11), Kong `8927af6`(3.10.0), OpenAI Codex `0d7b811`(2026-09-29 main).

## 1. 한 줄 요약

| 대상 | 무엇을 봤나 | 우리에게 남긴 것 |
| --- | --- | --- |
| LiteLLM 1.104 | `tool_catalog_guard.py`, `client_allowlist.py`, `gateway_dcr_flow.py`, `tool_search.py`, `McpCrudPermissionPanel.tsx` | 도구 설명 검사(D-52), 하네스 허용 목록·도구 검색 간접화는 후보 |
| IBM ContextForge 1.0.11 | 페더레이션, 가상 서버, 플러그인 프레임워크, `unified_pdp` | 회로 차단기는 후보. 페더레이션·가상 서버·다중 PDP·판정 캐시는 가져오지 않음 |
| Kong | OSS 저장소에 MCP 플러그인 **없음**(`git ls-tree … \| grep -i mcp` 0건). `ai-mcp-proxy`·`ai-mcp-oauth2`는 Enterprise 전용(**문서 근거**) | deny 우선 도구 ACL·토큰 미전달은 이미 같은 방향 |
| BeyondTrust | Pathfinder MCP Gateway, PRA JIT 승인, Entitle(**문서 근거**) | 무응답 자동 거부(D-51 검토 기한), 기한 있는 접근(D-49) |
| Claude Code | 관리형 MCP 문서(`managed-mcp`, `managed-settings`) | 계정 커넥터 탐지·거부 키(D-51) |
| Codex CLI | `config/src/config_requirements.rs`, `app-server-protocol` | `requirements.toml` 강제 키·`app/installed`(D-51) |

## 2. 하네스가 스스로 붙이는 커넥터를 통제하는 키 (D-51의 근거)

**Claude Code** (문서 근거: code.claude.com/docs/en/mcp, /managed-mcp, /managed-settings)
- claude.ai 계정으로 로그인하면 claude.ai에 추가한 커넥터가 자동으로 붙는다. `claude mcp list`에 `claude.ai <이름>: <url> - ✔ Connected`로 보인다.
- 모두 끄기: 아무 설정 범위에서 `"disableClaudeAiConnectors": true`, 또는 `ENABLE_CLAUDEAI_MCP_SERVERS=false`.
- 하나만 끄기: `deniedMcpServers`에 `{"serverName": "claude.ai Slack"}`(거부 목록의 이름은 아무 문자열 가능) 또는 `{"serverUrl": "https://mcp.slack.com/*"}`.
  이름은 바뀔 수 있어 URL을 권장한다. 거부 목록은 모든 범위에서 합쳐지고 무엇보다 먼저 적용된다.
- 허용 목록: `allowedMcpServers`의 `serverName`은 영문·숫자·`-`·`_`만 되므로 계정 커넥터는 `serverUrl`로 허용한다. 권위 있게 하려면
  관리형 설정에 `allowManagedMcpServersOnly: true`를 함께 둔다.
- `managed-mcp.json`(배타 제어)은 계정 커넥터도 끈다. 함께 쓰려면 관리형 설정 채널에 `"allowAllClaudeAiMcps": true`(사용자·프로젝트
  설정에 두면 무시됨). 경로: macOS `/Library/Application Support/ClaudeCode/`, Linux·WSL `/etc/claude-code/`,
  Windows `C:\Program Files\ClaudeCode\` — `managed-settings.json`·`managed-settings.d/*.json`·`managed-mcp.json`이 같은 폴더.
- 사용량 관측: OpenTelemetry 내보내기에 `OTEL_LOG_TOOL_DETAILS=1`이면 MCP 서버·도구 이름이 남는다(계정 커넥터 호출은 Gateway를 지나지 않으므로 이것이 유일한 사용 기록).

**Codex CLI** (소스 근거)
- 관리자 강제는 `requirements.toml`: Unix `/etc/codex/requirements.toml`, Windows `%ProgramData%\OpenAI\Codex\requirements.toml`,
  클라우드 번들·레거시 `managed_config.toml`·macOS MDM 계층을 합친다(`config/src/loader/mod.rs`).
- 키(`config/src/config_requirements.rs:1040-1075`): `allowed_web_search_modes`(예: `["disabled"]`), `allow_browser_and_computer_use`,
  `[features]`(이름 → bool), `[apps.<id>] enabled`, `[mcp_servers.<이름>.identity] url|command`.
- 앱 병합 규칙(`merge_app_requirements_descending`): 어느 계층이든 `enabled = false`면 최종 false — 사용자가 되돌릴 수 없다.
- 상태 읽기: `codex mcp list --json`, `codex features list`, `codex app-server`의 `app/installed`(설치된 앱: `id·runtimeName·enabled`)와
  `app/list`(앱 디렉터리 전체 — 실측 수천 개, `isAccessible`가 연결 여부). 웹 검색 기본값은 `cached`(`protocol/src/config_types.rs:376`).

실측(테스트 VM, Claude Code 2.1.283·Codex 0.158.0): 계정 커넥터 5개(Claude Docs·Mermaid·Vercel·Canva·Google Drive), 플러그인 서버 20여 개
(`plugin:engineering:slack` 등, 인증 필요·연결 실패 상태 포함), Codex 설치 앱 9개(Slack·Notion·Sites·Google Drive + OpenAI 자체
`connector_openai_*` 5개), 기본 켜진 기능 `apps`·`plugins`·`browser_use`·`computer_use`·`image_generation`.

## 3. LiteLLM 1.104 — 이전 비교 뒤 새로 생긴 것

- **도구 설명 검사** `litellm/proxy/_experimental/mcp_server/tool_catalog_guard.py`: 도구가 목록에 오르기 전에 이름·설명·스키마를
  가드레일에 통과시키고(`scan_tool_descriptions`, :152-173), 막히거나 예외가 나면 그 도구를 숨긴다(fail-closed, :191). 관리자가
  고정한 카탈로그와 다르면 옛 버전을 계속 내보내며 경보만 낸다(`pin_tool_catalog`, :122-137). → **D-52**(승인 시점 규칙 검사).
- **클라이언트 허용 목록** `client_allowlist.py`: JWT 클레임 또는 클라이언트가 대는 헤더로 하네스를 식별해 허용/거부. 헤더 방식은
  "정책 통제일 뿐 보안 경계가 아니다"라고 주석에 명시(:6-9), 설정이 깨지면 아무도 통과 못 함(:89). → 후보: 우리는 clientInfo를
  기록만 하므로 **경보**(`P-HARNESS-001`)로 시작할 수 있다.
- **게이트웨이 자체 OAuth** `gateway_dcr_flow.py`: 상태 없는 DCR(`client_id`에 리다이렉트 URI를 봉인), S256 PKCE 필수, 완료는 POST 전용,
  단일 사용 코드는 Redis `INCR`로 원자 소비하고 Redis 장애 시 메모리로 폴백하지 않는다(:997-1046), 헤드리스 클라이언트용 수동 코드
  전달(:914-962). → 지금은 불필요(IT 배포 관리형 설정 + 헤더 헬퍼). BYOD로 바뀌면 참조 구현.
- **도구 검색 간접화** `tool_search.py`: 모델에게는 검색·호출 가상 도구만 보이고 실제 도구는 불투명 id로 부른다. 임베딩이 없으면 키워드
  점수로 조용히 폴백(:173-197). → 후보: 도구가 많은 서버(gitea 39개)용. 정책 판정은 실제 도구 이름 그대로.
- **CRUD 위험 묶음 UI** `ui/…/McpCrudPermissionPanel.tsx`: 도구를 읽기·생성·수정·삭제로 묶어 3상태 체크박스로 고른다. UI 보조일 뿐 정책
  입력이 아니다. → 등록 화면의 도구 고르기에 그대로 쓸 수 있다(우리는 `r/w/x`가 이미 있다).

## 4. IBM ContextForge 1.0.11

- **페더레이션**(`mcpgateway/services/gateway_service.py:8-10, 1889-2073`): 피어 게이트웨이의 도구를 끌어와 로컬 레지스트리에 넣는다.
  → 가져오지 않음: 피어가 광고한 도구를 검토 없이 들이는 것은 D-05(TOFU 금지)를 게이트웨이 단위로 어기는 것이다.
- **가상 서버**(`server_service.py`): 여러 소스의 도구·리소스·프롬프트를 묶어 한 이름으로. → 가져오지 않음: "이 도구가 어느 계약에서
  왔는가"가 흐려져 계약 재검증의 단위가 애매해진다.
- **플러그인 프레임워크**: 사전·사후 훅(`tool_pre_invoke`/`tool_post_invoke`), 프로세스 안(native)·밖(gRPC·mTLS·유닉스 소켓) 플러그인,
  서버·테넌트 조건부 적용. 공식 플러그인 중 **회로 차단기**(오류율·연속 실패로 열고 쿨다운 뒤 시험 요청 하나)와 **watchdog**(최대 실행
  시간) → 후보: 느려진 업스트림이 모든 호출을 90초씩 붙잡는 것을 막는다(보안이 아니라 가용성).
- **통합 PDP**(`plugins/unified_pdp`): OPA·Cedar·MAC·RBAC를 all/any/first로 조합, 빈 결과는 거부, `explain_decision`은 캐시 우회.
  → 가져오지 않음: 정책 원천이 하나(OPA)라야 배포 번들 digest로 "무엇이 집행 중인가"를 말할 수 있다(D-25). **판정 캐시**도
  가져오지 않는다 — 승인 기한·취소·종료 케이스처럼 시간에 따라 판정이 바뀌는 입력이 많다.

## 5. Kong (문서 근거 — OSS에 코드 없음)

- `ai-mcp-proxy` 모드: passthrough-listener, conversion-listener(REST→MCP), conversion-only, listener(여러 변환 도구를 한 엔드포인트로).
- 도구 ACL: `default_acl` + `tools[].acl`(병합이 아니라 교체), deny 우선, 주체는 Consumer·Consumer Group.
- `ai-mcp-oauth2`: MCP 인가 명세의 Resource Server, introspection 또는 JWKS, **액세스 토큰을 업스트림에 넘기지 않음**(우리와 같음), 클레임 →
  Consumer·Group 매핑. 감사 로그는 켜고 끄는 스위치뿐 필드 스키마는 공개되지 않았다.

## 6. BeyondTrust (문서 근거)

- **Pathfinder MCP Gateway**(2026-04): 사용자가 토큰을 직접 발급(30/60/90일~1년), 요청 단위 승인 없음, 기존 역할을 그대로 통과, 현재 읽기 전용.
  문서가 "Claude Code는 Bearer 토큰을 `~/.claude.json`에 평문 저장한다"고 경고 — 우리 키트가 토큰을 하네스 설정에 넣지 않고 헬퍼로
  주는 이유와 같다.
- **PRA JIT 승인**: 지명된 승인자, **응답 없는 요청은 정해진 시간 뒤 자동 거부**, 최대 세션 시간 도달 시 종료·연장은 재승인, 승인자·시각·
  세션 기록. → D-51의 검토 기한(`CONNECTOR_REVIEW_DAYS`), D-49의 사용 기한과 재승인.
- **Entitle**: 역할 기반 승인자, 만료 시 대상에서 자동 회수, 접근 검토. → 종료 판정의 회수 대상과 같은 모델.
- **AI Agent Security**(Pathfinder 모듈, 베타): "MCP와 API 연결을 거버넌스하고 민감한 작업 전 승인" — 세부는 미공개.

## 7. 가져오지 않기로 한 것 (이유 한 줄)

| 기능 | 출처 | 이유 |
| --- | --- | --- |
| 게이트웨이 페더레이션 | ContextForge | 검토 없이 도구를 들임(D-05 위반) |
| 가상 서버 합성 | ContextForge | 계약 재검증 단위가 흐려짐 |
| 다중 정책 엔진·판정 캐시 | ContextForge | 집행 정책 식별(D-25)과 시간에 따라 바뀌는 판정 |
| 네트워크 너머 플러그인 | ContextForge | 새 신뢰 경계, 감사 체인이 플러그인 안을 못 봄 |
| 도구 이름으로 위험도 추정을 정책 입력으로 | LiteLLM UI | D-06이 경계한 실수 — UI 보조로만 |
| 헤더로 자기소개한 클라이언트를 인가 근거로 | LiteLLM | 위조 가능 — 쓰더라도 경보로만 |
