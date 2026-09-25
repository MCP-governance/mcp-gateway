#!/usr/bin/env bash
# Security regression for the v2 lab: the guarantees that live outside the policy
# engine and outside a single request - network separation, loopback-only ports,
# token-gated read APIs, the Console's role boundary, logout taking effect at once,
# fail-closed when OPA or an upstream server is gone, tamper evidence of the audit
# chain, and the MCP contracts still matching the lock.
#
#   tests/security_regression.sh            (./console.sh test runs it)
#
# It stops and restarts OPA and one MCP server, and briefly lifts the audit table's
# append-only trigger to prove tampering is detected. Every step restores itself
# (trap), so a failed run does not leave the lab degraded.
set -uo pipefail
cd "$(dirname "$0")/.."
CONSOLE="${LAB_CONSOLE_URL:-http://127.0.0.1:8000}"
GATEWAY="${LAB_GATEWAY_URL:-http://127.0.0.1:8080}"
PASS=0
FAIL=0
ok() { PASS=$((PASS + 1)); printf 'PASS  %s\n' "$1"; }
bad() { FAIL=$((FAIL + 1)); printf 'FAIL  %s — %s\n' "$1" "$2"; }
expect() { if [[ "$2" == "$3" ]]; then ok "$1"; else bad "$1" "기대 '$3', 실제 '$2'"; fi; }

token() {
  curl -fsS -X POST "$CONSOLE/auth/mock-login" -H 'content-type: application/json' \
    -d "{\"email\":\"$1\",\"password\":\"${MOCK_SSO_PASSWORD:-test-password}\"}" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])'
}
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }
psql_q() { docker compose exec -T db psql -U mcp -d mcp_governance -At -v ON_ERROR_STOP=1 -c "$1"; }
wait_healthy() {
  for _ in $(seq 1 45); do
    [[ "$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -q "$1")" 2>/dev/null)" == healthy ]] && return 0
    sleep 2
  done
  return 1
}
# One call through the Gateway's enforced path, as <principal>: "decision policy executed"
PROBE='import asyncio, json, sys
from app import db
from app.core import execute_call
async def main():
    out = await execute_call({"server_id": sys.argv[2], "tool": sys.argv[3], "arguments": json.loads(sys.argv[4]),
                              "user_token": sys.argv[1], "client": {"agent": "security-regression"}})
    print(out["decision"], out["policy_id"], out["upstream_executed"])
    await db.close()
asyncio.run(main())'
probe() { docker compose exec -T gateway python -c "$PROBE" "$@" 2>/dev/null | tail -1; }
reachable() {  # reachable <service> <host> <port> -> open|closed
  docker compose exec -T "$1" python -c "
import socket
s = socket.socket(); s.settimeout(2)
try:
    s.connect(('$2', $3)); print('open')
except Exception:
    print('closed')" 2>/dev/null | tail -1
}
HANDBOOK='{"repo_path": "/repos/handbook", "max_count": 1}'

echo "── 망 분리: 직원 PC(office)에서 닿는 곳 ──"
expect "ws-ysg → gateway:8080 (MCP·IdP 경유)" "$(reachable ws-ysg gateway 8080)" open
expect "ws-ysg → agent-service:8000 (IdP)" "$(reachable ws-ysg agent-service 8000)" open
for target in mcp-filesystem:8000 mcp-postgres:8000 corp-db:5432 corp-git:3000 db:5432 opa:8181 external-web:80; do
  expect "ws-ysg ↛ $target" "$(reachable ws-ysg "${target%%:*}" "${target##*:}")" closed
done
# ws-nkk carries a shadow config pointing straight at mcp-filesystem: it must not work
expect "ws-nkk 섀도 설정(fs-direct) ↛ mcp-filesystem:8000" "$(reachable ws-nkk mcp-filesystem 8000)" closed
expect "mcp-memory ↛ corp-db:5432 (tools망 서버의 회사 DB 접근)" "$(reachable mcp-memory corp-db 5432)" closed
# The Console holds every user's session; it must not have a path to the tools either.
expect "agent-service ↛ mcp-filesystem:8000 (Console은 도구망 밖)" "$(reachable agent-service mcp-filesystem 8000)" closed
expect "gateway → mcp-filesystem:8000 (강제 경로만 도구망에)" "$(reachable gateway mcp-filesystem 8000)" open

echo "── 격리 워커의 검사 도구가 실제로 뜬다 ──"
# An intake request is only as good as the scanners behind it; a broken toolchain
# once turned every request into FAILED for days before anyone looked.
if [[ -n "$(docker compose ps -q intake-worker 2>/dev/null)" ]]; then
  for tool in "semgrep --version" "syft version" "trivy --version"; do
    if docker compose exec -T intake-worker sh -lc "$tool" >/dev/null 2>&1; then ok "intake-worker: $tool"; else bad "intake-worker: $tool" "실행 실패"; fi
  done
else
  bad "intake-worker 실행 중" "컨테이너가 없습니다"
fi

echo "── 호스트 게시 포트는 loopback에만 ──"
# A probe that crashes must not read as "nothing exposed": print "none" only on success.
exposed="$(docker compose ps --format json | python3 -c '
import json, sys
text = sys.stdin.read().strip()
rows = json.loads(text) if text.startswith("[") else [json.loads(line) for line in text.splitlines() if line]
published = [p for r in rows for p in (r.get("Publishers") or []) if p.get("PublishedPort")]
wide = [p["URL"] + ":" + str(p["PublishedPort"]) for p in published if p.get("URL") not in ("127.0.0.1", "::1")]
print(" ".join(wide) if wide else ("none" if published else "no-published-ports"))' || echo probe-error)"
expect "0.0.0.0에 게시된 포트 없음" "$exposed" none

echo "── Gateway 읽기 API는 토큰 필요 (직원 PC도 같은 망) ──"
for path in state registry policy/ledger policy/matrix monitor/summary supply-chain/coverage enforcement risk-catalog; do
  expect "GET /api/$path 무인증" "$(code "$GATEWAY/api/$path")" 401
done
expect "GET /api/health 무인증 (상태만)" "$(code "$GATEWAY/api/health")" 200

echo "── Console 역할 경계 ──"
EMP="$(token ysg@bob.local)"
for path in gw/registry gw/overview gw/termination/cases gw/policy/ledger gw/endpoint/inventory api/accounts approvals; do
  expect "직원 → /$path" "$(code "$CONSOLE/$path" -H "authorization: Bearer $EMP")" 403
done
others="$(curl -fsS "$CONSOLE/gw/activity?limit=500" -H "authorization: Bearer $EMP" \
  | python3 -c 'import json,sys; print(sum(1 for r in json.load(sys.stdin)["rows"] if r["who"] != "양승권"))')"
expect "직원 활동 로그에 다른 사람의 호출 없음" "$others" 0

echo "── 로그아웃은 다음 요청부터 ──"
T="$(token jwj@bob.local)"
expect "로그아웃 전 /gw/activity" "$(code "$CONSOLE/gw/activity?limit=1" -H "authorization: Bearer $T")" 200
curl -fsS -X POST "$CONSOLE/auth/logout" -H "authorization: Bearer $T" >/dev/null
expect "로그아웃 후 /gw/activity" "$(code "$CONSOLE/gw/activity?limit=1" -H "authorization: Bearer $T")" 401
expect "로그아웃 후 MCP ingress" "$(code -X POST "$GATEWAY/mcp/" -H "authorization: Bearer $T" \
  -H 'accept: application/json, text/event-stream' -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}')" 401

echo "── 실패 안전: 정책 엔진이 없으면 차단 ──"
trap 'docker compose start opa mcp-git >/dev/null 2>&1' EXIT
docker compose stop opa >/dev/null 2>&1
expect "OPA 정지 중 호출" "$(probe emp-ysg git git_log "$HANDBOOK")" "Block P-CONTROL-FAIL-CLOSED False"
docker compose start opa >/dev/null 2>&1 && wait_healthy opa
expect "OPA 복구 후 호출" "$(probe emp-ysg git git_log "$HANDBOOK")" "Allow P-333-ALLOW-001 True"

echo "── 실패 안전: 상위 서버가 없으면 실행되지 않음 ──"
docker compose stop mcp-git >/dev/null 2>&1
down="$(probe emp-ysg git git_log "$HANDBOOK")"
expect "mcp-git 정지 중 호출은 실행되지 않음" "${down##* }" False
docker compose start mcp-git >/dev/null 2>&1 && wait_healthy mcp-git
curl -fsS -X POST "$GATEWAY/api/catalog/refresh" -H "authorization: Bearer $(token kkg@bob.local)" >/dev/null
expect "mcp-git 복구 후 호출" "$(probe emp-ysg git git_log "$HANDBOOK")" "Allow P-333-ALLOW-001 True"
trap - EXIT

echo "── 감사 기록 변조는 드러난다 ──"
ADMIN="$(token kkg@bob.local)"
verify() { curl -fsS "$GATEWAY/api/audit/verify" -H "authorization: Bearer $ADMIN" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["intact"], d.get("broken_at"))'; }
row="$(psql_q "SELECT max(id) FROM decisions")"
if psql_q "UPDATE decisions SET reason = reason WHERE id = $row" >/dev/null 2>&1; then
  bad "decisions 수정 거부(append-only)" "UPDATE가 허용됨"
else
  ok "decisions 수정 거부(append-only 트리거)"
fi
restore_row() {
  psql_q "BEGIN; ALTER TABLE decisions DISABLE TRIGGER decisions_append_only;
          UPDATE decisions SET reason = left(reason, length(reason) - 8) WHERE id = $row AND reason LIKE '%[TAMPER]';
          ALTER TABLE decisions ENABLE TRIGGER decisions_append_only; COMMIT;" >/dev/null
}
trap restore_row EXIT
psql_q "BEGIN; ALTER TABLE decisions DISABLE TRIGGER decisions_append_only;
        UPDATE decisions SET reason = reason || '[TAMPER]' WHERE id = $row;
        ALTER TABLE decisions ENABLE TRIGGER decisions_append_only; COMMIT;" >/dev/null
expect "변조된 행을 검증이 지목" "$(verify)" "False $row"
restore_row
trap - EXIT
expect "원복 후 체인 정상" "$(verify | cut -d' ' -f1)" True

echo "── MCP 계약이 잠금과 같다 ──"
docker compose exec -T gateway python -m app.registry lock > /tmp/contracts.now.$$ 2>/dev/null
if python3 tests/contracts_check.py registry/contracts.lock.json /tmp/contracts.now.$$; then ok "계약 잠금 일치"; else bad "계약 잠금 일치" "위 변경 목록 참고"; fi
rm -f /tmp/contracts.now.$$

echo
echo "security regression: PASS $PASS · FAIL $FAIL"
[[ $FAIL -eq 0 ]]
