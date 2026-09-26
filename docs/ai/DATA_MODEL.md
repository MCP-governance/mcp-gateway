# 데이터 모델

> DB: Gateway의 PostgreSQL(`db`, 데이터베이스 `mcp_governance`; LiteLLM은 같은 서버의 `litellm` DB).
> 스키마 파일: `full_stack_lab/db/init.sql`(기본) → `gateway/app/agent_tables.sql` →
> `lifecycle_tables.sql` → `v2_tables.sql`(v2 추가·제약 재정의). Gateway와 agent-service가 기동할 때
> 이 순서로 멱등 실행한다. 마이그레이션 도구는 없다 — `CREATE … IF NOT EXISTS`/`ALTER … ADD COLUMN IF NOT EXISTS`.
> 회사 데이터(`corp-db`)는 별도 서버다 → `full_stack_lab/corp/corpdb.sql`.

## 1. 판정과 감사

### `decisions` — 호출 한 건 = 한 행 (append-only, 해시 체인)
| 열 | 의미 |
| --- | --- |
| `id`, `created_at`, `request_id`, `trace_id` | 식별·시각·runtime evidence 연결 키 |
| `user_token`, `role` | transport 토큰에서 정한 주체(`principals.token`) |
| `server_id`, `tool_name`, `resource_id`, `destinations`, `summary` | 무엇을 어디에(분류기 결과) |
| `data_class`, `action` | 자원 등급(public/nonimportant/important), 실효 행위(r/w/x) |
| `decision`, `policy_id`, `reason`, `policy_version`, `obligations`, `exception_id`, `conflicts`, `environment` | OPA 판정 |
| `restrictions` | 제한 실행 시 적용된 제한(`max_chars`, `journal_bcc`) |
| `upstream_attempted`, `upstream_executed` | 전달 시도 / 실행 확인. 시도했는데 미확인이면 종료 판정에서 "실행 여부 미확인" |
| `approval_id` | 승인 대기 요청 |
| `enforcement`, `would_decision`, `would_policy_id` | 관찰 모드 기록 |
| `client` | `{workstation, agent, harness, endpoint, task_id, token_jti, oauth_client}` — 클라이언트가 보고한 값, 그대로 기록. `harness`는 `{name, version, user_agent}`(MCP `initialize`의 clientInfo — `claude-code`, `codex-mcp-client`, `gemini-cli-mcp-client`, `opencode`, `inspector-cli`). `endpoint`는 호출이 들어온 서버 id 또는 `aggregate`(집계 엔드포인트). `workstation`은 `X-Workstation-Id` 헤더가 없으면 토큰의 `client_id`(=워크스테이션)로 대신한다. 판정에는 쓰지 않고 기록만 |
| `request_payload`, `result_preview`, `error` | 인자(긴 문자열 축약)·결과 미리보기·오류 |
| `policy_input` | OPA에 보낸 입력 전체(재생용). 개인정보 값은 없고 유형만 |
| `risk_score`, `privacy_types`, `sequence_flags` | 조사용 위험 점수(0~100), Presidio 엔터티 유형(입력 ∪ 출력), 연쇄 표지 |
| `prev_sha256`, `entry_sha256`, `chain_version` | 해시 체인(v6). `core.AUDIT_COLUMN_SETS[6]`의 열이 지문에 들어간다. v5 이하 행은 자기 버전의 열 집합으로 검증 |

- 트리거 `decisions_append_only`가 UPDATE/DELETE를 거부한다.
- `audit_chain`(1행)이 체인 head와 항목 수를 가진다. `GET /api/audit/verify`가 전체를 다시 계산해
  끊긴 행 id를 돌려준다(`tests/security_regression.sh`가 변조 → 지목 → 원복을 확인).
- 사람이 읽는 형태는 `activity.describe()`가 만든다(Console·`watch` 공용).

### `runtime_evidence` — 운영 span 증적 (append-only, 멱등 저장)
OpenTelemetry SDK가 만든 span은 OTel Collector에서 민감 속성을 제거한 뒤 내부 Audit API
(`POST /api/audit/otlp/v1/traces`)로 전달된다. Audit API는 원문 요청·응답·토큰·MCP 인자를 저장하지 않고
서비스명, 작업명, 시작·종료 시각, 상태와 허용 목록에 든 운영 메타데이터만 정규화한다.

| 열 | 의미 |
| --- | --- |
| `trace_id`, `span_id`, `parent_span_id` | 요청 흐름 연결 키. `(trace_id, span_id)`는 Collector 재시도 중복 방지 키 |
| `service_name`, `operation` | span을 만든 서비스와 작업 |
| `started_at`, `ended_at`, `duration_ms`, `status_code` | 실행 시각·지연·성공/오류 상태 |
| `attributes`, `events` | 서버 측 허용 목록을 통과한 메타데이터와 이벤트 |
| `received_at` | Audit API가 증적을 수신한 시각 |

- `runtime_evidence_append_only` 트리거가 UPDATE/DELETE를 거부한다.
- 정책 결정 원장인 `decisions`의 해시 체인과는 별도다. 운영 흐름 증적을 보존하되 정책 판정 증적이라고
  과장하지 않기 위한 구분이다.
- 관리자만 `GET /api/runtime-evidence`와 Console의 **Runtime Evidence** 탭에서 조회한다.
- Collector→Audit API는 사용자 JWT가 아니라 별도 `OTEL_AUDIT_INGEST_TOKEN`으로 인증하며,
  동일 호스트 내부망 구간은 무압축 protobuf로 고정한다. 수집 API는 다른 표준 클라이언트를 위해 gzip도
  압축·해제 양쪽 크기 제한 아래 처리한다. 수집 endpoint 자체는 다시 trace하지 않아 재귀 전송을 막는다.

### `approvals`
`request_payload`(서버·도구·인자·클라이언트), `status`(PENDING → APPROVED → EXECUTED | NOT_EXECUTED |
UNCONFIRMED, 또는 REJECTED/EXPIRED), 만료 `APPROVAL_TTL_MINUTES`, `executed_decision_id`. 승인하면 Gateway가
`approval.granted=true`로 **다시 판정**해 실행한다(한 번만 — 두 번째 승인은 거부). 재판정에서 전송 전에 멈추면
NOT_EXECUTED, 전송했지만 결과를 확인하지 못하면 UNCONFIRMED(외부 효과가 있었을 수 있음). REJECTED는 사람의
거부와 요청 무결성 실패뿐이다(D-27).

## 2. 레지스트리와 계약

### `mcp_servers`
카탈로그 필드(`display_name`, `package`, `version`, `endpoint`, `deployment` internal/provider,
`downstream`, `source_url`, `supplier`, `license`, `exit_terms`, `server_held_credentials`) +
운영 상태(`status` READY/DRIFT/PENDING/ERROR/DISABLED/BLOCKED_SUPPLY_CHAIN, `status_reason`,
`advertised_name`, `last_seen_at`, `drift_observed_at`) + 전주기(`lifecycle` OPERATING/TERMINATING/RETIRED,
`termination_case_id`).

### `mcp_tools`
`(server_id, name)` 키. `action`(r/w/x), `enabled`(카탈로그 승인 여부), 승인 해시
(`approved_description_hash`, `approved_schema_hash`, `approved_server_version` — 잠금 파일에서 옴)와
관찰 해시(`observed_*`), `description`, `input_schema`(인자 검증에 사용), `annotations`.

- `registry.sync()`: 카탈로그 → DB. 잠금 파일 다이제스트가 바뀐 경우에만 승인 해시를 덮어쓴다.
- `core.refresh_catalog()`: upstream `tools/list` → 관찰 해시. 불일치면 서버 DRIFT.
- `catalog_snapshots`: 관찰 이력.

### `usage_relationships`
`id`(UR-…), `server_id`, `organization`, `purpose`, `provider`, `owner_department`, `allowed_resources`,
`status`(ACTIVE/TERMINATING/TERMINATED). 카탈로그 `[[usage_relationships]]`에서 동기화.

## 3. 종료·폐기
- `termination_cases`: `relationship_id`, `server_id`, `engagement_label`, `provider`, `allowed_resources`,
  `reason`, `status`(OPEN/REVOKING/ASSESSED/CLOSED/REOPENED), `grade`, `criteria`(케이스 판정 전체 JSON),
  `cutover_at`, 개시·판정·종결자와 시각, `risk_accepted_by/at`, `risk_acceptance_note`, `close_note`.
- `revocation_targets`: `kind`, `label`, `holder`, `discovered_by`, `status`(OUTSTANDING/REVOKED/EXPIRED/UNVERIFIABLE),
  `revoked_at/by`, `subject_ref`(주체 토큰·지문·자격 JSON), `expires_at`, `verification`, `criteria`, `grade`.
- `termination_evidence`: `kind`, `subject`, `source`, `detail`, `observed_at`, `target_id`, `sha256`, `recorded_by/at`.
- CHECK 제약(`revocation_targets_kind_check`, `termination_evidence_kind_check`)은 `v2_tables.sql`이 새 종류로 다시 만든다.
→ 규칙은 [TERMINATION_MODEL.md](TERMINATION_MODEL.md).

## 4. 신원
- `principals`: `token`(판정 원장의 주체 키, 예 `emp-ysg`), `user_id`, `email`, `display_name`, `role`,
  `department`, `status`(active/disabled/locked — 매 요청 확인), `password_hash`(bcrypt, DB의 `crypt()`로 비교).
- `agent_revoked_tokens`: 로그아웃·폐기된 JWT의 `jti`(uuid)와 만료.
- `oauth_issued_tokens`(jti text, family), `oauth_refresh_tokens`(해시·회전·폐기): refresh family 폐기 시
  같은 family의 접근 토큰 jti를 `agent_revoked_tokens`에 넣는다(`jti::uuid` 주의).

## 5. 엔드포인트 평면
`endpoint_agents`(장치·소유자·키 해시·scopes), `endpoint_inventory`(설정 파일에서 찾은 MCP 서버,
`classification` registered/shadow/retired-residue, `registry_match`, `fingerprint`), `endpoint_listeners`
(망/소켓에서 찾은 MCP 리스너), `endpoint_scan_policy`.

## 6. 공급망·도입
`mcp_intake_requests`(도입 신청. `exit_terms`는 관리자 검증 기록: 세 조항·`evidence_url`·`note`·`verified_by`·`verified_at`, D-26), `scan_jobs`(격리 워커 작업, lease), `supply_chain_reports`,
`worker_heartbeats`, `aig_risk_catalog`(AI-Infra-Guard 위험 범주 ↔ 통제 매핑).

## 7. 설정·정책
`gateway_settings`(`enforcement` = enforce/monitor), `policy_versions`(배포된 정책 묶음 — `policy.rego`·`data.json`·`exceptions.json`·`policy_ledger.json` — 의 sha256, id `bundle-<12자>`, D-25).

## 8. 쓰지 않는 v1 잔재
`agent_sessions`, `agent_runs`, `agent_gateway_receipts`(v1 웹 채팅)는 아직 `agent_tables.sql`이 만든다.
v2 코드는 읽지도 쓰지도 않는다 → [ROADMAP.md](ROADMAP.md) 정리 항목.

## 9. 회사 데이터 (`corp-db`, MCP 서버가 다루는 대상)
`public.products`(공개), `sales.orders`(내부), `sales.customers`(PII, 중요), `hr.employees`(내부),
`hr.salaries`(중요). 파일·저장소·메일·Redis·인트라넷 시드는 `corp/seed.py`(멱등, `--force`로 재시드).
