from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from . import core, db, decommission, endpoint_plane
from .core import (
    OPA_URL,
    approve_request,
    bootstrap,
    effect_count,
    execute_call,
    enforcement_mode,
    import_supply_chain_reports,
    supply_chain_coverage,
    monitor_summary,
    refresh_catalog,
    reject_request,
    set_enforcement_mode,
    verify_audit_chain,
)
from .mcp_facade import build_mcp, transport_security
from .agent_contract import DOCUMENT_IDS, authenticated_user
from .agent_gateway import router as agent_router

AGENT_SERVICE_URL = os.getenv("AGENT_SERVICE_URL", "http://agent-service:8000")

EFFECT_LOG = Path(os.getenv("EFFECT_LOG", "/runtime/upstream-effects.jsonl"))
gateway_mcp = build_mcp()
mcp_http = gateway_mcp.streamable_http_app(
    streamable_http_path="/", json_response=True, host="0.0.0.0",
    transport_security=transport_security(),
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CallRequest(StrictModel):
    tool_name: Literal["read_document", "write_document", "send_external", "get_current_time", "github_get_file"]
    document_id: Literal["notice-001", "work-001", "secret-001", "audit-001"] | None = None
    content: str = Field(default="합성 데모 내용", max_length=2000)
    destination: str = Field(default="outside.example", max_length=200)
    timezone: str = Field(default="Asia/Seoul", max_length=64)
    owner: str = Field(default="MCP-governance", max_length=100)
    repo: str = Field(default="mcp-gateway", max_length=100)
    path: str = Field(default="README.md", max_length=300)


# Literal은 정적이어야 해서 목록을 한 번 더 적는다. 갈라지는 순간 기동이 실패하게
# 둔다. 두 목록이 다른 채로 뜨면 한쪽 ingress만 새 문서를 받는다.
assert set(CallRequest.model_fields["document_id"].annotation.__args__[0].__args__) == set(DOCUMENT_IDS), \
    "CallRequest.document_id와 agent_contract.DOCUMENT_IDS가 다릅니다."


class MockModelRequest(StrictModel):
    message: str = Field(min_length=1, max_length=500)


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
    try:
        async with gateway_mcp.session_manager.run():
            yield
    finally:
        await db.close()


app = FastAPI(title="MCP Governance Security Gateway", version="1.1.0", lifespan=lifespan)
app.include_router(agent_router)


async def _probe(url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            response = await client.get(url)
            return response.status_code < 500
    except Exception:
        return False


@app.get("/api/health")
async def health() -> dict:
    opa_ok, upstream_ok, jaeger_ok = await asyncio.gather(
        _probe(OPA_URL.rsplit("/v1/", 1)[0] + "/health?bundles=true"),
        _probe("http://mock-http-mcp:9000/health"),
        _probe("http://jaeger:16686/api/services"),
    )
    try:
        await db.fetch_one("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False
    github = await db.fetch_one("SELECT status FROM mcp_servers WHERE id='github'") if db_ok else None
    components = {
        "gateway": True,
        "postgresql": db_ok,
        "opa": opa_ok,
        "mock_http_mcp": upstream_ok,
        "jaeger": jaeger_ok,
        "github_mcp": bool(os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN") and github and github["status"] == "READY"),
    }
    return {"status": "ok" if all(value for key, value in components.items() if key != "github_mcp") else "degraded", "components": components}


@app.get("/api/state")
async def state() -> dict:
    servers, tools, decisions, approvals, reports, principals, documents, policy = await asyncio.gather(
        db.fetch_all("SELECT * FROM mcp_servers ORDER BY id"),
        db.fetch_all("SELECT * FROM mcp_tools ORDER BY server_id,name"),
        db.fetch_all("SELECT * FROM decisions ORDER BY id DESC LIMIT 40"),
        db.fetch_all("SELECT * FROM approvals WHERE status='PENDING' ORDER BY created_at DESC"),
        db.fetch_all("SELECT * FROM supply_chain_reports ORDER BY id DESC LIMIT 20"),
        db.fetch_all("SELECT display_name,role,synthetic FROM principals ORDER BY role"),
        db.fetch_all("SELECT * FROM documents ORDER BY id"),
        db.fetch_one("SELECT * FROM policy_versions WHERE status='ACTIVE' ORDER BY activated_at DESC LIMIT 1"),
    )
    return {
        "servers": servers,
        "tools": tools,
        "decisions": decisions,
        "approvals": approvals,
        "supply_chain": reports,
        "principals": principals,
        "documents": documents,
        "policy": policy,
        "upstream_effect_count": effect_count(),
        "github_auth_configured": bool(os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")),
    }


@app.get("/api/integration")
async def integration() -> dict:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get("http://agent-service:8000/api/readiness")
            response.raise_for_status()
            readiness = response.json()
    except (httpx.HTTPError, ValueError):
        readiness = {"status": "not_ready", "model": {"mode": "unknown"}}
    runs = await db.fetch_all("SELECT id,session_id,status,user_id,created_at,response->>'status' AS outcome FROM agent_runs ORDER BY created_at DESC LIMIT 10")
    return {"readiness": readiness, "runs": runs}


@app.get("/api/policy/matrix")
async def policy_matrix() -> dict:
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
async def policy_ledger_view() -> dict:
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


@app.post("/api/calls")
async def call_tool(request: CallRequest, user: dict = Depends(caller)) -> dict:
    payload = {**request.model_dump(exclude_none=True), "user_token": user["principal"]}
    if request.tool_name in {"read_document", "write_document", "send_external"} and not request.document_id:
        raise HTTPException(422, "문서 도구에는 document_id가 필요합니다.")
    return await execute_call(payload)


@app.post("/api/mock-model")
async def mock_model(request: MockModelRequest, user: dict = Depends(caller)) -> dict:
    message = request.message
    if "시간" in message:
        tool = "get_current_time"
    elif any(word in message for word in ("외부", "전송", "보내")):
        tool = "send_external"
    elif any(word in message for word in ("수정", "작성", "써")):
        tool = "write_document"
    else:
        tool = "read_document"

    if any(word in message for word in ("중요", "계약", "비밀")):
        document_id = "secret-001"
    elif any(word in message for word in ("내부", "업무")):
        document_id = "work-001"
    else:
        document_id = "notice-001"
    payload = {
        "user_token": user["principal"],
        "tool_name": tool,
        "document_id": document_id,
        "content": message,
        "destination": "outside.example",
        "timezone": "Asia/Seoul",
    }
    result = await execute_call(payload)
    return {"generator": "deterministic-mock-v1", "generated_call": payload, "result": result}


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
async def catalog_refresh(user: dict = Depends(caller)) -> dict:
    results = []
    for server_id in ("mock-http", "mock-stdio"):
        try:
            results.append(await refresh_catalog(server_id))
        except Exception as exc:
            results.append({"server_id": server_id, "status": "ERROR", "reason": str(exc)})
    return {"results": results}


@app.post("/api/supply-chain/import")
async def supply_chain_import(user: dict = Depends(admin_caller)) -> dict:
    try:
        return {"imported": await import_supply_chain_reports()}
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(422, f"보고서 파싱 실패: {exc}") from exc


@app.get("/api/supply-chain/coverage")
async def supply_chain_cover() -> dict:
    """Says, per server, whether its scan output actually gates calls."""
    rows = await supply_chain_coverage()
    return {"servers": rows,
            "unwired": [row["server_id"] for row in rows if row["scan_path"] and not row["reports"]]}


@app.get("/api/enforcement")
async def enforcement() -> dict:
    return {"enforcement": await enforcement_mode()}


@app.put("/api/enforcement")
async def enforcement_update(request: EnforcementRequest, user: dict = Depends(admin_caller)) -> dict:
    """Turning enforcement on is an operator decision, so it is authenticated and logged."""
    try:
        return await set_enforcement_mode(request.mode, user["principal"])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/monitor/summary")
async def monitor(hours: int = 168) -> dict:
    """What enforcement would have stopped, so a team can turn it on with numbers."""
    return await monitor_summary(min(max(hours, 1), 8760))


@app.get("/api/audit/verify")
async def audit_verify(user: dict = Depends(admin_caller)) -> dict:
    """Answers "감사 로그가 위변조됐나요?" with a row id instead of an assurance."""
    return await verify_audit_chain()


@app.get("/api/effects")
async def effects() -> dict:
    events = []
    if EFFECT_LOG.exists():
        for line in EFFECT_LOG.read_text(encoding="utf-8").splitlines()[-30:]:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return {"count": len(events), "events": list(reversed(events))}


# ── 전주기 종료·폐기 ────────────────────────────────────────────────────────
#
# 이 API가 하는 일은 "끄기"가 아니라 "끈 것을 증명할 수 있게 하기"다. 그래서
# 케이스를 여는 것과 닫는 것이 따로 있고, 그 사이에 회수 대상·증거·판정이 있다.
# 한 번의 호출로 서버를 끄고 끝낼 수 있게 만들면 아무도 나머지를 하지 않는다.


class TerminationOpen(StrictModel):
    server_id: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=10, max_length=1000)
    engagement_label: str | None = Field(default=None, max_length=300)


class TargetCreate(StrictModel):
    kind: Literal["client-token", "refresh-token", "dynamic-registration", "session",
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
                  "gateway-denial", "liveness-probe", "endpoint-inventory",
                  "operator-statement"]
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


@app.get("/api/termination/cases")
async def termination_cases(user: dict = Depends(admin_caller)) -> dict:
    return {"cases": await decommission.list_cases(), "summary": await decommission.summary()}


@app.post("/api/termination/cases", status_code=201)
async def termination_open(request: TerminationOpen, user: dict = Depends(admin_caller)) -> dict:
    try:
        return await decommission.open_case(
            request.server_id, request.reason, user["principal"], request.engagement_label)
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


@app.post("/api/endpoint/enroll", status_code=201)
async def endpoint_enroll(request: EndpointEnroll, user: dict = Depends(admin_caller)) -> dict:
    """엔드포인트 등록. 관리자 자격을 요구한다.

    에이전트가 스스로 등록할 수 있게 열어두면 아무나 엔드포인트를 만들어 임의의
    인벤토리를 올릴 수 있고, 그 인벤토리가 종료 판정의 입력이 된다. 보고는 자동,
    등록은 사람이다.
    """
    row = await endpoint_plane.enroll(
        request.endpoint_id, request.hostname, request.platform,
        request.agent_version, request.owner_token, request.detail)
    return {key: (value.isoformat() if hasattr(value, "isoformat") else value)
            for key, value in dict(row).items()}


@app.post("/api/endpoint/inventory")
async def endpoint_report(request: EndpointReport, user: dict = Depends(caller)) -> dict:
    """관측 보고를 받는다. 이 본문은 데이터이지 지시가 아니다.

    보고 내용으로 Registry를 바꾸거나 서버를 활성화하는 경로는 없다. 조작된
    엔드포인트가 할 수 있는 최악은 없는 잔존을 보고하는 것이고, 그것은 판정을
    보수적인 쪽으로만 민다.
    """
    try:
        return await endpoint_plane.ingest(
            request.endpoint_id, [entry.model_dump() for entry in request.entries])
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
        "entries": await endpoint_plane.inventory(classification),
    }


@app.get("/api/risk-catalog")
async def risk_catalog() -> dict:
    """AI-Infra-Guard의 위험 범주와 이 조직의 통제를 연결한 표.

    발견 목록을 읽을거리가 아니라 통제로 잇는 것은 이 매핑뿐이다. 인증 없이 여는
    이유는 조직 자산이 아니라 참조 분류표이기 때문이다(13절의 열린 읽기 목록).
    """
    rows = await db.fetch_all("SELECT * FROM aig_risk_catalog ORDER BY ordinal")
    return {"categories": [dict(row) for row in rows]}


app.mount("/mcp", mcp_http)


@app.get("/", include_in_schema=False)
async def console() -> RedirectResponse:
    """The browser console lives with the Agent service; this port remains the API boundary."""
    return RedirectResponse("http://localhost:8000/workspace")
