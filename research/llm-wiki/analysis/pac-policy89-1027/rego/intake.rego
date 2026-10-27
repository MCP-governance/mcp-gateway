# METADATA
# title: 도입 검토 게이트
# description: |
#   MCP 서버 도입 신청 한 건을 판정한다. 결과는 proceed(다음 단계)·block·manual(보안 관리자 판단 대기).
#   검사가 끝나지 않았거나 결과가 없으면 통과가 아니라 차단이다(시트 판정 원칙: 필수값 누락·검증 실패 시 차단).
package mcp.pol.intake

import data.mcp.pol.lib
import rego.v1

app := input.application

# METADATA
# title: 제공자·공식 배포 주소 승인 목록 대조
# custom:
#   pol_id: POL-001
#   risk_id: RSK-01
#   checkpoint: 서버·설치 파일 등록 전
findings contains {"policy_id": "POL-001", "effect": "block", "reason": "미승인·만료 제공자 또는 배포 주소"} if {
	not provider_approved
	not lib.exception_for("POL-001", app.provider, app.source_url)
}

provider_approved if {
	some p in lib.active(data.providers)
	p.provider == app.provider
	app.source_url in p.official_urls
}

# METADATA
# title: Tool 설명 위험 문구
# description: 금지 문구는 거부, 불분명은 보안 관리자 판단 대기, 검사 미완료는 차단.
# custom:
#   pol_id: POL-004
#   risk_id: RSK-04
findings contains {"policy_id": "POL-004", "effect": "block", "reason": concat(": ", ["설명 검사 미완료", t.name])} if {
	some t in app.tools
	not t.description_scan.status == "completed"
}

findings contains {"policy_id": "POL-004", "effect": "block", "reason": concat(": ", ["금지 문구", t.name])} if {
	some t in app.tools
	some f in t.description_scan.findings
	f.level == "forbidden"
}

findings contains {"policy_id": "POL-004", "effect": "block", "reason": concat(": ", ["알 수 없는 판정", t.name])} if {
	some t in app.tools
	some f in t.description_scan.findings
	not f.level in {"forbidden", "unclear"}
}

findings contains {"policy_id": "POL-004", "effect": "manual", "reason": concat(": ", ["위험 불분명", t.name])} if {
	some t in app.tools
	some f in t.description_scan.findings
	f.level == "unclear"
}

# METADATA
# title: 예상 출력 정의와 시험 호출
# description: 정의가 있고, 시험 호출이 한 번 이상 있었고, 관측한 동작·자료 범위가 선언과 같아야 한다.
# custom:
#   pol_id: [POL-005, POL-006]
#   risk_id: RSK-05
findings contains {"policy_id": "POL-005", "effect": "block", "reason": concat(": ", ["출력 정의 없음", t.name])} if {
	some t in app.tools
	count(lib.missing(object.get(t, "output_contract", {}), ["fields", "data_scope"])) > 0
}

findings contains {"policy_id": "POL-005", "effect": "block", "reason": concat(": ", ["범위 밖 자료", t.name])} if {
	some t in app.tools
	some r in t.trial_results
	some field in r.observed_fields
	not field in t.output_contract.fields
}

findings contains {"policy_id": "POL-006", "effect": "block", "reason": concat(": ", ["시험 호출 없음", t.name])} if {
	some t in app.tools
	count(object.get(t, "trial_results", [])) == 0
}

findings contains {"policy_id": "POL-006", "effect": "block", "reason": concat(": ", ["시험 결과 불일치", t.name])} if {
	some t in app.tools
	some r in t.trial_results
	r.observed_effect != t.declared_effect
}

# METADATA
# title: 민감 작업 Tool의 사용자 확인 대상 표시
# description: 선언된 작업이든 시험에서 관측된 작업이든 삭제·공유·외부 전송이면 확인 대상이어야 한다.
# custom:
#   pol_id: POL-010
#   risk_id: RSK-09
sensitive := {"delete", "share", "external_send"}

findings contains {"policy_id": "POL-010", "effect": "block", "reason": concat(": ", ["확인 대상 미표시", t.name])} if {
	some t in app.tools
	tool_is_sensitive(t)
	not t.requires_confirmation == true
}

tool_is_sensitive(t) if t.declared_effect in sensitive

tool_is_sensitive(t) if {
	some r in t.trial_results
	r.observed_effect in sensitive
}

# METADATA
# title: 요구사항 문서 필수 4항목
# custom:
#   pol_id: POL-011
#   risk_id: RSK-02
findings contains {"policy_id": "POL-011", "effect": "block", "reason": concat(", ", sort(gaps))} if {
	gaps := lib.missing(object.get(app, "requirements", {}), ["functions", "data_types", "permissions", "acceptance_criteria"])
	count(gaps) > 0
}

# Tool이 하나도 없는 신청은 위 Tool별 검사를 모두 비켜 간다.
findings contains {"policy_id": "POL-011", "effect": "block", "reason": "Tool 목록 없음"} if {
	count(object.get(app, "tools", [])) == 0
}

ids(effect) := sort({f.policy_id | some f in findings; f.effect == effect})

# block > manual > proceed. manual은 「차단 상태에서 보안 관리자가 판단」이므로 진행시키지 않는다.
default decision := {"result": "proceed", "policy_ids": []}

decision := {"result": "block", "policy_ids": ids("block")} if count(ids("block")) > 0

decision := {"result": "manual", "policy_ids": ids("manual")} if {
	count(ids("block")) == 0
	count(ids("manual")) > 0
}
