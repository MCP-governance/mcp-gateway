package mcp.authz_test

# 프레임워크 §11.11 "정책 시험 및 검증"이 요구하는 시험 조건을 그대로 항목화한다.
#
#   정상 허용 / 비인가 차단 / 경계값·누락 입력 / 권한·Scope 초과 / 미등록 구성요소 /
#   민감정보 접근·외부 전송 / 고위험 추가 승인 / 예외 적용과 유효기간 만료 /
#   다중 정책 동시 적용 / 정책 충돌과 우선순위 / 연쇄호출(누적) /
#   이전 버전과의 결과 비교 / 정상 업무 오탐
#
# 판단 장애·시간초과(P-CONTROL-FAIL-CLOSED)와 정책 경로 우회는 정책 엔진 밖의
# 조건이라 tests/drift_and_fail_closed.sh가 담당한다.

import data.mcp.authz.decision
import rego.v1

base := {
	"environment": "prod",
	"now": "2026-09-16T10:00:00Z",
	"principal": {"role": "customer", "department": "고객"},
	"resource": {"id": "notice-001", "data_class": "public"},
	"tool": {"name": "read_document", "action": "r"},
	"approval": {"granted": false},
	"contract": {
		"registered": true,
		"enabled": true,
		"schema_hash_match": true,
		"description_hash_match": true,
		"version_match": true,
		"known_tools_only": true,
		"metadata_safe": true,
		"supplier_approved": true,
		"critical_vulnerabilities": 0,
	},
}

with_input(patch) := object.union(base, patch)

# ── T-ALLOW-001 정상 요청의 허용 ────────────────────────────────────────────

test_allow if {
	result := decision with input as base
	result.decision == "Allow"
	result.policy_id == "P-333-ALLOW-001"
	result.restrictions == {}
}

# §11.7 판단 결과에 적용 정책과 정책 버전이 포함되어야 한다.
test_decision_carries_policy_management_information if {
	result := decision with input as base
	result.policy_version == "1.0.0"
	result.policy_status == "운영"
	result.policy_set_version == "1.0.0-draft"
	count(result.risk_ids) > 0
	count(result.control_ids) > 0
	count(result.obligations) > 0
	result.environment == "prod"
}

# ── T-RBAC-001/002 비인가 요청과 권한 초과 ──────────────────────────────────

test_block_customer_write if {
	result := decision with input as with_input({"tool": {"action": "w"}})
	result.decision == "Block"
	result.policy_id == "P-333-DENY-001"
}

test_block_customer_important_read if {
	result := decision with input as with_input({"resource": {"data_class": "important"}})
	result.decision == "Block"
	result.policy_id == "P-333-DENY-001"
}

# 권한 없는 x는 외부 전송 제한이 아니라 차단이어야 한다.
test_block_beats_restrict_for_unprivileged_external_send if {
	result := decision with input as with_input({"tool": {"action": "x"}})
	result.policy_id == "P-333-DENY-001"
}

# ── T-REGISTRY-001/002 미등록·비활성 구성요소 ───────────────────────────────

test_block_unregistered if {
	result := decision with input as with_input({"contract": {"registered": false}})
	result.policy_id == "MCP-REGISTRY-001"
}

test_block_disabled_tool if {
	result := decision with input as with_input({"contract": {"enabled": false}})
	result.policy_id == "MCP-REGISTRY-002"
}

# 미등록이 비활성보다 우선한다(§11.14 더 제한적인 정책 우선).
test_unregistered_outranks_disabled if {
	result := decision with input as with_input({"contract": {"registered": false, "enabled": false}})
	result.policy_id == "MCP-REGISTRY-001"
	result.priority == 10
}

# ── T-SUPPLY-001/002 공급망 ─────────────────────────────────────────────────

test_block_unapproved_supplier if {
	result := decision with input as with_input({"contract": {"supplier_approved": false}})
	result.policy_id == "MCP-SUPPLY-001"
}

test_block_critical_vulnerability if {
	result := decision with input as with_input({"contract": {"critical_vulnerabilities": 1}})
	result.policy_id == "MCP-SUPPLY-001"
}

# ── T-CATALOG-001 계약 변조 ─────────────────────────────────────────────────

test_block_description_drift if {
	result := decision with input as with_input({"contract": {"description_hash_match": false}})
	result.policy_id == "MCP-CATALOG-001"
	result.conditions.violated == ["description_hash_match"]
}

test_catalog_reports_every_violated_field if {
	result := decision with input as with_input({"contract": {"schema_hash_match": false, "version_match": false}})
	result.conditions.violated == ["schema_hash_match", "version_match"]
}

# ── T-CLASS-001/002 데이터 등급 관리대장 ────────────────────────────────────

test_block_required_classification_without_source if {
	result := decision with input as with_input({"resource": {"classification": {"required": true}}})
	result.policy_id == "P-CLASSIFICATION-001"
}

test_allow_required_manual_classification if {
	result := decision with input as with_input({"resource": {"classification": {
		"required": true,
		"source": "manual-registry",
		"version": "demo-v1",
	}}})
	result.decision == "Allow"
}

# ── T-APPROVAL-001/002 승인 유효기간 (§11.4.1) ──────────────────────────────

test_block_expired_asset_approval if {
	result := decision with input as with_input({"contract": {"approval_valid_until": "2026-08-01T00:00:00Z"}})
	result.policy_id == "P-APPROVAL-EXPIRY-001"
	result.decision == "Block"
}

test_allow_valid_asset_approval if {
	result := decision with input as with_input({"contract": {"approval_valid_until": "2027-01-01T00:00:00Z"}})
	result.decision == "Allow"
}

# ── T-INPUT-001/002 누락된 입력 (§11.16) ────────────────────────────────────

test_block_missing_contract if {
	result := decision with input as object.remove(base, {"contract"})
	result.policy_id == "P-CONTROL-INPUT-001"
	"contract" in result.conditions.violated
}

test_block_missing_role if {
	result := decision with input as object.union(base, {"principal": {}}) with input.principal as {}
	result.policy_id == "P-CONTROL-INPUT-001"
}

# 만료를 판단해야 하는데 시각이 없으면 통과시키지 않는다.
test_block_expiry_check_without_clock if {
	no_clock := object.remove(with_input({"contract": {"approval_valid_until": "2026-08-01T00:00:00Z"}}), {"now"})
	result := decision with input as no_clock
	result.policy_id == "P-CONTROL-INPUT-001"
	"now" in result.conditions.violated
}

# ── T-RATE-001/002 경계값 ───────────────────────────────────────────────────

test_rate_limit_blocks_at_limit if {
	result := decision with input as with_input({"context": {"recent_calls": 60, "call_limit": 60}})
	result.policy_id == "P-RATE-001"
}

test_rate_limit_allows_one_below_limit if {
	result := decision with input as with_input({"context": {"recent_calls": 59, "call_limit": 60}})
	result.decision == "Allow"
}

test_rate_limit_inert_without_context if {
	result := decision with input as base
	result.decision == "Allow"
}

# ── T-VOLUME-001/002 연쇄호출 누적 ──────────────────────────────────────────

test_volume_escalates_important_read if {
	result := decision with input as with_input({
		"principal": {"role": "employee"},
		"resource": {"data_class": "important"},
		"context": {"recent_important": 10, "important_limit": 10},
	})
	result.policy_id == "P-VOLUME-001"
	result.decision == "Approval"
}

test_volume_under_limit_still_alerts if {
	result := decision with input as with_input({
		"principal": {"role": "employee"},
		"resource": {"data_class": "important"},
		"context": {"recent_important": 3, "important_limit": 10},
	})
	result.decision == "Alert"
}

# ── T-APPROVAL-X-001/002 고위험 행위 추가 승인 ──────────────────────────────

test_approval_admin_important_x if {
	result := decision with input as with_input({
		"principal": {"role": "admin"},
		"resource": {"data_class": "important"},
		"tool": {"action": "x"},
	})
	result.decision == "Approval"
	result.policy_id == "P-X-APPROVAL-001"
	"approval.required" in result.obligations
}

test_approved_admin_important_x if {
	result := decision with input as with_input({
		"principal": {"role": "admin"},
		"resource": {"data_class": "important"},
		"tool": {"action": "x"},
		"approval": {"granted": true},
	})
	result.decision == "Allow"
}

# ── T-RESTRICT-001/002 외부 전송 제한 ───────────────────────────────────────

test_restrict_admin_public_x if {
	result := decision with input as with_input({"principal": {"role": "admin"}, "tool": {"action": "x"}})
	result.decision == "Restrict"
	result.policy_id == "P-X-RESTRICT-001"
}

test_restrict_values_come_from_policy_data if {
	result := decision with input as with_input({"principal": {"role": "admin"}, "tool": {"action": "x"}})
	result.restrictions.destination == data.restrictions.external_destination
	result.restrictions.max_chars == data.restrictions.max_chars
}

# ── T-ALERT-001 중요정보 열람 증적 강화 ─────────────────────────────────────

test_alert_employee_important_read if {
	result := decision with input as with_input({
		"principal": {"role": "employee"},
		"resource": {"data_class": "important"},
	})
	result.decision == "Alert"
	"evidence.enhanced" in result.obligations
}

# ── T-DEPT-001/002 조직 축 (기본 중지) ──────────────────────────────────────

# 관리대장 status가 "중지"라 부서 축은 data.json을 켜도 집행되지 않는다.
test_department_scope_inert_while_suspended if {
	result := decision with input as with_input({
		"principal": {"role": "employee", "department": "보안기술팀"},
		"resource": {"data_class": "important", "owner_department": "거버넌스팀"},
	})
		with data.department_scope as {"enabled": true}
	result.decision == "Alert"
}

test_department_scope_escalates_when_both_switches_on if {
	live := object.union(data.policy_ledger, {"P-DEPT-001": object.union(
		data.policy_ledger["P-DEPT-001"],
		{"status": "운영"},
	)})
	result := decision with input as with_input({
		"principal": {"role": "employee", "department": "보안기술팀"},
		"resource": {"data_class": "important", "owner_department": "거버넌스팀"},
	})
		with data.department_scope as {"enabled": true}
		with data.policy_ledger as live
	result.policy_id == "P-DEPT-001"
}

test_department_scope_allows_own_department if {
	live := object.union(data.policy_ledger, {"P-DEPT-001": object.union(
		data.policy_ledger["P-DEPT-001"],
		{"status": "운영"},
	)})
	result := decision with input as with_input({
		"principal": {"role": "employee", "department": "거버넌스팀"},
		"resource": {"data_class": "important", "owner_department": "거버넌스팀"},
	})
		with data.department_scope as {"enabled": true}
		with data.policy_ledger as live
	result.decision == "Alert"
}

# ── T-CONFLICT 정책 충돌과 우선순위 (§11.14) ────────────────────────────────

test_conflicts_are_recorded_not_hidden if {
	result := decision with input as with_input({
		"principal": {"role": "employee"},
		"resource": {"data_class": "important"},
		"context": {"recent_important": 10, "important_limit": 10},
	})
	result.policy_id == "P-VOLUME-001"
	losers := {item.policy_id | some item in result.conflicts}
	losers == {"P-IMPORTANT-ALERT-001", "P-333-ALLOW-001"}
}

test_more_restrictive_policy_wins if {
	result := decision with input as with_input({
		"contract": {"registered": false, "supplier_approved": false},
		"tool": {"action": "w"},
	})
	result.policy_id == "MCP-REGISTRY-001"
	every item in result.conflicts {
		item.priority > result.priority
	}
}

# ── T-STATUS 정책 생명주기 상태 (§11.9) ─────────────────────────────────────

test_suspended_policy_is_not_enforced if {
	suspended := object.union(data.policy_ledger, {"P-333-ALLOW-001": object.union(
		data.policy_ledger["P-333-ALLOW-001"],
		{"status": "중지"},
	)})
	result := decision with input as base with data.policy_ledger as suspended
	result.policy_id == "P-CONTROL-DEFAULT-001"
	result.decision == "Block"
}

test_policy_outside_its_environment_is_not_enforced if {
	result := decision with input as with_input({"environment": "sandbox"})
	result.policy_id == "P-CONTROL-DEFAULT-001"
	result.decision == "Block"
}

test_declared_environment_is_enforced if {
	result := decision with input as with_input({"environment": "dev"})
	result.decision == "Allow"
	result.environment == "dev"
}

# ── T-LEDGER-001 관리정보 없는 정책 (§11.8) ─────────────────────────────────

test_policy_without_ledger_entry_blocks if {
	stripped := object.remove(data.policy_ledger, {"P-333-ALLOW-001"})
	result := decision with input as base with data.policy_ledger as stripped
	result.policy_id == "P-CONTROL-LEDGER-001"
	result.decision == "Block"
}

# ── T-EXC 예외 적용과 유효기간 (§8, §11.2) ──────────────────────────────────

exception_request := with_input({
	"resource": {"id": "audit-001", "data_class": "important"},
	"tool": {"name": "read_document", "action": "r"},
})

test_registered_exception_relaxes_block if {
	result := decision with input as exception_request
	result.decision == "Alert"
	result.policy_id == "P-333-DENY-001"
	result.exception.id == "EXC-001"
	"사후 수동 검토 적용" in result.obligations

	# §8.14 예외로 완화된 호출은 원래 정책보다 약한 증적을 남겨서는 안 된다.
	"evidence.enhanced" in result.obligations
	"exception.monitored" in result.obligations
}

test_expired_exception_does_not_apply if {
	result := decision with input as object.union(exception_request, {"now": "2027-02-01T00:00:00Z"})
	result.decision == "Block"
	result.exception == null
}

test_exception_before_validity_does_not_apply if {
	result := decision with input as object.union(exception_request, {"now": "2026-01-01T00:00:00Z"})
	result.decision == "Block"
}

test_exception_outside_its_scope_does_not_apply if {
	out_of_scope := object.union(exception_request, {"resource": {"id": "work-001"}})
	result := decision with input as out_of_scope
	result.decision == "Block"
	result.exception == null
}

# §8.6 요청자가 자신의 예외를 단독으로 승인하는 경우
test_self_approved_exception_is_rejected if {
	bad := [object.union(data.exceptions[0], {"approved_by": data.exceptions[0].requested_by})]
	result := decision with input as exception_request with data.exceptions as bad
	result.decision == "Block"
}

# §8.6 중대한 위험에 대해 적절한 보완통제가 없는 경우
test_exception_without_compensating_control_is_rejected if {
	bad := [object.union(data.exceptions[0], {"compensating_controls": []})]
	result := decision with input as exception_request with data.exceptions as bad
	result.decision == "Block"
}

# §8.6 적용범위가 불명확한 포괄 예외
test_blanket_exception_is_rejected if {
	bad := [object.union(object.remove(data.exceptions[0], {"scope"}), {"scope": {}})]
	result := decision with input as exception_request with data.exceptions as bad
	result.decision == "Block"
}

# §8.6 종료일을 정하지 않은 무기한 예외
test_open_ended_exception_is_rejected if {
	bad := [object.remove(data.exceptions[0], {"valid_until"})]
	result := decision with input as exception_request with data.exceptions as bad
	result.decision == "Block"
}

# 무결성 통제는 예외 대상이 아니다(관리대장 exceptionable=false).
test_exception_cannot_relax_integrity_control if {
	bad := [object.union(data.exceptions[0], {
		"policy_id": "MCP-REGISTRY-001",
		"scope": {"principal_role": "customer"},
	})]
	result := decision with input as with_input({"contract": {"registered": false}})
		with data.exceptions as bad
	result.decision == "Block"
	result.policy_id == "MCP-REGISTRY-001"
}

# 예외는 완화만 할 수 있고 강화는 변경관리 절차를 따라야 한다.
test_exception_cannot_tighten_a_decision if {
	bad := [object.union(data.exceptions[0], {
		"policy_id": "P-333-ALLOW-001",
		"scope": {"principal_role": "customer"},
		"effect": "Block",
	})]
	result := decision with input as base with data.exceptions as bad
	result.decision == "Allow"
}

# ── T-BASELINE 이전 버전과의 결과 비교 (§11.11) ─────────────────────────────
#
# 27칸 권한 매트릭스는 정책집을 다시 쓰기 전의 확정 판정이다. 구조를 바꾸면서
# 조용히 달라진 칸이 없는지 여기서 대조한다.

baseline := {
	"customer": {
		"public": {"r": "Allow", "w": "Block", "x": "Block"},
		"nonimportant": {"r": "Block", "w": "Block", "x": "Block"},
		"important": {"r": "Block", "w": "Block", "x": "Block"},
	},
	"employee": {
		"public": {"r": "Allow", "w": "Block", "x": "Block"},
		"nonimportant": {"r": "Allow", "w": "Allow", "x": "Block"},
		"important": {"r": "Alert", "w": "Block", "x": "Block"},
	},
	"admin": {
		"public": {"r": "Allow", "w": "Allow", "x": "Restrict"},
		"nonimportant": {"r": "Allow", "w": "Allow", "x": "Restrict"},
		"important": {"r": "Allow", "w": "Allow", "x": "Approval"},
	},
}

# 예외 대장이 비어 있을 때의 순수 권한 판정을 본다.
matrix_cell(role, data_class, action) := result.decision if {
	result := decision with input as with_input({
		"principal": {"role": role},
		"resource": {"id": "matrix", "data_class": data_class},
		"tool": {"action": action},
	})
		with data.exceptions as []
}

test_permission_matrix_matches_recorded_baseline if {
	every role, classes in baseline {
		every data_class, actions in classes {
			every action, expected in actions {
				matrix_cell(role, data_class, action) == expected
			}
		}
	}
}

# ── T-LEDGER 관리대장 자체의 정합성 (§12.3) ─────────────────────────────────

test_ledger_priorities_are_unique if {
	ids := [pid | some pid, _ in data.policy_ledger]
	priorities := {data.policy_ledger[pid].priority | some pid in ids}
	count(priorities) == count(ids)
}

test_every_ledger_entry_has_required_management_information if {
	required := ["name", "purpose", "risk_ids", "control_ids", "owner", "approver", "version", "status", "priority", "environments", "obligations", "exceptionable"]
	every _, entry in data.policy_ledger {
		every field in required {
			object.get(entry, field, null) != null
		}
	}
}

test_every_ledger_status_is_a_reference_value if {
	allowed := {"작성 중", "검토 중", "승인", "시험", "운영", "제한", "중지", "폐기"}
	every _, entry in data.policy_ledger {
		entry.status in allowed
	}
}

test_every_ledger_outcome_is_a_reference_value if {
	allowed := {"허용", "경고", "제한", "추가 승인", "차단"}
	every _, entry in data.policy_ledger {
		object.get(entry, "outcome", "차단") in allowed
	}
}

test_every_registered_exception_survives_section_8_6 if {
	every exc in data.exceptions {
		exc.requested_by != exc.approved_by
		is_string(exc.valid_until)
		count(exc.scope) > 0
		count(exc.compensating_controls) > 0
		is_string(exc.exit_plan)
		data.policy_ledger[exc.policy_id].exceptionable == true
	}
}
