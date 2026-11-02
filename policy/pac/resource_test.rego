# Resource·Prompt 시험(중개 도입 시 사용). 이름 규칙: test_pol_<번호>_pass_* / test_pol_<번호>_block_*.
package mcp.pol.resource_test

import data.mcp.pol.resource
import rego.v1

now := 1793000000000000000

pol_data := {"servers": {"srv": {"prompts": {"summarize": {"sha256": "p1"}}, "resource_sources": ["git:corp/handbook"]}}, "exceptions": []}

run(req, facts, resp) := d if {
	d := resource.decision with input as {"request": req, "facts": object.union({"now_ns": now, "trusted": true}, facts), "response": resp}
		with data.pol as pol_data
}

blocked(d, pol) if {
	d.effect == "DENY"
	pol in d.policy_ids
}

prompt_req := {"stage": "prompt_use", "user": "kim", "server_id": "srv", "prompt": "summarize"}

prompt_facts := {"prompt_sha256": "p1", "prompt_scan": {"blocked_types": []}, "acl": {"user_can": true, "user": "kim", "prompt": "summarize"}}

test_pol_o_05_pass_approved_template if run(prompt_req, prompt_facts, {}).effect == "ALLOW"

test_pol_o_05_block_changed_template if blocked(run(prompt_req, object.union(prompt_facts, {"prompt_sha256": "p2"}), {}), "POL-O-05")

test_pol_o_05_block_unknown_template if blocked(run(object.union(prompt_req, {"prompt": "other"}), prompt_facts, {}), "POL-O-05")

test_pol_i_07_pass_no_blocked_instruction if not "POL-I-07" in run(prompt_req, prompt_facts, {}).policy_ids

test_pol_i_07_block_blocked_instruction if {
	blocked(run(prompt_req, object.union(prompt_facts, {"prompt_scan": {"blocked_types": ["exfiltrate"]}}), {}), "POL-I-07")
}

test_pol_i_07_block_scan_missing if blocked(run(prompt_req, json.remove(prompt_facts, ["prompt_scan"]), {}), "POL-I-07")

test_pol_i_07_block_user_without_permission if {
	blocked(run(prompt_req, json.patch(prompt_facts, [{"op": "replace", "path": "/acl/user_can", "value": false}]), {}), "POL-I-07")
}

test_pol_o_05_block_non_string_hashes if {
	d := resource.decision with input as {"request": prompt_req, "facts": object.union({"now_ns": now, "trusted": true}, object.union(prompt_facts, {"prompt_sha256": []}))}
		with data.pol as {"servers": {"srv": {"prompts": {"summarize": {"sha256": []}}}}, "exceptions": []}
	blocked(d, "POL-O-05")
}

read_req := {"stage": "resource_read", "user": "kim", "server_id": "srv"}

read_acl := {"user_can": true, "user": "kim", "resource_id": "file-1"}

test_pol_e_10_pass_permitted_resource if run(read_req, {"resource": {"resolved_id": "file-1"}, "acl": read_acl}, {}).effect == "ALLOW"

test_pol_e_10_block_no_permission if blocked(run(read_req, {"resource": {"resolved_id": "file-1"}, "acl": object.union(read_acl, {"user_can": false})}, {}), "POL-E-10")

test_pol_e_10_block_acl_for_other_user if blocked(run(read_req, {"resource": {"resolved_id": "file-1"}, "acl": object.union(read_acl, {"user": "lee"})}, {}), "POL-E-10")

test_pol_e_10_block_unresolved_id if blocked(run(read_req, {"acl": read_acl}, {}), "POL-E-10")

list_req := {"stage": "resource_list", "user": "kim", "server_id": "srv"}

test_pol_o_03_pass_permitted_list if run(list_req, {"permitted_resources": ["a", "b"], "deleted_resources": []}, {"resources": ["a"]}).effect == "ALLOW"

test_pol_o_03_block_deleted_resource if blocked(run(list_req, {"permitted_resources": ["a", "b"], "deleted_resources": ["b"]}, {"resources": ["a", "b"]}), "POL-O-03")

test_pol_o_03_block_deletion_list_unknown if blocked(run(list_req, {"permitted_resources": ["a", "b"]}, {"resources": ["a"]}), "POL-O-03")

test_pol_o_03_block_unpermitted_resource if blocked(run(list_req, {"permitted_resources": ["a"]}, {"resources": ["a", "c"]}), "POL-O-03")

update_req := {"stage": "resource_update", "user": "kim", "server_id": "srv"}

test_pol_o_04_pass_approved_source if run(update_req, {"change": {"source": "git:corp/handbook", "within_approved_scope": true}}, {}).effect == "ALLOW"

test_pol_o_04_block_unapproved_source if blocked(run(update_req, {"change": {"source": "web:unknown", "within_approved_scope": true}}, {}), "POL-O-04")

test_pol_o_04_block_out_of_scope_change if blocked(run(update_req, {"change": {"source": "git:corp/handbook", "within_approved_scope": false}}, {}), "POL-O-04")
