"""OAuth 2.0 endpoints of the synthetic IdP, for workstation agents.

The metadata, revocation and introspection endpoints are the standard ones the paper
measured on 2,802 providers (RFC 8414 / RFC 7009 / RFC 7662). They are implemented
here faithfully, including the parts that make termination hard:

* revocation answers 200 whether or not the token was valid (RFC 7009 §2.2), so the
  response alone never proves the target's state;
* revoking an access token does not revoke its refresh token (RFC 7009 leaves it at
  MAY), which reproduces experiment E1;
* revoking a refresh token revokes its whole family, including issued access tokens.

The Gateway validates tokens statefully (signature + revocation list + account
ledger), so a revoked token stops working at the Gateway immediately. A verifier that
only checks signatures would keep accepting it until `exp` - see experiments/e1.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, Form, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import Field

from . import db
from .agent_contract import ACCOUNT_STATUS_REASON, ALGORITHM, AUDIENCE, ISSUER, StrictModel, authenticated_user, issue_token, public_key

router = APIRouter()
ISSUER_URL = os.getenv("IDP_ISSUER", "http://agent-service:8000")
ACCESS_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "10"))
REFRESH_HOURS = int(os.getenv("REFRESH_TOKEN_HOURS", "8"))


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _error(code: str, description: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"error": code, "error_description": description}, status_code=status,
                        headers={"Cache-Control": "no-store"})


@router.get("/.well-known/oauth-authorization-server")
async def metadata() -> dict:
    return {
        "issuer": ISSUER_URL,
        "token_endpoint": f"{ISSUER_URL}/oauth/token",
        "revocation_endpoint": f"{ISSUER_URL}/oauth/revoke",
        "introspection_endpoint": f"{ISSUER_URL}/oauth/introspect",
        "grant_types_supported": ["password", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none"],
        "revocation_endpoint_auth_methods_supported": ["none"],
        "introspection_endpoint_auth_methods_supported": ["bearer"],
        "scopes_supported": ["mcp"],
    }


async def _issue(user_row: dict, client_id: str, family_id: uuid.UUID) -> dict:
    user = {"user_id": user_row["user_id"]}
    token, claims = issue_token(user, minutes=ACCESS_MINUTES, client_id=client_id,
                                extra={"sid": str(family_id), "scope": "mcp"})
    await db.execute(
        "INSERT INTO oauth_issued_tokens(jti, user_id, client_id, family_id, expires_at) VALUES (%s,%s,%s,%s,%s)",
        (claims["jti"], user_row["user_id"], client_id, family_id, claims["exp"]))
    refresh = "rt_" + secrets.token_urlsafe(32)
    await db.execute(
        """INSERT INTO oauth_refresh_tokens(id, family_id, user_id, client_id, token_sha256, expires_at)
           VALUES (%s,%s,%s,%s,%s,%s)""",
        (uuid.uuid4(), family_id, user_row["user_id"], client_id, _sha(refresh),
         datetime.now(UTC) + timedelta(hours=REFRESH_HOURS)))
    return {"access_token": token, "token_type": "Bearer", "expires_in": ACCESS_MINUTES * 60,
            "refresh_token": refresh, "scope": "mcp"}


@router.post("/oauth/token")
async def token(request: Request, grant_type: str = Form(...), client_id: str = Form(...),
                username: str | None = Form(None), password: str | None = Form(None),
                refresh_token: str | None = Form(None)):
    client_id = client_id.strip()[:64]
    if not client_id:
        return _error("invalid_client", "client_id가 필요합니다.", 401)
    if grant_type == "password":
        if not username or not password:
            return _error("invalid_request", "username과 password가 필요합니다.")
        from .agent_service import login_allowed, record_failed_login
        caller = request.client.host if request.client else "unknown"
        key = f"{caller}|{username.strip().lower()}"
        if not login_allowed(key):
            return _error("slow_down", "로그인 시도가 너무 많습니다.", 429)
        row = await db.fetch_one(
            """SELECT token, user_id, status, managed_required, (password_hash IS NOT NULL AND password_hash = crypt(%s, password_hash)) AS ok
                 FROM principals WHERE lower(email)=%s""", (password, username.strip().lower()))
        if not row or not row["ok"]:
            record_failed_login(key)
            return _error("invalid_grant", "계정 또는 비밀번호가 올바르지 않습니다.")
        if row["status"] != "active":
            return _error("invalid_grant", ACCOUNT_STATUS_REASON.get(row["status"], "사용할 수 없는 계정입니다."))
        if row["managed_required"]:
            from .endpoint_plane import managed_event
            await managed_event(None, row["token"], "unmanaged-login-denied", {"client_id": client_id})
            return _error("invalid_client", "관리형 단말 등록이 필요합니다. Console의 내 PC 연결에서 키트를 설치하세요.", 403)
        return await _issue(row, client_id, uuid.uuid4())
    if grant_type == "refresh_token":
        if not refresh_token:
            return _error("invalid_request", "refresh_token이 필요합니다.")
        stored = await db.fetch_one("SELECT * FROM oauth_refresh_tokens WHERE token_sha256=%s", (_sha(refresh_token),))
        if not stored or stored["client_id"] != client_id:
            return _error("invalid_grant", "알 수 없는 refresh token입니다.")
        if stored["revoked_at"] or stored["expires_at"] <= datetime.now(UTC):
            return _error("invalid_grant", "폐기되었거나 만료된 refresh token입니다.")
        if stored["rotated_at"]:
            # Reuse of a rotated refresh token means it leaked: revoke the family.
            await _revoke_family(stored["family_id"])
            return _error("invalid_grant", "이미 사용된 refresh token입니다. 이 인가 전체를 폐기했습니다.")
        row = await db.fetch_one("SELECT user_id, status, managed_required FROM principals WHERE user_id=%s", (stored["user_id"],))
        if not row or row["status"] != "active":
            return _error("invalid_grant", "사용할 수 없는 계정입니다.")
        if row["managed_required"]:
            await _revoke_family(stored["family_id"])
            return _error("invalid_grant", "관리형 단말 인증으로 전환했습니다. 기존 사용자 refresh 인증은 폐기했습니다.", 403)
        await db.execute("UPDATE oauth_refresh_tokens SET rotated_at=now() WHERE id=%s", (stored["id"],))
        return await _issue(row, client_id, stored["family_id"])
    return _error("unsupported_grant_type", "password 또는 refresh_token만 지원합니다.")


class DeviceEnrollment(StrictModel):
    enrollment_token: str = Field(min_length=32, max_length=128)
    device_key: str = Field(min_length=43, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    hostname: str = Field(min_length=1, max_length=200)
    local_username: str = Field(pattern=r"^[a-z_][a-z0-9_-]{0,30}$")
    local_uid: int = Field(ge=1000)


@router.post("/oauth/device-enroll", status_code=201)
async def device_enroll(request: DeviceEnrollment):
    from .endpoint_plane import consume_enrollment
    try:
        device = await consume_enrollment(request.enrollment_token, request.device_key, request.hostname,
                                           request.local_username, request.local_uid)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    return {"endpoint_id": device["endpoint_id"], "state": device["managed_state"],
            "owner_token": device["owner_token"], "device_epoch": device["device_epoch"]}


@router.post("/oauth/device-token")
async def device_token(x_endpoint_key: str | None = Header(default=None)):
    from .endpoint_plane import authenticate_device, managed_event, managed_failure, managed_policy
    try:
        device = await authenticate_device(x_endpoint_key, "enforcement")
    except PermissionError as exc:
        return _error("invalid_client", str(exc), 401)
    row = await db.fetch_one("SELECT token,user_id,status,managed_required FROM principals WHERE token=%s", (device["owner_token"],))
    if not row or row["status"] != "active":
        return _error("invalid_grant", "사용할 수 없는 계정입니다.", 403)
    claims = {"device_id": device["endpoint_id"], "device_epoch": device["device_epoch"]}
    failure = await managed_failure(row, claims, mint=True)
    if failure:
        await managed_event(device["endpoint_id"], row["token"], "token-denied", {"reason": failure})
        return _error("invalid_grant", failure, 403)
    policy = await managed_policy(device)
    token, signed = issue_token(row, minutes=5, client_id=device["endpoint_id"],
                               extra={**claims, "scope": "mcp", "device_policy": policy["policy_hash"]})
    await db.execute(
        """INSERT INTO oauth_issued_tokens(jti,user_id,client_id,family_id,expires_at,device_id,device_epoch,device_policy)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        (signed["jti"], row["user_id"], device["endpoint_id"], uuid.uuid4(), signed["exp"],
         device["endpoint_id"], device["device_epoch"], policy["policy_hash"]))
    return JSONResponse({"access_token": token, "token_type": "Bearer", "expires_in": 300, "scope": "mcp"},
                        headers={"Cache-Control": "no-store"})


async def _revoke_family(family_id) -> None:
    await db.execute("UPDATE oauth_refresh_tokens SET revoked_at=COALESCE(revoked_at, now()) WHERE family_id=%s", (family_id,))
    await db.execute(
        """INSERT INTO agent_revoked_tokens(jti, expires_at)
           SELECT jti::uuid, expires_at FROM oauth_issued_tokens WHERE family_id=%s AND expires_at > now()
           ON CONFLICT DO NOTHING""", (family_id,))


@router.post("/oauth/revoke")
async def revoke(token: str = Form(...), token_type_hint: str | None = Form(None)):
    """RFC 7009. Always 200 - including for unknown or already invalid tokens."""
    if token.startswith("rt_"):
        stored = await db.fetch_one("SELECT family_id FROM oauth_refresh_tokens WHERE token_sha256=%s", (_sha(token),))
        if stored:
            await _revoke_family(stored["family_id"])
    else:
        try:
            claims = jwt.decode(token, public_key(), algorithms=[ALGORITHM], audience=AUDIENCE, issuer=ISSUER,
                                options={"verify_exp": False})
            await db.execute("INSERT INTO agent_revoked_tokens(jti, expires_at) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                             (claims["jti"], datetime.fromtimestamp(claims["exp"], UTC)))
        except jwt.PyJWTError:
            pass
    return JSONResponse({}, status_code=200, headers={"Cache-Control": "no-store"})


async def introspection(token: str) -> dict:
    """RFC 7662 view of one token. Used by the endpoint below and by termination
    evidence collection, which records exactly this document."""
    now = datetime.now(UTC)
    if token.startswith("rt_"):
        stored = await db.fetch_one("SELECT * FROM oauth_refresh_tokens WHERE token_sha256=%s", (_sha(token),))
        if not stored or stored["revoked_at"] or stored["rotated_at"] or stored["expires_at"] <= now:
            return {"active": False}
        return {"active": True, "token_type": "refresh_token", "client_id": stored["client_id"],
                "sub": stored["user_id"], "exp": int(stored["expires_at"].timestamp())}
    try:
        claims = jwt.decode(token, public_key(), algorithms=[ALGORITHM], audience=AUDIENCE, issuer=ISSUER)
    except jwt.PyJWTError:
        return {"active": False}
    if await db.fetch_one("SELECT 1 FROM agent_revoked_tokens WHERE jti=%s", (claims["jti"],)):
        return {"active": False}
    row = await db.fetch_one("SELECT token,status,managed_required FROM principals WHERE user_id=%s", (claims["sub"],))
    if not row or row["status"] != "active":
        return {"active": False}
    if "mcp" in str(claims.get("scope", "")).split():
        from .endpoint_plane import managed_failure
        if await managed_failure(row, claims):
            return {"active": False}
    return {"active": True, "token_type": "access_token", "scope": claims.get("scope", ""),
            "client_id": claims.get("client_id"), "sub": claims["sub"], "jti": claims["jti"],
            "exp": claims["exp"], "iat": claims["iat"], "iss": claims["iss"], "aud": claims["aud"]}


async def introspect_jti(jti: str) -> dict:
    """Introspection by identifier, for evidence collection about tokens the
    organisation's own records enumerate (the token value itself is never stored)."""
    row = await db.fetch_one("SELECT * FROM oauth_issued_tokens WHERE jti=%s", (jti,))
    if not row:
        return {"active": False, "jti": jti, "known": False}
    revoked = await db.fetch_one("SELECT 1 FROM agent_revoked_tokens WHERE jti=%s", (jti,))
    active = not revoked and row["expires_at"] > datetime.now(UTC)
    person = await db.fetch_one("SELECT token,status,managed_required FROM principals WHERE user_id=%s", (row["user_id"],))
    if not person or person["status"] != "active":
        active = False
    elif active:
        from .endpoint_plane import managed_failure
        if await managed_failure(person, {"scope": "mcp", **{k: row.get(k) for k in ("device_id", "device_epoch", "device_policy")}}):
            active = False
    return {"active": bool(active), "jti": jti, "known": True, "client_id": row["client_id"],
            "sub": row["user_id"], "exp": int(row["expires_at"].timestamp()), "revoked": bool(revoked)}


@router.post("/oauth/introspect")
async def introspect(token: str = Form(...), authorization: str | None = Header(default=None)):
    """Protected: only an admin (or a resource server acting as one) may ask."""
    user = await authenticated_user(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "조사 엔드포인트는 관리자만 사용할 수 있습니다.")
    return JSONResponse(await introspection(token), headers={"Cache-Control": "no-store"})
