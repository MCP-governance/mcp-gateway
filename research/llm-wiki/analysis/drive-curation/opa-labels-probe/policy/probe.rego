# METADATA
# scope: package
# labels:
#   probe: opa-labels
package probe

import rego.v1

# METADATA
# title: 외부 전송 목적지 확인
# labels:
#   policy_id: POL-26
#   runtime_pac: PAC-12
deny contains "PAC-12" if {
	not pac12
}

pac12 if input.destination in {"approved.example"}

# METADATA
# title: 고위험 건별 승인
# labels:
#   policy_id: POL-27
#   runtime_pac: PAC-13
deny contains "PAC-13" if {
	input.high_risk
	not input.approval_bound
}

# METADATA
# labels:
#   policy_id: POL-22
allow if count(deny) == 0
