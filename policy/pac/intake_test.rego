# 도입 검토 시험. 이름 규칙: test_pol_<번호>_pass_* (통과·진행) / test_pol_<번호>_block_* (차단·수동·제한).
# 시트 「정책 실행 규칙」의 자동 통과·자동 차단 열과 값 누락 반례를 옮겼다.
package mcp.pol.intake_test

import data.mcp.pol.intake
import rego.v1

now := 1793000000000000000

day := 86400000000000

tool := {
	"name": "search", "declared_effect": "read", "data_types": ["public_doc"], "permissions": ["read"],
	"description_scan": {"status": "completed", "findings": []},
	"output_contract": {"fields": ["title"], "data_scope": "public"},
	"trial_results": [{"observed_effect": "read", "observed_fields": ["title"], "sensitive_found": false, "observed_data_scope": "public"}],
}

app := {
	"id": "req-1", "provider": "acme", "source_url": "https://github.com/acme/mcp", "hosting": "gateway_managed",
	"requirements": {"functions": "검색", "data_types": "공개 문서", "permissions": "읽기", "acceptance_criteria": "시험 통과"},
	"business_scope": {"operations": ["read"], "data_types": ["public_doc"], "permissions": ["read"]},
	"tools": [tool],
	"sbom": {"status": "completed"},
	"packages": [{"name": "mcp-sdk", "version": "2.2.0", "source": "pypi"}],
}

pol_data := {
	"providers": [{"provider": "acme", "official_urls": ["https://github.com/acme/mcp"], "not_after_ns": now + day, "status": "approved", "approved_by": "admin-1", "approved_by_role": "security_admin"}],
	"package_allowlist": [{"name": "mcp-sdk", "source": "pypi", "versions": ["2.2.0"], "not_after_ns": now + day, "status": "approved", "approved_by": "admin-1", "approved_by_role": "security_admin"}],
	"data_types": ["public_doc", "internal_doc"],
	"exceptions": [],
}

decide(a) := d if {
	d := intake.decision with input as {"application": a, "facts": {"now_ns": now, "trusted": true}} with data.pol as pol_data
}

decide_with(a, extra) := d if {
	d := intake.decision with input as {"application": a, "facts": {"now_ns": now, "trusted": true}}
		with data.pol as object.union(pol_data, extra)
}

with_tool(t) := object.union(app, {"tools": [t]})

blocked(d, pol) if {
	d.effect == "DENY"
	pol in d.policy_ids
}

exception(pol, target, scope, role) := {
	"policy_id": pol, "target": target, "scope": [scope], "status": "approved",
	"approved_by_role": role, "approved_by": "admin-1", "not_after_ns": now + day,
}

test_all_checks_pass_allow if {
	d := decide(app)
	d.effect == "ALLOW"
	d.all_policy_ids == []
}

test_contract_block_untrusted_input if {
	d := intake.decision with input as {"application": app, "facts": {"now_ns": now, "trusted": false}} with data.pol as pol_data
	blocked(d, "INPUT_CONTRACT")
}

test_contract_block_tool_without_name if {
	blocked(decide(with_tool(json.remove(tool, ["name"]))), "INPUT_CONTRACT")
}

# --- POL-I-01 ---

test_pol_i_01_pass_approved_provider_and_url if not "POL-I-01" in decide(app).policy_ids

test_pol_i_01_block_unknown_url if blocked(decide(object.union(app, {"source_url": "https://evil.example/mcp"})), "POL-I-01")

test_pol_i_01_block_expired_allowlist if {
	d := intake.decision with input as {"application": app, "facts": {"now_ns": now + (2 * day), "trusted": true}} with data.pol as pol_data
	blocked(d, "POL-I-01")
}

test_pol_i_01_block_missing_provider if blocked(decide(json.remove(app, ["provider"])), "POL-I-01")

newco := object.union(app, {"provider": "newco", "source_url": "https://github.com/newco/mcp"})

newco_entry := {"provider": "newco", "official_urls": ["https://github.com/newco/mcp"], "not_after_ns": now + day, "status": "approved", "approved_by": "admin-1", "approved_by_role": "security_admin"}

with_provider(entry) := array.concat(pol_data.providers, [entry])

# 새 제공자는 보안 관리자가 승인 목록에 올려야 통과한다(실행 중 면제 없음).
test_pol_i_01_pass_new_provider_listed_by_security_admin if {
	not "POL-I-01" in decide_with(newco, {"providers": with_provider(newco_entry)}).policy_ids
}

test_pol_i_01_block_listed_by_wrong_role if {
	blocked(decide_with(newco, {"providers": with_provider(object.union(newco_entry, {"approved_by_role": "data_owner"}))}), "POL-I-01")
}

test_pol_i_01_block_listing_not_approved if {
	blocked(decide_with(newco, {"providers": with_provider(object.union(newco_entry, {"status": "requested"}))}), "POL-I-01")
}

test_pol_i_01_block_listing_without_end_date if {
	blocked(decide_with(newco, {"providers": with_provider(json.remove(newco_entry, ["not_after_ns"]))}), "POL-I-01")
}

test_pol_i_01_block_listing_other_url if {
	a := object.union(newco, {"source_url": "https://evil.example/newco"})
	blocked(decide_with(a, {"providers": with_provider(newco_entry)}), "POL-I-01")
}

test_pol_i_01_block_exception_is_not_a_listing if {
	blocked(decide_with(newco, {"exceptions": [exception("POL-I-01", "newco", "https://github.com/newco/mcp", "security_admin")]}), "POL-I-01")
}

# --- POL-I-02 ---

test_pol_i_02_pass_tool_in_business_scope if not "POL-I-02" in decide(app).policy_ids

test_pol_i_02_block_unclassified_data_type if blocked(decide(with_tool(object.union(tool, {"data_types": ["unknown_kind"]}))), "POL-I-02")

test_pol_i_02_block_operation_outside_scope if {
	t := object.union(tool, {"declared_effect": "write", "trial_results": [{"observed_effect": "write", "observed_fields": ["title"], "sensitive_found": false, "observed_data_scope": "public"}]})
	blocked(decide(with_tool(t)), "POL-I-02")
}

test_pol_i_02_block_extra_permission if blocked(decide(with_tool(object.union(tool, {"permissions": ["read", "admin"]}))), "POL-I-02")

test_pol_i_02_block_missing_business_scope if blocked(decide(json.remove(app, ["business_scope"])), "POL-I-02")

test_pol_i_02_block_taxonomy_missing if {
	d := intake.decision with input as {"application": app, "facts": {"now_ns": now, "trusted": true}}
		with data.pol as json.remove(pol_data, ["data_types"])
	blocked(d, "POL-I-02")
}

# --- POL-I-04 ---

test_pol_i_04_pass_clean_description if not "POL-I-04" in decide(app).policy_ids

test_pol_i_04_block_unclear_waits_for_admin if {
	d := decide(with_tool(object.union(tool, {"description_scan": {"status": "completed", "findings": [{"level": "unclear"}]}})))
	d.effect == "MANUAL"
	d.policy_ids == ["POL-I-04"]
}

test_pol_i_04_block_forbidden_beats_unclear if {
	d := decide(with_tool(object.union(tool, {"description_scan": {"status": "completed", "findings": [{"level": "unclear"}, {"level": "forbidden"}]}})))
	blocked(d, "POL-I-04")
}

test_pol_i_04_block_scan_not_completed if blocked(decide(with_tool(object.union(tool, {"description_scan": {"status": "error", "findings": []}}))), "POL-I-04")

test_pol_i_04_block_scan_missing if blocked(decide(with_tool(json.remove(tool, ["description_scan"]))), "POL-I-04")

test_pol_i_04_block_completed_without_findings_list if {
	blocked(decide(with_tool(json.remove(tool, ["description_scan/findings"]))), "POL-I-04")
}

test_pol_i_04_block_finding_without_level if {
	blocked(decide(with_tool(object.union(tool, {"description_scan": {"status": "completed", "findings": [{"text": "?"}]}}))), "POL-I-04")
}

# --- POL-I-05 ---

test_pol_i_05_pass_output_within_contract if not "POL-I-05" in decide(app).policy_ids

test_pol_i_05_block_no_output_contract if blocked(decide(with_tool(json.remove(tool, ["output_contract"]))), "POL-I-05")

test_pol_i_05_block_trial_returns_undeclared_field if {
	t := object.union(tool, {"trial_results": [{"observed_effect": "read", "observed_fields": ["title", "email"], "sensitive_found": false, "observed_data_scope": "public"}]})
	blocked(decide(with_tool(t)), "POL-I-05")
}

test_pol_i_05_block_trial_found_sensitive if {
	t := object.union(tool, {"trial_results": [{"observed_effect": "read", "observed_fields": ["title"], "sensitive_found": true}]})
	blocked(decide(with_tool(t)), "POL-I-05")
}

test_pol_i_05_block_trial_scope_outside_contract if {
	t := json.patch(tool, [{"op": "replace", "path": "/trial_results/0/observed_data_scope", "value": "internal"}])
	blocked(decide(with_tool(t)), "POL-I-05")
}

test_pol_i_05_block_boolean_fields if {
	t := json.patch(tool, [{"op": "replace", "path": "/output_contract/fields", "value": true}])
	blocked(decide(with_tool(t)), "POL-I-05")
}

test_pol_i_05_block_trial_fields_unknown if {
	t := object.union(tool, {"trial_results": [{"observed_effect": "read", "sensitive_found": false, "observed_data_scope": "public"}]})
	blocked(decide(with_tool(t)), "POL-I-05")
}

# --- POL-I-06 ---

test_pol_i_06_pass_trial_matches_declaration if not "POL-I-06" in decide(app).policy_ids

test_pol_i_06_block_no_trial if blocked(decide(with_tool(object.union(tool, {"trial_results": []}))), "POL-I-06")

test_pol_i_06_block_trial_sends_externally if {
	t := object.union(tool, {"trial_results": [{"observed_effect": "external_send", "observed_fields": ["title"], "sensitive_found": false, "observed_data_scope": "public"}]})
	blocked(decide(with_tool(t)), "POL-I-06")
}

test_pol_i_06_block_exception_not_allowed if {
	# 시트: 예외 심사 대상 아님 — 예외 항목이 있어도 무시한다.
	t := object.union(tool, {"trial_results": []})
	blocked(decide_with(with_tool(t), {"exceptions": [exception("POL-I-06", "search", "req-1", "security_admin")]}), "POL-I-06")
}

# --- POL-I-09 ---

external := object.union(app, {"hosting": "external"})

controls := {"internal_data_blocked": true, "personal_data_blocked": true, "credentials_blocked": true, "public_read_only": true}

test_pol_i_09_pass_verified_terms if {
	d := decide(object.union(external, {"provider_terms": {"status": "verified", "prohibited": false}}))
	not "POL-I-09" in d.policy_ids
}

test_pol_i_09_pass_not_external if not "POL-I-09" in decide(app).policy_ids

test_pol_i_09_block_prohibited_terms if {
	blocked(decide(object.union(external, {"provider_terms": {"status": "verified", "prohibited": true}})), "POL-I-09")
}

test_pol_i_09_block_unverified_restricts_to_public if {
	d := decide(object.union(external, {"provider_terms": {"status": "unverified"}, "gateway_controls": controls}))
	d.effect == "RESTRICT"
	d.policy_ids == ["POL-I-09"]
}

test_pol_i_09_block_unverified_without_controls if {
	blocked(decide(object.union(external, {"provider_terms": {"status": "unverified"}, "gateway_controls": object.union(controls, {"public_read_only": false})})), "POL-I-09")
}

test_pol_i_09_block_verified_without_prohibited_flag if {
	blocked(decide(object.union(external, {"provider_terms": {"status": "verified"}})), "POL-I-09")
}

# --- POL-I-10 (등록 단계) ---

mail := object.union(tool, {
	"name": "mail", "declared_effect": "external_send",
	"trial_results": [{"observed_effect": "external_send", "observed_fields": ["title"], "sensitive_found": false, "observed_data_scope": "public"}],
})

mail_app := object.union(app, {"tools": [mail], "business_scope": {"operations": ["read", "external_send"], "data_types": ["public_doc"], "permissions": ["read"]}})

test_pol_i_10_pass_flagged_send_tool if {
	d := decide(object.union(mail_app, {"tools": [object.union(mail, {"requires_confirmation": true})]}))
	not "POL-I-10" in d.policy_ids
}

test_pol_i_10_block_unflagged_send_tool if blocked(decide(mail_app), "POL-I-10")

test_pol_i_10_block_read_tool_observed_sending if {
	t := object.union(tool, {"trial_results": [{"observed_effect": "share", "observed_fields": ["title"], "sensitive_found": false, "observed_data_scope": "public"}]})
	blocked(decide(with_tool(t)), "POL-I-10")
}

# --- POL-I-11 ---

test_pol_i_11_pass_all_requirements if not "POL-I-11" in decide(app).policy_ids

test_pol_i_11_block_missing_requirement if blocked(decide(json.remove(app, ["requirements/acceptance_criteria"])), "POL-I-11")

test_pol_i_11_block_null_requirement if {
	blocked(decide(object.union(app, {"requirements": {"functions": null, "data_types": "", "permissions": [], "acceptance_criteria": {}}})), "POL-I-11")
}

test_pol_i_11_block_no_tools if blocked(decide(object.union(app, {"tools": []})), "POL-I-11")

test_pol_i_11_block_false_requirement if blocked(decide(json.patch(app, [{"op": "replace", "path": "/requirements/functions", "value": false}])), "POL-I-11")

# --- POL-O-06 ---

test_pol_o_06_pass_approved_packages if not "POL-O-06" in decide(app).policy_ids

test_pol_o_06_block_unapproved_version if {
	blocked(decide(object.union(app, {"packages": [{"name": "mcp-sdk", "version": "9.9.9", "source": "pypi"}]})), "POL-O-06")
}

test_pol_o_06_block_other_source if {
	blocked(decide(object.union(app, {"packages": [{"name": "mcp-sdk", "version": "2.2.0", "source": "mirror.example"}]})), "POL-O-06")
}

test_pol_o_06_block_sbom_not_completed if blocked(decide(json.remove(app, ["sbom"])), "POL-O-06")

test_pol_o_06_pass_new_version_listed if {
	a := object.union(app, {"packages": [{"name": "mcp-sdk", "version": "9.9.9", "source": "pypi"}]})
	entry := {"name": "mcp-sdk", "source": "pypi", "versions": ["9.9.9"], "not_after_ns": now + day, "status": "approved", "approved_by": "admin-1", "approved_by_role": "security_admin"}
	not "POL-O-06" in decide_with(a, {"package_allowlist": [entry]}).policy_ids
}

test_pol_o_06_block_packages_null_with_completed_sbom if blocked(decide(object.union(app, {"packages": null})), "POL-O-06")
