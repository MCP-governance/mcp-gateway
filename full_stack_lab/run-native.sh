#!/usr/bin/env bash
# Docker 없이 이 저장소를 한 호스트에서 띄운다.
#
# compose.yaml이 정본이고 이 스크립트는 그 정본을 저사양 장비에서 재현하는 경로다.
# Docker Desktop이 없는 노트북(또는 WSL2 한 대)에서도 게이트웨이·OPA·mock MCP·
# Agent Service를 그대로 돌려 acceptance를 실행할 수 있어야, "환경이 없어서 검증을
# 못 했다"가 나오지 않는다.
#
# 컨테이너가 주던 격리는 여기에 없다. 이 경로는 개발·검증용이고 운영 배치 모델이
# 아니다. 그래서 바인딩은 전부 127.0.0.1이고 그 사실을 아래에서 강제한다.
set -euo pipefail

LAB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$LAB_DIR"

RUN_DIR="${NATIVE_RUN_DIR:-$LAB_DIR/.native}"
VENV="${NATIVE_VENV:-$HOME/mcpgw-venv}"
TIME_VENV="${NATIVE_TIME_VENV:-$HOME/mcpgw-time-venv}"
OPA_BIN="${OPA_BIN:-$HOME/bin/opa}"
PGHOST="${PGHOST:-127.0.0.1}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-mcp}"
PGPASSWORD_VALUE="${POSTGRES_PASSWORD:-demo-only-change-me}"
PGDATABASE="${PGDATABASE:-mcp_governance}"
BIND="${BIND_ADDR:-127.0.0.1}"

case "$BIND" in
  0.0.0.0|::|"*")
    echo "BIND_ADDR=$BIND는 모든 인터페이스에 여는 설정입니다. 네이티브 경로는 컨테이너 격리가 없어 더 위험합니다." >&2
    exit 2 ;;
esac

mkdir -p "$RUN_DIR" reports
ENV_FILE="$LAB_DIR/.env.native"

log() { printf '[native] %s\n' "$*"; }
die() { printf '[native] %s\n' "$*" >&2; exit 1; }

need() { command -v "$1" >/dev/null 2>&1 || die "$1 이(가) 필요합니다. $2"; }

preflight() {
  [[ -x "$VENV/bin/python" ]] || die "python venv가 없습니다: $VENV — 먼저 ./run-native.sh setup"
  [[ -x "$OPA_BIN" ]] || die "opa 바이너리가 없습니다: $OPA_BIN — 먼저 ./run-native.sh setup"
  need psql "postgresql-client를 설치하세요."
  PGPASSWORD="$PGPASSWORD_VALUE" psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -tAc 'select 1' >/dev/null \
    || die "PostgreSQL에 접속할 수 없습니다: $PGUSER@$PGHOST:$PGPORT/$PGDATABASE"
}

# compose 경로와 같은 규칙이다. Agent Service만 개인키를 갖고 검증자는 공개키만
# 갖는다. 네이티브라고 한 프로세스가 둘 다 들고 있으면 그 분리가 사라진다.
ensure_keys() {
  touch "$ENV_FILE" && chmod 600 "$ENV_FILE"
  if grep -qE '^AGENT_JWT_PRIVATE_KEY=.+' "$ENV_FILE" && grep -qE '^AGENT_JWT_PUBLIC_KEY=.+' "$ENV_FILE"; then
    return
  fi
  log "Ed25519 키쌍 생성 (최초 1회)"
  ( cd "$LAB_DIR/gateway" && "$VENV/bin/python" -m app.keygen ) >> "$ENV_FILE"
  chmod 600 "$ENV_FILE"
}

load_env() {
  set -a
  if [[ -f "$LAB_DIR/.env" ]]; then
    source <(grep -E '^[A-Z][A-Z0-9_]*=' "$LAB_DIR/.env" || true)
  fi
  source <(grep -E '^[A-Z][A-Z0-9_]*=' "$ENV_FILE")
  set +a
}

common_env() {
  export DATABASE_URL="postgresql://${PGUSER}:${PGPASSWORD_VALUE}@${PGHOST}:${PGPORT}/${PGDATABASE}"
  export OPA_URL="http://127.0.0.1:8181/v1/data/mcp/authz/decision"
  export POLICY_LEDGER_URL="http://127.0.0.1:8181/v1/data/policy_ledger"
  export HTTP_MCP_URL="http://127.0.0.1:9000/mcp/"
  export MOCK_MCP_HEALTH_URL="http://127.0.0.1:9000/health"
  export EFFECT_LOG="$RUN_DIR/upstream-effects.jsonl"
  export REPORT_DIR="$LAB_DIR/reports"
  export POLICY_PATH="$LAB_DIR/opa/policy.rego"
  export TIME_MCP_PYTHON="$TIME_VENV/bin/python"
  export GATEWAY_URL="http://127.0.0.1:8080"
  export AGENT_SERVICE_URL="http://127.0.0.1:8000"
  export GATEWAY_SSE_URL="http://127.0.0.1:8081/sse"
  # 네이티브 경로에는 Jaeger가 없다. 끄지 않으면 매 스팬마다 연결 실패 로그가
  # 쌓여서 실제 오류가 그 안에 묻힌다.
  export OTEL_SDK_DISABLED="${OTEL_SDK_DISABLED:-true}"
  export JAEGER_QUERY_URL="${JAEGER_QUERY_URL:-}"
  export MOCK_SSO_PASSWORD="${MOCK_SSO_PASSWORD:-test-password}"
  export PYTHONPATH="$LAB_DIR/gateway"
  export PYTHONUNBUFFERED=1
}

pidfile() { echo "$RUN_DIR/$1.pid"; }

start_one() {
  local name="$1"; shift
  local pf; pf="$(pidfile "$name")"
  if [[ -f "$pf" ]] && kill -0 "$(cat "$pf")" 2>/dev/null; then
    log "$name 이미 실행 중 (pid $(cat "$pf"))"
    return
  fi
  # setsid로 새 세션에 넣는다. 그러지 않으면 이 스크립트를 띄운 셸이 끝날 때
  # (원격 실행, CI 스텝, wsl.exe 한 번 호출) 프로세스 그룹째 같이 죽는다.
  setsid nohup "$@" >"$RUN_DIR/$name.log" 2>&1 < /dev/null &
  echo $! > "$pf"
  disown 2>/dev/null || true
  log "$name 기동 (pid $(cat "$pf")) · 로그 $RUN_DIR/$name.log"
}

stop_one() {
  local name="$1" pf pid
  pf="$(pidfile "$name")"
  [[ -f "$pf" ]] || return 0
  pid="$(cat "$pf")"
  if kill -0 "$pid" 2>/dev/null; then
    pkill -TERM -P "$pid" 2>/dev/null || true
    kill -TERM "$pid" 2>/dev/null || true
    for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.2; done
    kill -KILL "$pid" 2>/dev/null || true
  fi
  rm -f "$pf"
  log "$name 정지"
}

wait_http() {
  local url="$1" label="$2" tries="${3:-60}"
  for _ in $(seq 1 "$tries"); do
    curl -fsS -o /dev/null "$url" 2>/dev/null && return 0
    sleep 1
  done
  die "$label 이(가) 준비되지 않았습니다: $url (로그: $RUN_DIR)"
}

schema() {
  log "스키마·시드 적용"
  PGPASSWORD="$PGPASSWORD_VALUE" psql -v ON_ERROR_STOP=1 -q \
    -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -f "$LAB_DIR/db/init.sql"
}

cmd_setup() {
  [[ -x "$VENV/bin/python" ]] || python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q --upgrade pip
  "$VENV/bin/pip" install -q -r "$LAB_DIR/gateway/requirements.txt"
  # Time MCP는 반드시 별도 venv다. mcp-server-time은 mcp<2를 요구하고 게이트웨이는
  # mcp==2.2.0을 쓴다. 한 venv에 넣으면 둘 중 하나가 조용히 내려가고, 그 결과가
  # "stdio 시험 실패"가 아니라 "서버 기동 실패"로 나타나 원인을 찾기 어려워진다.
  # gateway/Dockerfile이 /opt/time-mcp를 따로 만드는 이유와 같다.
  [[ -x "$TIME_VENV/bin/python" ]] || python3 -m venv "$TIME_VENV"
  "$TIME_VENV/bin/pip" install -q --upgrade pip
  "$TIME_VENV/bin/pip" install -q "mcp-server-time==2026.8.18" || log "mcp-server-time 설치 실패 (stdio 시나리오만 영향)"
  if [[ ! -x "$OPA_BIN" ]]; then
    mkdir -p "$(dirname "$OPA_BIN")"
    curl -sSL -o "$OPA_BIN" https://openpolicyagent.org/downloads/v1.20.2/opa_linux_amd64_static
    chmod +x "$OPA_BIN"
  fi
  log "setup 완료"
}

cmd_up() {
  preflight
  ensure_keys
  load_env
  common_env
  schema

  start_one opa "$OPA_BIN" run --server --addr=127.0.0.1:8181 \
    --set=decision_logs.console=false --log-level=error "$LAB_DIR/opa"
  wait_http "http://127.0.0.1:8181/health" "OPA"

  start_one mock-mcp env MCP_TRANSPORT=streamable-http MCP_PORT=9000 \
    MCP_CATALOG_MODE="${MCP_CATALOG_MODE:-normal}" EFFECT_LOG="$EFFECT_LOG" \
    MCP_BIND_ADDR=127.0.0.1 "$VENV/bin/python" "$LAB_DIR/mock_server/server.py"
  wait_http "http://127.0.0.1:9000/health" "mock MCP"

  start_one gateway env AGENT_JWT_PUBLIC_KEY="$AGENT_JWT_PUBLIC_KEY" \
    "$VENV/bin/uvicorn" app.main:app --host "$BIND" --port 8080 --app-dir "$LAB_DIR/gateway"
  wait_http "http://127.0.0.1:8080/api/health" "Gateway"

  # legacy SSE ingress. 전송이 달라도 같은 정책 경로로 수렴하는지를 acceptance가
  # 확인하므로, 이것이 없으면 전송 호환성 검증이 통째로 빠진다.
  start_one gateway-sse env AGENT_JWT_PUBLIC_KEY="$AGENT_JWT_PUBLIC_KEY" \
    SSE_BIND_ADDR=127.0.0.1 SSE_PORT=8081 \
    "$VENV/bin/python" -m app.sse_entry
  sleep 1

  start_one agent env AGENT_JWT_PRIVATE_KEY="$AGENT_JWT_PRIVATE_KEY" \
    AGENT_JWT_PUBLIC_KEY="$AGENT_JWT_PUBLIC_KEY" \
    "$VENV/bin/uvicorn" app.agent_service:app --host "$BIND" --port 8000 --app-dir "$LAB_DIR/gateway"
  wait_http "http://127.0.0.1:8000/health" "Agent Service"

  log "Console  http://127.0.0.1:8000"
  log "Gateway  http://127.0.0.1:8080/api/health"
}

cmd_down() {
  for name in agent gateway-sse gateway mock-mcp opa; do stop_one "$name"; done
}

cmd_status() {
  local pf
  for name in opa mock-mcp gateway gateway-sse agent; do
    pf="$(pidfile "$name")"
    if [[ -f "$pf" ]] && kill -0 "$(cat "$pf")" 2>/dev/null; then
      printf '%-10s running (pid %s)\n' "$name" "$(cat "$pf")"
    else
      printf '%-10s stopped\n' "$name"
    fi
  done
}

cmd_logs() { tail -n "${1:-60}" "$RUN_DIR"/*.log; }

cmd_reset() {
  cmd_down
  PGPASSWORD="$PGPASSWORD_VALUE" psql -q -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d postgres \
    -c "DROP DATABASE IF EXISTS $PGDATABASE WITH (FORCE)" \
    -c "CREATE DATABASE $PGDATABASE OWNER $PGUSER"
  rm -f "$RUN_DIR/upstream-effects.jsonl"
  log "데이터베이스 초기화 완료"
}

cmd_test() {
  load_env
  common_env
  local failed=0
  # acceptance는 기본 모델(mock)의 결정론적 제안을 전제로 판정을 대조한다.
  # provider 모드로 띄운 스택에 그대로 돌리면 "정책이 틀렸다"가 아니라 "모델이
  # 다른 도구를 골랐다"로 실패하고, 그 둘은 화면에서 구분되지 않는다.
  if curl -fsS "$AGENT_SERVICE_URL/api/readiness" 2>/dev/null       | grep -q '"mode": *"provider"'; then
    die "Agent Service가 provider 모드입니다. acceptance는 MODEL_MODE=mock으로 다시 띄운 뒤 실행하세요 (./run-native.sh restart)."
  fi
  log "Rego 단위 시험"
  "$OPA_BIN" test "$LAB_DIR/opa" 2>&1 | tail -3 || failed=1
  for suite in acceptance agent_acceptance runtime_acceptance; do
    log "$suite"
    ( cd "$LAB_DIR/gateway" && AGENT_JWT_PRIVATE_KEY="$AGENT_JWT_PRIVATE_KEY"         "$VENV/bin/python" -m "app.$suite" ) > "$LAB_DIR/reports/$suite.json" 2>"$RUN_DIR/$suite.err" || failed=1
    # 실패를 "failures: None"으로 접지 않는다. 결과 파일이 JSON이 아니면 그것은
    # 통과가 아니라 스위트가 예외로 죽었다는 뜻이고, stderr에 이유가 있다.
    "$VENV/bin/python" - "$LAB_DIR/reports/$suite.json" "$RUN_DIR/$suite.err" <<'PYEOF' || failed=1
import json, sys
try:
    report = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception as exc:
    print("  결과 파일을 읽을 수 없습니다: %s" % exc)
    print("  " + (open(sys.argv[2], encoding="utf-8", errors="replace").read().strip().splitlines() or ["(stderr 없음)"])[-1][:200])
    raise SystemExit(1)
summary = report.get("summary") or {}
passed, failed = summary.get("passed"), summary.get("failed")
if passed is None:
    print("  status=%s %s" % (report.get("status"), str(report.get("error"))[:160]))
    raise SystemExit(1)
print("  통과 %s · 실패 %s" % (passed, failed))
for case in report.get("checks", []) + report.get("cases", []):
    if case.get("status") == "FAIL":
        print("   FAIL %s %s" % (case.get("name"), str(case.get("details"))[:120]))
raise SystemExit(1 if failed else 0)
PYEOF
  done
  if [[ $failed -ne 0 ]]; then
    log "검증 실패. reports/ 와 $RUN_DIR/*.err 를 보세요."
    return 1
  fi
  log "전체 통과"
}

# 이 호스트에서 설치된 서버의 계약을 승인본으로 올린다.
#
# 왜 필요한가: mcp-server-time 같은 pip 설치형 stdio 서버는 도구 Schema가 그
# 서버의 의존성 버전에 따라 달라진다. db/init.sql에 박힌 해시는 어느 한 빌드의
# 값이라, 다른 호스트에서는 정당한 설치도 MCP-CATALOG-001 드리프트로 잡힌다.
#
# 자동으로 하지 않는 이유: 기동할 때마다 관측값을 승인하면 계약 고정이라는 통제
# 자체가 사라진다. 사람이 무엇이 바뀌었는지 보고 누르는 행위여야 한다.
cmd_baseline() {
  load_env
  common_env
  local token
  token="$(curl -fsS -X POST http://127.0.0.1:8080/api/session     -H 'content-type: application/json'     -d "{\"email\":\"kkg@bob.local\",\"password\":\"${MOCK_SSO_PASSWORD}\"}"     | "$VENV/bin/python" -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"
  for server in "${@:-mock-stdio}"; do
    log "계약 재승인: $server"
    curl -fsS -X POST "http://127.0.0.1:8080/api/registry/${server}/approve-contract"       -H "authorization: Bearer $token" -H 'content-type: application/json'       -d '{"note":"native 실행 환경에서 설치된 빌드의 계약을 기준선으로 승인"}'       | "$VENV/bin/python" -m json.tool
  done
}

case "${1:-up}" in
  setup) cmd_setup ;;
  baseline) shift; cmd_baseline "$@" ;;
  up) cmd_up ;;
  down) cmd_down ;;
  restart) cmd_down; cmd_up ;;
  status) cmd_status ;;
  logs) shift; cmd_logs "$@" ;;
  reset) cmd_reset ;;
  test) cmd_test ;;
  *) echo "사용법: $0 {setup|up|down|restart|status|logs|reset|baseline|test}" >&2; exit 2 ;;
esac
