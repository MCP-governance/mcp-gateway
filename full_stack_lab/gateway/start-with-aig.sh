#!/usr/bin/env bash
set -euo pipefail
pids=()

stop() {
  trap - INT TERM
  kill -TERM "${pids[@]}" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap 'stop; exit 0' INT TERM

(cd /aig-web && exec ./start.sh) &
pids+=("$!")
for _ in {1..60}; do
  if curl -fsS http://127.0.0.1:8088/ >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
if ! curl -fsS http://127.0.0.1:8088/ >/dev/null; then
  echo "A.I.G Web가 60초 안에 준비되지 않았습니다." >&2
  stop
  exit 1
fi
(cd /app && exec ./start_agent_container.sh) &
pids+=("$!")
gosu appuser:appuser /opt/gateway-venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8080 &
pids+=("$!")

# Any failed component must restart the whole combined container.
wait -n "${pids[@]}" || true
echo "Gateway 또는 A.I.G 프로세스가 종료되어 컨테이너를 재시작합니다." >&2
stop
exit 1
