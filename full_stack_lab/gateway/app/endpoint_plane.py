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
import os
import secrets
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


def command_digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(" ".join((value or "").split()).encode()).hexdigest()


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


# 이 게이트웨이 자신의 MCP 파사드. 강제 경로 그 자체를 섀도로 올리면 모든
# 엔드포인트가 매번 오탐을 하나씩 보고하고, 그 목록은 곧 읽히지 않게 된다.
SELF_MCP_NAME = "mcp-governance-security-gateway"


async def _registry_index() -> list[dict]:
    rows = await db.fetch_all(
        """SELECT id, transport, endpoint, display_name, advertised_name, lifecycle, status
             FROM mcp_servers"""
    )
    index = [{
        "id": "__gateway__",
        "lifecycle": "OPERATING",
        "status": "READY",
        "keys": {SELF_MCP_NAME},
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
        elif matched["id"] == "__gateway__":
            classification = "registered"
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


# ── 장치 자격 ────────────────────────────────────────────────────────────────
#
# 사람 계정과 완전히 다른 축이다. 로그인하지 않고, 사람의 토큰을 발급받지 않으며,
# 할 수 있는 일이 scopes에 적힌 것뿐이다. 그래서 이 자격이 새도 관리자 API는
# 열리지 않는다 — v1.5까지 이 평면의 가장 큰 구멍이 그것이었다.

DEVICE_SCOPES = ("inventory", "netscan")


def _hash_key(raw: str) -> str:
    # 장치 키는 32바이트 난수라 사전공격 대상이 아니다. 유추 불가능한 고엔트로피
    # 비밀에는 느린 KDF가 주는 이득이 없고, 매 보고마다 bcrypt를 돌리면 보고
    # 주기가 짧은 대규모 배치에서 게이트웨이가 먼저 무너진다.
    pepper = os.getenv("ENDPOINT_KEY_PEPPER", "")
    return hashlib.sha256((pepper + raw).encode()).hexdigest()


async def issue_device(endpoint_id: str, hostname: str, platform: str, owner_token: str | None,
                       scopes: list[str], issued_by: str) -> dict:
    """장치를 등록하고 자격을 한 번만 돌려준다.

    평문 키는 이 응답에만 존재한다. 저장은 해시로 하고, 잃어버리면 재발급한다.
    다시 보여줄 수 있게 두면 관리 화면이 조직에서 두 번째로 위험한 표가 된다.
    """
    unknown = sorted(set(scopes) - set(DEVICE_SCOPES))
    if unknown:
        raise ValueError("알 수 없는 장치 권한입니다: " + ", ".join(unknown))
    raw = secrets.token_urlsafe(32)
    await db.execute(
        """INSERT INTO endpoint_agents(endpoint_id, hostname, platform, agent_version,
                                       owner_token, key_hash, key_prefix, scopes, status,
                                       issued_by, issued_at)
           VALUES (%s,%s,%s,'unregistered',%s,%s,%s,%s,'active',%s,now())
           ON CONFLICT (endpoint_id) DO UPDATE SET
             hostname=EXCLUDED.hostname, platform=EXCLUDED.platform,
             owner_token=EXCLUDED.owner_token, key_hash=EXCLUDED.key_hash,
             key_prefix=EXCLUDED.key_prefix, scopes=EXCLUDED.scopes,
             status='active', issued_by=EXCLUDED.issued_by, issued_at=now()""",
        (endpoint_id, hostname, platform, owner_token, _hash_key(raw), raw[:8],
         Jsonb(sorted(set(scopes))), issued_by),
    )
    return {"endpoint_id": endpoint_id, "enrollment_key": raw, "scopes": sorted(set(scopes)),
            "note": "이 키는 다시 표시되지 않습니다. 잃어버리면 재발급하세요."}


async def revoke_device(endpoint_id: str, actor: str) -> dict:
    changed = await db.execute(
        "UPDATE endpoint_agents SET status='revoked', issued_by=%s WHERE endpoint_id=%s",
        (actor, endpoint_id),
    )
    if not changed:
        raise ValueError("등록되지 않은 엔드포인트입니다.")
    return {"endpoint_id": endpoint_id, "status": "revoked"}


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
        for key in ("issued_at", "enrolled_at", "last_seen_at", "last_scan_at"):
            if item.get(key):
                item[key] = item[key].isoformat()
        result.append(item)
    return result


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


async def ingest_listeners(endpoint_id: str, findings: list) -> dict:
    """한 엔드포인트가 관측한 리스너 목록 전체를 정본으로 교체한다.

    인벤토리와 같은 이유로 누적이 아니라 교체다. 꺼진 서버가 표에 남으면
    "지금 열려 있는 미등록 경로 수"를 셀 수 없고, 그 수가 정책 입력이다.
    """
    agent = await db.fetch_one("SELECT * FROM endpoint_agents WHERE endpoint_id=%s", (endpoint_id,))
    if not agent:
        raise ValueError("등록되지 않은 엔드포인트입니다.")
    index = await _registry_index()

    seen = []
    counts = {"registered": 0, "shadow": 0, "retired-residue": 0}
    evidence = {"confirmed": 0, "suspected": 0, "unknown": 0}
    for raw in findings:
        source = str(raw.get("source") or "network")
        if source not in {"local-socket", "network", "stdio-process"}:
            source = "network"
        address = str(raw.get("address") or "")[:200]
        port_raw = raw.get("port")
        port = int(port_raw) if str(port_raw).isdigit() else None
        command_line = str(raw.get("command_line") or "")[:600]
        process_name = str(raw.get("process_name") or "")[:120] or None
        mcp_evidence = str(raw.get("mcp_evidence") or "unknown")
        if mcp_evidence not in evidence:
            mcp_evidence = "unknown"
        server_name = str(raw.get("server_name") or "")[:200] or None
        mark = listener_fingerprint(source, address, port, command_line)

        matched = None
        candidates = _listener_keys(address, port, server_name or "", command_line)
        for entry in index:
            if entry["keys"] & candidates:
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
            classification, registry_match = "registered", matched["id"]
        counts[classification] += 1
        evidence[mcp_evidence] += 1
        seen.append(mark)
        await db.execute(
            """INSERT INTO endpoint_listeners(
                 endpoint_id, source, address, port, process_name, command_line,
                 mcp_evidence, server_name, server_version, protocol_version,
                 fingerprint, registry_match, classification, raw)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (endpoint_id, fingerprint) DO UPDATE SET
                 observed_at=now(), mcp_evidence=EXCLUDED.mcp_evidence,
                 server_name=EXCLUDED.server_name, server_version=EXCLUDED.server_version,
                 protocol_version=EXCLUDED.protocol_version,
                 registry_match=EXCLUDED.registry_match,
                 classification=EXCLUDED.classification, raw=EXCLUDED.raw""",
            (endpoint_id, source, address, port, process_name, command_line,
             mcp_evidence, server_name, str(raw.get("server_version") or "")[:80] or None,
             str(raw.get("protocol_version") or "")[:40] or None,
             mark, registry_match, classification, Jsonb(raw)),
        )
    removed = await db.execute(
        "DELETE FROM endpoint_listeners WHERE endpoint_id=%s AND NOT (fingerprint = ANY(%s::text[]))",
        (endpoint_id, seen),
    )
    await db.execute(
        "UPDATE endpoint_agents SET last_seen_at=now(), last_scan_at=now() WHERE endpoint_id=%s",
        (endpoint_id,),
    )
    return {"endpoint_id": endpoint_id, "accepted": len(findings), "removed": removed,
            "counts": counts, "evidence": evidence}


async def listeners(classification: str | None = None, limit: int = 200) -> list:
    query = """SELECT l.*, a.hostname, a.owner_token, p.display_name AS owner_name,
                      s.display_name AS registry_name, s.lifecycle
                 FROM endpoint_listeners l
                 JOIN endpoint_agents a USING (endpoint_id)
                 LEFT JOIN principals p ON p.token = a.owner_token
                 LEFT JOIN mcp_servers s ON s.id = l.registry_match"""
    params = []
    if classification:
        query += " WHERE l.classification=%s"
        params.append(classification)
    query += " ORDER BY l.observed_at DESC LIMIT %s"
    params.append(limit)
    rows = await db.fetch_all(query, tuple(params))
    result = []
    for row in rows:
        item = dict(row)
        if item.get("observed_at"):
            item["observed_at"] = item["observed_at"].isoformat()
        result.append(item)
    return result


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
