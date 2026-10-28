# METADATA
# title: 운영 및 변경·폐기 — 상태 점검
# description: |
#   호출이 아니라 「운영 중인 서버 목록」 스냅숏을 주기·이벤트마다 넣어 위반 서버와 조치를 받는다.
#   게이트웨이·작업자는 결과의 action(restrict/block/stop)을 등록부 상태로 반영한다.
package mcp.pol.ops

import data.mcp.pol.lib
import rego.v1

hour_ns := ((60 * 60) * 1000) * 1000000

day_ns := 24 * hour_ns

# POL-069 등급별 조치 기한(확인 시각 기준). 낮은 위험은 기한이 아니라 서버에 등록한 정기 변경일이다.
due_ns(v, s) := v.confirmed_ns + (48 * hour_ns) if {
	v.exploited == true
	v.exposed == true
	v.severity == "critical"
} else := v.confirmed_ns + (14 * day_ns) if {
	v.severity in {"critical", "high"}
} else := v.confirmed_ns + (30 * day_ns) if {
	v.severity == "medium"
} else := v.confirmed_ns + (90 * day_ns) if {
	v.severity == "low_actionable"
} else := s.scheduled_change_ns if {
	v.severity == "low"
}

# METADATA
# title: 취약점 등급별 조치 기한
# description: 패치 또는 효과가 확인된 제한·격리 조치가 있으면 유지, 기한(포함) 지나면 차단, 값을 모르면 차단.
# custom:
#   pol_id: [POL-068, POL-069]
#   risk_id: RSK-49
violations contains {"policy_id": "POL-069", "server": s.id, "action": "block", "vuln": v.id} if {
	some s in input.servers
	some v in s.vulnerabilities
	not mitigated(v)
	not before_due(v, s)
	not lib.exception_for("POL-069", s.id, v.id)
}

# `not due_ns(v, s) > now`라고 쓰면 OPA가 함수 호출을 not 밖으로 끌어내, 기한을 모를 때 규칙 전체가
# 정의되지 않음이 되어 차단을 건너뛴다(fail-open). 보조 규칙으로 감싸야 「모르면 차단」이 된다.
before_due(v, s) if due_ns(v, s) > input.facts.now_ns

mitigated(v) if v.patched == true

mitigated(v) if v.compensating_control.verified == true

# METADATA
# title: Tool 정의 변경 감지
# description: 승인값과 다른 해시, 승인 목록에 없는 새 Tool 모두 제한한다.
# custom:
#   pol_id: POL-062
#   risk_id: RSK-44
violations contains {"policy_id": "POL-062", "server": s.id, "action": "restrict", "tool": t.name} if {
	some s in input.servers
	some t in s.observed_tools
	not tool_approved(s, t)
}

tool_approved(s, t) if s.approved_tools[t.name] == t.contract_sha256

# METADATA
# title: 업데이트 뒤 권한 확대
# custom:
#   pol_id: [POL-074, POL-076]
#   risk_id: [RSK-54, RSK-55]
violations contains {"policy_id": "POL-074", "server": s.id, "action": "block", "permission": p} if {
	some s in input.servers
	some p in s.observed_permissions
	not p in s.approved_permissions
}

# METADATA
# title: 백업 복원 뒤 승인·폐기 목록 재대조
# description: 폐기된 서버가 돌아오거나, 현재 승인 등록부와 주소·권한이 다른 서버가 돌아오면 멈춘다.
# custom:
#   pol_id: POL-089
#   risk_id: RSK-66
violations contains {"policy_id": "POL-089", "server": s.id, "action": "stop"} if {
	input.event == "restored"
	some s in input.servers
	s.id in data.decommissioned
}

violations contains {"policy_id": "POL-089", "server": s.id, "action": "stop"} if {
	input.event == "restored"
	some s in input.servers
	not restored_matches_registry(s)
}

restored_matches_registry(s) if {
	r := data.registry[s.id]
	r.address == s.address
	every p in s.observed_permissions { p in r.permissions }
}
