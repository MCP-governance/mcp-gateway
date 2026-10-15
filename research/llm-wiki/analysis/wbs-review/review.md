# G01–G10 목표 기능 기반 40개 원자 WBS 검토안

2026-10-14 읽기 전용 검토 초안. 목표 G01–G10마다 작업 4개다. 정책 링크는 원본 `PAC01–PAC24`이며 런타임 `PAC-01–15`와 같은 ID로 취급하지 않는다. 최종 완료율 산정은 main이 정본 근거를 대조해 수행한다.

각 작업은 구현·회귀·배포·실기기·완료조건을 각각 20%로 제안했다. JSON boolean은 제한적인 근거 상태다. `implementation=true`는 source/symbol 경로의 구현 존재만 뜻한다. 이번 검토에서는 테스트를 실행하지 않아 회귀는 전부 false다. 역사적 PASS는 보고서 날짜·revision·hash 기준으로만 남겼다. source와 hash가 현재 revision에 맞지 않으면 현 branch 회귀 PASS로 계산하지 않는다.

## 엔드포인트 로그 전달에서 확인된 경계

- `2026-10-14-pj1-ghidra-logs.json` (2026-10-14 19:13:55 KST): 실제 GhidraMCP SDK `initialize → tools/list(28) → get_program_info` read 성공. 프로세스는 UID 1000/unconfined였다. 관리 UID 1001의 Python 실행은 exit 126으로 거부됐다. 이 계정별 결과를 전체 사용자·앱 통제로 확대하지 않는다.
- 프로세스/stdio inventory 자동 전송은 꺼져 있다 (`managed-linux.py::serve`의 NETSCAN=0). 수동 1회 report는 shadow/suspected로 수신됐다. 별도 OS kernel denial event는 수동 report 없이 약 35.84초 후 자동 수신됐다. 이 셋은 다른 채널/상태다.
- SDK 호출 구간 Gateway tool decision 0건은 local stdio가 Gateway `tools/call`을 우회한 경로와 부합한다. endpoint call이 없었다는 증거는 아니다.
- D-79로 자가 승인 9-tool 결과는 무효. ledger 744–800은 감사 이력으로 보존하며 positive governance evidence로 세지 않는다.
- E13은 `not_run`. 변형된 PJ1 시험에서 관리 UID 선택 거부와 unmanaged 대조군 동작은 확인했지만 공식 filesystem MCP 직접 stdio tool call은 미수행. 모델 거부/Node 실행 거부만으로 E13 통과 처리하지 않는다.
- source event hash, raw forwarded payload hash, sanitized projection hash를 각각 비교해야 한다. report JSON의 artifact hash만으로 source↔receiver byte equality를 주장하지 않는다. manual report를 auto-collection으로 세지 않는다.

## 단계 플래그 의미

| 플래그 | 제안 weight | 적용 기준 |
| --- | ---: | --- |
| `implementation` | 20% | 해당 source 경로 존재. 동적 정합성은 별도 |
| `regression` | 20% | 동일 source hash에서 완료조건에 맞는 테스트 PASS |
| `deployment` | 20% | 대상 build/revision/hash가 task source를 가리킴 |
| `real_device` | 20% | 실제 기기·계정·하네스 행위와 독립 효과 확인 |
| `acceptance_complete` | 20% | 명시 완료조건·범위·원복·근거를 reviewer 확인 |

JSON true는 해당 row의 좁은 범위만 뜻한다. false는 미증명/미완료다. E01–E13이나 전체 G/PAC 항목을 자동완료시키지 않는다.

## G01 — 도입·공급망 검증

### G01.01 도입물 출처·버전·원본 해시 등록

- 원본 PAC: PAC01
- 제안 완료조건: 신규 승인마다 공급 URL·immutable version/commit·license·artifact SHA-256이 저장되고 배포 파일과 일치하며, 누락 또는 mismatch는 등록 보류된다.
- 구현 위치/심볼: full_stack_lab/gateway/app/agent_service.py::intake*, full_stack_lab/supply_chain/
- 회귀 후보: full_stack_lab/tests/intake_validation_test.py
- 근거 경로: research/llm-wiki/analysis/local-tools/data.json, research/llm-wiki/analysis/local-tools/desktop.json, research/llm-wiki/analysis/pj1-ghidra/report.json
- 알려진 공백: 현재 공개 MCP 아티팩트 hash 보존은 개별 연구에 있고, 모든 도입 요청과 실행 artifact 연결·독립 재검증은 범위 밖.
- 현재 제안 플래그 (I/R/D/실기기/완료): 1/0/0/0/0
- 인용된 근거 날짜/범위: 독립 실기기/효과 근거 미확인.

### G01.02 SBOM·취약점·라이선스 검사와 재평가 연결

- 원본 PAC: PAC01, PAC02
- 제안 완료조건: SBOM 각 component·license·vulnerability snapshot 및 source timestamp가 승인된 release와 묶이고 scanner outage/critical finding은 fail-closed; stale database case도 증명한다.
- 구현 위치/심볼: full_stack_lab/supply_chain/, full_stack_lab/gateway/app/core.py::import_supply_chain_reports, full_stack_lab/gateway/app/core.py::supply_chain_coverage
- 회귀 후보: full_stack_lab/tests/intake_validation_test.py, full_stack_lab/tests/intake_register.py
- 근거 경로: research/llm-wiki/status/backlog.md#DEV-02
- 알려진 공백: 최신 취약점 정보의 수집시각·오탐 승인·재검토 SLA·실제 격리 scanner fail-closed가 현재 보고에서 미확인.
- 현재 제안 플래그 (I/R/D/실기기/완료): 1/0/0/0/0
- 인용된 근거 날짜/범위: 독립 실기기/효과 근거 미확인.

### G01.03 도입 범위·기능별 최소권한 사전 심사

- 원본 PAC: PAC02, PAC07
- 제안 완료조건: 각 도구별 목적·자산·읽기/변경/실행·외부 목적지가 사람이 승인한 범위로 잠기고 미검토 도구는 discover/call 불가; 독립 효과로 범위를 확인한다.
- 구현 위치/심볼: full_stack_lab/gateway/app/agent_service.py, full_stack_lab/gateway/app/pac.py, full_stack_lab/registry/catalog.toml
- 회귀 후보: full_stack_lab/tests/catalog_refresh_check.py, full_stack_lab/tests/schema_check.py
- 근거 경로: research/llm-wiki/status/reports/2026-10-13-feature-design.md
- 알려진 공백: PAC 번호는 source policies와 runtime PAC-01~15가 다른 체계. 기존 권한 분류가 제품별 실제 자원 효과와 모두 일치하는지는 별도시험.
- 현재 제안 플래그 (I/R/D/실기기/완료): 1/0/0/0/0
- 인용된 근거 날짜/범위: 2026-10-13-feature-design.md: 2026-10-13 static design/source analysis, not behavior validation.

### G01.04 설치·로그 수신물의 원본/정규화 hash 사슬

- 원본 PAC: PAC01, PAC22
- 제안 완료조건: 공급자 원본 hash·기기 설치 hash·수신 payload raw hash·비밀 제거 projection hash를 역할별로 남기고 raw 전달물과 기기 이벤트의 일치/정규화 규칙을 독립 검증한다.
- 구현 위치/심볼: research/llm-wiki/analysis/pj1-ghidra/report.json, research/llm-wiki/tools/build_pj1_ghidra_log_report.py
- 회귀 후보: research/llm-wiki/experiments/pj1-ghidra/check_automatic_os_event.py
- 근거 경로: research/llm-wiki/status/reports/2026-10-14-pj1-ghidra-logs.json
- 알려진 공백: 현재 Ghidra 설치는 /dev/shm volatile, 자동 MCP stdio 수집 미설정. 보고 해시 일치 확인을 전체 수신 경로의 자동 무결성으로 일반화 금지.
- 현재 제안 플래그 (I/R/D/실기기/완료): 1/0/0/0/0
- 인용된 근거 날짜/범위: 2026-10-14-pj1-ghidra-logs.json: 2026-10-14 19:13:55 KST actual SDK read and separate manual/automatic log-channel evidence.

## G02 — 승인·계약 관리

### G02.01 신청자와 승인자 독립성·승인 기록 보호

- 원본 PAC: PAC03, PAC16
- 제안 완료조건: 신청자≠검토자 강제, risk-level별 사람 승인, 승인 provenance/검토 범위 기록; 무효된 self-approval fixture는 disabled 감사 상태로만 보존한다.
- 구현 위치/심볼: full_stack_lab/gateway/app/agent_service.py, full_stack_lab/gateway/app/core.py, docs/ai/DECISIONS.md#D-79
- 회귀 후보: full_stack_lab/tests/managed_enrollment_check.py
- 근거 경로: research/llm-wiki/status/reports/2026-10-14-pj1-nine-tools.md
- 알려진 공백: D-79에 의해 자가 승인된 PJ1 nine-tools의 rows 744–800은 무효 시험 근거이며 긍정 증거로 계상 금지.
- 현재 제안 플래그 (I/R/D/실기기/완료): 1/0/0/0/0
- 인용된 근거 날짜/범위: 2026-10-14-pj1-nine-tools.md: 2026-10-14 D-79 invalidated self-approved run; not positive test evidence.

### G02.02 도구 이름·설명·schema·버전 계약 해시 잠금

- 원본 PAC: PAC06, PAC21
- 제안 완료조건: 등록/승인된 description+input schema+server version hashes가 재시작/재발견/동명 도구에도 일치하고 B drift는 전달 전에 차단, A 복귀 시 A가 관찰된다.
- 구현 위치/심볼: full_stack_lab/gateway/app/core.py::refresh_catalog, approve_contract, full_stack_lab/gateway/app/contract.py, full_stack_lab/registry/contracts.lock.json
- 회귀 후보: full_stack_lab/tests/catalog_refresh_check.py, full_stack_lab/tests/schema_check.py
- 근거 경로: research/llm-wiki/status/reports/2026-10-13-development-results.md
- 알려진 공백: 보고된 A→B→A 4/4는 당시 구현/회귀 증거; 현재 source와 새 PJ1 도구 전부에 대한 검증은 아님.
- 현재 제안 플래그 (I/R/D/실기기/완료): 1/0/1/0/0
- 인용된 근거 날짜/범위: 2026-10-13-development-results.md: 2026-10-13 historical report; deployed implementation rev 6178dd3; not a rerun on this review branch.

### G02.03 승인 만료·중지·변경 후 재승인

- 원본 PAC: PAC03, PAC21, PAC23
- 제안 완료조건: 만료/철회/계약변경 뒤 기존 설정과 fresh tool-call이 전달되지 않고 사용자 동의와 운영자 승인이 별도로 기록됨을 실제 하네스에서 확인한다.
- 구현 위치/심볼: full_stack_lab/gateway/app/core.py, full_stack_lab/gateway/app/decommission.py
- 회귀 후보: full_stack_lab/tests/managed_enrollment_check.py, full_stack_lab/tests/termination_flow.py
- 근거 경로: research/llm-wiki/experiments/E12-managed-admission.md
- 알려진 공백: E12 카드 자체는 미실행. 현재 시행중인 registry TTL/user consent end-to-end 확인은 이 검토에서 없음.
- 현재 제안 플래그 (I/R/D/실기기/완료): 0/0/0/0/0
- 인용된 근거 날짜/범위: 독립 실기기/효과 근거 미확인.

### G02.04 승인 서버 설정을 하네스별 최소 집합으로 배포

- 원본 PAC: PAC03, PAC06, PAC07
- 제안 완료조건: fresh approved harness는 허용된 서버만 보며 등록 철회 서버는 목록·호출 모두 불가; 모델→MCP→decision을 연결한다.
- 구현 위치/심볼: full_stack_lab/registry/catalog.toml, full_stack_lab/gateway/app/agent_service.py, endpoint-agent/agent.py
- 회귀 후보: full_stack_lab/tests/endpoint_inventory_check.py, full_stack_lab/tests/field_kit_check.py
- 근거 경로: research/llm-wiki/status/reports/2026-10-14-pj1-endpoint-update.json
- 알려진 공백: 선택된 Codex/Claude version·hash 일치와 정상 설정 전달을 보여도 등록 도구 전체 인가/사용자 동의를 자동 증명하지 않음.
- 현재 제안 플래그 (I/R/D/실기기/완료): 0/0/0/0/0
- 인용된 근거 날짜/범위: 2026-10-14-pj1-endpoint-update.json: 2026-10-14 selected PJ1 account/kernel checks; scope is the tested managed UID/profile.

## G03 — 신원·호출 권한

### G03.01 transport 인증 주체·audience·scope·만료 검증

- 원본 PAC: PAC08, PAC10
- 제안 완료조건: wrong issuer/audience/scope, expired/revoked token은 upstream attempted=false로 차단; transport principal만 사용하고 prompt/header self-claim은 권한에 영향 없음.
- 구현 위치/심볼: full_stack_lab/gateway/app/idp.py, full_stack_lab/gateway/app/agent_contract.py, full_stack_lab/gateway/app/core.py
- 회귀 후보: full_stack_lab/tests/managed_enrollment_check.py, full_stack_lab/tests/oauth_rotation_pg_check.py
- 근거 경로: research/llm-wiki/status/reports/2026-10-13-development-results.md
- 알려진 공백: 보고된 3개 PG 경쟁 시나리오는 운영 IdP 외부 배선·모든 공급자 audience/scope lifecycle 증거가 아님.
- 현재 제안 플래그 (I/R/D/실기기/완료): 1/0/1/0/0
- 인용된 근거 날짜/범위: 2026-10-13-development-results.md: 2026-10-13 historical report; deployed implementation rev 6178dd3; not a rerun on this review branch.

### G03.02 PAC-05 agent delegation 교집합 상태를 명시

- 원본 PAC: PAC09
- 제안 완료조건: True
- 구현 위치/심볼: full_stack_lab/gateway/app/pac.py, docs/ai/SECURITY_BOUNDARIES.md
- 회귀 후보: docs/ai/SECURITY_BOUNDARIES.md, full_stack_lab/tests/pac_boundary_check.py
- 근거 경로: research/llm-wiki/status/backlog.md#DEV-17
- 알려진 공백: PAC-05 agent/user delegation은 하네스 인증 근거 부재로 의도적 미구현; harness clientInfo는 self-reported. 이를 완료 처리하지 말 것.
- 현재 제안 플래그 (I/R/D/실기기/완료): 0/0/0/0/0
- 인용된 근거 날짜/범위: 독립 실기기/효과 근거 미확인.

### G03.03 요청별 행위·인자·자산·목적지 권한 재판정

- 원본 PAC: PAC11, PAC12, PAC13, PAC14, PAC15
- 제안 완료조건: same tool with changed SQL/path/recipient/asset must be reclassified on every call; normalized deny occurs pre-send and independent target confirms effect 0.
- 구현 위치/심볼: full_stack_lab/gateway/app/classify.py, full_stack_lab/gateway/app/pac.py, full_stack_lab/gateway/app/core.py::execute_call
- 회귀 후보: full_stack_lab/tests/security_edges_check.py, full_stack_lab/tests/reservation_effect_check.py
- 근거 경로: research/llm-wiki/status/reports/2026-10-13-development-results.md
- 알려진 공백: 새 로그 evidence는 Gateway decision 0건일 수 있음; absent ledger alone은 local MCP call absent 증명이 아님.
- 현재 제안 플래그 (I/R/D/실기기/완료): 1/0/1/0/0
- 인용된 근거 날짜/범위: 2026-10-13-development-results.md: 2026-10-13 historical report; deployed implementation rev 6178dd3; not a rerun on this review branch.

### G03.04 동일 호출·동시 실행·승인 재사용 예약의 원자성

- 원본 PAC: PAC16, PAC17
- 제안 완료조건: 경계조건에서 허용 effect가 정확히 1, 중복/승인 재사용은 0; process crash는 uncertain으로 남고 자동 재시도하지 않는다.
- 구현 위치/심볼: full_stack_lab/gateway/app/core.py::execute_call, call_reservations
- 회귀 후보: full_stack_lab/tests/reservation_effect_check.py, full_stack_lab/tests/managed_enrollment_check.py
- 근거 경로: research/llm-wiki/status/reports/2026-10-14-risk-scenarios.md
- 알려진 공백: 전용 PG stage에서 보고된 5 cases는 endpoint-agent admission DB 효과이며 MCP caller authorization/reservation races와 다른 대상.
- 현재 제안 플래그 (I/R/D/실기기/완료): 1/0/0/0/0
- 인용된 근거 날짜/범위: 2026-10-14-risk-scenarios.md: 2026-10-14 dedicated PostgreSQL application-state scenarios; not OS kernel proof.

## G04 — 데이터·주입 통제

### G04.01 입력 schema·크기·경로 검사 및 injection 분류

- 원본 PAC: PAC13, PAC18
- 제안 완료조건: schema/path/encoding/size and injection corpus are tested with normal controls, exact policy ID, tool transmission status, false-positive/false-negative counts.
- 구현 위치/심볼: full_stack_lab/gateway/app/core.py, full_stack_lab/gateway/app/poisoning.py, full_stack_lab/gateway/app/classify.py
- 회귀 후보: full_stack_lab/tests/security_edges_check.py, full_stack_lab/tests/injection_corpus_check.py
- 근거 경로: research/llm-wiki/status/reports/2026-10-13-mcp-validation-plan.md
- 알려진 공백: 현 보고상 PyRIT 고정 seed 26 injection attempts 중 21 탐지 (historical); 누락 5와 의미적 미탐은 남음.
- 현재 제안 플래그 (I/R/D/실기기/완료): 0/0/0/0/0
- 인용된 근거 날짜/범위: 2026-10-13-mcp-validation-plan.md: 2026-10-13 experiment plan; listed cases were not run by that planning report.

### G04.02 응답 PII/secret 마스킹·hold/release 경계

- 원본 PAC: PAC19, PAC20
- 제안 완료조건: synthetic secrets are absent from model-facing raw text/structuredContent; original upstream attempted/executed and masked/held/released outcome shown separately.
- 구현 위치/심볼: full_stack_lab/gateway/app/privacy.py, full_stack_lab/gateway/app/secret_scan.py, full_stack_lab/gateway/app/core.py
- 회귀 후보: full_stack_lab/tests/mcp_result_contract_check.py, full_stack_lab/tests/mcp_result_services_check.py
- 근거 경로: research/llm-wiki/status/reports/2026-10-13-pj1-evidence.json
- 알려진 공백: 원장742 Block pre-send와 달리 output hold는 이미 upstream가 실행됐을 수 있어 upstream execution과 사용자 노출을 분리해야 함.
- 현재 제안 플래그 (I/R/D/실기기/완료): 1/0/0/0/0
- 인용된 근거 날짜/범위: 2026-10-13-pj1-evidence.json: Historical PJ1 managed harness actual calls 740–742; provider quota and no independent receiver caveat apply.

### G04.03 도구 결과의 비신뢰 지시 보류와 정상 언어 대조

- 원본 PAC: PAC18, PAC20
- 제안 완료조건: EN/KR/encoding benign and attack corpus is rerun against matched source; false positives and misses are disclosed; held responses are not called upstream prevention.
- 구현 위치/심볼: full_stack_lab/gateway/app/poisoning.py::text_findings, OVERRIDE_RULES
- 회귀 후보: full_stack_lab/tests/injection_corpus_check.py, full_stack_lab/tests/mcp_result_contract_check.py
- 근거 경로: research/llm-wiki/status/reports/2026-10-13-mcp-validation-plan.md
- 알려진 공백: string rules do not equal semantic injection understanding; user must not take historic exact counts as present-source result.
- 현재 제안 플래그 (I/R/D/실기기/완료): 0/0/0/0/0
- 인용된 근거 날짜/범위: 2026-10-13-mcp-validation-plan.md: 2026-10-13 experiment plan; listed cases were not run by that planning report.

### G04.04 검사기·PDP·목적지 자료 누락은 fail-closed

- 원본 PAC: PAC05, PAC15, PAC19
- 제안 완료조건: missing/wrong-type scanner/PDP/catalog result denies before upstream; explicit empty allow set is distinguished from error; independent receivers see no request.
- 구현 위치/심볼: full_stack_lab/gateway/app/core.py, full_stack_lab/gateway/app/privacy.py, full_stack_lab/gateway/app/classify.py
- 회귀 후보: full_stack_lab/tests/mcp_result_services_check.py, full_stack_lab/tests/security_edges_check.py
- 근거 경로: research/llm-wiki/status/reports/2026-10-13-real-inspectors-results.json
- 알려진 공백: 단위 failure injection 및 historical test PASS는 deployment runtime availability를 보장하지 않음.
- 현재 제안 플래그 (I/R/D/실기기/완료): 1/0/0/0/0
- 인용된 근거 날짜/범위: 2026-10-13-real-inspectors-results.json: Historical local inspector tests; source/current deployment hash needs matching.

## G05 — 엔드포인트 관리

### G05.01 관리형 UID/profile/kernel 건강상태를 exact-bound 검증

- 원본 PAC: PAC07, PAC08
- 제안 완료조건: only exact UID/profile/rule names/SID/config hashes and current enforcing state counts compliant; disabled, missing, foreign-account, complain-mode cases deny.
- 구현 위치/심볼: endpoint-agent/managed-linux.py, endpoint-agent/managed-windows.py, endpoint-agent/enforce-linux.py
- 회귀 후보: full_stack_lab/tests/managed_enforcement_check.py
- 근거 경로: research/llm-wiki/status/reports/2026-10-14-endpoint-regressions.json
- 알려진 공백: 9 Linux/Windows synthetic regressions passed on reported source; Windows OS device enforcement still unverified. Linux PJ1 exact check is one managed identity only.
- 현재 제안 플래그 (I/R/D/실기기/완료): 1/0/1/1/0
- 인용된 근거 날짜/범위: 2026-10-14-endpoint-regressions.json: 2026-10-14 14:01 KST offline regression report; does not imply current source hash or Windows real-device enforcement.

### G05.02 비인가 stdio·IPv4/IPv6 loopback을 독립 효과 0으로 확인

- 원본 PAC: PAC07
- 제안 완료조건: fresh managed official filesystem MCP actually attempts direct stdio and IPv4+IPv6 marker receivers; independent listener/data effect 0 under enforced profile, exact denial layer retained; approved Gateway control succeeds.
- 구현 위치/심볼: endpoint-agent/enforce-linux.py, endpoint-agent/managed-linux.py, research/llm-wiki/experiments/E13-local-bypass.md
- 회귀 후보: full_stack_lab/tests/managed_kernel_proof.py, research/llm-wiki/experiments/E13-local-bypass.md
- 근거 경로: research/llm-wiki/status/reports/2026-10-14-pj1-endpoint-update.json
- 알려진 공백: E13 is NOT completed: selected actual block tests targeted Node/interpreter and ssh loopback, not actual filesystem MCP stdio. Admin/root and other unconfined accounts out of scope.
- 현재 제안 플래그 (I/R/D/실기기/완료): 1/0/1/0/0
- 인용된 근거 날짜/범위: 2026-10-14-pj1-endpoint-update.json: 2026-10-14 selected PJ1 account/kernel checks; scope is the tested managed UID/profile.

### G05.03 프로세스·MCP 발견자료를 자동·수동 전송 종류별로 구분

- 원본 PAC: PAC07, PAC22
- 제안 완료조건: process-only inventory must reach solution automatically with origin=automatic, source hash and event time; explicitly distinguish manual shadow upload and kernel OS-event auto forwarding, test collector stale/offline cases and duplicate prevention.
- 구현 위치/심볼: endpoint-agent/managed-linux.py::serve, endpoint-agent/os-observer.py, endpoint-agent/agent.py, full_stack_lab/gateway/app/endpoint_plane.py
- 회귀 후보: full_stack_lab/tests/endpoint_inventory_check.py
- 근거 경로: research/llm-wiki/status/reports/2026-10-14-pj1-ghidra-logs.json
- 알려진 공백: Critical: automatic stdio process observation/forwarding=false (NETSCAN=0). Manual one-off report accepted as shadow/suspected; automated kernel-denial event arrived independently after ~35.84 seconds. These are separate channels.
- 현재 제안 플래그 (I/R/D/실기기/완료): 0/0/0/0/0
- 인용된 근거 날짜/범위: 2026-10-14-pj1-ghidra-logs.json: 2026-10-14 19:13:55 KST actual SDK read and separate manual/automatic log-channel evidence.

### G05.04 통제 밖 UID·사용자 PC·Windows scope 명시

- 원본 PAC: PAC07
- 제안 완료조건: unmanaged account can be classified as outside enforcement scope; demonstrate observed coverage by UID/profile and no claim that all local apps/accounts are blocked; run isolated Windows acceptance before claiming Windows support.
- 구현 위치/심볼: endpoint-agent/managed-linux.py, endpoint-agent/managed-windows.py, research/llm-wiki/status/reports/2026-10-14-pj1-ghidra-logs.json
- 회귀 후보: full_stack_lab/tests/endpoint_inventory_check.py
- 근거 경로: research/llm-wiki/status/reports/2026-10-14-pj1-endpoint-update.json, research/llm-wiki/status/reports/2026-10-14-e13-local-mcp-natural-language.md
- 알려진 공백: Unconfined UID1000 actually called GhidraMCP read; managed UID1001 denied unapproved Python. This is account-specific. Windows OS direct enforcement is not evidenced.
- 현재 제안 플래그 (I/R/D/실기기/완료): 1/0/0/1/0
- 인용된 근거 날짜/범위: 2026-10-14-pj1-endpoint-update.json: 2026-10-14 selected PJ1 account/kernel checks; scope is the tested managed UID/profile.; 2026-10-14-e13-local-mcp-natural-language.md: 2026-10-14 partial E13-variant Claude test; canonical E13 card remains not_run.

## G06 — 실행·감사 증거

### G06.01 MCP request·Gateway decision·endpoint event ID 상관관계

- 원본 PAC: PAC22
- 제안 완료조건: one run joins harness event, endpoint process/event IDs, request/trace, policy decision, upstream attempt/result and independent receiver timestamps without merging distinct logs.
- 구현 위치/심볼: full_stack_lab/gateway/app/audit.py, full_stack_lab/gateway/app/core.py, full_stack_lab/gateway/app/endpoint_plane.py
- 회귀 후보: full_stack_lab/tests/oss_audit_test.py, full_stack_lab/tests/endpoint_inventory_check.py
- 근거 경로: research/llm-wiki/status/reports/2026-10-13-pj1-evidence.json
- 알려진 공백: Local stdio bypass creates no Gateway tools/call decision; telemetry POST is not a MCP decision. Missing ledger rows cannot prove no local action.
- 현재 제안 플래그 (I/R/D/실기기/완료): 1/0/1/0/0
- 인용된 근거 날짜/범위: 2026-10-13-pj1-evidence.json: Historical PJ1 managed harness actual calls 740–742; provider quota and no independent receiver caveat apply.

### G06.02 시도·판정·실행·응답 효과를 별도 표현

- 원본 PAC: PAC11, PAC19, PAC20
- 제안 완료조건: dashboard distinguishes Block-before-send, Alert-and-execute, upstream error, output held/masked, and successful independent effect; exact attempted/executed bits agree with receiver.
- 구현 위치/심볼: full_stack_lab/gateway/app/core.py, full_stack_lab/gateway/app/audit.py, full_stack_lab/gateway/app/agent_service.py
- 회귀 후보: full_stack_lab/tests/mcp_result_contract_check.py, full_stack_lab/tests/security_edges_check.py
- 근거 경로: research/llm-wiki/status/reports/2026-10-13-pj1-evidence.json
- 알려진 공백: Ledger 741 Alert executed upstream; 742 Block did not. They establish distinction but not all result redaction cases.
- 현재 제안 플래그 (I/R/D/실기기/완료): 1/0/1/1/0
- 인용된 근거 날짜/범위: 2026-10-13-pj1-evidence.json: Historical PJ1 managed harness actual calls 740–742; provider quota and no independent receiver caveat apply.

### G06.03 수집 성공·실패·last success·전체집계 표시

- 원본 PAC: PAC22
- 제안 완료조건: UI says received/latest N, separate all-time aggregate and last successful collection timestamp, stale/offline/error, and cannot label missing telemetry as zero denials.
- 구현 위치/심볼: endpoint-agent/agent.py, endpoint-agent/managed-linux.py, full_stack_lab/gateway/app/endpoint_plane.py, full_stack_lab/gateway/app/agent_service.py
- 회귀 후보: full_stack_lab/tests/endpoint_inventory_check.py
- 근거 경로: research/llm-wiki/status/reports/2026-10-13-development-results.md
- 알려진 공백: Development results say event list is recent received 200 only; aggregate count and collector freshness remain follow-up.
- 현재 제안 플래그 (I/R/D/실기기/완료): 0/0/0/0/0
- 인용된 근거 날짜/범위: 2026-10-13-development-results.md: 2026-10-13 historical report; deployed implementation rev 6178dd3; not a rerun on this review branch.

### G06.04 원본 event와 솔루션 보관본의 hash/projection 일치

- 원본 PAC: PAC01, PAC22
- 제안 완료조건: for every forwarded sample retain raw hash, source file/bytes hash, sanitized projection hash, transformation manifest and received timestamp; test mismatched bytes are detected without retaining secrets.
- 구현 위치/심볼: research/llm-wiki/analysis/pj1-ghidra/report.json, research/llm-wiki/status/reports/2026-10-14-pj1-ghidra-logs.json
- 회귀 후보: research/llm-wiki/experiments/pj1-ghidra/observe_pj1_logs.py
- 근거 경로: research/llm-wiki/analysis/pj1-ghidra/automatic-os-event.json
- 알려진 공백: Hash claims are per evidence artifact and projection; report does not imply every raw payload is losslessly retained at solution.
- 현재 제안 플래그 (I/R/D/실기기/완료): 0/0/0/0/0
- 인용된 근거 날짜/범위: 독립 실기기/효과 근거 미확인.

## G07 — 종료·권한 회수

### G07.01 사용자·device token·refresh family 즉시 폐기

- 원본 PAC: PAC10, PAC23, PAC24
- 제안 완료조건: revoked token and all descendants fail on fresh protected API and MCP call; race issuance/revocation transaction rolls back atomically; provider resource credential revocation separately evidenced.
- 구현 위치/심볼: full_stack_lab/gateway/app/idp.py, full_stack_lab/gateway/app/decommission.py
- 회귀 후보: full_stack_lab/tests/oauth_rotation_pg_check.py, full_stack_lab/tests/oauth_rotation_check.py
- 근거 경로: research/llm-wiki/status/reports/2026-10-13-development-results.md
- 알려진 공백: OAuth test proves 3 isolated PostgreSQL concurrency cases at that revision; provider-side revocation and all issued bearer reuse are not proven.
- 현재 제안 플래그 (I/R/D/실기기/완료): 1/0/1/0/0
- 인용된 근거 날짜/범위: 2026-10-13-development-results.md: 2026-10-13 historical report; deployed implementation rev 6178dd3; not a rerun on this review branch.

### G07.02 활성 세션·MCP server session 종료와 재접근 차단

- 원본 PAC: PAC23
- 제안 완료조건: C1-C4 exact termination predicates verified against fresh sessions and existing sessions; stale session cannot reacquire data; record T1-T3 evidence.
- 구현 위치/심볼: full_stack_lab/gateway/app/decommission.py, full_stack_lab/gateway/app/upstream.py, docs/ai/TERMINATION_MODEL.md
- 회귀 후보: full_stack_lab/tests/termination_flow.py
- 근거 경로: research/llm-wiki/status/backlog.md#DEV-08
- 알려진 공백: Gateway opens/closes call-scoped session, but downstream server-specific durable session/resource behavior is not universally validated.
- 현재 제안 플래그 (I/R/D/실기기/완료): 0/0/0/0/0
- 인용된 근거 날짜/범위: 독립 실기기/효과 근거 미확인.

### G07.03 외부 provider·resource server 잔존 접근 확인

- 원본 PAC: PAC23, PAC24
- 제안 완료조건: after local removal, actual provider protected resource rejects previous token/session; otherwise mark provider-side disposal unverified and report expiry/TTL only.
- 구현 위치/심볼: full_stack_lab/gateway/app/decommission.py, full_stack_lab/gateway/app/idp.py
- 회귀 후보: full_stack_lab/tests/termination_flow.py, full_stack_lab/tests/oauth_rotation_pg_check.py
- 근거 경로: research/llm-wiki/status/backlog.md#DEV-08
- 알려진 공백: Provider-claimed delete/revoke is not resource-server proof; downstream token acceptance/TTL/cache can outlive local settings.
- 현재 제안 플래그 (I/R/D/실기기/완료): 0/0/0/0/0
- 인용된 근거 날짜/범위: 독립 실기기/효과 근거 미확인.

### G07.04 설정·credential 제거 후 잔존/백업 복구 테스트

- 원본 PAC: PAC24
- 제안 완료조건: isolated test credential is unlinked, revoked, cannot be rehydrated from task backups/cache; cleanup proof preserves raw audit lineage and no unrelated files are deleted.
- 구현 위치/심볼: full_stack_lab/gateway/app/decommission.py, full_stack_lab/gateway/app/idp.py, endpoint-agent/agent.py
- 회귀 후보: full_stack_lab/tests/termination_flow.py, full_stack_lab/tests/endpoint_inventory_check.py
- 근거 경로: research/llm-wiki/status/backlog.md#DEV-08
- 알려진 공백: No evidence that setting deletion wipes external tokens, backups, caches, or exported logs; preserve evidence and avoid destructive operations against user profile.
- 현재 제안 플래그 (I/R/D/실기기/완료): 0/0/0/0/0
- 인용된 근거 날짜/범위: 독립 실기기/효과 근거 미확인.

## G08 — 현장 사용성

### G08.01 조직가입·장치 enrollment·활성화·재접속 경로

- 원본 PAC: PAC03, PAC07, PAC08
- 제안 완료조건: pending denied, correct owner activates, invalid/stale heartbeat quarantines, revoke epoch advances; independent DB query and managed user flow confirm expected user feedback.
- 구현 위치/심볼: full_stack_lab/gateway/app/endpoint_plane.py, full_stack_lab/tests/managed_enrollment_check.py
- 회귀 후보: full_stack_lab/tests/managed_enrollment_check.py
- 근거 경로: research/llm-wiki/status/reports/2026-10-14-risk-scenarios.md
- 알려진 공백: Dedicated PostgreSQL run validates 5 application state scenarios in synthetic DB, not host kernel or complete UX.
- 현재 제안 플래그 (I/R/D/실기기/완료): 1/0/1/0/0
- 인용된 근거 날짜/범위: 2026-10-14-risk-scenarios.md: 2026-10-14 dedicated PostgreSQL application-state scenarios; not OS kernel proof.

### G08.02 지원 공식 harness에서 fresh model→MCP call 검증

- 원본 PAC: PAC03, PAC07
- 제안 완료조건: approved current harness calls synthetic read/write through approved server; model version/thread, arguments, Gateway IDs, endpoint ID, provider response, independent effect and cleanup agree.
- 구현 위치/심볼: full_stack_lab/registry/catalog.toml, endpoint-agent/agent.py, full_stack_lab/gateway/app/core.py
- 회귀 후보: full_stack_lab/tests/managed_enrollment_check.py
- 근거 경로: research/llm-wiki/status/reports/2026-10-13-pj1-evidence.json
- 알려진 공백: Historical PJ1 Codex calls 740–742 are actual calls but one provider quota failure; they do not satisfy all E01–E13 cases or this new endpoint-log work.
- 현재 제안 플래그 (I/R/D/실기기/완료): 1/0/1/0/0
- 인용된 근거 날짜/범위: 2026-10-13-pj1-evidence.json: Historical PJ1 managed harness actual calls 740–742; provider quota and no independent receiver caveat apply.

### G08.03 사용자 승인/연결/등록 UI에 운영자 승인과 자가승인 분리

- 원본 PAC: PAC03, PAC06, PAC16
- 제안 완료조건: fresh enrollment request shows data/functions and needs independent human approval; test logs cannot be used as success if agent approved its own target.
- 구현 위치/심볼: full_stack_lab/gateway/app/agent_service.py::intake*, docs/ai/DECISIONS.md#D-79
- 회귀 후보: full_stack_lab/tests/managed_enrollment_check.py
- 근거 경로: research/llm-wiki/status/reports/2026-10-14-pj1-nine-tools.md
- 알려진 공백: The 9-tool self-approved test was invalidated; user consent and operator approval remain separate.
- 현재 제안 플래그 (I/R/D/실기기/완료): 0/0/0/0/0
- 인용된 근거 날짜/범위: 2026-10-14-pj1-nine-tools.md: 2026-10-14 D-79 invalidated self-approved run; not positive test evidence.

### G08.04 설치·업데이트·오류 원인 및 재시도 사용성

- 원본 PAC: PAC02, PAC03
- 제안 완료조건: isolated Linux and Windows installs/uninstalls are idempotent, report lock race resolved, user files preserved, and actual update rollback/heartbeat recovery evidenced.
- 구현 위치/심볼: endpoint-agent/bootstrap.py, endpoint-agent/managed-linux.py, endpoint-agent/managed-windows.py, research/llm-wiki/status/backlog.md#DEV-26
- 회귀 후보: full_stack_lab/tests/field_kit_check.py, full_stack_lab/tests/managed_enforcement_check.py
- 근거 경로: research/llm-wiki/status/reports/2026-10-14-endpoint-regressions.json
- 알려진 공백: Windows report.log WinError32 race remains in report; WSL Linux kit 17 pass does not clear the Windows concurrency issue.
- 현재 제안 플래그 (I/R/D/실기기/완료): 1/0/0/0/0
- 인용된 근거 날짜/범위: 2026-10-14-endpoint-regressions.json: 2026-10-14 14:01 KST offline regression report; does not imply current source hash or Windows real-device enforcement.

## G09 — 자원·연결 상태

### G09.01 CPU·메모리 값의 측정 범위·출처를 정확히 표기

- 원본 PAC: PAC22
- 제안 완료조건: admin obtains CPU delta and MemTotal-MemAvailable with units, source scope (Linux host/VM), sample time and missing state; no shell/docker socket needed.
- 구현 위치/심볼: full_stack_lab/gateway/app/system_metrics.py, full_stack_lab/gateway/app/agent_service.py::system_metrics
- 회귀 후보: full_stack_lab/tests/system_metrics_check.py
- 근거 경로: research/llm-wiki/status/reports/2026-10-13-development-results.md
- 알려진 공백: Measured /proc is host/VM visible data, not physical Windows or per-container quota. Historical deployed code rev differs from present worktree.
- 현재 제안 플래그 (I/R/D/실기기/완료): 1/0/1/1/0
- 인용된 근거 날짜/범위: 2026-10-13-development-results.md: 2026-10-13 historical report; deployed implementation rev 6178dd3; not a rerun on this review branch.

### G09.02 Console→고정 Gateway DNS/TCP 지연(ms) 표시 범위

- 원본 PAC: PAC22
- 제안 완료조건: fixed endpoint measurement shows DNS+TCP connect latency in ms and test failure/timeout/target semantics; do not label as user-device RTT.
- 구현 위치/심볼: full_stack_lab/gateway/app/system_metrics.py, full_stack_lab/gateway/app/agent_static/console.js
- 회귀 후보: full_stack_lab/tests/system_metrics_check.py, full_stack_lab/tests/console-state.test.mjs
- 근거 경로: research/llm-wiki/status/reports/2026-10-13-development-results.md
- 알려진 공백: The metric is internal Console→Gateway DNS/TCP connect, not PC→solution tailnet round-trip or packet loss.
- 현재 제안 플래그 (I/R/D/실기기/완료): 1/0/1/1/0
- 인용된 근거 날짜/범위: 2026-10-13-development-results.md: 2026-10-13 historical report; deployed implementation rev 6178dd3; not a rerun on this review branch.

### G09.03 미측정·실패·오래된 데이터의 신선도 표현

- 원본 PAC: PAC22
- 제안 완료조건: first sample, stale >30s, timeout, unknown and zero are visually distinct; no stale cached measurement is presented as current.
- 구현 위치/심볼: full_stack_lab/gateway/app/system_metrics.py, full_stack_lab/gateway/app/agent_static/console.js
- 회귀 후보: full_stack_lab/tests/system_metrics_check.py, full_stack_lab/tests/console-state.test.mjs
- 근거 경로: research/llm-wiki/status/reports/2026-10-13-development-results.md
- 알려진 공백: Report says initial/30s-old CPU and stale/failure show —, but this design WBS does not independently rerun tests on current source.
- 현재 제안 플래그 (I/R/D/실기기/완료): 1/0/1/1/0
- 인용된 근거 날짜/범위: 2026-10-13-development-results.md: 2026-10-13 historical report; deployed implementation rev 6178dd3; not a rerun on this review branch.

### G09.04 관리자 scope·화면 갱신·Chrome 실제 표시 확인

- 원본 PAC: PAC08, PAC22
- 제안 완료조건: unauthenticated, employee MCP scope, wrong role denied; admin console token sees current values, refresh cadence and stale states on actual supported Chrome.
- 구현 위치/심볼: full_stack_lab/gateway/app/agent_service.py::system_metrics, full_stack_lab/gateway/app/agent_static/console.js
- 회귀 후보: full_stack_lab/tests/open_endpoints.py, full_stack_lab/tests/console-state.test.mjs
- 근거 경로: research/llm-wiki/status/reports/2026-10-13-development-results.md
- 알려진 공백: Chrome product display was observed, but raster capture timed out; unauthorized/session-expired behavior was browser-specific.
- 현재 제안 플래그 (I/R/D/실기기/완료): 1/0/1/1/0
- 인용된 근거 날짜/범위: 2026-10-13-development-results.md: 2026-10-13 historical report; deployed implementation rev 6178dd3; not a rerun on this review branch.

## G10 — 개발 협업 가시성

### G10.01 개발 협업 현황 웹에서 공개 요청·응답·작업·검사 열람

- 원본 PAC: PAC22
- 제안 완료조건: actual request/response/task/check events render with links; raw conversation and secrets stay in ignored runtime; product operator view remains separate.
- 구현 위치/심볼: research/collaboration-console/, research/collaboration-console/console.py
- 회귀 후보: research/collaboration-console/test_console.py
- 근거 경로: research/llm-wiki/status/reports/2026-10-13-development-results.md
- 알려진 공백: Console is local development collaboration UI, not product operations Console; actual coverage limited to emitted public events.
- 현재 제안 플래그 (I/R/D/실기기/완료): 1/0/0/0/0
- 인용된 근거 날짜/범위: 2026-10-13-development-results.md: 2026-10-13 historical report; deployed implementation rev 6178dd3; not a rerun on this review branch.

### G10.02 모델 요청값·실응답 모델·turn error/NO_TOOL_CALL 구분

- 원본 PAC: PAC22
- 제안 완료조건: viewer distinguishes requested model/effort, actual response model, quota error, turn failed, zero calls and gateway silence; raw transcripts remain private.
- 구현 위치/심볼: research/collaboration-console/console.py, research/collaboration-console/
- 회귀 후보: research/collaboration-console/test_console.py
- 근거 경로: research/llm-wiki/status/reports/2026-10-14-pj1-nine-tools.md
- 알려진 공백: PJ1 Codex turn was refused before tool call due usage limit; absence of Gateway log was correctly not a Gateway logging bug. Synthetic/declared model labels must not be presented as server-used model.
- 현재 제안 플래그 (I/R/D/실기기/완료): 1/0/0/0/0
- 인용된 근거 날짜/범위: 2026-10-14-pj1-nine-tools.md: 2026-10-14 D-79 invalidated self-approved run; not positive test evidence.

### G10.03 WBS 40 원자항목의 목표·PAC·근거·단계 상태 추적

- 원본 PAC: PAC01, PAC02, PAC22
- 제안 완료조건: each G01-G10 contains exactly four unique atomic tasks; every task links PAC source, code/tests, exact evidence, gap, five equal 20% stage flags; current-source review gates regression.
- 구현 위치/심볼: research/llm-wiki/analysis/wbs-review/suggestions.json, research/llm-wiki/tools/check_wiki.py
- 회귀 후보: research/llm-wiki/tools/check_wiki.py
- 근거 경로: research/llm-wiki/status/reports/2026-10-13-development-goals.md
- 알려진 공백: This requested WBS is a proposal. Parent calculates completion rate; do not claim tests/report dated PASS apply to current sources unless source hash matches.
- 현재 제안 플래그 (I/R/D/실기기/완료): 0/0/0/0/0
- 인용된 근거 날짜/범위: 2026-10-13-development-goals.md: 2026-10-13 goal definition, not implementation proof.

### G10.04 보고·증거 원본 hash·상태변경·완료율 공개 기준

- 원본 PAC: PAC22
- 제안 완료조건: web view links immutable evidence and raw/source hashes, states report date and proof layer, preserves invalid/superseded history, and never counts manual telemetry as automatic collection.
- 구현 위치/심볼: research/llm-wiki/analysis/wbs-review/, research/llm-wiki/status/current.md, research/llm-wiki/status/backlog.md
- 회귀 후보: research/llm-wiki/tools/check_wiki.py
- 근거 경로: research/llm-wiki/status/reports/2026-10-14-pj1-ghidra-logs.json
- 알려진 공백: D-79 invalid runs and partial E13/automatic-vs-manual logs must retain separate statuses; summary must not flatten as complete.
- 현재 제안 플래그 (I/R/D/실기기/완료): 0/0/0/0/0
- 인용된 근거 날짜/범위: 2026-10-14-pj1-ghidra-logs.json: 2026-10-14 19:13:55 KST actual SDK read and separate manual/automatic log-channel evidence.

## 상위 위험

| ID | 위험 | 현재 증거 경계 |
| --- | --- | --- |
| R1 | E13/endpoint boundary overclaim | Real PJ1 evidence proves selected Linux UID/profile kernel checks, unapproved Node/interpreter denial and loopback attempts; it does not prove an actual official filesystem stdio tool-call denial. E13 remains not_run; managed account only. |
| R2 | Detection forwarding gap | GhidraMCP stdio process auto-forwarding is disabled (NETSCAN=0). A one-time manual report was accepted as shadow/suspected. Separately an OS kernel denial event auto-forwarded in about 35.84 seconds. Manual and automatic channels must not be merged. |
| R3 | Invalid self-approved success history | D-79 invalidated the earlier 9-tool self-approval test; do not count ledger IDs 744-800 or its “9/9” as governance completion. |
| R4 | Regression evidence may not match current sources | Offline report contains baseline/final PASS but this WBS review did not rerun tests or establish current working-tree hashes equal to report hashes. Keep regression stage false pending hash match or rerun. |
| R5 | Telemetry false zero/false coverage | No endpoint event or Gateway decision can mean no event, disabled forwarding, unsupported account or outside-control path. Show last-success/freshness, received-vs-all counts and explicit unsupported scope. |
| R6 | Raw evidence integrity/privacy | Do not replace source raw hashes with hashes of sanitized/report JSON. Keep raw hash, projection hash, redaction map, event timestamp and receiver hash bound while never publishing secret raw payload. |
| R7 | Scope namespace mismatch | PAC01-PAC24 from original source and runtime PAC-01..15 are different ID namespaces. Maintain explicit semantic mapping. |

테스트·배포·기기 상태는 변경하지 않았고 완료율을 산정하지 않았다. 작업 트리가 dirty하므로 과거 테스트 PASS는 report/revision/hash 대조 또는 재실행 전까지 현 source PASS가 아니다.
