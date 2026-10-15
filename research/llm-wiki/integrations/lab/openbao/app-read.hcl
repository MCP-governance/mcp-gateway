# The workload can read only the explicit model-gateway and smoke-test secrets.
path "lab-kv/data/integration/litellm" {
  capabilities = ["read"]
}
path "lab-kv/data/integration/smoke" {
  capabilities = ["read"]
}

# Renewal is bounded by the AppRole's explicit maximum TTL.
path "auth/token/lookup-self" {
  capabilities = ["read"]
}
path "auth/token/renew-self" {
  capabilities = ["update"]
}
path "auth/token/revoke-self" {
  capabilities = ["update"]
}
