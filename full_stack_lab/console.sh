#!/usr/bin/env bash
# MCP Governance Lab v2 — single entry point. See docs/ai/RUNBOOK.md.
set -euo pipefail

LAB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$LAB_DIR"
mkdir -p reports

env_value() { [[ -f .env ]] || return 0; sed -n "s/^$1=//p" .env | tail -1; }
# Host ports come from the environment or .env so two labs can share one Docker host.
host_port() { local v="${!1:-}"; [[ -n "$v" ]] || v="$(env_value "$1")"; echo "${v:-$2}"; }
CONSOLE="http://127.0.0.1:$(host_port CONSOLE_PORT 8000)"
GATEWAY="http://127.0.0.1:$(host_port GATEWAY_PORT 8080)"
export LAB_CONSOLE_URL="$CONSOLE" LAB_GATEWAY_URL="$GATEWAY"
WORKSTATIONS=(ws-ysg ws-jwj ws-pse ws-nkk)
declare -A WS_OWNER=([ws-ysg]=emp-ysg [ws-jwj]=emp-jwj [ws-pse]=emp-pse [ws-nkk]=partner-demo)

usage() {
  cat >&2 <<'EOF'
usage: ./console.sh <command>

  up [--no-llm]          전체 기동 (회사 시스템·MCP 10종·Gateway·Console·직원 PC 4대·로컬 LLM)
  workday [ws|all] [--mode llm|scripted] [--check]
                         직원의 하루 업무 시나리오를 각자의 하네스로 실행 (기본: 전원, llm 모드)
  ask <ws> "지시" [--servers a,b] [--harness claude|codex|gemini|opencode]
                         한 직원의 PC에 설치된 하네스에 업무 지시 (헤드리스)
  harnesses              직원 PC마다 하네스 4종이 Gateway의 MCP 서버에 붙는지 확인 (LLM 불필요)
  watch                  Gateway 판정을 사람이 읽는 한 줄 로그로 계속 출력
  contracts [--update|--check]
                         MCP 서버 계약 해시(registry/contracts.lock.json) 생성·대조
  experiment e1|e2|e3    논문 재현 실험 (E1 토큰 폐기, E2 세션 종료, E3 서버 보유 자격)
  restore <server>       (실습용) 종료·폐기한 서버를 다시 운영 상태로 되돌림 (gitea는 토큰 재발급)
  test                   전체 검증 (Rego·분류 self-check·acceptance·시나리오·보안 회귀)
  replay [N]             기록된 정책 입력 N건(기본 100)과 합성 라벨 사례를 후보 정책(REPLAY_POLICY_DIR)에 재생 — MCP 호출 없음
  status | logs [svc] | down | reset | scan | openapi
EOF
}

# ── .env: project name, signing keys, LiteLLM master key, per-workstation keys ──
ensure_env() {
  touch .env && chmod 600 .env
  if [[ -z "${COMPOSE_PROJECT_NAME:-}" ]] && ! grep -qE '^(MCP_COMPOSE_PROJECT|COMPOSE_PROJECT_NAME)=' .env; then
    printf 'MCP_COMPOSE_PROJECT=mcpgw-%s\n' "$(printf '%s' "$LAB_DIR" | sha256sum | cut -c1-10)" >> .env
  fi
  # compose.yaml gives every network an explicit /24 under this /16, picked once per
  # checkout from ranges no other Docker network or route uses (D-24). A failed pick
  # stops here rather than writing an empty prefix.
  if [[ -z "${MCP_NET_PREFIX:-}" ]] && ! grep -qE '^MCP_NET_PREFIX=10\.[0-9]+$' .env; then
    local prefix; prefix="$(python3 scripts/network_prefix.py "$LAB_DIR")"
    echo "MCP_NET_PREFIX=$prefix" >> .env
  fi
  if ! grep -qE '^AGENT_JWT_PRIVATE_KEY=.+' .env; then
    echo "합성 IdP 서명 키(Ed25519)를 생성합니다."
    export AGENT_JWT_PRIVATE_KEY=placeholder AGENT_JWT_PUBLIC_KEY=placeholder LITELLM_MASTER_KEY=placeholder
    docker compose build -q gateway
    docker compose run --rm --no-deps -T --entrypoint python gateway -m app.keygen | tr -d '\r' >> .env
    unset AGENT_JWT_PRIVATE_KEY AGENT_JWT_PUBLIC_KEY LITELLM_MASTER_KEY
  fi
  grep -q '^LITELLM_MASTER_KEY=' .env || echo "LITELLM_MASTER_KEY=sk-master-$(openssl rand -hex 16)" >> .env
  for ws in "${WORKSTATIONS[@]}"; do
    local up; up="$(echo "${ws#ws-}" | tr a-z A-Z)"
    grep -q "^LLM_KEY_WS_${up}=" .env || echo "LLM_KEY_WS_${up}=sk-${ws}-$(openssl rand -hex 12)" >> .env
    grep -q "^ENDPOINT_KEY_WS_${up}=" .env || echo "ENDPOINT_KEY_WS_${up}=ek-${ws}-$(openssl rand -hex 20)" >> .env
  done
}


admin_token() {
  curl -fsS -X POST $CONSOLE/auth/mock-login -H 'content-type: application/json' \
    -d "{\"email\":\"kkg@bob.local\",\"password\":\"$(env_value MOCK_SSO_PASSWORD || true)\"}" 2>/dev/null \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])' 2>/dev/null \
  || curl -fsS -X POST $CONSOLE/auth/mock-login -H 'content-type: application/json' \
    -d '{"email":"kkg@bob.local","password":"test-password"}' \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])'
}

wait_ready() {
  for _ in $(seq 1 90); do
    if curl -fsS $CONSOLE/api/readiness 2>/dev/null \
      | python3 -c 'import json,sys; sys.exit(0 if json.load(sys.stdin)["status"] == "ready" else 1)' 2>/dev/null; then
      return 0
    fi
    sleep 2
  done
  echo "Gateway·Console이 3분 안에 준비되지 않았습니다. ./console.sh logs gateway 로 확인하세요." >&2
  exit 1
}

# Device credentials for each workstation's endpoint agent, registered with the keys
# that ensure_env generated. Issuing is an admin act; the agent only reports.
provision_devices() {
  local token ws up key
  token="$(admin_token)"
  for ws in "${WORKSTATIONS[@]}"; do
    up="$(echo "${ws#ws-}" | tr a-z A-Z)"
    key="$(env_value "ENDPOINT_KEY_WS_${up}")"
    curl -fsS -o /dev/null -X POST $GATEWAY/api/endpoint/devices \
      -H "authorization: Bearer $token" -H 'content-type: application/json' \
      -d "{\"endpoint_id\":\"$ws\",\"hostname\":\"$ws\",\"platform\":\"linux\",\"owner_token\":\"${WS_OWNER[$ws]}\",\"scopes\":[\"inventory\",\"netscan\"],\"enrollment_key\":\"$key\"}"
  done
  echo "  장치 자격 ${#WORKSTATIONS[@]}건 등록"
}

ensure_contracts() {
  if [[ ! -s registry/contracts.lock.json ]]; then
    echo "  계약 기준선이 없어 지금 서버에서 생성합니다 (registry/contracts.lock.json)."
    contracts_update
  fi
}

contracts_update() {
  docker compose exec -T gateway python -m app.registry lock > /tmp/contracts.lock.$$ \
    && mv /tmp/contracts.lock.$$ registry/contracts.lock.json
  docker compose restart gateway gateway-sse >/dev/null
  wait_ready
  curl -fsS -X POST $GATEWAY/api/catalog/refresh -H "authorization: Bearer $(admin_token)" >/dev/null
}

up() {
  local llm=1
  [[ "${1:-}" == "--no-llm" ]] && llm=0
  ensure_env
  echo "[1/5] 이미지 빌드"
  docker compose build -q
  echo "[2/5] 회사 시스템과 MCP 서버 10종"
  docker compose up -d corp-git corp-redis corp-db corp-mail intranet external-web
  docker compose up -d mcp-filesystem mcp-git mcp-fetch mcp-memory mcp-desktop mcp-postgres \
    mcp-redis mcp-email mcp-gitea mcp-playwright
  if [[ $llm == 1 ]]; then
    echo "[3/5] 로컬 LLM (Ollama + LiteLLM 직원별 키)"
    # qwen3.5 2B (Q4) calls MCP tools well enough and loads in 1.7 GB; the 4B chooses
    # better but needs ~3.4 GB more than a 7.6 GB WSL VM can spare next to the lab (D-32).
    local model; model="$(env_value LOCAL_LLM_MODEL)"; model="${model:-qwen3.5:2b-q4_K_M}"
    # The manifest file is how Ollama records a pulled model; checking it needs no network.
    if ! docker compose --profile llm run --rm --no-deps --entrypoint sh ollama -c \
        "test -f /root/.ollama/models/manifests/registry.ollama.ai/library/${model%%:*}/${model##*:}"; then
      docker compose --profile llm-download run --rm ollama-pull
    fi
    docker compose --profile llm up -d ollama
    # The model employees get is a derived one with a fixed thread count. On hybrid
    # Intel CPUs (P + E + LP-E cores) llama.cpp's default of one thread per logical
    # CPU waits on the slowest cores: 0.5 tok/s at 16 threads vs 32 tok/s at 6-8 on
    # this lab's Ultra 7 255H. LOCAL_LLM_THREADS overrides it.
    local threads; threads="$(env_value LOCAL_LLM_THREADS)"; threads="${threads:-6}"
    # A harness's first turn is its prompt plus the MCP tool schemas of the servers in
    # use: 12k tokens holds Codex's compact prompt with its own tools and one large server.
    local ctx; ctx="$(env_value LOCAL_LLM_CONTEXT)"; ctx="${ctx:-12288}"
    for _ in $(seq 1 30); do docker compose --profile llm exec -T ollama ollama list >/dev/null 2>&1 && break; sleep 2; done
    docker compose --profile llm exec -T ollama sh -c \
      "printf 'FROM %s\nPARAMETER num_thread %s\nPARAMETER temperature 0\nPARAMETER num_ctx %s\n' '$model' '$threads' '$ctx' > /tmp/Modelfile && ollama create bob-assistant -f /tmp/Modelfile >/dev/null"
    docker compose --profile llm up -d llm-gateway
    docker compose --profile llm run --rm llm-provision
  else
    echo "[3/5] 로컬 LLM 생략 (--no-llm: 직원 PC의 도구 호출은 MCP Inspector CLI가 대신함)"
  fi
  echo "[4/5] Gateway·Console·검증 워커"
  docker compose up -d gateway gateway-sse agent-service intake-worker
  wait_ready
  ensure_contracts
  provision_devices
  echo "[5/5] 직원 워크스테이션"
  if [[ $llm == 1 ]]; then
    docker compose up -d "${WORKSTATIONS[@]}"
  else
    AGENT_MODE=scripted docker compose up -d "${WORKSTATIONS[@]}"
  fi
  echo
  echo "준비되었습니다."
  echo "  운영 콘솔 : ${CONSOLE/127.0.0.1/localhost}   (kkg@bob.local / test-password)"
  echo "  Gitea     : http://localhost:$(host_port GITEA_PORT 3000)   (corpadmin — 제공자 자격 확인용)"
  echo "  Jaeger    : http://localhost:$(host_port JAEGER_PORT 16686)"
  echo "  하루 업무 : ./console.sh workday        판정 흐름 : ./console.sh watch"
}

workday() {
  local target="all" mode="" check=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --mode) mode="$2"; shift 2 ;;
      --check) check="--check"; shift ;;
      *) target="$1"; shift ;;
    esac
  done
  local list=("${WORKSTATIONS[@]}")
  [[ "$target" != "all" ]] && list=("$target")
  local failed=0
  for ws in "${list[@]}"; do
    echo "════ $ws ════"
    docker compose exec -T "$ws" workday ${mode:+--mode "$mode"} $check || failed=1
  done
  return $failed
}

# Every harness on every PC connects to each managed MCP server through the Gateway
# with the SSO token. No model is involved: `mcp list` only opens the MCP sessions.
harness_check() {
  local failed=0 ws
  for ws in "${WORKSTATIONS[@]}"; do
    docker compose exec -T "$ws" harness-check || failed=1
  done
  return $failed
}

watch_decisions() {
  python3 scripts/watch.py "$(admin_token)"
}

case "${1:-up}" in
  up) shift || true; up "$@" ;;
  workday) shift; workday "$@" ;;
  ask)
    ws="${2:?워크스테이션을 지정하세요 (예: ws-ysg)}"; goal="${3:?지시를 입력하세요}"; shift 3
    docker compose exec -T "$ws" bob-ask "$@" "$goal"
    ;;
  harnesses) harness_check ;;
  watch) watch_decisions ;;
  contracts)
    case "${2:-}" in
      --update) contracts_update; echo "registry/contracts.lock.json 갱신" ;;
      --check|"") docker compose exec -T gateway python -m app.registry lock > /tmp/contracts.check.$$
                  python3 tests/contracts_check.py registry/contracts.lock.json /tmp/contracts.check.$$ ;;
    esac
    ;;
  restore)
    server="${2:?서버 id를 지정하세요 (예: gitea)}"
    curl -fsS -X POST "$GATEWAY/api/lab/restore/${server}" -H "authorization: Bearer $(admin_token)" | python3 -m json.tool
    # An `[[ … ]] && …` as the last command exits 1 for every other server under set -e.
    if [[ "$server" == "gitea" ]]; then "$0" restore-token gitea; fi
    ;;
  restore-token)
    # The Gitea MCP server's own token was revoked by a termination case: issue a new
    # one (corp-seed issues it when the secret file is missing) and restart the server.
    docker compose run --rm --no-deps --entrypoint sh corp-seed -c 'rm -f /run/corp-secrets/gitea-mcp.token' >/dev/null
    docker compose run --rm corp-seed >/dev/null
    docker compose restart mcp-gitea >/dev/null
    for _ in $(seq 1 30); do docker compose ps mcp-gitea | grep -q healthy && break; sleep 2; done
    curl -fsS -X POST $GATEWAY/api/catalog/refresh -H "authorization: Bearer $(admin_token)" >/dev/null
    echo "gitea-mcp 토큰을 재발급하고 서버를 재시작했습니다."
    ;;
  experiment)
    docker compose exec -T gateway python -m app.experiments "${2:?e1|e2|e3}" | tee "reports/experiment-${2}.json"
    ;;
  replay)
    # Candidate policy = REPLAY_POLICY_DIR (default: the current ./opa). Recorded policy
    # inputs and the frozen synthetic corpus go to it; no MCP tool is called.
    REPLAY_POLICY_DIR="${REPLAY_POLICY_DIR:-./opa}" docker compose --profile replay up -d --wait opa-candidate
    trap 'docker compose --profile replay stop opa-candidate >/dev/null' EXIT
    docker compose exec -T -e REPLAY_OPA_URL=http://opa-candidate:8181/v1/data/mcp/authz/decision \
      gateway python -m app.replay --limit "${2:-100}" | tee reports/policy-replay.json
    python3 tests/replay_check.py reports/policy-replay.json
    ;;
  test)
    ensure_env
    python3 scripts/network_prefix.py --self-check
    if command -v node >/dev/null; then node --test tests/console-state.test.mjs
    else echo "node 없음 — 콘솔 상태 테스트는 CI 정적 검사에서 실행됩니다."; fi
    # --entrypoint: the static image's default entrypoint runs the tests without printing them
    docker run --rm --entrypoint /opa -v "$LAB_DIR/opa:/policy:ro" openpolicyagent/opa:1.20.2-static test /policy
    docker compose exec -T gateway python -m app.classify
    docker compose exec -T gateway python -m app.acceptance | tee reports/acceptance.json
    harness_check | tee reports/harnesses.txt
    AGENT_MODE=scripted workday all --mode scripted --check | tee reports/workday.txt
    python3 tests/termination_flow.py | tee reports/termination-flow.txt
    tests/security_regression.sh | tee reports/security-regression.txt
    docker compose exec -T gateway python -m app.replay --limit 200 > reports/policy-replay.json
    python3 tests/replay_check.py reports/policy-replay.json
    for e in e1 e2 e3; do docker compose exec -T gateway python -m app.experiments "$e" > "reports/experiment-$e.json"; done
    python3 tests/experiments_check.py reports/experiment-e1.json reports/experiment-e2.json reports/experiment-e3.json
    echo "모든 필수 검증이 통과했습니다."
    ;;
  scan)
    docker compose --profile supply-chain run --rm syft
    docker compose --profile supply-chain run --rm trivy
    docker compose --profile supply-chain run --rm semgrep
    curl -fsS -X POST $GATEWAY/api/supply-chain/import -H "authorization: Bearer $(admin_token)" | python3 -m json.tool
    ;;
  openapi)
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
    ;;
  status)
    docker compose --profile llm ps --format 'table {{.Service}}\t{{.Status}}'
    curl -fsS $GATEWAY/api/health | python3 -m json.tool
    ;;
  logs) shift; docker compose --profile llm logs -f --tail=120 "${@:-gateway}" ;;
  down) docker compose --profile llm --profile llm-stub --profile replay down ;;
  reset)
    docker compose --profile llm --profile llm-stub --profile replay down -v
    rm -f reports/*.json reports/*.txt
    echo "DB·회사 시스템·모델 볼륨과 보고서를 초기화했습니다. registry/contracts.lock.json은 유지합니다."
    ;;
  -h|--help|help) usage ;;
  *) usage; exit 2 ;;
esac
