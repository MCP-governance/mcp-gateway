package mcp.authz_test

import data.mcp.authz.decision
import rego.v1

base := {
  "principal": {"role": "customer"},
  "resource": {"data_class": "public"},
  "tool": {"action": "r"},
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

test_allow if {
  decision with input as base == {"decision": "Allow", "policy_id": "P-333-ALLOW-001", "reason": "333 권한표와 등록 계약을 모두 충족했습니다.", "restrictions": {}}
}

test_alert_employee_important_read if {
  input2 := object.union(base, {"principal": {"role": "employee"}, "resource": {"data_class": "important"}})
  result := decision with input as input2
  result.decision == "Alert"
}

test_block_customer_write if {
  input2 := object.union(base, {"tool": {"action": "w"}})
  result := decision with input as input2
  result.decision == "Block"
}

test_approval_admin_important_x if {
  input2 := object.union(base, {"principal": {"role": "admin"}, "resource": {"data_class": "important"}, "tool": {"action": "x"}})
  result := decision with input as input2
  result.decision == "Approval"
}

test_approved_admin_important_x if {
  input2 := object.union(base, {"principal": {"role": "admin"}, "resource": {"data_class": "important"}, "tool": {"action": "x"}, "approval": {"granted": true}})
  result := decision with input as input2
  result.decision == "Allow"
}

test_restrict_admin_public_x if {
  input2 := object.union(base, {"principal": {"role": "admin"}, "tool": {"action": "x"}})
  result := decision with input as input2
  result.decision == "Restrict"
}

test_block_description_drift if {
  bad_contract := object.union(base.contract, {"description_hash_match": false})
  input2 := object.union(base, {"contract": bad_contract})
  result := decision with input as input2
  result.policy_id == "MCP-CATALOG-001"
}
