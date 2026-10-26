"""Authlib handles OIDC; the local ledger still owns roles and device policy."""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import Field

from . import db
from .agent_contract import StrictModel, authenticated_user, issue_token
from .identity_sessions import _refresh_upstream
from .oidc_client import (ADMIN_IDLE, ADMIN_MAX, CONSOLE_SCOPE, HANDOFF_COOKIE, REFRESH_EARLY_SECONDS,
                          TOKEN_LOGOUT_GRACE, PinnedOAuthApp, PinnedOAuthClient, cipher, client, configured,
                          http_transport, oauth, seal, settings, unseal)

# The client wiring moved to oidc_client; these names stay importable from here.
__all__ = ["ADMIN_IDLE", "ADMIN_MAX", "CONSOLE_SCOPE", "HANDOFF_COOKIE", "REFRESH_EARLY_SECONDS", "TOKEN_LOGOUT_GRACE",
           "PinnedOAuthApp", "PinnedOAuthClient", "cipher", "client", "configured", "http_transport", "oauth",
           "seal", "settings", "unseal"]

router = APIRouter()


class RedactCallbackQuery(logging.Filter):
    def filter(self, record):
        args = record.args
        if isinstance(args, tuple) and len(args) == 5 and str(args[2]).split("?", 1)[0] == "/auth/oidc/callback":
            record.args = (*args[:2], "/auth/oidc/callback", *args[3:])
        return True


def local_login_allowed() -> None:
    if settings()["provider"] == "oidc":
        raise HTTPException(403, "조직 SSO 로그인을 사용하세요. 로컬 비밀번호 인증은 비활성화됐습니다.")


def install(app) -> None:
    from starlette.middleware.sessions import SessionMiddleware
    config = settings()
    logging.getLogger("uvicorn.access").addFilter(RedactCallbackQuery())
    if config["provider"] not in {"local", "oidc"}:
        raise RuntimeError("AUTH_PROVIDER must be local or oidc")
    if configured():
        for name in ("issuer", "redirect_uri"):
            url = urlsplit(config[name])
            loopback = url.hostname in {"localhost", "127.0.0.1", "::1"}
            if url.scheme != "https" and not (url.scheme == "http" and loopback):
                raise RuntimeError(f"OIDC {name} must use HTTPS (HTTP is loopback-only)")
        if len(os.environ["OIDC_SESSION_SECRET"]) < 32:
            raise RuntimeError("OIDC_SESSION_SECRET must have at least 32 characters")
        oauth.register("organization", client_cls=PinnedOAuthApp, client_id=config["client_id"],
                       client_secret=os.environ["OIDC_CLIENT_SECRET"],
                       server_metadata_url=os.getenv("OIDC_DISCOVERY_URL", config["issuer"] + "/.well-known/openid-configuration"),
                       client_kwargs={"scope": "openid profile", "code_challenge_method": "S256", "timeout": 10,
                                      "trust_env": False})
        app.add_middleware(SessionMiddleware, secret_key=os.environ["OIDC_SESSION_SECRET"],
                           session_cookie="mcpgw_oidc_state", max_age=300, same_site="lax",
                           https_only=config["redirect_uri"].startswith("https://"))
    app.include_router(router)


@router.get("/auth/provider")
async def provider():
    config = settings()
    return {"provider": config["provider"], "label": config["label"], "configured": configured(),
            "login_url": "/auth/oidc/login" if config["provider"] == "oidc" else None}


@router.get("/auth/oidc/login")
async def login(request: Request):
    if settings()["provider"] != "oidc":
        raise HTTPException(404, "조직 SSO가 활성화되지 않았습니다.")
    try:
        return await client().authorize_redirect(request, settings()["redirect_uri"])
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, "조직 인증 서비스에 연결할 수 없습니다.") from exc


@router.get("/auth/oidc/callback")
async def callback(request: Request):
    config = settings()
    if config["provider"] != "oidc":
        raise HTTPException(404, "조직 SSO가 활성화되지 않았습니다.")
    try:
        result = await client().authorize_access_token(request, claims_options={
            "iss": {"essential": True, "value": config["issuer"]},
            # OIDC Core 3.1.3.7: aud must contain this client. Authlib only checks azp unless asked.
            "aud": {"essential": True, "value": config["client_id"]}}, leeway=30)
        identity = result.get("userinfo") or {}
        if identity.get("iss") != config["issuer"] or not identity.get("sub") or not result.get("access_token"):
            raise ValueError("missing validated identity")
        row = await db.fetch_one(
            """SELECT b.id, b.principal, p.user_id, p.status, p.role FROM oidc_bindings b
               JOIN principals p ON p.token=b.principal WHERE b.issuer=%s AND b.subject=%s""",
            (config["issuer"], identity["sub"]))
        if not row or row["status"] != "active":
            return RedirectResponse("/login?sso_error=unbound", status_code=303)
        refresh_token = result.get("refresh_token")
        if row["role"] == "admin" and not refresh_token:
            request.session.clear()
            return RedirectResponse("/login?sso_error=refresh_unavailable", status_code=303)
        handoff = secrets.token_urlsafe(32)
        upstream_lifetime = int(result.get("expires_in", 300))
        if upstream_lifetime <= 0:
            raise ValueError("expired upstream token")
        now = datetime.now(UTC)
        lifetime = int(ADMIN_MAX.total_seconds()) if row["role"] == "admin" else min(upstream_lifetime, 1800)
        expires_at = now + timedelta(seconds=lifetime)
        upstream_expires_at = now + timedelta(seconds=upstream_lifetime)
        jti = uuid4()
        async with db.transaction() as connection:
            await connection.execute(
                """INSERT INTO oidc_sessions(jti,binding_id,upstream_token,expires_at,handoff_hash,handoff_expires_at,
                       upstream_refresh_token,upstream_expires_at)
                   VALUES (%s,%s,%s,%s,%s,now()+interval '60 seconds',%s,%s)""",
                (jti, row["id"], seal(result["access_token"]), expires_at,
                 hashlib.sha256(handoff.encode()).hexdigest(), seal(refresh_token) if refresh_token else None,
                 upstream_expires_at))
            await connection.execute(
                "INSERT INTO console_sessions(jti,user_id,expires_at) VALUES (%s,%s,%s)",
                (jti, row["user_id"], expires_at))
        request.session.clear()
        response = RedirectResponse("/login?sso=complete", status_code=303)
        response.set_cookie(HANDOFF_COOKIE, handoff, max_age=60, path="/auth/oidc/session", httponly=True,
                            secure=config["redirect_uri"].startswith("https://"), samesite="strict")
        return response
    except HTTPException:
        raise
    except Exception:
        # Provider errors may carry tokens; never echo/log their message.
        request.session.clear()
        return RedirectResponse("/login?sso_error=invalid", status_code=303)


@router.post("/auth/oidc/session")
async def session(request: Request):
    handoff = request.cookies.get(HANDOFF_COOKIE, "")
    row = await db.fetch_one(
        """UPDATE oidc_sessions s SET handoff_hash=NULL FROM oidc_bindings b, principals p
           WHERE s.binding_id=b.id AND b.principal=p.token AND p.status='active'
             AND s.handoff_hash=%s AND s.handoff_expires_at>now() AND s.expires_at>now()
           RETURNING s.jti,s.binding_id,s.expires_at,p.user_id""", (hashlib.sha256(handoff.encode()).hexdigest(),))
    if not handoff or not row:
        raise HTTPException(401, "SSO 로그인 결과가 없거나 이미 사용됐습니다.")
    await db.execute("DELETE FROM console_sessions WHERE expires_at<now()")
    await db.execute("DELETE FROM oidc_sessions WHERE expires_at<now()")
    token, _ = issue_token({"user_id": row["user_id"]}, extra={"scope": CONSOLE_SCOPE,
                          "jti": str(row["jti"]), "exp": row["expires_at"] + TOKEN_LOGOUT_GRACE,
                          "identity_binding": str(row["binding_id"])})
    response = JSONResponse({"access_token": token, "token_type": "bearer"})
    response.delete_cookie(HANDOFF_COOKIE, path="/auth/oidc/session")
    response.set_cookie("mcpgw_git", token, max_age=300, path="/git", httponly=True, samesite="lax",
                        secure=settings()["redirect_uri"].startswith("https://"))
    return response


async def validate_session(claims: dict) -> None:
    scopes = claims.get("scope", "")
    if not isinstance(scopes, str) or CONSOLE_SCOPE not in scopes.split():
        if settings()["provider"] == "oidc" and not claims.get("device_id"):
            raise HTTPException(401, "SSO로 다시 로그인하세요.")
        return
    if not claims.get("jti") or not claims.get("sub"):
        raise HTTPException(401, "로그인 세션이 만료됐습니다.")
    session = await db.fetch_one(
        """SELECT cs.expires_at,cs.last_activity_at,cs.user_id,p.role,p.status
             FROM console_sessions cs JOIN principals p ON p.user_id=cs.user_id
            WHERE cs.jti=%s AND cs.user_id=%s""", (claims["jti"], claims["sub"]))
    now = datetime.now(UTC)
    if not session or session["status"] != "active" or session["expires_at"] <= now:
        if session:
            await end_session(claims)
        raise HTTPException(401, "로그인 세션이 만료됐습니다.")
    if session["role"] == "admin" and session["last_activity_at"] <= now - ADMIN_IDLE:
        await end_session(claims)
        raise HTTPException(401, "30분 동안 활동이 없어 로그아웃됐습니다.")
    if not claims.get("identity_binding"):
        if settings()["provider"] == "oidc":
            raise HTTPException(401, "SSO로 다시 로그인하세요.")
        return
    row = await db.fetch_one(
        """SELECT s.upstream_token,s.upstream_refresh_token,s.upstream_expires_at,b.issuer
             FROM oidc_sessions s JOIN oidc_bindings b ON b.id=s.binding_id
            WHERE s.jti=%s AND s.binding_id=%s AND s.expires_at>now()""",
        (claims["jti"], claims["identity_binding"]))
    if not row or row["issuer"] != settings()["issuer"]:
        raise HTTPException(401, "SSO 연결이 해제되었거나 만료됐습니다.")
    upstream_expiry = row["upstream_expires_at"]
    if (session["role"] == "admin" and
            (not upstream_expiry or upstream_expiry <= now + timedelta(seconds=REFRESH_EARLY_SECONDS))):
        refreshed = await _refresh_upstream(claims)
        if not refreshed:
            await end_session(claims)
            raise HTTPException(401, "SSO 세션이 만료됐습니다. 다시 로그인하세요.")
        row = refreshed
    try:
        metadata = await client().load_server_metadata()
        async with httpx.AsyncClient(timeout=10, trust_env=False, follow_redirects=False,
                                     transport=http_transport()) as http:
            response = await http.post(metadata["introspection_endpoint"],
                auth=(settings()["client_id"], os.environ["OIDC_CLIENT_SECRET"]),
                data={"token": unseal(bytes(row["upstream_token"]))})
            response.raise_for_status()
            active = response.json().get("active") is True
    except Exception as exc:
        raise HTTPException(503, "SSO 세션 상태를 확인하지 못해 접근을 보류했습니다.") from exc
    if not active:
        await end_session(claims)
        raise HTTPException(401, "조직 SSO 세션이 만료되거나 폐기됐습니다.")


async def touch_session(claims: dict) -> None:
    if not isinstance(claims.get("scope"), str) or CONSOLE_SCOPE not in claims["scope"].split():
        return
    changed = await db.execute(
        """UPDATE console_sessions SET last_activity_at=now()
             WHERE jti=%s AND user_id=%s AND expires_at>now()
               AND last_activity_at>now()-interval '30 minutes'""",
        (claims["jti"], claims["sub"]))
    if changed != 1:
        raise HTTPException(401, "로그인 세션이 만료됐습니다.")


async def end_session(claims: dict) -> None:
    jti = claims.get("jti")
    row = None
    if claims.get("identity_binding"):
        row = await db.fetch_one(
            """SELECT s.upstream_token,s.upstream_refresh_token,b.issuer
                 FROM oidc_sessions s JOIN oidc_bindings b ON b.id=s.binding_id
                WHERE s.jti=%s AND s.binding_id=%s""", (jti, claims["identity_binding"]))
    await db.execute("DELETE FROM console_sessions WHERE jti=%s", (jti,))
    await db.execute("DELETE FROM oidc_sessions WHERE jti=%s", (jti,))
    if not row:
        return
    try:
        metadata = await client().load_server_metadata()
        endpoint = metadata.get("revocation_endpoint")
        if not endpoint:
            return
        async with httpx.AsyncClient(timeout=10, trust_env=False, follow_redirects=False,
                                     transport=http_transport()) as http:
            for encrypted, token_type in ((row["upstream_refresh_token"], "refresh_token"),
                                          (row["upstream_token"], "access_token")):
                if not encrypted:
                    continue
                await http.post(endpoint, auth=(settings()["client_id"], os.environ["OIDC_CLIENT_SECRET"]),
                    data={"token": unseal(bytes(encrypted)), "token_type_hint": token_type})
    except Exception:
        logging.getLogger(__name__).warning("SSO token revocation failed during logout")


async def end_binding_sessions(binding_id: UUID) -> None:
    rows = await db.fetch_all("SELECT jti FROM oidc_sessions WHERE binding_id=%s", (binding_id,))
    for row in rows:
        await end_session({"jti": row["jti"], "identity_binding": str(binding_id)})


class Binding(StrictModel):
    subject: str = Field(min_length=1, max_length=255)
    principal: str = Field(min_length=1, max_length=150)


async def administrator(authorization):
    user = await authenticated_user(authorization, require_scope=CONSOLE_SCOPE)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "관리자만 SSO 계정을 연결할 수 있습니다.")
    return user


@router.get("/api/identity")
async def identity(authorization: str | None = Header(default=None)):
    await administrator(authorization)
    config = settings()
    return {**config, "configured": configured(), "bindings": await db.fetch_all(
        "SELECT id,issuer,subject,principal,linked_by,linked_at FROM oidc_bindings ORDER BY linked_at DESC")}


@router.post("/api/identity/bindings", status_code=201)
async def bind(body: Binding, authorization: str | None = Header(default=None)):
    user = await administrator(authorization)
    if not configured():
        raise HTTPException(409, "운영자가 먼저 OIDC 공급자를 설정해야 합니다.")
    if not await db.fetch_one("SELECT token FROM principals WHERE token=%s AND status='active'", (body.principal,)):
        raise HTTPException(422, "활성 사용자 ID가 필요합니다.")
    inserted = await db.fetch_one(
        """INSERT INTO oidc_bindings(id,issuer,subject,principal,linked_by) VALUES (%s,%s,%s,%s,%s)
           ON CONFLICT (issuer,subject) DO NOTHING RETURNING id""",
        (uuid4(), settings()["issuer"], body.subject, body.principal, user["principal"]))
    if not inserted:
        raise HTTPException(409, "이미 연결된 SSO 계정입니다.")
    return {"message": "SSO 계정을 연결했습니다."}


@router.delete("/api/identity/bindings/{binding_id}")
async def unbind(binding_id: UUID, authorization: str | None = Header(default=None)):
    await administrator(authorization)
    await end_binding_sessions(binding_id)
    await db.execute("DELETE FROM oidc_bindings WHERE id=%s", (binding_id,))
    return {"message": "SSO 연결을 해제했습니다."}
