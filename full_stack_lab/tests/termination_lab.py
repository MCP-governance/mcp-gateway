"""Termination of a real MCP relationship: cutover under an in-flight call, warm connections,
the protected resource's own answer after a credential is revoked, and what is left behind.

Run through termination_dispatch_lab.sh. Real: PostgreSQL, OPA, Presidio, the Gitea project's MCP
server image and a disposable Gitea (the resource server whose token is revoked). Test hooks (unit
level, named in the checks): the absent Gitleaks library is replaced by a scan that finds nothing,
and one hook runs the termination at the exact moment a call reaches the send."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import uuid
from datetime import UTC, datetime, timedelta

import httpx

from app import core, db, decommission, dispatch, registry, secret_scan, upstream
from termination_lab_support import Checks, add_principal, call_payload, mint, run, signing_keys

CHECKS = Checks("termination, provider-side residual access and credential removal (real Gitea)")
GITEA = os.environ["GITEA_ADMIN_URL"].rstrip("/") + "/api/v1"
AUTH = (os.environ["GITEA_ADMIN_USER"], os.environ["GITEA_ADMIN_PASSWORD"])
ENDPOINT = "http://mcp-gitea:8000/mcp"
ADMIN = "acceptance-admin"
STATE = {}


async def no_secrets(text):
    return []


async def issues(prefix):
    async with httpx.AsyncClient(auth=AUTH, timeout=20) as client:
        response = await client.get(f"{GITEA}/repos/bob/payment-service/issues", params={"state": "all", "type": "issues", "limit": 100})
    return [i["title"] for i in response.json() if i["title"].startswith(prefix)]


async def call(token, title):
    _, claims = mint(token, minutes=30)
    return await core.execute_call(call_payload(token, "gitea", "issue_write", {
        "method": "create", "owner": "bob", "repo": "payment-service", "title": title, "body": "lab"}, claims))


def shown(outcome):
    return {k: outcome.get(k) for k in ("decision", "policy_id", "upstream_attempted", "upstream_executed")}


async def baseline():
    title = f"before-{uuid.uuid4().hex[:8]}"
    first = await call("boundary-t1", title)
    CHECKS.ok("before the cutover the call executes", first["upstream_executed"], outcome=shown(first))
    keys = [k for k in upstream._pool if k[0] == ENDPOINT and k[1] == "boundary-t1"]
    CHECKS.ok("a warm upstream connection is held for this principal and server", len(keys) == 1, keys=len(keys))
    STATE["warm"] = upstream._pool[keys[0]].client


async def cutover_under_an_inflight_call():
    title = f"inflight-{uuid.uuid4().hex[:8]}"
    real = dispatch.record
    ran = {}

    async def terminate_then_record(*args, **kwargs):
        dispatch.record = real
        ran["case"] = await decommission.open_case("gitea", "lab: cutover while a call reaches the send", ADMIN)
        return await real(*args, **kwargs)

    dispatch.record = terminate_then_record
    try:
        outcome = await call("boundary-t1", title)
    finally:
        dispatch.record = real
    STATE["case"] = ran["case"]["case"]["id"]
    CHECKS.ok("a call already past its final checks when the cutover lands is not sent",
              outcome["decision"] == "Block" and outcome["policy_id"] == "MCP-DECOMM-001" and not outcome["upstream_attempted"],
              outcome=shown(outcome))
    CHECKS.ok("the downstream took nothing from it", await issues(title) == [])
    intents = await db.fetch_one("SELECT count(*) AS n FROM dispatch_intents WHERE request_id=%s", (outcome["request_id"],))
    CHECKS.ok("it left no dispatch intent", intents["n"] == 0)
    CHECKS.ok("no warm connection for this server survives the cutover",
              not [k for k in upstream._pool if k[0] == ENDPOINT])
    CHECKS.ok("the connection that was in use is closed once the call let go", STATE["warm"].is_closed)
    events = await db.fetch_one("SELECT count(*) AS n FROM upstream_pool_events WHERE endpoint=%s", (ENDPOINT,))
    CHECKS.ok("the closure is announced for the other gateway processes", events["n"] >= 1)
    later = await call("boundary-t1", f"after-{uuid.uuid4().hex[:8]}")
    CHECKS.ok("a new call after the cutover is refused by the policy", later["policy_id"] == "MCP-DECOMM-001" and not later["upstream_attempted"], outcome=shown(later))
    detail = await decommission.case_detail(STATE["case"])
    CHECKS.ok("the case enumerates the route, the caller and the provider-held credential",
              {t["kind"] for t in detail["targets"]} >= {"gateway-route", "gateway-access", "server-held-credential"},
              kinds=sorted({t["kind"] for t in detail["targets"]}))
    STATE["targets"] = {t["kind"]: t["id"] for t in detail["targets"]}


async def gitea(method, path, **kwargs):
    async with httpx.AsyncClient(auth=AUTH, timeout=20) as client:
        return await client.request(method, f"{GITEA}{path}", **kwargs)


async def provider_side():
    case = STATE["case"]
    collected = await decommission.collect(case, ["gateway"], ADMIN)
    CHECKS.ok("gateway denial evidence is collected for the route and the caller",
              sum(1 for e in collected["collected"] if e["kind"] == "gateway-denial" and e["detail"]["blocked"]) == 2)
    target = STATE["targets"]["server-held-credential"]
    token_file = os.environ["GITEA_PROBE_TOKEN_FILE"]
    before = await decommission._resource_verdict()
    CHECKS.ok("before the revocation the resource accepts the provider's token", before["rejected"] is False and before["http_status"] == 200, verdict=before)
    result = await decommission.collect(case, ["credentials"], ADMIN)
    pre = [e for e in result["collected"] if e["kind"] == "resource-rejection"]
    CHECKS.ok("collecting before the revocation records the resource still accepting it", len(pre) == 1 and pre[0]["detail"]["rejected"] is False)
    CHECKS.ok("and the token is still in the issuer's list", any(e["kind"] == "credential-check" and e["detail"]["present"] is True for e in result["collected"]))
    revoked = await decommission.revoke_credential(target, ADMIN)
    kinds = [e["kind"] for e in revoked["collected"]]
    rejection = next(e for e in revoked["collected"] if e["kind"] == "resource-rejection")
    CHECKS.ok("after the revocation the protected resource rejects the old token (401, not list absence)",
              rejection["detail"]["rejected"] is True and rejection["detail"]["http_status"] == 401
              and rejection["detail"]["accepted_before_revocation"] is True, detail=rejection["detail"])
    CHECKS.ok("the issuer's list agrees", any(e["kind"] == "credential-check" and e["detail"]["present"] is False for e in revoked["collected"]), kinds=kinds)
    direct = httpx.get(f"{GITEA}/user", headers={"Authorization": "token " + open(token_file, encoding="utf-8").read().strip()}, timeout=10)
    CHECKS.ok("asked directly, the resource refuses the old token on a protected route", direct.status_code == 401)
    row = await db.fetch_one("SELECT status FROM revocation_targets WHERE id=%s", (target,))
    CHECKS.ok("the target is recorded as revoked", row["status"] == "REVOKED")

    # Cannot be asked: no copy of the value, an unreadable file, an unreachable resource.
    saved = (decommission.GITEA_PROBE_TOKEN_FILE, decommission.GITEA_RESOURCE_URL)
    try:
        decommission.GITEA_PROBE_TOKEN_FILE = ""
        a = await decommission._resource_verdict()
        decommission.GITEA_PROBE_TOKEN_FILE = "/nonexistent/probe.token"
        b = await decommission._resource_verdict()
        decommission.GITEA_PROBE_TOKEN_FILE, decommission.GITEA_RESOURCE_URL = saved[0], "http://127.0.0.1:9"
        c = await decommission._resource_verdict()
    finally:
        decommission.GITEA_PROBE_TOKEN_FILE, decommission.GITEA_RESOURCE_URL = saved
    CHECKS.ok("when the resource cannot be asked the answer is unknown, never rejected",
              [a["rejected"], b["rejected"], c["rejected"]] == [None, None, None], reasons=[a["reason"], b["reason"], c["reason"]])

    # A second provider-held token that the operator marks revoked but never deletes: the resource still takes it.
    created = await gitea("POST", "/users/mcp-bot/tokens", headers={"Sudo": "mcp-bot"}, json={"name": "lab-second", "scopes": ["all"]})
    second_file = os.path.join(tempfile.mkdtemp(), "second.token")
    with open(second_file, "w", encoding="utf-8") as handle:
        handle.write(created.json()["sha1"])
    STATE["second_secret"] = created.json()["sha1"]
    cred = {"id": "lab-second", "label": "lab second token", "system": "corp-git", "verify": "gitea-token", "account": "mcp-bot",
            "token_name": "lab-second", "probe_token_file": second_file}
    added = await decommission.add_target(case, "server-held-credential", cred["label"], "provider", "operator-manual", ADMIN,
                                          subject_ref=json.dumps(cred), verification="gitea-token")
    await decommission.revoke_target(str(added["id"]), ADMIN, "REVOKED", "marked revoked by the operator")
    await decommission.collect(case, ["credentials"], ADMIN)
    judged = await decommission.assess(case, ADMIN)
    mine = next(t for t in judged["targets"] if str(t["id"]) == str(added["id"]))
    CHECKS.ok("a credential recorded revoked that the resource still accepts is residual access, not revoked",
              mine["criteria"]["provider_side"]["state"] == "accepted" and not mine["criteria"]["C3"]["met"]
              and any("수락" in gap for gap in mine["criteria"]["C3"]["gaps"]), criteria=mine["criteria"])
    CHECKS.ok("so the case cannot be T1", judged["case"]["grade"] != "T1", grade=judged["case"]["grade"])
    deleted = await gitea("DELETE", "/users/mcp-bot/tokens/lab-second", headers={"Sudo": "mcp-bot"})
    CHECKS.ok("the operator then really deletes it", deleted.status_code == 204)
    await decommission.collect(case, ["credentials"], ADMIN)
    judged = await decommission.assess(case, ADMIN)
    mine = next(t for t in judged["targets"] if str(t["id"]) == str(added["id"]))
    first = next(t for t in judged["targets"] if str(t["id"]) == str(target))
    CHECKS.ok("after that the resource's refusal is the latest answer", mine["criteria"]["provider_side"]["state"] == "rejected"
              and first["criteria"]["provider_side"]["state"] == "rejected")
    STATE["judged"] = judged
    print(json.dumps({"case_grade": judged["case"]["grade"],
                      "targets": [{"kind": t["kind"], "grade": t["grade"], "C": {k: t["criteria"][k]["met"] for k in ("C1", "C2", "C3", "C4")}}
                                  for t in judged["targets"]],
                      "activity": judged["activity"]}, ensure_ascii=False), flush=True)


def judge_unit():
    """Pure function: what the judgment does with each possible answer of the resource (unit level)."""
    now = datetime.now(UTC)
    target = {"kind": "server-held-credential", "status": "REVOKED", "revoked_at": now - timedelta(minutes=5), "holder": "provider",
              "verification": "gitea-token", "expires_at": None}
    activity = {"executed": 0, "blocked": 0, "unknown": 0, "straddled": 0}

    def evidence(kind, **detail):
        return {"id": uuid.uuid4(), "kind": kind, "detail": detail, "observed_at": now}

    listed = evidence("credential-check", present=False)
    unknown = decommission._judge_target(target, [listed], activity, True)
    refused = decommission._judge_target(target, [listed, evidence("resource-rejection", rejected=True, http_status=401)], activity, True)
    accepted = decommission._judge_target(target, [listed, evidence("resource-rejection", rejected=False, http_status=200)], activity, True)
    unverified_expiry = decommission._judge_target({**target, "expires_at": now + timedelta(hours=1)}, [listed], activity, True)
    CHECKS.ok("judgment: not asked is shown as unverified and the expiry is the only bound recorded",
              unknown["criteria"]["provider_side"] == {"state": "unverified", "expires_at": None}
              and unverified_expiry["criteria"]["provider_side"]["expires_at"] is not None)
    CHECKS.ok("judgment: the resource's refusal is shown as rejected and meets continuity", refused["criteria"]["provider_side"]["state"] == "rejected"
              and refused["criteria"]["C3"]["met"])
    CHECKS.ok("judgment: the resource's acceptance overrides the issuer's list", accepted["criteria"]["provider_side"]["state"] == "accepted"
              and not accepted["criteria"]["C3"]["met"] and accepted["grade"] == "T2", grade=accepted["grade"])
    other = decommission._judge_target({**target, "kind": "gateway-access", "verification": "gateway-probe"}, [], activity, True)
    CHECKS.ok("judgment: other target kinds carry no provider-side field", "provider_side" not in other["criteria"])


async def credential_removal():
    case = STATE["case"]
    secrets_ = [open(os.environ["GITEA_PROBE_TOKEN_FILE"], encoding="utf-8").read().strip(), STATE["second_secret"]]
    needles = secrets_ + [s[-8:] for s in secrets_]
    tables = ["termination_evidence", "revocation_targets", "termination_cases", "decisions", "dispatch_intents",
              "approvals", "upstream_pool_events", "call_reservations", "termination_cases"]
    found = []
    for table in tables:
        for row in await db.fetch_all(f"SELECT row_to_json(t)::text AS body FROM {table} t"):
            found += [(table, n[:4]) for n in needles if n in row["body"]]
    for name, document in (("report", await decommission.report(case)), ("disclosure", await decommission.disclosure_request(case)),
                           ("detail", await decommission.case_detail(case))):
        text = json.dumps(document, default=str, ensure_ascii=False)
        found += [(name, n[:4]) for n in needles if n in text]
    CHECKS.ok("no token value, nor its last eight characters, reached the audit evidence, the ledger or the exports", not found, found=found)

    directory = tempfile.mkdtemp()
    unrelated = os.path.join(directory, "unrelated.txt")
    with open(unrelated, "w", encoding="utf-8") as handle:
        handle.write("not the gateway's to touch")
    sentinel = hashlib.sha256(open(unrelated, "rb").read()).hexdigest()
    credentials = os.path.join(directory, "upstream-credentials.json")
    endpoint = "https://saas.example.test/mcp"
    document = {"credentials": [{"endpoint": endpoint, "allowed_principals": ["boundary-t1"], "expires_at": 0, "access_token": "lab-token-value"}]}
    with open(credentials, "w", encoding="utf-8") as handle:
        json.dump(document, handle)
    os.chmod(credentials, 0o600)
    os.environ["MCP_UPSTREAM_CREDENTIALS_FILE"] = credentials
    before = upstream.credential_headers(endpoint, "boundary-t1")
    async with upstream._dispatch_client(endpoint, "boundary-t1", before, 30):
        pass
    holding = [lease.client for key, lease in upstream._pool.items() if key[0] == endpoint]
    with open(credentials, "w", encoding="utf-8") as handle:
        json.dump({"credentials": []}, handle)
    after = upstream.credential_headers(endpoint, "boundary-t1")
    CHECKS.ok("a credential removed from the file is not read back", before.get("Authorization") == "Bearer lab-token-value" and after == {})
    async with upstream._dispatch_client(endpoint, "boundary-t1", after, 30):
        pass
    CHECKS.ok("and no cached client keeps the removed credential in memory",
              all(c.is_closed for c in holding) and not any("lab-token-value" in str(l.client.headers) for l in upstream._pool.values()))
    await upstream.close_pool(endpoint=endpoint)
    os.environ.pop("MCP_UPSTREAM_CREDENTIALS_FILE")
    CHECKS.ok("files the gateway does not own are untouched", hashlib.sha256(open(unrelated, "rb").read()).hexdigest() == sentinel)


async def close_and_stay_closed():
    case = STATE["case"]
    graded = STATE["judged"]["case"]["grade"]
    closed = await decommission.close_case(case, ADMIN, "lab: relationship ended", "lab: owner accepts" if graded == "T3" else None)
    row = await db.fetch_one("SELECT lifecycle, status FROM mcp_servers WHERE id='gitea'")
    CHECKS.ok("closing retires and disables the server", row["lifecycle"] == "RETIRED" and row["status"] == "DISABLED"
              and closed["case"]["status"] == "CLOSED", row=row)
    await registry.sync()
    again = await db.fetch_one("SELECT lifecycle, status FROM mcp_servers WHERE id='gitea'")
    CHECKS.ok("a restart-style registry sync does not bring the server back from the catalog files", again["lifecycle"] == "RETIRED"
              and again["status"] == "DISABLED", row=again)
    title = f"retired-{uuid.uuid4().hex[:8]}"
    outcome = await call("boundary-t1", title)
    CHECKS.ok("a retired relationship's call is refused and takes no effect", not outcome["upstream_attempted"] and outcome["decision"] == "Block"
              and await issues(title) == [], outcome=shown(outcome))
    refreshed = await core.refresh_catalog("gitea")
    CHECKS.ok("catalog refresh does not reconnect a retired server", refreshed["status"] == "DISABLED", refreshed=refreshed.get("status"))


async def main():
    signing_keys()
    secret_scan.labels = no_secrets
    await core.bootstrap()
    CHECKS.ok("the Gitea MCP server answers and its contract matches the reviewed lock", (await core.refresh_catalog("gitea"))["status"] == "READY")
    await add_principal("boundary-t1")
    await add_principal(ADMIN, role="admin")
    started = time.monotonic()
    await CHECKS.case("baseline", baseline())
    await CHECKS.case("cutover_under_an_inflight_call", cutover_under_an_inflight_call())
    await CHECKS.case("provider_side", provider_side())
    judge_unit()
    await CHECKS.case("credential_removal", credential_removal())
    await CHECKS.case("close_and_stay_closed", close_and_stay_closed())
    CHECKS.ok("run completed", time.monotonic() - started < 600)
    return CHECKS.finish()


if __name__ == "__main__":
    run(main)
