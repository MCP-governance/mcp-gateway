# 2026-10-20 LiteLLM 호환 (게이트웨이 신원·권한 경계 유지) — 미완료 (소유자 중단 지시로 저장)

- 브랜치 `10/20-litellm-compat`, 시작 `origin/main e1839f8`. 푸시 없음. 기기의 별도 프로젝트 `mint-llm`(`~/mint-llm-t1`)은 새 구성으로 실행 중이며 그대로 둔다. 제품 스택은 건드리지 않았다.
- **상태: 미완료.** 설계·소스 근거·구성·예비 확인(소량)까지만 했고, 요구한 N≥30 표본 시험·모델 경로 시험·managed_policy 변경·D-190은 **미실행**이다.

## 1. 소스 근거 (LiteLLM v1.105.0, tag commit `80b9556dd312d18c535ae06884faa97d1fdb8f46`)
`litellm/proxy`의 Python 소스는 기기 이미지(`ghcr.io/berriai/litellm-database:v1.105.0`, 패키지 1.105.0)와 tag가 일치(UI 산출물 제외 diff 없음). 경로는 `litellm/proxy/_experimental/mcp_server/` 기준.
- 사용자별 업스트림 토큰 전달은 가능하다. 헤더 `x-mcp-{서버}-authorization`을 서버별로 파싱(`auth/user_api_key_auth_mcp.py:1393-1444`, 첫 `-`에서 분리하므로 서버 별칭에 하이픈 금지), 호출 시 `lookup_mcp_server_auth_in_headers`로 해석(`utils.py:175-216`), `mcp_server_manager.py:6051-6140`에서 서버별 헤더가 우선.
- `auth_type: oauth_delegate`: LiteLLM은 호출자를 가상 키로 확인하고(`user_api_key_auth_mcp.py:519-526`) 호출자의 별도 Authorization을 그대로 전달, 발급·보관 안 함(`types/mcp_server/mcp_server_manager.py` 속성 `is_oauth_delegate`). 관리 키(Authorization이 LiteLLM 키인 경우)는 업스트림으로 새지 않도록 제거(`mcp_server_manager.py:1088-1152 _should_strip_caller_authorization`).
- 시작 시 도구 목록 채우기는 호출자 토큰이 필요한 서버를 건너뛴다(`operations.py:1769-1803` 주석) → LiteLLM이 공유 토큰을 쥘 필요가 없다.
- 도구 호출은 그 서버가 "그 호출자에게 목록으로 노출한" 도구만 전달한다(`mcp_server_manager.py:2908 server_exposes_tool`, `:6335-6365`). 도구→서버 매핑 `tool_name_to_mcp_server_name_mapping`은 프로세스 전역(`:1975`)이라 한 사용자의 목록이 다른 사용자의 호출 해석에 영향을 줄 수 있다(게이트웨이가 최종 판정하므로 신원 유출은 아님).
- 제공자가 직접 실행하는 원격 MCP를 막는 OSS 가드레일 `mcp_security`(`proxy/guardrails/guardrail_hooks/mcp_security/mcp_security_guardrail.py`), 프롬프트 차단 `litellm_content_filter`(정규식·prebuilt 패턴), 프롬프트 저장 `general_settings.store_prompts_in_spend_logs`(`proxy_server.py:7915`).
- MCP 집계를 끄는 단일 플래그는 없다. 끄는 방법: `mcp_servers` 미등록 + `require_key_mcp_access_defined: true` + 키 `allowed_routes=[llm_api_routes]` + 망 격리(아래).

## 2. 선택한 설계 (구현·기동함)
- LiteLLM을 internal 망에만 두고(밖으로 나갈 길 없음) 출구는 `edge-proxy`(Caddy) 하나: `:8081`이 제품 게이트웨이 `/mcp/*`만 TLS 검증하여 전달, 나머지는 403. 입구 `:4000`은 LiteLLM 앞단(loopback 게시). 파일: `full_stack_lab/llm/standalone/{compose.yaml,Caddyfile,litellm.yaml,litellm-llm-only.yaml,compose.llm-only.yaml,setup.sh}` (이전 MS Learn 우회 덮어쓰기 파일은 삭제).
- MCP 서버 3개를 `oauth_delegate`로 등록(upstream=게이트웨이 서버별 경로만). 직원은 `Authorization: Bearer <LiteLLM 키>` + `x-mcp-<서버>-authorization: Bearer <본인 게이트웨이 토큰>`(또는 `x-litellm-api-key`+분리된 Authorization) 전송.
- 출구 감사 로그(Caddy `log_append`)가 요청별 시각·경로·상태·`X-Agent-Task-Id`·Authorization 끝 8자만 남긴다(Caddy `hash`/`regexp` 필터는 배열 헤더에서 동작하지 않아 `request_header` 정규식 방식으로 교체).
- 가드레일 2개(`litellm_content_filter`, `mcp_security`)와 프롬프트 저장을 `litellm.yaml`에 추가(동작 시험은 미실행).

## 3. 실제로 실행한 확인 (예비, 각 1~수 회, 표본 부족)
- 격리: LiteLLM 컨테이너에서 게이트웨이 직접·learn.microsoft.com·1.1.1.1 모두 연결 불가, edge-proxy의 `/api/health`·`/oauth/token`은 403, `/mcp/github/`는 게이트웨이 401(토큰 없음). 1회씩.
- 토큰 전달: root 비관리 토큰(제품 `/oauth/token`)을 `x-mcp-github-authorization`으로 보내면 LiteLLM→게이트웨이 요청의 Authorization 끝 8자가 발급 토큰의 끝 8자와 일치(1회 확인). LiteLLM이 토큰 없이 보낸 요청은 인증 탐침 GET뿐 → LiteLLM이 보유한 서비스 토큰 없음.
- 결과 구분(1회씩, `server_outcomes`): 정상 토큰 ok / 변조 401 auth_required / root·user Console 토큰 403 forbidden / 토큰 없음 LiteLLM 401 / 틀린 LiteLLM 키 401 / 게이트웨이 토큰을 LiteLLM 키로 쓰면 401.
- 게이트웨이 쪽 기록: LiteLLM 경유 세션이 `mcp_client_sessions`에 principal·token_jti·서버로 남고 `oauth_issued_tokens.client_id`(예 `lc-probe-u5`)로 토큰 소유가 확인됨.

## 4. 막힌 점 (소유자 결정 필요)
- 사용 가능한 계정은 `root`(관리자, 비관리)뿐이다. `user`는 managed_required=true라 password grant가 거절(`idp.py` 103행대)되고 토큰은 PJ1 기기 헬퍼로만 나온다. PJ1 자격 빌려 쓰기 금지·계정 생성 금지·서버 승인 변경 금지 때문에 **승인된 주체의 토큰이 없다.**
- root는 세 서버의 승인 사용 주체가 아니라 `tools/list`가 빈 목록(직접 호출 시 `MCP-REGISTRY-003` Block 결정 7건)이고, LiteLLM은 노출되지 않은 도구 호출을 게이트웨이로 보내기 전에 "Tool not found"로 거절한다. 따라서 **LiteLLM 경유 허용 호출·도구 판정 결정 행(두 사용자 귀속)은 만들 수 없었다 — 미실행.** 대안으로 세운 시험: 미등록 게이트웨이 경로(`/mcp/lc-unregistered/`)를 LiteLLM에 임시 등록해 연결 단계 `MCP-REGISTRY-001` Block 결정을 사용자별로 얻는 것(미실행).
- 필요 입력: (a) 시험 전용 비관리 승인 주체 1명, 또는 (b) PJ1 헬퍼 토큰 사용 허가.

## 5. 남은 작업 / 재개 절차
1. 기기 `~/mint-llm-t1`(구성 반영됨, `. ./lc-env.sh && docker compose up -d`). 시험 도구 `research/llm-wiki/analysis/litellm-compat/scripts/lclib.py`(작성), 런처 `drv2.sh`는 WSL `/tmp/lc/`(저장소 밖; 호스트 망 컨테이너에서 LiteLLM 이미지 venv로 실행).
2. 미실행 시험(조건당 N≥30, 원시 JSON·Wilson 95% CI): MCP M1~M15(정상/변조/Console/폐기 토큰/키 없음/권한 없는 키/미등록 경로/외부 MCP 등록 시도/제공자 원격 MCP 가드레일), 모델 경로(Claude Code 2.1.288·Codex 0.160.0 컨테이너: 허용·예산 초과·모델 거부·잘못된 키·가드레일), 감지 점검 스크립트.
3. `endpoint_plane.managed_policy`에 기본 꺼진 `LLM_GATEWAY_URL` 옵션(Claude `ANTHROPIC_BASE_URL`+`apiKeyHelper`, Codex `model_providers`)과 단위 테스트(`tests/command_surfaces_check.py` 방식)·pyflakes — **미구현**.
4. `docs/ai/DECISIONS.md` D-190 — **미작성**. 보고서 최종판에 CI·한계 반영.
