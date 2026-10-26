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
docker compose exec -T gateway python - <<'PY' >> "$out/configuration.txt"
import json
from app import core, pac

profile = pac.capabilities()["execution_profile"]
assert profile["production_controls"] is True, "Production controls must remain enabled"
assert core.RATE_LIMIT_CALLS == profile["limits"]["max_calls"] == 10000, "Call ceilings disagree"
assert core.CONCURRENCY_LIMIT == profile["limits"]["max_concurrency"] == 500, "Concurrency ceilings disagree"
print(json.dumps({"execution_profile": profile}))
PY
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
  if ! python3 - "$out" "$scenario" <<'PY'
import json
import sys
from pathlib import Path

output, scenario = Path(sys.argv[1]), sys.argv[2]
result = json.loads((output / f"{scenario}-timings.json").read_text())
with (output / f"{scenario}.md").open("a") as summary:
    summary.write("\n| decision | policy_id | n |\n| --- | --- | ---: |\n")
    for row in result["policies"]:
        summary.write(f"| {row['decision']} | {row['policy_id']} | {row['n']} |\n")
assert sum(row["n"] for row in result["policies"]) == result["ledger_rows"], "Missing policy counts"
if sys.argv[2] != "list":
    actual = json.loads((output / f"{scenario}-counts.json").read_text())["requests"]
    assert actual > 0 and result["ledger_rows"] == actual, "Ledger count differs from measured requests"
    assert sum(row["n"] for row in result["verdicts"]) == actual, "Missing total timings"
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
