"""End-to-end check of the paper's judgment procedure on real relationships.

    python3 tests/termination_flow.py            (./console.sh test runs it)

UR-GITEA-DEV  provider-operated, credential disclosed, the organisation administers
              the downstream system  -> collectable evidence -> T1 after revocation
UR-EMAIL-ASSIST provider-operated, credential NOT disclosed -> C1 unmet -> T3,
              and closing a T3 case without a named risk acceptance is refused

Run only on a disposable lab volume: D-123 tombstones deliberately prevent restoring the same server.

D-156 token/resource-server C3/C4 cases supplement this live flow in
resource_residual_check.py and resource_residual_pg_check.py; its assertions stay unchanged.
"""
import atexit
import os
import json
import subprocess
import sys
import urllib.error
import urllib.request

GATEWAY = os.getenv("LAB_GATEWAY_URL", "http://127.0.0.1:8080")


def token() -> str:
    req = urllib.request.Request(os.getenv("LAB_CONSOLE_URL", "http://127.0.0.1:8000") + "/auth/mock-login", method="POST",
                                 data=json.dumps({"email": "kkg@bob.local", "password": "test-password"}).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))["access_token"]


if os.getenv("TERMINATION_DISPOSABLE_LAB") != "1":
    raise SystemExit("폐기 목록이 영구 기록됩니다. 격리한 일회용 랩에서만 TERMINATION_DISPOSABLE_LAB=1로 실행하세요.")

TOKEN = token()


def api(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(GATEWAY + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


failures = []


def managed_settings(excluded: str | None = None) -> None:
    for workstation in ("ws-ysg", "ws-jwj", "ws-pse", "ws-nkk"):
        command = ["docker", "compose", "exec", "-T", "--user", "root", workstation, "python3",
                   "/opt/office/managed/render.py", "/opt/office/catalog.toml", "/opt/office/rendered", "--install",
                   # D-124: a managed URL must be HTTPS; the isolated lab address is the one allowed exception.
                   "--gateway-url", "http://gateway:8080/mcp"]
        if excluded:
            command.extend(["--exclude-server", excluded])
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["docker", "compose", "exec", "-T", workstation, "sh", "-c",
            'ENDPOINT_ID="$WORKSTATION_ID" ENDPOINT_GATEWAY_URL="$GATEWAY_URL" '
            'ENDPOINT_CONFIG_PATHS="$HOME:/etc/claude-code:/etc/codex:/etc/gemini-cli:/etc/opencode" '
            'python3 /opt/office/endpoint_agent.py --once'], check=True, stdout=subprocess.DEVNULL)


atexit.register(managed_settings)


def check(condition: bool, name: str, detail: str = "") -> None:
    print(("PASS " if condition else "FAIL ") + name + (f" — {detail}" if detail else ""), flush=True)
    if not condition:
        failures.append(name)


def open_case(rel: str) -> dict:
    status, body = api("POST", "/api/termination/cases", {"relationship_id": rel, "reason": "계약 종료에 따른 이용 중단 (자동 검증)"})
    if status == 409:
        raise SystemExit("기존 종료 케이스를 변경하지 않습니다. 빈 일회용 랩을 사용하세요.")
    check(status == 201, f"{rel}: case opened", str(status))
    return body


# ── readiness (drill) ─────────────────────────────────────────────────────────
status, rels = api("GET", "/api/termination/relationships")
ready = {r["id"]: r["readiness"]["best_attainable_grade"] for r in rels.get("relationships", [])}
check(ready.get("UR-GITEA-DEV") == "T1", "drill: gitea best attainable T1", str(ready.get("UR-GITEA-DEV")))
check(ready.get("UR-EMAIL-ASSIST") == "T3", "drill: email best attainable T3", str(ready.get("UR-EMAIL-ASSIST")))

# ── UR-GITEA-DEV → T1 ─────────────────────────────────────────────────────────
case = open_case("UR-GITEA-DEV")
case_id = case["case"]["id"]
kinds = {t["kind"] for t in case["targets"]}
check({"gateway-route", "server-held-credential"} <= kinds, "gitea: population seeded", str(sorted(kinds)))
status, graded = api("POST", f"/api/termination/cases/{case_id}/assess")
check(graded["case"]["grade"] == "T3", "gitea: before any evidence the grade is T3", graded["case"]["grade"])
status, collected = api("POST", f"/api/termination/cases/{case_id}/collect", {"kinds": ["gateway", "endpoint", "credentials", "session"]})
denials = [e for e in collected.get("collected", []) if e["kind"] == "gateway-denial"]
check(denials and all(e["detail"]["blocked"] and not e["detail"].get("upstream_attempted") and (
    e["detail"]["policy_id"] == "MCP-DECOMM-001" or (
        e["detail"]["policy_id"] == "P-INPUT-001"
        and e["detail"].get("identity_status") in {"deleted", "disabled", "inactive", "suspended"})) for e in denials),
      "gitea: every historical caller is refused before dispatch with lifecycle or identity state evidence",
      f"{len(denials)} probes")
creds = [e for e in collected.get("collected", []) if e["kind"] == "credential-check"]
check(creds and creds[0]["detail"]["present"] is True, "gitea: server-held token still exists after cutover (E3)")
status, graded = api("POST", f"/api/termination/cases/{case_id}/assess")
check(graded["case"]["grade"] == "T2", "gitea: cutover alone is T2 (provider credential outstanding)", graded["case"]["grade"])
cred_target = next(t for t in graded["targets"] if t["kind"] == "server-held-credential")
status, revoked = api("POST", f"/api/termination/targets/{cred_target['id']}/revoke-credential")
after = [e for e in revoked.get("collected", []) if e["kind"] == "credential-check"]
check(status == 200 and after and after[0]["detail"]["present"] is False, "gitea: organisation revoked the token in Gitea and verified it", str(status))
status, graded = api("POST", f"/api/termination/cases/{case_id}/assess")
check(graded["case"]["grade"] == "T2", "gitea: actual endpoint configuration residue prevents T1", graded["case"]["grade"])
managed_settings("gitea")
status, collected = api("POST", f"/api/termination/cases/{case_id}/collect", {"kinds": ["endpoint"]})
removed = [e for e in collected.get("collected", []) if e["kind"] == "endpoint-inventory"]
check(removed and all(e["detail"]["absent"] for e in removed), "gitea: real managed settings removed and endpoint observer confirms absence")
status, graded = api("POST", f"/api/termination/cases/{case_id}/assess")
check(graded["case"]["grade"] == "T1", "gitea: T1 after revocation with state evidence", f"{graded['case']['grade']} {graded['case']['criteria'].get('notes')}")
credential_side = next(t for t in graded["targets"] if t["kind"] == "server-held-credential")["criteria"].get("provider_side", {})
check(credential_side.get("state") in {"rejected", "unverified"}, "gitea: the resource server never accepts the revoked token; without a copy to show it the state is unverified",
      str(credential_side))
check(graded["activity"].get("unknown") == 0 and "straddled" in graded["activity"], "gitea: no call is left with an unknown outcome and in-flight calls are counted apart",
      str(graded["activity"]))
status, unsent = api("GET", "/api/dispatch-intents")
check(status == 200 and isinstance(unsent.get("rows"), list), "dispatch intents are listed for administrators", str(status))
weak = [e for e in graded["evidence"] if e["kind"] == "revocation-response"]
check(weak and all(not e["meaning"]["state"] for e in weak), "gitea: the DELETE response is recorded as request-only evidence")
status, closed = api("POST", f"/api/termination/cases/{case_id}/close", {"note": "T1 확인 후 종결"})
check(status == 200 and closed["case"]["status"] == "CLOSED", "gitea: T1 case closes without risk acceptance")
status, report = api("GET", f"/api/termination/cases/{case_id}/report")
check(status == 200 and report["grade"] == "T1" and len(report["criteria"]) == 4, "gitea: judgment report")

# ── UR-EMAIL-ASSIST → T3 ──────────────────────────────────────────────────────
case = open_case("UR-EMAIL-ASSIST")
case_id = case["case"]["id"]
check(any(t["status"] == "UNVERIFIABLE" for t in case["targets"]), "email: undisclosed credential is an UNVERIFIABLE target")
api("POST", f"/api/termination/cases/{case_id}/collect", {"kinds": ["gateway", "endpoint"]})
status, graded = api("POST", f"/api/termination/cases/{case_id}/assess")
check(graded["case"]["grade"] == "T3", "email: grade T3 (C1 unmet)", graded["case"]["grade"])
status, refused = api("POST", f"/api/termination/cases/{case_id}/close", {"note": "제공자 미회신"})
check(status == 409, "email: T3 does not close without risk acceptance", str(status))
status, disclosure = api("GET", f"/api/termination/cases/{case_id}/disclosure-request")
check(status == 200 and "보유 자격 목록" in disclosure.get("markdown", ""), "email: disclosure request letter")
status, closed = api("POST", f"/api/termination/cases/{case_id}/close",
                     {"note": "제공자 미회신", "risk_acceptance": "CISO 승인 — 잔존 위험 수용 (자동 검증)"})
check(status == 200 and closed["case"]["risk_accepted_by"], "email: T3 closes with a named risk acceptance")

# D-123: restoring a database must not restore a disposed identity.
for server in ("gitea", "email"):
    status, _ = api("POST", f"/api/lab/restore/{server}")
    check(status == 409, f"disposed {server} cannot be restored")
status, health = api("GET", "/api/health")
print("mcp servers ready:", health.get("mcp_servers", {}).get("ready"), "/", health.get("mcp_servers", {}).get("total"))

print(f"\n{'OK' if not failures else 'FAILED'}: {len(failures)} failure(s)")
sys.exit(1 if failures else 0)
