# LiteLLM MCP 인증·인가·upstream 수명 경로

## 1. 요약

- LiteLLM은 LLM 프록시와 별도로 MCP 집계·실행 경로를 제공한다. MCP 입구도 공통 키 인증과 로깅을 재사용한다(`F:174–180`, `A:438–445`, `S:1183–1218`).
- 일반 HTTP MCP의 입구→서버/도구 권한→호출→사후 가드레일→로깅 호출 경계는 L3다. 인증 방식마다 같은 권한 교집합이라는 설명은 부정확하다(`A:1472–1652,1726–1932`, `S:3285–3396`).
- 일반 upstream은 작업마다 세션을 생성·초기화·종료한다. 게이트웨이의 downstream 상태형 세션과 OAuth 토큰 캐시는 별개다. DEV-29의 upstream 세션 재사용 구현 근거로 삼지 않는다(`C:429–521`, `S:577–604`).
- DEV-29에는 주체 결속·활성 호출 보호·유휴 회수의 반례를, DEV-44에는 원본 Tool 보존과 전체 페이지 순회를 참고한다. 단, 부분 목록 반환을 계약 승인에 가져오지 않는다(`S:641–713,3685–3739`, `M:5072–5104`, `T:101–156`).
- 사후 MCP 가드레일과 인증 오류 재시도가 구현돼 있다. 철회 즉시성·다중 worker의 자격 캐시 무효화·배포 효과는 L4 미검증이다(`S:3176–3207`, `M:5528–5566`, `K/dual_cache_token_backend.py:50–74`).

## 2. 고정 정보

분석일은 2026-10-15다. 분석 원본은 `C:\Users\bobysg\bob\프로젝트\분석_litellm\litellm`이다.
origin은 <https://github.com/BerriAI/litellm>이며, `git -C`에 명령별 `safe.directory` 예외를 적용해 HEAD `f8e456d105af921213267d0ef801ca08b8fdbc0b`와 clean 상태를 확인했다.
`git describe --tags --always`는 `v1.101.0-rc.1-534-gf8e456d105`다. package 판본은 `pyproject.toml:1–8`의 **1.102.0**이다. 정확한 release tag와 동일하다는 뜻은 아니다.
MCP 의존성은 `pyproject.toml:69,114`의 `mcp>=1.28.1,<2.0`, lock은 `uv.lock:5224–5226`의 **1.28.1**이다. 설치 환경을 확인한 값은 아니다.
라이선스는 `LICENSE:1–26`을 읽었다. enterprise 디렉터리 예외와 MIT 조건이 있다. root의 `*NOTICE*`는 정적 미발견이며, 전체 배포물의 NOTICE 부재로 일반화하지 않는다. enterprise 라이선스 본문은 미독이다.

MINT 비교 기준은 시작 HEAD `8f962f5dbfede539dff6d4bf42449bca617f6527`과 당시 읽은 작업 트리다.
원격 HEAD 재확인은 네트워크 제한으로 실패했다. 작업 브랜치 `10/15-litellm-mcp-path` 생성도 공용 Git 메타데이터 경로 쓰기 권한 제한으로 실패했다.
마지막 상태 조회에서 다른 작업의 `README.md` 수정이 관측됐다. 이를 수정하거나 되돌리지 않았다. 이 작업은 본 파일만 생성한다.
사용자의 단일 파일 지시에 따라 현황·백로그·별도 작업 보고·협업 기록은 갱신하지 않는다. 외부 clone의 설치·빌드·스크립트·시험을 실행하지 않았다.

이하 LiteLLM 경로 약칭은 모두 위 고정 commit 기준이다. `경로:행–행`은 읽은 구간이며 각 행을 전부 정독했다는 뜻은 아니다.

| 약칭 | 실제 경로 | 읽은 주요 범위 |
| --- | --- | --- |
| S | `litellm/proxy/_experimental/mcp_server/server.py` | 570–890,1108–1282,1521–1792,2066–2358,2539–2616,2863–3397,3639–3740,3804–3886,4387–4710,4855–5099 |
| M | `litellm/proxy/_experimental/mcp_server/mcp_server_manager.py` | 975–1036,3142–3340,3819–4264,4962–5106,5173–5268,5335–5455,5508–5828,5878–5941,6015–6163,6251–6395 |
| A | `litellm/proxy/_experimental/mcp_server/auth/user_api_key_auth_mcp.py` | 264–567,894–1253,1472–1933,2089–2310,2352–2430 |
| C / T | `litellm/experimental_mcp_client/client.py` / `tools.py` | C:284–382,429–577,615–755, T:1–238 |
| R | `litellm/proxy/_experimental/mcp_server/rest_endpoints.py` | 466–518,595–640,961–1100,1100–1172 |
| D | `litellm/proxy/_experimental/mcp_server/db.py` | 784–846,1387–1495,1509–1614 |
| K | `litellm/proxy/_experimental/mcp_server/outbound_credentials/` | `adapter.py`:61–168, `resolver.py`:111–196,303–396 |
| K(계속) | 같은 경로 | `per_user_oauth_store.py`:48–151,184–235, `oauth_token_store.py`:1–300, `dual_cache_token_backend.py`:1–74 |
| K(계속) | 같은 경로 | `authz_code_refresher.py`:1–130, `redis_refresh_coordinator.py`:1–136, `client_credentials.py`:100–356 |
| H / U | `litellm/proxy/_experimental/mcp_server/guardrail_translation/handler.py` / `utils.py` | H:1–273, U:251–271,789–893 |
| F / P | `litellm/proxy/_lazy_features.py` / `proxy_server.py` | F:167–186, P:7185–7206,7861–7894,9638–9663,10648–10670,10686–10720 |
| B | `litellm/proxy/auth/user_api_key_auth.py` | 1204–1260,1726–1777,1878–1945,2378–2450,2773–2847,2877–3040 |
| I / Q | `litellm/proxy/auth/resolvers/store.py` / `auth_checks.py` | I:42–130, Q:2363–2450,3521–3660 |
| J / V | `litellm/caching/dual_cache.py` / `litellm/proxy/common_utils/auth_cache_invalidation_pubsub.py` | J:223–262,484–500, V:1–180,190–204 |
| 기타 | `litellm/proxy/utils.py`, `management_endpoints/mcp_management_endpoints.py`, `auth/auth_exception_handler.py` | 순서대로 3127–3196, 2263–2358, 100–200. 모두 `litellm/proxy/` 아래 |

시험 파일은 5절의 약칭과 행 범위를 읽었다. MINT는 `README.md`, 위키 지시·현황·백로그, `docs/ai/{README,ARCHITECTURE,SECURITY_BOUNDARIES,RUNBOOK}.md` 및 6절의 코드를 읽었다.

### 기능별 깊이와 경계

| 선택 기능 | 판정 | 닫힌 경로 / 남은 경계 |
| --- | --- | --- |
| HTTP MCP 인증·서버/도구 인가 | L3 | 키·gateway session의 resolver→목록/실행→결과 연결. 외부 JWT 검증기·SSO 전체 내부 구현은 별도 L2 경계 |
| 일반 upstream 수명·자격 주입 | L3 | 새 MCPClient→transport→initialize→작업→종료, 사용자 OAuth 저장·refresh·캐시·삭제 연결 |
| 실패·회수·worker·결과 처리 | L3(읽은 분기) | timeout·예외·fallback·로컬/공유 상태·기존 시험 연결. OBO/ID-JAG 교환 내부와 모든 OAuth 입출구는 L2, 실제 철회 효과는 미검증 |
| LLM/MCP 공유 경계 | L3(인증·훅 경계) | 공통 인증·request metadata·pre hook·logging 연결. LLM provider 전체·SpendLogs 최종 DB commit/내구성은 L2 이하 |

L3는 정적 호출 경로 추적이다. 모든 인증 방식의 내부 구현 또는 제품 전체가 L3라는 판정이 아니다. L4는 전 항목 미실행이다.

## 3. 경로 추적

### 3.1 MCP 입구 → 신원 → 서버/도구 권한 → 목록/호출

| 단계 | 함수·근거 | 상태 저장소 | 실패 시 결정 |
| --- | --- | --- | --- |
| 외부 입구 | lazy feature가 `/mcp`에 app을 mount(`F:174–180`); subapp의 `/`, `/mcp`, `/{mcp_server_name}/mcp`를 HTTP handler에 연결(`S:4830–4848`) | app routing | mount 경로와 원래 경로를 구분해야 함 |
| 요청 추출 | `handle_streamable_http_mcp`→`extract_mcp_auth_context`→`process_mcp_request`(`S:3639–3671,4387–4398`) | ASGI scope, ContextVar | path 지정 서버가 header 범위보다 우선 |
| 키 인증 | 명시 LiteLLM 키가 있으면 공통 `user_api_key_auth` 호출(`A:438–445`); builder→`IdentityStore.resolve`→cache/DB(`B:2877–2937,1895–1907`, `I:74–130`) | UserApiKeyCache, DB | blocked 키 거부(`B:1939–1940`); 인증 예외는 전파 또는 설정별 fallback |
| gateway session 인증 | signing key·session bearer 검사→`reload_admitted_user`→live policy(`A:894–1059,1197–1236`) | 서명 설정, 사용자/권한 cache·DB | 유효하지 않은 bearer는 challenge, 미구성은 500, DB 장애 분류는 503 |
| 위임/패스스루 분기 | 명시 키가 없는 특정 delegate/true passthrough는 빈 UserAPIKeyAuth로 진입(`A:446–477`); 입구에서 challenge/probe 실행(`S:4427–4441`) | 서버 설정, 요청 헤더 | 일반 키 인증과 동일하다고 볼 수 없음. 모든 익명 요청을 허용한다는 뜻도 아님 |
| 서버 resolver | manager→`get_mcp_server_access`→key/team/access-group/end-user/agent/user/org 처리(`M:3204–3338`, `A:1472–1693`) | object permission, 팀/조직 cache·DB, registry | 빈 범위·해석 오류·명시 거부·operator-open 채널을 별도 취급 |
| alias·URL 범위 | `_get_allowed_mcp_servers_from_mcp_server_names`(`S:1521–1574`) | 허용 서버 집합 | 명시 이름이 전부 불일치하면 `[]`; 범위 미지정일 때만 원 집합. 일부만 일치하면 일치한 부분 반환 |
| 목록 입구 | `handle_list_tools`→`_list_mcp_tools`→`_get_tools_from_mcp_servers`(`S:798–889,2567–2616,2165–2176`) | 요청 auth context | 이름 지정 후 접근 불가면 403/MCP 오류. 일반 예외 일부는 빈 목록으로 축약 |
| 목록 권한 | 서버 allow/deny→key/team tool filter→override(`S:2241–2265,1654–1694,2539–2565`) | 서버 정책, 권한 resolver | `get_allowed_tools_for_server`와 `tool_is_granted` 사용 |
| 실행 입구 | `mcp_server_tool_call`→request metadata→`call_mcp_tool`(`S:1139–1218,3285–3350`) | 요청 context, logging object | 서버 집합 재계산; 빈 허용 집합은 403 |
| 도구/서버 결속 | `execute_mcp_tool`이 display name·prefix·requested_server_id를 해석(`S:2896–2973`) | registry, 도구→서버 map | REST server_id와 prefix의 서버가 다르면 403 |
| 실행 권한 | managed 경로는 manager `call_tool`→`pre_call_tool_check`(`M:6048–6076,5335–5454`); OpenAPI local 경로도 같은 사전 검사(`S:3023–3068`) | 서버 정책, 동일 도구 권한 resolver | allow/deny·key/team·허용 인자·사전 훅 거부면 dispatch하지 않음 |
| 실행·반환·기록 | managed upstream→`_run_post_mcp_call_guardrails`→`_fire_mcp_tool_call_logging`(`S:3106–3118,3176–3283,3387–3396`) | CallToolResult, logging callbacks | 사후 거부는 오류 반환. 이미 발생한 도구 효과를 취소하는 흐름은 아님 |

**서버 권한은 단순한 5단 교집합이 아니다.** 일반 키는 key/team의 존재 여부에 따라 상속 또는 교집합을 쓰고 access-group extras를 합친다(`A:1512–1562`).
`require_key_mcp_access_defined` 기본 조회값은 false다(`A:1552–1555`). 사용자 세션은 자신과 실제 소속 팀의 source별 서버 허용을 합집합으로 계산한다(`A:1726–1845`).
도구도 해당 서버를 허용하는 source만 기여하며, 그중 무제한 source가 있으면 전체 허용을 반환한다(`A:1901–1932`).
manager는 `allow_all_keys`·자기 제출 서버·특정 익명 위임 서버 등을 합친 뒤 session resource scope를 마지막에 제한한다(`M:3142–3190,3273–3327`).
`mcp_allow_all_keys_respects_mcp_scope` 기본 조회값도 false다. 엄격 범위 설정과 `no_mcp_servers`를 혼동하지 않는다(`M:3234–3240,3312–3323`).

**목록/실행 공유와 차이:** key/team 도구 resolver와 `tool_is_granted`는 공유한다(`S:2552–2565`, `M:5250–5258`, `A:2273–2293`).
그러나 목록은 allowlist를 적용한 뒤 denylist도 뺀다(`S:1679–1694`). 실행의 `check_allowed_or_banned_tools`는 allowlist가 활성화되면 그 결과를 즉시 반환한다(`M:5183–5189`).
따라서 두 목록에 같은 도구를 넣었을 때 목록에서는 숨고 실행 사전 검사는 허용할 수 있다는 **소스상 추론**이 성립한다. 구성 진입점의 모든 validation과 실제 실행은 미검증이다.
또한 목록은 `_get_allowed_mcp_servers`에서 IP 필터를 적용하지만, protocol 실행의 `call_mcp_tool`에는 같은 필터 호출이 보이지 않는다(`S:1757–1761,3309–3325`).
REST 실행은 `_resolve_allowed_mcp_servers_with_ip_filter`를 사용한다(`R:1047–1050,486–501`). protocol 입구의 probe/challenge를 포함한 완전한 IP 우회 가능성은 **미확인**이다.
발견에서 숨겼다는 사실을 실행 차단 증거로 대체하지 않는다.

### 3.2 upstream 클라이언트·세션·자격

| 단계 | 함수·근거 | 상태 저장소 | 실패 시 결정 |
| --- | --- | --- | --- |
| 목록 연결 준비 | `_get_tools_from_server`→static header 해석→`_create_mcp_client`→목록 timeout wrapper(`M:4136–4142,4193–4228`) | 서버 설정, 사용자 자격 | header/자격 오류는 목록 outcome으로 전환 |
| 실행 연결 준비 | `_call_regular_mcp_tool`이 서버별 header→공통 MCP header→OAuth/static/hook header를 조합(`M:5613–5677,5683–5726`) | 요청별 dict | 중복 Authorization은 기존 자격을 우선하며 hook 값을 제한(`M:5689–5711`) |
| 자격 provider | `_create_mcp_client`→server spec→`_resolve_v2_auth`→provider(`M:3963–3984,4050–4074,3819–3875`) | ServerSpec, Subject | authz-code 자격 없음은 challenge; 미구현/오류는 공개 오류 변환 |
| 주체/서버 결속 | `to_subject`: tenant=org/team, subject=user; `_authz_token`은 user/server 조회(`K/adapter.py:61–74`, `K/resolver.py:385–394`) | 사용자×서버 토큰 | 이 token-cache key가 downstream MCP session이나 승인 계약을 결속한다는 뜻은 아님 |
| transport 생성 | HTTP는 새 httpx AsyncClient와 streamable transport, SSE/stdio도 각 transport context(`C:336–381`) | 요청별 transport | transport 초기화 오류 전파 |
| MCP 수명 | `run_with_session`→`ClientSession`→initialize→operation→session/transport exit→HTTP close(`C:429–521`) | 한 operation의 세션 | 일반 HTTP 목록/호출 사이 MCP 세션 풀·재사용은 이 경로에 없음. 종료 오류는 debug 기록 후 삼키는 분기 존재 |
| OAuth 저장 | 관리 REST→`store_user_oauth_credential`→암호화 DB upsert→cache invalidation(`D:1387–1447`, `management_endpoints/mcp_management_endpoints.py:2287–2300`) | DB 암호문, cache | 저장 성공과 모든 worker의 즉시 폐기는 별개 |
| OAuth 읽기/만료 | Lazy→Cached→Refreshing→V2 store(`K/per_user_oauth_store.py:145–151`); expiry 60초 전 refresh(`K/oauth_token_store.py:257–300`) | 로컬 또는 DualCache | refresh 불가면 None→인증 필요; 만료 토큰으로 fallback하지 않는 읽은 경로 |
| refresh·회전 | `AuthorizationCodeRefresher.refresh`가 DB의 최신 토큰을 읽는 coordinator 안에서 refresh·저장(`K/oauth_token_store.py:280–299`, `K/authz_code_refresher.py:87–130`) | DB, single-flight/Redis lease | 응답에 새 refresh token이 없으면 이전 것을 보존. 삭제와 refresh 저장의 원자 경쟁 제어는 미확인 |
| 자격 삭제 | 관리 DELETE→DB 삭제→manager 양쪽 token cache invalidate(`management_endpoints/mcp_management_endpoints.py:2320–2349`, `M:5880–5900`) | DB, v2/legacy cache | best-effort 무효화; upstream 인가 서버의 revoke API 호출은 이 경로에서 정적 미발견 |
| 결과 | `client.call_tool`은 CallToolResult를 반환(`C:709–754`); manager→execute→사후 통제(`M:5800–5827`, `S:3176–3207`) | 응답 객체 | 일반 예외는 isError 결과가 될 수 있음 |

**패스스루 여부:** 일괄 금지가 아니다. `PassthroughConfig`는 들어온 token을 Authorization에 넣는다(`K/resolver.py:175–185`, `K/adapter.py:116–117`).
한편 gateway session 자격은 egress context에서 제거하고, M2M·이전한 사용자 OAuth·token exchange는 caller Authorization을 제거하는 분기가 있다(`A:544–555`, `M:1011–1030`).
따라서 “LiteLLM은 항상 직원 키를 upstream에 전달한다”도 부정확하다. 선택한 auth mode·명시 admission header·서버별 자격에 따라 구분해야 한다.
MINT에는 직원 transport 토큰과 공급자 자격을 분리하는 부분만 참고하고 caller-token 패스스루는 채택하지 않는다.

**M2M과 OBO:** client_credentials는 설정 identity hash에 token URL·client ID/secret·scope·audience·resource를 포함한다(`K/client_credentials.py:305–318`).
M2M httpx auth는 401이면 refetch 후 같은 HTTP request를 한 번 더 보낸다(`K/client_credentials.py:340–353`).
OBO/ID-JAG 경로는 인증 오류에서 캐시 무효화→새 client→도구 호출 한 번 재시도한다(`M:5528–5566`). 교환 프로토콜 내부 전체는 미독이다.
이는 “재시도 없음”과 다르며 쓰기 도구의 중복 효과가 없다는 보장도 아니다.

### 3.3 downstream 상태형 세션과 다중 worker

| 단계 | 함수·근거 | 상태 저장소 | 실패 시 결정 |
| --- | --- | --- | --- |
| 세션 선택 | initialize 또는 session ID는 stateful, 나머지는 stateless(`S:4506–4512`) | 프로세스별 두 manager | upstream 재사용 여부와 무관 |
| 소유자 | API key hash→user ID hash→OAuth hash→IP hash→anonymous 순서(`S:3685–3739`); 소유자 불일치 403(`S:4478–4494`) | session ID→owner dict | MINT의 강한 주체 결속 대신 IP/anonymous fallback을 가져오지 않음 |
| 요청 신원 갱신 | HTTP마다 먼저 인증(`S:4387–4398`), 기존 auth context 갱신(`S:4624–4638,4904–4949`) | mutable auth context, ContextVar | 새 요청의 갱신은 진행 중 호출의 철회 재검사를 뜻하지 않음 |
| 경쟁 | stateful POST/DELETE lock, JSON-RPC 응답은 deadlock 방지 예외(`S:4566–4604,4658–4678`) | session별 lock·활성 요청 수 | 같은 세션 직렬화. 모든 worker 공통 lock은 아님 |
| 유휴/상한 | idle 30분·owner당 100(`S:99–106`), 활성 요청은 만료/축출 제외(`S:641–713`) | last_seen, transport dict | idle transport terminate 후 tracking 삭제. 활성 호출을 TTL로 중단하지 않음 |
| worker 이동/재시작 | 이 worker가 모르는 ID는 DELETE 200, 그 외 ID 제거 후 새 흐름(`S:3804–3885`) | worker 메모리, event_store=None(`S:577–589`) | 이전 상태의 복구/삭제를 증명하지 않음. 다른 worker의 기존 transport를 닫는 보장 없음 |
| 서버 설정 갱신 | scheduled DB reload(`P:7865–7888,9649–9658`)→registry 교체(`M:6251–6394`) | DB, worker별 registry | 조회 실패 시 작업을 기록하고 다음 주기를 기다림. 기본 보정 주기는 30초이며 즉시 철회 아님 |

### 3.4 LLM 프록시와 공유하는 지점

| 구분 | 연결 근거 | 공유 범위와 분리 경계 |
| --- | --- | --- |
| 인증 | LLM `chat_completion`의 Depends(`P:10648–10653`), MCP의 공통 인증 호출(`A:438–445,510–528`) | UserAPIKeyAuth·키/팀/조직 cache·공통 route/budget 검사. MCP 전용 session/delegate 분기는 별도 |
| 공통 검사 | `_authorize_authenticated_request`→route checks→centralized checks(`B:2773–2809`); gateway session도 공통 검사(`A:1197–1236`) | 동일 함수 사용이 동일 권한 의미를 보장하지 않음. MCP 서버/도구 resolver는 추가 단계 |
| 요청 metadata | MCP synthetic request→`add_litellm_data_to_request`(`S:1183–1204`); LLM은 `base_process_llm_request`로 진행(`P:10697–10715`) | 사용자·team billing·trace metadata 연결. MCP 실행이 LLM completion을 반드시 호출한다는 뜻은 아님 |
| 사전 가드레일 | MCP kwargs→가상 LLM 형식→공통 pre hook(`M:5397–5454`) | 공통 훅을 쓰되 call_type은 `call_mcp_tool`, 실행 대상은 MCPClient |
| 사후 가드레일 | `post_mcp_call_hook`→MCP translation handler(`S:3183–3207`, `litellm/proxy/utils.py:3127–3178`) | LLM completion 결과와 MCP 결과의 lifecycle은 별개 |
| 로깅 | MCP metadata 작성(`S:2975–2985`), 성공/실패 handler 호출(`S:3219–3283`), list도 function_setup/성공 handler(`S:2151–2163,2300–2335`) | 공통 Logging/callback seam 확인. SpendLogs 최종 DB 반영·append-only·감사 내구성은 이번 분석에서 입증하지 않음 |

## 4. 실패·경합·복구 결정표

`closed`는 해당 검사에서 새 실행/결과를 거부한다는 뜻이다. upstream의 실제 효과가 없음을 뜻하지 않는다.

| 조건 | 코드 동작·근거 | fail-open/closed | 미확인·반례 |
| --- | --- | --- | --- |
| 명시 alias 전부 불일치/빈 범위 | scoped filter `[]`(`S:1538–1574`); 비어 있는 명시 목록은 목록 0개, 실행은 최종 403(`S:2171–2176,3322–3336`) | 범위 확장에는 closed | 혼합 known/unknown은 부분 허용임 |
| 서버 권한 조회 오류 | resolver는 scoped/unresolved 빈 집합(`A:1642–1652`); manager는 operator-open/제출 서버를 유지하거나 fallback(`M:3273–3338`) | 전역 fail-closed 아님 | allow_all·자기 제출과 장애 조합을 따로 시험 |
| 도구 권한 일반 예외 | ordinary key는 None, keyless/admitted 또는 UnloadableEntitlementError는 `[]`(`A:2184–2197`) | 일반 키는 open 가능 | None은 `tool_is_granted`에서 무제한(`A:2261–2270`) |
| 조직 ceiling 조회 실패 | ordinary key는 기존 범위 유지, keyless는 축소(`A:1675–1693,2233–2245`) | 호출자 종류별 상이 | 존재하는 entitlement가 해석 불가한 경우와 구분 |
| DB 불능 시 인증 fallback | 명시 설정 조건에서 제한된 INTERNAL_USER fallback 발급(`auth/auth_exception_handler.py:120–144`) | 인증 연속성 허용 | 모든 MCP가 실행된다는 뜻 아님. 후속 권한·operator-open 조합 필요 |
| 목록 upstream 장애 | 서버별 예외→빈 도구+outcome, 정상 서버는 유지(`S:2273–2297`); 상위 일반 예외는 빈 aggregate/목록(`S:2611–2616,874–883`) | 부분 서비스/오류 축약 | 정상 빈 목록과 최상위 오류를 항상 구분하지 못함 |
| 목록 timeout | manager는 외곽 fail_after로 분류 오류(`M:4992–5008`), 기본 30초(`litellm/constants.py:176`) | 해당 서버 조회 거부 | 내부 페이지 helper의 부분 반환과 경쟁 |
| 순회 timeout·반복 cursor·상한 | helper는 모은 tools 반환(`T:123–156`); 상한 1000(`litellm/constants.py:179`) | 완결성 기준 open | 내부 deadline이 먼저 끝나면 불완전 목록이 성공 취급될 가능성 |
| 도구 timeout | gather 전체에 서버 timeout 또는 기본 60초, 외곽 timeout은 504(`M:5802–5812`, `litellm/constants.py:175`) | 결과 오류 | client 내부 timeout은 isError로 변환될 수도 있음(`C:724–754`). 실행 여부는 독립 확인 필요 |
| upstream 일반 오류 | client 기본은 isError 반환, strict 모드는 예외(`C:724–754`); protocol은 예외를 isError로 변환(`S:1219–1273`) | 성공 결과 반환에는 closed | HTTP 200이 도구 성공을 뜻하지 않음 |
| 사용자 OAuth 만료·refresh 실패 | 60초 skew·coordinator·refresher가 None 반환→challenge(`K/oauth_token_store.py:272–300`, `K/authz_code_refresher.py:87–117`, `M:3860–3864`) | 읽은 경로 closed | 만료 필드 누락·손상 전체 조합 미검증 |
| 자격 회전 | M2M identity hash 변경으로 새 cache slot(`K/client_credentials.py:305–318`); 사용자 REST 저장 뒤 invalidate | 새 요청 갱신 | 이미 만든 auth 객체·진행 중 요청은 이전 자격을 가질 수 있음 |
| Redis refresh lock 장애 | lock ERROR면 refresh를 실행(`K/redis_refresh_coordinator.py:94–108`) | single-flight 보장에는 open | 중복 refresh·rotation replay·grant family 철회 위험을 L4로 확인 |
| refresh lease 유실/장기 지연 | lease 갱신 실패는 갱신 coroutine 종료; refresh task 자체는 계속(`K/redis_refresh_coordinator.py:110–136`) | 단일 실행 보장 미확인 | refresh budget 20초는 작업 취소 deadline이 아님 |
| 사용자 OAuth cache TTL | expiry 있으면 expiry−60−now, 없으면 기본 300초(`K/oauth_token_store.py:172–188`, `K/per_user_oauth_store.py:48`) | TTL 내 cache 우선 | 알려진 expiry의 cache TTL이 항상 300초 이하라는 설명은 틀림 |
| 다른 worker의 자격 cache | token backend delete→DualCache의 이 worker 메모리+Redis 삭제(`K/dual_cache_token_backend.py:70–74`, `J:484–491`); 읽기는 메모리 우선(`J:234–249`) | 즉시 철회 보장 없음 | 이 삭제 호출 경로에서 auth invalidation publish는 정적 미발견. 다른 worker의 warm cache 잔존은 추론 |
| 키/팀/사용자 auth cache | 별도 publish/subscriber가 존재(`V:70–121,190–203`, `P:7185–7198`) | best-effort | Redis/pubsub 장애·cluster 미지원이면 TTL에 의존(`V:154–180`). OAuth token 삭제와 혼동 금지 |
| 권한/자격 철회 후 진행 호출 | 사전 검사 후 task 생성·응답 대기(`M:6065–6076,5800–5827`); downstream idle sweep도 active 제외(`S:648–650`) | 진행 실행 취소 보장 없음 | 이 경로에서 철회 event→진행 task 취소 연결은 정적 미발견. 다른 subsystem 전체 부재 주장은 아님 |
| OBO/ID-JAG·M2M 401 | 자격 재취득 후 제한 재시도(`M:5548–5566`, `K/client_credentials.py:340–353`) | 인증 복구 | 쓰기/응답 유실·독립 효과·중복 억제 미검증 |
| 사후 가드레일 거부 | 실행 결과를 공통 post hook에서 거부하고 오류 전파(`S:3176–3207,1240–1251`) | 결과 제공에는 closed | 실행 취소/부수효과 rollback 아님 |
| 가드레일 미구성 | proxy logging object 없음, callback/handler 없음이면 원 결과(`S:3197–3200`, `litellm/proxy/utils.py:3148–3155`) | 검사에는 open | 구성이 없어도 자동 검사한다는 보장 없음 |
| 마스킹 계약 충돌 | 텍스트 개수 불일치·너무 깊은 구조·수정 불가 key/숫자면 거부(`H:220–272`) | 결과 제공 closed | 이미지·비텍스트 전체 검사와 outputSchema 검증은 별개 |
| 로그 장애 | list 성공 로깅 예외는 계속(`S:2321–2335`); tool 로깅/실패 훅은 별도 예외 경로(`S:3251–3283,3372–3385`) | 일률 판정 불가 | 로그 저장 성공과 도구 실행 성공의 원자성 없음/미검증 |
| 정책 엔진 장애 | 읽은 MCP 경로는 Python resolver·훅, MINT의 OPA 호출과 다른 구조(`M:5335–5454`) | 공통 PDP 규칙으로 환산 불가 | 각 configured guardrail의 외부 엔진 장애 계약은 미독 |

## 5. upstream 시험

아래는 **기존 시험 코드의 존재·assert를 읽은 증거**다. 이번에 실행하지 않았다. mock/AsyncMock 단위 시험을 실제 OSS MCP 실행 증거로 세지 않는다.
약칭 `TS`는 `tests/test_litellm/proxy/_experimental/mcp_server/`, `TC`는 `tests/test_litellm/experimental_mcp_client/`다.

| 기능 | 기존 파일·시험명·읽은 위치 | 확인 대상 / 빠진 반례 |
| --- | --- | --- |
| 명시 alias | `TS/test_mcp_server.py:7266–7443`의 `test_get_allowed_mcp_servers_from_mcp_server_names_unknown_name_fails_closed` 및 known/mixed/empty 시험(함수 위치 확인) | URL 불일치→범위 확장 금지. 실제 HTTP·팀/키 회수와 조합 미실행 |
| 세션 결속·경쟁 | 같은 파일 `:2299–2913`의 refresh/expiry/active/owner mismatch/serialization 시험(함수 위치 확인) | downstream 세션 대상. upstream 세션 재사용 시험으로 세지 않음 |
| stale worker | `TS/test_mcp_stale_session.py:20–189`의 strip/delete/preserve 시험(함수 위치 확인) | 실제 두 worker에서 이전 transport·callback 잔존 확인 필요 |
| 도구 권한 실패 | `TS/auth/test_user_api_key_auth_mcp.py:7801–7826`, `test_org_ceiling_fault_fails_closed_for_admitted_but_open_for_keys` | AsyncMock 오류에서 admitted는 빈 집합, key는 기존 서버 유지 assert. 두 allow/deny 목록 충돌·IP list/call 동등성은 추가 필요 |
| OAuth 캐시 | `TS/outbound_credentials/test_per_user_oauth_store.py:64–224`의 lazy Redis 전환·in-flight local fetch 대기·invalidate 시험(함수 위치 확인) | refresh coordinator와 warm cache 두 worker의 철회 즉시성·삭제/refresh 경쟁은 별도 |
| OBO 재시도 | `TS/test_mcp_server_manager.py:9766–9865`의 `test_upstream_401_on_id_jag_evicts_the_cached_bearer_and_retries`, `test_non_auth_error_does_not_retry` | 가짜 client와 AsyncMock으로 각 1회 호출·무효화 또는 비재시도를 assert. 실제 쓰기 중복 효과는 미검증 |
| 페이지 | `TC/test_tools.py:112–223`의 `test_load_mcp_tools_follows_pagination`, cap/repeated cursor/deadline 시험 | cursor 전달·누적·중단 후 부분 목록 반환을 assert. 완결성 실패를 기대하는 계약 검증 반례는 없음/검토 범위 내 미발견 |
| Tool 보존 | `TS/test_mcp_metadata_preservation.py:23–79`, `test_create_prefixed_tools_preserves_metadata` | metadata/_meta/inputSchema 보존 assert. 승인 outputSchema·$defs·복합 schema의 전 구간 보존 시험은 아님 |
| 사후 가드레일 | `TS/test_mcp_server.py:8828–8904`의 rewritten result/no logging object/block 시험 | 마스킹 객체를 반환하고 block 예외를 전파하는 AsyncMock assert. 실제 guardrail outage·로그 DB commit은 별도 |
| 구조화 출력 | `TS/guardrail_translation/test_mcp_guardrail_handler.py:527–788`의 text/structured/key/numeric/depth 시험(함수 위치 확인) | 문자열과 구조화 값의 이중 노출 반례 후보. 현대 MCP 배열 wire 형식의 실제 SDK 호환성은 입증하지 않음 |

## 6. MINT 대조

이 절의 `G/`는 `full_stack_lab/gateway/app/`다. 백로그 근거는 `research/llm-wiki/status/backlog.md:36,51`의 DEV-29·DEV-44다.

| 단계 | MINT 현재 코드 | 가져올 것 / 가져오지 않을 것 / 이유 |
| --- | --- | --- |
| 목록과 실행 권한 | `_approved_tools`는 reviewed tools·principal·`pac.visible`로 필터(`G/mcp_facade.py:106–133`); 실행은 `execute_call`(`:188–199`), 자원/인자 권한은 `pac.scope`(`G/pac.py:69–120`) | 동일 resolver의 공통 축을 재사용하고 목록≠인자 포함 실행 허용을 문서화. LiteLLM의 일부 장애 시 None/무제한 fallback은 가져오지 않음 |
| 실행 직전 재검사 | `_call_upstream`: 같은 세션에서 list→description/input hash→인자 검증→principal/approval/PAC 재검사→dispatch intent→call(`G/core.py:1225–1307`) | 세션 재사용 도입 후에도 이 순서를 유지. LiteLLM의 발견/실행 분리만 이식해 계약 재검증을 생략하지 않음 |
| DEV-29 현재 연결 풀 | `_dispatch_client` key=(endpoint,principal,timeout,headers hash), max pool 32, HTTP keepalive 60초(`G/upstream.py:89–98,157–184`); `session`은 매번 MCP Client 생성(`:188–203`) | 현재는 HTTP 연결 재사용과 MCP 세션 재사용을 구분해야 함. LiteLLM 일반 upstream도 작업별 MCP session임(`C:429–521`) |
| DEV-29 철회 | `close_pool`은 사용 중 lease를 evicted로 표시하고 반환 때 close; `release_pool`은 DB event, `_sweep`은 2초 간격 읽기(`G/upstream.py:101–184`) | graceful close와 진행 호출 취소를 별도 요구사항으로 둠. LiteLLM의 active-session 보호는 정상 호출 보존 반례로 참고 |
| DEV-29 재사용 설계 | DEV-29는 주체·downstream session·서버·자격 hash 결속을 제안(`status/backlog.md:36`) | 제안: MCP session key에 이 네 축과 transport/endpoint·자격 세대·계약/정책 재검사 시점을 결속. 현재 HTTP pool key에 downstream session이 없다는 사실을 MCP session 구현 완료로 읽지 않음 |
| DEV-44 Tool 원본 | `tool_view`가 name/description/input_schema/annotations만 구성(`G/upstream.py:206–225`); facade도 inputSchema만 재구성(`G/mcp_facade.py:132`) | LiteLLM의 `model_copy(deep=True)` 후 이름만 변경(`M:5086–5104`) 참고. 원본 Tool·outputSchema·$defs·추가 필드 보존과 승인 hash 반영을 별도 구현 |
| DEV-44 결과 | MINT는 structured_content를 옮기고(`G/core.py:1311–1314`) facade가 structuredContent로 반환(`G/mcp_facade.py:159–170`) | LiteLLM도 원 CallToolResult 반환·구조화 마스킹(`C:709–720`, `H:220–272`). 객체/배열의 SDK 판본별 wire 제약은 별도 검증하며 임의 객체 wrapper로 숨기지 않음 |
| DEV-44 페이지 | MINT의 discover와 호출 전 검사는 한 번의 `client.list_tools()`(`G/upstream.py:217–224`, `G/core.py:1229–1231`) | SDK가 자동 순회하는지는 이 파일만으로 판단 불가. 전체 목록 완결성·중복명·cursor loop·deadline을 직접 검증. 부분 목록을 정상 승인에 쓰는 helper 동작은 가져오지 않음 |
| 자격 | MINT는 endpoint·allowed_principals·HTTPS·만료·파일 권한 검사 후 별도 공급자 bearer 생성(`G/upstream.py:37–74`) | 공급자 자격 경계와 회전 fingerprint는 참고. 직원 토큰 passthrough·익명 위임·공유 개인 자격은 채택하지 않음. DEV-43의 회수 검수와 연결 |
| 오류·중복 | MINT는 호출 전 `dispatch.record`, 응답 유실은 uncertain 조회/관리자 확인 경로(`G/dispatch.py:37–117`); attempted/executed 분리(`G/core.py:1305–1314`) | OBO/M2M 재시도는 그대로 채택하지 않음. 읽기/멱등성 또는 공급자 idempotency 증거가 없으면 자동 재실행하지 않는 조건을 유지 |
| 사후 통제·증거 | MINT 출력 차단도 실행됨을 남김(`G/core.py:1838–1873`, `G/mcp_facade.py:174–180`) | LiteLLM의 content+structured 이중 마스킹 반례를 DEV-44·39에 사용. 기록 수나 훅 존재로 독립 효과·종료 C1~C4를 대신하지 않음 |

**DEV-29 결정 제안:** TTL은 유휴 TTL·절대 자격 만료·절대 승인 만료를 분리한다. TTL마다 세션이 끊기는지보다 재사용 직전 live principal/계약/PAC 검사를 통과하는지가 우선이다.
회수 시 새 lease 거부→대상 세대 무효화→유휴 세션 close→진행 호출의 취소/완료/실행불명 기록을 나누고 worker별 확인을 남긴다.
이는 제안이며 새 기능 구현·채택 결정·기존 세션이 즉시 중단된다는 주장이 아니다. 현재 `close_pool`은 진행 lease의 사용 종료를 기다린다(`G/upstream.py:108–114,181–184`).

**DEV-44 결정 제안:** 원본/정규화/승인 schema를 구분하고 원본 `$defs`·`$ref`·복합형·outputSchema의 의미를 보존한다.
검토한 upstream은 Tool deep copy를 하지만 OpenAI용 schema 변환에서는 type/properties/additionalProperties 기본값을 넣는다(`M:5086–5096`, `T:42–69`). 이를 MCP 원본 정본으로 역저장하지 않는다.
읽은 일반 MCP 경로에서 승인된 outputSchema와 결과를 게이트웨이가 직접 대조하는 검증은 정적 미발견이다. SDK 내부 검증 또는 tool-search의 별도 입력 검증까지 부재로 확대하지 않는다.
실제 SDK 판본의 배열 structuredContent·legacy 객체·마스킹 뒤 schema 적합성을 시험하고, 불완전 list는 오류로 처리해야 한다.

## 7. 목표 기능 재설계 시사점

| 목표 기능 | 제안과 근거 |
| --- | --- |
| 도입 검증·승인/계약 | 목록 완결성을 승인 전제에 추가한다. 원본 Tool·outputSchema·schema dialect를 승인 대상에 포함한다. 부분 목록 반환과 선택 필드 재구성이 근거다(`T:123–156`, `G/upstream.py:206–225`) |
| 신원·호출 권한 | None/빈 목록/해석 불가/명시 거부를 원자 조건으로 나눠 list/call 쌍 시험을 둔다. shared resolver만으로 일치 판정하지 않는다(`A:2184–2270`, `S:1679–1694`, `M:5183–5189`) |
| 데이터 보호 | content와 structured의 동일 민감값·key/숫자·depth·마스킹 후 schema를 함께 확인한다. 변환 불가하면 결과 보류와 실행 여부를 분리한다(`H:220–272`, `G/core.py:1865–1873`) |
| 종료·폐기·세션 운영 | 자격 DB 삭제·cache 삭제·HTTP pool close·MCP session terminate·공급자 자격 철회를 다른 증거로 둔다. DELETE 200 또는 cache invalidate는 C1~C4 충족 근거가 아니다(`S:3862–3885`, `D:1567–1612`) |
| 감사·지표 | permission deny·upstream auth failure·list partial·tool isError·output withheld·effect unknown을 분리한다. 성공 HTTP 수를 성공 업무/차단 효과로 세지 않는다(`S:3235–3283`, `G/mcp_facade.py:138–148`) |
| 엔드포인트 집행·하네스 운영 | 이번 소스에서 목표 변경 근거 없음. 게이트웨이를 통과하는 MCP와 LLM의 공유 경로를 읽은 것이며 우회 실행·실제 관리 하네스 집행은 검증하지 않았다 |

## 8. 정정

기존 파일은 변경하지 않는다. 아래는 이번 고정 commit/현재 비교 코드로 읽을 때의 대체 관계다. 과거 1.89.4 기록 자체의 진위를 소급 확정하지 않는다.

| 기존 문장·위치 | 이번 정정·근거 |
| --- | --- |
| `docs/ai/BENCHMARK_LITELLM.md:14–15,34,36`의 5단 교집합 | 1.102.0은 key/team 상속·교집합 외 access-group extras/open 채널 및 admitted source 합집합이 있다(`A:1537–1562,1839–1845`, `M:3273–3327`). 단일 교집합으로 표현하지 않음 |
| 같은 문서 `:39`의 사전만/사후 not implemented | 현 commit에는 `execute_mcp_tool` 반환 경로의 post_mcp_call과 구조화 출력 마스킹이 있다(`S:3176–3207`, `H:189–273`). 현재의 차별점 근거로 재사용 불가 |
| 같은 문서 `:48`의 재시도 없음 | 일반 비인증 오류 비재시도와 OBO/ID-JAG 인증 실패 재호출, M2M 401 HTTP 재전송을 구분(`M:5548–5566`, `K/client_credentials.py:340–353`) |
| 같은 문서 `:31–33`의 MINT upstream 자격 없음 | 현재 비교 코드는 파일 기반 공급자 자격 binding을 갖는다(`G/upstream.py:37–74`). 직원 transport 토큰 비전달 원칙과 공급자 자격 사용 가능성을 구분 |
| `research/llm-wiki/solutions/litellm.md:11`의 session resource 상한 위치 | `M:3175–3202`는 operator-open 및 scope 추출이다. 실제 마지막 scope 필터와 fallback 필터는 `M:3326–3337`. 결론의 범위는 유지하고 행 근거를 보완 |
| 같은 카드 `:9`의 unknown→빈 집합 | 유지. 상위에서 명시된 비어 있지 않은 unknown 범위는 403으로 바뀐다는 경로를 추가(`S:2171–2176,3326–3336`). helper 반환만 최종 wire 동작으로 설명하지 않음 |
| 같은 카드 `:23`의 미실행 한계 | 유지. 이번에는 정적 호출 경로를 보완했으며 OAuth 회수·다중 worker·부하를 실행한 것은 아님 |

## 9. 남은 미독 범위와 L4 재현 제안

미독/부분 읽기는 enterprise/SSO/JWT 전체, DCR/bridge/ID-JAG/token-exchange 내부, OpenAPI 생성기 전체, sampling/elicitation 실행 루프, SDK 1.28.1 내부, 최종 SpendLogs DB 저장·내구성이다.
일부 파일은 함수 위치/검색 결과만 읽었다. 위 표에서 표시한 시험도 실행 결과가 아니다. upstream 오류·취소·멀티 worker·schema 차이의 실제 효과를 이 문서로 통과 처리하지 않는다.

환경은 고정 LiteLLM commit·lock·MINT commit·정책/config hash, 독립 DB/Redis, worker 2개, 공개 OSS MCP의 고정 판본과 합성 데이터/격리 계정이다.
자체/mock MCP를 새로 만들지 않는다. 실제 도구가 제공하지 않는 경합은 제어 proxy/네트워크 장애 주입으로 재현하고 한계를 명시한다.
솔루션은 솔루션 기기에서만 띄우고, 하네스는 PJ1의 새 관리 세션을 사용한다. 이 분석 clone에서는 실행하지 않는다.

| 분류 | 최소 시나리오 | 기대 관측·DEV 연결 |
| --- | --- | --- |
| 정상 | 같은 주체/서버 읽기 2회, 서로 다른 주체·서버 각각 호출 | MCP initialize/transport 수, 지연, 공급자 수신과 반환을 분리. DEV-29 연결 풀과 MCP 세션 재사용 구분 |
| 음성 | unknown/빈/혼합 alias, server_id-prefix 불일치, 다른 팀/키, 두 allow/deny 목록 충돌 | 목록과 직접 call의 resolver·결정 이유·upstream 미수신을 쌍으로 확인 |
| 경계 | source 무제한/빈 권한, allow_all와 명시 scope, protocol/REST의 외부 IP | 인증 방식별 open 채널·ceiling 차이와 list/call 일치. 권한을 완화해 호환시키지 않음 |
| 계약·페이지 | `$defs/$ref`·oneOf/allOf·outputSchema, 정상 다중 페이지·중복명·반복 cursor·상한·중간 timeout | 완결성 실패는 승인 불가; schema 원본/노출/승인/호출 hash 및 SDK 1.x/2.x 객체·배열 결과. DEV-44 |
| 장애 | upstream 401/403/500·read timeout·응답 유실, guardrail/DB/Redis 장애 | 오류/부분목록/isError/출력보류/실행불명을 분리. 독립 부수효과로 자동 재시도 중복 확인 |
| 경쟁 | 두 worker warm cache 후 권한/자격 삭제·회전, refresh 중 삭제, lease 유실·서버 변경 | 새 호출 차단 시점·잔존 cache·진행 호출·refresh 토큰 재생/재저장 확인. DEV-29·43 |
| 복구 | worker 재시작·stale ID·Redis 재연결·DELETE·세션 TTL/상한 | orphan transport·다른 worker 잔존·정상 업무 복구·로그 누락을 확인. DELETE 200을 폐기 증명으로 세지 않음 |

각 run은 요청 ID·주체/서버/자격 세대·worker·설정 hash·판정/오류·upstream 독립 수신/효과·결과 제공 여부·정리 결과를 연결한다.
이번 산출물은 정적 분석이다. 배포·실제 OSS MCP 호출·PJ1 검수·독립 효과·회수 즉시성·성능은 확인하지 않았다.
