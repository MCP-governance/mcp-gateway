# 실행 및 통제 시험. 이름 규칙: test_pol_<번호>_pass_* / test_pol_<번호>_block_*.
package mcp.pol.call_test

import data.mcp.pol.call
import rego.v1

now := 1793000000000000000

day := 86400000000000

registry := {"srv": {"state": "active", "tools": {
	"search": {
		"state": "active", "approved_contract_sha256": "c1", "document_scoped": true, "roots": ["/srv/data"],
		"result_limit": {"max_items": 50, "max_bytes": 100000}, "window_document_limit": 200,
		"personal_fields_allowed": ["employee_id"],
	},
	"mail": {
		"state": "active", "approved_contract_sha256": "c2", "sensitive": true, "requires_confirmation": true,
		"egress_hosts": ["mail.partner.com"],
	},
	"shell": {"state": "active", "approved_contract_sha256": "c3", "kind": "command", "operations": ["execute"]},
	"fetch": {"state": "active", "approved_contract_sha256": "c4", "fetches_url": true, "url_destinations": ["docs.vendor.com"]},
}}}

grant(user, tool, data_class, op) := {"user": user, "server_id": "srv", "tool": tool, "data_class": data_class, "operation": op, "not_after_ns": now + day, "status": "approved", "approved_by": "owner-1", "approved_by_role": "data_owner"}

delegation(tool, data_class, op) := object.union(grant("kim", tool, data_class, op), {"agent": "claude-code"})

pol_data := {
	"servers": registry,
	"permission_table": [
		grant("kim", "search", "internal_doc", "read"), grant("kim", "mail", "internal_doc", "external_send"),
		grant("kim", "shell", "internal_doc", "execute"), grant("kim", "fetch", "public_doc", "read"),
	],
	"delegations": [
		delegation("search", "internal_doc", "read"), delegation("mail", "internal_doc", "external_send"),
		delegation("shell", "internal_doc", "execute"), delegation("fetch", "public_doc", "read"),
	],
	"document_grants": [{"user": "kim", "agent": "claude-code", "server_id": "srv", "tool": "search", "doc_id": "doc-1", "not_after_ns": now + day, "status": "approved", "approved_by": "owner-1", "approved_by_role": "data_owner"}],
	"transfers": [{"data_class": "internal_doc", "recipient": "a@partner.com", "purpose": "계약 검토", "not_after_ns": now + day, "status": "approved", "approved_by": "owner-1", "approved_by_role": "data_owner"}],
	"flows": [{"source_server": "drive", "dest_server": "srv", "data_class": "internal_doc", "purpose": "요약", "not_after_ns": now + day, "status": "approved", "approved_by": "owner-1", "approved_by_role": "data_owner"}],
	"server_accounts": {"srv": {"operations": ["read"], "data_classes": ["internal_doc"]}},
	"rate_limits": {"user": {"window_calls": 100, "concurrent": 4}, "agent": {"window_calls": 100, "concurrent": 4}, "tool": {"window_calls": 500, "concurrent": 10}},
	"default_result_limit": {"max_items": 20, "max_bytes": 50000},
	"exceptions": [],
}

usage := {"user": {"window_calls": 3, "concurrent": 1}, "agent": {"window_calls": 3, "concurrent": 1}, "tool": {"window_calls": 3, "concurrent": 1}}

base_facts := {
	"now_ns": now, "trusted": true, "approval": {"basis": "normal"},
	"token": {"valid": true, "audience": "srv", "expires_ns": now + day},
	"credential": {"used": true, "bound_server": "srv"},
	"catalog": {"matches": 1, "observed_contract_sha256": "c1"},
	"permission_lookup": {"status": "ok", "request_id": "r1"},
	"inspection": {"status": "completed", "secrets": [], "personal_data": []},
	"provenance": {"external_content": false},
	"schema": {"valid": true, "undeclared_fields": []},
	"data": {"contains_credential": false},
	"server_account": {"used": false},
	"usage": object.union(usage, {"window_documents": 10, "blocked_pattern": false}),
	"audit": {"central_writable": true, "buffer_writable": false, "recorded": true},
	"path": {"resolved": "/srv/data/a.txt"},
}

read_req := {
	"id": "r1", "stage": "request", "user": "kim", "agent": "claude-code", "server_id": "srv", "tool": "search",
	"operation": "read", "target": {"doc_id": "doc-1", "data_class": "internal_doc", "path": "/srv/data/a.txt"},
}

send_req := {
	"id": "r1", "stage": "request", "user": "kim", "agent": "claude-code", "server_id": "srv", "tool": "mail",
	"operation": "external_send", "target": {"doc_id": "doc-1", "data_class": "internal_doc"},
	"recipient": "a@partner.com", "purpose": "계약 검토",
}

confirmation := {
	"confirmed_by": "kim", "reserved_for": "r1", "used": false, "expires_ns": now + day,
	"server_id": "srv", "tool": "mail", "operation": "external_send", "target": "doc-1", "recipient": "a@partner.com",
	"arguments_sha256": "h1",
}

send_facts := object.union(base_facts, {
	"catalog": {"matches": 1, "observed_contract_sha256": "c2"},
	"egress": {"final_host": "mail.partner.com", "resolved_ips": ["93.184.216.34"]},
	"confirmation": confirmation, "arguments_sha256": "h1",
})

run(r, f) := d if {
	d := call.decision with input as {"request": r, "facts": f} with data.pol as pol_data
}

run_with(r, f, extra) := d if {
	d := call.decision with input as {"request": r, "facts": f} with data.pol as object.union(pol_data, extra)
}

run_response(r, f, resp) := d if {
	d := call.decision with input as {"request": r, "facts": f, "response": resp} with data.pol as pol_data
}

# object.union은 재귀로 합쳐 빈 값으로 덮어쓰지 못한다. 표를 통째로 바꿀 때는 이것을 쓴다.
run_replacing(r, f, path, value) := d if {
	d := call.decision with input as {"request": r, "facts": f} with data.pol as json.patch(pol_data, [{"op": "replace", "path": path, "value": value}])
}

read_run(patch) := run(read_req, json.patch(base_facts, patch))

send_run(patch) := run(send_req, json.patch(send_facts, patch))

blocked(d, pol) if {
	d.effect == "DENY"
	pol in d.policy_ids
}

exception(pol, target, scope, role) := {
	"policy_id": pol, "target": target, "scope": [scope], "status": "approved",
	"approved_by_role": role, "approved_by": "owner-1", "not_after_ns": now + day,
}

test_read_all_pass_allow if run(read_req, base_facts).effect == "ALLOW"

test_send_all_pass_allow if run(send_req, send_facts).effect == "ALLOW"

test_contract_block_identity_missing if blocked(run(json.remove(read_req, ["user"]), base_facts), "INPUT_CONTRACT")

test_contract_block_unknown_operation if blocked(run(object.union(read_req, {"operation": "launch"}), base_facts), "INPUT_CONTRACT")

# --- POL-I-03 ---

test_pol_i_03_pass_in_permission_table if not "POL-I-03" in run(read_req, base_facts).policy_ids

test_pol_i_03_block_other_data_class if {
	blocked(run(json.patch(read_req, [{"op": "replace", "path": "/target/data_class", "value": "hr_record"}]), base_facts), "POL-I-03")
}

test_pol_i_03_block_table_unavailable if {
	blocked(run_with(read_req, base_facts, {"permission_table": null}), "POL-I-03")
}

hr_req := json.patch(read_req, [{"op": "replace", "path": "/target/data_class", "value": "hr_record"}])

test_pol_i_03_pass_entry_approved_by_data_owner if {
	not "POL-I-03" in run_with(hr_req, base_facts, {"permission_table": [grant("kim", "search", "hr_record", "read")]}).policy_ids
}

test_pol_i_03_block_entry_approved_by_security_admin if {
	e := object.union(grant("kim", "search", "hr_record", "read"), {"approved_by_role": "security_admin"})
	blocked(run_with(hr_req, base_facts, {"permission_table": [e]}), "POL-I-03")
}

test_pol_i_03_block_exception_is_not_a_grant if {
	blocked(run_with(hr_req, base_facts, {"exceptions": [exception("POL-I-03", "kim", "srv/search", "data_owner")]}), "POL-I-03")
}

# --- POL-I-10 (실행 단계) ---

test_pol_i_10_pass_flagged_sensitive_tool if not "POL-I-10" in run(send_req, send_facts).policy_ids

test_pol_i_10_block_unflagged_sensitive_tool if {
	reg := json.patch(registry, [{"op": "replace", "path": "/srv/tools/mail/requires_confirmation", "value": false}])
	blocked(run_with(send_req, send_facts, {"servers": reg}), "POL-I-10")
}

test_pol_i_10_block_delete_on_read_tool if {
	r := object.union(read_req, {"operation": "delete"})
	blocked(run_with(r, base_facts, {"permission_table": [grant("kim", "search", "internal_doc", "delete")]}), "POL-I-10")
}

# --- POL-R-02 ---

test_pol_r_02_pass_normal_basis if not "POL-R-02" in run(read_req, base_facts).policy_ids

test_pol_r_02_block_expired_exception_basis if {
	e := object.union(exception("POL-R-02", "srv", "search", "security_admin"), {"not_after_ns": now - 1})
	blocked(run_with(read_req, json.patch(base_facts, [{"op": "replace", "path": "/approval/basis", "value": "exception"}]), {"exceptions": [e]}), "POL-R-02")
}

test_pol_r_02_pass_valid_exception_basis if {
	d := run_with(read_req, json.patch(base_facts, [{"op": "replace", "path": "/approval/basis", "value": "exception"}]), {"exceptions": [exception("POL-R-02", "srv", "search", "security_admin")]})
	not "POL-R-02" in d.policy_ids
}

test_pol_r_02_block_basis_missing if blocked(run(read_req, json.remove(base_facts, ["approval"])), "POL-R-02")

# --- POL-R-04 ---

test_pol_r_04_pass_exact_match if not "POL-R-04" in run(read_req, base_facts).policy_ids

test_pol_r_04_block_ambiguous_name if blocked(read_run([{"op": "replace", "path": "/catalog/matches", "value": 2}]), "POL-R-04")

test_pol_r_04_block_unknown_tool if blocked(run(object.union(read_req, {"tool": "search2"}), base_facts), "POL-R-04")

# --- POL-R-05 ---

test_pol_r_05_pass_valid_token if not "POL-R-05" in run(read_req, base_facts).policy_ids

test_pol_r_05_block_token_for_other_server if blocked(read_run([{"op": "replace", "path": "/token/audience", "value": "other"}]), "POL-R-05")

test_pol_r_05_block_expired_token if blocked(read_run([{"op": "replace", "path": "/token/expires_ns", "value": now}]), "POL-R-05")

test_pol_r_05_block_no_token if blocked(run(read_req, json.remove(base_facts, ["token"])), "POL-R-05")

test_pol_r_05_pass_local_server_without_token if {
	reg := json.patch(registry, [{"op": "add", "path": "/srv/kind", "value": "local"}])
	not "POL-R-05" in run_with(read_req, object.union(base_facts, {"token": {"used": false}}), {"servers": reg}).policy_ids
}

test_pol_r_05_block_remote_server_without_token if blocked(read_run([{"op": "replace", "path": "/token", "value": {"used": false}}]), "POL-R-05")

# --- POL-R-14 ---

test_pol_r_14_pass_bound_credential if not "POL-R-14" in run(read_req, base_facts).policy_ids

test_pol_r_14_pass_no_credential_used if not "POL-R-14" in read_run([{"op": "replace", "path": "/credential", "value": {"used": false}}]).policy_ids

test_pol_r_14_block_other_server_credential if blocked(read_run([{"op": "replace", "path": "/credential/bound_server", "value": "github"}]), "POL-R-14")

test_pol_r_14_block_credential_unknown if blocked(run(read_req, json.remove(base_facts, ["credential"])), "POL-R-14")

# --- POL-E-01 ---

test_pol_e_01_pass_delegated if not "POL-E-01" in run(read_req, base_facts).policy_ids

test_pol_e_01_block_other_agent if blocked(run(object.union(read_req, {"agent": "unknown-agent"}), base_facts), "POL-E-01")

test_pol_e_01_block_expired_delegation if {
	blocked(run_with(read_req, base_facts, {"delegations": [object.union(delegation("search", "internal_doc", "read"), {"not_after_ns": now})]}), "POL-E-01")
}

# --- POL-E-02 ---

test_pol_e_02_pass_fresh_lookup if not "POL-E-02" in run(read_req, base_facts).policy_ids

test_pol_e_02_block_lookup_failed if blocked(read_run([{"op": "replace", "path": "/permission_lookup/status", "value": "error"}]), "POL-E-02")

test_pol_e_02_block_lookup_reused_from_other_call if {
	blocked(read_run([{"op": "replace", "path": "/permission_lookup/request_id", "value": "r0"}]), "POL-E-02")
}

# --- POL-E-03 ---

test_pol_e_03_pass_document_granted if not "POL-E-03" in run(read_req, base_facts).policy_ids

test_pol_e_03_block_other_document if {
	blocked(run(json.patch(read_req, [{"op": "replace", "path": "/target/doc_id", "value": "doc-2"}]), base_facts), "POL-E-03")
}

test_pol_e_03_block_document_unknown if blocked(run(json.remove(read_req, ["target/doc_id"]), base_facts), "POL-E-03")

# --- POL-E-04 ---

test_pol_e_04_pass_plain_call if not "POL-E-04" in run(read_req, base_facts).policy_ids

test_pol_e_04_block_external_content_as_approval if {
	r := object.union(read_req, {"intent": "approval"})
	blocked(run(r, json.patch(base_facts, [{"op": "replace", "path": "/provenance/external_content", "value": true}])), "POL-E-04")
}

test_pol_e_04_block_permission_change_with_unknown_provenance if {
	blocked(run(object.union(read_req, {"intent": "permission_change"}), json.remove(base_facts, ["provenance"])), "POL-E-04")
}

test_pol_e_04_pass_approval_from_user_only if not "POL-E-04" in run(object.union(read_req, {"intent": "approval"}), base_facts).policy_ids

test_pol_e_04_block_unknown_intent if blocked(run(object.union(read_req, {"intent": "grant"}), base_facts), "POL-E-04")

# --- POL-E-05 ---

test_pol_e_05_pass_clean_input if not "POL-E-05" in run(read_req, base_facts).policy_ids

test_pol_e_05_block_secret_in_input if blocked(read_run([{"op": "replace", "path": "/inspection/secrets", "value": ["github_token"]}]), "POL-E-05")

test_pol_e_05_block_unneeded_personal_data if {
	blocked(read_run([{"op": "replace", "path": "/inspection/personal_data", "value": ["resident_number"]}]), "POL-E-05")
}

test_pol_e_05_pass_allowed_personal_field if {
	not "POL-E-05" in read_run([{"op": "replace", "path": "/inspection/personal_data", "value": ["employee_id"]}]).policy_ids
}

test_pol_e_05_block_completed_without_lists if {
	blocked(read_run([{"op": "replace", "path": "/inspection", "value": {"status": "completed"}}]), "POL-E-05")
}

test_pol_e_05_block_secret_list_as_string if blocked(read_run([{"op": "replace", "path": "/inspection/secrets", "value": "token-present"}]), "POL-E-05")

test_pol_e_05_block_inspection_not_done if blocked(run(read_req, json.remove(base_facts, ["inspection"])), "POL-E-05")

# --- POL-E-07 ---

test_pol_e_07_pass_approved_final_host if not "POL-E-07" in run(send_req, send_facts).policy_ids

test_pol_e_07_block_redirect_to_unapproved_host if blocked(send_run([{"op": "replace", "path": "/egress/final_host", "value": "evil.example"}]), "POL-E-07")

test_pol_e_07_block_internal_ip if blocked(send_run([{"op": "replace", "path": "/egress/resolved_ips", "value": ["192.168.0.10"]}]), "POL-E-07")

test_pol_e_07_block_outside_approved_ip_range if {
	reg := json.patch(registry, [{"op": "add", "path": "/srv/tools/mail/egress_ip_ranges", "value": ["8.8.8.0/24"]}])
	blocked(run_with(send_req, send_facts, {"servers": reg}), "POL-E-07")
}

test_pol_e_07_pass_inside_approved_ip_range if {
	reg := json.patch(registry, [{"op": "add", "path": "/srv/tools/mail/egress_ip_ranges", "value": ["93.184.216.0/24"]}])
	not "POL-E-07" in run_with(send_req, send_facts, {"servers": reg}).policy_ids
}

test_pol_e_07_block_egress_unknown if blocked(run(send_req, json.remove(send_facts, ["egress"])), "POL-E-07")

# --- POL-E-08 ---

test_pol_e_08_pass_approved_transfer if not "POL-E-08" in run(send_req, send_facts).policy_ids

test_pol_e_08_block_other_purpose if blocked(run(object.union(send_req, {"purpose": "마케팅"}), send_facts), "POL-E-08")

test_pol_e_08_block_other_recipient if blocked(run(object.union(send_req, {"recipient": "x@other.com"}), send_facts), "POL-E-08")

# --- POL-E-09 ---

test_pol_e_09_pass_inside_root if not "POL-E-09" in run(read_req, base_facts).policy_ids

test_pol_e_09_block_symlink_outside_root if blocked(read_run([{"op": "replace", "path": "/path/resolved", "value": "/etc/shadow"}]), "POL-E-09")

test_pol_e_09_block_prefix_trick if blocked(read_run([{"op": "replace", "path": "/path/resolved", "value": "/srv/data-secret/a.txt"}]), "POL-E-09")

test_pol_e_09_block_parent_traversal if blocked(read_run([{"op": "replace", "path": "/path/resolved", "value": "/srv/data/../../etc/passwd"}]), "POL-E-09")

test_pol_e_09_block_null_path_on_file_tool if {
	r := json.patch(read_req, [{"op": "replace", "path": "/target/path", "value": null}])
	blocked(run(r, json.patch(base_facts, [{"op": "replace", "path": "/path/resolved", "value": "/etc/passwd"}])), "POL-E-09")
}

test_pol_e_09_block_unresolved_path if blocked(run(read_req, json.remove(base_facts, ["path"])), "POL-E-09")

# --- POL-E-11 ---

flow_req := object.union(read_req, {"source_server": "drive", "purpose": "요약"})

test_pol_e_11_pass_approved_flow if not "POL-E-11" in run(flow_req, base_facts).policy_ids

test_pol_e_11_block_unapproved_flow if blocked(run(object.union(flow_req, {"source_server": "slack"}), base_facts), "POL-E-11")

test_pol_e_11_block_credential_transfer if blocked(read_run([{"op": "replace", "path": "/data/contains_credential", "value": true}]), "POL-E-11")

test_pol_e_11_block_source_server_not_a_name if blocked(run(object.union(read_req, {"source_server": ["drive"]}), base_facts), "POL-E-11")

test_pol_e_11_block_credential_unknown if blocked(run(read_req, json.remove(base_facts, ["data"])), "POL-E-11")

# --- POL-E-13 ---

shell_req := object.union(read_req, {"tool": "shell", "operation": "execute"})

shell_facts := object.union(base_facts, {"catalog": {"matches": 1, "observed_contract_sha256": "c3"}, "arguments_validated": true})

test_pol_e_13_pass_validated_command if not "POL-E-13" in run(shell_req, shell_facts).policy_ids

test_pol_e_13_block_unvalidated_arguments if blocked(run(shell_req, object.union(shell_facts, {"arguments_validated": false})), "POL-E-13")

test_pol_e_13_block_execute_on_unclassified_tool if {
	r := object.union(read_req, {"operation": "execute"})
	blocked(run_with(r, base_facts, {"permission_table": [grant("kim", "search", "internal_doc", "execute")]}), "POL-E-13")
}

test_pol_e_13_block_unapproved_operation if {
	r := object.union(shell_req, {"operation": "write"})
	blocked(run_with(r, shell_facts, {"permission_table": [grant("kim", "shell", "internal_doc", "write")]}), "POL-E-13")
}

# --- POL-E-14 ---

fetch_req := json.patch(read_req, [{"op": "replace", "path": "/tool", "value": "fetch"}, {"op": "replace", "path": "/target", "value": {"data_class": "public_doc"}}])

fetch_facts := object.union(base_facts, {
	"catalog": {"matches": 1, "observed_contract_sha256": "c4"},
	"egress": {"final_host": "docs.vendor.com", "resolved_ips": ["151.101.1.69"]},
})

test_pol_e_14_pass_approved_url if not "POL-E-14" in run(fetch_req, fetch_facts).policy_ids

test_pol_e_14_block_metadata_endpoint if {
	f := json.patch(fetch_facts, [{"op": "replace", "path": "/egress/resolved_ips", "value": ["169.254.169.254"]}])
	blocked(run(fetch_req, f), "POL-E-14")
}

test_pol_e_14_block_cidr_instead_of_address if {
	blocked(run(fetch_req, json.patch(fetch_facts, [{"op": "replace", "path": "/egress/resolved_ips", "value": ["8.8.8.0/24"]}])), "POL-E-14")
}

test_pol_e_14_block_unapproved_host if {
	blocked(run(fetch_req, json.patch(fetch_facts, [{"op": "replace", "path": "/egress/final_host", "value": "pastebin.com"}])), "POL-E-14")
}

# --- POL-E-15 ---

test_pol_e_15_pass_valid_schema if not "POL-E-15" in run(read_req, base_facts).policy_ids

test_pol_e_15_block_undeclared_field if blocked(read_run([{"op": "replace", "path": "/schema/undeclared_fields", "value": ["__hidden"]}]), "POL-E-15")

test_pol_e_15_block_invalid_schema if blocked(read_run([{"op": "replace", "path": "/schema/valid", "value": false}]), "POL-E-15")

# --- POL-E-16 ---

resp_req := object.union(read_req, {"stage": "response"})

test_pol_e_16_pass_within_limit if run_response(resp_req, base_facts, {"items": 50, "bytes": 1000}).effect == "ALLOW"

test_pol_e_16_block_over_limit_restricts if {
	d := run_response(resp_req, base_facts, {"items": 51, "bytes": 1000})
	d.effect == "RESTRICT"
	d.policy_ids == ["POL-E-16"]
}

test_pol_e_16_block_negative_count if blocked(run_response(resp_req, base_facts, {"items": -1, "bytes": 10}), "POL-E-16")

test_pol_e_16_block_size_unknown if blocked(run_response(resp_req, base_facts, {"items": 10}), "POL-E-16")

test_pol_e_16_block_default_limit_applies if {
	r := object.union(resp_req, {"tool": "mail"})
	d := run_response(r, base_facts, {"items": 21, "bytes": 10})
	d.effect == "RESTRICT"
}

test_pol_e_16_block_no_limit_at_all if {
	d := call.decision with input as {"request": object.union(resp_req, {"tool": "mail"}), "facts": base_facts, "response": {"items": 1, "bytes": 1}}
		with data.pol as json.remove(pol_data, ["default_result_limit"])
	blocked(d, "POL-E-16")
}

# --- POL-E-17 ---

test_pol_e_17_pass_within_volume if not "POL-E-17" in run(read_req, base_facts).policy_ids

test_pol_e_17_block_volume_exceeded if blocked(read_run([{"op": "replace", "path": "/usage/window_documents", "value": 201}]), "POL-E-17")

test_pol_e_17_block_blocked_pattern if blocked(read_run([{"op": "replace", "path": "/usage/blocked_pattern", "value": true}]), "POL-E-17")

test_pol_e_17_block_volume_unknown if blocked(read_run([{"op": "remove", "path": "/usage/window_documents"}]), "POL-E-17")

# --- POL-E-18 / POL-E-19 ---

account_facts := json.patch(base_facts, [{"op": "replace", "path": "/server_account", "value": {"used": true}}, {"op": "add", "path": "/acl", "value": {"user_can": true, "user": "kim", "doc_id": "doc-1"}}])

test_pol_e_18_pass_user_also_permitted if not "POL-E-18" in run(read_req, account_facts).policy_ids

test_pol_e_18_block_only_server_account_permitted if {
	blocked(run(read_req, json.patch(account_facts, [{"op": "replace", "path": "/acl/user_can", "value": false}])), "POL-E-18")
}

test_pol_e_18_block_acl_for_other_document if {
	blocked(run(read_req, json.patch(account_facts, [{"op": "replace", "path": "/acl/doc_id", "value": "doc-2"}])), "POL-E-18")
}

test_pol_e_18_block_acl_for_other_user if {
	blocked(run(read_req, json.patch(account_facts, [{"op": "replace", "path": "/acl/user", "value": "lee"}])), "POL-E-18")
}

test_pol_e_18_block_server_account_unknown if blocked(run(read_req, json.remove(base_facts, ["server_account"])), "POL-E-18")

test_pol_e_19_pass_account_in_scope if not "POL-E-19" in run(read_req, account_facts).policy_ids

test_pol_e_19_block_account_outside_scope if {
	blocked(run_with(read_req, account_facts, {"server_accounts": {"srv": {"operations": ["read"], "data_classes": ["public_doc"]}}}), "POL-E-19")
}

test_pol_e_19_block_other_document_than_account_scope if {
	blocked(run_with(read_req, account_facts, {"server_accounts": {"srv": {"operations": ["read"], "data_classes": ["internal_doc"], "documents": ["doc-9"]}}}), "POL-E-19")
}

test_pol_e_19_block_account_scope_missing if blocked(run_replacing(read_req, account_facts, "/server_accounts", {}), "POL-E-19")

# --- POL-E-20 / POL-E-21 ---

test_pol_e_20_pass_matching_confirmation if not "POL-E-20" in run(send_req, send_facts).policy_ids

test_pol_e_20_block_no_confirmation_asks_user if {
	d := run(send_req, json.remove(send_facts, ["confirmation"]))
	d.effect == "CONFIRM"
	d.policy_ids == ["POL-E-20", "POL-I-10"]
}

test_pol_i_10_block_no_confirmation_at_execution if "POL-I-10" in run(send_req, json.remove(send_facts, ["confirmation"])).policy_ids

test_pol_e_20_block_arguments_changed_after_confirmation if blocked(send_run([{"op": "replace", "path": "/arguments_sha256", "value": "h2"}]), "POL-E-20")

test_pol_e_20_block_recipient_changed if blocked(run(object.union(send_req, {"recipient": "b@partner.com"}), send_facts), "POL-E-20")

test_pol_e_20_block_confirmation_moved_to_other_tool if blocked(send_run([{"op": "replace", "path": "/confirmation/tool", "value": "share"}]), "POL-E-20")

test_pol_e_21_pass_unused_own_confirmation if not "POL-E-21" in run(send_req, send_facts).policy_ids

test_pol_e_21_block_reused_confirmation if blocked(send_run([{"op": "replace", "path": "/confirmation/used", "value": true}]), "POL-E-21")

test_pol_e_21_block_admin_confirmation_is_not_user if blocked(send_run([{"op": "replace", "path": "/confirmation/confirmed_by", "value": "admin-1"}]), "POL-E-21")

test_pol_e_21_block_expired_confirmation if blocked(send_run([{"op": "replace", "path": "/confirmation/expires_ns", "value": now}]), "POL-E-21")

test_pol_e_21_block_reserved_for_other_call if blocked(send_run([{"op": "replace", "path": "/confirmation/reserved_for", "value": "r0"}]), "POL-E-21")

# --- POL-E-23 ---

test_pol_e_23_pass_within_rate if not "POL-E-23" in run(read_req, base_facts).policy_ids

test_pol_e_23_block_agent_rate_exceeded if blocked(read_run([{"op": "replace", "path": "/usage/agent/window_calls", "value": 101}]), "POL-E-23")

test_pol_e_23_block_tool_concurrency_exceeded if blocked(read_run([{"op": "replace", "path": "/usage/tool/concurrent", "value": 11}]), "POL-E-23")

test_pol_e_23_block_counters_missing if blocked(read_run([{"op": "remove", "path": "/usage/user"}]), "POL-E-23")

test_pol_e_23_block_string_limits if {
	blocked(run_replacing(read_req, base_facts, "/rate_limits/tool", {"window_calls": "10", "concurrent": "2"}), "POL-E-23")
}

test_pol_e_23_block_limits_missing if blocked(run_replacing(read_req, base_facts, "/rate_limits", {}), "POL-E-23")

# --- POL-E-25 ---

test_pol_e_25_pass_central_store if not "POL-E-25" in run(read_req, base_facts).policy_ids

test_pol_e_25_pass_protected_buffer_only if {
	f := json.patch(base_facts, [{"op": "replace", "path": "/audit", "value": {"central_writable": false, "buffer_writable": true, "recorded": true}}])
	not "POL-E-25" in run(read_req, f).policy_ids
}

test_pol_e_25_block_no_store if {
	blocked(read_run([{"op": "replace", "path": "/audit", "value": {"central_writable": false, "buffer_writable": false}}]), "POL-E-25")
}

test_pol_e_25_block_writable_but_record_failed if blocked(read_run([{"op": "replace", "path": "/audit/recorded", "value": false}]), "POL-E-25")

test_pol_e_25_block_string_false if {
	blocked(read_run([{"op": "replace", "path": "/audit", "value": {"central_writable": "true", "buffer_writable": "true"}}]), "POL-E-25")
}

# --- POL-O-01 ---

test_pol_o_01_pass_unchanged_contract if not "POL-O-01" in run(read_req, base_facts).policy_ids

test_pol_o_01_block_changed_contract if blocked(read_run([{"op": "replace", "path": "/catalog/observed_contract_sha256", "value": "c9"}]), "POL-O-01")

# --- POL-O-02 ---

list_req := object.union(json.remove(read_req, ["operation"]), {"stage": "list"})

list_facts := object.union(base_facts, {"permitted_tools": ["search", "mail"]})

test_pol_o_02_pass_own_cache_permitted_tools if {
	d := run_response(list_req, list_facts, {"tools": ["search"], "cached": true, "cache_owner": "kim"})
	not "POL-O-02" in d.policy_ids
}

test_pol_o_02_block_other_users_cache if {
	blocked(run_response(list_req, list_facts, {"tools": ["search"], "cached": true, "cache_owner": "lee"}), "POL-O-02")
}

test_pol_o_02_block_unpermitted_tool_exposed if {
	blocked(run_response(list_req, list_facts, {"tools": ["search", "shell"], "cached": false}), "POL-O-02")
}

# --- POL-O-19 / POL-D-01 ---

test_pol_o_19_pass_active_server if not "POL-O-19" in run(read_req, base_facts).policy_ids

test_pol_o_19_block_suspended_tool if {
	reg := json.patch(registry, [{"op": "replace", "path": "/srv/tools/search/state", "value": "suspended"}])
	blocked(run_with(read_req, base_facts, {"servers": reg}), "POL-O-19")
}

test_pol_d_01_pass_active_server if not "POL-D-01" in run(read_req, base_facts).policy_ids

test_pol_d_01_block_decommissioned_server if {
	reg := json.patch(registry, [{"op": "replace", "path": "/srv/state", "value": "decommissioned"}])
	blocked(run_with(read_req, base_facts, {"servers": reg}), "POL-D-01")
}
