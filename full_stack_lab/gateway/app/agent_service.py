"""Adapted from MCP-governance/Agent-Service miso@81177a4 (login/workspace/chat)."""
from __future__ import annotations

import asyncio
import os
import secrets
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from psycopg.types.json import Jsonb

from . import db
from .agent_contract import (Envelope, IDENTITIES, StrictModel, authenticate, authenticated_user,
                             issue_agent_assertion, issue_token, private_key)
from .core import canonical_hash
from .model_client import propose, readiness, redact

STATIC_DIR = Path(__file__).parent / "agent_static"
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://gateway:8080")
# ponytail: four active requests per process; distributed quotas belong at ingress for multi-replica deployment.
slots = asyncio.Semaphore(4)

LOGIN_ATTEMPT_LIMIT = int(os.getenv("LOGIN_ATTEMPT_LIMIT", "10"))
LOGIN_ATTEMPT_WINDOW = int(os.getenv("LOGIN_ATTEMPT_WINDOW_SECONDS", "300"))
# Per process, like `slots` above: a deployment with replicas rate-limits at ingress.
# It still turns an unlimited password oracle into a bounded one.
_login_attempts: dict[str, list[float]] = defaultdict(list)


def login_allowed(key: str) -> bool:
    now = time.monotonic()
    for attempted, stamps in list(_login_attempts.items()):
        recent = [stamp for stamp in stamps if now - stamp < LOGIN_ATTEMPT_WINDOW]
        if recent:
            _login_attempts[attempted] = recent
        else:
            del _login_attempts[attempted]
    return len(_login_attempts.get(key, ())) < LOGIN_ATTEMPT_LIMIT


def record_failed_login(key: str) -> None:
    _login_attempts[key].append(time.monotonic())


@asynccontextmanager
async def lifespan(_: FastAPI):
    private_key()  # fail fast if this process is not actually the token issuer
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
    return FileResponse(STATIC_DIR / "console.html")


class Login(StrictModel):
    email: str = Field(max_length=150)
    password: str = Field(max_length=150)


class ChatRequest(StrictModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: UUID | None = None
    request_id: UUID = Field(default_factory=uuid4)


class McpIntake(StrictModel):
    display_name: str = Field(min_length=2, max_length=80)
    repository_url: str = Field(min_length=12, max_length=300)
    requested_transport: Literal["streamable-http", "stdio", "sse"]
    purpose: str = Field(min_length=10, max_length=1000)


class IntakeRejection(StrictModel):
    note: str = Field(min_length=2, max_length=500)


def github_repository_url(value: str) -> str:
    """Accept a repository identity, not an arbitrary URL the service might fetch."""
    parsed = urlsplit(value.strip())
    pieces = [piece for piece in parsed.path.split("/") if piece]
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {"github.com", "www.github.com"}
        or parsed.username
        or parsed.password
        or parsed.port
        or parsed.query
        or parsed.fragment
        or len(pieces) != 2
    ):
        raise ValueError("https://github.com/조직/저장소 형식의 URL만 제출할 수 있습니다.")
    owner, repository = pieces
    repository = repository.removesuffix(".git")
    if not owner or not repository or any(part in {".", ".."} for part in (owner, repository)):
        raise ValueError("유효한 GitHub 조직과 저장소 이름을 입력하세요.")
    return f"https://github.com/{owner}/{repository}"


async def current_identity(authorization: str | None) -> dict:
    return await authenticated_user(authorization)


@app.post("/auth/mock-login")
async def login(request: Login, http_request: Request):
    email = request.email.strip().lower()
    # Checked before the identity lookup so an unknown address is throttled too;
    # otherwise the limit itself tells an attacker which addresses exist.
    caller = http_request.client.host if http_request.client else "unknown"
    if not login_allowed(f"{caller}|{email}"):
        raise HTTPException(429, "로그인 시도가 너무 많습니다. 잠시 후 다시 시도하세요.")
    user = IDENTITIES.get(email)
    expected = os.getenv("MOCK_SSO_PASSWORD", "test-password")
    if not secrets.compare_digest(request.password.encode(), expected.encode()) or not user:
        record_failed_login(f"{caller}|{email}")
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


async def gateway_json(path: str, authorization: str | None = None, method: str = "GET") -> dict:
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
            response = await client.request(method, GATEWAY_URL + path, headers={"Authorization": authorization or ""})
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(503, "거버넌스 상태를 불러올 수 없습니다.") from exc


def console_user(user: dict) -> dict:
    return {key: user[key] for key in ("name", "department", "roles", "email")}


async def intake_rows(user: dict) -> list[dict]:
    query = """SELECT id, submitted_by, display_name, repository_url, requested_transport, purpose,
                      status, risk_level, review_note, reviewed_by, reviewed_at, created_at, updated_at
               FROM mcp_intake_requests"""
    if "admin" in user["roles"]:
        return await db.fetch_all(query + " ORDER BY created_at DESC LIMIT 100")
    return await db.fetch_all(query + " WHERE submitted_by=%s ORDER BY created_at DESC LIMIT 100", (user["principal"],))


@app.get("/api/console")
async def console(authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    health, state, coverage, monitor = await asyncio.gather(
        gateway_json("/api/health"),
        gateway_json("/api/state"),
        gateway_json("/api/supply-chain/coverage"),
        gateway_json("/api/monitor/summary?hours=168"),
    )
    reports = state["supply_chain"]
    severity = {
        "critical": sum(int(report.get("critical_count") or 0) for report in reports),
        "high": sum(int(report.get("high_count") or 0) for report in reports),
        "medium": sum(int(report.get("medium_count") or 0) for report in reports),
    }
    return {
        "viewer": console_user(user),
        "model": readiness(),
        "health": health,
        "registry": state["servers"],
        "decisions": state["decisions"],
        "approvals": state["approvals"],
        "supply_chain": reports,
        "coverage": coverage,
        "monitor": monitor,
        "policy": state["policy"],
        "upstream_effect_count": state["upstream_effect_count"],
        "intake": await intake_rows(user),
        "severity": severity,
    }


@app.post("/api/mcp-requests")
async def create_mcp_request(request: McpIntake, authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    try:
        repository_url = github_repository_url(request.repository_url)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    existing = await db.fetch_one(
        "SELECT id FROM mcp_intake_requests WHERE repository_url=%s AND status<>%s",
        (repository_url, "REJECTED"),
    )
    if existing:
        raise HTTPException(409, "같은 저장소가 이미 검토 대기 또는 검증 중입니다.")
    row = await db.fetch_one(
        """INSERT INTO mcp_intake_requests(
                 id, submitted_by, display_name, repository_url, requested_transport, purpose
             ) VALUES (%s,%s,%s,%s,%s,%s)
             RETURNING id, display_name, repository_url, requested_transport, purpose, status, risk_level, created_at""",
        (uuid4(), user["principal"], request.display_name.strip(), repository_url,
         request.requested_transport, request.purpose.strip()),
    )
    return {"request": row, "message": "제출 완료. 격리된 체크아웃과 검증 증적이 연결되기 전까지 보류됩니다."}


@app.post("/api/mcp-requests/{request_id}/queue-validation")
async def queue_validation(request_id: UUID, authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "검증 대기열은 관리자만 변경할 수 있습니다.")
    row = await db.fetch_one(
        """UPDATE mcp_intake_requests
           SET status='VALIDATION_QUEUED', reviewed_by=%s, reviewed_at=now(), updated_at=now()
           WHERE id=%s AND status='HOLD'
           RETURNING id, status, reviewed_by, reviewed_at""",
        (user["principal"], request_id),
    )
    if not row:
        raise HTTPException(409, "보류 상태의 요청만 검증 대기열로 이동할 수 있습니다.")
    return {"request": row, "message": "검증 대기열에 넣었습니다. 스캐너는 격리된 체크아웃에서 실행해야 합니다."}


@app.post("/api/mcp-requests/{request_id}/reject")
async def reject_mcp_request(request_id: UUID, request: IntakeRejection, authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "요청 거부는 관리자만 할 수 있습니다.")
    row = await db.fetch_one(
        """UPDATE mcp_intake_requests
           SET status='REJECTED', review_note=%s, reviewed_by=%s, reviewed_at=now(), updated_at=now()
           WHERE id=%s AND status IN ('HOLD','VALIDATION_QUEUED')
           RETURNING id, status, review_note, reviewed_by, reviewed_at""",
        (request.note.strip(), user["principal"], request_id),
    )
    if not row:
        raise HTTPException(409, "보류 또는 검증 대기 상태의 요청만 거부할 수 있습니다.")
    return {"request": row}


@app.post("/api/supply-chain/import")
async def import_supply_chain(authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "검증 결과 반영은 관리자만 할 수 있습니다.")
    return await gateway_json("/api/supply-chain/import", authorization, method="POST")


@app.post("/api/registry/refresh")
async def refresh_registry(authorization: str | None = Header(default=None)):
    await current_identity(authorization)
    return await gateway_json("/api/catalog/refresh", authorization, method="POST")


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
                envelope = Envelope(request_id=request.request_id, session_id=session_id,
                                    user_id=user["user_id"], tool_call_id=call_id,
                                    **proposal.model_dump())
                result["tool_call"] = {"tool_call_id": str(call_id), **proposal.model_dump()}
                async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
                    response = await client.post(
                        GATEWAY_URL + "/tool-call",
                        headers={"Authorization": authorization or "", "X-Agent-Assertion": "Bearer " + issue_agent_assertion(user, envelope)},
                        json=envelope.model_dump(mode="json"),
                    )
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


class Rejection(StrictModel):
    note: str = Field(min_length=1, max_length=500)


@app.post("/approvals/{approval_id}/reject")
async def reject(approval_id: UUID, request: Rejection, authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "합성 관리자 계정이 필요합니다.")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(f"{GATEWAY_URL}/agent/approvals/{approval_id}/reject",
                                     headers={"Authorization": authorization}, json={"note": request.note})
    if response.status_code >= 400:
        raise HTTPException(response.status_code, "거부할 수 없습니다. 이미 처리됐거나 만료된 요청인지 확인하세요.")
    return response.json()


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
