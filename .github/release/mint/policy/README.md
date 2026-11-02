# 정책 코드 (policy)

MCP 도입부터 폐기까지의 보안 정책 90개를 OPA/Rego 판정 코드로 표현한 패키지입니다. 보안 정책 담당자는 정책이 어떤 입력에서 어떤 판정을 내리는지 코드로 확인할 수 있고, 연동 개발자는 입력 계약에 맞춰 값을 채워 [OPA](https://www.openpolicyagent.org/)에 질의할 수 있습니다.

- [게이트웨이와의 관계](#게이트웨이와의-관계)
- [구성](#구성)
- [정책 ID 체계](#정책-id-체계)
- [판정 출력](#판정-출력)
- [입력 계약](#입력-계약)
- [데이터](#데이터)
- [OPA로 평가하기](#opa로-평가하기)
- [작성 규칙](#작성-규칙)

## 게이트웨이와의 관계

이 패키지는 MINT 게이트웨이의 실행 판정 경로에 연결되어 있지 않습니다.

- 게이트웨이는 `deploy/compose.yaml`의 `opa` 서비스에 `full_stack_lab/opa/`를 마운트하고, `mcp.authz` 패키지의 `decision` 규칙(`/v1/data/mcp/authz/decision`)에 질의합니다.
- `policy/pac/`의 패키지(`mcp.pol.*`)는 마운트되지 않으며, 게이트웨이 코드도 이 패키지를 질의하지 않습니다.
- 따라서 이 패키지는 조직의 보안 정책을 코드로 표현한 별도 패키지입니다. 정책 검토, 정책 문구와 판정 조건의 대조, 외부 시스템 연동에 쓰며, 이 패키지에 규칙이 있다는 사실만으로 게이트웨이가 해당 정책을 집행한다고 볼 수 없습니다.
- 게이트웨이 판정 번들이 쓰는 정책 ID는 이 패키지의 `POL-*` 체계와 별개입니다.

## 구성

```text
policy/
├── README.md        이 문서
└── pac/
    ├── catalog.rego   정책 카탈로그 90개 (package mcp.pol.catalog)
    ├── lib.rego       결과 형식, 판정 집계, 예외·기간 처리, 주소 검사 (package mcp.pol.lib)
    ├── intake.rego    도입 검토: 신청서 한 건 (package mcp.pol.intake)
    ├── connect.rego   등록 및 연결: 연결·승인 기록·로컬 실행·OAuth·복원 (package mcp.pol.connect)
    ├── call.rego      실행: Tool 호출 한 건 (package mcp.pol.call)
    ├── ops.rego       관리·폐기: 운영 중 서버 상태 점검 (package mcp.pol.ops)
    └── resource.rego  Resource·Prompt (package mcp.pol.resource)
```

| 파일 | 역할 | 판정 단위 | 규칙이 있는 정책 |
| --- | --- | --- | ---: |
| `catalog.rego` | 정책 ID별 제목·단계·우선순위·검사 시점·통과 조건·차단 조건·예외 승인 주체·분류를 담습니다. 생성 파일이므로 직접 고치지 않습니다. | 해당 없음 | 해당 없음 |
| `lib.rego` | 모든 패키지가 쓰는 공통 도구입니다. 결과 형식(`finding`), 판정 집계(`decide`), 필수값 검사, 승인 항목의 기간·승인자 확인(`approved`), 시한부 예외(`exception_for`), 공인 주소 검사(`all_public`)를 제공합니다. | 해당 없음 | 해당 없음 |
| `intake.rego` | MCP 서버 도입 신청서를 심사합니다. | 신청서 한 건 | 9 |
| `connect.rego` | `connection.stage`에 따라 서버 연결, 승인 기록, 로컬 서버 시작, OAuth, 백업 복원을 판정합니다. | 연결 한 건 | 16 |
| `call.rego` | `request.stage`에 따라 Tool 호출 전달, 결과 반환, Tool 목록 반환을 판정합니다. | 호출 한 건 | 30 |
| `ops.rego` | 운영 중인 서버 목록 스냅숏에서 서버별 위반과 조치를 냅니다. | 스냅숏 한 건 | 13 |
| `resource.rego` | Prompt 템플릿 사용, Resource 읽기·목록·변경을 판정합니다. | 요청 한 건 | 5 |

정책 90개 중 Rego 규칙이 있는 정책은 66개입니다. 한 정책이 여러 패키지에 나뉘어 있을 수 있어(예: `POL-I-10`은 도입 신청 단계의 분류와 호출 단계의 확인) 위 표의 합계는 66보다 큽니다. 나머지 24개는 이 패키지에 규칙이 없습니다. 카탈로그에서 정책별 `category`·`enforced_by`·`note`로 구분합니다.

### 패키지별 판정 단계

| 패키지 | 입력의 단계 값 | 의미 |
| --- | --- | --- |
| `mcp.pol.connect` | `connect` | 서버 연결을 열기 전 |
| | `approve` | 서버 연결 승인을 활성화하기 전 |
| | `launch` | 로컬 MCP 서버를 시작하기 전 |
| | `oauth` | 인증 서버 선택, 메타데이터 조회, scope 요청 전 |
| | `restore` | 백업에서 복원한 설정으로 연결·호출하기 전 |
| `mcp.pol.call` | `request` | Tool 호출을 상위 서버로 보내기 전 |
| | `response` | 결과를 Agent에 돌려주기 전 |
| | `list` | Tool 목록을 돌려주기 전 |
| `mcp.pol.resource` | `prompt_use` | 서버 제공 Prompt 템플릿을 쓰기 전 |
| | `resource_read` | Resource 내용을 반환하기 전 |
| | `resource_list` | Resource 목록을 돌려주기 전 |
| | `resource_update` | Resource 내용·출처 변경을 반영하기 전 |
| `mcp.pol.ops` | `periodic` `update` `restore` `package_change` `config_change` `incident` `provider_termination` | 점검을 일으킨 사건(`event`) |
| `mcp.pol.intake` | 없음 | 신청서 한 건을 한 번에 심사 |

`mcp.pol.resource`는 게이트웨이가 Resource·Prompt를 중개하지 않는 현재 구성에서 이 경로를 모두 거부한다는 전제로 작성되었습니다. 중개를 도입할 때 붙일 판정입니다.

## 정책 ID 체계

정책 ID는 정책이 속한 단계를 나타내는 `POL-<단계>-<번호>` 형식입니다.

| 접두 | 단계 | 정책 수 | 범위 |
| --- | --- | ---: | --- |
| `POL-I-` | 도입 검토 | 11 | `POL-I-01` ~ `POL-I-11` |
| `POL-R-` | 등록 및 연결 | 22 | `POL-R-01` ~ `POL-R-22` |
| `POL-E-` | 실행 | 29 | `POL-E-01` ~ `POL-E-29` |
| `POL-O-` | 관리 | 19 | `POL-O-01` ~ `POL-O-19` |
| `POL-D-` | 연결 해제 및 폐기 | 9 | `POL-D-01` ~ `POL-D-09` |

- 정책 ID의 단계와 규칙이 들어 있는 파일의 단계는 일치하지 않을 수 있습니다. 판정 시점이 기준입니다. 예를 들어 `POL-I-03`(Tool별 권한표)은 호출 때 판정하므로 `call.rego`에 있고, `POL-O-06`(패키지 승인 목록)은 도입 신청 때도 보므로 `intake.rego`와 `ops.rego`에 모두 있습니다.
- 각 규칙의 `METADATA`에 `custom.pol_id`(정책 ID), `custom.risk_id`(위험 ID), `custom.checkpoint`(검사 시점)가 있습니다. 카탈로그의 키가 `pol_id`입니다.
- 입력 계약 위반은 정책 ID가 아니라 `INPUT_CONTRACT`로 보고합니다.

### 카탈로그 항목

`data.mcp.pol.catalog.policies[<정책 ID>]`의 필드입니다.

| 필드 | 내용 |
| --- | --- |
| `title`, `stage`, `priority`, `risk_id` | 대상 구성요소, 단계, 우선순위(P1~P3), 위험 ID |
| `content` | 정책 문구 |
| `checkpoint`, `inputs` | 검사 시점, 판정에 필요한 입력 |
| `pass_condition`, `block_condition` | 통과 조건, 차단 조건 |
| `exception`, `exception_approver` | 예외 절차, 예외 최종 승인 주체: `security_admin`(보안 관리자), `data_owner`(자료 소유 부서), `none`(예외 없음) |
| `category`, `enforced_by`, `note` | 구현 분류(`pac`, `implemented`, `solution`, `excluded`), 집행 주체(`rego`, `rego+sensor`, `solution`), 비고 |

`exception_approver`는 `lib.approved`가 허용 항목의 승인자를 확인할 때 쓰입니다.

## 판정 출력

`intake`, `connect`, `call`, `ops`, `resource` 모든 패키지가 `findings`(걸린 정책별 판정 집합)와 `decision`(최종 결과)을 냅니다.

```json
{
  "effect": "DENY",
  "policy_ids": ["POL-I-01"],
  "reasons": ["POL-I-01: 미승인·만료 제공자 또는 배포 주소"],
  "all_policy_ids": ["POL-I-01", "POL-I-04"]
}
```

| 필드 | 내용 |
| --- | --- |
| `effect` | 최종 효과. 아래 표의 값 중 가장 강한 것 |
| `policy_ids` | 최종 효과를 낸 정책 ID |
| `reasons` | 최종 효과를 낸 정책의 사유(`정책 ID: 사유`) |
| `all_policy_ids` | 걸린 정책 전부. 더 강한 효과에 가려진 정책도 남깁니다(감사 기록용). |

### 효과

한 요청에 여러 정책이 걸리면 가장 강한 효과가 최종 결과입니다.

| 효과 | 강도 | 뜻 |
| --- | ---: | --- |
| `DENY` | 5 | 현재 요청을 차단합니다. |
| `MANUAL` | 4 | 보안 관리자의 판단이 있을 때까지 차단합니다. |
| `CONFIRM` | 3 | 요청한 사용자 본인에게 확인을 받은 뒤 한 번 진행합니다. |
| `RESTRICT` | 2 | 제한해서 허용합니다(공개자료 조회만, 한도까지 등). |
| `ALERT` | 1 | 진행하되 경보를 냅니다. |
| `ALLOW` | 해당 없음 | 걸린 정책이 하나도 없습니다. |

- 알 수 없는 효과 문자열은 `DENY`로 셉니다. 오타로 차단이 사라지는 일을 막기 위해서입니다.
- 필수값 누락, 값 확인 불가, 검증 실패는 현재 요청만 차단하는 방향(fail-closed)으로 작성되어 있습니다.

### `ops` 패키지의 추가 출력

`mcp.pol.ops`는 `findings`와 `decision` 외에 서버별 `violations` 집합을 냅니다. 각 항목은 `policy_id`, `server`, `action`, `detail`입니다. `action`은 효과로 바뀌어 `findings`에 들어갑니다.

| `action` | 효과 |
| --- | --- |
| `block`, `stop`, `stop_traffic`, `abort_restore`, `block_deploy`, `block_egress`, `revoke`, `block_transfer`, `keep_incomplete` | `DENY` |
| `restrict` | `RESTRICT` |
| `mark_unverified` | `ALERT` |
| 그 밖의 값 | `DENY` |

이 패키지는 조치를 실행하지 않습니다. 실행기나 게이트웨이가 `action`을 등록부 상태에 반영해야 합니다.

## 입력 계약

모든 패키지에 공통인 조건입니다.

- `input.facts.trusted`가 `true`여야 합니다. 판정 입력은 신뢰할 수 있는 출처에서만 만들어야 합니다.
- `input.facts.now_ns`는 현재 시각(나노초, 숫자)입니다. 기간 판정에 쓰입니다.

두 조건 중 하나라도 어긋나거나 패키지별 필수 필드가 없으면 `INPUT_CONTRACT`로 `DENY`입니다.

### 패키지별 입력

| 패키지 | 최상위 필드 | 필수 조건 |
| --- | --- | --- |
| `intake` | `application`, `facts` | `application.id`(문자열), `application.hosting`(`external` `local` `gateway_managed`), 각 Tool의 `name`, 각 패키지의 `name`·`version` |
| `connect` | `connection`, `approval`(`approve` 단계), `facts` | `connection.stage`(`connect` `approve` `launch` `oauth` `restore`), `connection.server_id` |
| `call` | `request`, `response`(`response`·`list` 단계), `facts` | `request.stage`(`request` `response` `list`), `request.id`·`user`·`agent`·`server_id`·`tool`(비어 있지 않은 문자열), `request.operation`(`list` 단계 제외) |
| `ops` | `event`, `servers`, `facts` | `event`는 위 표의 사건 값, `servers`는 배열이며 각 항목에 `id` |
| `resource` | `request`, `response`, `facts` | `request.stage`, `request.user`, `request.server_id` |

`request.operation`은 `read` `write` `delete` `share` `external_send` `execute` 중 하나입니다. 신원(`user`, `agent`)은 인자에 적힌 값이 아니라 전송 계층의 토큰에서 게이트웨이가 정한 값이어야 합니다.

### 단계별 주요 필드

패키지가 읽는 필드는 규칙에 따라 더 많습니다. 아래는 단계별로 주로 쓰이는 값입니다. 전체는 각 `.rego` 파일의 규칙 `METADATA`와 본문을 따릅니다.

| 패키지·단계 | 주요 필드 |
| --- | --- |
| `intake` | `application.provider`, `source_url`, `business_scope`(`operations`, `data_types`, `permissions`), `tools[]`(`declared_effect`, `data_types`, `permissions`, `description_scan`, `output_contract`, `trial_results[]`, `requires_confirmation`), `packages[]`, `sbom.status`, `provider_terms`, `gateway_controls`, `requirements` |
| `connect`·`connect` | `connection.kind`(`remote` `local`), `identity`, `address`, `transport.scheme`, `approval.basis`(`normal` `exception`), `consent`, `requested_access`, `requested_functions`, `credential`, `user` |
| `connect`·`approve` | `approval.server_id`, `purpose`, `scope`, `policy_version`, `method`(`auto` `manual` `exception`), `recorded`, 예외일 때 `approver`·`not_after_ns` |
| `connect`·`launch` | `connection.launch`(`executable`, `args`, `env`, `sha256`, `observed_permissions`, `isolation`) |
| `connect`·`oauth` | `connection.auth_server`(`address`, `id`), `metadata`(`request_host`, `final_host`, `resolved_ips`), `requested_scopes` |
| `connect`·`restore` | `connection.restored`(`address`, `tools`, `access`) |
| `call`·`request` | `request.target`(`data_class` 등), `purpose`, `recipient`, `source_server`, `facts.permission_lookup`, `token`, `credential`, `inspection`, `egress`, `path`, `confirmation`, `approval`, `audit`, `usage` 등 게이트웨이가 관측·조회한 값 |
| `call`·`response` | `response.items`, `response.bytes`(0 이상의 정수) |
| `call`·`list` | `response.tools`, `response.cached`, `response.cache_owner`, `facts.permitted_tools` |
| `ops` | `servers[]`의 `approved_tools`, `baseline_config_sha`, `config_scan`, `vuln_scan`, `scheduled_change_ns`, `restore`, `revoke_confirmed`, `provider_termination` 등 |

값이 없는 경우 `null`·빈 문자열·빈 배열은 모두 「확인 불가」로 봅니다. 불리언과 `0`은 값이 있는 것으로 봅니다. 사람이 적는 기록 항목(승인 기록, 요구사항 문서, 표시 정보)은 비어 있지 않은 문자열이나 배열이어야 하며, `false`나 `0`은 기록으로 인정하지 않습니다.

### 입력 예

`connect` 패키지에 연결 정보가 없는 입력입니다.

```json
{"facts": {"trusted": true, "now_ns": 1793600000000000000}}
```

## 데이터

규칙은 승인 목록·등록부·권한표를 `data.pol.*`에서 읽습니다. 이 저장소에는 데이터 파일이 들어 있지 않으며, 조직이 승인한 내용을 JSON으로 만들어 OPA에 함께 올려야 합니다. 데이터가 없으면 승인 항목을 찾지 못해 해당 정책은 차단 쪽으로 판정합니다.

| 패키지 | 읽는 데이터 |
| --- | --- |
| `intake` | `providers`, `package_allowlist`, `data_types`, `exceptions` |
| `connect` | `servers`(서버 ID별 승인 등록부), `exceptions` |
| `call` | `servers`, `permission_table`, `delegations`, `document_grants`, `transfers`, `flows`, `server_accounts`, `rate_limits`, `default_result_limit`, `exceptions` |
| `ops` | `package_allowlist`, `blocked_versions`, `stop_severities`, `exceptions` |
| `resource` | `servers`(서버별 `prompts`, `resource_sources`) |

### 허용 항목의 조건

승인 목록·권한표·등록부의 항목은 `lib.approved`가 다음을 모두 만족할 때만 인정합니다. 하나라도 맞지 않으면 그 항목은 없는 것으로 봅니다.

| 필드 | 조건 |
| --- | --- |
| `status` | `approved` |
| `approved_by` | 비어 있지 않은 문자열 |
| `not_after_ns` | 필수. 현재 시각(`now_ns`)보다 커야 합니다. |
| `not_before_ns` | 있으면 현재 시각 이하여야 합니다. |
| `approved_by_role` | 카탈로그의 `exception_approver`가 `security_admin` 또는 `data_owner`이면 그 값과 같아야 합니다. `none`이면 확인하지 않습니다. |

예외(`data.pol.exceptions`)는 예외 자체가 정책인 `POL-R-02`(예외 승인 기간)와 `POL-O-08`(기한 연장)에서만 판정을 건너뛰는 데 쓰입니다. 항목은 `policy_id`, `target`, `scope`와 위 승인 조건을 가집니다. 그 밖의 정책에서 새 제공자·권한·주소는 승인 목록을 바꾼 뒤에만 허용되며, 그 전에는 차단됩니다.

### 주소 검사

`lib.all_public`은 해석된 IP가 하나 이상 있고 모두 올바른 공인 주소일 때만 참입니다. 다음 대역은 공인 주소로 보지 않습니다: 루프백, 사설(10/8, 172.16/12, 192.168/16), 링크 로컬, CGNAT(100.64/10), 문서·벤치마크용, 멀티캐스트, 예약 대역과 IPv6 해당 대역(`::1`, `fc00::/7`, `fe80::/10` 등). 주소 형식이 틀리면 공인으로 보지 않습니다.

## OPA로 평가하기

규칙이 `rego.v1`을 가져오므로 OPA 1.x를 권장합니다. 아래 명령은 저장소 루트에서 실행합니다.

1. 패키지 구문을 검사합니다.

   ```bash
   opa check policy/pac
   ```

2. 데이터 없이 입력 계약만 확인합니다. 입력 계약 위반이므로 `DENY`가 나옵니다.

   ```bash
   echo '{"facts": {"trusted": true, "now_ns": 1793600000000000000}}' > input.json
   opa eval -d policy/pac -i input.json --format pretty 'data.mcp.pol.connect.decision'
   ```

   ```json
   {
     "all_policy_ids": ["INPUT_CONTRACT"],
     "effect": "DENY",
     "policy_ids": ["INPUT_CONTRACT"],
     "reasons": ["INPUT_CONTRACT: 연결 입력 계약 위반"]
   }
   ```

3. 승인 데이터를 함께 올려 평가합니다. `pol-data.json`은 `{"pol": {"servers": {...}, ...}}` 형태로, 위 「데이터」 표의 키를 `pol` 아래에 둡니다.

   ```bash
   opa eval -d policy/pac -d pol-data.json -i input.json --format pretty 'data.mcp.pol.connect.decision'
   ```

4. 패키지마다 질의 경로가 다릅니다.

   | 대상 | 질의 |
   | --- | --- |
   | 도입 신청 | `data.mcp.pol.intake.decision` |
   | 서버 연결 | `data.mcp.pol.connect.decision` |
   | Tool 호출 | `data.mcp.pol.call.decision` |
   | 운영 점검 | `data.mcp.pol.ops.decision` |
   | Resource·Prompt | `data.mcp.pol.resource.decision` |
   | 정책별 판정 | 위 경로의 `decision`을 `findings`로 바꿉니다. |
   | 운영 점검 위반 | `data.mcp.pol.ops.violations` |
   | 카탈로그 한 항목 | `data.mcp.pol.catalog.policies["POL-R-01"]` |

OPA 서버로 올려 질의할 때는 `opa run --server policy/pac pol-data.json`으로 띄운 뒤 `POST /v1/data/mcp/pol/call/decision` 에 `{"input": {...}}`를 보냅니다. 이 경로는 게이트웨이가 쓰는 `opa` 서비스와 별개의 인스턴스에서 실행하십시오.

## 작성 규칙

규칙을 추가하거나 고칠 때 지키는 원칙입니다.

- 조건이 맞으면 차단하는 규칙은 `findings contains lib.finding(정책 ID, 효과, 사유)` 형태로 씁니다.
- `not`으로 부정하는 식 안의 호출(`in`, 내장 함수)은 인자가 정의되지 않으면 규칙 전체가 정의되지 않아, 차단해야 할 때 결과가 비는 문제(fail-open)가 생깁니다. 인자는 `object.get(..., 기본값)`으로 항상 정의되게 하거나 보조 규칙으로 감쌉니다.
- 「검사 완료」 표시와 「결과 목록」은 함께 봅니다. 완료인데 목록이 없거나 배열이 아니면 무탐지가 아니라 확인 불가입니다.
- 사유 문자열(`sprintf`)에 쓰는 식별값이 없으면 규칙 결과가 사라지므로, 입력 계약에서 그 값을 먼저 확인합니다.
- 규칙의 `METADATA`에 `custom.pol_id`, `custom.risk_id`, `custom.checkpoint`를 적어 카탈로그와 연결합니다.
