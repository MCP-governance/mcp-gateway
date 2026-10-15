
# ContextForge 훅 오케스트레이션·fail_mode·캐시 심층 분석 (DEV-47)

확인일 2026-10-15. 작업 ID `contextforge-hooks`. `_brief.md`·`oss-audit/README.md`의 L0~L4 기준을 따른다.

> **메인 검토 정정(2026-10-15, 같은 commit 재확인).** 아래 요약의 "플러그인 장애는 정책 거부로 취급하지 않아 fail-open, MINT와 정반대 기본값"은 과장이다.
> ① `tool_service.py:7531-7540`의 `except PluginError` 분기는 원격 측정에 `plugin_error`를 표시한 뒤 **`raise`로 예외를 다시 올린다** — 그 오류가 이 분기까지 오면 호출은 실패한다. "effective_allowed stays True"는 원격 측정 누적값에 대한 주석이다.
> ② `fail_on_plugin_error: false`(`plugins/config.yaml:13`)의 의미는 공식 문서 `docs/docs/using/plugins/index.md:1128-1135`에 있다: `true`면 오류를 PluginError로 올려 차단, `false`면 **플러그인 모드에 따라** — `sequential`은 위반·오류 모두 차단, `sequential`+`on_error: ignore`는 오류를 기록만 하고 진행, `transform`은 둘 다 기록하고 진행.
> 따라서 fail-open은 "오류를 무시하도록 설정된 플러그인"과 transform 모드에 한정된다. 어떤 플러그인이 그 설정인지는 `plugins/config.yaml`의 플러그인별 `mode`·`on_error`를 대조해야 하며(이번에 전수 대조하지 않음), 실제 판정은 `cpex.framework`(이 클론에 없음) 구현에 달렸다. 문서 근거는 L1이다.
> MINT 대조 결론은 "MINT는 검사기 장애를 예외 없이 차단(P-CONTROL-FAIL-CLOSED)하고, ContextForge는 플러그인별 오류 정책을 운영자가 고른다"로 읽는다.

## 1. 요약

ContextForge(`mcpgateway/`)는 FastAPI MCP 게이트웨이다. 도구/프롬프트/리소스 호출의 pre/post 훅을
실제로 실행·배선하는 오케스트레이션 엔진은 이 클론에 없다 — `mcpgateway/`도 공개 `IBM/cpex-plugins`도
아닌 **별도 PyPI 패키지 `cpex`**(`pyproject.toml:74` `"cpex>=0.1.4"`)의 `cpex.framework` 모듈이다.
ContextForge 쪽은 이 패키지를 그대로 import해 쓰는 **소비자**이고, `IBM/cpex-plugins`는 `cpex.framework`가
PyO3로 Python에 바인딩하는 **Rust 탐지기(PII/비밀/SQL/URL/인코딩반출/rate-limit)만** 담는다. 기존
BENCHMARK 문서의 "`cpex.framework` 자체는 두 클론 어디에도 없다"는 결론을 이번에도 그대로 재확인했다.

그런데도 핵심 질문인 **"훅 timeout·예외 시 최종 fail_mode"는 `cpex.framework`를 읽지 않고도 게이트웨이
쪽 호출부와 배포 설정만으로 확정**할 수 있었다. `tool_service.py`는 정책이 의도적으로 내린 거부
(`PluginViolationError`)와 플러그인/엔진 장애(`PluginError` — 크래시·오탐·timeout 포함 추정)를 **타입으로
분리**해서 처리한다. 전자는 그대로 올려 호출을 막고, 후자는 명시적으로 **"정책 거부로 취급하지 않는다
(effective_allowed stays True)"**(`tool_service.py:7531-7540`)고 주석과 함께 되어 있다. 실제 배포
설정도 `plugin_settings.fail_on_plugin_error: false`(`plugins/config.yaml:13`)로 이 fail-open 경로를
켜 둔다. MINT의 모든 통제 실패 경로(OPA·예약 저장소·프라이버시 검사 불능)가 `P-CONTROL-FAIL-CLOSED`로
차단하는 것과 정반대 기본값이다.

캐시 쪽은 PDP 결정 캐시(`unified_pdp/cache.py`)에 `invalidate()` API가 있지만, 저장소 전체(`mcpgateway/`)
와 `plugins/` 어디에서도 **이 함수를 호출하는 코드가 없다**(grep 0건) — 철회·비활성화 이벤트와 전혀
연결되지 않은 죽은 API다. 다만 unified_pdp 플러그인 자체가 기본 `disabled`(§2)라 이 결함은 지금 배포본
에서는 발현하지 않는다. CPEX Rust 플러그인은 `tool_pre_invoke` 등을 **동기 PyO3 호출**로 구현하고
`allow_threads`를 쓰지 않는다 — `asyncio.wait_for` 기반 훅 타임아웃이 스캔 도중 실제로 끼어들 수
있는지는 구조상 의문이다(추론, §4).

| 선택 기능 | 판정 | 근거 |
| --- | --- | --- |
| 도구 호출 경로(pre/post invoke 배선, PluginViolationError vs PluginError 분기) | L3 | §3 경로 추적, §4 결정표 |
| 플러그인 엔진 활성 설정·fail_mode | L3(게이트웨이 소비 계약), L2(cpex.framework 내부) | §2, §4 |
| 캐시·다중 worker(PDP 캐시, TenantPluginManager 캐시, Redis pub/sub) | L3 | §3.2, §4 |
| CPEX Rust↔Python 입출력 계약 | L3(계약), L2(Rust 내부 스캐너) | §3.3 |
| 외부(원격) MCP 플러그인 호출 실패 처리 | L1(미확인) | §4, §9 |

## 2. 고정 정보

| 저장소 | commit | 라이선스 | 비고 |
| --- | --- | --- | --- |
| [IBM/mcp-context-forge](https://github.com/IBM/mcp-context-forge) | `5735c9db7f8f50cd5a55eb7fefe83ecde00b5324` | Apache-2.0(`LICENSE`, NOTICE 없음) | — |
| [IBM/cpex-plugins](https://github.com/IBM/cpex-plugins) | `ae26938128cb438a268e7f3217603bc39b9dd18f` | Apache-2.0(`LICENSE`, 파일별 SPDX 헤더) | — |

실제로 읽은 파일(대략 범위): `mcpgateway/plugins/gateway_plugin_manager.py`(전체 448행),
`mcpgateway/plugins/__init__.py:1-334`, `mcpgateway/plugins/policy.py`(전체),
`mcpgateway/services/tool_service.py:5930-7650`(초대형 `invoke_tool` 본문), `:6042-6120`(REST 경로
pre-invoke), `:7100-7530`(MCP/A2A 경로 pre/post invoke, 예외 분기),
`mcpgateway/main.py:1690-1770`(factory 초기화), `mcpgateway/config.py:4196-4230`(`settings.plugins`
위임), `plugins/config.yaml:1-500`(mode·priority·plugin_settings 전수),
`plugins/unified_pdp/cache.py`(전체), `plugins/unified_pdp/pdp_models.py:160-180`,
`llms/plugins-llms.md:1-110`(저장소 자체 LLM용 아키텍처 문서, 데이터로 취급),
`tests/acceptance/plugins/test_cpex_contract.py`(전체), `tests/unit/mcpgateway/services/test_tool_service.py:5260-5345`,
`tests/live_gateway/plugins/make_enforce_config.py:1-40`.
`IBM/cpex-plugins`: `crates/framework_bridge/src/lib.rs`(전체),
`plugins/rust/python-package/secrets_detection/{cpex_secrets_detection/secrets_detection.py 전체, src/plugin.rs:1-120, src/config.rs:1-40}`.

## 3. 경로 추적

### 3.1 도구 호출의 pre/post 훅 배선 (`tool_service.py`, MCP streamable-http 경로)

| 단계 | 함수(경로:행) | 상태 저장소 | 실패 시 결정 |
| --- | --- | --- | --- |
| 매니저 획득 | `self._get_plugin_manager(plugin_context_id)` → `get_plugin_manager()`(`plugins/__init__.py:327-334`) → `TenantPluginManagerFactory.get_manager()`(`gateway_plugin_manager.py:129-164`) | in-process `_managers: dict[str,_CachedManager]`, TTL 30s(`gateway_plugin_manager.py:89,109`) | 캐시 미스/만료 시 `_build_manager()` 재구성(§3.2) |
| pre-invoke 훅 | `plugin_manager.invoke_hook(ToolHookType.TOOL_PRE_INVOKE, ..., violations_as_exceptions=True)`(`tool_service.py:7162-7169`) | 없음(요청 로컬) | `PluginViolationError` → `_ctl_acc.add_violation(exc, hook="pre")` 후 `raise`(`:7170-7174`, 차단) |
| 업스트림 호출 | `connect_to_streamablehttp_server(...)` (`:7205`) | — | 타임아웃·예외는 `except BaseException`(`:7120-7148`)이 잡아 도구 오류 결과로 변환(정책 차단 아님) |
| post-invoke 훅 | `plugin_manager.invoke_hook(ToolHookType.TOOL_POST_INVOKE, ...)`(`:7455-7462`) | 없음 | `PluginViolationError` → 차단(`:7463-7467`) |
| 재시도 | `post_result.retry_delay_ms > 0` → `_retry_tool_invocation(...)`(`:7492-7515`) | — | `settings.max_tool_retries` 상한 |
| 외곽 예외 처리 | `except PluginViolationError`(`:7524-7530`) / `except PluginError`(`:7531-7540`) / `except ToolTimeoutError`(`:7541-7575`) | — | §4 참조 |

### 3.2 캐시·다중 worker

- **TenantPluginManager 캐시**(`gateway_plugin_manager.py:61-72,89,129-164`): context_id(`"<team>::<tool>"`)별 in-process `_CachedManager`, TTL 30s. 만료되면 `expired.manager.shutdown()` 후 재빌드(`:143-147`). 동시 요청의 중복 빌드는 `_inflight: dict[str, asyncio.Task]`로 단일화(`:149-164`).
- **DB 바인딩**(`get_config_from_db`, `:350-406`): `ToolPluginBinding` 행을 team·tool 단위로 읽어 `PluginConfigOverride`로 변환. DB 오류는 `raise`(바인딩을 놓치지 않으려고 재빌드 자체를 실패시킴, `:370-376`).
- **Redis 모드 오버라이드**(`_apply_redis_mode_overrides`, `:239-301`): 플러그인별 `plugin:{name}:mode` 키를 MGET, Redis가 권위, in-process local map이 폴백. Redis 클라이언트/MGET 오류는 경고 로그만 남기고 override 없이 진행(`:249-261`, fail-open: Redis 없으면 override가 무시될 뿐 기본 YAML `mode`가 그대로 적용).
- **크로스 워커 무효화**(`plugins/__init__.py:59-301`): `global_toggle`/`mode_change`/`binding_change`/`team_binding_change` 4종 메시지를 Redis pub/sub(`_REDIS_INVALIDATION_CHANNEL`)로 브로드캐스트, HMAC(`jwt_secret_key` 기반) 서명(`:103-124`). **서명 없는 메시지도 경고만 남기고 수용**한다(`:151-154`, 롤링 배포 호환 명시) — HMAC이 설정된 운영 환경에서도 스푸핑 메시지를 거부하지 않는 틈.
- **PDP 결정 캐시**(`unified_pdp/cache.py:103-307`): subject+action+resource+context(타임스탬프만 제외) 해시 키, in-memory LRU(`max_entries=10_000`) + 옵션 Redis, TTL 60s(`pdp_models.py:173-175`). `invalidate()`(`:261-307`)는 필터 인자가 있어도 **항상 전체 플러시**(`:284-287`, 주석으로 "future improvement" 명시)하고, **이 함수를 호출하는 코드가 저장소 전체에 없다**(grep, `cache.invalidate\(` 0건) — 토큰 철회·서버 비활성·팀 멤버십 변경 이벤트와 전혀 연결되지 않았다. unified_pdp 자체가 `plugins/config.yaml:1259` 부근에서 기본 `disabled`이므로 기본 배포에서는 발현하지 않는다.
- **CircuitBreaker 상태**(기존 BENCHMARK 문서 재확인, 변경 없음): `_STATE: Dict[str,_ToolState] = {}` 모듈 전역, 레플리카 간 공유 없음.

### 3.3 CPEX Rust↔Python 계약(`secrets_detection` 대표 사례)

- Python은 **단순 위임 shim**이다: `SecretsDetectionPlugin.tool_pre_invoke`는 `await` 없이
  `self._core.tool_pre_invoke(payload, context, extensions)`를 그대로 반환한다
  (`cpex_secrets_detection/secrets_detection.py:23-24`) — `_core`는 PyO3 `#[pyclass]`
  `SecretsDetectionPluginCore`(Rust, `src/plugin.rs:15-28`).
- 입력 계약: `tool_pre_invoke`/`prompt_pre_fetch`는 `payload.args`, `tool_post_invoke`는
  `payload.result`, `resource_post_fetch`는 **`payload.content.text`만** 읽는다(`src/plugin.rs:31-67,90-104`).
  `content.text` 속성이 없으면(`Err`) `default_result(...)`로 **스캔 자체를 건너뛴다**(`:101-103`) — 텍스트가
  아닌 content 필드(이미지·embedded resource 등)의 비밀 정보는 이 경로에서 구조적으로 검사되지 않는다.
  `context` 매개변수는 모든 훅에서 받아서 버린다(`let _ = &context;`, `:38,58,78,98`) — 요청 간 상태 없음,
  순수 무상태 패턴 매칭.
- 출력 계약: `scan_container`가 `(count, redacted_text, findings)`를 반환, `should_block(count)`이면
  `config.redact`일 때만 `content.text`를 교체한 `modified_payload`를 만든다(`:104-115`). 차단/비차단과
  마스킹 여부가 분리된 두 축이라는 점은 기존 BENCHMARK §2.6과 일치.
- **GIL/타임아웃**: Rust `#[pymethods]` 어디에도 `py.allow_threads`가 없다(그렙, `plugin.rs` 전체) —
  스캔이 GIL을 쥔 채 동기로 끝까지 실행된다. `tool_pre_invoke`를 감싼 Python 메서드는 `async def`이지만
  내부에 `await`가 없어 이 코루틴은 단일 틱에서 블로킹 호출로 완주한다. `cpex.framework`의
  `asyncio.wait_for(..., timeout=plugin_timeout)`(`llms/plugins-llms.md:58`, 소스 미확인)가 이 호출을
  취소할 수 있는 지점은 코루틴에 `await`가 없으므로 **반환 전에는 없다** — 매우 느린 스캔(큰 payload·깊은
  재귀 디코딩)에 대해 타임아웃이 "선언됐지만 실제로 끊지는 못하고, 반환 후 늦게 감지"로 끝날 가능성이
  구조적으로 있다(추론, 실행 재현 필요, §9).

## 4. 실패·경합·복구 결정표

| 조건 | 코드 동작(근거) | fail-open/closed | 미확인 |
| --- | --- | --- | --- |
| 훅이 정책 위반 신호(`continue_processing=False`) | `PluginViolationError` → `raise`, `_ctl_acc.add_violation`(`tool_service.py:7170-7174,7273-7277,7463-7467`) | **fail-closed**(의도된 차단) | — |
| 훅 실행 중 플러그인/엔진 장애(크래시·오탐·설정오류, `PluginError`) | 외곽 `except PluginError:`가 `mark_plugin_error`만 하고 **"정책 거부로 취급하지 않는다(effective_allowed stays True)"**(`:7531-7540`), 운영 설정 `fail_on_plugin_error: false`(`plugins/config.yaml:13`) | **fail-open** | `cpex.framework.PluginManager.invoke_hook` 내부에서 예외를 `PluginError`로 감싸 삼키는 정확한 분기 로직(미확인, 외부 패키지) |
| `fail_on_plugin_error: true`로 바꾼 경우 | 동일 훅 예외가 삼켜지지 않고 그대로 `raise`되어 호출 전체가 예외로 끝남(`tests/unit/.../test_tool_service.py:5292-5342`, mock으로 재현) | 사실상 fail-closed(차단은 아니고 요청 실패) | cpex가 `PluginError`로 변환하는지 raw Exception을 그대로 올리는지는 실제 패키지 미확인 |
| 훅 timeout(설정값 `plugin_timeout: 120`, `config.yaml:12`, `main.py:1719-1725`가 `TenantPluginManagerFactory(timeout=...)`로 전달) | `asyncio.wait_for` 기반(문서상, `llms/plugins-llms.md:58`) — CPEX Rust 훅처럼 내부에 `await` 지점이 없으면 실제 취소가 반환 전에 작동하지 않을 수 있음(§3.3) | 추정 fail-open(PluginError 경로와 동일 처리로 추정) | 소스 미확인, 실행 재현 필요 |
| Redis 연결 실패(모드 오버라이드 조회) | 경고 로그, override 미적용, 기본 YAML mode로 계속(`gateway_plugin_manager.py:249-261`) | fail-open(= 안전 쪽 기본 YAML 유지, 단 운영자가 Redis로 긴급 disable한 상태라면 그 변경이 반영 안 됨) | — |
| 플러그인 바인딩 DB 조회 실패 | `raise`로 전체 manager 재구성을 실패시킴(`get_config_from_db:370-376`, 주석 "바인딩을 놓치지 않으려 재구성 자체를 실패시킴") | 재구성은 실패 → 이전 캐시된(만료 전) manager 유지(재구성 트리거 자체가 캐시 만료 시점이므로, 만료 후 재구성 실패 시 다음 `get_manager` 호출에서 다시 시도) | 재구성 실패가 반복될 때 최종적으로 어떤 manager로 요청을 처리하는지 호출 스택 전체 미확인 |
| 토큰/서버 철회 뒤 PDP 결정 캐시 | `invalidate()` 호출자 0건(§3.2) — TTL 60s 경과 전까지 과거 ALLOW가 재사용될 수 있음 | fail-open 유사(의도적 설계가 아니라 미배선) | unified_pdp가 기본 disabled라 실제 영향은 그 플러그인을 enforce로 켠 배포에서만 발현 — 실행 재현 필요 |
| 승인되지 않은(서명 없는) pub/sub 무효화 메시지 | HMAC 미일치면 거부하지만, 서명 자체가 없는 메시지는 경고만 하고 수용(`plugins/__init__.py:151-154`) | 스푸핑에 열려 있음(운영 환경에서 HMAC 키가 설정돼 있어도) | 실제 악용 가능성(네트워크 접근 전제조건) 미확인 |
| 외부(원격, MCP STDIO/HTTP) 플러그인 호출 실패 | `ExternalPlugin` 클라이언트가 `cpex.framework`에 있다고 문서가 설명(`llms/plugins-llms.md:87`)하나 이 클론에 소스 없음 | 미확인 | 완전 미확인 — 재현 필요(§9) |

## 5. upstream 시험

- `tests/acceptance/plugins/test_cpex_contract.py`(전체): `cpex` **설치 패키지의 API 표면**을 캐너리로
  검증(심볼 존재, `PluginMode` 멤버 `{SEQUENTIAL,TRANSFORM,AUDIT,CONCURRENT,FIRE_AND_FORGET,DISABLED}`,
  `OnError.IGNORE`, `HookPayloadPolicy`, `PLUGINS_ENABLED`/`PLUGINS_PLUGIN_TIMEOUT` 환경변수). **내부
  오케스트레이션 동작은 검증하지 않는다** — "cpex가 이 심볼을 갖고 있다"만 확인하는 계약 캐너리.
- `tests/unit/mcpgateway/services/test_tool_service.py:5260-5345`: `invoke_hook`을 **mock**으로 대체해
  `PluginResult`/예외를 주입하는 단위 시험. `fail_on_plugin_error=True`일 때 예외가 전파되는 것은
  재현하지만, **`False`(운영 기본값)일 때 예외가 조용히 삼켜지는 경로는 이 파일에서 직접 재현된 시험을
  찾지 못함**(정적 미발견, 검색 범위: `fail_on_plugin_error` 그렙 전체 매치 중 `False` 단정 시험 없음).
- `tests/live_gateway/plugins/*_e2e.py`, `make_enforce_config.py`: 실제 cpex 플러그인 1개만 `enforce`로
  올려 격리 E2E. `fail_on_plugin_error`를 **항상 `true`로 강제**(`make_enforce_config.py:16-17,104`) —
  즉 ContextForge 자신의 E2E도 운영 기본값(`false`, fail-open)의 플러그인 장애 경로는 의도적으로 피해서
  시험한다. 운영 기본값 경로의 실제 동작을 보여주는 upstream 시험은 **없음**(정적 미발견).
- `IBM/cpex-plugins/plugins/tests/secrets_detection/*`(`test_hook_dispatch.py`,`test_plugin_hooks.py`,
  `test_plugin_hook_results.py`,`test_field_filters.py`,`test_public_rust_api.py`,`test_manifest.py`):
  Rust 플러그인 자체의 훅 분기·필드 필터·공개 API 시험. `resource_post_fetch`가 `content.text` 부재 시
  스캔을 건너뛰는 경로, timeout/GIL 블로킹 시나리오에 대한 시험은 파일명 상 확인되지 않음(정적 미발견,
  내용 전체 미독).
- 빠진 반례: ① `plugin_timeout` 경과 중 실제 Rust 동기 스캔이 취소되는지, ② `fail_on_plugin_error=false`
  운영 설정에서 훅 예외가 실제로 조용히 넘어가는지(mock이 아닌 실제 cpex 설치로), ③ 토큰 철회 직후
  PDP 캐시 TTL 창 안에서 ALLOW가 재사용되는지, ④ Redis pub/sub 무효화 메시지의 서명 검증 우회.

## 6. MINT 대조

| 단계 | ContextForge | MINT(경로:행) | 차이 |
| --- | --- | --- | --- |
| 정책/통제 실패 시 기본 태도 | `fail_on_plugin_error: false` → 엔진 장애는 허용(§4) | `execute_call`의 모든 통제 실패가 `P-CONTROL-FAIL-CLOSED`로 차단: OPA(`core.py:1774-1778`), 호출 예약(`:1683-1689`), 입력 프라이버시 검사 불능(`:1729-1733`), 업스트림/계약 재검증 실패(`:1853-1858`) | MINT는 README 불변식("실패는 차단으로") 그대로 전부 fail-closed. ContextForge는 **정책 거부(명시적 위반)와 엔진 장애를 타입으로 분리**해 후자만 fail-open — MINT는 이 구분 자체가 없다(장애는 전부 차단) |
| 장애 관측성 | `_ctl_acc.mark_plugin_error(hook=...)`로 "정책 거부"와 "엔진 장애"를 텔레메트리에서 구분(`tool_service.py:7531-7538`) | `base_event["error"] = _root_cause(exc)` 한 필드로 기록(`core.py:1778`), decision의 `policy_id`가 `P-CONTROL-FAIL-CLOSED`로 통일 | **가져올 아이디어**: 차단 사유가 "정책이 거부"인지 "검사기가 죽어서 차단"인지 decision 레코드에서 바로 구분되면 운영자가 장애 대응과 정책 튜닝을 섞지 않을 수 있다. fail-open으로 바꾸는 것은 아님(§7) |
| 플러그인 수정 범위 제한 | `HookPayloadPolicy.writable_fields`로 훅별로 수정 가능한 페이로드 필드를 화이트리스트(`plugins/policy.py:23-43`) — 정책에 없는 훅은 `default_hook_policy=deny`로 전부 거부(주석, `:36-38`) | `classify.apply_restrictions(cls, arguments, result.get("restrictions") or {})`(`core.py:1816`)가 OPA가 돌려준 restrictions만 적용 | 구조는 유사(정책 쪼개는 쪽이 수정 권한을 가짐). ContextForge는 필드명 자체를 코드 레벨 화이트리스트로 고정해 플러그인이 임의 필드를 건드릴 수 없게 한다 — MINT는 이미 OPA가 restrictions를 내려주는 구조라 동일 효과 |
| PDP 결정 캐시·철회 연동 | `DecisionCache.invalidate()` 존재하되 호출자 0건(§3.2,§4) | MINT는 매 호출마다 `_contract()`·`registry.allowed_principals()`를 **그 호출의 트랜잭션에서 다시 읽음**(`core.py:1671-1676,1741`) — 별도 결정 캐시가 없음 | MINT는 이 실패 유형 자체가 구조적으로 없다(캐시가 없으니 무효화 배선도 필요 없음). ContextForge의 설계(캐시+TTL+무효화 API)를 들여올 이유 없음(D-41/D-44와 무관, 현재도 앞섬) |
| 캐시·다중 worker 조율 | `TenantPluginManagerFactory`(TTL 30s) + Redis pub/sub 4종 무효화 메시지 + HMAC(§3.2) | 레지스트리 런타임 문서(`registry.runtime()`)는 `REGISTER_LOCK`(asyncio.Lock, 단일 프로세스 가정)로 직렬화(`core.py:473,608`), 다중 worker 간 캐시 동기화 메커니즘 별도 없음 | DEV-29(세션/다중 worker)·DEV-45(실행 ID 최신성)와 연결. ContextForge의 Redis pub/sub + HMAC 서명 패턴은 MINT가 다중 Gateway 인스턴스로 수평 확장할 때 참고할 아이디어(단, §4의 "서명 없는 메시지도 경고만 하고 수용" 결함은 그대로 들이지 않음) |
| 검사기(탐지 규칙) 실행 모델 | CPEX Rust: 동기 PyO3, `allow_threads` 없음, GIL 보유(§3.3) | `textscan.py`: 네이티브 PCRE2 확장(`mcpgw_textscan`), 불가 시 Python `re`로 폴백, "같은 결과·느리기만"(상단 docstring) | MINT는 확장 부재 시 **동일 결과를 보장하는 순수-Python 폴백**을 명시적으로 설계. ContextForge/CPEX는 폴백이 아니라 "느릴 수 있는 동기 블로킹"이 유일 경로 — MINT 쪽 설계가 더 안전한 디그레이드를 갖춤(검증은 각자 미실행) |
| 출력 콘텐츠 타입 제한 | `secrets_detection`의 `resource_post_fetch`는 `content.text`만 검사, 다른 content 필드는 스캔 생략(§3.3) | `RESULT_CONTENT_TYPES = {"text"}`(`core.py:104`) — text 외 콘텐츠(image/audio/resource/resource_link)는 검사하지 않고 **통째로 withheld**(`core.py:101-103` 주석) | MINT는 "검사 못 하는 타입은 보내지 않음"(차단), CPEX는 "검사 못 하면 그 필드만 건너뜀"(통과) — 같은 한계(비-text 콘텐츠 미검사)에 대해 정반대 기본 태도. DEV-44(출력 계약)와 직결 |

## 7. 목표 기능 재설계 시사점

**없음(fail-open 도입 안 함)**: `fail_on_plugin_error: false`·`except PluginError`의 "장애는 허용" 설계는
MINT README의 불변식("실패는 차단으로", "분류 모르면 important")과 정면으로 반대다. 이 조사로 MINT의
fail-closed 기조를 바꿀 근거는 없다 — 오히려 ContextForge 쪽이 운영 기본값에서 보안 통제(PII/비밀/SQL
검사) 전체가 "엔진이 죽으면 조용히 통과"로 설계돼 있다는 사실을 재확인했을 뿐이다.

**가져올 구체적 아이디어(설계만, 실행 전 보강 필요)**:
1. decision 레코드에 "정책이 거부"와 "검사기가 죽어서 차단"을 구분하는 필드(DEV-46 관측 후보) —
   `_ctl_acc.mark_plugin_error` 패턴 참고, MINT는 `policy_id=P-CONTROL-FAIL-CLOSED` 하나로 묶여 있어
   운영 대시보드에서 둘을 구분하지 못한다.
2. 훅/플러그인별 쓰기 가능 필드 화이트리스트(`HookPayloadPolicy`) — MINT는 이미 OPA가 restrictions를
   내려주는 구조라 동일 효과가 있지만, poisoning/privacy/secret_scan처럼 **코드가 직접** payload를
   바꾸는 지점에 필드 화이트리스트를 코드 레벨로 명시하면 회귀 방지에 도움(저위험·저비용).
3. Redis pub/sub + HMAC 캐시 무효화 패턴은 DEV-29/45(다중 worker·실행 최신성)에서 다중 Gateway
   인스턴스를 고려할 때 참고 — 단 "서명 없는 메시지 수용" 결함은 재현하지 않는다(필요하면 전환기에도
   서명 필수로 설계).

## 8. 정정

- 기존 `docs/ai/BENCHMARK_IBM_CONTEXTFORGE.md:78,118,319-320`은 "`cpex.framework`의 실제 fail_mode
  판정 로직은 확인 못 함"이라고 세 번 적었다. **이 결론은 "cpex.framework 내부 구현"에 대해서는 여전히
  맞지만, "플러그인/엔진 장애 시 ContextForge가 최종적으로 허용/차단 어느 쪽으로 가는가"라는 실무
  질문에는 이번에 게이트웨이 소비 코드(`tool_service.py:7531-7540`)와 배포 설정(`plugins/config.yaml:13`)
  만으로 답이 나온다(fail-open)** — 내부 구현 미확인과 관측 가능한 계약 확인을 분리해야 한다는 점을
  이번 조사에서 더 분명히 했다.
- `research/llm-wiki/solutions/ibm-contextforge.md:14`는 "PII 필터는 enforce"라고 적어 설정값은
  맞지만, 그 밑 "채택 판단" 절은 fail_mode를 다루지 않는다 — 이번 작업으로 §4·§6의 fail_mode 표를
  보강했다. 기존 문장을 틀렸다고 정정하는 것이 아니라 비어 있던 부분을 채운 것이다.
- 기존 BENCHMARK 문서의 unified_pdp 캐시 관련 서술(§2.1(B), "승인 만료·철회 같은 시간 종속 판정에
  최대 60초의 stale 창을 만든다")은 **TTL 상한만 지적했지, `invalidate()`가 애초에 호출되지 않는다는
  사실은 몰랐다.** 이번에 grep으로 호출자 0건을 확인해 "60초 stale 창"이 아니라 "철회 이벤트와 전혀
  연결되지 않고 TTL로만 식는다"로 더 정확하게 교체한다.

## 9. 남은 미독 범위와 L4 재현 제안

- `cpex` PyPI 패키지(`cpex.framework.PluginManager`/`TenantPluginManager`/`ExternalPlugin`) 소스 자체는
  이번 조사 범위(ref-src 두 클론)에 없다. 설치해 읽는 것은 "읽기만 한다"는 브리프 제약을 넘어서는 별도
  결정(새 소스 확보)이 필요하다 — 이 문서는 그 결정을 내리지 않고 공백으로 남긴다.
- 외부(원격 MCP) 플러그인 호출 실패 처리(§4 마지막 행)는 완전 미확인. `llms/plugins-llms.md:86-101`의
  문서 서술만 있고 클라이언트 코드가 어느 저장소에도 없다.
- L4 재현 제안(실행 환경: 격리된 ContextForge+cpex 설치, Redis, 테스트 MCP 업스트림 1개):
  1. **훅 timeout 중단성**: `plugin_timeout`을 1~2s로 낮추고 `time.sleep()`을 하는 동기 네이티브(Rust나
     C 확장) 훅을 붙여, 실제로 timeout 시각에 호출이 끊기는지 반환 후 사후 감지되는지 측정(§3.3 추론 검증).
  2. **`fail_on_plugin_error=false` 운영 경로 실측**: 정상 요청·훅에서 의도적 `RuntimeError`를 던지는
     테스트 플러그인으로 실제 설치본에서 호출이 통과(fail-open)하는지, decision에 무엇이 남는지 확인.
  3. **PDP 캐시·철회 경쟁**: unified_pdp를 enforce로 켜고 ALLOW 캐시를 만든 뒤 같은 윈도(60s) 안에
     토큰을 철회, 동일 subject/action/resource/context로 재호출해 캐시된 ALLOW가 나오는지 확인.
  4. **Redis pub/sub 서명 우회**: HMAC 키 설정 상태에서 서명 없는 무효화 메시지를 직접 publish해 워커가
     수용하는지 확인(§4 마지막 결함).
  이 네 가지는 모두 **미실행**이며, 이번 문서는 정적 코드·설정·테스트 파일 근거만 쓴다.
