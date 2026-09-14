"""Authenticated adapter for the teammate's /tool-call envelope."""
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException
from psycopg.types.json import Jsonb

from . import db
from .agent_contract import Envelope, Proposal, authenticated_user, validate_proposal
from .core import approve_request, canonical_hash, execute_call

router = APIRouter()

# A receipt is claimed before the call and filled in after it. If the worker dies in
# between, the row stays empty and that tool_call_id returns 409 forever with no way
# out. After this window the call is settled as unconfirmed instead - never retried,
# because the whole point of the receipt is that we cannot know whether it ran.
RECEIPT_TIMEOUT = timedelta(minutes=int(os.getenv("RECEIPT_TIMEOUT_MINUTES", "5")))


@router.post("/tool-call")
async def tool_call(request: Envelope, authorization: str | None = Header(default=None)):
    user = await authenticated_user(authorization)
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
        if datetime.now(UTC) - prior["created_at"] < RECEIPT_TIMEOUT:
            raise HTTPException(409, "이미 실행을 시작한 호출입니다. 증적을 확인하세요.")
        settled = {
            "decision": "Block",
            "policy_id": "MCP-RECEIPT-001",
            "reason": "이전 실행이 응답 없이 중단됐습니다. upstream 실행 여부를 확인할 수 없어 재실행하지 않습니다. 독립 효과 로그를 확인하세요.",
            "upstream_executed": None,
            "execution_status": "unknown",
            "tool_call_id": str(request.tool_call_id),
            "session_id": str(request.session_id),
        }
        await db.execute(
            "UPDATE agent_gateway_receipts SET response=%s WHERE id=%s AND response IS NULL",
            (Jsonb(settled), request.tool_call_id),
        )
        current = await db.fetch_one("SELECT response FROM agent_gateway_receipts WHERE id=%s", (request.tool_call_id,))
        return {**(current["response"] if current and current["response"] else settled), "replayed": True}
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
    user = await authenticated_user(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "관리자 계정이 필요합니다.")
    try:
        return await approve_request(str(approval_id), user["principal"])
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
