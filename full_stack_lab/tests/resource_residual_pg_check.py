"""DEV-08: real PostgreSQL, issued JWTs, signed disposal and an isolated Gitea resource.

Run via tests/termination_dispatch_lab.sh run resource_residual_pg_check.py.
The signature-only comparison is the existing E1 verifier, NOT an external resource
server or MCP execution. No MCP implementation is supplied by this test.
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi import HTTPException
from psycopg.types.json import Jsonb

from app import db, decommission, dispatch, idp, mcp_sessions
from app.agent_contract import authenticate, authenticated_user, issue_token
from app.experiments import _stateless_accepts
from termination_lab_support import (
    Checks, add_principal, add_server, apply_schema, isolated_disposal, reservation, run, signing_keys,
)

CHECKS = Checks("DEV-08 resource residual (PostgreSQL and Gitea)")
USER, ADMIN, SERVER = "residual-user", "residual-admin", "residual-server"


async def gateway_status(token):
    try:
        await authenticated_user("Bearer " + token, require_mcp=True)
        return 200
    except HTTPException as exc:
        return exc.status_code


async def issued_tokens():
    issued = await idp._issue({"user_id": USER}, "residual-client", uuid.uuid4())
    access, refresh = issued["access_token"], issued["refresh_token"]
    admin, _ = issue_token({"user_id": ADMIN}, client_id="residual-admin", extra={"scope": "mcp"})
    before = await idp.introspect(access, "Bearer " + admin)
    CHECKS.ok("issued token is initially active and introspection is no-store",
              json.loads(before.body)["active"] is True and before.headers["cache-control"] == "no-store"
              and await gateway_status(access) == 200)
    reply = await idp.revoke(access, "access_token")
    after = await idp.introspect(access, "Bearer " + admin)
    CHECKS.ok("access revocation is immediately visible to fresh introspection and gateway",
              reply.status_code == 200 and json.loads(after.body) == {"active": False}
              and after.headers["cache-control"] == "no-store" and await gateway_status(access) == 401)
    CHECKS.ok("existing E1 signature-only verifier still accepts before expiration (not a remote server)",
              _stateless_accepts(access))
    CHECKS.ok("access-only revocation leaves its refresh grant active", (await idp.introspection(refresh))["active"] is True)
    await idp.revoke(refresh, "refresh_token")
    CHECKS.ok("family revocation invalidates refresh and access, including identifier introspection",
              await idp.introspection(refresh) == {"active": False}
              and await idp.introspection(access) == {"active": False}
              and (await idp.introspect_jti(authenticate("Bearer " + access)[1]["jti"]))["active"] is False)
    return access


async def account_transition():
    issued = await idp._issue({"user_id": USER}, "residual-client", uuid.uuid4())
    access, refresh = issued["access_token"], issued["refresh_token"]
    try:
        await db.execute("UPDATE principals SET status='disabled' WHERE token=%s", (USER,))
        CHECKS.ok("account stop invalidates both introspection views even before token-row revocation",
                  await idp.introspection(refresh) == {"active": False}
                  and await idp.introspection(access) == {"active": False} and await gateway_status(access) == 403)
        await db.execute("UPDATE principals SET status='active', managed_required=true WHERE token=%s", (USER,))
        CHECKS.ok("managed transition makes the old local refresh grant inactive",
                  await idp.introspection(refresh) == {"active": False})
        await db.execute("UPDATE principals SET managed_required=false WHERE token=%s", (USER,))
        with patch.dict(os.environ, {"AUTH_PROVIDER": "oidc"}):
            CHECKS.ok("OIDC transition disables the local refresh introspection grant",
                      await idp.introspection(refresh) == {"active": False})
        CHECKS.ok("a temporary account restriction can recover without an introspection cache",
                  (await idp.introspection(refresh))["active"] is True)
        await idp.revoke_principal_tokens(USER)
        CHECKS.ok("permanent credential revocation survives account reactivation",
                  await idp.introspection(refresh) == {"active": False} and await gateway_status(access) == 401)
    finally:
        await idp.revoke(refresh, "refresh_token")
        await db.execute("UPDATE principals SET status='active', managed_required=false WHERE token=%s", (USER,))


async def target_grades(access):
    await add_server(SERVER, endpoint="http://mcp-gitea:8000/mcp")
    claims = authenticate("Bearer " + access)[1]
    await mcp_sessions.register("residual-session", USER, claims["jti"], None, SERVER)
    CHECKS.ok("a bound session exists before relationship cutover",
              await mcp_sessions.active("residual-session", USER, None, SERVER))
    case = await decommission.open_case(SERVER, "isolated residual check", ADMIN)
    case_id = case["case"]["id"]
    expiry = datetime.fromtimestamp(claims["exp"], UTC)
    ids = {}
    for label, verification in (("issuer", "introspection"), ("signature-only", "stateless"), ("unknown", "introspection")):
        target = await decommission.add_target(case_id, "client-token", label, "org", "operator-manual", ADMIN,
                                               verification=verification, subject_ref=claims["jti"], expires_at=expiry)
        ids[label] = str(target["id"])
        await decommission.revoke_target(ids[label], ADMIN, "REVOKED")
        if label != "unknown":
            await decommission.add_evidence(case_id, "introspection", label, "local issuer", await idp.introspection(access),
                                             ADMIN, target_id=ids[label])
    assessed = await decommission.assess(case_id, ADMIN)
    targets = {str(t["id"]): t for t in assessed["targets"]}
    CHECKS.ok("target grades distinguish issuer state T1, signature-only gap T2, unavailable state T3",
              {label: targets[target]["grade"] for label, target in ids.items()}
              == {"issuer": "T1", "signature-only": "T2", "unknown": "T3"})
    CHECKS.ok("target-only issuer T1 is not whole-relationship termination", assessed["case"]["grade"] == "T3")

    request = str(uuid.uuid4())
    await reservation(request, USER, SERVER, tool="get_me")
    try:
        CHECKS.ok("final dispatch refuses the terminated relationship", await dispatch.record(request, "r") == "terminated")
        rows = await db.fetch_one("SELECT count(*) AS n FROM dispatch_intents WHERE request_id=%s", (request,))
        CHECKS.ok("the refusal leaves no dispatch intent", rows["n"] == 0)
    finally:
        await db.execute("UPDATE call_reservations SET released_at=now() WHERE request_id=%s", (request,))
    CHECKS.ok("ended session reuse is refused under the termination policy",
              not await mcp_sessions.active("residual-session", USER, None, SERVER)
              and (await mcp_sessions.refusal("residual-session"))["policy_id"] == "MCP-DECOMM-001")
    return case_id


async def residual_sequence():
    name = "residual-" + uuid.uuid4().hex
    base = os.environ["GITEA_ADMIN_URL"].rstrip("/")
    auth = (os.environ["GITEA_ADMIN_USER"], os.environ["GITEA_ADMIN_PASSWORD"])
    async with httpx.AsyncClient(auth=auth, timeout=10, follow_redirects=False, trust_env=False) as admin:
        try:
            created = await admin.post(base + "/api/v1/users/mcp-bot/tokens", headers={"Sudo": "mcp-bot"},
                                       json={"name": name, "scopes": ["read:user"]})
            created.raise_for_status()
            secret = created.json()["sha1"]
            with tempfile.TemporaryDirectory(prefix="resource-residual-") as folder:
                path = Path(folder) / "probe.token"
                path.write_text(secret, encoding="utf-8", newline="\n")
                path.chmod(0o600)
                cred = {"id": name, "label": name, "system": "corp-git", "verify": "gitea-token",
                        "account": "mcp-bot", "token_name": name, "probe_token_file": str(path)}
                initial = await decommission._resource_verdict(cred)
                CHECKS.ok("the independent PAT is accepted before issuer-token revocation",
                          initial["http_status"] == 200 and initial["rejected"] is False)
                access = await issued_tokens()
                await account_transition()
                case_id = await target_grades(access)
                await db.execute("UPDATE mcp_servers SET server_held_credentials=%s WHERE id=%s", (Jsonb([cred]), SERVER))
                target = await decommission.add_target(case_id, "server-held-credential", name, "provider",
                                                       "provider-disclosure", ADMIN, verification="gitea-token",
                                                       subject_ref=json.dumps(cred))
                target_id = str(target["id"])
                # An operator status is an action claim; the real resource must still be asked.
                await decommission.revoke_target(target_id, ADMIN, "REVOKED")
                before = await decommission.collect(case_id, ["credentials"], ADMIN)
                observed = next(e for e in before["collected"] if e["kind"] == "resource-rejection")
                CHECKS.ok("the resource still accepts its separate PAT after issuer-token revocation",
                          observed["detail"]["http_status"] == 200 and observed["detail"]["rejected"] is False)
                graded = await decommission.assess(case_id, ADMIN)
                mine = next(t for t in graded["targets"] if str(t["id"]) == target_id)
                CHECKS.ok("resource acceptance prevents T1 despite an operator REVOKED status",
                          mine["grade"] == "T2" and not mine["criteria"]["C3"]["met"] and mine["criteria"]["C4"]["met"])
                revoked = await decommission.revoke_credential(target_id, ADMIN)
                observed = next(e for e in revoked["collected"] if e["kind"] == "resource-rejection")
                CHECKS.ok("real resource reaccess is 401 after downstream PAT revocation",
                          observed["detail"]["http_status"] == 401 and observed["detail"]["rejected"] is True
                          and observed["detail"]["accepted_before_revocation"] is True)
                graded = await decommission.assess(case_id, ADMIN)
                mine = next(t for t in graded["targets"] if str(t["id"]) == target_id)
                CHECKS.ok("provider credential target reaches T1 after direct rejection and issuer absence", mine["grade"] == "T1")
                for table in ("termination_evidence", "revocation_targets", "approval_events"):
                    rows = await db.fetch_all(f"SELECT row_to_json(t)::text AS body FROM {table} t")
                    CHECKS.ok(f"{table} contains no credential value", all(secret not in row["body"] for row in rows))
        finally:
            deleted = await admin.delete(base + "/api/v1/users/mcp-bot/tokens/" + name, headers={"Sudo": "mcp-bot"})
            if deleted.status_code not in (204, 404):
                raise RuntimeError("isolated PAT cleanup failed")


async def main():
    database = await db.fetch_one("SELECT current_database() AS name")
    if not database["name"].startswith("t_resource_residual_pg_check_py_"):
        raise RuntimeError("run only through termination_dispatch_lab.sh with its disposable database")
    signing_keys()
    with patch.dict(os.environ, {"AUTH_PROVIDER": "local"}), isolated_disposal():
        await apply_schema()
        await add_principal(USER)
        await add_principal(ADMIN, role="admin")
        # Keep dependencies sequential: a failed setup must never manufacture later evidence.
        await residual_sequence()
    return CHECKS.finish()


if __name__ == "__main__":
    run(main)
