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
from authlib.integrations.starlette_client import OAuth
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import Field

from . import db
from .agent_contract import CONSOLE_SCOPE, StrictModel, authenticated_user, issue_token

router = APIRouter()
oauth = OAuth()
HANDOFF_COOKIE = "mcpgw_oidc_handoff"


class RedactCallbackQuery(logging.Filter):
    def filter(self, record):
        args = record.args
        if isinstance(args, tuple) and len(args) == 5 and str(args[2]).split("?", 1)[0] == "/auth/oidc/callback":
            record.args = (*args[:2], "/auth/oidc/callback", *args[3:])
        return True


def settings() -> dict:
    return {"provider": os.getenv("AUTH_PROVIDER", "local"),
            "issuer": os.getenv("OIDC_ISSUER", "").rstrip("/"),
            "client_id": os.getenv("OIDC_CLIENT_ID", "mcp-console"),
            "redirect_uri": os.getenv("OIDC_REDIRECT_URI", ""),
            "label": os.getenv("OIDC_PROVIDER_LABEL", "조직 SSO")}


def configured() -> bool:
    return all(os.getenv(k) for k in ("OIDC_ISSUER", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET",
                                     "OIDC_REDIRECT_URI", "OIDC_SESSION_SECRET"))


def local_login_allowed() -> None:
    if settings()["provider"] == "oidc":
        raise HTTPException(403, "조직 SSO 로그인을 사용하세요. 로컬 비밀번호 인증은 비활성화됐습니다.")


def cipher() -> AESGCM:
    return AESGCM(hashlib.sha256(os.environ["OIDC_SESSION_SECRET"].encode()).digest())


def seal(value: str) -> bytes:
    nonce = secrets.token_bytes(12)
    return nonce + cipher().encrypt(nonce, value.encode(), b"mcpgw-oidc-session")


def unseal(value: bytes) -> str:
    return cipher().decrypt(value[:12], value[12:], b"mcpgw-oidc-session").decode()


def client():
    if not configured():
        raise HTTPException(503, "OIDC 설정이 완료되지 않았습니다.")
    if oauth.create_client("organization") is None:
        config = settings()
        oauth.register("organization", client_id=config["client_id"], client_secret=os.environ["OIDC_CLIENT_SECRET"],
                       server_metadata_url=os.getenv("OIDC_DISCOVERY_URL", config["issuer"]+"/.well-known/openid-configuration"),
                       client_kwargs={"scope": "openid profile", "code_challenge_method": "S256", "timeout": 10,
                                      "trust_env": False})
    return oauth.create_client("organization")


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
        oauth.register("organization", client_id=config["client_id"],
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
            "iss": {"essential": True, "value": config["issuer"]}}, leeway=30)
        identity = result.get("userinfo") or {}
        if identity.get("iss") != config["issuer"] or not identity.get("sub") or not result.get("access_token"):
            raise ValueError("missing validated identity")
        row = await db.fetch_one(
            """SELECT b.id, b.principal, p.user_id, p.status FROM oidc_bindings b
               JOIN principals p ON p.token=b.principal WHERE b.issuer=%s AND b.subject=%s""",
            (config["issuer"], identity["sub"]))
        if not row or row["status"] != "active":
            return RedirectResponse("/login?sso_error=unbound", status_code=303)
        handoff = secrets.token_urlsafe(32)
        lifetime = min(int(result.get("expires_in", 300)), 1800)
        if lifetime <= 0:
            raise ValueError("expired upstream token")
        await db.execute(
            """INSERT INTO oidc_sessions(jti,binding_id,upstream_token,expires_at,handoff_hash,handoff_expires_at)
               VALUES (%s,%s,%s,%s,%s,now()+interval '60 seconds')""",
            (uuid4(), row["id"], seal(result["access_token"]), datetime.now(UTC)+timedelta(seconds=lifetime),
             hashlib.sha256(handoff.encode()).hexdigest()))
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
    await db.execute("DELETE FROM oidc_sessions WHERE expires_at<now()")
    token, _ = issue_token({"user_id": row["user_id"]}, extra={"scope": CONSOLE_SCOPE,
                          "jti": str(row["jti"]), "exp": row["expires_at"], "identity_binding": str(row["binding_id"])})
    response = JSONResponse({"access_token": token, "token_type": "bearer"})
    response.delete_cookie(HANDOFF_COOKIE, path="/auth/oidc/session")
    response.set_cookie("mcpgw_git", token, max_age=300, path="/git", httponly=True, samesite="lax",
                        secure=settings()["redirect_uri"].startswith("https://"))
    return response


async def validate_session(claims: dict) -> None:
    if not claims.get("identity_binding"):
        if settings()["provider"] == "oidc" and not claims.get("device_id"):
            raise HTTPException(401, "SSO로 다시 로그인하세요.")
        return
    row = await db.fetch_one(
        """SELECT s.upstream_token,b.issuer FROM oidc_sessions s JOIN oidc_bindings b ON b.id=s.binding_id
           WHERE s.jti=%s AND s.binding_id=%s AND s.expires_at>now()""", (claims["jti"], claims["identity_binding"]))
    if not row or row["issuer"] != settings()["issuer"]:
        raise HTTPException(401, "SSO 연결이 해제되었거나 만료됐습니다.")
    try:
        metadata = await client().load_server_metadata()
        async with httpx.AsyncClient(timeout=10, trust_env=False) as http:
            response = await http.post(metadata["introspection_endpoint"],
                auth=(settings()["client_id"], os.environ["OIDC_CLIENT_SECRET"]),
                data={"token": unseal(bytes(row["upstream_token"]))})
            response.raise_for_status()
            active = response.json().get("active") is True
    except Exception as exc:
        raise HTTPException(503, "SSO 세션 상태를 확인하지 못해 접근을 보류했습니다.") from exc
    if not active:
        raise HTTPException(401, "조직 SSO 세션이 만료되거나 폐기됐습니다.")


class Binding(StrictModel):
    subject: str = Field(min_length=1, max_length=255)
    principal: str = Field(min_length=1, max_length=150)


async def administrator(authorization):
    user = await authenticated_user(authorization, require_scope=CONSOLE_SCOPE)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "관리자만 SSO 신원을 연결할 수 있습니다.")
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
        raise HTTPException(422, "활성 상태의 등록 사용자 id가 필요합니다.")
    inserted = await db.fetch_one(
        """INSERT INTO oidc_bindings(id,issuer,subject,principal,linked_by) VALUES (%s,%s,%s,%s,%s)
           ON CONFLICT (issuer,subject) DO NOTHING RETURNING id""",
        (uuid4(), settings()["issuer"], body.subject, body.principal, user["principal"]))
    if not inserted:
        raise HTTPException(409, "이미 연결된 SSO 신원입니다. 해제 후 다시 검토하세요.")
    return {"message": "SSO 신원을 연결했습니다. 권한은 기존 사용자 관리대장을 따릅니다."}


@router.delete("/api/identity/bindings/{binding_id}")
async def unbind(binding_id: UUID, authorization: str | None = Header(default=None)):
    await administrator(authorization)
    await db.execute("DELETE FROM oidc_bindings WHERE id=%s", (binding_id,))
    return {"message": "SSO 연결과 해당 세션을 해제했습니다."}
