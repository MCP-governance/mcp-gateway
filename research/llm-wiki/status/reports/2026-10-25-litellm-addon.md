# 2026-10-25 LiteLLM 애드온 — 기업 적용·정상 기능(S5)

- 작업자: Claude Code (Opus 5.5), 세션 `release-packaging`(리더 지시로 S5 이어받음)
- 코드 기준: `origin/10/25-integrate` 2a30570에서 분기 → 4679160(S1 2단계) 병합. 브랜치 `10/25-litellm-addon`
- 변경 파일: `full_stack_lab/gateway/app/litellm_sync.py`·`agent_service.py`·`agent_tables.sql`, `addons/litellm/mint_guardrail.py`·`README.md`·`config/litellm-{mint,plugin}.yaml`(신규), `deploy/compose.yaml`·`.env.example`·`.gitignore`·`mint.sh`·`check.py`·`README.md`, `full_stack_lab/llm/standalone/{compose.yaml,setup.sh,litellm.yaml,harness/Dockerfile}`, `full_stack_lab/integrations/litellm/preflight.py`(주석), `full_stack_lab/tests/litellm_sync_check.py`·`ai_gateway_addon_check.py`·`litellm_addon_e2e.py`(신규), `.github/workflows/verify.yml`(`litellm` 작업), `docs/ai/AI_GATEWAY_ADDON.md`·`LITELLM_SYNC.md`·`DECISIONS.md`(D-249·D-250), 위키 생성물(`catalogs/threats.json`, `analysis/requirements.json`·`integration-cases.json`)
- 시작 근거: astra 검토(10-25, 판정 「수정 필요」, `C:\Users\…\astra검토_LiteLLM애드온_20261025.md` — 로컬 원본), D-191·D-208, 소유자 지시(10-25) 「애드인도 편의·자동화·기업 패키징·위생, 정상 기능 우선」
- 완료 조건: astra 3절 8개 항목, 항목별 시험(실패→통과), CI 통과(LiteLLM 연동 작업 포함), `run_local_suite.py` 새 실패 0, pyflakes 0, 위키 재생성·`check_wiki.py` 오류 0, 결정·문서·보고서

## 결과 — astra 8개 항목 전/후

| # | 항목 | 전(2a30570) | 후(이 브랜치) | 시험 |
| --- | --- | --- | --- | --- |
| ① | 배포 연결 | `deploy/`에 URL·키 변수만, 매핑 파일·마운트 없음 → 안내대로 채우면 설정 읽기 실패 | `./mint.sh litellm enable --url --bindings [--ca] [--route] < 키`: 매핑을 `deploy/litellm/`에, 관리 키를 게이트웨이 이미지 안에서 0400·소유 10001 파일로, **쓰기 없는 점검**(`python -m app.litellm_sync check`) 통과 때만 게이트웨이 재생성. `check`·`status`·`rotate-key`(재기동 없음)·`disable`, 관리 origin 전용 CA, 매핑·CA 백업 | CI `litellm` 작업 ①단계(켜기·재기동·키 회전·옛 키 삭제 뒤 점검) |
| ② | 경로 일원화 | 동기화는 원래 upstream을 등록, standalone은 출구가 MINT뿐 → 등록과 호출 분리 | `MINT_LITELLM_ROUTE`: `mint`(기본) = MINT `/mcp/<서버>/` + `oauth_delegate`, `direct` = 원래 주소 + `none` + 가드레일. A→B 전환 때 우리 `oauth_delegate`를 물려받지 않음(직원 토큰 upstream 전달 방지). 경로가 지문에 들어가 바꾸면 재전파. standalone은 A 전용 명시. A/B LiteLLM 설정 견본 | 단위: `test_route_a_registers_pass_through_auth_and_route_b_drops_it`, `desired` A/B. CI ②③·B 단계 |
| ③ | 정상 업무 통합 검수 | A: 승인 주체 아닌 root만, 도구 판정 0건. B: MINT 대역, context7 한도 오류 | CI: `deploy/` MINT + LiteLLM 1.105.0(digest) + Microsoft Learn MCP. 승인 직원 2명(`emp1`·`emp2`, AI 게이트웨이 전용) A 호출 → 결과 본문(>200자, 오류·한도 문구 아님) + 원장 `decisions`의 직원별 `Allow`·`upstream_executed`. MINT 토큰 없는 호출은 거절·새 Allow 없음 | `litellm_addon_e2e.py call-a` |
| ④ | 철회·복구 | 대역 21건뿐 | CI: 등록 해제 → LiteLLM 서버 사라짐·호출 거절·새 Allow 없음, 같은 공급자의 **관계없는 서버(`msdocs`)는 계속 성공** → 재신청·등록 → 성공. 재기동(`mint.sh up`) 뒤 유지 | `revoke`·`recover`·`restart-check` |
| ⑤ | 지속 재조회 | `verified`면 지문이 같을 때 외부 재조회 생략 | `MINT_LITELLM_SYNC_RECHECK_SECONDS`(기본 **300초**, 최소 30초)마다 읽기 전용 `observe`. 일치면 원장 기록 없이 시각만, 불일치면 `drift` 관측과 재전파(그때만 사건). CI는 30초로 두고 LiteLLM에서 키 권한을 지운 뒤 복구까지 시간을 잰다 | 단위 `test_verified_state_is_reread_and_drift_is_reported`, CI `drift` |
| ⑥ | 실패 영향 축소 | 활성 서버 전파 중 예외면 서버 삭제 → 다른 직원도 중단 | 키·팀 단위 오류(소유자 불일치·재조회 불일치·관리 API 오류)는 그 대상만 실패(`partial` 관측에 해시), 서버·다른 권한 유지. 서버 자체 불일치만 삭제 | 단위 `test_one_wrong_key_does_not_stop_the_other_employee`·`test_management_timeout_on_one_key_keeps_the_server`·`test_permissions_mismatch_fails_the_subject_not_the_server`, CI `isolation` |
| ⑦ | 설치·직원 연결 자동화 | YAML 수작업, 직원 이중 헤더, 키트 없는 직원은 토큰 불가 | 설치는 `mint.sh litellm`으로 자동. **AI 게이트웨이 전용 직원**(`add-account --ai-gateway`, D-250): 필드 기동이 관리형 PC 요구를 되살리지 않아 IdP 비밀번호 인증으로 자기 MCP 토큰을 받는다. **하네스 헤더 자동 구성(토큰 복사 없는 연결·만료 후 재연결)은 미구현** — Windows 시험 PC 실측도 미실행 | CI 계정 3명 생성·토큰 발급 |
| ⑧ | 판본·위생·관측 | standalone 판본은 로컬 pull digest, 기기 주소 예시·특정 컨테이너 기본값·시험 PC 주석, 프롬프트 저장 켬, 위생 검사 밖, `recorded:false` 무시 | LiteLLM 1.105.0·postgres·ollama·caddy digest 고정, 예시·기본값·주석 제거, 저장 기본 끔, `deploy/check.py`가 `addons/litellm`·`llm/standalone`·`integrations/litellm` 포함, 가드레일이 `recorded:false`를 경고 | `test_post_hook_reports_a_refused_record`, `deploy/check.py` |

**실제 1.105에서 새로 찾은 결함과 정정(D-249 6항)**: 동기화는 서버를 만들기 전에 `require_key_mcp_access_defined=true`를 `/config/field/info`로 읽었는데, 1.105 이미지는 이 필드를 `/config/field/*`에서 400(`Invalid field`)으로 거절한다. 대역 시험(D-208)은 200을 돌려줘 가려져 있었고, 실제 배치에서는 **동기화가 한 번도 서버를 만들 수 없었다.** 1.105 소스상 이 값은 자기 MCP 목록이 없는 키의 팀 권한 상속만 정하므로, 팀 매핑이 없으면 점검을 건너뛰고(`team-ceiling: no-team-grants`), 팀 매핑이 있으면 API로 읽히거나 운영자 확인(`MINT_LITELLM_KEY_ACCESS_CONFIRMED=1`) 때만 진행한다. 단위 시험 `test_team_ceiling_on_litellm_1_105_where_the_switch_is_not_readable` 추가.

**실제 MINT 원장에서 찾은 결함(같은 이유로 D-208 이후 동기화는 한 번도 완료되지 않았다)**: 동기화는 결과 사건을 `approval_events.outcome='verified'|'failed'`로 썼지만 원장 제약은 `recorded·approved·rejected·refused·held`만 받는다(`v2_tables.sql`). CI 3차 실행에서 LiteLLM 서버는 실제로 만들어졌지만 사건 기록이 매번 `CheckViolation`으로 실패해 작업이 `pending`에 머물렀다. 메모리 대역은 제약이 없어 가렸다. 결과는 `recorded`로 쓰고 상태는 `scope.state`에 담는다. 단위 시험의 원장 대역이 이제 같은 제약을 검사한다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 단위(동기화) | `tests/litellm_sync_check.py`, 로컬 venv, 10-25 | 26/26 통과(원장 outcome 제약 검사 포함). 새 8건 중 7건(경로·격리·재조회)은 이전 코드에서 실패(4 실패·3 오류)함을 확인 | 이 세션 출력 |
| 단위(애드온) | `tests/ai_gateway_addon_check.py` | 13/13 통과. `recorded:false` 시험은 이전 가드레일에서 실패 | 이 세션 출력 |
| 로컬 회귀 | `run_local_suite.py`(Windows venv) | 이 브랜치 실패 4(`acceptance_tls_check`·`output_credential_span_check`·`sbom_impact_check`·`threat_trace_mapping_check`) / 기준 4679160 실패 7(같은 4건 + `command_surfaces_check`·`dest_pin_credential_redaction_check`·`harness_detect_check`) → **새 실패 0**. `threat_trace_mapping_check`는 Windows 작업 트리 CRLF로 인한 해시 차이(손대지 않은 `review.py`에서도 남) | 이 세션 출력 |
| pyflakes | CI 정적 검사 목록 + `addons/litellm/*.py`·`deploy/check.py`·새 시험 | 0건 | 이 세션 출력 |
| 위키 | `refresh_generated.py`(위협 매핑·요구사항 코드 해시·저장소 스냅샷·보고서 색인·결정 색인), `check_wiki.py --ci-ignored-local-sources`·`check_trace.py`·`check_enterprise_analysis.py` | 재생성, 오류 0(`check_trace` 경고 5는 기존 참조 0 항목, 신선도 경고 3은 현황·백로그가 S3·리더 소유) | 이 세션 출력 |
| CI 1차 | [실행 40180032298](https://github.com/MCP-governance/mcp-gateway/actions/runs/40180032298) (b17454b) | 정적 통과. `litellm` 작업 실패: 1.105가 `require_key_mcp_access_defined` 필드 API를 400으로 거절 → 위 정정 | 작업 로그 |
| CI 2차 이후 | `full_stack_lab 검증 / LiteLLM 애드온 통합 검수`(이 브랜치 최신 커밋) | 결과는 아래 「CI 결과」에 덧붙임 | Actions |

## 실패·미완료·한계

- **⑦ 하네스 헤더 자동 구성 미구현.** 직원은 IdP에서 토큰을 받아 LiteLLM 호출 헤더에 넣어야 한다. 설계: 키트 헬퍼(`mcpgw-header`)처럼 갱신 토큰을 OS 비밀 저장소에 두고 `x-mcp-<서버>-authorization`을 출력하는 헤더 헬퍼를 하네스 관리형 설정(`headersHelper`)에 렌더링. Windows 시험 PC 실측 미실행.
- 다중 LiteLLM 워커·분산 캐시·세션 종료(`/v1/mcp/sessions`)의 실제 효과는 CI 단일 워커 범위다.
- B의 사람 승인은 차단으로 끝난다(D-191). 동기화는 관리 상태 관측이지 호출별 통제·종료 T1 증거가 아니다.
- AI 게이트웨이 전용 직원은 콘솔에서 따로 구분 표시되지 않는다. 비밀번호 인증 토큰은 장치에 결속되지 않는다(D-250 한계).
- `preflight.py`는 여전히 실제 LiteLLM 판본을 확인하지 않는다. 판본 확인은 CI 통합 검수(`/health/readiness`의 `litellm_version` 기록)가 맡는다.
- 실습 스택(`full_stack_lab/compose.yaml`)의 LiteLLM은 1.102.1 그대로다(모델 경로 실습용, 애드온 지원 판본과 별개).

## 다음 작업

- 리더: CI `litellm` 작업 통과 확인 뒤 병합. 기기 `mint-llm`에서 실제 운영 구성으로 한 번 더 보려면(솔루션 기기, 리더 실행):
  ```bash
  cd ~/mcp-gateway/deploy && ./mint.sh add-account <직원> --role 직원 --ai-gateway
  ./mint.sh litellm enable --url http://<mint-llm LiteLLM 관리 주소>:4000 --bindings ~/litellm-bindings.json --route mint < ~/litellm-admin.key
  ./mint.sh litellm status
  ```
  `mint-llm`의 standalone은 A 전용이므로 `--route mint`만 해당한다. 매핑의 `workers`에는 `mint-llm` LiteLLM 워커 origin 전체를 적는다.
- S1 또는 다음 세션: ⑦ 하네스 헤더 헬퍼, 콘솔의 AI 게이트웨이 전용 직원 표시.

## 사용자에게 필요한 입력

없음. (기기 `mint-llm` 실측은 리더 실행 명령으로 위에 적었다.)

## CI 결과

- [실행 40181172632](https://github.com/MCP-governance/mcp-gateway/actions/runs/40181172632) (fa28c53): ① 통과, 두 서버 실제 등록(READY), 동기화 사건이 원장 제약에 걸려 `pending` → 62bf87f에서 수정.
- [실행 40182011434](https://github.com/MCP-governance/mcp-gateway/actions/runs/40182011434) (62bf87f): **실제 LiteLLM 1.105 + 실제 MINT로 통과한 것** — 동기화 완료 learn 6.2초·msdocs 0.1초(LiteLLM 서버 `https://<MINT>/mcp/<서버>/`·`oauth_delegate`), 직원 2명 A 호출 성공(결과 36,966자·47,062자, `learn-microsoft_docs_search`), 원장 `decisions` 1·2번 = `emp-emp1`·`emp-emp2` `Allow` `P-AUTHZ-ALLOW-001` 실행, MINT 토큰 없는 호출은 도구 목록 자체가 비어 거절, LiteLLM에서 지운 키 권한을 재조회로 **15.1초** 만에 복구(재조회 30초 설정), 틀린 매핑(emp3) 중 emp1 호출 성공·작업은 `failed/key-owner-mismatch`, 관리 키 회전 뒤 옛 키 삭제·점검 통과, 철회 3.2초 뒤 learn 거절·새 Allow 없음·msdocs는 계속 성공. **실패**: 재승인 복구에서 동기화가 `key-owner-mismatch`로 완료되지 않음 — 매핑에서 뺀 옛 키가 보존 대상으로 남아 매번 오류, 철회 때 LiteLLM이 지운 서버를 키 권한에서 빼 버린 것을 재조회 불일치로 봄. 다음 커밋에서 두 경우를 정정(단위 `test_removed_mapping_and_stripped_revocation_do_not_block_completion`, 이전 코드에서 실패).
- [실행 40182906931](https://github.com/MCP-governance/mcp-gateway/actions/runs/40182906931) (68378ba): **A 경로 전 단계 통과** — 직원 2명 호출·원장 귀속, 재조회 복구 20.1초, 격리, 키 회전, 철회(3.1초, 동기화 `verified`)·관계없는 서버 유지, 재승인 복구 6.1초, 재기동 뒤 유지. **B 실패**: 동기화가 서버 주소를 `https://learn.microsoft.com/api/mcp`·`none`으로 바꾼 것은 확인했으나 도구가 목록에 없음 — 1.105가 `tools/list` 때 같은 사전 훅을 `list_mcp_tools`로 불러 도구 설명을 검사하는데(`tool_catalog_guard.py`) MINT 가드레일이 이를 호출로 보고 막아 3개 도구를 모두 숨겼다. 다음 커밋에서 목록 조회는 판정하지 않게 정정(단위 `test_tool_listing_scan_is_not_judged_as_a_call`).

