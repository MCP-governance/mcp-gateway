#!/usr/bin/env bash
set -euo pipefail

LAB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$LAB_DIR"

# This script deliberately tampers with the upstream catalog and stops OPA. Without
# a restore on exit, a failure in the middle leaves the demo blocking every call and
# the next `./console.sh` looks broken for reasons unrelated to the change under test.
restore() {
  status=$?
  echo "[cleanup] restore approved contract and policy engine"
  restart_mock normal >/dev/null 2>&1 || true
  docker compose start opa >/dev/null 2>&1 || true
  exit "$status"
}
trap restore EXIT

# `up --force-recreate` returns before Docker has always released the previous
# fixed container name. Stop/remove first so the next drift case cannot race its
# predecessor and turn a security regression into a Docker-name failure.
restart_mock() {
  local mode="$1"
  MCP_CATALOG_MODE="$mode" docker compose stop mock-http-mcp >/dev/null 2>&1 || true
  docker compose rm -f mock-http-mcp >/dev/null 2>&1 || true
  MCP_CATALOG_MODE="$mode" docker compose up -d --no-deps mock-http-mcp >/dev/null
}

python3 tests/regression.py unauthenticated

for mode in description-drift schema-drift shadow version-drift; do
  echo "[catalog] $mode"
  restart_mock "$mode"
  python3 tests/regression.py refresh DRIFT
  python3 tests/regression.py block MCP-CATALOG-001
done

echo "[catalog] restore approved contract"
restart_mock normal
python3 tests/regression.py refresh READY

echo "[availability] stop OPA and verify fail-closed"
docker compose stop opa >/dev/null
python3 tests/regression.py block P-CONTROL-FAIL-CLOSED
docker compose start opa >/dev/null
python3 tests/regression.py wait

if [[ -n "$(docker compose port mock-http-mcp 9000 2>/dev/null)" ]]; then
  echo "FAIL mock MCP is exposed to the host" >&2
  exit 1
fi
echo "PASS upstream MCP has no host port"
echo "PASS security regression"
