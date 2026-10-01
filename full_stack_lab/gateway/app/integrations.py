"""Which control plane governs each integration, and what evidence says so (D-62).

The Gateway enforces only the calls that reach it. A vendor's native connector is
governed in the vendor's admin plane, a local plugin or stdio server by the endpoint,
and a shadow server by nobody until an endpoint closes its path. This module puts the
registry, harness reports, endpoint inventory and listeners side by side in one model
and says, per item, who manages it, whether that manager actually enforces it now, and
how it can be bypassed. It reads; it never changes a registration or a device.

class   gateway_mcp · gateway_backend_connector · vendor_native_connector ·
        local_plugin_or_stdio · shadow_or_unknown
state   gateway_enforced · endpoint_enforced · vendor_enforced · observed_only ·
        unknown_not_enrolled · bypass_possible

`endpoint_enforced` needs a Linux managed device whose last heartbeat (under 180 s) says
the AppArmor profiles, the UID nftables table and the protected harness files match.
Any other account on that device, an old agent that did not report the others, Windows
or WSL is a bypass, not an enforcement. `vendor_enforced` needs an administrator's
recorded check of the vendor admin console; it is labelled as a manual record.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import Field
from psycopg.types.json import Jsonb

from . import classify, db, registry
from .agent_contract import StrictModel, authenticated_user
from .connectors import REVIEW_DAYS, require_admin, state_of
from .endpoint_plane import HEARTBEAT_SECONDS, MANAGED_CHECKS

router = APIRouter()
STATES = ("gateway_enforced", "endpoint_enforced", "vendor_enforced", "observed_only", "unknown_not_enrolled", "bypass_possible")
CLASSES = ("gateway_mcp", "gateway_backend_connector", "vendor_native_connector", "local_plugin_or_stdio", "shadow_or_unknown")


def host_report(device: dict, now: datetime) -> dict | None:
    """The validated heartbeat report of other accounts, if it is current.

    Only the managed heartbeat writes it, but an older row or a hand-edited detail must
    not break the inventory or keep vouching after the agent stopped reporting."""
    host = (device.get("detail") or {}).get("host")
    if not isinstance(host, dict) or not isinstance(host.get("other_accounts", []), list):
        return None
    if any(not isinstance(a, dict) or not isinstance(a.get("name"), str) for a in host.get("other_accounts", [])):
        return None
    try:
        reported = datetime.fromisoformat(str(host.get("reported_at")))
    except ValueError:
        return None
    return host if (now - reported).total_seconds() < HEARTBEAT_SECONDS else None


def platform_of(device: dict, host: dict | None = None) -> str:
    host = host or {}
    text = f"{device.get('platform') or ''} {host.get('kernel') or ''}".lower()
    if host.get("wsl") or "microsoft" in text or "wsl" in text:
        return "wsl"
    if "windows" in text or text.startswith("win"):
        return "windows"
    return "linux" if "linux" in text else "other"


def device_state(device: dict, now: datetime) -> dict:
    """The managed account's path, and every other path the same device leaves open."""
    host = host_report(device, now)
    platform = platform_of(device, host)
    checks = device.get("enforcement_checks") or {}
    age = (now - device["heartbeat_at"]).total_seconds() if device.get("heartbeat_at") else None
    bypass = []
    for account in (host or {}).get("other_accounts") or []:
        groups = [str(g) for g in account.get("privileged_groups") or []]
        bypass.append(f"{account['name']}({','.join(groups)}) 관리 불가" if groups else f"{account['name']} 비관리 계정")
    if device.get("device_epoch") and host is None:
        bypass.append("같은 단말의 다른 계정 보고 없음·만료")
    if platform in {"windows", "wsl"}:
        bypass.append(f"{platform} 강제 미지원")
    if device.get("status") != "active":
        bypass = []  # a revoked device is no path at all; it is listed only as history
    managed = device.get("managed_state")
    if device.get("status") != "active":
        state, evidence = "unknown_not_enrolled", "장치 자격 폐기"
    elif platform != "linux":
        state, evidence = "observed_only", f"{platform}: 커널 강제 미지원, 관측만"
    elif (managed == "active" and age is not None and age < HEARTBEAT_SECONDS
          and set(checks) == MANAGED_CHECKS and all(v is True for v in checks.values())):
        state, evidence = "endpoint_enforced", f"AppArmor·UID nftables·보호 설정 일치, heartbeat {int(age)}초 전"
    elif managed in {"active", "quarantined"}:
        state = "bypass_possible"
        evidence = "격리됨 — 커널 규칙·설정 불일치" if managed == "quarantined" else "heartbeat 만료 — 커널 규칙 확인 불가"
    elif managed == "pending":
        state, evidence = "observed_only", "설치 보고, 관리자 활성화 전"
    else:
        state, evidence = "observed_only", "관측 에이전트 보고만 있음"
    return {"endpoint_id": device["endpoint_id"], "hostname": device.get("hostname"), "owner": device.get("owner_token"),
            "platform": platform, "account": device.get("local_username"), "uid": device.get("local_uid"),
            "account_state": state, "state": "bypass_possible" if bypass and state != "unknown_not_enrolled" else state,
            "evidence": evidence, "bypass": bypass, "verified_at": device.get("heartbeat_at") or device.get("last_seen_at"),
            "kernel_denials_24h": int(device.get("kernel_denials") or 0)}


def endpoint_item_state(device: dict | None, approved: bool) -> tuple[str, str, list[str]]:
    """An item found on a device is enforced only as far as that device is."""
    if device is None:
        return ("observed_only" if approved else "bypass_possible"), "단말 결합 없는 자체 보고", ["관리 단말 없음"]
    if device["state"] == "endpoint_enforced":
        return "endpoint_enforced", device["evidence"], []
    if device["account_state"] == "endpoint_enforced":
        return "bypass_possible", "관리 계정은 커널 차단 · " + device["evidence"], device["bypass"]
    return ("observed_only" if approved else "bypass_possible"), device["evidence"], device["bypass"] or [device["evidence"]]


async def snapshot() -> dict:
    now = datetime.now(UTC)
    raw_devices = await db.fetch_all(
        """SELECT a.*, (SELECT count(*) FROM endpoint_os_events e WHERE e.endpoint_id=a.endpoint_id
                            AND e.observed_at > now() - interval '24 hours') AS kernel_denials
             FROM endpoint_agents a WHERE a.agent_version<>'unregistered' OR a.device_epoch IS NOT NULL""")
    devices = {d["endpoint_id"]: device_state(d, now) for d in raw_devices}
    people = await db.fetch_all("SELECT token, role, status, managed_required FROM principals WHERE status='active'")
    # The managed account is confined even when its device has other open accounts; those
    # accounts are listed as their own bypass reasons, not as "no managed device".
    enforced_owners = {d["owner"] for d in devices.values() if d["account_state"] == "endpoint_enforced"}
    owners_with_device = {d["owner"] for d in devices.values() if d["state"] != "unknown_not_enrolled"}
    for person in people:
        if person["managed_required"] and person["token"] not in owners_with_device:
            devices[f"unenrolled:{person['token']}"] = {
                "endpoint_id": None, "owner": person["token"], "platform": None, "state": "unknown_not_enrolled",
                "account_state": "unknown_not_enrolled", "evidence": "관리형 단말 등록 없음", "bypass": [], "verified_at": None}
    items: list[dict] = []

    # Gateway routes: enforced for what reaches them; open wherever a holder is unmanaged.
    traversal = {r["server_id"]: r for r in await db.fetch_all(
        """SELECT server_id, max(created_at) FILTER (WHERE upstream_executed) AS executed_at,
                  max(created_at) AS last_at, count(*) FILTER (WHERE created_at > now() - interval '7 days') AS calls_7d
             FROM decisions WHERE created_at > now() - interval '30 days'
              AND COALESCE(client->>'event_kind','tools/call')='tools/call' GROUP BY server_id""")}
    for server in await db.fetch_all("SELECT id, endpoint, status, lifecycle, display_name FROM mcp_servers ORDER BY id"):
        spec = registry.server(server["id"]) or {}
        provider = classify.url_destination(server["endpoint"]).external
        allowed = registry.allowed_principals(server["id"])
        holders = sorted(allowed if allowed is not None else {p["token"] for p in people})
        operating = server["status"] == "READY" and server["lifecycle"] == "OPERATING"
        # A server the Gateway refuses has no holders; direct use of the SaaS is `residual`.
        bypass = [f"{p}: 관리 단말 없음" for p in holders if p not in enforced_owners] if operating else []
        bypass += sorted({f"{d['owner']}@{d['hostname']}: {b}" for d in devices.values()
                          if operating and d["owner"] in holders for b in d["bypass"]})
        seen = traversal.get(server["id"]) or {}
        items.append({
            "class": "gateway_backend_connector" if provider else "gateway_mcp",
            "key": f"gateway:{server['id']}", "name": server["display_name"] or server["id"], "target": server["endpoint"],
            "harness": None, "owner": ", ".join(holders) or "—", "device": None,
            "discovered_from": "Registry", "discovered_at": spec.get("registered_at"),
            "source": spec.get("source_url") or ("도입 신청 " + str(spec["intake_id"]) if spec.get("intake_id") else "검토 카탈로그"),
            "managed_by": "gateway", "enforced": True,
            "state": "bypass_possible" if operating and bypass else "gateway_enforced",
            "evidence": (f"Gateway 실행 {seen['executed_at'].isoformat(timespec='seconds')} · 7일 {seen['calls_7d']}건"
                         if seen.get("executed_at") else "Gateway 경유 실행 기록 없음") + ("" if operating else f" · {server['status']} 상태라 호출 차단"),
            "approval": {"state": "approved" if operating else server["status"].lower(), "expires_at": spec.get("valid_until")},
            "bypass": bypass, "last_verified_at": seen.get("last_at"),
            # Outside any device: the same SaaS account used from another machine.
            "residual": ["공급자 계정의 다른 단말·웹 접근은 SaaS 조직 정책 소관"] if provider else []})

    # Harness reports (kit, not device-bound): vendor connectors/apps/features and local plugins.
    decided = {d["item_key"]: d for d in await db.fetch_all("SELECT * FROM harness_decisions")}
    vendor_records = {v["item_key"]: v["record"] for v in await db.fetch_all("SELECT * FROM harness_vendor_controls")}
    for row in await db.fetch_all(
            """SELECT item_key, harness, kind, name, target, principal, workstation, status, active, first_seen, last_seen
                 FROM harness_items ORDER BY last_seen DESC LIMIT 2000"""):
        decision = decided.get(row["item_key"]) or {}
        approval = state_of(decision.get("decision"), False, row["first_seen"], now)
        local = row["kind"] in {"plugin", "server"} and not row["target"].startswith(("http://", "https://"))
        vendor = vendor_records.get(row["item_key"]) or {}
        # The kit reports with a Console token from whichever OS account ran it, so the
        # item is not bound to a managed device even when its owner has one.
        state, evidence, bypass = endpoint_item_state(None, approval == "approved")
        if not row["active"]:
            state, evidence = "observed_only", "마지막 보고에서 사라짐 — 차단 증거 아님"
        if row["kind"] in {"connector", "app"} and vendor.get("console_state") == "blocked" and vendor.get("verified_at"):
            # A manual record ages like a review: past REVIEW_DAYS it no longer vouches.
            checked = datetime.fromisoformat(vendor["verified_at"])
            if REVIEW_DAYS and (now - checked).days < REVIEW_DAYS:
                state, evidence = "vendor_enforced", f"벤더 관리 콘솔 차단(수기 확인 {vendor['verified_at']})"
            else:
                evidence = f"벤더 콘솔 수기 확인 만료({vendor['verified_at']})"
        items.append({
            "class": "local_plugin_or_stdio" if local else "vendor_native_connector",
            "key": f"{row['item_key']}|{row['principal']}|{row['workstation']}", "item_key": row["item_key"],
            "name": row["name"], "target": row["target"], "harness": row["harness"],
            "owner": row["principal"], "device": row["workstation"],
            "discovered_from": "PC 키트 보고", "discovered_at": row["first_seen"], "source": row["kind"],
            "managed_by": "endpoint" if local else "vendor", "enforced": state in {"endpoint_enforced", "vendor_enforced"},
            "state": state, "evidence": evidence,
            "approval": {"state": approval, "expires_at": None, "decided_by": decision.get("decided_by"),
                         "review_days": REVIEW_DAYS},
            "vendor_control": vendor or None, "bypass": bypass, "last_verified_at": row["last_seen"]})

    # Device-bound inventory: configs and listeners the endpoint agent reported.
    for row in await db.fetch_all(
            """SELECT 'config' AS source, endpoint_id, config_path AS location, server_label AS name, transport,
                      endpoint_ref AS target, classification, registry_match, reported_at AS seen
                 FROM endpoint_inventory WHERE classification <> 'registered'
               UNION ALL
               SELECT 'listener', endpoint_id, source || ' ' || address || COALESCE(':' || port, ''),
                      COALESCE(server_name, process_name, address), source, COALESCE(command_line, ''), classification,
                      registry_match, observed_at
                 FROM endpoint_listeners WHERE classification <> 'registered'"""):
        device = devices.get(row["endpoint_id"])
        state, evidence, bypass = endpoint_item_state(device, False)
        stdio = row["transport"] in {"stdio", "stdio-process"}
        items.append({
            "class": "local_plugin_or_stdio" if stdio and row["classification"] == "retired-residue" else "shadow_or_unknown",
            "key": f"{row['source']}:{row['endpoint_id']}:{row['location']}:{row['name']}", "name": row["name"],
            "target": row["target"], "harness": None, "owner": (device or {}).get("owner"), "device": row["endpoint_id"],
            "discovered_from": f"단말 {'설정' if row['source'] == 'config' else '리스너'} {row['location']}",
            "discovered_at": row["seen"], "source": row["classification"],
            "managed_by": "endpoint" if state == "endpoint_enforced" else "none", "enforced": state == "endpoint_enforced",
            "state": state, "evidence": evidence,
            "approval": {"state": "unapproved", "expires_at": None}, "bypass": bypass, "last_verified_at": row["seen"]})

    summary = {"states": {s: sum(i["state"] == s for i in items) for s in STATES},
               "classes": {c: sum(i["class"] == c for i in items) for c in CLASSES},
               "devices": {s: sum(d["state"] == s for d in devices.values()) for s in STATES}}
    return {"generated_at": now.isoformat(), "items": items, "devices": list(devices.values()), "summary": summary}


class VendorControl(StrictModel):
    key: str = Field(min_length=3, max_length=300)
    console_state: Literal["allowed", "limited", "blocked", "unknown"]
    allowed_actions: list[str] = Field(default_factory=list, max_length=30)
    oauth_scopes: list[str] = Field(default_factory=list, max_length=30)
    role_access: str = Field(default="", max_length=200)
    evidence_url: str = Field(default="", max_length=500)
    note: str = Field(default="", max_length=500)


@router.get("/api/integrations")
async def list_integrations(authorization: str | None = Header(default=None)) -> Any:
    require_admin(await authenticated_user(authorization))
    return await snapshot()


@router.put("/api/integrations/vendor-control")
async def record_vendor_control(request: VendorControl, authorization: str | None = Header(default=None)) -> dict:
    """An administrator's record of what the vendor admin console shows. Not fetched from the vendor."""
    user = await authenticated_user(authorization)
    require_admin(user)
    if not await db.fetch_one("SELECT 1 FROM harness_items WHERE item_key=%s LIMIT 1", (request.key,)):
        raise HTTPException(404, "보고된 적 없는 항목입니다.")
    record = {**request.model_dump(exclude={"key"}), "verified_by": user["principal"],
              "verified_at": datetime.now(UTC).isoformat(timespec="seconds"), "source": "manual-admin-console-check"}
    await db.execute(
        """INSERT INTO harness_vendor_controls(item_key, record) VALUES (%s, %s)
           ON CONFLICT (item_key) DO UPDATE SET record=EXCLUDED.record, recorded_at=now()""",
        (request.key, Jsonb(record)))
    return {"key": request.key, "vendor_control": record}


if __name__ == "__main__":
    from datetime import timedelta
    now = datetime.now(UTC)
    fresh = now.isoformat(timespec="seconds")
    checks = {key: True for key in MANAGED_CHECKS}
    base = {"endpoint_id": "d1", "status": "active", "managed_state": "active", "platform": "Linux 7.0", "device_epoch": "e",
            "heartbeat_at": now, "enforcement_checks": checks, "owner_token": "user", "local_username": "managed"}
    host = lambda accounts, **extra: {"host": {"kernel": "7.0", "wsl": False, "other_accounts": accounts, "reported_at": fresh, **extra}}
    clean = device_state({**base, "detail": host([])}, now)
    assert clean["state"] == "endpoint_enforced", clean
    shared = device_state({**base, "detail": host([{"name": "pj1", "uid": 1000, "privileged_groups": ["sudo", "docker"]}])}, now)
    assert shared["account_state"] == "endpoint_enforced" and shared["state"] == "bypass_possible", shared
    assert device_state({**base, "detail": {}}, now)["state"] == "bypass_possible"  # old agent: other accounts unknown
    stale = {"host": {**host([])["host"], "reported_at": (now - timedelta(seconds=HEARTBEAT_SECONDS)).isoformat()}}
    assert device_state({**base, "detail": stale}, now)["state"] == "bypass_possible"  # an old empty report vouches for nothing
    assert device_state({**base, "detail": {"host": "x"}}, now)["state"] == "bypass_possible"  # malformed detail never crashes
    assert device_state({**base, "detail": {"host": {"other_accounts": [1], "reported_at": fresh}}}, now)["state"] == "bypass_possible"
    wsl = device_state({**base, "platform": "Linux 6.6-microsoft-standard-WSL2", "detail": host([])}, now)
    assert wsl["account_state"] == "observed_only" and wsl["state"] == "bypass_possible", wsl
    assert device_state({**base, "heartbeat_at": now - timedelta(seconds=HEARTBEAT_SECONDS), "detail": host([])}, now)["account_state"] == "bypass_possible"
    assert device_state({**base, "enforcement_checks": {**checks, "nftables_active": False}, "detail": host([])}, now)["account_state"] == "bypass_possible"
    assert device_state({**base, "managed_state": "pending", "detail": host([])}, now)["state"] == "observed_only"
    revoked = device_state({**base, "status": "revoked", "detail": {}}, now)
    assert revoked["state"] == "unknown_not_enrolled" and revoked["bypass"] == [], revoked
    assert endpoint_item_state(None, True)[0] == "observed_only" and endpoint_item_state(None, False)[0] == "bypass_possible"
    assert endpoint_item_state(clean, False)[0] == "endpoint_enforced"
    assert endpoint_item_state(shared, False)[0] == "bypass_possible"
    print("integrations self-check OK")
