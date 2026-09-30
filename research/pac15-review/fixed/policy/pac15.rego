package mcp.pac15

# The Gateway constructs input from verified sources. Request body fields alone
# must never be used as authoritative identity, approval, or connection facts.

pack_version := "pac15-v1"

base_valid if {
    input.facts.trusted == true
    is_number(input.facts.now_ns)
    is_string(input.request.id)
    # REVIEW B7: " " passed `!= ""` and became a reservation and approval key.
    trim_space(input.request.id) != ""
    is_string(input.request.server_id)
    is_string(input.request.feature_id)
    is_string(input.request.action)
    is_object(input.request.arguments)
    is_boolean(input.request.high_risk)
    input.facts.classification.verified == true
    input.request.high_risk == input.facts.classification.high_risk
    input.request.transfer.enabled == input.facts.classification.transfer_required
    input.request.on_behalf_of == input.facts.classification.on_behalf_of
    input.request.automated == input.facts.classification.automated
}

within(now, start, end) if {
    is_number(now)
    is_number(start)
    is_number(end)
    start <= now
    now < end
}

subset(items, allowed) if {
    is_array(items)
    is_array(allowed)
    every item in items { item in allowed }
}

target_set(items) := {item | item := items[_]}

binding_value(binding) := value if {
    value := object.get(input.request.arguments, binding.argument_path, null)
    value != null
}

binding_valid(binding) if {
    binding.target_type == "file"
    is_string(binding_value(binding))
    binding_value(binding) != ""
}
binding_valid(binding) if {
    binding.target_type == "command"
    is_string(binding_value(binding))
    binding_value(binding) != ""
}
binding_valid(binding) if {
    binding.target_type == "recipient"
    is_string(binding_value(binding))
    binding_value(binding) != ""
}
binding_valid(binding) if {
    binding.target_type == "scalar"
    binding_value(binding) in binding.allowed_values
}
# REVIEW B3: every binding had to be present, so a call that left out an optional
# argument (a mail without `mode`) was refused. A binding marked optional may be absent;
# when present it is checked like any other.
binding_valid(binding) if {
    binding.optional == true
    object.get(input.request.arguments, binding.argument_path, null) == null
}

# REVIEW B2: only the top-level key was checked against a binding, so `opts.cmd` rode
# along inside a bound `opts` object. Every scalar leaf must be a bound path; a leaf
# under an array has an index in its path and so is never bound (arrays need a
# feature-specific extractor, as PAC_DESIGN.md already says).
unbound_leaves contains path if {
    walk(input.request.arguments, [path, value])
    count(path) > 0
    not is_object(value)
    not is_array(value)
    not path_is_bound(path)
}

path_is_bound(path) if {
    some binding in input.facts.approval.parameter_bindings
    binding.argument_path == path
}

bound_targets(kind) := {value |
    some binding in input.facts.approval.parameter_bindings
    binding.target_type == kind
    value := binding_value(binding)
}

# PAC-01: approved status and validity window.
pac01 if {
    a := input.facts.approval
    a.status == "APPROVED"
    a.server_id == input.request.server_id
    within(input.facts.now_ns, a.valid_from_ns, a.valid_until_ns)
}
pac01 if {
    a := input.facts.approval
    a.status == "CONDITIONAL_APPROVED"
    a.server_id == input.request.server_id
    a.conditions_met == true
    within(input.facts.now_ns, a.valid_from_ns, a.valid_until_ns)
}

# PAC-02: observed configuration against the approved baseline.
pac02 if {
    b := input.facts.baseline
    a := input.facts.approval.baseline
    b.verified == true
    b.server_version == a.server_version
    b.feature_definition_hash == a.feature_definition_hash
    b.schema_hash == a.schema_hash
    b.policy_version == a.policy_version
}

# PAC-03: approved execution environment and production-equivalent test data.
pac03 if {
    e := input.facts.environment
    e.verified == true
    e.id == input.request.environment
    e.id in input.facts.approval.environments
    e.production_equivalent == false
}
pac03 if {
    e := input.facts.environment
    e.verified == true
    e.id == input.request.environment
    e.id in input.facts.approval.environments
    e.production_equivalent == true
    input.facts.approval.production_controls == true
}

# PAC-04: authenticated user, agent and application/Gateway session.
pac04 if {
    i := input.facts.identity
    a := input.facts.approval.subject
    i.verified == true
    i.user_id == a.user_id
    i.agent_id == a.agent_id
    i.session_id == a.session_id
    input.request.user_id == i.user_id
    input.request.agent_id == i.agent_id
    input.request.session_id == i.session_id
}

# PAC-05: delegated execution uses the intersection of user and agent rights.
pac05 if { input.request.on_behalf_of == false }
pac05 if {
    input.request.on_behalf_of == true
    d := input.facts.delegation
    d.verified == true
    d.user_id == input.facts.identity.user_id
    d.agent_id == input.facts.identity.agent_id
    within(input.facts.now_ns, d.valid_from_ns, d.valid_until_ns)
    input.request.action in d.user_actions
    input.request.action in d.agent_actions
    input.request.action in d.delegated_actions
}

# PAC-06: HTTP token checks or verified local connector identity.
# REVIEW B5: a local connection skipped revocation, validity and scope altogether, so
# `mode: "local"` was a way around every token check. A local connector has no issuer or
# audience, but it has an identity, a lifetime and a set of actions it was approved for.
pac06 if {
    t := input.facts.auth
    t.mode == "local"
    t.verified == true
    t.not_revoked == true
    t.connector_id in input.facts.approval.local_connectors
    within(input.facts.now_ns, t.valid_from_ns, t.valid_until_ns)
    input.request.action in t.scopes
}
pac06 if {
    t := input.facts.auth
    t.mode == "http"
    t.verified == true
    t.not_revoked == true
    t.issuer == input.facts.approval.auth_issuer
    t.audience == input.request.server_id
    within(input.facts.now_ns, t.valid_from_ns, t.valid_until_ns)
    input.request.action in t.scopes
}

# PAC-07: the actual connection target is verified and approved.
pac07 if {
    c := input.facts.connection
    c.verified == true
    c.final_target_verified == true
    c.server_id == input.request.server_id
    some approved in input.facts.approval.connections
    approved.server_id == c.server_id
    approved.endpoint_id == c.endpoint_id
    approved.final_target_id == c.final_target_id
}

# PAC-08: exact Server + feature type + feature ID and definition.
pac08 if {
    f := input.facts.catalog_feature
    f.verified == true
    f.server_id == input.request.server_id
    f.type == input.request.feature_type
    f.id == input.request.feature_id
    f.definition_hash == input.facts.approval.baseline.feature_definition_hash
    some approved in input.facts.approval.features
    approved.server_id == f.server_id
    approved.type == f.type
    approved.id == f.id
    approved.definition_hash == f.definition_hash
}

# PAC-09: normalized action in approved scope and subject rights.
pac09 if {
    input.facts.action.verified == true
    input.facts.action.normalized == input.request.action
    input.request.action in input.facts.approval.actions
    input.request.action in input.facts.identity.allowed_actions
}

# PAC-10: canonical argument targets, including paths, commands, recipients.
pac10 if {
    p := input.facts.parameters
    p.verified == true
    p.normalized == true
    p.schema_valid == true
    p.coverage_complete == true
    p.canonical_arguments == input.request.arguments
    p.derived_targets == input.request.targets
    every key, _ in input.request.arguments {
        key in input.facts.approval.allowed_argument_keys
        some binding in input.facts.approval.parameter_bindings
        binding.argument_path[0] == key
    }
    every binding in input.facts.approval.parameter_bindings {
        binding_valid(binding)
    }
    count(unbound_leaves) == 0
    target_set(input.request.targets.files) == bound_targets("file")
    target_set(input.request.targets.commands) == bound_targets("command")
    target_set(input.request.targets.recipients) == bound_targets("recipient")
    subset(input.request.targets.files, input.facts.approval.targets.files)
    subset(input.request.targets.commands, input.facts.approval.targets.commands)
    subset(input.request.targets.recipients, input.facts.approval.targets.recipients)
}

# PAC-11: classified data asset and grade are approved for this call.
pac11 if {
    d := input.facts.data
    d.verified == true
    d.asset_id == input.request.data.asset_id
    d.grade == input.request.data.grade
    some approved in input.facts.approval.data_scopes
    approved.asset_id == d.asset_id
    approved.grade == d.grade
}

# PAC-12: external transfer requires an approved final destination/grade pair.
pac12 if { input.request.transfer.enabled == false }
pac12 if {
    input.request.transfer.enabled == true
    x := input.facts.transfer
    x.verified == true
    x.final_destination_verified == true
    x.final_destination_id == input.request.transfer.destination_id
    x.data_grade == input.facts.data.grade
    some pair in input.facts.approval.transfer_pairs
    pair.destination_id == x.final_destination_id
    pair.grade == x.data_grade
}

approval_missing if { object.get(input.facts, "individual_approval", null) == null }

bound_destination_id := "" if {
    input.request.transfer.enabled == false
}
bound_destination_id := input.facts.transfer.final_destination_id if {
    input.request.transfer.enabled == true
}

approval_binding := {
    "request_id": input.request.id,
    "user_id": input.facts.identity.user_id,
    "agent_id": input.facts.identity.agent_id,
    "session_id": input.facts.identity.session_id,
    "server_id": input.request.server_id,
    "feature_type": input.request.feature_type,
    "feature_id": input.request.feature_id,
    "action": input.request.action,
    "arguments": input.request.arguments,
    "targets": input.request.targets,
    "data": input.request.data,
    "transfer": input.request.transfer,
    "endpoint_id": input.facts.connection.endpoint_id,
    "final_target_id": input.facts.connection.final_target_id,
    "final_destination_id": bound_destination_id,
    "baseline": input.facts.approval.baseline,
    # REVIEW B4: an approval given for a manual call in one environment could be spent
    # on an automated or delegated call, or in another environment - none of these were
    # in the digest. They change what the approver agreed to, so they are bound too.
    "environment": input.request.environment,
    "automated": input.request.automated,
    "on_behalf_of": input.request.on_behalf_of,
    "high_risk": input.request.high_risk,
}

request_digest := crypto.sha256(json.marshal(approval_binding))

# PAC-13: a high-risk approval is bound to this exact canonical request.
pac13_approved if {
    a := input.facts.individual_approval
    a.verified == true
    a.approver_authorized == true
    # REVIEW B6: nothing stopped the requester from approving their own high-risk call.
    is_string(a.approver_id)
    trim_space(a.approver_id) != ""
    a.approver_id != input.facts.identity.user_id
    a.single_use_reserved == true
    a.status == "APPROVED"
    a.request_id == input.request.id
    a.request_digest == request_digest
    a.server_id == input.request.server_id
    a.feature_id == input.request.feature_id
    a.action == input.request.action
    within(input.facts.now_ns, a.valid_from_ns, a.valid_until_ns)
}

approval_needed if {
    input.request.high_risk == true
    approval_missing
    input.facts.approval_workflow_available == true
}

# PAC-14: all revocation signals must be current and clear.
pac14 if {
    r := input.facts.revocation
    r.verified == true
    r.fresh == true
    r.user == false
    r.agent == false
    r.server == false
    r.feature == false
    r.approval == false
}

# PAC-15: the Gateway must first reserve state atomically.
# REVIEW B1: Rego orders values of different types (null < boolean < number < string),
# so `null <= 10`, `true <= 10` and `5 <= "1"` were all true and a missing or mistyped
# counter or limit passed. A count is a non-negative number and so is its limit.
within_limit(value, limit) if {
    is_number(value)
    is_number(limit)
    value >= 0
    value <= limit
}

execution_within_limits if {
    s := input.facts.execution
    l := input.facts.approval.limits
    s.atomic_reservation_verified == true
    s.reservation_request_id == input.request.id
    is_number(s.reservation_expires_ns)
    s.reservation_expires_ns > input.facts.now_ns
    s.duplicate_status == "clear"
    s.previous_mutation_status == "clear"
    within_limit(s.retry_count, l.max_retries)
    within_limit(s.active_concurrency, l.max_concurrency)
    within_limit(s.total_calls, l.max_calls)
    within_limit(s.chain_depth, l.max_chain_depth)
    within_limit(s.requested_timeout_ms, l.max_execution_ms)
}

pac15 if {
    execution_within_limits
    input.request.automated == false
}
pac15 if {
    execution_within_limits
    input.request.automated == true
    input.facts.approval.limits.allow_automated == true
}

deny contains "PAC-01" if { not pac01 }
deny contains "PAC-02" if { not pac02 }
deny contains "PAC-03" if { not pac03 }
deny contains "PAC-04" if { not pac04 }
deny contains "PAC-05" if { not pac05 }
deny contains "PAC-06" if { not pac06 }
deny contains "PAC-07" if { not pac07 }
deny contains "PAC-08" if { not pac08 }
deny contains "PAC-09" if { not pac09 }
deny contains "PAC-10" if { not pac10 }
deny contains "PAC-11" if { not pac11 }
deny contains "PAC-12" if { not pac12 }
deny contains "PAC-13" if {
    input.request.high_risk == true
    approval_missing
    object.get(input.facts, "approval_workflow_available", false) != true
}
deny contains "PAC-13" if {
    input.request.high_risk == true
    not approval_missing
    not pac13_approved
}
deny contains "PAC-13" if {
    input.request.high_risk != true
    input.request.high_risk != false
}
deny contains "PAC-14" if { not pac14 }
deny contains "PAC-15" if { not pac15 }

findings contains {"policy_id": "INPUT_CONTRACT", "effect": "DENY"} if {
    not base_valid
}
findings contains {"policy_id": id, "effect": "DENY"} if {
    base_valid
    id := deny[_]
}
findings contains {"policy_id": "PAC-13", "effect": "APPROVAL"} if {
    base_valid
    approval_needed
}
