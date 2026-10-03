"""Shared Agent-Service/Gateway boundary. Model output never supplies identity."""
from __future__ import annotations

import base64
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict

from . import db

ISSUER = "mcp-governance-synthetic-agent"
AUDIENCE = "mcp-governance-gateway"
ALGORITHM = "EdDSA"
# 신원의 정본은 principals 관리대장 하나다. 이전 판은 여기 Python 상수에도
# 같은 목록이 있어서, 사람이 늘거나 부서가 바뀔 때마다 배포가 필요했고 둘이
# 갈라지면 "관리대장에는 있는데 로그인은 안 되는 계정"이 생겼다. 서명 검증은
# 토큰이 이 IdP가 발급한 것인지만 보고, 그 주체가 누구인지는 관리대장이 답한다.


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _key_material(name: str) -> bytes:
    """Ed25519 keys travel as 32 raw base64url bytes so they fit one .env line."""
    try:
        material = base64.urlsafe_b64decode(os.getenv(name, ""))
    except ValueError:
        material = b""
    if len(material) != 32:
        raise RuntimeError(f"{name} must be 32 base64url-encoded bytes; run ./console.sh")
    return material


def private_key() -> Ed25519PrivateKey:
    """Held only by the synthetic identity provider (Agent Service)."""
    return Ed25519PrivateKey.from_private_bytes(_key_material("AGENT_JWT_PRIVATE_KEY"))


def public_key() -> Ed25519PublicKey:
    """Held by every verifier.

    With a shared HS256 secret each verifier could also mint tokens, so the Gateway
    could forge an admin session for itself and "Agent 인증과 Gateway는 별도 신뢰
    경계" was a claim the key material contradicted. A verifier that holds only this
    cannot sign anything.
    """
    return Ed25519PublicKey.from_public_bytes(_key_material("AGENT_JWT_PUBLIC_KEY"))


def issue_token(user: dict, minutes: int = 30, client_id: str = "console",
                extra: dict | None = None) -> tuple[str, dict]:
    """A self-contained access token. Returns (jwt, claims) so the issuer can record
    what it issued - verification never needs that record, which is exactly the
    paper's E1 property: a verifier that only checks signatures keeps accepting a
    revoked token until it expires."""
    now = datetime.now(UTC)
    claims = {"sub": user["user_id"], "iss": ISSUER, "aud": AUDIENCE, "client_id": client_id,
              "iat": now, "nbf": now, "exp": now + timedelta(minutes=minutes), "jti": str(uuid4()),
              "scope": "console" if client_id == "console" else "mcp",
              **(extra or {})}
    return jwt.encode(claims, private_key(), algorithm=ALGORITHM), claims


def authenticate(authorization: str | None) -> tuple[dict, dict]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "로그인이 필요합니다.")
    try:
        claims = jwt.decode(authorization[7:], public_key(), algorithms=[ALGORITHM], audience=AUDIENCE,
                            issuer=ISSUER, options={"require": ["sub", "iss", "aud", "exp", "iat", "nbf", "jti"]})
        subject = claims["sub"]
        if not isinstance(subject, str) or not subject:
            raise ValueError("unknown subject")
        # 여기서는 "이 토큰을 이 IdP가 발급했다"까지만 말한다. 역할·부서·계정
        # 상태는 authenticated_user()가 관리대장에서 읽는다.
        return {"user_id": subject}, claims
    except (jwt.PyJWTError, ValueError) as exc:
        raise HTTPException(401, "인증이 만료되었거나 유효하지 않습니다.") from exc


ACCOUNT_STATUS_REASON = {
    "disabled": "사용 중지된 계정입니다.",
    "locked": "잠긴 계정입니다. 관리자에게 문의하세요.",
    "deleted": "삭제된 계정입니다.",
}

# What a token was issued for. `mcp` tokens are what `bob-sso` keeps on the employee's
# PC for the harnesses, so they sit at rest in a file a local process can read; `console`
# tokens come from an interactive sign-in and last 30 minutes. They authenticate the same
# person, which is why the administrative APIs ask for the second: otherwise anything that
# could read the token file could also approve a high-risk call in that person's name.
# Missing scope never grants an administrative capability; old sessions sign in again.
CONSOLE_SCOPE = "console"


def token_scopes(claims: dict) -> set[str]:
    value = claims.get("scope")
    return set(value.split()) if isinstance(value, str) else set()


async def authenticated_user(authorization: str | None, require_scope: str | None = None, *, require_mcp: bool = False) -> dict:
    """The one verified-caller helper every ingress uses.

    `authenticate` proves the token was minted by the synthetic IdP; this adds the
    revocation check so a logout invalidates HTTP, SSE and Agent ingresses alike.

    역할과 계정 상태는 서명된 토큰이 아니라 신원 관리대장에서 읽는다. 토큰 안의
    역할을 믿으면 "관리자 권한을 내렸다"가 그 사람의 토큰이 만료될 때까지 적용되지
    않고, 계정을 끄는 일이 30분짜리 예약 작업이 된다. 정지된 계정은 이미 발급된
    토큰으로도 통과하지 못한다.
    """
    user, claims = authenticate(authorization)
    from .oidc import validate_session
    await validate_session(claims)
    if require_scope and require_scope not in token_scopes(claims):
        raise HTTPException(403, "이 작업에는 Console 로그인으로 받은 인증이 필요합니다. "
                                 "하네스에 배포된 MCP 토큰으로는 할 수 없습니다.")
    if await db.fetch_one("SELECT jti FROM agent_revoked_tokens WHERE jti=%s", (claims["jti"],)):
        raise HTTPException(401, "로그아웃된 인증입니다.")
    row = await db.fetch_one(
        """SELECT token, user_id, email, display_name, role, department, job_title, status, managed_required
           FROM principals WHERE user_id=%s""", (claims["sub"],))
    if not row:
        # 관리대장에서 사라진 신원은 토큰이 유효해도 신원이 아니다.
        raise HTTPException(401, "신원 관리대장에 없는 계정입니다.")
    if row["status"] != "active":
        # The header lets the Console end a session whose account was just switched off, instead
        # of leaving the shell open with every panel failing.
        raise HTTPException(403, ACCOUNT_STATUS_REASON.get(row["status"], "사용할 수 없는 계정입니다."),
                            headers={"X-Account-Status": row["status"]})
    if require_mcp or "mcp" in token_scopes(claims):
        from .endpoint_plane import managed_failure
        failure = await managed_failure(row, claims)
        if failure:
            raise HTTPException(403, failure, headers={"X-Endpoint-Policy": "ENDPOINT-MANAGED-001"})
    return {**user, "principal": row["token"], "name": row["display_name"],
            "department": row["department"] or "미지정", "job_title": row["job_title"],
            "roles": [row["role"]], "status": row["status"],
            "managed_required": row["managed_required"],
            "email": row["email"], "claims": claims}
