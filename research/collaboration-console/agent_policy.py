"""Versioned role policy; identities come from queue records, never model prose."""
import copy
import math
import time


PROFILES = {
    "opus": ("claude", "claude-opus-5-5", "high"),
    "sol": ("codex", "gpt-6.1-sol", "high"),
    "sonnet": ("claude", "claude-sonnet-5-5", "high"),
    "gemini": ("antigravity", "gemini-3.8-flash-medium", "medium"),
    "luna": ("codex", "gpt-6-luna", "medium"),
    "haiku": ("claude", "claude-haiku-5-5", "medium"),
    "astra": ("codex", "gpt-6-astra", "high"),
    "fable": ("claude", "claude-fable-5-1", "high"),
    "mythos": ("claude", "claude-mythos-5-1", "high"),
}
HIGH_END = {"astra", "fable", "mythos"}
MAIN = {"sol", "sonnet", "gemini"}


def policy(config):
    supplied = config.get("agent_policy", {})
    result = {"version": 2, "enabled": bool(supplied.get("enabled", False)),
              "lead_agent": "opus", "max_stages": 16, "max_calls": 18,
              "max_revisions": 1, "reserve_percent": 10, "quota_fresh_seconds": 300,
              "profiles": {}}
    for key in ("reserve_percent", "quota_fresh_seconds"):
        value = supplied.get(key, result[key])
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError("Invalid agent policy " + key)
        result[key] = value
    if result["reserve_percent"] >= 100:
        raise ValueError("Quota reserve must be below 100 percent")
    for name, (provider, model, effort) in PROFILES.items():
        override = supplied.get("profiles", {}).get(name, {})
        profile = {"agent": name, "provider": provider, "model": model, "effort": effort,
                   "enabled": name != "mythos", "availability": "unverified",
                   "write_enabled": name in {"opus", "sol", "sonnet", "gemini"}}
        profile.update(copy.deepcopy(override))
        if profile["agent"] != name or profile["provider"] != provider:
            raise ValueError("Role provider cannot be reassigned: " + name)
        if not isinstance(profile["model"], str) or not profile["model"] or len(profile["model"]) > 100:
            raise ValueError("Invalid model identifier")
        if profile["effort"] not in {"low", "medium", "high", "xhigh", "max"}:
            raise ValueError("Invalid effort")
        if name in HIGH_END and profile["effort"] not in {"low", "medium", "high"}:
            raise ValueError("High-end consultation effort must be below xhigh")
        if profile["availability"] not in {"unverified", "verified", "unavailable"}:
            raise ValueError("Invalid model availability")
        if type(profile["enabled"]) is not bool or type(profile["write_enabled"]) is not bool:
            raise ValueError("Role permissions must be boolean")
        if name in HIGH_END | {"luna", "haiku"} and profile["write_enabled"]:
            raise ValueError("Auxiliary and consultation roles are read-only")
        profile["verified"] = profile["availability"] == "verified"
        result["profiles"][name] = profile
    return result


def quota_observation(event, now=None):
    """Accept explicit provider usage metadata, never estimate from token totals."""
    now = time.time() if now is None else now
    kind = event.get("type", event.get("event"))
    if kind == "rate_limit_event":
        data = event.get("rate_limit_info", event.get("rate_limit", {}))
        if not isinstance(data, dict):
            return None
        percent = data.get("used_percent")
        utilization = data.get("utilization")
        if percent is None and type(utilization) in (int, float):
            percent = utilization * 100
        windows = [data]
        status = data.get("status", "unknown")
    elif kind in {"token_count", "account/rateLimits/updated", "rate_limits"}:
        rates = event.get("rate_limits", event.get("rateLimits", {}))
        if not isinstance(rates, dict):
            return None
        windows = [value for key, value in rates.items() if key in {"primary", "secondary"} and isinstance(value, dict)]
        percent, status = None, "unknown"
    else:
        return None
    remaining, resets = [], []
    for window in windows:
        used = window.get("used_percent", window.get("usedPercent", percent))
        reset = window.get("resetsAt", window.get("resets_at", window.get("reset_at")))
        reset = reset if type(reset) in (int,float) and math.isfinite(reset) and reset>now else None
        if type(used) in (int, float) and math.isfinite(used) and 0 <= used <= 100:
            remaining.append((round(100-used, 2),reset))
        if reset:
            resets.append(reset)
    if not windows and status == "unknown":
        return None
    return {"status": "exhausted" if status in {"rejected", "blocked"} or any(value[0]==0 for value in remaining) else
            "warning" if status == "allowed_warning" else "known" if remaining else "unknown",
            "remaining_percent": min(value[0] for value in remaining) if remaining else None,
            "reset_at": min(remaining,key=lambda value:(value[0],-(value[1] or 0)))[1] if remaining else max(resets) if resets else None, "observed_at": now,
            "source": "CLI " + str(kind)}


def visible_quota(value, fresh_seconds=300, now=None):
    now = time.time() if now is None else now
    result = dict(value or {"status": "unknown", "remaining_percent": None,
                           "reset_at": None, "observed_at": None, "source": "CLI 미보고"})
    result["stale"] = not result.get("observed_at") or now-result["observed_at"] > fresh_seconds
    return result


def reserve_blocked(quota, reserve_percent, now=None):
    """Age does not replenish an account; only its reset or newer usage can do so."""
    now = time.time() if now is None else now
    reset = quota.get("reset_at")
    if reset is not None and reset <= now:
        return False
    remaining = quota.get("remaining_percent")
    return quota.get("status") == "exhausted" or remaining is not None and remaining <= reserve_percent
