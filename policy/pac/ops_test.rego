# 운영 및 변경·폐기 시험. 이름 규칙: test_pol_<번호>_pass_* / test_pol_<번호>_block_*.
package mcp.pol.ops_test

import data.mcp.pol.ops
import rego.v1

now := 1793000000000000000

day := 86400000000000

hour := 3600000000000

server := {
	"id": "srv",
	"config_scan": {"status": "completed", "plaintext_secrets": [], "storage_approved": true},
	"observed_tools": [{"name": "search", "contract_sha256": "c1"}], "approved_tools": {"search": "c1"},
	"packages": [{"name": "mcp-sdk", "version": "2.2.0", "source": "pypi"}],
	"vuln_scan": {"status": "completed"}, "vulnerabilities": [], "scheduled_change_ns": now + (7 * day),
	"baseline_config_sha256": "base", "instances": [{"id": "i-1", "config_sha256": "base"}],
	"downstream": {"observed": ["api.vendor.com"], "approved": ["api.vendor.com"]},
	"observed_permissions": ["fs:read"], "approved_permissions": ["fs:read"],
	"revoke_confirmed": [], "in_use_permissions": ["fs:read"],
	"oauth_scopes": {"observed": ["repo:read"], "approved": ["repo:read"]},
	"tool_permissions": {"observed": ["read"], "approved": ["read"]},
	"incidents": [],
}

pol_data := {
	"package_allowlist": [{"name": "mcp-sdk", "source": "pypi", "versions": ["2.2.0"], "not_after_ns": now + day, "status": "approved", "approved_by": "admin-1", "approved_by_role": "security_admin"}],
	"blocked_versions": {"srv": ["1.0.0"]},
	"exceptions": [],
}

check(event, s) := v if {
	v := ops.violations with input as {"event": event, "servers": [s], "facts": {"now_ns": now, "trusted": true}} with data.pol as pol_data
}

decide(event, s) := d if {
	d := ops.decision with input as {"event": event, "servers": [s], "facts": {"now_ns": now, "trusted": true}} with data.pol as pol_data
}

hit(event, s, pol, action) if {
	some v in check(event, s)
	v.policy_id == pol
	v.action == action
}

clean(event, s, pol) if {
	not some_hit(event, s, pol)
}

some_hit(event, s, pol) if {
	some v in check(event, s)
	v.policy_id == pol
}

patched(patch) := json.patch(server, patch)

vuln(id, severity, age_ns) := {
	"id": id, "severity": severity, "exploited": false, "exposed": false, "affected_version": "2.2.0",
	"patched": false, "confirmed_ns": now - age_ns,
}

test_all_events_pass_allow if {
	every e in ["periodic", "update", "config_change", "package_change"] {
		decide(e, server).effect == "ALLOW"
	}
}

test_contract_block_unknown_event if {
	d := ops.decision with input as {"event": "reboot", "servers": [server], "facts": {"now_ns": now, "trusted": true}} with data.pol as pol_data
	"INPUT_CONTRACT" in d.policy_ids
}

# --- POL-024 ---

test_pol_024_pass_no_plaintext if clean("config_change", server, "POL-024")

test_pol_024_block_plaintext_secret if hit("config_change", patched([{"op": "replace", "path": "/config_scan/plaintext_secrets", "value": ["args:--token"]}]), "POL-024", "block_deploy")

test_pol_024_block_null_scan_result if hit("periodic", patched([{"op": "replace", "path": "/config_scan/plaintext_secrets", "value": null}]), "POL-024", "block_deploy")

test_pol_024_block_secret_outside_approved_store if hit("config_change", patched([{"op": "replace", "path": "/config_scan/storage_approved", "value": false}]), "POL-024", "block_deploy")

test_pol_024_block_scan_missing if hit("periodic", json.remove(server, ["config_scan"]), "POL-024", "block_deploy")

# --- POL-063 ---

test_pol_063_pass_unchanged_tools if clean("periodic", server, "POL-063")

test_pol_063_block_changed_hash if hit("update", patched([{"op": "replace", "path": "/observed_tools/0/contract_sha256", "value": "c9"}]), "POL-063", "block")

test_pol_063_block_new_tool if hit("periodic", patched([{"op": "add", "path": "/observed_tools/-", "value": {"name": "delete_all", "contract_sha256": "x"}}]), "POL-063", "block")

test_pol_063_block_approved_list_missing if hit("periodic", json.remove(server, ["approved_tools"]), "POL-063", "block")

test_pol_063_block_tool_without_name if hit("periodic", patched([{"op": "replace", "path": "/observed_tools", "value": [{"contract_sha256": "c1"}]}]), "POL-063", "block")

test_pol_063_block_tool_list_unobserved if hit("periodic", patched([{"op": "replace", "path": "/observed_tools", "value": null}]), "POL-063", "block")

# --- POL-068 ---

test_pol_068_pass_approved_packages if clean("package_change", server, "POL-068")

test_pol_068_block_unapproved_version if hit("package_change", patched([{"op": "replace", "path": "/packages/0/version", "value": "2.3.0"}]), "POL-068", "block")

test_pol_068_block_package_without_name if hit("update", patched([{"op": "replace", "path": "/packages", "value": [{"version": "1.0", "source": "pypi"}]}]), "POL-068", "block")

test_pol_068_block_package_list_missing if hit("update", json.remove(server, ["packages"]), "POL-068", "block")

# --- POL-069 ---

test_pol_069_pass_complete_scan if clean("periodic", patched([{"op": "replace", "path": "/vulnerabilities", "value": [vuln("CVE-1", "high", hour)]}]), "POL-069")

test_pol_069_block_scan_failed if hit("periodic", patched([{"op": "replace", "path": "/vuln_scan/status", "value": "error"}]), "POL-069", "mark_unverified")

test_pol_069_block_missing_exploit_flag if {
	hit("periodic", patched([{"op": "replace", "path": "/vulnerabilities", "value": [json.remove(vuln("CVE-1", "high", hour), ["exploited"])]}]), "POL-069", "mark_unverified")
}

test_pol_069_block_inventory_null if hit("periodic", patched([{"op": "replace", "path": "/vulnerabilities", "value": null}]), "POL-069", "mark_unverified")

test_pol_069_block_unknown_severity if {
	hit("periodic", patched([{"op": "replace", "path": "/vulnerabilities", "value": [vuln("CVE-1", "UNKNOWN", hour)]}]), "POL-069", "mark_unverified")
}

test_pol_069_block_missing_confirmation_time if {
	hit("periodic", patched([{"op": "replace", "path": "/vulnerabilities", "value": [json.remove(vuln("CVE-1", "high", hour), ["confirmed_ns"])]}]), "POL-069", "mark_unverified")
}

# --- POL-070 ---

with_vuln(v) := patched([{"op": "replace", "path": "/vulnerabilities", "value": [v]}])

test_pol_070_pass_high_within_14_days if clean("periodic", with_vuln(vuln("CVE-2", "high", 3 * day)), "POL-070")

test_pol_070_block_exploited_exposed_critical_after_48h if {
	hit("periodic", with_vuln(object.union(vuln("CVE-1", "critical", 49 * hour), {"exploited": true, "exposed": true})), "POL-070", "block")
}

test_pol_070_pass_exploited_critical_within_48h if {
	clean("periodic", with_vuln(object.union(vuln("CVE-1", "critical", 47 * hour), {"exploited": true, "exposed": true})), "POL-070")
}

test_pol_070_block_exploited_only_critical_after_48h if {
	hit("periodic", with_vuln(object.union(vuln("CVE-1", "critical", 49 * hour), {"exploited": true})), "POL-070", "block")
}

test_pol_070_block_exposed_only_critical_after_48h if {
	hit("periodic", with_vuln(object.union(vuln("CVE-1", "critical", 48 * hour), {"exposed": true})), "POL-070", "block")
}

test_pol_070_pass_other_critical_within_14_days if clean("periodic", with_vuln(vuln("CVE-3", "critical", 13 * day)), "POL-070")

test_pol_070_block_due_moment_included if hit("periodic", with_vuln(vuln("CVE-3", "critical", 14 * day)), "POL-070", "block")

test_pol_070_pass_high_within_30_days if clean("periodic", with_vuln(vuln("CVE-3", "high", 29 * day)), "POL-070")

test_pol_070_block_high_after_30_days if hit("periodic", with_vuln(vuln("CVE-3", "high", 30 * day)), "POL-070", "block")

test_pol_070_pass_medium_within_90_days if clean("periodic", with_vuln(vuln("CVE-4", "medium", 89 * day)), "POL-070")

test_pol_070_block_medium_after_90_days if hit("periodic", with_vuln(vuln("CVE-4", "medium", 90 * day)), "POL-070", "block")

test_pol_070_block_low_with_text_change_date if {
	s := object.union(with_vuln(vuln("CVE-6", "low", day)), {"scheduled_change_ns": "tomorrow"})
	hit("periodic", s, "POL-070", "block")
}

test_pol_070_pass_deadline_extended_by_security_admin if {
	e := {"policy_id": "POL-070", "target": "srv", "scope": ["CVE-9"], "not_after_ns": now + day, "status": "approved", "approved_by": "admin-1", "approved_by_role": "security_admin"}
	v := ops.violations with input as {"event": "periodic", "servers": [with_vuln(vuln("CVE-9", "high", 40 * day))], "facts": {"now_ns": now, "trusted": true}}
		with data.pol as object.union(pol_data, {"exceptions": [e]})
	not some_policy(v, "POL-070")
}

some_policy(v, pol) if {
	some x in v
	x.policy_id == pol
}

test_pol_070_pass_verified_compensating_control if {
	clean("periodic", with_vuln(object.union(vuln("CVE-5", "high", 20 * day), {"compensating_control": {"verified": true}})), "POL-070")
}

test_pol_070_pass_low_before_scheduled_change if clean("periodic", with_vuln(vuln("CVE-6", "low", 100 * day)), "POL-070")

test_pol_070_block_low_after_scheduled_change if {
	s := object.union(with_vuln(vuln("CVE-6", "low", 100 * day)), {"scheduled_change_ns": now - day})
	hit("periodic", s, "POL-070", "block")
}

test_pol_070_block_unknown_severity if hit("periodic", with_vuln(vuln("CVE-7", "unrated", hour)), "POL-070", "block")

test_pol_070_block_confirmation_time_unknown if hit("periodic", with_vuln(json.remove(vuln("CVE-8", "high", hour), ["confirmed_ns"])), "POL-070", "block")

# --- POL-071 ---

test_pol_071_pass_matching_instances if clean("config_change", server, "POL-071")

test_pol_071_block_drifted_instance if hit("config_change", patched([{"op": "add", "path": "/instances/-", "value": {"id": "i-2", "config_sha256": "drift"}}]), "POL-071", "stop_traffic")

test_pol_071_block_instances_null if hit("config_change", patched([{"op": "replace", "path": "/instances", "value": null}]), "POL-071", "stop_traffic")

test_pol_071_block_null_instance if hit("config_change", patched([{"op": "replace", "path": "/instances", "value": [null]}]), "POL-071", "stop_traffic")

test_pol_071_block_empty_hashes if {
	hit("config_change", patched([{"op": "replace", "path": "/baseline_config_sha256", "value": ""}, {"op": "replace", "path": "/instances/0/config_sha256", "value": ""}]), "POL-071", "stop_traffic")
}

test_pol_071_block_baseline_missing if hit("periodic", json.remove(server, ["baseline_config_sha256"]), "POL-071", "stop_traffic")

# --- POL-072 ---

restore(r) := object.union(server, {"restore": r})

good_restore := {"version": "2.1.0", "risky_settings": [], "approval": {"not_after_ns": now + day, "status": "approved", "approved_by": "admin-1", "approved_by_role": "security_admin"}}

test_pol_072_pass_approved_restore if clean("restore", restore(good_restore), "POL-072")

test_pol_072_block_blocked_version if hit("restore", restore(object.union(good_restore, {"version": "1.0.0"})), "POL-072", "abort_restore")

test_pol_072_block_risky_setting if hit("restore", restore(object.union(good_restore, {"risky_settings": ["auth=off"]})), "POL-072", "abort_restore")

test_pol_072_block_malformed_blocked_list if {
	v := ops.violations with input as {"event": "restore", "servers": [restore(good_restore)], "facts": {"now_ns": now, "trusted": true}}
		with data.pol as object.union(pol_data, {"blocked_versions": {"srv": "1.0.0"}})
	some x in v
	x.policy_id == "POL-072"
}

test_pol_072_block_no_approval if hit("restore", restore(json.remove(good_restore, ["approval"])), "POL-072", "abort_restore")

# --- POL-074 ---

test_pol_074_pass_approved_downstream if clean("periodic", server, "POL-074")

test_pol_074_block_new_downstream if hit("periodic", patched([{"op": "add", "path": "/downstream/observed/-", "value": "exfil.example"}]), "POL-074", "block_egress")

test_pol_074_block_downstream_unobserved if hit("periodic", json.remove(server, ["downstream"]), "POL-074", "block_egress")

# --- POL-075 ---

test_pol_075_pass_same_permissions_after_update if clean("update", server, "POL-075")

test_pol_075_block_expanded_permission if hit("update", patched([{"op": "add", "path": "/observed_permissions/-", "value": "net:any"}]), "POL-075", "block")

test_pol_075_block_permissions_unobserved if hit("update", json.remove(server, ["observed_permissions"]), "POL-075", "block")

# --- POL-076 ---

test_pol_076_pass_nothing_to_revoke if clean("periodic", server, "POL-076")

test_pol_076_block_confirmed_revoke_not_in_use if hit("periodic", patched([{"op": "replace", "path": "/revoke_confirmed", "value": ["fs:write"]}]), "POL-076", "revoke")

test_pol_076_block_confirmed_revoke_still_used if hit("periodic", patched([{"op": "replace", "path": "/revoke_confirmed", "value": ["fs:read"]}]), "POL-076", "revoke")

# --- POL-077 ---

test_pol_077_pass_no_expansion if clean("periodic", server, "POL-077")

test_pol_077_block_oauth_scope_expansion if hit("periodic", patched([{"op": "add", "path": "/oauth_scopes/observed/-", "value": "repo:admin"}]), "POL-077", "block")

test_pol_077_block_oauth_observation_null if hit("periodic", patched([{"op": "replace", "path": "/oauth_scopes/observed", "value": null}]), "POL-077", "block")

test_pol_077_block_tool_permission_expansion if hit("update", patched([{"op": "add", "path": "/tool_permissions/observed/-", "value": "delete"}]), "POL-077", "block")

# --- POL-081 ---

test_pol_081_pass_unconfirmed_incident if {
	clean("incident", patched([{"op": "replace", "path": "/incidents", "value": [{"severity": "critical", "confirmed": false}]}]), "POL-081")
}

test_pol_081_block_confirmed_critical if {
	hit("incident", patched([{"op": "replace", "path": "/incidents", "value": [{"severity": "critical", "confirmed": true, "tool": "search"}]}]), "POL-081", "stop")
}

test_pol_081_pass_below_stop_threshold if {
	clean("incident", patched([{"op": "replace", "path": "/incidents", "value": [{"severity": "medium", "confirmed": true}]}]), "POL-081")
}

test_pol_081_block_custom_threshold if {
	s := patched([{"op": "replace", "path": "/incidents", "value": [{"severity": "high", "confirmed": true}]}])
	v := ops.violations with input as {"event": "incident", "servers": [s], "facts": {"now_ns": now, "trusted": true}}
		with data.pol as object.union(pol_data, {"stop_severities": ["critical", "high"]})
	some x in v
	x.policy_id == "POL-081"
}

# --- POL-088 ---

termination(t) := object.union(server, {"provider_termination": t})

test_pol_088_pass_evidenced_termination if {
	clean("provider_termination", termination({"requested_complete": true, "evidence_verified": true, "new_transfer_blocked": true}), "POL-088")
}

test_pol_088_block_complete_without_evidence if {
	hit("provider_termination", termination({"requested_complete": true, "evidence_verified": false, "new_transfer_blocked": true}), "POL-088", "keep_incomplete")
}

test_pol_088_block_transfers_still_open if {
	hit("provider_termination", termination({"requested_complete": false, "new_transfer_blocked": false}), "POL-088", "block_transfer")
}

test_pol_088_block_termination_facts_missing if hit("provider_termination", server, "POL-088", "block_transfer")
