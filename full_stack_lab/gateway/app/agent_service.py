"""Adapted from MCP-governance/Agent-Service miso@81177a4 (login/workspace/chat)."""
from __future__ import annotations

import asyncio
import json
import os
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
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from psycopg.types.json import Jsonb

from . import db
from .agent_contract import (ACCOUNT_STATUS_REASON, Envelope, StrictModel, authenticate,
                             authenticated_user, issue_agent_assertion, issue_token, private_key)
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


async def bootstrap_passwords() -> None:
    """합성 계정의 초기 비밀번호를 한 번만 채운다.

    해시를 SQL 파일에 박아두면 `.env`의 `MOCK_SSO_PASSWORD`로 바꿀 수 없고, 매
    기동마다 덮어쓰면 관리대장이 아니라 환경변수가 정본이 된다. 그래서 비어 있는
    계정만 채운다. 바꾸고 싶으면 `./console.sh reset`으로 다시 심는다.
    """
    await db.execute(
        """UPDATE principals SET password_hash = crypt(%s, gen_salt('bf', 12))
           WHERE password_hash IS NULL AND email IS NOT NULL""",
        (os.getenv("MOCK_SSO_PASSWORD", "test-password"),))


@asynccontextmanager
async def lifespan(_: FastAPI):
    private_key()  # fail fast if this process is not actually the token issuer
    await db.wait_until_ready()
    await db.execute((Path(__file__).parent / "agent_tables.sql").read_text())
    await bootstrap_passwords()
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
    """합성 로그인. 비밀번호 검증은 신원 관리대장의 사용자별 bcrypt 해시로 한다.

    이전 판은 모든 계정이 같은 환경변수 하나(`MOCK_SSO_PASSWORD`)를 비밀번호로
    썼다. 그러면 한 계정만 잠그거나 한 계정의 비밀번호만 바꾸는 일이 불가능하고,
    "계정을 끈다"는 조치가 배포가 된다. 팀원 저장소 Agent-Service의 `miso` 브랜치가
    쓰던 `crypt()` 검증 방식을 이 관리대장에 맞춰 가져왔다.
    """
    email = request.email.strip().lower()
    # Checked before the identity lookup so an unknown address is throttled too;
    # otherwise the limit itself tells an attacker which addresses exist.
    caller = http_request.client.host if http_request.client else "unknown"
    if not login_allowed(f"{caller}|{email}"):
        raise HTTPException(429, "로그인 시도가 너무 많습니다. 잠시 후 다시 시도하세요.")
    # 비밀번호 비교는 DB에서 한다. 애플리케이션으로 해시를 꺼내오면 "찾았지만 틀림"과
    # "없음"이 코드 경로로 갈라져 응답 시간이 주소 존재 여부를 알려준다.
    row = await db.fetch_one(
        """SELECT token, user_id, email, display_name, role, department, job_title, status,
                  (password_hash IS NOT NULL AND password_hash = crypt(%s, password_hash)) AS password_ok
           FROM principals WHERE lower(email)=%s""",
        (request.password, email))
    if not row or not row["password_ok"]:
        record_failed_login(f"{caller}|{email}")
        raise HTTPException(401, "합성 계정과 비밀번호를 확인해주세요.")
    if row["status"] != "active":
        # 실패 한도를 소진시키지 않는다. 비밀번호는 맞았고 계정 상태가 문제다.
        raise HTTPException(403, ACCOUNT_STATUS_REASON.get(row["status"], "사용할 수 없는 계정입니다."))
    user = {"user_id": row["user_id"], "principal": row["token"], "name": row["display_name"],
            "department": row["department"] or "미지정", "roles": [row["role"]], "email": row["email"]}
    return {"access_token": issue_token(user), "token_type": "bearer", "expires_in": 1800,
            "user": {k: v for k, v in {**user, "job_title": row["job_title"], "synthetic": True}.items()
                     if k != "principal"}}


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


class AccountStatus(StrictModel):
    status: Literal["active", "disabled", "locked"]
    note: str = Field(default="", max_length=300)


@app.get("/api/accounts")
async def list_accounts(authorization: str | None = Header(default=None)):
    """신원 관리대장. 관리자만 본다. 비밀번호 해시는 응답에 넣지 않는다."""
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "신원 관리대장은 관리자만 볼 수 있습니다.")
    return {"accounts": await db.fetch_all(
        """SELECT token, user_id, email, display_name, role, department, employee_no, job_title,
                  status, status_changed_by, status_changed_at,
                  (password_hash IS NOT NULL) AS has_password
           FROM principals ORDER BY role, email""")}


@app.put("/api/accounts/{user_id}/status")
async def set_account_status(user_id: str, request: AccountStatus,
                             authorization: str | None = Header(default=None)):
    """계정을 끄고 켜는 일이 배포가 되면 아무도 제때 끄지 않는다.

    상태는 신원 관리대장에 있고 매 요청마다 확인되므로, 여기서 `disabled`로 바꾸면
    이미 발급된 토큰도 다음 요청에서 막힌다. 토큰 만료를 기다리지 않는다.
    """
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "계정 상태 변경은 관리자만 할 수 있습니다.")
    if user["user_id"] == user_id and request.status != "active":
        # 마지막 관리자가 스스로를 잠그면 되돌릴 사람이 남지 않는다.
        raise HTTPException(409, "자기 계정은 스스로 중지하거나 잠글 수 없습니다.")
    row = await db.fetch_one(
        """UPDATE principals SET status=%s, status_changed_by=%s, status_changed_at=now()
           WHERE user_id=%s
           RETURNING token, user_id, email, display_name, role, status, status_changed_by, status_changed_at""",
        (request.status, user["principal"], user_id))
    if not row:
        raise HTTPException(404, "관리대장에 없는 계정입니다.")
    return {"account": row,
            "message": f"{row['email']} 계정을 {request.status}로 바꿨습니다. 이미 발급된 인증도 다음 요청부터 적용됩니다."}


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


# 역할이 볼 수 있는 화면. 숨기기만 하는 메뉴는 통제가 아니라 장식이므로
# /api/console이 이 목록을 기준으로 데이터 자체를 빼고 응답한다.
PAGES_BY_ROLE = {
    # 내부 직원도 최소권한이다. 직원에게 필요한 것은 "내가 쓸 MCP가 이미 승인돼
    # 있는가"와 "내 호출이 어떻게 판정됐는가"이지 조직 전체의 정책 관리대장이나
    # 공급망 증적이 아니다.
    "partner": ("execution", "intake"),
    "employee": ("execution", "intake", "audit"),
    "admin": ("overview", "intake", "verification", "risks", "mcpscan", "policy", "accounts", "execution", "audit"),
}
ROLE_LABELS = {"partner": "협력업체 직원", "employee": "직원", "admin": "관리자"}


def allowed_pages(user: dict) -> list[str]:
    pages: list[str] = []
    for role in user["roles"]:
        for page in PAGES_BY_ROLE.get(role, ()):
            if page not in pages:
                pages.append(page)
    return pages


def console_user(user: dict) -> dict:
    return {
        **{key: user[key] for key in ("name", "department", "roles", "email")},
        # 신원 관리대장 화면이 "본인 계정"을 가려내려면 필요하다. 관리자가 자기
        # 계정을 잠그는 버튼을 누를 수 있게 두면, 되돌릴 사람이 남지 않는다.
        "user_id": user.get("user_id"),
        "role_label": ", ".join(ROLE_LABELS.get(role, role) for role in user["roles"]),
        "pages": allowed_pages(user),
    }


async def intake_rows(user: dict) -> list[dict]:
    query = """SELECT id, submitted_by, display_name, repository_url, requested_transport, purpose,
                      status, risk_level, review_note, reviewed_by, reviewed_at, created_at, updated_at,
                      commit_sha, source_ref, evidence, validated_at
               FROM mcp_intake_requests"""
    if "admin" in user["roles"]:
        return await db.fetch_all(query + " ORDER BY created_at DESC LIMIT 100")
    return await db.fetch_all(query + " WHERE submitted_by=%s ORDER BY created_at DESC LIMIT 100", (user["principal"],))


@app.get("/api/console")
async def console(authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    pages = allowed_pages(user)
    is_admin = "admin" in user["roles"]

    wanted = {"health": gateway_json("/api/health"), "state": gateway_json("/api/state")}
    if "verification" in pages or "risks" in pages:
        wanted["coverage"] = gateway_json("/api/supply-chain/coverage")
    if "overview" in pages:
        wanted["monitor"] = gateway_json("/api/monitor/summary?hours=168")
    if "policy" in pages:
        wanted["ledger"] = gateway_json("/api/policy/ledger")
    results = dict(zip(wanted, await asyncio.gather(*wanted.values())))
    state = results["state"]

    # 공급망 증적과 정책 판정은 역할에 따라 아예 실어 보내지 않는다. 화면에서만
    # 숨기면 개발자 도구를 여는 순간 통제가 사라진다.
    reports = state["supply_chain"] if "risks" in pages or "verification" in pages else []
    decisions = state["decisions"] if is_admin else [
        row for row in state["decisions"] if row.get("user_token") == user["principal"]
    ]
    payload = {
        "viewer": console_user(user),
        "health": results["health"],
        "registry": state["servers"] if "overview" in pages else [],
        "decisions": decisions if "overview" in pages or "audit" in pages else [],
        "approvals": state["approvals"] if is_admin else [],
        "supply_chain": reports,
        "coverage": results.get("coverage", {"servers": []}),
        "monitor": results.get("monitor", {}),
        "policy": state["policy"] if "policy" in pages else None,
        # §12.5 PaC 정책 관리대장. 운영자가 정책 코드를 읽지 않고도 어떤 위험·통제를
        # 구현한 정책이 지금 어떤 버전·상태로 적용 중인지 확인할 수 있어야 한다.
        "ledger": results.get("ledger", {}),
        "upstream_effect_count": state["upstream_effect_count"],
        "intake": await intake_rows(user),
        "severity": {
            "critical": sum(int(report.get("critical_count") or 0) for report in reports),
            "high": sum(int(report.get("high_count") or 0) for report in reports),
            "medium": sum(int(report.get("medium_count") or 0) for report in reports),
        },
    }
    return payload


@app.get("/api/mcp-catalog/search")
async def search_catalog(q: str = "", authorization: str | None = Header(default=None)):
    """이미 누가 신청했거나 승인받은 MCP인지 누구나 조회할 수 있다.

    이것이 없으면 같은 저장소를 여러 사람이 반복해서 신청하고, 이미 거부된
    서버를 모르고 다시 올린다. 대신 신청자 신원과 도입 목적 본문은 돌려주지
    않는다. 필요한 답은 "이미 있는가 / 어떤 상태인가"이지 "누가 왜 냈는가"가
    아니다.
    """
    await current_identity(authorization)
    term = q.strip()
    like = f"%{term}%"
    request_query = """SELECT display_name, repository_url, requested_transport, status, risk_level,
                              commit_sha, source_ref, validated_at, reviewed_at, created_at
                       FROM mcp_intake_requests"""
    server_query = """SELECT id, display_name, transport, source_url, source_ref, supplier,
                             status, status_reason
                      FROM mcp_servers"""
    if term:
        requests = await db.fetch_all(
            request_query + " WHERE repository_url ILIKE %s OR display_name ILIKE %s"
            " ORDER BY created_at DESC LIMIT 50", (like, like))
        servers = await db.fetch_all(
            server_query + " WHERE source_url ILIKE %s OR display_name ILIKE %s OR id ILIKE %s"
            " ORDER BY id LIMIT 50", (like, like, like))
    else:
        requests = await db.fetch_all(request_query + " ORDER BY created_at DESC LIMIT 50")
        servers = await db.fetch_all(server_query + " ORDER BY id LIMIT 50")
    return {"query": term, "requests": requests, "registry": servers}


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
    return {"request": row, "message": "격리 워커가 복제 없이 대기 중인 요청을 가져가 SBOM·SCA·SAST를 만듭니다."}


@app.post("/api/mcp-requests/{request_id}/approve")
async def approve_mcp_request(request_id: UUID, authorization: str | None = Header(default=None)):
    """검증을 통과한 요청만 Registry 등록 대상이 된다.

    승인이 곧 연결은 아니다. 승인은 "이 저장소를 Registry에 올려도 된다"까지이고,
    실제 활성화는 endpoint와 catalog 해시를 고정하는 별도 단계다. 승인 버튼 하나로
    외부 저장소가 실행 경로에 들어오면 도입 심사가 형식이 된다.
    """
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "도입 승인은 관리자만 할 수 있습니다.")
    # T2 · 승인 게이트. AI 코드 감사를 요구하도록 설정했다면, 승인 시점에 "지금
    # 이 commit에 대한" 감사 결과가 있어야 한다. 감사가 승인 뒤에만 가능하면
    # 그것은 승인의 근거가 아니라 승인 뒤의 기록이다.
    if SCAN_REQUIRED_FOR_APPROVAL:
        evidence = await db.fetch_one(
            """SELECT j.id FROM scan_jobs j
               JOIN mcp_intake_requests r ON r.id::text = j.target_id
               WHERE j.target_kind='intake' AND r.id=%s
                 AND j.status='DONE' AND j.commit_sha = r.commit_sha""",
            (request_id,))
        if not evidence:
            raise HTTPException(
                409, "이 commit에 대한 AI 코드 감사 결과가 없습니다. "
                     "감사를 실행해 완료된 뒤에 승인할 수 있습니다.")
    row = await db.fetch_one(
        """UPDATE mcp_intake_requests
           SET status='APPROVED', reviewed_by=%s, reviewed_at=now(), updated_at=now()
           WHERE id=%s AND status='VALIDATED'
           RETURNING id, status, reviewed_by, reviewed_at, source_ref""",
        (user["principal"], request_id),
    )
    if not row:
        raise HTTPException(409, "격리 검증을 통과한 요청만 승인할 수 있습니다.")
    return {"request": row, "message": "Registry 등록 대상으로 승인했습니다. 실제 활성화는 endpoint와 catalog 해시 고정 후입니다."}


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


@app.get("/api/enforcement")
async def read_enforcement(authorization: str | None = Header(default=None)):
    await current_identity(authorization)
    return await gateway_json("/api/enforcement", authorization)


class EnforcementSwitch(StrictModel):
    mode: Literal["enforce", "monitor"]


@app.put("/api/enforcement")
async def switch_enforcement(request: EnforcementSwitch, authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "집행 모드 전환은 관리자만 할 수 있습니다.")
    async with httpx.AsyncClient(timeout=8) as client:
        response = await client.put(GATEWAY_URL + "/api/enforcement",
                                    headers={"Authorization": authorization or ""},
                                    json={"mode": request.mode})
    if response.status_code >= 400:
        raise HTTPException(response.status_code, "집행 모드를 바꾸지 못했습니다.")
    return response.json()


MCP_SCAN_CONFIG = {
    "MCP_SCAN_BASE_URL": os.getenv("MCP_SCAN_BASE_URL", ""),
    "MCP_SCAN_MODEL": os.getenv("MCP_SCAN_MODEL", ""),
    "MCP_SCAN_API_KEY": os.getenv("MCP_SCAN_API_KEY", ""),
}
# 워커가 lease를 갱신하는 주기보다 넉넉하게 잡는다. 이 값을 넘도록 소식이 없으면
# "큐에 넣었다"와 "누군가 실행한다"가 더는 같은 말이 아니다.
WORKER_STALE_SECONDS = int(os.getenv("INTAKE_WORKER_STALE_SECONDS", "60"))
# §11.4.1의 승인 유효기간과 같은 생각이다. 승인에 기한이 있는데 그 승인의 근거인
# 감사에 기한이 없으면, 먼저 낡는 것은 승인이 아니라 근거다.
SCAN_REQUIRED_FOR_APPROVAL = os.getenv("MCP_SCAN_REQUIRED_FOR_APPROVAL", "0") not in ("0", "false", "")


def mcp_scan_status() -> dict:
    missing = [key for key, value in MCP_SCAN_CONFIG.items() if not value]
    return {
        "configured": not missing,
        "missing": missing,
        "base_url": MCP_SCAN_CONFIG["MCP_SCAN_BASE_URL"],
        "model": MCP_SCAN_CONFIG["MCP_SCAN_MODEL"],
        "pinned_commit": "036c39bd03b39ce4a811f7f125bc3b8f47e39b7c",
        "required_for_approval": SCAN_REQUIRED_FOR_APPROVAL,
    }


async def scan_worker_status() -> dict:
    """감사를 실제로 돌릴 주체가 살아 있는지.

    설정이 채워져 있다는 것과 실행할 워커가 있다는 것은 다른 사실이다. 둘을
    구분하지 못하면 큐에 쌓이기만 하는 상태가 화면에서 "진행 중"으로 읽힌다.
    """
    row = await db.fetch_one(
        """SELECT worker, seen_at, detail,
                  EXTRACT(EPOCH FROM (now() - seen_at))::int AS age_seconds
           FROM worker_heartbeats WHERE role='intake' ORDER BY seen_at DESC LIMIT 1""")
    queued = await db.fetch_one(
        """SELECT count(*) FILTER (WHERE status='QUEUED') AS queued,
                  count(*) FILTER (WHERE status='RUNNING') AS running,
                  count(*) FILTER (WHERE status='RUNNING' AND lease_expires_at < now()) AS stale
           FROM scan_jobs""")
    alive = bool(row) and int(row["age_seconds"] or 0) <= WORKER_STALE_SECONDS
    return {
        "alive": alive,
        "worker": row["worker"] if row else None,
        "seen_at": row["seen_at"] if row else None,
        "age_seconds": int(row["age_seconds"]) if row else None,
        "detail": row["detail"] if row else {},
        "queued": int(queued["queued"]) if queued else 0,
        "running": int(queued["running"]) if queued else 0,
        "stale": int(queued["stale"]) if queued else 0,
        "stale_after_seconds": WORKER_STALE_SECONDS,
    }


@app.get("/api/mcp-scan")
async def mcp_scan_overview(authorization: str | None = Header(default=None)):
    """AI 코드 감사 화면의 전부: 설정과 워커 상태, 실행 가능한 대상, 작업, 결과."""
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "AI 코드 감사는 관리자만 볼 수 있습니다.")
    jobs, reports, intake_targets, server_targets, worker = await asyncio.gather(
        db.fetch_all("""SELECT j.*, r.display_name, r.repository_url AS intake_repository_url
                        FROM scan_jobs j
                        LEFT JOIN mcp_intake_requests r
                          ON j.target_kind='intake' AND r.id::text = j.target_id
                        ORDER BY j.created_at DESC LIMIT 30"""),
        db.fetch_all("""SELECT * FROM supply_chain_reports
                        WHERE scanner='AI-Infra-Guard mcp-scan' ORDER BY id DESC LIMIT 20"""),
        db.fetch_all("""SELECT r.id::text AS id, r.display_name, r.repository_url, r.commit_sha, r.status,
                               j.status AS last_status, j.finished_at AS last_finished_at,
                               j.commit_sha AS last_commit_sha
                        FROM mcp_intake_requests r
                        LEFT JOIN LATERAL (
                            SELECT status, finished_at, commit_sha FROM scan_jobs
                            WHERE target_kind='intake' AND target_id = r.id::text
                            ORDER BY created_at DESC LIMIT 1) j ON true
                        WHERE r.commit_sha IS NOT NULL
                          AND r.status IN ('VALIDATED','APPROVED','REJECTED')
                        ORDER BY r.created_at DESC LIMIT 30"""),
        # 등록된 서버도 대상이다. 이미 호출되고 있는 코드를 감사 대상에서 빼두면
        # "심사한 코드"와 "지금 도는 코드"가 갈라져도 아무도 모른다.
        db.fetch_all("""SELECT s.id, s.display_name, s.source_url, s.source_ref, s.status,
                               (s.source_url LIKE 'https://github.com/%%') AS scannable,
                               j.status AS last_status, j.finished_at AS last_finished_at
                        FROM mcp_servers s
                        LEFT JOIN LATERAL (
                            SELECT status, finished_at FROM scan_jobs
                            WHERE target_kind='server' AND target_id = s.id
                            ORDER BY created_at DESC LIMIT 1) j ON true
                        ORDER BY s.id"""),
        scan_worker_status(),
    )
    return {"config": mcp_scan_status(), "worker": worker, "jobs": jobs, "reports": reports,
            "targets": intake_targets, "servers": server_targets}


@app.post("/api/mcp-scan/connection-test")
async def mcp_scan_connection_test(authorization: str | None = Header(default=None)):
    """설정한 endpoint가 실제로 OpenAI 호환 API를 말하는지만 확인한다.

    이것은 감사가 아니다. "돌려보니 발견 0건"과 "엔드포인트가 죽어 있었다"를
    구분하지 못하면 감사 결과를 믿을 수 없어서 따로 둔다.
    """
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "관리자만 확인할 수 있습니다.")
    status = mcp_scan_status()
    if not status["configured"]:
        raise HTTPException(409, f"설정이 없습니다: {', '.join(status['missing'])}")
    url = status["base_url"].rstrip("/") + "/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(url, headers={
                "Authorization": "Bearer " + MCP_SCAN_CONFIG["MCP_SCAN_API_KEY"],
            }, json={"model": status["model"], "max_tokens": 1,
                     "messages": [{"role": "user", "content": "ping"}]})
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"endpoint에 연결하지 못했습니다: {type(exc).__name__}") from exc
    ok = response.status_code < 400
    worker = await scan_worker_status()
    return {"ok": ok, "http_status": response.status_code, "base_url": status["base_url"],
            "model": status["model"], "worker_alive": worker["alive"],
            "message": "endpoint가 응답했습니다. 이것은 연결 확인이며 보안 판단이 아닙니다."
                       if ok else response.text[:200]}


class ScanRequest(StrictModel):
    # 이전 판은 intake_id 하나만 받아 도입 요청만 감사할 수 있었다. 대상 종류를
    # 받아야 등록된 서버의 재감사가 가능해진다.
    target_kind: Literal["intake", "server"] = "intake"
    target_id: str = Field(min_length=1, max_length=200)


async def resolve_scan_target(target_kind: str, target_id: str) -> str:
    """대상이 실제로 감사 가능한지 확인하고 표시 이름을 돌려준다."""
    if target_kind == "intake":
        try:
            key = str(UUID(target_id))
        except ValueError as exc:
            raise HTTPException(422, "도입 요청 ID 형식이 아닙니다.") from exc
        row = await db.fetch_one(
            "SELECT display_name, commit_sha FROM mcp_intake_requests WHERE id=%s", (key,))
        if not row:
            raise HTTPException(404, "도입 요청을 찾을 수 없습니다.")
        if not row["commit_sha"]:
            raise HTTPException(409, "격리 검증을 먼저 통과해야 합니다. 고정된 commit이 없습니다.")
        return row["display_name"]
    row = await db.fetch_one(
        "SELECT display_name, source_url FROM mcp_servers WHERE id=%s", (target_id,))
    if not row:
        raise HTTPException(404, "등록 서버를 찾을 수 없습니다.")
    if not str(row["source_url"] or "").startswith("https://github.com/"):
        raise HTTPException(409, "원격 전용 서버라 국소 코드 감사 대상이 아닙니다. "
                                 "공급자의 증적으로 대신해야 합니다.")
    return row["display_name"]


@app.post("/api/mcp-scan/run")
async def run_mcp_scan_job(request: ScanRequest, authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "AI 코드 감사 실행은 관리자만 할 수 있습니다.")
    status = mcp_scan_status()
    if not status["configured"]:
        raise HTTPException(409, f"OpenAI 호환 endpoint 설정이 필요합니다: {', '.join(status['missing'])}")
    target_id = str(UUID(request.target_id)) if request.target_kind == "intake" else request.target_id
    label = await resolve_scan_target(request.target_kind, target_id)

    # lease가 만료된 RUNNING은 워커가 죽은 흔적이다. 여기서 먼저 회수하지 않으면
    # 관리자는 "이미 진행 중입니다"라는 409만 영원히 보게 된다.
    await db.execute(
        """UPDATE scan_jobs SET status='QUEUED', lease_expires_at=NULL,
                  error='워커 lease 만료로 관리자가 회수했습니다.'
           WHERE target_kind=%s AND target_id=%s AND status='RUNNING'
             AND (lease_expires_at IS NULL OR lease_expires_at < now())""",
        (request.target_kind, target_id))
    live = await db.fetch_one(
        """SELECT id, status, lease_expires_at FROM scan_jobs
           WHERE target_kind=%s AND target_id=%s AND status IN ('QUEUED','RUNNING')""",
        (request.target_kind, target_id))
    if live:
        raise HTTPException(409, f"이 대상의 감사가 이미 {live['status']} 상태입니다. "
                                 "취소한 뒤 다시 실행하세요.")

    worker = await scan_worker_status()
    job_id = uuid4()
    await db.execute(
        """INSERT INTO scan_jobs(id, kind, target_kind, target_id, target_label, requested_by, trigger)
           VALUES (%s,'mcp-scan',%s,%s,%s,%s,'manual')""",
        (job_id, request.target_kind, target_id, label, user["principal"]),
    )
    message = "AI 코드 감사를 큐에 넣었습니다. 고정된 commit을 다시 복제해 실행합니다."
    if not worker["alive"]:
        message += " 다만 격리 워커의 생존 신호가 없습니다. 워커가 뜨기 전에는 실행되지 않습니다."
    return {"job_id": str(job_id), "worker_alive": worker["alive"], "message": message}


@app.post("/api/mcp-scan/jobs/{job_id}/cancel")
async def cancel_mcp_scan_job(job_id: UUID, authorization: str | None = Header(default=None)):
    """잘못 건 감사를 되돌릴 방법이 재시작밖에 없으면 그건 실행 통제가 아니다."""
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "AI 코드 감사 취소는 관리자만 할 수 있습니다.")
    row = await db.fetch_one(
        """UPDATE scan_jobs
           SET cancel_requested=true,
               status = CASE WHEN status='QUEUED' THEN 'CANCELLED' ELSE status END,
               finished_at = CASE WHEN status='QUEUED' THEN now() ELSE finished_at END,
               error = COALESCE(error, '') || %s
           WHERE id=%s AND status IN ('QUEUED','RUNNING')
           RETURNING id, status""",
        (f" · {user['principal']}가 취소를 요청했습니다.", job_id))
    if not row:
        raise HTTPException(409, "대기 또는 실행 중인 작업만 취소할 수 있습니다.")
    return {"job": row, "message": "취소했습니다." if row["status"] == "CANCELLED"
            else "실행 중인 작업에 취소를 표시했습니다. 현재 회차가 끝나면 반영됩니다."}


@app.post("/api/mcp-scan/jobs/{job_id}/retry")
async def retry_mcp_scan_job(job_id: UUID, authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "AI 코드 감사 재시도는 관리자만 할 수 있습니다.")
    job = await db.fetch_one("SELECT target_kind, target_id FROM scan_jobs WHERE id=%s", (job_id,))
    if not job:
        raise HTTPException(404, "작업을 찾을 수 없습니다.")
    live = await db.fetch_one(
        """SELECT id FROM scan_jobs WHERE target_kind=%s AND target_id=%s
           AND status IN ('QUEUED','RUNNING')""", (job["target_kind"], job["target_id"]))
    if live:
        raise HTTPException(409, "이 대상의 감사가 이미 대기 또는 실행 중입니다.")
    row = await db.fetch_one(
        """UPDATE scan_jobs SET status='QUEUED', attempts=0, cancel_requested=false,
                  error=NULL, finished_at=NULL, lease_expires_at=NULL
           WHERE id=%s AND status IN ('FAILED','CANCELLED')
           RETURNING id, status""", (job_id,))
    if not row:
        raise HTTPException(409, "실패했거나 취소된 작업만 다시 돌릴 수 있습니다.")
    return {"job": row, "message": "대기열에 다시 넣었습니다."}


@app.get("/api/stream/decisions")
async def stream_decisions(after: int = 0, authorization: str | None = Header(default=None)):
    """정책 판정 실시간 흐름.

    숫자만 있는 대시보드는 "지금 무슨 일이 일어나는가"에 답하지 못한다. 역할
    범위는 여기서도 그대로다. 관리자가 아니면 자기 호출만 흘러나온다.
    """
    user = await current_identity(authorization)
    is_admin = "admin" in user["roles"]

    async def events():
        cursor = after
        if cursor <= 0:
            row = await db.fetch_one("SELECT COALESCE(max(id), 0) AS id FROM decisions")
            cursor = int(row["id"]) if row else 0
        idle = 0
        while idle < 300:  # 10분 뒤에는 브라우저가 다시 붙게 둔다
            query = """SELECT id, created_at, user_token, role, tool_name, data_class, action,
                              decision, policy_id, policy_version, exception_id, upstream_executed, trace_id
                       FROM decisions WHERE id > %s"""
            params: tuple = (cursor,)
            if not is_admin:
                query += " AND user_token = %s"
                params = (cursor, user["principal"])
            rows = await db.fetch_all(query + " ORDER BY id LIMIT 25", params)
            if rows:
                idle = 0
                cursor = max(int(row["id"]) for row in rows)
                yield "event: decisions\ndata: " + json.dumps(
                    {"rows": rows, "cursor": cursor}, ensure_ascii=False, default=str) + "\n\n"
            else:
                idle += 1
                yield ": keep-alive\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.get("/api/audit/verify")
async def verify_audit(authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "감사 체인 검증은 관리자만 할 수 있습니다.")
    return await gateway_json("/api/audit/verify", authorization)


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
