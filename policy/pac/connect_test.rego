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
	"consent": consent, "requested_functions": ["search"], "credential": {"used": false},
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

# --- POL-012 ---

test_pol_012_pass_registered_active if not "POL-012" in run(conn).policy_ids

test_pol_012_block_unregistered if blocked(run(object.union(conn, {"server_id": "ghost"})), "POL-012")

test_pol_012_block_identity_mismatch if blocked(run(object.union(conn, {"identity": "sha256:other"})), "POL-012")

test_pol_012_block_expired_approval if {
	d := connect.decision with input as {"connection": conn, "facts": {"now_ns": now + (2 * day), "trusted": true}} with data.pol as pol_data
	blocked(d, "POL-012")
}

test_pol_012_block_null_identities if {
	reg := json.patch(registry, [{"op": "replace", "path": "/srv/identity", "value": null}])
	d := connect.decision with input as {"connection": object.union(conn, {"identity": null}), "facts": {"now_ns": now, "trusted": true}}
		with data.pol as {"servers": reg, "exceptions": []}
	blocked(d, "POL-012")
}

test_pol_012_block_approval_not_by_security_admin if {
	reg := json.patch(registry, [{"op": "replace", "path": "/srv/approval/approved_by_role", "value": "data_owner"}])
	d := connect.decision with input as {"connection": conn, "facts": {"now_ns": now, "trusted": true}} with data.pol as {"servers": reg, "exceptions": []}
	blocked(d, "POL-012")
}

test_pol_012_block_no_registry_at_all if {
	d := connect.decision with input as {"connection": conn, "facts": {"now_ns": now, "trusted": true}} with data.pol as {}
	blocked(d, "POL-012")
}

# --- POL-013 ---

exc_conn := object.union(conn, {"approval": {"basis": "exception"}})

test_pol_013_pass_valid_exception if {
	not "POL-013" in run_with(exc_conn, {"exceptions": [exception("POL-013", "srv", "connect", "security_admin")]}).policy_ids
}

test_pol_013_block_expired_exception if {
	e := object.union(exception("POL-013", "srv", "connect", "security_admin"), {"not_after_ns": now})
	blocked(run_with(exc_conn, {"exceptions": [e]}), "POL-013")
}

test_pol_013_block_exception_for_other_scope if {
	blocked(run_with(exc_conn, {"exceptions": [exception("POL-013", "srv", "launch", "security_admin")]}), "POL-013")
}

test_pol_013_block_basis_missing if blocked(run(json.remove(conn, ["approval"])), "POL-013")

# --- POL-014 ---

test_pol_014_pass_complete_record if not "POL-014" in run_approve(approval).policy_ids

test_pol_014_block_missing_policy_version if blocked(run_approve(json.remove(approval, ["policy_version"])), "POL-014")

test_pol_014_block_exception_without_end_date if {
	blocked(run_approve(object.union(approval, {"method": "exception", "approver": "admin-1"})), "POL-014")
}

test_pol_014_pass_exception_with_approver_and_end if {
	not "POL-014" in run_approve(object.union(approval, {"method": "exception", "approver": "admin-1", "not_after_ns": now + day})).policy_ids
}

test_pol_014_block_record_failed if blocked(run_approve(object.union(approval, {"recorded": false})), "POL-014")

test_pol_014_block_approval_for_other_server if blocked(run_approve(object.union(approval, {"server_id": "other"})), "POL-014")

test_pol_014_block_exception_with_past_end_date if {
	blocked(run_approve(object.union(approval, {"method": "exception", "approver": "admin-1", "not_after_ns": now})), "POL-014")
}

test_pol_014_block_unknown_method if blocked(run_approve(object.union(approval, {"method": "tofu"})), "POL-014")

test_pol_014_block_no_approval_object if {
	d := connect.decision with input as {"connection": {"stage": "approve", "server_id": "srv"}, "facts": {"now_ns": now, "trusted": true}}
		with data.pol as pol_data
	blocked(d, "POL-014")
}

# --- POL-019 ---

test_pol_019_pass_approved_auth_server if not "POL-019" in run(oauth).policy_ids

test_pol_019_block_other_auth_server if {
	blocked(run(object.union(oauth, {"auth_server": {"address": "https://evil-idp.example", "id": "corp-idp"}})), "POL-019")
}

test_pol_019_block_missing_auth_server if blocked(run(json.remove(oauth, ["auth_server"])), "POL-019")

test_pol_019_block_null_auth_server if blocked(run(object.union(oauth, {"auth_server": null})), "POL-019")

test_pol_019_block_same_address_other_id if {
	blocked(run(object.union(oauth, {"auth_server": {"address": "https://idp.corp", "id": "other-idp"}})), "POL-019")
}

# --- POL-022 ---

test_pol_022_pass_approved_metadata_host if not "POL-022" in run(oauth).policy_ids

test_pol_022_block_unapproved_metadata_host if {
	blocked(run(json.patch(oauth, [{"op": "replace", "path": "/metadata/request_host", "value": "169.254.169.254"}])), "POL-022")
}

test_pol_022_block_metadata_missing if blocked(run(json.remove(oauth, ["metadata"])), "POL-022")

test_pol_022_block_unregistered_server if blocked(run(object.union(oauth, {"server_id": "ghost"})), "POL-022")

# --- POL-023 ---

test_pol_023_pass_public_final_address if not "POL-023" in run(oauth).policy_ids

test_pol_023_block_redirect_to_private_ip if {
	blocked(run(json.patch(oauth, [{"op": "replace", "path": "/metadata/resolved_ips", "value": ["10.0.0.5"]}])), "POL-023")
}

test_pol_023_block_redirect_to_other_host if {
	blocked(run(json.patch(oauth, [{"op": "replace", "path": "/metadata/final_host", "value": "evil.example"}])), "POL-023")
}

test_pol_023_block_no_resolution if {
	blocked(run(json.patch(oauth, [{"op": "replace", "path": "/metadata/resolved_ips", "value": []}])), "POL-023")
}

test_pol_023_block_malformed_ip if {
	blocked(run(json.patch(oauth, [{"op": "replace", "path": "/metadata/resolved_ips", "value": ["not-an-ip"]}])), "POL-023")
}

test_pol_023_block_ipv4_mapped_private if {
	blocked(run(json.patch(oauth, [{"op": "replace", "path": "/metadata/resolved_ips", "value": ["::ffff:10.0.0.5"]}])), "POL-023")
}

test_pol_023_block_documentation_range if {
	blocked(run(json.patch(oauth, [{"op": "replace", "path": "/metadata/resolved_ips", "value": ["203.0.113.10"]}])), "POL-023")
}

test_pol_023_block_ipv6_loopback if {
	blocked(run(json.patch(oauth, [{"op": "replace", "path": "/metadata/resolved_ips", "value": ["::1"]}])), "POL-023")
}

# --- POL-026 ---

test_pol_026_pass_scope_within_approval if not "POL-026" in run(oauth).policy_ids

test_pol_026_block_scope_expansion if blocked(run(object.union(oauth, {"requested_scopes": ["repo:read", "repo:admin"]})), "POL-026")

test_pol_026_block_scopes_missing if blocked(run(json.remove(oauth, ["requested_scopes"])), "POL-026")

# 범위 확대는 등록부의 승인 scope를 바꾼 뒤에만 — 예외 항목으로는 넓어지지 않는다.
test_pol_026_block_exception_does_not_extend_scope if {
	d := run_with(object.union(oauth, {"requested_scopes": ["repo:admin"]}), {"exceptions": [exception("POL-026", "srv", "repo:admin", "security_admin")]})
	blocked(d, "POL-026")
}

# --- POL-029 ---

test_pol_029_pass_remote_https if not "POL-029" in run(conn).policy_ids

test_pol_029_block_remote_plain_http if blocked(run(object.union(conn, {"transport": {"scheme": "http"}})), "POL-029")

test_pol_029_block_local_without_launch_config if {
	reg := json.remove(registry, ["srv/launch"])
	d := connect.decision with input as {"connection": launch, "facts": {"now_ns": now, "trusted": true}} with data.pol as {"servers": reg, "exceptions": []}
	blocked(d, "POL-029")
}

test_pol_029_block_empty_launch_registration if {
	reg := json.patch(registry, [{"op": "replace", "path": "/srv/launch", "value": {}}])
	d := connect.decision with input as {"connection": object.union(conn, {"kind": "local"}), "facts": {"now_ns": now, "trusted": true}}
		with data.pol as {"servers": reg, "exceptions": []}
	blocked(d, "POL-029")
}

test_pol_029_block_unknown_kind if blocked(run(json.remove(conn, ["kind"])), "POL-029")

# --- POL-031 ---

test_pol_031_pass_launch_matches if not "POL-031" in run(launch).policy_ids

test_pol_031_block_changed_args if {
	blocked(run(json.patch(launch, [{"op": "replace", "path": "/launch/args", "value": ["--stdio", "--allow-write"]}])), "POL-031")
}

test_pol_031_block_changed_binary_hash if {
	blocked(run(json.patch(launch, [{"op": "replace", "path": "/launch/sha256", "value": "def"}])), "POL-031")
}

test_pol_031_block_env_missing if blocked(run(json.remove(launch, ["launch/env"])), "POL-031")

test_pol_031_block_empty_hashes_on_both_sides if {
	reg := json.patch(registry, [{"op": "replace", "path": "/srv/launch/sha256", "value": ""}])
	c := json.patch(launch, [{"op": "replace", "path": "/launch/sha256", "value": ""}])
	d := connect.decision with input as {"connection": c, "facts": {"now_ns": now, "trusted": true}} with data.pol as {"servers": reg, "exceptions": []}
	blocked(d, "POL-031")
}

# --- POL-008 ---

test_pol_008_pass_permissions_within_approval if not "POL-008" in run(launch).policy_ids

test_pol_008_block_excess_permission_isolated_restricts if {
	d := run(json.patch(launch, [{"op": "replace", "path": "/launch/observed_permissions", "value": ["fs:read:/srv/data", "net:any"]}]))
	d.effect == "RESTRICT"
	"POL-008" in d.policy_ids
}

test_pol_008_block_excess_permission_without_isolation if {
	c := json.patch(launch, [
		{"op": "replace", "path": "/launch/observed_permissions", "value": ["net:any"]},
		{"op": "replace", "path": "/launch/isolation/verified", "value": false},
	])
	blocked(run(c), "POL-008")
}

test_pol_008_block_unknown_permissions_without_isolation if {
	c := json.patch(json.remove(launch, ["launch/observed_permissions"]), [{"op": "remove", "path": "/launch/isolation"}])
	blocked(run(c), "POL-008")
}

# --- POL-032 ---

test_pol_032_pass_consented if not "POL-032" in run(conn).policy_ids

test_pol_032_block_declined if blocked(run(json.patch(conn, [{"op": "replace", "path": "/consent/decision", "value": "decline"}])), "POL-032")

test_pol_032_block_consent_for_other_server if {
	blocked(run(json.patch(conn, [{"op": "replace", "path": "/consent/server_id", "value": "other"}])), "POL-032")
}

test_pol_032_block_provider_not_shown if blocked(run(json.remove(conn, ["consent/shown/provider"])), "POL-032")

test_pol_032_block_false_display_fields if {
	blocked(run(json.patch(conn, [{"op": "replace", "path": "/consent/shown", "value": {"provider": false, "address": false, "functions": false}}])), "POL-032")
}

test_pol_032_block_no_consent if blocked(run(json.remove(conn, ["consent"])), "POL-032")

# --- POL-033 ---

test_pol_033_pass_consent_reused_in_scope if not "POL-033" in run(conn).policy_ids

test_pol_033_block_other_user if blocked(run(object.union(conn, {"user": "lee"})), "POL-033")

test_pol_033_block_new_function if blocked(run(object.union(conn, {"requested_functions": ["search", "delete"]})), "POL-033")

test_pol_033_block_expired_consent if {
	blocked(run(json.patch(conn, [{"op": "replace", "path": "/consent/not_after_ns", "value": now}])), "POL-033")
}

# --- POL-073 ---

test_pol_073_pass_registered_address if not "POL-073" in run(conn).policy_ids

test_pol_073_block_moved_address if blocked(run(object.union(conn, {"address": "https://srv-new.corp/mcp"})), "POL-073")

test_pol_073_block_exception_does_not_move_address if {
	d := run_with(object.union(conn, {"address": "https://srv-new.corp/mcp"}), {"exceptions": [exception("POL-073", "srv", "https://srv-new.corp/mcp", "security_admin")]})
	blocked(d, "POL-073")
}

test_pol_073_pass_after_registry_update if {
	reg := json.patch(registry, [{"op": "replace", "path": "/srv/address", "value": "https://srv-new.corp/mcp"}])
	d := connect.decision with input as {"connection": object.union(conn, {"address": "https://srv-new.corp/mcp"}), "facts": {"now_ns": now, "trusted": true}}
		with data.pol as {"servers": reg, "exceptions": []}
	not "POL-073" in d.policy_ids
}

# --- POL-025 (연결 단계) ---

test_pol_025_pass_connect_without_credential if not "POL-025" in run(conn).policy_ids

test_pol_025_pass_oauth_with_bound_credential if not "POL-025" in run(oauth).policy_ids

test_pol_025_block_credential_of_other_server if {
	blocked(run(object.union(oauth, {"credential": {"used": true, "bound_server": "github"}})), "POL-025")
}

test_pol_025_block_credential_unknown if blocked(run(json.remove(conn, ["credential"])), "POL-025")

# --- POL-082 ---

test_pol_082_pass_active_server if not "POL-082" in run(conn).policy_ids

test_pol_082_block_decommissioned_server if {
	reg := json.patch(registry, [{"op": "replace", "path": "/srv/state", "value": "decommissioned"}])
	d := connect.decision with input as {"connection": oauth, "facts": {"now_ns": now, "trusted": true}} with data.pol as {"servers": reg, "exceptions": []}
	blocked(d, "POL-082")
}
