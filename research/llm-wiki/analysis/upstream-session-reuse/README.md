# 업스트림 MCP 세션 재사용 설계 비교 (DEV-29)

작성 2026-10-15 · 기준 코드 `b301e42`(`10/15-wbs-implementation`) · 상태 **제안, 사용자 결정 대기** · 제품 코드·기기 배포 변경 없음.

질문: Gateway가 `tools/call`마다 업스트림 MCP 세션을 열고 닫으며 실행 직전 `tools/list`로 계약을 다시 확인하는 구조(D-79)를, 지연을 줄이기 위해 어디까지 바꿀 수 있는가. 세션 재사용(a), 계약 목록 캐시(b), 상태 의존 서버 지원(c)과, 조사 중 찾은 세션 재사용 없는 연결 단축(d)을 비교한다.

## 결론

| 단계 | 내용 | github 원격 MCP 한 건(추정) | 보안 모델 변경 |
| --- | --- | --- | --- |
| 현행 | 호출별 세션 + 호출별 `tools/list` | 약 3.0 s + 종료 | — |
| **1. (d) 협상 결과 고정** | 카탈로그에 기록된 프로토콜 판으로 SDK 연결 모드를 고정(탐색 왕복 제거), 신형(2026-07-28) 서버는 핸드셰이크·종료 요청 자체가 없음 | 약 2.8 s(−0.2~0.3 s). 신형 서버는 연결·종료 구간이 사라짐 | 없음(세션 수명 그대로) |
| **2. (a) 세션 재사용** | `(주체, 다운스트림 세션, 서버, 자격 해시)`에 묶은 세션을 유휴 60 s·최대 10분 재사용, 호출마다 목록 재확인은 유지 | 재사용 시 약 2.2 s(−0.7~0.9 s − 종료) | D-79 "호출별 세션" 개정 |
| 3. (b) 계약 목록 캐시(제한) | 카탈로그가 읽기(`r`)로 검토한 도구만, TTL ≤ min(서버 `ttlMs`, 30 s), 변경 알림·감시·승인·종료·자격 교체로 무효화. 쓰기·중요 도구는 항상 재확인 | 읽기 도구 약 1.0 s(−1.2~1.3 s 추가) | 실행 직전 재확인을 "≤30 s 이내 확인"으로 완화(읽기 한정) |

**추천**: 1단계는 보안 경계를 건드리지 않으므로 먼저 구현한다. 2단계는 ContextForge가 교훈으로 바꾼 1:1 바인딩(다운스트림 세션 단위)을 따르고, 실행 직전 재판정·종료 시 차단은 그대로 둔 채 D-79를 개정한다. 3단계는 TOCTOU 창을 의도적으로 여는 결정이라 2단계 실측 뒤 사용자 결정으로 따로 정한다. 상태 의존 서버(c)는 2단계 위에서 **관리자가 등록 검토 때 켜는 서버별 선택 기능**으로만 지원하고 기본은 끈다.

수치는 2026-10-15 `decisions.timings`·`GET /api/latency` 관찰(게이트웨이 85–110 ms, github 연결 0.7–0.9 s·목록 1.2–1.3 s·실행 0.9 s, context7 각 약 0.2 s)에서 산술로 추정했다. 종료(`close`) 구간은 이 관찰에 없어 따로 측정해야 한다. 실측 전 숫자는 계획 값이다.

## 1. 현재 구조

[`core.py::_call_upstream`](https://github.com/MCP-governance/mcp-gateway/blob/b301e42899d3f896813a122c4cf0776dba2f9a98/full_stack_lab/gateway/app/core.py#L1193-L1316)이 한 연결 안에서 다음을 순서대로 한다. 각 단계는 [`_Laps`](https://github.com/MCP-governance/mcp-gateway/blob/b301e42899d3f896813a122c4cf0776dba2f9a98/full_stack_lab/gateway/app/core.py#L128-L145)가 `decisions.timings`에 남긴다.

| 구간 | 하는 일 | 코드 |
| --- | --- | --- |
| `connect` | `upstream.session()` → SDK `Client` 진입. SDK 2.2.0 기본 `mode="auto"`는 `server/discover`를 먼저 보내고, 구형 서버면 `initialize`·`notifications/initialized`로 되돌아간다 | [upstream.py:186–196](https://github.com/MCP-governance/mcp-gateway/blob/b301e42899d3f896813a122c4cf0776dba2f9a98/full_stack_lab/gateway/app/upstream.py#L186-L196) |
| `list` | `tools/list` → 활성 도구 전체의 설명·스키마 해시를 승인값과 대조(D-69), 인자를 관찰 스키마로 검증 | core.py:1218–1238 |
| `recheck` | 승인 만료·주체 상태·관리형 장치 실패·PAC 재구성·OPA 재판정·제한 변경 | core.py:1239–1278 |
| `intent` | `dispatch.record` — 예약·주체·서버 종료를 한 문장으로 마지막 확인하고 "나갔을 수 있음"을 기록 | core.py:1279–1294 |
| `call` | `tools/call` | core.py:1295–1306 |
| `close` | 세션 종료. 구형 서버는 SDK가 `DELETE`로 세션을 끝낸다 | SDK `streamable_http.py:663–677` |

HTTP 연결만 [`_dispatch_client`](https://github.com/MCP-governance/mcp-gateway/blob/b301e42899d3f896813a122c4cf0776dba2f9a98/full_stack_lab/gateway/app/upstream.py#L155-L183) 풀에서 `(endpoint, principal, timeout, 자격 헤더 해시)`로 재사용한다(TCP·TLS만 절약). 풀은 [`release_pool`](https://github.com/MCP-governance/mcp-gateway/blob/b301e42899d3f896813a122c4cf0776dba2f9a98/full_stack_lab/gateway/app/upstream.py#L117-L152)이 주체 중지([agent_service.py:680·698](https://github.com/MCP-governance/mcp-gateway/blob/b301e42899d3f896813a122c4cf0776dba2f9a98/full_stack_lab/gateway/app/agent_service.py#L675-L700))와 서버 종료([decommission.py:270](https://github.com/MCP-governance/mcp-gateway/blob/b301e42899d3f896813a122c4cf0776dba2f9a98/full_stack_lab/gateway/app/decommission.py#L270))에서 닫고, `upstream_pool_events`로 다른 프로세스에 알린다(2초 주기 `_sweep`). 2단계는 이 경로를 그대로 쓴다.

판정에 쓰이는 사실 두 가지:

- 하네스가 보는 도구 설명·스키마는 업스트림이 아니라 Gateway가 승인값으로 내준다([mcp_facade.py:9](https://github.com/MCP-governance/mcp-gateway/blob/b301e42899d3f896813a122c4cf0776dba2f9a98/full_stack_lab/gateway/app/mcp_facade.py#L9)). 업스트림 설명이 바뀌어도 모델에는 닿지 않는다. 실행 직전 재확인이 막는 것은 "검토 뒤 서버가 바뀐 상태로 실행"(스키마 의미 변경·서버 교체)이다.
- 그 재확인은 서버가 **광고하는** 계약만 본다. 목록을 바꾸지 않고 동작만 바꾸는 서버는 호출별 재확인으로도 잡히지 않는다. 지금도 목록 응답과 실행 사이에 Gateway 처리 시간(recheck·intent, 수십 ms)만큼의 창이 있다. 재확인은 정직한 변경과 단순한 rug pull을 잡는 탐지기이지 보증이 아니다.

등록 서버 프로토콜 판([contracts.lock.json](../../../../full_stack_lab/registry/contracts.lock.json)): 9개가 `2025-11-25`(구형·세션 있음), Gitea MCP 1.7.0이 `2026-07-28`(신형·세션 없음). Gateway 자신은 상태 저장 Streamable HTTP로 하네스에 응답한다([main.py:46–49](https://github.com/MCP-governance/mcp-gateway/blob/b301e42899d3f896813a122c4cf0776dba2f9a98/full_stack_lab/gateway/app/main.py#L46-L49), `stateless_http` 미설정)라서 구형 하네스 연결에는 다운스트림 `Mcp-Session-Id`가 있다.

## 2. 근거 (고정 판본)

| 근거 | 판본 | 확인한 사실 | 설계에 쓰는 곳 |
| --- | --- | --- | --- |
| MCP 규격 2025-11-25 [transports L192–218](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/86f6e0c675afea9a8f233e09b6faf566b126086c/docs/specification/2025-11-25/basic/transports.mdx#L192-L218) | `86f6e0c` | 서버가 `MCP-Session-Id`를 줄 수 있고(MAY), 클라이언트는 이후 요청에 반드시 붙이며, 404면 새 `initialize`, 끝낼 때 `DELETE`(SHOULD) | 구형 서버 세션 재사용의 프로토콜 조건, 만료 처리(T10) |
| 같은 판 [보안 모범 사례 L573–584](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/86f6e0c675afea9a8f233e09b6faf566b126086c/docs/docs/2025-11-25/tutorials/security/security_best_practices.mdx#L573-L584) | `86f6e0c` | 서버는 모든 요청을 검증하고 세션을 인증에 쓰지 말 것(MUST NOT), 세션 ID를 사용자 정보에 묶을 것(SHOULD) | 세션 재사용이 재판정을 대신하지 않는다(I3) |
| MCP 규격 2026-07-28 [changelog L12–14](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/86f6e0c675afea9a8f233e09b6faf566b126086c/docs/specification/2026-07-28/changelog.mdx#L12-L14) | `86f6e0c` | 프로토콜 세션·`Mcp-Session-Id`·`initialize` 제거. 호출 간 상태는 서버가 만든 핸들을 도구 인자로 넘긴다 | 신형 서버는 재사용할 세션이 없음 → (d)로 연결 비용 자체가 사라짐, (c)는 구형 서버 한정 |
| 같은 판 [changelog L34–36](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/86f6e0c675afea9a8f233e09b6faf566b126086c/docs/specification/2026-07-28/changelog.mdx#L34-L36), [tools L61–69](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/86f6e0c675afea9a8f233e09b6faf566b126086c/docs/specification/2026-07-28/server/tools.mdx#L61-L69) | `86f6e0c` | `tools/list`에 `ttlMs`·`cacheScope` 필수, 목록은 연결마다 달라지면 안 되지만 **요청의 인가에 따라 달라질 수 있다** | 캐시 키에 자격을 넣는다(b), SDK 캐시 위험(I8) |
| 같은 판 [tools L236–248](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/86f6e0c675afea9a8f233e09b6faf566b126086c/docs/specification/2026-07-28/server/tools.mdx#L236-L248) | `86f6e0c` | 목록 변경 알림은 `subscriptions/listen` 구독자에게 보낼 것(SHOULD) | 알림은 무효화 보조 신호일 뿐 보안 근거가 아님(b) |
| MCP Python SDK `mcp==2.2.0`(Gateway 고정판, [requirements.txt](../../../../full_stack_lab/gateway/requirements.txt)) | wheel SHA-256 `bde98258…7f92be004f81` | `Client.mode` 기본 `auto`(`client.py:330–337`), `negotiate_auto`는 탐색 후 구형이면 `initialize`(`_probe.py:52–96`), 버전 문자열 고정 시 탐색 없이 채택(`client.py:456–462`). `Client.cache` 기본값이 서버 `ttlMs`를 따르는 **클라이언트별 메모리 캐시**(`client.py:358–366`, `caching.py:99–124`) | (d)의 근거. 세션을 재사용하면 `list_tools()`가 조용히 캐시를 돌려줄 수 있음(I8) |
| IBM ContextForge [upstream_session_registry.py L1–17·L750–904](https://github.com/IBM/mcp-context-forge/blob/5735c9db7f8f50cd5a55eb7fefe83ecde00b5324/mcpgateway/services/upstream_session_registry.py#L750-L904) | `5735c9d`, Apache-2.0 | 신원 키 풀이 같은 사용자의 두 다운스트림 세션 사이에 상태를 흘려(#4205) `(다운스트림 Mcp-Session-Id, gateway_id)` 1:1 레지스트리로 교체. 벽시계 TTL 없음, 유휴 60 s 뒤 재사용 전 건강 확인, 세션 사용 직렬화(SDK 요청 ID 경합), 전송 오류 시 축출 | 2단계 키·직렬화·축출 규칙 |
| 같은 저장소 [ADR-032 L1–21](https://github.com/IBM/mcp-context-forge/blob/5735c9db7f8f50cd5a55eb7fefe83ecde00b5324/docs/docs/architecture/adr/032-mcp-session-pool.md#L1-L21), [tool_service.py L6719–6745](https://github.com/IBM/mcp-context-forge/blob/5735c9db7f8f50cd5a55eb7fefe83ecde00b5324/mcpgateway/services/tool_service.py#L6719-L6745), [gateway_service.py L563–600](https://github.com/IBM/mcp-context-forge/blob/5735c9db7f8f50cd5a55eb7fefe83ecde00b5324/mcpgateway/services/gateway_service.py#L563-L600), [session_registry.py L1244–1258](https://github.com/IBM/mcp-context-forge/blob/5735c9db7f8f50cd5a55eb7fefe83ecde00b5324/mcpgateway/cache/session_registry.py#L1244-L1258) | `5735c9d` | 다운스트림 세션 ID가 없거나 추적 중이면 레지스트리를 쓰지 않는다. 게이트웨이 인증·URL 변경 커밋 뒤 해당 세션 전부 축출, 다운스트림 세션 삭제 시 축출. 호출 경로에 실행 전 업스트림 `tools/list` 재확인은 없다 | 다운스트림 세션 없으면 호출별로 되돌림, 자격 변경 시 닫기. ContextForge보다 우리가 엄격한 지점(재확인) 명시 |
| Microsoft mcp-gateway [AdapterSessionRoutingHandler.cs L52–68·L98–120](https://github.com/microsoft/mcp-gateway/blob/3594c4eee36308ac131aad1c946ea14140b4353d/dotnet/Microsoft.McpGateway.Service/src/Session/AdapterSessionRoutingHandler.cs#L52-L120), [시험 L135–160](https://github.com/microsoft/mcp-gateway/blob/3594c4eee36308ac131aad1c946ea14140b4353d/dotnet/Microsoft.McpGateway.Service/test/AdapterSessionRoutingHandlerTests.cs#L135-L160) | `3594c4e`, MIT | 세션 라우팅 키를 `사용자:어댑터:세션ID`로 묶어, 다른 사용자가 세션 ID를 알아도, 권한이 회수된 어댑터 경로로 재생해도 찾지 못하게 한다 | 키에 주체·서버를 반드시 넣는 근거(I2), 교차 주체 시험(T2) |
| Lunar MCPX [upstream-handler.ts L126–129·L473–494](https://github.com/TheLunarCompany/lunar/blob/7193eab5535ec0be2c973007b9ab5cccab15fd70/mcpx/packages/mcpx-server/src/services/upstream-handler.ts#L126-L494) | `7193eab`, MIT(`mcpx/LICENSE.MD`) | 대상 서버마다 오래 사는 클라이언트 하나(`Map<string, TargetClient>`)를 모든 소비자 호출이 공유 | 채택하지 않는 반례(주체 간 공유, D-79) |

10-14 [보고](../../status/reports/2026-10-14-pj1-nine-tools.md)는 ContextForge 레지스트리 소스·ADR을 "미열람", Microsoft는 2차 자료로 적었다. 이번에 두 소스를 고정 커밋으로 읽어 위 표로 대체한다. 결론(호출자 간 공유 금지, 다운스트림 세션 단위 바인딩)은 바뀌지 않는다. Lunar MCPX는 세션 처리 부분만 읽었고 나머지 기능 분석은 [솔루션 항목](../../solutions/lunar-mcpx.md)의 미확인 상태 그대로다.

## 3. 선택지

### (d) 협상 결과 고정 — 세션 재사용 없음

- 동작: 카탈로그 승인 때 기록한 `protocol_version`으로 SDK `Client(mode=…)`를 정한다. 구형(`2025-11-25`)은 `mode="legacy"`(탐색 왕복 제거), 신형(`2026-07-28`)은 `mode="2026-07-28"`+기록한 `DiscoverResult`(핸드셰이크 없음, 세션 없음 → 종료 `DELETE` 없음).
- 절감: 구형 github는 연결 3왕복 중 탐색 1왕복(추정 0.2–0.3 s), context7 약 0.07 s. 신형 서버는 `connect`·`close`가 거의 0이 된다(Gitea로 측정 가능).
- 위험: 서버가 판을 올리거나 내리면 첫 호출이 실패한다. 완화: `UnsupportedProtocolVersionError`·핸드셰이크 오류면 그 호출 안에서 `auto`로 한 번 다시 연결(실행 전 단계라 부작용 없음)하고, 판 변화는 `catalog_watch`가 기록한다(D-69처럼 판 문자열만 바뀐 것은 기록만). 판 변경을 차단 사유로 삼을지는 기존 규칙 그대로.
- 불변식 영향: 없음. 세션 수명·재확인·키 모두 현행.

### (a) MCP 세션 재사용

- 키: `(principal, downstream_session_id, server_id, sha256(자격 헤더))`. 다운스트림 세션 ID가 없으면(신형 하네스·stdio 브리지) 재사용하지 않고 호출별 세션(ContextForge와 같은 되돌림). 주체만으로 묶으면 한 사람의 두 대화가 상태를 나눈다(#4205).
- 수명: 유휴 60 s(현재 HTTP keepalive와 같음), 최대 수명 10분(자격이 메모리에 머무는 시간 상한), 전체 상한은 `UPSTREAM_POOL_SIZE`와 같은 방식. 다운스트림 세션 종료·`release_pool`(주체 중지·서버 종료)·자격 해시 변경·전송 오류에서 닫는다.
- 호출 경로: 세션만 재사용하고 `list`·`recheck`·`intent`는 호출마다 그대로 한다. SDK `Client`는 `cache=None`으로 만든다(I8). 한 세션은 한 번에 한 호출만 쓴다(ContextForge 직렬화 근거). 같은 키에서 동시 호출이 오면 세션을 하나 더 연다(같은 키 상한 4).
- 절감: 재사용된 호출에서 `connect`+`close`. github −0.7~0.9 s − 종료, context7 −0.2 s − 종료. 첫 호출·TTL 밖 호출은 현행과 같다. 하네스 한 대화 안의 연속 호출이 주 대상.
- 위험과 완화

| 위험 | 완화 |
| --- | --- |
| 주체·대화 간 상태 유출 | 키에 주체·다운스트림 세션 포함, 공유 경로 없음. 업스트림이 준 세션 ID는 다른 키로 옮기지 않음 |
| 중지·종료 뒤 세션이 남음 | 실행은 `intent`의 마지막 확인이 막는다(현행). 세션은 `release_pool`·`_sweep`(≤2 s)으로 닫힘. 남는 동안 실행 0 |
| 자격 교체 뒤 옛 자격 세션 | 키의 자격 해시가 바뀌면 같은 `(principal, server)`의 옛 세션을 닫음(`_dispatch_client`의 기존 규칙과 같음) |
| SDK 응답 캐시로 재확인이 조용히 낡음 | `cache=None` 고정과 시험 T7(신형 서버는 `ttlMs`를 반드시 보내므로 재현 가능) |
| 업스트림이 세션을 끝냄(404) | `list` 단계면 새 세션으로 한 번 다시 연다. `call` 단계면 재시도하지 않고 현행처럼 "실행 여부 불명"으로 기록 |
| 업스트림의 서버 발신 요청(구형 GET 스트림의 sampling·elicitation) | 핸들러가 거부, 알림 중 `tools/list_changed`만 (b)의 무효화에 씀 |
| 예외 처리 구조 | 현행은 연결을 닫은 뒤 판정해 `ExceptionGroup` 혼동을 피한다(core.py:1193 docstring). 재사용 세션은 호출 범위에서 닫히지 않으므로 같은 성질을 유지하도록 판정·예외 경로를 다시 짠다 |
| 프로세스 간 | 레지스트리는 프로세스 안. 닫기 신호는 `upstream_pool_events`를 그대로 씀 |

### (b) 계약 목록 캐시와 TOCTOU

- 동작: `(server_id, 자격 해시)`별로 최근 `tools/list` 결과와 승인 대조 결과를 둔다. TTL = min(서버 `ttlMs`, 30 s). 구형 서버는 `ttlMs`가 없으니 30 s 상한만.
- 무효화: 업스트림 `tools/list_changed`(구독한 경우), `catalog_watch` 드리프트(60 s 주기, `CATALOG_REFRESH_SECONDS`), 도구 승인·철회·재승인, 서버 종료, 자격 교체, 세션 재생성. 알림은 SHOULD라 없을 수 있으므로 TTL이 상한이다.
- 적용 범위: 카탈로그가 사람 검토로 읽기(`r`)로 둔 도구만. 쓰기·중요 분류·승인 대기 도구는 항상 실시간 재확인. 도구 자신의 `readOnlyHint`는 서버 자기 신고라 쓰지 않는다.
- 절감: 캐시 적중 시 `list` 전체. github −1.2~1.3 s, context7 −0.2 s.
- 위험: 서버가 계약을 바꾼 뒤 최대 TTL 동안 읽기 호출이 바뀐 서버로 나간다. 모델은 승인된 설명만 보므로 설명 변경으로 모델이 속지는 않지만, 스키마 의미가 바뀐 도구나 교체된 서버로 읽기 요청과 인자가 나간다. 결과는 출력 검사(`inspect_out`)를 지난다.
- 검토했지만 채택하지 않은 변형: `tools/list`와 `tools/call`을 동시에 보내고 계약이 다르면 결과를 보류 — 요청과 인자가 이미 나간 뒤라 쓰기 도구에는 쓸 수 없고, 읽기 도구에서도 (b)보다 절감이 작다(github 목록 1.25 s > 실행 0.9 s).

### (c) 상태 의존 서버

| 서버 | 상태 의존 | 현행 | (a) 키에 다운스트림 세션 포함 시 |
| --- | --- | --- | --- |
| Playwright MCP 0.0.83(구형) | 탭이 세션에 묶이고 마지막 세션이 닫히면 탭도 닫힘(10-14 직접 실험) | 탐색→조회가 이어지지 않음 | 한 대화 안에서 탭 유지, 대화 간 분리, TTL 만료 시 탭 닫힘 |
| mcp-email-server 1.9.1(구형, 읽기 도구 8개) | 미확인(소스 미열람) | 확인 필요 | T3로 확인 |
| Gitea MCP 1.7.0(신형) | 프로토콜 세션 없음 | 영향 없음 | 해당 없음 — (d)만 적용 |

- 신형 규격에서 호출 간 상태는 명시적 핸들(도구 인자)이므로 세션 바인딩은 구형 서버를 위한 과도기 기능이다.
- 상태가 유지되면 앞선 허용 호출이 만든 상태를 뒤 호출이 쓴다. 호출마다 정책 판정은 그대로이고, 상태 연쇄는 핸들 방식에서도 같은 문제라 세션이 새로 만드는 위험은 아니다. 다만 등록 검토에서 사람이 "세션 유지" 서버로 표시할 때 이 점을 본다.
- 서버별 `session_affinity` 표시(카탈로그, 사람 검토, 기본 끔)가 켜진 서버만 (a)를 쓰게 하는 방식도 가능하다. 1차 구현은 (a)를 모든 구형 서버에 쓰고 상태 의존은 표시만 하는 것을 권한다(재사용이 지연 절감의 본체이고 키 분리는 같다).

## 4. 지연 추정

| 경우 | github 원격 MCP | context7 |
| --- | --- | --- |
| 현행 | 0.1 + 0.8 + 1.25 + 0.9 + close ≈ 3.05 s + close | 0.1 + 0.2 + 0.2 + 0.2 + close ≈ 0.7 s + close |
| (d) | ≈ 2.8 s + close | ≈ 0.63 s + close |
| (d)+(a), 재사용 적중 | ≈ 0.1 + 1.25 + 0.9 ≈ 2.25 s | ≈ 0.5 s |
| (d)+(a)+(b), 읽기 도구 적중 | ≈ 0.1 + 0.9 ≈ 1.0 s(−67%) | ≈ 0.3 s |

Tailscale DERP 중계(DEV-37)는 원격 SaaS 구간이 아니라 PC↔Gateway 구간이므로 이 표에 들어 있지 않다. 탐색 왕복을 연결의 1/3로 본 것은 가정이고, `close`는 측정하지 않았다. 1단계 구현 때 `connect`를 세분해(`discover`·`initialize`) 기록해야 2단계 전후 비교가 된다.

## 5. 보안 불변식

| ID | 불변식 | 지키는 방법 | 시험 |
| --- | --- | --- | --- |
| I1 | 직원 토큰을 업스트림에 넘기지 않는다 | 세션은 `credential_headers(endpoint, principal)`의 운영자 자격으로만 만든다. 다운스트림 요청 헤더를 세션 생성에 넘기는 경로를 만들지 않는다 | T1에서 업스트림 수신 헤더에 직원 토큰 없음 |
| I2 | 주체 간·대화 간 상태 공유 금지 | 키에 주체·다운스트림 세션·서버. 다운스트림 세션이 없으면 재사용 안 함 | T2·T3 |
| I3 | 실행 직전 재판정 | 승인·주체·관리형 장치·OPA·`dispatch.record`는 재사용과 무관하게 호출마다. 목록 재확인은 (b) 미채택 시 호출마다, 채택 시 읽기 도구만 ≤30 s | T4·T7·T8 |
| I4 | 종료·중지 시 차단 | `intent`의 마지막 확인(현행) + `release_pool`로 세션 닫기 + 닫힌 키로 새 세션 금지 | T4·T5·T11 |
| I5 | 자격 교체 시 옛 세션 폐기 | 키의 자격 해시, 교체 시 같은 `(principal, server)` 옛 세션 닫기 | T6 |
| I6 | 실패는 차단 | 재사용 세션 오류는 새 세션 또는 차단, 캐시 오류는 실시간 재확인. 통과로 떨어지는 경로 없음 | T10 |
| I7 | 감사 원장 불변 | 원장 형식·append-only 그대로. `timings`에 재사용·캐시 적중 표시만 더함 | T1 |
| I8 | SDK 응답 캐시가 재확인을 대신하지 않음 | 재사용 `Client`는 `cache=None`. 캐시는 (b)의 Gateway 캐시 하나뿐 | T7 |

## 6. 시험 계획

격리 실행기 [`termination_dispatch_lab.sh`](../../../../full_stack_lab/tests/termination_dispatch_lab.sh)(`wbs-c-*`, 제품 스택과 무관, 3시간 뒤 자동 삭제)에 시험 파일을 추가해 `run`으로 돌린다. 지금 실험실에는 실제 Gitea MCP 1.7.0(신형)이 있다. 구형·상태 의존 서버로 공개 OSS Playwright MCP 공식 이미지(판 고정)를 `up`에 더해야 한다(자체/mock MCP 금지 규칙). 판정은 `decision`과 `policy_id`까지, 부작용은 Gitea 이슈 수·Playwright 페이지 상태로 독립 확인한다. 기존 `dispatch_effect_lab.py`의 게이트(예약과 전송 사이에서 호출을 붙잡는 시험 훅)를 경쟁 시나리오에 쓴다.

| ID | 시나리오 | 성공 조건 | 대상 |
| --- | --- | --- | --- |
| T1 | 같은 주체·대화로 20회 호출 | 2번째부터 `connect`≈0·재사용 표시, Gitea 이슈 20건, 업스트림 수신 헤더에 직원 토큰 없음 | (a) |
| T2 | 주체 A·B가 같은 서버 | 업스트림 세션 ID가 다름, A가 연 탭을 B가 못 봄(`about:blank`) | (a)(c) |
| T3 | 같은 주체의 두 대화 | 탭 분리. email 서버의 상태 의존 여부 기록 | (a)(c) |
| T4 | 예약~전송 사이 붙잡힌 호출 중 주체 중지 | `Principal was revoked before dispatch`, Gitea 증가 0, `upstream_pool_events` 행·세션 닫힘 | I3·I4 |
| T5 | 재사용 세션이 있는 서버를 종료 절차로 | `Block/MCP-DECOMM-001`, 엔드포인트 세션 0, 이후 새 세션 없음 | I4 |
| T6 | `reset`으로 공급자 토큰 교체 후 호출 | 새 키로 새 세션, 옛 세션 닫힘, 옛 토큰으로 업스트림 요청 0 | I5 |
| T7 | 재사용 세션에서 업스트림 도구 목록 변경(서버 재기동으로 도구 세트 변경 — 방법은 Gitea MCP 옵션으로 확인 필요) | 다음 호출 `MCP contract changed before execution`. 신형 서버의 `ttlMs`가 있어도 목록 요청이 매번 서버에 도달 | I3·I8 |
| T8 | (b) 켠 상태에서 계약 변경 | 쓰기 도구 즉시 차단, 읽기 도구는 무효화 신호 또는 TTL 안에 차단으로 바뀜. 실제 창 길이 기록 | (b) |
| T9 | 같은 키 동시 10호출 | 응답이 인자와 1:1로 맞음, 키당 세션 ≤ 상한 | (a) |
| T10 | 목록 단계·실행 단계에서 업스트림 재기동 | 목록 단계는 한 번 재연결 후 성공, 실행 단계는 재시도 없이 "실행 여부 불명" 기록 | I6 |
| T11 | Gateway 프로세스 2개, 한쪽에서 주체 중지 | 다른 쪽이 ≤2 s 안에 세션을 닫고, 그 전에도 호출은 거부 | I4 |
| T12 | (d) 판 고정 후 서버 판 변경 | 한 번 `auto`로 다시 연결해 성공, 판 변화는 기록만 | (d) |

실측: 각 단계 배포 뒤 PJ1 실제 하네스로 이미 승인된 github·context7을 쓰고 `GET /api/latency`로 전후를 비교한다. 시험 대상 서버를 에이전트가 승인·등록하지 않는다(D-79).

## 7. 사용자 결정이 필요한 것

1. 1단계 (d) 구현 여부 — 보안 경계 변경 없음.
2. 2단계 (a)로 D-79의 "호출별 세션 유지"를 개정할지, 수명 값(유휴 60 s·최대 10분).
3. 3단계 (b)로 읽기 도구의 계약 재확인을 ≤30 s 이내 확인으로 완화할지.
4. 상태 의존 서버를 서버별 표시로만 둘지, 표시된 서버만 세션을 유지할지.

## 8. 한계

- 지연 숫자는 10-15 관찰의 범위값에서 계산한 추정이다. `close`·탐색 왕복은 미측정이다.
- SDK 2.2.0은 PyPI wheel을 정적으로 읽었고 실행하지 않았다. GitHub 원격 MCP가 실제로 어떤 판을 협상하는지는 기기 DB의 `catalog_snapshots`로 확인해야 한다(저장소 잠금 파일에는 github 항목이 없다).
- ContextForge·Microsoft·MCPX는 정적 소스 검토이며 실행하지 않았다. ContextForge의 "SDK 요청 ID 경합"이 SDK 2.2.0에도 해당하는지는 T9로 확인한다.
- 하네스(Claude Code·Codex)가 Gateway에 구형·신형 중 무엇으로 붙는지 확인하지 않았다. 신형이면 다운스트림 세션 ID가 없어 (a)의 재사용이 일어나지 않는다. 그 경우 대안은 주체·서버 키 재사용과 상태 의존 서버 제외인데, 이는 #4205 위험을 다시 여는 별도 결정이다.
