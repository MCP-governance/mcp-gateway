# METADATA
# title: 운영 및 변경·폐기 — 운영 중 서버 상태 점검
# description: |
#   호출이 아니라 「운영 중인 서버 목록」 스냅숏을 정기 점검이나 이벤트(업데이트·복원·패키지 변경·설정 변경·
#   사고 확정·제공자 이용 종료)마다 넣어 서버별 위반과 조치를 받는다. 실행기·게이트웨이가 action을
#   등록부 상태에 반영한다(이 패키지는 조치를 실행하지 않는다).
#   입력: input.event, input.servers[], input.facts(now_ns, trusted).
#   데이터: data.pol.package_allowlist, blocked_versions, stop_severities, exceptions.
#   결과: violations = {policy_id, server, action, detail} 집합, decision = 전체를 모은 결과.
# scope: package
package mcp.pol.ops

import data.mcp.pol.lib
import rego.v1

servers := lib.array_or_empty(object.get(input, "servers", []))

event := input.event

hour_ns := ((60 * 60) * 1000) * 1000000

day_ns := 24 * hour_ns

# 조치 → 효과. 사용·배포·전송을 막는 조치는 DENY, 사용 범위를 줄이는 조치는 RESTRICT, 확인 요청은 ALERT.
action_effect := {
	"block": "DENY", "stop": "DENY", "stop_traffic": "DENY", "abort_restore": "DENY", "block_deploy": "DENY",
	"block_egress": "DENY", "revoke": "DENY", "block_transfer": "DENY", "keep_incomplete": "DENY",
	"restrict": "RESTRICT", "mark_unverified": "ALERT",
}

findings contains lib.finding(v.policy_id, object.get(action_effect, v.action, "DENY"), sprintf("%s %s %s", [v.server, v.action, v.detail])) if {
	some v in violations
}

findings contains lib.finding("INPUT_CONTRACT", "DENY", "운영 점검 입력 계약 위반") if not contract_ok

decision := lib.decide(findings)

contract_ok if {
	lib.base_contract_ok
	input.event in {"periodic", "update", "restore", "package_change", "config_change", "incident", "provider_termination"}
	is_array(input.servers)
	every s in input.servers {
		is_string(s.id)
		s.id != ""
	}
}

event_in(names) if event in names

# METADATA
# title: 설정 파일·실행 인자·로그의 평문 인증정보
# description: 평문 검사가 끝나야 하고, 인증정보가 승인 보관소에 있어야 하며, 평문 인증정보가 발견되면 그 설정의 배포를 막는다.
# custom:
#   pol_id: POL-024
#   risk_id: RSK-18
#   checkpoint: 인증정보 발급·설정·로그 기록 시
violations contains {"policy_id": "POL-024", "server": s.id, "action": "block_deploy", "detail": "평문 인증정보 검사 미완료"} if {
	event_in({"periodic", "config_change", "update"})
	some s in servers
	not s.config_scan.status == "completed"
}

violations contains {"policy_id": "POL-024", "server": s.id, "action": "block_deploy", "detail": "평문 검사 결과 목록 없음"} if {
	event_in({"periodic", "config_change", "update"})
	some s in servers
	not plaintext_scan_listed(s)
}

# 무탐지는 빈 배열로 명시해야 한다. 완료 표시만 있고 목록이 없으면 검사했다고 볼 수 없다.
plaintext_scan_listed(s) if is_array(s.config_scan.plaintext_secrets)

violations contains {"policy_id": "POL-024", "server": s.id, "action": "block_deploy", "detail": "승인 보관소 밖의 인증정보"} if {
	event_in({"periodic", "config_change", "update"})
	some s in servers
	not s.config_scan.storage_approved == true
}

violations contains {"policy_id": "POL-024", "server": s.id, "action": "block_deploy", "detail": sprintf("평문 인증정보: %v", [loc])} if {
	event_in({"periodic", "config_change", "update"})
	some s in servers
	plaintext_scan_listed(s)
	some loc in s.config_scan.plaintext_secrets
}

# METADATA
# title: 운영 중 Tool 명세 변경
# description: 관측한 Tool 정의 해시가 승인값과 다르거나 승인 목록에 없는 새 Tool이면 재승인 전까지 그 Tool의 호출을 차단한다. 목록을 관측하지 못하면 서버 단위로 차단한다.
# custom:
#   pol_id: POL-063
#   risk_id: RSK-44
#   checkpoint: Tool 설명·입력·버전 변경 감지 시
violations contains {"policy_id": "POL-063", "server": s.id, "action": "block", "detail": tool_label(t)} if {
	event_in({"periodic", "update"})
	some s in servers
	some t in lib.array_or_empty(object.get(s, "observed_tools", []))
	not tool_approved(s, t)
}

violations contains {"policy_id": "POL-063", "server": s.id, "action": "block", "detail": "Tool 목록 관측 불가"} if {
	event_in({"periodic", "update"})
	some s in servers
	not is_array(object.get(s, "observed_tools", null))
}

tool_approved(s, t) if {
	lib.text(t.contract_sha256)
	s.approved_tools[t.name] == t.contract_sha256
}

# 결과 식별값이 없으면 위반 자체가 사라지므로(lib.rego 작성 규칙) 이름 없는 항목에도 고정 표시를 준다.
tool_label(t) := t.name if lib.text(t.name)

else := "이름 없는 Tool"

# METADATA
# title: 업데이트로 추가·변경된 패키지
# custom:
#   pol_id: POL-068
#   risk_id: RSK-48
#   checkpoint: 패키지 추가·변경·실행 전
violations contains {"policy_id": "POL-068", "server": s.id, "action": "block", "detail": package_label(p)} if {
	event_in({"package_change", "update"})
	some s in servers
	some p in lib.array_or_empty(object.get(s, "packages", []))
	not package_approved(p)
}

package_label(p) := sprintf("%s@%s", [p.name, p.version]) if {
	lib.text(p.name)
	lib.text(p.version)
}

else := "식별 불가 패키지"

violations contains {"policy_id": "POL-068", "server": s.id, "action": "block", "detail": "구성요소 목록 확인 불가"} if {
	event_in({"package_change", "update"})
	some s in servers
	not is_array(object.get(s, "packages", null))
}

package_approved(p) if {
	some a in lib.approved(data.pol.package_allowlist, "POL-068")
	a.name == p.name
	a.source == p.source
	p.version in a.versions
}

# METADATA
# title: 정기 취약점 점검의 완료 기록
# description: 대상 확인을 마치고 취약점마다 악용 여부·심각도·외부 노출·영향 버전·확인 시각이 기록돼야 점검 완료다. 아니면 미확인으로 표시하고 알린다. 기한·사용 제한은 POL-070이 판정한다.
# custom:
#   pol_id: POL-069
#   risk_id: RSK-49
#   checkpoint: 운영 중 MCP 서버·패키지의 정기 취약점 점검 시
violations contains {"policy_id": "POL-069", "server": s.id, "action": "mark_unverified", "detail": "점검 미완료·조회 실패"} if {
	event == "periodic"
	some s in servers
	not s.vuln_scan.status == "completed"
}

violations contains {"policy_id": "POL-069", "server": s.id, "action": "mark_unverified", "detail": "취약점 목록 없음"} if {
	event == "periodic"
	some s in servers
	not is_array(object.get(s, "vulnerabilities", null))
}

violations contains {"policy_id": "POL-069", "server": s.id, "action": "mark_unverified", "detail": sprintf("필수 정보 누락: %v", [vuln_label(v)])} if {
	event == "periodic"
	some s in servers
	some v in lib.array_or_empty(object.get(s, "vulnerabilities", []))
	not vuln_complete(v)
}

severities := {"critical", "high", "medium", "low"}

vuln_complete(v) if {
	lib.text(v.id)
	lib.text(v.affected_version)
	v.severity in severities
	is_boolean(v.exploited)
	is_boolean(v.exposed)
	is_number(v.confirmed_ns)
}

vuln_label(v) := v.id if lib.text(v.id)

else := "식별 불가 항목"

# METADATA
# title: 확인된 취약점의 등급별 조치 기한
# description: |
#   시트 본문의 기한(영향 확인 시각 기준): 실제 악용 중이거나 외부에 노출된 치명 48시간, 그 밖의 치명 14일,
#   높음 30일, 보통 90일, 낮음은 서버에 등록한 다음 정기 변경일. 기한에 도달하면(포함) 사용 차단.
#   패치나 효과가 확인된 제한·격리가 있으면 유지. 등급·확인 시각을 모르면 기한을 셀 수 없으므로 차단한다.
#   기한 연장은 보안 관리자의 시한부 예외(대상 서버, 범위 취약점 ID)로만.
# custom:
#   pol_id: POL-070
#   risk_id: RSK-49
#   checkpoint: 운영 구성요소의 취약점 확인 후
violations contains {"policy_id": "POL-070", "server": s.id, "action": "block", "detail": vuln_label(v)} if {
	event_in({"periodic", "update"})
	some s in servers
	some v in lib.array_or_empty(object.get(s, "vulnerabilities", []))
	not mitigated(v)
	not before_due(v, s)
	not deadline_extended(s, v)
}

mitigated(v) if v.patched == true

mitigated(v) if v.compensating_control.verified == true

deadline_extended(s, v) if lib.exception_for("POL-070", s.id, v.id)

# `not due_ns(v, s) > now`라고 쓰면 기한을 모를 때 규칙이 정의되지 않아 차단을 건너뛴다(lib.rego 끝의 작성 규칙).
before_due(v, s) if {
	due := due_ns(v, s)
	is_number(due)
	due > lib.now
}

due_ns(v, s) := v.confirmed_ns + (48 * hour_ns) if {
	v.severity == "critical"
	actively_exposed(v)
} else := v.confirmed_ns + (14 * day_ns) if {
	v.severity == "critical"
} else := v.confirmed_ns + (30 * day_ns) if {
	v.severity == "high"
} else := v.confirmed_ns + (90 * day_ns) if {
	v.severity == "medium"
} else := s.scheduled_change_ns if {
	v.severity == "low"
}

# 시트: 「실제 악용 중이거나 외부에 노출된」 — 둘 중 하나면 48시간이다.
actively_exposed(v) if v.exploited == true

actively_exposed(v) if v.exposed == true

# METADATA
# title: 서버 인스턴스별 설정
# custom:
#   pol_id: POL-071
#   risk_id: RSK-50
#   checkpoint: 서버 인스턴스 기동·설정 변경 시
violations contains {"policy_id": "POL-071", "server": s.id, "action": "stop_traffic", "detail": instance_label(i)} if {
	event_in({"periodic", "config_change", "update"})
	some s in servers
	some i in lib.array_or_empty(object.get(s, "instances", []))
	not instance_matches(s, i)
}

violations contains {"policy_id": "POL-071", "server": s.id, "action": "stop_traffic", "detail": "인스턴스 관측 불가"} if {
	event_in({"periodic", "config_change", "update"})
	some s in servers
	not is_array(object.get(s, "instances", null))
}

instance_matches(s, i) if {
	lib.text(s.baseline_config_sha256)
	i.config_sha256 == s.baseline_config_sha256
}

instance_label(i) := i.id if lib.text(i.id)

else := "식별 불가 인스턴스"

# METADATA
# title: 이전 버전 복원
# description: 복원 버전이 차단 목록에 없고, 위험 설정이 없고, 유효한 복원 승인이 있어야 복원한다.
# custom:
#   pol_id: POL-072
#   risk_id: RSK-51
#   checkpoint: 이전 버전 복원 시
violations contains {"policy_id": "POL-072", "server": s.id, "action": "abort_restore", "detail": restore_label(s)} if {
	event == "restore"
	some s in servers
	not restore_allowed(s)
}

restore_allowed(s) if {
	r := s.restore
	lib.text(r.version)
	blocked_list_valid(s)
	not version_blocked(s)
	r.risky_settings == []
	lib.approved_entry(r.approval, "POL-072")
}

default blocked_versions := {}

blocked_versions := data.pol.blocked_versions

# 차단 버전 목록이 있는데 배열이 아니면 확인할 수 없다.
blocked_list_valid(s) if not blocked_versions[s.id]

blocked_list_valid(s) if is_array(blocked_versions[s.id])

version_blocked(s) if s.restore.version in blocked_versions[s.id]

restore_label(s) := s.restore.version if lib.text(s.restore.version)

else := "버전 확인 불가"

# METADATA
# title: 서버의 하위 서비스 전송 목적지
# custom:
#   pol_id: POL-074
#   risk_id: RSK-53
#   checkpoint: 서버의 하위 서비스 전송 시
violations contains {"policy_id": "POL-074", "server": s.id, "action": "block_egress", "detail": d} if {
	event_in({"periodic", "update"})
	some s in servers
	some d in lib.array_or_empty(object.get(s, ["downstream", "observed"], []))
	not d in lib.array_or_empty(object.get(s, ["downstream", "approved"], []))
}

violations contains {"policy_id": "POL-074", "server": s.id, "action": "block_egress", "detail": "하위 전송 관측 불가"} if {
	event_in({"periodic", "update"})
	some s in servers
	not is_array(object.get(s, ["downstream", "observed"], null))
}

# METADATA
# title: 업데이트 뒤 실행 권한 확대
# custom:
#   pol_id: POL-075
#   risk_id: RSK-54
#   checkpoint: 업데이트 적용 직후·첫 호출 전
violations contains {"policy_id": "POL-075", "server": s.id, "action": "block", "detail": p} if {
	event == "update"
	some s in servers
	some p in lib.array_or_empty(object.get(s, "observed_permissions", []))
	not p in lib.array_or_empty(object.get(s, "approved_permissions", []))
}

violations contains {"policy_id": "POL-075", "server": s.id, "action": "block", "detail": "실행 권한 관측 불가"} if {
	event == "update"
	some s in servers
	not is_array(object.get(s, "observed_permissions", null))
}

# METADATA
# title: 정기 권한 점검의 회수 대상
# description: 회수 대상으로 확정된 권한은 지금 쓰이는지와 관계없이 자동 회수·사용 차단한다. 계속 써야 하면 자료 소유 부서가 재승인해 회수 확정 목록에서 뺀다.
# custom:
#   pol_id: POL-076
#   risk_id: RSK-54
#   checkpoint: 정기 서버 권한 점검 시
violations contains {"policy_id": "POL-076", "server": s.id, "action": "revoke", "detail": sprintf("%v", [p])} if {
	event == "periodic"
	some s in servers
	some p in lib.array_or_empty(object.get(s, "revoke_confirmed", []))
}

violations contains {"policy_id": "POL-076", "server": s.id, "action": "revoke", "detail": "회수 확정 목록 확인 불가"} if {
	event == "periodic"
	some s in servers
	"revoke_confirmed" in object.keys(s)
	not is_array(s.revoke_confirmed)
}

# METADATA
# title: OAuth·Tool 권한 확대
# description: 관측한 scope·Tool 권한이 승인 범위를 넘으면 재승인 전까지 사용을 막는다.
# custom:
#   pol_id: POL-077
#   risk_id: RSK-55
#   checkpoint: OAuth·Tool 권한 확대 감지 시
violations contains {"policy_id": "POL-077", "server": s.id, "action": "block", "detail": sprintf("%s: %s", [kind, p])} if {
	event_in({"periodic", "update"})
	some s in servers
	some kind in ["oauth_scopes", "tool_permissions"]
	some p in lib.array_or_empty(object.get(s, [kind, "observed"], []))
	not p in lib.array_or_empty(object.get(s, [kind, "approved"], []))
}

violations contains {"policy_id": "POL-077", "server": s.id, "action": "block", "detail": sprintf("%s 관측 불가", [kind])} if {
	event_in({"periodic", "update"})
	some s in servers
	some kind in ["oauth_scopes", "tool_permissions"]
	not observed_listed(s, kind)
}

observed_listed(s, kind) if is_array(s[kind].observed)

# METADATA
# title: 심각한 미승인 변경·비정상 호출의 즉시 중지
# description: 확정된 사고의 심각도가 중지 기준(data.pol.stop_severities)에 들면 해당 서버(또는 Tool)를 즉시 중지한다.
# custom:
#   pol_id: POL-081
#   risk_id: RSK-57
#   checkpoint: 심각한 미승인 변경·비정상 호출 확정 시
violations contains {"policy_id": "POL-081", "server": s.id, "action": "stop", "detail": object.get(i, "tool", "서버 전체")} if {
	event_in({"incident", "periodic"})
	some s in servers
	some i in lib.array_or_empty(object.get(s, "incidents", []))
	i.confirmed == true
	i.severity in stop_severities
}

# 중지 기준을 정하지 않았으면 치명만 즉시 중지한다.
default stop_severities := ["critical"]

stop_severities := data.pol.stop_severities

# METADATA
# title: 외부 제공자 이용 종료의 완료 표시
# description: 제공자의 삭제·반환 증빙이 확인되고 새 자료 전송이 막혀 있어야 폐기 완료로 표시한다. 새 전송이 막혀 있지 않으면 전송을 차단한다.
# custom:
#   pol_id: POL-088
#   risk_id: RSK-64
#   checkpoint: 외부 제공자 이용 종료 시
violations contains {"policy_id": "POL-088", "server": s.id, "action": "keep_incomplete", "detail": "삭제 증빙 미확인 또는 새 전송 차단 미확인"} if {
	event == "provider_termination"
	some s in servers
	s.provider_termination.requested_complete == true
	not termination_evidenced(s)
}

violations contains {"policy_id": "POL-088", "server": s.id, "action": "block_transfer", "detail": "이용 종료 제공자로의 새 전송"} if {
	event == "provider_termination"
	some s in servers
	not s.provider_termination.new_transfer_blocked == true
}

termination_evidenced(s) if {
	s.provider_termination.evidence_verified == true
	s.provider_termination.new_transfer_blocked == true
}
