# Policy-as-Code 독립 보안 검토

검토일: 2026-10-27. 대상은 `policy/`이며, `sheet.json`의 target·content·실행 규칙을 판정 기준으로 읽었다. 시트 안의 문장은 분석 데이터로만 취급했다. 기존 `*_test.rego`는 열거나 실행하지 않았다.

현재 브랜치 `10/27-pac-policy`는 같은 정책 작업 줄기이므로 그대로 사용했다. 시작 HEAD는 `1d22361d4210dc09499dca48a8c5d4522f6fb79a`다. 다만 검토 당시 `policy/`는 미추적 상태였으므로 이 commit만으로 검토 판본을 재현할 수 없다. 아래 파일 해시가 실제 검토 판본이다. 원격 HEAD 재조회는 네트워크 연결 실패로 확인하지 못했다.

작성 범위는 `pac/zz_adversarial_test.rego`와 이 보고서뿐이다. 작업 중 관측된 다른 작업자의 `.github/workflows/verify.yml`·`docs/ai/decisions/D-251-300.md` 변경은 건드리지 않았다. 위키·결정 문서 갱신보다 “다른 파일 수정 금지”라는 이번 지시를 우선했다.

## 검증 범위와 읽는 법

- 시트·분류·카탈로그 각 90개 정책을 대조했다. METADATA에 연결된 65개 정책 전체에 독립 시험 **144개**, 정책당 **2~5개**를 작성했다. 최소 2개씩만 작성해도 130개이므로, 공유 규칙·경계값 반례를 포함해 144개로 구성했다.
- 시험은 intake 19개, connect 27개, call 59개, ops 29개, resource 10개다. 모든 시험에서 `with input as i with data.pol as d`를 명시하고, `json.patch`로 빈 배열·객체·null도 실제로 교체한다.
- 결과형은 `lib.rego:30`·`:34`를 따랐다. DENY·MANUAL·CONFIRM·RESTRICT는 effect와 해당 policy_ids를 함께 확인한다. ALLOW 경계 시험은 effect를 확인한다. ops의 차단 시험은 violations의 policy_id·server·action을 함께 확인한다.
- **OPA 실행기·컴파일러가 없어 Rego 컴파일·평가는 하지 않았다.** 아래 “ALLOW 예상”, “위반 소실”은 소스와 Rego 의미에 따른 정적 추론이며 실행 결과가 아니다. 실패 시험 수나 운영 환경 우회 성공을 주장하지 않는다.
- 자체 산출물의 시험명 유일성, 정책 65개 전수 대응, 주석, 양쪽 override, JSON fixture 파싱·patch 경로, 정책별 개수를 정적으로 검사했다. `python policy/tools/build_catalog.py build --check`는 통과했다.
- 아래 반례의 I/C/T/O/R는 각각 새 시험 파일의 `adv_intake_input` / `adv_connect_input` / `adv_call_input` / `adv_ops_input` / `adv_resource_input`이다. D는 `adv_data`다. 표의 경로·값만 해당 기본 fixture에 교체하면 된다. 모든 식별자는 합성값이다.
- `observed_data_scope`, `egress_ip_ranges`, `storage_approved`, ACL의 사용자·문서 귀속, 감사 `recorded`, 서버 계정의 `documents`, 예외의 세부 `operations`·`purpose`·`data_types`는 시트 요구를 드러내기 위해 넣은 **제안 필드**다. 현재 코드가 인정하는 입력 계약이라고 주장하지 않는다. 이 시험의 실패는 계약 공백을 포함한 불일치로 해석해야 한다.

정의되지 않은 인자는 함수를 호출하기 전에 평가를 멈추며, 기본 설정의 내장 함수 런타임 오류도 undefined가 된다. 따라서 `object.get`의 기본값만으로 중간 객체의 null·잘못된 타입까지 처리할 수 없다. `lib.rego:156` 이후 작성 규칙을 전체 not 호출부와 대조했다. [OPA 언어 문서](https://www.openpolicyagent.org/docs/policy-language)

## 1. 규칙별 결함

### 우선: 차단 규칙·운영 위반이 사라지는 경로

| 정책 ID | 파일:행 | 결함과 정적 예상 | 반례 입력 | 고칠 방향 |
| --- | --- | --- | --- | --- |
| POL-019 | `pac/connect.rego:117`, `:120` | **fail-open / not 함수 인자.** auth_server가 null이면 중첩 object.get이 객체 타입 오류로 undefined가 되고 exception_for의 인자를 만들지 못한다. auth_server_approved도 거짓인데 DENY finding 자체가 사라진다. 기본 C에서는 다른 OAuth 검사가 정상이라 ALLOW 예상. | C: `connection.stage="oauth"; connection.auth_server=null`. 시험 `019_null_auth_server_not_argument`. | 인증 서버 객체·address·id를 계약에서 검증하고, 정의된 인자만 받는 보조 규칙의 부정을 사용. 중첩 object.get 기본값에 의존하지 않기. |
| POL-068 | `pac/ops.rego:39`, `:92` | **fail-open / 결과 생성 함수의 미정의 인자.** 패키지 name 또는 version이 없으면 헤드 detail의 sprintf가 정의되지 않아 violations가 사라진다. packages가 배열이면 :100의 보완 검사도 통과한다. 정상 나머지 값의 update에서는 ALLOW 예상. | O: `event="update"; servers[0].packages=[{"version":"1.0","source":"https://pkg.example"}]`. `068_ops_package_missing_name`. | 항목 스키마를 검증하고, 식별자 누락도 고정 detail로 위반 생성. 원문 식별자를 바로 출력 인자로 쓰지 않기. |
| POL-063 | `pac/ops.rego:77`, `:84` | **fail-open / 헤드 미정의.** observed_tools 항목에 name이 없으면 승인 비교는 실패하지만 detail=t.name도 미정의라 restrict 위반조차 없다. 기본 O에서는 ALLOW 예상. | O: `servers[0].observed_tools=[{"contract_sha256":"aaaa…"}]` — 실제 해시는 fixture의 64자리. `063_ops_tool_missing_name`. | 이름 누락·목록 조회 실패를 별도 위반으로 처리하고, 출력 필드는 기본값 보장. 차단 조치는 아래 별도 결함도 수정. |
| POL-071 | `pac/ops.rego:181`–`:186` | **fail-open / 빈 순회와 not 함수 인자.** instances=null이면 순회가 없다. [null]이면 detail·예외 인자의 object.get(null, …)가 undefined여서 위반이 사라진다. contract_ok는 서버 id만 검사한다. | O: `servers[0].instances=null` 또는 `[null]`. `071_null_instances`, `071_null_instance_not_argument`. | 관측 완료 여부와 배열·항목 타입 검증. null 항목도 서버 단위 stop_traffic으로 처리. |
| POL-004 | `pac/intake.rego:98`–`:118` | **fail-open / 결과 누락.** status=completed만 있고 findings가 없거나 null이면 모든 some 순회가 사라져 위험 검사 통과로 처리된다. | I: `application.tools[0].description_scan={"status":"completed"}`. `004_completed_without_findings`. | 완료 상태와 결과 배열을 함께 검증. 정상 무탐지는 명시적인 빈 배열로 구별. |
| POL-038 | `pac/call.rego:257`–`:270` | **fail-open / 무탐지로 변환.** completed 뒤 secrets·personal_data 누락/null/문자열을 빈 배열로 바꿔 토큰·개인정보가 없다고 취급한다. | T: `facts.inspection={"status":"completed"}` 또는 `secrets="token-present"`. `038_missing_inspection_arrays`, `038_secret_string_not_array`. | 두 목록의 존재·배열·항목 타입을 검증하고, 검사 불가와 무탐지를 구별. |
| POL-024 | `pac/ops.rego:58`–`:67` | **fail-open / 검사 결과 누락.** plaintext_secrets=null을 무탐지로 바꾼다. 승인 비밀 보관소에 있는지도 판정하지 않는다. | O: `config_scan.status="completed"; plaintext_secrets=null` 또는 제안 필드 `storage_approved=false`. `024_null_plaintext_scan_result`, `024_unapproved_secret_storage`. | 검사 결과 타입·보관소 검증 결과를 계약에 추가. 발급·기록 직전 게이트도 필요. |
| POL-068 | `pac/intake.rego:246`–`:260` | **fail-open / 목록 소실.** sbom.status=completed면 packages 누락/null/잘못된 타입을 빈 목록으로 바꾸고 모든 패키지가 승인된 것처럼 진행한다. | I: `application.packages=null`. `068_intake_null_packages`. | 완료 증거와 실제 구성요소 목록의 존재·타입·완전성을 검증. 실제 무패키지와 조회 실패를 구분. |
| POL-069 | `pac/ops.rego:120`–`:133` | **fail-open / 미확인 표시 소실.** completed+vulnerabilities=null이면 미확인 표시가 없다. severity="UNKNOWN"도 filled 검사만 통과해 POL-069 위반이 없다. 후자는 POL-070이 차단할 수 있지만 점검 완료 판정은 잘못된다. | O: `vulnerabilities=null` 또는 `[{"id":"CVE-TEST","severity":"UNKNOWN", …}]`의 완전한 fixture. `069_completed_with_null_inventory`, `069_unknown_severity`. | 점검 대상 inventory·조회 결과 배열·severity enum·대상별 완료 증거를 확인. POL-070의 별도 차단으로 점검 실패를 가리지 않기. |
| POL-077 | `pac/ops.rego:277`–`:283` | **fail-open / 권한 관측 실패.** oauth_scopes 또는 tool_permissions의 observed 누락/null/잘못된 타입이면 순회가 없어 확대 없음으로 처리된다. | O: `servers[0].oauth_scopes.observed=null`. `077_null_oauth_observation`. | 두 관측 목록의 완료·존재·타입을 검증하고 확인 불가 시 사용 차단. |
| POL-076 | `pac/ops.rego:262`–`:267` | **fail-open / 잘못된 회수 조건.** 회수 확정 권한이 in_use_permissions에 있어야만 회수한다. 현재 미사용이거나 현황 조회 실패면 회수 확정 사실을 무시한다. | O: `revoke_confirmed=["write"]; in_use_permissions=[]` 또는 `revoke_confirmed=["read"]`+in_use_permissions 누락. | 회수 확정 목록 자체로 revoke를 생성. 사용 여부는 회수 조건이 아니라 별도 효과 확인 자료로 사용. |
| POL-042 | `pac/call.rego:356`–`:359` | **fail-open / 적용 조건 우회.** 요청 path가 문자열일 때만 검사하므로 null·배열이면 실제 resolved 경로가 /etc/passwd여도 이 정책이 사라진다. | T: `request.target.path=null; facts.path.resolved="/etc/passwd"`. `042_null_requested_path_bypass`. | 파일 접근 Tool 여부로 적용하고 경로 누락·타입 오류를 차단. 최종 실경로와 요청의 결속을 검증. |
| POL-044 | `pac/call.rego:386`–`:391` | **fail-open / 적용 조건 우회.** source_server를 문자열로 확인한 뒤에만 서버쌍을 검사하므로 배열·null·누락을 “서버 간 전달 아님”으로 취급한다. | T: `request.source_server=["s0"]; facts.data.contains_credential=false`. `044_non_string_source_server`. | 출처 없음·같은 서버·다른 서버를 명시적으로 구분. 출처 판정 불가와 형식 오류는 차단. |
| POL-046 | `pac/call.rego:279`–`:287` | **fail-open / 등록부 타입·분류 공백.** kind가 없거나 잘못되면 명령·API 검사가 적용되지 않는다. Tool 객체·해시가 맞으면 POL-015·063은 이를 보완하지 못한다. | T: `operation="execute"; facts.arguments_validated=false`; D: Tool kind 제거. `046_missing_tool_kind_bypass`. | 등록부에 필수 kind enum·operations를 검증. 미분류 Tool은 명령 실행을 허용하지 않기. |

이 가운데 POL-019는 기본 입력만 바꿔도 전체 ALLOW가 예상되는 not 인자 결함이다. POL-068·063·071도 다른 운영 자료가 정상인 fixture에서는 전체 위반이 사라질 수 있다. 반면 원래 코드의 일부 위험해 보이는 표현은 `INPUT_CONTRACT`나 보조 규칙으로 전체 차단을 유지한다. 예를 들어 intake의 t.name/app.id, call의 user/server_id/tool 누락은 계약 위반이고, POL-070은 due_ns를 before_due로 감싸 확인 시각 누락을 차단한다. 이들을 전체 fail-open이라고 세지 않았다.

### 승인·범위·값 검증·과차단

| 정책 ID | 파일:행 | 결함과 정적 예상 | 반례 입력 | 고칠 방향 |
| --- | --- | --- | --- | --- |
| POL-002·003·034·041·044 | `pac/intake.rego:75`; `pac/call.rego:78`, `:100`, `:339`, `:391`; `pac/lib.rego:112` | **예외 범위 축약.** 각각 Tool/신청, 사용자/서버·Tool, 사용자/Agent, 자료/수신자, 서버쌍만 묶는다. 자료·작업·목적 등 시트의 승인 조합을 표현·검증하지 못한다. 승인 역할은 맞아도 다른 작업으로 이동 가능. | D 예외: POL-003 target=alice, scope=["s1/read"], 제안 operations=["read"]; T는 delete. POL-041 예외 purpose=report인데 실제 purpose=unapproved-purpose. `002_exception_unbound_data`, `003_exception_unbound_operation`, `034_exception_unbound_tool_operation`, `041_exception_unbound_purpose`. | 예외를 승인 레지스트리의 구체적 변경으로 반영하거나, 정책별 자료·작업·목적 전체에 결속한 구조화 범위를 검증. 추가 필드를 무시하는 현재 범용 예외를 그대로 쓰지 않기. |
| POL-009 | `pac/intake.rego:183`–`:194` | **제한 허용을 무제한 허용으로 변경.** 보안 관리자 예외만 있으면 공개자료 제한을 강제할 수 없어도 DENY·RESTRICT가 모두 사라진다. | I: provider_terms={}, gateway_controls={}; D: 승인 POL-009 예외 target=vendor, scope=["s1"]. `009_exception_cannot_remove_restriction`. | 새 처리 기준 승인과 미확인 상태의 강제 제한을 구별. 예외로 최소 차단 조건을 생략하지 않기. |
| POL-005 | `pac/intake.rego:128`–`:149` | **자료 범위 미검사·잘못된 타입 허용.** data_scope는 비었는지만 보고 실제 반환 자료 범위와 비교하지 않는다. fields=true도 filled를 통과하며 빈 observed_fields와 결합하면 허용. | I: 관측 자료 범위 internal, 승인 범위 public; 또는 fields=true, observed_fields=[]. `005_outside_data_scope`, `005_boolean_output_fields`. | 출력 항목·자료 범위의 타입과 실제 결과를 모두 대조. observed_data_scope 등의 관측값 계약 필요. |
| POL-011 | `pac/intake.rego:232`; `pac/lib.rego:64` | **내용 없는 필수 문서 허용.** filled는 false·0을 유효한 기록으로 보므로 functions=false도 통과. 공유 helper를 무조건 바꾸면 정상 불리언·0까지 깨진다. | I: `application.requirements.functions=false`. `011_false_requirement`. | 문서 항목에 맞는 타입·비어 있지 않은 내용 검사를 해당 계약에 추가. |
| POL-012 | `pac/connect.rego:52`–`:55` | **확인 불가 신원의 동일 취급.** 등록부와 입력 identity가 둘 다 null/빈 문자열이면 일치로 인정한다. 계약은 identity를 검증하지 않는다. | C·D의 identity=null. `012_null_identity_equals_null`. | 양쪽 신원 형식·실제 검증 성공을 요구하고 주소·인증서/키·서버 ID에 결속. |
| POL-014 | `pac/connect.rego:83`–`:107` | **다른 대상 승인 활성화·예외 기록의 약한 검증.** approval.server_id와 connection.server_id를 비교하지 않는다. 예외 approver는 filled만, 종료일은 숫자인지만 확인한다. | C: stage=approve, approval.server_id=s2인데 connection.server_id=s1. 별도 반례로 method=exception, approver=false, not_after_ns=0, recorded=true도 기록 완전성 검사 통과 예상. | 대상 결속, 승인자 신원·보안 관리자 권한·승인 상태, 종료일 유효성을 확인. 단순 기록 완전성인지 실제 활성화 판정인지 계약을 분리. |
| POL-019·073 | `pac/connect.rego:120`, `:291` | **등록 전 차단 원칙 우회.** 예외로 인증 서버 ID 불일치나 등록부에 반영되지 않은 새 주소를 곧바로 허용한다. POL-019 예외에는 인증 서버 ID도 없다. | 인증 서버 id=other-auth인데 주소만 맞는 예외, 또는 connection.address=new.example인데 등록부는 mcp.example인 승인 예외. `019_exception_does_not_bind_auth_id`, `073_exception_without_registry_update`. | 시트대로 승인된 변경을 등록부에 먼저 반영한 뒤 정상 비교. 인증 서버 신원·주소를 함께 결속. |
| POL-029·031 | `pac/connect.rego:190`–`:211` | **승인 실행 설정 검증 부족.** launch={}도 POL-029는 승인 설정으로 인정한다. 실제·승인 sha256이 모두 빈 문자열이면 POL-031도 통과한다. 빈 launch의 경우 launch 단계 POL-031이 대신 차단할 수 있으나 connect 단계에는 그 검사도 없다. | C kind=local, D.launch={}; 또는 launch 단계 양쪽 sha256="". `029_empty_local_launch_registration`, `031_empty_launch_hashes`. | 승인 설정의 필수 항목·타입·파일 해시 형식 검증. connect/launch 단계별 책임을 명확히 연결. |
| POL-032 | `pac/connect.rego:253`–`:257` | **미표시 정보로 동의 통과.** shown의 provider/address/functions=false도 filled를 통과한다. 표시값과 실제 제공자·주소·기능의 일치도 검사하지 않는다. | C: shown={provider:false,address:false,functions:false}, decision=accept. `032_false_display_fields`. | 표시 여부와 표시 실제값을 구별하고, 해당 동의 화면의 값·요청에 결속. |
| POL-007·043·051 | `pac/resource.rego:51`–`:80`; `pac/call.rego:523` | **권한·관측값 귀속 부재.** Prompt 사용 권한을 전혀 보지 않는다. Resource 및 서버 계정의 사용자 ACL은 true 하나만 보며 실제 사용자·파일·작업·호출과 결속하지 않는다. | R acl.user_can=false인 승인 Prompt; R resource_read의 acl.user=bob/user_can=true; T server_account.used=true, acl.doc_id=d2인데 요청 d1. 관련 `007_prompt_user_without_permission`, `043_acl_for_other_user`, `051_acl_for_other_document`. | 사용자·문서·작업·request ID·조회 시각/권한 판본을 계약에 포함하고 대조. 현재 Prompt/Resource는 미중개라는 배포 경계와 구분. |
| POL-052 | `pac/call.rego:542`–`:545` | **계정의 문서 범위 미검사.** 서버 계정은 작업과 data_class만 대조하므로 같은 등급의 다른 문서에 접근 가능. 문서 사용자 권한과 계정 자체의 승인 범위는 별개다. | D 계정 documents=["d1"]; T 대상 d2, 사용자 document_grants는 d2를 허용. `052_server_account_other_document`. | 계정 ID와 승인 문서·폴더/저장소 범위를 표현하고 실제 접근 대상과 대조. |
| POL-040·047·023 | `pac/call.rego:324`, `:415`; `pac/connect.rego:153`; `pac/lib.rego:130`–`:152` | **주소 허용 범위 불완전.** 호스트+전역 사설 주소 제외만 보며 정책별 승인 IP 범위를 보지 않는다. valid_ip는 CIDR도 받는 cidr_contains로 구현되어 "8.8.8.0/24"를 단일 해석 IP로 인정한다. protected_cidrs는 주석과 달리 문서용 IPv4·IPv6 대역도 빠져 있다. | T egress.resolved_ips=["1.1.1.1"], 제안 egress_ip_ranges=["8.8.8.0/24"]; 또는 resolved_ips=["8.8.8.0/24"]. `040_public_ip_outside_approved_range`, `047_cidr_is_not_resolved_ip`. | 단일 IP 형식을 먼저 확인한 뒤 승인 CIDR·특수 목적 주소 기준과 대조. 최종 URL의 scheme·port·path 승인 범위도 계약화. |
| POL-049·050·056·070 | `pac/call.rego:454`–`:509`; `pac/ops.rego:159`–`:172` | **수치 타입·범위 검증 부족.** 음수/소수 반환량·사용량을 허용한다. rate limit 상한에는 is_number가 없어 숫자가 문자열 상한보다 작은 것으로 비교될 수 있다. 낮음 취약점 scheduled_change_ns="tomorrow"도 숫자 now보다 큰 문자열로 비교되어 기한 내로 판단될 수 있다. | T response.items=-1; D rate_limits.tool={window_calls:"10",concurrent:"2"}; O low 취약점의 scheduled_change_ns="tomorrow". `049_negative_result_count`, `056_string_rate_limits`, `070_string_scheduled_change_date`. | 카운터·한도는 유한한 0 이상 정수, 시각은 숫자 및 허용 범위로 검증. 비교 전에 양쪽 타입 확인. |
| POL-050·056·070 | `pac/call.rego:479`, `:500`; `pac/ops.rego:151`; `pac/lib.rego:112` | **예외가 새 한도·잔여 위험을 표현하지 못함.** 예외 존재만으로 원래 판정을 통째로 생략한다. 조회량 예외가 blocked_pattern까지 무시하며 호출 상한·기한 연장의 실제 새 값·제한 범위·잔여 위험은 검사하지 않는다. | 정상 승인 역할·기간의 POL-050 예외 target=alice/scope=["read"]와 usage.blocked_pattern=true; POL-056 예외 scope=["tool"]와 tool 집계 999999. | 승인된 새 수치·허용 패턴·새 기한과 제한 범위로 정상 판정을 재계산. 예외 존재를 무제한 면제로 쓰지 않기. |
| POL-070 | `pac/ops.rego:138`, `:161`–`:172` | **악용 조건 완화·등급별 조기 차단.** 시트 content는 실제 악용 **또는** 외부 노출 치명에 48시간인데 코드는 두 조건의 AND다. 그 밖의 치명 14일·높음 30일·보통 90일이라는 본문과 달리 코드는 critical/high 14일·medium 30일·시트에 없는 low_actionable 90일로 매핑한다. | O: critical, exploited=true, exposed=false, confirmed_ns=now−48시간이면 코드상 14일 유예가 남는다. `070_exploited_critical_only_at_48h_deadline`. 반대로 high를 확인한 지 14일이면 본문상 30일 기한 전인데 차단 예상. | 시트의 등급·기한 정본을 명확히 하고 OR 조건과 등급표를 그대로 옮기기. block_condition의 48시간/등급별 기한 문장과 content를 함께 추적하고, 현재 코드 주석을 시트의 확정 매핑으로 취급하지 않기. |
| POL-058 | `pac/call.rego:628`–`:631` | **기록 가능성과 성공 혼동.** writable=true 하나로 진행하며 현재 호출의 안전한 기록 성공·보호 임시 저장소 상태·동기화 결과를 검증하지 않는다. | T audit.central_writable=true, 제안 audit.recorded=false. `058_writable_but_record_failed`. | 실행 전 기록/예약과 결과 감사 상태를 결속하고 실패 후 중단·알림을 실행기에서 구현. Rego true만으로 실제 저장 성공을 입증하지 않기. |
| POL-063 | `pac/ops.rego:77`; `:25`–`:28` | **시트보다 약한 조치.** 명세 변경에 restrict를 내고 RESTRICT로 집계한다. 시트는 불일치 호출을 차단하고 재판정하라고 한다. call의 별도 DENY가 있어도 운영 조치만 소비하는 경로는 불충분하다. | O observed_tools[0].contract_sha256=다른 64자리 해시. `063_ops_changed_hash_must_block`는 action=block을 요구. | 변경 Tool을 지정해 실행 차단 상태로 전이. 제한 허용과 실행 금지를 혼동하지 않기. |
| POL-065·067·071 | `pac/resource.rego:98`, `:63`; `pac/ops.rego:189` | **유효성 검증 부족.** 삭제 목록 누락을 빈 목록으로 취급한다. Prompt 해시는 양쪽 []여도 같다고 인정한다. baseline_config_sha256=""와 config_sha256=""도 인스턴스 일치로 인정한다. | R deleted_resources 제거; 양쪽 Prompt sha256=[]; O 양쪽 config 해시="". 관련 `065_missing_deletion_snapshot`, `067_non_string_template_hash`, `071_empty_baseline_hash`. | 스냅숏의 완료·판본·삭제 정보, 해시의 문자열·길이·인코딩·신뢰 출처 검증. |
| POL-016 | `pac/call.rego:197`–`:206` | **과차단 / 적용 대상.** 모든 request에 원격 토큰 검증을 요구한다. 시트 체크포인트는 “토큰을 사용하는 원격 요청마다”이므로 토큰 없는 정상 로컬 호출을 표현할 수 없다. | 승인 로컬 서버에 대한 유효한 request에서 facts.token 미제공. 해당 정책 DENY 예상. 토큰 만료·문자열 true 시험과는 별도 정적 반례. | 서버 transport·인증 방식·토큰 사용 여부를 신뢰된 등록부에서 정하고 적용 대상을 구별. |

수치 타입 간 비교는 자동 숫자 변환이 아니다. 공식 OPA 비교 구현에서 Number가 String보다 먼저 정렬된다. CIDR 포함 내장 함수의 두 번째 인자도 단일 IP에 한정되지 않는다. 위 두 항목은 이 의미에 따른 추론이며 사용자가 실행할 OPA 판본에서 확인해야 한다. [OPA 비교 구현](https://raw.githubusercontent.com/open-policy-agent/opa/main/v1/ast/compare.go), [OPA 네트워크 내장 함수](https://www.openpolicyagent.org/docs/policy-reference/builtins/net)

## 2. 입력 계약의 빈틈

머리 주석은 최상위 객체 이름을 나열하지만, 다음 필드의 타입·의미·검증 주체·최신성·결속 조건이 부족하다. `facts.trusted=true`는 문자열 true를 거절하지만 그 자체가 출처 증명은 아니다. 게이트웨이가 사용자 입력을 그대로 facts에 복사하면 모든 검사 결과를 위조할 수 있다.

| 필요한 계약 | 영향 정책과 필요한 보완 |
| --- | --- |
| stage와 실행 게이트의 연결 | 승인 활성화·실제 connect·launch·OAuth·request·response·list·이벤트를 누가 언제 호출하는지. 해당 stage를 건너뛸 수 없어야 한다. ops는 제안 action을 생성할 뿐이며 실제 차단 효과 증거는 별도로 필요하다. |
| transport 신원과 facts 귀속 | call의 user·agent 외 connect.user와 Resource user도 transport에서만 생성. ACL·token·permission_lookup·schema·inspection·arguments_validated를 request ID, 사용자, 서버, Tool, 대상·작업·인자 해시, 관측 시각/판본과 결속. 현재 permission_lookup는 request_id만, 다른 다수 결과는 그것도 없다. |
| 센서 완료와 빈 결과 구별 | 설명 검사·입력 검사·평문 검사·패키지/SBOM·취약점·인스턴스·scope/권한·삭제 상태의 status, 목록 타입, 개별 항목 필수값, 대상 inventory와 완전성. [] 자체를 조회 성공으로 해석하지 않기. |
| 등록부의 검증된 내용 | state enum, identity의 검증된 형식, Tool kind/document_scoped/fetches_url/sensitive 불리언, 해시 형식, launch 필수 항목, 승인 주체·승인 상태·유효기간. 분류 플래그를 없애 검사를 끄는 입력을 막아야 한다. |
| 승인과 예외의 차이 | 일반 권한표·위임·제공자·패키지 allowlist는 active()로 날짜만 필터링한다. status·승인자·역할 검증은 exception_for에만 있다. 일반 승인 데이터는 누가 승인·철회해 배포하는지 명시해야 한다. 사용자 제시 자기 승인값을 허용해서는 안 된다. |
| 정책별 구체적 예외 범위 | 대상·scope 문자열 목록 외 자료·작업·목적·서버/Tool·주소/IP·새 한도·기한·제한 조건·잔여 위험과 예외 승인 기록 ID. 승인자 역할뿐 아니라 실제 신원과 권한 근거, 철회 상태도 신뢰된 저장소에서 조회. |
| 실제 출력 자료·계정 문서 범위 | POL-005의 실제 자료 유형/범위, POL-052의 계정 ID·문서/저장소 범위, POL-007의 Prompt 사용 권한이 없다. 보고서의 제안 필드명은 이를 드러내기 위한 것이며 확정 스키마가 아니다. |
| 최종 네트워크 접속과 경로 결속 | DNS 전체 결과·실제 선택 IP·각 redirect hop·최종 URL·scheme·port·정책별 IP 범위, 승인 host 정규화 기준. 경로는 원문과 symlink 해석 결과·OS·실제 열린 파일 ID에 결속하고 판정 뒤 재해석/재접속 우회를 막아야 한다. |
| 수치·시각의 단위와 경계 | 카운터는 음수·소수 금지, 한도도 같은 검증. now_ns/expiry/confirmed_ns는 신뢰된 숫자 시각. 취약점 저위험 변경일 및 exploited/exposed 누락을 일반 14일로 떨어뜨릴지 미확인 차단할지 명시. |
| 경쟁·복구 상태 | 호출량/동시 실행 수와 확인값 예약이 이번 호출을 포함하는지, 원자적 예약·1회 소비·실패 해제 절차. 현재 확인값은 reserved_for/used만 보므로 실제 원자성은 실행기가 보장해야 한다. |
| 감사·취약점·폐기 증거 | writable와 현재 기록 성공을 구별하고 보호 버퍼/동기화 상태를 확인. 패치·대체 통제·삭제 증빙은 어떤 CVE·영향 버전·제공자·자료·시각에 대한 누구의 검증인지 필요. 단순 verified=true만으로 실제 효과를 입증하지 못한다. |

## 3. 카탈로그·분류와 규칙의 불일치

생성 바이트 대조는 통과했고, 90개 카탈로그 항목의 checkpoint·block_condition이 시트와 같은 것도 확인했다. **생성물 최신성과 집행 의미 일치는 별개다.**

| 정책/영역 | 불일치 |
| --- | --- |
| POL-003 | 시트는 Tool 등록·권한 변경·호출 모두인데 call.request에서만 검사한다. intake에는 자료 소유 부서의 권한표 대조가 없다. |
| POL-008 | 시트는 로컬 시작 및 Tool 호출 전인데 connect.launch에만 실제 권한/격리 검사가 있다. 호출 전 권한 변화·격리 강제 상태 재검증 계약이 없다. |
| POL-025 | 시트는 서버 연결·토큰 선택 때인데 call.request에만 있다. connect/oauth에서 잘못된 서버 자격이 사용되는 것을 이 규칙만으로 막을 수 없다. |
| POL-037 | METADATA와 시트는 외부 문서·Tool 결과를 Agent에 전달할 때인데 실제 규칙은 request의 intent가 approval/permission_change일 때만 적용된다. response에 권한 변경 채널로 전달되는 사실을 넣어도 검사하지 않는다. `037_response_into_authority_channel`로 이를 드러낸다. |
| POL-010·053·054 | POL-010의 시트는 미확인 실행도 차단하지만 코드 POL-010은 확인 대상 분류만 보고 유효 확인은 053/054에 위임한다. CONFIRM은 lib 설명대로 실행 중단 상태로 소비해야 한다. 이를 허용으로 취급하면 우회다. 한 정책 ID씩 추적할 때 010이 유효 확인을 검증하는 것처럼 표시하면 안 된다. |
| POL-024·071·074·077 | 시트는 발급/로그 기록, 인스턴스 기동, 실제 하위 전송, 권한 확대 감지 시점인데 ops의 제한된 이벤트·스냅숏만 검사한다. 예를 들어 024의 block_deploy는 이미 기록된 평문 로그를 막지 못하고, 074의 정기 점검은 전송 직전 게이트가 아니다. 외부 실행기 연결은 이번 범위에서 확인하지 않았다. |
| POL-063 | 시트는 불일치 호출 차단인데 ops는 restrict/RESTRICT. call의 DENY와 소비 경로가 다르므로 같은 정책의 동일 집행으로 볼 수 없다. |
| POL-070 | 카탈로그는 시트 content를 보존하지 않아 “악용 또는 노출”과 등급별 14/30/90일 매핑이 추적에서 빠진다. ops 머리 주석과 due_ns의 AND·등급 매핑을 시트로 오인하면 지연 차단과 과차단을 놓친다. 원문의 “실제 악용·외부 노출”이라는 축약 block_condition만으로 본문의 명시적 OR를 AND로 바꿀 근거는 없다. |
| POL-002·003·034·041 등 예외 | 자료 소유 부서 역할 값 자체는 카탈로그와 lib에서 맞게 비교한다. 결함은 최종 역할 오역보다 **승인된 자료·작업·목적 범위의 누락**과 “권한표 변경 승인”을 실행 예외 면제로 취급하는 데 있다. |
| POL-008·009·069 카탈로그 | `build_catalog.py:53`–`:61`는 예외 문장에 보안 관리자가 등장하면 security_admin으로 분류한다. 그러나 008/009는 제한 허용·새 기준 승인이고 069는 실패 재조회·보안 관리자 통보다. 이를 일반 실행 면제 권한으로 해석하면 안 된다. 현재 009는 실제로 면제에 사용하고, 008/069에는 그 호출이 없으므로 후자는 카탈로그 의미 손실이다. |
| POL-007·043·065·066·067 | 분류는 excluded이지만 resource 패키지에 판정 규칙이 있다. 머리 주석상 미래 중개용이며 현재 게이트웨이의 전부 거부와 구별해야 한다. 5개 모두 이번 시험에는 포함했지만 실제 Resource/Prompt 집행 증거로 세지 않았다. |
| 전체 분류 | 규칙이 있는 65개는 pac 47개·implemented 13개·excluded 5개다. classification의 status/note/evidence는 기존 게이트웨이 경로의 부분·미구현·구조적 차단 사유를 포함한다. 새 policy/pac 소스 존재만으로 “배포되어 구현됨”으로 갱신할 수 없다. |

POL-013의 종료일 미확인·정각 만료, POL-016의 문자열 true·만료, POL-033의 다른 사용자·정각 만료, POL-054의 다른 확인자·재사용·정각 만료 등은 회귀를 지켜야 할 정상 차단 기대 시험으로 포함했다. 정적 검토만으로 이들이 실행 통과했다고 보고하지 않는다.

## 4. METADATA·trace 추적성

| 위치 | 어려운 점 | 고칠 방향 |
| --- | --- | --- |
| `tools/trace.py:54`–`:58` | test_pol_NNN_pass/block만 집계하므로 이번 필수 이름 test_adv_pol_NNN_*는 **144개 모두 추적 집계에서 빠진다**. 기존 시험 개수는 독립성 조건 때문에 읽거나 집계하지 않았다. | 일반·적대적 시험 이름을 함께 인식하고 기대 effect/action과 실행 결과를 별도 기록. 이번 요청에서는 trace.py를 수정하지 않았다. |
| `tools/trace.py:33`–`:50` | 주석 아래 첫 규칙 하나만 정책 위치로 기록한다. resource의 [POL-007, POL-067]은 둘 다 :51의 POL-067 finding에 연결되지만 실제 POL-007 finding은 :56이다. intake/call/ops의 후속 규칙·보조 함수도 누락된다. | OPA AST/메타데이터로 정책 ID와 각 finding/violation 및 보조 규칙 관계를 연결. 다중 ID annotation은 각 결과를 정확히 가리키게 작성. |
| `tools/trace.py:72`–`:77`, `:104`–`:117` | 규칙 주석과 pass/block 이름 존재만으로 “Rego 규칙·시험”이 된다. 본문이 실제 그 정책을 내는지, effect·policy_id·server/action까지 검증하는지, 컴파일·실행됐는지 확인하지 않는다. 제외 정책도 규칙이 있으면 같은 표시가 된다. | 정적 연결·컴파일·평가·게이트웨이 연결·실기기 효과를 별도 열로 구별. expected checkpoint/승인 주체·반례도 연결. |
| `pac/lib.rego:34`–`:39` | decision.policy_ids/reasons는 최강 effect의 정책만 남긴다. DENY와 동시에 발생한 MANUAL/CONFIRM/RESTRICT는 결과에서 사라지므로 전체 정책 적용 내역이 아니다. | 집행 effect와 전체 findings를 구별해 감사에 남기기. 시험은 약한 효과가 다른 DENY에 가려지지 않도록 정상 fixture를 사용. ops는 전체 violations를 직접 확인. |
| `tools/build_catalog.py:89`–`:99`; `pac/catalog.rego:10` 이후 | pass_condition·inputs·exception 원문·content가 카탈로그에 없고 exception은 역할 하나로 축약된다. “예외 없음/수동 판단/제한 허용/승인 기준 변경”을 구별할 수 없다. | 원문 추적 링크·해시와 승인 방식·조건의 구조화 필드를 보존. 카탈로그를 의미상 완전한 정책 원문으로 취급하지 않기. |
| 규칙 METADATA 전반 | risk_id·checkpoint·pol_id는 있으나 시트 해시·행/필드·원자 조건·소비 게이트·입력 스키마 판본·판정 후 실제 조치가 연결되지 않는다. | 시트 조건 → 규칙/보조 함수 → 합성 반례 → 실제 OPA 결과 → 게이트 → 실제 차단/복구 증거를 연결. 기존 도구 실행만으로 추론·운영 효과를 혼동하지 않기. |

`trace.py --check`는 내부에서 기존 시험을 읽으므로 실행하지 않았다. 소스만 읽어 추적 한계를 검토했다. `TRACE.md`나 기존 시험의 실제 내용·통과 상태를 추정하지 않았다.

## 판본과 후속 실행

| 입력 파일 | SHA-256 |
| --- | --- |
| `source/sheet.json` | `4e19c2482eab209b2582d95bf5832452f6a9cafdc15a33268bda7b3c5ee95330` |
| `source/classification.json` | `e86046c5476ee355d969420e4188b01f384c93d3c652be917d7df882825c27b4` |
| `pac/catalog.rego` | `c084949f889c1fae3ad33a5673efc14a931814cff40eeb725b91121da4ec6498` |
| `pac/lib.rego` | `98704d8b79e4aa3a13e572af60c33a893e26d607c690fbbc293b9ef97c8a190f` |
| `pac/intake.rego` | `cf1da5057e0c606149a49714407286dbc2b664203d03304a3ebce0c9b23cbaca` |
| `pac/connect.rego` | `9a0a3ac374cf75f3ce634958e37e46ca3a03fb6984528d8d4cb2464f6b332c49` |
| `pac/call.rego` | `6fdd5b6caeadc6b4bb3cb6d097de15d9293a0019f766c9739c682447884636e1` |
| `pac/ops.rego` | `0a69966448a3a4078bdcffc24ba665096f05cb293242ec2396a7f4b8d37cf096` |
| `pac/resource.rego` | `25406971d543c43111c2880db4dd833e3f770ace265846cc670c2de6d21ccadc` |

다른 시험 파일을 로드하지 않고 독립 시험만 실행하려면 저장소 루트 PowerShell에서 다음과 같이 실행한다. OPA 버전과 종료 코드, 실패 시험명·설명 trace를 함께 보관해야 한다.

```powershell
$policyFiles = @('lib', 'catalog', 'intake', 'connect', 'call', 'ops', 'resource', 'zz_adversarial_test') |
    ForEach-Object { "policy/pac/$_.rego" }
opa test @policyFiles -v --run '^test_adv_pol_'
```

OPA 오류·컴파일 실패는 실패로 취급해야 한다. 이 보고서는 수정 제안이며 정책 본문·분류·카탈로그·추적 도구를 고치지 않았다. 네트워크 접속·게이트웨이 배포·실제 하네스·경쟁/복구 효과는 확인하지 않았다.

## 총평

미정의 인자·결과 식별자와 잘못된 타입의 빈 목록 변환이 필수 차단을 없애는 경로를 먼저 닫아야 한다.  
승인 역할 비교만으로는 부족하며, 시트의 자료·작업·목적·한도·기간을 실제 요청과 결속해야 한다.  
144개 독립 시험과 정적 근거를 제공했으며, OPA 실행 결과와 실제 게이트 집행·복구 증거는 아직 없다.

