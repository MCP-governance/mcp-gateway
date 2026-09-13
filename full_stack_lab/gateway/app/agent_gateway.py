"""Authenticated adapter for the teammate's /tool-call envelope."""
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException
from psycopg.types.json import Jsonb

from . import db
from .agent_contract import Envelope, Proposal, authenticate, validate_proposal
from .core import approve_request, canonical_hash, execute_call

router = APIRouter()


async def identity(authorization):
    user, claims = authenticate(authorization)
    if await db.fetch_one("SELECT jti FROM agent_revoked_tokens WHERE jti=%s", (claims["jti"],)):
        raise HTTPException(401, "로그아웃된 인증입니다.")
    return user


@router.post("/tool-call")
async def tool_call(request: Envelope, authorization: str | None = Header(default=None)):
    user = await identity(authorization)
    if request.user_id != user["user_id"]:
        raise HTTPException(403, "요청자와 서명된 사용자 정보가 다릅니다.")
    try:
        payload = validate_proposal(Proposal(server_id=request.server_id, tool_name=request.tool_name, arguments=request.arguments))
    except ValueError as exc:
        raise HTTPException(422, "등록된 서버·도구·JSON Schema를 확인하세요.") from exc
    fingerprint = canonical_hash(request.model_dump(mode="json"))
    prior = await db.fetch_one("SELECT * FROM agent_gateway_receipts WHERE id=%s", (request.tool_call_id,))
    if prior:
        if prior["user_id"] != user["user_id"] or prior["fingerprint"] != fingerprint:
            raise HTTPException(409, "Tool Call ID가 다른 내용에 사용됐습니다.")
        if prior["response"] is not None:
            return {**prior["response"], "replayed": True}
        raise HTTPException(409, "이미 실행을 시작한 호출입니다. 증적을 확인하세요.")
    claimed = await db.fetch_one("INSERT INTO agent_gateway_receipts(id,user_id,fingerprint) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id", (request.tool_call_id, user["user_id"], fingerprint))
    if not claimed:
        raise HTTPException(409, "같은 호출이 처리 중입니다.")
    payload.update(user_token=user["principal"], _agent_context={"request_id": str(request.request_id), "session_id": str(request.session_id), "tool_call_id": str(request.tool_call_id), "user_id": user["user_id"], "agent_id": request.agent_id})
    outcome = await execute_call(payload)
    outcome.update(tool_call_id=str(request.tool_call_id), session_id=str(request.session_id), execution_status="success" if outcome["upstream_executed"] else "unknown" if outcome.get("upstream_attempted") else "blocked")
    await db.execute("UPDATE agent_gateway_receipts SET response=%s WHERE id=%s", (Jsonb(outcome), request.tool_call_id))
    return outcome


@router.post("/agent/approvals/{approval_id}/approve")
async def approve(approval_id: UUID, authorization: str | None = Header(default=None)):
    user = await identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "관리자 계정이 필요합니다.")
    try:
        return await approve_request(str(approval_id), user["principal"])
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
