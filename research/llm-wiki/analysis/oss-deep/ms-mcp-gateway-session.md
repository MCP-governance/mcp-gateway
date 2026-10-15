# microsoft/mcp-gateway 심층 분석 — 세션·제어평면 연결·수명·장애 (DEV-47, ms-mcp-gateway-session)

## 1. 요약

이 저장소는 .NET/Kubernetes 기반 MCP 리버스 프록시 + 경량 관리 포털이다. 데이터 평면(세션 인지 라우팅),
제어 평면(어댑터/도구 등록·소유권·역할), 수명(K8s StatefulSet 생성·갱신·삭제), 장애(백엔드 불능·세션
저장소 장애·재시작) 네 기능을 코드로 추적했다.

판정(L3, 네 기능 모두 입구→인증→권한→실행→결과/상태저장까지 닫힘):

1. **세션 결속(데이터 평면)**: 세션 ID는 `사용자:어댑터이름:세션ID` 3중 키로 결속된다
   (`AdapterSessionRoutingHandler.cs:113-126`). 다른 사용자가 같은 세션 ID를 들고 와도, 같은 사용자가
   다른 어댑터 경로로 같은 세션 ID를 재생해도 조회되지 않는다. 단위 시험이 두 시나리오를 모두
   `SEC-0003`로 명명해 커버한다(`AdapterSessionRoutingHandlerTests.cs:137-190`). **세션 ID 자체는
   정책 입력이 아니라 라우팅 키일 뿐**이라는 기존 BENCHMARK 문서의 결론은 유지된다.
2. **제어평면↔tools/call 연결점**: 등록 시점에 쓰는 소유자·`RequiredRoles`와 호출 시점 권한 판정이
   실제로 **같은 `IPermissionProvider` 인스턴스(`SimplePermissionProvider`)를 공유**해 닫혀 있다
   (`ToolManagementService.cs` 등록 ↔ `HttpToolExecutor.cs:72` 실행 직전 판정). 그러나 이 연결은
   **"Tool"(개별 함수, HTTP 백엔드) 리소스에만 있고 "Adapter"(통짜 MCP 서버) 리소스에는 없다**. 어댑터
   경로(`AdapterReverseProxyController.cs:99-122`)는 어댑터 전체에 대한 Read 권한 한 번만 확인하고,
   그 뒤로는 JSON-RPC 바디를 들여다보지 않고 그대로 프록시한다 — 등록자가 정한 역할이 어댑터
   안의 개별 도구(`tools/call`의 `name`)별로는 전혀 적용되지 않는다.
3. **수명**: 생성은 즉시 활성(승인 대기 단계 없음, 기존 결론 유지). **삭제는 스토어 레코드와 K8s
   워크로드만 지우고 세션 저장소는 건드리지 않는다**(`AdapterManagementService.cs:111-127`에
   `IAdapterSessionStore` 의존성 자체가 없음, 생성자 `AdapterManagementService.cs:15` 확인). 삭제된
   어댑터로의 **새** 요청은 스토어 조회 실패로 404가 되어 막히지만(`AdapterReverseProxyController.cs:106-112`),
   이는 세션 무효화가 아니라 "자원이 사라져서 못 찾음"이다.
4. **장애**: 세션 저장소(분산 캐시) 조회/저장에 `try/catch`가 없다(`DistributedMemorySessionStore.cs:37-66`).
   Redis/Cosmos 장애 시 예외가 그대로 올라가 요청이 500으로 떨어진다 — 결과적으로는 차단(fail-closed)이지만,
   **신규 세션과 기존 세션 재사용 모두가 같은 장애점에 걸린다**(세션별이 아니라 저장소 전체 장애).

MINT에 주는 결론: (a) `(주체, 다운스트림 세션, 서버)` 3중 키 결속은 DEV-29 2단계(세션 재사용) 설계의
독립적 두 번째 근거다. (b) 어댑터 단위로만 권한을 걸고 도구 단위로는 안 거는 이 구조는 MINT가 이미
피하고 있는 모델이며, 그 이유를 구체적 코드로 재확인했다. (c) 세션 저장소 장애를 전원 차단이 아니라
온건 열화로 다루는 설계는 이 저장소에 없다 — MINT가 그런 열화를 만들 근거도 당장은 없다.

## 2. 고정 정보

- 저장소: `https://github.com/microsoft/mcp-gateway`, commit `3594c4eee36308ac131aad1c946ea14140b4353d`
  (2026-08-25, `git log -1`로 재확인). 로컬 경로 `ref-src/ms-mcp-gateway`(origin 일치, clean).
- 라이선스: MIT(`LICENSE:1-3`, Copyright Microsoft 2025), `NOTICE` 파일 존재(본문 미독).
- 읽은 파일(행 범위 대략):
  - `dotnet/Microsoft.McpGateway.Service/src/Session/AdapterSessionRoutingHandler.cs`(1-128, 전문)
  - `dotnet/Microsoft.McpGateway.Service/src/Session/DistributedMemorySessionStore.cs`(1-119, 전문)
  - `dotnet/Microsoft.McpGateway.Service/src/Controllers/AdapterReverseProxyController.cs`(1-146, 전문)
  - `dotnet/Microsoft.McpGateway.Service/src/Controllers/SessionManagementController.cs`(1-188, 전문)
  - `dotnet/Microsoft.McpGateway.Service/src/HttpProxy.cs`(1-125, 전문)
  - `dotnet/Microsoft.McpGateway.Service/src/Program.cs`(1-273, 전문)
  - `dotnet/Microsoft.McpGateway.Service/src/Authentication/DevelopmentAuthenticationHandler.cs`(1-76, 전문)
  - `dotnet/Microsoft.McpGateway.Service/src/McpSubPathAwareAuthenticationHandler.cs`(1-181, 전문)
  - `dotnet/Microsoft.McpGateway.Service/src/Routing/AdapterKubernetesNodeInfoProvider.cs`(1-181, 전문)
  - `dotnet/Microsoft.McpGateway.Management/src/Authorization/SimplePermissionProvider.cs`(1-96, 전문)
  - `dotnet/Microsoft.McpGateway.Management/src/Authorization/ForwardedIdentityHeaders.cs`(1-16, 전문)
  - `dotnet/Microsoft.McpGateway.Management/src/Service/AdapterManagementService.cs`(1-185, 전문)
  - `dotnet/Microsoft.McpGateway.Management/src/Service/ToolManagementService.cs`(1-235, 전문)
  - `dotnet/Microsoft.McpGateway.Management/src/Contracts/ToolDefinition.cs`(1-41, 전문)
  - `dotnet/Microsoft.McpGateway.Management/src/Deployment/KubernetesAdapterDeploymentManager.cs`(1-254, 전문)
  - `dotnet/Microsoft.McpGateway.Tools/src/Program.cs`(1-159, 전문)
  - `dotnet/Microsoft.McpGateway.Tools/src/Services/HttpToolExecutor.cs`(1-174, 전문)
  - `dotnet/Microsoft.McpGateway.Service/test/AdapterSessionRoutingHandlerTests.cs`(1-312, 전문)
  - `dotnet/Microsoft.McpGateway.Service/test/HttpProxyTests.cs`(1-268, 전문)
  - `dotnet/Microsoft.McpGateway.Service/test/SessionStoreTests.cs`(테스트명만, grep)
  - `dotnet/Microsoft.McpGateway.Management/test/AdapterManagementServiceTests.cs`(테스트명만, grep)
  - `deployment/k8s/local-deployment.yml`(replica·StatefulSet/Deployment 종류만)
  - `README.md:1-40`(Key Concepts — Adapter/Tool/Tool Gateway Router 자기 정의)
  - 읽지 않음: `portal/`(React), Foundry 에이전트 실행기 전체(`SessionManagementController`가 다루는
    "에이전트 세션"은 MCP 어댑터 세션과 무관한 별도 기능이라 이번 조사에서 제외, §8 참고),
    `deployment/k8s/cloud-deployment-template.yml` 본문(grep만, replicas 매치 없음).

## 3. 경로 추적

### 3.1 데이터 평면 — 세션 인지 라우팅

| 단계 | 함수(경로:행) | 상태 저장소 | 실패 시 결정 |
| --- | --- | --- | --- |
| 입구 | `AdapterReverseProxyController.ForwardStreamableHttpRequest`(`AdapterReverseProxyController.cs:36-97`), 라우트 `POST /mcp`·`POST /adapters/{name}/mcp` | — | — |
| 인증 | `[Authorize]`(클래스 데코레이터, `AdapterReverseProxyController.cs:14`) → Entra JWT 또는 dev 핸들러(§3.4) | ASP.NET 인증 파이프라인 | 미인증은 `[Authorize]`가 401로 끊음(컨트롤러 코드 도달 전) |
| 권한(어댑터 단위) | `EnsureAdapterReadAccessAsync`(`:99-122`) — 스토어에서 어댑터 조회 후 `permissionProvider.CheckAccessAsync(User, adapter, Operation.Read)` | `IAdapterResourceStore`(Redis/Cosmos) | 어댑터 없음→404(`:106-112`), 권한 없음→403(`:114-119`) |
| 세션 조회/신규 | 세션 ID 있으면 `sessionRoutingHandler.GetExistingSessionTargetAsync`(`AdapterSessionRoutingHandler.cs:33-69`), 없으면 `GetNewSessionTargetAsync`(`:22-31`, K8s 헬시 풀에서 무작위 선택) | `IAdapterSessionStore`(분산+로컬 캐시) / `IServiceNodeInfoProvider`(K8s watch, 인메모리) | 스코프 키 미스·형식 불량→`ArgumentException`(`:46-66`), 대상 풀이 비어있으면 `null`→503(`AdapterReverseProxyController.cs:54-58`) |
| 실행(프록시) | `HttpProxy.CreateProxiedHttpRequest`(`HttpProxy.cs:23-84`)로 재구성한 요청을 대상 파드로 전달, 신원 헤더는 인증된 Principal에서 재주입(인바운드 Authorization/신원 헤더는 버림, `:41-53,61-73`) | — | 대상이 응답 없음/오류면 `client.SendAsync` 예외가 try/catch 없이 전파(§4) |
| 결과 처리 | `HttpProxy.CopyProxiedHttpResponseAsync`(`:106-124`), 응답 헤더는 allowlist만 복사(`:87-104`) | — | — |
| 세션 등록(최초 호출만) | 응답의 `mcp-session-id`를 형식 검사(`AdapterSessionRoutingHandler.IsValidSessionId`) 후 `BuildScopedSessionKey`로 `사용자:어댑터:세션ID` 결합해 저장(`AdapterReverseProxyController.cs:67-93`) | `IAdapterSessionStore.SetAsync`(`DistributedMemorySessionStore.cs:59-66`) | 형식 불량이면 세션 ID를 응답에서 제거해 클라이언트에 전달하지 않음(`:76-84`, 캐시 오염 방지) |
| 감사/상태 | 구조화 로그(`ILogger`)만. 전용 감사 원장·해시체인 없음(기존 BENCHMARK 결론 재확인) | — | — |

핵심 보안 설계 하나: `forwardGatewaySecret`은 `name is null`(즉 어댑터 이름이 없는 기본
`/mcp` 경로, "툴 게이트웨이" 자체)일 때만 `true`이고, 이름 있는 외부 어댑터 경로는 항상
`false`다(`AdapterReverseProxyController.cs:62`). 사용자 제공 어댑터 파드는 게이트웨이 공유 비밀을
절대 받지 않는다 — 시험으로도 고정됨(`HttpProxyTests.cs:20-27,50-59`).

### 3.2 제어 평면 ↔ `tools/call` 연결점

| 단계 | 함수(경로:행) | 상태 저장소 | 실패 시 결정 |
| --- | --- | --- | --- |
| 등록 | `ToolManagementService.CreateAsync`(`ToolManagementService.cs:50-81`) — 이름 검증, `ValidateToolDefinition`(포트/경로 SSRF 방지, `:185-193`), 소유자·시각 기록(`ToolResource.Create`) | `IToolResourceStore` | 이름 중복·형식 불량→400 |
| 소유권/역할 | `ToolResource`가 `CreatedBy`·`RequiredRoles`를 들고 다님(기존 BENCHMARK의 `IManagedResource` 모델과 동일) | 같은 스토어 | — |
| 호출 입구 | `HttpToolExecutor.ExecuteToolAsync`(`HttpToolExecutor.cs:36-163`), MCP SDK의 `WithCallToolHandler`가 호출(`Tools/Program.cs:79-83`) | — | 도구 이름 없음→오류 결과(IsError, `:41-52`) |
| 신원 | `httpContextAccessor.HttpContext.User`(`:58-63`) — 이 Principal은 상위 게이트웨이가 넣어준 `X-Mcp-UserId`/`X-Mcp-Roles` 헤더에서 **서명 재검증 없이** 구성됨(`Tools/Program.cs:116-140`), 단 `X-Gateway-Secret` 일치가 선행 미들웨어에서 강제됨(`:101-114`) | — | 공유 비밀 불일치→401(헤더 신뢰 전 단계에서 차단) |
| **권한 판정(연결점)** | `toolResourceStore.TryGetAsync(toolName)`(`:65`)로 등록 레코드를 다시 읽고, `permissionProvider.CheckAccessAsync(principal, toolResource, Operation.Read)`(`:72`) — **등록 시점 소유자/`RequiredRoles`와 같은 `SimplePermissionProvider.CanRead`(`SimplePermissionProvider.cs:52-76`)를 그대로 재사용** | `IToolResourceStore` | 거부→"permission" 오류 결과(`:73-76`), 도구 없음→"not found"(`:66-70`) |
| 실행 | `{toolName}-service.adapter.svc.cluster.local`로 `UriBuilder` 조립(authority 주입 방지, `:88-99`) 후 HTTP POST | — | 비정상 상태코드→오류 결과 포함 응답(`:119-139`), `HttpRequestException`→오류 결과(`:153-157`) |

**연결의 범위 한계**: 위 표는 **"Tool"(개별 함수) 리소스에만 성립**한다. "Adapter"(통짜 MCP 서버,
`/adapters/{name}/mcp`)는 §3.1의 `EnsureAdapterReadAccessAsync`가 어댑터 레벨 Read 권한만 한 번 확인하고,
그 뒤 프록시는 JSON-RPC 바디의 `method`/`params.name`을 전혀 파싱하지 않는다
(`AdapterReverseProxyController.cs:62-96`에 바디 역직렬화 코드 없음, `HttpProxy.CreateProxiedHttpRequest`는
스트림을 그대로 전달). 즉 등록자가 어댑터에 건 `RequiredRoles`는 "이 서버를 쓸 수 있는가"까지만 걸리고,
"이 서버의 어떤 도구를 쓸 수 있는가"는 전적으로 백엔드 MCP 서버 자신에게 위임된다. README가 "Adapters"와
"Tools"를 서로 다른 리소스 종류로 명시하는 것(`README.md:25-27`)과 일치하는 설계상의 구분이며, 버그가
아니라 두 리소스 종류가 애초에 다른 세분화 수준을 제공한다는 뜻이다.

### 3.3 수명 — 생성·갱신·삭제

| 단계 | 함수(경로:행) | 상태 저장소 | 실패 시 결정 |
| --- | --- | --- | --- |
| 생성 | `AdapterManagementService.CreateAsync`(`AdapterManagementService.cs:24-52`) — 이름 중복만 확인 후 `_deploymentManager.CreateDeploymentAsync`(K8s StatefulSet+headless Service, `KubernetesAdapterDeploymentManager.cs:33-149`)와 스토어 upsert를 순서대로 수행 | `IAdapterResourceStore`, K8s API | 이름 중복→400, 이미지 참조 검증 실패(`ValidateImageReference`, `:239-252`)→400. **승인 대기 단계 없음**(생성 즉시 활성, 기존 결론 재확인) |
| 갱신 | `UpdateAsync`(`AdapterManagementService.cs:70-109`) — 소유자/admin만, `UseWorkloadIdentity`·`Name` 불변 필드는 거부. replica·image·env 변경 시에만 `UpdateDeploymentAsync`(전략적 병합 패치, `KubernetesAdapterDeploymentManager.cs:151-193`) 호출 | 동일 | 불변 필드 변경→400 |
| 삭제 | `DeleteAsync`(`AdapterManagementService.cs:111-127`) — 소유자/admin만, 스토어 레코드 삭제 후 `DeleteDeploymentAsync`(StatefulSet+Service 삭제, 404는 로그만 하고 무시, `KubernetesAdapterDeploymentManager.cs:195-209`) | 동일 | 어댑터 없음→400. **`IAdapterSessionStore`를 전혀 참조하지 않음**(서비스 생성자에 의존성 없음, `AdapterManagementService.cs:15`) — 세션 저장소의 `사용자:어댑터:세션ID` 엔트리는 TTL(유휴 1h·절대 12h, `DistributedMemorySessionStore.cs:24,32-33`)까지 그대로 남음 |
| 삭제 후 호출 | 새 요청은 `EnsureAdapterReadAccessAsync`가 스토어에서 어댑터를 찾지 못해 404로 막음(`AdapterReverseProxyController.cs:106-112`) — **세션이 살아있어도 자원 부재로 차단되는 것이지, 세션이 무효화된 것이 아님** | — | 404 |
| 스케일 | `ReplicaCount` 변경 시 StatefulSet patch(`KubernetesAdapterDeploymentManager.cs:151-193`). 축소로 사라진 파드 주소는 `AdapterKubernetesNodeInfoProvider`의 K8s watch가 반영(§3.4)하지만, **이미 저장된 세션의 target 주소는 재계산되지 않는다** — 그 파드가 사라지면 해당 세션의 다음 호출은 연결 실패(§4) |

### 3.4 세션 저장소·헬시 풀의 내부 구조

- `DistributedMemorySessionStore`: 프로세스-로컬 `ConcurrentDictionary`(유휴 1h, 10분 주기 스윕,
  `DistributedMemorySessionStore.cs:74-101`)가 L1, `IDistributedCache`(Redis/Cosmos, 절대 12h,
  `:24,33`)가 L2. `TryGetAsync`(`:37-57`)·`SetAsync`(`:59-66`) 모두 L2 호출에 `try/catch` 없음(§4).
- `AdapterKubernetesNodeInfoProvider`: 생성자에서 백그라운드 루프 시작(`FetchPodAddressInfo`,
  `AdapterKubernetesNodeInfoProvider.cs:50-163`) — 최초 `ListNamespacedPodAsync`로 헬시 파드 맵을
  구성하고, 이후 K8s watch 이벤트로 갱신. watch가 끊기면(오류·종료) 10초 뒤 재시작(`:155-160`).
  `GetNodeAddressesAsync`는 `_initialFetchCompleted` 완료를 기다린 뒤(`:35-37`, 재시작 시에도 빈 목록을
  즉시 주는 대신 대기) 현재 맵에서 반환한다 — **watch가 아직 재연결되지 않은 짧은 구간에는 방금
  사라진 파드가 여전히 "헬시"로 남을 수 있다**(watch 이벤트 수신 지연).

## 4. 실패·경합·복구 결정표

| 조건 | 코드 동작(근거) | fail-open/closed | 미확인 |
| --- | --- | --- | --- |
| 백엔드 파드 불능(기존 세션의 target이 죽음) | `GetExistingSessionTargetAsync`는 저장된 주소를 그대로 반환(재검증 없음, `AdapterSessionRoutingHandler.cs:61-68`). 이후 `client.SendAsync`가 던지는 예외를 컨트롤러가 잡지 않음(`AdapterReverseProxyController.cs:62-96`에 try/catch 없음) | closed(호출이 성공하지 못함)이지만 **재시도·다른 파드로의 전환 없음** — 클라이언트가 세션 없이 재접속해야 함(`GetNewSessionTargetAsync`로 새 파드 선택) | ASP.NET 기본 예외 처리가 어떤 상태 코드를 내는지(개발/운영 모드별 상이) — 소스에 전역 예외 핸들러 미발견 |
| watch 지연 중 신규 세션이 방금 죽은 파드를 선택 | `_healthyPodsByStatefulSet`가 watch 이벤트를 받기 전까지 죽은 파드를 포함(`AdapterKubernetesNodeInfoProvider.cs:84-140`) | 열림(죽은 대상 선택 가능) | 실측 지연 시간(watch 이벤트 전파 지연) |
| 세션 저장소(Redis/Cosmos) 장애 | `TryGetAsync`/`SetAsync`의 `_distributedCache` 호출에 `try/catch` 없음(`DistributedMemorySessionStore.cs:44,64`) → 예외가 `AdapterSessionRoutingHandler`를 거쳐 컨트롤러까지 전파 | **closed(요청 실패)지만 범위가 전체 서비스** — 신규/기존 세션 모두, 모든 사용자·모든 어댑터가 동시에 영향받음. MINT의 `_sweep`/`release_pool`처럼 저장소 장애를 호출별로 격리하는 장치 없음(`upstream.py:118-152`와 대조, §6) | 실제 프로덕션 예외 핸들링 미들웨어(Program.cs에 전역 핸들러 등록 없음, ASP.NET 기본값 추정) |
| 토큰 만료 | `[Authorize]`가 표준 JWT 검증 파이프라인에서 매 요청 재검증(세션 존재와 무관) | closed | — |
| 삭제 후 진행 중 호출 | 신규 요청은 스토어 404로 막힘(`AdapterReverseProxyController.cs:106-112`). 이미 `EnsureAdapterReadAccessAsync`를 통과해 프록시 중인 호출은 K8s가 파드를 내리는 시점에 연결 오류로 끝남(별도 취소 신호 없음) | closed(신규), **미확인(진행 중 호출의 정확한 타이밍)** | 삭제~K8s 파드 종료 사이의 정확한 경합 창 |
| 재시작(Service 파드) | L1 캐시 소실, L2(분산 캐시)는 유지 → 세션은 끊기지 않고 재개 가능(백엔드 파드가 살아있다면). `AdapterKubernetesNodeInfoProvider`는 매 시작마다 K8s List+Watch를 새로 하고, 완료 전에는 `GetNodeAddressesAsync`가 대기(빈 응답을 주지 않음, `:35-37`) | closed(대기로 안전) | — |
| 다중 Gateway 복제본 | L2가 단일 진실원이지만 L1은 복제본별로 독립(유휴 1h). 한 복제본의 `RemoveAsync`가 다른 복제본의 L1을 즉시 비우는 신호가 없음(`DistributedMemorySessionStore.cs`에 pub/sub·무효화 알림 없음) | 미확인에 가까움 — 삭제 경로(§3.3)는 애초에 세션을 지우지 않으므로 이 틈이 실제로 드러나는 시나리오는 "자격/권한 변경 뒤 세션 유지" 쪽이나, 그 경로 자체가 코드에 없음(별도 "자격 교체" 개념이 이 저장소에 없음) | 운영 환경의 실제 복제본 수(로컬 템플릿은 `replicas: 1`, `deployment/k8s/local-deployment.yml:24,116`) |
| 자격/권한 회수 후 기존 세션 | 코드에 "자격 회수" 개념 자체가 없다(MCP 어댑터 세션은 사용자 신원에만 묶이고, 신원이 아니라 어댑터 리소스의 `RequiredRoles`가 바뀌는 경우 다음 호출의 `EnsureAdapterReadAccessAsync`가 바로 재평가함 — 세션은 매 요청 재검사되는 권한 확인 **앞에서** 걸린다, `AdapterReverseProxyController.cs:38` 순서) | closed(권한 변경이 다음 요청부터 즉시 적용) | — |

## 5. upstream 시험

- `AdapterSessionRoutingHandlerTests.cs` — 교차 사용자(`:137-159`), 교차 어댑터(`SEC-0003`,
  `:162-190`), 형식 불량 세션 ID의 fast-fail(`:114-134`), 미인증(`:221-230`) 등 세션 결속의 핵심
  반례를 충실히 커버한다. **빠진 것**: 분산 캐시 타임아웃/예외 시나리오, 삭제된 어댑터에 대한
  재사용 시도(이 파일은 라우팅 핸들러만 단위로 보고 컨트롤러의 404 우선순위까지는 검증하지 않음).
- `SessionStoreTests.cs` — 캐시 조회 순서(L1→L2)와 제거를 검증하지만(그렙 결과 `GetAsync_Returns*`,
  `SetAsync_StoresInBothCaches`, `RemoveAsync_RemovesFromBothCaches`), **`_distributedCache`가
  예외를 던지는 경우는 시험되지 않는다** — §4의 "세션 저장소 장애" 행이 코드 경로상 추론이지
  시험으로 확인된 것은 아니다.
- `HttpProxyTests.cs` — 신원 헤더 재주입/제거, 게이트웨이 비밀의 어댑터·툴게이트웨이 분기, 요청
  바디 재읽기(버퍼링) 경계 조건까지 꼼꼼하다. **실제 `SendAsync` 실패(죽은 백엔드)는 이 파일의 범위
  밖**(순수 요청 조립만 다룸, 네트워크 호출 없음).
- `AdapterManagementServiceTests.cs` — CRUD·권한·워크로드 아이덴티티 분기는 넓게 커버하지만
  **`IAdapterSessionStore`를 아예 모킹하지 않는다**(서비스에 그 의존성이 없으므로 당연함) —
  "삭제가 세션에 미치는 영향"은 이 스위트의 관심사 밖임을 재확인.
  `AdapterKubernetesNodeInfoProvider`에 대한 단위 시험 파일은 찾지 못했다(디렉터리 목록에
  없음 — watch 재연결·헬시 파드 갱신 지연은 전혀 시험되지 않는다, 정적 미발견).

## 6. MINT 대조

| 항목 | ms-mcp-gateway | MINT(현재) | 차이 |
| --- | --- | --- | --- |
| 세션 결속 키 | `사용자:어댑터:세션ID`(문자열 결합, `AdapterSessionRoutingHandler.cs:125`) | DEV-29 설계가 제안하는 `(principal, downstream_session_id, server_id, sha256(자격 헤더))`(`dev29-design.md` §3(a)) | MINT 설계가 자격 해시까지 키에 넣는다는 점에서 한 단계 더 좁다. 어댑터/서버 단위 결속은 동일한 발상이며, 이 OSS의 테스트(`SEC-0003`)가 "다른 서버 경로로 재생 금지"라는 같은 불변식을 독립적으로 검증해 DEV-29의 I2 근거를 보강한다 |
| 호출 경로의 세션 재사용 범위 | 세션은 **라우팅**에만 쓰이고 매 호출의 권한 재판정과 분리되어 있지 않다(권한은 세션과 무관하게 매 요청 `EnsureAdapterReadAccessAsync`로 재확인, 세션은 "어느 파드로 보낼지"만 결정) | MINT는 세션(연결) 재사용과 `list`/`recheck`/`intent`(권한 재확인)을 명시적으로 분리하는 설계(`core.py:1211-1278`, DEV-29 §3(a)) | 구조가 유사하다: 둘 다 "연결 재사용"과 "권한 재확인"을 별개 축으로 둔다. ms-mcp-gateway는 권한 재확인이 어댑터 단위로 거칠고, MINT는 도구 계약 단위로 더 세밀하다(§3.2의 Tool/Adapter 구분과 대응) |
| 세션 저장소 장애 격리 | 없음(§4) | `release_pool`/`_sweep`이 DB 테이블로 다른 프로세스에 알리고, 실패해도 로그만 하고 디스패치 경계가 스스로 막는다(`upstream.py:118-153`, "실패해도 호출을 막지 않는다"는 설계 docstring) | MINT는 풀 정리 알림의 실패를 디스패치 차단과 분리해 설계했다. ms-mcp-gateway는 세션 저장소 자체가 세션 조회의 유일한 경로라 장애가 곧 기능 정지다 — **이 차이는 MINT가 이미 잘 하고 있는 부분**이지 가져올 결함이 아니다 |
| 삭제 시 세션 정리 | 하지 않음(§3.3) | DEV-29 설계의 I4(`release_pool`로 세션 닫기)는 종료 시 적극적으로 세션을 닫는 것을 불변식으로 제안 | MINT가 설계 중인 "종료 시 적극적 세션 종료"가 이 OSS에는 없다는 것을 코드로 확인했다 — MINT 설계가 이 지점에서 더 엄격하다는 근거가 추가됐다(채택 방향 유지, 새로 바꿀 것 없음) |
| 제어평면↔실행 권한 연결 | Tool 리소스에서만 닫혀 있고 Adapter 리소스에서는 어댑터 단위로만 열림(§3.2) | MINT는 `mcp_facade.py:9`가 하네스에 내주는 설명/스키마 자체를 Gateway 승인값으로 바꿔치기하고, `core.py:1236-1246`이 실행 직전 도구별 계약을 재확인 — 등록 단위가 아니라 **도구 단위**로 항상 재확인 | MINT는 이미 "어댑터(서버) 전체 신뢰"가 아니라 "도구별 계약 확인"을 하고 있다. 이 OSS의 Adapter/Tool 이분법은 그 세밀함이 "개별 함수로 등록된 것"에만 있다는 반례로 쓸 수 있다 — MINT가 지금 하는 일을 포기할 근거는 없음 |
| 개발 모드 우회 | `X-Dev-UserId`/`X-Dev-Roles` 자기신고(§3.4, 기존 BENCHMARK 재확인) | 해당 없음(MINT는 신원을 transport 토큰에서만 정함, 루트 불변식) | 재확인만, 신규 아님 |

## 7. 목표 기능 재설계 시사점

**없음(세션/수명/장애 설계를 바꿀 근거는 이번 조사에서 나오지 않았다)**. 이유:

- 세션 결속 키 설계(사용자+서버+세션ID)는 DEV-29가 이미 독립적으로 도달한 결론과 같은 방향이고,
  이 OSS가 자격 해시까지는 넣지 않는다는 점에서 MINT 설계가 더 엄격하다. 채택할 것이 아니라
  "같은 방향의 바깥 증거"로 DEV-29 §7의 사용자 결정 항목에 참고 각주를 더하는 정도가 적절하다.
- Adapter/Tool 이분법(서버 단위 권한 vs 함수 단위 권한)은 MINT가 이미 도구 단위 계약 재확인으로
  대체한 모델의 "약한 버전"이다. 가져올 것이 없다.
- 세션 저장소 장애를 전역 실패로 다루는 방식은 MINT가 이미 더 세밀하게(풀 단위 알림 분리) 하고
  있어 참고할 개선점이 아니다.
- 삭제 시 세션 미정리는 MINT의 DEV-29 설계(I4, `release_pool`)가 이미 반대 방향으로 가고 있다는
  확인일 뿐, 설계를 바꿀 근거가 아니다.

## 8. 정정

- 기존 `docs/ai/BENCHMARK_MICROSOFT.md`(§2.2, §3 PAC-04행)의 "세션 ID는 라우팅용, 정책 입력 아님"이라는
  서술은 **여전히 맞다** — 틀린 주장은 아니다. 다만 그 문서는 `AdapterSessionRoutingHandler`의
  사용자+어댑터 결속 키와 교차 사용자/교차 어댑터 방지 시험(`SEC-0003`)을 전혀 언급하지 않아, "세션이
  라우팅에만 쓰인다"는 서술이 "그래서 세션 보안이 약하다"는 오해로 읽힐 수 있었다. 이번 조사로
  라우팅 자체의 결속은 사용자/대화 간 상태 유출을 막는 별도 보안장치임을 보완했다 — 정정이 아니라
  깊이 추가다.
- `research/llm-wiki/analysis/review-2026-10-15/dev29-design.md`(스크래치패드 사본)가 인용한
  `AdapterSessionRoutingHandler.cs L52-68·L98-120`과 테스트 인용(`AdapterSessionRoutingHandlerTests.cs
  L135-160`)은 이번 재독으로 **그대로 정확함을 확인**했다(현재 행 번호는 각각 §3.1·§5에서 재인용한
  범위와 거의 일치, ±10행 이내 차이는 파일 전체 재포맷 없음을 뜻하는 정상 오차). 정정 없음.
- SessionManagementController(`SessionManagementController.cs:1-188`)가 다루는 "세션"은 **Foundry
  에이전트 실행 세션**(system prompt+모델+도구목록을 실행한 한 번의 대화)이며, DEV-29·이 분석이
  다루는 "MCP 어댑터 스트리밍 세션"(`mcp-session-id` 헤더, 파드 라우팅용)과 **이름만 같고 전혀 다른
  기능**이다. 이 구분을 명시한 기존 문서를 찾지 못했다 — 향후 Microsoft 관련 문서에서 "세션"을
  인용할 때 어느 쪽인지 반드시 명시해야 한다(정정이 아니라 주의 추가).

## 9. 남은 미독 범위와 L4 재현 제안

- 미독: `portal/`(React 관리 UI) 전체, Foundry 에이전트 실행기(`SubAgentInvoker.cs` 등)의 세션 재귀
  호출 구조, `deployment/k8s/cloud-deployment-template.yml` 본문(운영 replica 수 미확인),
  `AdapterKubernetesNodeInfoProvider`의 단위 시험 부재를 보완할 통합 시험 설계.
- 미확인(코드로는 추론했으나 실행 검증 없음): (a) ASP.NET 기본 예외 처리 미들웨어가 `SendAsync`
  실패·분산 캐시 예외를 실제로 몇 번 상태코드로 바꾸는지, (b) K8s watch 재연결 지연의 실측 구간,
  (c) 삭제~K8s 파드 종료 사이에 걸린 프록시 호출의 정확한 결과(연결 오류 vs 빈 응답 vs 타임아웃).
- L4 재현 제안(판본·환경 고정, 정상/음성/경계/장애/경쟁/복구):
  1. **세션 교차 방지**: 로컬 `kind` 클러스터에 두 사용자 JWT(또는 `BypassEntra` dev 헤더, 비운영
     환경에서만)로 같은 어댑터에 접속해 세션 ID를 교환 시도 — `AdapterSessionRoutingHandlerTests.cs`가
     이미 단위로 증명한 것을 실제 HTTP 계층까지 올려 재현.
  2. **세션 저장소 장애 주입**: Redis 컨테이너를 중지한 채 기존 세션 재사용과 신규 세션 생성을
     각각 시도해 실제 응답 코드와 지연을 측정 — §4의 "전역 장애" 추론을 실행으로 확정.
  3. **삭제 경쟁**: 어댑터에 세션을 연 상태에서 `DELETE /adapters/{name}`을 호출하고, 그 직후
     진행 중이던 `tools/call` 하나의 결과(성공/연결 오류/타임아웃)와 K8s 파드 종료 타이밍을
     상관시켜 경쟁 창의 실제 폭을 잰다.
  4. **스케일 다운 중 세션 유지**: 레플리카 3→1로 축소하면서 사라지는 파드에 세션이 묶인 클라이언트의
     다음 호출이 어떻게 실패하는지(연결 거부/타임아웃)와 watch 갱신 지연의 실측값을 함께 기록한다.
  필요 환경: 로컬 `kind`/`k3s`(저장소의 `local-deployment.yml` 그대로), Redis 컨테이너, 공개 OSS MCP
  서버 1종(합성 데이터)을 어댑터로 등록. 이 저장소의 스크립트·`docker-compose`는 실행하지 않고
  매니페스트만 참고해 MINT 쪽 격리된 실험 환경에서 재현한다(저장소 규칙).
