"""D-123 backup restoration check against PostgreSQL and product lifecycle functions.

Run only through termination_dispatch_lab.sh. The backup is a row-level logical
snapshot of the fixture in PostgreSQL; no product database or MCP endpoint is used.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os

from fastapi import HTTPException
from psycopg.types.json import Jsonb
from starlette.requests import Request

from app import core, db, decommission, disposal, endpoint_plane, idp
from app.agent_contract import authenticate, authenticated_user, issue_token
from termination_lab_support import Checks, add_principal, add_server, apply_schema, isolated_disposal, run, signing_keys

CHECKS = Checks("restore residual PostgreSQL")
REQUEST = Request({"type": "http", "client": ("127.0.0.1", 1), "headers": []})
USER, ACCOUNT, ADMIN, SERVER = "acceptance-partner", "acceptance-employee", "restore-admin", "gitea"
DEVICE = ""


async def verdict(header: str) -> int:
    try:
        await authenticated_user(header, require_mcp=True)
        return 200
    except HTTPException as exc:
        return exc.status_code


async def account_login(email: str) -> dict:
    result = await idp.token(REQUEST, grant_type="password", client_id="lab-client", username=email,
                             password="lab-password", refresh_token=None)
    assert isinstance(result, dict), result
    return result


async def snapshot() -> dict:
    """Capture fixture rows before revocation, like a scoped logical DB backup."""
    queries = {
        "principal": ("SELECT * FROM principals WHERE user_id=ANY(%s)", ([USER, ACCOUNT],)),
        "device": ("SELECT * FROM endpoint_agents WHERE endpoint_id=%s", (DEVICE,)),
        "issued": ("SELECT * FROM oauth_issued_tokens WHERE user_id=ANY(%s)", ([USER, ACCOUNT],)),
        "refresh": ("SELECT * FROM oauth_refresh_tokens WHERE user_id=ANY(%s)", ([USER, ACCOUNT],)),
        "server": ("SELECT * FROM mcp_servers WHERE id=%s", (SERVER,)),
        "case": ("SELECT * FROM termination_cases WHERE server_id=%s", (SERVER,)),
        "target": ("SELECT * FROM revocation_targets WHERE label='restore credential'", ()),
        "revoked": ("SELECT * FROM agent_revoked_tokens WHERE jti IN (SELECT jti::uuid FROM oauth_issued_tokens WHERE user_id=ANY(%s))", ([USER, ACCOUNT],)),
        "blocks": ("SELECT * FROM disposal_blocks WHERE subject IN (SELECT jti FROM oauth_issued_tokens WHERE user_id=ANY(%s)) OR server_id=%s", ([USER, ACCOUNT], SERVER)),
    }
    return {name: await db.fetch_all(query, params) for name, (query, params) in queries.items()}


async def restore_rows(backup: dict) -> None:
    """Restore fixture rows and remove revocation state that was absent in backup."""
    async with db.transaction() as connection:
        await connection.execute("DELETE FROM agent_revoked_tokens WHERE jti IN (SELECT jti::uuid FROM oauth_issued_tokens WHERE user_id=ANY(%s))", ([USER, ACCOUNT],))
        await connection.execute("DELETE FROM disposal_blocks WHERE subject IN (SELECT jti FROM oauth_issued_tokens WHERE user_id=ANY(%s)) OR server_id=%s", ([USER, ACCOUNT], SERVER))
        for row in backup["principal"]:
            await connection.execute("UPDATE principals SET status=%s WHERE user_id=%s", (row["status"], row["user_id"]))
        for row in backup["device"]:
            await connection.execute("UPDATE endpoint_agents SET status=%s, managed_state=%s WHERE endpoint_id=%s",
                                     (row["status"], row["managed_state"], row["endpoint_id"]))
        for row in backup["issued"]:
            await connection.execute("UPDATE oauth_issued_tokens SET expires_at=%s WHERE jti=%s", (row["expires_at"], row["jti"]))
        for row in backup["refresh"]:
            await connection.execute("UPDATE oauth_refresh_tokens SET revoked_at=%s, rotated_at=%s WHERE id=%s",
                                     (row["revoked_at"], row["rotated_at"], row["id"]))
        for row in backup["server"]:
            await connection.execute("UPDATE mcp_servers SET status=%s,status_reason=%s,lifecycle=%s,server_held_credentials=%s WHERE id=%s",
                                     (row["status"], row["status_reason"], row["lifecycle"], Jsonb(row["server_held_credentials"]), SERVER))
        for row in backup["case"]:
            await connection.execute("UPDATE termination_cases SET status=%s,grade=%s,closed_by=%s,closed_at=%s,close_note=%s WHERE id=%s",
                                     (row["status"], row["grade"], row["closed_by"], row["closed_at"], row["close_note"], row["id"]))
        for row in backup["target"]:
            await connection.execute("UPDATE revocation_targets SET status=%s,revoked_at=%s,revoked_by=%s WHERE id=%s",
                                     (row["status"], row["revoked_at"], row["revoked_by"], row["id"]))
        for row in backup["revoked"]:
            await connection.execute("INSERT INTO agent_revoked_tokens(jti,expires_at) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                                     (row["jti"], row["expires_at"]))
        for row in backup["blocks"]:
            await connection.execute("INSERT INTO disposal_blocks(kind,subject,server_id,detail) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                                     (row["kind"], row["subject"], row["server_id"], Jsonb(row["detail"])))


async def setup_fixture() -> tuple[str, str, str, str]:
    await add_principal(USER)
    await add_principal(ACCOUNT)
    await add_principal(ADMIN, role="admin")
    await db.execute("UPDATE principals SET password_hash=crypt('lab-password', gen_salt('bf', 4)) WHERE token=%s", (ACCOUNT,))
    await add_server(SERVER)
    await db.execute("UPDATE mcp_servers SET server_held_credentials=%s WHERE id=%s",
                     (Jsonb([{"label": "restore credential", "verify": "gitea-token", "account": "mcp-bot",
                              "token_name": "gitea-mcp-server", "probe_token_file": os.getenv("GITEA_PROBE_TOKEN_FILE")}]), SERVER))
    await db.execute("UPDATE mcp_servers SET deployment='provider', exit_terms=%s WHERE id=%s",
                     (Jsonb({"provider_credential_disclosure": True}), SERVER))

    login = await account_login(f"{ACCOUNT}@bob.local")
    kit = await endpoint_plane.enrollment_token(USER)
    device = await endpoint_plane.consume_enrollment(
        kit["enrollment_token"], "restore-device-key-material-0123456789", "restore-host", "labuser", 1000)
    global DEVICE
    DEVICE = device["endpoint_id"]
    managed = await endpoint_plane.managed_policy(device)
    checks = {name: True for name in endpoint_plane.managed_checks(device)}
    beat = await endpoint_plane.heartbeat(device, managed["policy_hash"], managed["configuration_hashes"], checks)
    await endpoint_plane.activate_managed(device["endpoint_id"], ADMIN, beat["policy_hash"], "restore check")
    device_token = await idp.device_token(x_endpoint_key="restore-device-key-material-0123456789")
    assert device_token.status_code == 200, device_token.status_code
    device_access = json.loads(device_token.body)["access_token"]

    control_access, _ = issue_token({"user_id": ADMIN}, minutes=10, client_id="lab-client")
    return login["access_token"], login["refresh_token"], device_access, control_access


async def restore_residual() -> None:
    access, refresh, device_access, control_access = await setup_fixture()
    CHECKS.ok("account and device tokens authenticate before backup", await verdict("Bearer " + access) == 200
              and await verdict("Bearer " + device_access) == 200
              and await verdict("Bearer " + control_access) == 200
              and (await idp.introspection(refresh))["active"] is True)
    CHECKS.ok("registered server credential reference is in managed settings before termination",
              SERVER in json.dumps(await endpoint_plane.managed_policy(await db.fetch_one(
                  "SELECT * FROM endpoint_agents WHERE endpoint_id=%s", (DEVICE,))), ensure_ascii=False))

    opened = await decommission.open_case(SERVER, "restore check", ADMIN, "restore credential check")
    case_id = str(opened["case"]["id"])
    target = next(row for row in opened["targets"] if row["label"] == "restore credential")
    target_id = str(target["id"])
    backup = await snapshot()

    await idp.revoke_principal_tokens(ACCOUNT)
    await endpoint_plane.revoke_device(DEVICE, ADMIN)
    target = backup["target"][0]
    credential_result = await decommission.revoke_credential(target_id, ADMIN)
    judged = await decommission.assess(case_id, ADMIN)
    closed = await decommission.close_case(case_id, ADMIN, "lab termination",
                                           "lab residual accepted" if judged["case"]["grade"] == "T3" else None)
    signed = disposal.read()
    tombstones = {(row["kind"], row["subject"], row["server_id"]) for row in signed}
    refresh_hash = hashlib.sha256(refresh.encode()).hexdigest()
    issued = {row["jti"] for row in backup["issued"]}
    CHECKS.ok("account, refresh family, device, credential and server tombstones are signed before DB restore",
              all(("token", jti, "") in tombstones for jti in issued)
              and ("refresh", refresh_hash, "") in tombstones
              and any(row["kind"] == "token" and row["subject"] in issued for row in signed)
              and ("credential", target_id, SERVER) in tombstones
              and ("server", SERVER, SERVER) in tombstones and closed["case"]["status"] == "CLOSED"
              and any(row["kind"] == "credential-check" and row["detail"].get("present") is False
                      for row in credential_result.get("collected", [])))

    await restore_rows(backup)
    restored = await db.fetch_one("SELECT status FROM principals WHERE user_id=%s", (ACCOUNT,))
    restored_device = await db.fetch_one("SELECT status FROM endpoint_agents WHERE endpoint_id=%s", (DEVICE,))
    restored_refresh = await db.fetch_one("SELECT revoked_at FROM oauth_refresh_tokens WHERE token_sha256=%s",
                                          (idp._sha(refresh),))
    CHECKS.ok("logical backup restores pre-revocation DB rows while the signed list still blocks access",
              restored["status"] == "active" and restored_device["status"] == "active"
              and restored_refresh["revoked_at"] is None
              and await verdict("Bearer " + access) == 401 and await verdict("Bearer " + device_access) == 401
              and (await idp.introspection(refresh))["active"] is False)
    await disposal.capture_existing()
    await disposal.reconcile()
    CHECKS.ok("boot reconciliation restores token and device revocation rows and server disablement",
              await verdict("Bearer " + access) == 401 and await verdict("Bearer " + device_access) == 401
              and disposal.blocked(server_id=SERVER))
    policy = await endpoint_plane.managed_policy(await db.fetch_one(
        "SELECT * FROM endpoint_agents WHERE endpoint_id=%s", (DEVICE,)))
    CHECKS.ok("terminated server is absent from rendered managed settings after reconciliation",
              SERVER not in json.dumps(policy, ensure_ascii=False)
              and (await db.fetch_one("SELECT status,lifecycle FROM mcp_servers WHERE id=%s", (SERVER,))) == {
                  "status": "DISABLED", "lifecycle": "RETIRED"})
    claims = authenticate("Bearer " + device_access)[1]
    call = await core.execute_call({"server_id": SERVER, "tool": "get_me", "arguments": {},
                                    "user_token": USER, "transport_claims": claims})
    CHECKS.ok("restored credential reference cannot reach dispatch", call.get("decision") == "Block"
              and not call.get("upstream_attempted") and not call.get("upstream_executed"),
              policy_id=call.get("policy_id"))

    journal = disposal.DIRECTORY / "journal.jsonl"
    original = journal.read_bytes()
    try:
        journal.write_bytes(original[:-1] + b"x")
        CHECKS.ok("tampered disposal journal fails closed for token, device and server", disposal.blocked(jti=next(iter(issued)))
                  and disposal.blocked(server_id=SERVER) and await verdict("Bearer " + control_access) == 401)
    finally:
        journal.write_bytes(original)
    head = disposal.DIRECTORY / "head.json"
    saved_head = head.read_bytes()
    try:
        head.unlink()
        CHECKS.ok("missing signed head fails closed", disposal.blocked(jti=next(iter(issued)))
                  and disposal.blocked(server_id=SERVER) and await verdict("Bearer " + control_access) == 401)
    finally:
        head.write_bytes(saved_head)
    try:
        journal.unlink()
        CHECKS.ok("missing signed disposal list fails closed", disposal.blocked(jti=next(iter(issued)))
                  and disposal.blocked(server_id=SERVER) and await verdict("Bearer " + control_access) == 401)
    finally:
        journal.write_bytes(original)


async def main() -> int:
    signing_keys()
    os.environ["AUTH_PROVIDER"] = "local"
    await apply_schema()
    with isolated_disposal():
        await CHECKS.case("restore_residual", restore_residual())
    return CHECKS.finish()


if __name__ == "__main__":
    run(main)
