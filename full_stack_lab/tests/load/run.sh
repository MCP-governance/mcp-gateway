#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
[[ "${GITHUB_ACTIONS:-}" == true && "${RUNNER_ENVIRONMENT:-}" == github-hosted ]] || {
  echo 'This load runner requires a disposable GitHub-hosted Actions runner.' >&2; exit 1;
}
K6_IMAGE='grafana/k6:1.3.0@sha256:3ddc8b1a33a2c3d8edc6e99b6a762ae36cba08788463458f5e6a7703e14eb77d'
out="$PWD/reports/load"
mkdir -p "$out"
printf '%s\n' "$K6_IMAGE" > "$out/k6-image.txt"
printf 'revision=%s\nRATE_LIMIT_CALLS=10000\nCONCURRENCY_LIMIT=500\n' "${GITHUB_SHA:-unknown}" > "$out/configuration.txt"
printf 'scenario\tstarted_utc\tended_utc\tk6_exit\n' > "$out/windows.tsv"
docker pull "$K6_IMAGE"
docker run --rm --network none -v "$PWD/tests/load:/s:ro" "$K6_IMAGE" inspect /s/load.js > "$out/inspect.json"
# Join the workstation's office network; neither upstream tools nor data are reachable directly.
ws="$(docker compose ps -q ws-ysg)"
network="$(docker inspect --format '{{range .NetworkSettings.Networks}}{{.NetworkID}}{{end}}' "$ws")"
test -n "$network"
failed=0
for scenario in list allow deny; do
  started="$(date -u +%Y-%m-%dT%H:%M:%S.%NZ)"
  rc=0
  docker run --rm --name mint-k6 --network "$network" --user "$(id -u):$(id -g)" \
    --cap-drop ALL --security-opt no-new-privileges \
    -v "$PWD/tests/load:/s:ro" -v "$out:/out" -e LOAD_CASE="$scenario" \
    "$K6_IMAGE" run --summary-export "/out/$scenario.json" /s/load.js || rc=$?
  ended="$(date -u +%Y-%m-%dT%H:%M:%S.%NZ)"
  printf '%s\t%s\t%s\t%s\n' "$scenario" "$started" "$ended" "$rc" >> "$out/windows.tsv"
  [[ "$rc" == 0 ]] || failed=1
  if ! docker compose exec -T db psql -X -qAt -U mcp -d mcp_governance \
    -v started="$started" -v ended="$ended" -v scenario="$scenario" \
    < tests/load/timings.sql > "$out/$scenario-timings.json"; then failed=1; fi
  if ! python3 - "$out/$scenario-timings.json" "$scenario" <<'PY'
import json
import sys

with open(sys.argv[1]) as source:
    result = json.load(source)
if sys.argv[2] != "list":
    assert result["ledger_rows"] == 3000, "Expected 3000 scenario ledger rows"
    assert sum(row["n"] for row in result["verdicts"]) == 3000, "Missing total timings"
PY
  then failed=1; fi
  # Only counts are persisted: raw logs can contain request data or credentials.
  if logs="$(docker logs --since "$started" --until "$ended" "$(docker compose ps -q gateway)" 2>&1)"; then
    waits="$(printf '%s\n' "$logs" | grep -Eic 'pool.*(wait|waiting|exhaust)|waiting.*pool|couldn.t get a connection' || true)"
    timeouts="$(printf '%s\n' "$logs" | grep -c 'PoolTimeout' || true)"
    printf 'pool_wait_matching_lines=%s\nPoolTimeout_matching_lines=%s\n' "$waits" "$timeouts" > "$out/$scenario-pool.txt"
  else
    failed=1
    printf 'Gateway log collection failed\n' > "$out/$scenario-pool.txt"
  fi
  unset logs
done
exit "$failed"
