package mcp.authz

import rego.v1

permissions := {
  "customer": {"public": {"r": true}},
  "employee": {"public": {"r": true}, "nonimportant": {"r": true, "w": true}},
  "admin": {
    "public": {"r": true, "w": true, "x": true},
    "nonimportant": {"r": true, "w": true, "x": true},
    "important": {"r": true, "w": true, "x": true},
  },
}

has_permission if {
  permissions[input.principal.role][input.resource.data_class][input.tool.action]
}

decision := {
  "decision": "DENY",
  "policy_id": "MCP-CHANGE-001",
  "reason": "approved tool schema does not match the upstream catalog",
} if {
  not input.contract.schema_hash_match
} else := {
  "decision": "DENY",
  "policy_id": "MCP-CONTRACT-001",
  "reason": "approval contract is not valid",
} if {
  not input.contract.valid
} else := {
  "decision": "ALLOW",
  "policy_id": "P-RBAC-ALLOW-001",
  "reason": "role, data class, and read permission are approved",
} if {
  has_permission
} else := {
  "decision": "DENY",
  "policy_id": "P-RBAC-001",
  "reason": "role lacks read permission for this data class",
}
