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
| `id`, `created_at`, `request_id`, `trace_id` | 식별·시각·Jaeger trace |
| `user_token`, `role` | transport 토큰에서 정한 주체(`principals.token`) |
| `server_id`, `tool_name`, `resource_id`, `destinations`, `summary` | 무엇을 어디에(분류기 결과) |
| `data_class`, `action` | 자원 등급(public/nonimportant/important), 실효 행위(r/w/x) |
| `decision`, `policy_id`, `reason`, `policy_version`, `obligations`, `exception_id`, `conflicts`, `environment` | OPA 판정 |
| `restrictions` | 제한 실행 시 적용된 제한(`max_chars`, `journal_bcc`) |
| `upstream_attempted`, `upstream_executed` | 전달 시도 / 실행 확인. 시도했는데 미확인이면 종료 판정에서 "실행 여부 미확인" |
| `approval_id` | 승인 대기 요청 |
| `enforcement`, `would_decision`, `would_policy_id` | 관찰 모드 기록 |
| `client` | `{workstation, agent, task_id, token_jti, oauth_client}` — 클라이언트가 보고한 값, 그대로 기록 |
| `request_payload`, `result_preview`, `error` | 인자(긴 문자열 축약)·결과 미리보기·오류 |
| `policy_input` | OPA에 보낸 입력 전체(재생용). 개인정보 값은 없고 유형만 |
| `risk_score`, `privacy_types`, `sequence_flags` | 조사용 위험 점수(0~100), Presidio 엔터티 유형(입력 ∪ 출력), 연쇄 표지 |
| `prev_sha256`, `entry_sha256`, `chain_version` | 해시 체인(v6). `core.AUDIT_COLUMN_SETS[6]`의 열이 지문에 들어간다. v5 이하 행은 자기 버전의 열 집합으로 검증 |

- 트리거 `decisions_append_only`가 UPDATE/DELETE를 거부한다.
- `audit_chain`(1행)이 체인 head와 항목 수를 가진다. `GET /api/audit/verify`가 전체를 다시 계산해
  끊긴 행 id를 돌려준다(`tests/security_regression.sh`가 변조 → 지목 → 원복을 확인).
- 사람이 읽는 형태는 `activity.describe()`가 만든다(Console·`watch` 공용).

### `approvals`
`request_payload`(서버·도구·인자·클라이언트), `status`(PENDING → APPROVED → EXECUTED, 또는
REJECTED/EXPIRED), 만료 `APPROVAL_TTL_MINUTES`, `executed_decision_id`. 승인하면 Gateway가
`approval.granted=true`로 **다시 판정**해 실행한다(한 번만 — 두 번째 승인은 거부). 재판정에서 실행되지
않으면 REJECTED로 닫힌다.

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
`mcp_intake_requests`(도입 신청, `exit_terms` 포함), `scan_jobs`(격리 워커 작업, lease), `supply_chain_reports`,
`worker_heartbeats`, `aig_risk_catalog`(AI-Infra-Guard 위험 범주 ↔ 통제 매핑).

## 7. 설정·정책
`gateway_settings`(`enforcement` = enforce/monitor), `policy_versions`(배포된 Rego의 sha256).

## 8. 쓰지 않는 v1 잔재
`agent_sessions`, `agent_runs`, `agent_gateway_receipts`(v1 웹 채팅)는 아직 `agent_tables.sql`이 만든다.
v2 코드는 읽지도 쓰지도 않는다 → [ROADMAP.md](ROADMAP.md) 정리 항목.

## 9. 회사 데이터 (`corp-db`, MCP 서버가 다루는 대상)
`public.products`(공개), `sales.orders`(내부), `sales.customers`(PII, 중요), `hr.employees`(내부),
`hr.salaries`(중요). 파일·저장소·메일·Redis·인트라넷 시드는 `corp/seed.py`(멱등, `--force`로 재시드).
