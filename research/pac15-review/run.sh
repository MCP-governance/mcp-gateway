#!/usr/bin/env bash
# Start the teammate's draft and the reviewed copy side by side in the Gateway's OPA
# image, then send both the same 300 inputs. Nothing here touches the Gateway itself.
set -euo pipefail
cd "$(dirname "$0")"
IMAGE=openpolicyagent/opa:1.20.2-static
cleanup() { docker rm -f pac15-review-original pac15-review-fixed >/dev/null 2>&1 || true; }
trap cleanup EXIT
cleanup
docker run -d --name pac15-review-original -p 127.0.0.1:18291:8181 -v "$PWD/original/policy:/policy:ro" \
  "$IMAGE" run --server --addr=0.0.0.0:8181 /policy >/dev/null
docker run -d --name pac15-review-fixed -p 127.0.0.1:18292:8181 -v "$PWD/fixed/policy:/policy:ro" \
  "$IMAGE" run --server --addr=0.0.0.0:8181 /policy >/dev/null
for port in 18291 18292; do
  for _ in $(seq 1 30); do curl -fsS "127.0.0.1:$port/health" >/dev/null 2>&1 && break; sleep 1; done
done
status=0
for variant in original:18291 fixed:18292; do
  echo "######## ${variant%%:*}"
  OPA="http://127.0.0.1:${variant##*:}" python3 pac15_suite.py all || status=1
done
exit $status
