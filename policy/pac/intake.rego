# METADATA
# title: 도입 검토 — MCP 서버 도입 신청 한 건
# description: |
#   검사 시점: 서버·설치 파일 등록 전, Tool 도입·기능 변경 심사, 신규 MCP 서버 도입 승인 전.
#   입력: input.application(신청서·격리 시험 결과·구성요소 목록), input.facts(now_ns, trusted).
#   데이터: data.pol.providers, data.pol.package_allowlist, data.pol.data_types, data.pol.exceptions.
#   결과: decision = {effect, policy_ids, reasons}. 모든 검사를 통과하면 ALLOW(시트의 자동 승인 — 다음 단계 진행).
#   MANUAL은 보안 관리자 판단 전까지 등록하지 않는다는 뜻이다.
# scope: package
package mcp.pol.intake

import data.mcp.pol.lib
import rego.v1

app := input.application

tools := lib.array_or_empty(object.get(app, "tools", []))

known_effects := {"read", "write", "delete", "share", "external_send", "execute"}

sensitive_effects := {"delete", "share", "external_send"}

decision := lib.decide(findings)

# METADATA
# title: 입력 계약
# description: 신청 ID와 운영 형태를 모르면 어떤 정책도 판정할 수 없다.
findings contains lib.finding("INPUT_CONTRACT", "DENY", "도입 신청 입력 계약 위반") if not contract_ok

contract_ok if {
	lib.base_contract_ok
	is_object(app)
	is_string(app.id)
	app.id != ""
	app.hosting in {"external", "local", "gateway_managed"}

	# 이유 문자열(sprintf)에 쓰는 식별값이 없으면 그 규칙 전체가 정의되지 않아 차단이 빠진다.
	every t in tools {
		is_string(t.name)
		t.name != ""
	}
	every p in lib.array_or_empty(object.get(app, "packages", [])) {
		is_string(p.name)
		is_string(p.version)
	}
}

# METADATA
# title: 제공자·공식 배포 주소 승인 목록 대조
# description: 제공자와 공식 배포 주소가 승인 목록 항목과 모두 일치해야 다음 심사로 간다. 새 제공자·배포 주소는 보안 관리자가 대상·범위·종료일을 정해 목록에 올린다(그 전에는 차단 — 실행 중 면제 없음).
# custom:
#   pol_id: POL-001
#   risk_id: RSK-01
#   checkpoint: 서버·설치 파일 등록 전
findings contains lib.finding("POL-001", "DENY", "미승인·만료 제공자 또는 배포 주소") if {
	not provider_approved
}

provider_approved if {
	some p in lib.approved(data.pol.providers, "POL-001")
	p.provider == app.provider
	app.source_url in p.official_urls
}

# METADATA
# title: Tool 기능·자료·권한 분류와 승인 업무 범위
# description: 각 Tool의 기능(작업 유형)·자료 유형·요청 권한이 분류돼 있고 승인된 업무 범위에 모두 들어야 한다. 분류 체계(data.pol.data_types) 밖의 자료 유형은 미분류로 본다.
# custom:
#   pol_id: POL-002
#   risk_id: RSK-02
#   checkpoint: Tool 도입·기능 변경 심사
findings contains lib.finding("POL-002", "DENY", sprintf("미분류이거나 승인 업무 범위 밖: %s", [t.name])) if {
	some t in tools
	not tool_in_business_scope(t)
}

tool_in_business_scope(t) if {
	scope := app.business_scope
	t.declared_effect in known_effects
	t.declared_effect in scope.operations
	is_array(t.data_types)
	count(t.data_types) > 0
	every d in t.data_types {
		d in data.pol.data_types
		d in scope.data_types
	}
	lib.subset(t.permissions, scope.permissions)
}

# METADATA
# title: Tool 설명의 위험 문구
# description: 검사가 끝나지 않았거나 판정이 알 수 없는 값이면 차단, 금지 문구는 도입 거부, 불분명하면 보안 관리자 판단(MANUAL). 이 검사만으로 최종 승인하지 않는다.
# custom:
#   pol_id: POL-004
#   risk_id: RSK-04
#   checkpoint: 신규 MCP 서버 도입 승인 전
findings contains lib.finding("POL-004", "DENY", sprintf("설명 검사 미완료: %s", [t.name])) if {
	some t in tools
	not t.description_scan.status == "completed"
}

findings contains lib.finding("POL-004", "DENY", sprintf("설명 검사 결과 목록 없음: %s", [t.name])) if {
	some t in tools
	not scan_findings_listed(t)
}

# 무탐지는 빈 배열로 명시해야 한다. 완료 표시만 있고 목록이 없으면 검사했다고 볼 수 없다.
scan_findings_listed(t) if is_array(t.description_scan.findings)

findings contains lib.finding("POL-004", "DENY", sprintf("금지 문구: %s", [t.name])) if {
	some t in tools
	some f in t.description_scan.findings
	f.level == "forbidden"
}

findings contains lib.finding("POL-004", "DENY", sprintf("알 수 없는 설명 검사 판정: %s", [t.name])) if {
	some t in tools
	some f in t.description_scan.findings
	not object.get(f, "level", null) in {"forbidden", "unclear"}
}

findings contains lib.finding("POL-004", "MANUAL", sprintf("위험 문구 불분명 — 보안 관리자 판단: %s", [t.name])) if {
	some t in tools
	some f in t.description_scan.findings
	f.level == "unclear"
}

# METADATA
# title: 예상 출력 형식·반환 자료 범위
# description: 출력 정의(반환 항목 목록·자료 범위)가 있어야 하고, 시험 결과의 항목·자료 범위가 정의 밖이거나 민감정보가 나오면 차단한다.
# custom:
#   pol_id: POL-005
#   risk_id: RSK-05
#   checkpoint: 신규 MCP 서버 도입 승인 전
findings contains lib.finding("POL-005", "DENY", sprintf("출력 정의 없음: %s", [t.name])) if {
	some t in tools
	not output_contract_defined(t)
}

output_contract_defined(t) if {
	c := t.output_contract
	is_array(c.fields)
	count(c.fields) > 0
	every f in c.fields {
		lib.text(f)
	}
	count(scope_set(c.data_scope)) > 0
}

# 자료 범위는 한 값("public")이나 값 목록(["public", "internal"])이다. 빈 값·다른 타입은 빈 집합.
scope_set(v) := {v} if lib.text(v)

scope_set(v) := {x | some x in v} if {
	is_array(v)
	every x in v {
		lib.text(x)
	}
}

scope_set(v) := set() if {
	not lib.text(v)
	not text_array(v)
}

text_array(v) if {
	is_array(v)
	every x in v {
		lib.text(x)
	}
}

findings contains lib.finding("POL-005", "DENY", sprintf("시험 결과의 자료 범위가 정의와 다름: %s", [t.name])) if {
	some t in tools
	some r in lib.array_or_empty(object.get(t, "trial_results", []))
	not trial_scope_matches(t, r)
}

trial_scope_matches(t, r) if {
	observed := scope_set(r.observed_data_scope)
	count(observed) > 0
	observed - scope_set(t.output_contract.data_scope) == set()
}

findings contains lib.finding("POL-005", "DENY", sprintf("시험 결과에 정의 밖 항목: %s", [t.name])) if {
	some t in tools
	some r in lib.array_or_empty(object.get(t, "trial_results", []))
	some field in lib.array_or_empty(r.observed_fields)
	not field in lib.array_or_empty(object.get(object.get(t, "output_contract", {}), "fields", []))
}

findings contains lib.finding("POL-005", "DENY", sprintf("시험 결과의 반환 항목 확인 불가: %s", [t.name])) if {
	some t in tools
	some r in lib.array_or_empty(object.get(t, "trial_results", []))
	not is_array(object.get(r, "observed_fields", null))
}

findings contains lib.finding("POL-005", "DENY", sprintf("시험 결과에 민감정보: %s", [t.name])) if {
	some t in tools
	some r in lib.array_or_empty(object.get(t, "trial_results", []))
	not r.sensitive_found == false
}

# METADATA
# title: 도입 전 시험 호출과 실제 동작
# description: 필수 시험 호출이 한 번 이상 있어야 하고, 관측한 조회·변경·전송이 선언한 기능과 같아야 한다. 예외 없음 — 불일치면 정의를 고쳐 재시험한다.
# custom:
#   pol_id: POL-006
#   risk_id: RSK-05
#   checkpoint: 신규 MCP 서버 도입 승인 전
findings contains lib.finding("POL-006", "DENY", sprintf("시험 호출 없음: %s", [t.name])) if {
	some t in tools
	count(lib.array_or_empty(object.get(t, "trial_results", []))) == 0
}

findings contains lib.finding("POL-006", "DENY", sprintf("선언과 다른 실제 동작: %s", [t.name])) if {
	some t in tools
	some r in lib.array_or_empty(object.get(t, "trial_results", []))
	not r.observed_effect == t.declared_effect
}

# METADATA
# title: 외부 서버 제공자의 자료 처리 조건
# description: 조건이 확인되고 금지 기준에 해당하지 않으면 통과, 금지 기준이면 차단. 조건 미확인이면 게이트웨이가 내부자료·개인정보·인증정보를 막고 공개자료 조회만 강제할 수 있을 때만 제한 허용한다.
# custom:
#   pol_id: POL-009
#   risk_id: RSK-08
#   checkpoint: 외부 서버 도입 전·처리 조건 변경 시
findings contains lib.finding("POL-009", "DENY", "제공자 처리 조건이 금지 기준") if {
	app.hosting == "external"
	app.provider_terms.status == "verified"
	not app.provider_terms.prohibited == false
}

# 새 제공자 처리 기준은 보안 관리자가 승인해 provider_terms에 반영한다. 예외로 제한을 건너뛰지 않는다.
findings contains lib.finding("POL-009", "RESTRICT", "제공자 조건 미확인 — 공개자료 조회만 허용") if {
	app.hosting == "external"
	not app.provider_terms.status == "verified"
	gateway_limits_enforced
}

findings contains lib.finding("POL-009", "DENY", "제공자 조건 미확인이고 내부자료 전달을 막을 수 없음") if {
	app.hosting == "external"
	not app.provider_terms.status == "verified"
	not gateway_limits_enforced
}

gateway_limits_enforced if {
	c := app.gateway_controls
	c.internal_data_blocked == true
	c.personal_data_blocked == true
	c.credentials_blocked == true
	c.public_read_only == true
}

# METADATA
# title: 삭제·공유·외부 전송 기능의 사용자 확인 대상 분류(등록 단계)
# description: 선언한 기능이든 시험에서 관측한 기능이든 삭제·공유·외부 전송이면 사용자 확인 대상으로 분류돼야 등록한다. 실행 단계의 확인은 call 패키지의 POL-010·053·054가 본다.
# custom:
#   pol_id: POL-010
#   risk_id: RSK-09
#   checkpoint: 삭제·공유·외부 전송 Tool 등록 시
findings contains lib.finding("POL-010", "DENY", sprintf("민감 기능이 사용자 확인 대상으로 분류되지 않음: %s", [t.name])) if {
	some t in tools
	tool_is_sensitive(t)
	not t.requires_confirmation == true
}

tool_is_sensitive(t) if t.declared_effect in sensitive_effects

tool_is_sensitive(t) if {
	some r in lib.array_or_empty(object.get(t, "trial_results", []))
	r.observed_effect in sensitive_effects
}

# METADATA
# title: 요구사항 문서 필수 항목
# description: 기능·처리 가능 자료·필요 권한·승인 기준 네 항목이 모두 글로 기록돼 있어야 하고(false·0은 기록이 아님), Tool이 하나도 없는 신청은 다른 Tool 검사를 비켜 가므로 차단한다.
# custom:
#   pol_id: POL-011
#   risk_id: RSK-02
#   checkpoint: 신규 MCP 서버 도입 승인 전
findings contains lib.finding("POL-011", "DENY", concat(", ", sort(gaps))) if {
	gaps := lib.unwritten(object.get(app, "requirements", {}), ["functions", "data_types", "permissions", "acceptance_criteria"])
	count(gaps) > 0
}

findings contains lib.finding("POL-011", "DENY", "Tool 목록 없음") if count(tools) == 0

# METADATA
# title: 패키지 제공처·버전 승인 목록
# description: 구성요소 목록(SBOM) 확인이 끝나고 목록이 있어야 하며, 모든 패키지가 승인 목록의 제공처·버전과 일치해야 한다. 새 제공처·버전은 보안 관리자가 목록에 올린다.
# custom:
#   pol_id: POL-068
#   risk_id: RSK-48
#   checkpoint: 패키지 추가·변경·실행 전
findings contains lib.finding("POL-068", "DENY", "구성요소 목록 확인 불가") if {
	not app.sbom.status == "completed"
}

findings contains lib.finding("POL-068", "DENY", "구성요소 목록 없음") if not is_array(object.get(app, "packages", null))

findings contains lib.finding("POL-068", "DENY", sprintf("미승인 패키지: %s@%s", [p.name, p.version])) if {
	some p in lib.array_or_empty(object.get(app, "packages", []))
	not package_approved(p)
}

package_approved(p) if {
	some a in lib.approved(data.pol.package_allowlist, "POL-068")
	a.name == p.name
	a.source == p.source
	p.version in a.versions
}
