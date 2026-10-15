# Bootstrap root is replaced with a short-lived operator limited to this lab.
path "lab-kv/data/integration/*" {
  capabilities = ["create", "read", "update", "delete"]
}
path "lab-kv/metadata/integration/*" {
  capabilities = ["read", "list"]
}
path "auth/lab-approle/role/litellm-lab*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}
path "auth/token/revoke-accessor" {
  capabilities = ["update"]
}
path "auth/token/lookup-self" {
  capabilities = ["read"]
}
path "auth/token/renew-self" {
  capabilities = ["update"]
}
path "auth/token/revoke-self" {
  capabilities = ["update"]
}
