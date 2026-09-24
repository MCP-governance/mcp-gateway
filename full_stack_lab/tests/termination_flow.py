"""End-to-end check of the paper's judgment procedure on real relationships.

    python3 tests/termination_flow.py            (./console.sh test runs it)

UR-GITEA-DEV  provider-operated, credential disclosed, the organisation administers
              the downstream system  -> collectable evidence -> T1 after revocation
UR-EMAIL-ASSIST provider-operated, credential NOT disclosed -> C1 unmet -> T3,
              and closing a T3 case without a named risk acceptance is refused

Both servers are restored afterwards (lab only) so the demo can run again.
"""
import json
import subprocess
import sys
import urllib.error
import urllib.request

GATEWAY = "http://127.0.0.1:8080"


def token() -> str:
    req = urllib.request.Request("http://127.0.0.1:8000/auth/mock-login", method="POST",
                                 data=json.dumps({"email": "kkg@bob.local", "password": "test-password"}).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))["access_token"]


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


def check(condition: bool, name: str, detail: str = "") -> None:
    print(("PASS " if condition else "FAIL ") + name + (f" — {detail}" if detail else ""), flush=True)
    if not condition:
        failures.append(name)


def open_case(rel: str) -> dict:
    status, body = api("POST", "/api/termination/cases", {"relationship_id": rel, "reason": "계약 종료에 따른 이용 중단 (자동 검증)"})
    if status == 409:  # a previous run left it open: restore and retry once
        server = {"UR-GITEA-DEV": "gitea", "UR-EMAIL-ASSIST": "email"}[rel]
        api("POST", f"/api/lab/restore/{server}")
        status, body = api("POST", "/api/termination/cases", {"relationship_id": rel, "reason": "계약 종료에 따른 이용 중단 (자동 검증)"})
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
check(denials and all(e["detail"]["blocked"] and e["detail"]["policy_id"] == "MCP-DECOMM-001" for e in denials),
      "gitea: every gateway path is refused as MCP-DECOMM-001", f"{len(denials)} probes")
creds = [e for e in collected.get("collected", []) if e["kind"] == "credential-check"]
check(creds and creds[0]["detail"]["present"] is True, "gitea: server-held token still exists after cutover (E3)")
status, graded = api("POST", f"/api/termination/cases/{case_id}/assess")
check(graded["case"]["grade"] == "T2", "gitea: cutover alone is T2 (provider credential outstanding)", graded["case"]["grade"])
cred_target = next(t for t in graded["targets"] if t["kind"] == "server-held-credential")
status, revoked = api("POST", f"/api/termination/targets/{cred_target['id']}/revoke-credential")
after = [e for e in revoked.get("collected", []) if e["kind"] == "credential-check"]
check(status == 200 and after and after[0]["detail"]["present"] is False, "gitea: organisation revoked the token in Gitea and verified it", str(status))
status, graded = api("POST", f"/api/termination/cases/{case_id}/assess")
check(graded["case"]["grade"] == "T1", "gitea: T1 after revocation with state evidence", f"{graded['case']['grade']} {graded['case']['criteria'].get('notes')}")
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

# ── restore the lab (servers back, Gitea token re-issued) ────────────────────
for server in ("gitea", "email"):
    status, _ = api("POST", f"/api/lab/restore/{server}")
    check(status == 200, f"restore {server}")
subprocess.run(["./console.sh", "restore-token", "gitea"], check=False)
status, health = api("GET", "/api/health")
print("mcp servers ready:", health.get("mcp_servers", {}).get("ready"), "/", health.get("mcp_servers", {}).get("total"))

print(f"\n{'OK' if not failures else 'FAILED'}: {len(failures)} failure(s)")
sys.exit(1 if failures else 0)
