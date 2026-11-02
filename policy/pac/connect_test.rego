# 등록 및 연결 시험. 이름 규칙: test_pol_<번호>_pass_* / test_pol_<번호>_block_*.
package mcp.pol.connect_test

import data.mcp.pol.connect
import rego.v1

now := 1793000000000000000

day := 86400000000000

registry := {"srv": {
	"state": "active", "address": "https://srv.corp/mcp", "identity": "sha256:srv",
	"approval": {"not_after_ns": now + day, "status": "approved", "approved_by": "admin-1", "approved_by_role": "security_admin"},
	"auth_servers": [{"address": "https://idp.corp", "id": "corp-idp"}],
	"metadata_hosts": ["idp.corp"],
	"approved_scopes": ["repo:read"],
	"approved_access": ["search:internal_doc"],
	"tools": {"search": {"state": "active"}, "export": {"state": "retired"}},
	"launch": {"executable": "/opt/mcp/srv", "args": ["--stdio"], "env": {"MODE": "ro"}, "sha256": "abc"},
	"permissions": ["fs:read:/srv/data"],
}}

consent := {
	"user": "kim", "server_id": "srv", "decision": "accept", "functions": ["search"], "not_after_ns": now + day,
	"shown": {"provider": "acme", "address": "https://srv.corp/mcp", "functions": ["search"]},
}

conn := {
	"stage": "connect", "server_id": "srv", "user": "kim", "kind": "remote", "address": "https://srv.corp/mcp",
	"identity": "sha256:srv", "transport": {"scheme": "https"}, "approval": {"basis": "normal"},
	"consent": consent, "requested_functions": ["search"], "requested_access": ["search:internal_doc"],
	"credential": {"used": false},
}

restored := {
	"stage": "restore", "server_id": "srv",
	"restored": {"address": "https://srv.corp/mcp", "tools": ["search"], "access": ["search:internal_doc"]},
}

oauth := {
	"stage": "oauth", "server_id": "srv", "auth_server": {"address": "https://idp.corp", "id": "corp-idp"},
	"metadata": {"request_host": "idp.corp", "final_host": "idp.corp", "resolved_ips": ["93.184.216.34"]},
	"requested_scopes": ["repo:read"], "credential": {"used": true, "bound_server": "srv"},
}

launch := {
	"stage": "launch", "server_id": "srv", "kind": "local", "approval": {"basis": "normal"},
	"launch": {
		"executable": "/opt/mcp/srv", "args": ["--stdio"], "env": {"MODE": "ro"}, "sha256": "abc",
		"observed_permissions": ["fs:read:/srv/data"],
		"isolation": {"verified": true, "public_read_only": true, "internal_data_blocked": true},
	},
}

approval := {"server_id": "srv", "purpose": "문서 검색", "scope": "search", "policy_version": "2026-10-27", "method": "manual", "recorded": true}

pol_data := {"servers": registry, "exceptions": []}

run(c) := d if {
	d := connect.decision with input as {"connection": c, "facts": {"now_ns": now, "trusted": true}} with data.pol as pol_data
}

run_with(c, extra) := d if {
	d := connect.decision with input as {"connection": c, "facts": {"now_ns": now, "trusted": true}}
		with data.pol as object.union(pol_data, extra)
}

run_approve(a) := d if {
	d := connect.decision with input as {"connection": {"stage": "approve", "server_id": "srv"}, "approval": a, "facts": {"now_ns": now, "trusted": true}}
		with data.pol as pol_data
}

blocked(d, pol) if {
	d.effect == "DENY"
	pol in d.policy_ids
}

exception(pol, target, scope, role) := {
	"policy_id": pol, "target": target, "scope": [scope], "status": "approved",
	"approved_by_role": role, "approved_by": "admin-1", "not_after_ns": now + day,
}

test_connect_all_pass_allow if run(conn).effect == "ALLOW"

test_oauth_all_pass_allow if run(oauth).effect == "ALLOW"

test_launch_all_pass_allow if run(launch).effect == "ALLOW"

test_approve_all_pass_allow if run_approve(approval).effect == "ALLOW"

test_contract_block_unknown_stage if blocked(run(object.union(conn, {"stage": "other"})), "INPUT_CONTRACT")

# --- POL-R-01 ---

test_pol_r_01_pass_registered_active if not "POL-R-01" in run(conn).policy_ids

test_pol_r_01_block_unregistered if blocked(run(object.union(conn, {"server_id": "ghost"})), "POL-R-01")

test_pol_r_01_block_identity_mismatch if blocked(run(object.union(conn, {"identity": "sha256:other"})), "POL-R-01")

test_pol_r_01_block_expired_approval if {
	d := connect.decision with input as {"connection": conn, "facts": {"now_ns": now + (2 * day), "trusted": true}} with data.pol as pol_data
	blocked(d, "POL-R-01")
}

test_pol_r_01_block_null_identities if {
	reg := json.patch(registry, [{"op": "replace", "path": "/srv/identity", "value": null}])
	d := connect.decision with input as {"connection": object.union(conn, {"identity": null}), "facts": {"now_ns": now, "trusted": true}}
		with data.pol as {"servers": reg, "exceptions": []}
	blocked(d, "POL-R-01")
}

test_pol_r_01_block_approval_not_by_security_admin if {
	reg := json.patch(registry, [{"op": "replace", "path": "/srv/approval/approved_by_role", "value": "data_owner"}])
	d := connect.decision with input as {"connection": conn, "facts": {"now_ns": now, "trusted": true}} with data.pol as {"servers": reg, "exceptions": []}
	blocked(d, "POL-R-01")
}

test_pol_r_01_block_no_registry_at_all if {
	d := connect.decision with input as {"connection": conn, "facts": {"now_ns": now, "trusted": true}} with data.pol as {}
	blocked(d, "POL-R-01")
}

# --- POL-R-02 ---

exc_conn := object.union(conn, {"approval": {"basis": "exception"}})

test_pol_r_02_pass_valid_exception if {
	not "POL-R-02" in run_with(exc_conn, {"exceptions": [exception("POL-R-02", "srv", "connect", "security_admin")]}).policy_ids
}

test_pol_r_02_block_expired_exception if {
	e := object.union(exception("POL-R-02", "srv", "connect", "security_admin"), {"not_after_ns": now})
	blocked(run_with(exc_conn, {"exceptions": [e]}), "POL-R-02")
}

test_pol_r_02_block_exception_for_other_scope if {
	blocked(run_with(exc_conn, {"exceptions": [exception("POL-R-02", "srv", "launch", "security_admin")]}), "POL-R-02")
}

test_pol_r_02_block_basis_missing if blocked(run(json.remove(conn, ["approval"])), "POL-R-02")

# --- POL-R-03 ---

test_pol_r_03_pass_complete_record if not "POL-R-03" in run_approve(approval).policy_ids

test_pol_r_03_block_missing_policy_version if blocked(run_approve(json.remove(approval, ["policy_version"])), "POL-R-03")

test_pol_r_03_block_exception_without_end_date if {
	blocked(run_approve(object.union(approval, {"method": "exception", "approver": "admin-1"})), "POL-R-03")
}

test_pol_r_03_pass_exception_with_approver_and_end if {
	not "POL-R-03" in run_approve(object.union(approval, {"method": "exception", "approver": "admin-1", "not_after_ns": now + day})).policy_ids
}

test_pol_r_03_block_record_failed if blocked(run_approve(object.union(approval, {"recorded": false})), "POL-R-03")

test_pol_r_03_block_approval_for_other_server if blocked(run_approve(object.union(approval, {"server_id": "other"})), "POL-R-03")

test_pol_r_03_block_exception_with_past_end_date if {
	blocked(run_approve(object.union(approval, {"method": "exception", "approver": "admin-1", "not_after_ns": now})), "POL-R-03")
}

test_pol_r_03_block_unknown_method if blocked(run_approve(object.union(approval, {"method": "tofu"})), "POL-R-03")

test_pol_r_03_block_no_approval_object if {
	d := connect.decision with input as {"connection": {"stage": "approve", "server_id": "srv"}, "facts": {"now_ns": now, "trusted": true}}
		with data.pol as pol_data
	blocked(d, "POL-R-03")
}

# --- POL-R-08 ---

test_pol_r_08_pass_approved_auth_server if not "POL-R-08" in run(oauth).policy_ids

test_pol_r_08_block_other_auth_server if {
	blocked(run(object.union(oauth, {"auth_server": {"address": "https://evil-idp.example", "id": "corp-idp"}})), "POL-R-08")
}

test_pol_r_08_block_missing_auth_server if blocked(run(json.remove(oauth, ["auth_server"])), "POL-R-08")

test_pol_r_08_block_null_auth_server if blocked(run(object.union(oauth, {"auth_server": null})), "POL-R-08")

test_pol_r_08_block_same_address_other_id if {
	blocked(run(object.union(oauth, {"auth_server": {"address": "https://idp.corp", "id": "other-idp"}})), "POL-R-08")
}

# --- POL-R-11 ---

test_pol_r_11_pass_approved_metadata_host if not "POL-R-11" in run(oauth).policy_ids

test_pol_r_11_block_unapproved_metadata_host if {
	blocked(run(json.patch(oauth, [{"op": "replace", "path": "/metadata/request_host", "value": "169.254.169.254"}])), "POL-R-11")
}

test_pol_r_11_block_metadata_missing if blocked(run(json.remove(oauth, ["metadata"])), "POL-R-11")

test_pol_r_11_block_unregistered_server if blocked(run(object.union(oauth, {"server_id": "ghost"})), "POL-R-11")

# --- POL-R-12 ---

test_pol_r_12_pass_public_final_address if not "POL-R-12" in run(oauth).policy_ids

test_pol_r_12_block_redirect_to_private_ip if {
	blocked(run(json.patch(oauth, [{"op": "replace", "path": "/metadata/resolved_ips", "value": ["10.0.0.5"]}])), "POL-R-12")
}

test_pol_r_12_block_redirect_to_other_host if {
	blocked(run(json.patch(oauth, [{"op": "replace", "path": "/metadata/final_host", "value": "evil.example"}])), "POL-R-12")
}

test_pol_r_12_block_no_resolution if {
	blocked(run(json.patch(oauth, [{"op": "replace", "path": "/metadata/resolved_ips", "value": []}])), "POL-R-12")
}

test_pol_r_12_block_malformed_ip if {
	blocked(run(json.patch(oauth, [{"op": "replace", "path": "/metadata/resolved_ips", "value": ["not-an-ip"]}])), "POL-R-12")
}

test_pol_r_12_block_ipv4_mapped_private if {
	blocked(run(json.patch(oauth, [{"op": "replace", "path": "/metadata/resolved_ips", "value": ["::ffff:10.0.0.5"]}])), "POL-R-12")
}

test_pol_r_12_block_documentation_range if {
	blocked(run(json.patch(oauth, [{"op": "replace", "path": "/metadata/resolved_ips", "value": ["203.0.113.10"]}])), "POL-R-12")
}

test_pol_r_12_block_ipv6_loopback if {
	blocked(run(json.patch(oauth, [{"op": "replace", "path": "/metadata/resolved_ips", "value": ["::1"]}])), "POL-R-12")
}

# --- POL-R-15 ---

test_pol_r_15_pass_scope_within_approval if not "POL-R-15" in run(oauth).policy_ids

test_pol_r_15_pass_access_within_approval if not "POL-R-15" in run(conn).policy_ids

test_pol_r_15_block_access_expansion if {
	blocked(run(object.union(conn, {"requested_access": ["search:internal_doc", "delete:internal_doc"]})), "POL-R-15")
}

test_pol_r_15_block_access_missing if blocked(run(json.remove(conn, ["requested_access"])), "POL-R-15")

test_pol_r_15_block_access_null if blocked(run(object.union(conn, {"requested_access": null})), "POL-R-15")

test_pol_r_15_block_scope_expansion if blocked(run(object.union(oauth, {"requested_scopes": ["repo:read", "repo:admin"]})), "POL-R-15")

test_pol_r_15_block_scopes_missing if blocked(run(json.remove(oauth, ["requested_scopes"])), "POL-R-15")

# 범위 확대는 등록부의 승인 scope를 바꾼 뒤에만 — 예외 항목으로는 넓어지지 않는다.
test_pol_r_15_block_exception_does_not_extend_scope if {
	d := run_with(object.union(oauth, {"requested_scopes": ["repo:admin"]}), {"exceptions": [exception("POL-R-15", "srv", "repo:admin", "security_admin")]})
	blocked(d, "POL-R-15")
}

# --- POL-R-18 ---

test_pol_r_18_pass_remote_https if not "POL-R-18" in run(conn).policy_ids

test_pol_r_18_block_remote_plain_http if blocked(run(object.union(conn, {"transport": {"scheme": "http"}})), "POL-R-18")

test_pol_r_18_block_local_without_launch_config if {
	reg := json.remove(registry, ["srv/launch"])
	d := connect.decision with input as {"connection": launch, "facts": {"now_ns": now, "trusted": true}} with data.pol as {"servers": reg, "exceptions": []}
	blocked(d, "POL-R-18")
}

test_pol_r_18_block_empty_launch_registration if {
	reg := json.patch(registry, [{"op": "replace", "path": "/srv/launch", "value": {}}])
	d := connect.decision with input as {"connection": object.union(conn, {"kind": "local"}), "facts": {"now_ns": now, "trusted": true}}
		with data.pol as {"servers": reg, "exceptions": []}
	blocked(d, "POL-R-18")
}

test_pol_r_18_block_unknown_kind if blocked(run(json.remove(conn, ["kind"])), "POL-R-18")

# --- POL-R-20 ---

test_pol_r_20_pass_launch_matches if not "POL-R-20" in run(launch).policy_ids

test_pol_r_20_block_changed_args if {
	blocked(run(json.patch(launch, [{"op": "replace", "path": "/launch/args", "value": ["--stdio", "--allow-write"]}])), "POL-R-20")
}

test_pol_r_20_block_changed_binary_hash if {
	blocked(run(json.patch(launch, [{"op": "replace", "path": "/launch/sha256", "value": "def"}])), "POL-R-20")
}

test_pol_r_20_block_env_missing if blocked(run(json.remove(launch, ["launch/env"])), "POL-R-20")

test_pol_r_20_block_empty_hashes_on_both_sides if {
	reg := json.patch(registry, [{"op": "replace", "path": "/srv/launch/sha256", "value": ""}])
	c := json.patch(launch, [{"op": "replace", "path": "/launch/sha256", "value": ""}])
	d := connect.decision with input as {"connection": c, "facts": {"now_ns": now, "trusted": true}} with data.pol as {"servers": reg, "exceptions": []}
	blocked(d, "POL-R-20")
}

# --- POL-I-08 ---

test_pol_i_08_pass_permissions_within_approval if not "POL-I-08" in run(launch).policy_ids

test_pol_i_08_block_excess_permission_isolated_restricts if {
	d := run(json.patch(launch, [{"op": "replace", "path": "/launch/observed_permissions", "value": ["fs:read:/srv/data", "net:any"]}]))
	d.effect == "RESTRICT"
	"POL-I-08" in d.policy_ids
}

test_pol_i_08_block_excess_permission_without_isolation if {
	c := json.patch(launch, [
		{"op": "replace", "path": "/launch/observed_permissions", "value": ["net:any"]},
		{"op": "replace", "path": "/launch/isolation/verified", "value": false},
	])
	blocked(run(c), "POL-I-08")
}

test_pol_i_08_block_unknown_permissions_without_isolation if {
	c := json.patch(json.remove(launch, ["launch/observed_permissions"]), [{"op": "remove", "path": "/launch/isolation"}])
	blocked(run(c), "POL-I-08")
}

# --- POL-R-21 ---

test_pol_r_21_pass_consented if not "POL-R-21" in run(conn).policy_ids

test_pol_r_21_block_declined if blocked(run(json.patch(conn, [{"op": "replace", "path": "/consent/decision", "value": "decline"}])), "POL-R-21")

test_pol_r_21_block_consent_for_other_server if {
	blocked(run(json.patch(conn, [{"op": "replace", "path": "/consent/server_id", "value": "other"}])), "POL-R-21")
}

test_pol_r_21_block_provider_not_shown if blocked(run(json.remove(conn, ["consent/shown/provider"])), "POL-R-21")

test_pol_r_21_block_false_display_fields if {
	blocked(run(json.patch(conn, [{"op": "replace", "path": "/consent/shown", "value": {"provider": false, "address": false, "functions": false}}])), "POL-R-21")
}

test_pol_r_21_block_no_consent if blocked(run(json.remove(conn, ["consent"])), "POL-R-21")

# --- POL-R-22 ---

test_pol_r_22_pass_consent_reused_in_scope if not "POL-R-22" in run(conn).policy_ids

test_pol_r_22_block_other_user if blocked(run(object.union(conn, {"user": "lee"})), "POL-R-22")

test_pol_r_22_block_new_function if blocked(run(object.union(conn, {"requested_functions": ["search", "delete"]})), "POL-R-22")

test_pol_r_22_block_expired_consent if {
	blocked(run(json.patch(conn, [{"op": "replace", "path": "/consent/not_after_ns", "value": now}])), "POL-R-22")
}

# --- POL-O-11 ---

test_pol_o_11_pass_registered_address if not "POL-O-11" in run(conn).policy_ids

test_pol_o_11_block_moved_address if blocked(run(object.union(conn, {"address": "https://srv-new.corp/mcp"})), "POL-O-11")

test_pol_o_11_block_exception_does_not_move_address if {
	d := run_with(object.union(conn, {"address": "https://srv-new.corp/mcp"}), {"exceptions": [exception("POL-O-11", "srv", "https://srv-new.corp/mcp", "security_admin")]})
	blocked(d, "POL-O-11")
}

test_pol_o_11_pass_after_registry_update if {
	reg := json.patch(registry, [{"op": "replace", "path": "/srv/address", "value": "https://srv-new.corp/mcp"}])
	d := connect.decision with input as {"connection": object.union(conn, {"address": "https://srv-new.corp/mcp"}), "facts": {"now_ns": now, "trusted": true}}
		with data.pol as {"servers": reg, "exceptions": []}
	not "POL-O-11" in d.policy_ids
}

# --- POL-R-14 (연결 단계) ---

test_pol_r_14_pass_connect_without_credential if not "POL-R-14" in run(conn).policy_ids

test_pol_r_14_pass_oauth_with_bound_credential if not "POL-R-14" in run(oauth).policy_ids

test_pol_r_14_block_credential_of_other_server if {
	blocked(run(object.union(oauth, {"credential": {"used": true, "bound_server": "github"}})), "POL-R-14")
}

test_pol_r_14_block_credential_unknown if blocked(run(json.remove(conn, ["credential"])), "POL-R-14")

# --- POL-D-01 ---

test_pol_d_01_pass_active_server if not "POL-D-01" in run(conn).policy_ids

test_pol_d_01_block_decommissioned_server if {
	reg := json.patch(registry, [{"op": "replace", "path": "/srv/state", "value": "decommissioned"}])
	d := connect.decision with input as {"connection": oauth, "facts": {"now_ns": now, "trusted": true}} with data.pol as {"servers": reg, "exceptions": []}
	blocked(d, "POL-D-01")
}

# --- POL-D-09 ---

test_pol_d_09_pass_restored_matches_approval if run(restored).effect == "ALLOW"

test_pol_d_09_block_decommissioned_server_restored if {
	blocked(run_with(restored, {"servers": {"srv": object.union(registry.srv, {"state": "decommissioned"})}}), "POL-D-09")
}

test_pol_d_09_block_expired_approval_restored if {
	expired := object.union(registry.srv, {"approval": object.union(registry.srv.approval, {"not_after_ns": now - 1})})
	blocked(run_with(restored, {"servers": {"srv": expired}}), "POL-D-09")
}

test_pol_d_09_block_unregistered_server_restored if {
	blocked(run(object.union(restored, {"server_id": "gone"})), "POL-D-09")
}

test_pol_d_09_block_restored_address_differs if {
	blocked(run(json.patch(restored, [{"op": "replace", "path": "/restored/address", "value": "https://old.corp/mcp"}])), "POL-D-09")
}

test_pol_d_09_block_retired_tool_restored if {
	blocked(run(json.patch(restored, [{"op": "add", "path": "/restored/tools/-", "value": "export"}])), "POL-D-09")
}

test_pol_d_09_block_unknown_tool_restored if {
	blocked(run(json.patch(restored, [{"op": "add", "path": "/restored/tools/-", "value": "shell"}])), "POL-D-09")
}

test_pol_d_09_block_restored_access_wider if {
	blocked(run(json.patch(restored, [{"op": "add", "path": "/restored/access/-", "value": "delete:internal_doc"}])), "POL-D-09")
}

test_pol_d_09_block_restored_config_missing if blocked(run(json.remove(restored, ["restored"])), "POL-D-09")

test_pol_d_09_block_restored_tools_null if {
	blocked(run(json.patch(restored, [{"op": "replace", "path": "/restored/tools", "value": null}])), "POL-D-09")
}
