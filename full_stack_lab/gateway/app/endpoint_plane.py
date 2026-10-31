"""엔드포인트 평면 수신부.

Gateway는 자기를 통과한 호출만 안다. 그것이 이 저장소가 반복해서 적어 온 한계다
— "이 Gateway의 효과는 모든 MCP 도구 호출이 이 강제 경로를 통과할 때만 성립한다."
통과하지 않는 경로는 정책으로 막을 수 없고, 막을 수 없는 것은 세지도 못한다.

세는 일은 엔드포인트 평면이 한다. 사용자 PC의 MCP 클라이언트 설정 파일에는 그
사람이 실제로 쓰는 서버 목록이 있다. 그 목록과 Registry를 대조하면 두 가지가
드러난다.

  shadow          : 조직이 모르는 서버. 게이트웨이를 통과하지 않는 경로다.
  retired-residue : 폐기했는데 설정에 남은 서버. 회수되지 않은 접근 경로다.

두 번째가 종료 판정의 C1로 직접 이어진다. 관리대장에서 지운 것과 사람들의 PC에서
사라진 것은 다른 사건이고, 종료를 진술하려면 뒤쪽이 필요하다.

신뢰 경계: 이 모듈이 받는 것은 **관측 보고**이지 지시가 아니다. 보고 내용으로
Registry를 바꾸거나 서버를 활성화하지 않는다. 엔드포인트가 조작되면 조작된
인벤토리가 올라올 뿐이고, 그 경우에도 최악은 "없는 잔존이 보고되는 것"이다.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from psycopg.types.json import Jsonb

from . import db, server_egress
from .event_correlation import correlation_result

AGENT_PROTOCOL = "1"

# 클라이언트 설정이 서버를 가리키는 방식은 제품마다 다르다. 비교 가능한 형태로
# 줄여야 Registry의 endpoint와 대조된다. 지나치게 관대하게 맞추면 서로 다른
# 서버가 같은 것으로 접히고, 그러면 섀도 서버가 등록 서버로 분류된다.
def normalise(transport: str, endpoint_ref: str) -> str:
    value = (endpoint_ref or "").strip()
    if transport in {"stdio", "STDIO"}:
        return " ".join(value.split())
    return safe_endpoint_ref(value).rstrip("/").lower()


def command_digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(" ".join((value or "").split()).encode()).hexdigest()


def safe_endpoint_ref(value: str) -> str:
    # Also protect reports from older collectors before anything is persisted.
    try:
        parsed = urlsplit(value)
        if not (parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment):
            return value
    except ValueError:
        pass
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


def fingerprint(config_path: str, server_label: str, transport: str, endpoint_ref: str) -> str:
    return hashlib.sha256(
        "\x1f".join([config_path, server_label, transport, normalise(transport, endpoint_ref)]).encode()
    ).hexdigest()


# ── 증거 출처 ────────────────────────────────────────────────────────────────
#
# 저장된 행이 에이전트가 보냈다고 말한 형태와 같은지를 해시로 남긴다. 에이전트가
# 보고한 projection 해시와 서버가 저장된 필드만으로 다시 계산한 해시가 다르면
# 전달 중 또는 저장 중에 형태가 바뀐 것이다. 원본 해시는 서버가 검증할 수 없다
# (원본은 그 단말에만 있다) — 나중에 단말의 원본과 대조하기 위해 보관만 한다.

ORIGINS = ("automatic", "manual", "os_event")
RAW_DEDUPE_DAYS = 7
PAGE_MAX = 200
INVENTORY_FIELDS = ("config_path", "server_label", "transport", "endpoint_ref")
LISTENER_FIELDS = ("source", "address", "port", "process_name", "command_line", "mcp_evidence",
                   "server_name", "server_version", "protocol_version")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def canonical_time(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def projection_of(row: dict, fields: tuple[str, ...]) -> dict:
    # An absent text field and an empty one are the same stored value; a port stays null.
    return {key: row.get(key) if key == "port" else ("" if row.get(key) is None else row.get(key)) for key in fields}


def provenance_of(reported: dict | None, projection: dict, server_steps: list[str] | None = None) -> dict:
    reported = reported or {}
    server_hash = canonical_sha256(projection)
    agent_hash = reported.get("projection_sha256")
    return {
        "raw_sha256": reported.get("raw_sha256"),
        "agent_projection_sha256": agent_hash,
        "server_projection_sha256": server_hash,
        "state": "unreported" if not agent_hash else "match" if agent_hash == server_hash else "mismatch",
        "transformations": [*(reported.get("transformations") or []), *("server:" + step for step in server_steps or [])],
        "collector": reported.get("collector"),
        "received_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def _clip(value: str, size: int, steps: list[str]) -> str:
    if len(value) > size and "truncate" not in steps:
        steps.append("truncate")
    return value[:size]


def _origin(value: str) -> str:
    if value not in ORIGINS[:2]:
        raise ValueError("알 수 없는 수집 출처입니다.")
    return value


async def enroll(endpoint_id: str, hostname: str, platform: str, agent_version: str,
                 owner_token: str | None, detail: dict | None = None) -> dict:
    # `host` comes only from the validated managed heartbeat (main.HostReport).
    detail = {key: value for key, value in (detail or {}).items() if key not in {"host", "observation"}}
    await db.execute(
        """INSERT INTO endpoint_agents(endpoint_id, hostname, platform, agent_version, owner_token, detail)
           VALUES (%s,%s,%s,%s,%s,%s)
           ON CONFLICT (endpoint_id) DO UPDATE SET
             hostname=EXCLUDED.hostname, platform=EXCLUDED.platform,
             agent_version=EXCLUDED.agent_version, owner_token=EXCLUDED.owner_token,
             detail=endpoint_agents.detail || EXCLUDED.detail, last_seen_at=now()""",
        (endpoint_id, hostname, platform, agent_version, owner_token, Jsonb(detail or {})),
    )
    return await db.fetch_one("SELECT * FROM endpoint_agents WHERE endpoint_id=%s", (endpoint_id,))


# 이 게이트웨이 자신의 MCP 파사드. 강제 경로 그 자체를 섀도로 올리면 모든
# 엔드포인트가 매번 오탐을 하나씩 보고하고, 그 목록은 곧 읽히지 않게 된다.
SELF_MCP_NAME = "mcp-governance-security-gateway"


async def _registry_index(connection=None) -> list[dict]:
    query = "SELECT id, transport, endpoint, display_name, advertised_name, lifecycle, status FROM mcp_servers"
    rows = (await db.fetch_all(query) if connection is None
            else await (await connection.execute(query)).fetchall())
    # The Gateway is recognised by its MCP URL, not by a label: anyone can name a
    # server "bob-gateway" in a config file.
    gateway_urls = {normalise("streamable-http", url) for url in (
        os.getenv("GATEWAY_PUBLIC_MCP_URL", "http://gateway:8080/mcp/"),
        "http://localhost:8080/mcp/", "http://127.0.0.1:8080/mcp/")}
    index = [{
        "id": "__gateway__",
        "lifecycle": "OPERATING",
        "status": "READY",
        "keys": {SELF_MCP_NAME, *gateway_urls},
        "bases": gateway_urls,
    }]
    for row in rows:
        index.append({
            "id": row["id"],
            "lifecycle": row["lifecycle"],
            "status": row["status"],
            "keys": {
                normalise(row["transport"], row["endpoint"] or ""),
                normalise("stdio", row["endpoint"] or ""),
                command_digest(row["endpoint"] or "") if row["transport"] == "stdio" else "",
                row["id"].lower(),
                (row["display_name"] or "").strip().lower(),
                # 서버가 스스로 말한 이름. 망 관측은 이 값만 손에 넣는다.
                (row["advertised_name"] or "").strip().lower(),
            } - {""},
        })
    return index


def _match(index: list[dict], transport: str, endpoint_ref: str, server_label: str) -> dict | None:
    ref = normalise(transport, endpoint_ref)
    # A harness's managed config names each server after itself ("filesystem") but
    # points it at /mcp/<server>/ under the Gateway (D-30). The URL decides: checked
    # before labels, or every managed entry would read as a copy of the real server.
    for base in index[0].get("bases", ()):
        if transport.lower() != "stdio" and ref == base:
            return index[0]
        if transport.lower() != "stdio" and ref.startswith(base + "/"):
            server_id = ref[len(base) + 1:]
            matched = next((entry for entry in index[1:] if entry["id"] == server_id), None)
            if not matched:
                return None
            # Still registered (READY, or DRIFT/ERROR/PENDING which the Gateway blocks per
            # call): a managed route, not a shadow. Deregistered (DISABLED) is a config
            # for something no longer approved, and a retiring server is residue.
            if matched["lifecycle"] == "OPERATING" and matched["status"] != "DISABLED":
                return {**index[0], "routed_server_id": server_id}
            return matched
    candidates = {ref, (server_label or "").strip().lower()} - {""}
    # A claimed server name cannot turn a direct/stdio route into the Gateway.
    for entry in index[1:]:
        if entry["keys"] & candidates:
            return entry
    return None


def check_route_matching() -> None:
    base = "https://gateway.internal/mcp"
    gateway = {"id": "__gateway__", "lifecycle": "OPERATING", "status": "READY", "keys": {base}, "bases": {base}}
    server = {"id": "github", "lifecycle": "OPERATING", "status": "READY", "keys": {"github"}}
    index = [gateway, server]
    assert _match(index, "streamable-http", base + "/github/", "github")["routed_server_id"] == "github"
    assert _match(index, "streamable-http", base + "/unregistered/", "github") is None
    assert _match(index, "streamable-http", base + "/github/extra/", "github") is None
    disabled = {**server, "status": "DISABLED"}
    assert _match([gateway, disabled], "streamable-http", base + "/github", "github")["id"] == "github"
    drift = {**server, "status": "DRIFT"}
    assert _match([gateway, drift], "streamable-http", base + "/github/", "github")["routed_server_id"] == "github"
    retiring = {**server, "lifecycle": "TERMINATING"}
    assert _match([gateway, retiring], "streamable-http", base + "/github/", "github")["id"] == "github"
    assert _match(index, "streamable-http", "https://vendor.example/mcp", "github")["id"] == "github"


if __name__ == "__main__":
    check_route_matching()
    print("PASS registered Gateway routes (incl. drifted) are managed; unknown/disabled/direct routes never count as approved")


async def ingest(endpoint_id: str, entries: list[dict], *, complete: bool = False, origin: str = "manual") -> dict:
    if not isinstance(complete, bool) or len(entries) > 500:
        raise ValueError("알 수 없는 스냅샷 완전성 또는 보고 상한입니다.")
    async with db.transaction() as connection:
        result = await _ingest_inventory(connection, endpoint_id, entries, complete, _origin(origin))
    await _link_residue_to_cases(endpoint_id)
    return result


async def _record_observation(connection, endpoint_id: str, channel: str, state: str,
                              accepted_count: int = 0, error_code: str = "", sources: list | None = None) -> None:
    stamp = datetime.now(UTC).isoformat()
    row = await (await connection.execute(
        "SELECT detail FROM endpoint_agents WHERE endpoint_id=%s FOR UPDATE", (endpoint_id,))).fetchone()
    if not row:
        raise ValueError("등록되지 않은 엔드포인트입니다.")
    previous = (row.get("detail") or {}).get("observation", {}).get(channel, {})
    value = {"state": state, "reported_at": stamp, "accepted_count": accepted_count,
             "last_success_at": stamp if state == "success" else previous.get("last_success_at"),
             "error_code": error_code}
    if sources is not None or previous.get("sources") is not None:
        value["sources"] = sources if sources is not None else previous["sources"]
    await connection.execute(
        """UPDATE endpoint_agents SET detail=jsonb_set(COALESCE(detail,'{}'::jsonb),'{observation}',
               COALESCE(detail->'observation','{}'::jsonb) || %s::jsonb), last_seen_at=now()
             WHERE endpoint_id=%s""", (Jsonb({channel: value}), endpoint_id))


async def observation_status(endpoint_id: str, channel: str, state: str,
                             accepted_count: int = 0, error_code: str = "", *,
                             buffer_event_uid: str | None = None, dropped_count: int = 0,
                             buffer_reason: str | None = None) -> dict:
    if channel not in {"inventory", "process", "network", "os"} or state not in {
            "success", "partial", "failed", "disabled", "unauthorized", "unsupported", "unknown"}:
        raise ValueError("알 수 없는 수집 상태입니다.")
    async with db.transaction() as connection:
        if dropped_count:
            if not buffer_event_uid or buffer_reason not in {"capacity", "retention", "mixed"}:
                raise ValueError("버퍼 미적재·만료 건수 보고에 식별자·사유가 필요합니다.")
            await connection.execute(
                # 같은 uid의 재보고는 더 큰 건수일 때만 반영한다. 응답 유실 뒤 장치가 누적한 값이
                # 다시 오고, 재전송·순서 뒤바뀜으로 작은 값이 올 수도 있다.
                """INSERT INTO endpoint_buffer_events(endpoint_id,event_uid,dropped_count,reason)
                   VALUES (%s,%s,%s,%s)
                   ON CONFLICT(endpoint_id,event_uid) DO UPDATE SET
                     dropped_count=EXCLUDED.dropped_count, reason=EXCLUDED.reason, reported_at=now()
                   WHERE EXCLUDED.dropped_count > endpoint_buffer_events.dropped_count""",
                (endpoint_id, buffer_event_uid, dropped_count, buffer_reason))
        await _record_observation(connection, endpoint_id, channel, state, accepted_count, error_code)
    return {"endpoint_id": endpoint_id, "channel": channel, "state": state}


def observation_freshness(status: dict, observed_at, now: datetime | None = None) -> str:
    if status.get("state") != "success" or observed_at is None:
        return "unknown"
    try:
        observed = datetime.fromisoformat(str(observed_at).replace("Z", "+00:00"))
        reported = datetime.fromisoformat(str(status["reported_at"]).replace("Z", "+00:00"))
        ages = [(now or datetime.now(UTC)) - item for item in (observed, reported)]
        if any(age.total_seconds() < 0 for age in ages):
            return "unknown"
        return "fresh" if all(0 <= age.total_seconds() <= 180 for age in ages) else "stale"
    except (ValueError, TypeError, KeyError):
        return "unknown"


async def _ingest_inventory(connection, endpoint_id: str, entries: list[dict], complete: bool, origin: str) -> dict:
    """한 엔드포인트가 보고한 설정 목록 전체를 정본으로 교체한다.

    누적이 아니라 교체인 이유는, 설정에서 지워진 항목이 관리대장에 남아 있으면
    잔존이 해소되어도 C1이 영원히 미충족이 되기 때문이다. 회수를 확인할 방법이
    없는 통제는 회수를 유도하지 못한다.
    """
    agent = await (await connection.execute("SELECT * FROM endpoint_agents WHERE endpoint_id=%s FOR UPDATE", (endpoint_id,))).fetchone()
    if not agent:
        raise ValueError("등록되지 않은 엔드포인트입니다. 먼저 enroll 하세요.")
    index = await _registry_index(connection)

    known = {row["fingerprint"]: row["hash"] for row in await (await connection.execute(
        "SELECT fingerprint, provenance->>'raw_sha256' AS hash FROM endpoint_inventory WHERE endpoint_id=%s",
        (endpoint_id,))).fetchall()}
    seen: list[str] = []
    counts = {"registered": 0, "shadow": 0, "retired-residue": 0}
    duplicates = 0
    for item in entries:
        raw = {key: value for key, value in item.items() if key != "provenance"}
        steps: list[str] = []
        config_path = _clip(str(raw.get("config_path") or "unknown"), 400, steps)
        server_label = _clip(str(raw.get("server_label") or "unnamed"), 200, steps)
        transport = _clip(str(raw.get("transport") or "stdio"), 40, steps)
        value = str(raw.get("endpoint_ref") or "")
        if transport.lower() == "stdio" and not value.startswith("sha256:"):
            endpoint_ref = command_digest(value)
            steps.append("command_sha256")
        else:
            endpoint_ref = safe_endpoint_ref(value)
            if endpoint_ref != value:
                steps.append("url_sha256")
        endpoint_ref = _clip(endpoint_ref, 600, steps)
        observed = {**raw, "endpoint_ref": endpoint_ref}
        provenance = provenance_of(item.get("provenance"), projection_of(
            {"config_path": config_path, "server_label": server_label, "transport": transport,
             "endpoint_ref": endpoint_ref}, INVENTORY_FIELDS), steps)
        mark = fingerprint(config_path, server_label, transport, endpoint_ref)
        matched = _match(index, transport, endpoint_ref, server_label)
        if matched is None:
            classification = "shadow"
            registry_match = None
        elif matched["id"] == "__gateway__":
            classification = "registered"
            registry_match = matched.get("routed_server_id")
        elif matched["lifecycle"] in {"TERMINATING", "RETIRED"}:
            classification = "retired-residue"
            registry_match = matched["id"]
        else:
            # v2: every approved server sits behind the Gateway, so a client config
            # that points at a registered server itself is a path around the
            # enforcement point, not a registered use of it.
            classification = "shadow"
            registry_match = matched["id"]
        counts[classification] += 1
        seen.append(mark)
        duplicates += bool(provenance["raw_sha256"]) and known.get(mark) == provenance["raw_sha256"]
        await connection.execute(
            """INSERT INTO endpoint_inventory(
                 endpoint_id, config_path, server_label, transport, endpoint_ref,
                 fingerprint, registry_match, classification, raw, origin, provenance)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (endpoint_id, fingerprint) DO UPDATE SET
                 reported_at=now(), registry_match=EXCLUDED.registry_match,
                 classification=EXCLUDED.classification, raw=EXCLUDED.raw,
                 origin=EXCLUDED.origin, provenance=EXCLUDED.provenance""",
            (endpoint_id, config_path, server_label, transport, endpoint_ref,
             mark, registry_match, classification, Jsonb(observed), origin, Jsonb(provenance)),
        )
    removed = 0
    if complete:
        removed = (await connection.execute(
            "DELETE FROM endpoint_inventory WHERE endpoint_id=%s AND NOT (fingerprint = ANY(%s::text[]))",
            (endpoint_id, seen))).rowcount
    await connection.execute("UPDATE endpoint_agents SET last_seen_at=now() WHERE endpoint_id=%s", (endpoint_id,))
    await _record_observation(connection, endpoint_id, "inventory", "success" if complete else "partial", len(entries),
                              "" if complete else "incomplete_snapshot")
    return {"endpoint_id": endpoint_id, "accepted": len(entries), "duplicates": int(duplicates),
            "removed": removed, "counts": counts, "complete": complete}


async def _link_residue_to_cases(endpoint_id: str) -> None:
    """폐기 절차가 진행 중인 서버의 잔존 설정을 그 케이스의 회수 대상으로 올린다.

    보고를 받아놓고 케이스에 연결하지 않으면 판정이 그것을 보지 못한다. 화면에만
    있는 발견은 판정에 들어가지 않고, 판정에 들어가지 않으면 조치되지 않는다.
    """
    rows = await db.fetch_all(
        """SELECT i.id, i.server_label, i.config_path, a.hostname, c.id AS case_id
             FROM endpoint_inventory i
             JOIN endpoint_agents a USING (endpoint_id)
             JOIN termination_cases c ON c.server_id = i.registry_match
            WHERE i.endpoint_id=%s AND i.classification='retired-residue'
              AND c.status IN ('OPEN','REVOKING','ASSESSED','REOPENED')""",
        (endpoint_id,),
    )
    for row in rows:
        label = f"{row['hostname']} · {row['config_path']} 의 '{row['server_label']}' 항목"
        exists = await db.fetch_one(
            "SELECT id FROM revocation_targets WHERE case_id=%s AND label=%s",
            (row["case_id"], label),
        )
        if exists:
            continue
        from .decommission import add_target
        await add_target(str(row["case_id"]), "endpoint-config", label,
                         "endpoint", "endpoint-agent", "endpoint-plane",
                         note="엔드포인트 보고로 새로 발견된 잔존 설정")


CLASSES = ("registered", "shadow", "retired-residue")


def _classes(value: str | None) -> list[str] | None:
    items = [item for item in (value or "").split(",") if item]
    if any(item not in CLASSES for item in items):
        raise ValueError("알 수 없는 분류입니다.")
    return items or None


def _bounds(limit: int, cursor: str | None) -> tuple[int, int | None]:
    if cursor in (None, ""):
        after = None
    elif re.fullmatch(r"\d{1,18}", str(cursor)):
        after = int(cursor)
    else:
        raise ValueError("잘못된 페이지 위치입니다.")
    return max(1, min(int(limit), PAGE_MAX)), after


def _window(rows: list[dict], limit: int) -> tuple[list[dict], str | None]:
    more = len(rows) > limit
    rows = rows[:limit]
    return rows, (str(rows[-1]["id"]) if more and rows else None)


def _listed(row: dict, *times: str) -> dict:
    item = dict(row)
    for key in times:
        if item.get(key):
            item[key] = item[key].isoformat()
    item["provenance_state"] = (item.pop("provenance", None) or {}).get("state")
    return item


async def inventory_page(classification: str | None = None, limit: int = 100, cursor: str | None = None) -> dict:
    """전체 건수는 반환 창과 따로 센다. 창이 200건이라고 전체가 200건은 아니다."""
    limit, after = _bounds(limit, cursor)
    where, params = ["a.status='active'", "a.agent_version<>'unregistered'"], []
    if classes := _classes(classification):
        where.append("i.classification = ANY(%s::text[])")
        params.append(classes)
    base = " AND ".join(where)
    total = await db.fetch_one(
        "SELECT count(*) AS n FROM endpoint_inventory i JOIN endpoint_agents a USING (endpoint_id) WHERE " + base,
        tuple(params))
    rows = await db.fetch_all(
        """SELECT i.*, a.hostname, a.platform, a.owner_token, a.last_seen_at,
                  s.display_name AS registry_name, s.lifecycle
             FROM endpoint_inventory i
             JOIN endpoint_agents a USING (endpoint_id)
             LEFT JOIN mcp_servers s ON s.id = i.registry_match
            WHERE """ + base + (" AND i.id < %s" if after else "") + " ORDER BY i.id DESC LIMIT %s",
        (*params, *([after] if after else []), limit + 1))
    rows, next_cursor = _window(rows, limit)
    return {"rows": [_listed(row, "reported_at", "last_seen_at") for row in rows],
            "total": int(total["n"] or 0), "limit": limit, "next_cursor": next_cursor}


async def agents() -> list[dict]:
    rows = await db.fetch_all(
        """SELECT a.*, count(i.id) AS entries,
                  count(i.id) FILTER (WHERE i.classification='shadow') AS shadow,
                  count(i.id) FILTER (WHERE i.classification='retired-residue') AS residue
             FROM endpoint_agents a LEFT JOIN endpoint_inventory i USING (endpoint_id)
            WHERE a.status='active' AND a.agent_version<>'unregistered'
            GROUP BY a.endpoint_id ORDER BY a.last_seen_at DESC"""
    )
    result = []
    for row in rows:
        item = dict(row)
        for key in ("enrolled_at", "last_seen_at"):
            if item.get(key):
                item[key] = item[key].isoformat()
        result.append(item)
    return result


async def shadow_count_for(user_token: str) -> int:
    """이 사용자의 엔드포인트에 보고된 섀도 MCP 수. 정책 입력이 된다."""
    if not user_token:
        return 0
    row = await db.fetch_one(
        """SELECT count(*) AS n FROM endpoint_inventory i
             JOIN endpoint_agents a USING (endpoint_id)
            WHERE a.owner_token=%s AND a.status='active' AND a.agent_version<>'unregistered'
              AND i.classification='shadow'""",
        (user_token,),
    )
    return int(row["n"] or 0) if row else 0


async def coverage() -> dict:
    """엔드포인트 평면이 실제로 무엇을 덮고 있는가.

    보고한 엔드포인트 수만으로는 "우리 조직의 몇 퍼센트를 본다"에 답하지 못한다.
    이 테스트베드는 전체 자산 목록을 갖고 있지 않으므로, 그 사실을 감추지 않고
    known_endpoints로만 말한다. 분모를 모르면 분모를 모른다고 적는다.
    """
    rows = await db.fetch_all(
        """SELECT i.classification, count(*) AS n FROM endpoint_inventory i
             JOIN endpoint_agents a USING (endpoint_id)
            WHERE a.status='active' AND a.agent_version<>'unregistered'
            GROUP BY i.classification"""
    )
    counts = {row["classification"]: int(row["n"]) for row in rows}
    agent_rows = await db.fetch_all(
        """SELECT count(*) AS total,
                  count(*) FILTER (WHERE last_seen_at > now() - interval '15 minutes') AS fresh
             FROM endpoint_agents
            WHERE status='active' AND agent_version<>'unregistered'"""
    )
    stats = agent_rows[0] if agent_rows else {"total": 0, "fresh": 0}
    return {
        "known_endpoints": int(stats["total"] or 0),
        "reporting_recently": int(stats["fresh"] or 0),
        "registered": counts.get("registered", 0),
        "shadow": counts.get("shadow", 0),
        "retired_residue": counts.get("retired-residue", 0),
        "note": "자산 목록이 없어 전체 대비 비율은 산출하지 않습니다.",
    }


# ── 장치 자격 ────────────────────────────────────────────────────────────────
#
# 사람 계정과 완전히 다른 축이다. 로그인하지 않고, 사람의 토큰을 발급받지 않으며,
# 할 수 있는 일이 scopes에 적힌 것뿐이다. 그래서 이 자격이 새도 관리자 API는
# 열리지 않는다 — v1.5까지 이 평면의 가장 큰 구멍이 그것이었다.

DEVICE_SCOPES = ("inventory", "netscan", "enforcement")


DENIAL_CLASSES = ("harness_startup", "blocked_attempt", "listener_reply", "unknown")


async def ingest_os_events(endpoint_id: str, events: list[dict]) -> dict:
    accepted = 0
    async with db.transaction() as connection:
        for event in events:
            denial_class = event.get("denial_class") if event.get("denial_class") in DENIAL_CLASSES else "unknown"
            provenance = provenance_of(event.get("provenance"), {
                "event_id": event["event_id"], "observed_at": canonical_time(event["observed_at"]),
                "kind": event["kind"], "details": event["details"], "denial_class": denial_class})
            raw_hash = provenance["raw_sha256"]
            # The same raw record inside the window is a replay (a rewound cursor, a retried batch
            # under a new key), not a second event.
            accepted += (await connection.execute(
                """INSERT INTO endpoint_os_events(endpoint_id,event_id,observed_at,kind,details,denial_class,provenance,raw_sha256)
                   SELECT %s,%s,%s,%s,%s,%s,%s,%s
                    WHERE NOT EXISTS (SELECT 1 FROM endpoint_os_events WHERE endpoint_id=%s AND raw_sha256=%s
                                         AND received_at > now() - make_interval(days => %s))
                   ON CONFLICT(endpoint_id,event_id) DO NOTHING""",
                (endpoint_id, event["event_id"], event["observed_at"], event["kind"], Jsonb(event["details"]),
                 denial_class, Jsonb(provenance), raw_hash, endpoint_id, raw_hash, RAW_DEDUPE_DAYS))).rowcount
        await _record_observation(connection, endpoint_id, "os", "success", len(events))
    return {"endpoint_id": endpoint_id, "accepted": accepted, "received": len(events),
            "duplicates": len(events) - accepted}


def tool_path(server: str) -> str:
    """Which route a reported MCP call took. Gateway servers carry their registry id as the harness server name;
    claude.ai connectors and ChatGPT apps arrive under the vendor's own server names."""
    from . import registry
    if server in registry.servers():
        return "gateway"
    if server.startswith("claude_ai_") or server == "codex_apps":
        return "connector"
    return "local"


async def ingest_tool_events(endpoint_id: str, events: list[dict]) -> dict:
    accepted = 0
    async with db.transaction() as connection:
        for event in events:
            accepted += (await connection.execute(
                """INSERT INTO endpoint_tool_events(endpoint_id,event_id,called_at,harness,account,server,tool,path,
                                                    input_bytes,input_sha256,output_bytes,failed)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(endpoint_id,event_id) DO NOTHING""",
                (endpoint_id, event["event_id"], event["called_at"], event["harness"], event.get("account") or "",
                 event["server"], event["tool"], tool_path(event["server"]), event.get("input_bytes") or 0,
                 event.get("input_sha256") or "", event.get("output_bytes") or 0, bool(event.get("failed"))))).rowcount
        await connection.execute("UPDATE endpoint_agents SET last_seen_at=now() WHERE endpoint_id=%s", (endpoint_id,))
    return {"endpoint_id": endpoint_id, "accepted": accepted, "received": len(events)}


async def tool_events_page(path: str | None = None, limit: int = 100, cursor: str | None = None) -> dict:
    limit, after = _bounds(limit, cursor)
    base, params = ("e.path=%s", [path]) if path else ("TRUE", [])
    total = await db.fetch_one("SELECT count(*) AS n FROM endpoint_tool_events e WHERE " + base, tuple(params))
    rows = await db.fetch_all(
        """SELECT e.*, a.hostname, p.display_name AS owner_name FROM endpoint_tool_events e
             JOIN endpoint_agents a USING (endpoint_id) LEFT JOIN principals p ON p.token = a.owner_token WHERE """
        + base + (" AND e.id < %s" if after else "") + " ORDER BY e.id DESC LIMIT %s",
        (*params, *([after] if after else []), limit + 1))
    rows, next_cursor = _window(rows, limit)
    return {"rows": rows, "total": int(total["n"] or 0), "limit": limit, "next_cursor": next_cursor}


async def os_events_page(kind: str | None = None, denial_class: str | None = None,
                         limit: int = 100, cursor: str | None = None) -> dict:
    limit, after = _bounds(limit, cursor)
    where, params = [], []
    for column, value in (("kind", kind), ("denial_class", denial_class)):
        if value:
            where.append(f"e.{column}=%s")
            params.append(value)
    base = " AND ".join(where) or "TRUE"
    total = await db.fetch_one("SELECT count(*) AS n FROM endpoint_os_events e WHERE " + base, tuple(params))
    rows = await db.fetch_all(
        "SELECT e.*, a.hostname FROM endpoint_os_events e JOIN endpoint_agents a USING (endpoint_id) WHERE "
        + base + (" AND e.id < %s" if after else "") + " ORDER BY e.id DESC LIMIT %s",
        (*params, *([after] if after else []), limit + 1))
    rows, next_cursor = _window(rows, limit)
    return {"rows": [_listed(row, "observed_at", "received_at") for row in rows],
            "total": int(total["n"] or 0), "limit": limit, "next_cursor": next_cursor}


def _hash_key(raw: str) -> str:
    # 장치 키는 32바이트 난수라 사전공격 대상이 아니다. 유추 불가능한 고엔트로피
    # 비밀에는 느린 KDF가 주는 이득이 없고, 매 보고마다 bcrypt를 돌리면 보고
    # 주기가 짧은 대규모 배치에서 게이트웨이가 먼저 무너진다.
    pepper = os.getenv("ENDPOINT_KEY_PEPPER", "")
    return hashlib.sha256((pepper + raw).encode()).hexdigest()


async def issue_device(endpoint_id: str, hostname: str, platform: str, owner_token: str | None,
                       scopes: list[str], issued_by: str, enrollment_key: str | None = None) -> dict:
    """장치를 등록하고 자격을 한 번만 돌려준다.

    평문 키는 이 응답에만 존재한다. 저장은 해시로 하고, 잃어버리면 재발급한다.
    다시 보여줄 수 있게 두면 관리 화면이 조직에서 두 번째로 위험한 표가 된다.
    """
    unknown = sorted(set(scopes) - set(DEVICE_SCOPES))
    if unknown:
        raise ValueError("알 수 없는 장치 권한입니다: " + ", ".join(unknown))
    # An administrator may supply the key (workstation provisioning generates it
    # before the container exists); otherwise it is generated here.
    raw = enrollment_key or secrets.token_urlsafe(32)
    if len(raw) < 32:
        raise ValueError("장치 자격은 32자 이상이어야 합니다.")
    await db.execute(
        """INSERT INTO endpoint_agents(endpoint_id, hostname, platform, agent_version,
                                       owner_token, key_hash, key_prefix, scopes, status,
                                       issued_by, issued_at)
           VALUES (%s,%s,%s,'unregistered',%s,%s,%s,%s,'active',%s,now())
           ON CONFLICT (endpoint_id) DO UPDATE SET
             hostname=EXCLUDED.hostname, platform=EXCLUDED.platform,
             owner_token=EXCLUDED.owner_token, key_hash=EXCLUDED.key_hash,
             key_prefix=EXCLUDED.key_prefix, scopes=EXCLUDED.scopes,
             status='active', issued_by=EXCLUDED.issued_by, issued_at=now(),
             managed_state='unmanaged',device_epoch=NULL,heartbeat_at=NULL,activated_at=NULL,activated_by=NULL""",
        (endpoint_id, hostname, platform, owner_token, _hash_key(raw), raw[:8],
         Jsonb(sorted(set(scopes))), issued_by),
    )
    return {"endpoint_id": endpoint_id, "enrollment_key": raw, "scopes": sorted(set(scopes)),
            "note": "이 키는 다시 표시되지 않습니다. 잃어버리면 재발급하세요."}


async def revoke_device(endpoint_id: str, actor: str) -> dict:
    from . import endpoint_lifecycle
    return await endpoint_lifecycle.revoke_device(endpoint_id, actor)


async def authenticate_device(key: str | None, scope: str) -> dict:
    """장치 키를 확인하고 그 장치가 이 범위를 가졌는지 본다."""
    if not key or len(key) < 16:
        raise PermissionError("엔드포인트 장치 자격이 필요합니다.")
    digest = _hash_key(key)
    rows = await db.fetch_all(
        "SELECT * FROM endpoint_agents WHERE key_prefix=%s AND status='active'", (key[:8],))
    for row in rows:
        # 접두사로 후보를 좁히고 비교는 상수 시간으로 한다.
        if row["key_hash"] and hmac.compare_digest(row["key_hash"], digest):
            if scope not in (row["scopes"] or []):
                raise PermissionError("이 장치에는 " + scope + " 권한이 없습니다.")
            return row
    raise PermissionError("엔드포인트 장치 자격이 유효하지 않습니다.")


async def devices() -> list[dict]:
    rows = await db.fetch_all(
        # 두 표를 같은 질의에서 join하면 행이 곱해진다. 설정 섀도 3건과 리스너
        # 4건이 12로 보이는 식이라, 화면의 숫자가 관측 수가 아니라 곱이 된다.
        # 각 표를 따로 세고 결과만 붙인다.
        """SELECT a.endpoint_id, a.hostname, a.platform, a.agent_version, a.owner_token,
                  a.scopes, a.status, a.issued_by, a.issued_at, a.enrolled_at,
                  a.last_seen_at, a.last_scan_at, p.display_name AS owner_name,
                  a.managed_state, a.policy_hash, a.heartbeat_at, a.configuration_hashes,
                  a.enforcement_checks, a.activated_by, a.activated_at, a.local_username, a.local_uid,
                  (SELECT count(*) FROM endpoint_inventory i
                    WHERE i.endpoint_id = a.endpoint_id AND i.classification='shadow')
                    AS config_shadow,
                  (SELECT count(*) FROM endpoint_listeners l
                    WHERE l.endpoint_id = a.endpoint_id AND l.classification='shadow')
                    AS listener_shadow,
                  (SELECT count(*) FROM endpoint_listeners l
                    WHERE l.endpoint_id = a.endpoint_id) AS listeners_seen
             FROM endpoint_agents a
             LEFT JOIN principals p ON p.token = a.owner_token
            ORDER BY a.last_seen_at DESC""")
    result = []
    for row in rows:
        item = dict(row)
        for key in ("issued_at", "enrolled_at", "last_seen_at", "last_scan_at", "heartbeat_at", "activated_at"):
            if item.get(key):
                item[key] = item[key].isoformat()
        result.append(item)
    return result


# Managed enrollment reuses the device-key boundary. The key stays with the root
# service; the ordinary user receives only a short-lived, device-bound MCP JWT.
HEARTBEAT_SECONDS = 180
HEARTBEAT_INTERVAL = 60
NETWORK_RETENTION_DAYS = 7
MANAGED_CHECKS = {"apparmor_enforcing", "nftables_active", "protected_configs", "ordinary_account", "user_command_helpers"}
MANAGED_CHECKS_BY_PLATFORM = {"linux": MANAGED_CHECKS,
                              "macos": {"pf_enforcing", "protected_configs", "ordinary_account", "user_command_helpers"},
                              "windows": {"firewall_enforcing", "protected_configs", "ordinary_account", "user_command_helpers"}}


# Simple mode (D-239): the harness runs in the employee's own account with no kernel confinement, so the only
# endpoint fact the Gateway can hold it to is that the managed settings it rendered are in place and root-owned.
SIMPLE_CHECKS = {"protected_configs"}


def managed_platform(device: dict) -> str:
    # Not the platform column: the observer's own enroll report rewrites it ("Windows 10", "Linux 6.8").
    detail = device.get("detail") or {}
    return "windows" if detail.get("local_sid") else "macos" if detail.get("managed_platform") == "macos" else "linux"


def managed_mode(device: dict) -> str:
    """simple (the employee's own account, D-239) or isolated. Kits before D-239 enrolled isolated installs only."""
    return "simple" if (device.get("detail") or {}).get("mode") == "simple" else "isolated"


def managed_checks(device: dict, reported: dict | None = None) -> set[str]:
    if managed_mode(device) == "simple":
        return SIMPLE_CHECKS
    required = MANAGED_CHECKS_BY_PLATFORM[managed_platform(device)]
    # Agents installed before D-148 do not scan user settings and cannot be updated remotely;
    # quarantining them all on deploy would cut off every enrolled PC. Once a device has reported
    # the scan it is required for good, so reinstalling an older kit does not drop it.
    if (device.get("detail") or {}).get("command_settings_checked") or "user_command_helpers" in (reported or {}):
        return required
    return required - {"user_command_helpers"}


async def managed_event(endpoint_id: str | None, owner: str, kind: str, detail: dict) -> None:
    await db.execute(
        "INSERT INTO endpoint_managed_events(endpoint_id,owner_token,kind,detail) VALUES (%s,%s,%s,%s)",
        (endpoint_id, owner, kind, Jsonb(detail)))


async def enrollment_token(owner: str) -> dict:
    raw = secrets.token_urlsafe(32)
    expires = datetime.now(UTC) + timedelta(minutes=30)
    await db.execute(
        "INSERT INTO endpoint_enrollment_tokens(token_hash,owner_token,expires_at) VALUES (%s,%s,%s)",
        (_hash_key(raw), owner, expires))
    await managed_event(None, owner, "kit-issued", {"expires_at": expires.isoformat()})
    return {"enrollment_token": raw, "expires_at": expires.isoformat()}


def companion_names(username: str) -> list[str]:
    """The account itself and the companions an isolated install of it creates (Linux, Windows): a switch between
    the modes (D-239) replaces the earlier device instead of leaving it as an active record nobody reports for."""
    base = re.sub(r"^(managed|mcpgw)-", "", username)  # from the companion back to the employee, too (pj2 10-25)
    return sorted({base, ("managed-" + base)[:31], ("mcpgw-" + base)[:20], username})


def _same_pc(old: dict, hostname: str, platform: str, machine_id: str | None, local_sid: str | None,
             username: str | None = None) -> bool:
    """An earlier device of this employee's account that this install replaces: same platform and managed account,
    and the same PC. The machine id decides when both sides report one; otherwise the host name does (installs
    before D-217 sent none, and macOS sends none). The platform column is not compared: the observer's enroll
    report rewrites it ("Linux 6.8"), which kept the earlier reinstall cleanup from ever finding its ghosts."""
    detail = old.get("detail") or {}
    if managed_platform(old) != platform:
        return False
    # A Windows companion account has its own SID; that row is matched by the host name below.
    if platform == "windows" and detail.get("local_sid") != local_sid and old.get("local_username", username) == username:
        return False
    if machine_id and detail.get("machine_id"):
        return machine_id == detail["machine_id"]
    return old["hostname"] == hostname


async def endpoint_settings() -> dict:
    row = await db.fetch_one("SELECT auto_activate, updated_by, updated_at FROM endpoint_settings WHERE id=1")
    item = dict(row) if row else {"auto_activate": True, "updated_by": None, "updated_at": None}
    if item.get("updated_at"):
        item["updated_at"] = item["updated_at"].isoformat()
    return item


async def set_endpoint_settings(actor: str, auto_activate: bool) -> dict:
    await db.execute("""INSERT INTO endpoint_settings(id,auto_activate,updated_by,updated_at) VALUES (1,%s,%s,now())
                        ON CONFLICT (id) DO UPDATE SET auto_activate=EXCLUDED.auto_activate,
                          updated_by=EXCLUDED.updated_by, updated_at=EXCLUDED.updated_at""", (auto_activate, actor))
    return await endpoint_settings()


async def consume_enrollment(raw: str, key: str, hostname: str, username: str, uid: int | None, *,
                             platform: str = "linux", local_sid: str | None = None,
                             helper_command: str | None = None, machine_id: str | None = None,
                             mode: str = "isolated") -> dict:
    endpoint_id = "managed-" + str(uuid.uuid4())
    async with db.transaction() as connection:
        grant = await (await connection.execute(
            """UPDATE endpoint_enrollment_tokens SET consumed_at=now()
                 WHERE token_hash=%s AND consumed_at IS NULL AND expires_at>now()
                   AND EXISTS (SELECT 1 FROM principals p WHERE p.token=owner_token AND p.status='active')
                 RETURNING owner_token""", (_hash_key(raw),))).fetchone()
        if not grant:
            raise PermissionError("설치 키트가 만료·소비됐거나 계정이 비활성 상태입니다. 새 키트를 받으세요.")
        # The same employee on the same PC installing again (an update is the new kit's installer) replaces the
        # earlier device. Its activation carries over only when that device was still active: a quarantined
        # one, one the administrator stopped (revoked, or its local runs stopped) or an unactivated one starts
        # over as pending, so a reinstall never lifts a hold (D-217).
        earlier = [r for r in await (await connection.execute(
            """SELECT endpoint_id,hostname,managed_state,activated_by,activated_at,detail,local_username FROM endpoint_agents
                 WHERE owner_token=%s AND local_username=ANY(%s) AND status='active' AND device_epoch IS NOT NULL
                 ORDER BY issued_at DESC FOR UPDATE""", (grant["owner_token"], companion_names(username)))).fetchall()
            if _same_pc(r, hostname, platform, machine_id, local_sid, username)]
        # Another employee's device on this PC and managed account was just removed by this install's
        # cleanup; its record would stay "active" forever.
        # It is retired, never inherited: an activation belongs to the person it was granted to.
        displaced = [r for r in await (await connection.execute(
            """SELECT endpoint_id,hostname,detail FROM endpoint_agents
                 WHERE owner_token<>%s AND local_username=%s AND status='active' AND device_epoch IS NOT NULL""",
            (grant["owner_token"], username))).fetchall() if _same_pc(r, hostname, platform, machine_id, local_sid)]
        inherited, held = None, None
        if earlier:
            held = await (await connection.execute(
                "SELECT 1 FROM local_run_stops WHERE device_id=%s", (earlier[0]["endpoint_id"],))).fetchone()
        # An isolated install keeps the administrator's check: it does not inherit an automatic activation (D-239).
        if (earlier and earlier[0]["managed_state"] == "active" and earlier[0]["activated_by"]
                and not (mode == "isolated" and earlier[0]["activated_by"] == "auto")):
            inherited = None if held else earlier[0]
        detail = ({"local_sid": local_sid, "helper_command": helper_command} if platform == "windows"
                  else {"managed_platform": "macos"} if platform == "macos" else {})
        detail["mode"] = mode
        if machine_id:
            detail["machine_id"] = machine_id
        if inherited:
            detail["inherited_from"] = inherited["endpoint_id"]
        elif earlier and (held or earlier[0]["managed_state"] == "quarantined"):
            # Automatic activation never lifts a hold (D-217): a reinstall of a stopped or quarantined PC waits for a person.
            detail["held_from"] = earlier[0]["endpoint_id"]
        await connection.execute(
            """INSERT INTO endpoint_agents(endpoint_id,hostname,platform,agent_version,owner_token,
                 key_hash,key_prefix,scopes,status,issued_by,issued_at,managed_state,device_epoch,local_username,local_uid,
                 activated_by,activated_at,detail)
               VALUES (%s,%s,%s,'managed-1',%s,%s,%s,%s,'active',%s,now(),%s,%s,%s,%s,%s,%s,%s)""",
            (endpoint_id, hostname, platform, grant["owner_token"], _hash_key(key), key[:8],
             Jsonb(list(DEVICE_SCOPES)), grant["owner_token"], "active" if inherited else "pending", str(uuid.uuid4()),
             username, uid, inherited["activated_by"] if inherited else None,
             inherited["activated_at"] if inherited else None, Jsonb(detail)))
        await connection.execute(
            "UPDATE endpoint_enrollment_tokens SET endpoint_id=%s WHERE token_hash=%s", (endpoint_id, _hash_key(raw)))
        await connection.execute("UPDATE principals SET managed_required=true WHERE token=%s", (grant["owner_token"],))
        await connection.execute(
            "INSERT INTO endpoint_managed_events(endpoint_id,owner_token,kind,detail) VALUES (%s,%s,'enrolled',%s)",
            (endpoint_id, grant["owner_token"], Jsonb({"platform": platform, "local_username": username,
                                                       "local_uid": uid, "local_sid": local_sid, "mode": mode})))
        if inherited:
            await connection.execute(
                "INSERT INTO endpoint_managed_events(endpoint_id,owner_token,kind,detail) VALUES (%s,%s,'activated',%s)",
                (endpoint_id, grant["owner_token"], Jsonb({"actor": inherited["activated_by"], "inherited_from": inherited["endpoint_id"],
                                                           "note": "같은 직원·같은 PC의 재설치로 이전 장치의 활성화를 이어받음"})))
    # The earlier devices no longer report: revoke them (their tokens with them) and say what replaced them.
    for old in {r["endpoint_id"]: r for r in earlier + displaced}.values():
        await revoke_device(old["endpoint_id"], "reinstall")
        await db.execute("UPDATE endpoint_agents SET detail = detail || %s WHERE endpoint_id=%s",
                         (Jsonb({"superseded_by": endpoint_id}), old["endpoint_id"]))
    return await db.fetch_one("SELECT * FROM endpoint_agents WHERE endpoint_id=%s", (endpoint_id,))


async def managed_policy(device: dict, *, connection=None) -> dict:
    from . import connectors, pac, registry
    if not device.get("device_epoch"):
        raise PermissionError("관리형 설치로 등록한 장치가 아닙니다.")
    public = os.getenv("IDP_ISSUER", "").rstrip("/")
    parsed = urlsplit(public)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.path or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("관리형 설치의 Gateway 공개 주소가 구성되지 않았습니다.")
    if os.getenv("MCP_FIELD_MODE") == "1" and parsed.scheme != "https":
        raise ValueError("현장 관리형 연결에는 HTTPS가 필요합니다.")
    addresses = os.getenv("ENDPOINT_GATEWAY_IPS", parsed.hostname).split(",")
    addresses = [str(ipaddress.ip_address(a.strip())) for a in addresses]
    rows = await db.fetch_all("SELECT id FROM mcp_servers WHERE status IN ('READY','DRIFT') AND lifecycle='OPERATING' ORDER BY id", connection=connection)
    # The minimal set (D-93): a harness is told about the servers whose tools this person may see
    # in tools/list, not about every operating server.
    owner = await db.fetch_one("SELECT * FROM principals WHERE token=%s", (device["owner_token"],), connection=connection)
    usable = set(pac.servers_for(owner)) if owner else set()
    servers = [r["id"] for r in rows if r["id"] in usable]
    windows = managed_platform(device) == "windows"
    if windows:
        # Windows has no PC-isolated local runner: a local-run server would be listed but fail every call (MCP-CATALOG-001).
        servers = [s for s in servers if (registry.server(s) or {}).get("deployment") != "local"]
    version = await db.fetch_one("SELECT last_value FROM mcp_servers_version", connection=connection)
    # Said to the harness while the device waits for activation, so the model does not hunt for MCP settings
    # in the user's files or try to run the harness from its shell.
    guidance = (("# 조직 승인 MCP 도구\n이 PC는 조직 관리자의 활성화를 기다리는 중이라 아직 MCP 도구를 쓸 수 없습니다. "
                "사용자에게 이 사실과 함께 관리자에게 활성화를 요청하라고 안내하고, 설정 파일을 찾거나 다른 방법으로 MCP를 연결하려 하지 않습니다.\n")
                if device.get("managed_state") in ("pending", "quarantined") else pac.harness_guidance(owner, servers))
    detail = device.get("detail") or {}
    helper = (detail.get("helper_command") if windows
              else f'/Library/MCPGatewayManaged/enforcement/mcpgw-{device["local_username"]}/header-helper'
              if managed_platform(device) == "macos"
              else f'/usr/local/lib/mcpgw-enforcement/mcpgw-{device["local_username"]}/header-helper')
    if not helper:
        raise ValueError("관리형 설치의 헤더 명령이 등록되지 않았습니다.")
    # The managed account reaches nothing but the Gateway host, so the harness reaches its model
    # through the approved proxy there. MCP traffic to the Gateway itself stays direct (NO_PROXY).
    proxy_port = int(os.getenv("MODEL_PROXY_PORT") or 0) or None
    proxy = {}
    if proxy_port:
        proxy_url = f"http://{parsed.hostname}:{proxy_port}"
        proxy = {"HTTPS_PROXY": proxy_url, "HTTP_PROXY": proxy_url, "NO_PROXY": ",".join(sorted({parsed.hostname, *addresses}))}
    # Simple mode (D-239): the employee's own Claude takes the Gateway's private CA from the managed settings, so a terminal
    # opened before the install connects too; the session variable alone left it at UNABLE_TO_GET_ISSUER_CERT_LOCALLY
    # (pj2 10-25). The path is where the kit writes the CA. Codex still needs the session variable.
    # ponytail: field mode stands for "kits carry the private CA"; record the kit's CA at enrollment if that ever differs.
    ca_env = {}
    if (device.get("detail") or {}).get("mode") == "simple" and os.getenv("MCP_FIELD_MODE") == "1":  # managed_mode written out: some checks load managed_policy alone
        if windows:
            programs = re.search(r'"([A-Za-z]:\\[^"]+)\\managed-windows\.py"', helper or "")
            if programs and detail.get("local_sid"):
                ca_env = {"NODE_EXTRA_CA_CERTS": programs.group(1) + "\\launchers\\" + detail["local_sid"] + "\\root.crt"}
        elif managed_platform(device) == "linux":
            ca_env = {"NODE_EXTRA_CA_CERTS": f"/usr/local/lib/mcpgw-managed/ca-{device['local_uid']}.crt"}
    # Built-in features and the harness account's connectors are allowed unless an administrator blocked them (D-298).
    controls = await connectors.managed_controls(connection)
    # Every MCP tool call the harness makes, on any path, is reported by a managed PostToolUse hook that runs the kit's
    # own agent (D-301). Only managed hooks load (allowManagedHooksOnly / allow_managed_hooks_only).
    hook_dir = hook_python = None
    if windows and '\\managed-windows.py"' in (helper or ""):
        head = helper[:helper.index('\\managed-windows.py"')]
        hook_dir = head[head.rfind('"') + 1:]
        hook_python = (hook_dir + "\\python\\python.exe").replace("\\", "/")
    elif managed_platform(device) == "linux":
        hook_dir, hook_python = "/usr/local/lib/mcpgw-managed", "/usr/bin/python3"

    def hook_args(harness: str) -> list:
        return ["-I", "-S", "-X", "utf8", (hook_dir + "/agent.py").replace(chr(92), "/"), "hook", harness]

    def hook(harness: str) -> str:
        # Codex on Windows runs hook commands in PowerShell, where a quoted path is a string until `&` calls it (pj3 10-31).
        return ("& " if windows else "") + " ".join(f'"{a}"' if " " in a else a for a in [hook_python, *hook_args(harness)])

    def render(servers: list, guidance: str | None) -> dict:
        routes = {s: public + "/mcp/" + s + "/" for s in servers}
        # managed-mcp.json keeps exclusive control: the employee's own and plugin servers never load. claude.ai connectors
        # load beside it only with allowAllClaudeAiMcps, and the allow-list still applies to them, so it admits https hosts
        # then (managed servers skip the list); the deny-list blocks the ones an administrator closed.
        allowed = [{"serverUrl": u} for u in routes.values()] + ([{"serverUrl": "https://*/*"}] if controls["claude_connectors"] else [])
        settings = {"allowAllClaudeAiMcps": controls["claude_connectors"], "disableClaudeAiConnectors": not controls["claude_connectors"],
                    # Claude in Chrome is a built-in server the managed set blocks unless this device setting allows it.
                    "allowClaudeInChromeWithManagedMcp": controls["claude_chrome"],
                    "allowManagedMcpServersOnly": True, "allowedMcpServers": allowed,
                    "deniedMcpServers": controls["claude_servers_denied"],
                    "strictKnownMarketplaces": [],
                    # Account-synced plugins and skills load from the claude.ai account, outside the managed set
                    # (a synced productivity plugin loaded); only `false` is honoured, so this cannot be undone
                    # from the user's settings. Web tools reach the web through the account, not the Gateway:
                    # the deny rules close them, and only managed permission rules count so the account cannot
                    # allow them again. The Gateway servers stay pre-approved in the harness; the Gateway decides.
                    "syncClaudeAiPlugins": False, "syncClaudeAiSkills": False,
                    "allowManagedPermissionRulesOnly": True,
                    "permissions": {"allow": [f"mcp__{s}" for s in routes], "deny": controls["claude_tools_denied"]},
                    # User, project and plugin hooks run commands the harness starts; a hook could call the
                    # header helper the harness profile may run (DEV-42). Only managed hooks load, and the
                    # same gate narrows statusLine and fileSuggestion to managed values (D-147).
                    "allowManagedHooksOnly": True}
        if hook_dir:
            # Executable and arguments apart: Claude Code on Windows runs hooks in Git Bash or PowerShell, whichever it has.
            settings["hooks"] = {"PostToolUse": [{"matcher": "mcp__.*", "hooks": [{"type": "command", "command": hook_python,
                                                                                   "args": hook_args("claude"), "timeout": 10}]}]}
        if guidance:
            settings["claudeMd"] = guidance  # managed-only; users cannot exclude it (code.claude.com/docs/en/memory)
        if proxy or ca_env:
            settings["env"] = {**proxy, **ca_env}
        off = set(controls["codex_features_off"])
        # Plugins stay off (they are reviewed, not built in); ChatGPT apps follow the connector switch.
        features_off = sorted({"plugins"} | (off - {"web_search"}) | (set() if controls["codex_apps"] else {"apps"}))
        # Per-app blocks go in requirements: `enabled = false` from any layer wins and the user cannot turn it back on.
        disabled_apps = "".join(f"\n[apps.{a}]\nenabled = false\n" for a in controls["codex_apps_disabled"])
        codex_servers = "".join(f'\n[mcp_servers.{s}]\nurl = {json_document(u).strip()}\nhttp_headers_helper = {json_document(helper).strip()}\n'
                                'default_tools_approval_mode = "approve"\nstartup_timeout_sec = 30\ntool_timeout_sec = 300\n' for s, u in routes.items())
        files = {
            "managed-mcp.json": json_document({"mcpServers": {s: {"type": "http", "url": url,
                        "headersHelper": helper, "timeout": 300000} for s, url in routes.items()}}),
            "managed-settings.json": json_document(settings),
            # Codex user and plugin hooks are the same command surface as Claude's (D-147).
            "requirements.toml": ('allowed_web_search_modes = ["disabled"]\n' if "web_search" in off else "")
                        + ("allow_browser_and_computer_use = false\n" if {"browser_use", "computer_use"} <= off else "")
                        + 'allow_managed_hooks_only = true\n'
                        # An absent table leaves Codex unconstrained; present but empty disables every MCP server
                        # (learn.chatgpt.com managed configuration). A device with no approved server gets the empty table.
                        + '\n[mcp_servers]\n'
                        + "".join(f'\n[mcp_servers.{s}]\nidentity = {{ url = {json_document(u).strip()} }}\n' for s, u in routes.items())
                        + '\n[features]\n' + ("hooks = true\n" if hook_dir else "") + "".join(f"{f} = false\n" for f in features_off)
                        + '\n[marketplaces]\nrestrict_to_allowed_sources = true\n' + disabled_apps
                        + (f'\n[hooks]\n{"windows_managed_dir" if windows else "managed_dir"} = {json_document(hook_dir).strip()}\n'
                           '\n[[hooks.PostToolUse]]\nmatcher = "^mcp__"\n'
                           f'\n[[hooks.PostToolUse.hooks]]\ntype = "command"\ncommand = {json_document(hook("codex")).strip()}\ntimeout = 10\n'
                           if hook_dir else ""),
        }
        if windows:
            # Codex on Windows reads no managed_config.toml. requirements.toml admits only these servers;
            # their definitions go in the account's own config.toml as one marked block.
            files["codex-config.toml"] = codex_servers
        else:
            # developer_instructions is a top-level key, so it precedes the server tables.
            # Windows is left out: its block goes into the employee's own config.toml, where the key may already exist.
            files["managed_config.toml"] = ('mcp_oauth_credentials_store = "file"\n'
                                            + ('web_search = "disabled"\n' if "web_search" in off else "")
                                            + (f"developer_instructions = {json_document(guidance).strip()}\n" if guidance else "")
                                            + codex_servers)
        return files

    files = render(servers, guidance)
    policy = {"version": 2, "gateway_url": public, "gateway_ips": addresses, "gateway_port": parsed.port or (443 if parsed.scheme == "https" else 80),
              "tailscale_node_id": os.getenv("ENDPOINT_TAILSCALE_NODE_ID", ""), "servers": servers,
              "server_names": {s: (registry.server(s) or {}).get("display_name") or s for s in servers},
              "local_username": device["local_username"], "local_uid": device["local_uid"],
              "heartbeat_seconds": HEARTBEAT_INTERVAL, "max_heartbeat_age": HEARTBEAT_SECONDS, "files": files}
    if proxy_port:
        policy["proxy_port"] = proxy_port
        policy["proxy_environment"] = proxy
    if windows:
        policy.update(platform="windows", local_sid=detail.get("local_sid"))
    elif managed_platform(device) == "macos":
        policy["platform"] = "macos"
    policy["configuration_hashes"] = {k: hashlib.sha256(v.encode()).hexdigest() for k, v in files.items()}
    # control_hash is what the device must enforce and nothing that changes in ordinary use (D-238):
    # - the policy fields above: Gateway URL, IPs, port, Tailscale node, account and UID, heartbeat cadence,
    #   platform and SID, model proxy port and environment;
    # - the managed files rendered for one placeholder server and no guidance: the allow-list form
    #   (allowManagedMcpServersOnly, allowedMcpServers entry shape), protection settings (allowAllClaudeAiMcps,
    #   disableClaudeAiConnectors, strictKnownMarketplaces, sync*, allowManaged*Only, Codex requirements and
    #   features), permissions.deny, web_search, the header helper and the per-server template (approval, timeouts).
    # Left out: which servers are listed (judged per call, managed_failure) and the guidance text, which follows
    # the activation state; putting either in made every approval or activation look like tampering.
    control = {k: v for k, v in policy.items() if k not in ("servers", "server_names", "files", "configuration_hashes")}
    control["files"] = render(["server"], None)
    policy["control_hash"] = hashlib.sha256(json_document(control).encode()).hexdigest()
    policy["servers_version"] = (version or {}).get("last_value") or 0
    policy["policy_hash"] = installed_hash(policy["control_hash"], policy["configuration_hashes"])
    return policy


def json_document(value) -> str:
    import json
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def installed_hash(control_hash: str, hashes: dict) -> str:
    """policy_hash: the control a rendering was made under, bound to its file hashes. The kit echoes it with the
    hashes of the files it holds, so a heartbeat alone proves which control they were rendered for (D-238)."""
    return hashlib.sha256(json_document({"control_hash": control_hash, "configuration_hashes": hashes}).encode()).hexdigest()


def legacy_hash(policy: dict) -> str:
    """policy_hash as Gateways before D-238 computed it, over the same rendering."""
    return hashlib.sha256(json_document({k: v for k, v in policy.items() if k not in ("policy_hash", "control_hash", "servers_version", "server_names")}).encode()).hexdigest()


def policy_installed(policy: dict, reported: str | None, hashes: dict | None) -> bool:
    """The device holds a rendering of the current control; its server list and guidance may lag behind."""
    hashes = hashes or {}
    if set(hashes) != set(policy["configuration_hashes"]):
        return False
    # ponytail: the legacy branch carries kits that installed before D-238 to their next fetch; drop it once none reports one.
    return reported == installed_hash(policy["control_hash"], hashes) or (
        reported == legacy_hash(policy) and hashes == policy["configuration_hashes"])


def control_matches(policy: dict, value: str | None) -> bool:
    """A token or local job bound at issue to the control now in force (legacy: to the same rendering)."""
    return value in (policy["control_hash"], legacy_hash(policy))


def held_servers(device: dict, policy: dict) -> list:
    """The servers this device's files list: all current ones when its managed-mcp.json is the current one,
    else the list last confirmed by a heartbeat (only ever behind; a removed server is refused per call)."""
    if (device.get("configuration_hashes") or {}).get("managed-mcp.json") == policy["configuration_hashes"]["managed-mcp.json"]:
        return policy["servers"]
    return (device.get("detail") or {}).get("policy_servers") or []


async def policy_accepted(device: dict, policy: dict | None = None, *, connection=None) -> bool:
    return policy_installed(policy or await managed_policy(device, connection=connection), device.get("policy_hash"), device.get("configuration_hashes"))


async def heartbeat(device: dict, policy_hash: str, hashes: dict, checks: dict, host: dict | None = None,
                    quality: dict | None = None, user_command_settings: list | None = None) -> dict:
    policy = await managed_policy(device)
    simple = managed_mode(device) == "simple"
    # In simple mode any process of the employee can reach the header helper anyway, so a personal command helper
    # in the employee's settings is recorded (detail below), not a reason to cut the PC off (D-239).
    if user_command_settings and not simple:
        checks = {**checks, "user_command_helpers": False}
    # Only control decides (D-238): a device that has not yet fetched a server change or the guidance of its
    # new activation state is behind, not tampered with.
    installed = policy_installed(policy, policy_hash, hashes)
    # An administrator changed the harness controls a moment ago: a heartbeat for the previous rendering is a device
    # that has not fetched yet (it applies the policy before its next heartbeat), not a tampered one (D-298).
    # Only a device that holds exactly what it held at its last good heartbeat, with every check passing, is behind.
    changed = None if installed else await db.fetch_one("SELECT controls_changed_at FROM endpoint_settings WHERE id=1")
    behind = (not installed and bool(changed and changed.get("controls_changed_at"))
              and (datetime.now(UTC) - changed["controls_changed_at"]).total_seconds() < HEARTBEAT_SECONDS
              and ((device.get("detail") or {}).get("install_receipt") or {}).get("match") is True
              and policy_hash == device.get("policy_hash") and hashes == (device.get("configuration_hashes") or {})
              and set(checks) == managed_checks(device, checks) and all(value is True for value in checks.values()))
    compliant = (installed
                 and set(checks) == managed_checks(device, checks) and all(value is True for value in checks.values())
                 and (simple or not user_command_settings))
    # A new simple-mode PC whose install checks pass is activated by the Gateway itself when the organization
    # allows it (D-239); isolated installs and reinstalls of a held PC still wait for an administrator.
    automatic = (compliant and simple and device["managed_state"] == "pending"
                 and not (device.get("detail") or {}).get("held_from") and (await endpoint_settings())["auto_activate"])
    # The host report is not a compliance input: another account on the device does not
    # quarantine the managed one; it is shown as a bypass path (integrations.device_state).
    # A heartbeat without the report drops the previous one: an old "no other account"
    # must not keep standing in for a check that is no longer made.
    detail = {"host": {**host, "reported_at": datetime.now(UTC).isoformat(timespec="seconds")}} if host else {}
    detail["user_command_settings"] = user_command_settings or []
    if hashes.get("managed-mcp.json") == policy["configuration_hashes"]["managed-mcp.json"]:
        detail["policy_servers"] = policy["servers"]  # held_servers: newly approved ones wait for this
    if "user_command_helpers" in checks:
        detail["command_settings_checked"] = True
    # What the Gateway rendered (provider artifact) beside what the device says is installed.
    detail["install_receipt"] = {
        "provider_artifact_sha256": policy["configuration_hashes"], "installed_sha256": hashes,
        "policy_sha256": {"expected": policy["policy_hash"], "installed": policy_hash},
        "control_sha256": policy["control_hash"], "match": installed,
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds")}
    async with db.transaction() as connection:
        row = await (await connection.execute(
            """UPDATE endpoint_agents SET heartbeat_at=now(),last_seen_at=now(),policy_hash=%s,
                 configuration_hashes=%s,enforcement_checks=%s, detail=(detail - 'host') || %s,
                 managed_state=CASE WHEN NOT %s AND NOT %s THEN 'quarantined' WHEN %s AND managed_state='pending' THEN 'active'
                                    ELSE managed_state END,
                 activated_by=CASE WHEN %s AND managed_state='pending' THEN 'auto' ELSE activated_by END,
                 activated_at=CASE WHEN %s AND managed_state='pending' THEN now() ELSE activated_at END
               WHERE endpoint_id=%s AND status='active' RETURNING managed_state""",
            (policy_hash, Jsonb(hashes), Jsonb(checks), Jsonb(detail), compliant, behind, automatic, automatic, automatic,
             device["endpoint_id"]))).fetchone()
        if not row:
            raise PermissionError("폐기한 장치는 heartbeat로 복구할 수 없습니다.")
        if automatic and row["managed_state"] == "active" and device["managed_state"] == "pending":
            await connection.execute(
                "INSERT INTO endpoint_managed_events(endpoint_id,owner_token,kind,detail) VALUES (%s,%s,'activated',%s)",
                (device["endpoint_id"], device["owner_token"], Jsonb({"actor": "auto", "note": "설치 점검 통과로 자동 활성화",
                                                                      "policy_hash": policy_hash})))
        if quality:
            await connection.execute(
                """INSERT INTO endpoint_network_samples(endpoint_id,measured_at,rtt_p50_ms,rtt_p95_ms,jitter_ms,failure_pct,probes)
                   VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (endpoint_id, measured_at) DO NOTHING""",
                (device["endpoint_id"], quality["measured_at"], quality["rtt_p50_ms"], quality["rtt_p95_ms"],
                 quality["jitter_ms"], quality["failure_pct"], quality["probes"]))
            await connection.execute("DELETE FROM endpoint_network_samples WHERE measured_at < now() - make_interval(days => %s)",
                                     (NETWORK_RETENTION_DAYS,))
        if (not compliant and not behind) or (row["managed_state"] != device["managed_state"] and not automatic):
            await connection.execute(
                "INSERT INTO endpoint_managed_events(endpoint_id,owner_token,kind,detail) VALUES (%s,%s,'quarantined',%s)",
                (device["endpoint_id"], device["owner_token"], Jsonb({"policy_hash": policy_hash, "checks": checks,
                 "user_command_settings": user_command_settings or [],
                 "policy_match": installed,
                 "mismatched_files": sorted(name for name, expected in policy["configuration_hashes"].items()
                                            if hashes.get(name) != expected)})))
    return {"state": row["managed_state"], "compliant": compliant, "policy_hash": policy["policy_hash"]}


async def network_quality() -> dict:
    """엔드포인트에서 게이트웨이까지의 측정값. 오래된 값은 지연으로 보이지 않고 stale로 남는다."""
    rows = await db.fetch_all(
        """SELECT DISTINCT ON (a.endpoint_id) a.endpoint_id, a.hostname, s.measured_at, s.rtt_p50_ms,
                  s.rtt_p95_ms, s.jitter_ms, s.failure_pct
             FROM endpoint_agents a LEFT JOIN endpoint_network_samples s ON s.endpoint_id = a.endpoint_id
            WHERE a.status='active' AND a.agent_version<>'unregistered'
              AND (a.device_epoch IS NOT NULL OR s.endpoint_id IS NOT NULL)
            ORDER BY a.endpoint_id, s.measured_at DESC NULLS LAST""")
    now = datetime.now(UTC)
    devices, fresh = [], []
    for row in rows:
        measured = row["measured_at"]
        state = ("unknown" if measured is None else
                 "fresh" if 0 <= (now - measured).total_seconds() <= 3 * HEARTBEAT_INTERVAL else "stale")
        if state == "fresh":
            fresh.append(row["endpoint_id"])
        devices.append({
            "endpoint_id": row["endpoint_id"], "hostname": row["hostname"],
            "measured_at": measured.isoformat() if measured else None,
            "rtt_p50_ms": _round(row["rtt_p50_ms"]), "rtt_p95_ms": _round(row["rtt_p95_ms"]),
            "jitter_ms": _round(row["jitter_ms"]), "failure_pct": _round(row["failure_pct"]), "state": state})
    total = await db.fetch_one(
        """SELECT percentile_disc(0.5) WITHIN GROUP (ORDER BY rtt_p50_ms) AS p50,
                  percentile_disc(0.95) WITHIN GROUP (ORDER BY rtt_p95_ms) AS p95,
                  sum(failure_pct * probes) / NULLIF(sum(probes), 0) AS failure
             FROM endpoint_network_samples
            WHERE endpoint_id = ANY(%s::text[]) AND measured_at > now() - interval '24 hours'""", (fresh,)) or {}
    return {"devices": devices,
            "summary": {"p50_ms": _round(total.get("p50")), "p95_ms": _round(total.get("p95")),
                        "failure_pct": _round(total.get("failure")), "devices": len(fresh)}}


def _round(value: Any) -> float | None:
    return None if value is None else round(float(value), 1)


async def activate_managed(endpoint_id: str, actor: str, expected_hash: str, note: str) -> dict:
    # Compare-and-set: the reviewer approves the state actually displayed, not a
    # later changed enrollment or a heartbeat supplied by another device.
    device = await db.fetch_one("SELECT * FROM endpoint_agents WHERE endpoint_id=%s", (endpoint_id,))
    if not device or device["owner_token"] == actor:
        raise ValueError("등록 장치가 없거나 자기 소유 장치는 스스로 활성화할 수 없습니다.")
    # Activation changes only the guidance the device is served next, so the hash it reports stays valid (D-238).
    installed = policy_installed(await managed_policy(device), expected_hash, device["configuration_hashes"])
    async with db.transaction() as connection:
        changed = await connection.execute(
            """UPDATE endpoint_agents SET managed_state='active',activated_by=%s,activated_at=now()
               WHERE endpoint_id=%s AND status='active' AND policy_hash=%s
                 AND heartbeat_at>now()-interval '180 seconds' AND configuration_hashes=%s AND enforcement_checks=%s""",
            (actor, endpoint_id, expected_hash, Jsonb(device["configuration_hashes"]),
             Jsonb({key: True for key in managed_checks(device)})))
        if not installed or not changed.rowcount:
            raise ValueError("최근 정상 설치 증거가 없거나 검토한 정책이 바뀌었습니다. 장치 설치를 확인하세요.")
        await connection.execute(
            "INSERT INTO endpoint_managed_events(endpoint_id,owner_token,kind,detail) VALUES (%s,%s,'activated',%s)",
            (endpoint_id, device["owner_token"], Jsonb({"actor": actor, "note": note, "policy_hash": expected_hash})))
    return {"endpoint_id": endpoint_id, "managed_state": "active"}


async def managed_failure(principal: dict, claims: dict, *, mint: bool = False, server: str | None = None) -> str | None:
    if not principal.get("managed_required") and not claims.get("device_id"):
        return None
    if not claims.get("device_id") or (not mint and "mcp" not in str(claims.get("scope", "")).split()):
        return "관리형 엔드포인트 인증이 필요합니다. 내 PC 연결에서 설치 키트를 받으세요."
    device = await db.fetch_one("SELECT * FROM endpoint_agents WHERE endpoint_id=%s", (claims["device_id"],))
    if (not device or device["owner_token"] != principal["token"] or device["status"] != "active"
            or device["managed_state"] != "active" or device["device_epoch"] != claims.get("device_epoch")):
        return "활성 상태가 아니거나 이 사용자에게 등록되지 않은 엔드포인트입니다."
    if not device["heartbeat_at"] or (datetime.now(UTC) - device["heartbeat_at"]).total_seconds() >= HEARTBEAT_SECONDS:
        return "엔드포인트 점검 보고가 만료되어 연결을 중단했습니다."
    policy = await managed_policy(device)
    # A control change stops everything; a server list the device has not fetched yet is judged per server (D-238).
    if (not policy_installed(policy, device["policy_hash"], device["configuration_hashes"])
            or (not mint and not control_matches(policy, claims.get("device_policy")))):
        return "엔드포인트 정책이 최신 정책과 달라 연결을 중단했습니다."
    held = held_servers(device, policy)
    if server and held is not policy["servers"]:
        if server not in policy["servers"]:
            return "사용할 수 없는 서버입니다."
        if server not in held:
            return "새로 승인된 서버입니다. PC가 새 정책을 적용하면 사용할 수 있습니다."
    return None


# ── 탐색 정책 ────────────────────────────────────────────────────────────────
#
# 범위를 에이전트가 정하면 그것은 조직이 통제하지 못하는 스캐너다. 여기서 정하고
# 에이전트는 받아서 그대로 따른다. 비어 있으면 루프백만 본다.

async def scan_policy() -> dict:
    row = await db.fetch_one("SELECT * FROM endpoint_scan_policy WHERE id=1")
    if not row:
        return {"enabled": False, "allowed_cidrs": [], "ports": [], "max_hosts": 0,
                "connect_timeout_ms": 300, "probe_mcp": True, "interval_seconds": 900}
    item = dict(row)
    item.pop("id", None)
    if item.get("updated_at"):
        item["updated_at"] = item["updated_at"].isoformat()
    return item


async def set_scan_policy(actor: str, **fields: Any) -> dict:
    allowed = fields.get("allowed_cidrs")
    if allowed is not None:
        for entry in allowed:
            network = ipaddress.ip_network(str(entry), strict=False)
            # 공인 대역 스캔은 이 저장소가 지원하지 않는다. 내부 자산 탐색과
            # 인터넷 스캔은 법적으로도 운영상으로도 다른 행위다.
            if not (network.is_private or network.is_loopback or network.is_link_local):
                raise ValueError("내부 대역만 지정할 수 있습니다: " + str(entry))
            if network.num_addresses > 4096:
                raise ValueError("대역이 너무 넓습니다(최대 /20): " + str(entry))
    ports = fields.get("ports")
    if ports is not None and any(not (0 < int(p) < 65536) for p in ports):
        raise ValueError("포트는 1~65535 범위여야 합니다.")
    sets, params = [], []
    for column in ("enabled", "allowed_cidrs", "ports", "max_hosts",
                   "connect_timeout_ms", "probe_mcp", "interval_seconds"):
        if fields.get(column) is not None:
            sets.append(column + "=%s")
            params.append(Jsonb(fields[column]) if column in {"allowed_cidrs", "ports"} else fields[column])
    if not sets:
        return await scan_policy()
    params.append(actor)
    await db.execute(
        "UPDATE endpoint_scan_policy SET " + ", ".join(sets)
        + ", updated_by=%s, updated_at=now() WHERE id=1",
        tuple(params),
    )
    return await scan_policy()


# ── 망 관측 수신 ─────────────────────────────────────────────────────────────

def listener_fingerprint(source: str, address: str, port, command_line: str) -> str:
    joined = "\x1f".join([source, address.lower(), str(port or ""),
                          " ".join((command_line or "").split())])
    return hashlib.sha256(joined.encode()).hexdigest()


def _listener_keys(address: str, port, server_name: str, command_line: str) -> set:
    base = address.lower() + ":" + str(port or "")
    keys = {
        "http://" + base + "/mcp/",
        "http://" + base + "/mcp",
        "http://" + base,
        (server_name or "").strip().lower(),
        " ".join((command_line or "").split()),
    }
    return keys - {""}


async def ingest_listeners(endpoint_id: str, findings: list, *, complete: bool = False,
                           sources: list[str] | None = None, origin: str = "manual") -> dict:
    sources = ["local-socket", "network", "stdio-process"] if sources is None else sources
    if (not isinstance(complete, bool) or len(findings) > 500 or not isinstance(sources, list)
            or not sources or len(set(sources)) != len(sources)
            or not set(sources) <= {"local-socket", "network", "stdio-process"}
            or any(item.get("source", "network") not in sources for item in findings)):
        raise ValueError("알 수 없거나 일치하지 않는 관측 범위입니다.")
    async with db.transaction() as connection:
        return await _ingest_listeners(connection, endpoint_id, findings, complete, sources, _origin(origin))


async def _ingest_listeners(connection, endpoint_id: str, findings: list, complete: bool, sources: list,
                            origin: str) -> dict:
    """한 엔드포인트가 관측한 리스너 목록 전체를 정본으로 교체한다.

    인벤토리와 같은 이유로 누적이 아니라 교체다. 꺼진 서버가 표에 남으면
    "지금 열려 있는 미등록 경로 수"를 셀 수 없고, 그 수가 정책 입력이다.
    """
    agent = await (await connection.execute("SELECT * FROM endpoint_agents WHERE endpoint_id=%s FOR UPDATE", (endpoint_id,))).fetchone()
    if not agent:
        raise ValueError("등록되지 않은 엔드포인트입니다.")
    index = await _registry_index(connection)

    known = {row["fingerprint"]: row["hash"] for row in await (await connection.execute(
        "SELECT fingerprint, provenance->>'raw_sha256' AS hash FROM endpoint_listeners WHERE endpoint_id=%s",
        (endpoint_id,))).fetchall()}
    seen = []
    counts = {"registered": 0, "shadow": 0, "retired-residue": 0}
    evidence = {"confirmed": 0, "suspected": 0, "unknown": 0}
    duplicates = 0
    for item in findings:
        raw = {key: value for key, value in item.items() if key != "provenance"}
        steps: list[str] = []
        source = str(raw.get("source") or "network")
        if source not in {"local-socket", "network", "stdio-process"}:
            source = "network"
        address = _clip(str(raw.get("address") or ""), 200, steps)
        port_raw = raw.get("port")
        port = int(port_raw) if str(port_raw).isdigit() else None
        command_line = str(raw.get("command_line") or "")
        if command_line and not command_line.startswith("sha256:"):
            command_line = command_digest(command_line)
            steps.append("command_sha256")
        command_line = _clip(command_line, 600, steps)
        process_name = _clip(str(raw.get("process_name") or ""), 120, steps) or None
        mcp_evidence = str(raw.get("mcp_evidence") or "unknown")
        if mcp_evidence not in evidence:
            mcp_evidence = "unknown"
        server_name = _clip(str(raw.get("server_name") or ""), 200, steps) or None
        server_version = _clip(str(raw.get("server_version") or ""), 80, steps) or None
        protocol_version = _clip(str(raw.get("protocol_version") or ""), 40, steps) or None
        mark = listener_fingerprint(source, address, port, command_line)
        provenance = provenance_of(item.get("provenance"), projection_of(
            {"source": source, "address": address, "port": port, "process_name": process_name,
             "command_line": command_line, "mcp_evidence": mcp_evidence, "server_name": server_name,
             "server_version": server_version, "protocol_version": protocol_version}, LISTENER_FIELDS), steps)
        duplicates += bool(provenance["raw_sha256"]) and known.get(mark) == provenance["raw_sha256"]

        matched = None
        candidates = _listener_keys(address, port, server_name or "", command_line)
        for entry in index:
            route_candidates = _listener_keys(address, port, "", "") if entry["id"] == "__gateway__" else candidates
            if entry["keys"] & route_candidates:
                matched = entry
                break
        if matched is None:
            classification, registry_match = "shadow", None
        elif matched["id"] == "__gateway__":
            # 강제 경로 자신. Registry 행이 아니므로 registry_match는 비운다.
            classification, registry_match = "registered", None
        elif matched["lifecycle"] in {"TERMINATING", "RETIRED"}:
            classification, registry_match = "retired-residue", matched["id"]
        else:
            classification, registry_match = "shadow", matched["id"]
        counts[classification] += 1
        evidence[mcp_evidence] += 1
        seen.append(mark)
        await connection.execute(
            """INSERT INTO endpoint_listeners(
                 endpoint_id, source, address, port, process_name, command_line,
                 mcp_evidence, server_name, server_version, protocol_version,
                 fingerprint, registry_match, classification, raw, origin, provenance)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (endpoint_id, fingerprint) DO UPDATE SET
                 observed_at=now(), mcp_evidence=EXCLUDED.mcp_evidence,
                 server_name=EXCLUDED.server_name, server_version=EXCLUDED.server_version,
                 protocol_version=EXCLUDED.protocol_version,
                 registry_match=EXCLUDED.registry_match,
                 classification=EXCLUDED.classification, raw=EXCLUDED.raw,
                 origin=EXCLUDED.origin, provenance=EXCLUDED.provenance""",
            (endpoint_id, source, address, port, process_name, command_line,
             mcp_evidence, server_name, server_version, protocol_version,
             mark, registry_match, classification, Jsonb({**raw, "command_line": command_line}),
             origin, Jsonb(provenance)),
        )
    removed = 0
    if complete:
        removed = (await connection.execute(
            "DELETE FROM endpoint_listeners WHERE endpoint_id=%s AND source = ANY(%s::text[]) AND NOT (fingerprint = ANY(%s::text[]))",
            (endpoint_id, sources, seen))).rowcount
    await connection.execute(
        "UPDATE endpoint_agents SET last_seen_at=now(), last_scan_at=CASE WHEN %s THEN now() ELSE last_scan_at END WHERE endpoint_id=%s",
        (complete, endpoint_id))
    for channel, covered in (("process", ["stdio-process"]), ("network", ["local-socket", "network"])):
        reported = [source for source in covered if source in sources]
        if reported:
            count = sum(str(item.get("source") or "network") in reported for item in findings)
            await _record_observation(connection, endpoint_id, channel, "success" if complete else "partial", count,
                                      "" if complete else "incomplete_snapshot", reported)
    return {"endpoint_id": endpoint_id, "accepted": len(findings), "duplicates": int(duplicates), "removed": removed,
            "counts": counts, "evidence": evidence, "complete": complete, "sources": sources}


async def listeners_page(classification: str | None = None, limit: int = 100, cursor: str | None = None) -> dict:
    limit, after = _bounds(limit, cursor)
    where, params = [], []
    if classes := _classes(classification):
        where.append("l.classification = ANY(%s::text[])")
        params.append(classes)
    base = " AND ".join(where) or "TRUE"
    total = await db.fetch_one("SELECT count(*) AS n FROM endpoint_listeners l WHERE " + base, tuple(params))
    rows = await db.fetch_all(
        """SELECT l.*, a.hostname, a.owner_token, p.display_name AS owner_name,
                  s.display_name AS registry_name, s.lifecycle, a.detail->'observation' AS observation
             FROM endpoint_listeners l
             JOIN endpoint_agents a USING (endpoint_id)
             LEFT JOIN principals p ON p.token = a.owner_token
             LEFT JOIN mcp_servers s ON s.id = l.registry_match
            WHERE """ + base + (" AND l.id < %s" if after else "") + " ORDER BY l.id DESC LIMIT %s",
        (*params, *([after] if after else []), limit + 1))
    rows, next_cursor = _window(rows, limit)
    result = []
    for row in rows:
        item = _listed(row)
        channel = "process" if item["source"] == "stdio-process" else "network"
        status = (item.pop("observation", None) or {}).get(channel, {})
        item["scan_source_status"] = status.get("state", "unknown")
        item["freshness"] = observation_freshness(status, item.get("observed_at"))
        if item.get("observed_at"):
            item["observed_at"] = item["observed_at"].isoformat()
        result.append(item)
    return {"rows": result, "total": int(total["n"] or 0), "limit": limit, "next_cursor": next_cursor}


OBSERVATION_CHANNELS = ("inventory", "process", "network", "os")


async def observations_page(limit: int = 100, cursor: str | None = None) -> dict:
    """엔드포인트 단위로 넘긴다. 채널 상태와 신선도는 따로 두어 수집 중단이 0건으로 읽히지 않게 한다."""
    limit = max(1, min(int(limit), PAGE_MAX))
    if cursor and not re.fullmatch(r"[A-Za-z0-9._:-]{1,120}", cursor):
        raise ValueError("잘못된 페이지 위치입니다.")
    base = "status='active' AND agent_version<>'unregistered'"
    total = await db.fetch_one("SELECT count(*) AS n FROM endpoint_agents WHERE " + base)
    agents = await db.fetch_all(
        """SELECT endpoint_id, hostname, last_seen_at, detail->'observation' AS observation
             FROM endpoint_agents WHERE """ + base + " AND endpoint_id > %s ORDER BY endpoint_id LIMIT %s",
        (cursor or "", limit + 1))
    more = len(agents) > limit
    agents = agents[:limit]
    now = datetime.now(UTC)
    rows = []
    for agent in agents:
        online = agent["last_seen_at"] is not None and (now - agent["last_seen_at"]).total_seconds() <= 900
        for channel in OBSERVATION_CHANNELS:
            status = (agent["observation"] or {}).get(channel, {})
            reported = status.get("reported_at")
            try:
                age = (now - datetime.fromisoformat(str(reported).replace("Z", "+00:00"))).total_seconds()
            except (TypeError, ValueError):
                age = None
            rows.append({
                "endpoint_id": agent["endpoint_id"], "hostname": agent["hostname"], "channel": channel,
                "state": status.get("state", "unknown"), "reported_at": reported,
                "last_success_at": status.get("last_success_at"), "accepted_count": status.get("accepted_count"),
                "error_code": status.get("error_code") or "",
                "freshness": "unknown" if age is None or age < 0 else "fresh" if age <= 180 else "stale",
                "agent_state": "online" if online else "offline"})
    return {"rows": rows, "total": int(total["n"] or 0), "limit": limit,
            "next_cursor": agents[-1]["endpoint_id"] if more else None}


# kind -> (table, alias, time column). A record keeps its own source and time.
RECORD_KINDS = {"config": ("endpoint_inventory", "i", "reported_at"),
                "listener": ("endpoint_listeners", "l", "observed_at"),
                "os-event": ("endpoint_os_events", "e", "observed_at")}


async def record_detail(kind: str, record_id: int) -> dict | None:
    table, alias, when = RECORD_KINDS[kind]
    row = await db.fetch_one(
        f"SELECT {alias}.*, a.hostname, a.owner_token FROM {table} {alias} "
        f"JOIN endpoint_agents a USING (endpoint_id) WHERE {alias}.id=%s", (record_id,))
    if not row:
        return None
    item = dict(row)
    item.pop("raw", None)
    item["record_kind"], item["at"] = kind, item[when].isoformat()
    for key in ("reported_at", "observed_at", "received_at"):
        if item.get(key):
            item[key] = item[key].isoformat()
    return item


def _record(kind: str, row: dict, when: str) -> dict:
    provenance = row.get("provenance") or {}
    title = {"os-event": lambda: (row["details"] or {}).get("executable") or (row["details"] or {}).get("destination_ip"),
             "listener": lambda: f"{row['address']}:{row['port']}" if row.get("port") else row["address"],
             "config": lambda: row["server_label"]}[kind]()
    return {"kind": kind, "id": row["id"], "at": row[when].isoformat(), "endpoint_id": row["endpoint_id"],
            "source": provenance.get("collector"), "origin": row.get("origin"), "title": title,
            "denial_class": row.get("denial_class"), "provenance_state": provenance.get("state")}


async def correlate(*, decision_id: int | None = None, kind: str | None = None, record_id: int | None = None,
                    window_seconds: int = 300) -> dict | None:
    """같은 엔드포인트 장치와 같은 사용자의 기록을 시간 창 안에서 따로 늘어놓는다.

    호출·전송 의도는 request_id로 정확히 잇고, OS 관측은 장치·주체·시간 창의
    일치만 보조 근거로 표시한다. 시간만 겹치는 행은 결과에 넣지 않는다.
    """
    window = max(10, min(int(window_seconds), 3600))
    span = timedelta(seconds=window)
    if decision_id is not None:
        call = await db.fetch_one(
            """SELECT id, created_at, request_id, trace_id, user_token, decision, policy_id, server_id, tool_name,
                      client->>'device_id' AS device_id
                 FROM decisions WHERE id=%s""", (decision_id,))
        if not call:
            return None
        device = await db.fetch_one(
            "SELECT endpoint_id FROM endpoint_agents WHERE endpoint_id=%s AND owner_token=%s",
            (call["device_id"], call["user_token"])) if call["device_id"] else None
        intent = await db.fetch_one(
            "SELECT request_id, decision_id, attempted_at, state FROM dispatch_intents WHERE request_id=%s",
            (call["request_id"],)) if call.get("request_id") else None
        records: list[dict] = []
        if device:
            low, high = call["created_at"] - span, call["created_at"] + span
            for record_kind, (table, alias, when) in RECORD_KINDS.items():
                for row in await db.fetch_all(
                        f"SELECT {alias}.*, a.owner_token AS event_user_token FROM {table} {alias} "
                        f"JOIN endpoint_agents a USING (endpoint_id) WHERE {alias}.endpoint_id=%s "
                        f"AND {alias}.{when} BETWEEN %s AND %s ORDER BY {alias}.{when} DESC LIMIT 25",
                        (device["endpoint_id"], low, high)):
                    item = _record(record_kind, row, when)
                    item["at"] = row[when]
                    item["event_user_token"] = row["event_user_token"]
                    records.append(item)
        result = correlation_result(call, intent, records, bound=bool(device), window_seconds=window)
        egress = await server_egress.for_decision(call, intent)
        result['records'].extend(egress.pop('records'))
        result['records'].sort(key=lambda row: datetime.fromisoformat(row['at']), reverse=True)
        result['server_egress'] = egress
        return result
    if kind not in RECORD_KINDS or record_id is None:
        raise ValueError("알 수 없는 기록 종류입니다.")
    table, alias, when = RECORD_KINDS[kind]
    found = await db.fetch_one(
        f"SELECT {alias}.id, {alias}.{when} AS at, {alias}.endpoint_id, a.owner_token FROM {table} {alias} "
        f"JOIN endpoint_agents a USING (endpoint_id) WHERE {alias}.id=%s", (record_id,))
    if not found:
        return None
    anchor = {"kind": kind, "id": found["id"], "at": found["at"].isoformat(), "endpoint_id": found["endpoint_id"]}
    rows = await db.fetch_all(
        """SELECT d.id, d.created_at, d.decision, d.policy_id, d.server_id, d.tool_name, d.client->>'traceparent' AS traceparent
             FROM decisions d WHERE d.user_token=%s AND d.client->>'device_id'=%s AND d.created_at BETWEEN %s AND %s
            ORDER BY d.created_at DESC LIMIT 25""",
        (found["owner_token"], found["endpoint_id"], found["at"] - span, found["at"] + span)) if found["owner_token"] else []
    return {"anchor": anchor, "bound": bool(found["owner_token"]), "window_seconds": window,
            "records": [{"kind": "decision", "id": row["id"], "at": row["created_at"].isoformat(), "endpoint_id": found["endpoint_id"],
                         "source": "gateway", "decision": row["decision"], "policy_id": row["policy_id"],
                         "title": f"{row['server_id']}.{row['tool_name']}", "traceparent": row["traceparent"]} for row in rows]}


async def shadow_listener_count_for(user_token: str) -> int:
    """이 사용자의 엔드포인트 망에서 확인된 미등록 MCP 리스너 수.

    MCP 여부가 확인된 것만 센다. "열려 있는데 뭔지 모르는 포트"를 정책 입력으로
    쓰면 사무실 프린터가 어느 직원의 호출을 경보로 만든다.
    """
    if not user_token:
        return 0
    row = await db.fetch_one(
        """SELECT count(*) AS n FROM endpoint_listeners l
             JOIN endpoint_agents a USING (endpoint_id)
            WHERE a.owner_token=%s AND l.classification='shadow'
              AND l.mcp_evidence IN ('confirmed','suspected')""",
        (user_token,),
    )
    return int(row["n"] or 0) if row else 0
