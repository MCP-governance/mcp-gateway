"""Human-labelled impact and value-free explanations for per-call review."""
from __future__ import annotations

from collections import Counter

DOMAINS = ("employment", "credit", "legal", "benefits", "contract", "service_access")
REASONS = {"scope_confirmed": "요청 범위·정책 근거 확인", "request_inappropriate": "요청 부적합",
           "approval_withdrawn": "승인 판단 변경"}


def normalize(item: dict) -> dict:
    flag = item.get("high_impact", False)
    domains = item.get("impact_domains") or []
    if not isinstance(flag, bool) or not isinstance(domains, list) or any(d not in DOMAINS for d in domains):
        raise ValueError("중대 영향 여부와 영향 영역이 올바르지 않습니다.")
    if bool(domains) != flag:
        raise ValueError("중대 영향 도구에는 영향 영역이 필요합니다.")
    return {"high_impact": flag, "impact_domains": sorted(set(domains))}


def terms(item: dict) -> dict:
    return {k: v for k, v in item.items() if k not in ("reviewed_by", "reviewed_at")}


def explanation(approval_id: str, arguments: dict, item: dict, verdict: dict, data_class: str, action: str,
                server_id: str = "", tool: str = "") -> dict:
    # Even keys, summaries and reviewer prose can contain personal data. Export only fixed categories.
    counts = Counter()
    def count(value):
        kind = ("null" if value is None else "boolean" if isinstance(value, bool) else
                "object" if isinstance(value, dict) else "array" if isinstance(value, list) else
                "string" if isinstance(value, str) else "number")
        counts[kind] += 1
        for child in value.values() if isinstance(value, dict) else value if isinstance(value, list) else ():
            count(child)
    count(arguments)
    return {"approval_id": approval_id, "summary": "중대 영향 도구 호출", **normalize(item),
            "server_id": server_id, "tool": tool,
            "arguments": dict(sorted(counts.items())), "data_class": data_class, "action": action,
            "policy_id": "P-HIGH-IMPACT-001", "basis_policy_id": verdict["policy_id"],
            "basis_decision": verdict["decision"], "policy_version": verdict.get("policy_version", "unknown"),
            "effect_reversal": False}


def bound(approval: dict | None, payload: dict, item: dict, digest) -> bool:
    if not approval or approval.get("status") != "APPROVED" or not approval.get("reviewed_by") or approval.get("revoked_at"):
        return False
    stored = approval.get("request_payload") or {}
    return (approval.get("request_fingerprint") == digest(stored)
            and stored.get("impact_scope_sha256") == digest(terms(item))
            and all(stored.get(k) == payload.get(k) for k in ("server_id", "tool", "arguments", "user_token"))
            and bool(approval.get("explanation")))
