# 시트 「정책 실행 규칙」의 자동 통과·자동 차단 열과, 교차검증(Codex sol)이 찾은 반례를 시험으로 옮긴 것이다.
package mcp.pol_test

import data.mcp.pol.call
import data.mcp.pol.intake
import data.mcp.pol.ops
import rego.v1

now := 1793000000000000000

day := 86400000000000

providers := [{"provider": "acme", "official_urls": ["https://github.com/acme/mcp"], "not_after_ns": now + day}]

good_tool := {
	"name": "search", "declared_effect": "read",
	"description_scan": {"status": "completed", "findings": []},
	"output_contract": {"fields": ["title"], "data_scope": "public"},
	"trial_results": [{"observed_effect": "read", "observed_fields": ["title"]}],
}

good_app := {
	"provider": "acme", "source_url": "https://github.com/acme/mcp", "tools": [good_tool],
	"requirements": {"functions": "검색", "data_types": "공개", "permissions": "읽기", "acceptance_criteria": "시험 통과"},
}

intake_with(app, exceptions) := d if {
	d := intake.decision with input as {"application": app, "facts": {"now_ns": now}}
		with data.providers as providers
		with data.exceptions as exceptions
}

with_tool(t) := object.union(good_app, {"tools": [t]})

# --- 도입 검토 ---

test_intake_all_checks_pass_proceeds if {
	intake_with(good_app, []).result == "proceed"
}

test_pol001_unknown_url_blocks if {
	intake_with(object.union(good_app, {"source_url": "https://evil.example/mcp"}), []) == {"result": "block", "policy_ids": ["POL-001"]}
}

test_pol001_expired_provider_blocks if {
	d := intake.decision with input as {"application": good_app, "facts": {"now_ns": now + (2 * day)}}
		with data.providers as providers
		with data.exceptions as []
	d.policy_ids == ["POL-001"]
}

exception := {
	"policy_id": "POL-001", "target": "newco", "scope": ["https://github.com/newco/mcp"],
	"status": "approved", "approved_by_role": "security_admin", "not_after_ns": now + day,
}

newco := object.union(good_app, {"provider": "newco", "source_url": "https://github.com/newco/mcp"})

test_pol001_exception_in_scope_allows if {
	intake_with(newco, [exception]).result == "proceed"
}

test_pol001_exception_does_not_cover_other_url if {
	intake_with(object.union(newco, {"source_url": "https://evil.example/newco"}), [exception]).policy_ids == ["POL-001"]
}

test_pol001_exception_by_wrong_role_ignored if {
	intake_with(newco, [object.union(exception, {"approved_by_role": "data_owner"})]).policy_ids == ["POL-001"]
}

test_pol001_expired_exception_ignored if {
	intake_with(newco, [object.union(exception, {"not_after_ns": now})]).policy_ids == ["POL-001"]
}

test_pol004_unclear_waits_for_admin if {
	t := object.union(good_tool, {"description_scan": {"status": "completed", "findings": [{"level": "unclear"}]}})
	intake_with(with_tool(t), []).result == "manual"
}

test_pol004_forbidden_beats_unclear if {
	t := object.union(good_tool, {"description_scan": {"status": "completed", "findings": [{"level": "unclear"}, {"level": "forbidden"}]}})
	intake_with(with_tool(t), []) == {"result": "block", "policy_ids": ["POL-004"]}
}

test_pol004_missing_scan_blocks if {
	intake_with(with_tool(json.remove(good_tool, ["description_scan"])), []).policy_ids == ["POL-004"]
}

test_pol004_failed_scan_blocks if {
	t := object.union(good_tool, {"description_scan": {"status": "error", "findings": []}})
	intake_with(with_tool(t), []).policy_ids == ["POL-004"]
}

test_pol004_unknown_level_blocks if {
	t := object.union(good_tool, {"description_scan": {"status": "completed", "findings": [{"level": "scanner_timeout"}]}})
	intake_with(with_tool(t), []).policy_ids == ["POL-004"]
}

test_pol005_missing_scope_blocks if {
	intake_with(with_tool(json.remove(good_tool, ["output_contract/data_scope"])), []).policy_ids == ["POL-005"]
}

test_pol005_trial_returns_undeclared_field_blocks if {
	t := object.union(good_tool, {"trial_results": [{"observed_effect": "read", "observed_fields": ["title", "email"]}]})
	intake_with(with_tool(t), []).policy_ids == ["POL-005"]
}

test_pol006_no_trial_blocks if {
	intake_with(with_tool(object.union(good_tool, {"trial_results": []})), []).policy_ids == ["POL-006"]
}

test_pol006_trial_mismatch_blocks if {
	t := object.union(good_tool, {"trial_results": [{"observed_effect": "write", "observed_fields": ["title"]}]})
	intake_with(with_tool(t), []).policy_ids == ["POL-006"]
}

mail := object.union(good_tool, {
	"name": "mail", "declared_effect": "external_send",
	"trial_results": [{"observed_effect": "external_send", "observed_fields": ["title"]}],
})

test_pol010_unflagged_send_tool_blocks if {
	intake_with(with_tool(mail), []).policy_ids == ["POL-010"]
}

test_pol010_flagged_send_tool_proceeds if {
	intake_with(with_tool(object.union(mail, {"requires_confirmation": true})), []).result == "proceed"
}

test_pol010_read_tool_that_sends_in_trial_blocks if {
	# 설명은 조회인데 시험에서 외부 전송이 관측됐다: 불일치(006)와 확인 대상 미표시(010) 둘 다.
	t := object.union(good_tool, {"trial_results": [{"observed_effect": "external_send", "observed_fields": ["title"]}]})
	intake_with(with_tool(t), []).policy_ids == ["POL-006", "POL-010"]
}

test_pol011_missing_requirement_blocks if {
	intake_with(json.remove(good_app, ["requirements/acceptance_criteria"]), []).policy_ids == ["POL-011"]
}

test_pol011_null_values_block if {
	app := object.union(good_app, {"requirements": {"functions": null, "data_types": null, "permissions": null, "acceptance_criteria": null}})
	intake_with(app, []).policy_ids == ["POL-011"]
}

test_pol011_no_tools_blocks if {
	intake_with(object.union(good_app, {"tools": []}), []).policy_ids == ["POL-011"]
}

# --- 실행 및 통제 ---

request := {
	"id": "r1", "operation": "external_send", "server_id": "mail-srv", "tool": "send",
	"target": "doc-1", "recipient": "a@corp", "source_server": "mail-srv",
}

confirmed := {
	"reserved_for": "r1", "expires_ns": now + day, "confirmed_by": "kim", "server_id": "mail-srv",
	"tool": "send", "operation": "external_send", "target": "doc-1", "recipient": "a@corp", "arguments_sha256": "h1",
}

call_input(confirmation, sha) := {
	"stage": "request", "request": request,
	"facts": {
		"now_ns": now, "identity": {"user": "kim"}, "confirmation": confirmation, "arguments_sha256": sha,
		"audit": {"central_writable": true, "buffer_writable": false}, "data": {"contains_credential": false},
	},
}

findings_for(i) := f if {
	f := call.findings with input as i
		with data.result_limits as {"search": {"max_items": 50, "max_bytes": 100000}}
		with data.default_result_limit as {"max_items": 20, "max_bytes": 50000}
}

needs_confirmation(i) if {
	{"policy_id": "POL-053", "effect": "APPROVAL"} in findings_for(i)
}

test_pol053_matching_reserved_confirmation_runs if {
	count(findings_for(call_input(confirmed, "h1"))) == 0
}

test_pol053_changed_arguments_need_new_confirmation if {
	needs_confirmation(call_input(confirmed, "h2"))
}

test_pol053_confirmation_reserved_for_other_call_refused if {
	needs_confirmation(call_input(object.union(confirmed, {"reserved_for": "r0"}), "h1"))
}

test_pol053_moved_to_other_tool_refused if {
	needs_confirmation(call_input(object.union(confirmed, {"tool": "share"}), "h1"))
}

test_pol053_admin_approval_is_not_user_confirmation if {
	needs_confirmation(call_input(object.union(confirmed, {"confirmed_by": "admin"}), "h1"))
}

test_pol057_no_audit_store_denies if {
	i := json.patch(call_input(confirmed, "h1"), [{"op": "replace", "path": "/facts/audit/central_writable", "value": false}])
	{"policy_id": "POL-057", "effect": "DENY"} in findings_for(i)
}

test_pol057_string_false_is_not_writable if {
	i := json.patch(call_input(confirmed, "h1"), [{"op": "replace", "path": "/facts/audit/central_writable", "value": "false"}])
	{"policy_id": "POL-057", "effect": "DENY"} in findings_for(i)
}

test_pol057_buffer_alone_keeps_running if {
	i := json.patch(call_input(confirmed, "h1"), [
		{"op": "replace", "path": "/facts/audit/central_writable", "value": false},
		{"op": "replace", "path": "/facts/audit/buffer_writable", "value": true},
	])
	count(findings_for(i)) == 0
}

read_response(items, bytes) := json.patch(call_input(confirmed, "h1"), [
	{"op": "replace", "path": "/stage", "value": "response"},
	{"op": "replace", "path": "/request/operation", "value": "read"},
	{"op": "replace", "path": "/request/tool", "value": "search"},
	{"op": "add", "path": "/response", "value": {"items": items, "bytes": bytes}},
])

test_pol048_within_limit_returns if {
	count(findings_for(read_response(50, 1000))) == 0
}

test_pol048_too_many_items_denied if {
	{"policy_id": "POL-048", "effect": "DENY"} in findings_for(read_response(51, 1000))
}

test_pol048_unknown_size_denied if {
	{"policy_id": "POL-048", "effect": "DENY"} in findings_for(read_response(10, null))
}

test_pol048_tool_without_limit_uses_default if {
	i := json.patch(read_response(30, 1000), [{"op": "replace", "path": "/request/tool", "value": "other"}])
	{"policy_id": "POL-048", "effect": "DENY"} in findings_for(i)
}

test_pol043_credential_to_other_server_denied if {
	i := json.patch(call_input(confirmed, "h1"), [
		{"op": "replace", "path": "/request/source_server", "value": "github"},
		{"op": "replace", "path": "/facts/data/contains_credential", "value": true},
	])
	{"policy_id": "POL-043", "effect": "DENY"} in findings_for(i)
}

# --- 운영 및 변경·폐기 ---

server(vulns) := {
	"id": "s1", "address": "https://s1.corp/mcp", "vulnerabilities": vulns, "scheduled_change_ns": now + (7 * day),
	"observed_tools": [], "approved_tools": {}, "observed_permissions": ["read"], "approved_permissions": ["read"],
}

violations_for(servers) := v if {
	v := ops.violations with input as {"servers": servers, "facts": {"now_ns": now}}
		with data.exceptions as []
}

blocked(vid, servers) if {
	some v in violations_for(servers)
	v.policy_id == "POL-069"
	v.vuln == vid
}

vuln(id, severity, age_days) := {
	"id": id, "severity": severity, "exploited": false, "exposed": false,
	"patched": false, "confirmed_ns": now - (age_days * day),
}

test_pol069_exploited_critical_after_48h_blocks if {
	blocked("CVE-1", [server([object.union(vuln("CVE-1", "critical", 3), {"exploited": true, "exposed": true})])])
}

test_pol069_high_within_14_days_keeps_running if {
	not blocked("CVE-2", [server([vuln("CVE-2", "high", 3)])])
}

test_pol069_due_moment_is_included if {
	blocked("CVE-3", [server([vuln("CVE-3", "high", 14)])])
}

test_pol069_verified_compensating_control_keeps_running if {
	v := object.union(vuln("CVE-4", "high", 20), {"compensating_control": {"verified": true}})
	not blocked("CVE-4", [server([v])])
}

test_pol069_low_uses_scheduled_change_date if {
	not blocked("CVE-5", [server([vuln("CVE-5", "low", 100)])])
	blocked("CVE-5", [object.union(server([vuln("CVE-5", "low", 100)]), {"scheduled_change_ns": now - day})])
}

test_pol069_unknown_confirmation_time_blocks if {
	blocked("CVE-6", [server([json.remove(vuln("CVE-6", "high", 1), ["confirmed_ns"])])])
}

test_pol062_changed_tool_contract_restricts if {
	s := object.union(server([]), {"observed_tools": [{"name": "search", "contract_sha256": "new"}], "approved_tools": {"search": "old"}})
	{"policy_id": "POL-062", "server": "s1", "action": "restrict", "tool": "search"} in violations_for([s])
}

test_pol062_new_unapproved_tool_restricts if {
	s := object.union(server([]), {"observed_tools": [{"name": "delete_all", "contract_sha256": "x"}], "approved_tools": {"search": "old"}})
	{"policy_id": "POL-062", "server": "s1", "action": "restrict", "tool": "delete_all"} in violations_for([s])
}

test_pol074_new_permission_blocks if {
	s := object.union(server([]), {"observed_permissions": ["read", "network"]})
	{"policy_id": "POL-074", "server": "s1", "action": "block", "permission": "network"} in violations_for([s])
}

restored(servers, decommissioned) := v if {
	v := ops.violations with input as {"event": "restored", "servers": servers, "facts": {"now_ns": now}}
		with data.decommissioned as decommissioned
		with data.registry as {"s1": {"address": "https://s1.corp/mcp", "permissions": ["read"]}}
		with data.exceptions as []
}

test_pol089_restored_matching_server_keeps_running if {
	count(restored([server([])], [])) == 0
}

test_pol089_restored_decommissioned_server_stops if {
	{"policy_id": "POL-089", "server": "s1", "action": "stop"} in restored([server([])], ["s1"])
}

test_pol089_restored_with_old_address_stops if {
	s := object.union(server([]), {"address": "https://old.corp/mcp"})
	{"policy_id": "POL-089", "server": "s1", "action": "stop"} in restored([s], [])
}

test_pol062_server_without_approved_list_restricts if {
	s := object.union(json.remove(server([]), ["approved_tools"]), {"observed_tools": [{"name": "search", "contract_sha256": "x"}]})
	{"policy_id": "POL-062", "server": "s1", "action": "restrict", "tool": "search"} in violations_for([s])
}

test_pol048_no_limits_configured_denied if {
	f := call.findings with input as read_response(1, 10)
	{"policy_id": "POL-048", "effect": "DENY"} in f
}
