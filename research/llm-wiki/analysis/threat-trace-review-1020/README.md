# DEV-03 원본 위협표와 구현 추적 독립 검토

검토자: Codex sol · 기준: `22238b54f2a5ce1a18c19e0f3968658d264c6c72` · 2026-10-20

원본 PAC01~24(정책 최종본 5~28행)를 의미로 대조했다. 런타임 PAC-01~15·정책50과 번호로 대응시키지 않는다. 24행 모두 부분 근거가 있으며 전체 요구 충족·현재 배포 검수를 판정하지 않는다. 12건의 매핑 결함/오독 위험을 정정했고 제품 코드와 기존 시험은 변경하지 않았다.

## 정본·판본·검토 방법

[구조화 검토](review.json)는 원본 요구, 코드 심볼/행/파일 SHA-256, 회귀 범위, 증거 층과 정정 전 매핑을 보존한다. [카탈로그](../../catalogs/threats.json)와 [통제 지도](../../threats/control-map.md)는 `python research/llm-wiki/tools/map_threats.py`로 재생성한다. 심볼은 AST로 확인하고 함수 본문·호출 경계·시험 단언을 대조했다. 기존 매핑에는 심볼 자체가 없었으며 없는 파일/심볼 결함은 발견하지 않았다. 파일 존재만으로 통제 전체를 해석할 수 있는 범위는 아래에서 축소했다.

XLSM 원본 SHA-256: `c4ebd824cc8e355347ef0fc05b1cf866f621d05ff45352d30351c3827feb3141`. [보존 추출본](../../threats/extracted/policies.json)의 정책명·본문·행을 사용했다. 이번 XLSM 원본 바이트 재검증/매크로 실행/재저장은 하지 않았다. 정상·음성·경계·실패·경쟁·복구의 일부 시험을 여섯 조건 전체 또는 모든 MCP의 검수로 합산하지 않는다.

[아키텍처](../../../../docs/ai/ARCHITECTURE.md)·[경계](../../../../docs/ai/SECURITY_BOUNDARIES.md)·[정책](../../../../docs/ai/POLICY.md)·[결정](../../../../docs/ai/DECISIONS.md)과 기존 고정 SDK·OPA·[OSS 심층 비교](../oss-deep/README.md)를 재사용했다. 원격 GitHub HEAD 조회는 연결 실패였고 새 외부 스킬·OSS·의존성은 도입하지 않았다. 별도 D-번호가 지정되지 않아 새 번호를 만들지 않았다.

검토 결정: 관리대장 ID·제품 코드·회귀 시험을 구분한다. PG/OPA 함수 시험·실제 MCP·PJ1·독립 효과·현재 배포도 구분한다. 최초 실패/미실행과 후속 성공이 함께 있으면 마지막 추가 기록을 그 판본의 보고 증거로 채택하며 원시 출력 부재를 명시한다.

참조 파일과 검토 스냅샷 대조: 불일치 — 재검토 필요: endpoint-agent/managed-windows.py, full_stack_lab/gateway/app/agent_service.py, full_stack_lab/gateway/app/classify.py, full_stack_lab/gateway/app/core.py, full_stack_lab/gateway/app/dispatch.py, full_stack_lab/gateway/app/endpoint_plane.py, full_stack_lab/gateway/app/mcp_facade.py, full_stack_lab/gateway/app/review.py, full_stack_lab/runtime/worker.py, research/llm-wiki/status/reports/2026-10-20-poisoning-corpus.md. 파일 변경 시 생성기는 과거 심볼 행/해시를 갱신하지 않고 낡은 검토로 표시한다.

## 24개 정책별 대조

회귀 칸은 시험 소스의 범위이며 이번 실행 통과를 뜻하지 않는다. E번호는 아래의 당시 판본·수준·한계와 함께 읽는다.

| 원본·셀·정책 | 통제 위치·런타임 후보 | 코드 심볼·근거 행 | 회귀 시험·범위 | 실험/실기기 근거 | 남은 한계 |
| --- | --- | --- | --- | --- | --- |
| PAC01 · A5<br>배포물 출처와 무결성 확인 | 운영 절차 · 게이트웨이 · 실행기 · OPA<br>(MCP-SUPPLY-001) | [intake_gate:107](../../../../full_stack_lab/gateway/app/review.py#L107)<br>[validate:215](../../../../full_stack_lab/supply_chain/intake_worker.py#L215)<br>[fetch_source:301](../../../../full_stack_lab/runtime/worker.py#L301)<br>[build:330](../../../../full_stack_lab/runtime/worker.py#L330) | [test_provenance_records_source_commit_and_artifact_digest:148](../../../../full_stack_lab/tests/intake_validation_test.py#L148) — 커밋/배포물 해시 기록 대역<br>[test_scanner_outage_fails_closed:68](../../../../full_stack_lab/tests/intake_identity_test.py#L68) — 스캐너 장애 보류<br>[policy_test.rego:356](../../../../full_stack_lab/opa/policy_test.rego#L356) — 미승인 공급자 차단 | [E01](#e01) | 출처·미러 해시·스캔 결과와 승인 절차를 연결한다. 배포자 서명 신뢰/모든 의존성 출처 보증, 모든 도입 유형의 실기기 증거는 부족하다. 스캐너 시험 파일 자체는 공급망 집행 코드가 아니다. |
| PAC02 · A6<br>도입 범위와 필요 권한 검토 | 운영 절차 · 게이트웨이 · OPA<br>(PAC-01, PAC-08, PAC-09) | [approve_mcp_request:1402](../../../../full_stack_lab/gateway/app/agent_service.py#L1402)<br>[normalize_tool_reviews:211](../../../../full_stack_lab/gateway/app/review.py#L211)<br>[derived_constraints:265](../../../../full_stack_lab/gateway/app/review.py#L265)<br>[scope:69](../../../../full_stack_lab/gateway/app/pac.py#L69) | [test_every_approved_tool_needs_a_review_and_the_action_comes_from_the_approval:135](../../../../full_stack_lab/tests/intake_identity_test.py#L135) — 도구별 범위·행위 검토<br>[test_gaps_are_refused:143](../../../../full_stack_lab/tests/intake_identity_test.py#L143) — 심사 누락 거부 | [E01](#e01), [E19](#e19) | 필요 권한·목적·등급·목적지를 사람이 승인한다. 새 위험 등급은 신청자 입력의 표 산정이다. 적법 근거/고영향 해당 여부와 공급자 실제 권한은 사람의 확인이 필요하며 전체 도입 적정성을 자동 증명하지 않는다. |
| PAC03 · A7<br>연결 승인과 사용자 동의 확인 | 게이트웨이 · OPA · 운영 절차<br>(PAC-01, P-APPROVAL-EXPIRY-001, P-CONSENT-001) | [execute_call:1990](../../../../full_stack_lab/gateway/app/core.py#L1990)<br>[missing:33](../../../../full_stack_lab/gateway/app/consent.py#L33)<br>[for_dispatch:66](../../../../full_stack_lab/gateway/app/consent.py#L66)<br>[record:64](../../../../full_stack_lab/gateway/app/dispatch.py#L64) | [policy_test.rego:397](../../../../full_stack_lab/opa/policy_test.rego#L397) — 만료 차단<br>[policy_test.rego:403](../../../../full_stack_lab/opa/policy_test.rego#L403) — 유효기간 정상<br>[test_no_consent_leaves_a_request_and_blocks:140](../../../../full_stack_lab/tests/remaining_controls_check.py#L140) — 동의 없으면 보류<br>[consent_revoke_first:185](../../../../full_stack_lab/tests/dispatch_recheck_pg_check.py#L185) — 동의 철회 선커밋·intent 없음 | [E02](#e02), [E03](#e03) | 관리자 연결 승인과 본인 동의를 분리한다. consent=true 심사 도구에만 사용자 동의를 요구하므로 모든 연결의 포괄 동의를 뜻하지 않는다. 최종 intent 이후 철회가 이미 전송 가능한 호출의 외부 효과를 되돌리지는 않는다. |
| PAC04 · A8<br>실행 환경과 시험 데이터 관리 | OPA · 게이트웨이 · 실행기 · 운영 절차<br>(PAC-03) | [build:185](../../../../full_stack_lab/gateway/app/pac.py#L185)<br>[mcp_run_args:118](../../../../full_stack_lab/runtime/worker.py#L118)<br>[egress_run_args:132](../../../../full_stack_lab/runtime/worker.py#L132) | [runtime_worker_check.py:1](../../../../full_stack_lab/tests/runtime_worker_check.py#L1) — 읽기 전용/권한/자원·egress 실행 인자 단위 | [E01](#e01) | 환경 사실은 게이트웨이 환경 설정·capability 실행 프로필에서 생성된다. PAC-03 통과만으로 개발/시험/운영 망 분리·생성 데이터 사용·운영정보 승인/삭제를 증명하지 않는다. 실행기 격리 실증은 MarkItDown 한 레시피 범위다. |
| PAC05 · A9<br>실제 연결 주소 확인 | 게이트웨이 · OPA · 실행기<br>(PAC-07, MCP-EGRESS-001, MCP-EGRESS-002) | [PinnedBackend:14](../../../../full_stack_lab/gateway/app/destination.py#L14)<br>[_client:101](../../../../full_stack_lab/gateway/app/upstream.py#L101)<br>[http_transport:73](../../../../full_stack_lab/gateway/app/oidc.py#L73)<br>[host_category:274](../../../../full_stack_lab/gateway/app/classify.py#L274) | [dest_pin_transport_check.py:1](../../../../full_stack_lab/tests/dest_pin_transport_check.py#L1) — DNS 전체 검사·혼합 응답·직접 IP 고정 단위<br>[policy_test.rego:550](../../../../full_stack_lab/opa/policy_test.rego#L550) — 인자 SSRF 음성<br>[policy_test.rego:559](../../../../full_stack_lab/opa/policy_test.rego#L559) — 내부 정상 | [E01](#e01), [E10](#e10) | 직접 연결은 승인 origin·DNS 전체 검사 후 IP 고정, HTTP 리디렉션은 따르지 않는다. OIDC 설정 origin 예외와 서버가 자체 수행하는 outbound는 별도 경계다. 프록시 connected 사건은 최종 업무 수신·도구별 리디렉션/DNS 재결속 검증이 아니다. |
| PAC06 · A10<br>서버별 사용 기능 등록 | 게이트웨이 · OPA · 운영 절차<br>(MCP-CATALOG-001, PAC-08) | [_approved_tools:119](../../../../full_stack_lab/gateway/app/mcp_facade.py#L119)<br>[build_mcp:221](../../../../full_stack_lab/gateway/app/mcp_facade.py#L221)<br>[_contract:957](../../../../full_stack_lab/gateway/app/core.py#L957)<br>[reviewed_tools:139](../../../../full_stack_lab/gateway/app/registry.py#L139) | [contracts_check.py:1](../../../../full_stack_lab/tests/contracts_check.py#L1) — 고정 계약 파일 비교<br>[catalog_refresh_check.py:1](../../../../full_stack_lab/tests/catalog_refresh_check.py#L1) — 카탈로그 A→B→A 회귀<br>[drift_detection_and_isolation:99](../../../../full_stack_lab/tests/auto_suspend_pg_check.py#L99) — 제품 목록의 변경 도구 제한; 실제 DB 대기 | [E01](#e01), [E13](#e13), [E15](#e15) | 서버+도구 키와 승인 해시로 Tool 목록/호출을 제한한다. facade는 tools/list·tools/call만 등록하므로 Resource·Prompt 허용목록 구현으로 확대할 수 없다. 동명 기능 간 승인 비재사용의 실제 두 서버 교차 음성은 추가 검증 대상이다. |
| PAC07 · A11<br>게이트웨이 우회 연결 차단 | 엔드포인트 · 게이트웨이 · 운영 절차<br>(MCP-SHADOW-001, MCP-SHADOW-002, ENDPOINT-MANAGED-001) | [nft_rules:67](../../../../endpoint-agent/enforce-linux.py#L67)<br>[profile:92](../../../../endpoint-agent/enforce-linux.py#L92)<br>[wrapper:164](../../../../endpoint-agent/enforce-linux.py#L164)<br>[checks:351](../../../../endpoint-agent/managed-windows.py#L351)<br>[managed_failure:939](../../../../full_stack_lab/gateway/app/endpoint_plane.py#L939) | [managed_enforcement_check.py:1](../../../../full_stack_lab/tests/managed_enforcement_check.py#L1) — 관리 Linux 네트워크/실행 통제 검사<br>[launcher_pin_check.py:1](../../../../full_stack_lab/tests/launcher_pin_check.py#L1) — 하네스 설정 옵션 주입·Windows 복원 경계<br>[user_command_settings_check.py:1](../../../../full_stack_lab/tests/user_command_settings_check.py#L1) — 사용자 명령 헬퍼 탐지와 준수 보고 | [E08](#e08), [E09](#e09) | SHADOW 정책은 경보이고 직접 차단은 관리 OS 정책과 managed_failure가 맡는다. Linux PJ1 확인을 Windows/full-OS로 확대하지 않는다. Windows 원본 바이너리 직접 실행·loopback·하이브 미탑재 허용·검사 사이 경쟁과 구형 장치 전환 유예가 남는다. |
| PAC08 · A12<br>사용자와 에이전트 신원 확인 | 게이트웨이 · OPA<br>(PAC-04, ENDPOINT-MANAGED-001) | [authenticate:106](../../../../full_stack_lab/gateway/app/agent_contract.py#L106)<br>[authenticated_user:142](../../../../full_stack_lab/gateway/app/agent_contract.py#L142)<br>[build:185](../../../../full_stack_lab/gateway/app/pac.py#L185)<br>[active:21](../../../../full_stack_lab/gateway/app/mcp_sessions.py#L21) | [test_agent_identity_is_a_reported_source_and_never_verified:33](../../../../full_stack_lab/tests/pac_delegation_check.py#L33) — 하네스 자기 신고 신원은 미검증<br>[oauth_negative_pg_check.py:1](../../../../full_stack_lab/tests/oauth_negative_pg_check.py#L1) — 검증 토큰·현재 계정·scope 경계<br>[session_termination_check.py:1](../../../../full_stack_lab/tests/session_termination_check.py#L1) — 주체/장치 결속과 토큰 교체 | [E04](#e04), [E09](#e09), [E16](#e16) | 사용자는 전송 토큰·현재 계정으로 검증한다. agent_id는 고정 게이트웨이 broker이며 clientInfo/하네스 실행파일을 증명하지 않는다. 세션 결속은 주체/장치이고 실제 하네스 바이너리 원격 증명·업무 세션 전체 결합과 다르다. |
| PAC09 · A13<br>위임 범위와 유효기간 확인 | 게이트웨이 · OPA<br>(PAC-05, PAC-05-DELEGATION-UNSUPPORTED) | [delegation:30](../../../../full_stack_lab/gateway/app/pac.py#L30) | [test_a_forged_verified_flag_in_the_request_is_ignored:42](../../../../full_stack_lab/tests/pac_delegation_check.py#L42) — 요청의 검증 주장 무시<br>[policy_test.rego:700](../../../../full_stack_lab/opa/policy_test.rego#L700) — 자기 신고 위임 거부<br>[policy_test.rego:691](../../../../full_stack_lab/opa/policy_test.rego#L691) — 합성 verified actor 권한 교집합 | 실제 위임 검증 없음 | 대리 실행 주장에는 검증된 agent 신원이 없어 미지원 차단한다. 위임 없는 호출은 통과 가능하다. 위임 발급·유효기간·교집합의 Rego 합성 정상 시험은 실제 위임 체계 구현/실기기 증거가 아니다. 발급자·수명주기 도입은 결정 필요. |
| PAC10 · A14<br>OAuth 토큰 검증 | 게이트웨이 · OPA · 운영 절차<br>(PAC-06) | [authenticated_user:142](../../../../full_stack_lab/gateway/app/agent_contract.py#L142)<br>[introspection:299](../../../../full_stack_lab/gateway/app/idp.py#L299)<br>[credential_headers:40](../../../../full_stack_lab/gateway/app/upstream.py#L40) | [oauth_negative_pg_check.py:1](../../../../full_stack_lab/tests/oauth_negative_pg_check.py#L1) — 실제 서명/대상/scope/철회 음성<br>[credential_binding_check.py:1](../../../../full_stack_lab/tests/credential_binding_check.py#L1) — 별도 upstream 자격의 주체·대상·만료 경계 | [E04](#e04), [E05](#e05) | MCP 인입 mcp scope와 관리 API console scope를 구분하며 upstream에는 별도 자격만 구성한다. OAuth 음성 PG 시험은 실제 HTTP/MCP 전송·직원 토큰 미전달의 독립 관측이 아니다. 제공자 자격 scope/회전은 별도 공급자 정책 범위다. |
| PAC11 · A15<br>요청마다 실행 권한 확인 | 게이트웨이 · OPA<br>(PAC-09, PAC-14, P-CONTROL-FAIL-CLOSED, P-FLOW-001) | [execute_call:1990](../../../../full_stack_lab/gateway/app/core.py#L1990)<br>[_call_upstream:1465](../../../../full_stack_lab/gateway/app/core.py#L1465)<br>[_dispatch_flow_recheck:1213](../../../../full_stack_lab/gateway/app/core.py#L1213)<br>[record:64](../../../../full_stack_lab/gateway/app/dispatch.py#L64) | [test_db_lock_flow_and_commit_failures_never_send:374](../../../../full_stack_lab/tests/dispatch_recheck_check.py#L374) — 잠금/조회/commit 실패 차단<br>[account_update_first:138](../../../../full_stack_lab/tests/dispatch_recheck_pg_check.py#L138) — 중지 선커밋 차단<br>[test_jti_revoked_after_approval_before_dispatch:224](../../../../full_stack_lab/tests/fresh_requester_check.py#L224) — 승인 후 요청자 철회 | [E03](#e03), [E07](#e07), [E16](#e16) | 호출마다 정책 평가 후 라이브 계약/토큰/주체·동의/흐름과 intent를 재확인한다. PAC-09 하나가 전부를 수행하는 것은 아니다. intent commit과 실제 송신 사이 취소·이미 전송된 호출 회수·다중 인스턴스 장애 효과는 미검증이다. |
| PAC12 · A16<br>작업별 권한 구분 | 게이트웨이 · OPA<br>(PAC-09) | [classify:808](../../../../full_stack_lab/gateway/app/classify.py#L808)<br>[sql_facts:482](../../../../full_stack_lab/gateway/app/classify.py#L482)<br>[scope:69](../../../../full_stack_lab/gateway/app/pac.py#L69) | [main:6](../../../../full_stack_lab/tests/pac_boundary_check.py#L6) — 유한 SQL 허용·DELETE/다문장/권한 밖 거부<br>[policy_test.rego:674](../../../../full_stack_lab/opa/policy_test.rego#L674) — 승인 밖 작업 거부 | [E07](#e07) | 내부 행위는 r/w/x 3종이며 생성/수정/삭제는 w로 묶는다. SQL은 AST로 실효 행위를 올리지만 원격 Tool은 심사 행위를 신뢰한다. 원본 여섯 행위별 독립 권한이 모두 구현됐다고 볼 수 없다. |
| PAC13 · A17<br>입력값과 실행 대상 검사 | 게이트웨이 · OPA · 실행기<br>(P-INPUT-SCHEMA-001, PAC-10) | [execute_call:1990](../../../../full_stack_lab/gateway/app/core.py#L1990)<br>[_call_upstream:1465](../../../../full_stack_lab/gateway/app/core.py#L1465)<br>[build:185](../../../../full_stack_lab/gateway/app/pac.py#L185)<br>[path_resource:209](../../../../full_stack_lab/gateway/app/classify.py#L209) | [main:23](../../../../full_stack_lab/tests/schema_check.py#L23) — 스키마·인자 반례<br>[main:6](../../../../full_stack_lab/tests/pac_boundary_check.py#L6) — 정규화 경로와 중첩 인자<br>[dest_pin_transport_check.py:1](../../../../full_stack_lab/tests/dest_pin_transport_check.py#L1) — IP 정규화/주소 우회 반례 | [E01](#e01), [E07](#e07) | 승인 스키마와 라이브 스키마를 검사하고 파일/명령/수신자를 결속한다. 일반 원격 서버의 실제 객체 해석·파일 symlink·서버 내부 명령 효과를 모두 증명하지는 않는다. 알려진 추출기 밖은 심사 스키마/실행기 경계에 의존한다. |
| PAC14 · A18<br>데이터별 접근권한 확인 | 게이트웨이 · OPA · 운영 절차<br>(P-CLASSIFICATION-001, PAC-11) | [path_resource:209](../../../../full_stack_lab/gateway/app/classify.py#L209)<br>[table_resource:538](../../../../full_stack_lab/gateway/app/classify.py#L538)<br>[classify:808](../../../../full_stack_lab/gateway/app/classify.py#L808)<br>[scope:69](../../../../full_stack_lab/gateway/app/pac.py#L69) | [policy_test.rego:381](../../../../full_stack_lab/opa/policy_test.rego#L381) — 분류 근거 없음 차단<br>[policy_test.rego:386](../../../../full_stack_lab/opa/policy_test.rego#L386) — 수동 분류 정상<br>[main:6](../../../../full_stack_lab/tests/pac_boundary_check.py#L6) — 자원·권한 범위 거부 | [E07](#e07) | 미지 자산을 important로 분류하는 것과 자산 미확인 시 항상 차단은 다르다. 내장 경로/테이블 규칙과 원격 서비스 수동 등급에 의존한다. 현재 agent 독립 위임권한이 없고 모든 데이터 자산이 독립 등록돼 있다는 증거도 없다. |
| PAC15 · A19<br>외부 전송 대상과 데이터 확인 | 게이트웨이 · OPA · 실행기 · 운영 절차<br>(MCP-DATA-EGRESS-001, PAC-12, P-CONSENT-001, P-CHAIN-001, P-FLOW-001, P-RESIDENCY-001, P-RESIDENCY-002) | [transfer_binding:165](../../../../full_stack_lab/gateway/app/pac.py#L165)<br>[execute_call:1990](../../../../full_stack_lab/gateway/app/core.py#L1990)<br>[_flow_sources:1181](../../../../full_stack_lab/gateway/app/core.py#L1181)<br>[missing:33](../../../../full_stack_lab/gateway/app/consent.py#L33) | [test_reviewed_destination_on_a_runtime_server_is_bound_to_purpose_and_grade:70](../../../../full_stack_lab/tests/remaining_controls_check.py#L70) — 심사 목적·목적지·등급 결속<br>[test_anything_else_fails_closed:77](../../../../full_stack_lab/tests/remaining_controls_check.py#L77) — 최종 목적지 불확실 거부<br>[policy_test.rego:1277](../../../../full_stack_lab/opa/policy_test.rego#L1277) — 저장국 누락 우회 거부<br>[flow_publication_first:253](../../../../full_stack_lab/tests/dispatch_recheck_pg_check.py#L253) — 새 흐름 출처 선게시 차단 | [E02](#e02), [E03](#e03), [E10](#e10), [E18](#e18) | 실행기 프록시의 서버 전체 허용 호스트가 도구 심사 안에 들어가야 최종 목적지로 인정한다. 제3자 SaaS outbound·재시도/자격·독립 수신은 미관측이다. 국가/법적 근거는 선언·잠정 규칙이며 개인정보 적법성 확인 자동화가 아니다. LLM 모델 프롬프트 경로는 별도다. |
| PAC16 · A20<br>민감한 작업의 개별 승인 | 게이트웨이 · OPA · 운영 절차<br>(PAC-13, P-HIGH-IMPACT-001) | [approve_request:2319](../../../../full_stack_lab/gateway/app/core.py#L2319)<br>[digest:151](../../../../full_stack_lab/gateway/app/pac.py#L151)<br>[bound:45](../../../../full_stack_lab/gateway/app/high_impact.py#L45)<br>[record:64](../../../../full_stack_lab/gateway/app/dispatch.py#L64) | [test_self_approval_and_expiry_do_not_execute:160](../../../../full_stack_lab/tests/high_impact_check.py#L160) — 자가 승인/만료 거부<br>[test_concurrent_claim_loser_does_not_execute:170](../../../../full_stack_lab/tests/high_impact_check.py#L170) — 경쟁 패자 미실행<br>[test_approval_binds_every_request_field_scope_and_integrity:84](../../../../full_stack_lab/tests/high_impact_check.py#L84) — 요청 필드·범위 결속<br>[test_jti_revoked_after_approval_before_dispatch:224](../../../../full_stack_lab/tests/fresh_requester_check.py#L224) — 요청자 철회 재확인 | [E07](#e07), [E19](#e19), [E16](#e16) | reservation_effect_check는 호출량/중복 시험이라 이 행에서 제거했다. 설명 열람·고용/신용 등 중대 영향은 새 대역 근거다. 모든 민감 작업의 지정 완전성, PJ1 실제 중대 영향 승인·외부 효과, 긴 승인 대기 중 토큰 만료의 사용성은 미검증이다. |
| PAC17 · A21<br>호출량과 실행 시간 제한 | 게이트웨이 · OPA<br>(P-RATE-001, P-RATE-002, P-RATE-003, PAC-15) | [_reserve_call:1275](../../../../full_stack_lab/gateway/app/core.py#L1275)<br>[execute_call:1990](../../../../full_stack_lab/gateway/app/core.py#L1990)<br>[record:64](../../../../full_stack_lab/gateway/app/dispatch.py#L64) | [race:47](../../../../full_stack_lab/tests/reservation_effect_check.py#L47) — 실제 PostgreSQL MCP 동시 상한/중복·업무 DB 효과 관측용<br>[policy_test.rego:431](../../../../full_stack_lab/opa/policy_test.rego#L431) — 빈도 상한<br>[policy_test.rego:454](../../../../full_stack_lab/opa/policy_test.rego#L454) — 동시 정확 경계<br>[completed_ttl_and_scope:53](../../../../full_stack_lab/tests/dispatch_idempotency_pg_check.py#L53) — 완료 TTL/주체·인자 독립성; 실제 DB 대기 | [E07](#e07), [E12](#e12) | 주체별 예약/동시 상한과 dispatch 시간 예산, 완료 변경 이력 TTL을 구분한다. 서버/기능/독립 agent별 상한을 모두 제공하지 않는다. 대기 종료는 원격 실행 강제 취소가 아니며 새 TTL PG 시험은 미실행이다. |
| PAC18 · A22<br>외부 콘텐츠를 이용한 권한 변경 차단 | 게이트웨이 · OPA · 엔드포인트<br>(P-UNTRUSTED-CONTENT-001, P-UNTRUSTED-CONTENT-002, MCP-CATALOG-001) | [findings:321](../../../../full_stack_lab/gateway/app/poisoning.py#L321)<br>[result_findings:301](../../../../full_stack_lab/gateway/app/poisoning.py#L301)<br>[untrusted_markers:1071](../../../../full_stack_lab/gateway/app/core.py#L1071)<br>[execute_call:1990](../../../../full_stack_lab/gateway/app/core.py#L1990) | [poisoning_corpus_check.py:1](../../../../full_stack_lab/tests/poisoning_corpus_check.py#L1) — 계약 전용 해독·오탐·평가 분리 순수 회귀<br>[policy_test.rego:1123](../../../../full_stack_lab/opa/policy_test.rego#L1123) — 표지 기반 고위험 승인<br>[test_a_forged_verified_flag_in_the_request_is_ignored:42](../../../../full_stack_lab/tests/pac_delegation_check.py#L42) — 외부 검증 주장 신뢰 금지 | [E11](#e11) | 권한 원천은 토큰/등록부이고 외부 텍스트로 확장하지 않는다. 표지·정규식/해독 탐지는 의미적 주입 탐지와 다르다. 공개 재현율 미측정·독립 다국어 정상/공격군 부족·LLM 내부 판단은 범위 밖이다. |
| PAC19 · A23<br>도구 입력의 민감정보 제한 | 게이트웨이 · 운영 절차<br>(P-INPUT-FIELD-001, P-DATA-INSPECTION-001, P-DLP-001, MCP-DATA-EGRESS-001) | [execute_call:1990](../../../../full_stack_lab/gateway/app/core.py#L1990)<br>[check_inputs:256](../../../../full_stack_lab/gateway/app/review.py#L256)<br>[mask_payload:173](../../../../full_stack_lab/gateway/app/privacy.py#L173)<br>[labels:74](../../../../full_stack_lab/gateway/app/secret_scan.py#L74) | [test_narrowed_inputs_close_the_schema:50](../../../../full_stack_lab/tests/remaining_controls_check.py#L50) — 허용 항목 축소<br>[test_unknown_or_required_inputs_are_refused:58](../../../../full_stack_lab/tests/remaining_controls_check.py#L58) — 알 수 없는/필수 입력 처리<br>[test_missing_scanner_fails_closed:110](../../../../full_stack_lab/tests/oss_audit_test.py#L110) — 실제 검사기 부재 차단 | [E02](#e02) | 스캐너 장애 정책만으로 최소수집을 증명하지 않는다. 허용 항목·선택 마스킹·잔존 재검사를 함께 연결했다. 모든 내부 읽기 입력을 전수 비밀 검사하지 않으며 미탐·업무 필요 항목의 의미 심사는 남는다. |
| PAC20 · A24<br>응답의 민감정보 노출 제한 | 게이트웨이<br>(MCP-OUTPUT-001) | [_guarded_result:1756](../../../../full_stack_lab/gateway/app/core.py#L1756)<br>[_inspected_result:1787](../../../../full_stack_lab/gateway/app/core.py#L1787)<br>[mask_payload:173](../../../../full_stack_lab/gateway/app/privacy.py#L173)<br>[redact_error:97](../../../../full_stack_lab/gateway/app/secret_scan.py#L97)<br>[_render:172](../../../../full_stack_lab/gateway/app/mcp_facade.py#L172) | [mcp_result_contract_check.py:1](../../../../full_stack_lab/tests/mcp_result_contract_check.py#L1) — SDK content·structuredContent 보존/출력 보류<br>[response_cap_boundary_check.py:1](../../../../full_stack_lab/tests/response_cap_boundary_check.py#L1) — 바이트/건수 경계·마스킹 후 증가<br>[dest_pin_credential_redaction_check.py:1](../../../../full_stack_lab/tests/dest_pin_credential_redaction_check.py#L1) — 오류/인자/원장의 자격 비노출 | [E15](#e15) | 응답 전체를 받은 뒤 크기·출력 계약·민감정보를 검사/가린다. 결과 보류도 upstream 실행은 이미 일어났다. D-117만의 로컬 한계를 전체 최신 출력 경로로 일반화하지 않는다. 현재 HEAD 실제 검사기/SDK·큰 응답 PJ1·권한별 출력 의미 검사는 미검증이다. |
| PAC21 · A25<br>구성 변경 검토와 재승인 | 운영 절차 · 게이트웨이 · OPA<br>(MCP-CATALOG-001, PAC-02) | [refresh_catalog:201](../../../../full_stack_lab/gateway/app/core.py#L201)<br>[approve_contract:367](../../../../full_stack_lab/gateway/app/core.py#L367)<br>[tool_hashes:268](../../../../full_stack_lab/gateway/app/registry.py#L268)<br>[review_matches:274](../../../../full_stack_lab/gateway/app/registry.py#L274) | [catalog_refresh_check.py:1](../../../../full_stack_lab/tests/catalog_refresh_check.py#L1) — A→B→A 계약 회귀<br>[output_contract_check.py:1](../../../../full_stack_lab/tests/output_contract_check.py#L1) — 출력 스키마 승인/협상 판본<br>[d149_transition_check.py:1](../../../../full_stack_lab/tests/d149_transition_check.py#L1) — NULL 전환·재승인 사건<br>[drift_detection_and_isolation:99](../../../../full_stack_lab/tests/auto_suspend_pg_check.py#L99) — 도구별 제한과 무관한 도구 보존; 실제 DB 대기 | [E13](#e13), [E15](#e15) | 설명/입력/출력 해시·버전/정책 기준을 비교한다. 옛 NULL 출력 해시는 스키마 부재 계약으로 유지하며 첫 관측 스키마를 승인하지 않는다. 새 PostgreSQL 선택 제한·출력 재승인/PJ1 복구 미실행, 라이선스/권한·공급자 내부 변경의 모든 감지는 보장하지 않는다. |
| PAC22 · A26<br>호출과 권한 변경 이력 관리 | 게이트웨이 · 엔드포인트 · 운영 절차<br>(정책 ID 없음) | [_record_decision:1824](../../../../full_stack_lab/gateway/app/core.py#L1824)<br>[_audit_payload:1804](../../../../full_stack_lab/gateway/app/core.py#L1804)<br>[verify_audit_chain:1955](../../../../full_stack_lab/gateway/app/core.py#L1955)<br>[export:84](../../../../full_stack_lab/gateway/app/audit.py#L84)<br>[set_setting:98](../../../../full_stack_lab/gateway/app/retention.py#L98) | [test_admin_boundary_and_limits:27](../../../../full_stack_lab/tests/oss_audit_test.py#L27) — 감사 조회 관리자 경계<br>[test_below_floor_is_refused_and_the_longest_floor_wins:57](../../../../full_stack_lab/tests/ledger_retention_check.py#L57) — 보존 하한<br>[main:82](../../../../full_stack_lab/tests/policy_selftest_pg_check.py#L82) — 실제 OPA/DB 자체 시험·합성 경보 분리<br>[endpoint_evidence_pg_check.py:1](../../../../full_stack_lab/tests/endpoint_evidence_pg_check.py#L1) — 감사 UPDATE 거부·장치 사건 결속 PG | [E06](#e06), [E10](#e10), [E14](#e14) | append-only audit는 정책 ID가 아니므로 runtime 목록에서 제거했다. SHA 사슬·DB 트리거·접근제어는 보존·정기 권한 검토·전체 비노출과 다르다. 원장 요청 본문/개인정보 보관과 최소화 충돌, DB 소유자 재계산, 삭제/봉인 절차와 주변 표 보존은 결정 필요다. |
| PAC23 · A27<br>권한 철회와 연결 해제 | 게이트웨이 · OPA · 엔드포인트 · 실행기 · 운영 절차<br>(MCP-DECOMM-001, PAC-14) | [open_case:221](../../../../full_stack_lab/gateway/app/decommission.py#L221)<br>[assess:715](../../../../full_stack_lab/gateway/app/decommission.py#L715)<br>[terminate:50](../../../../full_stack_lab/gateway/app/mcp_sessions.py#L50)<br>[reconcile:504](../../../../full_stack_lab/runtime/worker.py#L504)<br>[deregister_server:748](../../../../full_stack_lab/gateway/app/core.py#L748) | [termination_flow.py:1](../../../../full_stack_lab/tests/termination_flow.py#L1) — C1~C4·T1~T3 live 회귀용; 이번 미실행<br>[session_termination_check.py:1](../../../../full_stack_lab/tests/session_termination_check.py#L1) — 주체/장치 세션 종료·토큰 교체<br>[resource_residual_check.py:1](../../../../full_stack_lab/tests/resource_residual_check.py#L1) — 실행기 제거 재시도·자원 수락 우선<br>[policy_test.rego:979](../../../../full_stack_lab/opa/policy_test.rego#L979) — 종료 중 호출 거부 | [E07](#e07), [E05](#e05), [E13](#e13), [E17](#e17) | DB 경계 종료·설정/경로 제거·프로세스 제거·자원 거부를 분리한다. 집계 MCP 세션은 한 서버 종료로 전체 종료하지 않는다. 실제 지속 세션/실행기 잔존·Windows·현재 PJ1 종료 재접근은 미검증이다. 설정 소멸은 C4 상태 증거 일부이며 외부 효과 철회 증거가 아니다. |
| PAC24 · A28<br>토큰과 API 키 회수 | 게이트웨이 · 운영 절차 · 실행기<br>(PAC-14) | [revoke_principal_tokens:237](../../../../full_stack_lab/gateway/app/idp.py#L237)<br>[revoke_device_tokens:257](../../../../full_stack_lab/gateway/app/idp.py#L257)<br>[introspection:299](../../../../full_stack_lab/gateway/app/idp.py#L299)<br>[remember_token:157](../../../../full_stack_lab/gateway/app/disposal.py#L157)<br>[_judge_target:626](../../../../full_stack_lab/gateway/app/decommission.py#L626) | [restore_residual_pg_check.py:1](../../../../full_stack_lab/tests/restore_residual_pg_check.py#L1) — DB 복원 뒤 access/refresh/등록/관리 설정 잔존<br>[resource_residual_check.py:1](../../../../full_stack_lab/tests/resource_residual_check.py#L1) — 발급자 inactive와 자원 수락 충돌<br>[residual_sequence:128](../../../../full_stack_lab/tests/resource_residual_pg_check.py#L128) — 격리 Gitea PAT 자원 재접근; 미실행 | [E05](#e05), [E07](#e07), [E17](#e17) | C3/C4는 종료 판정 기준이며 런타임 정책 ID에서 분리했다. DB 밖 서명 기록이 복원된 자격을 막지만 DB+서명 볼륨/키 동시 복원·외부 JWT 캐시·복제/미고지 공급자 자격은 보장하지 않는다. D-154 회전 순서 후보 수용과 새 자원 서버 시험은 별도다. |

## 오류·누락·과대 해석 위험

매핑 결함을 제품 기능의 전체 부재로 자동 환산하지 않는다. 정정 전 값은 review.json에 보존했다.

| ID·원본 | 유형·기존 문제 | 정정·남긴 판단 | 근거 행 | 상태 |
| --- | --- | --- | --- | --- |
| F01 · PAC01 | 통제 위치 누락: 스캐너 시험 한 파일만 집행 코드 후보로 등록 | review.intake_gate·intake_worker.validate·실행기 소스/빌드 심볼로 교체하고 시험은 별도 필드로 이동 | [intake_gate:107](../../../../full_stack_lab/gateway/app/review.py#L107)<br>[validate:215](../../../../full_stack_lab/supply_chain/intake_worker.py#L215)<br>[fetch_source:301](../../../../full_stack_lab/runtime/worker.py#L301)<br>[build:330](../../../../full_stack_lab/runtime/worker.py#L330) | 수정 |
| F02 · PAC03 | 통제/증거 누락: 승인·만료만 연결하고 사용자 동의는 필요한 별도 증거라고만 기재 | P-CONSENT-001·동의 함수·PJ1/PG 철회 선후 근거 연결 | [execute_call:1990](../../../../full_stack_lab/gateway/app/core.py#L1990)<br>[missing:33](../../../../full_stack_lab/gateway/app/consent.py#L33)<br>[for_dispatch:66](../../../../full_stack_lab/gateway/app/consent.py#L66)<br>[record:64](../../../../full_stack_lab/gateway/app/dispatch.py#L64) | 수정 |
| F03 · PAC04 | 통제 범위 오독 위험: PAC-03 Rego 파일만 있어 환경 플래그를 실제 분리로 읽을 수 있음 | 실행기 격리와 운영 데이터/삭제 절차 공백을 분리 | [build:185](../../../../full_stack_lab/gateway/app/pac.py#L185)<br>[mcp_run_args:118](../../../../full_stack_lab/runtime/worker.py#L118)<br>[egress_run_args:132](../../../../full_stack_lab/runtime/worker.py#L132) | 수정 |
| F04 · PAC05 | 직접 연결 통제 누락: DNS 전체 검사·IP 고정이라고 적었지만 destination.PinnedBackend는 후보 파일에서 누락 | 연결 경계 심볼·테스트 추가; 서버 outbound와 구별; PAC-07 추가 | [PinnedBackend:14](../../../../full_stack_lab/gateway/app/destination.py#L14)<br>[_client:101](../../../../full_stack_lab/gateway/app/upstream.py#L101)<br>[http_transport:73](../../../../full_stack_lab/gateway/app/oidc.py#L73)<br>[host_category:274](../../../../full_stack_lab/gateway/app/classify.py#L274) | 수정 |
| F05 · PAC06 | 원본 요구 범위 누락: 도구 계약이라고만 요약해 원본 Tool/Resource/Prompt 차이가 사라짐 | 현재 facade tools 전용 근거를 명시, Resource/Prompt 지원 여부는 결정 필요 | [_approved_tools:119](../../../../full_stack_lab/gateway/app/mcp_facade.py#L119)<br>[build_mcp:221](../../../../full_stack_lab/gateway/app/mcp_facade.py#L221)<br>[_contract:957](../../../../full_stack_lab/gateway/app/core.py#L957)<br>[reviewed_tools:139](../../../../full_stack_lab/gateway/app/registry.py#L139) | 수정·결정 필요 |
| F06 · PAC08, PAC09 | 증거 과대 해석 위험: 신원/위임이라는 요약과 교집합 시험 계획만 있어 실제 actor 신원/위임 지원으로 오독 가능 | 고정 broker·verified=false·미지원 차단과 합성 Rego 정상군을 구별 | [authenticate:106](../../../../full_stack_lab/gateway/app/agent_contract.py#L106)<br>[authenticated_user:142](../../../../full_stack_lab/gateway/app/agent_contract.py#L142)<br>[build:185](../../../../full_stack_lab/gateway/app/pac.py#L185)<br>[active:21](../../../../full_stack_lab/gateway/app/mcp_sessions.py#L21)<br>[delegation:30](../../../../full_stack_lab/gateway/app/pac.py#L30) | 수정·결정 필요 |
| F07 · PAC12 | 원본 행위 세분화 미반영: 실제 효과로 분류한다고만 적고 원본 여섯 행위와 r/w/x 집약 차이 없음 | 생성/수정/삭제가 w라는 실제 범위·미지원 권한 세분화 명시 | [classify:808](../../../../full_stack_lab/gateway/app/classify.py#L808)<br>[sql_facts:482](../../../../full_stack_lab/gateway/app/classify.py#L482)<br>[scope:69](../../../../full_stack_lab/gateway/app/pac.py#L69) | 수정·결정 필요 |
| F08 · PAC16 | 정책과 무관한 시험 연결: reservation_effect_check.py를 개별 승인 근거로 연결 | 해당 race는 P-RATE-002/003 동시/중복 효과 시험. PAC17에 유지하고 PAC16은 승인·지문·경쟁·철회 시험으로 교체 | [approve_request:2319](../../../../full_stack_lab/gateway/app/core.py#L2319)<br>[race:47](../../../../full_stack_lab/tests/reservation_effect_check.py#L47) | 수정 |
| F09 · PAC19 | 통제 위치 누락: privacy/secret_scan과 검사 불능 정책만 연결해 허용 항목·최소화 구현 빠짐 | core 입력 항목·review.check_inputs·선택 마스킹·잔존 검사·PJ1 근거 추가 | [execute_call:1990](../../../../full_stack_lab/gateway/app/core.py#L1990)<br>[check_inputs:256](../../../../full_stack_lab/gateway/app/review.py#L256)<br>[mask_payload:173](../../../../full_stack_lab/gateway/app/privacy.py#L173)<br>[labels:74](../../../../full_stack_lab/gateway/app/secret_scan.py#L74) | 수정 |
| F10 · PAC20, PAC21 | 판본/실행 범위 표류: D-117 로컬 회귀 한계와 입출력 변경/재승인 이후 사실이 구분되지 않음 | 현재 출력 계약/NULL 전환·미실행 DB/PJ1과 과거 범위를 명시 | [_guarded_result:1756](../../../../full_stack_lab/gateway/app/core.py#L1756)<br>[_inspected_result:1787](../../../../full_stack_lab/gateway/app/core.py#L1787)<br>[mask_payload:173](../../../../full_stack_lab/gateway/app/privacy.py#L173)<br>[redact_error:97](../../../../full_stack_lab/gateway/app/secret_scan.py#L97)<br>[_render:172](../../../../full_stack_lab/gateway/app/mcp_facade.py#L172)<br>[refresh_catalog:201](../../../../full_stack_lab/gateway/app/core.py#L201)<br>[approve_contract:367](../../../../full_stack_lab/gateway/app/core.py#L367)<br>[tool_hashes:268](../../../../full_stack_lab/gateway/app/registry.py#L268)<br>[review_matches:274](../../../../full_stack_lab/gateway/app/registry.py#L274) | 수정 |
| F11 · PAC22, PAC24 | 식별자 유형 혼합: append-only audit와 C3/C4를 런타임 정책 후보 배열에 넣음 | 관리대장에 존재하는 ID만 유지. 감사는 통제·C3/C4는 판정 기준으로 별도 설명 | [_record_decision:1824](../../../../full_stack_lab/gateway/app/core.py#L1824)<br>[_audit_payload:1804](../../../../full_stack_lab/gateway/app/core.py#L1804)<br>[verify_audit_chain:1955](../../../../full_stack_lab/gateway/app/core.py#L1955)<br>[export:84](../../../../full_stack_lab/gateway/app/audit.py#L84)<br>[set_setting:98](../../../../full_stack_lab/gateway/app/retention.py#L98)<br>[revoke_principal_tokens:237](../../../../full_stack_lab/gateway/app/idp.py#L237)<br>[revoke_device_tokens:257](../../../../full_stack_lab/gateway/app/idp.py#L257)<br>[introspection:299](../../../../full_stack_lab/gateway/app/idp.py#L299)<br>[remember_token:157](../../../../full_stack_lab/gateway/app/disposal.py#L157)<br>[_judge_target:626](../../../../full_stack_lab/gateway/app/decommission.py#L626) | 수정 |
| F12 · PAC07, PAC11, PAC15, PAC17, PAC22, PAC23, PAC24 | 실험/실기기 증거 미연결: 새 실제 PostgreSQL/OPA·PJ1 보고와 미실행 시험을 목록/범위로 구분할 수 없음 | E01~E19의 판본·층·미실행·대역/독립 효과를 연결, 280/280 등을 MCP 전체 성공으로 전용 금지 | [nft_rules:67](../../../../endpoint-agent/enforce-linux.py#L67)<br>[profile:92](../../../../endpoint-agent/enforce-linux.py#L92)<br>[wrapper:164](../../../../endpoint-agent/enforce-linux.py#L164)<br>[checks:351](../../../../endpoint-agent/managed-windows.py#L351)<br>[managed_failure:939](../../../../full_stack_lab/gateway/app/endpoint_plane.py#L939)<br>[execute_call:1990](../../../../full_stack_lab/gateway/app/core.py#L1990)<br>[_call_upstream:1465](../../../../full_stack_lab/gateway/app/core.py#L1465)<br>[_dispatch_flow_recheck:1213](../../../../full_stack_lab/gateway/app/core.py#L1213)<br>[record:64](../../../../full_stack_lab/gateway/app/dispatch.py#L64)<br>[transfer_binding:165](../../../../full_stack_lab/gateway/app/pac.py#L165)<br>[execute_call:1990](../../../../full_stack_lab/gateway/app/core.py#L1990)<br>[_flow_sources:1181](../../../../full_stack_lab/gateway/app/core.py#L1181)<br>[missing:33](../../../../full_stack_lab/gateway/app/consent.py#L33)<br>[_reserve_call:1275](../../../../full_stack_lab/gateway/app/core.py#L1275)<br>[execute_call:1990](../../../../full_stack_lab/gateway/app/core.py#L1990)<br>[record:64](../../../../full_stack_lab/gateway/app/dispatch.py#L64)<br>[_record_decision:1824](../../../../full_stack_lab/gateway/app/core.py#L1824)<br>[_audit_payload:1804](../../../../full_stack_lab/gateway/app/core.py#L1804)<br>[verify_audit_chain:1955](../../../../full_stack_lab/gateway/app/core.py#L1955)<br>[export:84](../../../../full_stack_lab/gateway/app/audit.py#L84)<br>[set_setting:98](../../../../full_stack_lab/gateway/app/retention.py#L98)<br>[open_case:221](../../../../full_stack_lab/gateway/app/decommission.py#L221)<br>[assess:715](../../../../full_stack_lab/gateway/app/decommission.py#L715)<br>[terminate:50](../../../../full_stack_lab/gateway/app/mcp_sessions.py#L50)<br>[reconcile:504](../../../../full_stack_lab/runtime/worker.py#L504)<br>[deregister_server:748](../../../../full_stack_lab/gateway/app/core.py#L748)<br>[revoke_principal_tokens:237](../../../../full_stack_lab/gateway/app/idp.py#L237)<br>[revoke_device_tokens:257](../../../../full_stack_lab/gateway/app/idp.py#L257)<br>[introspection:299](../../../../full_stack_lab/gateway/app/idp.py#L299)<br>[remember_token:157](../../../../full_stack_lab/gateway/app/disposal.py#L157)<br>[_judge_target:626](../../../../full_stack_lab/gateway/app/decommission.py#L626) | 수정 |

## 실험·실기기 증거 목록

E03~E06의 실제 PostgreSQL/OPA 통과 수치는 후속 보고를 확인한 것이다. 이번 독립 재실행 수치가 아니며 보고서에 원시 실행 JSON이 없어 재계산하지 못했다. E02는 [보존 원장](../controls-1018/device-e2e.json), E01은 [실행기 기록](../wbs-1015/dev38-runtime.json), E07은 [실험실 기록](../wbs-1015/lab-results.jsonl)과 대조했다.

### E01

[2026-10-15-dev38-runtime.md:35](../../../../research/llm-wiki/status/reports/2026-10-15-dev38-runtime.md#L35) · 솔루션 기기·PJ1 실제 OSS MCP

b639432: MarkItDown 격리 플래그·egress 5종, PJ1 정상/범위 밖, 중복 시작·SIGKILL·이미지 교체·재실행 기록.

한계: 10-15 당시 판본. 빌드 중 승인 철회/등록 해제/종료 실기기 미확인. 실제 리디렉션 MCP 사례 없음.

### E02

[2026-10-18-remaining-controls.md:39](../../../../research/llm-wiki/status/reports/2026-10-18-remaining-controls.md#L39) · PJ1 실제 관리 Codex·기존 OSS MCP

4857adc: Context7 입력 마스킹 #30→31/37, MarkItDown 목적 결속 #34/35, 동의 #32→33→36.

한계: 별도 device-e2e.json과 대조. Context7은 할당량 오류로 정상 업무 성공 아님. 서버 간 중요정보 전달 실기기 미실행. 현재 HEAD 재실행 아님.

### E03

[2026-10-20-dispatch-recheck-pg.md:25](../../../../research/llm-wiki/status/reports/2026-10-20-dispatch-recheck-pg.md#L25) · 격리 실제 PostgreSQL·제품 함수

최종 추가 기록: 계정/동의/흐름 여섯 순서와 무작위 30회, 280/280을 두 번, 교착 0.

한계: 앞선 장벽/fixture 실패를 최종 추가 기록이 대체. 합성 중요 읽기, 실제 MCP/독립 효과/PJ1 미확인; 원시 실행 JSON 미첨부.

### E04

[2026-10-20-oauth-negative.md:55](../../../../research/llm-wiki/status/reports/2026-10-20-oauth-negative.md#L55) · 격리 실제 PostgreSQL·IdP·MCP 인증 함수

정상과 audience/scope/만료/철회/키/알고리즘 음성 11/11. 실제 콘솔 세션 토큰 사례와 scope 제거 변이 실패.

한계: MCP 전송 없음. dispatch intent 0은 외부 효과 0의 독립 관측 아님; 원시 실행 JSON 미첨부.

### E05

[2026-10-20-restore-residual.md:57](../../../../research/llm-wiki/status/reports/2026-10-20-restore-residual.md#L57) · 격리 실제 PostgreSQL·Gitea 관리 API

최종 추가 기록: 복원 잔존 10/10, idp 서명 기록 제거 변이 3건 실패.

한계: 행 스냅샷 복원이며 전체 pg_dump 복원 아님. 실제 MCP/PJ1 없음; 원시 실행 JSON 미첨부.

### E06

[2026-10-20-policy-selftest-lab.md:45](../../../../research/llm-wiki/status/reports/2026-10-20-policy-selftest-lab.md#L45) · 격리 실제 PostgreSQL·OPA 1.20.2

최종 추가 기록: 자체 시험 7/7, 규칙 제거/OPA 장애 실패 저장·합성 경보, 보강 제거 변이 2건 실패.

한계: 운영 자체 시험·합성 경보 증거. PAC24 전체 회귀·실제 MCP·SIEM 수신 증거로 전용 금지; 원시 실행 JSON 미첨부.

### E07

[2026-10-15-termination-dispatch.md:31](../../../../research/llm-wiki/status/reports/2026-10-15-termination-dispatch.md#L31) · 격리 실제 PostgreSQL·Gitea 1.27.3·공개 MCP 1.7.0

과거 intent 47, 효과 45, 종료 38, 토큰 22 통과 보고. 중복/동시/승인 경합·변형 요청·답 유실·cutover·자원 거부.

한계: 비밀 검사만 단위 대역. 판정 일부 합성, 풀은 무통신 단위. PJ1 아님. 이후 변경된 현재 HEAD 통과로 승격 금지.

### E08

[2026-10-20-user-command-settings-pj1.md:15](../../../../research/llm-wiki/status/reports/2026-10-20-user-command-settings-pj1.md#L15) · PJ1 Linux 실제 관리 Claude

c986fdd: 사용자 apiKeyHelper/notify 발견→다음 heartbeat 격리→원복·관리자 복귀→MarkItDown 정상.

한계: 주기 탐지이며 실행 전 원자 차단 아님. PJ1 파일 수동 교체, 정식 키트 재설치·Codex 격리/복구 미확인.

### E09

[2026-10-20-command-surfaces.md:26](../../../../research/llm-wiki/status/reports/2026-10-20-command-surfaces.md#L26) · PJ1 Linux 실제 관리 Codex

a61c7fa 관리 훅 정책 반영 뒤 사용자 훅 표식 없음·정상 응답, Context7 게이트웨이 호출은 제공자 할당량 오류.

한계: 정상 MCP 업무 결과 성공으로 세지 않음. statusLine 대화형·Windows 미확인.

### E10

[2026-10-20-server-egress.md:132](../../../../research/llm-wiki/status/reports/2026-10-20-server-egress.md#L132) · PJ1 Claude·MarkItDown·실행기 프록시 관측

355888a 배포: 변환 성공, 판정85와 server-egress 1건(learn.microsoft.com connected) 후보 연결.

한계: 시간 창 보조 근거. 자격 사용 unobserved·재시도 null·독립 외부 효과 unverified; 정확 요청 인과 아님.

### E11

[2026-10-20-poisoning-corpus.md:67](../../../../research/llm-wiki/status/reports/2026-10-20-poisoning-corpus.md#L67) · 로컬 순수 회귀·운영 스키마 표본

합성 공격 4개 0→4·정상28/OSS92 FP0, 기기 운영 도구31 설명 FP0.

한계: 공개 dev/held-out 재측정 미실행. 같은 작성자 합성 수치, 의미적 주입 방어·공개 재현율 개선 증거 아님.

### E12

[2026-10-20-idempotency-pg.md:20](../../../../research/llm-wiki/status/reports/2026-10-20-idempotency-pg.md#L20) · 시험 작성·정적 검사만

새 멱등 PostgreSQL 시험은 작성됐으나 실제 DB 미실행.

한계: 10-15 실제 효과 결과를 새 D-126 TTL·미확인 복구 분기의 현재 통과로 쓰지 않음.

### E13

[2026-10-20-auto-suspend-pg.md:33](../../../../research/llm-wiki/status/reports/2026-10-20-auto-suspend-pg.md#L33) · 시험 보강·정적 검사만

자동 중지 PostgreSQL 시험은 미실행, 두 목록 실패는 capability fixture 불일치로 정정.

한계: 선택 DRIFT는 해당 도구 제한. 미분류 변경/반복 이상은 전체 중지; 실제 MCP DRIFT 효과 아님.

### E14

[2026-10-20-ledger-retention.md:15](../../../../research/llm-wiki/status/reports/2026-10-20-ledger-retention.md#L15) · 로컬 단위·설계 보류

보존 하한 구현·봉인 검증 단위, 원장 행 삭제 미구현.

한계: 서명 봉인·두 사람 만료 삭제와 append-only 원칙의 관계는 결정 필요. 보존 전체 완료 아님.

### E15

[2026-10-20-d149-transition.md:32](../../../../research/llm-wiki/status/reports/2026-10-20-d149-transition.md#L32) · 로컬 순수/대역·전환 검토

NULL 출력 승인 해시는 스키마 부재 계약, 첫 관측 스키마 자동 승인 아님. 신규 승인 입력 검증 보강.

한계: 실제 PostgreSQL 전환·신규 도입·PJ1·출력 스키마 재승인/복구 미실행.

### E16

[2026-10-20-s9b-s10b.md:27](../../../../research/llm-wiki/status/reports/2026-10-20-s9b-s10b.md#L27) · 로컬 AST·대역

요청자 재검증 10건·세션 재사용40 통과 보고, 폐기 목록 조회 오류를 명시적 실패로 전달.

한계: 실제 DB/서명 파일/기기/PJ1 미실행. D-154 후보 회전 기록 순서의 현재 수용 증거 아님.

### E17

[2026-10-20-resource-server-residual.md:25](../../../../research/llm-wiki/status/reports/2026-10-20-resource-server-residual.md#L25) · 로컬 순수·대역

자원 잔존 13/13: refresh introspection 현재 상태·자원 수락 우선·풀/실행기 경계.

한계: 새 PostgreSQL/Gitea resource_residual_pg_check.py 미실행. 외부 자원 서버 캐시·실행기 실제 제거 미확인.

### E18

[2026-10-20-dev69-data-residency.md:68](../../../../research/llm-wiki/status/reports/2026-10-20-dev69-data-residency.md#L68) · 로컬 순수·이미지 대기

위치 규칙 순수8 통과, 게이트웨이/OPA/실기기 후속 대기.

한계: 처리/저장 국가와 법적 근거는 관리자 선언. 잠정 국가 규칙은 적법성 확정 아님.

### E19

[2026-10-20-high-impact-main-merge.md:38](../../../../research/llm-wiki/status/reports/2026-10-20-high-impact-main-merge.md#L38) · 로컬 순수·DB 대역

중대 영향17 통과·이미지7 생략, 위치8·위험12 통과.

한계: 사람 설명 열람/일회용·철회 경계의 대역. 실제 고위험 작업/PJ1/독립 효과 미확인.

## 결정 필요·후속 검수

- PAC06: Resource·Prompt를 추가할지 원본 대비 미지원으로 유지할지 결정 필요.
- PAC08~09: 검증된 에이전트 신원·위임 발급자/교집합/철회 수명주기 도입 결정 필요. 미지원 차단 유지.
- PAC12: 원본 여섯 행위와 내부 r/w/x 집약의 수용 여부 결정 필요.
- PAC15: 잠정 처리 국가 규칙·공급자 실제 위치/이전 근거 검토는 사람의 결정 범위.
- PAC22: 요청 본문 최소화/보존과 append-only, 봉인 구간 만료 삭제/암호 삭제는 DEV-67 결정 필요.
- PAC23~24: D-154 회전 기록 후보·외부 캐시/복제 자격·실행기 제거·서명 저장소 동시 복원은 별도 검수.

DEV-03의 독립 추적 검토를 완료하며 각 기능의 검수 점수는 변경하지 않는다. 기기 재실행: `dispatch_recheck_pg_check.py`, `oauth_negative_pg_check.py`, `restore_residual_pg_check.py`, `policy_selftest_pg_check.py`(과거 성공의 현 판본 확인), `dispatch_idempotency_pg_check.py`, `auto_suspend_pg_check.py`, `resource_residual_pg_check.py`(미실행 범위). 솔루션 기기 `full_stack_lab`의 준비된 전용 랩에서 `tests/termination_dispatch_lab.sh run <파일>`로 실행한다. 다른 사람이 사용 중인 랩을 시작/초기화/정지하지 않는다. PJ1 새 관리 하네스·OSS MCP·독립 효과 검수는 별도다.
