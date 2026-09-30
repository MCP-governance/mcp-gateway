package mcp.decision

# Add each future policy pack here. Every pack exports findings with
# {"policy_id": string, "effect": "DENY" | "APPROVAL" | "ALERT"}.
bundle_ready if {
    data.mcp.pac15.pack_version == input.facts.approval.baseline.policy_version
}

all_findings contains {"policy_id": "POLICY_BUNDLE", "effect": "DENY"} if {
    not bundle_ready
}
all_findings contains finding if {
    finding := data.mcp.pac15.findings[_]
}

denied_ids := sort([finding.policy_id |
    finding := all_findings[_]
    finding.effect == "DENY"
])

approval_ids := sort([finding.policy_id |
    finding := all_findings[_]
    finding.effect == "APPROVAL"
])

alert_ids := sort([finding.policy_id |
    finding := all_findings[_]
    finding.effect == "ALERT"
])

# One enforceable result: DENY > APPROVAL > ALERT > ALLOW.
decision := {"effect": "DENY", "policy_ids": denied_ids} if {
    count(denied_ids) > 0
}
decision := {"effect": "APPROVAL", "policy_ids": approval_ids} if {
    count(denied_ids) == 0
    count(approval_ids) > 0
}
decision := {"effect": "ALERT", "policy_ids": alert_ids} if {
    count(denied_ids) == 0
    count(approval_ids) == 0
    count(alert_ids) > 0
}
decision := {"effect": "ALLOW", "policy_ids": []} if {
    count(all_findings) == 0
}
