#!/usr/bin/env bash
set -euo pipefail

: "${PJ1_SSH:=pj1@192.168.85.129}"
: "${PJ2_SSH:=pj2@192.168.85.130}"
: "${GATEWAY_PORT:=8080}"
: "${MCP_PORT:=9001}"
: "${MCP_DEMO_UPSTREAM_TOKEN:=demo-upstream-only}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REMOTE_DIR="/tmp/mcp-demo"
PJ1_HOST="${PJ1_SSH#*@}"
PJ2_HOST="${PJ2_SSH#*@}"
SSH_OPTS=(-o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new)

command -v ssh >/dev/null || { echo "ssh is required" >&2; exit 1; }
command -v scp >/dev/null || { echo "scp is required" >&2; exit 1; }
command -v curl >/dev/null || { echo "curl is required" >&2; exit 1; }

echo "[1/6] prepare remote directories"
ssh "${SSH_OPTS[@]}" "$PJ1_SSH" "mkdir -p '$REMOTE_DIR'"
ssh "${SSH_OPTS[@]}" "$PJ2_SSH" "mkdir -p '$REMOTE_DIR'"

echo "[2/6] copy demo"
scp "${SSH_OPTS[@]}" "$ROOT_DIR/two_vm_demo.py" "$PJ1_SSH:$REMOTE_DIR/two_vm_demo.py"
scp "${SSH_OPTS[@]}" "$ROOT_DIR/two_vm_demo.py" "$PJ2_SSH:$REMOTE_DIR/two_vm_demo.py"

echo "[3/6] start mock MCP server on $PJ2_SSH:$MCP_PORT"
ssh "${SSH_OPTS[@]}" "$PJ2_SSH" "if [ -s '$REMOTE_DIR/server.pid' ]; then kill \$(cat '$REMOTE_DIR/server.pid') 2>/dev/null || true; fi; rm -f '$REMOTE_DIR/effects.jsonl'; nohup env MCP_DEMO_UPSTREAM_TOKEN='$MCP_DEMO_UPSTREAM_TOKEN' python3 '$REMOTE_DIR/two_vm_demo.py' server --port '$MCP_PORT' --effects '$REMOTE_DIR/effects.jsonl' </dev/null >'$REMOTE_DIR/server.log' 2>&1 & echo \$! > '$REMOTE_DIR/server.pid'"

echo "[4/6] start enforcing gateway on $PJ1_SSH:$GATEWAY_PORT"
ssh "${SSH_OPTS[@]}" "$PJ1_SSH" "if [ -s '$REMOTE_DIR/gateway.pid' ]; then kill \$(cat '$REMOTE_DIR/gateway.pid') 2>/dev/null || true; fi; rm -f '$REMOTE_DIR/gateway.jsonl'; nohup env MCP_DEMO_UPSTREAM_TOKEN='$MCP_DEMO_UPSTREAM_TOKEN' python3 '$REMOTE_DIR/two_vm_demo.py' gateway --port '$GATEWAY_PORT' --upstream 'http://$PJ2_HOST:$MCP_PORT/mcp' --audit '$REMOTE_DIR/gateway.jsonl' </dev/null >'$REMOTE_DIR/gateway.log' 2>&1 & echo \$! > '$REMOTE_DIR/gateway.pid'"

echo "[5/6] health check"
wait_health() {
  local url="$1"
  for _ in $(seq 1 20); do
    if curl --fail --silent --show-error --max-time 2 "$url"; then
      echo
      return 0
    fi
    sleep 0.2
  done
  echo "health check failed: $url" >&2
  return 1
}
wait_health "http://$PJ2_HOST:$MCP_PORT/health"
wait_health "http://$PJ1_HOST:$GATEWAY_PORT/health"

echo "[6/6] run allow/deny demo through the gateway"
ssh "${SSH_OPTS[@]}" "$PJ1_SSH" "python3 '$REMOTE_DIR/two_vm_demo.py' client --gateway 'http://127.0.0.1:$GATEWAY_PORT/mcp'"
echo "done: gateway=$PJ1_SSH:$GATEWAY_PORT upstream=$PJ2_SSH:$MCP_PORT"
