"""Session-side OIDC work that talks to the identity provider: refreshing an admin's upstream token.

Depends only on oidc_client and the ledger, so oidc can re-export it without an import back."""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import HTTPException

from . import db
from .oidc_client import ADMIN_IDLE, REFRESH_EARLY_SECONDS, client, http_transport, seal, settings, unseal


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
