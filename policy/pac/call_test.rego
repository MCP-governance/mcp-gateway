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

# --- POL-003 ---

test_pol_003_pass_in_permission_table if not "POL-003" in run(read_req, base_facts).policy_ids

test_pol_003_block_other_data_class if {
	blocked(run(json.patch(read_req, [{"op": "replace", "path": "/target/data_class", "value": "hr_record"}]), base_facts), "POL-003")
}

test_pol_003_block_table_unavailable if {
	blocked(run_with(read_req, base_facts, {"permission_table": null}), "POL-003")
}

hr_req := json.patch(read_req, [{"op": "replace", "path": "/target/data_class", "value": "hr_record"}])

test_pol_003_pass_entry_approved_by_data_owner if {
	not "POL-003" in run_with(hr_req, base_facts, {"permission_table": [grant("kim", "search", "hr_record", "read")]}).policy_ids
}

test_pol_003_block_entry_approved_by_security_admin if {
	e := object.union(grant("kim", "search", "hr_record", "read"), {"approved_by_role": "security_admin"})
	blocked(run_with(hr_req, base_facts, {"permission_table": [e]}), "POL-003")
}

test_pol_003_block_exception_is_not_a_grant if {
	blocked(run_with(hr_req, base_facts, {"exceptions": [exception("POL-003", "kim", "srv/search", "data_owner")]}), "POL-003")
}

# --- POL-010 (실행 단계) ---

test_pol_010_pass_flagged_sensitive_tool if not "POL-010" in run(send_req, send_facts).policy_ids

test_pol_010_block_unflagged_sensitive_tool if {
	reg := json.patch(registry, [{"op": "replace", "path": "/srv/tools/mail/requires_confirmation", "value": false}])
	blocked(run_with(send_req, send_facts, {"servers": reg}), "POL-010")
}

test_pol_010_block_delete_on_read_tool if {
	r := object.union(read_req, {"operation": "delete"})
	blocked(run_with(r, base_facts, {"permission_table": [grant("kim", "search", "internal_doc", "delete")]}), "POL-010")
}

# --- POL-013 ---

test_pol_013_pass_normal_basis if not "POL-013" in run(read_req, base_facts).policy_ids

test_pol_013_block_expired_exception_basis if {
	e := object.union(exception("POL-013", "srv", "search", "security_admin"), {"not_after_ns": now - 1})
	blocked(run_with(read_req, json.patch(base_facts, [{"op": "replace", "path": "/approval/basis", "value": "exception"}]), {"exceptions": [e]}), "POL-013")
}

test_pol_013_pass_valid_exception_basis if {
	d := run_with(read_req, json.patch(base_facts, [{"op": "replace", "path": "/approval/basis", "value": "exception"}]), {"exceptions": [exception("POL-013", "srv", "search", "security_admin")]})
	not "POL-013" in d.policy_ids
}

test_pol_013_block_basis_missing if blocked(run(read_req, json.remove(base_facts, ["approval"])), "POL-013")

# --- POL-015 ---

test_pol_015_pass_exact_match if not "POL-015" in run(read_req, base_facts).policy_ids

test_pol_015_block_ambiguous_name if blocked(read_run([{"op": "replace", "path": "/catalog/matches", "value": 2}]), "POL-015")

test_pol_015_block_unknown_tool if blocked(run(object.union(read_req, {"tool": "search2"}), base_facts), "POL-015")

# --- POL-016 ---

test_pol_016_pass_valid_token if not "POL-016" in run(read_req, base_facts).policy_ids

test_pol_016_block_token_for_other_server if blocked(read_run([{"op": "replace", "path": "/token/audience", "value": "other"}]), "POL-016")

test_pol_016_block_expired_token if blocked(read_run([{"op": "replace", "path": "/token/expires_ns", "value": now}]), "POL-016")

test_pol_016_block_no_token if blocked(run(read_req, json.remove(base_facts, ["token"])), "POL-016")

test_pol_016_pass_local_server_without_token if {
	reg := json.patch(registry, [{"op": "add", "path": "/srv/kind", "value": "local"}])
	not "POL-016" in run_with(read_req, object.union(base_facts, {"token": {"used": false}}), {"servers": reg}).policy_ids
}

test_pol_016_block_remote_server_without_token if blocked(read_run([{"op": "replace", "path": "/token", "value": {"used": false}}]), "POL-016")

# --- POL-025 ---

test_pol_025_pass_bound_credential if not "POL-025" in run(read_req, base_facts).policy_ids

test_pol_025_pass_no_credential_used if not "POL-025" in read_run([{"op": "replace", "path": "/credential", "value": {"used": false}}]).policy_ids

test_pol_025_block_other_server_credential if blocked(read_run([{"op": "replace", "path": "/credential/bound_server", "value": "github"}]), "POL-025")

test_pol_025_block_credential_unknown if blocked(run(read_req, json.remove(base_facts, ["credential"])), "POL-025")

# --- POL-034 ---

test_pol_034_pass_delegated if not "POL-034" in run(read_req, base_facts).policy_ids

test_pol_034_block_other_agent if blocked(run(object.union(read_req, {"agent": "unknown-agent"}), base_facts), "POL-034")

test_pol_034_block_expired_delegation if {
	blocked(run_with(read_req, base_facts, {"delegations": [object.union(delegation("search", "internal_doc", "read"), {"not_after_ns": now})]}), "POL-034")
}

# --- POL-035 ---

test_pol_035_pass_fresh_lookup if not "POL-035" in run(read_req, base_facts).policy_ids

test_pol_035_block_lookup_failed if blocked(read_run([{"op": "replace", "path": "/permission_lookup/status", "value": "error"}]), "POL-035")

test_pol_035_block_lookup_reused_from_other_call if {
	blocked(read_run([{"op": "replace", "path": "/permission_lookup/request_id", "value": "r0"}]), "POL-035")
}

# --- POL-036 ---

test_pol_036_pass_document_granted if not "POL-036" in run(read_req, base_facts).policy_ids

test_pol_036_block_other_document if {
	blocked(run(json.patch(read_req, [{"op": "replace", "path": "/target/doc_id", "value": "doc-2"}]), base_facts), "POL-036")
}

test_pol_036_block_document_unknown if blocked(run(json.remove(read_req, ["target/doc_id"]), base_facts), "POL-036")

# --- POL-037 ---

test_pol_037_pass_plain_call if not "POL-037" in run(read_req, base_facts).policy_ids

test_pol_037_block_external_content_as_approval if {
	r := object.union(read_req, {"intent": "approval"})
	blocked(run(r, json.patch(base_facts, [{"op": "replace", "path": "/provenance/external_content", "value": true}])), "POL-037")
}

test_pol_037_block_permission_change_with_unknown_provenance if {
	blocked(run(object.union(read_req, {"intent": "permission_change"}), json.remove(base_facts, ["provenance"])), "POL-037")
}

test_pol_037_pass_approval_from_user_only if not "POL-037" in run(object.union(read_req, {"intent": "approval"}), base_facts).policy_ids

test_pol_037_block_unknown_intent if blocked(run(object.union(read_req, {"intent": "grant"}), base_facts), "POL-037")

# --- POL-038 ---

test_pol_038_pass_clean_input if not "POL-038" in run(read_req, base_facts).policy_ids

test_pol_038_block_secret_in_input if blocked(read_run([{"op": "replace", "path": "/inspection/secrets", "value": ["github_token"]}]), "POL-038")

test_pol_038_block_unneeded_personal_data if {
	blocked(read_run([{"op": "replace", "path": "/inspection/personal_data", "value": ["resident_number"]}]), "POL-038")
}

test_pol_038_pass_allowed_personal_field if {
	not "POL-038" in read_run([{"op": "replace", "path": "/inspection/personal_data", "value": ["employee_id"]}]).policy_ids
}

test_pol_038_block_completed_without_lists if {
	blocked(read_run([{"op": "replace", "path": "/inspection", "value": {"status": "completed"}}]), "POL-038")
}

test_pol_038_block_secret_list_as_string if blocked(read_run([{"op": "replace", "path": "/inspection/secrets", "value": "token-present"}]), "POL-038")

test_pol_038_block_inspection_not_done if blocked(run(read_req, json.remove(base_facts, ["inspection"])), "POL-038")

# --- POL-040 ---

test_pol_040_pass_approved_final_host if not "POL-040" in run(send_req, send_facts).policy_ids

test_pol_040_block_redirect_to_unapproved_host if blocked(send_run([{"op": "replace", "path": "/egress/final_host", "value": "evil.example"}]), "POL-040")

test_pol_040_block_internal_ip if blocked(send_run([{"op": "replace", "path": "/egress/resolved_ips", "value": ["192.168.0.10"]}]), "POL-040")

test_pol_040_block_outside_approved_ip_range if {
	reg := json.patch(registry, [{"op": "add", "path": "/srv/tools/mail/egress_ip_ranges", "value": ["8.8.8.0/24"]}])
	blocked(run_with(send_req, send_facts, {"servers": reg}), "POL-040")
}

test_pol_040_pass_inside_approved_ip_range if {
	reg := json.patch(registry, [{"op": "add", "path": "/srv/tools/mail/egress_ip_ranges", "value": ["93.184.216.0/24"]}])
	not "POL-040" in run_with(send_req, send_facts, {"servers": reg}).policy_ids
}

test_pol_040_block_egress_unknown if blocked(run(send_req, json.remove(send_facts, ["egress"])), "POL-040")

# --- POL-041 ---

test_pol_041_pass_approved_transfer if not "POL-041" in run(send_req, send_facts).policy_ids

test_pol_041_block_other_purpose if blocked(run(object.union(send_req, {"purpose": "마케팅"}), send_facts), "POL-041")

test_pol_041_block_other_recipient if blocked(run(object.union(send_req, {"recipient": "x@other.com"}), send_facts), "POL-041")

# --- POL-042 ---

test_pol_042_pass_inside_root if not "POL-042" in run(read_req, base_facts).policy_ids

test_pol_042_block_symlink_outside_root if blocked(read_run([{"op": "replace", "path": "/path/resolved", "value": "/etc/shadow"}]), "POL-042")

test_pol_042_block_prefix_trick if blocked(read_run([{"op": "replace", "path": "/path/resolved", "value": "/srv/data-secret/a.txt"}]), "POL-042")

test_pol_042_block_parent_traversal if blocked(read_run([{"op": "replace", "path": "/path/resolved", "value": "/srv/data/../../etc/passwd"}]), "POL-042")

test_pol_042_block_null_path_on_file_tool if {
	r := json.patch(read_req, [{"op": "replace", "path": "/target/path", "value": null}])
	blocked(run(r, json.patch(base_facts, [{"op": "replace", "path": "/path/resolved", "value": "/etc/passwd"}])), "POL-042")
}

test_pol_042_block_unresolved_path if blocked(run(read_req, json.remove(base_facts, ["path"])), "POL-042")

# --- POL-044 ---

flow_req := object.union(read_req, {"source_server": "drive", "purpose": "요약"})

test_pol_044_pass_approved_flow if not "POL-044" in run(flow_req, base_facts).policy_ids

test_pol_044_block_unapproved_flow if blocked(run(object.union(flow_req, {"source_server": "slack"}), base_facts), "POL-044")

test_pol_044_block_credential_transfer if blocked(read_run([{"op": "replace", "path": "/data/contains_credential", "value": true}]), "POL-044")

test_pol_044_block_source_server_not_a_name if blocked(run(object.union(read_req, {"source_server": ["drive"]}), base_facts), "POL-044")

test_pol_044_block_credential_unknown if blocked(run(read_req, json.remove(base_facts, ["data"])), "POL-044")

# --- POL-046 ---

shell_req := object.union(read_req, {"tool": "shell", "operation": "execute"})

shell_facts := object.union(base_facts, {"catalog": {"matches": 1, "observed_contract_sha256": "c3"}, "arguments_validated": true})

test_pol_046_pass_validated_command if not "POL-046" in run(shell_req, shell_facts).policy_ids

test_pol_046_block_unvalidated_arguments if blocked(run(shell_req, object.union(shell_facts, {"arguments_validated": false})), "POL-046")

test_pol_046_block_execute_on_unclassified_tool if {
	r := object.union(read_req, {"operation": "execute"})
	blocked(run_with(r, base_facts, {"permission_table": [grant("kim", "search", "internal_doc", "execute")]}), "POL-046")
}

test_pol_046_block_unapproved_operation if {
	r := object.union(shell_req, {"operation": "write"})
	blocked(run_with(r, shell_facts, {"permission_table": [grant("kim", "shell", "internal_doc", "write")]}), "POL-046")
}

# --- POL-047 ---

fetch_req := json.patch(read_req, [{"op": "replace", "path": "/tool", "value": "fetch"}, {"op": "replace", "path": "/target", "value": {"data_class": "public_doc"}}])

fetch_facts := object.union(base_facts, {
	"catalog": {"matches": 1, "observed_contract_sha256": "c4"},
	"egress": {"final_host": "docs.vendor.com", "resolved_ips": ["151.101.1.69"]},
})

test_pol_047_pass_approved_url if not "POL-047" in run(fetch_req, fetch_facts).policy_ids

test_pol_047_block_metadata_endpoint if {
	f := json.patch(fetch_facts, [{"op": "replace", "path": "/egress/resolved_ips", "value": ["169.254.169.254"]}])
	blocked(run(fetch_req, f), "POL-047")
}

test_pol_047_block_cidr_instead_of_address if {
	blocked(run(fetch_req, json.patch(fetch_facts, [{"op": "replace", "path": "/egress/resolved_ips", "value": ["8.8.8.0/24"]}])), "POL-047")
}

test_pol_047_block_unapproved_host if {
	blocked(run(fetch_req, json.patch(fetch_facts, [{"op": "replace", "path": "/egress/final_host", "value": "pastebin.com"}])), "POL-047")
}

# --- POL-048 ---

test_pol_048_pass_valid_schema if not "POL-048" in run(read_req, base_facts).policy_ids

test_pol_048_block_undeclared_field if blocked(read_run([{"op": "replace", "path": "/schema/undeclared_fields", "value": ["__hidden"]}]), "POL-048")

test_pol_048_block_invalid_schema if blocked(read_run([{"op": "replace", "path": "/schema/valid", "value": false}]), "POL-048")

# --- POL-049 ---

resp_req := object.union(read_req, {"stage": "response"})

test_pol_049_pass_within_limit if run_response(resp_req, base_facts, {"items": 50, "bytes": 1000}).effect == "ALLOW"

test_pol_049_block_over_limit_restricts if {
	d := run_response(resp_req, base_facts, {"items": 51, "bytes": 1000})
	d.effect == "RESTRICT"
	d.policy_ids == ["POL-049"]
}

test_pol_049_block_negative_count if blocked(run_response(resp_req, base_facts, {"items": -1, "bytes": 10}), "POL-049")

test_pol_049_block_size_unknown if blocked(run_response(resp_req, base_facts, {"items": 10}), "POL-049")

test_pol_049_block_default_limit_applies if {
	r := object.union(resp_req, {"tool": "mail"})
	d := run_response(r, base_facts, {"items": 21, "bytes": 10})
	d.effect == "RESTRICT"
}

test_pol_049_block_no_limit_at_all if {
	d := call.decision with input as {"request": object.union(resp_req, {"tool": "mail"}), "facts": base_facts, "response": {"items": 1, "bytes": 1}}
		with data.pol as json.remove(pol_data, ["default_result_limit"])
	blocked(d, "POL-049")
}

# --- POL-050 ---

test_pol_050_pass_within_volume if not "POL-050" in run(read_req, base_facts).policy_ids

test_pol_050_block_volume_exceeded if blocked(read_run([{"op": "replace", "path": "/usage/window_documents", "value": 201}]), "POL-050")

test_pol_050_block_blocked_pattern if blocked(read_run([{"op": "replace", "path": "/usage/blocked_pattern", "value": true}]), "POL-050")

test_pol_050_block_volume_unknown if blocked(read_run([{"op": "remove", "path": "/usage/window_documents"}]), "POL-050")

# --- POL-051 / POL-052 ---

account_facts := json.patch(base_facts, [{"op": "replace", "path": "/server_account", "value": {"used": true}}, {"op": "add", "path": "/acl", "value": {"user_can": true, "user": "kim", "doc_id": "doc-1"}}])

test_pol_051_pass_user_also_permitted if not "POL-051" in run(read_req, account_facts).policy_ids

test_pol_051_block_only_server_account_permitted if {
	blocked(run(read_req, json.patch(account_facts, [{"op": "replace", "path": "/acl/user_can", "value": false}])), "POL-051")
}

test_pol_051_block_acl_for_other_document if {
	blocked(run(read_req, json.patch(account_facts, [{"op": "replace", "path": "/acl/doc_id", "value": "doc-2"}])), "POL-051")
}

test_pol_051_block_acl_for_other_user if {
	blocked(run(read_req, json.patch(account_facts, [{"op": "replace", "path": "/acl/user", "value": "lee"}])), "POL-051")
}

test_pol_051_block_server_account_unknown if blocked(run(read_req, json.remove(base_facts, ["server_account"])), "POL-051")

test_pol_052_pass_account_in_scope if not "POL-052" in run(read_req, account_facts).policy_ids

test_pol_052_block_account_outside_scope if {
	blocked(run_with(read_req, account_facts, {"server_accounts": {"srv": {"operations": ["read"], "data_classes": ["public_doc"]}}}), "POL-052")
}

test_pol_052_block_other_document_than_account_scope if {
	blocked(run_with(read_req, account_facts, {"server_accounts": {"srv": {"operations": ["read"], "data_classes": ["internal_doc"], "documents": ["doc-9"]}}}), "POL-052")
}

test_pol_052_block_account_scope_missing if blocked(run_replacing(read_req, account_facts, "/server_accounts", {}), "POL-052")

# --- POL-053 / POL-054 ---

test_pol_053_pass_matching_confirmation if not "POL-053" in run(send_req, send_facts).policy_ids

test_pol_053_block_no_confirmation_asks_user if {
	d := run(send_req, json.remove(send_facts, ["confirmation"]))
	d.effect == "CONFIRM"
	d.policy_ids == ["POL-010", "POL-053"]
}

test_pol_010_block_no_confirmation_at_execution if "POL-010" in run(send_req, json.remove(send_facts, ["confirmation"])).policy_ids

test_pol_053_block_arguments_changed_after_confirmation if blocked(send_run([{"op": "replace", "path": "/arguments_sha256", "value": "h2"}]), "POL-053")

test_pol_053_block_recipient_changed if blocked(run(object.union(send_req, {"recipient": "b@partner.com"}), send_facts), "POL-053")

test_pol_053_block_confirmation_moved_to_other_tool if blocked(send_run([{"op": "replace", "path": "/confirmation/tool", "value": "share"}]), "POL-053")

test_pol_054_pass_unused_own_confirmation if not "POL-054" in run(send_req, send_facts).policy_ids

test_pol_054_block_reused_confirmation if blocked(send_run([{"op": "replace", "path": "/confirmation/used", "value": true}]), "POL-054")

test_pol_054_block_admin_confirmation_is_not_user if blocked(send_run([{"op": "replace", "path": "/confirmation/confirmed_by", "value": "admin-1"}]), "POL-054")

test_pol_054_block_expired_confirmation if blocked(send_run([{"op": "replace", "path": "/confirmation/expires_ns", "value": now}]), "POL-054")

test_pol_054_block_reserved_for_other_call if blocked(send_run([{"op": "replace", "path": "/confirmation/reserved_for", "value": "r0"}]), "POL-054")

# --- POL-056 ---

test_pol_056_pass_within_rate if not "POL-056" in run(read_req, base_facts).policy_ids

test_pol_056_block_agent_rate_exceeded if blocked(read_run([{"op": "replace", "path": "/usage/agent/window_calls", "value": 101}]), "POL-056")

test_pol_056_block_tool_concurrency_exceeded if blocked(read_run([{"op": "replace", "path": "/usage/tool/concurrent", "value": 11}]), "POL-056")

test_pol_056_block_counters_missing if blocked(read_run([{"op": "remove", "path": "/usage/user"}]), "POL-056")

test_pol_056_block_string_limits if {
	blocked(run_replacing(read_req, base_facts, "/rate_limits/tool", {"window_calls": "10", "concurrent": "2"}), "POL-056")
}

test_pol_056_block_limits_missing if blocked(run_replacing(read_req, base_facts, "/rate_limits", {}), "POL-056")

# --- POL-058 ---

test_pol_058_pass_central_store if not "POL-058" in run(read_req, base_facts).policy_ids

test_pol_058_pass_protected_buffer_only if {
	f := json.patch(base_facts, [{"op": "replace", "path": "/audit", "value": {"central_writable": false, "buffer_writable": true, "recorded": true}}])
	not "POL-058" in run(read_req, f).policy_ids
}

test_pol_058_block_no_store if {
	blocked(read_run([{"op": "replace", "path": "/audit", "value": {"central_writable": false, "buffer_writable": false}}]), "POL-058")
}

test_pol_058_block_writable_but_record_failed if blocked(read_run([{"op": "replace", "path": "/audit/recorded", "value": false}]), "POL-058")

test_pol_058_block_string_false if {
	blocked(read_run([{"op": "replace", "path": "/audit", "value": {"central_writable": "true", "buffer_writable": "true"}}]), "POL-058")
}

# --- POL-063 ---

test_pol_063_pass_unchanged_contract if not "POL-063" in run(read_req, base_facts).policy_ids

test_pol_063_block_changed_contract if blocked(read_run([{"op": "replace", "path": "/catalog/observed_contract_sha256", "value": "c9"}]), "POL-063")

# --- POL-064 ---

list_req := object.union(json.remove(read_req, ["operation"]), {"stage": "list"})

list_facts := object.union(base_facts, {"permitted_tools": ["search", "mail"]})

test_pol_064_pass_own_cache_permitted_tools if {
	d := run_response(list_req, list_facts, {"tools": ["search"], "cached": true, "cache_owner": "kim"})
	not "POL-064" in d.policy_ids
}

test_pol_064_block_other_users_cache if {
	blocked(run_response(list_req, list_facts, {"tools": ["search"], "cached": true, "cache_owner": "lee"}), "POL-064")
}

test_pol_064_block_unpermitted_tool_exposed if {
	blocked(run_response(list_req, list_facts, {"tools": ["search", "shell"], "cached": false}), "POL-064")
}

# --- POL-081 / POL-082 ---

test_pol_081_pass_active_server if not "POL-081" in run(read_req, base_facts).policy_ids

test_pol_081_block_suspended_tool if {
	reg := json.patch(registry, [{"op": "replace", "path": "/srv/tools/search/state", "value": "suspended"}])
	blocked(run_with(read_req, base_facts, {"servers": reg}), "POL-081")
}

test_pol_082_pass_active_server if not "POL-082" in run(read_req, base_facts).policy_ids

test_pol_082_block_decommissioned_server if {
	reg := json.patch(registry, [{"op": "replace", "path": "/srv/state", "value": "decommissioned"}])
	blocked(run_with(read_req, base_facts, {"servers": reg}), "POL-082")
}
