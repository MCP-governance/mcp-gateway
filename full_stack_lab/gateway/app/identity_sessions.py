"""Session-side OIDC work that talks to the identity provider: validating, refreshing and ending a console session.

Depends only on oidc_client and the ledger, so oidc can re-export it and agent_contract/idp can use it without an import
back toward oidc."""
from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import HTTPException

from . import db
from .oidc_client import (ADMIN_IDLE, CONSOLE_SCOPE, REFRESH_EARLY_SECONDS, client, http_transport, seal, settings,
                          unseal)


async def _refresh_upstream(claims: dict) -> dict | None:
    """Refresh an admin's online OIDC token under a row lock so rotation is single-use."""
    try:
        metadata = await client().load_server_metadata()
        async with db.transaction() as connection:
            cursor = await connection.execute(
                """SELECT s.upstream_token,s.upstream_refresh_token,s.upstream_expires_at,s.expires_at,
                          cs.last_activity_at,cs.user_id,p.status
                     FROM oidc_sessions s JOIN console_sessions cs ON cs.jti=s.jti
                     JOIN principals p ON p.user_id=cs.user_id
                    WHERE s.jti=%s AND s.binding_id=%s FOR UPDATE OF s""",
                (claims["jti"], claims["identity_binding"]))
            row = await cursor.fetchone()
            now = datetime.now(UTC)
            if (not row or row["status"] != "active" or row["expires_at"] <= now
                    or row["last_activity_at"] <= now - ADMIN_IDLE):
                return None
            upstream_expiry = row["upstream_expires_at"]
            if upstream_expiry and upstream_expiry > now + timedelta(seconds=REFRESH_EARLY_SECONDS):
                return {"upstream_token": row["upstream_token"], "issuer": settings()["issuer"]}
            if not row["upstream_refresh_token"]:
                await connection.execute("UPDATE console_sessions SET expires_at=now() WHERE jti=%s", (claims["jti"],))
                return None
            refresh_token = unseal(bytes(row["upstream_refresh_token"]))
            async with httpx.AsyncClient(timeout=10, trust_env=False, follow_redirects=False,
                                         transport=http_transport()) as http:
                response = await http.post(metadata["token_endpoint"],
                    auth=(settings()["client_id"], os.environ["OIDC_CLIENT_SECRET"]),
                    data={"grant_type": "refresh_token", "refresh_token": refresh_token})
            if response.status_code == 400 and response.json().get("error") == "invalid_grant":
                await connection.execute("UPDATE console_sessions SET expires_at=now() WHERE jti=%s", (claims["jti"],))
                await connection.execute("UPDATE oidc_sessions SET upstream_refresh_token=NULL WHERE jti=%s", (claims["jti"],))
                return None
            response.raise_for_status()
            refreshed = response.json()
            access_token = refreshed.get("access_token")
            expires_in = int(refreshed.get("expires_in", 0))
            if not access_token or expires_in <= 0:
                raise ValueError("invalid token refresh response")
            replacement = refreshed.get("refresh_token") or refresh_token
            await connection.execute(
                """UPDATE oidc_sessions SET upstream_token=%s,upstream_refresh_token=%s,upstream_expires_at=%s
                    WHERE jti=%s""",
                (seal(access_token), seal(replacement), now + timedelta(seconds=expires_in), claims["jti"]))
            return {"upstream_token": seal(access_token), "issuer": settings()["issuer"]}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, "인증 제공자에서 세션을 갱신하지 못해 접근을 보류했습니다.") from exc


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
