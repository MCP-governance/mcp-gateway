#!/bin/bash
# Runs ON the solution appliance, started by termination_dispatch_lab.sh. Builds and removes an
# isolated lab beside the product stack without touching it: its own network, PostgreSQL, OPA,
# Presidio, a disposable Gitea and the Gitea MCP server (the project's own image) bound to it. Everything is named wbs-c-* and removed by `down`.
#
#   termination_dispatch_remote.sh up | run <test.py> [env...] | reset | down
# `reset` gives the provider a fresh token (a termination check revokes it) and restarts the MCP server with it.
set -uo pipefail
P=wbs-c
LAB=/tmp/$P-lab
SRC=/tmp/$P-src
GATEWAY_IMAGE=mcpgw-55e075465e-gateway:latest
NET=$P-net

env_file() { printf '%s' "$LAB/env"; }
load() { set -a; . "$(env_file)"; set +a; }

down() {
  docker rm -f $P-pg $P-opa $P-presidio-analyzer $P-presidio-anonymizer $P-gitea $P-mcp-gitea >/dev/null 2>&1
  docker network rm $NET >/dev/null 2>&1
  rm -rf "$LAB"
  # The self-removal timer of an earlier `up`, with its sleep.
  for pid in $(pgrep -f "sleep 10800; bash $SRC/tests/termination_dispatch_remote.sh"); do pkill -P "$pid"; kill "$pid"; done 2>/dev/null
  return 0
}

wait_for() { # name, seconds, command...
  local name=$1 limit=$2; shift 2
  for _ in $(seq 1 "$limit"); do "$@" >/dev/null 2>&1 && return 0; sleep 1; done
  echo "not ready: $name" >&2; return 1
}

mcp_gitea() {
  load
  docker rm -f $P-mcp-gitea >/dev/null 2>&1
  # The Gitea project's own MCP server image, the one the product stack pins (gitea-mcp-server:1.7.0).
  docker run -d --name $P-mcp-gitea --network $NET --network-alias mcp-gitea \
    -e GITEA_ACCESS_TOKEN="$(cat $LAB/secrets/gitea-mcp.token)" \
    docker.gitea.com/gitea-mcp-server:1.7.0 /app/gitea-mcp -t http -p 8000 -H http://corp-git:3000 >/dev/null || return 1
}

# Org, repositories and the provider's token (written to the file the MCP server and the probe read).
provision() {
  load
  docker run --rm --network $NET -e GITEA_ADMIN_URL=http://corp-git:3000 -e GITEA_ADMIN_USER=corpadmin \
    -e GITEA_ADMIN_PASSWORD="$GITEA_ADMIN_PASSWORD" -v $LAB/secrets:/secrets -v $SRC/tests:/tests:ro \
    $GATEWAY_IMAGE python /tests/termination_dispatch_provision.py
}

up() {
  down
  mkdir -p "$LAB/secrets" && chmod 777 "$LAB/secrets"
  PG_PASS=$(openssl rand -hex 12); GITEA_ADMIN_PASSWORD=$(openssl rand -hex 12)
  cat > "$(env_file)" <<E
PG_PASS=$PG_PASS
GITEA_ADMIN_PASSWORD=$GITEA_ADMIN_PASSWORD
E
  chmod 600 "$(env_file)"
  # A lab nobody removes is the failure to avoid: it removes itself.
  setsid nohup bash -c "sleep 10800; bash $SRC/tests/termination_dispatch_remote.sh down" >/dev/null 2>&1 </dev/null &
  docker network create $NET >/dev/null || return 1

  docker run -d --name $P-pg --network $NET -e POSTGRES_USER=mcp -e POSTGRES_DB=postgres \
    -e POSTGRES_PASSWORD="$PG_PASS" postgres:18-alpine >/dev/null || return 1
  docker run -d --name $P-opa --network $NET -v $SRC/opa:/policy:ro \
    openpolicyagent/opa:1.20.2-static run --server --addr=0.0.0.0:8181 /policy >/dev/null || return 1
  docker run -d --name $P-presidio-analyzer --network $NET --network-alias presidio-analyzer \
    mcpgw/presidio-analyzer-sm:2.2.364 >/dev/null || return 1
  docker run -d --name $P-presidio-anonymizer --network $NET --network-alias presidio-anonymizer \
    ghcr.io/data-privacy-stack/presidio-anonymizer:2.2.364 >/dev/null || return 1
  docker run -d --name $P-gitea --network $NET --network-alias corp-git \
    -e GITEA__security__INSTALL_LOCK=true -e GITEA__database__DB_TYPE=sqlite3 \
    -e GITEA__server__ROOT_URL=http://corp-git:3000/ -e GITEA__service__DISABLE_REGISTRATION=true \
    gitea/gitea:1.27.3-rootless >/dev/null || return 1

  wait_for pg 60 docker exec $P-pg pg_isready -U mcp || return 1
  wait_for gitea 90 docker exec $P-gitea wget -q -O- http://localhost:3000/api/healthz || return 1
  docker exec $P-gitea gitea admin user create --admin --username corpadmin --password "$GITEA_ADMIN_PASSWORD" \
    --email corpadmin@bob.local --must-change-password=false >/dev/null || return 1
  docker exec $P-gitea gitea admin user create --username mcp-bot --random-password \
    --email mcp-bot@bob.local --must-change-password=false >/dev/null || return 1
  provision || return 1
  mcp_gitea || return 1
  wait_for presidio 120 docker exec $P-presidio-analyzer python -c "import urllib.request; urllib.request.urlopen('http://localhost:3000/health', timeout=2)" || return 1
  wait_for presidio-anonymizer 60 docker exec $P-presidio-anonymizer python -c "import urllib.request; urllib.request.urlopen('http://localhost:3000/health', timeout=2)" || return 1
  wait_for mcp-gitea 60 docker run --rm --network $NET $GATEWAY_IMAGE python -c \
    "import httpx,sys; r=httpx.post('http://mcp-gitea:8000/mcp', json={}, headers={'accept':'application/json, text/event-stream'}, timeout=3); sys.exit(0 if r.status_code < 500 else 1)" || return 1
  echo "lab up"
}

run() {
  load
  local test=$1; shift
  local db=t_$(echo "$test" | tr -c 'a-z0-9\n' '_' | cut -c1-40)_$$
  docker exec $P-pg psql -U mcp -d postgres -qc "CREATE DATABASE $db" || return 1
  docker cp $SRC/db/init.sql $P-pg:/tmp/init.sql && docker exec $P-pg psql -U mcp -d $db -q -f /tmp/init.sql >/dev/null || return 1
  # The PostgreSQL, OPA, Presidio, Gitea and MCP legs are real; the code under test is this tree, mounted read-only.
  docker run --rm --network $NET --tmpfs /registry-runtime:uid=10001,gid=10001 --tmpfs /reports:uid=10001,gid=10001 \
    -v $SRC/gateway/app:/app/app:ro -v $SRC/tests:/tests:ro -v $SRC/registry:/registry:ro -v $SRC/opa:/policy:ro \
    -v $LAB/secrets:/secrets:ro -v $SRC/supply_chain:/supply_chain:ro -v $SRC/endpoint-agent:/endpoint-agent:ro \
    -e AGENT_DIR=/endpoint-agent \
    -e DATABASE_URL=postgresql://mcp:$PG_PASS@$P-pg:5432/$db -e DB_POOL_MAX=24 -e OTEL_SDK_DISABLED=true \
    -e OPA_URL=http://$P-opa:8181/v1/data/mcp/authz/decision -e POLICY_LEDGER_URL=http://$P-opa:8181/v1/data/policy_ledger -e POLICY_PATH=/policy/policy.rego \
    -e REGISTRY_DIR=/registry -e REGISTRY_RUNTIME_DIR=/registry-runtime -e REPORT_DIR=/reports \
    -e GITEA_ADMIN_URL=http://corp-git:3000 -e GITEA_ADMIN_USER=corpadmin -e GITEA_ADMIN_PASSWORD="$GITEA_ADMIN_PASSWORD" \
    -e GITEA_PROBE_TOKEN_FILE=/secrets/gitea-mcp.token \
    -e PRESIDIO_ANALYZER_URL=http://presidio-analyzer:3000 -e PRESIDIO_ANONYMIZER_URL=http://presidio-anonymizer:3000 \
    -e IDP_ISSUER=http://gateway.lab:8000 -e ENDPOINT_GATEWAY_IPS=10.0.0.5 -e PYTHONUNBUFFERED=1 -e PYTHONPATH=/app "$@" \
    -w /app $GATEWAY_IMAGE python /tests/"$test"
  local status=$?
  docker exec $P-pg psql -U mcp -d postgres -qc "DROP DATABASE IF EXISTS $db WITH (FORCE)" >/dev/null 2>&1
  return $status
}

case "${1:-}" in
  up) up || { echo "lab not ready (left running for inspection; it removes itself after 3 hours)" >&2; exit 1; } ;;
  run) shift; run "$@" ;;
  mcp) mcp_gitea ;;
  reset) provision && mcp_gitea ;;
  down) down ;;
  *) echo "usage: $0 up | run <test.py> [docker env args] | down" >&2; exit 2 ;;
esac
