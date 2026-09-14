package mcp.authz

import rego.v1

# 잠정 확정안: 3 roles x 3 data classes x r/w/x.
permissions := {
  "customer": {
    "public": {"r": true},
  },
  "employee": {
    "public": {"r": true},
    "nonimportant": {"r": true, "w": true},
    "important": {"r": true},
  },
  "admin": {
    "public": {"r": true, "w": true, "x": true},
    "nonimportant": {"r": true, "w": true, "x": true},
    "important": {"r": true, "w": true, "x": true},
  },
}

has_permission if {
  permissions[input.principal.role][input.resource.data_class][input.tool.action]
}

# The gateway measures, the policy decides. Defaults are deliberately unreachable so
# an input without context (the 27-cell matrix preview, a unit test) behaves exactly
# as before rather than silently gaining a new control.
recent_calls := object.get(input, ["context", "recent_calls"], 0)
call_limit := object.get(input, ["context", "call_limit"], 1000000000)
recent_important := object.get(input, ["context", "recent_important"], 0)
important_limit := object.get(input, ["context", "important_limit"], 1000000000)
classification_required := object.get(input, ["resource", "classification", "required"], false)
classification_source := object.get(input, ["resource", "classification", "source"], null)

classification_missing if {
  classification_source == null
}

classification_missing if {
  classification_source == ""
}

# The organisational axis. Ships disabled in opa/data.json: widening the input is what
# avoids a rewrite later, turning it on is a tenant's decision.
# Reference the concrete path, never the root `data` document: object.get(data, ...)
# pulls every package into the rule's dependency graph, including the test package,
# and OPA rejects the whole policy as recursive.
default department_scope_enabled := false

department_scope_enabled if {
  data.department_scope.enabled == true
}

cross_department if {
  owner := object.get(input, ["resource", "owner_department"], null)
  owner != null
  object.get(input, ["principal", "department"], null) != owner
}

contract_ok if {
  input.contract.registered
  input.contract.enabled
  input.contract.schema_hash_match
  input.contract.description_hash_match
  input.contract.version_match
  input.contract.known_tools_only
  input.contract.metadata_safe
  input.contract.supplier_approved
  input.contract.critical_vulnerabilities == 0
}

decision := {
  "decision": "Block",
  "policy_id": "MCP-REGISTRY-001",
  "reason": "등록되었고 활성화된 MCP 서버/도구가 아닙니다.",
  "restrictions": {},
} if {
  not input.contract.registered
} else := {
  "decision": "Block",
  "policy_id": "MCP-REGISTRY-002",
  "reason": "Registry에서 비활성화된 MCP 도구입니다.",
  "restrictions": {},
} if {
  not input.contract.enabled
} else := {
  "decision": "Block",
  "policy_id": "MCP-SUPPLY-001",
  "reason": "승인되지 않은 공급자이거나 치명적 공급망 취약점이 있습니다.",
  "restrictions": {},
} if {
  not input.contract.supplier_approved
} else := {
  "decision": "Block",
  "policy_id": "MCP-SUPPLY-001",
  "reason": "승인되지 않은 공급자이거나 치명적 공급망 취약점이 있습니다.",
  "restrictions": {},
} if {
  input.contract.critical_vulnerabilities > 0
} else := {
  "decision": "Block",
  "policy_id": "MCP-CATALOG-001",
  "reason": "도구 목록, 설명, 스키마 또는 서버 버전이 승인본과 다릅니다.",
  "restrictions": {},
} if {
  not contract_ok
} else := {
  "decision": "Block",
  "policy_id": "P-CLASSIFICATION-001",
  "reason": "데이터 등급의 관리대장 출처가 없어 기본 차단했습니다.",
  "restrictions": {},
} if {
  classification_required
  classification_missing
} else := {
  "decision": "Block",
  "policy_id": "P-RATE-001",
  "reason": "짧은 시간 동안의 호출 수가 상한을 넘었습니다.",
  "restrictions": {},
} if {
  recent_calls >= call_limit
} else := {
  "decision": "Block",
  "policy_id": "P-333-DENY-001",
  "reason": "역할·데이터 등급·행위 조합에 권한이 없습니다.",
  "restrictions": {},
} if {
  not has_permission
} else := {
  "decision": "Approval",
  "policy_id": "P-X-APPROVAL-001",
  "reason": "중요정보 외부 전송 또는 고위험 실행은 10분 이내 승인이 필요합니다.",
  "restrictions": {},
} if {
  input.tool.action == "x"
  input.resource.data_class == "important"
  not input.approval.granted
} else := {
  "decision": "Approval",
  "policy_id": "P-VOLUME-001",
  "reason": "짧은 시간에 중요정보 접근이 몰려 승인이 필요합니다. 단건으로는 정상인 열람도 누적되면 유출 패턴입니다.",
  "restrictions": {},
} if {
  input.resource.data_class == "important"
  recent_important >= important_limit
  not input.approval.granted
} else := {
  "decision": "Approval",
  "policy_id": "P-DEPT-001",
  "reason": "소관 부서가 아닌 중요정보 접근이라 승인이 필요합니다.",
  "restrictions": {},
} if {
  department_scope_enabled
  input.resource.data_class == "important"
  cross_department
  not input.approval.granted
} else := {
  "decision": "Restrict",
  "policy_id": "P-X-RESTRICT-001",
  "reason": "외부 전송은 승인된 목적지와 길이 제한을 적용한 뒤 실행합니다.",
  # Values, not rules: an organisation changes its allowed destination far more often
  # than it changes the shape of the policy. They live in opa/data.json.
  "restrictions": {
    "destination": data.restrictions.external_destination,
    "max_chars": data.restrictions.max_chars,
  },
} if {
  input.tool.action == "x"
  input.resource.data_class != "important"
} else := {
  "decision": "Alert",
  "policy_id": "P-IMPORTANT-ALERT-001",
  "reason": "직원의 중요정보 열람은 허용하되 경보와 증적을 남깁니다.",
  "restrictions": {},
} if {
  input.principal.role == "employee"
  input.resource.data_class == "important"
  input.tool.action == "r"
} else := {
  "decision": "Allow",
  "policy_id": "P-333-ALLOW-001",
  "reason": "333 권한표와 등록 계약을 모두 충족했습니다.",
  "restrictions": {},
} if {
  has_permission
}
