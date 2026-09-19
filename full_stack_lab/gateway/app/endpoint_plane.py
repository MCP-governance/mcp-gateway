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
from typing import Any

from psycopg.types.json import Jsonb

from . import db

AGENT_PROTOCOL = "1"

# 클라이언트 설정이 서버를 가리키는 방식은 제품마다 다르다. 비교 가능한 형태로
# 줄여야 Registry의 endpoint와 대조된다. 지나치게 관대하게 맞추면 서로 다른
# 서버가 같은 것으로 접히고, 그러면 섀도 서버가 등록 서버로 분류된다.
def normalise(transport: str, endpoint_ref: str) -> str:
    value = (endpoint_ref or "").strip()
    if transport in {"stdio", "STDIO"}:
        return " ".join(value.split())
    return value.rstrip("/").lower()


def fingerprint(config_path: str, server_label: str, transport: str, endpoint_ref: str) -> str:
    return hashlib.sha256(
        "\x1f".join([config_path, server_label, transport, normalise(transport, endpoint_ref)]).encode()
    ).hexdigest()


async def enroll(endpoint_id: str, hostname: str, platform: str, agent_version: str,
                 owner_token: str | None, detail: dict | None = None) -> dict:
    await db.execute(
        """INSERT INTO endpoint_agents(endpoint_id, hostname, platform, agent_version, owner_token, detail)
           VALUES (%s,%s,%s,%s,%s,%s)
           ON CONFLICT (endpoint_id) DO UPDATE SET
             hostname=EXCLUDED.hostname, platform=EXCLUDED.platform,
             agent_version=EXCLUDED.agent_version, owner_token=EXCLUDED.owner_token,
             detail=EXCLUDED.detail, last_seen_at=now()""",
        (endpoint_id, hostname, platform, agent_version, owner_token, Jsonb(detail or {})),
    )
    return await db.fetch_one("SELECT * FROM endpoint_agents WHERE endpoint_id=%s", (endpoint_id,))


async def _registry_index() -> list[dict]:
    rows = await db.fetch_all(
        "SELECT id, transport, endpoint, display_name, lifecycle, status FROM mcp_servers"
    )
    index = []
    for row in rows:
        index.append({
            "id": row["id"],
            "lifecycle": row["lifecycle"],
            "status": row["status"],
            "keys": {
                normalise(row["transport"], row["endpoint"] or ""),
                normalise("stdio", row["endpoint"] or ""),
                row["id"].lower(),
                (row["display_name"] or "").strip().lower(),
            } - {""},
        })
    return index


def _match(index: list[dict], transport: str, endpoint_ref: str, server_label: str) -> dict | None:
    candidates = {normalise(transport, endpoint_ref), (server_label or "").strip().lower()} - {""}
    for entry in index:
        if entry["keys"] & candidates:
            return entry
    return None


async def ingest(endpoint_id: str, entries: list[dict]) -> dict:
    """한 엔드포인트가 보고한 설정 목록 전체를 정본으로 교체한다.

    누적이 아니라 교체인 이유는, 설정에서 지워진 항목이 관리대장에 남아 있으면
    잔존이 해소되어도 C1이 영원히 미충족이 되기 때문이다. 회수를 확인할 방법이
    없는 통제는 회수를 유도하지 못한다.
    """
    agent = await db.fetch_one("SELECT * FROM endpoint_agents WHERE endpoint_id=%s", (endpoint_id,))
    if not agent:
        raise ValueError("등록되지 않은 엔드포인트입니다. 먼저 enroll 하세요.")
    index = await _registry_index()

    seen: list[str] = []
    counts = {"registered": 0, "shadow": 0, "retired-residue": 0}
    for raw in entries:
        config_path = str(raw.get("config_path") or "unknown")[:400]
        server_label = str(raw.get("server_label") or "unnamed")[:200]
        transport = str(raw.get("transport") or "stdio")[:40]
        endpoint_ref = str(raw.get("endpoint_ref") or "")[:600]
        mark = fingerprint(config_path, server_label, transport, endpoint_ref)
        matched = _match(index, transport, endpoint_ref, server_label)
        if matched is None:
            classification = "shadow"
            registry_match = None
        elif matched["lifecycle"] in {"TERMINATING", "RETIRED"}:
            classification = "retired-residue"
            registry_match = matched["id"]
        else:
            classification = "registered"
            registry_match = matched["id"]
        counts[classification] += 1
        seen.append(mark)
        await db.execute(
            """INSERT INTO endpoint_inventory(
                 endpoint_id, config_path, server_label, transport, endpoint_ref,
                 fingerprint, registry_match, classification, raw)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (endpoint_id, fingerprint) DO UPDATE SET
                 reported_at=now(), registry_match=EXCLUDED.registry_match,
                 classification=EXCLUDED.classification, raw=EXCLUDED.raw""",
            (endpoint_id, config_path, server_label, transport, endpoint_ref,
             mark, registry_match, classification, Jsonb(raw)),
        )
    removed = await db.execute(
        "DELETE FROM endpoint_inventory WHERE endpoint_id=%s AND NOT (fingerprint = ANY(%s::text[]))",
        (endpoint_id, seen),
    )
    await db.execute(
        "UPDATE endpoint_agents SET last_seen_at=now() WHERE endpoint_id=%s", (endpoint_id,)
    )
    await _link_residue_to_cases(endpoint_id)
    return {"endpoint_id": endpoint_id, "accepted": len(entries),
            "removed": removed, "counts": counts}


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


async def inventory(classification: str | None = None, limit: int = 200) -> list[dict]:
    query = """SELECT i.*, a.hostname, a.platform, a.owner_token, a.last_seen_at,
                      s.display_name AS registry_name, s.lifecycle
                 FROM endpoint_inventory i
                 JOIN endpoint_agents a USING (endpoint_id)
                 LEFT JOIN mcp_servers s ON s.id = i.registry_match"""
    params: list[Any] = []
    if classification:
        query += " WHERE i.classification=%s"
        params.append(classification)
    query += " ORDER BY i.reported_at DESC LIMIT %s"
    params.append(limit)
    rows = await db.fetch_all(query, tuple(params))
    result = []
    for row in rows:
        item = dict(row)
        for key in ("reported_at", "last_seen_at"):
            if item.get(key):
                item[key] = item[key].isoformat()
        result.append(item)
    return result


async def agents() -> list[dict]:
    rows = await db.fetch_all(
        """SELECT a.*, count(i.id) AS entries,
                  count(i.id) FILTER (WHERE i.classification='shadow') AS shadow,
                  count(i.id) FILTER (WHERE i.classification='retired-residue') AS residue
             FROM endpoint_agents a LEFT JOIN endpoint_inventory i USING (endpoint_id)
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
            WHERE a.owner_token=%s AND i.classification='shadow'""",
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
        """SELECT classification, count(*) AS n FROM endpoint_inventory GROUP BY classification"""
    )
    counts = {row["classification"]: int(row["n"]) for row in rows}
    agent_rows = await db.fetch_all(
        """SELECT count(*) AS total,
                  count(*) FILTER (WHERE last_seen_at > now() - interval '15 minutes') AS fresh
             FROM endpoint_agents"""
    )
    stats = agent_rows[0] if agent_rows else {"total": 0, "fresh": 0}
    return {
        "known_endpoints": int(stats["total"] or 0),
        "reporting_recently": int(stats["fresh"] or 0),
        "registered": counts.get("registered", 0),
        "shadow": counts.get("shadow", 0),
        "retired_residue": counts.get("retired-residue", 0),
        "note": "조직 전체 자산 대비 커버리지는 이 실습이 자산 목록을 갖고 있지 않아 산출하지 않습니다.",
    }
