---
date: 2026-10-15
scope: MINT 의존성 MCP Python SDK(ClientSession/Client), Authlib(OIDC 소비자), OPA(HTTP data API)의 "사용 API→호출자→실패 시 최종 결정" 연결
---

# MCP SDK + Authlib + OPA 의존성 심층 분석 (DEV-47 2단계)

## 요약

세 의존성 모두 MINT의 판정 경로 바로 앞 또는 뒤에 있다: MCP SDK는 업스트림 호출(`upstream.py`/`core.py:_call_upstream`), Authlib은 콘솔 로그인(`oidc.py`), OPA는 PAC 판정(`core.py:_policy`)이다. 다룬 기능과 판정은 다음과 같다.

- **MCP SDK `tools/list` 페이지(cursor)** — L3. MINT는 `upstream.py`·`core.py` 어디서도 `next_cursor`를 읽지 않는다. SDK는 자동 페이지 병합을 하지 않으므로(한 번 보낸 요청의 응답만 반환), 업스트림이 페이지를 나누면 두 번째 페이지 이후의 도구는 카탈로그 비교(`refresh_catalog`)와 실행 직전 재검증(`_call_upstream`)에서 빠진다. 실행 직전 재검증 쪽은 **등록된 도구 전체**를 기준으로 막기 때문에, 영향은 "그 도구만 못 부름"이 아니라 "그 서버의 모든 호출이 차단"으로 번진다 — 보안 우회가 아니라 가용성 버그다.
- **DEV-29 1단계(mode 고정)** — L3, 코드와 주장이 일치한다. `upstream.py:188-203`은 `protocol`이 handshake-era 버전이면 `mode="legacy"`로 바로 `initialize`를 보낸다. SDK의 `mode="auto"` 경로(`_probe.py`)는 legacy 서버를 상대로 `server/discover` 1회 실패 후 `initialize` 1회, 총 2 라운드트립이므로 "1회 절감" 주장은 소스로 확인된다.
- **DEV-44(outputSchema)** — L3. SDK는 `CallToolResult.structured_content`를 선언된 `outputSchema`로 검증하지만(`session.py:1118-1183`), 그 스키마 캐시도 `list_tools()`의 첫 페이지에서만 채워진다 — 1번 항목과 같은 뿌리의 문제다. MINT 쪽의 별도 방어(`core.py:_guarded_result`)는 `structured`가 object가 아니면(배열 등) 통째로 버리고 text로만 전달 — 이미 해결된 사례로 재확인했다.
- **Authlib `aud` 미검증** — L2/L3, 새로 확인한 구체적 공백. `oidc.py:132-133`의 `claims_options`는 `iss`만 지정하고 `aud`를 지정하지 않는다. Authlib은 `aud`가 `claims_options`에 없으면 **값 비교를 하지 않는다**(`validate_aud`는 존재 여부만 요구하는 `IDToken.ESSENTIAL_CLAIMS`와 별개로 값 검사는 opt-in). OIDC Core §3.1.3.7 9번이 요구하는 "aud가 자신의 client_id를 포함하는지 검증"을 하지 않는 상태다. PKCE(S256)와 code-to-client 바인딩이 1차 방어선이라 즉시 악용 경로는 좁지만, 스펙 미준수이며 한 줄로 고칠 수 있다.
- **JWKS 회전/kid 불일치**는 이미 안전하다: `find_by_kid` 실패 → `ValueError` → Authlib이 강제 재조회 1회 후 재시도(`async_openid.py:71-79`), 재실패 시 예외가 `oidc.py`의 콜백 전체 `except Exception`으로 번져 로그인 실패로 안전하게 닫힌다.
- **OPA undefined 응답**은 이미 안전하다: Rego 평가 결과가 0개(undefined)면 OPA는 HTTP 200에 `result` 키 없는 바디를 돌려주고(`v1/server/server.go:1915-1927`), MINT의 `_policy()`는 그 경우 스키마 검증 실패로 `RuntimeError`를 던져 `P-CONTROL-FAIL-CLOSED` Block으로 닫힌다(`core.py:1187-1198`, `1279-1282`). `/api/health`도 `?bundles=true`로 OPA 번들 활성화 실패를 감지한다(`main.py:228`, OPA `v1/server/server.go:1321-1325`).

MINT에 주는 결론: (1) `list_tools` 전체 페이지 수집 로직 추가가 DEV-44의 가장 먼저 닫아야 할 공백이고 영향 범위가 "서버 전체 차단"이라 우선순위가 높다, (2) DEV-29 1단계는 추가 조치 불필요, (3) outputSchema 비object 방어는 유지, (4) Authlib `aud` claims_options 추가는 작은 수정으로 스펙 미준수를 없앨 수 있다, (5) JWKS/OPA 실패 경로는 이미 fail-closed로 닫혀 있어 변경 불필요.

## 고정 정보

| 항목 | 값 |
| --- | --- |
| MCP Python SDK | `/mnt/c/Users/bobysg/bob/프로젝트/ref-src/mcp-python-sdk`, commit `9972c21aa42054fb1450c5fc614761ed11847ec6` (2026-09-07), tag `v2.2.0`. 우리 pin: `full_stack_lab/gateway/requirements.txt`의 `mcp==2.2.0`. 라이선스: `mcp-python-sdk/LICENSE` |
| Authlib | `/mnt/c/Users/bobysg/bob/프로젝트/ref-src/authlib`, commit `e46e515b3a87ea63ab0606b248d75f69d83a2391` (2026-05-04), tag `v1.6.12`. 우리 pin: `Authlib==1.6.12`. 라이선스: `authlib/LICENSE` |
| OPA | `/mnt/c/Users/bobysg/bob/프로젝트/ref-src/opa`, commit `b2c26708e9d55645d7f837db495031f7e4152594` (2026-09-03), tag `v1.20.2`. MINT는 OPA를 이미지(`openpolicyagent/opa:1.20.2-static`, 루트 `AGENTS.md` 명령 참고)로만 쓰고 바이너리를 import하지 않으며, HTTP data API만 호출. 라이선스: `opa/LICENSE` |

실제로 읽은 파일(대략 행 범위): `mcp/client/client.py`(전체, 950행), `mcp/client/caching.py`(전체, 388행), `mcp/client/session.py:990-1329`, `mcp/client/_probe.py`(전체), `mcp/client/streamable_http.py:1-230, 370-430, 655-758`, `docs/client/caching.md`(전체) / `authlib/jose/rfc7519/claims.py`(전체), `authlib/oidc/core/claims.py:1-150`, `authlib/integrations/base_client/async_openid.py`(전체), `authlib/integrations/starlette_client/apps.py:1-99`, `authlib/jose/rfc7517/key_set.py`(전체), `authlib/jose/rfc7519/jwt.py`(전체) / `opa/v1/server/server.go:1299-1430, 1750-1941`. MINT 쪽: `gateway/app/upstream.py`(전체, 255행), `gateway/app/core.py:176-270, 1100-1439`, `gateway/app/oidc.py`(전체, 394행), `gateway/app/idp.py:1-33`(import 확인용).

**미확인 영역**: `git log`/`git blame`으로 DEV-29 1단계의 도입 시점을 확인하려 했으나, 이 워크트리의 `.git`이 Windows 경로(`C:/Users/.../worktrees/mcp-gateway-wbs`)를 가리켜 WSL `git`이 열지 못한다(`fatal: not a git repository`). 현재 코드 상태로만 확인했고 이력 대조는 못 했다.

## 경로 추적

### A. `tools/list` 발견→카탈로그→실행 직전 재검증 (페이지 처리)

| 단계 | 함수(경로:행) | 상태 저장소 | 실패/누락 시 결정 |
| --- | --- | --- | --- |
| 카탈로그 갱신 입구 | `core.py:183` `refresh_catalog` | `mcp_servers`, `mcp_tools` 테이블 | 서버 DISABLED/BLOCKED_SUPPLY_CHAIN·TERMINATING/RETIRED면 재조회 안 함(183-196) |
| 발견 | `core.py:176-180` `_discover` → `upstream.py:216-225` `discover()` | 없음(순수 조회) | `client.list_tools()` 단 1회, `cursor` 미전달·`listed.next_cursor` 미확인 |
| SDK 호출 | `mcp/client/client.py:924-944` `Client.list_tools` → `session.py:1278-1289` | `ClientSession._tool_output_schemas` 등 | `complete = cursor is None and result.next_cursor is None`; 2페이지 이상이면 `complete=False`로 1페이지만 반환, SDK가 자동으로 다음 페이지를 더 가져오지 않음 |
| 계약 비교 | `core.py:199-267` `refresh_catalog` 본문 | `catalog_snapshots`, `mcp_tools.approved_*` | `observed`(1페이지)에 없는 **등록된 도구**는 `enabled_missing`에 들어가 `hashes_match=False` → 계약 drift로 기록, enable 상태 유지 여부는 운영자 재승인 정책을 따름(코드 밖) |
| 실행 직전 재검증 입구 | `core.py:1201` `_call_upstream` | 없음 | 이 함수는 호출마다 새 세션을 연다(`upstream.session`) |
| 재조회 | `core.py:1229` `listed = await client.list_tools()` | 세션 로컬 `_tool_output_schemas` | 역시 1페이지만; `registered`(DB의 모든 행, enabled 불문)와 비교 |
| 통과/차단 판정 | `core.py:1236-1246` | `problem` 로컬 변수 | `tool not in observed` 이거나 **`enabled_rows`(이 서버의 활성화된 도구 전체) 중 하나라도 observed에 없으면** `problem="MCP catalog changed before execution"` → 이번 호출 자체를 차단(어느 도구를 부르든) |
| 실행 | `core.py:1304-1314` | `dispatch_state["upstream_executed"]` | `problem is None`일 때만 `client.call_tool()` 호출 |
| 결과 출력 스키마 재검증 | `mcp/client/session.py:1101-1102, 1118-1183` | `_tool_output_schemas`, `_tool_output_validators` | 호출된 도구가 observed(1페이지)에 없으면 위 단계에서 이미 차단되므로, 현재 코드 경로상 "스키마 캐시 없이 조용히 통과"는 발생하지 않음 — 차단이 먼저 일어난다(아래 "실패 결정표" 참고) |

### B. OIDC 콘솔 로그인 (Authlib 소비)

| 단계 | 함수(경로:행) | 상태 저장소 | 실패 시 결정 |
| --- | --- | --- | --- |
| 리디렉트 | `oidc.py:114-123` `login()` → Authlib `authorize_redirect` | Starlette 세션 쿠키(`state`, `nonce`) | PKCE S256 고정(`oidc.py:77,99`) |
| 콜백 수신 | `oidc.py:126-177` `callback()` | `oidc_sessions`, `oidc_bindings`, `console_sessions` | 예외는 전부 `/login?sso_error=invalid`로, 메시지는 로그/화면에 노출 안 함(174-177) |
| 토큰 교환+ID 토큰 검증 | Authlib `starlette_client/apps.py:61-99` → `base_client/async_openid.py:37-85` | 없음(순수 검증) | `claims_options={"iss":{"essential":True,"value":issuer}}`만 전달(`oidc.py:132-133`) → `aud` 값 비교 생략(아래 결정표) |
| JWKS 조회/재조회 | `async_openid.py:11-27, 62-79` | `self.server_metadata["jwks"]`(프로세스 메모리 캐시) | `kid` 불일치 → `ValueError` 1회 재조회 후 재시도(63-79) |
| 결과 소비 | `oidc.py:134-136` | — | `iss`/`sub`/`access_token` 존재만 재확인(애플리케이션 레벨 이중 점검) |
| 세션 발급 | `oidc.py:147-171` | `oidc_sessions`, `console_sessions` | `refresh_token` 없는 admin 로그인은 거부(144-146) |

### C. PAC 판정 (OPA HTTP data API)

| 단계 | 함수(경로:행) | 상태 저장소 | 실패 시 결정 |
| --- | --- | --- | --- |
| 호출 | `core.py:1187-1188` `_policy()` | 없음 | `httpx.AsyncClient(timeout=5)`(`core.py:1124-1125`), 타임아웃·연결 실패는 `httpx.HTTPError` |
| OPA 평가 | `opa/v1/server/server.go:1883-1941` `v1DataPost` | OPA in-memory store/번들 | `len(rs)==0`(undefined) → `result.Result` 미설정, HTTP 200 |
| 응답 해석 | `core.py:1188-1198` | — | `response.json().get("result")` → `None`일 수 있음; `POLICY_RESULT.is_valid(result)` 실패 시 `RuntimeError` |
| 상위 소비 | `core.py:1279-1282` `_call_upstream` | — | `except Exception: verdict = local_verdict("P-CONTROL-FAIL-CLOSED","Block", ...)` |
| 헬스체크 | `main.py:224-231` `/api/health` | — | OPA `/health?bundles=true` 확인(`opa/v1/server/server.go:1299-1325`: 번들 미활성화 시 HTTP 500) |

## 실패·경합·복구 결정표

| 조건 | 코드 동작(근거) | fail-open/closed | 미확인 |
| --- | --- | --- | --- |
| 업스트림이 `tools/list`를 2페이지 이상으로 나눠 반환, **활성화된 도구가 2페이지 이후에 있음** | `core.py:1236` `any(row["name"] not in observed for row in enabled_rows)` → `problem` 설정 → 그 서버의 **모든** `_call_upstream` 호출이 "MCP catalog changed before execution"으로 차단 | **closed, 그러나 오탐(가용성 버그)**: 실제 계약 변경이 없어도 차단됨 | 실제 OSS MCP 서버가 기본값으로 페이지를 나누는 경우는 드묾(대개 서버 구현이 명시적으로 cursor를 켜야 함) — 재현 환경에서 cursor 지원 서버로만 확인 가능 |
| 위와 동일 상황을 `refresh_catalog`에서 먼저 감지 | `core.py:246-267` `enabled_missing` 비어있지 않음 → `hashes_match=False` → `contract-drift`/`enabled-tool-missing` finding 기록 | **closed**(승인 보류로 이어짐, 운영자 재검토 필요) | 재조회 주기 동안 반복 발생 시 알림 누적 여부 미확인 |
| `call_tool` 직전 세션이 업스트림에서 끊김(세션 evict, 404) | SDK `streamable_http.py:402-409`: `session_id` 있는데 404 → `INVALID_REQUEST "Session terminated"`(자동 재접속 없음) | **closed**: 예외가 `core.py:1316-1318`에서 재throw → 상위 `_upstream_failure`가 `MCP-UPSTREAM-001` Block, `upstream_attempted=True/executed=False`로 "불확실" 표시 | 실제 업스트림 재시작 타이밍 레이스는 미재현 |
| Client 종료 시 세션 정리 | `streamable_http.py:680-758` `terminate_on_close=True`(기본) → 매 호출마다 DELETE 전송(`terminate_session:663-677`) | 실패해도 `logger.warning`만, 호출 자체엔 영향 없음 | 업스트림이 DELETE를 지원 안 하면(405) 세션이 자체 TTL로만 만료 — 그 TTL 길이는 업스트림마다 다름(미확인) |
| OPA 평가 undefined (정책 패키지 오류·경로 불일치 등) | `opa/v1/server/server.go:1915-1927` `result`無 → `core.py:1192-1193` 스키마 검증 실패 → `RuntimeError` → `P-CONTROL-FAIL-CLOSED` | **closed** | — |
| OPA 번들 로드/활성화 실패 | `opa/v1/server/server.go:1321-1325` `/health?bundles=true` 500 | `/api/health`가 즉시 감지(`main.py:228`)하지만, **판정 경로 자체(`_policy`)는 health를 선결 조건으로 쓰지 않는다** — 번들이 꺼진 상태에서도 `/v1/data/...` POST는 "그 경로가 정의되지 않음"으로만 보여 위 undefined 케이스와 동일하게 처리됨 | **closed**(두 경로 모두 결국 fail-closed로 수렴) | 번들이 "일부만" 로드 실패(예: 핵심 정책은 있는데 참조 데이터 번들만 실패)할 때 undefined가 아니라 다른 값을 반환할 가능성은 Rego 쪽 조건이라 미확인 |
| JWKS `kid` 불일치(키 회전 중) | `authlib/integrations/base_client/async_openid.py:71-79`: `ValueError` → 강제 재조회 1회 → 재시도 | 1차는 **투명 복구**, 재실패 시 **closed**(`oidc.py:172-177` 전체 catch → 로그인 실패) | 재조회 자체가 캐시 안 된 `server_metadata["jwks"]`를 즉시 갱신하므로 반복 회전 중 과도한 JWKS 호출 가능성 미확인 |
| ID 토큰 `aud` ≠ MINT `client_id`(다른 OAuth 클라이언트용 토큰) | `authlib/jose/rfc7519/claims.py:143-146` `aud_option`이 없으면 `return`(검사 생략); `oidc.py:132-133`가 `aud` 옵션을 안 줌 | **open**(값 검사 생략) — 다만 PKCE S256 + 토큰엔드포인트의 code-to-client 바인딩이 1차 방어선이라 독립적으로 바로 악용되긴 어려움(아래 "시사점" 참고) | IdP가 code를 여러 client_id에 재사용 허용하거나, resource/audience 파라미터로 한 code가 여러 audience의 토큰을 발급하는 비표준 구성일 때의 실제 위험은 미재현 |
| `AsyncOAuth2Mixin.authorize_access_token`가 `nonce` 검증 | `authlib/integrations/starlette_client/apps.py:90`: `"nonce" in state_data`일 때만 `parse_id_token` 호출, 내부에서 `IDToken.validate_nonce`(`oidc/core/claims.py:76-93`)가 세션에 저장된 nonce와 비교 | **closed**(불일치 시 `InvalidClaimError`) | — |

## upstream 시험

- **MCP SDK**: `tests/client/test_session.py`, `tests/client/test_client_caching.py`, `tests/client/test_caching.py`에 캐시·TTL·eviction 시험 존재(파일명만 확인, 본문 전체 미독). `tests/docs_src/test_caching.py`는 문서 튜토리얼 재현. **페이지 2개 이상에서 `Client.list_tools()`를 반복 호출해 전체 집합을 모으는 상위 패턴의 시험은 SDK 쪽에도 없음** — SDK는 "cursor가 있으면 호출자가 반복하라"는 계약만 제공하고, 그 반복 자체를 검증하지 않는다(`list_tools` docstring에 그 계약이 명시됨, `session.py:1278-1283`).
- **Authlib**: `tests/flask/test_oauth2/test_jwt_bearer_client_auth.py` 등은 RFC7523 client-auth용이고 OIDC `aud` 검증 전용 시험은 이번 탐색 범위(파일명 grep)에서 못 찾음(`grep 0건`은 정적 미발견이지 부재 단정 아님).
- **OPA**: `v1/server/server.go`를 호출하는 `v1/server/server_test.go` 등 서버 테스트 존재 추정(미독). undefined 처리(`len(rs)==0`)는 코드 경로 자체에서 분기점이 명확해 재현 난이도가 낮음.
- **MINT 쪽 기존 시험**: `full_stack_lab/gateway/app/acceptance.py:75-77` `list_tools()`도 커서 없이 1회 호출 — 수용시험 자체가 페이지 분할 서버를 가정하지 않는다. `tests/termination_flow.py` 등 종료 모델 시험은 이 경로와 무관.

## MINT 대조

| 우리 코드 | 참고 상위 동작 | 가져올 것 / 보류 / 이유 |
| --- | --- | --- |
| `upstream.py:216-225` `discover()`, `core.py:1229` `_call_upstream` 안 재조회 | SDK `list_tools(params=PaginatedRequestParams(cursor=...))`가 `next_cursor`를 돌려주면 호출자가 반복해야 함(`session.py:1278-1283`, 문서화된 계약) | **가져올 것**: `next_cursor`가 있으면 반복 수집하는 헬퍼(`upstream.discover`/`_call_upstream` 공용)를 추가. 현재는 1페이지 가정이 암묵적 — DEV-44와 직결 |
| `upstream.py:188-203` `mode="legacy" if protocol in HANDSHAKE_PROTOCOL_VERSIONS else "auto"` | SDK `_probe.py`의 2-RTT fallback 비용 | **이미 있음**: 추가 작업 불필요, 코드 주석과 실제 절감 효과가 일치함을 확인 |
| `core.py:1391-1399` `_guarded_result`의 비object `structured` 폐기 | SDK는 선언된 outputSchema 타입대로 검증(`session.py:1118-1183`)하고 object로 강제하지 않음 | **이미 있음, 의도적 제약**: MINT는 SDK보다 보수적으로 object만 클라이언트에 전달. 유지 |
| `oidc.py:132-133` `claims_options={"iss": ...}` | Authlib `validate_aud`는 `aud` 옵션이 있을 때만 값 비교(`jose/rfc7519/claims.py:130-163`); `parse_id_token`은 `claims_options`가 `None`일 때만 `iss`를 자동 채움 — `aud`는 어떤 경우도 자동으로 안 채움(`async_openid.py:53-54`) | **가져올 것**: `claims_options`에 `"aud": {"essential": True, "value": config["client_id"]}` 추가. 한 줄 수정, 스펙 준수 목적 |
| `oidc.py` JWKS 재조회(Authlib 내장) | `async_openid.py:71-79`의 1회 강제 재조회 | **이미 있음**(Authlib 내장 동작을 그대로 사용 중, MINT 쪽 추가 코드 불필요) |
| `core.py:1187-1198` `_policy()` | OPA undefined 응답 처리(서버 쪽) | **이미 있음**: schema 검증으로 undefined를 감지해 fail-closed. 변경 불필요 |
| `idp.py:27,230,250` `import jwt`(PyJWT) | — | **범위 정정**: 이 파일과 `agent_service.py`는 Authlib이 아니라 PyJWT를 쓴다(`jwt.decode(..., audience=AUDIENCE, issuer=ISSUER, algorithms=[ALGORITHM])`). PyJWT는 `audience=`/`issuer=` kwarg를 주면 **자동으로 값 검증**하므로 이쪽은 이미 aud 검증이 걸려 있다 — Authlib 쪽(`oidc.py`)과 다른 라이브러리/다른 상태임을 분명히 한다 |

### 백로그 연결

- **DEV-44**: `tools/list` 전체 페이지 수집이 가장 먼저 닫아야 할 공백. 영향은 "일부 도구 누락"이 아니라 "서버 전체 차단"이라는 점을 위 결정표로 구체화했다.
- **DEV-29**: 1단계(모드 고정)는 추가 검증 없이 완료로 봐도 되는 근거를 확보(SDK 소스 기준 2-RTT vs 1-RTT 비교).
- **DEV-41/43**: OIDC `aud` 미검증은 신원 판정 입력이므로 두 항목의 "자격 경계" 범위에 들어간다.

## 목표 기능 재설계 시사점

**승인·계약**: `tools/list` 페이지 수집 공백은 "계약 승인은 사람이" 불변식과 충돌하지 않지만(사람이 승인한 도구가 사라지는 게 아니라 차단되는 쪽), 운영 중 특정 업스트림이 cursor를 켜는 순간 그 서버 전체가 멈추는 급성 장애로 나타난다. 목표 기능 "엔드포인트 집행"에서 이 실패 모드를 "계약 변경"과 구분해 보여줄 필요가 있다(현재는 둘 다 `contract-drift`/`MCP catalog changed`로 동일하게 보임).

**신원·호출 권한**: Authlib `aud` 공백은 "신원은 transport의 토큰에서만 정한다" 불변식의 **구현 디테일** 문제다 — 토큰이 transport로 왔다는 사실 자체는 맞지만, 그 토큰이 "MINT를 위해 발급됐다"는 확인이 빠져 있다. 단일 발급자·PKCE 환경에서는 당장 악용로가 좁지만, 다른 목표 기능(SSO 연동 확장, 다중 클라이언트 IdP)을 설계할 때는 전제가 바뀐다.

나머지(데이터 보호·종료/폐기·하네스 운영·지표)에 대해서는 이번 분석이 바꿀 근거를 찾지 못했다: **없음**.

## 정정

- `docs/ai/BENCHMARK_*` 문서군에서 이 세 의존성을 직접 다룬 기존 문장을 찾지 못했다(정적 grep, 전체 재독 아님) — 정정할 기존 결론 없음.
- `research/llm-wiki/analysis/oss-deep/deps-presidio-gitleaks.md`와 겹치는 주장 없음(대상이 다름).

## 남은 미독 범위와 L4 재현 제안

### 미독

- MCP SDK: `mcp/client/session.py` 1-989행(초기화 핸드셰이크, `send_request` 공통 경로), `mcp/server/streamable_http.py`(서버 쪽 페이지네이션 구현 — 실제로 어떤 OSS MCP 서버가 cursor를 기본으로 켜는지는 서버 구현별로 다름, 미확인).
- Authlib: `authlib/oauth2/rfc9068/*`(토큰 자체검사용, MINT 미사용 추정), flask 전용 테스트.
- OPA: `v1/server/server_test.go`(미확인 — 존재 추정), `util/decoding` 패키지의 요청 바디 크기 한도(이번에 못 봄), 부분 번들 실패 시 Rego 평가 결과(undefined 외 다른 값 가능성).

### L4 재현 제안

1. **페이지 분할 재현**: 로컬에서 FastMCP/low-level `Server`로 `tools/list` 핸들러가 `cursor` 파라미터에 따라 2페이지(각 1개 도구)를 반환하도록 만들고, 그중 하나를 MINT에 등록·활성화한다. `refresh_catalog`와 `_call_upstream` 양쪽에서 "MCP catalog changed" 차단이 뜨는지, 1페이지에 있는 **다른** 활성 도구 호출까지 막히는지 확인한다. 정상군(페이지 1개)과 비교해 독립 효과를 본다.
2. **세션 404 경합**: 업스트림 컨테이너를 `_call_upstream`의 `list_tools()`와 `call_tool()` 사이에서 재시작시켜(sleep 삽입 또는 디버거), SDK가 "Session terminated"를 던지는지와 MINT 감사 기록이 `MCP-UPSTREAM-001`/`disposition: unknown`으로 남는지 확인.
3. **OIDC `aud` 공백 재현**: 테스트 IdP(Keycloak 등)에 클라이언트 B를 추가 등록하고, 같은 사용자로 클라이언트 B의 authorization code 흐름을 완주해 ID 토큰(aud=B)을 얻는다. 그 code를 MINT(client A)의 토큰 교환에 주입했을 때 IdP가 `invalid_grant`로 거부하는지(스펙 준수 IdP라면 거부되어야 함) 확인해, "PKCE+code 바인딩이 1차 방어선"이라는 이 보고서의 판단이 실제로 맞는지 검증한다. 거부되지 않는 IdP 구성이 있다면 `aud` 공백의 심각도를 올려야 한다.
4. **OPA undefined 경계**: 정책 패키지 경로를 일부러 틀리게 배포(Rego 문법은 맞지만 다른 package명)해 `/v1/data/mcp/authz/decision`이 undefined가 되게 하고, `_call_upstream`이 `P-CONTROL-FAIL-CLOSED`로 닫히는지, `/api/health`가 동시에 무엇을 보고하는지(번들은 떠 있으므로 `bundlesReady`는 true일 것) 비교한다 — "정책은 떠 있지만 내용이 비정상"과 "번들 자체가 안 뜸"이 서로 다른 신호로 구분되는지 확인.
