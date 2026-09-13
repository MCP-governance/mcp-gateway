from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from . import db
from .core import (
    OPA_URL,
    TOOL_SPECS,
    approve_request,
    bootstrap,
    effect_count,
    execute_call,
    import_supply_chain_reports,
    refresh_catalog,
)
from .mcp_facade import build_mcp, transport_security

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
    user_token: Literal["cust-demo", "emp-demo", "admin-demo"]
    tool_name: Literal["read_document", "write_document", "send_external", "get_current_time", "github_get_file"]
    document_id: Literal["notice-001", "work-001", "secret-001"] | None = None
    content: str = Field(default="합성 데모 내용", max_length=2000)
    destination: str = Field(default="outside.example", max_length=200)
    timezone: str = Field(default="Asia/Seoul", max_length=64)
    owner: str = Field(default="MCP-governance", max_length=100)
    repo: str = Field(default="mcp-gateway", max_length=100)
    path: str = Field(default="README.md", max_length=300)


class MockModelRequest(StrictModel):
    user_token: Literal["cust-demo", "emp-demo", "admin-demo"]
    message: str = Field(min_length=1, max_length=500)


class ApprovalRequest(StrictModel):
    reviewer_token: Literal["admin-demo"] = "admin-demo"


@asynccontextmanager
async def lifespan(_: FastAPI):
    await bootstrap()
    async with gateway_mcp.session_manager.run():
        yield


app = FastAPI(title="MCP Governance Security Gateway", version="1.0.0", lifespan=lifespan)


async def _probe(url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            response = await client.get(url)
            return response.status_code < 500
    except Exception:
        return False


@app.get("/api/health")
async def health() -> dict:
    db_ok, opa_ok, upstream_ok, jaeger_ok = await asyncio.gather(
        _probe("http://db:5432"),
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
        db.fetch_all("SELECT token,display_name,role,synthetic FROM principals ORDER BY role"),
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


@app.post("/api/calls")
async def call_tool(request: CallRequest) -> dict:
    payload = request.model_dump(exclude_none=True)
    if request.tool_name in {"read_document", "write_document", "send_external"} and not request.document_id:
        raise HTTPException(422, "문서 도구에는 document_id가 필요합니다.")
    return await execute_call(payload)


@app.post("/api/mock-model")
async def mock_model(request: MockModelRequest) -> dict:
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
        "user_token": request.user_token,
        "tool_name": tool,
        "document_id": document_id,
        "content": message,
        "destination": "outside.example",
        "timezone": "Asia/Seoul",
    }
    result = await execute_call(payload)
    return {"generator": "deterministic-mock-v1", "generated_call": payload, "result": result}


@app.post("/api/approvals/{approval_id}/approve")
async def approve(approval_id: str, request: ApprovalRequest) -> dict:
    try:
        return await approve_request(approval_id, request.reviewer_token)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/catalog/refresh")
async def catalog_refresh() -> dict:
    results = []
    for server_id in ("mock-http", "mock-stdio"):
        try:
            results.append(await refresh_catalog(server_id))
        except Exception as exc:
            results.append({"server_id": server_id, "status": "ERROR", "reason": str(exc)})
    return {"results": results}


@app.post("/api/supply-chain/import")
async def supply_chain_import() -> dict:
    try:
        return {"imported": await import_supply_chain_reports()}
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(422, f"보고서 파싱 실패: {exc}") from exc


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
        candidate = UI_DIR / path
        return FileResponse(candidate if candidate.is_file() else UI_DIR / "index.html")
