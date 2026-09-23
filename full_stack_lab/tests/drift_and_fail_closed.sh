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

# upstream MCP에 host port가 없다는 사실이 이 실습의 경로 통제 절반이다.
#
# 이전 판은 `docker compose port`의 출력이 비어 있지 않으면 노출로 봤다. 그런데
# Compose v5는 매핑이 없는 포트에 대해 빈 문자열이 아니라 `invalid IP:0`을
# stdout으로 낸다. 그래서 실제로는 노출되지 않았는데 FAIL이 났다. 거짓 실패를
# 내는 보안 회귀 검사는 결국 무시되거나 지워진다.
#
# 반대 방향이 더 위험하다. 미래의 Compose가 오류에 아무것도 출력하지 않으면
# 진짜 노출을 못 잡는다. 그래서 두 가지를 같이 본다: (1) 출력이 실제 host:port
# 모양인가, (2) 컨테이너에 게시된 HostPort 바인딩이 있는가.
published="$(docker compose port mock-http-mcp 9000 2>/dev/null |
  grep -Eo '^\[?[0-9a-fA-F.:]+\]?:[0-9]+$' || true)"

# docker inspect가 정본이다. HostPort가 붙어 있으면 그것이 노출이다.
container="$(docker compose ps -q mock-http-mcp 2>/dev/null | head -1)"
bindings=""
if [[ -n "$container" ]]; then
  template='{{range $p, $conf := .NetworkSettings.Ports}}{{range $conf}}{{$p}}={{.HostIp}}:{{.HostPort}} {{end}}{{end}}'
  bindings="$(docker inspect -f "$template" "$container" 2>/dev/null | tr -d '[:space:]')"
fi

if [[ -n "$published" || -n "$bindings" ]]; then
  echo "FAIL mock MCP is exposed to the host (port=${published:-none} bindings=${bindings:-none})" >&2
  exit 1
fi
echo "PASS upstream MCP has no host port"

# Published UIs stay on host loopback. The Agent cannot resolve the upstream
# service name, while the Gateway can: this is the actual Compose trust path.
python3 - <<'PY'
import json
import subprocess

for service in ("gateway", "agent-service", "jaeger"):
    container = subprocess.check_output(["docker", "compose", "ps", "-q", service], text=True).strip()
    ports = json.loads(subprocess.check_output(
        ["docker", "inspect", "--format", "{{json .NetworkSettings.Ports}}", container], text=True))
    hosts = [binding["HostIp"] for bindings in ports.values() if bindings for binding in bindings]
    if not hosts or any(host != "127.0.0.1" for host in hosts):
        raise SystemExit(f"FAIL {service} published outside loopback: {hosts}")
print("PASS published APIs are loopback-only")
PY
curl -fsS --max-time 3 http://127.0.0.1:16686/ >/dev/null
echo "PASS Jaeger UI is reachable on loopback"

# Only a resolver miss proves isolation. A stopped container or a missing
# interpreter must fail this check instead of passing it.
docker compose exec -T agent-service python -c '
import socket, sys
try:
    socket.getaddrinfo("mock-http-mcp", 9000)
except socket.gaierror:
    sys.exit(0)
sys.exit("FAIL Agent Service can resolve the upstream MCP")'
docker compose exec -T gateway python -c \
  'import socket; socket.getaddrinfo("mock-http-mcp", 9000)'
echo "PASS only Gateway resolves the upstream MCP"

# 격리 워커의 스캐너가 실제로 실행되는지.
#
# acceptance는 도입 요청을 VALIDATION_QUEUED까지만 확인하고 행을 지운다. 그래서
# 검증 스캔 경로 자체는 어떤 자동 검사도 타지 않았고, aig-mcp-scan이 끌어온
# mcp 2.x가 semgrep을 import 시점에 죽인 것을 아무도 몰랐다. 전체 검증을 돌리는
# 것은 네트워크와 시간을 쓰지만, 도구가 뜨는지 보는 것은 몇 초면 된다.
echo "[worker] scanner toolchain"
for probe in "semgrep --version" "syft version" "trivy --version" "aig-mcp-scan --help"; do
  if ! docker compose exec -T intake-worker sh -lc "$probe" >/dev/null 2>&1; then
    echo "FAIL intake worker cannot run: $probe" >&2
    docker compose exec -T intake-worker sh -lc "$probe" 2>&1 | tail -5 >&2
    exit 1
  fi
done
echo "PASS intake worker scanners run"
# The audit must fetch the release the gateway image installs, not a copy of it.
time_pin="$(sed -n 's/.*mcp-server-time==\([0-9.]*\).*/\1/p' gateway/Dockerfile)"
docker compose exec -T -e TIME_MCP_PIN="$time_pin" intake-worker python - <<'PY'
import os
import psycopg
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row
import intake_worker
from intake_worker import scan_target
from uuid import uuid4

with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as connection:
    target = scan_target(connection, {"target_kind": "server", "target_id": "mock-stdio"})
    assert target["ref"] == os.environ["TIME_MCP_PIN"] and target["source_ref"] == "mcp-server-time", target

    class StopBeforeNetwork(Exception):
        pass

    def inspect_before_clone(*args, **kwargs):
        assert connection.info.transaction_status == TransactionStatus.IDLE
        raise StopBeforeNetwork

    intake_worker.clone = inspect_before_clone
    try:
        intake_worker.run_mcp_scan(connection, {
            "id": uuid4(), "target_kind": "server", "target_id": "mock-stdio", "mode": "static",
        })
    except StopBeforeNetwork:
        pass
    else:
        raise AssertionError("expected to stop before network clone")
print("PASS Time MCP scan uses its pinned upstream release")
print("PASS scan releases registry lock before network work")
PY
echo "PASS security regression"
