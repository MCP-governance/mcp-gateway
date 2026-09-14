#!/usr/bin/env bash
set -euo pipefail

LAB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$LAB_DIR"
mkdir -p reports

# The synthetic IdP signs with Ed25519: Agent Service holds the private key, every
# verifier holds only the public key. Generated inside the gateway image so the host
# needs no crypto library. The placeholders only satisfy compose interpolation.
ensure_keys() {
  touch .env && chmod 600 .env
  if grep -qE '^AGENT_JWT_PRIVATE_KEY=.+' .env && grep -qE '^AGENT_JWT_PUBLIC_KEY=.+' .env; then
    return
  fi
  echo "합성 인증용 Ed25519 키쌍을 생성합니다. (최초 1회, gateway 이미지 빌드 필요)"
  AGENT_JWT_PRIVATE_KEY=placeholder AGENT_JWT_PUBLIC_KEY=placeholder docker compose build --quiet gateway
  local generated
  generated="$(AGENT_JWT_PRIVATE_KEY=placeholder AGENT_JWT_PUBLIC_KEY=placeholder \
    docker compose run --rm --no-deps -T --entrypoint python gateway -m app.keygen | tr -d '\r')"
  if ! grep -q '^AGENT_JWT_PRIVATE_KEY=' <<<"$generated"; then
    echo "키 생성에 실패했습니다. docker compose build gateway 를 먼저 확인하세요." >&2
    exit 1
  fi
  sed -i -E '/^AGENT_JWT_(PRIVATE|PUBLIC)_KEY=/d' .env
  printf '%s\n' "$generated" >> .env
  chmod 600 .env
}

ensure_keys

# The gateway API is authenticated now, so scripted maintenance calls log in the
# same way a person does. The password lives in the uncommitted .env.
gateway_token() {
  local password
  password="$(sed -n 's/^MOCK_SSO_PASSWORD=//p' .env 2>/dev/null | tail -1)"
  curl -fsS -X POST http://127.0.0.1:8080/api/session \
    -H 'content-type: application/json' \
    -d "{\"email\":\"admin@bob.local\",\"password\":\"${password:-test-password}\"}" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])'
}

# A workspace-wide scan tells you nothing about which MCP server is affected, and the
# MCP-SUPPLY-001 gate counts criticals against a server's pinned source_ref. So each
# registered server with a scan_path is scanned on its own and the report is named
# after it; core.import_supply_chain_reports attributes it from that name.
scan_registered_servers() {
  local targets
  targets="$(curl -fsS http://127.0.0.1:8080/api/supply-chain/coverage \
    | python3 -c 'import json,sys
for row in json.load(sys.stdin)["servers"]:
    if row["scan_path"]:
        print(row["server_id"], row["scan_path"])')"
  if [[ -z "$targets" ]]; then
    echo "스캔 대상으로 등록된 서버가 없습니다." >&2
    return
  fi
  while read -r server_id scan_path; do
    [[ -z "$server_id" ]] && continue
    echo "[supply-chain] $server_id <- $scan_path"
    docker compose --profile supply-chain run --rm trivy \
      fs --scanners vuln,misconfig,secret --format json \
      --output "/reports/trivy-${server_id}.json" "/workspace/${scan_path}"
  done <<< "$targets"
}

import_reports() {
  curl -fsS -X POST http://127.0.0.1:8080/api/supply-chain/import \
    -H "authorization: Bearer $(gateway_token)" | python3 -m json.tool
}

wait_ready() {
  for _ in {1..60}; do
    if curl -fsS http://127.0.0.1:8000/api/readiness | python3 -c 'import json,sys; sys.exit(0 if json.load(sys.stdin)["status"] == "ready" else 1)' >/dev/null 2>&1; then
      return
    fi
    sleep 1
  done
  echo "Agent와 Gateway가 60초 안에 준비되지 않았습니다. ./demo.sh logs 로 확인하세요." >&2
  exit 1
}

up() {
  docker compose up -d --build gateway gateway-sse agent-service
  wait_ready
  echo
  echo "MCP Governance 데모가 준비되었습니다."
  echo "  Dashboard : http://localhost:8080"
  echo "  업무 공간  : http://localhost:8000 (합성 로그인)"
  echo "  Jaeger    : http://localhost:16686"
  echo "  상태       : ./demo.sh status"
  echo "  전체 검증  : ./demo.sh test"
}

case "${1:-up}" in
  up)
    up
    ;;
  test)
    up
    docker run --rm -v "$LAB_DIR/opa:/policy:ro" openpolicyagent/opa:1.20.2-static test /policy -v
    docker compose exec -T gateway python -m app.acceptance | tee reports/acceptance.json
    tests/drift_and_fail_closed.sh | tee reports/security-regression.txt
    # The gateway service has no private key. The acceptance run is handed one here
    # on purpose, so it can forge expired/wrong-audience/wrong-issuer claim variants.
    docker compose exec -T \
      -e AGENT_JWT_PRIVATE_KEY="$(sed -n 's/^AGENT_JWT_PRIVATE_KEY=//p' .env | tail -1)" \
      gateway python -m app.agent_acceptance | tee reports/agent-acceptance.json
    echo "모든 필수 검증이 통과했습니다."
    ;;
  scan)
    up
    docker compose --profile supply-chain run --rm syft
    docker compose --profile supply-chain run --rm trivy
    scan_registered_servers
    import_reports
    echo "SBOM과 서버별 취약점 결과를 reports/ 및 Dashboard에 반영했습니다."
    ;;
  mcp-scan)
    if [[ -z "${MCP_SCAN_API_KEY:-}" || -z "${MCP_SCAN_BASE_URL:-}" || -z "${MCP_SCAN_MODEL:-}" ]]; then
      echo "mcp-scan은 LLM 기반 CLI라 현재 합의한 무-LLM 모드에서는 자동 실행하지 않습니다." >&2
      echo "로컬 OpenAI 호환 모의 모델이 준비되면 MCP_SCAN_API_KEY, MCP_SCAN_BASE_URL, MCP_SCAN_MODEL을 지정하세요." >&2
      exit 2
    fi
    docker compose --profile mcp-scan run --rm mcp-scan
    import_reports
    ;;
  status)
    docker compose ps
    curl -fsS http://127.0.0.1:8080/api/health | python3 -m json.tool
    curl -fsS http://127.0.0.1:8000/api/readiness | python3 -m json.tool
    ;;
  logs)
    docker compose logs -f --tail=120 agent-service gateway opa mock-http-mcp
    ;;
  down)
    docker compose down
    ;;
  reset)
    docker compose down -v
    # trivy-*.json are the per-server reports that actually feed MCP-SUPPLY-001.
    # Leaving them behind meant a reset did not reset supply-chain evidence: the
    # next import re-attributed stale findings to a freshly created database.
    rm -f reports/acceptance.json reports/agent-acceptance.json reports/security-regression.txt \
      reports/full-test.log reports/sbom.cdx.json reports/trivy.json reports/trivy-*.json \
      reports/mcp-scan.sarif.json
    echo "이 실습 전용 DB·효과 로그·생성 보고서를 초기화했습니다."
    ;;
  *)
    echo "usage: ./demo.sh [up|test|scan|mcp-scan|status|logs|down|reset]" >&2
    exit 2
    ;;
esac
