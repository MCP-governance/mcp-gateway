# MCPX(Lunar) + Cisco MCP Scanner 심층 분석 — DEV-47 / mcpx-cisco-scanner

## 1. 요약

두 계층을 봤다. (A) **MCPX** — 여러 MCP 서버를 하나의 MCP 엔드포인트로 집계하는 Node.js 게이트웨이(신원 식별 → 도구 ACL → 업스트림 세션 → 결과/감사). (B) **Cisco MCP Scanner** — MCP 도구/프롬프트/리소스 정의와 서버 연결을 정적·행동·API 기반으로 판정하는 Python 스캐너(런타임 집행기가 아니라 독립 실행 분석기).

판정(L3, 선택 기능 기준):
- MCPX 신원·ACL·세션: **L3**. 입구(`downstream-transports.ts`)→신원 추출(`metadata.ts`)→ACL(`permissions.ts`)→업스트림 세션 재사용(`upstream-handler.ts`)→감사(`audit-log-service.ts`)까지 코드로 연결했고 실패/경합 지점을 특정했다.
- MCPX outbound 통제·secret: **L2**. mcpx(MIT) 안에는 egress 통제가 없음을 소스로 확인(정적 미발견이 아니라 "없다"는 자기 주석 근거). outbound 통제는 별도 라이선스의 Lunar Proxy 몫이라 이 조사 범위 밖이다.
- Cisco Scanner 입력/엔진/오류: **L3**. `scanner.py`의 호출 경로, 분석기별 외부 전송 여부, 예외 시 상태 전이를 코드로 확인했다.

MINT에 줄 결론(상세는 6·7절):
1. MCPX의 `x-lunar-consumer-tag`는 **서명되지 않은 자기 신고 헤더**다. transport 토큰 검증과는 다른 범주이며, MINT의 "신원은 transport 토큰에서만" 불변식을 어기는 설계를 그대로 가져오면 안 된다.
2. MCPX는 업스트림 MCP 서버 연결을 **서버 이름당 하나, 모든 소비자가 공유**하는 모델이다. MINT가 이미 채택하지 않은 모델의 구체적 반례로 쓴다(세션 결속 비교 문서와 연결).
3. Cisco Scanner는 분석기 예외를 "탐지 결과 없음"과 **구분되지 않는 빈 findings**로 반환할 수 있어, 소비자가 `status`/`analyzer_errors`를 같이 보지 않으면 timeout이 "정상" 스캔으로 보인다. MINT가 검사기 결과를 소비할 때 이 함정을 그대로 두면 안 된다(DEV-02/46).
4. Cisco Scanner의 API/LLM/VirusTotal 분석기는 도구 설명·프롬프트 본문·리소스 내용을 외부 SaaS(Cisco AI Defense API, LiteLLM이 가리키는 LLM 제공자, VirusTotal)로 보낸다. 모두 키 설정 여부로 켜지는 옵트인이라 기본값은 오프라인(YARA/Readiness/PromptDefense)이다. DEV-41의 "목적지 제한" 설계에 참고할 옵트인 경계다.

## 2. 고정 정보

| 항목 | 값 |
| --- | --- |
| MCPX 저장소 | `TheLunarCompany/lunar`, 로컬 경로 `ref-src/lunar-mcpx` |
| MCPX HEAD | `fb93c38bf10173a74b12170be48832645dbed189` (2026-10-15) |
| MCPX 하위 라이선스 | 루트 `LICENSE`(MIT, Lunar.dev 2023) / `mcpx/LICENSE.MD`(MIT, Lunar.dev 2025, 독립 사본) / `proxy/LICENSE.md`(**MIT 아님** — "Lunar Software License Agreement", 평가판 전용 상용 계약) |
| Cisco MCP Scanner 저장소 | `cisco-ai-defense/mcp-scanner`, 로컬 경로 `ref-src/cisco-mcp-scanner` |
| Cisco Scanner HEAD / 태그 | `5d147dc7e3635606e41104112fa297b45444b05c`, 태그 `v4.8.6` (2026-10-07) |
| Cisco Scanner 라이선스 | 루트 `LICENSE` 1개, Apache-2.0 (각 소스 파일 헤더에도 SPDX 명시 확인) |
| 기존 위키 문서 | `research/llm-wiki/solutions/lunar-mcpx.md` — 커밋 `7193eab`에서 `upstream-handler.ts:126-494`만 읽은 상태였음. 이번에 같은 파일을 HEAD `fb93c38`에서 전체 재확인(아래 8절 정정) |

읽은 파일(대략 행 범위):
- MCPX: `server/mcp-gateway.ts`(1-856), `server/metadata.ts`(1-125), `server/downstream-transports.ts`(1-738), `server/auth.ts`(1-59), `server/auth-mcpx.ts`(1-52), `server/identity.ts`(1-27), `services/permissions.ts`(1-256), `services/capability-resolver.ts`(1-464), `services/upstream-handler.ts`(전체 1556행), `services/audit-log/audit-log-service.ts`(1-124), `services/target-server-connection-factory.ts`(1-284), `command-policy.ts`(1-77), 루트/`mcpx`/`proxy`의 LICENSE 파일, 루트·`proxy` README 발췌.
- Cisco Scanner: `mcp_scanner_entry.py`(전체), `mcpscanner/core/scanner.py`(1-1574, 4058행 중 앞부분. 나머지 2484행 — 리모트 서버 연결 루프·CLI 경로 — 미독), `core/analyzers/api_analyzer.py`(1-150), `core/analyzers/llm_analyzer.py`(1-150), `core/analyzers/readiness/llm_judge.py`(1-80), `config/constants.py`(타임아웃 상수 발췌), `config/config.py`(옵트인 플래그 발췌), 디렉터리 트리 전체 목록.
- MINT 비교: `gateway/app/poisoning.py`(274-303 발췌 + 전체 함수 목록), `gateway/app/textscan.py`(함수 목록), `gateway/app/main.py`(160-200, `caller`/`admin_caller`), `supply_chain/intake_worker.py`(1-60 + 함수 목록).

## 3. 경로 추적

### 3.1 MCPX — 신원 → ACL → 업스트림 → 감사

| 단계 | 함수(경로:행) | 상태 저장소 | 실패 시 결정 |
| --- | --- | --- | --- |
| 입구(세션 생성/재사용) | `registerTransportRoutes` POST 핸들러 `mcp-gateway-server/downstream-transports.ts:213-309` | 세션 맵(`services/sessions.ts`, 파일 내 미독), 선택적 Hub(클라우드) 영속화 | 세션 없음+initialize 아님 → `tryRestoreStreamableSession`으로 Hub에서 복원 시도, 실패 시 404(`respondSessionNotFound:528`) → 클라이언트가 재초기화 |
| 신원 추출 | `extractMetadata` `server/metadata.ts:50-71` | 없음(요청마다 헤더 파싱) | `x-lunar-consumer-tag`/`authorization` 헤더가 없으면 `consumerTag=undefined`, `clientName`은 MCP `initialize` 바디의 `clientInfo.name`에서 옴(둘 다 클라이언트가 보낸 값, 서명 검증 없음) |
| 세션 메타데이터 결합 | `mergeMetadata` `downstream-transports.ts:467-512` | 세션 객체의 `metadata` 필드 | 재연결 시 `incoming.consumerTag ?? current.consumerTag` — 새 요청이 헤더를 생략하면 **이전 세션의 consumerTag를 그대로 승계** |
| ACL 판정 | `PermissionManager.hasPermission→resolveConsumer→evaluatePermission` `services/permissions.ts:169-228` | 설정 로드 시 구성된 `Map<string, ConsumerLevelPermission>`(재배포 전까지 불변) | 알려지지 않은 `consumerTag`/`clientName`은 `defaultConsumer`로 폴백(`permissions.ts:201-204`). 매칭 우선순위는 `consumerTag > clientName > default`(주석 `permissions.ts:185-186`), 둘 다 **문자열 일치**일 뿐 암호적 바인딩 없음 |
| 도구 가시성/해석 | `CapabilityResolver.resolve` `services/capability-resolver.ts:279-291`, `.allows` `:343-355` | 레지스트리 변경 시 재계산되는 인메모리 `_activeByKind` 맵 | 이름 미존재 → `unresolved`(`:294-308`, "unknown" 또는 "server-inactive"). 권한 거부 → `"permission-denied"`. 내부(internal) 출처 capability는 PermissionManager를 **건너뛴다**(`:287`) |
| 실행(업스트림 호출) | `executeUpstreamToolCall` `server/mcp-gateway.ts:502-597` → `UpstreamHandler.callTool→proxyToUpstream→requireConnectedClient` `services/upstream-handler.ts:487-531` | `_clientsByService: Map<string, TargetClient>`(**서버 이름당 1개, 모든 세션·모든 consumerTag가 공유**, `upstream-handler.ts:129`) | 토큰 만료(OAuth) → `TokenExpiredError`를 에이전트에 그대로 전달(`mcp-gateway.ts:531-537`); 그 외 전송 오류는 그대로 throw |
| 호출자 권한 전달 | `withCallerAuthorization` `server/mcp-gateway.ts:850-855`, 호출부 `:152-156`·`:528` | 없음(요청별 `_meta`) | 다운스트림이 보낸 `Authorization` 헤더 값을 **업스트림 MCP 호출의 `_meta.authorization`에 그대로 포워드**. 업스트림이 이를 신뢰하면 호출자 자격이 그대로 전달되는 셈이지만, 실제 업스트림 인증은 `oauthConnectionHandler`가 서버 단위로 별도 관리(개별 호출자 토큰과 무관) |
| 결과/지표 | `measureNonFailable` 블록 `mcp-gateway.ts:523-556` | 없음(즉시 기록) | 성공/실패 모두 `systemStateTracker.recordToolCall`·`metricRecorder`·`hubService.recordToolCall` 호출(실패도 집계됨) |
| 감사 | `services.auditLog.log(toolUsedEvent)` `mcp-gateway.ts:545-554` → `AuditLogService.log` `services/audit-log/audit-log-service.ts:79-89` | 인메모리 `buffer: AuditLog[]`, 주기적으로 `persistence.persist`(`:91-108`, 기본 주기 `AUDIT_LOG_FLUSH_INTERVAL_IN_SEC`) | `env.ENABLE_AUDIT_LOG`가 거짓이면 **버퍼에 쌓지도 않음**(`:86-88`, 감사 끔이 기본값일 가능성 — 정확한 기본값은 `env.ts` 미독, 미확인) |

### 3.2 MCPX — 업스트림 연결/secret 주입

| 단계 | 함수(경로:행) | 상태 저장소 | 실패 시 결정 |
| --- | --- | --- | --- |
| stdio 연결 | `TargetServerConnectionFactory.createStdioConnection` `services/target-server-connection-factory.ts:75-174` | 없음(연결마다 신규 프로세스) | `ENABLE_STDIO_MCP_SERVERS`/`DIND_ENABLED` 플래그 끄짐 → `FailedToConnectToTargetServer`로 즉시 거부(`:81-93`). `STDIO_INHERIT_PROCESS_ENV=true`이면 MCPX 프로세스의 **전체 환경변수**를 자식 MCP 서버에 상속(`:147-154`, `inheritedProcessEnv:234-241`) |
| remote 연결 헤더/secret | `resolveRemoteHeaders` `target-server-connection-factory.ts:257-283` | 카탈로그의 `privateHeaders`(워터마크), `TargetServerEnvSource`가 해석하는 환경변수 | 사용자 헤더 값에 미해석 환경변수가 남으면 `PendingInputError`(미확인 변수 목록과 함께) — `isSpace`(워크스페이스 모드)가 아니면 연결을 막음(`:272-273`) |
| 자격 범위 | (위와 동일 경로) | — | 주입되는 secret은 **서버(타깃) 단위로 1쌍**이며 호출자별로 분리되지 않음 — MCPX 전체를 통해 그 서버를 호출하는 모든 consumerTag가 같은 upstream 자격을 공유 |

### 3.3 Cisco MCP Scanner — 입력 → 엔진 → 판정

| 단계 | 함수(경로:행) | 상태 저장소 | 실패 시 결정 |
| --- | --- | --- | --- |
| 입력 선택 | `Scanner.__init__` `core/scanner.py:144-221` — 원격 서버 연결(`scan_remote_server_tool(s)`), 정적 설정 파일(`config_parser.MCPConfigScanner`, 미독), 직접 콘텐츠(`analyze(name=..., description=...)`) 세 경로가 같은 `Scanner` 인스턴스를 공유 | 없음(요청마다 신규 분석) | — |
| 분석기 활성화 게이트 | `Scanner.__init__:158-200`, `_validate_analyzer_requirements:230-311` | `Config` 객체(불변, 생성 시 1회 결정) | API/LLM/Behavioral/VirusTotal/Meta는 각각 `api_key`/`llm_provider_api_key`(or Bedrock)/`virustotal_api_key`가 없으면 **인스턴스 자체가 None** → 명시적으로 `_validate_analyzer_requirements`를 거치는 호출 경로는 `ValueError`로 거부하지만, `_analyze_tool`처럼 `if ... and self._api_analyzer:`로만 가드하는 경로는 **조용히 스킵**(에러 기록 없음, `:1342`, `:1393-1417`) |
| YARA(정적, 로컬) | `_analyze_tool` 내 YARA 분기 `core/scanner.py:1358-1391` → `YaraAnalyzer.analyze`(파일 미독, 외부 전송 없음 — 로컬 규칙 매칭) | 없음 | 예외 시 `_record_analyzer_error`(`:1370`, `:1390`)만 기록, 해당 콘텐츠의 YARA 결과는 빈 채로 다음 분석기로 진행 |
| API(Cisco AI Defense, 외부) | `_analyze_tool` API 분기 `:1342-1356` → `ApiAnalyzer.analyze` `core/analyzers/api_analyzer.py:107-150+` | 없음 | `httpx.AsyncClient().post(api_url, ..., timeout=self._DEFAULT_TIMEOUT)`(기본 30초, `config/constants.py:215`). 타임아웃/5xx 등 예외는 `analyze()`가 그대로 raise(docstring `:120-121`), 호출부가 `except Exception as e: self._record_analyzer_error(...)`로 흡수(`:1353-1356`) → **findings는 빈 리스트, 에러는 `analyzer_errors`에만** |
| LLM(LiteLLM 경유, 외부 또는 자체 호스팅) | `_analyze_tool` LLM 분기 `:1393-1413` → `LLMAnalyzer.__init__` `core/analyzers/llm_analyzer.py:66-130` | 없음 | 비-Bedrock 제공자는 API 키 필수(`:87-93`), `llm_base_url`로 호환 엔드포인트 재지정 가능(외부 전송 범위를 바꿀 수 있는 유일한 손잡이, 코드상 확인, 운영 시 실제 적용은 미확인) |
| LLM 판정(readiness, 기본 꺼짐) | `ReadinessLLMJudge` 클래스 docstring `core/analyzers/readiness/llm_judge.py:17-32` | 없음 | "DISABLED BY DEFAULT"를 모듈 docstring과 클래스 docstring에서 2중 명시(`:20-22`, `:68-69`) — `MCP_SCANNER_LLM_API_KEY` 미설정 시 비활성 |
| 도구 단위 결과 합성 | `_analysis_outcome` `core/scanner.py:1276-1297` | — | 성공한 분석기가 1개 이상이면 `status="completed"`(에러 없음) 또는 `"partial"`(일부 에러), **전부 실패해도 findings가 쌓여 있으면 그 findings는 유지**되고 `status="failed"`만 떨어짐(`:1295-1297`) — 소비자가 findings만 보면 부분 실패를 못 알아챈다 |
| Meta(LLM 2차 판정, 오탐 필터) | `_meta_analyze_one_tool` `core/scanner.py:782-831` | 없음 | 예외 시 원본 `result`를 findings 그대로 반환(`:825-831`) — meta 실패가 1차 findings를 삭제하지 않음(fail-closed 쪽으로 안전) |

## 4. 실패·경합·복구 결정표

| 조건 | 코드 동작(근거) | fail-open/closed | 미확인 |
| --- | --- | --- | --- |
| MCPX: consumerTag 헤더 위조(다른 사용자 태그 자가 기재) | `extractMetadata`는 헤더 값을 그대로 신뢰(`metadata.ts:54`), `resolveConsumer`는 문자열 일치만 수행(`permissions.ts:187-205`) — 서명·세션 바인딩 검증 없음 | **fail-open**(검증 자체가 없어 스푸핑이 그냥 통과) | 배포 가이드가 프런트 프록시에서 헤더를 강제로 재기록하는지는 미확인(코드상 MCPX 자체는 안 함) |
| MCPX: 세션 재연결 시 consumerTag 생략 | `mergeMetadata`가 이전 값을 승계(`downstream-transports.ts:494`) | 세션ID가 `randomUUID()`라 추측 곤란하지만, 같은 세션ID를 쥔 쪽은 자동으로 이전 신원을 이어받음 | 세션ID 노출·재사용 경로(로그, 프록시 캐시)는 미확인 |
| MCPX: PermissionManager 설정 미초기화 상태에서 호출 | `hasPermission`이 `throw new Error("PermissionManager is not initialized")`(`permissions.ts:176-178`) | **fail-closed**(예외로 요청 자체가 끊김) | 이 예외가 MCP 에러 응답으로 어떻게 변환되는지(500 vs 연결 종료)는 상위 핸들러 미독 |
| MCPX: 업스트림 OAuth 토큰 만료, 재인증 실패 | `executeWithAuthRetry`→`handleAuthFailure`→`runAuthRecovery`가 실패하면 `pending-auth`로 전환하고 `TokenExpiredError`를 에이전트에 전달(`upstream-handler.ts:1314-1324`, `:1392-1420`) | 호출 거부(사실상 closed), 단 재시도·재연결 큐는 계속 살아 있음 | — |
| MCPX: 도구 호출 캐시 적중 중 동일 키 재요청(진행 중 호출) | `getCachedToolCallEntry`가 `pending` 상태 promise를 공유 반환(`mcp-gateway.ts:276-285`) — 중복 업스트림 호출 방지 | 의도된 동작(경쟁 방지) | 캐시는 `ENABLE_TOOL_CALL_CACHE` 설정과 진행-토큰 존재가 모두 필요(`:640-651`) — 기본 활성 여부 미확인 |
| MCPX: 감사 로그 flush 중 `persistence.persist` 실패 | `flush()`가 버퍼를 **먼저 비우고** `persist`를 호출, 실패 시 로그만 남기고 throw(`audit-log-service.ts:31-49`); 주기 타이머는 그 예외를 `catch`해서 경고만 남김(`:98-104`) | **fail-open에 가까운 데이터 손실** — persist 실패 시 그 배치의 이벤트는 버퍼에도 디스크에도 남지 않고 소실, 서비스는 계속 동작 | 재시도/재큐잉 로직 없음(코드상 확인) |
| MCPX: `ENABLE_AUDIT_LOG` 꺼짐 | `log()`가 아무 것도 버퍼에 넣지 않음(`:86-88`) | 설계상 옵트인 — 기본값이 켜짐/꺼짐인지는 `env.ts` 미독으로 미확인 | 기본값 |
| MCPX: stdio 자식 프로세스에 `STDIO_INHERIT_PROCESS_ENV=true` | 호스트 프로세스 전체 env를 자식에 상속(`target-server-connection-factory.ts:147-154`) | **fail-open형 비밀 노출 경로**(MCPX 프로세스가 쥔 비밀이 모든 stdio MCP 자식에 전달됨) | 기본값이 꺼짐인지 `env.ts` 미독으로 미확인 — 꺼짐이 기본이라면 이 항목은 옵트인 위험으로 하향 조정 필요 |
| Cisco Scanner: API/LLM 분석기 HTTP 타임아웃(30초 기본) | 예외가 `analyze()`에서 raise되고 `_analyze_tool`의 `except Exception`이 흡수(`scanner.py:1353-1356`, `:1410-1413`) → 해당 분석기는 `findings=[]`, `analyzer_errors`에 1건 추가, `status`는 다른 분석기 성공 여부에 따라 `partial`(에러 섞임) 또는 `failed`(전부 에러) | **findings 관점에서는 fail-open**(그 콘텐츠에 대해 "탐지 없음"과 동일한 빈 리스트), `status` 필드를 보면 구분 가능 — **소비자가 `status`를 무시하면 사실상 fail-open** | 재시도 로직 유무는 `_analyze_tool` 수준에서는 없음(상위 CLI/API 레이어의 재시도는 2484행 미독 구간에 있을 수 있어 미확인 |
| Cisco Scanner: 분석기 요청했지만 키 미설정(`_analyze_tool` 경로) | `self._llm_analyzer`가 `None`이면 `elif ... and not self._llm_analyzer: logger.warning(...)`만 남기고 **`analyzer_errors`에는 기록하지 않음**(`:1414-1417`) | 조용한 스킵 — `_validate_analyzer_requirements`를 거치지 않는 호출 경로에서는 "요청한 분석기가 실행되지 않았다"는 사실이 findings/analyzer_errors 어디에도 구조화되어 남지 않음(로그에만) | 어떤 공개 메서드가 검증을 거치고 어떤 경로가 `_analyze_tool`을 직접 타는지는 2484행 미독 구간(리모트 스캔 루프) 확인 필요 |
| Cisco Scanner: prompt/resource 본문 크기 초과 | `CoverageLimitExceeded`로 명시적 예외 클래스 발생, `excerpt`만 분석에 투입하고 완전 분석이 아님을 결과에 표시(`scanner.py:101-121`, `:433-451`) | **fail-closed 설계**(불완전함을 숫자로 남김) — 세 가지 중 유일하게 "모른다"를 구조화해서 보존 | — |
| Cisco Scanner: meta(2차 LLM 필터) 예외 | 원본 findings를 그대로 유지, `meta_filtered_findings=[]`로 리셋(`:825-831` 등 4곳 동일 패턴) | **fail-closed**(필터링 실패가 findings를 지우지 않음) | — |

## 5. upstream 시험

- MCPX: `mcpx/packages/mcpx-server/it/`에 `oauth.it.test.ts`, `hub.it.test.ts`, `mock-oauth-servers.ts` 등 통합 시험이 있고(파일 목록만 확인, 본문 미독), `src/` 내 `*.test.ts`가 다수(permissions, capability-resolver, capability-scope, audit-log-diff/service, env-resolver, dns-cache, hub-backoff, tool-call-cache 등 — 파일 존재만 확인). 현재 조사에서 이 테스트들의 **본문은 읽지 않았다**(미확인). `permissions.test.ts`·`capability-resolver.test.ts`가 존재하므로 consumerTag 스푸핑처럼 이번에 발견한 반례가 이미 커버됐는지는 그 파일을 읽어야 안다(미실행).
- Cisco Scanner: `tests/behavioral/`, `tests/readiness/`, `tests/static_analysis/`, `tests/threat_files/cross_file_malicious/` 디렉터리 존재(목록만 확인). `evals/behavioral-analysis/data/`에 위협 카테고리별(`data-exfiltration`, `prompt-injection`, `tool-poisoning` 등) 샘플이 있다(목록만 확인, 라벨된 정상/공격 분리 여부·반례 커버리지는 미독).
- 두 프로젝트 모두 "타임아웃/키-미설정 시 findings가 비어 보이는" 이번 발견에 대응하는 명시적 반례 테스트가 있는지는 **확인하지 못했다**(검색만 했고 본문은 안 읽음).

## 6. MINT 대조

| 축 | MCPX / Cisco Scanner | MINT 심볼(경로) | 차이 |
| --- | --- | --- | --- |
| 신원 | MCPX: `x-lunar-consumer-tag` 헤더(서명 없음, `metadata.ts:54`) | `caller()`/`admin_caller()` `gateway/app/main.py:172-192` → `authenticated_user(authorization)` — 서명된 토큰 검증, 바디/헤더의 자가 신고 값은 쓰지 않음 | MINT가 이미 더 엄격하다. **가져오지 않음**: consumerTag류 자가 신고 헤더를 ACL 키로 쓰는 패턴. 이유: MINT 불변식("신원은 transport 토큰에서만") 직접 위반 |
| 업스트림 세션 | 서버 이름당 1개 공유 `TargetClient`(`upstream-handler.ts:129`, `:516-531`) | (세션 결속 설계는 별도 문서 `analysis/upstream-session-reuse/README.md`에서 다룸, 이번 조사에서 코드 재확인은 안 함) | 기존 위키 문서가 이미 이 반례를 인용 중. 이번 조사로 HEAD가 `fb93c38`로 올라가도 **같은 구조가 유지됨**을 재확인(8절 정정 참고) |
| secret 주입 | 서버(타깃) 단위 헤더/env 1쌍(`target-server-connection-factory.ts:257-283`), `STDIO_INHERIT_PROCESS_ENV` 옵션은 호스트 전체 env 상속 가능 | 업스트림 자격 주입 경로(레지스트리/`upstream.py` 등, 이번 조사에서 코드 재독은 안 함) | **가져오지 않음**: 프로세스 전체 env를 자식 MCP 서버에 상속하는 옵션. MINT는 호출별로 필요한 자격만 좁혀 넣는 방향이 이미 맞다(재확인 필요 시 `upstream.py` 별도 조사) |
| outbound(egress) 통제 | mcpx(MIT) 안에는 없음(`command-policy.ts:1-8` 자기 주석: "harm reduction, NOT a security boundary"), 통제는 별도 라이선스의 Lunar Proxy 몫 | DEV-41(동적 목적지/인자/egress) | **참고만**: "집계 게이트웨이와 egress 통제를 별도 컴포넌트·별도 라이선스로 분리"한 선례. MINT는 Gateway 자신이 집행 경로이므로 이 분리를 그대로 가져올 필요는 없지만, "집계 로직에 egress 통제를 넣지 않고 공개했다"는 선택 자체는 DEV-41 설계 시 비교 대상으로만 기록 |
| 감사 원장 | 인메모리 버퍼 + 주기 flush, persist 실패 시 **이벤트 소실**(`audit-log-service.ts:31-49`) | append-only 원장(불변식, 구현 경로는 별도 조사) | **가져오지 않음**: "버퍼 먼저 비우고 persist" 순서. MINT의 append-only 불변식과 정반대 실패 모드이며, 구체적인 반례로 DEV-29(감사 관련 백로그가 있다면)·불변식 문서에 인용할 수 있다 |
| 도입/공급망 정적 검사 | Cisco Scanner: YARA + 커스텀 tree-sitter 기반 taint/dataflow/call-graph(`core/static_analysis/`, 디렉터리만 확인) + 옵트인 API/LLM/VirusTotal | `supply_chain/intake_worker.py` — Trivy(SCA)+Semgrep(SAST)+Gitleaks(비밀) 조합, 코드 미실행, 격리 컨테이너, `CLONE_TIMEOUT`/`SCAN_TIMEOUT`(`intake_worker.py:34-37`) | MINT는 **검증된 OSS 스캐너를 그대로 래핑**(자체 정적 분석 엔진을 새로 안 만듦)하는 전략이 맞다. Cisco Scanner의 커스텀 call-graph/taint 엔진은 더 깊지만 유지보수 비용이 크다 — **가져오지 않음**(자체 taint 엔진 신규 개발), 참고만: tree-sitter 기반 JS/Py 교차 파일 분석이라는 "더 깊은 단계"가 존재한다는 사실 자체는 DEV-02 향후 범위 후보로 기록 |
| 도구 설명/오염 탐지 | Cisco Scanner: YARA(로컬 규칙) + LLM(외부, 옵트인) + API(Cisco 클라우드, 옵트인) 3중, 결과를 findings 리스트로 합성(`scanner.py:1319-1489`) | `poisoning.py:299-303` `findings()` — 정규식 기반 지시문·override·base64 스머글링 탐지(`:284-296`), `textscan.py` — 유니코드 혼동 문자 포함 자체 정규식 엔진(`Scanner` 클래스) | MINT는 **로컬·결정적 규칙만**(외부 전송 없음)이고 Cisco는 로컬+클라우드 하이브리드다. **가져오지 않음**: 외부 LLM/API로 도구 설명을 보내는 기본 경로. **참고**: Cisco의 "분석기별 성공/실패를 `status`+`analyzer_errors`로 분리해 보존"하는 결과 스키마는 DEV-46(검사 결과 신뢰성 보고)에 참고할 만하다 — 다만 이번 조사에서 본 바로는 **그 스키마조차 소비자가 안 보면 fail-open**이라는 한계가 있으므로 그대로 베끼기보다 "findings 없음"과 "분석 실패"를 **타입 수준에서 구분**하는 더 엄격한 설계가 필요 |

## 7. 목표 기능 재설계 시사점

- **DEV-41(목적지/egress 제한)**: MCPX 자체에는 참고할 구현이 없다(코드로 없음을 확인). Lunar Proxy는 라이선스가 달라 코드 분석 대상이 아니다. 시사점 없음 — 기존 RV-01 결론(정적 허용 범위 문제, 제품 수정/우회 재현 미실행)을 그대로 유지.
- **DEV-46(검사 결과의 독립 효과/신뢰성 보고)**: Cisco Scanner의 `status`(completed/partial/failed) + `analyzer_errors` 분리 스키마는 "탐지 없음"과 "분석 실패"를 구조적으로 나누려는 시도이지만, 이번 조사로 **그 분리가 소비자 쪽 구현에 의존**한다는 한계를 확인했다(findings만 보면 무력화됨). MINT가 검사 파이프라인의 결과를 리포트할 때는 "분석기 전부 성공 + 탐지 0건"과 "분석기 일부/전부 실패"를 **같은 필드에서 구분 불가능하게 섞지 말아야** 한다는 구체적 근거가 추가됐다.
- **DEV-02(계약 변경·오염 탐지 코퍼스)**: Cisco Scanner의 공격 카테고리 디렉터리명(`tool-poisoning`, `data-exfiltration`, `prompt-injection`, `defense-evasion`, `backdoor`, `template-injection`, `goal-manipulation`, `general-description-code-mismatch`, `resource-exhaustion`, `unauthorized-*`)은 기존 DEV-02 코퍼스의 위협 분류와 겹치는지 대조할 값은 있으나, 본문(라벨·샘플)을 읽지 않아 **코퍼스 자체를 가져올 수 있는지는 미확인**이다. 다음 조사에서 `evals/behavioral-analysis/data/*/`의 샘플 수·라이선스를 확인할 것.
- 그 외 목표 기능(도입 검증, 승인·계약, 신원·호출 권한, 데이터 보호, 엔드포인트 집행, 감사, 하네스 운영, 지표)에 대해 **이번 분석이 기존 설계를 바꿔야 한다는 근거는 없음**. MCPX의 신원/세션 패턴은 전부 MINT가 이미 피해간 반례로 쓰기 좋고, Cisco Scanner는 "검사기"이지 "집행기"가 아니라서 MINT의 집행 경로(core.py 등)와 직접 비교할 대상이 아니다.

## 8. 정정

- `research/llm-wiki/solutions/lunar-mcpx.md:13-15`의 "대상 서버 연결 처리" 절은 커밋 `7193eab`에서 `upstream-handler.ts:126-494`만 읽고 "오래 사는 클라이언트 하나를 모든 소비자의 `callTool`이 공유한다"고 적었다. 이번에 HEAD `fb93c38`(커밋 753개 이상 차이, 정확한 커밋 수는 미확인)에서 `upstream-handler.ts` 전체(1556행)와 `mcp-gateway.ts`를 다시 읽은 결과 **구조적 결론은 그대로 유효**하다(`_clientsByService: Map<string, TargetClient>`가 여전히 서버 이름 단위 공유, `upstream-handler.ts:129`). 정정이 아니라 **재확인**이지만, 기존 문서가 "부분 코드 확인"으로만 표시해 둔 신뢰도를 이번 전체 파일 재독 결과로 올릴 수 있다는 점은 그 문서 쪽에 반영이 필요하다(이 작업 지시상 다른 파일 수정 금지라 이 문서에만 기록).
- 같은 문서 11줄의 "MCPX OSS 저장소와 Lunar 상용 Control Plane의 라이선스·배포 기능은 분리해야 한다"는 추측이 맞았다: 이번에 `proxy/LICENSE.md`를 직접 읽어 **mcpx/는 MIT, proxy/는 평가판 전용 상용 라이선스**임을 바이트 수준으로 확인했다. 또한 `proxy/README.md:5`에 MIT 배지가 떠 있는데 실제 `proxy/LICENSE.md`는 MIT가 아니다 — 배지와 라이선스 파일이 불일치하는 문서 오류(또는 README가 저장소 전체를 대표하는 배지를 그대로 복사한 것)로, Lunar Proxy를 "MIT"로 인용하면 안 된다.

## 9. 남은 미독 범위와 L4 재현 제안

미독 범위:
- MCPX: `services/sessions.ts`, `services/oauth-connection-handler.ts`, `services/hub.ts`(클라우드 Control Plane 연동), `it/` 테스트 본문, `packages/ui`(콘솔), `interceptors/lunar-ts-interceptor`(라이선스 파일이 따로 없어 귀속 라이선스 미확인), `env.ts`(각 플래그의 실제 기본값 — `ENABLE_AUDIT_LOG`, `STDIO_INHERIT_PROCESS_ENV`, `ENABLE_TOOL_CALL_CACHE` 등).
- Cisco Scanner: `scanner.py`의 나머지 2484행(원격 서버 연결 루프, CLI 경로, `_validate_analyzer_requirements`를 실제로 거치는 공개 메서드 식별), `core/static_analysis/` 전체(taint/dataflow/call-graph 상세), `config/config.py` 전체(모든 옵트인 플래그), `claude-code-plugin/`(스킬 형태 배포), `evals/` 샘플 본문.

L4 재현 제안(정상·음성·경계·장애·경쟁·복구):
1. MCPX consumerTag 스푸핑: 정상 요청(올바른 태그) vs 음성(다른 사용자 태그 도용) vs 경계(태그 생략) — 세 경우 모두 ACL 판정과 감사 로그의 `consumerTag` 필드를 비교해 스푸핑이 그대로 통과하는지 재현. 필요 환경: mcpx-server 로컬 기동 + 테스트용 `permissions` 설정 2개 consumerTag.
2. 감사 로그 손실 재현: `persistence.persist`가 실패하도록(디스크 쓰기 권한 제거 등) 만든 뒤 flush 주기를 넘겨 이벤트가 실제로 사라지는지 확인(장애·복구).
3. Cisco Scanner 타임아웃 재현: `_DEFAULT_TIMEOUT`을 낮추고 API 엔드포인트를 느린 목서버로 가리켜, 반환된 `ToolScanResult.status`가 `partial`/`failed`인데 `findings=[]`인 경우를 재현하고, 이를 그대로 소비하는 상상의 게이트가 "통과" 판정을 내리는지 확인(장애).
4. 두 프로젝트 모두 이번 조사는 **소스 정독**이며 실제 기동·재현은 하지 않았다. 재현에는 격리된 로컬 환경(샌드박스 컨테이너, 합성 자격)과 저장소 규칙상 솔루션 기기/PJ1 하네스가 필요하며, 이번 작업 범위에서는 수행하지 않았다.
