package probe_test

import rego.v1

import data.probe

test_allow_when_destination_approved if {
	probe.allow with input as {"destination": "approved.example", "high_risk": false}
}

test_deny_unapproved_destination if {
	probe.deny == {"PAC-12"} with input as {"destination": "evil.example", "high_risk": false}
}

test_deny_high_risk_without_binding if {
	probe.deny == {"PAC-13"} with input as {"destination": "approved.example", "high_risk": true}
}
