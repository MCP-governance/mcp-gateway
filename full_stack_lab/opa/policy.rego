package mcp.authz

# MCP 보안 관리 프레임워크 V1.0 §11(보안통제 자동화 및 PaC 연계) 초안 구현.
#
#   규칙      : 이 파일
#   값        : opa/data.json          (조직이 자주 바꾸는 허용 목적지·길이 제한)
#   관리정보  : opa/policy_ledger.json (§11.8 / §12.5 정책 관리대장)
#   예외      : opa/exceptions.json    (§8 예외 관리대장)
#
# 세 가지가 이 파일 밖에 있는 이유는 수명이 다르기 때문이다. 판단조건은 재검토와
# 재승인을 거쳐 바뀌고, 허용 목적지는 그보다 훨씬 자주 바뀌며, 예외는 기간이 지나면
# 코드 변경 없이 사라져야 한다.
#
# 구조: else 사슬이 아니라 "성립한 후보 전부"를 모으고 관리대장의 priority로 최종
# 판단을 고른다(§11.14). else 사슬은 첫 일치 이후를 볼 수 없어 정책 충돌 자체를
# 관측할 수 없다. 여기서는 진 후보가 conflicts에 남는다.

import rego.v1

# ── 정책 입력 (§11.6) ────────────────────────────────────────────────────────

# 적용환경. 관리대장의 environments와 대조해 정책의 적용 여부를 정한다.
environment := object.get(input, ["environment"], "prod")

# 상황정보(요청 시각). 없으면 undefined가 되어 시간 기반 판단이 성립하지 않는다.
# 조용히 현재 시각으로 대체하면 만료된 예외가 되살아나므로 대체하지 않는다.
now_ns := time.parse_rfc3339_ns(input.now)

recent_calls := object.get(input, ["context", "recent_calls"], 0)

call_limit := object.get(input, ["context", "call_limit"], 1000000000)

recent_important := object.get(input, ["context", "recent_important"], 0)

important_limit := object.get(input, ["context", "important_limit"], 1000000000)

classification_required := object.get(input, ["resource", "classification", "required"], false)

classification_source := object.get(input, ["resource", "classification", "source"], null)

approval_valid_until := object.get(input, ["contract", "approval_valid_until"], null)

# 이용 관계의 전주기 단계. 값이 없는 배포(구버전 Gateway)는 운영 중으로 본다.
# 기본값을 TERMINATING으로 두면 스키마가 아직 안 올라간 순간에 전부 막힌다.
lifecycle_state := object.get(input, ["contract", "lifecycle"], "OPERATING")

# 요청자의 엔드포인트에 보고된 미등록 MCP 설정 수. 게이트웨이를 통과하지 않는
# 경로의 존재를 정책 입력으로 넘긴다. 세는 일은 엔드포인트 평면이, 판단은 정책이.
shadow_endpoints := object.get(input, ["principal", "shadow_endpoints"], 0)

# ── 권한표: 3 역할 x 3 등급 x r/w/x ─────────────────────────────────────────

permissions := {
	"partner": {"public": {"r": true}},
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

classification_missing if {
	classification_source == null
}

classification_missing if {
	classification_source == ""
}

# 조직 축. opa/data.json에서 꺼진 채 배포된다. 입력을 미리 넓혀두지 않으면
# 조직이 켜기로 결정한 날 규칙 전체를 다시 써야 한다.
# 루트 `data` 문서를 참조하면 테스트 패키지까지 의존성 그래프에 들어가 재귀로
# 거부되므로 항상 구체 경로를 쓴다.
default department_scope_enabled := false

department_scope_enabled if {
	data.department_scope.enabled == true
}

cross_department if {
	owner := object.get(input, ["resource", "owner_department"], null)
	owner != null
	object.get(input, ["principal", "department"], null) != owner
}

# ── 필수 입력 누락 (§11.16) ─────────────────────────────────────────────────

missing_inputs contains "principal.role" if not input.principal.role

missing_inputs contains "resource.data_class" if not input.resource.data_class

missing_inputs contains "tool.action" if not input.tool.action

missing_inputs contains "contract" if not input.contract

# 시각은 시간 기반 통제가 걸려 있을 때만 필수다. 없는데 만료를 판단하면
# 만료된 승인이 통과하므로, 그때는 판단하지 않고 차단한다.
missing_inputs contains "now" if {
	approval_valid_until != null
	not input.now
}

# ── 정책 후보 (§11.7 판단 결과) ─────────────────────────────────────────────
#
# 각 후보는 자기 조건만 본다. "앞 규칙이 안 걸렸으니까"에 기대지 않는다.
# 더 제한적인 정책이 이기는 것은 관리대장의 priority가 정한다.

candidate["P-CONTROL-INPUT-001"] := {
	"decision": "Block",
	"reason": "정책 판단에 필요한 입력이 없어 안전한 상태로 차단했습니다.",
	"restrictions": {},
	"conditions": {"matched": [], "violated": [x | some x in missing_inputs]},
} if {
	count(missing_inputs) > 0
}

candidate["MCP-REGISTRY-001"] := {
	"decision": "Block",
	"reason": "등록되었고 활성화된 MCP 서버/도구가 아닙니다.",
	"restrictions": {},
	"conditions": {"matched": [], "violated": ["contract.registered"]},
} if {
	not input.contract.registered
}

candidate["MCP-REGISTRY-002"] := {
	"decision": "Block",
	"reason": "Registry에서 비활성화된 MCP 도구입니다.",
	"restrictions": {},
	"conditions": {"matched": ["contract.registered"], "violated": ["contract.enabled"]},
} if {
	input.contract.registered
	not input.contract.enabled
}

# 전주기의 마지막 통제. 종료 절차에 들어갔거나 폐기된 이용 관계의 호출은 권한을
# 따지기 전에 끊는다. 이 판정이 Registry 비활성(MCP-REGISTRY-002)보다 우선순위가
# 앞선 이유는, 둘이 동시에 성립할 때 감사에 남아야 하는 사실이 "비활성이라 막혔다"가
# 아니라 "폐기된 관계라 막혔다"이기 때문이다. 되돌리는 절차가 서로 다르다.
#
# 그리고 이 차단은 종료 판정의 C3(연속성)을 조직이 자체 증명하는 수단이기도 하다.
# 차단 시각 이후 실행된 호출이 0건이라는 사실은 제공자가 아니라 이 강제 경로가
# 만든다. 그래서 관찰 모드에서도 풀리지 않는다(MCP- 접두사는 항상 집행).
candidate["MCP-DECOMM-001"] := {
	"decision": "Block",
	"reason": "종료·폐기 절차에 들어간 이용 관계입니다. 실행하지 않습니다.",
	"restrictions": {},
	"conditions": {"matched": [], "violated": ["contract.lifecycle"]},
} if {
	lifecycle_state in {"TERMINATING", "RETIRED"}
}

candidate["MCP-SUPPLY-001"] := {
	"decision": "Block",
	"reason": "승인되지 않은 공급자이거나 치명적 공급망 취약점이 있습니다.",
	"restrictions": {},
	"conditions": {"matched": [], "violated": ["contract.supplier_approved"]},
} if {
	not input.contract.supplier_approved
}

candidate["MCP-SUPPLY-001"] := {
	"decision": "Block",
	"reason": "승인되지 않은 공급자이거나 치명적 공급망 취약점이 있습니다.",
	"restrictions": {},
	"conditions": {"matched": [], "violated": ["contract.critical_vulnerabilities"]},
} if {
	input.contract.supplier_approved
	input.contract.critical_vulnerabilities > 0
}

candidate["MCP-CATALOG-001"] := {
	"decision": "Block",
	"reason": "도구 목록, 설명, 스키마 또는 서버 버전이 승인본과 다릅니다.",
	"restrictions": {},
	"conditions": {"matched": [], "violated": catalog_violations},
} if {
	input.contract.registered
	input.contract.enabled
	input.contract.supplier_approved
	input.contract.critical_vulnerabilities == 0
	not contract_ok
}

catalog_violations := sort([field |
	some field in ["schema_hash_match", "description_hash_match", "version_match", "known_tools_only", "metadata_safe"]
	object.get(input, ["contract", field], false) == false
])

candidate["P-APPROVAL-EXPIRY-001"] := {
	"decision": "Block",
	"reason": "도입·사용 승인의 유효기간이 지났습니다. 재승인 전에는 실행할 수 없습니다.",
	"restrictions": {},
	"conditions": {"matched": [], "violated": ["contract.approval_valid_until"]},
} if {
	approval_valid_until != null
	now_ns >= time.parse_rfc3339_ns(approval_valid_until)
}

candidate["P-CLASSIFICATION-001"] := {
	"decision": "Block",
	"reason": "데이터 등급의 관리대장 출처가 없어 기본 차단했습니다.",
	"restrictions": {},
	"conditions": {"matched": [], "violated": ["resource.classification.source"]},
} if {
	classification_required
	classification_missing
}

candidate["P-RATE-001"] := {
	"decision": "Block",
	"reason": "짧은 시간 동안의 호출 수가 상한을 넘었습니다.",
	"restrictions": {},
	"conditions": {"matched": [], "violated": ["context.recent_calls"]},
} if {
	recent_calls >= call_limit
}

candidate["P-333-DENY-001"] := {
	"decision": "Block",
	"reason": "역할·데이터 등급·행위 조합에 권한이 없습니다.",
	"restrictions": {},
	"conditions": {"matched": [], "violated": ["permissions[role][data_class][action]"]},
} if {
	not has_permission
}

candidate["P-X-APPROVAL-001"] := {
	"decision": "Approval",
	"reason": "중요정보 외부 전송 또는 고위험 실행은 10분 이내 승인이 필요합니다.",
	"restrictions": {},
	"conditions": {"matched": ["tool.action=x", "resource.data_class=important"], "violated": ["approval.granted"]},
} if {
	input.tool.action == "x"
	input.resource.data_class == "important"
	not input.approval.granted
}

candidate["P-VOLUME-001"] := {
	"decision": "Approval",
	"reason": "짧은 시간에 중요정보 접근이 몰려 승인이 필요합니다. 단건으로는 정상인 열람도 누적되면 유출 패턴입니다.",
	"restrictions": {},
	"conditions": {"matched": ["resource.data_class=important", "context.recent_important"], "violated": ["approval.granted"]},
} if {
	input.resource.data_class == "important"
	recent_important >= important_limit
	not input.approval.granted
}

candidate["P-DEPT-001"] := {
	"decision": "Approval",
	"reason": "소관 부서가 아닌 중요정보 접근이라 승인이 필요합니다.",
	"restrictions": {},
	"conditions": {"matched": ["resource.owner_department"], "violated": ["principal.department", "approval.granted"]},
} if {
	department_scope_enabled
	input.resource.data_class == "important"
	cross_department
	not input.approval.granted
}

candidate["P-X-RESTRICT-001"] := {
	"decision": "Restrict",
	"reason": "외부 전송은 승인된 목적지와 길이 제한을 적용한 뒤 실행합니다.",
	# 값이지 규칙이 아니다. 조직은 정책의 모양보다 허용 목적지를 훨씬 자주 바꾼다.
	"restrictions": {
		"destination": data.restrictions.external_destination,
		"max_chars": data.restrictions.max_chars,
	},
	"conditions": {"matched": ["tool.action=x", "permissions[role][data_class][action]"], "violated": []},
} if {
	input.tool.action == "x"
	input.resource.data_class != "important"
	has_permission
}

candidate["P-IMPORTANT-ALERT-001"] := {
	"decision": "Alert",
	"reason": "직원의 중요정보 열람은 허용하되 경보와 증적을 남깁니다.",
	"restrictions": {},
	"conditions": {"matched": ["principal.role=employee", "resource.data_class=important"], "violated": []},
} if {
	input.principal.role == "employee"
	input.resource.data_class == "important"
	input.tool.action == "r"
}

# 엔드포인트 평면이 이 요청자의 PC에서 등록되지 않은 MCP 설정을 발견한 상태.
# 호출 자체는 정상이고 막을 근거가 없다 — 막으면 통제가 아니라 연좌다. 다만 이
# 사람에게는 강제 경로를 통과하지 않는 경로가 따로 있으므로, 같은 권한의 같은
# 호출이어도 남겨야 할 증적의 양이 다르다.
candidate["MCP-SHADOW-001"] := {
	"decision": "Alert",
	"reason": "요청자의 엔드포인트에 등록되지 않은 MCP 설정이 보고되어 증적을 강화합니다.",
	"restrictions": {},
	"conditions": {"matched": ["principal.shadow_endpoints"], "violated": []},
} if {
	shadow_endpoints > 0
	has_permission
	contract_ok
}

candidate["P-333-ALLOW-001"] := {
	"decision": "Allow",
	"reason": "333 권한표와 등록 계약을 모두 충족했습니다.",
	"restrictions": {},
	"conditions": {"matched": ["permissions[role][data_class][action]", "contract"], "violated": []},
} if {
	has_permission
	contract_ok
}

# ── 정책 상태·적용환경 필터 (§11.9, §11.12) ─────────────────────────────────
#
# 관리대장이 "운영" 또는 "제한"이라고 말하고, 이 요청의 환경이 정책의 적용환경에
# 들어 있을 때만 집행한다. "중지"된 정책이 계속 집행되면 중지 결정이 기록에만
# 존재하고 실제와 다르다(§11.12 승인된 정책과 실제 배포 정책의 일치).

enforcing_status := {"운영", "제한"}

in_force(pid) if {
	entry := data.policy_ledger[pid]
	entry.status in enforcing_status
	environment in entry.environments
}

active_candidates[pid] := verdict if {
	some pid, verdict in candidate
	in_force(pid)
}

# 관리대장에 아예 없는 정책. §11.8은 정책 코드만으로 목적과 근거를 대신하지 말
# 것을 요구하므로, 관리정보 없는 정책이 판단에 관여하면 통제 실패로 본다.
unregistered_candidates contains pid if {
	some pid, _ in candidate
	not data.policy_ledger[pid]
}

# ── 우선순위 기반 최종 판단 (§11.14) ────────────────────────────────────────

ranked := sort([[data.policy_ledger[pid].priority, pid] |
	some pid, _ in active_candidates
])

selected_id := ranked[0][1]

base_verdict := active_candidates[selected_id]

conflicts := [{
	"policy_id": pid,
	"decision": verdict.decision,
	"priority": data.policy_ledger[pid].priority,
} |
	some pid, verdict in active_candidates
	pid != selected_id
]

# ── 예외 (§8, §11.2) ────────────────────────────────────────────────────────

severity := {"Block": 5, "Approval": 4, "Restrict": 3, "Alert": 2, "Allow": 1}

# §8.6 예외를 허용해서는 안 되는 경우를 그대로 검사한다. 하나라도 어기면 예외가
# 적용되지 않고, 원래 판단이 그대로 집행된다.
valid_exception(exc) if {
	exc.status == "적용"
	is_string(exc.valid_until) # 무기한 예외 금지
	count(object.get(exc, "scope", {})) > 0 # 적용범위 불명확 금지
	count(object.get(exc, "compensating_controls", [])) > 0 # 보완통제 없는 완화 금지
	exc.requested_by != exc.approved_by # 자가 승인 금지
	now_ns >= time.parse_rfc3339_ns(exc.valid_from)
	now_ns < time.parse_rfc3339_ns(exc.valid_until)
}

scope_value("principal_role") := input.principal.role

scope_value("department") := object.get(input, ["principal", "department"], null)

scope_value("tool") := object.get(input, ["tool", "name"], null)

scope_value("action") := input.tool.action

scope_value("resource_id") := object.get(input, ["resource", "id"], null)

scope_value("data_class") := input.resource.data_class

scope_matches(exc) if {
	every key, value in exc.scope {
		scope_value(key) == value
	}
}

# 같은 정책·범위에 유효한 예외가 둘 이상 있는 것은 그 자체로 예외관리 미흡이다.
# 여기서는 대장 순서의 첫 건을 적용하고 나머지는 exception.candidates로 드러낸다.
matching_exceptions := [exc |
	some exc in data.exceptions
	exc.policy_id == selected_id
	data.policy_ledger[selected_id].exceptionable == true
	valid_exception(exc)
	scope_matches(exc)
	severity[exc.effect] < severity[base_verdict.decision] # 예외는 완화만, 강화는 변경관리로
]

applicable_exception := matching_exceptions[0]

exception_verdict := {
	"decision": applicable_exception.effect,
	"reason": sprintf(
		"%s 예외 %s(%s)가 적용되어 %s로 완화했습니다. 유효기간 %s.",
		[
			base_verdict.reason, applicable_exception.id, applicable_exception.title,
			applicable_exception.effect, applicable_exception.valid_until,
		],
	),
	"restrictions": base_verdict.restrictions,
	"conditions": base_verdict.conditions,
}

# ── 실패 안전 (§11.16) ──────────────────────────────────────────────────────

default_verdict := {
	"decision": "Block",
	"reason": "집행 중인 정책 후보가 없어 기본 차단했습니다. 정책 상태·적용환경·입력을 확인하세요.",
	"restrictions": {},
	"conditions": {"matched": [], "violated": ["no-in-force-policy"]},
}

ledger_failure_verdict := {
	"decision": "Block",
	"reason": sprintf("관리대장에 없는 정책이 판단에 관여했습니다: %v", [sort([pid | some pid in unregistered_candidates])]),
	"restrictions": {},
	"conditions": {"matched": [], "violated": ["policy-ledger-missing"]},
}

# ── 판단 결과 조립 (§11.7, §11.17) ──────────────────────────────────────────

obligations(entry, exc) := object.get(entry, "obligations", []) if {
	count(exc) == 0
}

# §8.14는 예외 적용기간의 실제 사용내역과 보완통제 동작을 모니터링하라고 요구한다.
# 예외로 완화된 호출이 원래 정책의 기본 증적만 남기면, 완화됐다는 사실이 통제를
# 가장 많이 필요로 하는 바로 그 호출에서 가장 약한 기록으로 남는다.
obligations(entry, exc) := array.concat(
	array.concat(
		object.get(entry, "obligations", []),
		["evidence.enhanced", "exception.monitored", "alert.security"],
	),
	object.get(exc, "compensating_controls", []),
) if {
	count(exc) > 0
}

exception_view(exc) := null if {
	count(exc) == 0
}

exception_view(exc) := {
	"id": exc.id,
	"title": exc.title,
	"valid_until": exc.valid_until,
	"approved_by": exc.approved_by,
	"compensating_controls": exc.compensating_controls,
	"candidates": count(matching_exceptions),
} if {
	count(exc) > 0
}

enrich(verdict, pid, exc) := object.union(verdict, {
	"policy_id": pid,
	"policy_name": object.get(data.policy_ledger, [pid, "name"], ""),
	"policy_version": object.get(data.policy_ledger, [pid, "version"], "unknown"),
	"policy_status": object.get(data.policy_ledger, [pid, "status"], "unknown"),
	"priority": object.get(data.policy_ledger, [pid, "priority"], 9999),
	"risk_ids": object.get(data.policy_ledger, [pid, "risk_ids"], []),
	"control_ids": object.get(data.policy_ledger, [pid, "control_ids"], []),
	"requirement_ids": object.get(data.policy_ledger, [pid, "requirement_ids"], []),
	"obligations": obligations(object.get(data.policy_ledger, pid, {}), exc),
	"exception": exception_view(exc),
	"conflicts": conflicts,
	"policy_set_version": object.get(data.policy_set, "version", "unknown"),
	"environment": environment,
})

decision := enrich(ledger_failure_verdict, "P-CONTROL-LEDGER-001", {}) if {
	count(unregistered_candidates) > 0
} else := enrich(exception_verdict, selected_id, applicable_exception) if {
	applicable_exception
} else := enrich(base_verdict, selected_id, {}) if {
	selected_id
} else := enrich(default_verdict, "P-CONTROL-DEFAULT-001", {})
