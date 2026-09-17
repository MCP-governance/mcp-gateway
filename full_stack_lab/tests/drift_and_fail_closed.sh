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
echo "PASS security regression"
