"""Revoked tokens, their refresh family and revoked devices, with real signed tokens on a real schema.

Run through termination_dispatch_lab.sh. The signing key is a throwaway Ed25519 pair, the tokens are
the gateway's own JWTs, and every acceptance question is asked of authenticated_user(), the one
function the protected API and the MCP ingress both call. No double: the issue, rotate and revoke
SQL runs on PostgreSQL, including the rollback of a failed issuance."""
from __future__ import annotations

import asyncio
import json
import os
import uuid

import jwt
import psycopg
from fastapi import HTTPException
from starlette.requests import Request

from app import db, endpoint_plane, idp, disposal
from app.agent_contract import authenticated_user, public_key
from termination_lab_support import Checks, add_principal, apply_schema, isolated_disposal, run, signing_keys

CHECKS = Checks("token, refresh family and device revocation (PostgreSQL)")
REQUEST = Request({"type": "http", "client": ("127.0.0.1", 1), "headers": []})
CLIENT = "lab-client"


async def login(email):
    reply = await idp.token(REQUEST, grant_type="password", client_id=CLIENT, username=email, password="lab-password", refresh_token=None)
    assert isinstance(reply, dict), reply
    return reply


async def rotate(refresh):
    return await idp.token(REQUEST, grant_type="refresh_token", client_id=CLIENT, username=None, password=None, refresh_token=refresh)


async def verdict(access, require_mcp=True):
    """200 for a token the gateway accepts, the status code otherwise."""
    try:
        await authenticated_user("Bearer " + access, require_mcp=require_mcp)
        return 200
    except HTTPException as exc:
        return exc.status_code


async def accepted(tokens):
    return [await verdict(t) for t in tokens]


async def family_revocation():
    await add_principal("tok-a")
    await db.execute("UPDATE principals SET password_hash=crypt('lab-password', gen_salt('bf', 4)) WHERE token='tok-a'")
    first = await login("tok-a@bob.local")
    second = await rotate(first["refresh_token"])
    third = await rotate(second["refresh_token"])
    access = [first["access_token"], second["access_token"], third["access_token"]]
    CHECKS.ok("every token of the family is accepted on the protected API and the MCP ingress", await accepted(access) == [200, 200, 200]
              and [await verdict(t, False) for t in access] == [200, 200, 200])
    reply = await idp.revoke(third["refresh_token"], None)
    CHECKS.ok("revocation answers 200 as RFC 7009 requires", reply.status_code == 200)
    CHECKS.ok("after revoking the refresh token every access token of its family is refused (API and MCP)",
              await accepted(access) == [401, 401, 401] and [await verdict(t, False) for t in access] == [401, 401, 401],
              verdicts=await accepted(access))
    CHECKS.ok("introspection agrees for each of them", [(await idp.introspection(t))["active"] for t in access] == [False, False, False])
    refused = [await rotate(r) for r in (first["refresh_token"], second["refresh_token"], third["refresh_token"])]
    CHECKS.ok("no refresh token of the family mints another access token", all(getattr(r, "status_code", 200) == 400 for r in refused))
    count = await db.fetch_one("SELECT count(*) AS n FROM oauth_issued_tokens WHERE family_id = (SELECT family_id FROM oauth_refresh_tokens WHERE token_sha256=%s)",
                               (idp._sha(first["refresh_token"]),))
    CHECKS.ok("nothing was issued after the revocation", count["n"] == 3, issued=count["n"])

    fourth = await login("tok-a@bob.local")
    fifth = await rotate(fourth["refresh_token"])
    replay = await rotate(fourth["refresh_token"])
    CHECKS.ok("replaying a rotated refresh token revokes the whole family",
              getattr(replay, "status_code", 200) == 400
              and await accepted([fourth["access_token"], fifth["access_token"]]) == [401, 401]
              and getattr(await rotate(fifth["refresh_token"]), "status_code", 200) == 400)

    sixth = await login("tok-a@bob.local")
    seventh = await rotate(sixth["refresh_token"])
    await idp.revoke(seventh["access_token"], "access_token")
    CHECKS.ok("revoking one access token refuses that token only (RFC 7009 scope, as the paper's E1 requires)",
              await accepted([sixth["access_token"], seventh["access_token"]]) == [200, 401])
    await db.execute("UPDATE principals SET status='disabled' WHERE token='tok-a'")
    disabled = await accepted([sixth["access_token"], seventh["access_token"]])
    CHECKS.ok("a disabled principal is refused on every token it holds (the one already revoked stays 401)", disabled == [403, 401], verdicts=disabled)
    CHECKS.ok("and cannot refresh", getattr(await rotate(seventh["refresh_token"]), "status_code", 200) == 400)
    await db.execute("UPDATE principals SET status='active' WHERE token='tok-a'")


async def issue_against_revoke():
    await add_principal("tok-b")
    await db.execute("UPDATE principals SET password_hash=crypt('lab-password', gen_salt('bf', 4)) WHERE token='tok-b'")
    survivors = 0
    for trial in range(12):
        start = await login("tok-b@bob.local")
        replies = await asyncio.gather(rotate(start["refresh_token"]), idp.revoke(start["refresh_token"], "refresh_token"),
                                       rotate(start["refresh_token"]), return_exceptions=True)
        minted = [r["access_token"] for r in replies if isinstance(r, dict) and "access_token" in r]
        verdicts = [await verdict(t) for t in [start["access_token"], *minted]]
        family = await db.fetch_one("SELECT family_id FROM oauth_refresh_tokens WHERE token_sha256=%s", (idp._sha(start["refresh_token"]),))
        rows = await db.fetch_one(
            """SELECT (SELECT count(*) FROM oauth_refresh_tokens WHERE family_id=%s AND revoked_at IS NULL) AS live_refresh,
                      (SELECT count(*) FROM oauth_issued_tokens i LEFT JOIN agent_revoked_tokens r ON r.jti=i.jti::uuid
                        WHERE i.family_id=%s AND i.expires_at>now() AND r.jti IS NULL) AS live_access""",
            (family["family_id"], family["family_id"]))
        survivors += int(any(v == 200 for v in verdicts) or rows["live_refresh"] or rows["live_access"])
        errors = [r for r in replies if isinstance(r, Exception)]
        assert not errors, errors
    CHECKS.ok("12 rounds of two refreshes racing a revocation: no token and no refresh token of the family survives", survivors == 0, survivors=survivors)


async def issuance_rolls_back():
    await add_principal("tok-c")
    await db.execute("UPDATE principals SET password_hash=crypt('lab-password', gen_salt('bf', 4)) WHERE token='tok-c'")
    start = await login("tok-c@bob.local")
    family = (await db.fetch_one("SELECT family_id FROM oauth_refresh_tokens WHERE token_sha256=%s", (idp._sha(start["refresh_token"]),)))["family_id"]
    constraint = "lab_fail_" + uuid.uuid4().hex[:8]
    await db.execute(f"ALTER TABLE oauth_refresh_tokens ADD CONSTRAINT {constraint} CHECK (family_id <> '{family}' OR token_sha256 = '{idp._sha(start['refresh_token'])}')")
    before = (await db.fetch_one("SELECT count(*) AS n FROM oauth_issued_tokens WHERE family_id=%s", (family,)))["n"]
    try:
        await rotate(start["refresh_token"])
        failed = False
    except psycopg.errors.CheckViolation:
        failed = True
    parent = await db.fetch_one("SELECT rotated_at FROM oauth_refresh_tokens WHERE token_sha256=%s", (idp._sha(start["refresh_token"]),))
    after = (await db.fetch_one("SELECT count(*) AS n FROM oauth_issued_tokens WHERE family_id=%s", (family,)))["n"]
    await db.execute(f"ALTER TABLE oauth_refresh_tokens DROP CONSTRAINT {constraint}")
    CHECKS.ok("a failed issuance rolls back the rotation and the access-token record together", failed and parent["rotated_at"] is None and before == after)
    CHECKS.ok("and the refresh token still works afterwards", isinstance(await rotate(start["refresh_token"]), dict))


async def device_revocation():
    await add_principal("tok-d")
    await add_principal("tok-reviewer", role="admin")
    kit = await endpoint_plane.enrollment_token("tok-d")
    key = "k" * 43
    device = await endpoint_plane.consume_enrollment(kit["enrollment_token"], key, "lab-host", "labuser", 1000)
    endpoint = device["endpoint_id"]
    policy = await endpoint_plane.managed_policy(device)
    checks = {name: True for name in endpoint_plane.managed_checks(device)}
    beat = await endpoint_plane.heartbeat(device, policy["policy_hash"], policy["configuration_hashes"], checks)
    await endpoint_plane.activate_managed(endpoint, "tok-reviewer", beat["policy_hash"], "lab")
    issued = await idp.device_token(x_endpoint_key=key)
    body = json.loads(issued.body)
    CHECKS.ok("an active managed device receives a device-bound token", issued.status_code == 200 and "access_token" in body)
    claims = jwt.decode(body["access_token"], public_key(), algorithms=["EdDSA"], audience="mcp-governance-gateway", issuer="mcp-governance-synthetic-agent")
    CHECKS.ok("the token is bound to the device", claims["device_id"] == endpoint)
    CHECKS.ok("it is accepted on the MCP ingress while the device is active", await verdict(body["access_token"]) == 200)
    current = await db.fetch_one("SELECT * FROM endpoint_agents WHERE endpoint_id=%s", (endpoint,))
    await endpoint_plane.revoke_device(endpoint, "tok-reviewer")
    CHECKS.ok("revoking the device refuses the token it already holds, at once (API and MCP)",
              # G07.04 records the device's tokens in the signed list and the revocation table; that check runs
              # first, so both ingresses answer 401 - and the record itself must be there (sol review B).
              await verdict(body["access_token"]) == 401 and await verdict(body["access_token"], False) == 401
              and disposal.blocked(jti=claims["jti"])
              and bool(await db.fetch_one("SELECT 1 FROM agent_revoked_tokens WHERE jti=%s", (claims["jti"],))))
    refused = []
    for scope in endpoint_plane.DEVICE_SCOPES:
        try:
            await endpoint_plane.authenticate_device(key, scope)
            refused.append(False)
        except PermissionError:
            refused.append(True)
    CHECKS.ok("the device key authenticates for no scope (enrollment, inventory, scan, enforcement)", all(refused), refused=refused)
    try:
        await endpoint_plane.heartbeat(current, policy["policy_hash"], policy["configuration_hashes"], checks)
        CHECKS.ok("a heartbeat does not bring a revoked device back", False)
    except PermissionError:
        CHECKS.ok("a heartbeat does not bring a revoked device back", True)
    status = await db.fetch_one("SELECT status, managed_state FROM endpoint_agents WHERE endpoint_id=%s", (endpoint,))
    CHECKS.ok("the device stays revoked after the attempt", status["status"] == "revoked")
    minted = await idp.device_token(x_endpoint_key=key)
    CHECKS.ok("the device cannot mint a new token", minted.status_code == 401)
    event = await db.fetch_one("SELECT count(*) AS n FROM endpoint_managed_events WHERE endpoint_id=%s AND kind='revoked'", (endpoint,))
    CHECKS.ok("the revocation is on the managed-event journal", event["n"] == 1)


async def main():
    signing_keys()
    os.environ["AUTH_PROVIDER"] = "local"
    await apply_schema()
    # D-123 made the signed disposal list mandatory (fail-closed); give the lab its own throwaway one.
    with isolated_disposal():
        for case in (family_revocation, issue_against_revoke, issuance_rolls_back, device_revocation):
            await CHECKS.case(case.__name__, case())
    return CHECKS.finish()


if __name__ == "__main__":
    run(main)
