"""Shared Agent-Service/Gateway boundary. Model output never supplies identity."""
from __future__ import annotations

import base64
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
ALGORITHM = "EdDSA"
IDENTITIES = {
    "customer@bob.local": {"user_id": "user-customer-001", "principal": "cust-demo", "name": "고객 김민수", "department": "고객", "roles": ["customer"]},
    "miso@bob.local": {"user_id": "user-test-001", "principal": "emp-demo", "name": "김미소", "department": "보안기술팀", "roles": ["employee"]},
    "admin@bob.local": {"user_id": "user-admin-001", "principal": "admin-demo", "name": "관리자 박지훈", "department": "거버넌스팀", "roles": ["admin"]},
}
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


def _key_material(name: str) -> bytes:
    """Ed25519 keys travel as 32 raw base64url bytes so they fit one .env line."""
    try:
        material = base64.urlsafe_b64decode(os.getenv(name, ""))
    except ValueError:
        material = b""
    if len(material) != 32:
        raise RuntimeError(f"{name} must be 32 base64url-encoded bytes; run ./demo.sh")
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


def authenticate(authorization: str | None) -> tuple[dict, dict]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "로그인이 필요합니다.")
    try:
        claims = jwt.decode(authorization[7:], public_key(), algorithms=[ALGORITHM], audience=AUDIENCE,
                            issuer=ISSUER, options={"require": ["sub", "iss", "aud", "exp", "iat", "nbf", "jti"]})
        user = next(({**u, "email": email} for email, u in IDENTITIES.items() if u["user_id"] == claims["sub"]), None)
        if not user:
            raise ValueError("unknown subject")
        return user, claims
    except (jwt.PyJWTError, ValueError) as exc:
        raise HTTPException(401, "인증이 만료되었거나 유효하지 않습니다.") from exc


async def authenticated_user(authorization: str | None) -> dict:
    """The one verified-caller helper every ingress uses.

    `authenticate` proves the token was minted by the synthetic IdP; this adds the
    revocation check so a logout invalidates HTTP, SSE and Agent ingresses alike.
    """
    user, claims = authenticate(authorization)
    if await db.fetch_one("SELECT jti FROM agent_revoked_tokens WHERE jti=%s", (claims["jti"],)):
        raise HTTPException(401, "로그아웃된 인증입니다.")
    return user


def schema(properties: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


DOC = {"type": "string", "enum": ["notice-001", "work-001", "secret-001"]}
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
