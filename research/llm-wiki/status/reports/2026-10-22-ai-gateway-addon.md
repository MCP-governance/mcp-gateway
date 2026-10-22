# 2026-10-22 AI 게이트웨이 애드온 (LiteLLM 중앙 MCP 연동)

- 작업자: Claude Code (개발 레인, Sonnet 5.5)
- 코드 기준: 브랜치 `10/22-ai-gateway-addon`, 시작 `origin/main 1c59a00`. 변경 파일은 아래 「결과」.
- 시작 근거: 평가자 피드백(LiteLLM 쪽에서 MCP를 중앙 연동하는 경우 미커버), [Codex 분석](../../analysis/litellm-mint-opportunities-20261022.md)의 우선안, [10-20 호환 보고](2026-10-20-litellm-compat.md), 백로그 AIG-01, 결정 D-191.
- 해결할 문제와 완료 조건: 외부 AI 게이트웨이를 거치는 MCP 호출에도 MINT 통제를 붙이는 애드온. A 업스트림(주력), B LiteLLM 플러그인, C 범용 HTTP 계약(문서). 정상 동작 우선, 심화 보안은 제외.

## 결과

구현·단위 시험: 완료. 솔루션 기기 시험: A 일부, B는 판정 API 대역으로 LiteLLM 쪽만. 제품 스택 배포: 하지 않음(리더 담당).

| 구분 | 파일 | 내용 |
| --- | --- | --- |
| A | `addons/litellm/gen_mcp_servers.py` | `GET /api/registry`(또는 저장한 JSON)에서 운영 중인 서버만 골라 LiteLLM `mcp_servers`(`oauth_delegate`, 서버별 `/mcp/<서버>/`) 생성. 서비스 키 없음, 표준 라이브러리만 |
| B | `addons/litellm/mint_guardrail.py` | LiteLLM `CustomGuardrail`. `pre_mcp_call`에서 판정 API 호출, 허용이 아니면 403으로 차단, 제한 실행이면 `modified_arguments` 교체, 호출 후 `async_post_mcp_tool_call_hook`에서 결과 해시 기록 |
| B 서버 | `full_stack_lab/gateway/app/addon.py`, `main.py` | `POST /api/addon/v1/mcp-decision`, `/mcp-result` (둘 다 `Depends(caller)` + `mcp` scope 확인) |
| B 서버 | `full_stack_lab/gateway/app/core.py` | `execute_call`에 `_decide_only`: 정책 판정·원장 기록까지 하고 upstream 전송과 승인 대기 행 생성은 건너뜀 (+7행) |
| 앞단 | `full_stack_lab/field/Caddyfile`, `llm/standalone/Caddyfile` | HTTPS 사이트에 `/api/addon/v1/*` 추가(적용에는 스택 재기동 필요), 독립 LiteLLM 출구에 같은 경로 허용 |
| C | `docs/ai/AI_GATEWAY_ADDON.md` | 판정 API HTTP 계약(요청·응답 JSON, 오류 시 차단 규칙), 한계, 게이트웨이별 상태 |
| 문서 | `addons/litellm/README.md`, D-191, 백로그 AIG-01 | 설치 3단계, 한계 |
| 시험 | `full_stack_lab/tests/ai_gateway_addon_check.py` | 12건 |

설계에서 의도한 동작: 신원은 요청의 직원 MCP 토큰에서만 정하고 `asserted`(LiteLLM 사용자·팀)는 `decisions.client`에 기록만 한다. 사후 기록은 판정 행을 고치지 않고 `approval_events`(append-only, `addon-result`)에 덧붙인다. 승인 대기는 만들지 않는다(승인 뒤 MINT가 같은 호출을 한 번 더 보내 이중 실행되기 때문).

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 정적 검사 | `.venv-mcpgw` Python 3.12 `-m pyflakes` addon.py main.py core.py 시험·addons, 10-22 | 경고 없음 | |
| 무인증 목록 | `python tests/open_endpoints.py` | PASS(무인증 1개 일치, 새 라우트는 인증 필요 집계) | |
| 단위 | `python tests/ai_gateway_addon_check.py` | 12건 OK. `core.py` 변경을 되돌리면 `_decide_only` 시험 2건이 실패함을 확인 | |
| 앞단 시험 | `field_kit_check.py` 17건(1 skip), `field_tls_check.py` 9건 | OK | |
| Caddy 문법 | 기기에서 `caddy validate`(2.11.4) `llm/standalone/Caddyfile` | 설정 해석 통과(CA 파일이 없는 임시 환경이라 마지막 단계에서 실패, 경로 문법 오류 없음) | |
| A: LiteLLM 기동 | 기기 별도 compose 프로젝트 `mint-addon`(`llm/standalone` 구성, LiteLLM 1.105.0, 포트 127.0.0.1:4021). 서버 목록은 기기 콘솔 `/gw/registry`에서 생성기로 생성 | context7·github·markitdown 3개 등록, 헬스 통과 | |
| A: 토큰 전달 | root 토큰 2개(client_id `addon-e2e-a`/`-b`)를 `x-mcp-<서버>-authorization`으로 LiteLLM에 전송 | 출구 로그에서 토큰 끝 8자별로 200 16건·202 4건씩 따로 집계. 변조 토큰(끝 3자 변경)은 401 4건, 토큰 없는 LiteLLM의 요청은 인증 탐침 401뿐. LiteLLM이 보관한 서비스 토큰은 없음 | 출구 로그 |
| A: MINT 쪽 기록 | `mcp_client_sessions ⨝ oauth_issued_tokens` | LiteLLM 경유 세션이 토큰마다 4건(context7 2·github 1·markitdown 1) 계정 `root`에 기록되고 발급 client_id가 `addon-e2e-a`(jti caf63919…)와 `-b`(jti 600ce43f…)로 갈린다 | DB 조회 |
| A: 도구 호출 | LiteLLM `tools/list`, `tools/call` | **판정 행 0건.** root는 어느 서버의 승인 사용 주체도 아니라 MINT `tools/list`가 비어 있고 LiteLLM이 「Tool not found」로 전송 전에 막음. MCP 경로와 REST `/mcp-rest/tools/call` 모두 | 원장 id 880 이후 신규 행 0 |
| B: LiteLLM 플러그인 | 기기 단일 컨테이너(LiteLLM 1.105.0, 포트 127.0.0.1:4022) + `mint_guardrail.py` + **MINT 판정 API 대역**(`tok-allow` 등 토큰 문자열로 응답) + 실제 context7 원격 MCP | 아래 | |

B 관측값(LiteLLM 1.105.0, 대역 판정 서버):
- 허용 토큰: 대역이 `Authorization: Bearer tok-allow`와 `{"server_id":"context7","tool":"resolve-library-id", "asserted":{"user_id":"default_user_id"}}`를 받았다. 호출은 실제 context7에 도달해 응답(공개 키 월 한도 초과 문구, `isError`)이 왔고 호출 후 `/mcp-result`에 `decision_id` 101, 크기 163바이트, SHA-256이 기록됐다.
- 제한 실행 토큰: 대역이 인자를 `{"libraryName":"vue"}`로 바꿔 돌려주자 context7이 「query 필수」 입력 검증 오류를 냈다(허용 토큰은 월 한도 문구). 바뀐 인자가 실제 upstream까지 갔다.
- 차단 판정 토큰, 대역이 401을 주는 토큰, `Authorization` 없음: 모두 LiteLLM이 `Error: [MINT] …`로 응답했고 사후 기록은 없다.
- 대역 서버를 중단한 뒤 허용 토큰으로 호출: `MINT 판정을 받지 못해 도구 호출을 막았습니다(ConnectError)`.
- 직접 등록한 MCP 서버(헤더 수집용 업스트림)는 이 호출에서 `Authorization` 헤더를 받지 않았다(`extra_headers`에 넣지 않은 경우).
- 시험 컨테이너·볼륨·네트워크·작업 폴더는 모두 제거했다(`mint-addon*` 잔여 없음). 기존 `mint-llm`·제품 스택은 건드리지 않았다.

LiteLLM 소스 근거(고정 소스 1.102.0 `f8e456d`, `litellm/` 기준 줄 번호; 동작은 1.105.0 이미지에서 확인):
- 가드레일 호출: `proxy/_experimental/mcp_server/mcp_server_manager.py:5335-5445` `pre_call_tool_check` → `proxy/utils.py:1492` pre_call을 `pre_mcp_call`로 바꿔 `mode: pre_mcp_call` 가드레일을 실행.
- 가드레일이 받는 데이터: `proxy/utils.py:1056-1096` `_convert_mcp_to_llm_format`(`mcp_tool_name`, `mcp_arguments`, `mcp_server_name`, `incoming_bearer_token`, `user_api_key_*`). `incoming_bearer_token`은 `Authorization: Bearer` 값(`mcp_server_manager.py:5390-5395`).
- 인자 교체: 가드레일이 돌려준 `modified_arguments`가 `mcp_server_manager.py:5435`(`hook_result["arguments"]`)를 거쳐 `server.py:3171-3172`에서 적용.
- 사후 훅: `integrations/custom_logger.py:567` 시그니처, `litellm_core_utils/litellm_logging.py:1510-1549` 디스패치(예외는 비차단으로 삼킴 → 사후는 기록용), 호출 상관 키 `litellm_call_id`는 기기 시험에서 `model_call_details`에 있음을 확인.
- 가드레일 로더: `proxy/guardrails/guardrail_registry.py:596-650`, `proxy/types_utils/utils.py:9-56`(config 옆 `mint_guardrail.py`를 불러옴).
- 사용자별 헤더: `proxy/_experimental/mcp_server/utils.py:159-215` `x-mcp-{별칭}-authorization` 조회(별칭은 `_`로 정규화), `:984-1007`·`:1063-1092` 이 헤더들은 가드레일에 넘기는 헤더에서 제거됨 → B에서 직원 토큰은 `Authorization`으로 받아야 한다.
- 전달 규칙: `mcp_server_manager.py:975-1040` `_should_strip_caller_authorization`과 `:1190-1211` `_client_forwarded_authorization_headers`는 위임(`oauth_delegate`)·패스스루 서버의 호출자 Authorization 전달 규칙이다. 일반 서버(B)에서 Authorization이 upstream으로 가지 않는 것은 소스가 아니라 기기 시험(헤더 수집용 업스트림)으로 확인했다.
- 이 밖에 10-20 보고의 1.105.0 줄 번호(`auth/user_api_key_auth_mcp.py:1393-1444`, `mcp_server_manager.py:6051-6140`)를 이어받았고 이번에 다시 읽은 범위는 위 목록이다.

## 실패·미완료·한계

- **A의 도구 호출 판정 행을 만들지 못했다.** 기기의 승인 사용 주체가 managed_required 계정 `user` 하나뿐이고 그 토큰은 PJ1 헬퍼만 발급한다(자격 빌려 쓰기 금지). 비관리 계정 `root`는 승인 주체가 아니라 LiteLLM이 전송 전에 막는다. 따라서 「두 계정」으로는 비관리 계정 한 개(`root`)의 토큰 2개(workstation별)로 신원 분리를 확인했고, 승인된 두 직원 계정의 원장 귀속은 미실행이다.
- **B는 실제 MINT와 연동하지 않았다.** 판정 API는 제품 스택에 배포되지 않았고, 시험한 판정 서버는 대역이다. `addon.py`·`core.py`의 동작은 단위 시험(DB·OPA 대역)까지만 확인했다. 배포 후 필요한 시험: 허용·차단·제한 실행·승인 대기의 `policy_id`, `addon-result` 사건 기록, `field/Caddyfile` 경로, 원장 해시 체인 검증.
- 단위 시험의 DB·OPA·LiteLLM은 대역이다(실제 MCP 실행 증거 아님). 실제 MCP는 context7(B 시험)뿐이며 호출이 한도 초과 응답이라 정상 결과 본문은 보지 못했다.
- 사후 기록은 LiteLLM 예외 비차단 구조상 실패하면 LiteLLM 로그에만 남는다. 판정과 전송 사이 경쟁, 출력 검사 부재, 도구 계약 고정 부재는 B의 구조적 한계다([문서](../../../../docs/ai/AI_GATEWAY_ADDON.md)).
- 이번에 시험한 LiteLLM은 하나의 판본(1.105.0)과 하나의 헤더 구성(`x-litellm-api-key` + `Authorization`/`x-mcp-*`)이다. 다른 판본·가상 키/팀 권한 조합·`require_key_mcp_access_defined`와의 상호작용은 미확인.
- Kong·Portkey·Envoy `ext_authz`는 계약만 제공하고 붙여 보지 않았다.
- D-번호: 원격 브랜치 3개가 각각 D-190을 쓰고 있어 D-191을 택했다. 병합 순서에 따라 번호가 겹치면 정리가 필요하다.

## 다음 작업

- 리더: 이 브랜치 병합 후 `./console.sh field up`으로 판정 API와 Caddy 경로를 배포하고 B를 실제 MINT로 재시험(AIG-01 완료 조건 B).
- 승인된 비관리 시험 직원 계정 두 개(또는 PJ1 헬퍼 토큰 사용 허가)로 A의 `tools/call` 판정 행 두 건 이상을 직원 신원으로 확인(완료 조건 A).
- 방향 제안(이번 범위 밖, 콘솔): 활동 화면에서 `client.ingress=ai-gateway-addon` 판정과 `addon-result` 사건을 「외부 게이트웨이 경유」로 구분해 보여 주는 필터.

## 사용자에게 필요한 입력

- A의 호출 판정 확인을 위해 시험용 승인 주체를 어떻게 둘지 결정(승인은 사람이 한다): 비관리 시험 계정에 대한 도입 승인, 또는 PJ1 헬퍼 토큰 사용 허가.
- 평가 대응을 B까지 해야 하는지(아니면 A + 문서로 충분한지) 결정. 필요 없으면 B 라우트와 `_decide_only`는 제거 가능(D-191 되돌릴 조건).
