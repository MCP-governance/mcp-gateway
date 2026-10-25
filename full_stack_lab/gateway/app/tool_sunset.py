"""Time out unused, human-scoped tools using the append-only decision ledger (DEV-75)."""
from __future__ import annotations

import json
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
CACHE_LIMIT = 4096
COVERAGE_CACHE_LIMIT = 32
_states: dict[tuple[str, str], tuple] = {}
_coverage_versions: dict[tuple, bool | datetime] = {}
_generation = 0


def invalidate(server_id: str, tool_name: str) -> None:
    global _generation
    _states.pop((server_id, tool_name), None)
    # An in-flight snapshot must not publish evidence read before this write.
    _generation += 1


def _remember(cache: dict, key, value, limit: int) -> None:
    cache.pop(key, None)
    if len(cache) >= limit:
        cache.pop(next(iter(cache)))
    cache[key] = value


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


async def _last_event(connection, server_id: str, tool_name: str | list[str]) -> dict | None:
    if isinstance(tool_name, list):
        rows = await (await connection.execute(
            """SELECT DISTINCT ON (target_id) target_id, kind, outcome, scope, created_at
                 FROM approval_events WHERE target_kind=%s AND target_id=ANY(%s::text[])
                   AND kind=ANY(%s::text[]) ORDER BY target_id, id DESC""",
            (TARGET, [target_id(server_id, name) for name in tool_name], list(EVENTS)))).fetchall()
        return {row["target_id"]: row for row in rows}
    return await (await connection.execute(
        """SELECT kind, outcome, scope, created_at FROM approval_events
             WHERE target_kind=%s AND target_id=%s AND kind=ANY(%s::text[])
             ORDER BY id DESC LIMIT 1""",
        (TARGET, target_id(server_id, tool_name), list(EVENTS)))).fetchone()


async def _last_check(connection, server_id: str, tool_name: str | list[str]) -> dict | None:
    if isinstance(tool_name, list):
        rows = await (await connection.execute(
            """SELECT DISTINCT ON (target_id) target_id, kind, outcome, scope, created_at
                 FROM approval_events WHERE target_kind=%s AND target_id=ANY(%s::text[])
                   AND kind='tool-sunset-check' ORDER BY target_id, id DESC""",
            (TARGET, [target_id(server_id, name) for name in tool_name]))).fetchall()
        return {row["target_id"]: row for row in rows}
    return await (await connection.execute(
        """SELECT kind, outcome, scope, created_at FROM approval_events
             WHERE target_kind=%s AND target_id=%s AND kind='tool-sunset-check'
             ORDER BY id DESC LIMIT 1""", (TARGET, target_id(server_id, tool_name)))).fetchone()


async def _coverage(connection, cutoff: datetime, setting: dict, seal=None, entries=None) -> tuple[bool, str]:
    if max(IDLE_DAYS + GRACE_DAYS, OBSERVATION_DAYS) > int(setting["days"]):
        return False, "미사용 판정 기간이 원장 보존 기간보다 깁니다."
    if seal:
        version = ("sealed", json.dumps(seal, sort_keys=True, default=str))
        if version not in _coverage_versions:
            _remember(_coverage_versions, version,
                      datetime.fromisoformat(str(seal["last_created_at"]).replace("Z", "+00:00")),
                      COVERAGE_CACHE_LIMIT)
        sealed_at = _coverage_versions[version]
        if sealed_at >= cutoff:
            return False, "관측 창 일부가 폐기된 원장 구간과 겹칩니다."
    else:
        version = ("unsealed", entries)
        if version not in _coverage_versions:
            row = await (await connection.execute(
                """SELECT a.entries, (SELECT count(*) FROM decisions) AS retained
                     FROM audit_chain a WHERE a.id=1""")).fetchone()
            valid = not row or int(row["entries"]) == int(row["retained"])
            _remember(_coverage_versions, version, valid, COVERAGE_CACHE_LIMIT)
        if not _coverage_versions[version]:
            return False, "원장 봉인 자료를 확인할 수 없습니다."
    return True, ""


async def _locks(connection, keys: list[str]) -> None:
    # Order the actual hash keys, including collisions, in every writer.
    await connection.execute(
        """SELECT pg_advisory_xact_lock(lock_key) FROM
             (SELECT DISTINCT hashtext(key) AS lock_key FROM unnest(%s::text[]) AS keys(key)
              ORDER BY lock_key) ordered_keys""", (keys,))


async def _record_event(connection, isolate: bool, key: str, write):
    # write(connection) carries the literal kind to review.record_event so the static scan
    # of event kinds (console labels) sees it, instead of a kind forwarded through *args.
    _states.pop(tuple(key.split("/", 1)), None)
    if isolate:
        # A rejected append must not abort the other tools in this snapshot.
        async with connection.transaction():
            return await write(connection)
    return await write(connection)


async def _state(connection, server_id, tool_name, reviewed_at, now, event, check_event,
                 last_use, cutoff, covered, coverage_reason, isolate=False) -> dict:
    key = target_id(server_id, tool_name)
    if event and event["kind"] == "tool-sunset" and event["outcome"] == "held":
        return {"active": False, "available": True, "eligible": True,
                "last_use": event["scope"].get("last_use"),
                "deadline": event["scope"].get("deadline"), "status": "재심사 필요"}
    if not covered:
        if not check_event or check_event["scope"].get("window_start") != cutoff.isoformat():
            await _record_event(connection, isolate, key, lambda c: review.record_event(
                "tool-sunset-check", "recorded", TARGET, key, "automatic", reason=coverage_reason,
                scope={"server": server_id, "tool": tool_name, "window_start": cutoff.isoformat(),
                       "observation_days": OBSERVATION_DAYS, "idle_days": IDLE_DAYS,
                       "grace_days": GRACE_DAYS}, connection=c))
        return {"active": True, "available": True, "eligible": True, "last_use": None, "deadline": None,
                "status": "자료 없음", "reason": coverage_reason}
    result = evaluate(reviewed_at, last_use, now)
    if result["expired"]:
        scope = {"server": server_id, "tool": tool_name,
                 "last_use": last_use.isoformat() if last_use else None,
                 "observation_days": OBSERVATION_DAYS, "idle_days": IDLE_DAYS,
                 "grace_days": GRACE_DAYS, "window_start": cutoff.isoformat(),
                 "inactive_at": result["inactive_at"].isoformat(), "deadline": result["deadline"].isoformat()}
        await _record_event(connection, isolate, key, lambda c: review.record_event(
            "tool-sunset", "held", TARGET, key, "automatic",
            reason="도구 이용 기한 만료", scope=scope, connection=c))
        return {"active": False, "available": True, "eligible": True, **result, "status": "재심사 필요"}
    # The deadline moves with every call by seconds; one extension a day per tool is the record worth keeping
    # (an event per call grew the ledger by the call count). The decision still uses the exact last use.
    if result["recent"] and last_use and (not event or event["kind"] != "tool-sunset-extension"
                                           or str(event["scope"].get("deadline") or "")[:10]
                                           != result["deadline"].astimezone(timezone.utc).date().isoformat()):
        scope = {"server": server_id, "tool": tool_name, "last_use": last_use.isoformat(),
                 "observation_days": OBSERVATION_DAYS, "idle_days": IDLE_DAYS, "grace_days": GRACE_DAYS,
                 "window_start": cutoff.isoformat(), "deadline": result["deadline"].isoformat(),
                 "previous_deadline": (event or {}).get("scope", {}).get("deadline") or
                                      (reviewed_at + timedelta(days=IDLE_DAYS)).isoformat()}
        await _record_event(connection, isolate, key, lambda c: review.record_event(
            "tool-sunset-extension", "approved", TARGET, key, "automatic",
            reason="관측 기간 안에 이용 이력이 있습니다.", scope=scope, connection=c))
    return {"active": True, "available": True, "eligible": True, **result, "status": "사용 가능"}


async def _unavailable(server_id, tool_name, exc) -> dict:
    invalidate(server_id, tool_name)
    try:
        await review.record_event(
            "tool-sunset-check", "recorded", TARGET, target_id(server_id, tool_name), "automatic",
            reason=type(exc).__name__, scope={"server": server_id, "tool": tool_name,
                                              "observation_days": OBSERVATION_DAYS})
    except Exception:
        logger.exception("도구 이용 상태 확인 실패를 기록하지 못했습니다: %s/%s", server_id, tool_name)
    return {"active": True, "available": False, "eligible": True, "last_use": None, "deadline": None,
            "status": "자료 없음", "reason": type(exc).__name__}


def _cache_state(server_id, name, version, now, state):
    if not state.get("available", True) or state["status"] == "자료 없음":
        return
    if not state["active"]:
        state = {key: state[key] for key in ("active", "available", "eligible", "last_use", "deadline", "status")}
        state = {**state, "last_use": iso(state["last_use"]), "deadline": iso(state["deadline"])}
        until = None
    else:
        until = (now.astimezone(timezone.utc) + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        boundaries = [state.get("inactive_at"), state.get("deadline")]
        if state.get("last_use"):
            boundaries.append(state["last_use"] + timedelta(days=OBSERVATION_DAYS, microseconds=1))
        until = min([until] + [at for at in boundaries if at and at > now])
    _remember(_states, (server_id, name), (version, now, until, dict(state)), CACHE_LIMIT)


async def check_many(server_id: str, tool_names: list[str], now: datetime | None = None, *,
                     use_cache: bool = True) -> dict[str, dict]:
    """Read one server atomically; uncertainty never becomes proof of tool inactivity."""
    now = now or datetime.now(timezone.utc)
    spec = registry.server(server_id)
    reviews = (spec or {}).get("tool_reviews") or {}
    states, reviewed, errors = {}, {}, {}
    for name in dict.fromkeys(tool_names):
        item = reviews.get(name)
        if not item:
            states[name] = {"active": True, "eligible": False, "last_use": None, "deadline": None, "status": "미심사"}
            continue
        try:
            reviewed[name] = datetime.fromisoformat(str(item.get("reviewed_at")).replace("Z", "+00:00"))
        except Exception as exc:
            errors[name] = exc
    fresh, versions = {}, {}
    generation = _generation
    if reviewed:
        read_complete = False
        try:
            # Reading settings while holding a pool connection previously deadlocked all ten readers.
            setting = await retention.setting()
            seal = retention.current_seal()
            async with db.transaction() as connection:
                await _locks(connection, [target_id(server_id, name) for name in reviewed])
                if seal:
                    seal_version = ("sealed", json.dumps(seal, sort_keys=True, default=str))
                else:
                    row = await (await connection.execute("SELECT entries FROM audit_chain WHERE id=1")).fetchone()
                    seal_version = ("unsealed", row["entries"] if row else None)
                pending = []
                for name in reviewed:
                    raw = reviews[name].get("reviewed_at")
                    versions[name] = (raw, seal_version, int(setting["days"]))
                    cached = _states.get((server_id, name)) if use_cache and raw else None
                    if (cached and cached[0] == versions[name] and cached[1] <= now
                            and (cached[2] is None or now < cached[2])):
                        states[name] = dict(cached[3])
                    else:
                        pending.append(name)
                if pending:
                    single = len(pending) == 1
                    names = pending[0] if single else pending
                    events = await _last_event(connection, server_id, names)
                    if single:
                        events = {target_id(server_id, names): events}
                    for name in pending:
                        event = events.get(target_id(server_id, name))
                        if event and event["kind"] == "tool-sunset" and event["outcome"] == "held":
                            states[name] = {"active": False, "available": True, "eligible": True,
                                            "last_use": event["scope"].get("last_use"),
                                            "deadline": event["scope"].get("deadline"), "status": "재심사 필요"}
                    fresh.update({name: states[name] for name in pending if name in states})
                    pending = [name for name in pending if name not in states]
                    checks = await _last_check(connection, server_id, names) if pending else {}
                    if single and pending:
                        checks = {target_id(server_id, names): checks}
                    cutoff = now - timedelta(days=max(IDLE_DAYS + GRACE_DAYS, OBSERVATION_DAYS))
                    covered, reason = (await _coverage(connection, cutoff, setting, seal, seal_version[1])
                                       if pending else (False, ""))
                    if covered:
                        if single:
                            row = await (await connection.execute(
                                """SELECT max(created_at) AS last_use FROM decisions
                                     WHERE server_id=%s AND tool_name=%s AND upstream_executed
                                       AND created_at <= %s
                                       AND COALESCE(client->>'event_kind','tools/call')='tools/call'""",
                                (server_id, names, now))).fetchone()
                            uses = {names: row["last_use"] if row else None}
                        else:
                            rows = await (await connection.execute(
                                """SELECT tool_name, max(created_at) AS last_use FROM decisions
                                     WHERE server_id=%s AND tool_name=ANY(%s::text[]) AND upstream_executed
                                       AND created_at <= %s
                                       AND COALESCE(client->>'event_kind','tools/call')='tools/call'
                                     GROUP BY tool_name""", (server_id, pending, now))).fetchall()
                            uses = {row["tool_name"]: row["last_use"] for row in rows}
                    else:
                        uses = {}
                    for name in pending:
                        try:
                            fresh[name] = await _state(
                                connection, server_id, name, reviewed[name], now,
                                events.get(target_id(server_id, name)), checks.get(target_id(server_id, name)),
                                uses.get(name), cutoff, covered, reason, isolate=not single)
                        except Exception as exc:
                            errors[name] = exc
                read_complete = True
            states.update(fresh)
            # Publish only after commit and only if no concurrent writer invalidated the snapshot.
            if use_cache and generation == _generation:
                for name, state in fresh.items():
                    if reviews[name].get("reviewed_at"):
                        _cache_state(server_id, name, versions[name], now, state)
        except Exception as exc:
            errors.update({name: exc for name in reviewed if read_complete or name not in states})
    for name, exc in errors.items():
        states[name] = await _unavailable(server_id, name, exc)
    return states


async def check(server_id: str, tool_name: str, now: datetime | None = None) -> dict:
    """Record extensions or sunset atomically; uncertainty always leaves the tool usable."""
    # Calls need the exact latest use; only listing/display snapshots reuse deadline state.
    return (await check_many(server_id, [tool_name], now, use_cache=False))[tool_name]


async def snapshot() -> dict:
    """Admin display data for registered, human-scoped tools."""
    result = {}
    for server_id, spec in registry.runtime().get("servers", {}).items():
        states = await check_many(server_id, list(spec.get("tool_reviews") or {}))
        for tool_name, state in states.items():
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
    for name in tool_names:
        invalidate(server_id, name)
    try:
        async with db.transaction() as connection:
            await _locks(connection, [target_id(server_id, name) for name in tool_names])
            for tool_name in sorted(set(tool_names)):
                key = target_id(server_id, tool_name)
                await review.record_event("tool-sunset-review", "approved", TARGET, key, actor,
                                          reason="도구 범위 재심사·재승인", scope={"server": server_id,
                                          "tool": tool_name, "reviewed_at": datetime.now(timezone.utc).isoformat()},
                                          connection=connection)
    finally:
        for name in tool_names:
            invalidate(server_id, name)
