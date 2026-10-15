ui = false
api_addr = "https://openbao:8200"
log_level = "info"
disable_mlock = true

# OpenBao2.7 removed the file backend. PebbleDB persists this single lab node.
storage "pebbledb" {
  path = "/openbao/data/pebbledb"
}

listener "tcp" {
  address = "0.0.0.0:8200"
  tls_disable = false
  tls_cert_file = "/openbao/tls/server.pem"
  tls_key_file = "/openbao/tls/server.key"
  tls_min_version = "tls13"
  tls_max_version = "tls13"
  tls_acme_ca_directory = ""
}

telemetry {
  disable_hostname = true
}
