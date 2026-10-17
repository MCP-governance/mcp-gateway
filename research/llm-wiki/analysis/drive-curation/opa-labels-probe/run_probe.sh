#!/usr/bin/env bash
# 일회성 OPA 서버(결정 로그 콘솔 출력)를 띄워 규칙 labels가 결정 로그에 남는지 본다. compose 스택과 무관하다.
set -u
IMAGE="${1:?image tag}"
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/out-$(echo "$IMAGE" | tr '/:' '__')"
mkdir -p "$OUT"
NAME="opa-labels-probe-$$"
trap 'docker rm -f "$NAME" >/dev/null 2>&1' EXIT
docker run --rm -d --name "$NAME" -p 127.0.0.1:18181:8181 -v "$HERE/policy:/policy:ro" "$IMAGE" \
  run --server --addr 0.0.0.0:8181 --set decision_logs.console=true --log-level=info /policy >/dev/null
for i in $(seq 1 30); do curl -sf http://127.0.0.1:18181/health >/dev/null && break; sleep 0.5; done
python3 - "$HERE/cases.json" "$OUT" <<'PY'
import json, sys, urllib.request
cases = json.load(open(sys.argv[1]))
for c in cases:
    req = urllib.request.Request('http://127.0.0.1:18181/v1/data/' + c['path'], data=json.dumps({'input': c['input']}).encode(), headers={'Content-Type': 'application/json'}, method='POST')
    body = urllib.request.urlopen(req).read().decode()
    open(f"{sys.argv[2]}/response-{c['name']}.json", 'w').write(body + '\n')
    print(c['name'], body.strip())
PY
sleep 1
docker logs "$NAME" 2>&1 | grep '"decision_id"' > "$OUT/decision-log-events.jsonl"
docker run --rm -v "$HERE/policy:/policy:ro" "$IMAGE" version | head -3 > "$OUT/opa-version.txt"
docker run --rm -v "$HERE/policy:/policy:ro" "$IMAGE" test /policy -v > "$OUT/opa-test.txt" 2>&1
echo "events: $(wc -l < "$OUT/decision-log-events.jsonl")"
