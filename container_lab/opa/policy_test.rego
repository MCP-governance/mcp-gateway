package mcp.authz_test

import data.mcp.authz.decision

base_input := {
  "principal": {"role": "customer"},
  "resource": {"data_class": "public"},
  "tool": {"action": "r"},
  "contract": {"valid": true, "schema_hash_match": true},
  "catalog": {
    "known_tools_only": true,
    "schema_hash_match": true,
    "description_hash_match": true,
    "metadata_safe": true,
  },
}

test_allows_approved_read if {
  output := decision with input as base_input
  output.decision == "ALLOW"
}

test_blocks_description_drift if {
  output := decision with input as object.union(base_input, {"catalog": object.union(base_input.catalog, {"description_hash_match": false})})
  output.policy_id == "MCP-TOOL-POISON-001"
}
