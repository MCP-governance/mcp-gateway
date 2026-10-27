# MCP 전주기 보안정책 PaC

팀 정책 시트 「MCP 보안 관리 정책」(정책 90개, POL-001~090)을 OPA/Rego 판정 코드로 옮긴 패키지다.
정책 하나하나가 **시트 → 카탈로그 → Rego 규칙 → 시험 → 추적표**로 이어진다.

- 정책 90개 중 Rego 규칙이 있는 정책은 65개다. 나머지 25개는 솔루션 기능이 집행하거나(전송 계층·실행기·감사 저장소·엔드포인트·연동·운영 절차) 현재 범위에서 제외했으며, 사유를 [TRACE.md](TRACE.md)에 둔다.
- 이 패키지는 게이트웨이의 현재 판정 번들(`full_stack_lab/opa/`)과 별도다. 게이트웨이가 아래 입력 계약대로 값을 채워 질의하기 전까지는 판정 경로에 연결돼 있지 않다.

## 구성

```text
policy/
├── README.md              이 문서
├── TRACE.md               정책 추적표(생성 파일)
├── source/
│   ├── sheet.json         시트의 「보안 정책」·「정책 실행 규칙」 추출(생성 파일)
│   └── classification.json 정책별 구현 분류·판정 주체·사유
├── pac/
│   ├── catalog.rego       정책 카탈로그(생성 파일, package mcp.pol.catalog)
│   ├── lib.rego           결과 형식·집계·예외·기간·주소 검사·작성 규칙
│   ├── intake.rego        도입 검토(신청서 한 건)
│   ├── connect.rego       등록 및 연결(연결·승인 기록·로컬 실행·OAuth)
│   ├── call.rego          실행 및 통제(Tool 호출 한 건)
│   ├── ops.rego           운영 및 변경·폐기(운영 중 서버 상태 스냅숏)
│   ├── resource.rego      Resource·Prompt(중개 도입 시 사용)
│   └── *_test.rego        시험
└── tools/
    ├── build_catalog.py   시트 → sheet.json → catalog.rego
    └── trace.py           TRACE.md 생성·추적 검사
```

## 판정 결과

모든 체크포인트 패키지는 `findings`(정책별 판정)와 `decision`(최종 결과)을 낸다.

```json
{"effect": "DENY", "policy_ids": ["POL-001", "POL-068"], "reasons": ["POL-001: 미승인·만료 제공자 또는 배포 주소", "..."],
 "all_policy_ids": ["POL-001", "POL-004", "POL-068"]}
```

| 효과 | 뜻 | 시트 표현 |
| --- | --- | --- |
| `DENY` | 현재 요청 차단 | 차단·거부·중단 |
| `MANUAL` | 사람 판단 전까지 차단 | 보안 관리자 판단 전까지 차단 |
| `CONFIRM` | 요청 사용자 본인 확인 뒤 한 번 진행 | 사용자 확인(POL-053) |
| `RESTRICT` | 제한 허용 | 공개자료 조회만 허용, 한도까지 제한 |
| `ALERT` | 진행하되 알림 | 미확인 표시·보안 관리자 알림 |
| `ALLOW` | 모든 검사 통과 | 자동 통과(다음 단계 진행) |

여러 정책이 걸리면 가장 강한 효과가 결과다(`DENY > MANUAL > CONFIRM > RESTRICT > ALERT > ALLOW`). `policy_ids`·`reasons`에는 그 효과를 낸 정책만, `all_policy_ids`에는 걸린 정책 전부가 들어간다(DENY에 가려진 MANUAL·CONFIRM도 감사 기록에 남기기 위해서다).
모르는 효과 값은 `DENY`로 센다. `ops`는 서버별 조치 목록 `violations`(`{policy_id, server, action, detail}`)도 낸다.

## 입력 계약

판정 입력은 게이트웨이가 검증된 출처(토큰·등록부·관측·조회)에서 만든다. 요청 인자에 적힌 신원·승인·상태는 쓰지 않는다.
모든 입력에 `facts.trusted: true`와 `facts.now_ns`(유닉스 나노초)가 있어야 하고, 없으면 `INPUT_CONTRACT`로 차단한다.
아래 값이 빠지면 해당 정책이 차단한다(값을 모르면 통과가 아니다).

### intake — `data.mcp.pol.intake.decision`

| 입력 | 쓰는 정책 |
| --- | --- |
| `application.id`, `hosting`(`external`·`local`·`gateway_managed`) | 계약 |
| `application.provider`, `source_url` | POL-001 |
| `application.business_scope.{operations, data_types, permissions}` | POL-002 |
| `application.tools[]`: `name`, `declared_effect`(`read`·`write`·`delete`·`share`·`external_send`·`execute`), `data_types`, `permissions`, `requires_confirmation` | POL-002·010 |
| `tools[].description_scan.{status, findings[].level}`(`forbidden`·`unclear`, 무탐지는 `findings: []`) | POL-004 |
| `tools[].output_contract.{fields(문자열 배열), data_scope(문자열 또는 문자열 배열)}` | POL-005 |
| `tools[].trial_results[]`: `observed_effect`, `observed_fields`, `observed_data_scope`, `sensitive_found` | POL-005·006·010 |
| `application.provider_terms.{status, prohibited}`, `gateway_controls.{internal_data_blocked, personal_data_blocked, credentials_blocked, public_read_only}` | POL-009 |
| `application.requirements.{functions, data_types, permissions, acceptance_criteria}` | POL-011 |
| `application.sbom.status`, `packages[]`: `name`, `version`, `source` | POL-068 |

### connect — `data.mcp.pol.connect.decision`

`connection.stage`와 `connection.server_id`는 항상 필요하다.

| 단계 | 입력 | 쓰는 정책 |
| --- | --- | --- |
| `connect` | `kind`(`remote`·`local`), `address`, `identity`, `transport.scheme`, `approval.basis`(`normal`·`exception`), `user`, `requested_functions`, `consent.{user, server_id, decision, functions, not_after_ns, shown.{provider, address, functions}}`, `credential.{used, bound_server}` | POL-012·013·025·029·032·033·073·082 |
| `approve` | 최상위 `approval.{server_id, purpose, scope, policy_version, method(auto·manual·exception), recorded, approver, not_after_ns}` | POL-014 |
| `launch` | `kind`, `approval.basis`, `launch.{executable, args, env, sha256, observed_permissions, isolation.{verified, public_read_only, internal_data_blocked}}` | POL-008·013·029·031·082 |
| `oauth` | `auth_server.{address, id}`, `metadata.{request_host, final_host, resolved_ips}`, `requested_scopes`, `credential.{used, bound_server}` | POL-019·022·023·025·026·082 |

### call — `data.mcp.pol.call.decision`

`request.{id, stage, user, agent, server_id, tool}`는 항상, `request.operation`은 `list` 단계 밖에서 필요하다.

| 단계 | 입력 | 쓰는 정책 |
| --- | --- | --- |
| `request` | `request.target.{data_class, doc_id, path}` | POL-003·034·036·042 |
| | `facts.permission_lookup.{status, request_id}` | POL-035 |
| | `facts.approval.basis` | POL-013 |
| | `facts.catalog.{matches, observed_contract_sha256}` | POL-015·063 |
| | `facts.token.{valid, audience, expires_ns}` 또는 등록부가 로컬로 정한 서버에서 `facts.token.used: false`, `facts.credential.{used, bound_server}` | POL-016·025 |
| | `request.intent`(`call`·`approval`·`permission_change`), `facts.provenance.external_content` | POL-037 |
| | `facts.inspection.{status, secrets, personal_data}`(무탐지는 빈 배열) | POL-038 |
| | `facts.egress.{final_host, resolved_ips}`, `request.{recipient, purpose}` | POL-040·041·047 |
| | `facts.path.resolved`(심볼릭 링크·상위 이동을 푼 실제 경로) | POL-042 |
| | `request.source_server`, `facts.data.contains_credential` | POL-044 |
| | `facts.arguments_validated`, `facts.schema.{valid, undeclared_fields}` | POL-046·048 |
| | `facts.usage.{user, agent, tool}.{window_calls, concurrent}`, `facts.usage.{window_documents, blocked_pattern}` | POL-050·056 |
| | `facts.server_account.used`, `facts.acl.{user_can, user, doc_id}`(이번 요청의 사용자·문서에 대한 조회) | POL-051·052 |
| | `facts.confirmation.{confirmed_by, reserved_for, used, expires_ns, server_id, tool, operation, target, recipient, arguments_sha256}`, `facts.arguments_sha256` | POL-010·053·054 |
| | `facts.audit.{central_writable, buffer_writable, recorded}` — `recorded`는 이번 호출의 실행 전 기록이 저장됐다는 뜻 | POL-058 |
| `response` | `response.{items, bytes}` | POL-049 |
| `list` | `response.{tools, cached, cache_owner}`, `facts.permitted_tools` | POL-064 |

### ops — `data.mcp.pol.ops.decision`, `violations`

`event`: `periodic`·`update`·`restore`·`package_change`·`config_change`·`incident`·`provider_termination`. `servers[]`마다 `id`가 필요하다.

| 서버 값 | 쓰는 정책 |
| --- | --- |
| `config_scan.{status, plaintext_secrets, storage_approved}` | POL-024 |
| `observed_tools[].{name, contract_sha256}`, `approved_tools` | POL-063 |
| `packages[]` | POL-068 |
| `vuln_scan.status`, `vulnerabilities[]`: `id`, `severity`(`critical`·`high`·`medium`·`low`), `exploited`, `exposed`, `affected_version`, `confirmed_ns`, `patched`, `compensating_control.verified`; `scheduled_change_ns` | POL-069·070 |
| `baseline_config_sha256`, `instances[].{id, config_sha256}` | POL-071 |
| `restore.{version, risky_settings, approval.not_after_ns}` | POL-072 |
| `downstream.{observed, approved}` | POL-074 |
| `observed_permissions`, `approved_permissions` | POL-075 |
| `revoke_confirmed`, `in_use_permissions` | POL-076 |
| `oauth_scopes.{observed, approved}`, `tool_permissions.{observed, approved}` | POL-077 |
| `incidents[].{severity, confirmed, tool}` | POL-081 |
| `provider_termination.{requested_complete, evidence_verified, new_transfer_blocked}` | POL-088 |

### resource — `data.mcp.pol.resource.decision`

`request.stage`: `prompt_use`(POL-007·067, `request.prompt`, `facts.{prompt_sha256, prompt_scan.blocked_types, acl.{user_can, user, prompt}}`) · `resource_read`(POL-043, `facts.{resource.resolved_id, acl.{user_can, user, resource_id}}`) · `resource_list`(POL-065, `facts.{permitted_resources, deleted_resources}`) · `resource_update`(POL-066, `facts.change.{source, within_approved_scope}`).
현재 게이트웨이는 Resource·Prompt를 중개하지 않아 모두 거부한다. 중개를 도입할 때 이 패키지를 붙인다.

## 데이터(`data.pol`)

승인 목록·권한표·한도·예외는 규칙이 아니라 데이터다. 콘솔에서 바꾸고 번들로 내려 코드 배포 없이 반영한다.

**승인 항목의 공통 형식** — `providers`·`package_allowlist`·`permission_table`·`delegations`·`document_grants`·`transfers`·`flows`의 항목,
등록부의 `servers{ID}.approval`, 복원 승인 `restore.approval`, `exceptions`의 항목은 모두 다음을 갖는다. 하나라도 어긋나면 그 항목은 없는 것으로 본다.

| 필드 | 뜻 |
| --- | --- |
| `status` | `approved`일 때만 유효 |
| `approved_by` | 승인한 사람(비어 있으면 무효) |
| `approved_by_role` | 시트가 그 정책에 정한 최종 승인 주체와 같아야 함 — `security_admin`(보안 관리자) · `data_owner`(자료 소유 부서). 「예외 심사 대상 아님」 정책의 목록은 따지지 않음 |
| `not_after_ns` | 종료일(필수). 지나면 판정에서 자동으로 빠진다 |
| `not_before_ns` | 시작일(선택) |

| 키 | 내용 | 쓰는 정책 |
| --- | --- | --- |
| `providers[]` | `provider`, `official_urls`, `not_after_ns` | POL-001 |
| `data_types` | 자료 유형 분류 체계 | POL-002 |
| `package_allowlist[]` | `name`, `source`, `versions`, `not_after_ns` | POL-068 |
| `servers{ID}` | `state`(`active`·`suspended`·`decommissioning`·`decommissioned`), `kind`(`remote`·`local`), `address`, `identity`, `approval`(승인 항목 형식), `auth_servers`, `metadata_hosts`, `approved_scopes`, `launch.{executable, args, env, sha256}`, `permissions`, `prompts`, `resource_sources`, `tools{이름}` | connect·call·resource |
| `servers{ID}.tools{이름}` | `state`, `approved_contract_sha256`, `sensitive`, `requires_confirmation`, `document_scoped`, `roots`, `kind`(`command`·`api`), `operations`, `fetches_url`, `url_destinations`, `url_ip_ranges`, `egress_hosts`, `egress_ip_ranges`, `personal_fields_allowed`, `result_limit`, `window_document_limit` | call |
| `permission_table[]` | `user`, `server_id`, `tool`, `data_class`, `operation`, `not_after_ns`(자료 소유 부서 승인) | POL-003 |
| `delegations[]` | 위의 항목 + `agent` | POL-034 |
| `document_grants[]` | `user`, `agent`, `server_id`, `tool`, `doc_id`, `not_after_ns` | POL-036 |
| `transfers[]` | `data_class`, `recipient`, `purpose`, `not_after_ns` | POL-041 |
| `flows[]` | `source_server`, `dest_server`, `data_class`, `purpose`, `not_after_ns` | POL-044 |
| `server_accounts{ID}` | `operations`, `data_classes`, `documents`(선택 — 있으면 문서까지 대조) | POL-052 |
| `rate_limits.{user, agent, tool}` | `window_calls`, `concurrent` | POL-056 |
| `default_result_limit` | `max_items`, `max_bytes` | POL-049 |
| `blocked_versions{ID}` | 복원 금지 버전 | POL-072 |
| `stop_severities` | 즉시 중지할 사고 심각도(기본 `["critical"]`) | POL-081 |
| `exceptions[]` | 승인 항목 형식 + `policy_id`, `target`, `scope`(배열) | POL-013·070 |

**예외의 뜻.** 시트의 「예외 심사」는 대부분 「새 제공자·권한·목적지·한도를 승인 목록에 올릴 때만 심사하고, 승인 전에는 차단한다」이다.
그래서 이 패키지에서 예외는 판정을 건너뛰는 면제가 아니라 **승인 목록의 항목**이며, 목록에 오르기 전에는 차단된다.
판정을 건너뛰는 시한부 예외(`exceptions`)는 예외 자체가 정책인 두 곳에만 쓴다: POL-013(예외 승인에 근거한 연결·실행, 대상=서버, 범위=단계 또는 Tool)과
POL-070(취약점 조치 기한 연장, 대상=서버, 범위=취약점 ID). 시트에 「예외 심사 대상 아님」인 정책은 예외 항목이 있어도 무시한다.

## 정책 추적

### 규칙에 정책 번호를 단다

규칙마다 OPA METADATA 주석을 달고 `custom.pol_id`에 시트의 정책 ID를 쓴다. `opa inspect -a`와 `tools/trace.py`가 이 값을 읽는다.

```rego
# METADATA
# title: 제공자·공식 배포 주소 승인 목록 대조
# description: 왜 이렇게 판정하는지(시트 조건의 해석·예외 처리)
# custom:
#   pol_id: POL-001          # 여러 정책이면 [POL-052, POL-053]
#   risk_id: RSK-01
#   checkpoint: 서버·설치 파일 등록 전
findings contains lib.finding("POL-001", "DENY", "미승인·만료 제공자 또는 배포 주소") if { ... }
```

### 시험 이름에 정책 번호를 넣는다

`test_pol_<세 자리 번호>_pass_<설명>`은 통과(진행) 사례, `test_pol_<번호>_block_<설명>`은 차단·수동·확인·제한 사례다.
Rego 규칙이 있는 정책은 둘 다 하나 이상 있어야 한다. 「값이 빠졌을 때 차단」 사례를 반드시 넣는다.
`test_adv_pol_<번호>_<설명>`(`zz_adversarial_test.rego`)은 규칙 작성자의 시험을 보지 않고 시트 조건만으로 쓴 독립 반례 시험이다. 추적표에 「반례」로 따로 센다.

### 추적표

[TRACE.md](TRACE.md)는 정책마다 단계·우선순위·통제 대상·분류·판정 주체·판정 위치(그 정책의 결과를 내는 줄)·시험 수·반례 수·상태·사유를 보여 준다.
카탈로그(`catalog.rego`)에는 시트의 정책 본문·검사 시점·판정 값·통과 조건·차단 조건·예외 원문이 그대로 들어 있다.
`python policy/tools/trace.py --check`는 다음을 어기면 실패한다.

- 분류가 「이미 구현」·「구현 가능(PaC)」이고 Rego가 판정하는 정책에 그 정책을 내는 판정 줄이 없다.
- 판정 줄과 METADATA `custom.pol_id`가 서로 다른 정책을 가리킨다.
- 규칙이 있는 정책에 통과 시험이나 차단 시험이 없다.
- 규칙·시험이 시트에 없는 정책 ID를 가리킨다.
- 솔루션·제외 정책에 사유가 없다.
- TRACE.md가 최신이 아니다.

### 시트가 바뀌었을 때

```bash
python policy/tools/build_catalog.py extract "<시트 파일>.xlsm"   # source/sheet.json 갱신(openpyxl 필요)
python policy/tools/build_catalog.py build                       # pac/catalog.rego 갱신
python policy/tools/trace.py                                     # TRACE.md 갱신, 빠진 연결은 경고
```

정책이 새로 생기거나 번호가 바뀌면 `source/classification.json`에 분류를 더하고, 규칙의 `custom.pol_id`와 시험 이름을 함께 고친다.
`build --check`와 `trace.py --check`가 어긋남을 잡는다.

## 게이트웨이 연결

이 패키지를 게이트웨이 판정 경로에 붙이기 전에 게이트웨이와 센서가 보장해야 하는 것이다. Rego는 입력을 그대로 믿기 때문이다.

- **각 단계를 건너뛸 수 없다.** 승인 활성화(`approve`)·연결·로컬 실행·OAuth·호출·응답·목록·운영 이벤트마다 게이트웨이가 질의하고, `DENY`·`MANUAL`·`CONFIRM`이면 진행하지 않는다. `ops`는 조치를 제안할 뿐이며 실행기가 등록부 상태에 반영한다.
- **관측값은 이번 요청에 묶는다.** 사용자·Agent는 transport의 토큰에서 정하고, ACL·토큰·권한 조회·스키마·입력 검사·인자 검증 결과는 같은 요청 ID·사용자·서버·Tool·대상·인자 해시와 관측 시각에 대한 것이어야 한다. 요청 인자를 facts로 복사하지 않는다.
- **「검사 완료」와 「무탐지」를 구별한다.** 센서는 검사를 끝냈으면 결과 목록을 빈 배열로라도 보내고, 끝내지 못했으면 완료로 표시하지 않는다.
- **원자성은 게이트웨이가 맡는다.** 확인값 1회 소비, 동시 실행 수, 중복 실행 방지는 판정 전에 잠금·예약하고 규칙은 「이 호출에 예약됐는가」만 본다. 감사 기록은 실행 전에 남긴다(`recorded`).
- **판정 뒤 재해석을 막는다.** 경로는 판정한 실제 경로 그대로 열고, 외부 전송·URL 접속은 판정한 IP로 접속한다(판정 뒤 다시 DNS를 풀지 않는다).
- **값을 만드는 센서가 먼저 필요하다.** 도입 시험 호출, 입력·로그 민감정보 탐지, 실제 경로 해석, DNS·리다이렉트 재검사, 취약점 피드, 실제 권한 관측이다(TRACE.md의 「Rego + 센서」).

검사 시점이 여러 곳인 정책이 있다. 지금 규칙이 보는 곳은 TRACE.md의 「판정 위치」다. 시트 검사 시점 중 아직 규칙이 없는 곳은 다음과 같다.

- POL-003: Tool 등록·권한 변경 때의 권한표 대조(지금은 호출 때만).
- POL-008: 호출 전 격리 상태 재확인(지금은 로컬 실행 때만).
- POL-024·071·074·077: 발급·기동·전송·감지 직전의 게이트(지금은 운영 이벤트의 상태 점검).

## 작성 규칙

1. **모르면 차단한다.** 필수값 누락·검증 실패·조회 실패는 통과가 아니다. 규칙은 「허용 조건이 성립하지 않으면 차단」 꼴로 쓴다.
2. **`not` 안의 호출 인자를 정의된 값으로 만든다.** `not a.b == "x"`는 `a.b`가 없어도 참이 되지만, `in`·함수·내장 함수(`is_array`·`count` 등)는 인자가 정의되지 않으면 규칙 전체가 정의되지 않아 차단이 사라진다. `object.get(obj, path, 기본값)`을 넘기거나 보조 규칙으로 감싼다. 등록부처럼 없을 수 있는 데이터는 `default reg := {}`로 받는다.
3. **이유 문자열의 값도 정의돼 있어야 한다.** `sprintf`에 넣는 식별값(Tool 이름 등)이 없으면 그 규칙이 사라진다. 식별값은 입력 계약에서 먼저 검사한다.
4. **불리언은 `== true`로 비교한다.** 문자열 `"true"`나 누락을 참으로 보지 않는다.
5. **원자성은 게이트웨이가 맡는다.** 확인값 1회 소비·동시 실행 수·중복 실행은 게이트웨이가 판정 전에 잠금·예약하고, 규칙은 「이 호출에 예약됐는가」만 본다.
6. **규칙과 값을 나눈다.** 목록·한도·권한표는 `data.pol`에 둔다. 규칙에 상수로 넣지 않는다.
7. **결과 식별값이 없어도 결과가 나와야 한다.** 위반 표시에 쓰는 이름(Tool·패키지·인스턴스)이 없으면 고정 표시(`이름 없는 Tool` 등)로 대신한다.
8. **IP는 단일 주소만 인정한다.** `net.cidr_contains`는 두 번째 인자로 대역도 받으므로 `/`가 있는 값은 거부한다. 보호 대역에 `::ffff:0:0/96`을 넣지 않는다(Go의 net이 모든 IPv4를 그 형태로 다룬다).

## 실행

```bash
docker run --rm --entrypoint /opa -v "$PWD/policy/pac:/policy:ro" openpolicyagent/opa:1.20.2-static check --strict /policy
docker run --rm --entrypoint /opa -v "$PWD/policy/pac:/policy:ro" openpolicyagent/opa:1.20.2-static test /policy --coverage
python3 policy/tools/build_catalog.py build --check
python3 policy/tools/trace.py --check
```

한 건 판정 예:

```bash
opa eval -d policy/pac -d data.json -i input.json 'data.mcp.pol.call.decision'
```
