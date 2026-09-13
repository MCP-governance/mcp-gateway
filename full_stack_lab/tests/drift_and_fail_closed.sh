#!/usr/bin/env bash
set -euo pipefail

LAB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$LAB_DIR"

for mode in description-drift schema-drift shadow version-drift; do
  echo "[catalog] $mode"
  MCP_CATALOG_MODE="$mode" docker compose up -d --force-recreate mock-http-mcp >/dev/null
  python3 tests/regression.py refresh DRIFT
  python3 tests/regression.py block MCP-CATALOG-001
done

echo "[catalog] restore approved contract"
MCP_CATALOG_MODE=normal docker compose up -d --force-recreate mock-http-mcp >/dev/null
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
