package probe_id

import rego.v1

# METADATA
# id: ID-PROBE-01
# labels:
#   policy_id: POL-44
#   runtime_pac: PAC-14
revoked if input.revoked
