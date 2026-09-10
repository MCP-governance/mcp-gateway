#!/usr/bin/env bash
set -euo pipefail

: "${PJ1_SSH:=pj1@192.168.85.129}"
: "${LIBRARY_PORT:=8090}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REMOTE_DIR="/tmp/mcp-library-lab"
PJ1_HOST="${PJ1_SSH#*@}"
SSH_OPTS=(-o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new)

echo "[1/5] copy library lab to Gateway VM"
ssh "${SSH_OPTS[@]}" "$PJ1_SSH" "mkdir -p '$REMOTE_DIR'"
scp "${SSH_OPTS[@]}" "$ROOT_DIR"/*.py "$ROOT_DIR"/*.txt "$ROOT_DIR"/*.conf "$ROOT_DIR"/*.csv "$PJ1_SSH:$REMOTE_DIR/"

echo "[2/5] create isolated virtual environments"
ssh "${SSH_OPTS[@]}" "$PJ1_SSH" "python3 -m venv '$REMOTE_DIR/gateway-venv'; python3 -m venv '$REMOTE_DIR/public-mcp-venv'"

echo "[3/5] install pinned library sets"
ssh "${SSH_OPTS[@]}" "$PJ1_SSH" "'$REMOTE_DIR/gateway-venv/bin/pip' install --disable-pip-version-check -r '$REMOTE_DIR/requirements-gateway.txt'; '$REMOTE_DIR/public-mcp-venv/bin/pip' install --disable-pip-version-check -r '$REMOTE_DIR/requirements-public-time.txt'"

echo "[4/5] start FastAPI Gateway on $PJ1_SSH:$LIBRARY_PORT"
ssh "${SSH_OPTS[@]}" "$PJ1_SSH" "if [ -s '$REMOTE_DIR/gateway.pid' ]; then kill \$(cat '$REMOTE_DIR/gateway.pid') 2>/dev/null || true; fi; nohup env PUBLIC_MCP_PYTHON='$REMOTE_DIR/public-mcp-venv/bin/python' '$REMOTE_DIR/gateway-venv/bin/uvicorn' library_gateway:app --host 0.0.0.0 --port '$LIBRARY_PORT' --app-dir '$REMOTE_DIR' </dev/null >'$REMOTE_DIR/gateway.log' 2>&1 & echo \$! > '$REMOTE_DIR/gateway.pid'"

echo "[5/5] health check"
for _ in $(seq 1 25); do
  if curl --fail --silent --show-error --max-time 2 "http://$PJ1_HOST:$LIBRARY_PORT/health"; then echo; exit 0; fi
  sleep 0.2
done
echo "library Gateway health check failed" >&2
exit 1
