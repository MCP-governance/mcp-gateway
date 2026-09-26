# LiteLLM MCP 게이트웨이 벤치마킹 (2026-09-26)

> 이 랩이 LLM 게이트웨이로 쓰는 LiteLLM에는 **MCP 게이트웨이 기능**이 따로 있다. v1~v3를 설계하면서 이 기능을 비교하지
> 않았고, 이 문서가 그 비교다. 반영한 것은 D-39·D-40, 다음 후보는 [ROADMAP.md](ROADMAP.md) 1절에 옮겼다.
>
> - 근거: LiteLLM **1.89.4 설치 소스**(`litellm/proxy/_experimental/mcp_server/` 등, 아래 경로는 `litellm/` 기준)와
>   이 저장소 `main`(`dacc1ce`, v3.0). 문서보다 코드를 우선했다. 줄 번호는 그 시점 기준이다.
> - 같은 조사를 Proxy 브랜치에도 했다(투명 프록시의 경계에서 가져올 것). 결과는 Proxy 브랜치의 `docs/ai/DECISIONS.md` D-38.

## 1. 요약

1. LiteLLM MCP 게이트웨이는 **멀티테넌트형**이다: 키·팀·조직·end-user·agent의 교집합 권한, 업스트림 인증 9종(OAuth2
   4가지, BYOK, 토큰 패스스루 포함), 도구 이름 접두어로 여러 서버를 한 엔드포인트에 합친다. main은 **단일 조직 거버넌스형**이다:
   역할×등급×행위 권한 번들, 매 호출 계약 재검증, 해시 체인 감사, 논문의 종료 판정.
2. 그래서 기능을 그대로 옮기면 안 되는 곳이 많다. 특히 `oauth_passthrough`·`delegate_auth_to_upstream`·BYOK는
   "직원 토큰을 upstream에 넘기지 않는다"·"신원은 transport 토큰에서만" 불변식과 정면으로 부딪힌다(5절).
3. 비교하다 main 안의 격차를 찾았다: **이용 관계의 `allowed_resources`가 실시간 판정에 쓰이지 않았다.** 종료 케이스를 열 때만
   읽혀서(`gateway/app/decommission.py:226`), 논문의 분석 단위가 평상시 호출에는 서류로만 있었다 → D-39로 연결.
4. LiteLLM은 헬스 체크(`health_check_server`)를 도구 목록 조회와 분리해 둔다. main은 연결 확인이 계약 재검증(`refresh_catalog`)과
   묶여 무거웠다 → D-40.

## 2. 기능 대조

| # | 기능 | LiteLLM (1.89.4) | main (v3.0) |
| --- | --- | --- | --- |
| 1 | 서버 등록·저장 | 설정 파일 서버와 DB 서버를 합집합으로 노출(`mcp_server_manager.py:589-593`), CRUD `POST/PUT/DELETE /v1/mcp/server`(`management_endpoints/mcp_management_endpoints.py:1416,1848,2413`) | **부분** — `registry/catalog.toml`(git 리뷰)을 기동 때 DB로 동기화(`registry.py`). 런타임 추가 없음, 카탈로그 수정 + 이미지 재빌드 |
| 2 | 업스트림 전송 | stdio·sse·http(`types/mcp.py:19-22`) | **부분** — upstream은 Streamable HTTP만, 대신 **클라이언트 쪽**이 HTTP·SSE·stdio 3종(`sse_entry.py`, `stdio_entry.py`) |
| 3 | 서버별·통합 엔드포인트, 도구 접두어 | `/mcp`, `/{server}/mcp`, 접두어 `{server}-{tool}`(`server.py:4119-4123`, `utils.py:29-30,245-253`) | **동등** — `/mcp/<server>/`(원래 이름) + `/mcp/`(`<server>__<tool>`) |
| 4 | 업스트림 인증 | 9종 `auth_type`(`types/mcp.py:31-40`) | **없음(의도)** — Gateway는 자격 없이 붙고 서버가 자기 자격을 가진다(`upstream.py` 머리말) |
| 5 | static/extra headers | 서버별 고정 헤더 + 클라이언트 헤더 전달 목록(`mcp_server_manager.py:3309-3435`) | 없음(같은 이유) |
| 6 | OAuth2·BYOK·패스스루 | client_credentials, RFC 8693 교환, `delegate_auth_to_upstream`, `oauth_passthrough`, BYOK(`auth/`, `byok_oauth_endpoints.py`, `db.py:872-1210`) | **없음(의도)** — 자체 IdP는 하네스↔Gateway 신원 전용 |
| 7 | 서버 허용(주체별) | `object_permission.mcp_servers`, 5단 교집합(`auth/user_api_key_auth_mcp.py:615-767`) | **다른 축** — 서버가 아니라 자원 단위의 역할×등급×행위 번들(`opa/data.json`) |
| 8 | 도구 허용 목록 | `mcp_tool_permissions: {server: [tool]}`(`auth/user_api_key_auth_mcp.py:822-927`) | **부분** — 카탈로그의 `enabled`·`action`이 전사 1벌. 이용 관계·부서별 목록 없음 |
| 9 | 도구 목록 필터 | 허용 교집합 + `filter_tools_by_allowed_tools()`(`server.py:1102-1144`) | **부분** — `mcp_facade._approved_tools()`가 승인·상태로 거르고 협력사는 읽기만 |
| 10 | 공개 서버 | `available_on_public_internet`(`mcp_server_manager.py:3944-4011`) | **없음(의도)** — `/mcp`는 전부 Bearer 필수 |
| 11 | 헬스 체크 | `health_check_server()` 세션 협상만(`mcp_server_manager.py:4173-4295`), `GET /v1/mcp/server/health` | **부분** → **D-40으로 보완**. 전에는 60초 주기 `refresh_all_catalogs()`가 `tools/list`까지 읽으며 상태를 겸함 |
| 12 | 가드레일 | 사전만(`guardrail_translation/handler.py:33-87`), 사후는 "not implemented"(`:89-100`) | **앞섬** — 사전 Presidio 검사 + 사후 마스킹·주입 표지·크기 거부 |
| 13 | 비용 | 도구별 고정 단가(`cost_calculator.py:19-77`) | 없음 |
| 14 | 호출 로그 | `StandardLoggingMCPToolCall` → SpendLogs(`types/utils.py:2549-2591`, `schema.prisma:577-614`) | **앞섬** — 판정·정책 입력·위험 점수·개인정보 유형 + 해시 체인 |
| 15 | 도구 레지스트리 | 프로세스 전역 `{이름→(스키마, handler)}`(`tool_registry.py:22-42`) | 다른 모양 — `mcp_tools` 테이블 + 카탈로그 정본 |
| 16 | toolset(도구 묶음) | `LiteLLM_MCPToolsetTable`(`toolset_db.py:14-117`) | 없음 |
| 17 | 의미 기반 도구 선택 | 임베딩 top-K(`semantic_tool_filter.py:21-201`) | 없음 — ROADMAP의 "CPU 2B 모델 도구 선택" 격차와 관련 |
| 18 | OpenAPI→MCP | `openapi_to_mcp_generator.py` | 없음 |
| 19 | 관리 REST | `/v1/mcp/*` 34개, `/mcp-rest/*` 4개 | **부분** — 계약 승인·카탈로그 재조회·종료 REST(LiteLLM엔 없는 영역) |
| 20 | 속도 제한 | MCP 전용은 없고 LLM 훅에 얹힘(`mcp_server_manager.py:3149-3267`) | **있음** — `P-RATE-001`·중요정보 버스트·차단 연속을 정책이 판단 |
| 21 | 타임아웃·재시도 | `MCP_CLIENT_TIMEOUT` 60초, 재시도 없음 | 90초, 재시도 없음(`MCP-UPSTREAM-001`) |
| 22 | 서버 제출→승인 | 비관리자 `register` → 관리자 `approve`(`mcp_management_endpoints.py:1084-1207`) | **없음** — 도입 신청은 있으나 승인해도 카탈로그에 안 들어감 |
| 23 | Sampling·Elicitation | 지원(`sampling_handler.py`, `elicitation_handler.py`) | **없음(의도)** — 중재 메서드는 initialize·ping·tools/list·tools/call |
| 24 | 공개 카탈로그 | `/v1/mcp/registry.json` | 없음 — 무인증은 `/api/health`·로그인뿐 |

## 3. 이번에 반영한 것

| 결정 | 무엇 | LiteLLM 참고 | 바뀐 곳 |
| --- | --- | --- | --- |
| D-39 | 이용 관계의 허용 자원을 **모든 호출의 정책 입력**(`relationship`)에 싣고, 범위 밖이면 `P-SCOPE-001` 경보 | 권한 목록을 호출 때마다 평가하는 구조(`get_allowed_mcp_servers()`, `get_allowed_tools_for_server()`) | `classify.outside_scope`, `core._relationship_scope`, `opa/policy.rego`, 관리대장 2.3.0 |
| D-40 | `POST /api/registry/{server}/check` — 세션만 협상하고 계약·상태·감사는 건드리지 않는 연결 확인, Console 서버 화면의 "연결 확인" | `health_check_server()`와 도구 조회의 분리 | `upstream.handshake`, `core.check_server`, `main.py`, `console.js` |
| D-41 | 해시·결과 스키마·감사 열 집합을 순수 모듈 `contract.py`로(7절 3번) | TypedDict·선언 파일로 스키마를 관리하는 방향(`_types.py`) | `contract.py`, `core.py`, `replay.py`, `registry.py` |

## 4. 다음 후보 (우선순위순)

1. **도입 신청 → 카탈로그 초안** — 승인 시 `catalog.toml` 항목 초안과 계약 잠금 후보를 만들어 사람이 검토·커밋한다.
   LiteLLM의 제출→대기열→승인 REST 모양만 참고하고, 승인 뒤 재검증 없이 신뢰하는 모델은 가져오지 않는다(5절).
2. **이용 관계별 도구 허용 목록** — `[[usage_relationships]]`에 `allowed_tools`를 두고 `P-SCOPE-001`과 같은 입력으로 판단.
   LiteLLM `mcp_tool_permissions`의 자료 구조만 참고(키→팀→조직 교집합 대신 이용 관계 1단).
3. **`P-SCOPE-001` 차단 승격** — 이용 관계 소유 부서가 `allowed_resources`를 인가 목록으로 검토한 뒤 관리대장에서 결정.
4. **하네스의 완전한 MCP OAuth(DCR + 인가 코드 + PKCE)** — IdP에 `/oauth/register`·`/oauth/authorize`. LiteLLM의
   `discoverable_endpoints.py`는 위임형이라 뼈대만 참고.
5. **CPU 소형 모델용 도구 선택 보조** — 도구가 많은 서버(gitea 39개, desktop 19개)에서 질의와 가까운 도구만 노출.
   LiteLLM은 임베딩을 쓰지만 의존성 없이 키워드 방식부터.
6. **도구 호출 비용 필드** — 고정 단가를 `decisions`에 남겨 "차단이 아낀 비용"을 정량화(LiteLLM의 3단 해석 순서 참고).

## 5. 가져오지 않는 것

| LiteLLM 기능 | 이유 |
| --- | --- |
| `oauth_passthrough`·`true_passthrough`(`mcp_server_manager.py:166-200`) | 클라이언트 토큰을 upstream에 그대로 전달 — MCP 인가 명세의 토큰 전달 금지, AGENTS.md 불변식 |
| `delegate_auth_to_upstream`의 익명 접근(`auth/user_api_key_auth_mcp.py:377-427`) | 신원은 transport 토큰에서만, 무인증은 `/api/health`·로그인뿐 |
| BYOK(`db.py:872-1210`) | Gateway가 직원 개인 자격을 보관하면 새 신원 경로가 생기고 침해 시 전 직원의 upstream 계정으로 번진다 |
| 승인 후 무재검증 신뢰(`mcp_management_endpoints.py:1195-1207`) | main은 TOFU 금지 + 매 호출 계약 재검증(`MCP-CATALOG-001`) |
| Sampling·Elicitation | 두 채널의 분류·감사·차단 기준을 먼저 설계해야 한다. 지금 10종 서버 중 쓰는 곳이 없다 |
| 공개 서버·공개 카탈로그 | 무인증 경로를 늘리지 않는다 |

## 6. main이 앞선 점 (논문·발표의 차별점)

1. **호출 직전 계약 재검증** — 같은 연결에서 `tools/list`를 다시 받아 해시를 대조한다(`core._call_upstream`).
2. **사후(출력) 통제** — 결과의 개인정보 마스킹·주입 표지·크기 제한. LiteLLM MCP 가드레일은 사전만 구현.
3. **해시 체인 append-only 감사 원장**과 변조 행 지목(`/api/audit/verify`).
4. **후보 수집 + 우선순위 PaC** — 진 후보가 `conflicts`에 남아 정책 충돌이 관측된다.
5. **위험·통제·요구사항 추적이 달린 관리대장**과 배포 정책 묶음 digest(D-25).
6. **논문의 종료 판정(C1~C4 / T1~T3)** — LiteLLM에는 서버 삭제 외에 종료 보증 개념이 없다.
7. **읽기 뒤 외부 전송 연쇄 탐지**(`P-CHAIN-001`)와 **관찰 모드**(`would_decision`).

## 7. 리팩터링 후보

1. **권한 원천이 둘로 나뉘어 있다** — 역할×등급×행위 번들(`opa/data.json`)과 이용 관계 허용 자원(`catalog.toml`). D-39로 둘 다
   정책 입력이 됐지만, 후자는 아직 경보만 낸다. 차단으로 올릴 때 POLICY.md에 두 원천의 관계를 한 표로 정리한다.
2. **카탈로그 원천 분리** — LiteLLM은 설정 서버와 런타임 서버를 두 맵으로 합친다(`mcp_server_manager.py:589-593`). 도입 신청을
   카탈로그에 잇는 후보 1을 하려면 `registry.py`가 "리뷰된 카탈로그"와 "승인 대기 초안"을 구분해야 한다.
3. ~~**감사 열 집합 상수**(`core.AUDIT_COLUMN_SETS`)를 `core` 밖 모듈로 — ROADMAP 6절의 "순수 계약 모듈"과 함께.~~ → D-41
