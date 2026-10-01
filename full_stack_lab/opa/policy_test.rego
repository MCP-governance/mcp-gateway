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

pac_fixture := {
  "request": {
    "id": "req-001",
    "user_id": "user-1",
    "agent_id": "agent-1",
    "session_id": "session-1",
    "server_id": "server-1",
    "feature_type": "tool",
    "feature_id": "read_file",
    "action": "READ",
    "arguments": {
      "path": "file-1"
    },
    "on_behalf_of": true,
    "environment": "prod",
    "targets": {
      "files": [
        "file-1"
      ],
      "commands": [],
      "recipients": []
    },
    "data": {
      "asset_id": "asset-1",
      "grade": "internal"
    },
    "transfer": {
      "enabled": false,
      "destination_id": ""
    },
    "high_risk": false,
    "automated": false
  },
  "facts": {
    "trusted": true,
    "now_ns": 1800000000000000000,
    "classification": {
      "verified": true,
      "high_risk": false,
      "transfer_required": false,
      "on_behalf_of": true,
      "automated": false
    },
    "approval_workflow_available": true,
    "approval": {
      "status": "APPROVED",
      "server_id": "server-1",
      "conditions_met": true,
      "valid_from_ns": 1700000000000000000,
      "valid_until_ns": 1900000000000000000,
      "baseline": {
        "server_version": "1.0.0",
        "feature_definition_hash": "sha256:feature-v1",
        "schema_hash": "sha256:schema-v1",
        "policy_version": "pac15-v1"
      },
      "environments": [
        "prod"
      ],
      "production_controls": true,
      "subject": {
        "user_id": "user-1",
        "agent_id": "agent-1",
        "session_id": "session-1"
      },
      "auth_issuer": "https://auth.example.test",
      "connections": [
        {
          "server_id": "server-1",
          "endpoint_id": "endpoint-1",
          "final_target_id": "target-1"
        }
      ],
      "features": [
        {
          "server_id": "server-1",
          "type": "tool",
          "id": "read_file",
          "definition_hash": "sha256:feature-v1"
        }
      ],
      "actions": [
        "READ"
      ],
      "allowed_argument_keys": [
        "path"
      ],
      "parameter_bindings": [
        {
          "argument_path": [
            "path"
          ],
          "target_type": "file"
        }
      ],
      "targets": {
        "files": [
          "file-1"
        ],
        "commands": [],
        "recipients": []
      },
      "data_scopes": [
        {
          "asset_id": "asset-1",
          "grade": "internal"
        }
      ],
      "transfer_pairs": [
        {
          "destination_id": "dest-1",
          "grade": "internal"
        }
      ],
      "limits": {
        "allow_automated": false,
        "max_retries": 2,
        "max_concurrency": 2,
        "max_calls": 10,
        "max_chain_depth": 3,
        "max_execution_ms": 30000
      }
    },
    "baseline": {
      "verified": true,
      "server_version": "1.0.0",
      "feature_definition_hash": "sha256:feature-v1",
      "schema_hash": "sha256:schema-v1",
      "policy_version": "pac15-v1"
    },
    "environment": {
      "verified": true,
      "id": "prod",
      "production_equivalent": false
    },
    "identity": {
      "verified": true,
      "user_id": "user-1",
      "agent_id": "agent-1",
      "session_id": "session-1",
      "allowed_actions": [
        "READ"
      ]
    },
    "delegation": {
      "verified": true,
      "user_id": "user-1",
      "agent_id": "agent-1",
      "valid_from_ns": 1700000000000000000,
      "valid_until_ns": 1900000000000000000,
      "user_actions": [
        "READ"
      ],
      "agent_actions": [
        "READ"
      ],
      "delegated_actions": [
        "READ"
      ]
    },
    "auth": {
      "mode": "http",
      "verified": true,
      "not_revoked": true,
      "issuer": "https://auth.example.test",
      "audience": "server-1",
      "valid_from_ns": 1700000000000000000,
      "valid_until_ns": 1900000000000000000,
      "scopes": [
        "READ"
      ]
    },
    "connection": {
      "verified": true,
      "final_target_verified": true,
      "server_id": "server-1",
      "endpoint_id": "endpoint-1",
      "final_target_id": "target-1"
    },
    "catalog_feature": {
      "verified": true,
      "server_id": "server-1",
      "type": "tool",
      "id": "read_file",
      "definition_hash": "sha256:feature-v1"
    },
    "action": {
      "verified": true,
      "normalized": "READ"
    },
    "parameters": {
      "verified": true,
      "normalized": true,
      "schema_valid": true,
      "coverage_complete": true,
      "canonical_arguments": {
        "path": "file-1"
      },
      "derived_targets": {
        "files": [
          "file-1"
        ],
        "commands": [],
        "recipients": []
      }
    },
    "data": {
      "verified": true,
      "asset_id": "asset-1",
      "grade": "internal"
    },
    "transfer": {
      "verified": true,
      "final_destination_verified": true,
      "final_destination_id": "dest-1",
      "data_grade": "internal"
    },
    "revocation": {
      "verified": true,
      "fresh": true,
      "user": false,
      "agent": false,
      "server": false,
      "feature": false,
      "approval": false
    },
    "execution": {
      "atomic_reservation_verified": true,
      "reservation_request_id": "req-001",
      "reservation_expires_ns": 1800000001000000000,
      "duplicate_status": "clear",
      "previous_mutation_status": "clear",
      "retry_count": 0,
      "active_concurrency": 1,
      "total_calls": 1,
      "chain_depth": 1,
      "requested_timeout_ms": 5000
    }
  }
}

base := {
    "pac": pac_fixture,
	"environment": "prod",
	"now": "2026-09-16T10:00:00Z",
	"principal": {"role": "partner", "department": "협력사 A"},
	"resource": {"id": "notice-001", "data_class": "public"},
	"tool": {"name": "read_text_file", "action": "r"},
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
	result.policy_id == "P-AUTHZ-ALLOW-001"
	result.restrictions == {}
}

# §11.7 판단 결과에 적용 정책과 정책 버전이 포함되어야 한다.
test_decision_carries_policy_management_information if {
	result := decision with input as base
	result.policy_version == "pac15-v1"
	result.policy_status == "운영"
	result.policy_set_version == "4.0.0-pac15"
	count(result.risk_ids) > 0
	count(result.control_ids) > 0
	count(result.obligations) > 0
	result.environment == "prod"
}

# ── T-RBAC-001/002 비인가 요청과 권한 초과 ──────────────────────────────────

test_block_approved_scope_write if {
    facts := object.union(pac_fixture.facts, {"approval": object.union(pac_fixture.facts.approval, {"data_scopes": []})})
    request := object.union(base, {"pac": {"request": pac_fixture.request, "facts": facts},
                                  "principal": {"role": "admin", "shadow_endpoints": 5},
                                  "relationship": {"defined": true, "in_scope": false}})
    result := decision with input as request
    result.decision == "Block"
    result.policy_id == "PAC-11"
    result.exception == null
}

test_block_approved_scope_important_read if {
    facts := object.union(pac_fixture.facts, {"approval": object.union(pac_fixture.facts.approval, {"data_scopes": []})})
    request := object.union(base, {"pac": {"request": pac_fixture.request, "facts": facts},
                                  "principal": {"role": "admin", "shadow_endpoints": 5},
                                  "relationship": {"defined": true, "in_scope": false}})
    result := decision with input as request
    result.decision == "Block"
    result.policy_id == "PAC-11"
    result.exception == null
}

# 권한 없는 x는 외부 전송 제한이 아니라 차단이어야 한다.
test_block_beats_restrict_for_unprivileged_external_send if {
    facts := object.union(pac_fixture.facts, {"approval": object.union(pac_fixture.facts.approval, {"data_scopes": []})})
    request := object.union(base, {"pac": {"request": pac_fixture.request, "facts": facts},
                                  "principal": {"role": "admin", "shadow_endpoints": 5},
                                  "relationship": {"defined": true, "in_scope": false}})
    result := decision with input as request
    result.decision == "Block"
    result.policy_id == "PAC-11"
    result.exception == null
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

# ── T-RATE-003/004 동시 실행과 중복 (PAC-15) ────────────────────────────────

test_concurrency_blocks_above_limit if {
	result := decision with input as with_input({"context": {"active_calls": 5, "concurrency_limit": 4}})
	result.policy_id == "P-RATE-002"
	result.decision == "Block"
}

test_concurrency_allows_at_limit if {
	result := decision with input as with_input({"context": {"active_calls": 4, "concurrency_limit": 4}})
	result.decision == "Allow"
}

test_duplicate_call_in_flight_blocks if {
	result := decision with input as with_input({"context": {"duplicate_in_flight": true}})
	result.policy_id == "P-RATE-003"
	result.decision == "Block"
}

test_duplicate_call_after_release_allows if {
	result := decision with input as with_input({"context": {"duplicate_in_flight": false}})
	result.decision == "Allow"
}

# 예약 값이 없던 때에 기록된 입력(정책 재생)은 이 통제로 판단하지 않는다.
test_ceilings_inert_for_recorded_inputs_without_reservation if {
	result := decision with input as with_input({"context": {"recent_calls": 1, "call_limit": 60}})
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
	result := decision with input as with_input({"principal": {"role": "admin"}, "tool": {"action": "x", "restrictable": ["max_chars"]}})
	result.decision == "Restrict"
	result.policy_id == "P-X-RESTRICT-001"
}

test_restrict_values_come_from_policy_data if {
	result := decision with input as with_input({"principal": {"role": "admin"}, "tool": {"action": "x", "restrictable": ["max_chars", "journal_bcc"]}})
	result.restrictions == {"max_chars": data.restrictions.max_chars, "journal_bcc": data.restrictions.journal_bcc}
}

# 도구가 집행할 수 없는 제한은 제안하지 않는다. 판정에 실린 제한을 Gateway가 적용하지
# 못하면 fail-closed가 되므로, 제한 목록은 도구가 선언한 것과 교집합이어야 한다.
test_restrict_only_what_the_tool_can_enforce if {
	result := decision with input as with_input({"principal": {"role": "admin"}, "tool": {"action": "x", "restrictable": ["max_chars"]}})
	object.keys(result.restrictions) == {"max_chars"}
}

# ── T-X-ALERT-001 제한 불가 외부 전송 ───────────────────────────────────────

test_x_without_restrictable_is_alert if {
	result := decision with input as with_input({"principal": {"role": "admin"}, "tool": {"action": "x"}})
	result.decision == "Alert"
	result.policy_id == "P-X-ALERT-001"
}

# ── T-EGRESS-002 인자 목적지 SSRF ───────────────────────────────────────────

test_ssrf_destination_blocks_even_admin if {
	result := decision with input as with_input({
		"principal": {"role": "admin"}, "tool": {"action": "r"},
		"destinations": [{"kind": "url", "value": "http://corp-git:3000/api/v1/admin/users", "category": "infrastructure"}],
	})
	result.decision == "Block"
	result.policy_id == "MCP-EGRESS-002"
}

test_intranet_destination_is_not_ssrf if {
	result := decision with input as with_input({
		"principal": {"role": "employee"}, "tool": {"action": "r"}, "resource": {"data_class": "nonimportant"},
		"destinations": [{"kind": "url", "value": "http://intranet.bob.local/", "category": "intranet"}],
	})
	result.decision == "Allow"
}

# ── T-DLP-001 민감정보 외부 전송 ────────────────────────────────────────────

test_dlp_blocks_external_send_even_with_approval if {
	result := decision with input as with_input({
		"principal": {"role": "admin"}, "tool": {"action": "x"}, "resource": {"data_class": "important"},
		"request": {"dlp": ["kr-rrn"]}, "approval": {"granted": true},
	})
	result.decision == "Block"
	result.policy_id == "P-DLP-001"
}

test_dlp_on_internal_write_is_not_dlp_block if {
	result := decision with input as with_input({
		"principal": {"role": "employee"}, "tool": {"action": "w"}, "resource": {"data_class": "nonimportant"},
		"request": {"dlp": ["kr-mobile"]},
	})
	result.policy_id != "P-DLP-001"
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
	losers == {"P-IMPORTANT-ALERT-001", "P-AUTHZ-ALLOW-001"}
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
	suspended := object.union(data.policy_ledger, {"P-AUTHZ-ALLOW-001": object.union(
		data.policy_ledger["P-AUTHZ-ALLOW-001"],
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
	stripped := object.remove(data.policy_ledger, {"P-AUTHZ-ALLOW-001"})
	result := decision with input as base with data.policy_ledger as stripped
	result.policy_id == "P-CONTROL-LEDGER-001"
	result.decision == "Block"
}

# ── T-EXC 예외 적용과 유효기간 (§8, §11.2) ──────────────────────────────────

exception_request := with_input({
	"resource": {"id": "/shared/confidential/audit/external-audit-copy-2026.md", "data_class": "important"},
	"tool": {"name": "read_text_file", "action": "r"},
})

test_retired_333_exceptions_cannot_authorize_a_pac_denial if {
    every exc in [x | some x in data.exceptions; x.policy_id == "P-AUTHZ-DENY-001"] { exc.status == "종료" }
    facts := object.union(pac_fixture.facts, {"approval": object.union(pac_fixture.facts.approval, {"data_scopes": []})})
    request := object.union(exception_request, {"pac": {"request": pac_fixture.request, "facts": facts}})
    result := decision with input as request
    result.decision == "Block"
    result.policy_id == "PAC-11"
    result.exception == null
}

valid_exception_fixture := object.union(data.exceptions[0], {"status": "적용"})

test_exception_valid_window if {
    data.mcp.authz.valid_exception(valid_exception_fixture) with input as base
}
test_exception_rejects_self_approval if {
    bad := object.union(valid_exception_fixture, {"approved_by": valid_exception_fixture.requested_by})
    not data.mcp.authz.valid_exception(bad) with input as base
}
test_exception_rejects_missing_controls if {
    bad := object.union(valid_exception_fixture, {"compensating_controls": []})
    not data.mcp.authz.valid_exception(bad) with input as base
}
test_exception_rejects_blanket_scope if {
    bad := object.union(object.remove(valid_exception_fixture, {"scope"}), {"scope": {}})
    not data.mcp.authz.valid_exception(bad) with input as base
}
test_exception_rejects_open_ended_window if {
    bad := object.remove(valid_exception_fixture, {"valid_until"})
    not data.mcp.authz.valid_exception(bad) with input as base
}
test_exception_rejects_expired_window if {
    not data.mcp.authz.valid_exception(valid_exception_fixture) with input as with_input({"now": "2027-02-01T00:00:00Z"})
}
test_exception_rejects_before_window if {
    not data.mcp.authz.valid_exception(valid_exception_fixture) with input as with_input({"now": "2026-01-01T00:00:00Z"})
}


# 무결성 통제는 예외 대상이 아니다(관리대장 exceptionable=false).
test_exception_cannot_relax_integrity_control if {
	bad := [object.union(data.exceptions[0], {
		"policy_id": "MCP-REGISTRY-001",
		"scope": {"principal_role": "partner"},
	})]
	result := decision with input as with_input({"contract": {"registered": false}})
		with data.exceptions as bad
	result.decision == "Block"
	result.policy_id == "MCP-REGISTRY-001"
}

# D-62: 우선순위가 PAC보다 높은 예외 가능 정책(MCP-EGRESS-001)이 선택돼도, conflicts에 남은
# PAC 거부를 그 예외가 지우지 못한다. 대조군은 같은 예외가 PAC 결과가 없을 때 실제로 적용됨을 보인다.
egress_exception := [object.union(object.remove(valid_exception_fixture, {"scope"}),
	{"policy_id": "MCP-EGRESS-001", "scope": {"tool": "read_text_file"}})]

egress_request := with_input({"contract": object.union(base.contract, {"endpoint_allowed": false})})

test_exception_cannot_hide_a_lower_ranked_pac_denial if {
	facts := object.union(pac_fixture.facts, {"approval": object.union(pac_fixture.facts.approval, {"data_scopes": []})})
	request := object.union(egress_request, {"pac": {"request": pac_fixture.request, "facts": facts}})
	result := decision with input as request with data.exceptions as egress_exception
	result.decision == "Block"
	result.policy_id == "MCP-EGRESS-001"
	result.exception == null
	some c in result.conflicts
	c.policy_id == "PAC-11"
}

test_exception_applies_when_pac_has_no_finding if {
	result := decision with input as egress_request with data.exceptions as egress_exception
	result.decision == "Alert"
	result.exception.id == valid_exception_fixture.id
}

# 공급자 호스팅 서버는 읽기 인자도 받는다. 인자에서 탐지된 PII는 행위와 무관하게 실행 전에 막는다.
test_pii_to_provider_hosted_server_blocks_even_for_reads if {
	result := decision with input as with_input({"tool": {"name": "read_text_file", "action": "r", "provider_hosted": true},
		"request": {"pii_types": ["KR_RRN"]}})
	result.decision == "Block"
	result.policy_id == "MCP-DATA-EGRESS-001"
}

test_provider_hosted_read_without_pii_is_not_an_egress_block if {
	result := decision with input as with_input({"tool": {"name": "read_text_file", "action": "r", "provider_hosted": true}})
	result.policy_id != "MCP-DATA-EGRESS-001"
}

# 예외는 완화만 할 수 있고 강화는 변경관리 절차를 따라야 한다.
test_exception_cannot_tighten_a_decision if {
	bad := [object.union(data.exceptions[0], {
		"policy_id": "P-AUTHZ-ALLOW-001",
		"scope": {"principal_role": "partner"},
		"effect": "Block",
	})]
	result := decision with input as base with data.exceptions as bad
	result.decision == "Allow"
}

# PAC 입력 누락은 역할에 관계없이 실행 전에 차단한다.
test_missing_pac_facts_fails_closed if {
    result := decision with input as object.remove(base, {"pac"})
    result.decision == "Block"
    result.policy_id == "INPUT_CONTRACT"
}

test_pac_scope_denies_unapproved_action if {
    altered := object.union(pac_fixture.request, {"action": "WRITE"})
    facts := object.union(pac_fixture.facts, {"action": {"verified": true, "normalized": "WRITE"}})
    request := object.union(base, {"pac": {"request": altered, "facts": facts}})
    result := decision with input as request
    result.decision == "Block"
    some violation in array.concat([{"policy_id": result.policy_id}], result.conflicts)
    violation.policy_id == "PAC-09"
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

# 팀원의 실행 전 정책 PAC-01~15 중 이 정책이 무엇을 집행하는지(docs/ai/PAC_MAPPING.md).
# 없는 번호를 적어 두면 대응표와 관리대장이 조용히 갈라진다.
test_pac_ids_reference_existing_controls if {
	valid := {sprintf("PAC-%02d", [n]) | some n in numbers.range(1, 15)}
	every _, entry in data.policy_ledger {
		every pac in object.get(entry, "pac_ids", []) {
			pac in valid
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

# PDF runtime data boundary: the registered server endpoint and the call's recipient
# are independent destinations. Only the latter carries the requested disclosure.
external_mail := {"kind": "email", "value": "buyer@outside.example", "host": "outside.example",
	"category": "external-mail", "external": true}

internal_mail := {"kind": "email", "value": "review@bob.local", "host": "bob.local",
	"category": "internal-mail", "external": false}

test_confidential_external_send_blocks_before_approval if {
	request := with_input({
		"principal": {"role": "admin"},
		"resource": {"id": "mail", "data_class": "important"},
		"tool": {"name": "send_email", "action": "x"},
		"destinations": [external_mail],
	})
	result := decision with input as request
	result.policy_id == "MCP-DATA-EGRESS-001"
}

test_pii_external_send_blocks_even_for_public_document if {
	request := with_input({
		"principal": {"role": "admin"},
		"tool": {"name": "send_email", "action": "x"},
		"destinations": [external_mail],
		"request": {"pii_types": ["KR_RRN"]},
	})
	result := decision with input as request
	result.policy_id == "MCP-DATA-EGRESS-001"
}

test_internal_important_send_still_requires_approval if {
	request := with_input({
		"principal": {"role": "admin"},
		"resource": {"id": "mail", "data_class": "important"},
		"tool": {"name": "send_email", "action": "x"},
		"destinations": [internal_mail],
	})
	result := decision with input as request
	result.policy_id == "P-X-APPROVAL-001"
}

test_sensitive_read_then_send_blocks_even_with_public_document if {
	request := with_input({
		"principal": {"role": "admin"},
		"tool": {"name": "fetch", "action": "x"},
		"destinations": [{"kind": "url", "value": "https://share.external.example/u", "host": "share.external.example",
			"category": "external", "external": true}],
		"request": {"sequence_flags": ["sensitive_read_then_send"]},
	})
	result := decision with input as request
	result.policy_id == "P-CHAIN-001"
}

test_read_then_internal_send_is_not_a_chain if {
	request := with_input({
		"principal": {"role": "admin"},
		"tool": {"name": "send_email", "action": "w"},
		"destinations": [internal_mail],
		"request": {"sequence_flags": ["sensitive_read_then_send"]},
	})
	result := decision with input as request
	result.policy_id != "P-CHAIN-001"
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

# ── T-DECOMM 전주기 종료 (§11.11 미등록·비인가 구성요소 + 전주기 종료 단계) ──
#
# 이 시험들이 지키는 것은 "폐기했다"가 판정이 아니라 집행이 되게 하는 것이다.
# 관리대장에서 상태만 바꾸고 호출은 계속 되는 구성은 종료가 아니라 표기다.

test_terminating_engagement_is_blocked if {
	result := decision with input as with_input({"contract": object.union(
		base.contract, {"lifecycle": "TERMINATING"},
	)})
	result.decision == "Block"
	result.policy_id == "MCP-DECOMM-001"
}

test_retired_engagement_is_blocked if {
	result := decision with input as with_input({"contract": object.union(
		base.contract, {"lifecycle": "RETIRED"},
	)})
	result.decision == "Block"
	result.policy_id == "MCP-DECOMM-001"
}

# 폐기된 서버는 Registry에서도 비활성이 된다. 둘 다 성립할 때 감사에 남아야 하는
# 사실은 "폐기된 관계였다"이고, 비활성 판정은 경합 후보로만 남아야 한다.
test_decommission_outranks_disabled_registry if {
	result := decision with input as with_input({"contract": object.union(
		base.contract, {"lifecycle": "RETIRED", "enabled": false},
	)})
	result.policy_id == "MCP-DECOMM-001"
	some conflict in result.conflicts
	conflict.policy_id == "MCP-REGISTRY-002"
}

# lifecycle 입력이 없는 배포(구버전 Gateway)는 운영 중으로 본다. 기본값을 종료로
# 두면 스키마가 아직 올라가지 않은 몇 초 동안 전부 차단된다.
test_absent_lifecycle_defaults_to_operating if {
	result := decision with input as base
	result.decision == "Allow"
	result.policy_id == "P-AUTHZ-ALLOW-001"
}

# 폐기 차단은 예외로 완화할 수 없다. 완화되면 종료 판정의 연속성 근거가 사라진다.
test_decommission_is_not_exceptionable if {
	data.policy_ledger["MCP-DECOMM-001"].exceptionable == false
}

# ── T-SHADOW 강제 경로 밖 설정 (§11.11 다중 정책 동시 적용) ─────────────────

test_shadow_endpoint_upgrades_allow_to_alert if {
	result := decision with input as with_input({
		"principal": {"role": "partner", "department": "협력사 A", "shadow_endpoints": 2},
	})
	result.decision == "Alert"
	result.policy_id == "MCP-SHADOW-001"
	some conflict in result.conflicts
	conflict.policy_id == "P-AUTHZ-ALLOW-001"
}

# 섀도 설정을 가진 사람이라고 해서 원래 막혔을 호출이 경고로 바뀌지는 않는다.
# 더 제한적인 판정이 이긴다.
test_shadow_endpoint_does_not_weaken_a_block if {
    facts := object.union(pac_fixture.facts, {"approval": object.union(pac_fixture.facts.approval, {"data_scopes": []})})
    request := object.union(base, {"pac": {"request": pac_fixture.request, "facts": facts},
                                  "principal": {"role": "admin", "shadow_endpoints": 5},
                                  "relationship": {"defined": true, "in_scope": false}})
    result := decision with input as request
    result.decision == "Block"
    result.policy_id == "PAC-11"
    result.exception == null
}

test_no_shadow_report_leaves_allow_unchanged if {
	result := decision with input as with_input({
		"principal": {"role": "partner", "department": "협력사 A", "shadow_endpoints": 0},
	})
	result.decision == "Allow"
	result.policy_id == "P-AUTHZ-ALLOW-001"
}

# ── T-SCOPE-001/002 이용 관계 범위 (D-39) ────────────────────────────────────

scope_outside := {"relationship": {"defined": true, "in_scope": false, "ids": ["UR-FS-SHARED"], "outside": ["/workspace/notes.md"]}}

test_scope_outside_relationship_raises_alert if {
	result := decision with input as with_input(scope_outside)
	result.decision == "Alert"
	result.policy_id == "P-SCOPE-001"
	contains(result.reason, "/workspace/notes.md")
	some conflict in result.conflicts
	conflict.policy_id == "P-AUTHZ-ALLOW-001"
}

test_scope_inside_relationship_leaves_allow if {
	result := decision with input as with_input({"relationship": {"defined": true, "in_scope": true, "ids": ["UR-FS-SHARED"], "outside": []}})
	result.decision == "Allow"
	result.policy_id == "P-AUTHZ-ALLOW-001"
}

# 이용 관계가 없는 서버, relationship을 모르는 입력(구버전 Gateway·재생 사례)은 판단하지 않는다.
test_scope_needs_a_relationship if {
	result := decision with input as with_input({"relationship": {"defined": false, "in_scope": false}})
	result.policy_id == "P-AUTHZ-ALLOW-001"
	older := decision with input as base
	older.policy_id == "P-AUTHZ-ALLOW-001"
}

# 범위 밖이라고 원래 막혔을 호출이 경보로 약해지지는 않는다.
test_scope_does_not_weaken_a_block if {
    facts := object.union(pac_fixture.facts, {"approval": object.union(pac_fixture.facts.approval, {"data_scopes": []})})
    request := object.union(base, {"pac": {"request": pac_fixture.request, "facts": facts},
                                  "principal": {"role": "admin", "shadow_endpoints": 5},
                                  "relationship": {"defined": true, "in_scope": false}})
    result := decision with input as request
    result.decision == "Block"
    result.policy_id == "PAC-11"
    result.exception == null
}

# ── 통합관리대장 V1.0 PaC 후보에서 새로 정책화한 통제 ───────────────────────
#
# 추가된 후보마다 "성립하는 경우"와 "성립하지 않아야 하는 경우"를 함께 둔다.
# 성립 시험만 있으면 조건을 넓게 잡은 규칙이 시험을 통과한 채로 정상 업무를
# 막는다(§11.11 정상 업무 오탐).

# T-TRANSPORT-001 CTL-24 평문 원격 연결
test_block_plaintext_remote_endpoint if {
	result := decision with input as with_input({"contract": object.union(base.contract, {"transport_secure": false})})
	result.decision == "Block"
	result.policy_id == "MCP-TRANSPORT-001"
}

test_secure_transport_is_not_blocked if {
	result := decision with input as with_input({"contract": object.union(base.contract, {"transport_secure": true})})
	result.policy_id == "P-AUTHZ-ALLOW-001"
}

# 입력이 아예 없는 구버전 Gateway에서 전부 막히면 안 된다.
test_missing_transport_field_defaults_open if {
	result := decision with input as base
	result.policy_id == "P-AUTHZ-ALLOW-001"
}

# T-EGRESS-001 CTL-25 허용 목록 밖 목적지
test_block_endpoint_outside_egress_allowlist if {
	result := decision with input as with_input({"contract": object.union(base.contract, {"endpoint_allowed": false})})
	result.decision == "Block"
	result.policy_id == "MCP-EGRESS-001"
}

# 전송 보호가 더 근본적인 실패라 목적지보다 앞선다.
test_transport_outranks_egress if {
	patch := {"contract": object.union(base.contract, {"transport_secure": false, "endpoint_allowed": false})}
	result := decision with input as with_input(patch)
	result.policy_id == "MCP-TRANSPORT-001"
}

# T-UNTRUSTED-001 CTL-13 비신뢰 콘텐츠 기반 고위험 실행
test_untrusted_marker_on_write_requires_approval if {
	patch := {
		"principal": {"role": "employee"},
		"resource": {"id": "work-001", "data_class": "nonimportant"},
		"tool": {"name": "write_document", "action": "w"},
		"request": {"untrusted_markers": ["content"]},
	}
	result := decision with input as with_input(patch)
	result.decision == "Approval"
	result.policy_id == "P-UNTRUSTED-CONTENT-001"
}

# T-UNTRUSTED-002 같은 표지라도 읽기는 막지 않는다.
test_untrusted_marker_on_read_only_alerts if {
	patch := {
		"principal": {"role": "employee"},
		"resource": {"id": "work-001", "data_class": "nonimportant"},
		"request": {"untrusted_markers": ["content"]},
	}
	result := decision with input as with_input(patch)
	result.decision == "Alert"
	result.policy_id == "P-UNTRUSTED-CONTENT-002"
}

# 표지가 없으면 같은 쓰기가 그냥 허용이어야 한다(오탐 방지).
test_clean_write_is_not_escalated if {
	patch := {
		"principal": {"role": "employee"},
		"resource": {"id": "work-001", "data_class": "nonimportant"},
		"tool": {"name": "write_document", "action": "w"},
		"request": {"untrusted_markers": []},
	}
	result := decision with input as with_input(patch)
	result.policy_id == "P-AUTHZ-ALLOW-001"
}

# 승인을 받은 뒤에는 같은 호출이 통과해야 한다.
test_untrusted_marker_clears_after_approval if {
	patch := {
		"principal": {"role": "employee"},
		"resource": {"id": "work-001", "data_class": "nonimportant"},
		"tool": {"name": "write_document", "action": "w"},
		"request": {"untrusted_markers": ["content"]},
		"approval": {"granted": true},
	}
	result := decision with input as with_input(patch)
	result.policy_id == "P-AUTHZ-ALLOW-001"
}

# T-ANOMALY-001 CTL-28 반복 차단
test_repeated_blocks_raise_alert if {
	patch := {
		"principal": {"role": "employee"},
		"resource": {"id": "work-001", "data_class": "nonimportant"},
		"context": {"recent_blocks": 5, "block_limit": 5},
	}
	result := decision with input as with_input(patch)
	result.decision == "Alert"
	result.policy_id == "P-ANOMALY-001"
}

test_blocks_below_limit_do_not_alert if {
	patch := {
		"principal": {"role": "employee"},
		"resource": {"id": "work-001", "data_class": "nonimportant"},
		"context": {"recent_blocks": 4, "block_limit": 5},
	}
	result := decision with input as with_input(patch)
	result.policy_id == "P-AUTHZ-ALLOW-001"
}

# T-SHADOW-002 망에서 발견된 리스너는 설정 기반 발견보다 앞선다.
test_network_shadow_outranks_config_shadow if {
	patch := {"principal": {"role": "employee", "shadow_endpoints": 1, "shadow_listeners": 2}}
	result := decision with input as with_input(patch)
	result.decision == "Alert"
	result.policy_id == "MCP-SHADOW-002"
}

test_no_listener_falls_back_to_config_shadow if {
	patch := {"principal": {"role": "employee", "shadow_endpoints": 1, "shadow_listeners": 0}}
	result := decision with input as with_input(patch)
	result.policy_id == "MCP-SHADOW-001"
}

# 관리대장 추적성: 새 정책도 통합관리대장 V1.0의 실제 행을 가리켜야 한다.
test_new_policies_carry_register_ids if {
	some pid in ["MCP-TRANSPORT-001", "MCP-EGRESS-001", "P-UNTRUSTED-CONTENT-001", "P-ANOMALY-001", "MCP-SHADOW-002"]
	entry := data.policy_ledger[pid]
	count(entry.risk_ids) > 0
	count(entry.control_ids) > 0
	startswith(entry.control_ids[0], "CTL-")
	entry.pac_candidate_id != ""
}

# ── 승인형 예외(EXC-002): 승인이 부여되면 실행, 없으면 승인 대기 ───────────────
approval_exception_request := with_input({
	"principal": {"role": "employee", "department": "플랫폼개발팀"},
	"resource": {"id": "/workspace", "data_class": "nonimportant"},
	"tool": {"name": "start_process", "action": "x"},
})

test_old_approval_exception_cannot_bypass_pac if {
    changed := object.union(pac_fixture.facts, {"approval": object.union(pac_fixture.facts.approval, {"data_scopes": []})})
    request := object.union(approval_exception_request, {"pac": {"request": pac_fixture.request, "facts": changed}, "approval": {"granted": true}})
    result := decision with input as request
    result.decision == "Block"
    result.policy_id == "PAC-11"
    result.exception == null
}
