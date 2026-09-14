from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from . import db
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
from .agent_contract import authenticated_user
from .agent_gateway import router as agent_router

AGENT_SERVICE_URL = os.getenv("AGENT_SERVICE_URL", "http://agent-service:8000")

UI_DIR = Path("/app/ui")
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
    document_id: Literal["notice-001", "work-001", "secret-001"] | None = None
    content: str = Field(default="합성 데모 내용", max_length=2000)
    destination: str = Field(default="outside.example", max_length=200)
    timezone: str = Field(default="Asia/Seoul", max_length=64)
    owner: str = Field(default="MCP-governance", max_length=100)
    repo: str = Field(default="mcp-gateway", max_length=100)
    path: str = Field(default="README.md", max_length=300)


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
    roles = ("customer", "employee", "admin")
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
            result = {"decision": "Block", "policy_id": "P-CONTROL-FAIL-CLOSED"}
        return {"role": role, "data_class": data_class, "action": action, **result}

    cells = await asyncio.gather(*(evaluate(role, data_class, action) for role in roles for data_class in classes for action in actions))
    return {"roles": roles, "data_classes": classes, "actions": actions, "cells": cells}


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


app.mount("/mcp", mcp_http)

if UI_DIR.exists():
    app.mount("/assets", StaticFiles(directory=UI_DIR / "assets"), name="assets")

    @app.get("/{path:path}", response_class=FileResponse)
    async def ui(path: str) -> FileResponse:
        candidate = (UI_DIR / path).resolve()
        if not candidate.is_relative_to(UI_DIR.resolve()):
            raise HTTPException(404, "Not found")
        return FileResponse(candidate if candidate.is_file() else UI_DIR / "index.html")
