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

# 이 실습에서 upstream MCP에 host port가 없다는 사실과 API가 loopback에만 붙는다는
# 사실이 유일한 경로 통제다. BIND_ADDR을 와일드카드로 열면 그 통제가 사라지는데,
# 화면에는 아무 변화도 없어서 아무도 알아채지 못한다. 그래서 여기서 거절한다.
# tailnet에 붙이려면 와일드카드가 아니라 이 호스트의 tailscale0 주소를 준다.
case "${BIND_ADDR:-127.0.0.1}" in
  0.0.0.0|::|"*")
    echo "BIND_ADDR=${BIND_ADDR}는 모든 인터페이스에 여는 설정입니다." >&2
    echo "특정 주소(127.0.0.1 또는 이 호스트의 tailscale0 100.x 주소)를 지정하세요. NETWORK.md 참고." >&2
    exit 2
    ;;
esac

# The gateway API is authenticated now, so scripted maintenance calls log in the
# same way a person does. The password lives in the uncommitted .env.
session_token() {
  local email="$1"
  local password
  password="$(sed -n 's/^MOCK_SSO_PASSWORD=//p' .env 2>/dev/null | tail -1)"
  curl -fsS -X POST http://127.0.0.1:8080/api/session \
    -H 'content-type: application/json' \
    -d "{\"email\":\"${email}\",\"password\":\"${password:-test-password}\"}" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])'
}

gateway_token() { session_token admin@bob.local; }

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

agent_test() {
  # The gateway service has no private key. The acceptance run is handed one here
  # on purpose, so it can forge expired/wrong-audience/wrong-issuer claim variants.
  docker compose exec -T \
    -e AGENT_JWT_PRIVATE_KEY="$(sed -n 's/^AGENT_JWT_PRIVATE_KEY=//p' .env | tail -1)" \
    gateway python -m app.agent_acceptance | tee reports/agent-acceptance.json
}

wait_ready() {
  for _ in {1..60}; do
    if curl -fsS http://127.0.0.1:8000/api/readiness | python3 -c 'import json,sys; sys.exit(0 if json.load(sys.stdin)["status"] == "ready" else 1)' >/dev/null 2>&1; then
      return
    fi
    sleep 1
  done
  echo "Agent와 Gateway가 60초 안에 준비되지 않았습니다. ./console.sh logs 로 확인하세요." >&2
  exit 1
}

# Corporate-lab is a separate Compose overlay: it adds Tencent A.I.G and two
# internal-only networks, without widening the normal lab's exposed surface.
lab_compose() {
  LAB_MODE=1 docker compose -f compose.yaml -f compose.corporate-lab.yaml "$@"
}

wait_aig_ready() {
  for _ in {1..60}; do
    # Docker Desktop/WSL port forwarding can lag even after the container's own
    # listener is ready. Verify the service from its network namespace first.
    if lab_compose exec -T aig-webserver curl -fsS http://localhost:8088/ >/dev/null 2>&1; then
      return
    fi
    sleep 1
  done
  echo "A.I.G Web UI가 60초 안에 준비되지 않았습니다. ./console.sh lab-logs 로 확인하세요." >&2
  exit 1
}

lab_up() {
  lab_compose up -d --build gateway gateway-sse agent-service intake-worker \
    aig-lab-model aig-webserver aig-agent
  wait_ready
  wait_aig_ready
  echo "기업 내부망 실습과 Tencent A.I.G가 준비되었습니다."
  echo "  Governance Console: http://localhost:8000"
  echo "  A.I.G Web UI       : http://localhost:8088"
}

lab_gateway() {
  lab_compose exec -T gateway python -m app.corporate_lab "$@"
}

submit_normal_intake() {
  local employee admin created request_id
  employee="$(session_token miso@bob.local)"
  created="$(curl -fsS -X POST http://127.0.0.1:8000/api/mcp-requests \
    -H "authorization: Bearer $employee" -H 'content-type: application/json' \
    -d '{"display_name":"GitHub MCP Server (normal intake)","repository_url":"https://github.com/github/github-mcp-server","requested_transport":"streamable-http","purpose":"Corporate-lab normal intake through the isolated supply-chain queue.","provider_credential_disclosure":true,"revocation_evidence":true,"audit_access_retained":true}')"
  request_id="$(printf '%s' "$created" | python3 -c 'import json,sys; print(json.load(sys.stdin)["request"]["id"])')"
  admin="$(gateway_token)"
  curl -fsS -X POST "http://127.0.0.1:8000/api/mcp-requests/${request_id}/queue-validation" \
    -H "authorization: Bearer $admin" | python3 -m json.tool
  echo "정상 MCP 도입 요청을 격리 검증 대기열에 넣었습니다: $request_id"
}

run_candidate_trivy() {
  lab_compose --profile supply-chain run --rm trivy \
    fs --scanners vuln --format json --output /reports/trivy-mock-http.json \
    /workspace/full_stack_lab/lab/candidates/filesystem-0.6.2
  import_reports
}

queue_aig_dynamic_scan() {
  local admin job_id
  admin="$(gateway_token)"
  job_id="$(curl -fsS -X POST http://127.0.0.1:8000/api/mcp-scan/run \
    -H "authorization: Bearer $admin" -H 'content-type: application/json' \
    -d '{"target_kind":"server","target_id":"mock-http","mode":"dynamic"}' \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["job_id"])')"
  for _ in {1..180}; do
    local state
    state="$(curl -fsS http://127.0.0.1:8000/api/mcp-scan -H "authorization: Bearer $admin" \
      | python3 -c 'import json,sys; job=sys.argv[1]; rows=json.load(sys.stdin)["jobs"]; print(next((r["status"] for r in rows if str(r["id"]) == job), "MISSING"))' "$job_id")"
    case "$state" in
      DONE) echo "A.I.G mcp-scan 완료: $job_id"; return ;;
      FAILED|CANCELLED|MISSING) echo "A.I.G mcp-scan 실패 상태: $state ($job_id)" >&2; return 1 ;;
    esac
    sleep 1
  done
  echo "A.I.G mcp-scan 시간 초과: $job_id" >&2
  return 1
}

lab_network_targets() {
  local network
  while read -r network; do
    [[ -z "$network" ]] && continue
    docker network inspect "$network" --format '{{range $id, $container := .Containers}}{{$container.IPv4Address}}{{"\\n"}}{{end}}'
  done < <(docker network ls --filter 'label=com.docker.compose.project=mcp-governance-full' --format '{{.Name}}') \
    | sed 's:/.*::' | sort -u | paste -sd, -
}

scan_internal_network() {
  local targets
  targets="$(lab_network_targets)"
  if [[ -z "$targets" ]]; then
    echo "Compose 내부망 자산 IP를 찾지 못했습니다." >&2
    return 1
  fi
  LAB_NET_TARGETS="$targets" LAB_NET_PORTS='5432,8000,8080,8088,8181,9000,4010,4317,4318,16686' \
    lab_compose --profile lab-network-probe run --rm --no-deps aig-network-probe \
    | tee reports/aig-network-inventory.json
}

up() {
  docker compose up -d --build gateway gateway-sse agent-service intake-worker
  wait_ready
  echo
  echo "MCP Governance Console이 준비되었습니다."
  echo "  운영 콘솔  : http://localhost:8000"
  echo "  Jaeger    : http://localhost:16686"
  echo "  상태       : ./console.sh status"
  echo "  전체 검증  : ./console.sh test"
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
    agent_test
    docker compose exec -T gateway python -m app.runtime_acceptance | tee reports/runtime-acceptance.json
    echo "모든 필수 검증이 통과했습니다."
    ;;
  agent-test)
    up
    agent_test
    ;;
  endpoint)
    # 엔드포인트 평면. 기본 기동에 넣지 않는 이유는 남의 PC 설정을 읽는 기능이
    # 기본값으로 켜져 있으면 안 되기 때문이다. 켤 때는 무엇을 읽는지 화면에 적는다.
    up
    echo "관측 경로: ${ENDPOINT_CONFIG_SOURCE:-./endpoint/sample-configs} (읽기 전용)"
    docker compose --profile endpoint up -d --build endpoint-agent
    echo "엔드포인트 에이전트를 올렸습니다. Console의 '엔드포인트' 화면에서 확인하세요."
    echo "  로그: docker compose logs -f endpoint-agent"
    ;;
  corporate-lab)
    lab_up
    lab_gateway self-check
    scan_internal_network
    lab_gateway verify-network
    submit_normal_intake
    lab_gateway seed
    run_candidate_trivy
    lab_gateway verify-supply
    queue_aig_dynamic_scan
    lab_gateway verify-aig
    lab_gateway contain
    lab_gateway open-retirement
    # The target has no host port. Removing this one container is the physical
    # removal proof that the retirement probe evaluates; it does not touch DB.
    lab_compose rm -sf mock-http-mcp
    lab_gateway finish-retirement
    lab_gateway summary | tee reports/corporate-lab-summary.json
    echo "기업 내부망 시나리오를 완료했습니다. 증적: reports/corporate-lab-summary.json"
    ;;
  lab-down)
    # This overlay owns only lab services/volumes. It also removes the test
    # double and Tencent A.I.G data; normal `down` remains non-destructive.
    lab_compose --profile endpoint --profile llm-stub down -v
    ;;
  lab-logs)
    lab_compose logs -f --tail=120 aig-webserver aig-agent aig-lab-model intake-worker gateway agent-service
    ;;
  openapi)
    # 개발용 API 명세. FastAPI가 코드에서 만들어 주므로 손으로 쓴 문서가 코드와
    # 갈라질 일이 없다. 통합 단계에서 다른 팀이 보는 것은 이 파일이다.
    up
    mkdir -p ../docs/openapi
    for service in gateway agent-service; do
      docker compose exec -T "$service" python -c "
import json, sys
from importlib import import_module
module = import_module('app.main' if '$service' == 'gateway' else 'app.agent_service')
json.dump(module.app.openapi(), sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
" > "../docs/openapi/${service}.json"
      echo "docs/openapi/${service}.json"
    done
    echo "OpenAPI 명세를 생성했습니다. 사람이 읽는 명세는 docs/API.md 입니다."
    ;;
  scan)
    up
    docker compose --profile supply-chain run --rm syft
    docker compose --profile supply-chain run --rm trivy
    docker compose --profile supply-chain run --rm semgrep
    scan_registered_servers
    import_reports
    echo "SBOM·SCA·SAST 결과를 reports/ 및 운영 콘솔에 반영했습니다."
    ;;
  status)
    docker compose ps
    curl -fsS http://127.0.0.1:8080/api/health | python3 -m json.tool
    curl -fsS http://127.0.0.1:8000/api/readiness | python3 -m json.tool
    ;;
  logs)
    docker compose logs -f --tail=120 agent-service gateway opa mock-http-mcp intake-worker
    ;;
  down)
    # 프로필로 띄운 서비스는 profile을 함께 줘야 내려간다. 그러지 않으면
    # down 뒤에도 엔드포인트 에이전트가 남아 계속 보고한다.
    docker compose --profile endpoint --profile llm-stub down
    ;;
  reset)
    docker compose --profile endpoint --profile llm-stub down -v
    # trivy-*.json are the per-server reports that actually feed MCP-SUPPLY-001.
    # Leaving them behind meant a reset did not reset supply-chain evidence: the
    # next import re-attributed stale findings to a freshly created database.
    # 이전 판은 줄바꿈 이어쓰기가 끊겨서 두 번째 줄부터가 삭제 대상이 아니라
    # 실행할 명령으로 해석됐다. reset이 보고서를 한 번도 지우지 못했다는 뜻이다.
    rm -f \
      reports/acceptance.json \
      reports/agent-acceptance.json \
      reports/runtime-acceptance.json \
      reports/security-regression.txt \
      reports/full-test.log \
      reports/sbom.cdx.json \
      reports/trivy.json \
      reports/trivy-*.json \
      reports/semgrep.json \
      reports/intake-*.json
    echo "이 실습 전용 DB·효과 로그·생성 보고서를 초기화했습니다."
    ;;
  *)
    echo "usage: ./console.sh [up|test|agent-test|endpoint|scan|openapi|status|logs|down|reset|corporate-lab|lab-down|lab-logs]" >&2
    exit 2
    ;;
esac
