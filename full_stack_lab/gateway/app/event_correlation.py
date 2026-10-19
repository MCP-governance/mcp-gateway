"""Pure projection for gateway and endpoint event correlation."""
from __future__ import annotations

from datetime import datetime, timedelta


def correlation_result(call: dict, intent: dict | None, events: list[dict], *, bound: bool,
                       window_seconds: int) -> dict:
    """Project a call and endpoint observations with the evidence for each link."""
    call_at = call["created_at"]
    request_id = str(call.get("request_id") or "")
    trace_id = call.get("trace_id")
    decision = {"kind": "decision", "id": call["id"], "at": call_at.isoformat(),
                "endpoint_id": call.get("device_id"), "trace_id": trace_id,
                "request_id": request_id, "decision": call.get("decision"),
                "policy_id": call.get("policy_id"), "title": f"{call.get('server_id')}.{call.get('tool_name')}",
                "source": "gateway", "link_basis": [x for x, present in
                    (("request_id", bool(request_id)), ("trace_id", bool(trace_id))) if present],
                "link_strength": "exact"}
    records = [decision]
    if intent and request_id:
        records.append({"kind": "dispatch-intent", "id": request_id, "at": intent["attempted_at"].isoformat(),
                        "endpoint_id": call.get("device_id"), "request_id": request_id,
                        "decision_id": intent.get("decision_id"), "state": intent.get("state"),
                        "title": f"{call.get('server_id')}.{call.get('tool_name')}", "source": "gateway",
                        "link_basis": ["request_id", "decision_id"], "link_strength": "exact"})
    span = timedelta(seconds=window_seconds)
    for event in events:
        at = event["at"]
        if (event.get("endpoint_id") != call.get("device_id") or
                event.get("event_user_token") != call.get("user_token") or
                not call_at - span <= at <= call_at + span):
            continue
        # OS observations carry no request ID, so they corroborate but do not prove causation.
        records.append({**{k: v for k, v in event.items() if k != "event_user_token"},
                        "at": at.isoformat(), "link_basis": ["same_endpoint", "same_principal", "time_window"],
                        "link_strength": "corroborating"})
    records.sort(key=lambda item: datetime.fromisoformat(item["at"]), reverse=True)
    return {"anchor": {"kind": "decision", "id": call["id"], "at": call_at.isoformat(),
                       "endpoint_id": call.get("device_id"), "trace_id": trace_id,
                       "request_id": request_id},
            "bound": bound, "window_seconds": window_seconds, "records": records}
