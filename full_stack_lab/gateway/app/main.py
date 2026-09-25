from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from . import core, db, decommission, endpoint_plane
from .core import (
    OPA_URL,
    approve_request,
    bootstrap,
    enforcement_mode,
    import_supply_chain_reports,
    supply_chain_coverage,
    monitor_summary,
    refresh_all_catalogs,
    catalog_watch,
    reject_request,
    set_enforcement_mode,
    verify_audit_chain,
)
from .mcp_facade import build_mcp, transport_security
from .agent_contract import authenticated_user
from . import activity, registry

AGENT_SERVICE_URL = os.getenv("AGENT_SERVICE_URL", "http://agent-service:8000")

# 배선 주소를 코드에 박아두면 compose 바깥(네이티브 실행)에서 항상 degraded가 된다.
# 실제로 무엇이 죽었는지와 "이 배치에는 그 구성요소가 없다"가 구분되지 않는다.
JAEGER_QUERY_URL = os.getenv("JAEGER_QUERY_URL", "http://jaeger:16686/api/services")
gateway_mcp = build_mcp()
mcp_http = gateway_mcp.streamable_http_app(
    streamable_http_path="/", json_response=True, host="0.0.0.0",
    transport_security=transport_security(),
)


# RFC 9728 via the MCP authorization spec: a protected MCP server answers an
# unauthenticated request with 401 and points at its resource metadata, so a client
# can find the organisation's IdP. Without this the request reaches the MCP app,
# `initialize` succeeds and the refusal arrives later as a JSON-RPC error.
RESOURCE_METADATA_URL = os.getenv("GATEWAY_PUBLIC_URL", "http://gateway:8080").rstrip("/") + \
    "/.well-known/oauth-protected-resource"


class RequireBearer:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            authorization = dict(scope.get("headers") or []).get(b"authorization", b"").decode("latin-1")
            try:
                await authenticated_user(authorization or None)
            except HTTPException as exc:
                challenge = f'Bearer resource_metadata="{RESOURCE_METADATA_URL}"'
                if authorization:
                    challenge += ', error="invalid_token"'
                headers = {"WWW-Authenticate": challenge} if exc.status_code == 401 else {}
                await JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=headers)(scope, receive, send)
                return
        await self.app(scope, receive, send)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RejectRequest(StrictModel):
    note: str = Field(min_length=1, max_length=500)


class EnforcementRequest(StrictModel):
    mode: Literal["enforce", "monitor"]


class SessionRequest(StrictModel):
    email: str = Field(max_length=150)
    password: str = Field(max_length=150)


async def caller(authorization: str | None = Header(default=None)) -> dict:
    """Every state-changing gateway API runs as a verified synthetic user.

    The principal used for the policy decision comes from this signed token, never
    from the request body, so the dashboard, curl and the MCP ingresses all sit on
    the same identity boundary.
    """
    return await authenticated_user(authorization)


async def admin_caller(user: dict = Depends(caller)) -> dict:
    if "admin" not in user["roles"]:
        raise HTTPException(403, "합성 관리자 계정이 필요합니다.")
    return user


@asynccontextmanager
async def lifespan(_: FastAPI):
    await bootstrap()
    watcher = asyncio.create_task(catalog_watch())
    try:
        async with gateway_mcp.session_manager.run():
            yield
    finally:
        watcher.cancel()
        await db.close()


app = FastAPI(title="MCP Governance Security Gateway", version="1.1.0", lifespan=lifespan)


async def _absent() -> None:
    """이 배치에 없는 구성요소. False(장애)가 아니라 None(대상 아님)으로 구분한다."""
    return None


async def _probe(url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            response = await client.get(url)
            return response.status_code < 500
    except Exception:
        return False


@app.get("/api/health")
async def health() -> dict:
    opa_ok, jaeger_ok = await asyncio.gather(
        _probe(OPA_URL.rsplit("/v1/", 1)[0] + "/health?bundles=true"),
        _probe(JAEGER_QUERY_URL) if JAEGER_QUERY_URL else _absent(),
    )
    try:
        rows = await db.fetch_all("SELECT id, status FROM mcp_servers ORDER BY id")
        db_ok = True
    except Exception:
        rows, db_ok = [], False
    servers = {row["id"]: row["status"] for row in rows if row["id"] in registry.servers()}
    components = {"gateway": True, "postgresql": db_ok, "opa": opa_ok, "jaeger": jaeger_ok}
    required = [value for value in components.values() if value is not None]
    return {"status": "ok" if all(required) else "degraded", "components": components,
            # Upstream state is reported, not required: one server in DRIFT must not
            # make the control point "unhealthy" - that is the Gateway doing its job.
            "mcp_servers": {"ready": sum(1 for v in servers.values() if v == "READY"),
                            "total": len(servers), "status": servers}}


@app.get("/api/state")
async def state(user: dict = Depends(admin_caller)) -> dict:
    servers, tools, decisions, approvals, reports, principals, policy = await asyncio.gather(
        db.fetch_all("SELECT * FROM mcp_servers ORDER BY id"),
        db.fetch_all("""SELECT server_id, name, action, enabled,
                               approved_schema_hash = observed_schema_hash AS schema_ok
                          FROM mcp_tools ORDER BY server_id, name"""),
        db.fetch_all("SELECT * FROM decisions ORDER BY id DESC LIMIT 40"),
        db.fetch_all("SELECT * FROM approvals WHERE status='PENDING' ORDER BY created_at DESC"),
        db.fetch_all("SELECT * FROM supply_chain_reports ORDER BY id DESC LIMIT 20"),
        db.fetch_all("SELECT display_name,role,synthetic FROM principals ORDER BY role"),
        db.fetch_one("SELECT * FROM policy_versions WHERE status='ACTIVE' ORDER BY activated_at DESC LIMIT 1"),
    )
    return {"servers": servers, "tools": tools, "decisions": decisions, "approvals": approvals,
            "supply_chain": reports, "principals": principals, "policy": policy,
            "catalog_version": registry.catalog_version()}


@app.get("/api/registry")
async def registry_view(user: dict = Depends(admin_caller)) -> dict:
    """Catalog + contract state in one document: what was approved, what runs now."""
    servers, tools, relationships = await asyncio.gather(
        db.fetch_all("SELECT * FROM mcp_servers ORDER BY id"),
        db.fetch_all("""SELECT server_id, name, action, enabled, description,
                               approved_schema_hash IS NOT NULL AS pinned,
                               (approved_schema_hash = observed_schema_hash
                                AND approved_description_hash = observed_description_hash) AS contract_ok
                          FROM mcp_tools ORDER BY server_id, name"""),
        db.fetch_all("SELECT * FROM usage_relationships ORDER BY id"),
    )
    catalog_servers = registry.servers()
    return {"catalog_version": registry.catalog_version(),
            "classification": registry.catalog().get("classification", {}),
            "organization": registry.catalog().get("organization", {}),
            "servers": [row for row in servers if row["id"] in catalog_servers],
            "tools": tools, "usage_relationships": relationships}


@app.get("/api/overview")
async def overview(user: dict = Depends(admin_caller)) -> dict:
    """Everything the first Console screen shows, in one round trip."""
    today, per_server, stations, alerts, approvals, cases = await asyncio.gather(
        db.fetch_all(f"""SELECT decision, count(*) AS n FROM decisions d
                          WHERE created_at > date_trunc('day', now()) AND {decommission.REAL_CALL} GROUP BY decision"""),
        db.fetch_all(f"""SELECT s.id, s.display_name, s.status, s.lifecycle, s.deployment, s.status_reason,
                               count(d.id) FILTER (WHERE d.created_at > now() - interval '24 hours') AS calls,
                               count(d.id) FILTER (WHERE d.created_at > now() - interval '24 hours' AND d.decision='Block') AS blocked,
                               max(d.created_at) AS last_call,
                               (SELECT count(*) FROM mcp_tools t WHERE t.server_id=s.id AND t.enabled) AS tools
                          FROM mcp_servers s LEFT JOIN decisions d ON d.server_id = s.id AND {decommission.REAL_CALL}
                         WHERE s.id = ANY(%s::text[])
                         GROUP BY s.id ORDER BY s.id""", (sorted(registry.servers()),)),
        db.fetch_all("""SELECT a.endpoint_id, a.hostname, a.owner_token, a.last_seen_at, p.display_name, p.department, p.role,
                               (SELECT count(*) FROM endpoint_inventory i WHERE i.endpoint_id=a.endpoint_id AND i.classification='shadow') AS shadow,
                               (SELECT max(d.created_at) FROM decisions d WHERE d.client->>'workstation' = a.endpoint_id) AS last_call
                          FROM endpoint_agents a LEFT JOIN principals p ON p.token = a.owner_token
                         WHERE a.status='active' ORDER BY a.endpoint_id"""),
        db.fetch_all(f"""SELECT decision, policy_id, count(*) AS n FROM decisions d
                          WHERE created_at > now() - interval '24 hours' AND decision IN ('Block','Alert')
                            AND {decommission.REAL_CALL}
                         GROUP BY decision, policy_id ORDER BY n DESC LIMIT 8"""),
        db.fetch_one("SELECT count(*) AS n FROM approvals WHERE status='PENDING' AND expires_at > now()"),
        decommission.summary(),
    )
    counts = {row["decision"]: int(row["n"]) for row in today}
    return {
        "today": {"total": sum(counts.values()), **{k: counts.get(k, 0) for k in ("Allow", "Alert", "Restrict", "Approval", "Block")}},
        "servers": per_server, "workstations": stations, "top_policies": alerts,
        "pending_approvals": int(approvals["n"] or 0), "termination": cases,
        "enforcement": await enforcement_mode(), "catalog_version": registry.catalog_version(),
    }


@app.get("/api/activity")
async def activity_feed(after: int = 0, limit: int = 100, decision: str | None = None,
                        server: str | None = None, person: str | None = None,
                        user: dict = Depends(caller)) -> dict:
    """Decisions as readable sentences. Admins see everyone; others see themselves."""
    own = None if "admin" in user["roles"] else user["principal"]
    return await activity.recent(after, limit, own, decision, server, person)


@app.get("/.well-known/oauth-protected-resource")
async def protected_resource_metadata() -> dict:
    """RFC 9728. The Gateway's MCP endpoint is a protected resource; employees get
    tokens from the organisation's IdP, never from an upstream MCP server."""
    return {"resource": os.getenv("GATEWAY_PUBLIC_MCP_URL", "http://gateway:8080/mcp/"),
            "authorization_servers": [os.getenv("IDP_ISSUER", "http://agent-service:8000")],
            "bearer_methods_supported": ["header"],
            "resource_name": "BoB Corp MCP Gateway"}


@app.get("/api/policy/matrix")
async def policy_matrix(user: dict = Depends(caller)) -> dict:
    roles = ("partner", "employee", "admin")
    classes = ("public", "nonimportant", "important")
    actions = ("r", "w", "x")
    contract = {
        "registered": True, "enabled": True, "schema_hash_match": True,
        "description_hash_match": True, "version_match": True, "known_tools_only": True,
        "metadata_safe": True, "supplier_approved": True, "critical_vulnerabilities": 0,
    }

    async def evaluate(role: str, data_class: str, action: str) -> dict:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                response = await client.post(OPA_URL, json={"input": {
                    "principal": {"role": role}, "resource": {"data_class": data_class},
                    "tool": {"action": action}, "approval": {"granted": False}, "contract": contract,
                }})
                response.raise_for_status()
                result = response.json()["result"]
        except Exception:
            result = core.local_verdict("P-CONTROL-FAIL-CLOSED", "Block", "정책 엔진에 질의하지 못했습니다.")
        return {"role": role, "data_class": data_class, "action": action, **result}

    cells = await asyncio.gather(*(evaluate(role, data_class, action) for role in roles for data_class in classes for action in actions))
    return {"roles": roles, "data_classes": classes, "actions": actions, "cells": cells}


@app.get("/api/policy/ledger")
async def policy_ledger_view(user: dict = Depends(caller)) -> dict:
    """§12.5 PaC 정책 관리대장.

    정책 코드만으로는 정책의 목적과 근거를 대신할 수 없다(§11.8). 어떤 위험과 통제를
    구현하는 정책인지, 지금 어떤 상태와 버전으로 어느 환경에 적용 중인지, 어떤 예외가
    붙어 있는지를 집행 중인 정본에서 그대로 읽어 보여준다.
    """
    ledger, exceptions, policy_set, active = await asyncio.gather(
        core.policy_ledger(refresh=True),
        core.opa_document("exceptions"),
        core.opa_document("policy_set"),
        db.fetch_one("SELECT * FROM policy_versions WHERE status='ACTIVE' ORDER BY activated_at DESC LIMIT 1"),
    )
    entries = [{"policy_id": pid, **entry} for pid, entry in sorted(ledger.items(), key=lambda item: item[1].get("priority", 9999))]
    return {
        "policy_set": policy_set or {},
        "deployed_rego": active,
        "environment": core.GATEWAY_ENVIRONMENT,
        "policies": entries,
        "exceptions": exceptions if isinstance(exceptions, list) else [],
    }


@app.post("/api/session")
async def session(request: SessionRequest) -> dict:
    """Dashboard and CLI login.

    The gateway does not mint tokens itself; it forwards to the single synthetic
    identity provider so there stays exactly one issuer to harden later.
    """
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.post(AGENT_SERVICE_URL + "/auth/mock-login", json=request.model_dump())
    except httpx.HTTPError as exc:
        raise HTTPException(503, "합성 인증 서비스에 연결할 수 없습니다.") from exc
    if response.status_code == 429:
        raise HTTPException(429, "로그인 시도가 너무 많습니다. 잠시 후 다시 시도하세요.")
    if response.status_code == 403:
        # 계정 상태 때문에 막힌 것을 "비밀번호를 확인하세요"로 접으면, 계정을 끈
        # 관리자조차 자기 조치가 먹혔는지 알 수 없다.
        detail = "사용할 수 없는 계정입니다."
        try:
            detail = response.json().get("detail") or detail
        except ValueError:
            pass
        raise HTTPException(403, detail)
    if response.status_code != 200:
        raise HTTPException(401, "합성 계정과 비밀번호를 확인하세요.")
    return response.json()


@app.post("/api/approvals/{approval_id}/approve")
async def approve(approval_id: str, user: dict = Depends(admin_caller)) -> dict:
    try:
        return await approve_request(approval_id, user["principal"])
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/approvals/{approval_id}/reject")
async def reject(approval_id: str, request: RejectRequest, user: dict = Depends(admin_caller)) -> dict:
    try:
        return await reject_request(approval_id, user["principal"], request.note)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/catalog/refresh")
async def catalog_refresh(user: dict = Depends(admin_caller)) -> dict:
    return {"results": await refresh_all_catalogs()}




class ContractApproval(StrictModel):
    note: str = Field(min_length=5, max_length=500)


@app.post("/api/registry/{server_id}/approve-contract")
async def registry_approve_contract(server_id: str, request: ContractApproval,
                                    user: dict = Depends(admin_caller)) -> dict:
    """검토를 마친 계약 변경을 승인본으로 올린다 (CTL-30).

    이 경로가 없으면 정당한 변경 뒤에 남는 선택지가 "SQL을 직접 고친다"와
    "MCP-CATALOG-001 차단을 계속 본다" 둘뿐이고, 현장은 늘 앞쪽을 고른다.
    """
    try:
        return await core.approve_contract(server_id, user["principal"], request.note)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"catalog를 다시 읽지 못했습니다: {exc}") from exc


@app.post("/api/supply-chain/import")
async def supply_chain_import(user: dict = Depends(admin_caller)) -> dict:
    try:
        return {"imported": await import_supply_chain_reports()}
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(422, f"보고서 파싱 실패: {exc}") from exc


@app.get("/api/supply-chain/coverage")
async def supply_chain_cover(user: dict = Depends(admin_caller)) -> dict:
    """Says, per server, whether its scan output actually gates calls."""
    rows = await supply_chain_coverage()
    return {"servers": rows,
            "unwired": [row["server_id"] for row in rows if row["scan_path"] and not row["reports"]]}


@app.get("/api/enforcement")
async def enforcement(user: dict = Depends(caller)) -> dict:
    return {"enforcement": await enforcement_mode()}


@app.put("/api/enforcement")
async def enforcement_update(request: EnforcementRequest, user: dict = Depends(admin_caller)) -> dict:
    """Turning enforcement on is an operator decision, so it is authenticated and logged."""
    try:
        return await set_enforcement_mode(request.mode, user["principal"])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/monitor/summary")
async def monitor(hours: int = 168, user: dict = Depends(admin_caller)) -> dict:
    """What enforcement would have stopped, so a team can turn it on with numbers."""
    return await monitor_summary(min(max(hours, 1), 8760))


@app.get("/api/audit/verify")
async def audit_verify(user: dict = Depends(admin_caller)) -> dict:
    """Answers "감사 로그가 위변조됐나요?" with a row id instead of an assurance."""
    return await verify_audit_chain()


# ── 전주기 종료·폐기 ────────────────────────────────────────────────────────
#
# 이 API가 하는 일은 "끄기"가 아니라 "끈 것을 증명할 수 있게 하기"다. 그래서
# 케이스를 여는 것과 닫는 것이 따로 있고, 그 사이에 회수 대상·증거·판정이 있다.
# 한 번의 호출로 서버를 끄고 끝낼 수 있게 만들면 아무도 나머지를 하지 않는다.


class TerminationOpen(StrictModel):
    # A usage relationship id (UR-...) or, for compatibility, a server id.
    server_id: str | None = Field(default=None, min_length=1, max_length=120)
    relationship_id: str | None = Field(default=None, min_length=1, max_length=120)
    reason: str = Field(min_length=10, max_length=1000)
    engagement_label: str | None = Field(default=None, max_length=300)


class TargetCreate(StrictModel):
    kind: Literal["gateway-route", "gateway-access", "client-token", "refresh-token", "dynamic-registration", "session",
                  "server-held-credential", "endpoint-config", "api-key", "webhook",
                  "cached-artifact"]
    label: str = Field(min_length=1, max_length=300)
    holder: Literal["org", "provider", "endpoint"]
    discovered_by: Literal["gateway-ledger", "endpoint-agent", "provider-disclosure",
                           "operator-manual", "liveness-probe"]
    status: Literal["OUTSTANDING", "REVOKED", "EXPIRED", "UNVERIFIABLE"] = "OUTSTANDING"
    note: str | None = Field(default=None, max_length=1000)


class TargetUpdate(StrictModel):
    status: Literal["OUTSTANDING", "REVOKED", "EXPIRED", "UNVERIFIABLE"]
    note: str | None = Field(default=None, max_length=1000)


class EvidenceCreate(StrictModel):
    kind: Literal["revocation-response", "introspection", "provider-attestation",
                  "gateway-denial", "liveness-probe", "endpoint-inventory", "credential-check",
                  "session-termination", "operator-statement"]
    subject: str = Field(min_length=1, max_length=300)
    source: str = Field(min_length=1, max_length=300)
    detail: dict = Field(default_factory=dict)
    target_id: str | None = None
    observed_at: str | None = None


class CaseClose(StrictModel):
    note: str = Field(min_length=1, max_length=1000)
    risk_acceptance: str | None = Field(default=None, max_length=1000)


class CaseReopen(StrictModel):
    reason: str = Field(min_length=1, max_length=1000)


class EvidenceCollect(StrictModel):
    kinds: list[Literal["gateway", "endpoint", "credentials", "liveness", "session"]] = Field(
        default=["gateway", "endpoint", "credentials", "liveness"], min_length=1, max_length=5)


@app.get("/api/termination/relationships")
async def termination_relationships(user: dict = Depends(admin_caller)) -> dict:
    """Usage relationships with their exit readiness (best attainable grade)."""
    return {"relationships": await decommission.relationships(),
            "evidence_kinds": decommission.EVIDENCE_KINDS, "criteria": decommission.CRITERION_LABEL}


@app.post("/api/termination/cases/{case_id}/collect")
async def termination_collect(case_id: str, request: EvidenceCollect, user: dict = Depends(admin_caller)) -> dict:
    """Collect state evidence the organisation can obtain itself (paper 5.2)."""
    try:
        return await decommission.collect(case_id, list(request.kinds), user["principal"])
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.post("/api/termination/targets/{target_id}/revoke-credential")
async def termination_revoke_credential(target_id: str, user: dict = Depends(admin_caller)) -> dict:
    """Revoke a disclosed server-held credential in a downstream system the
    organisation administers, then verify its state."""
    try:
        return await decommission.revoke_credential(target_id, user["principal"])
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.post("/api/lab/restore/{server_id}")
async def lab_restore(server_id: str, user: dict = Depends(admin_caller)) -> dict:
    """Lab only: bring a terminated server back so the demo can be repeated."""
    try:
        result = await decommission.restore_server(server_id, user["principal"])
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    try:
        result["catalog"] = await core.refresh_catalog(server_id)
    except Exception as exc:
        result["catalog"] = {"status": "ERROR", "reason": str(exc)[:200]}
    return result


@app.get("/api/termination/cases")
async def termination_cases(user: dict = Depends(admin_caller)) -> dict:
    return {"cases": await decommission.list_cases(), "summary": await decommission.summary()}


@app.post("/api/termination/cases", status_code=201)
async def termination_open(request: TerminationOpen, user: dict = Depends(admin_caller)) -> dict:
    try:
        target = request.relationship_id or request.server_id
        if not target:
            raise HTTPException(422, "relationship_id 또는 server_id가 필요합니다.")
        return await decommission.open_case(target, request.reason, user["principal"], request.engagement_label)
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.get("/api/termination/cases/{case_id}")
async def termination_detail(case_id: str, user: dict = Depends(admin_caller)) -> dict:
    try:
        return await decommission.case_detail(case_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@app.post("/api/termination/cases/{case_id}/targets", status_code=201)
async def termination_add_target(case_id: str, request: TargetCreate,
                                 user: dict = Depends(admin_caller)) -> dict:
    try:
        return await decommission.add_target(
            case_id, request.kind, request.label, request.holder,
            request.discovered_by, user["principal"], request.status, request.note)
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.put("/api/termination/targets/{target_id}")
async def termination_update_target(target_id: str, request: TargetUpdate,
                                    user: dict = Depends(admin_caller)) -> dict:
    try:
        return await decommission.revoke_target(
            target_id, user["principal"], request.status, request.note)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@app.post("/api/termination/cases/{case_id}/evidence", status_code=201)
async def termination_add_evidence(case_id: str, request: EvidenceCreate,
                                   user: dict = Depends(admin_caller)) -> dict:
    observed = None
    if request.observed_at:
        try:
            observed = datetime.fromisoformat(request.observed_at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(422, "observed_at은 ISO 8601 시각이어야 합니다.")
    try:
        return await decommission.add_evidence(
            case_id, request.kind, request.subject, request.source,
            request.detail, user["principal"], observed, request.target_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.post("/api/termination/cases/{case_id}/probe")
async def termination_probe(case_id: str, user: dict = Depends(admin_caller)) -> dict:
    """차단 이후 endpoint 도달 확인. 결과는 그대로 증거가 된다."""
    try:
        return await decommission.probe(case_id, user["principal"])
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.post("/api/termination/cases/{case_id}/assess")
async def termination_assess(case_id: str, user: dict = Depends(admin_caller)) -> dict:
    try:
        return await decommission.assess(case_id, user["principal"])
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.post("/api/termination/cases/{case_id}/close")
async def termination_close(case_id: str, request: CaseClose,
                            user: dict = Depends(admin_caller)) -> dict:
    try:
        return await decommission.close_case(
            case_id, user["principal"], request.note, request.risk_acceptance)
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.post("/api/termination/cases/{case_id}/reopen")
async def termination_reopen(case_id: str, request: CaseReopen,
                             user: dict = Depends(admin_caller)) -> dict:
    try:
        return await decommission.reopen_case(case_id, user["principal"], request.reason)
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.get("/api/termination/cases/{case_id}/report")
async def termination_report(case_id: str, user: dict = Depends(admin_caller)) -> dict:
    """감사에 그대로 낼 수 있는 종료 판정서."""
    try:
        return await decommission.report(case_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@app.get("/api/termination/cases/{case_id}/disclosure-request")
async def termination_disclosure(case_id: str, user: dict = Depends(admin_caller)) -> dict:
    """제공자에게 보낼 고지 요청서.

    T3의 가장 흔한 원인은 제공자가 보유 자격을 고지하지 않는 것이고, 그 상태에서
    조직이 할 수 있는 일은 요청하는 것뿐입니다. 매번 사람이 새로 쓰게 두면 하지
    않게 됩니다.
    """
    try:
        return await decommission.disclosure_request(case_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@app.get("/api/termination/drill/{server_id}")
async def termination_drill(server_id: str, user: dict = Depends(admin_caller)) -> dict:
    """폐기 드릴. 실제로 끊지 않고 도달 가능한 최선 등급을 계산합니다.

    도입 심사에서 묻는 질문을 하나 늘립니다 — "들일 수 있는가"가 아니라
    "끊을 수 있는가".
    """
    try:
        return await decommission.drill(server_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


# ── 엔드포인트 평면 ─────────────────────────────────────────────────────────
#
# 이 구간의 자격은 사람 계정이 아니라 **장치 자격**이다. v1.5까지 에이전트는
# 관리자 계정으로 로그인했고, 그래서 사람들의 PC에 깔린 프로세스가 침해되면
# 관리자 API 전체가 노출됐다. 지금은 장치 키로만 들어오고, 그 키로 할 수 있는
# 일은 scopes에 적힌 보고 두 가지뿐이다. 발급·조회·폐기는 관리자만 한다.


class EndpointDeviceCreate(StrictModel):
    endpoint_id: str = Field(min_length=3, max_length=120)
    hostname: str = Field(min_length=1, max_length=200)
    platform: str = Field(default="unknown", max_length=80)
    owner_token: str | None = Field(default=None, max_length=120)
    scopes: list[Literal["inventory", "netscan"]] = Field(default=["inventory"], max_length=2)
    enrollment_key: str | None = Field(default=None, min_length=32, max_length=128)


class EndpointEnroll(StrictModel):
    endpoint_id: str = Field(min_length=3, max_length=120)
    hostname: str = Field(min_length=1, max_length=200)
    platform: str = Field(min_length=1, max_length=80)
    agent_version: str = Field(min_length=1, max_length=40)
    owner_token: str | None = Field(default=None, max_length=120)
    detail: dict = Field(default_factory=dict)


class EndpointEntry(StrictModel):
    config_path: str = Field(min_length=1, max_length=400)
    server_label: str = Field(min_length=1, max_length=200)
    transport: str = Field(min_length=1, max_length=40)
    endpoint_ref: str = Field(default="", max_length=600)


class EndpointReport(StrictModel):
    endpoint_id: str = Field(min_length=3, max_length=120)
    entries: list[EndpointEntry] = Field(default_factory=list, max_length=500)


class ListenerFinding(StrictModel):
    source: Literal["local-socket", "network", "stdio-process"]
    address: str = Field(min_length=1, max_length=200)
    port: int | None = Field(default=None, ge=1, le=65535)
    process_name: str = Field(default="", max_length=120)
    command_line: str = Field(default="", max_length=600)
    mcp_evidence: Literal["confirmed", "suspected", "unknown"] = "unknown"
    server_name: str = Field(default="", max_length=200)
    server_version: str = Field(default="", max_length=80)
    protocol_version: str = Field(default="", max_length=40)


class ListenerReport(StrictModel):
    endpoint_id: str = Field(min_length=3, max_length=120)
    findings: list[ListenerFinding] = Field(default_factory=list, max_length=500)


class ScanPolicyUpdate(StrictModel):
    enabled: bool | None = None
    allowed_cidrs: list[str] | None = Field(default=None, max_length=16)
    ports: list[int] | None = Field(default=None, max_length=64)
    max_hosts: int | None = Field(default=None, ge=1, le=4096)
    connect_timeout_ms: int | None = Field(default=None, ge=50, le=5000)
    probe_mcp: bool | None = None
    interval_seconds: int | None = Field(default=None, ge=60, le=86400)


def endpoint_device(scope: str):
    """장치 자격 의존성. 사람 토큰으로는 통과하지 못하고 그 반대도 마찬가지다."""
    async def dependency(x_endpoint_key: str | None = Header(default=None)) -> dict:
        try:
            return await endpoint_plane.authenticate_device(x_endpoint_key, scope)
        except PermissionError as exc:
            raise HTTPException(401, str(exc)) from exc
    return dependency


@app.post("/api/endpoint/devices", status_code=201)
async def endpoint_device_create(request: EndpointDeviceCreate,
                                 user: dict = Depends(admin_caller)) -> dict:
    """장치를 등록하고 자격을 한 번만 돌려준다.

    에이전트가 스스로 등록할 수 있게 열어두면 아무나 엔드포인트를 만들어 임의의
    인벤토리를 올릴 수 있고, 그 인벤토리가 종료 판정의 입력이 된다. 보고는 자동,
    발급은 사람이다.
    """
    try:
        return await endpoint_plane.issue_device(
            request.endpoint_id, request.hostname, request.platform,
            request.owner_token, list(request.scopes), user["principal"], request.enrollment_key)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.delete("/api/endpoint/devices/{endpoint_id}")
async def endpoint_device_revoke(endpoint_id: str, user: dict = Depends(admin_caller)) -> dict:
    try:
        return await endpoint_plane.revoke_device(endpoint_id, user["principal"])
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/endpoint/devices")
async def endpoint_device_list(user: dict = Depends(admin_caller)) -> dict:
    return {"devices": await endpoint_plane.devices()}


@app.post("/api/endpoint/enroll", status_code=201)
async def endpoint_enroll(request: EndpointEnroll,
                          device: dict = Depends(endpoint_device("inventory"))) -> dict:
    """에이전트가 자기 버전과 관측 경로를 신고한다.

    장치 키가 가리키는 엔드포인트 외에는 등록할 수 없다. 키 하나로 남의
    엔드포인트를 덮어쓸 수 있으면 그 키는 장치 자격이 아니라 관리자 자격이다.
    """
    if request.endpoint_id != device["endpoint_id"]:
        raise HTTPException(403, "장치 자격과 다른 엔드포인트는 등록할 수 없습니다.")
    row = await endpoint_plane.enroll(
        request.endpoint_id, request.hostname, request.platform,
        request.agent_version, device["owner_token"], request.detail)
    return {key: (value.isoformat() if hasattr(value, "isoformat") else value)
            for key, value in dict(row).items()
            if key not in {"key_hash", "key_prefix"}}


@app.get("/api/endpoint/scan-policy")
async def endpoint_scan_policy_read(device: dict = Depends(endpoint_device("netscan"))) -> dict:
    """에이전트가 탐색 범위를 받아 간다.

    범위를 에이전트가 정하면 그것은 조직이 통제하지 못하는 스캐너다. 여기서
    내려주는 대역·포트·주기 밖으로 나가는 에이전트는 구현 오류다.
    """
    return await endpoint_plane.scan_policy()


@app.get("/api/endpoint/scan-policy/admin")
async def endpoint_scan_policy_admin(user: dict = Depends(admin_caller)) -> dict:
    return await endpoint_plane.scan_policy()


@app.put("/api/endpoint/scan-policy")
async def endpoint_scan_policy_update(request: ScanPolicyUpdate,
                                      user: dict = Depends(admin_caller)) -> dict:
    try:
        return await endpoint_plane.set_scan_policy(
            user["principal"], **request.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/endpoint/inventory")
async def endpoint_report(request: EndpointReport,
                          device: dict = Depends(endpoint_device("inventory"))) -> dict:
    """관측 보고를 받는다. 이 본문은 데이터이지 지시가 아니다.

    보고 내용으로 Registry를 바꾸거나 서버를 활성화하는 경로는 없다. 조작된
    엔드포인트가 할 수 있는 최악은 없는 잔존을 보고하는 것이고, 그것은 판정을
    보수적인 쪽으로만 민다.
    """
    if request.endpoint_id != device["endpoint_id"]:
        raise HTTPException(403, "장치 자격과 다른 엔드포인트의 보고는 받지 않습니다.")
    try:
        return await endpoint_plane.ingest(
            request.endpoint_id, [entry.model_dump() for entry in request.entries])
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@app.post("/api/endpoint/listeners")
async def endpoint_listener_report(request: ListenerReport,
                                   device: dict = Depends(endpoint_device("netscan"))) -> dict:
    """내부망에서 관측된 MCP 리스너 보고.

    게이트웨이 장비는 사원 PC의 루프백과 세그먼트 너머를 볼 수 없다. 그 관측은
    엔드포인트 프로그램의 권한으로 그 단말에서 수행하고 결과만 여기로 온다.
    여기서도 받는 것은 관측이지 지시가 아니다.
    """
    if request.endpoint_id != device["endpoint_id"]:
        raise HTTPException(403, "장치 자격과 다른 엔드포인트의 보고는 받지 않습니다.")
    try:
        return await endpoint_plane.ingest_listeners(
            request.endpoint_id, [item.model_dump() for item in request.findings])
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@app.get("/api/endpoint/inventory")
async def endpoint_inventory(classification: str | None = None,
                             user: dict = Depends(admin_caller)) -> dict:
    if classification and classification not in {"registered", "shadow", "retired-residue"}:
        raise HTTPException(422, "알 수 없는 분류입니다.")
    return {
        "coverage": await endpoint_plane.coverage(),
        "agents": await endpoint_plane.agents(),
        "devices": await endpoint_plane.devices(),
        "entries": await endpoint_plane.inventory(classification),
        "listeners": await endpoint_plane.listeners(classification),
        "scan_policy": await endpoint_plane.scan_policy(),
    }


@app.get("/api/risk-catalog")
async def risk_catalog(user: dict = Depends(caller)) -> dict:
    """AI-Infra-Guard의 위험 범주와 이 조직의 통제를 연결한 표.

    발견 목록을 읽을거리가 아니라 통제로 잇는 것은 이 매핑뿐이다. 인증 없이 여는
    이유는 조직 자산이 아니라 참조 분류표이기 때문이다(13절의 열린 읽기 목록).
    """
    rows = await db.fetch_all("SELECT * FROM aig_risk_catalog ORDER BY ordinal")
    return {"categories": [dict(row) for row in rows]}


app.mount("/mcp", RequireBearer(mcp_http))


@app.get("/", include_in_schema=False)
async def console() -> RedirectResponse:
    """The browser console lives with the Agent service; this port remains the API boundary."""
    return RedirectResponse(os.getenv("CONSOLE_PUBLIC_URL", "http://localhost:8000").rstrip("/") + "/workspace")
