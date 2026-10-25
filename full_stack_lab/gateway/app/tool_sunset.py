"""Time out unused, human-scoped tools using the append-only decision ledger (DEV-75)."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from . import db, registry, retention, review

IDLE_DAYS = int(os.getenv("TOOL_SUNSET_IDLE_DAYS", "90"))
OBSERVATION_DAYS = int(os.getenv("TOOL_SUNSET_OBSERVATION_DAYS", "30"))
GRACE_DAYS = int(os.getenv("TOOL_SUNSET_GRACE_DAYS", "30"))
TARGET = "tool-sunset"
EVENTS = ("tool-sunset", "tool-sunset-extension", "tool-sunset-review")
logger = logging.getLogger(__name__)


def target_id(server_id: str, tool_name: str) -> str:
    return f"{server_id}/{tool_name}"


def iso(value) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else value


def listable(state: dict) -> bool:
    if not state.get("available", True):
        raise RuntimeError("도구 이용 상태를 확인할 수 없습니다.")
    return bool(state["active"])


def call_verdict(state: dict) -> tuple[str, str] | None:
    if not state.get("available", True):
        return "P-CONTROL-FAIL-CLOSED", "도구 이용 상태를 확인할 수 없어 실행하지 않았습니다."
    if not state["active"]:
        return "P-APPROVAL-EXPIRY-001", "도구 이용 기한이 지났습니다. 범위 재심사·재승인 전에는 실행할 수 없습니다."
    return None


def evaluate(reviewed_at: datetime, last_use: datetime | None, now: datetime, *,
             idle_days: int = IDLE_DAYS, grace_days: int = GRACE_DAYS,
             observation_days: int = OBSERVATION_DAYS) -> dict:
    """Pure deadline rule; callers must first prove the whole observation window is retained."""
    if idle_days < 1 or grace_days < 0 or observation_days < 1:
        raise ValueError("도구 비활성 기한과 관측 기간은 양수, 유예는 0일 이상이어야 합니다.")
    base = max(reviewed_at, last_use) if last_use else reviewed_at
    inactive_at = base + timedelta(days=idle_days)
    deadline = inactive_at + timedelta(days=grace_days)
    recent = last_use is not None and last_use >= now - timedelta(days=observation_days)
    return {"last_use": last_use, "inactive_at": inactive_at, "deadline": deadline,
            "recent": recent, "expired": now >= deadline}


async def _last_event(connection, server_id: str, tool_name: str) -> dict | None:
    return await (await connection.execute(
        """SELECT kind, outcome, scope, created_at FROM approval_events
             WHERE target_kind=%s AND target_id=%s AND kind=ANY(%s::text[])
             ORDER BY id DESC LIMIT 1""",
        (TARGET, target_id(server_id, tool_name), list(EVENTS)))).fetchone()


async def _last_check(connection, server_id: str, tool_name: str) -> dict | None:
    return await (await connection.execute(
        """SELECT kind, outcome, scope, created_at FROM approval_events
             WHERE target_kind=%s AND target_id=%s AND kind='tool-sunset-check'
             ORDER BY id DESC LIMIT 1""", (TARGET, target_id(server_id, tool_name)))).fetchone()


async def _coverage(connection, cutoff: datetime, setting: dict) -> tuple[bool, str]:
    if max(IDLE_DAYS + GRACE_DAYS, OBSERVATION_DAYS) > int(setting["days"]):
        return False, "미사용 판정 기간이 원장 보존 기간보다 깁니다."
    seal = retention.current_seal()
    if seal:
        sealed_at = datetime.fromisoformat(str(seal["last_created_at"]).replace("Z", "+00:00"))
        if sealed_at >= cutoff:
            return False, "관측 창 일부가 폐기된 원장 구간과 겹칩니다."
    else:
        row = await (await connection.execute(
            """SELECT a.entries, (SELECT count(*) FROM decisions) AS retained
                 FROM audit_chain a WHERE a.id=1""")).fetchone()
        if row and int(row["entries"]) != int(row["retained"]):
            return False, "원장 봉인 자료를 확인할 수 없습니다."
    return True, ""


async def check(server_id: str, tool_name: str, now: datetime | None = None) -> dict:
    """Record extensions or sunset atomically; uncertainty always leaves the tool usable."""
    now = now or datetime.now(timezone.utc)
    spec = registry.server(server_id) or {}
    tool_review = (spec.get("tool_reviews") or {}).get(tool_name)
    if not tool_review:
        return {"active": True, "eligible": False, "last_use": None, "deadline": None, "status": "미심사"}
    reviewed_text = tool_review.get("reviewed_at")
    try:
        reviewed_at = datetime.fromisoformat(str(reviewed_text).replace("Z", "+00:00"))
        # Read before taking the transaction's connection: a second pool connection per check deadlocked
        # the pool when a harness listed ten servers at once (S4-01).
        setting = await retention.setting()
        async with db.transaction() as connection:
            key = target_id(server_id, tool_name)
            await connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (key,))
            event = await _last_event(connection, server_id, tool_name)
            if event and event["kind"] == "tool-sunset" and event["outcome"] == "held":
                return {"active": False, "available": True, "eligible": True,
                        "last_use": event["scope"].get("last_use"),
                        "deadline": event["scope"].get("deadline"), "status": "재심사 필요"}
            cutoff = now - timedelta(days=max(IDLE_DAYS + GRACE_DAYS, OBSERVATION_DAYS))
            covered, coverage_reason = await _coverage(connection, cutoff, setting)
            if not covered:
                check_event = await _last_check(connection, server_id, tool_name)
                if not check_event or check_event["scope"].get("window_start") != cutoff.isoformat():
                    await review.record_event(
                        "tool-sunset-check", "recorded", TARGET, key, "automatic", reason=coverage_reason,
                        scope={"server": server_id, "tool": tool_name, "window_start": cutoff.isoformat(),
                               "observation_days": OBSERVATION_DAYS, "idle_days": IDLE_DAYS,
                               "grace_days": GRACE_DAYS}, connection=connection)
                return {"active": True, "available": True, "eligible": True, "last_use": None, "deadline": None,
                        "status": "자료 없음", "reason": coverage_reason}
            row = await (await connection.execute(
                """SELECT max(created_at) AS last_use FROM decisions
                     WHERE server_id=%s AND tool_name=%s AND upstream_executed
                       AND created_at <= %s
                       AND COALESCE(client->>'event_kind','tools/call')='tools/call'""",
                (server_id, tool_name, now))).fetchone()
            last_use = row["last_use"] if row else None
            result = evaluate(reviewed_at, last_use, now)
            key = target_id(server_id, tool_name)
            if result["expired"]:
                scope = {"server": server_id, "tool": tool_name,
                         "last_use": last_use.isoformat() if last_use else None,
                         "observation_days": OBSERVATION_DAYS, "idle_days": IDLE_DAYS,
                         "grace_days": GRACE_DAYS, "window_start": cutoff.isoformat(),
                         "inactive_at": result["inactive_at"].isoformat(), "deadline": result["deadline"].isoformat()}
                await review.record_event("tool-sunset", "held", TARGET, key, "automatic",
                                          reason="도구 이용 기한 만료", scope=scope, connection=connection)
                return {"active": False, "available": True, "eligible": True, **result, "status": "재심사 필요"}
            if result["recent"] and last_use and (not event or event["kind"] != "tool-sunset-extension"
                                                   or event["scope"].get("deadline") != result["deadline"].isoformat()):
                scope = {"server": server_id, "tool": tool_name, "last_use": last_use.isoformat(),
                         "observation_days": OBSERVATION_DAYS, "idle_days": IDLE_DAYS, "grace_days": GRACE_DAYS,
                         "window_start": cutoff.isoformat(), "deadline": result["deadline"].isoformat(),
                         "previous_deadline": (event or {}).get("scope", {}).get("deadline") or
                                              (reviewed_at + timedelta(days=IDLE_DAYS)).isoformat()}
                await review.record_event("tool-sunset-extension", "approved", TARGET, key, "automatic",
                                          reason="관측 기간 안에 이용 이력이 있습니다.", scope=scope, connection=connection)
            return {"active": True, "available": True, "eligible": True, **result, "status": "사용 가능"}
    except Exception as exc:
        try:
            await review.record_event(
                "tool-sunset-check", "recorded", TARGET, target_id(server_id, tool_name), "automatic",
                reason=type(exc).__name__, scope={"server": server_id, "tool": tool_name,
                                                  "observation_days": OBSERVATION_DAYS})
        except Exception:
            logger.exception("도구 이용 상태 확인 실패를 기록하지 못했습니다: %s/%s", server_id, tool_name)
        return {"active": True, "available": False, "eligible": True, "last_use": None, "deadline": None,
                "status": "자료 없음", "reason": type(exc).__name__}


async def snapshot() -> dict:
    """Admin display data for registered, human-scoped tools."""
    result = {}
    for server_id, spec in registry.runtime().get("servers", {}).items():
        for tool_name in (spec.get("tool_reviews") or {}):
            state = await check(server_id, tool_name)
            result[target_id(server_id, tool_name)] = {
                "server_id": server_id, "tool": tool_name,
                "last_use": iso(state.get("last_use")), "deadline": iso(state.get("deadline")),
                "status": state["status"],
            }
    return {"idle_days": IDLE_DAYS, "observation_days": OBSERVATION_DAYS,
            "grace_days": GRACE_DAYS, "tools": result}


async def recently_used(server_id: str, tool_names: list[str], now: datetime) -> list[dict] | None:
    """None means the evidence window is incomplete; it never qualifies for automatic renewal."""
    cutoff = now - timedelta(days=OBSERVATION_DAYS)
    try:
        reason = ""
        if max(IDLE_DAYS + GRACE_DAYS, OBSERVATION_DAYS) > int((await retention.setting())["days"]):
            reason = "비활성 판정 기간이 원장 보존 기간보다 깁니다."
        seal = retention.current_seal()
        if seal and datetime.fromisoformat(str(seal["last_created_at"]).replace("Z", "+00:00")) >= cutoff:
            reason = "관측 창 일부가 폐기된 원장 구간과 겹칩니다."
        if not seal:
            rows = await db.fetch_all(
                """SELECT a.entries, (SELECT count(*) FROM decisions) AS retained
                     FROM audit_chain a WHERE a.id=1""")
            if rows and int(rows[0]["entries"]) != int(rows[0]["retained"]):
                reason = "원장 봉인 자료를 확인할 수 없습니다."
        if reason:
            await review.record_event("tool-sunset-check", "recorded", TARGET, server_id, "automatic", reason=reason,
                                      scope={"server": server_id, "observation_days": OBSERVATION_DAYS,
                                             "idle_days": IDLE_DAYS, "grace_days": GRACE_DAYS,
                                             "window_start": cutoff.isoformat()})
            return None
        rows = await db.fetch_all(
            """SELECT tool_name, max(created_at) AS last_use FROM decisions
                 WHERE server_id=%s AND tool_name=ANY(%s::text[]) AND upstream_executed AND created_at >= %s
                   AND created_at <= %s AND COALESCE(client->>'event_kind','tools/call')='tools/call'
                 GROUP BY tool_name""",
            (server_id, tool_names, cutoff, now))
        return rows
    except Exception as exc:
        try:
            await review.record_event("tool-sunset-check", "recorded", TARGET, server_id, "automatic",
                                      reason=type(exc).__name__, scope={"server": server_id,
                                                                       "observation_days": OBSERVATION_DAYS})
        except Exception:
            logger.exception("도구 이용 이력 확인 실패를 기록하지 못했습니다: %s", server_id)
        return None


async def approve_review(server_id: str, tool_names: list[str], actor: str) -> None:
    """A human scope review is the reversible path back from an automatic sunset."""
    async with db.transaction() as connection:
        for tool_name in sorted(tool_names):
            key = target_id(server_id, tool_name)
            await connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (key,))
            await review.record_event("tool-sunset-review", "approved", TARGET, key, actor,
                                      reason="도구 범위 재심사·재승인", scope={"server": server_id,
                                      "tool": tool_name, "reviewed_at": datetime.now(timezone.utc).isoformat()},
                                      connection=connection)
