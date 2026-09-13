"""Shared Agent-Service/Gateway boundary. Model output never supplies identity."""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

import jwt
from fastapi import HTTPException
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field

ISSUER = "mcp-governance-synthetic-agent"
AUDIENCE = "mcp-governance-gateway"
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


def signing_key() -> str:
    key = os.getenv("AGENT_JWT_SECRET", "")
    if len(key) < 32:
        raise RuntimeError("AGENT_JWT_SECRET must contain at least 32 characters; run ./demo.sh")
    return key


def issue_token(user: dict) -> str:
    now = datetime.now(UTC)
    return jwt.encode({"sub": user["user_id"], "iss": ISSUER, "aud": AUDIENCE,
                       "iat": now, "nbf": now, "exp": now + timedelta(minutes=30), "jti": str(uuid4())}, signing_key(), algorithm="HS256")


def authenticate(authorization: str | None) -> tuple[dict, dict]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "로그인이 필요합니다.")
    try:
        claims = jwt.decode(authorization[7:], signing_key(), algorithms=["HS256"], audience=AUDIENCE,
                            issuer=ISSUER, options={"require": ["sub", "iss", "aud", "exp", "iat", "nbf", "jti"]})
        user = next(({**u, "email": email} for email, u in IDENTITIES.items() if u["user_id"] == claims["sub"]), None)
        if not user:
            raise ValueError("unknown subject")
        return user, claims
    except (jwt.PyJWTError, ValueError) as exc:
        raise HTTPException(401, "인증이 만료되었거나 유효하지 않습니다.") from exc


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
