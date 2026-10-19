"""Pure, conservative projections of call evidence; no ledger updates or provider text retained."""
from __future__ import annotations

import re


def outcome_axes(event: dict) -> dict:
    """Keep policy permission, an MCP answer and independent effects separate."""
    executed = bool(event.get("upstream_executed"))
    attempted = bool(event.get("upstream_attempted")) or executed
    policy = event.get("policy_id") or ""
    verdict = event.get("decision")
    preview = event.get("result_evidence") or event.get("result_preview") or {}
    result = event.get("result")
    status = event.get("upstream_http_status")
    connected = event.get("upstream_connected") or attempted
    connection = "연결 성공" if connected else "연결 실패" if policy == "MCP-UPSTREAM-001" else "미시도"

    if verdict == "Approval":
        decision = "승인 대기"
    elif verdict == "Block" and (event.get("control_failure") or policy.startswith("P-CONTROL-") or policy in {
            "P-DATA-INSPECTION-001", "MCP-CATALOG-001", "INPUT_CONTRACT", "POLICY_BUNDLE"}):
        decision = "통제 장애 차단"
    elif policy == "MCP-UPSTREAM-001":
        # This verdict replaces the permission after a transport failure.
        decision = "허용"
    elif verdict == "Block":
        decision = "정책 거부"
    else:
        decision = "허용" if verdict in {"Allow", "Alert", "Restrict"} else "미확인"

    withheld = (preview.get("disposition") == "withheld"
                or event.get("response_disposition") == "withheld" or policy == "MCP-OUTPUT-001")
    # 401 authentication, 403 access refused, 429 rate or quota: different provider outcomes (luna review 1).
    provider_task = {401: "제공자 인증 실패", 403: "제공자 접근 거부", 429: "제공자 한도 초과"}.get(status)
    provider_failure = provider_task is not None
    if isinstance(result, dict):
        # Match only the documented Context7 error prefix, never arbitrary document text.
        content = result.get("content") or []
        text = "\n".join(item.get("text", "") for item in content
                         if isinstance(item, dict) and item.get("type") == "text")
        provider_failure = provider_failure or bool(re.match(
            r"^\s*Monthly quota (?:exceeded|reached)(?:[.!\s]|$)", text, re.I))
    else:
        provider_failure = provider_failure or bool(executed and re.match(
            r"^\s*Monthly quota (?:exceeded|reached)(?:[.!\s]|$)", event.get("error") or "", re.I))

    if withheld and executed:
        task = "응답 보류"
    elif provider_failure:
        task = provider_task or "제공자 한도 초과"
    elif isinstance(result, dict) and (result.get("is_error") or result.get("isError")):
        task = "도구 오류"
    elif executed and isinstance(result, dict):
        task = "업무 성공"
    elif executed:
        # Older rows retain only a digest/disposition, not is_error or the answer.
        task = "도구 오류" if event.get("error") and not withheld else "미확인"
    else:
        task = "미확인" if attempted else "미실행"

    intent = event.get("intent_state")
    effect = ("실행됨" if intent == "confirmed_executed" else "실행 안 됨"
              if intent == "confirmed_not_executed" else "미확인"
              if attempted or intent in {"pending", "uncertain", "resolved"} else "실행 안 됨")
    return {"connection": connection, "decision": decision, "task": task, "effect": effect}


def recorded_outcome(event: dict) -> dict:
    """New rows keep their snapshot; legacy rows are projected without rewriting."""
    axes = dict(event.get("outcome") or outcome_axes(event))
    if event.get("intent_state") in {"confirmed_executed", "confirmed_not_executed"}:
        axes["effect"] = outcome_axes(event)["effect"]
    return axes
