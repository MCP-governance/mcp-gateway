# METADATA
# title: 정책 실행 규칙 공통 원칙
# description: 모든 허용 목록·예외는 정책 ID·대상·범위·종료일·승인 주체를 가지며 만료 항목은 조회에서 빠진다.
package mcp.pol.lib

import rego.v1

# 유효한(종료일 전) 항목만 남긴다. 종료일이 없는 항목은 인정하지 않는다(POL-013 「종료일이 없는 승인은 허용하지 않는다」).
active(entries) := [e |
	some e in entries
	is_number(e.not_after_ns)
	input.facts.now_ns < e.not_after_ns
]

# 시트는 예외의 최종 승인 주체를 정책마다 정한다(보안 관리자 / 자료 소유 부서).
approver_role := {
	"POL-001": "security_admin",
	"POL-002": "data_owner",
	"POL-069": "security_admin",
}

# 예외는 정책 ID·대상·범위가 정확히 맞고, 정한 주체가 승인했고, 기간 안일 때만 적용된다.
# 범위를 보지 않으면 제공자 하나의 예외가 그 제공자의 아무 주소나 통과시킨다.
exception_for(pol_id, target, scope_item) if {
	some e in active(data.exceptions)
	e.policy_id == pol_id
	e.target == target
	scope_item in e.scope
	e.status == "approved"
	e.approved_by_role == approver_role[pol_id]
}

# 판정에 필요한 값이 없거나 비어 있으면 「확인 불가」 — 각 정책은 이를 차단으로 다룬다(판정 원칙: 필수값 누락 시 현재 요청 차단).
missing(obj, keys) := {k | some k in keys; not filled(obj, k)}

filled(obj, k) if {
	v := obj[k]
	v != null
	v != ""
	v != []
	v != {}
}
