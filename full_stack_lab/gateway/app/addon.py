"""외부 AI 게이트웨이(LiteLLM·Kong·Portkey 등)가 MCP 도구 호출 직전에 부르는 판정 API (D-191).

판정은 `core.execute_call`의 기존 경로를 그대로 쓰고 upstream 전송만 건너뛴다(`_decide_only`).
신원은 요청의 Bearer 직원 토큰에서만 정한다. 게이트웨이가 주장하는 사용자·키·팀(`asserted`)은 기록만 한다.
전송은 호출한 게이트웨이가 하므로 판정과 전송 사이의 경쟁은 이 경로에서 막지 못한다 — 최종 전송 검사가 필요하면
게이트웨이가 MINT의 `/mcp/<서버>/`를 upstream으로 호출하는 구성을 쓴다.
"""
from __future__ import annotations

from fastapi import HTTPException

from . import core, db, review
from .agent_contract import token_scopes

INGRESS = "ai-gateway-addon"
ALLOWED = {"Allow", "Alert", "Restrict"}


def _employee(user: dict) -> dict:
    """외부 AI 게이트웨이는 직원 PC의 MCP 토큰을 그대로 가져와 부른다. 콘솔 토큰으로는 직원 행세를 할 수 없다."""
    if "mcp" not in token_scopes(user.get("claims") or {}):
        raise HTTPException(403, "애드온 판정에는 직원 PC의 MCP 인증이 필요합니다.")
    return user


async def decide(user: dict, request: dict) -> dict:
    user = _employee(user)
    claims = user.get("claims") or {}
    asserted = {str(k)[:40]: str(v)[:120] for k, v in (request.get("asserted") or {}).items()}
    outcome = await core.execute_call({
        "server_id": request["server_id"], "tool": request["tool"], "arguments": dict(request["arguments"]),
        "_decide_only": True, "user_token": user["principal"], "transport_claims": claims,
        "client": {"ingress": INGRESS, "gateway": request["gateway"], "asserted": asserted,
                   "call_ref": request.get("call_ref"), "token_jti": claims.get("jti"),
                   "oauth_client": claims.get("client_id"), "endpoint": request["server_id"]},
    })
    decision = outcome.get("decision", "Block")
    arguments = outcome.get("effective_arguments")
    return {
        "decision": decision, "allow": decision in ALLOWED and bool(outcome.get("decision_id")),
        "policy_id": outcome.get("policy_id"), "reason": outcome.get("reason"),
        "decision_id": outcome.get("decision_id"),
        # 제한 실행이면 게이트웨이는 이 인자로 보내야 한다. 바뀐 것이 없으면 생략.
        "effective_arguments": arguments if decision in ALLOWED and arguments != request["arguments"] else None,
        "upstream_executed": False, "delivery": "caller",
    }


async def record_result(user: dict, request: dict) -> dict:
    """게이트웨이가 실제로 전송한 뒤의 결과. 판정 행은 고치지 않고 별도 사건으로 덧붙인다."""
    user = _employee(user)
    row = await db.fetch_one("SELECT user_token, client FROM decisions WHERE id=%s", (request["decision_id"],))
    # 다른 직원의 판정에 결과를 붙일 수 없고, 애드온이 만든 판정에만 붙는다.
    if not row or row["user_token"] != user["principal"] or (row["client"] or {}).get("ingress") != INGRESS:
        return {"recorded": False, "reason": "이 계정의 애드온 판정이 아닙니다."}
    event_id = await review.record_event(
        "addon-result", "recorded", "decision", request["decision_id"], user["principal"],
        applicant=user["principal"], reason=request["outcome"],
        scope={"outcome": request["outcome"], "is_error": request["is_error"],
               "result_sha256": request.get("result_sha256"), "result_bytes": request.get("result_bytes"),
               "reported_by": "gateway"})
    return {"recorded": True, "event_id": event_id}
