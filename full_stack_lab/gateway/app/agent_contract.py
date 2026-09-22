"""Shared Agent-Service/Gateway boundary. Model output never supplies identity."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from fastapi import HTTPException
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field

from . import db

ISSUER = "mcp-governance-synthetic-agent"
AUDIENCE = "mcp-governance-gateway"
TOOL_CALL_AUDIENCE = "mcp-governance-gateway-tool-call"
TOOL_CALL_SCOPE = "mcp:tools/call"
ALGORITHM = "EdDSA"
# 신원의 정본은 principals 관리대장 하나다. 이전 판은 여기 Python 상수에도
# 같은 목록이 있어서, 사람이 늘거나 부서가 바뀔 때마다 배포가 필요했고 둘이
# 갈라지면 "관리대장에는 있는데 로그인은 안 되는 계정"이 생겼다. 서명 검증은
# 토큰이 이 IdP가 발급한 것인지만 보고, 그 주체가 누구인지는 관리대장이 답한다.
FILE_IDS = {"/data/public/notice.txt": "notice-001", "/data/nonimportant/team-note.txt": "work-001", "/data/sensitive/secret.txt": "secret-001"}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Proposal(StrictModel):
    server_id: Literal["file-mcp", "mock-http", "mock-stdio", "github"]
    tool_name: str = Field(min_length=1, max_length=80)
    arguments: dict = Field(default_factory=dict)


class Envelope(StrictModel):
    request_id: UUID
    session_id: UUID
    user_id: str = Field(min_length=1, max_length=80)
    agent_id: Literal["document-agent-test"] = "document-agent-test"
    tool_call_id: UUID
    server_id: str
    tool_name: str
    arguments: dict


def envelope_sha256(envelope: Envelope) -> str:
    """Hash the exact agent-to-gateway envelope, not a model-provided subset."""
    encoded = json.dumps(envelope.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


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


def issue_token(user: dict) -> str:
    now = datetime.now(UTC)
    return jwt.encode({"sub": user["user_id"], "iss": ISSUER, "aud": AUDIENCE,
                       "iat": now, "nbf": now, "exp": now + timedelta(minutes=30), "jti": str(uuid4())},
                      private_key(), algorithm=ALGORITHM)


def issue_agent_assertion(user: dict, envelope: Envelope) -> str:
    """Short-lived proof that Agent Service delegated this exact call for the user."""
    now = datetime.now(UTC)
    return jwt.encode({
        "sub": f"agent:{envelope.agent_id}", "act": {"sub": user["user_id"]},
        "scope": TOOL_CALL_SCOPE, "call_sha256": envelope_sha256(envelope),
        "iss": ISSUER, "aud": TOOL_CALL_AUDIENCE, "iat": now, "nbf": now,
        "exp": now + timedelta(seconds=60), "jti": str(uuid4()),
    }, private_key(), algorithm=ALGORITHM)


def validate_agent_assertion(authorization: str | None, user: dict, envelope: Envelope) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "에이전트 위임 증명이 필요합니다.")
    try:
        claims = jwt.decode(
            authorization[7:], public_key(), algorithms=[ALGORITHM], audience=TOOL_CALL_AUDIENCE,
            issuer=ISSUER, options={"require": ["sub", "act", "scope", "call_sha256", "iss", "aud", "exp", "iat", "nbf", "jti"]},
        )
        actor = claims["act"]
        if (
            claims["sub"] != f"agent:{envelope.agent_id}"
            or not isinstance(actor, dict)
            or actor.get("sub") != user["user_id"]
            or claims["scope"] != TOOL_CALL_SCOPE
            or not isinstance(claims["call_sha256"], str)
            or not hmac.compare_digest(claims["call_sha256"], envelope_sha256(envelope))
        ):
            raise ValueError("agent assertion is not bound to this call")
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise HTTPException(401, "에이전트 위임 증명이 유효하지 않습니다.") from exc


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
}


async def authenticated_user(authorization: str | None) -> dict:
    """The one verified-caller helper every ingress uses.

    `authenticate` proves the token was minted by the synthetic IdP; this adds the
    revocation check so a logout invalidates HTTP, SSE and Agent ingresses alike.

    역할과 계정 상태는 서명된 토큰이 아니라 신원 관리대장에서 읽는다. 토큰 안의
    역할을 믿으면 "관리자 권한을 내렸다"가 그 사람의 토큰이 만료될 때까지 적용되지
    않고, 계정을 끄는 일이 30분짜리 예약 작업이 된다. 정지된 계정은 이미 발급된
    토큰으로도 통과하지 못한다.
    """
    user, claims = authenticate(authorization)
    if await db.fetch_one("SELECT jti FROM agent_revoked_tokens WHERE jti=%s", (claims["jti"],)):
        raise HTTPException(401, "로그아웃된 인증입니다.")
    row = await db.fetch_one(
        """SELECT token, user_id, email, display_name, role, department, job_title, status
           FROM principals WHERE user_id=%s""", (claims["sub"],))
    if not row:
        # 관리대장에서 사라진 신원은 토큰이 유효해도 신원이 아니다.
        raise HTTPException(401, "신원 관리대장에 없는 계정입니다.")
    if row["status"] != "active":
        raise HTTPException(403, ACCOUNT_STATUS_REASON.get(row["status"], "사용할 수 없는 계정입니다."))
    return {**user, "principal": row["token"], "name": row["display_name"],
            "department": row["department"] or "미지정", "job_title": row["job_title"],
            "roles": [row["role"]], "status": row["status"],
            "email": row["email"]}


def schema(properties: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


# 승인된 문서 ID의 단일 정본. ingress 스키마와 API 모델이 각자 목록을 들면 하나만
# 늘어난 날 조용히 갈라진다. main.py가 import 시점에 이 값과 대조한다.
DOCUMENT_IDS = ("notice-001", "work-001", "secret-001", "audit-001")
DOC = {"type": "string", "enum": list(DOCUMENT_IDS)}
TEXT = {"type": "string", "maxLength": 2000}
SCHEMAS = {
    "read_file": schema({"path": {"type": "string", "enum": list(FILE_IDS)}}, ["path"]),
    "read_document": schema({"document_id": DOC}, ["document_id"]),
    "write_document": schema({"document_id": DOC, "content": TEXT}, ["document_id", "content"]),
    "send_external": schema({"document_id": DOC, "destination": {"type": "string", "minLength": 1, "maxLength": 200}, "content": TEXT}, ["document_id", "destination", "content"]),
    "get_current_time": schema({"timezone": {"type": "string", "maxLength": 64}}, ["timezone"]),
    "github_get_file": schema({key: {"type": "string", "minLength": 1, "maxLength": 300} for key in ("owner", "repo", "path")}, ["owner", "repo", "path"]),
}
SERVER_IDS = {"read_file": "file-mcp", "read_document": "mock-http", "write_document": "mock-http", "send_external": "mock-http", "get_current_time": "mock-stdio", "github_get_file": "github"}
DESCRIPTIONS = {
    "read_file": "Read a registered synthetic file path. Legacy Agent-Service compatibility.",
    "read_document": "Read a synthetic document: notice-001 public, work-001 internal, secret-001 important.",
    "write_document": "Write synthetic document content after gateway policy evaluation.",
    "send_external": "Request synthetic external transmission; gateway may restrict, require approval, or block.",
    "get_current_time": "Get current public time from the stdio MCP server.",
    "github_get_file": "Read a GitHub file; blocked until credentials and catalog approval are configured.",
}


def validate_proposal(proposal: Proposal) -> dict:
    if proposal.tool_name not in SCHEMAS or proposal.server_id != SERVER_IDS.get(proposal.tool_name):
        raise ValueError("등록되지 않은 도구 또는 서버 조합입니다.")
    errors = list(Draft202012Validator(SCHEMAS[proposal.tool_name]).iter_errors(proposal.arguments))
    if errors:
        raise ValueError("도구 인자가 승인된 JSON Schema와 일치하지 않습니다.")
    if proposal.tool_name == "read_file":
        return {"tool_name": "read_document", "document_id": FILE_IDS[proposal.arguments["path"]]}
    return {"tool_name": proposal.tool_name, **proposal.arguments}


def model_tools() -> list[dict]:
    return [{"type": "function", "function": {"name": name, "description": DESCRIPTIONS[name], "parameters": value}} for name, value in SCHEMAS.items()]
