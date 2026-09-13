#!/usr/bin/env bash
set -euo pipefail

LAB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$LAB_DIR"
mkdir -p reports

wait_gateway() {
  for _ in {1..60}; do
    if curl -fsS http://127.0.0.1:8080/api/health >/dev/null 2>&1; then
      return
    fi
    sleep 1
  done
  echo "Gateway가 60초 안에 준비되지 않았습니다. ./demo.sh logs 로 확인하세요." >&2
  exit 1
}

up() {
  docker compose up -d --build gateway gateway-sse
  wait_gateway
  echo
  echo "MCP Governance 데모가 준비되었습니다."
  echo "  Dashboard : http://localhost:8080"
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
    echo "모든 필수 검증이 통과했습니다."
    ;;
  scan)
    up
    docker compose --profile supply-chain run --rm syft
    docker compose --profile supply-chain run --rm trivy
    curl -fsS -X POST http://127.0.0.1:8080/api/supply-chain/import | python3 -m json.tool
    echo "SBOM과 취약점 결과를 reports/ 및 Dashboard에 반영했습니다."
    ;;
  mcp-scan)
    if [[ -z "${MCP_SCAN_API_KEY:-}" || -z "${MCP_SCAN_BASE_URL:-}" || -z "${MCP_SCAN_MODEL:-}" ]]; then
      echo "mcp-scan은 LLM 기반 CLI라 현재 합의한 무-LLM 모드에서는 자동 실행하지 않습니다." >&2
      echo "로컬 OpenAI 호환 모의 모델이 준비되면 MCP_SCAN_API_KEY, MCP_SCAN_BASE_URL, MCP_SCAN_MODEL을 지정하세요." >&2
      exit 2
    fi
    docker compose --profile mcp-scan run --rm mcp-scan
    curl -fsS -X POST http://127.0.0.1:8080/api/supply-chain/import | python3 -m json.tool
    ;;
  status)
    docker compose ps
    curl -fsS http://127.0.0.1:8080/api/health | python3 -m json.tool
    ;;
  logs)
    docker compose logs -f --tail=120 gateway opa mock-http-mcp
    ;;
  down)
    docker compose down
    ;;
  reset)
    docker compose down -v
    rm -f reports/acceptance.json reports/security-regression.txt reports/sbom.cdx.json reports/trivy.json reports/mcp-scan.sarif.json
    echo "이 실습 전용 DB·효과 로그·생성 보고서를 초기화했습니다."
    ;;
  *)
    echo "usage: ./demo.sh [up|test|scan|mcp-scan|status|logs|down|reset]" >&2
    exit 2
    ;;
esac
