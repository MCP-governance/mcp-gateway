# 독립 반례 시험. 규칙 작성자의 시험을 보지 않고 시트(source/sheet.json)의 조건만으로 쓴 것이다.
# 이름 규칙: test_adv_pol_<번호>_* — 추적표에 「반례」 열로 따로 센다. 합성 입력이며 실제 MCP 실행 증거가 아니다.
# 모든 시험이 input과 data.pol을 통째로 바꾼다(json.patch는 빈 값으로도 덮어쓴다).
# 기본 입력(adv_*)은 입력 계약이 바뀌면 그에 맞춰 고친다. 단언(기대 결과)은 시트가 바뀔 때만 고친다.
package mcp.pol.adversarial_test

import data.mcp.pol.call
import data.mcp.pol.connect
import data.mcp.pol.intake
import data.mcp.pol.ops
import data.mcp.pol.resource
import rego.v1

# POL-070: 시트 본문은 실제 악용 중이거나 외부 노출된 치명 취약점을 48시간 내 조치하도록 요구.
test_adv_pol_070_exploited_critical_only_at_48h_deadline if {
	i := json.patch(adv_ops_input, [{"op": "add", "path": "/servers/0/vulnerabilities", "value": [{"id": "CVE-TEST", "severity": "critical", "exploited": true, "exposed": false, "affected_version": "1.0", "confirmed_ns": 19827200000000000, "patched": false, "compensating_control": {"verified": false}}]}])
	d := json.patch(adv_data, [])
	vs := ops.violations with input as i with data.pol as d
	some v in vs
	v.policy_id == "POL-070"
	v.server == "s1"
	v.action == "block"
}

# POL-047: 해석 IP 자리에 CIDR을 넣으면 실제 단일 접속 IP를 확인한 것이 아님.
test_adv_pol_047_cidr_is_not_resolved_ip if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/facts/egress/resolved_ips", "value": ["8.8.8.0/24"]}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-047" in decision.policy_ids
}

# POL-019: 인증 서버 신원·주소가 null이면 승인 목록 확인 불가로 인증 요청 차단.
test_adv_pol_019_null_auth_server_not_argument if {
	i := json.patch(adv_connect_input, [{"op": "add", "path": "/connection/stage", "value": "oauth"}, {"op": "add", "path": "/connection/auth_server", "value": null}])
	d := json.patch(adv_data, [])
	decision := connect.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-019" in decision.policy_ids
}

# POL-071: 인스턴스 항목 null은 승인 설정 확인 불가이므로 트래픽 차단.
test_adv_pol_071_null_instance_not_argument if {
	i := json.patch(adv_ops_input, [{"op": "add", "path": "/servers/0/instances", "value": [null]}])
	d := json.patch(adv_data, [])
	vs := ops.violations with input as i with data.pol as d
	some v in vs
	v.policy_id == "POL-071"
	v.server == "s1"
	v.action == "stop_traffic"
}

# POL-001: 승인 목록 종료일 정각에는 도입 차단.
test_adv_pol_001_allowlist_at_expiry if {
	i := json.patch(adv_intake_input, [])
	d := json.patch(adv_data, [{"op": "add", "path": "/providers/0/not_after_ns", "value": 20000000000000000}])
	decision := intake.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-001" in decision.policy_ids
}

# POL-001: 예외가 심사 중이면 승인 전 도입 차단.
test_adv_pol_001_exception_pending if {
	i := json.patch(adv_intake_input, [{"op": "add", "path": "/application/provider", "value": "new-vendor"}])
	d := json.patch(adv_data, [{"op": "add", "path": "/exceptions", "value": [{"policy_id": "POL-001", "target": "new-vendor", "scope": ["https://pkg.example/mcp"], "approved_by": "reviewer", "approved_by_role": "security_admin", "status": "pending", "not_before_ns": 19913600000000000, "not_after_ns": 20086400000000000}]}])
	decision := intake.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-001" in decision.policy_ids
}

# POL-001: 새 제공자 예외의 최종 승인 주체는 보안 관리자.
test_adv_pol_001_exception_wrong_approver if {
	i := json.patch(adv_intake_input, [{"op": "add", "path": "/application/provider", "value": "new-vendor"}])
	d := json.patch(adv_data, [{"op": "add", "path": "/exceptions", "value": [{"policy_id": "POL-001", "target": "new-vendor", "scope": ["https://pkg.example/mcp"], "approved_by": "reviewer", "approved_by_role": "data_owner", "status": "approved", "not_before_ns": 19913600000000000, "not_after_ns": 20086400000000000}]}])
	decision := intake.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-001" in decision.policy_ids
}

# POL-001: 제공자·공식 주소를 확인할 수 없으면 도입 차단.
test_adv_pol_001_missing_provider if {
	i := json.patch(adv_intake_input, [{"op": "remove", "path": "/application/provider"}])
	d := json.patch(adv_data, [])
	decision := intake.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-001" in decision.policy_ids
}

# POL-002: 자료 소유 부서의 범위 심사는 다른 자료 범위까지 허용하지 않음.
test_adv_pol_002_exception_unbound_data if {
	i := json.patch(adv_intake_input, [{"op": "add", "path": "/application/tools/0/data_types", "value": ["secret"]}])
	d := json.patch(adv_data, [{"op": "add", "path": "/exceptions", "value": [{"policy_id": "POL-002", "target": "read", "scope": ["s1"], "approved_by": "reviewer", "approved_by_role": "data_owner", "status": "approved", "not_before_ns": 19913600000000000, "not_after_ns": 20086400000000000, "data_types": ["public"]}]}])
	decision := intake.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-002" in decision.policy_ids
}

# POL-002: Tool 권한이 미분류이면 등록 차단.
test_adv_pol_002_missing_permissions if {
	i := json.patch(adv_intake_input, [{"op": "remove", "path": "/application/tools/0/permissions"}])
	d := json.patch(adv_data, [])
	decision := intake.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-002" in decision.policy_ids
}

# POL-003: 새 자료·작업 권한은 승인 권한표 변경 전 호출 차단.
test_adv_pol_003_exception_unbound_operation if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/request/operation", "value": "delete"}, {"op": "add", "path": "/facts/confirmation", "value": {"server_id": "s1", "tool": "read", "operation": "delete", "target": "d1", "recipient": "partner", "arguments_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "confirmed_by": "alice", "reserved_for": "r1", "used": false, "expires_ns": 20003600000000000}}])
	d := json.patch(adv_data, [{"op": "add", "path": "/permission_table", "value": []}, {"op": "add", "path": "/exceptions", "value": [{"policy_id": "POL-003", "target": "alice", "scope": ["s1/read"], "approved_by": "reviewer", "approved_by_role": "data_owner", "status": "approved", "not_before_ns": 19913600000000000, "not_after_ns": 20086400000000000, "operations": ["read"]}]}])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-003" in decision.policy_ids
}

# POL-003: 다른 사용자의 권한표로 현재 호출을 허용할 수 없음.
test_adv_pol_003_permission_other_user if {
	i := json.patch(adv_call_input, [])
	d := json.patch(adv_data, [{"op": "add", "path": "/permission_table", "value": [{"user": "bob", "server_id": "s1", "tool": "read", "data_class": "internal", "operation": "read", "not_after_ns": 20086400000000000}]}])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-003" in decision.policy_ids
}

# POL-004: 위험 문구 검사 결과가 없으면 승인 검사항목 통과를 입증할 수 없음.
test_adv_pol_004_completed_without_findings if {
	i := json.patch(adv_intake_input, [{"op": "remove", "path": "/application/tools/0/description_scan/findings"}])
	d := json.patch(adv_data, [])
	decision := intake.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-004" in decision.policy_ids
}

# POL-004: 위험 여부가 불분명하면 보안 관리자 판단 전까지 중단.
test_adv_pol_004_unclear_is_manual if {
	i := json.patch(adv_intake_input, [{"op": "add", "path": "/application/tools/0/description_scan/findings", "value": [{"level": "unclear"}]}])
	d := json.patch(adv_data, [])
	decision := intake.decision with input as i with data.pol as d
	decision.effect == "MANUAL"
	"POL-004" in decision.policy_ids
}

# POL-005: 출력 항목 정의가 true이면 유효한 출력 정의가 아님.
test_adv_pol_005_boolean_output_fields if {
	i := json.patch(adv_intake_input, [{"op": "add", "path": "/application/tools/0/output_contract/fields", "value": true}, {"op": "add", "path": "/application/tools/0/trial_results/0/observed_fields", "value": []}])
	d := json.patch(adv_data, [])
	decision := intake.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-005" in decision.policy_ids
}

# POL-005: 시험 결과가 정의된 반환 자료 범위 밖이면 도입 차단.
test_adv_pol_005_outside_data_scope if {
	i := json.patch(adv_intake_input, [{"op": "add", "path": "/application/tools/0/trial_results/0/observed_data_scope", "value": ["internal"]}])
	d := json.patch(adv_data, [])
	decision := intake.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-005" in decision.policy_ids
}

# POL-006: 필수 시험을 통과하지 않은 빈 시험 목록은 다음 심사로 진행할 수 없음.
test_adv_pol_006_empty_trials if {
	i := json.patch(adv_intake_input, [{"op": "add", "path": "/application/tools/0/trial_results", "value": []}])
	d := json.patch(adv_data, [])
	decision := intake.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-006" in decision.policy_ids
}

# POL-006: 시험의 실제 동작을 확인할 수 없으면 재시험 전 등록 차단.
test_adv_pol_006_missing_observed_effect if {
	i := json.patch(adv_intake_input, [{"op": "remove", "path": "/application/tools/0/trial_results/0/observed_effect"}])
	d := json.patch(adv_data, [])
	decision := intake.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-006" in decision.policy_ids
}

# POL-007: 차단된 지시 유형 검사를 확인할 수 없으면 템플릿 사용 차단.
test_adv_pol_007_missing_prompt_scan if {
	i := json.patch(adv_resource_input, [{"op": "remove", "path": "/facts/prompt_scan/blocked_types"}])
	d := json.patch(adv_data, [])
	decision := resource.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-007" in decision.policy_ids
}

# POL-007: 승인 템플릿과 같아도 사용 권한이 없으면 사용 불가.
test_adv_pol_007_prompt_user_without_permission if {
	i := json.patch(adv_resource_input, [{"op": "add", "path": "/facts/acl/user_can", "value": false}])
	d := json.patch(adv_data, [])
	decision := resource.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-007" in decision.policy_ids
}

# POL-008: 실제 권한을 확인하지 못하고 격리도 강제하지 못하면 실행 차단.
test_adv_pol_008_missing_observed_permissions if {
	i := json.patch(adv_connect_input, [{"op": "add", "path": "/connection/stage", "value": "launch"}, {"op": "add", "path": "/connection/kind", "value": "local"}, {"op": "remove", "path": "/connection/launch/observed_permissions"}])
	d := json.patch(adv_data, [])
	decision := connect.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-008" in decision.policy_ids
}

# POL-008: 문자열 true는 격리 검증 사실이 아님.
test_adv_pol_008_string_isolation_verified if {
	i := json.patch(adv_connect_input, [{"op": "add", "path": "/connection/stage", "value": "launch"}, {"op": "add", "path": "/connection/kind", "value": "local"}, {"op": "add", "path": "/connection/launch/observed_permissions", "value": ["write"]}, {"op": "add", "path": "/connection/launch/isolation", "value": {"verified": "true", "public_read_only": true, "internal_data_blocked": true}}])
	d := json.patch(adv_data, [])
	decision := connect.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-008" in decision.policy_ids
}

# POL-009: 조건 미확인의 제한 허용은 공개자료 강제 제한 설정을 생략하지 않음.
test_adv_pol_009_exception_cannot_remove_restriction if {
	i := json.patch(adv_intake_input, [{"op": "add", "path": "/application/provider_terms", "value": {}}, {"op": "add", "path": "/application/gateway_controls", "value": {}}])
	d := json.patch(adv_data, [{"op": "add", "path": "/exceptions", "value": [{"policy_id": "POL-009", "target": "vendor", "scope": ["s1"], "approved_by": "reviewer", "approved_by_role": "security_admin", "status": "approved", "not_before_ns": 19913600000000000, "not_after_ns": 20086400000000000}]}])
	decision := intake.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-009" in decision.policy_ids
}

# POL-009: 조건 미확인이라도 공개자료 조회만 강제되면 제한 허용.
test_adv_pol_009_unknown_terms_enforced_restriction if {
	i := json.patch(adv_intake_input, [{"op": "add", "path": "/application/provider_terms", "value": {}}])
	d := json.patch(adv_data, [])
	decision := intake.decision with input as i with data.pol as d
	decision.effect == "RESTRICT"
	"POL-009" in decision.policy_ids
}

# POL-009: 제공자 조건 미확인이고 내부자료 전달을 막지 못하면 차단.
test_adv_pol_009_unknown_terms_without_controls if {
	i := json.patch(adv_intake_input, [{"op": "add", "path": "/application/provider_terms", "value": {}}, {"op": "add", "path": "/application/gateway_controls", "value": {}}])
	d := json.patch(adv_data, [])
	decision := intake.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-009" in decision.policy_ids
}

# POL-010: 민감 작업이 확인 대상으로 분류되지 않았으면 호출 차단.
test_adv_pol_010_call_unclassified_sensitive if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/request/operation", "value": "delete"}, {"op": "add", "path": "/facts/confirmation", "value": {"server_id": "s1", "tool": "read", "operation": "delete", "target": "d1", "recipient": "partner", "arguments_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "confirmed_by": "alice", "reserved_for": "r1", "used": false, "expires_ns": 20003600000000000}}])
	d := json.patch(adv_data, [{"op": "remove", "path": "/servers/s1/tools/read/requires_confirmation"}])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-010" in decision.policy_ids
}

# POL-010: 삭제 기능은 사용자 확인 대상에 반드시 포함.
test_adv_pol_010_intake_confirmation_string if {
	i := json.patch(adv_intake_input, [{"op": "add", "path": "/application/business_scope/operations", "value": ["delete"]}, {"op": "add", "path": "/application/tools/0/declared_effect", "value": "delete"}, {"op": "add", "path": "/application/tools/0/trial_results/0/observed_effect", "value": "delete"}, {"op": "add", "path": "/application/tools/0/requires_confirmation", "value": "true"}])
	d := json.patch(adv_data, [])
	decision := intake.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-010" in decision.policy_ids
}

# POL-011: 기능 기록 false는 기능·자료·권한·승인 기준 문서가 아님.
test_adv_pol_011_false_requirement if {
	i := json.patch(adv_intake_input, [{"op": "add", "path": "/application/requirements/functions", "value": false}])
	d := json.patch(adv_data, [])
	decision := intake.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-011" in decision.policy_ids
}

# POL-011: 네 가지 필수 도입 항목 중 하나가 없으면 도입 차단.
test_adv_pol_011_missing_requirement if {
	i := json.patch(adv_intake_input, [{"op": "remove", "path": "/application/requirements/acceptance_criteria"}])
	d := json.patch(adv_data, [])
	decision := intake.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-011" in decision.policy_ids
}

# POL-012: 서버 신원을 확인할 수 없으면 연결 거부.
test_adv_pol_012_null_identity_equals_null if {
	i := json.patch(adv_connect_input, [{"op": "add", "path": "/connection/identity", "value": null}])
	d := json.patch(adv_data, [{"op": "add", "path": "/servers/s1/identity", "value": null}])
	decision := connect.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-012" in decision.policy_ids
}

# POL-012: 서버 승인 종료일 정각에는 승인 기간이 유효하지 않음.
test_adv_pol_012_server_approval_at_expiry if {
	i := json.patch(adv_connect_input, [])
	d := json.patch(adv_data, [{"op": "add", "path": "/servers/s1/approval/not_after_ns", "value": 20000000000000000}])
	decision := connect.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-012" in decision.policy_ids
}

# POL-013: 예외 종료일을 확인할 수 없으면 Tool 실행 차단.
test_adv_pol_013_call_exception_missing_end if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/facts/approval/basis", "value": "exception"}])
	d := json.patch(adv_data, [{"op": "add", "path": "/exceptions", "value": [{"policy_id": "POL-013", "target": "s1", "scope": ["read"], "approved_by": "reviewer", "approved_by_role": "security_admin", "status": "approved", "not_before_ns": 19913600000000000}]}])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-013" in decision.policy_ids
}

# POL-013: 예외 종료일 정각에는 예외에 근거한 연결 차단.
test_adv_pol_013_connection_exception_at_expiry if {
	i := json.patch(adv_connect_input, [{"op": "add", "path": "/connection/approval/basis", "value": "exception"}])
	d := json.patch(adv_data, [{"op": "add", "path": "/exceptions", "value": [{"policy_id": "POL-013", "target": "s1", "scope": ["connect"], "approved_by": "reviewer", "approved_by_role": "security_admin", "status": "approved", "not_before_ns": 19913600000000000, "not_after_ns": 20000000000000000}]}])
	decision := connect.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-013" in decision.policy_ids
}

# POL-014: 다른 서버의 승인 기록으로 현재 연결 승인을 활성화할 수 없음.
test_adv_pol_014_approval_for_other_server if {
	i := json.patch(adv_connect_input, [{"op": "add", "path": "/connection/stage", "value": "approve"}, {"op": "add", "path": "/approval/server_id", "value": "s2"}])
	d := json.patch(adv_data, [])
	decision := connect.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-014" in decision.policy_ids
}

# POL-014: 연결 승인 목적 기록 누락은 승인 상태 활성화 차단.
test_adv_pol_014_missing_approval_purpose if {
	i := json.patch(adv_connect_input, [{"op": "add", "path": "/connection/stage", "value": "approve"}, {"op": "remove", "path": "/approval/purpose"}])
	d := json.patch(adv_data, [])
	decision := connect.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-014" in decision.policy_ids
}

# POL-015: 서버가 다르면 같은 Tool 이름도 승인 조합이 아님.
test_adv_pol_015_other_server_same_name if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/request/server_id", "value": "s2"}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-015" in decision.policy_ids
}

# POL-015: 정확히 일치하지 않는 Tool 이름은 호출 차단.
test_adv_pol_015_tool_case_changed if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/request/tool", "value": "READ"}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-015" in decision.policy_ids
}

# POL-016: 만료 토큰은 인증 거부.
test_adv_pol_016_token_at_expiry if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/facts/token/expires_ns", "value": 20000000000000000}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-016" in decision.policy_ids
}

# POL-016: 문자열 true는 검증된 토큰 유효성이 아님.
test_adv_pol_016_token_valid_string if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/facts/token/valid", "value": "true"}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-016" in decision.policy_ids
}

# POL-019: 인증 서버 주소뿐 아니라 ID도 승인 목록과 일치해야 함.
test_adv_pol_019_auth_server_other_id if {
	i := json.patch(adv_connect_input, [{"op": "add", "path": "/connection/stage", "value": "oauth"}, {"op": "add", "path": "/connection/auth_server/id", "value": "other-auth"}])
	d := json.patch(adv_data, [])
	decision := connect.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-019" in decision.policy_ids
}

# POL-019: 새 인증 서버는 신원·주소 등록 전 인증 요청 차단.
test_adv_pol_019_exception_does_not_bind_auth_id if {
	i := json.patch(adv_connect_input, [{"op": "add", "path": "/connection/stage", "value": "oauth"}, {"op": "add", "path": "/connection/auth_server/id", "value": "other-auth"}])
	d := json.patch(adv_data, [{"op": "add", "path": "/exceptions", "value": [{"policy_id": "POL-019", "target": "s1", "scope": ["https://auth.example"], "approved_by": "reviewer", "approved_by_role": "security_admin", "status": "approved", "not_before_ns": 19913600000000000, "not_after_ns": 20086400000000000, "auth_server_id": "auth"}]}])
	decision := connect.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-019" in decision.policy_ids
}

# POL-022: 미승인 외부 주소의 인증 서버 정보 조회 차단.
test_adv_pol_022_metadata_unapproved_host if {
	i := json.patch(adv_connect_input, [{"op": "add", "path": "/connection/stage", "value": "oauth"}, {"op": "add", "path": "/connection/metadata/request_host", "value": "other.example"}])
	d := json.patch(adv_data, [])
	decision := connect.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-022" in decision.policy_ids
}

# POL-022: 실제 정보 조회 목적지를 확인할 수 없으면 조회 차단.
test_adv_pol_022_missing_metadata_host if {
	i := json.patch(adv_connect_input, [{"op": "add", "path": "/connection/stage", "value": "oauth"}, {"op": "remove", "path": "/connection/metadata/request_host"}])
	d := json.patch(adv_data, [])
	decision := connect.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-022" in decision.policy_ids
}

# POL-023: IPv6 루프백도 내부 보호 주소이므로 접속 차단.
test_adv_pol_023_ipv6_loopback if {
	i := json.patch(adv_connect_input, [{"op": "add", "path": "/connection/stage", "value": "oauth"}, {"op": "add", "path": "/connection/metadata/resolved_ips", "value": ["::1"]}])
	d := json.patch(adv_data, [])
	decision := connect.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-023" in decision.policy_ids
}

# POL-023: DNS 해석 IP를 확인할 수 없으면 최종 접속 허용 불가.
test_adv_pol_023_missing_resolved_ips if {
	i := json.patch(adv_connect_input, [{"op": "add", "path": "/connection/stage", "value": "oauth"}, {"op": "remove", "path": "/connection/metadata/resolved_ips"}])
	d := json.patch(adv_data, [])
	decision := connect.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-023" in decision.policy_ids
}

# POL-024: 평문 노출 검사 결과 확인 불가이면 배포·기록 차단.
test_adv_pol_024_null_plaintext_scan_result if {
	i := json.patch(adv_ops_input, [{"op": "add", "path": "/servers/0/config_scan/plaintext_secrets", "value": null}])
	d := json.patch(adv_data, [])
	vs := ops.violations with input as i with data.pol as d
	some v in vs
	v.policy_id == "POL-024"
	v.server == "s1"
	v.action == "block_deploy"
}

# POL-024: 평문이 없어도 인증정보가 승인 보관소에 있어야 사용.
test_adv_pol_024_unapproved_secret_storage if {
	i := json.patch(adv_ops_input, [{"op": "add", "path": "/servers/0/config_scan/storage_approved", "value": false}])
	d := json.patch(adv_data, [])
	vs := ops.violations with input as i with data.pol as d
	some v in vs
	v.policy_id == "POL-024"
	v.server == "s1"
	v.action == "block_deploy"
}

# POL-025: 다른 서버에 귀속된 인증정보는 사용 차단.
test_adv_pol_025_credential_other_server if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/facts/credential/bound_server", "value": "s2"}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-025" in decision.policy_ids
}

# POL-025: 문자열 false로 인증정보 미사용 검증을 대신할 수 없음.
test_adv_pol_025_credential_used_string if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/facts/credential/used", "value": "false"}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-025" in decision.policy_ids
}

# POL-026: 실제 요청 scope 확인 불가이면 승인 범위 대조 실패.
test_adv_pol_026_missing_requested_scopes if {
	i := json.patch(adv_connect_input, [{"op": "add", "path": "/connection/stage", "value": "oauth"}, {"op": "remove", "path": "/connection/requested_scopes"}])
	d := json.patch(adv_data, [])
	decision := connect.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-026" in decision.policy_ids
}

# POL-026: 승인 목록에 없는 대문자 scope는 승인 범위 밖.
test_adv_pol_026_scope_case_changed if {
	i := json.patch(adv_connect_input, [{"op": "add", "path": "/connection/stage", "value": "oauth"}, {"op": "add", "path": "/connection/requested_scopes", "value": ["READ"]}])
	d := json.patch(adv_data, [])
	decision := connect.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-026" in decision.policy_ids
}

# POL-029: 빈 객체는 승인된 로컬 실행 파일·설정이 아님.
test_adv_pol_029_empty_local_launch_registration if {
	i := json.patch(adv_connect_input, [{"op": "add", "path": "/connection/kind", "value": "local"}])
	d := json.patch(adv_data, [{"op": "add", "path": "/servers/s1/launch", "value": {}}])
	decision := connect.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-029" in decision.policy_ids
}

# POL-029: 연결 방식을 모르면 HTTPS 또는 승인 로컬 실행 검증 불가.
test_adv_pol_029_unknown_connection_kind if {
	i := json.patch(adv_connect_input, [{"op": "remove", "path": "/connection/kind"}])
	d := json.patch(adv_data, [])
	decision := connect.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-029" in decision.policy_ids
}

# POL-031: 빈 해시끼리의 일치는 승인 실행 파일 확인이 아님.
test_adv_pol_031_empty_launch_hashes if {
	i := json.patch(adv_connect_input, [{"op": "add", "path": "/connection/stage", "value": "launch"}, {"op": "add", "path": "/connection/kind", "value": "local"}, {"op": "add", "path": "/connection/launch/sha256", "value": ""}])
	d := json.patch(adv_data, [{"op": "add", "path": "/servers/s1/launch/sha256", "value": ""}])
	decision := connect.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-031" in decision.policy_ids
}

# POL-031: 실제 환경 설정 누락이면 승인 시작값과 대조 불가.
test_adv_pol_031_missing_launch_env if {
	i := json.patch(adv_connect_input, [{"op": "add", "path": "/connection/stage", "value": "launch"}, {"op": "add", "path": "/connection/kind", "value": "local"}, {"op": "remove", "path": "/connection/launch/env"}])
	d := json.patch(adv_data, [])
	decision := connect.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-031" in decision.policy_ids
}

# POL-032: 다른 서버에 대한 동의는 현재 연결에 재사용 불가.
test_adv_pol_032_consent_other_server if {
	i := json.patch(adv_connect_input, [{"op": "add", "path": "/connection/consent/server_id", "value": "s2"}])
	d := json.patch(adv_data, [])
	decision := connect.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-032" in decision.policy_ids
}

# POL-032: 제공자·주소·기능이 표시되지 않았다면 동의 진행 불가.
test_adv_pol_032_false_display_fields if {
	i := json.patch(adv_connect_input, [{"op": "add", "path": "/connection/consent/shown", "value": {"provider": false, "address": false, "functions": false}}])
	d := json.patch(adv_data, [])
	decision := connect.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-032" in decision.policy_ids
}

# POL-033: 동의 기간 종료일 정각에 이전 동의 재사용 차단.
test_adv_pol_033_consent_at_expiry if {
	i := json.patch(adv_connect_input, [{"op": "add", "path": "/connection/consent/not_after_ns", "value": 20000000000000000}])
	d := json.patch(adv_data, [])
	decision := connect.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-033" in decision.policy_ids
}

# POL-033: 다른 사용자의 서버 연결 동의 재사용 차단.
test_adv_pol_033_consent_other_user if {
	i := json.patch(adv_connect_input, [{"op": "add", "path": "/connection/consent/user", "value": "bob"}])
	d := json.patch(adv_data, [])
	decision := connect.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-033" in decision.policy_ids
}

# POL-034: Agent가 현재 위임 조합과 다르면 실행 차단.
test_adv_pol_034_delegation_other_agent if {
	i := json.patch(adv_call_input, [])
	d := json.patch(adv_data, [{"op": "add", "path": "/delegations", "value": [{"user": "alice", "agent": "a2", "server_id": "s1", "tool": "read", "data_class": "internal", "operation": "read", "not_after_ns": 20086400000000000}]}])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-034" in decision.policy_ids
}

# POL-034: 새 위임 범위는 서버·Tool·자료·작업 모두 승인돼야 함.
test_adv_pol_034_exception_unbound_tool_operation if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/request/operation", "value": "delete"}, {"op": "add", "path": "/facts/confirmation", "value": {"server_id": "s1", "tool": "read", "operation": "delete", "target": "d1", "recipient": "partner", "arguments_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "confirmed_by": "alice", "reserved_for": "r1", "used": false, "expires_ns": 20003600000000000}}])
	d := json.patch(adv_data, [{"op": "add", "path": "/delegations", "value": []}, {"op": "add", "path": "/exceptions", "value": [{"policy_id": "POL-034", "target": "alice", "scope": ["a1"], "approved_by": "reviewer", "approved_by_role": "data_owner", "status": "approved", "not_before_ns": 19913600000000000, "not_after_ns": 20086400000000000, "operations": ["read"]}]}])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-034" in decision.policy_ids
}

# POL-035: 이전 호출의 권한 조회 결과를 재사용할 수 없음.
test_adv_pol_035_lookup_for_previous_request if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/facts/permission_lookup/request_id", "value": "r0"}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-035" in decision.policy_ids
}

# POL-035: 권한표 조회 결과가 없으면 현재 호출 실행 차단.
test_adv_pol_035_missing_permission_lookup if {
	i := json.patch(adv_call_input, [{"op": "remove", "path": "/facts/permission_lookup"}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-035" in decision.policy_ids
}

# POL-036: 문서 단위 승인 기간 만료 시 호출 차단.
test_adv_pol_036_document_grant_at_expiry if {
	i := json.patch(adv_call_input, [])
	d := json.patch(adv_data, [{"op": "add", "path": "/document_grants/0/not_after_ns", "value": 20000000000000000}])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-036" in decision.policy_ids
}

# POL-036: 대상 문서가 불명확하면 권한표 보완 전 호출 차단.
test_adv_pol_036_missing_document_id if {
	i := json.patch(adv_call_input, [{"op": "remove", "path": "/request/target/doc_id"}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-036" in decision.policy_ids
}

# POL-037: 외부 자료를 권한 변경 입력으로 쓰는 흐름 차단.
test_adv_pol_037_external_permission_change if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/request/intent", "value": "permission_change"}, {"op": "add", "path": "/facts/provenance/external_content", "value": true}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-037" in decision.policy_ids
}

# POL-037: 외부 Tool 결과가 권한 변경 채널로 전달되면 차단.
test_adv_pol_037_response_into_authority_channel if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/request/stage", "value": "response"}, {"op": "add", "path": "/request/intent", "value": "permission_change"}, {"op": "add", "path": "/facts/provenance/external_content", "value": true}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-037" in decision.policy_ids
}

# POL-038: 탐지 결과가 없는 입력은 금지 정보 제거를 입증하지 못함.
test_adv_pol_038_missing_inspection_arrays if {
	i := json.patch(adv_call_input, [{"op": "remove", "path": "/facts/inspection/secrets"}, {"op": "remove", "path": "/facts/inspection/personal_data"}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-038" in decision.policy_ids
}

# POL-038: 남아 있는 토큰을 문자열 결과라는 이유로 전송할 수 없음.
test_adv_pol_038_secret_string_not_array if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/facts/inspection/secrets", "value": "token-present"}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-038" in decision.policy_ids
}

# POL-040: 실제 최종 IP가 형식 오류이면 승인 수신지 검증 실패.
test_adv_pol_040_malformed_ip if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/request/operation", "value": "external_send"}, {"op": "add", "path": "/facts/confirmation", "value": {"server_id": "s1", "tool": "read", "operation": "external_send", "target": "d1", "recipient": "partner", "arguments_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "confirmed_by": "alice", "reserved_for": "r1", "used": false, "expires_ns": 20003600000000000}}, {"op": "add", "path": "/facts/egress/resolved_ips", "value": ["not-an-ip"]}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-040" in decision.policy_ids
}

# POL-040: 호스트가 같아도 IP가 승인 허용 범위 밖이면 전송 차단.
test_adv_pol_040_public_ip_outside_approved_range if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/request/operation", "value": "external_send"}, {"op": "add", "path": "/facts/confirmation", "value": {"server_id": "s1", "tool": "read", "operation": "external_send", "target": "d1", "recipient": "partner", "arguments_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "confirmed_by": "alice", "reserved_for": "r1", "used": false, "expires_ns": 20003600000000000}}, {"op": "add", "path": "/facts/egress/resolved_ips", "value": ["1.1.1.1"]}])
	d := json.patch(adv_data, [{"op": "add", "path": "/servers/s1/tools/read/egress_ip_ranges", "value": ["8.8.8.0/24"]}])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-040" in decision.policy_ids
}

# POL-041: 자료 소유 부서의 전송 예외도 승인된 목적 조합으로 한정.
test_adv_pol_041_exception_unbound_purpose if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/request/operation", "value": "external_send"}, {"op": "add", "path": "/facts/confirmation", "value": {"server_id": "s1", "tool": "read", "operation": "external_send", "target": "d1", "recipient": "partner", "arguments_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "confirmed_by": "alice", "reserved_for": "r1", "used": false, "expires_ns": 20003600000000000}}, {"op": "add", "path": "/request/purpose", "value": "unapproved-purpose"}])
	d := json.patch(adv_data, [{"op": "add", "path": "/exceptions", "value": [{"policy_id": "POL-041", "target": "internal", "scope": ["partner"], "approved_by": "reviewer", "approved_by_role": "data_owner", "status": "approved", "not_before_ns": 19913600000000000, "not_after_ns": 20086400000000000, "purpose": "report"}]}])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-041" in decision.policy_ids
}

# POL-041: 자료·수신자가 같아도 목적이 승인 조합 밖이면 차단.
test_adv_pol_041_unapproved_transfer_purpose if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/request/operation", "value": "external_send"}, {"op": "add", "path": "/facts/confirmation", "value": {"server_id": "s1", "tool": "read", "operation": "external_send", "target": "d1", "recipient": "partner", "arguments_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "confirmed_by": "alice", "reserved_for": "r1", "used": false, "expires_ns": 20003600000000000}}, {"op": "add", "path": "/request/purpose", "value": "unapproved-purpose"}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-041" in decision.policy_ids
}

# POL-042: 형식 오류 요청 경로로 허용 폴더 밖 파일 검사를 생략할 수 없음.
test_adv_pol_042_null_requested_path_bypass if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/request/target/path", "value": null}, {"op": "add", "path": "/facts/path/resolved", "value": "/etc/passwd"}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-042" in decision.policy_ids
}

# POL-042: 승인 폴더 /srv/data와 /srv/data-x는 다른 범위.
test_adv_pol_042_root_prefix_confusion if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/facts/path/resolved", "value": "/srv/data-x/file"}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-042" in decision.policy_ids
}

# POL-043: 다른 사용자의 실제 파일 권한을 현재 사용자에게 적용 불가.
test_adv_pol_043_acl_for_other_user if {
	i := json.patch(adv_resource_input, [{"op": "add", "path": "/request/stage", "value": "resource_read"}, {"op": "add", "path": "/facts/acl/user", "value": "bob"}])
	d := json.patch(adv_data, [])
	decision := resource.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-043" in decision.policy_ids
}

# POL-043: 실제 파일 ID 판정 실패는 Resource 반환 차단.
test_adv_pol_043_missing_resolved_resource_id if {
	i := json.patch(adv_resource_input, [{"op": "add", "path": "/request/stage", "value": "resource_read"}, {"op": "remove", "path": "/facts/resource/resolved_id"}])
	d := json.patch(adv_data, [])
	decision := resource.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-043" in decision.policy_ids
}

# POL-044: 문자열 false는 서버 간 인증정보 부재 검증이 아님.
test_adv_pol_044_credential_flag_string_false if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/facts/data/contains_credential", "value": "false"}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-044" in decision.policy_ids
}

# POL-044: 출발 서버의 잘못된 타입으로 서버쌍 검사를 생략할 수 없음.
test_adv_pol_044_non_string_source_server if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/request/source_server", "value": ["s0"]}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-044" in decision.policy_ids
}

# POL-046: 문자열 true는 승인 명령·인자 검증 결과가 아님.
test_adv_pol_046_arguments_validated_string if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/facts/arguments_validated", "value": "true"}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-046" in decision.policy_ids
}

# POL-046: 명령·API 유형 누락으로 미검증 임의 실행을 허용할 수 없음.
test_adv_pol_046_missing_tool_kind_bypass if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/request/operation", "value": "execute"}, {"op": "add", "path": "/facts/arguments_validated", "value": false}])
	d := json.patch(adv_data, [{"op": "remove", "path": "/servers/s1/tools/read/kind"}])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-046" in decision.policy_ids
}

# POL-047: IPv6 사설 주소는 허용 호스트 뒤에서도 접속 차단.
test_adv_pol_047_private_ipv6 if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/facts/egress/resolved_ips", "value": ["fd00::1"]}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-047" in decision.policy_ids
}

# POL-047: 승인 최종 호스트의 공인 IPv6는 나머지 조건 충족 시 접속 허용.
test_adv_pol_047_public_ipv6_allowed if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/facts/egress/resolved_ips", "value": ["2606:4700:4700::1111"]}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "ALLOW"
}

# POL-048: 미정의 항목 목록 null은 숨은 항목 부재 검사 결과가 아님.
test_adv_pol_048_null_undeclared_fields if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/facts/schema/undeclared_fields", "value": null}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-048" in decision.policy_ids
}

# POL-048: 문자열 true는 입력 스키마 적합 판정이 아님.
test_adv_pol_048_schema_valid_string if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/facts/schema/valid", "value": "true"}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-048" in decision.policy_ids
}

# POL-049: 문서 수와 크기가 승인 상한과 같으면 반환 허용.
test_adv_pol_049_exact_result_limit if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/request/stage", "value": "response"}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "ALLOW"
}

# POL-049: 음수 문서 수는 실제 반환 건수를 확인한 값이 아님.
test_adv_pol_049_negative_result_count if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/request/stage", "value": "response"}, {"op": "add", "path": "/response/items", "value": -1}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-049" in decision.policy_ids
}

# POL-049: 문서 수가 승인 상한보다 1 많으면 결과 제한 또는 거부.
test_adv_pol_049_one_item_over_limit if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/request/stage", "value": "response"}, {"op": "add", "path": "/response/items", "value": 11}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "RESTRICT"
	"POL-049" in decision.policy_ids
}

# POL-050: 시간창 조회량이 승인 한도와 같고 차단 패턴이 없으면 계속 조회.
test_adv_pol_050_exact_window_limit if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/facts/usage/window_documents", "value": 10}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "ALLOW"
}

# POL-050: 시간창 조회량이 승인 한도보다 1 많으면 추가 조회 중단.
test_adv_pol_050_one_document_over_window if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/facts/usage/window_documents", "value": 11}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-050" in decision.policy_ids
}

# POL-051: 다른 문서에 대한 사용자 권한으로 현재 문서를 열 수 없음.
test_adv_pol_051_acl_for_other_document if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/facts/server_account/used", "value": true}, {"op": "add", "path": "/facts/acl/doc_id", "value": "d2"}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-051" in decision.policy_ids
}

# POL-051: 서버 계정 사용 시 사용자 문서 권한 확인 불가이면 호출 차단.
test_adv_pol_051_missing_user_acl if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/facts/server_account/used", "value": true}, {"op": "remove", "path": "/facts/acl/user_can"}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-051" in decision.policy_ids
}

# POL-052: 자료 등급이 같아도 서버 계정의 승인 문서 범위 밖이면 차단.
test_adv_pol_052_server_account_other_document if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/facts/server_account/used", "value": true}, {"op": "add", "path": "/request/target/doc_id", "value": "d2"}])
	d := json.patch(adv_data, [{"op": "add", "path": "/document_grants/0/doc_id", "value": "d2"}])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-052" in decision.policy_ids
}

# POL-052: 서버 계정의 승인 작업 범위 밖 접근 차단.
test_adv_pol_052_server_account_unapproved_operation if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/facts/server_account/used", "value": true}])
	d := json.patch(adv_data, [{"op": "add", "path": "/server_accounts/s1/operations", "value": ["write"]}])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-052" in decision.policy_ids
}

# POL-053: 확인 화면의 작업 대상과 실제 호출 대상이 다르면 차단.
test_adv_pol_053_displayed_target_changed if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/request/operation", "value": "delete"}, {"op": "add", "path": "/facts/confirmation", "value": {"server_id": "s1", "tool": "read", "operation": "delete", "target": "d1", "recipient": "partner", "arguments_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "confirmed_by": "alice", "reserved_for": "r1", "used": false, "expires_ns": 20003600000000000}}, {"op": "add", "path": "/facts/confirmation/target", "value": "d2"}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-053" in decision.policy_ids
}

# POL-053: 삭제 작업의 사용자 확인이 없으면 본인 확인 전 실행 중단.
test_adv_pol_053_no_user_confirmation if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/request/operation", "value": "delete"}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "CONFIRM"
	"POL-053" in decision.policy_ids
}

# POL-054: 사용한 확인값은 작업값이 같아도 재사용 차단.
test_adv_pol_054_confirmation_already_used if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/request/operation", "value": "delete"}, {"op": "add", "path": "/facts/confirmation", "value": {"server_id": "s1", "tool": "read", "operation": "delete", "target": "d1", "recipient": "partner", "arguments_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "confirmed_by": "alice", "reserved_for": "r1", "used": false, "expires_ns": 20003600000000000}}, {"op": "add", "path": "/facts/confirmation/used", "value": true}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-054" in decision.policy_ids
}

# POL-054: 확인값 만료 시각 정각에는 한 호출 허용도 불가.
test_adv_pol_054_confirmation_at_expiry if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/request/operation", "value": "delete"}, {"op": "add", "path": "/facts/confirmation", "value": {"server_id": "s1", "tool": "read", "operation": "delete", "target": "d1", "recipient": "partner", "arguments_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "confirmed_by": "alice", "reserved_for": "r1", "used": false, "expires_ns": 20003600000000000}}, {"op": "add", "path": "/facts/confirmation/expires_ns", "value": 20000000000000000}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-054" in decision.policy_ids
}

# POL-054: 요청 사용자 본인이 아닌 관리자의 확인은 사용 불가.
test_adv_pol_054_other_confirming_user if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/request/operation", "value": "delete"}, {"op": "add", "path": "/facts/confirmation", "value": {"server_id": "s1", "tool": "read", "operation": "delete", "target": "d1", "recipient": "partner", "arguments_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "confirmed_by": "alice", "reserved_for": "r1", "used": false, "expires_ns": 20003600000000000}}, {"op": "add", "path": "/facts/confirmation/confirmed_by", "value": "bob"}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-054" in decision.policy_ids
}

# POL-056: 호출량과 동시 실행 수가 각각 상한과 같으면 수용.
test_adv_pol_056_exact_rate_limits if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/facts/usage/user", "value": {"window_calls": 10, "concurrent": 2}}, {"op": "add", "path": "/facts/usage/agent", "value": {"window_calls": 10, "concurrent": 2}}, {"op": "add", "path": "/facts/usage/tool", "value": {"window_calls": 10, "concurrent": 2}}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "ALLOW"
}

# POL-056: Agent 단위 호출량이 1 초과해도 요청 거부.
test_adv_pol_056_one_agent_call_over_limit if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/facts/usage/agent/window_calls", "value": 11}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-056" in decision.policy_ids
}

# POL-056: 문자열 상한은 승인된 수치 상한으로 검증할 수 없음.
test_adv_pol_056_string_rate_limits if {
	i := json.patch(adv_call_input, [])
	d := json.patch(adv_data, [{"op": "add", "path": "/rate_limits/tool", "value": {"window_calls": "10", "concurrent": "2"}}])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-056" in decision.policy_ids
}

# POL-058: 어느 감사 저장소에도 기록할 수 없으면 호출 차단.
test_adv_pol_058_no_writable_audit_store if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/facts/audit", "value": {"central_writable": false, "buffer_writable": "true"}}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-058" in decision.policy_ids
}

# POL-058: 쓰기 가능 표시만 있고 현재 호출 기록이 실패했다면 처리 불가.
test_adv_pol_058_writable_but_record_failed if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/facts/audit/recorded", "value": false}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-058" in decision.policy_ids
}

# POL-063: 실제 Tool 정의 확인 불가이면 승인 정의와 대조 실패.
test_adv_pol_063_call_missing_observed_hash if {
	i := json.patch(adv_call_input, [{"op": "remove", "path": "/facts/catalog/observed_contract_sha256"}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-063" in decision.policy_ids
}

# POL-063: 운영 Tool 정의가 변경되면 기존 승인값과 불일치하는 사용 차단.
test_adv_pol_063_ops_changed_hash_must_block if {
	i := json.patch(adv_ops_input, [{"op": "add", "path": "/servers/0/observed_tools/0/contract_sha256", "value": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"}])
	d := json.patch(adv_data, [])
	vs := ops.violations with input as i with data.pol as d
	some v in vs
	v.policy_id == "POL-063"
	v.server == "s1"
	v.action == "block"
}

# POL-063: 이름 확인 불가 Tool은 승인 정의 확인 전 사용 차단.
test_adv_pol_063_ops_tool_missing_name if {
	i := json.patch(adv_ops_input, [{"op": "add", "path": "/servers/0/observed_tools", "value": [{"contract_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}]}])
	d := json.patch(adv_data, [])
	vs := ops.violations with input as i with data.pol as d
	some v in vs
	v.policy_id == "POL-063"
	v.server == "s1"
	v.action == "block"
}

# POL-064: 다른 사용자 소유 캐시는 Tool 목록으로 노출 불가.
test_adv_pol_064_cache_owned_by_other_user if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/request/stage", "value": "list"}, {"op": "add", "path": "/response/cached", "value": true}, {"op": "add", "path": "/response/cache_owner", "value": "bob"}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-064" in decision.policy_ids
}

# POL-064: 현재 권한 목록 확인 불가 시 저장된 Tool 목록 재사용 차단.
test_adv_pol_064_missing_permitted_tools if {
	i := json.patch(adv_call_input, [{"op": "add", "path": "/request/stage", "value": "list"}, {"op": "remove", "path": "/facts/permitted_tools"}])
	d := json.patch(adv_data, [])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-064" in decision.policy_ids
}

# POL-065: 삭제 Resource는 현재 권한 목록에 남아 있어도 표시 차단.
test_adv_pol_065_deleted_resource_in_list if {
	i := json.patch(adv_resource_input, [{"op": "add", "path": "/request/stage", "value": "resource_list"}, {"op": "add", "path": "/facts/deleted_resources", "value": ["d1"]}])
	d := json.patch(adv_data, [])
	decision := resource.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-065" in decision.policy_ids
}

# POL-065: 삭제 상태를 확인할 수 없는 목록은 변경 후 유효성을 입증하지 못함.
test_adv_pol_065_missing_deletion_snapshot if {
	i := json.patch(adv_resource_input, [{"op": "add", "path": "/request/stage", "value": "resource_list"}, {"op": "remove", "path": "/facts/deleted_resources"}])
	d := json.patch(adv_data, [])
	decision := resource.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-065" in decision.policy_ids
}

# POL-066: 문자열 true는 승인 변경 범위 확인 결과가 아님.
test_adv_pol_066_scope_verified_string if {
	i := json.patch(adv_resource_input, [{"op": "add", "path": "/request/stage", "value": "resource_update"}, {"op": "add", "path": "/facts/change/within_approved_scope", "value": "true"}])
	d := json.patch(adv_data, [])
	decision := resource.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-066" in decision.policy_ids
}

# POL-066: 승인되지 않은 Resource 출처를 자동 반영할 수 없음.
test_adv_pol_066_unapproved_resource_source if {
	i := json.patch(adv_resource_input, [{"op": "add", "path": "/request/stage", "value": "resource_update"}, {"op": "add", "path": "/facts/change/source", "value": "other-source"}])
	d := json.patch(adv_data, [])
	decision := resource.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-066" in decision.policy_ids
}

# POL-067: 배열끼리 같은 값이어도 승인 템플릿 해시 검증이 아님.
test_adv_pol_067_non_string_template_hash if {
	i := json.patch(adv_resource_input, [{"op": "add", "path": "/facts/prompt_sha256", "value": []}])
	d := json.patch(adv_data, [{"op": "add", "path": "/servers/s1/prompts/summary/sha256", "value": []}])
	decision := resource.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-067" in decision.policy_ids
}

# POL-067: 승인 목록에 없는 Prompt 변경본은 재심사 전 사용 차단.
test_adv_pol_067_unapproved_template if {
	i := json.patch(adv_resource_input, [{"op": "add", "path": "/request/prompt", "value": "other-template"}])
	d := json.patch(adv_data, [])
	decision := resource.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-067" in decision.policy_ids
}

# POL-068: 실제 패키지 목록 null로 패키지 승인 대조를 생략할 수 없음.
test_adv_pol_068_intake_null_packages if {
	i := json.patch(adv_intake_input, [{"op": "add", "path": "/application/packages", "value": null}])
	d := json.patch(adv_data, [])
	decision := intake.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-068" in decision.policy_ids
}

# POL-068: 승인 패키지 항목 종료일 정각에는 실행 허용 불가.
test_adv_pol_068_ops_expired_package_allowlist if {
	i := json.patch(adv_ops_input, [{"op": "add", "path": "/event", "value": "package_change"}])
	d := json.patch(adv_data, [{"op": "add", "path": "/package_allowlist/0/not_after_ns", "value": 20000000000000000}])
	vs := ops.violations with input as i with data.pol as d
	some v in vs
	v.policy_id == "POL-068"
	v.server == "s1"
	v.action == "block"
}

# POL-068: 식별되지 않은 업데이트 패키지는 승인 제공처·버전 대조 불가.
test_adv_pol_068_ops_package_missing_name if {
	i := json.patch(adv_ops_input, [{"op": "add", "path": "/event", "value": "update"}, {"op": "remove", "path": "/servers/0/packages/0/name"}])
	d := json.patch(adv_data, [])
	vs := ops.violations with input as i with data.pol as d
	some v in vs
	v.policy_id == "POL-068"
	v.server == "s1"
	v.action == "block"
}

# POL-069: 취약점 조회 목록 null이면 완료 대신 미확인 처리.
test_adv_pol_069_completed_with_null_inventory if {
	i := json.patch(adv_ops_input, [{"op": "add", "path": "/servers/0/vulnerabilities", "value": null}])
	d := json.patch(adv_data, [])
	vs := ops.violations with input as i with data.pol as d
	some v in vs
	v.policy_id == "POL-069"
	v.server == "s1"
	v.action == "mark_unverified"
}

# POL-069: 심각도 미지정 enum이면 필수 판단 정보 미확인.
test_adv_pol_069_unknown_severity if {
	i := json.patch(adv_ops_input, [{"op": "add", "path": "/servers/0/vulnerabilities", "value": [{"id": "CVE-TEST", "severity": "UNKNOWN", "exploited": true, "exposed": true, "affected_version": "1.0", "confirmed_ns": 19827200000000000, "patched": false, "compensating_control": {"verified": false}}]}])
	d := json.patch(adv_data, [])
	vs := ops.violations with input as i with data.pol as d
	some v in vs
	v.policy_id == "POL-069"
	v.server == "s1"
	v.action == "mark_unverified"
}

# POL-070: 실제 악용·외부 노출 치명이 48시간 기한에 도달하면 사용 차단.
test_adv_pol_070_critical_at_48h_deadline if {
	i := json.patch(adv_ops_input, [{"op": "add", "path": "/servers/0/vulnerabilities", "value": [{"id": "CVE-TEST", "severity": "critical", "exploited": true, "exposed": true, "affected_version": "1.0", "confirmed_ns": 19827200000000000, "patched": false, "compensating_control": {"verified": false}}]}])
	d := json.patch(adv_data, [])
	vs := ops.violations with input as i with data.pol as d
	some v in vs
	v.policy_id == "POL-070"
	v.server == "s1"
	v.action == "block"
}

# POL-070: 영향 확인 시각이 없으면 기한 판정 불가로 사용 차단.
test_adv_pol_070_missing_confirmation_time if {
	i := json.patch(adv_ops_input, [{"op": "add", "path": "/servers/0/vulnerabilities", "value": [{"id": "CVE-TEST", "severity": "critical", "exploited": true, "exposed": true, "affected_version": "1.0", "patched": false, "compensating_control": {"verified": false}}]}])
	d := json.patch(adv_data, [])
	vs := ops.violations with input as i with data.pol as d
	some v in vs
	v.policy_id == "POL-070"
	v.server == "s1"
	v.action == "block"
}

# POL-070: 48시간 기한 1초 전에는 기한 초과 차단을 아직 적용하지 않음.
test_adv_pol_070_one_second_before_critical_deadline if {
	i := json.patch(adv_ops_input, [{"op": "add", "path": "/servers/0/vulnerabilities", "value": [{"id": "CVE-TEST", "severity": "critical", "exploited": true, "exposed": true, "affected_version": "1.0", "confirmed_ns": 19827201000000000, "patched": false, "compensating_control": {"verified": false}}]}])
	d := json.patch(adv_data, [])
	decision := ops.decision with input as i with data.pol as d
	decision.effect == "ALLOW"
	vs := ops.violations with input as i with data.pol as d
	every v in vs {
		v.policy_id != "POL-070"
	}
}

# POL-070: 정기 변경일이 잘못된 타입이면 기한 내 운영을 입증할 수 없음.
test_adv_pol_070_string_scheduled_change_date if {
	i := json.patch(adv_ops_input, [{"op": "add", "path": "/servers/0/vulnerabilities", "value": [{"id": "CVE-TEST", "severity": "low", "exploited": true, "exposed": true, "affected_version": "1.0", "confirmed_ns": 19827200000000000, "patched": false, "compensating_control": {"verified": false}}]}, {"op": "add", "path": "/servers/0/scheduled_change_ns", "value": "tomorrow"}])
	d := json.patch(adv_data, [])
	vs := ops.violations with input as i with data.pol as d
	some v in vs
	v.policy_id == "POL-070"
	v.server == "s1"
	v.action == "block"
}

# POL-071: 빈 해시끼리 일치는 인스턴스 필수 설정 확인이 아님.
test_adv_pol_071_empty_baseline_hash if {
	i := json.patch(adv_ops_input, [{"op": "add", "path": "/servers/0/baseline_config_sha256", "value": ""}, {"op": "add", "path": "/servers/0/instances/0/config_sha256", "value": ""}])
	d := json.patch(adv_data, [])
	vs := ops.violations with input as i with data.pol as d
	some v in vs
	v.policy_id == "POL-071"
	v.server == "s1"
	v.action == "stop_traffic"
}

# POL-071: 인스턴스 관측 불가이면 승인 설정 확인 전 트래픽 투입 불가.
test_adv_pol_071_null_instances if {
	i := json.patch(adv_ops_input, [{"op": "add", "path": "/servers/0/instances", "value": null}])
	d := json.patch(adv_data, [])
	vs := ops.violations with input as i with data.pol as d
	some v in vs
	v.policy_id == "POL-071"
	v.server == "s1"
	v.action == "stop_traffic"
}

# POL-072: 차단 버전 목록이 잘못된 타입이면 차단 버전 복원 불가.
test_adv_pol_072_malformed_blocked_versions if {
	i := json.patch(adv_ops_input, [{"op": "add", "path": "/event", "value": "restore"}, {"op": "add", "path": "/servers/0/restore/version", "value": "0.1"}])
	d := json.patch(adv_data, [{"op": "add", "path": "/blocked_versions/s1", "value": "0.1"}])
	vs := ops.violations with input as i with data.pol as d
	some v in vs
	v.policy_id == "POL-072"
	v.server == "s1"
	v.action == "abort_restore"
}

# POL-072: 복원 승인 종료일 정각에는 유효한 복원 승인이 아님.
test_adv_pol_072_restore_approval_at_expiry if {
	i := json.patch(adv_ops_input, [{"op": "add", "path": "/event", "value": "restore"}, {"op": "add", "path": "/servers/0/restore/approval/not_after_ns", "value": 20000000000000000}])
	d := json.patch(adv_data, [])
	vs := ops.violations with input as i with data.pol as d
	some v in vs
	v.policy_id == "POL-072"
	v.server == "s1"
	v.action == "abort_restore"
}

# POL-073: 새 주소가 승인 등록부에 반영되기 전 연결 차단.
test_adv_pol_073_exception_without_registry_update if {
	i := json.patch(adv_connect_input, [{"op": "add", "path": "/connection/address", "value": "https://new.example/mcp"}])
	d := json.patch(adv_data, [{"op": "add", "path": "/exceptions", "value": [{"policy_id": "POL-073", "target": "s1", "scope": ["https://new.example/mcp"], "approved_by": "reviewer", "approved_by_role": "security_admin", "status": "approved", "not_before_ns": 19913600000000000, "not_after_ns": 20086400000000000}]}])
	decision := connect.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-073" in decision.policy_ids
}

# POL-073: 운영 서버 미승인 새 주소 연결 차단.
test_adv_pol_073_new_unregistered_address if {
	i := json.patch(adv_connect_input, [{"op": "add", "path": "/connection/address", "value": "https://new.example/mcp"}])
	d := json.patch(adv_data, [])
	decision := connect.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-073" in decision.policy_ids
}

# POL-074: 승인 목록 밖 새 하위 서비스 목적지는 전송 차단.
test_adv_pol_074_new_downstream_destination if {
	i := json.patch(adv_ops_input, [{"op": "add", "path": "/servers/0/downstream/observed", "value": ["https://other.example"]}])
	d := json.patch(adv_data, [])
	vs := ops.violations with input as i with data.pol as d
	some v in vs
	v.policy_id == "POL-074"
	v.server == "s1"
	v.action == "block_egress"
}

# POL-074: 하위 서비스 최종 주소 관측 불가이면 전송 차단.
test_adv_pol_074_null_downstream_observation if {
	i := json.patch(adv_ops_input, [{"op": "add", "path": "/servers/0/downstream/observed", "value": null}])
	d := json.patch(adv_data, [])
	vs := ops.violations with input as i with data.pol as d
	some v in vs
	v.policy_id == "POL-074"
	v.server == "s1"
	v.action == "block_egress"
}

# POL-075: 업데이트로 미승인 쓰기 권한 추가 시 실행 차단.
test_adv_pol_075_expanded_permission if {
	i := json.patch(adv_ops_input, [{"op": "add", "path": "/event", "value": "update"}, {"op": "add", "path": "/servers/0/observed_permissions", "value": ["read", "write"]}])
	d := json.patch(adv_data, [])
	vs := ops.violations with input as i with data.pol as d
	some v in vs
	v.policy_id == "POL-075"
	v.server == "s1"
	v.action == "block"
}

# POL-075: 업데이트 뒤 실제 실행 권한 확인 불가이면 사용 불가.
test_adv_pol_075_null_observed_permissions if {
	i := json.patch(adv_ops_input, [{"op": "add", "path": "/event", "value": "update"}, {"op": "add", "path": "/servers/0/observed_permissions", "value": null}])
	d := json.patch(adv_data, [])
	vs := ops.violations with input as i with data.pol as d
	some v in vs
	v.policy_id == "POL-075"
	v.server == "s1"
	v.action == "block"
}

# POL-076: 회수 확정 권한은 현재 사용 중이 아니어도 회수.
test_adv_pol_076_confirmed_revoke_not_in_use if {
	i := json.patch(adv_ops_input, [{"op": "add", "path": "/servers/0/revoke_confirmed", "value": ["write"]}, {"op": "add", "path": "/servers/0/in_use_permissions", "value": []}])
	d := json.patch(adv_data, [])
	vs := ops.violations with input as i with data.pol as d
	some v in vs
	v.policy_id == "POL-076"
	v.server == "s1"
	v.action == "revoke"
}

# POL-076: 회수 확정 시 사용 현황 조회가 실패해도 회수 유지.
test_adv_pol_076_missing_in_use_permissions if {
	i := json.patch(adv_ops_input, [{"op": "add", "path": "/servers/0/revoke_confirmed", "value": ["read"]}, {"op": "remove", "path": "/servers/0/in_use_permissions"}])
	d := json.patch(adv_data, [])
	vs := ops.violations with input as i with data.pol as d
	some v in vs
	v.policy_id == "POL-076"
	v.server == "s1"
	v.action == "revoke"
}

# POL-077: 재승인 전 확대된 Tool 권한 사용 차단.
test_adv_pol_077_expanded_tool_permission if {
	i := json.patch(adv_ops_input, [{"op": "add", "path": "/servers/0/tool_permissions/observed", "value": ["read", "admin"]}])
	d := json.patch(adv_data, [])
	vs := ops.violations with input as i with data.pol as d
	some v in vs
	v.policy_id == "POL-077"
	v.server == "s1"
	v.action == "block"
}

# POL-077: 관측 scope null이면 권한이 확대되지 않았음을 확인할 수 없음.
test_adv_pol_077_null_oauth_observation if {
	i := json.patch(adv_ops_input, [{"op": "add", "path": "/servers/0/oauth_scopes/observed", "value": null}])
	d := json.patch(adv_data, [])
	vs := ops.violations with input as i with data.pol as d
	some v in vs
	v.policy_id == "POL-077"
	v.server == "s1"
	v.action == "block"
}

# POL-081: 긴급 중지 서버는 차단 조건 해제·재승인 전 호출 차단.
test_adv_pol_081_call_suspended_server if {
	i := json.patch(adv_call_input, [])
	d := json.patch(adv_data, [{"op": "add", "path": "/servers/s1/state", "value": "suspended"}])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-081" in decision.policy_ids
}

# POL-081: 중지 기준에 맞는 확정 사고는 즉시 중지.
test_adv_pol_081_confirmed_critical_incident if {
	i := json.patch(adv_ops_input, [{"op": "add", "path": "/event", "value": "incident"}, {"op": "add", "path": "/servers/0/incidents", "value": [{"confirmed": true, "severity": "critical"}]}])
	d := json.patch(adv_data, [])
	vs := ops.violations with input as i with data.pol as d
	some v in vs
	v.policy_id == "POL-081"
	v.server == "s1"
	v.action == "stop"
}

# POL-082: 폐기 Tool의 신규 호출 즉시 차단.
test_adv_pol_082_call_retired_tool if {
	i := json.patch(adv_call_input, [])
	d := json.patch(adv_data, [{"op": "add", "path": "/servers/s1/tools/read/state", "value": "retired"}])
	decision := call.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-082" in decision.policy_ids
}

# POL-082: 폐기 서버의 신규 연결 즉시 차단.
test_adv_pol_082_connect_decommissioned_server if {
	i := json.patch(adv_connect_input, [])
	d := json.patch(adv_data, [{"op": "add", "path": "/servers/s1/state", "value": "decommissioned"}])
	decision := connect.decision with input as i with data.pol as d
	decision.effect == "DENY"
	"POL-082" in decision.policy_ids
}

# POL-088: 문자열 true는 새 자료 전송 중지 확인 결과가 아님.
test_adv_pol_088_string_transfer_blocked if {
	i := json.patch(adv_ops_input, [{"op": "add", "path": "/event", "value": "provider_termination"}, {"op": "add", "path": "/servers/0/provider_termination/new_transfer_blocked", "value": "true"}])
	d := json.patch(adv_data, [])
	vs := ops.violations with input as i with data.pol as d
	some v in vs
	v.policy_id == "POL-088"
	v.server == "s1"
	v.action == "block_transfer"
}

# POL-088: 삭제·반환 완료 증빙 미확인이면 완료 표시 불가.
test_adv_pol_088_unverified_deletion_evidence if {
	i := json.patch(adv_ops_input, [{"op": "add", "path": "/event", "value": "provider_termination"}, {"op": "add", "path": "/servers/0/provider_termination/evidence_verified", "value": false}])
	d := json.patch(adv_data, [])
	vs := ops.violations with input as i with data.pol as d
	some v in vs
	v.policy_id == "POL-088"
	v.server == "s1"
	v.action == "keep_incomplete"
}

adv_data := {
	"servers": {
		"s1": {
			"state": "active",
			"identity": "server-key",
			"address": "https://mcp.example/mcp",
			"approval": {
				"status": "approved", "approved_by": "admin-1", "approved_by_role": "security_admin",
				"not_before_ns": 19913600000000000,
				"not_after_ns": 20086400000000000,
			},
			"permissions": [
				"read",
			],
			"launch": {
				"executable": "/opt/bin/mcp",
				"args": [
					"--safe",
				],
				"env": {},
				"sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
				"observed_permissions": [
					"read",
				],
				"isolation": {
					"verified": false,
					"public_read_only": false,
					"internal_data_blocked": false,
				},
			},
			"tools": {
				"read": {
					"state": "active",
					"kind": "api",
					"operations": [
						"read",
						"write",
						"delete",
						"share",
						"external_send",
						"execute",
					],
					"document_scoped": true,
					"sensitive": false,
					"requires_confirmation": true,
					"personal_fields_allowed": [
						"name",
					],
					"egress_hosts": [
						"api.example",
					],
					"url_destinations": [
						"api.example",
					],
					"fetches_url": true,
					"roots": [
						"/srv/data",
					],
					"result_limit": {
						"max_items": 10,
						"max_bytes": 1024,
					},
					"window_document_limit": 10,
					"approved_contract_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
				},
			},
			"auth_servers": [
				{
					"id": "auth",
					"address": "https://auth.example",
				},
			],
			"metadata_hosts": [
				"auth.example",
			],
			"approved_scopes": [
				"read",
			],
			"prompts": {
				"summary": {
					"sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
				},
			},
			"resource_sources": [
				"approved-source",
			],
		},
	},
	"exceptions": [],
	"providers": [
		{
			"status": "approved", "approved_by": "admin-1", "approved_by_role": "security_admin",
			"not_before_ns": 19913600000000000,
			"not_after_ns": 20086400000000000,
			"provider": "vendor",
			"official_urls": [
				"https://pkg.example/mcp",
			],
		},
	],
	"data_types": [
		"public",
		"internal",
	],
	"package_allowlist": [
		{
			"status": "approved", "approved_by": "admin-1", "approved_by_role": "security_admin",
			"not_before_ns": 19913600000000000,
			"not_after_ns": 20086400000000000,
			"name": "pkg",
			"source": "https://pkg.example",
			"versions": [
				"1.0",
			],
		},
	],
	"permission_table": [
		{
			"status": "approved", "approved_by": "owner-1", "approved_by_role": "data_owner",
			"not_before_ns": 19913600000000000,
			"not_after_ns": 20086400000000000,
			"user": "alice",
			"server_id": "s1",
			"tool": "read",
			"data_class": "internal",
			"operation": "read",
		},
		{
			"status": "approved", "approved_by": "owner-1", "approved_by_role": "data_owner",
			"not_before_ns": 19913600000000000,
			"not_after_ns": 20086400000000000,
			"user": "alice",
			"server_id": "s1",
			"tool": "read",
			"data_class": "internal",
			"operation": "write",
		},
		{
			"status": "approved", "approved_by": "owner-1", "approved_by_role": "data_owner",
			"not_before_ns": 19913600000000000,
			"not_after_ns": 20086400000000000,
			"user": "alice",
			"server_id": "s1",
			"tool": "read",
			"data_class": "internal",
			"operation": "delete",
		},
		{
			"status": "approved", "approved_by": "owner-1", "approved_by_role": "data_owner",
			"not_before_ns": 19913600000000000,
			"not_after_ns": 20086400000000000,
			"user": "alice",
			"server_id": "s1",
			"tool": "read",
			"data_class": "internal",
			"operation": "share",
		},
		{
			"status": "approved", "approved_by": "owner-1", "approved_by_role": "data_owner",
			"not_before_ns": 19913600000000000,
			"not_after_ns": 20086400000000000,
			"user": "alice",
			"server_id": "s1",
			"tool": "read",
			"data_class": "internal",
			"operation": "external_send",
		},
		{
			"status": "approved", "approved_by": "owner-1", "approved_by_role": "data_owner",
			"not_before_ns": 19913600000000000,
			"not_after_ns": 20086400000000000,
			"user": "alice",
			"server_id": "s1",
			"tool": "read",
			"data_class": "internal",
			"operation": "execute",
		},
	],
	"delegations": [
		{
			"status": "approved", "approved_by": "owner-1", "approved_by_role": "data_owner",
			"not_before_ns": 19913600000000000,
			"not_after_ns": 20086400000000000,
			"user": "alice",
			"agent": "a1",
			"server_id": "s1",
			"tool": "read",
			"data_class": "internal",
			"operation": "read",
		},
		{
			"status": "approved", "approved_by": "owner-1", "approved_by_role": "data_owner",
			"not_before_ns": 19913600000000000,
			"not_after_ns": 20086400000000000,
			"user": "alice",
			"agent": "a1",
			"server_id": "s1",
			"tool": "read",
			"data_class": "internal",
			"operation": "write",
		},
		{
			"status": "approved", "approved_by": "owner-1", "approved_by_role": "data_owner",
			"not_before_ns": 19913600000000000,
			"not_after_ns": 20086400000000000,
			"user": "alice",
			"agent": "a1",
			"server_id": "s1",
			"tool": "read",
			"data_class": "internal",
			"operation": "delete",
		},
		{
			"status": "approved", "approved_by": "owner-1", "approved_by_role": "data_owner",
			"not_before_ns": 19913600000000000,
			"not_after_ns": 20086400000000000,
			"user": "alice",
			"agent": "a1",
			"server_id": "s1",
			"tool": "read",
			"data_class": "internal",
			"operation": "share",
		},
		{
			"status": "approved", "approved_by": "owner-1", "approved_by_role": "data_owner",
			"not_before_ns": 19913600000000000,
			"not_after_ns": 20086400000000000,
			"user": "alice",
			"agent": "a1",
			"server_id": "s1",
			"tool": "read",
			"data_class": "internal",
			"operation": "external_send",
		},
		{
			"status": "approved", "approved_by": "owner-1", "approved_by_role": "data_owner",
			"not_before_ns": 19913600000000000,
			"not_after_ns": 20086400000000000,
			"user": "alice",
			"agent": "a1",
			"server_id": "s1",
			"tool": "read",
			"data_class": "internal",
			"operation": "execute",
		},
	],
	"document_grants": [
		{
			"status": "approved", "approved_by": "owner-1", "approved_by_role": "data_owner",
			"not_before_ns": 19913600000000000,
			"not_after_ns": 20086400000000000,
			"user": "alice",
			"agent": "a1",
			"server_id": "s1",
			"tool": "read",
			"doc_id": "d1",
		},
	],
	"transfers": [
		{
			"status": "approved", "approved_by": "owner-1", "approved_by_role": "data_owner",
			"not_before_ns": 19913600000000000,
			"not_after_ns": 20086400000000000,
			"data_class": "internal",
			"recipient": "partner",
			"purpose": "report",
		},
	],
	"flows": [
		{
			"status": "approved", "approved_by": "owner-1", "approved_by_role": "data_owner",
			"not_before_ns": 19913600000000000,
			"not_after_ns": 20086400000000000,
			"source_server": "s0",
			"dest_server": "s1",
			"data_class": "internal",
			"purpose": "report",
		},
	],
	"server_accounts": {
		"s1": {
			"operations": [
				"read",
				"write",
				"delete",
				"share",
				"external_send",
				"execute",
			],
			"data_classes": [
				"internal",
			],
			"documents": [
				"d1",
			],
		},
	},
	"rate_limits": {
		"user": {
			"window_calls": 10,
			"concurrent": 2,
		},
		"agent": {
			"window_calls": 10,
			"concurrent": 2,
		},
		"tool": {
			"window_calls": 10,
			"concurrent": 2,
		},
	},
	"default_result_limit": {
		"max_items": 10,
		"max_bytes": 1024,
	},
	"blocked_versions": {
		"s1": [
			"0.1",
		],
	},
	"stop_severities": [
		"critical",
		"high",
	],
}

adv_intake_input := {
	"facts": {
		"trusted": true,
		"now_ns": 20000000000000000,
	},
	"application": {
		"id": "s1",
		"hosting": "external",
		"provider": "vendor",
		"source_url": "https://pkg.example/mcp",
		"business_scope": {
			"operations": [
				"read",
			],
			"data_types": [
				"public",
			],
			"permissions": [
				"read",
			],
		},
		"requirements": {
			"functions": "read",
			"data_types": "public",
			"permissions": "read",
			"acceptance_criteria": "reviewed",
		},
		"provider_terms": {
			"status": "verified",
			"prohibited": false,
		},
		"gateway_controls": {
			"internal_data_blocked": true,
			"personal_data_blocked": true,
			"credentials_blocked": true,
			"public_read_only": true,
		},
		"sbom": {
			"status": "completed",
		},
		"packages": [
			{
				"name": "pkg",
				"version": "1.0",
				"source": "https://pkg.example",
			},
		],
		"tools": [
			{
				"name": "read",
				"declared_effect": "read",
				"data_types": [
					"public",
				],
				"permissions": [
					"read",
				],
				"description_scan": {
					"status": "completed",
					"findings": [],
				},
				"output_contract": {
					"fields": [
						"title",
					],
					"data_scope": [
						"public",
					],
				},
				"trial_results": [
					{
						"observed_effect": "read",
						"observed_fields": [
							"title",
						],
						"sensitive_found": false,
						"observed_data_scope": [
							"public",
						],
					},
				],
				"requires_confirmation": false,
			},
		],
	},
}

adv_connect_input := {
	"facts": {
		"trusted": true,
		"now_ns": 20000000000000000,
	},
	"connection": {
		"stage": "connect",
		"server_id": "s1",
		"user": "alice",
		"identity": "server-key",
		"address": "https://mcp.example/mcp",
		"kind": "remote",
		"transport": {
			"scheme": "https",
		},
		"approval": {
			"basis": "normal",
		},
		"consent": {
			"not_before_ns": 19913600000000000,
			"not_after_ns": 20086400000000000,
			"decision": "accept",
			"server_id": "s1",
			"user": "alice",
			"functions": [
				"read",
			],
			"shown": {
				"provider": "vendor",
				"address": "https://mcp.example/mcp",
				"functions": [
					"read",
				],
			},
		},
		"requested_functions": [
			"read",
		],
		"credential": {
			"used": false,
		},
		"auth_server": {
			"id": "auth",
			"address": "https://auth.example",
		},
		"metadata": {
			"request_host": "auth.example",
			"final_host": "auth.example",
			"resolved_ips": [
				"8.8.8.8",
			],
		},
		"requested_scopes": [
			"read",
		],
		"launch": {
			"executable": "/opt/bin/mcp",
			"args": [
				"--safe",
			],
			"env": {},
			"sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
			"observed_permissions": [
				"read",
			],
			"isolation": {
				"verified": false,
				"public_read_only": false,
				"internal_data_blocked": false,
			},
		},
	},
	"approval": {
		"server_id": "s1",
		"purpose": "report",
		"scope": [
			"read",
		],
		"policy_version": "policy-approved",
		"method": "manual",
		"recorded": true,
	},
}

adv_call_input := {
	"request": {
		"stage": "request",
		"id": "r1",
		"user": "alice",
		"agent": "a1",
		"server_id": "s1",
		"tool": "read",
		"operation": "read",
		"target": {
			"data_class": "internal",
			"doc_id": "d1",
			"path": "/srv/data/file",
		},
		"recipient": "partner",
		"purpose": "report",
		"source_server": "s1",
		"intent": "call",
	},
	"facts": {
		"trusted": true,
		"now_ns": 20000000000000000,
		"permission_lookup": {
			"status": "ok",
			"request_id": "r1",
		},
		"approval": {
			"basis": "normal",
		},
		"token": {
			"valid": true,
			"audience": "s1",
			"expires_ns": 20003600000000000,
		},
		"credential": {
			"used": true,
			"bound_server": "s1",
		},
		"provenance": {
			"external_content": false,
		},
		"inspection": {
			"status": "completed",
			"secrets": [],
			"personal_data": [],
		},
		"arguments_validated": true,
		"arguments_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
		"schema": {
			"valid": true,
			"undeclared_fields": [],
		},
		"egress": {
			"final_host": "api.example",
			"resolved_ips": [
				"8.8.8.8",
			],
		},
		"path": {
			"resolved": "/srv/data/file",
		},
		"data": {
			"contains_credential": false,
		},
		"catalog": {
			"matches": 1,
			"observed_contract_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		},
		"usage": {
			"window_documents": 5,
			"blocked_pattern": false,
			"user": {
				"window_calls": 5,
				"concurrent": 1,
			},
			"agent": {
				"window_calls": 5,
				"concurrent": 1,
			},
			"tool": {
				"window_calls": 5,
				"concurrent": 1,
			},
		},
		"server_account": {
			"used": false,
		},
		"acl": {
			"user_can": true,
			"user": "alice",
			"doc_id": "d1",
		},
		"audit": {
			"central_writable": true,
			"buffer_writable": false,
			"recorded": true,
		},
		"permitted_tools": [
			"read",
		],
	},
	"response": {
		"items": 10,
		"bytes": 1024,
		"cached": false,
		"tools": [
			"read",
		],
	},
}

adv_ops_input := {
	"facts": {
		"trusted": true,
		"now_ns": 20000000000000000,
	},
	"event": "periodic",
	"servers": [
		{
			"id": "s1",
			"config_scan": {
				"status": "completed",
				"plaintext_secrets": [],
				"storage_approved": true,
			},
			"observed_tools": [
				{
					"name": "read",
					"contract_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
				},
			],
			"approved_tools": {
				"read": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
			},
			"packages": [
				{
					"name": "pkg",
					"version": "1.0",
					"source": "https://pkg.example",
				},
			],
			"vuln_scan": {
				"status": "completed",
			},
			"vulnerabilities": [],
			"instances": [
				{
					"id": "i1",
					"config_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
				},
			],
			"baseline_config_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
			"downstream": {
				"observed": [
					"https://api.example",
				],
				"approved": [
					"https://api.example",
				],
			},
			"observed_permissions": [
				"read",
			],
			"approved_permissions": [
				"read",
			],
			"revoke_confirmed": [],
			"in_use_permissions": [
				"read",
			],
			"oauth_scopes": {
				"observed": [
					"read",
				],
				"approved": [
					"read",
				],
			},
			"tool_permissions": {
				"observed": [
					"read",
				],
				"approved": [
					"read",
				],
			},
			"incidents": [],
			"restore": {
				"version": "1.0",
				"risky_settings": [],
				"approval": {
					"status": "approved", "approved_by": "admin-1", "approved_by_role": "security_admin",
					"not_before_ns": 19913600000000000,
					"not_after_ns": 20086400000000000,
				},
			},
			"provider_termination": {
				"requested_complete": true,
				"evidence_verified": true,
				"new_transfer_blocked": true,
			},
		},
	],
}

adv_resource_input := {
	"facts": {
		"trusted": true,
		"now_ns": 20000000000000000,
		"prompt_scan": {
			"blocked_types": [],
		},
		"prompt_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		"resource": {
			"resolved_id": "d1",
		},
		"acl": {
			"user_can": true,
			"user": "alice",
			"doc_id": "d1",
			"prompt": "summary",
			"resource_id": "d1",
		},
		"permitted_resources": [
			"d1",
		],
		"deleted_resources": [],
		"change": {
			"source": "approved-source",
			"within_approved_scope": true,
		},
	},
	"request": {
		"stage": "prompt_use",
		"user": "alice",
		"server_id": "s1",
		"prompt": "summary",
	},
	"response": {
		"resources": [
			"d1",
		],
	},
}
