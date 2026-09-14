"""Adapted from MCP-governance/Agent-Service miso@81177a4 (login/workspace/chat)."""
from __future__ import annotations

import asyncio
import os
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from psycopg.types.json import Jsonb

from . import db
from .agent_contract import IDENTITIES, StrictModel, authenticate, authenticated_user, issue_token, signing_key
from .core import canonical_hash
from .model_client import propose, readiness, redact

STATIC_DIR = Path(__file__).parent / "agent_static"
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://gateway:8080")
# ponytail: four active requests per process; distributed quotas belong at ingress for multi-replica deployment.
slots = asyncio.Semaphore(4)


@asynccontextmanager
async def lifespan(_: FastAPI):
    signing_key()
    await db.wait_until_ready()
    await db.execute((Path(__file__).parent / "agent_tables.sql").read_text())
    try:
        yield
    finally:
        await db.close()


app = FastAPI(title="Agent Service · miso integration", version="1.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def browser_boundary(request: Request, call_next):
    origin = request.headers.get("origin")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and origin and origin != str(request.base_url).rstrip("/"):
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "다른 출처의 요청은 허용하지 않습니다."}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
    return response


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/login")


@app.get("/login", include_in_schema=False)
async def login_page():
    return FileResponse(STATIC_DIR / "login.html")


@app.get("/workspace", include_in_schema=False)
async def workspace_page():
    return FileResponse(STATIC_DIR / "workspace.html")


class Login(StrictModel):
    email: str = Field(max_length=150)
    password: str = Field(max_length=150)


class ChatRequest(StrictModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: UUID | None = None
    request_id: UUID = Field(default_factory=uuid4)


async def current_identity(authorization: str | None) -> dict:
    return await authenticated_user(authorization)


@app.post("/auth/mock-login")
async def login(request: Login):
    email = request.email.strip().lower()
    user = IDENTITIES.get(email)
    expected = os.getenv("MOCK_SSO_PASSWORD", "test-password")
    if not secrets.compare_digest(request.password.encode(), expected.encode()) or not user:
        raise HTTPException(401, "합성 계정과 비밀번호를 확인해주세요.")
    return {"access_token": issue_token(user), "token_type": "bearer", "expires_in": 1800,
            "user": {k: v for k, v in {**user, "email": email, "synthetic": True}.items() if k != "principal"}}


@app.get("/auth/me")
async def me(authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    return {k: v for k, v in {**user, "synthetic": True}.items() if k != "principal"}


@app.post("/auth/logout")
async def logout(authorization: str | None = Header(default=None)):
    _, claims = authenticate(authorization)
    await db.execute("INSERT INTO agent_revoked_tokens(jti,expires_at) VALUES (%s,%s) ON CONFLICT DO NOTHING", (claims["jti"], datetime.fromtimestamp(claims["exp"], UTC)))
    # Rows are only ever added here, so purging here bounds the table by the number
    # of logouts inside one token lifetime. A revoked token past its own expiry is
    # already rejected by the signature check.
    await db.execute("DELETE FROM agent_revoked_tokens WHERE expires_at < now()")
    return {"status": "logged_out"}


@app.get("/health")
async def health():
    await db.fetch_one("SELECT 1")
    return {"status": "ok", "service": "agent-service", "model": readiness()}


@app.get("/api/readiness")
async def ready():
    gateway_ok = False
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(GATEWAY_URL + "/api/health")
            gateway_ok = response.status_code == 200 and response.json().get("status") == "ok"
    except (httpx.HTTPError, ValueError):
        pass
    config = readiness()
    return {"status": "ready" if gateway_ok and config["configured"] else "not_ready", "gateway": gateway_ok, "model": config,
            "identity": "synthetic-jwt", "github_mcp": "catalog-and-auth-pending",
            "source": "MCP-governance/Agent-Service miso@81177a41d917a2c1382485cc8f5ae115637aff89"}


@app.get("/sessions")
async def sessions(authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    return {"sessions": await db.fetch_all("SELECT id,created_at FROM agent_sessions WHERE user_id=%s ORDER BY created_at DESC LIMIT 20", (user["user_id"],))}


@app.get("/sessions/{session_id}")
async def session_history(session_id: UUID, authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    await owned_session(session_id, user["user_id"])
    return {"runs": await db.fetch_all("SELECT id,message,status,response,created_at FROM agent_runs WHERE session_id=%s ORDER BY created_at DESC LIMIT 30", (session_id,))}


async def owned_session(session_id: UUID, user_id: str):
    session = await db.fetch_one("SELECT user_id FROM agent_sessions WHERE id=%s", (session_id,))
    if not session or session["user_id"] != user_id:
        raise HTTPException(404, "접근할 수 없는 세션입니다.")


@app.post("/chat")
async def chat(request: ChatRequest, authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    message = request.message.strip()
    if not message:
        raise HTTPException(422, "업무 요청을 입력하세요.")
    fingerprint = canonical_hash({"message": message, "session_id": str(request.session_id)})
    prior = await db.fetch_one("SELECT * FROM agent_runs WHERE id=%s", (request.request_id,))
    if prior:
        if prior["user_id"] != user["user_id"] or prior["fingerprint"] != fingerprint:
            raise HTTPException(409, "요청 ID가 다른 내용에 이미 사용됐습니다.")
        if prior["response"] is not None:
            return {**prior["response"], "replayed": True}
        raise HTTPException(409, "진행 중이거나 확인이 필요한 요청입니다. 같은 작업을 중복 실행하지 않습니다.")
    session_id = request.session_id or uuid4()
    if request.session_id:
        await owned_session(session_id, user["user_id"])
    else:
        await db.execute("INSERT INTO agent_sessions(id,user_id) VALUES (%s,%s)", (session_id, user["user_id"]))
    inserted = await db.fetch_one("INSERT INTO agent_runs(id,session_id,user_id,fingerprint,message) VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id",
                                  (request.request_id, session_id, user["user_id"], fingerprint, redact(message)))
    if not inserted:
        raise HTTPException(409, "같은 요청이 처리 중입니다.")
    result = {"request_id": str(request.request_id), "session_id": str(session_id), "status": "failed", "tool_call": None, "gateway_result": None, "replayed": False}
    async with slots:
        try:
            history = await db.fetch_all("SELECT message FROM agent_runs WHERE session_id=%s AND id<>%s AND status='COMPLETE' ORDER BY created_at DESC LIMIT 4", (session_id, request.request_id))
            proposal, generator = await propose(message, [r["message"] for r in reversed(history)])
            result["generator"] = generator
            if not proposal:
                result.update(status="no_tool", message="등록된 업무 도구로 변환할 수 없는 요청입니다. 실행하지 않았습니다.")
            else:
                call_id = uuid4()
                envelope = {"request_id": str(request.request_id), "session_id": str(session_id), "user_id": user["user_id"], "agent_id": "document-agent-test", "tool_call_id": str(call_id), **proposal.model_dump()}
                result["tool_call"] = {"tool_call_id": str(call_id), **proposal.model_dump()}
                async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
                    response = await client.post(GATEWAY_URL + "/tool-call", headers={"Authorization": authorization}, json=envelope)
                    response.raise_for_status()
                    outcome = response.json()
                result.update(gateway_result=outcome, status=outcome["decision"].lower(), message=outcome["reason"])
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            # Never echo provider URLs, credentials or raw provider error responses to the browser/audit.
            code = "MODEL-TIMEOUT" if isinstance(exc, httpx.TimeoutException) else "AGENT-PIPELINE-001"
            result.update(error_code=code, message="모델 또는 Gateway 응답 검증에 실패했습니다. 실행 결과가 불확실할 수 있으므로 같은 요청을 자동 재실행하지 않습니다.")
    await db.execute("UPDATE agent_runs SET status=%s,response=%s,completed_at=now() WHERE id=%s", ("FAILED" if result["status"] == "failed" else "COMPLETE", Jsonb(result), request.request_id))
    return result


@app.get("/approvals")
async def approvals(authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "합성 관리자 계정이 필요합니다.")
    return {"approvals": await db.fetch_all("SELECT id,requested_by,created_at,expires_at,request_payload->>'tool_name' AS tool_name FROM approvals WHERE status='PENDING' AND expires_at>now() ORDER BY created_at DESC LIMIT 30")}


@app.post("/approvals/{approval_id}/approve")
async def approve(approval_id: UUID, authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "합성 관리자 계정이 필요합니다.")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(f"{GATEWAY_URL}/agent/approvals/{approval_id}/approve", headers={"Authorization": authorization})
    if response.status_code >= 400:
        raise HTTPException(response.status_code, "승인할 수 없습니다. 이미 처리됐거나 만료된 요청인지 확인하세요.")
    return response.json()
