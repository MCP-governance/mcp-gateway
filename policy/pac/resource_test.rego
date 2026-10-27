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

test_pol_067_pass_approved_template if run(prompt_req, prompt_facts, {}).effect == "ALLOW"

test_pol_067_block_changed_template if blocked(run(prompt_req, object.union(prompt_facts, {"prompt_sha256": "p2"}), {}), "POL-067")

test_pol_067_block_unknown_template if blocked(run(object.union(prompt_req, {"prompt": "other"}), prompt_facts, {}), "POL-067")

test_pol_007_pass_no_blocked_instruction if not "POL-007" in run(prompt_req, prompt_facts, {}).policy_ids

test_pol_007_block_blocked_instruction if {
	blocked(run(prompt_req, object.union(prompt_facts, {"prompt_scan": {"blocked_types": ["exfiltrate"]}}), {}), "POL-007")
}

test_pol_007_block_scan_missing if blocked(run(prompt_req, json.remove(prompt_facts, ["prompt_scan"]), {}), "POL-007")

test_pol_007_block_user_without_permission if {
	blocked(run(prompt_req, json.patch(prompt_facts, [{"op": "replace", "path": "/acl/user_can", "value": false}]), {}), "POL-007")
}

test_pol_067_block_non_string_hashes if {
	d := resource.decision with input as {"request": prompt_req, "facts": object.union({"now_ns": now, "trusted": true}, object.union(prompt_facts, {"prompt_sha256": []}))}
		with data.pol as {"servers": {"srv": {"prompts": {"summarize": {"sha256": []}}}}, "exceptions": []}
	blocked(d, "POL-067")
}

read_req := {"stage": "resource_read", "user": "kim", "server_id": "srv"}

read_acl := {"user_can": true, "user": "kim", "resource_id": "file-1"}

test_pol_043_pass_permitted_resource if run(read_req, {"resource": {"resolved_id": "file-1"}, "acl": read_acl}, {}).effect == "ALLOW"

test_pol_043_block_no_permission if blocked(run(read_req, {"resource": {"resolved_id": "file-1"}, "acl": object.union(read_acl, {"user_can": false})}, {}), "POL-043")

test_pol_043_block_acl_for_other_user if blocked(run(read_req, {"resource": {"resolved_id": "file-1"}, "acl": object.union(read_acl, {"user": "lee"})}, {}), "POL-043")

test_pol_043_block_unresolved_id if blocked(run(read_req, {"acl": read_acl}, {}), "POL-043")

list_req := {"stage": "resource_list", "user": "kim", "server_id": "srv"}

test_pol_065_pass_permitted_list if run(list_req, {"permitted_resources": ["a", "b"], "deleted_resources": []}, {"resources": ["a"]}).effect == "ALLOW"

test_pol_065_block_deleted_resource if blocked(run(list_req, {"permitted_resources": ["a", "b"], "deleted_resources": ["b"]}, {"resources": ["a", "b"]}), "POL-065")

test_pol_065_block_deletion_list_unknown if blocked(run(list_req, {"permitted_resources": ["a", "b"]}, {"resources": ["a"]}), "POL-065")

test_pol_065_block_unpermitted_resource if blocked(run(list_req, {"permitted_resources": ["a"]}, {"resources": ["a", "c"]}), "POL-065")

update_req := {"stage": "resource_update", "user": "kim", "server_id": "srv"}

test_pol_066_pass_approved_source if run(update_req, {"change": {"source": "git:corp/handbook", "within_approved_scope": true}}, {}).effect == "ALLOW"

test_pol_066_block_unapproved_source if blocked(run(update_req, {"change": {"source": "web:unknown", "within_approved_scope": true}}, {}), "POL-066")

test_pol_066_block_out_of_scope_change if blocked(run(update_req, {"change": {"source": "git:corp/handbook", "within_approved_scope": false}}, {}), "POL-066")
