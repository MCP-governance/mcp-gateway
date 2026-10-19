"""OAuth audience, scope, expiry, revocation and signature negatives on PostgreSQL.

Run through termination_dispatch_lab.sh. Tokens come from the product IdP, and
the MCP facade's actual caller gate rejects them before execute_call can dispatch.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
from fastapi import HTTPException
from starlette.requests import Request

from app import db, idp, mcp_facade
from app.agent_contract import ALGORITHM, AUDIENCE, ISSUER, private_key
from termination_lab_support import Checks, add_principal, apply_schema, isolated_disposal, run, signing_keys

CHECKS = Checks("OAuth negatives before MCP dispatch (PostgreSQL)")
REQUEST = Request({"type": "http", "client": ("127.0.0.1", 1), "headers": []})
CLIENT = "oauth-negative-lab"
PRINCIPAL = "oauth-negative"


async def login() -> dict:
    result = await idp.token(REQUEST, grant_type="password", client_id=CLIENT,
                             username=f"{PRINCIPAL}@bob.local", password="lab-password", refresh_token=None)
    assert isinstance(result, dict), result
    return result


def signed(claims: dict) -> str:
    return jwt.encode(claims, private_key(), algorithm=ALGORITHM)


def context(token: str):
    return SimpleNamespace(request=SimpleNamespace(
        headers={"authorization": "Bearer " + token}, scope={"path": "/mcp/oauth-negative/"}))


async def intent_count() -> int:
    row = await db.fetch_one("SELECT count(*) AS n FROM dispatch_intents WHERE user_token=%s", (PRINCIPAL,))
    return row["n"]


async def accepted(token: str) -> bool:
    try:
        user = await mcp_facade._caller(context(token))
        return user["principal"] == PRINCIPAL
    except HTTPException:
        return False


async def refused_before_dispatch(name: str, token: str) -> None:
    before = await intent_count()
    status = 200
    try:
        await mcp_facade._caller(context(token))
    except HTTPException as exc:
        status = exc.status_code
    after = await intent_count()
    CHECKS.ok(f"{name}: MCP caller refuses before dispatch intent", status in {401, 403} and after == before == 0,
              status=status, intents=after)


async def main() -> int:
    signing_keys()
    os.environ["AUTH_PROVIDER"] = "local"
    await apply_schema()
    await add_principal(PRINCIPAL)
    await db.execute("UPDATE principals SET password_hash=crypt('lab-password', gen_salt('bf', 4)) WHERE token=%s",
                     (PRINCIPAL,))
    with isolated_disposal():
        normal = await login()
        CHECKS.ok("product IdP normal token reaches the MCP caller gate", await accepted(normal["access_token"]))
        CHECKS.ok("normal authentication creates no dispatch intent without a tools/call", await intent_count() == 0)

        claims = jwt.decode(normal["access_token"], options={"verify_signature": False})
        await refused_before_dispatch("other audience", signed({**claims, "aud": "another-resource"}))
        await refused_before_dispatch("missing mcp scope", signed({**claims, "scope": "console"}))
        # A real console session (as agent_service.login issues it) passes validate_session; only the
        # mcp scope requirement keeps it off the MCP ingress (D-153).
        from app.agent_contract import issue_token
        row = await db.fetch_one("SELECT * FROM principals WHERE token=%s", (PRINCIPAL,))
        session_user = {"user_id": row["user_id"], "principal": row["token"], "name": row["display_name"],
                        "department": row["department"] or "미지정", "roles": [row["role"]], "email": row["email"]}
        console_token, console_claims = issue_token(session_user, minutes=30, extra={"scope": "console"})
        await db.execute("INSERT INTO console_sessions(jti,user_id,expires_at) VALUES (%s,%s,now()+interval '30 minutes')",
                         (console_claims["jti"], row["user_id"]))
        await refused_before_dispatch("real console session token", console_token)
        await refused_before_dispatch("expired token",
                                      signed({**claims, "exp": datetime.now(UTC) - timedelta(seconds=30)}))

        revoked = await login()
        await idp.revoke(revoked["access_token"], "access_token")
        await refused_before_dispatch("revoked jti", revoked["access_token"])

        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        other_key = Ed25519PrivateKey.generate()
        await refused_before_dispatch("different issuer signing key", jwt.encode(claims, other_key, algorithm=ALGORITHM))
        await refused_before_dispatch("alg none", jwt.encode(claims, key=None, algorithm="none"))
        await refused_before_dispatch("HS256 instead of EdDSA", jwt.encode(claims, "untrusted-hs256-key", algorithm="HS256"))

        CHECKS.ok("product issuer and audience constants remain explicit",
                  ISSUER == "mcp-governance-synthetic-agent" and AUDIENCE == "mcp-governance-gateway")
    return CHECKS.finish()


if __name__ == "__main__":
    run(main)
