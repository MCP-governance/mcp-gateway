"""Adapted from MCP-governance/Agent-Service miso@81177a4 (login/workspace/chat)."""
from __future__ import annotations

import asyncio
import base64
import binascii
import os
import re
import secrets
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import quote, urlsplit
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from psycopg.types.json import Jsonb

from . import db
from .agent_contract import (ACCOUNT_STATUS_REASON, StrictModel, authenticate,
                             authenticated_user, issue_token, private_key)
from .connectors import router as connectors_router
from .idp import router as idp_router

STATIC_DIR = Path(__file__).parent / "agent_static"
INTAKE_REPORT_DIR = Path(os.getenv("INTAKE_REPORT_DIR", "/intake-reports"))
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://gateway:8080")

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


async def bootstrap_field_accounts() -> None:
    if os.getenv("MCP_FIELD_MODE") != "1":
        return
    # Keep the lab fixture in its own volume; old field volumes may still contain it.
    await db.execute("UPDATE principals SET status='disabled' WHERE email LIKE '%@bob.local'")
    for username, role in (("root", "admin"), ("user", "employee")):
        await db.execute(
            """INSERT INTO principals(token, user_id, email, display_name, role, password_hash)
               VALUES (%s,%s,%s,%s,%s,crypt(%s, gen_salt('bf', 12)))
               ON CONFLICT (token) DO NOTHING""",
            (username, username, username, username, role, username),
        )
    await db.execute(
        "UPDATE endpoint_agents SET status='revoked' WHERE endpoint_id = ANY(%s::text[])",
        (["ws-ysg", "ws-jwj", "ws-pse", "ws-nkk"],),
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    private_key()  # fail fast if this process is not actually the token issuer
    await db.wait_until_ready()
    await db.execute((Path(__file__).parent / "agent_tables.sql").read_text())
    await db.execute((Path(__file__).parent / "lifecycle_tables.sql").read_text())
    await db.execute((Path(__file__).parent / "v2_tables.sql").read_text())
    await bootstrap_passwords()
    await bootstrap_field_accounts()
    try:
        yield
    finally:
        await db.close()


app = FastAPI(title="MCP Governance Console · IdP", version="2.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(idp_router)
app.include_router(connectors_router)


@app.middleware("http")
async def browser_boundary(request: Request, call_next):
    origin = request.headers.get("origin")
    allowed_origins = {str(request.base_url).rstrip("/"), os.getenv("IDP_ISSUER", "").rstrip("/")}
    if request.method not in {"GET", "HEAD", "OPTIONS"} and origin and origin not in allowed_origins:
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


@app.get("/signup", include_in_schema=False)
async def signup_page():
    return FileResponse(STATIC_DIR / "signup.html")


@app.get("/workspace", include_in_schema=False)
async def workspace_page():
    return FileResponse(STATIC_DIR / "console.html")


class Login(StrictModel):
    email: str = Field(max_length=150)
    password: str = Field(max_length=150)


class Signup(StrictModel):
    username: str = Field(min_length=3, max_length=32)
    display_name: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=8, max_length=150)


@app.post("/auth/signup")
async def request_signup(request: Signup, http_request: Request):
    username = request.username.strip().lower()
    # 같은 아이디가 내부 Gitea의 사용자 이름이 된다(D-48). Gitea는 기호 연속·기호로 끝나는 이름을 받지 않는다.
    if not (3 <= len(username) <= 32 and re.fullmatch(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*", username)):
        raise HTTPException(422, "아이디는 영문자로 시작하는 영문·숫자 3~32자이고, 기호(._-)는 영문·숫자 사이에만 쓸 수 있습니다.")
    if username.endswith(GITEA_ALIAS_SUFFIX):
        raise HTTPException(422, "이 아이디는 쓸 수 없습니다.")
    caller = http_request.client.host if http_request.client else "unknown"
    key = f"signup|{caller}"
    if not login_allowed(key):
        raise HTTPException(429, "가입 신청이 너무 많습니다. 잠시 후 다시 시도하세요.")
    record_failed_login(key)
    if await db.fetch_one("SELECT 1 FROM principals WHERE lower(email)=%s", (username,)):
        raise HTTPException(409, "이미 사용 중인 아이디입니다.")
    row = await db.fetch_one(
        """INSERT INTO signup_requests(id,username,display_name,password_hash)
           VALUES (%s,%s,%s,crypt(%s, gen_salt('bf', 12)))
           ON CONFLICT (username) DO NOTHING RETURNING id""",
        (uuid4(), username, request.display_name.strip(), request.password),
    )
    if not row:
        raise HTTPException(409, "이미 접수된 아이디입니다.")
    return {"status": "pending", "message": "가입 신청을 접수했습니다. 관리자 승인 후 로그인할 수 있습니다."}


class McpIntake(StrictModel):
    display_name: str = Field(min_length=2, max_length=80)
    repository_url: str = Field(min_length=12, max_length=300)
    requested_transport: Literal["streamable-http", "stdio", "sse"]
    purpose: str = Field(min_length=10, max_length=1000)


class ExitTermsReview(StrictModel):
    provider_credential_disclosure: bool
    revocation_evidence: bool
    audit_access_retained: bool
    evidence_url: str = Field(min_length=12, max_length=500)
    note: str = Field(min_length=10, max_length=1000)


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
    caller = http_request.client.host if http_request.client else "unknown"
    row = await password_principal(request.email, request.password, caller)
    user = {"user_id": row["user_id"], "principal": row["token"], "name": row["display_name"],
            "department": row["department"] or "미지정", "roles": [row["role"]], "email": row["email"]}
    token, _claims = issue_token(user)
    response = JSONResponse({"access_token": token, "token_type": "bearer", "expires_in": 1800,
            "user": {k: v for k, v in {**user, "job_title": row["job_title"], "synthetic": os.getenv("MCP_FIELD_MODE") != "1"}.items()
                     if k != "principal"}})
    # 같은 토큰을 내부 Gitea(/git) 전용 쿠키로도 준다. Console API는 계속 Bearer만 받으므로 이 쿠키로는
    # Console을 조작할 수 없고, 스크립트도 읽지 못한다(HttpOnly).
    response.set_cookie(GIT_COOKIE, token, max_age=1800, path="/git", httponly=True, samesite="lax")
    return response


async def password_principal(email: str, password: str, caller: str) -> dict:
    """Console 로그인과 git의 Basic 인증이 함께 쓰는 비밀번호 확인과 시도 제한."""
    email = email.strip().lower()
    # Checked before the identity lookup so an unknown address is throttled too;
    # otherwise the limit itself tells an attacker which addresses exist.
    if not login_allowed(f"{caller}|{email}"):
        raise HTTPException(429, "로그인 시도가 너무 많습니다. 잠시 후 다시 시도하세요.")
    # 비밀번호 비교는 DB에서 한다. 애플리케이션으로 해시를 꺼내오면 "찾았지만 틀림"과
    # "없음"이 코드 경로로 갈라져 응답 시간이 주소 존재 여부를 알려준다.
    row = await db.fetch_one(
        """SELECT token, user_id, email, display_name, role, department, job_title, status,
                  (password_hash IS NOT NULL AND password_hash = crypt(%s, password_hash)) AS password_ok
           FROM principals WHERE lower(email)=%s""",
        (password, email))
    if not row or not row["password_ok"]:
        record_failed_login(f"{caller}|{email}")
        raise HTTPException(401, "합성 계정과 비밀번호를 확인해주세요.")
    if row["status"] != "active":
        # 실패 한도를 소진시키지 않는다. 비밀번호는 맞았고 계정 상태가 문제다.
        raise HTTPException(403, ACCOUNT_STATUS_REASON.get(row["status"], "사용할 수 없는 계정입니다."))
    return row


@app.get("/auth/me")
async def me(authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    field = os.getenv("MCP_FIELD_MODE") == "1"
    git_url = os.getenv("GITEA_PUBLIC_URL", "") if field else ""
    # The org page, not Gitea's home: the home is a personal dashboard where company repos were hard to find.
    return {**console_user(user), "synthetic": not field,
            "git_url": f"{git_url.rstrip('/')}/{GITEA_ORG}" if git_url else "", "kit": await pc_kit() if field else None}


async def pc_kit() -> dict | None:
    """직원 PC 연결 한 줄: 키트를 받고 지금 운영 중인 서버로 setup한다(field, D-42 키트 그대로)."""
    public = os.getenv("IDP_ISSUER", "").rstrip("/")
    if not (STATIC_DIR / "kit" / "mcpgw_pc.py").is_file() or not public:
        return None
    rows = await db.fetch_all(
        "SELECT id FROM mcp_servers WHERE status='READY' AND COALESCE(lifecycle,'OPERATING')='OPERATING' ORDER BY id")
    servers = ",".join(row["id"] for row in rows)
    return {"url": "/static/kit/mcpgw_pc.py", "servers": servers,
            "command": (f"curl -fsSO {public}/static/kit/mcpgw_pc.py && python3 mcpgw_pc.py setup --url {public} --servers {servers}"
                        if servers else "")}


@app.post("/auth/logout")
async def logout(authorization: str | None = Header(default=None)):
    _, claims = authenticate(authorization)
    await db.execute("INSERT INTO agent_revoked_tokens(jti,expires_at) VALUES (%s,%s) ON CONFLICT DO NOTHING", (claims["jti"], datetime.fromtimestamp(claims["exp"], UTC)))
    # Rows are only ever added here, so purging here bounds the table by the number
    # of logouts inside one token lifetime. A revoked token past its own expiry is
    # already rejected by the signature check.
    await db.execute("DELETE FROM agent_revoked_tokens WHERE expires_at < now()")
    response = JSONResponse({"status": "logged_out"})
    response.delete_cookie(GIT_COOKIE, path="/git")
    return response


# ── 내부 Gitea의 신원과 권한(D-48) ──────────────────────────────────────────────
# Caddy가 /git/* 요청마다 이 엔드포인트에 묻는다(forward_auth). 통과하면 Gitea 사용자 이름을
# X-WEBAUTH-USER로 돌려주고, Gitea는 Caddy의 고정 IP에서 온 그 헤더만 믿는다. 그래서 Gitea에
# 들어가는 길은 솔루션 로그인 하나이고, 계정을 중지하면 Gitea도 다음 요청부터 막힌다.
GIT_COOKIE = "mcpgw_git"
GITEA_ORG = os.getenv("GITEA_ORG", "mcp")
# Gitea가 자기 경로로 예약한 이름(models/user/user.go reservedUsernames). 시험 계정 `user`가 여기 걸린다.
GITEA_RESERVED = {"api", "assets", "attachments", "avatar", "avatars", "captcha", "explore", "ghost",
                  "gitea-actions", "issues", "login", "metrics", "milestones", "notifications", "org",
                  "pulls", "repo", "repo-avatars", "user"}
GITEA_ALIAS_SUFFIX = "-mcpgw"
_gitea_ready: set[str] = set()  # ponytail: 프로세스별 캐시 — 역할이 바뀌면 키가 달라져 다시 맞춘다
_gitea_lock = asyncio.Lock()


def gitea_login(email: str) -> str:
    name = email.split("@", 1)[0].lower()
    return name + GITEA_ALIAS_SUFFIX if name in GITEA_RESERVED else name


def gitea_admin_client() -> httpx.AsyncClient:
    base = os.getenv("GITEA_ADMIN_URL", "http://corp-git:3000").rstrip("/")
    return httpx.AsyncClient(base_url=base, timeout=30, trust_env=False,
                             auth=(os.getenv("GITEA_ADMIN_USER", "corpadmin"),
                                   os.getenv("GITEA_ADMIN_PASSWORD", "corp-admin-lab-only")))


GITEA_TEAM = "employees"


async def ensure_org(client: httpx.AsyncClient) -> int:
    """`mcp` 조직과, 모든 사용자가 드는 읽기 팀(모든 저장소 포함)의 id.

    구성원이 아니면 Gitea 첫 화면(개인 대시보드)에 조직 저장소가 보이지 않아 직원이 사내 저장소를
    찾지 못했다. 팀에 넣으면 대시보드·조직 화면·검색에 승인 저장소가 바로 나온다.
    """
    found = await client.get(f"/api/v1/orgs/{GITEA_ORG}")
    if found.status_code == 404:
        created = await client.post("/api/v1/orgs", json={
            "username": GITEA_ORG, "full_name": "승인된 MCP", "visibility": "limited",
            "repo_admin_change_team_access": False})
        if created.status_code != 201:
            raise HTTPException(502, f"내부 Git 조직을 만들지 못했습니다 (Gitea {created.status_code}).")
    elif not found.is_success:
        raise HTTPException(502, f"내부 Git 조직 확인 실패 (Gitea {found.status_code}).")
    teams = await client.get(f"/api/v1/orgs/{GITEA_ORG}/teams")
    if not teams.is_success:
        raise HTTPException(502, f"내부 Git 팀을 확인하지 못했습니다 (Gitea {teams.status_code}).")
    for team in teams.json():
        if team.get("name") == GITEA_TEAM:
            return team["id"]
    created = await client.post(f"/api/v1/orgs/{GITEA_ORG}/teams", json={
        "name": GITEA_TEAM, "description": "승인된 MCP 저장소 읽기·이슈(모든 직원)", "permission": "read",
        "includes_all_repositories": True, "can_create_org_repo": False,
        "units": ["repo.code", "repo.issues", "repo.releases", "repo.wiki"],
        "units_map": {"repo.code": "read", "repo.issues": "read", "repo.releases": "read", "repo.wiki": "read"}})
    if created.status_code != 201:
        raise HTTPException(502, f"내부 Git 팀을 만들지 못했습니다 (Gitea {created.status_code}).")
    return created.json()["id"]


async def ensure_gitea_user(user: dict) -> str:
    """솔루션 계정과 같은 이름의 Gitea 사용자를 만들고, 읽기 팀에 넣고, 관리자 역할이면 Gitea 관리자로 맞춘다."""
    login = gitea_login(user["email"])
    admin = "admin" in user["roles"]
    key = f"{login}|{admin}"
    if key in _gitea_ready:
        return login
    async with _gitea_lock, gitea_admin_client() as client:
        found = await client.get(f"/api/v1/users/{quote(login)}")
        if found.status_code == 404:
            created = await client.post("/api/v1/admin/users", json={
                # 비밀번호는 쓰이지 않는다(Gitea의 비밀번호 로그인 화면을 껐다). 빈 값은 Gitea가 받지 않는다.
                "username": login, "email": f"{login}@noreply.localhost", "full_name": user["name"],
                "password": secrets.token_urlsafe(32), "must_change_password": False,
                "send_notify": False, "visibility": "limited"})
            if created.status_code != 201:
                raise HTTPException(502, f"내부 Git 사용자를 만들지 못했습니다 (Gitea {created.status_code}).")
        elif not found.is_success:
            raise HTTPException(502, f"내부 Git 사용자를 확인하지 못했습니다 (Gitea {found.status_code}).")
        if (found.status_code == 404 and admin) or (found.is_success and found.json().get("is_admin") != admin):
            changed = await client.patch(f"/api/v1/admin/users/{quote(login)}", json={
                "login_name": login, "source_id": 0, "admin": admin})
            if not changed.is_success:
                raise HTTPException(502, f"내부 Git 권한을 맞추지 못했습니다 (Gitea {changed.status_code}).")
        team = await ensure_org(client)
        if (await client.get(f"/api/v1/teams/{team}/members/{quote(login)}")).status_code == 404:
            joined = await client.put(f"/api/v1/teams/{team}/members/{quote(login)}")
            if not joined.is_success:
                raise HTTPException(502, f"내부 Git 팀에 넣지 못했습니다 (Gitea {joined.status_code}).")
    _gitea_ready.add(key)
    return login


@app.get("/auth/gitea", include_in_schema=False)
async def gitea_forward_auth(request: Request):
    user = None
    if token := request.cookies.get(GIT_COOKIE):
        try:
            user = await authenticated_user(f"Bearer {token}")
        except HTTPException:
            user = None
    basic = request.headers.get("authorization", "")
    if user is None and basic[:6].lower() == "basic ":
        # git clone·push는 쿠키가 없다. 같은 솔루션 ID/PW를 Basic으로 받는다(시도 제한도 로그인과 같다).
        try:
            name, _, password = base64.b64decode(basic[6:], validate=True).decode("utf-8").partition(":")
        except (binascii.Error, UnicodeDecodeError):
            name = password = ""
        if name and password:
            caller = request.client.host if request.client else "unknown"
            try:
                row = await password_principal(name, password, caller)
                user = {"email": row["email"], "name": row["display_name"], "roles": [row["role"]]}
            except HTTPException as exc:
                if exc.status_code == 429:
                    raise
    if user is None:
        uri = request.headers.get("x-forwarded-uri", "/git/")
        if "text/html" in request.headers.get("accept", ""):
            target = uri if uri.startswith("/git/") and "//" not in uri else "/git/"
            return RedirectResponse("/login?next=" + quote(target, safe="/"), status_code=302)
        return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="MCP Gateway Git"'})
    return Response(status_code=200, headers={"X-WEBAUTH-USER": await ensure_gitea_user(user)})


class AccountStatus(StrictModel):
    status: Literal["active", "disabled", "locked"]
    note: str = Field(default="", max_length=300)


@app.get("/api/accounts")
async def list_accounts(authorization: str | None = Header(default=None)):
    """신원 관리대장. 관리자만 본다. 비밀번호 해시는 응답에 넣지 않는다."""
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "신원 관리대장은 관리자만 볼 수 있습니다.")
    field_filter = " WHERE email NOT LIKE '%@bob.local'" if os.getenv("MCP_FIELD_MODE") == "1" else ""
    return {"accounts": await db.fetch_all(
        """SELECT token, user_id, email, display_name, role, department, employee_no, job_title,
                  status, status_changed_by, status_changed_at,
                  (password_hash IS NOT NULL) AS has_password
           FROM principals""" + field_filter + " ORDER BY role, email")}


@app.get("/api/signup-requests")
async def list_signup_requests(authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "가입 신청은 관리자만 볼 수 있습니다.")
    return {"requests": await db.fetch_all(
        """SELECT id, username, display_name, status, requested_at, reviewed_at, reviewed_by
           FROM signup_requests ORDER BY requested_at DESC LIMIT 100""")}


@app.post("/api/signup-requests/{request_id}/approve")
async def approve_signup(request_id: UUID, authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "가입 승인은 관리자만 할 수 있습니다.")
    async with db.transaction() as connection:
        row = await (await connection.execute(
            "SELECT * FROM signup_requests WHERE id=%s FOR UPDATE", (request_id,))).fetchone()
        if not row or row["status"] != "pending":
            raise HTTPException(409, "대기 중인 가입 신청이 아닙니다.")
        created = await (await connection.execute(
            """INSERT INTO principals(token,user_id,email,display_name,role,password_hash)
               VALUES (%s,%s,%s,%s,'employee',%s)
               ON CONFLICT DO NOTHING RETURNING user_id""",
            (f"emp-{row['username']}", row["username"], row["username"],
             row["display_name"], row["password_hash"]),
        )).fetchone()
        if not created:
            raise HTTPException(409, "이미 등록된 아이디입니다.")
        await connection.execute(
            "UPDATE signup_requests SET status='approved', reviewed_at=now(), reviewed_by=%s WHERE id=%s",
            (user["principal"], request_id),
        )
    return {"status": "approved", "message": f"{row['username']} 계정을 승인했습니다."}


@app.post("/api/signup-requests/{request_id}/reject")
async def reject_signup(request_id: UUID, authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "가입 거부는 관리자만 할 수 있습니다.")
    row = await db.fetch_one(
        """UPDATE signup_requests SET status='rejected', reviewed_at=now(), reviewed_by=%s
           WHERE id=%s AND status='pending' RETURNING id""",
        (user["principal"], request_id),
    )
    if not row:
        raise HTTPException(409, "대기 중인 가입 신청이 아닙니다.")
    return {"status": "rejected"}


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
    label = {"active": "사용", "disabled": "중지", "locked": "잠금"}[request.status]
    return {"account": row,
            "message": f"{row['display_name'] or row['email']} 계정을 {label} 상태로 바꿨어요. 로그인 중인 기기에도 바로 적용돼요."}


@app.get("/health")
async def health():
    await db.fetch_one("SELECT 1")
    return {"status": "ok", "service": "agent-service"}


@app.get("/api/readiness")
async def ready():
    gateway_ok = False
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(GATEWAY_URL + "/api/health")
            gateway_ok = response.status_code == 200 and response.json().get("status") == "ok"
    except (httpx.HTTPError, ValueError):
        pass
    llm = None
    if os.getenv("LITELLM_URL"):
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                llm = (await client.get(os.getenv("LITELLM_URL") + "/health/liveliness")).status_code == 200
        except httpx.HTTPError:
            llm = False
    # The LLM is optional for readiness: scripted workstations and every control
    # work without it. Its state is reported, not required.
    return {"status": "ready" if gateway_ok else "not_ready", "gateway": gateway_ok,
            "identity": "synthetic-oauth2", "llm_gateway": llm}


async def gateway_proxy(path: str, authorization: str | None, method: str = "GET",
                        body: dict | None = None, timeout: float = 15) -> dict:
    """Gateway가 정본인 조작을 Console 포트에서 대신 부른다.

    상태 코드를 그대로 넘기는 것이 gateway_json과 다른 점이다. "판정하지 않은
    케이스는 종결할 수 없습니다"가 화면에서 503 '상태를 불러올 수 없습니다'로
    보이면, 운영자는 시스템 장애로 읽고 같은 버튼을 다시 누른다.
    """
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            response = await client.request(
                method, GATEWAY_URL + path,
                headers={"Authorization": authorization or "", "content-type": "application/json"},
                json=body,
            )
    except httpx.HTTPError as exc:
        raise HTTPException(503, "Gateway에 연결할 수 없습니다.") from exc
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = None
        raise HTTPException(response.status_code, detail or "Gateway가 요청을 거절했습니다.")
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError as exc:
        raise HTTPException(502, "Gateway 응답을 해석할 수 없습니다.") from exc


# 역할이 볼 수 있는 화면. 숨기기만 하는 메뉴는 통제가 아니라 장식이므로
# /api/console이 이 목록을 기준으로 데이터 자체를 빼고 응답한다.
PAGES_BY_ROLE = {
    # 직원·협력사 직원에게 필요한 것은 "내 호출이 어떻게 판정됐는가"와 "쓰고 싶은
    # MCP를 신청하는 길"이다. 조직 전체의 기록·정책·종료 판정은 관리자 몫이다.
    "partner": ("activity", "intake"),
    "employee": ("activity", "intake"),
    "admin": ("overview", "activity", "approvals", "servers", "people", "intake", "termination", "policy"),
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
                      commit_sha, source_ref, evidence, validated_at, exit_terms, internal_repo_url,
                      registered_server_id
               FROM mcp_intake_requests"""
    if "admin" in user["roles"]:
        return await db.fetch_all(query + " ORDER BY created_at DESC LIMIT 100")
    return await db.fetch_all(query + " WHERE submitted_by=%s ORDER BY created_at DESC LIMIT 100", (user["principal"],))


@app.get("/api/mcp-requests")
async def list_mcp_requests(authorization: str | None = Header(default=None)):
    """도입 신청 목록. 관리자는 전체, 그 외에는 자기 신청만 본다."""
    user = await current_identity(authorization)
    return {"requests": await intake_rows(user)}


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


def internal_repo_name(repository_url: str) -> str:
    """https://github.com/Owner/Repo -> owner-repo (Gitea 이름 규칙: 영문·숫자 사이의 기호 하나)."""
    owner, repo = urlsplit(repository_url).path.strip("/").split("/")[:2]
    return re.sub(r"[^a-z0-9]+", "-", f"{owner}-{repo}".lower()).strip("-")[:90] or "mcp"


async def repo_head(client: httpx.AsyncClient, path: str, info: dict) -> str:
    branch = info.get("default_branch")
    if not branch:
        raise HTTPException(502, "가져온 저장소에 기본 브랜치가 없습니다.")
    head = await client.get(f"{path}/branches/{quote(branch, safe='')}")
    if not head.is_success:
        raise HTTPException(502, "가져온 저장소의 커밋을 확인하지 못했습니다.")
    return head.json().get("commit", {}).get("id") or ""


async def publish_internal_repo(row: dict) -> str:
    """검증한 공개 GitHub 저장소를 이 기기의 Gitea `mcp` 조직으로 가져온다(D-48).

    조직은 limited — 로그인한 사용자만 본다. 직원은 읽기·클론·이슈, 관리자는 Gitea 관리자다.
    풀 리퀘스트는 끈다: 이 저장소는 검증한 커밋의 사본이고, 고친 코드는 도입 신청을 다시 거친다.
    """
    org = GITEA_ORG
    name = internal_repo_name(row["repository_url"])
    try:
        async with gitea_admin_client() as client:
            client.timeout = httpx.Timeout(120)
            await ensure_org(client)
            path = f"/api/v1/repos/{org}/{name}"
            existing = await client.get(path)
            if existing.is_success and await repo_head(client, path, existing.json()) != row["commit_sha"]:
                # 같은 저장소의 예전 승인본이 있다. 덮어쓰지 않고 이번 신청의 사본을 따로 둔다.
                name = f"{name}-{str(row['id'])[:8]}"
                path = f"/api/v1/repos/{org}/{name}"
                existing = await client.get(path)
            if existing.status_code == 404:
                imported = await client.post("/api/v1/repos/migrate", json={
                    "clone_addr": row["repository_url"], "repo_owner": org,
                    "repo_name": name, "service": "git", "private": True,
                    "mirror": False, "issues": False, "pull_requests": False,
                    "wiki": False, "releases": False, "lfs": False,
                })
                if imported.status_code not in (200, 201):
                    raise HTTPException(502, f"내부 저장소 가져오기 실패 (Gitea {imported.status_code}).")
                info = imported.json()
            elif existing.is_success:
                info = existing.json()
            else:
                raise HTTPException(502, f"내부 저장소 확인 실패 (Gitea {existing.status_code}).")
            if await repo_head(client, path, info) != row["commit_sha"]:
                raise HTTPException(409, "검증한 커밋과 현재 원격 저장소의 기본 브랜치가 달라졌습니다. 재검증하세요.")
            published = await client.patch(path, json={
                "private": False, "has_issues": True, "has_pull_requests": False, "has_wiki": False,
                "website": row["repository_url"],
                "description": f"{row.get('display_name') or name} · 검증 커밋 {row['commit_sha'][:12]}"})
            if not published.is_success:
                raise HTTPException(502, f"직원 읽기 권한 게시 실패 (Gitea {published.status_code}).")
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"내부 저장소에 연결하지 못했습니다: {type(exc).__name__}") from exc
    public = os.getenv("GITEA_PUBLIC_URL", "http://localhost:3000").rstrip("/")
    return f"{public}/{org}/{name}"


@app.post("/api/mcp-requests")
async def create_mcp_request(request: McpIntake, authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    try:
        repository_url = github_repository_url(request.repository_url)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    # 거부(REJECTED)는 사람의 판단이고 실패(FAILED)는 검증이 끝나지 못한 오류다.
    # 둘을 같이 막으면, 스캐너 장애 한 번이 그 저장소를 영구히 신청 불가로 만든다.
    # 실제로 워커의 semgrep이 깨져 있던 동안 들어온 요청이 전부 그렇게 됐다.
    # 실패한 시도의 행과 사유는 그대로 남으므로 증적이 사라지지는 않는다.
    existing = await db.fetch_one(
        "SELECT id, status FROM mcp_intake_requests"
        " WHERE repository_url=%s AND status NOT IN ('REJECTED', 'FAILED')",
        (repository_url,),
    )
    if existing:
        raise HTTPException(409, f"같은 저장소가 이미 {existing['status']} 상태로 등록돼 있습니다.")
    row = await db.fetch_one(
        """INSERT INTO mcp_intake_requests(
                 id, submitted_by, display_name, repository_url, requested_transport,
                 purpose, exit_terms, status
             ) VALUES (%s,%s,%s,%s,%s,%s,%s,'VALIDATION_QUEUED')
             RETURNING id, display_name, repository_url, requested_transport, purpose,
                       status, risk_level, exit_terms, created_at""",
        (uuid4(), user["principal"], request.display_name.strip(), repository_url,
         request.requested_transport, request.purpose.strip(), Jsonb({})),
    )
    message = "요청을 접수하고 자동 검증을 예약했습니다. 공급망 검사와 종료조건 조사 후 관리자가 승인합니다."
    return {"request": row, "message": message}


@app.put("/api/mcp-requests/{request_id}/exit-terms")
async def review_exit_terms(request_id: UUID, review: ExitTermsReview,
                            authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "종료 조건은 플랫폼 관리자만 검증할 수 있습니다.")
    parsed = urlsplit(review.evidence_url.strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(422, "증거는 담당자가 확인한 HTTPS 문서 주소여야 합니다.")
    terms = {**review.model_dump(), "verified_by": user["principal"],
             "verified_at": datetime.now(UTC).isoformat()}
    row = await db.fetch_one(
        """UPDATE mcp_intake_requests SET exit_terms=%s, updated_at=now()
           WHERE id=%s AND status IN ('HOLD','VALIDATION_QUEUED','VALIDATING','VALIDATED')
           RETURNING id, status, exit_terms""",
        (Jsonb(terms), request_id),
    )
    if not row:
        raise HTTPException(409, "승인 전 도입 요청만 검증 기록을 바꿀 수 있습니다.")
    return {"request": row, "message": "플랫폼 종료 조건 검증을 기록했습니다."}


@app.post("/api/mcp-requests/{request_id}/queue-validation")
async def queue_validation(request_id: UUID, authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "검증 대기열은 관리자만 변경할 수 있습니다.")
    row = await db.fetch_one(
        """UPDATE mcp_intake_requests
           SET status='VALIDATION_QUEUED', reviewed_by=%s, reviewed_at=now(), updated_at=now(),
               validation_lease_expires_at=NULL, validation_attempts=0,
               commit_sha=NULL, source_ref=NULL, evidence='{}', validated_at=NULL,
               risk_level='UNASSESSED', review_note=NULL
           WHERE id=%s AND status IN ('HOLD','FAILED','VALIDATED')
           RETURNING id, status, reviewed_by, reviewed_at""",
        (user["principal"], request_id),
    )
    if not row:
        raise HTTPException(409, "승인 전(보류·검증 실패·검증 완료) 요청만 다시 검증할 수 있습니다.")
    return {"request": row, "message": "격리 워커의 재검증 대기열에 넣었습니다."}


async def intake_report_row(request_id: UUID, authorization: str | None) -> dict:
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "상세 보안 보고서는 관리자만 볼 수 있습니다.")
    row = await db.fetch_one("SELECT * FROM mcp_intake_requests WHERE id=%s", (request_id,))
    if not row:
        raise HTTPException(404, "도입 요청을 찾지 못했습니다.")
    return row


@app.get("/api/mcp-requests/{request_id}/report")
async def intake_report(request_id: UUID, authorization: str | None = Header(default=None)):
    row = await intake_report_row(request_id, authorization)
    reports = await db.fetch_all(
        """SELECT id, scanner, scanner_version, source_ref, status, critical_count,
                  high_count, medium_count, summary, imported_at
           FROM supply_chain_reports
           WHERE source_ref=%s AND report_path LIKE %s ORDER BY id""",
        (row.get("source_ref"), f"%/intake-{request_id}-%"),
    )
    # Retried requests may have older report rows; expose only this attempt's
    # completed scanners, not previous findings as a current successful scan.
    scanner_states = (row.get("evidence") or {}).get("scanners", {})
    if scanner_states:
        reports = [r for r in reports if scanner_states.get(r["scanner"].lower(), {}).get("status") == "DONE"]
    artifacts = {"sbom": "sbom.cdx.json", "trivy": "trivy.json", "semgrep": "semgrep.json",
                 "exit-terms": "exit-terms.json"}
    available = []
    for kind, suffix in artifacts.items():
        name = f"intake-{request_id}-{suffix}"
        if name in (row.get("evidence") or {}).get("reports", []):
            available.append({"kind": kind, "filename": name,
                              "url": f"/api/mcp-requests/{request_id}/artifacts/{kind}"})
    return {"request": row, "reports": reports, "artifacts": available,
            "exit_terms_discovery": (row.get("evidence") or {}).get("exit_terms_discovery"),
            "worker": await scan_worker_status()}


@app.get("/api/mcp-requests/{request_id}/artifacts/{kind}")
async def intake_artifact(request_id: UUID, kind: str,
                          authorization: str | None = Header(default=None)):
    row = await intake_report_row(request_id, authorization)
    suffix = {"sbom": "sbom.cdx.json", "trivy": "trivy.json", "semgrep": "semgrep.json",
              "exit-terms": "exit-terms.json"}.get(kind)
    if not suffix:
        raise HTTPException(404, "지원하지 않는 보고서입니다.")
    name = f"intake-{request_id}-{suffix}"
    if name not in (row.get("evidence") or {}).get("reports", []):
        raise HTTPException(404, "이 요청의 보고서가 아직 생성되지 않았습니다.")
    root = INTAKE_REPORT_DIR.resolve()
    path = root / name
    # File names are generated from a UUID and an allowlist; never accept a path.
    if path.is_symlink() or path.resolve().parent != root or not path.is_file():
        raise HTTPException(404, "보고서 파일을 찾지 못했습니다.")
    return FileResponse(path, media_type="application/json", filename=name)


EXIT_TERM_KEYS = ("provider_credential_disclosure", "revocation_evidence", "audit_access_retained")


def manual_terms_verified(terms: dict) -> bool:
    return bool(terms.get("verified_by") and terms.get("evidence_url") and all(terms.get(k) is True for k in EXIT_TERM_KEYS))


def exit_term_flags(row: dict) -> dict[str, bool]:
    """What the Gateway registration carries: the admin's record if there is one, else the conclusion."""
    terms = row.get("exit_terms") or {}
    if terms.get("verified_by"):
        return {key: terms.get(key) is True for key in EXIT_TERM_KEYS}
    concluded = ((row.get("evidence") or {}).get("exit_terms_conclusion") or {}).get("terms") or {}
    return {key: (concluded.get(key) or {}).get("verdict") == "met" for key in EXIT_TERM_KEYS}


class IntakeApproval(StrictModel):
    risk_acceptance: str = Field(default="", max_length=1000)


@app.post("/api/mcp-requests/{request_id}/approve")
async def approve_mcp_request(request_id: UUID, approval: IntakeApproval | None = None,
                              authorization: str | None = Header(default=None)):
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
    pending = await db.fetch_one(
        """SELECT id, status, display_name, requested_transport, exit_terms, evidence, repository_url, commit_sha
           FROM mcp_intake_requests WHERE id=%s""", (request_id,))
    terms = (pending or {}).get("exit_terms") or {}
    conclusion = ((pending or {}).get("evidence") or {}).get("exit_terms_conclusion") or {}
    risk = (approval.risk_acceptance.strip() if approval else "")
    if pending and pending["requested_transport"] != "stdio" and not (
        manual_terms_verified(terms) or conclusion.get("grade") == "T1" or len(risk) >= 10
    ):
        # D-50: the platform concludes; below T1 the admin either records provider evidence or
        # accepts the risk in writing - the same rule that closes a T3 termination case.
        raise HTTPException(409, f"종료 조건 결론이 {conclusion.get('grade') or '아직 없음'}입니다. 위험을 수용하는 사유를 "
                                 "10자 이상 적거나, 제공자 증거 문서로 확인한 기록을 남겨야 승인할 수 있습니다.")
    if not pending or pending["status"] != "VALIDATED" or not pending["commit_sha"]:
        raise HTTPException(409, "격리 검증을 통과한 요청만 승인할 수 있습니다.")
    if risk and pending["requested_transport"] != "stdio" and not manual_terms_verified(terms):
        terms = {**terms, "risk_acceptance": risk, "risk_accepted_by": user["principal"],
                 "risk_accepted_at": datetime.now(UTC).isoformat(), "conclusion_grade": conclusion.get("grade")}
    internal_repo_url = await publish_internal_repo(pending)
    row = await db.fetch_one(
        """UPDATE mcp_intake_requests
           SET status='APPROVED', internal_repo_url=%s, reviewed_by=%s, reviewed_at=now(), updated_at=now(),
               exit_terms=%s
           WHERE id=%s AND status='VALIDATED'
           RETURNING id, status, internal_repo_url, reviewed_by, reviewed_at, source_ref, exit_terms""",
        (internal_repo_url, user["principal"], Jsonb(terms), request_id),
    )
    if not row:
        raise HTTPException(409, "격리 검증을 통과한 요청만 승인할 수 있습니다.")
    return {"request": row, "message": "검증한 커밋을 내부 저장소에 게시했습니다. Gateway 활성화는 별도 등록 절차입니다."}


class IntakeRegistration(StrictModel):
    server_id: str = Field(pattern=r"^[a-z][a-z0-9-]{1,30}$")
    endpoint: str = Field(min_length=8, max_length=500)
    catalog_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    tools: dict[str, Literal["r", "w", "x"]] = Field(min_length=1, max_length=300)
    data_class: Literal["public", "nonimportant", "important"]
    valid_days: int = Field(ge=1, le=365)
    poisoning_ack: bool = False


@app.post("/api/mcp-requests/{request_id}/register")
async def register_mcp_request(request_id: UUID, request: IntakeRegistration,
                               authorization: str | None = Header(default=None)):
    """승인한 신청을 Gateway에 등록한다(D-49).

    승인은 "이 코드를 들여도 된다", 등록은 "이 엔드포인트의 이 도구를 이 등급·이 기한으로 쓴다"는
    결정이다. 신청의 저장소·검증 커밋·목적·종료 조건을 그대로 실어, 등록 뒤의 A.I.G 감사와 종료
    판정이 도입 때와 같은 근거를 쓴다.
    """
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "Gateway 등록은 관리자만 할 수 있습니다.")
    row = await db.fetch_one(
        """SELECT r.*, p.department FROM mcp_intake_requests r
           LEFT JOIN principals p ON p.token = r.submitted_by WHERE r.id=%s""", (request_id,))
    if not row or row["status"] != "APPROVED":
        raise HTTPException(409, "승인된 도입 신청만 Gateway에 등록할 수 있습니다.")
    body = {**request.model_dump(), "display_name": row["display_name"], "source_url": row["repository_url"],
            "commit_sha": row["commit_sha"] or "",
            "supplier": urlsplit(row["repository_url"]).path.strip("/").split("/")[0],
            "purpose": row["purpose"], "owner_department": row.get("department") or "",
            "intake_id": str(row["id"]), "exit_terms": exit_term_flags(row)}
    result = await gateway_proxy("/api/registry/servers", authorization, "POST", body, timeout=120)
    await db.execute("UPDATE mcp_intake_requests SET registered_server_id=%s, updated_at=now() WHERE id=%s",
                     (request.server_id, request_id))
    return {**result, "message": f"Gateway에 등록했습니다 · /mcp/{request.server_id}/ · {result['valid_until'][:10]}까지 사용"}


@app.post("/api/mcp-requests/{request_id}/reject")
async def reject_mcp_request(request_id: UUID, request: IntakeRejection, authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "요청 거부는 관리자만 할 수 있습니다.")
    row = await db.fetch_one(
        """UPDATE mcp_intake_requests
           SET status='REJECTED', review_note=%s, reviewed_by=%s, reviewed_at=now(), updated_at=now()
           WHERE id=%s AND status IN ('HOLD','VALIDATION_QUEUED','VALIDATED','FAILED')
           RETURNING id, status, review_note, reviewed_by, reviewed_at""",
        (request.note.strip(), user["principal"], request_id),
    )
    if not row:
        raise HTTPException(409, "승인 전(보류·검증 대기·검증 완료·검증 실패) 요청만 거부할 수 있습니다.")
    return {"request": row}


MCP_SCAN_CONFIG = {
    "MCP_SCAN_BASE_URL": os.getenv("MCP_SCAN_BASE_URL", ""),
    "MCP_SCAN_MODEL": os.getenv("MCP_SCAN_MODEL", ""),
    "MCP_SCAN_API_KEY": os.getenv("MCP_SCAN_API_KEY", ""),
}
MCP_SCAN_EVIDENCE_MODE = os.getenv("MCP_SCAN_EVIDENCE_MODE", "live").strip().lower()
MCP_SCAN_EVIDENCE_MODES = {"live", "advisory", "test-double"}
# 워커가 lease를 갱신하는 주기보다 넉넉하게 잡는다. 이 값을 넘도록 소식이 없으면
# "큐에 넣었다"와 "누군가 실행한다"가 더는 같은 말이 아니다.
WORKER_STALE_SECONDS = int(os.getenv("INTAKE_WORKER_STALE_SECONDS", "60"))
# §11.4.1의 승인 유효기간과 같은 생각이다. 승인에 기한이 있는데 그 승인의 근거인
# 감사에 기한이 없으면, 먼저 낡는 것은 승인이 아니라 근거다.
SCAN_REQUIRED_FOR_APPROVAL = os.getenv("MCP_SCAN_REQUIRED_FOR_APPROVAL", "0") not in ("0", "false", "")
def mcp_scan_status() -> dict:
    missing = [key for key, value in MCP_SCAN_CONFIG.items() if not value]
    if MCP_SCAN_EVIDENCE_MODE not in MCP_SCAN_EVIDENCE_MODES:
        missing.append("MCP_SCAN_EVIDENCE_MODE(live|advisory|test-double)")
    return {
        "configured": not missing,
        "missing": missing,
        "base_url": MCP_SCAN_CONFIG["MCP_SCAN_BASE_URL"],
        "model": MCP_SCAN_CONFIG["MCP_SCAN_MODEL"],
        "evidence_mode": MCP_SCAN_EVIDENCE_MODE,
        "local": local_model_endpoint(),
        "pinned_commit": "036c39bd03b39ce4a811f7f125bc3b8f47e39b7c",
        "required_for_approval": SCAN_REQUIRED_FOR_APPROVAL,
        "auto_on_anomaly": (not missing and local_model_endpoint()
                            and os.getenv("MCP_SCAN_AUTO_ON_ANOMALY", "0") == "1"
                            and MCP_SCAN_EVIDENCE_MODE == "live"),
        "auto_on_validated": (not missing and os.getenv("MCP_SCAN_AUTO_ON_VALIDATED", "1") == "1"),
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
                               s.lifecycle, s.endpoint,
                               (s.source_url LIKE 'https://github.com/%%') AS scannable,
                               -- 동적 점검은 코드 출처가 아니라 지금 붙을 주소가
                               -- 있는지를 본다. 둘은 다른 조건이고, 원격 전용이라
                               -- 정적 감사를 못 하는 서버가 오히려 동적 점검의
                               -- 주 대상이다.
                               (s.endpoint LIKE 'http%%') AS probeable,
                               j.status AS last_status, j.finished_at AS last_finished_at
                        FROM mcp_servers s
                        LEFT JOIN LATERAL (
                            SELECT status, finished_at FROM scan_jobs
                            WHERE target_kind='server' AND target_id = s.id AND mode='static'
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
        async with httpx.AsyncClient(timeout=120 if local_model_endpoint() else 20,
                                     trust_env=False) as client:
            response = await client.post(url, headers={
                "Authorization": "Bearer " + MCP_SCAN_CONFIG["MCP_SCAN_API_KEY"],
            }, json={"model": status["model"], "max_tokens": 1,
                     "messages": [{"role": "user", "content": "ping"}]})
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"endpoint에 연결하지 못했습니다: {type(exc).__name__}") from exc
    try:
        body = response.json()
    except ValueError:
        body = {}
    ok = (response.status_code < 400 and isinstance(body, dict)
          and isinstance(body.get("choices"), list) and bool(body["choices"]))
    worker = await scan_worker_status()
    ready = ok and worker["alive"]
    return {"ok": ok, "ready_for_scan": ready, "http_status": response.status_code,
            "base_url": status["base_url"], "model": status["model"],
            "worker_alive": worker["alive"],
            "message": ("모델과 검사 워커가 응답했습니다. 실제 검사 결과는 작업 이력에서 확인하세요."
                        if ready else "모델은 응답했지만 검사 워커가 준비되지 않았습니다."
                        if ok else f"모델 응답을 확인하지 못했습니다 (HTTP {response.status_code}).")}


class ScanRequest(StrictModel):
    # 이전 판은 intake_id 하나만 받아 도입 요청만 감사할 수 있었다. 대상 종류를
    # 받아야 등록된 서버의 재감사가 가능해진다.
    #
    # 'endpoint'는 엔드포인트 평면이 망에서 찾아낸 미등록 MCP 리스너다. 등록되지
    # 않았으므로 Registry에 행이 없고, 그래서 이전 판에서는 A.I.G를 붙일 방법이
    # 아예 없었다 - 가장 알고 싶은 대상이 유일하게 검사할 수 없는 대상이었다.
    target_kind: Literal["intake", "server", "endpoint"] = "intake"
    target_id: str = Field(min_length=1, max_length=200)
    # 정적 감사는 코드를 복제해 읽고, 동적 점검은 실행 중인 endpoint에 붙는다.
    # 후자는 그 서버의 응답이 설정한 LLM endpoint로 나간다.
    mode: Literal["static", "dynamic"] = "static"
    # 동적 점검을 외부 모델로 돌릴 때의 확인. 기본값이 False인 것이 핵심이다.
    # "돌렸더니 코드가 나갔다"를 사후에 알게 되면 그때는 이미 나간 뒤다.
    acknowledge_external_model: bool = False


# 로컬로 볼 수 있는 모델 endpoint. core의 provider 검증과 같은 기준을 쓴다.
LOCAL_MODEL_HOSTS = {"localhost", "127.0.0.1", "::1", "host.docker.internal",
                     "model-stub", "llm-stub", "ollama"}


def local_model_endpoint() -> bool:
    host = urlsplit(MCP_SCAN_CONFIG["MCP_SCAN_BASE_URL"] or "").hostname or ""
    return host in LOCAL_MODEL_HOSTS


async def resolve_scan_target(target_kind: str, target_id: str, mode: str = "static") -> str:
    """대상이 실제로 감사 가능한지 확인하고 표시 이름을 돌려준다."""
    if target_kind == "endpoint":
        # 미등록 리스너는 코드가 없다. 주소만 있으므로 동적 점검만 가능하다.
        if mode != "dynamic":
            raise HTTPException(409, "발견된 리스너에는 동적 점검만 할 수 있습니다. 복제할 코드가 없습니다.")
        if not target_id.isdigit():
            raise HTTPException(422, "리스너 ID 형식이 아닙니다.")
        row = await db.fetch_one(
            """SELECT address, port, server_name, classification, mcp_evidence
                 FROM endpoint_listeners WHERE id=%s""", (int(target_id),))
        if not row:
            raise HTTPException(404, "관측된 리스너를 찾을 수 없습니다.")
        if row["mcp_evidence"] != "confirmed":
            # 추정 단계에서 붙으면 MCP가 아닌 서비스에 요청을 보내게 된다.
            raise HTTPException(409, "MCP로 확인된 리스너만 점검할 수 있습니다.")
        if not row["port"]:
            raise HTTPException(409, "포트가 없는 관측(stdio 프로세스)은 동적 점검 대상이 아닙니다.")
        return "%s (%s:%s)" % (row["server_name"] or "미등록 MCP", row["address"], row["port"])
    if mode == "dynamic":
        # 동적 점검은 "지금 이 주소에 있는 것"을 보는 검사다. 아직 들이지 않기로
        # 한 도입 요청에는 붙일 주소가 없고, 붙인다면 그것은 격리 원칙과 반대다.
        if target_kind != "server":
            raise HTTPException(409, "동적 점검은 등록된 서버에만 할 수 있습니다.")
        row = await db.fetch_one(
            "SELECT display_name, endpoint FROM mcp_servers WHERE id=%s", (target_id,))
        if not row:
            raise HTTPException(404, "등록 서버를 찾을 수 없습니다.")
        if not str(row["endpoint"] or "").startswith(("http://", "https://")):
            raise HTTPException(409, "HTTP endpoint가 있는 서버에만 동적 점검을 할 수 있습니다.")
        return row["display_name"]
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
    # 형식 오류는 500이 아니라 422다. resolve_scan_target이 같은 검사를 하지만
    # 여기서 정규화한 값이 아래의 조회·삽입에 그대로 쓰이므로 먼저 거른다.
    if request.target_kind == "intake":
        try:
            target_id = str(UUID(request.target_id))
        except ValueError as exc:
            raise HTTPException(422, "도입 요청 ID 형식이 아닙니다.") from exc
    else:
        target_id = request.target_id
    label = await resolve_scan_target(request.target_kind, target_id, request.mode)

    # 동적 점검은 서버가 돌려주는 내용을 모델로 보낸다. 폐기 중인 서버의 응답에
    # 잔존 데이터가 들어 있을 수 있으므로, 외부 endpoint를 쓸 때는 관리자가 그
    # 사실을 확인한 기록이 남아야 한다. 로컬 모델은 확인 없이 진행한다.
    # 미등록 리스너 점검은 조직이 모르는 서버의 응답을 모델로 보낸다. 등록 서버보다
    # 내용을 덜 알고 있는 대상이라 확인 요구를 낮출 이유가 없다.
    external_model = request.mode == "dynamic" and not local_model_endpoint()
    if external_model and not request.acknowledge_external_model:
        raise HTTPException(
            409,
            "동적 점검은 대상 서버의 응답을 설정한 모델 endpoint로 보냅니다. "
            f"지금 endpoint는 외부({MCP_SCAN_CONFIG['MCP_SCAN_BASE_URL'] or '미설정'})입니다. "
            "확인 후 다시 실행하세요.")

    # lease가 만료된 RUNNING은 워커가 죽은 흔적이다. 여기서 먼저 회수하지 않으면
    # 관리자는 "이미 진행 중입니다"라는 409만 영원히 보게 된다.
    await db.execute(
        """UPDATE scan_jobs SET status='QUEUED', lease_expires_at=NULL,
                  error='워커 lease 만료로 관리자가 회수했습니다.'
           WHERE target_kind=%s AND target_id=%s AND mode=%s AND status='RUNNING'
             AND (lease_expires_at IS NULL OR lease_expires_at < now())""",
        (request.target_kind, target_id, request.mode))
    live = await db.fetch_one(
        """SELECT id, status, lease_expires_at FROM scan_jobs
           WHERE target_kind=%s AND target_id=%s AND mode=%s
             AND status IN ('QUEUED','RUNNING')""",
        (request.target_kind, target_id, request.mode))
    if live:
        raise HTTPException(409, f"이 대상의 감사가 이미 {live['status']} 상태입니다. "
                                 "취소한 뒤 다시 실행하세요.")

    worker = await scan_worker_status()
    job_id = uuid4()
    await db.execute(
        """INSERT INTO scan_jobs(id, kind, target_kind, target_id, target_label,
                                 requested_by, trigger, mode)
           VALUES (%s,'mcp-scan',%s,%s,%s,%s,'manual',%s)""",
        (job_id, request.target_kind, target_id, label, user["principal"], request.mode),
    )
    message = ("실행 중인 endpoint에 대한 동적 점검을 큐에 넣었습니다."
               if request.mode == "dynamic"
               else "AI 코드 감사를 큐에 넣었습니다. 고정된 commit을 다시 복제해 실행합니다.")
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


class ListenerScanRequest(StrictModel):
    listener_id: int = Field(ge=1)
    acknowledge_external_model: bool = False


@app.post("/api/endpoint/listeners/{listener_id}/scan")
async def endpoint_listener_scan(listener_id: int, request: ListenerScanRequest,
                                 authorization: str | None = Header(default=None)):
    """발견된 미등록 MCP에 A.I.G 동적 점검을 건다.

    등록되지 않은 서버라 Registry 행이 없고, 그래서 이전 판에서는 가장 알고 싶은
    대상이 유일하게 검사할 수 없는 대상이었다.
    """
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "동적 점검 실행은 관리자만 할 수 있습니다.")
    return await run_mcp_scan_job(
        ScanRequest(target_kind="endpoint", target_id=str(listener_id), mode="dynamic",
                    acknowledge_external_model=request.acknowledge_external_model),
        authorization)


@app.get("/api/risk-catalog")
async def risk_catalog(authorization: str | None = Header(default=None)):
    """AI-Infra-Guard 위험 범주와 이 조직 통제의 매핑표.

    로그인한 사람이면 누구나 본다. 발견 내역이 아니라 분류 기준이고, 직원이
    "내가 신청한 서버가 어떤 기준으로 검사되는가"를 알 수 없으면 도입 요청서의
    '도입 목적'은 형식이 된다.
    """
    await current_identity(authorization)
    return await gateway_proxy("/api/risk-catalog", authorization)


@app.get("/approvals")
async def approvals(authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "합성 관리자 계정이 필요합니다.")
    pending, history = await asyncio.gather(db.fetch_all(
        """SELECT a.id, a.requested_by, a.created_at, a.expires_at,
                  a.request_payload->>'server_id' AS server_id, a.request_payload->>'tool' AS tool,
                  a.request_payload->'arguments' AS arguments, a.request_payload->'client' AS client,
                  p.display_name, p.department, d.summary, d.policy_id, d.reason, d.data_class, d.action
             FROM approvals a
             LEFT JOIN principals p ON p.token = a.requested_by
             LEFT JOIN LATERAL (SELECT summary, policy_id, reason, data_class, action FROM decisions
                                 WHERE approval_id = a.id ORDER BY id LIMIT 1) d ON true
            WHERE a.status='PENDING' AND a.expires_at>now() ORDER BY a.created_at DESC LIMIT 30"""),
        # Decided (or lapsed) requests: what the queue turned into.
        db.fetch_all(
        """SELECT a.id, a.requested_by, a.created_at, a.reviewed_at, a.reviewed_by,
                  CASE WHEN a.status='PENDING' THEN 'EXPIRED' ELSE a.status END AS status,
                  a.request_payload->>'server_id' AS server_id, a.request_payload->>'tool' AS tool,
                  p.display_name, p.department
             FROM approvals a LEFT JOIN principals p ON p.token = a.requested_by
            WHERE a.status <> 'PENDING' OR a.expires_at <= now()
            ORDER BY COALESCE(a.reviewed_at, a.expires_at) DESC LIMIT 50"""))
    return {"approvals": pending, "history": history}


class Rejection(StrictModel):
    note: str = Field(min_length=1, max_length=500)


@app.post("/approvals/{approval_id}/reject")
async def reject(approval_id: UUID, request: Rejection, authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "합성 관리자 계정이 필요합니다.")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(f"{GATEWAY_URL}/api/approvals/{approval_id}/reject",
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
        response = await client.post(f"{GATEWAY_URL}/api/approvals/{approval_id}/approve", headers={"Authorization": authorization})
    if response.status_code >= 400:
        raise HTTPException(response.status_code, "승인할 수 없습니다. 이미 처리됐거나 만료된 요청인지 확인하세요.")
    return response.json()


# ── generic Gateway API proxy for the Console ────────────────────────────────
# The Console lives on :8000 and the Gateway API on :8080; the browser's CSP allows
# only same-origin requests. The proxy forwards the caller's own bearer token, so
# every authorisation decision stays with the Gateway. Only these prefixes pass.
GATEWAY_PROXY_PREFIXES = ("overview", "activity", "registry", "health", "termination/", "approvals/",
                          "catalog/", "enforcement", "monitor/", "audit/", "policy/", "endpoint/",
                          "supply-chain/", "risk-catalog", "lab/")
# Several Gateway read APIs are open to any authenticated caller; the Console adds
# the role boundary here so an employee's session cannot read the organisation's
# registry, policy ledger or endpoint inventory through it.
EMPLOYEE_PROXY_PREFIXES = ("activity", "health")


@app.api_route("/gw/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def gateway_passthrough(path: str, request: Request, authorization: str | None = Header(default=None)):
    if not path.startswith(GATEWAY_PROXY_PREFIXES) or ".." in path:
        raise HTTPException(404, "Console이 중계하지 않는 경로입니다.")
    user = await current_identity(authorization)
    if "admin" not in user["roles"] and not path.startswith(EMPLOYEE_PROXY_PREFIXES):
        raise HTTPException(403, "관리자만 볼 수 있는 화면입니다.")
    body = await request.body()
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.request(
                request.method, f"{GATEWAY_URL}/api/{path}", params=dict(request.query_params),
                content=body or None, headers={"Authorization": authorization or "",
                                               "Content-Type": request.headers.get("content-type", "application/json")})
    except httpx.HTTPError as exc:
        raise HTTPException(503, "Gateway에 연결할 수 없습니다. 잠시 후 다시 시도하세요.") from exc
    status = response.headers.get("x-account-status")
    return Response(response.content, status_code=response.status_code,
                    media_type=response.headers.get("content-type", "application/json"),
                    headers={"X-Account-Status": status} if status else None)
