# 데이터 모델

LiteLLM 선택 동기화(D-208)는 `litellm_sync_jobs`에 서버별 revision·fingerprint·재시도 상태·적용 대상·자격 모집단 확인불가 상태를 저장한다. 이 표는 수정 가능한 작업 상태다. G5 재조회 증거는 기존 append-only `approval_events(kind=litellm-sync)`에 별도 추가하며 판정 행을 고치지 않는다. [계약](LITELLM_SYNC.md).

도입 신청의 `requested_tools`(JSON 도구 이름 배열, 빈 저장소 선택은 전체)은 `v2_tables.sql` 끝의 추가 열이다(D-184·187). 검사 워커의 `evidence` 재작성에도 신청자의 선택을 보존한다. `evidence.approval_proposal`은 읽기 화면의 계약·검사·신청 지문과 자동 제안이고, `one_click_pending`은 같은 범위의 승인자 목록, `one_click_scope`는 등록 시 재확인할 최종 선택 범위다. 감사의 정본은 append-only `approval_events`이며 신청 상태의 JSON 갱신은 감사 행 수정이 아니다.

> DB: Gateway의 PostgreSQL(`db`, 데이터베이스 `mcp_governance`; LiteLLM은 같은 서버의 `litellm` DB).
> 스키마 파일: `full_stack_lab/db/init.sql`(기본) → `gateway/app/agent_tables.sql` →
> `lifecycle_tables.sql` → `v2_tables.sql`(v2 추가·제약 재정의) → `oidc_tables.sql` → `ops_tables.sql`. Gateway와 agent-service가 기동할 때
> 이 순서로 멱등 실행한다. 마이그레이션 도구는 없다 — `CREATE … IF NOT EXISTS`/`ALTER … ADD COLUMN IF NOT EXISTS`.

D-120~D-123 추가: `runtime_image_scans`(이미지 검사 이력), `alert_self_tests`(합성 자체 시험), `ops_alerts`(경보·합성 표식), `ops_suspensions`(중지와 사람 복귀), `disposal_blocks`(외부 서명 목록에서 재구성한 차단 상태). 검사·경보·자체 시험 이력과 `approval_events`는 추가만 한다. `ops_suspensions`는 관리자가 복귀할 때 복귀 필드를 채우는 상태 기록이며 감사 판정을 수정하는 테이블이 아니다. 서명 목록 정본은 `/disposal` 볼륨이다. [운영 대응](OPS_RESPONSE.md).
D-181 추가: `user_server_suspensions`(직원×서버 이용 중지 상태, 조합당 활성 행 1개). 재개는 복귀 필드를 채우는 상태 갱신이고, 누가 언제 무엇을 했는지는 같은 트랜잭션의 `approval_events`(`user-server-suspend`·`user-server-resume`)가 추가만으로 남긴다.
D-235 추가: `user_upstream_credentials`(직원×endpoint 연결 자격, 조합당 1행). `ciphertext`는 AES-GCM(주체·endpoint를 연결 데이터로 묶음)이고 키는 기기 비밀 `USER_CREDENTIAL_KEY`다. `account`(GitHub 로그인 이름)·`expires_at`·`created_at`·`last_used_at`만 평문이며 값은 로그·원장·응답에 나가지 않는다. 연결·해제는 `approval_events`(`upstream-credential-connect`·`upstream-credential-disconnect`)가 값 없이 남긴다.
D-200 추가: `local_jobs.run_seconds`는 요청의 원래 실행 제한(0초 초과·최대 20초, 기존 행 기본 20초)이다. 초기화의 준비 기한과 구분하며 `/start`가 `deadline`과 `lease_until`을 이 실행 제한으로 줄인다. 비밀 검사한 종료 진단은 `local_jobs.error`와 append-only `local_job_events.evidence.failure`에 같은 값으로 남긴다. 후자의 존재를 확인한 오류만 게이트웨이의 공개 로컬 실행 진단으로 전달한다.
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
| `outcome` | D-136: 새 기록의 연결·정책 판정·도구 업무·독립 효과 네 축 JSON 스냅샷. 체인 판본 8에 포함. 과거 행은 NULL 유지 |
| `approval_id` | 승인 대기 요청 |
| `enforcement`, `would_decision`, `would_policy_id` | 관찰 모드 기록 |
| `client` | `{workstation, agent, harness, endpoint, task_id, token_jti, oauth_client}` — 클라이언트가 보고한 값, 그대로 기록. `harness`는 `{name, version, user_agent}`(MCP `initialize`의 clientInfo — `claude-code`, `codex-mcp-client`, `gemini-cli-mcp-client`, `opencode`, `inspector-cli`). `endpoint`는 호출이 들어온 서버 id 또는 `aggregate`(집계 엔드포인트). `workstation`은 `X-Workstation-Id` 헤더가 없으면 토큰의 `client_id`(=워크스테이션)로 대신한다. 판정에는 쓰지 않고 기록만 |
| `request_payload`, `result_preview`, `error` | 인자(긴 문자열 축약)·결과 미리보기·오류 |
| `policy_input` | OPA에 보낸 입력 전체(재생용). 개인정보 값은 없고 유형만 |
| `risk_score`, `privacy_types`, `sequence_flags` | 조사용 위험 점수(0~100), Presidio 엔터티 유형(입력 ∪ 출력), 연쇄 표지 |
| `timings` | 구간별 처리 시간 ms(`identity`…`inspect_out`, `total`, D-95). 지문 밖 운영 정보이며 행을 쓸 때 함께 기록 |
| `prev_sha256`, `entry_sha256`, `chain_version` | 해시 체인(v6). `core.AUDIT_COLUMN_SETS[6]`의 열이 지문에 들어간다. v5 이하 행은 자기 버전의 열 집합으로 검증 |

- 트리거 `decisions_append_only`가 UPDATE/DELETE를 거부한다.
- `audit_chain`(1행)이 체인 head와 항목 수를 가진다. `GET /api/audit/verify`가 전체를 다시 계산해
  끊긴 행 id를 돌려준다(`tests/security_regression.sh`가 변조 → 지목 → 원복을 확인).
- 사람이 읽는 형태는 `activity.describe()`가 만든다(Console·`watch` 공용).

### `approvals`
`request_payload`(서버·도구·인자·클라이언트), `status`(PENDING → APPROVED → EXECUTED | NOT_EXECUTED |
UNCONFIRMED, 또는 REJECTED/EXPIRED), 만료 `APPROVAL_TTL_MINUTES`, `executed_decision_id`. 승인하면 Gateway가
`approval.granted=true`로 **다시 판정**해 실행한다(한 번만 — 두 번째 승인은 거부). 재판정에서 전송 전에 멈추면
NOT_EXECUTED, 전송했지만 결과를 확인하지 못하면 UNCONFIRMED(외부 효과가 있었을 수 있음). REJECTED는 사람의
거부와 요청 무결성 실패뿐이다(D-27).

### `dispatch_intents` — 보내기 직전의 기록 (D-96)
`request_id`(PK), `user_token`, `server_id`, `tool_name`, `action`, `fingerprint`(예약과 같은 지문), `attempted_at`,
`state`(pending → resolved | uncertain, 관리자 확인 후 confirmed_executed | confirmed_not_executed), `decision_id`,
`resolved_at/by`, `note`. 판정 원장(`decisions`)과 별개 표이며 원장은 그대로 append-only다. 전송 직전 한 문장에서
예약·주체·서버를 확인하며 쓰고(`dispatch.record`), 판정을 기록한 뒤 예약 해제와 같은 문장에서 닫는다.
`uncertain` 또는 예약이 사라진 `pending`은 같은 쓰기 호출(`w`/`x`)을 `P-RATE-003`으로 막는다. 읽기는 막지 않는다.

D-126: `resolved`·`confirmed_executed` 쓰기도 `resolved_at`부터 기본 24시간 같은 주체·서버·도구·인자 지문을 차단한다.
`IDEMPOTENCY_TTL_SECONDS`는 완료 이력의 집행 기간이며 행 삭제 TTL이 아니다. `pending`·`uncertain`에는 적용하지 않는다.
`confirmed_not_executed`는 재시도 가능하다. 기존 `(user_token, fingerprint)` 부분 인덱스와 별도로 전체 상태 조회 인덱스를 둔다.
전송 직전의 재확인·intent 삽입·승인 소비도 예약과 같은 주체별 advisory lock 안에서 이루어진다. 결과 본문은 저장하지 않는다.

### `call_reservations`
진행 중 호출의 자리. 주체별 advisory lock 안에서 세고 쓴다. TTL로 스스로 만료한다. 전송이 확인되지 않은 호출의 자리는
풀지 않고, 막는 근거는 `dispatch_intents`가 가진다.

### `upstream_pool_events`
`endpoint`·`principal`(NULL이면 전체)·`reason`. 종료 개시·계정 중지/삭제가 남기고, 다른 게이트웨이 프로세스가
풀 연결을 사용하기 직전(2초 간격 이내)에 읽어 닫는다.

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
- 증거 종류에 `resource-rejection`(보호 자원이 이전 토큰을 거부/수락한 응답)이 있다. 대상 `criteria`에는 서버 보유 자격에 한해 `provider_side`(`rejected`/`accepted`/`unverified`, `expires_at`)가 붙는다.
- CHECK 제약(`revocation_targets_kind_check`, `termination_evidence_kind_check`)은 `v2_tables.sql`이 새 종류로 다시 만든다.
→ 규칙은 [TERMINATION_MODEL.md](TERMINATION_MODEL.md).

## 4. 신원
- `principals`: `token`(판정 원장의 주체 키, 예 `emp-ysg`), `user_id`, `email`, `display_name`, `role`,
  `department`, `status`(active/disabled/locked — 매 요청 확인), `password_hash`(bcrypt, DB의 `crypt()`로 비교).
- `agent_revoked_tokens`: 로그아웃·폐기된 JWT의 `jti`(uuid)와 만료.
- `oauth_issued_tokens`(jti text, family), `oauth_refresh_tokens`(해시·회전·폐기): refresh family 폐기 시
  같은 family의 접근 토큰 jti를 `agent_revoked_tokens`에 넣는다(`jti::uuid` 주의).
- `oidc_bindings`: 고유 `(issuer,subject)`를 기존 `principals.token`에 관리자가 명시적으로 연결한다.
  `linked_by/at`로 연결 기록을 보존한다. 공급자 이메일·role로 자동 연결하지 않는다.
- `console_sessions`: Console JWT의 jti, 사용자, 절대 만료, 마지막 사용자 활동 시각. 관리자는 서버가 유휴 30분과
  최대 8시간을 함께 강제한다. 브라우저는 실제 사용자 활동이 있을 때만 인증된 heartbeat를 보낸다.
- `oidc_sessions`: binding FK, Console JWT의 jti, AES-GCM 암호화된 외부 access token과 관리자용 refresh token,
  외부 access token 만료, 절대 만료, 60초 handoff 해시와 만료. handoff는 한 번 소비하고 binding 삭제 시 세션을 함께 삭제한다.
  관리자 접근 토큰은 만료 직전에 갱신하며 교체된 refresh token도 암호화해 저장한다. 요청마다 외부 introspection과 기존 계정 상태를 확인한다.

## 5. 엔드포인트 평면
`endpoint_agents`(장치·소유자·키 해시·scopes), `endpoint_inventory`(설정 파일에서 찾은 MCP 서버,
`classification` registered/shadow/retired-residue, `registry_match`, `fingerprint`), `endpoint_listeners`
(망/소켓에서 찾은 MCP 리스너), `endpoint_scan_policy`, `endpoint_os_events`(OS 거부 이벤트), `endpoint_network_samples`.

증거 열(D-86–D-88): `endpoint_inventory`·`endpoint_listeners`·`endpoint_os_events`에 `origin`(`automatic`/`manual`/`os_event`, 옛 행은 NULL)과 `provenance` jsonb
(`raw_sha256`, `agent_projection_sha256`, `server_projection_sha256`, `state` match/mismatch/unreported, `transformations`, `collector`, `received_at`)가 있다.
`endpoint_os_events`는 `raw_sha256`(7일 재전송 중복 판정)·`denial_class`(`harness_startup`/`blocked_attempt`/`listener_reply`/`unknown`)를 더한다.
관리형 Linux·Windows 관측기는 보호 설정 경로의 JSONL 버퍼에 정제 이벤트와 원본 SHA-256만 최대 8 MiB·10,000건·7일 보관한다. 재전송은 이 표의 기존 `raw_sha256` 7일 규칙과 `(endpoint_id,event_id)` 유일 키를 따른다. 한도 초과로 버퍼에 넣지 못한 이벤트 수와 보존 만료 폐기는 재연결 시 `endpoint_buffer_events`에 UID로 중복 제거해 추가하며 원본 이벤트 본문은 남기지 않는다. 한도 초과 시 원천 커서를 유지해 후속 수집을 멈춘다.
`endpoint_network_samples(endpoint_id, measured_at, rtt_p50_ms, rtt_p95_ms, jitter_ms, failure_pct, probes, received_at)`는 PK `(endpoint_id, measured_at)`이고
적재하는 하트비트가 7일 지난 행을 지운다. `endpoint_agents.detail.install_receipt`는 Gateway가 렌더링한 파일 해시(`provider_artifact_sha256`)와
장치가 보고한 설치 파일 해시(`installed_sha256`)를 따로 둔다. 감사 원장(`decisions`)은 그대로 append-only이며 연관 조회는 읽기만 한다. D-145 상관 조회는 `decisions.request_id`로 `dispatch_intents`를 정확히 잇고, `trace_id`를 함께 반환한다. 엔드포인트 관측은 같은 `endpoint_id`·소유 주체·시간 창을 모두 확인한 보조 근거로 표시한다. trace ID가 없는 과거 행은 그대로 조회하되 ID를 추정하지 않는다.

## 6. 공급망·도입
`mcp_intake_requests`(도입 신청. `exit_terms`는 관리자 검증 기록: 세 조항·`evidence_url`·`note`·`verified_by`·`verified_at`, D-26;
`internal_repo_url`은 Gitea `mcp` 조직의 사본, `registered_server_id`는 Gateway에 등록한 서버 id, D-48·D-49), `scan_jobs`(과거 코드 감사 작업 기록, 새 작업 없음), `supply_chain_reports`,
`worker_heartbeats`, `aig_risk_catalog`(AI-Infra-Guard 위험 범주 ↔ 통제 매핑).

D-90~D-92에서 더한 것(`v2_tables.sql`, 모두 멱등): `mcp_intake_requests.provenance`(출처 기록 — 공급 주소·고정 버전·라이선스·배포 파일 해시·사본 대조 결과; 제공자 운영 서비스는 `kind=provider-hosted`와 "해당 없음"),
`supply_chain_reports.vuln_db_updated_at`(그 검사가 쓴 취약점 DB의 갱신 시각), `accepted_risks`(치명적 발견의 기한부 수용: 신청·커밋·발견 id·사유·수용자·만료),
`mcp_tools.scope_review`(도구별 목적·자산·행위·외부 목적지), `approval_events`(승인·거부·보류·수용·등록 기록, append-only),
`audit_annotations`(`decisions.id` 범위의 무효 처리 표시, append-only). Console 등록 서버의 `servers.json` 항목에는 `tool_reviews`와 `provenance`가 들어간다.
DEV-78·D-180: `mcp_runtimes.rollback_target_generation`·`rollback_contract`는 중지 중인 세대가 되돌릴 승인 세대와 계약 스냅샷을 worker에 전달한다. `runtime-active` 승인 이벤트의 `scope.contract`에는 도구별 승인 설명·입력 스키마·출력 스키마 해시와 서버 판본, 계약 SHA-256, 마지막 사람 승인자·시각이 들어간다. 출력 스키마 해시(NULL 포함)는 D-149 승인 상태 그대로 보존한다. 되돌리기는 같은 `intake_id`의 과거 `runtime-active` 이벤트가 있는 세대만 선택할 수 있다. 실행기 정지·계약 복원·새 세대 예약은 worker가 한 DB 트랜잭션에서 처리하며 부분 유일 색인이 동시에 살아 있는 세대를 막는다. 과거 이벤트에 계약 스냅샷이 없는 세대는 자동 보충하거나 선택지로 노출하지 않는다.
D-143에서 더한 것: `mcp_intake_requests.risk_input`(신청자가 적은 영향평가 입력 여섯 항목, 등급은 저장하지 않고 `risk_tier.assess`로 매번 계산), `servers.json` 항목의 `risk_assessment`(등급·점수·입력·`input_sha256`·승인자)와 문서 최상위의 `risk_tier_grace_started_at`(입력 없는 기존 승인의 30일 유예 시작), `approval_events`의 `intake-cosign`(두 명 승인의 첫 번째)·`risk-input`(입력 기록).

Console 등록 서버(D-49)는 DB가 아니라 `REGISTRY_RUNTIME_DIR/servers.json`에 있다 — `servers`(catalog.toml과 같은 모양 +
`valid_until`·`intake_id`·`registered_by`), `contracts`(등록 때 고정한 도구 해시), `usage_relationships`(`UR-<ID>`), `history`(등록·연장·해제).
`registry.sync()`가 이 파일을 카탈로그와 함께 `mcp_servers`·`mcp_tools`(`approval_valid_until` = 사용 기한)·`usage_relationships`로 옮긴다.

## 7. 설정·정책
`gateway_settings`(`enforcement` = enforce/monitor), `policy_versions`(배포된 정책 묶음 — `policy.rego`·`pac15.rego`·`decision.rego`·`data.json`·`policy_ledger.json` — 의 sha256, id `bundle-<12자>`, D-25).

## 8. 쓰지 않는 v1 잔재
`agent_sessions`, `agent_runs`, `agent_gateway_receipts`(v1 웹 채팅)는 아직 `agent_tables.sql`이 만든다.
v2 코드는 읽지도 쓰지도 않는다 → [ROADMAP.md](ROADMAP.md) 정리 항목.

## 9. 회사 데이터 (`corp-db`, MCP 서버가 다루는 대상)
`public.products`(공개), `sales.orders`(내부), `sales.customers`(PII, 중요), `hr.employees`(내부),
`hr.salaries`(중요). 파일·저장소·메일·Redis·인트라넷 시드는 `corp/seed.py`(멱등, `--force`로 재시드).

## 선택적 제한·관제 전달 (D-127·128)

`catalog_snapshots.restricted_tools`는 제한 도구 이름 배열이다. `exact_match=true`는 전체 승인본 일치, `false`와 배열은 도구별 영향, `false`와 `NULL`은 전체 영향 미확정이다. 이전 스냅샷을 수정하지 않고 새 관측을 추가한다. 도구 자체의 승인 해시 비교·공급망·폐기·사용 권한은 별도로 적용한다.

`siem_outbox`는 원장이 아닌 전송 상태다. 소스 테이블·소스 ID 유일 키, 시도 수·다음 시각·수신 확인 시각·오류 종류만 보관한다. `decisions`, `approval_events`, 합성이 아닌 `ops_alerts`의 INSERT와 같은 트랜잭션으로 참조를 추가한다. 워커는 원장 내용을 수정하지 않고 큐 상태만 갱신한다. 별도 네트워크 워커가 중단되어도 참조는 DB에 남는다. 마이그레이션 이전 행은 자동 소급하지 않으며 보존·삭제 작업도 추가하지 않았다.

D-157의 전송 UID는 원장 행 ID와 사슬 해시(사슬 없는 소스는 UTC 기록 시각 해시)로 재구성하며 큐에 본문이나 별도 UID 열을 복제하지 않는다.
`attempts`는 DB에 커밋된 결과 수다. 수신 확인 뒤 큐 커밋 전 장애는 이 값을 늘리지 않으므로 UID별 실제 시도 기록은 워커의 `SIEM attempt` 로그와 대조한다.
로그 보존·D-128 UID 전환·수신 측 유일 키 계약은 [운영 대응](OPS_RESPONSE.md#사건-식별자와-전송-시도-기록-d-157)을 따른다.

## 도입 검증 보고서와 lease
`mcp_intake_requests.evidence`는 `scanners`(검사기별 DONE/FAILED·오류), `reports`(해당 시도의 성공한 산출물 이름), `exit_terms_discovery`(commit 고정 문서 후보 근거), SBOM 구성요소 수·위험 등급별 수를 담는다. `exit_terms`의 관리자 검증 기록과 자동 조사 결과는 별도 필드다.

`validation_lease_expires_at`와 `validation_attempts`는 VALIDATING 작업의 중단 복구에 쓰인다. 신규 요청은 API의 단일 INSERT에서 VALIDATION_QUEUED가 된다. Syft·Trivy·Semgrep·Gitleaks의 정규화 요약은 `supply_chain_reports`에 남고 Console은 source_ref뿐 아니라 신청 UUID가 포함된 report_path로 귀속을 제한한다. Gitleaks 산출물은 RuleID·상대 파일·행·설명만 남기고 Secret/Match를 제거한다. 부분 검사 실패 시 수집한 증적은 남지만 요청 상태는 FAILED이며 승인되지 않는다.

D-178: Syft 원본 CycloneDX JSON은 `intake_reports` named volume에 보존하고 `supply_chain_reports.summary.inventory`에는 앞 200개 구성요소만 보존한다(`truncated`로 잘림 표시). SBOM 영향 조회는 `registered_server_id`·`intake_id`·`mcp_runtimes.generation`과 현재 Syft 성공·source commit이 일치하는 경우만 판정한다. `workspace` 등 intake와 연결되지 않은 요약, 검사 실패·누락, 잘린 목록에서 찾지 못한 패키지는 완전한 비영향 증거가 아니다. 전체 원본 파일을 읽지 않는 이 조회는 DB에 저장된 요약 범위까지만 정확하다. 서버·실행 세대는 사용자·엔드포인트 영향으로 확장하지 않는다.

## 중대 영향 개별 승인 증빙 (D-139)

`approvals.explanation`은 요청 생성 시 고정한 원문 없는 설명 JSONB다. `revoked_at`·`revoked_by`는 승인 후 원승인자의 번복을 기록한다. 기존 status는 실행 경과를 유지하며 조회에서 revoked_at이 있으면 「승인 번복」으로 표시한다.
`request_payload.impact_scope_sha256`은 심사자/시각을 제외한 도구 범위 해시다. 기존 request_fingerprint는 원래 주체·서버·도구·인자를 포함한 저장 요청 전체를 결속한다. 최종 전송에서 현재 scope_review와 대조한다.
`approval_events`의 call-request/recorded, call-explanation-view/recorded, call-approve/approved, call-reject/rejected, call-revoke/recorded를 재사용한다. 신청·승인·거부·번복은 해당 상태 변경과 같은 트랜잭션으로 기록하며 사건/판정 행의 UPDATE·DELETE는 추가하지 않는다. 열람은 별도 append다.
설명·개입·판정 번들에는 인자 키·값·요청/응답 본문·자유 산문을 포함하지 않는다. 번복은 이미 전송된 호출이나 외부 효과를 복구하지 않는다. 실제 PostgreSQL 검증은 기기에서 수행한다.

## MCP 클라이언트 세션 종료 (D-146)

- `mcp_client_sessions`: 다운스트림 `Mcp-Session-Id`의 SHA-256, 검증된 주체·토큰 `jti`·장치·개별 서버 경로 및 종료 상태. 세션 ID 원문은 저장하지 않는다.
- `mcp_session_events`: 주체·장치·서버·세션 종료 사유와 종료 수를 append-only로 기록한다. 게이트웨이 내부 재접근 차단 기록이며 제공자 자원 거부(C4) 증거가 아니다.
- `oauth_issued_tokens` / `oauth_refresh_tokens` / `agent_revoked_tokens`: 계정·장치 종료 때 기존 토큰과 관련 리프레시 계열의 재사용을 막는다.

## 서버 간 전달 내용 지문 (D-142)

- `flow_fingerprints`: 중요 등급 읽기가 클라이언트에 돌려준 본문을 정규화한 문자열의 16자 조각 해시(`shingles`)와 이메일·9자리 이상 숫자의 해시(`identifiers`), 해시에 쓴 주체별 솔트와 `FLOW_FINGERPRINT_PEPPER`의 식별 값(`key_id`). 판정 기록 id(`decision_id`)당 한 행이고 원문은 저장하지 않는다. 10분(`CHAIN_WINDOW_MINUTES`) 뒤 만료되며 만료 행은 다음 중요 등급 읽기 때 지운다. 원장도 증거도 아니어서 수정은 막고(`UPDATE` 트리거) 만료 삭제만 한다. 행이 없는 읽기는 D-133의 거친 표지로 남는다.
