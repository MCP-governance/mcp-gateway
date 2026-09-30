"""하네스가 기본으로 붙이는 커넥터와 기능(D-51).

직원 PC의 보고는 인벤토리이며 집행 증거가 아니다(D-53). 벤더 출처와 무관하게 미승인 항목은 거부 정책의 대상이다.
승인은 Gateway 밖 경로의 예외 승인이고, 관리형 Gateway 전용 프로필을 넓히지 않는다. 정식 경로는 도입 신청이다.
사용자 설정은 보조 조치이며, 보호된 관리형 설정·단말 실행 통제·망·상위 자격 통제를 별도로 검증해야 한다.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Header, HTTPException
from pydantic import Field, field_validator

from . import db
from .agent_contract import StrictModel, authenticated_user

router = APIRouter()
REVIEW_DAYS = int(os.getenv("CONNECTOR_REVIEW_DAYS", "14"))
BLOCKING = {"pending", "denied", "expired", "default"}


def host_of(target: str) -> str:
    return (urlsplit(target).hostname or "") if target.startswith(("http://", "https://")) else ""


def key_of(harness: str, kind: str, name: str, target: str) -> str:
    """결정 단위. URL로 닿는 것은 목적지 호스트로 묶는다 — 같은 Notion이 계정 커넥터로 오든 플러그인으로 오든
    조직이 정하는 것은 "그 호스트로 데이터를 보내도 되는가"다."""
    if kind == "app":
        return f"codex:app:{target or name}"
    if kind == "feature":
        return f"codex:feature:{name}"
    host = host_of(target)
    return f"{harness}:host:{host}" if host else f"{harness}:stdio:{name}"


def first_party(kind: str, target: str) -> bool:
    host = host_of(target)
    return (kind == "feature" or (kind == "app" and target.startswith("connector_openai_"))
            or (kind == "connector" and (host == "anthropic.com" or host.endswith(".anthropic.com"))))


def state_of(decision: str | None, vendor_own: bool, first_seen: datetime, now: datetime) -> str:
    if decision:
        return decision
    # 출처는 표시용이다. 벤더 접두어와 기본 기능은 권한의 근거가 아니다.
    if REVIEW_DAYS and now - first_seen > timedelta(days=REVIEW_DAYS):
        return "expired"
    return "pending"


def policy(groups: list[dict], gateway_host: str = "") -> dict:
    """미승인·거부·검토 기한 만료를 하네스가 읽는 키로 바꾼다. 키트가 사용자 설정에, managed가 관리형
    설정에 그대로 쓴다. 이름 거부는 벤더가 붙인 이름(claude.ai …, plugin:…)에만 쓴다 — 직원이 붙인 이름을 막으면
    같은 이름의 Gateway 서버까지 막힐 수 있다. Gateway 자신의 호스트는 어떤 경우에도 거부 목록에 넣지 않는다."""
    denied, apps, features = [], [], []
    for g in sorted(groups, key=lambda g: g["key"]):
        harness, how, value = g["key"].split(":", 2)
        blocked = g["state"] in BLOCKING
        if not blocked:
            continue
        if harness == "claude":
            if how == "host" and value != gateway_host:
                denied.append({"serverUrl": f"*://{value}/*"})
            denied += [{"serverName": n} for n in sorted(g["names"]) if n.startswith(("claude.ai ", "plugin:"))]
        elif how == "app":
            apps.append(value)
        elif how == "feature":
            features.append(value)
    return {"scope": "managed-cli-gateway-only", "enforcement": "unverified",
            "claude": {"deniedMcpServers": denied, "allowAllClaudeAiMcps": False},
            "codex": {"apps_disabled": apps, "features_disabled": features}}


class HarnessItem(StrictModel):
    harness: Literal["claude", "codex"]
    kind: Literal["connector", "plugin", "server", "app", "feature"]
    name: str = Field(min_length=1, max_length=200)
    # URL은 scheme://host[:port]까지만 온다(경로·쿼리에 키가 든 MCP URL이 있다). stdio는 "stdio".
    target: str = Field(default="", max_length=300)
    status: str = Field(default="", max_length=120)
    active: bool = True

    @field_validator("target")
    @classmethod
    def safe_target(cls, value: str) -> str:
        if value.lower().startswith(("http://", "https://")):
            try:
                parts = urlsplit(value)
                if not parts.hostname:
                    raise ValueError("URL needs a host")
                host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
                return f"{parts.scheme}://{host}" + (f":{parts.port}" if parts.port else "")
            except ValueError:
                raise ValueError("invalid target origin") from None
        return value


class Inventory(StrictModel):
    workstation: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,63}$")
    harnesses: list[Literal["claude", "codex"]] = Field(max_length=2)
    items: list[HarnessItem] = Field(default_factory=list, max_length=500)


class Decision(StrictModel):
    key: str = Field(min_length=3, max_length=300)
    decision: Literal["approved", "denied", "reset"]
    note: str = Field(default="", max_length=500)


def gateway_host() -> str:
    return urlsplit(os.getenv("IDP_ISSUER", "")).hostname or ""


async def groups() -> list[dict]:
    rows = await db.fetch_all(
        """SELECT i.item_key AS key, array_agg(DISTINCT i.kind) AS kinds, array_agg(DISTINCT i.name) AS names,
                  max(i.target) AS target, min(i.first_seen) AS first_seen, max(i.last_seen) AS last_seen,
                  count(DISTINCT (i.principal, i.workstation)) FILTER (WHERE i.active) AS active_pcs,
                  count(DISTINCT (i.principal, i.workstation)) AS pcs,
                  count(DISTINCT i.principal) AS people,
                  d.decision, d.note, d.decided_by, d.decided_at
           FROM harness_items i LEFT JOIN harness_decisions d USING (item_key)
           GROUP BY i.item_key, d.decision, d.note, d.decided_by, d.decided_at""")
    now = datetime.now(UTC)
    for g in rows:
        g["harness"] = g["key"].split(":", 1)[0]
        g["vendor_own"] = any(first_party(k, g["target"]) for k in g["kinds"])
        g["state"] = state_of(g["decision"], g["vendor_own"], g["first_seen"], now)
        g["due"] = (g["first_seen"] + timedelta(days=REVIEW_DAYS)).isoformat() if REVIEW_DAYS else None
        g["enforcement"] = "unverified"  # 보고에서 사라져도 실행·송신 차단을 입증하지 못한다.
    return rows


@router.post("/api/pc/inventory")
async def pc_inventory(report: Inventory, authorization: str | None = Header(default=None)):
    """키트가 보고한 목록을 갱신한다. absent는 미관측이며 차단 확인이 아니다."""
    user = await authenticated_user(authorization)
    async with db.transaction() as connection:
        await connection.execute(
            """UPDATE harness_items SET active=false, status='absent'
               WHERE principal=%s AND workstation=%s AND harness = ANY(%s)""",
            (user["principal"], report.workstation, report.harnesses))
        for item in report.items:
            if item.harness not in report.harnesses:
                continue
            await connection.execute(
                """INSERT INTO harness_items(principal, workstation, harness, kind, name, item_key, target, status, active)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (principal, workstation, harness, kind, name) DO UPDATE
                   SET item_key=EXCLUDED.item_key, target=EXCLUDED.target, status=EXCLUDED.status,
                       active=EXCLUDED.active, last_seen=now()""",
                (user["principal"], report.workstation, item.harness, item.kind, item.name,
                 key_of(item.harness, item.kind, item.name, item.target), item.target, item.status, item.active))
    all_groups = await groups()
    mine = {key_of(i.harness, i.kind, i.name, i.target) for i in report.items}
    return {"accepted": len(report.items), "policy": policy(all_groups, gateway_host()),
            "review": [{"key": g["key"], "names": g["names"], "state": g["state"], "note": g["note"] or ""} for g in all_groups
                       if g["key"] in mine and g["state"] in {"pending", "denied", "expired"}]}


def require_admin(user: dict) -> None:
    if "admin" not in user["roles"]:
        raise HTTPException(403, "관리자만 볼 수 있습니다.")


@router.get("/api/connectors")
async def list_connectors(summary: bool = False, authorization: str | None = Header(default=None)):
    """summary=1은 메뉴 배지용(보고한 PC 목록 없이)."""
    require_admin(await authenticated_user(authorization))
    rows = await groups()
    counts = {s: sum(g["state"] == s for g in rows) for s in ("pending", "expired", "denied", "approved", "default")}
    if summary:
        return {"summary": counts}
    holders = await db.fetch_all(
        """SELECT i.item_key AS key, p.display_name, i.workstation, i.harness, i.name, i.status, i.active, i.last_seen
           FROM harness_items i LEFT JOIN principals p ON p.token = i.principal
           ORDER BY i.last_seen DESC LIMIT 2000""")
    by_key: dict[str, list] = {}
    for h in holders:
        by_key.setdefault(h.pop("key"), []).append(h)
    for g in rows:
        g["holders"] = by_key.get(g["key"], [])
        g["violation"] = g["state"] in BLOCKING and g["active_pcs"] > 0
    rows.sort(key=lambda g: ({"pending": 0, "expired": 1, "denied": 2, "default": 3, "approved": 4}[g["state"]],
                             -g["active_pcs"], g["key"]))
    return {"items": rows, "review_days": REVIEW_DAYS, "summary": counts | {"violations": sum(g["violation"] for g in rows)}}


@router.put("/api/connectors/decision")
async def decide_connector(request: Decision, authorization: str | None = Header(default=None)):
    user = await authenticated_user(authorization)
    require_admin(user)
    if not await db.fetch_one("SELECT 1 FROM harness_items WHERE item_key=%s LIMIT 1", (request.key,)):
        raise HTTPException(404, "보고된 적 없는 항목입니다.")
    if request.decision == "reset":
        await db.execute("DELETE FROM harness_decisions WHERE item_key=%s", (request.key,))
        return {"message": "결정을 지웠어요. 다시 검토 대기예요."}
    if request.decision == "denied" and len(request.note.strip()) < 2:
        raise HTTPException(422, "거부 사유를 적어 주세요. 직원 PC 키트가 이 사유를 보여 줘요.")
    await db.execute(
        """INSERT INTO harness_decisions(item_key, decision, note, decided_by) VALUES (%s,%s,%s,%s)
           ON CONFLICT (item_key) DO UPDATE SET decision=EXCLUDED.decision, note=EXCLUDED.note,
             decided_by=EXCLUDED.decided_by, decided_at=now()""",
        (request.key, request.decision, request.note.strip(), user["principal"]))
    return {"message": "예외 승인 저장. Gateway 전용 관리형 정책은 유지됩니다." if request.decision == "approved"
            else "거부 정책 저장. PC 설정 적용과 실제 차단은 별도 확인이 필요합니다."}


@router.get("/api/connectors/policy")
async def connector_policy(authorization: str | None = Header(default=None)):
    """`mcpgw_pc.py managed --connectors <이 파일>`이 관리형 설정 파일로 바꾼다."""
    require_admin(await authenticated_user(authorization))
    return {**policy(await groups(), gateway_host()), "generated_at": datetime.now(UTC).isoformat(),
            "review_days": REVIEW_DAYS}


if __name__ == "__main__":
    now = datetime.now(UTC)
    assert key_of("claude", "connector", "claude.ai Notion", "https://mcp.notion.com") == "claude:host:mcp.notion.com"
    assert key_of("claude", "plugin", "plugin:notion:notion", "https://mcp.notion.com") == "claude:host:mcp.notion.com"
    assert key_of("claude", "plugin", "plugin:pdf-viewer:pdf", "stdio") == "claude:stdio:plugin:pdf-viewer:pdf"
    assert key_of("codex", "app", "Notion", "asdk_app_1") == "codex:app:asdk_app_1"
    assert key_of("codex", "feature", "web_search", "cached") == "codex:feature:web_search"
    assert first_party("connector", "https://api.anthropic.com") and not first_party("connector", "https://evil-anthropic.com")
    assert first_party("app", "connector_openai_hotline") and not first_party("app", "asdk_app_1")
    old = now - timedelta(days=REVIEW_DAYS + 1)
    assert state_of(None, False, now, now) == "pending" and state_of(None, False, old, now) == "expired"
    assert state_of(None, True, now, now) == "pending" and state_of(None, True, old, now) == "expired"
    assert state_of("approved", False, old, now) == "approved"
    assert HarnessItem(harness="claude", kind="server", name="redaction",
                       target="https://user:secret@example.com:443/key-secret?token=secret").target == "https://example.com:443"
    assert HarnessItem(harness="claude", kind="server", name="upper",
                       target="HTTPS://user:secret@example.com/key").target == "https://example.com"
    g = lambda key, state, names, kinds=("connector",): {"key": key, "state": state, "names": list(names), "kinds": list(kinds)}
    p = policy([g("claude:host:mcp.notion.com", "denied", ["claude.ai Notion", "plugin:engineering:notion"], ("connector", "plugin")),
                g("claude:host:100.64.0.1", "denied", ["filesystem"], ("server",)),
                g("claude:host:mcp.canva.com", "pending", ["claude.ai Canva"]),
                g("claude:stdio:mine", "expired", ["mine"], ("server",)),
                g("codex:app:asdk_app_1", "expired", ["Notion"], ("app",)),
                g("codex:feature:browser_use", "denied", ["browser_use"], ("feature",))], gateway_host="100.64.0.1")
    assert p["claude"]["deniedMcpServers"] == [{"serverUrl": "*://mcp.canva.com/*"}, {"serverName": "claude.ai Canva"},
                                               {"serverUrl": "*://mcp.notion.com/*"}, {"serverName": "claude.ai Notion"},
                                               {"serverName": "plugin:engineering:notion"}], p
    assert p["claude"]["allowAllClaudeAiMcps"] is False
    assert policy([g("claude:host:mcp.canva.com", "approved", ["claude.ai Canva"])])["claude"]["allowAllClaudeAiMcps"] is False
    assert p["enforcement"] == "unverified"
    assert p["codex"] == {"apps_disabled": ["asdk_app_1"], "features_disabled": ["browser_use"]}
    print("connectors self-check OK")
