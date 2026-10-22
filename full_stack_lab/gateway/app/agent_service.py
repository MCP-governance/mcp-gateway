"""Adapted from MCP-governance/Agent-Service miso@81177a4 (login/workspace/chat)."""
from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import io
import logging
import os
import re
import secrets
import ssl
import tarfile
import tempfile
import time
import zipfile
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal
from urllib.parse import quote, urlsplit
from uuid import UUID, uuid4

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from psycopg.types.json import Jsonb

from . import artifact_provenance, connections, consent, core, db, idp, oidc, provenance, review, upstream
from . import intake_proposal, local_jobs, residency, risk_tier, sbom_impact, supplier_assurance
from .release import build_info
from .system_metrics import SystemMetrics
from .agent_contract import (ACCOUNT_STATUS_REASON, CONSOLE_SCOPE, StrictModel, ResidencyFields, ToolReview, authenticate,
                             authenticated_user, issue_token, private_key)
from .connectors import router as connectors_router
from .integrations import router as integrations_router
from .idp import router as idp_router

LOG = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "agent_static"
INTAKE_REPORT_DIR = Path(os.getenv("INTAKE_REPORT_DIR", "/intake-reports"))
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://gateway:8080")
system_metrics_sampler = SystemMetrics(GATEWAY_URL)

LOGIN_ATTEMPT_LIMIT = int(os.getenv("LOGIN_ATTEMPT_LIMIT", "10"))
LOGIN_ATTEMPT_WINDOW = int(os.getenv("LOGIN_ATTEMPT_WINDOW_SECONDS", "300"))
# Per process, like `slots` above: a deployment with replicas rate-limits at ingress.
# It still turns an unlimited password oracle into a bounded one.
_login_attempts: dict[str, list[float]] = defaultdict(list)
INTAKE_APPROVAL_LOCK = asyncio.Lock()


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
    await db.execute("UPDATE principals SET managed_required=true WHERE role<>'admin'")


@asynccontextmanager
async def lifespan(_: FastAPI):
    private_key()  # fail fast if this process is not actually the token issuer
    await db.wait_until_ready()
    await db.execute((Path(__file__).parent / "agent_tables.sql").read_text())
    await db.execute((Path(__file__).parent / "lifecycle_tables.sql").read_text())
    await db.execute((Path(__file__).parent / "v2_tables.sql").read_text())
    await db.execute((Path(__file__).parent / "oidc_tables.sql").read_text())
    await db.execute((Path(__file__).parent / "ops_tables.sql").read_text())
    await db.execute((Path(__file__).parent / "local_run_tables.sql").read_text())
    from . import litellm_sync
    await litellm_sync.initialize()
    from . import disposal
    await disposal.capture_existing()
    await disposal.reconcile()
    await bootstrap_passwords()
    await bootstrap_field_accounts()
    try:
        await review.record_solo_mode_observation()
    except Exception:  # D-188: a ledger write that fails is logged, not allowed to stop the console from starting
        LOG.exception("root solo mode setting was not recorded in approval_events")
    if os.getenv("MCP_FIELD_MODE") == "1":
        await reconcile_gitea_accounts()
    try:
        yield
    finally:
        await db.close()


app = FastAPI(title="MCP Governance Console · IdP", version="2.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(idp_router)
app.include_router(connectors_router)
app.include_router(integrations_router)
oidc.install(app)


def origin_key(value: str) -> tuple:
    """Scheme, host and port with the scheme's default port filled in: a browser sends
    https://host for the configured https://host:443 (10-18 field HTTPS)."""
    parts = urlsplit(value.strip().rstrip("/"))
    try:
        port = parts.port
    except ValueError:
        return ("", "", 0)
    return (parts.scheme, (parts.hostname or "").lower(), port or {"http": 80, "https": 443}.get(parts.scheme, 0))


@app.middleware("http")
async def browser_boundary(request: Request, call_next):
    origin = request.headers.get("origin")
    allowed_origins = {origin_key(str(request.base_url)), origin_key(os.getenv("IDP_ISSUER", ""))} - {("", "", 0)}
    if request.method not in {"GET", "HEAD", "OPTIONS"} and origin and origin_key(origin) not in allowed_origins:
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
    invitation_token: str = Field(default="", max_length=150)


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
    if request.invitation_token:
        async with db.transaction() as connection:
            invitation = await (await connection.execute(
                """UPDATE account_invitations SET consumed_at=now()
                   WHERE token_sha256=%s AND username=%s AND consumed_at IS NULL AND revoked_at IS NULL
                     AND expires_at > now() RETURNING id,department,issued_by""",
                (hashlib.sha256(request.invitation_token.encode()).hexdigest(), username))).fetchone()
            if not invitation:
                raise HTTPException(409, "초대가 만료·회수·사용되었거나 지정한 아이디와 다릅니다.")
            created = await (await connection.execute(
                """INSERT INTO principals(token,user_id,email,display_name,role,department,password_hash,managed_required)
                   VALUES (%s,%s,%s,%s,'employee',%s,crypt(%s,gen_salt('bf',12)),true)
                   ON CONFLICT DO NOTHING RETURNING user_id""",
                (f"emp-{username}", username, username, request.display_name.strip(),
                 invitation["department"], request.password))).fetchone()
            if not created:
                raise HTTPException(409, "이미 사용 중인 아이디입니다.")
            await connection.execute(
                """INSERT INTO signup_requests(id,username,display_name,password_hash,status,reviewed_at,reviewed_by)
                   SELECT %s,%s,%s,password_hash,'approved',now(),%s FROM principals WHERE user_id=%s
                   ON CONFLICT (username) DO UPDATE SET status='approved',reviewed_at=now(),reviewed_by=EXCLUDED.reviewed_by""",
                (invitation["id"], username, request.display_name.strip(), invitation["issued_by"], username))
        # A consumed one-time invitation is not the guessing this ceiling exists for, so
        # fifty colleagues behind one office address can all accept theirs.
        if _login_attempts.get(key):
            _login_attempts[key].pop()
        return {"status": "approved", "message": "등록을 완료했습니다. 로그인하세요."}
    # 거절된 아이디는 다시 신청할 수 있어야 한다. 승인·대기 중인 신청은 그대로 둔다.
    row = await db.fetch_one(
        """INSERT INTO signup_requests(id,username,display_name,password_hash)
           VALUES (%s,%s,%s,crypt(%s, gen_salt('bf', 12)))
           ON CONFLICT (username) DO UPDATE SET display_name=EXCLUDED.display_name,
               password_hash=EXCLUDED.password_hash, status='pending', requested_at=now(),
               reviewed_at=NULL, reviewed_by=NULL
           WHERE signup_requests.status='rejected' RETURNING id""",
        (uuid4(), username, request.display_name.strip(), request.password),
    )
    if not row:
        raise HTTPException(409, "이미 접수된 아이디입니다.")
    return {"status": "pending", "message": "가입 요청을 접수했습니다. 관리자 승인 후 로그인할 수 있습니다."}


class ImpactInput(StrictModel):
    data_class: Literal["public", "nonimportant", "important"]
    personal_data: Literal["none", "general", "unique_id", "sensitive"]
    external_transfer: bool
    permission: Literal["r", "w", "x"]
    users: int = Field(ge=1, le=risk_tier.MAX_USERS)
    autonomy: Literal["approve_each", "supervised", "autonomous"]


class McpIntake(StrictModel):
    display_name: str = Field(min_length=2, max_length=80)
    repository_url: str = Field(default="", max_length=300)
    intake_kind: Literal["repository", "remote-endpoint"] = "repository"
    endpoint_url: str = Field(default="", max_length=500)
    requested_transport: Literal["streamable-http", "stdio", "sse"]
    purpose: str = Field(min_length=10, max_length=1000)
    # Optional on the wire so older clients keep working; approval holds a request that has none (DEV-71).
    risk_input: ImpactInput | None = None
    data_class: Literal["public", "nonimportant", "important"] = "nonimportant"
    requested_tools: list[str] = Field(default_factory=list, max_length=300)


class ExitTermsReview(StrictModel):
    provider_credential_disclosure: bool
    revocation_evidence: bool
    audit_access_retained: bool
    evidence_url: str = Field(min_length=12, max_length=500)
    note: str = Field(min_length=10, max_length=1000)


class IntakeRejection(StrictModel):
    note: str = Field(min_length=2, max_length=500)


class RuntimeRollback(StrictModel):
    generation: int = Field(ge=1)
    note: str = Field(min_length=1, max_length=300)


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
        or not (len(pieces) == 2 or (len(pieces) >= 5 and pieces[2] == "tree"))
    ):
        raise ValueError("https://github.com/조직/저장소 형식의 URL만 제출할 수 있습니다.")
    owner, repository = pieces[:2]
    repository = repository.removesuffix(".git")
    if not owner or not repository or any(part in {".", ".."} for part in (owner, repository)):
        raise ValueError("유효한 GitHub 조직과 저장소 이름을 입력하세요.")
    return f"https://github.com/{owner}/{repository}"


def github_repository_path(value: str) -> str:
    """공식 서버 모음처럼 한 저장소에 여러 MCP가 있으면 `.../tree/<브랜치>/<경로>`로 그중 하나를 신청한다.

    복제·검사는 저장소 전체로 그대로 하고, 경로는 같은 저장소의 서로 다른 서버를 구분하는 신청 정보다.
    """
    pieces = [piece for piece in urlsplit(value.strip()).path.split("/") if piece]
    path = "/".join(pieces[4:]) if len(pieces) >= 5 and pieces[2] == "tree" else ""
    if path and not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9._-]*(?:/[A-Za-z0-9_-][A-Za-z0-9._-]*)*", path):
        raise ValueError("저장소 안 경로는 영문·숫자·._- 로 된 폴더 경로여야 합니다.")
    return path


async def current_identity(authorization: str | None) -> dict:
    return await authenticated_user(authorization, require_scope=CONSOLE_SCOPE)


async def admin_caller(authorization: str | None = Header(default=None)) -> dict:
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "관리자 계정이 필요합니다.")
    return user


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
    lifetime = 28800 if "admin" in user["roles"] else 1800
    session_expires = datetime.now(UTC) + timedelta(seconds=lifetime)
    token, claims = issue_token(user, minutes=lifetime // 60,
                                extra={"scope": CONSOLE_SCOPE, "exp": session_expires + timedelta(minutes=2)})
    await db.execute("INSERT INTO console_sessions(jti,user_id,expires_at) VALUES (%s,%s,%s)",
                     (claims["jti"], user["user_id"], session_expires))
    response = JSONResponse({"access_token": token, "token_type": "bearer", "expires_in": lifetime,
            "user": {k: v for k, v in {**user, "job_title": row["job_title"], "synthetic": os.getenv("MCP_FIELD_MODE") != "1"}.items()
                     if k != "principal"}})
    # 같은 토큰을 내부 Gitea(/git) 전용 쿠키로도 준다. Console API는 계속 Bearer만 받으므로 이 쿠키로는
    # Console을 조작할 수 없고, 스크립트도 읽지 못한다(HttpOnly).
    response.set_cookie(GIT_COOKIE, token, max_age=lifetime, path="/git", httponly=True, samesite="lax")
    return response


async def password_principal(email: str, password: str, caller: str) -> dict:
    """Console 로그인과 git의 Basic 인증이 함께 쓰는 비밀번호 확인과 시도 제한."""
    oidc.local_login_allowed()
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
        # 비밀번호까지 맞은 대기 신청만 알려 준다. 아이디 존재 여부는 드러나지 않는다.
        if not row and await db.fetch_one(
                """SELECT 1 FROM signup_requests WHERE username=%s AND status='pending'
                   AND password_hash = crypt(%s, password_hash)""", (email, password)):
            raise HTTPException(403, "관리자 승인을 기다리는 중입니다.")
        raise HTTPException(401, "아이디와 비밀번호를 확인하세요.")
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
            "managed_required": user["managed_required"],
            "managed_devices": await db.fetch_all(
                "SELECT endpoint_id,managed_state,status,heartbeat_at FROM endpoint_agents WHERE owner_token=%s AND device_epoch IS NOT NULL",
                (user["principal"],)),
            "git_url": git_url.rstrip("/") + f"/{GITEA_ORG}" if git_url else "", "kit": await pc_kit() if field else None}


KIT_FILES = {"linux": ("install.sh", "bootstrap.py", "managed-linux.py", "enforce-linux.py", "broker_binding.py", "agent.py", "os-observer.py", "offline_buffer.py", "local-runner.py"),
             "macos": ("install.sh", "install-macos.sh", "bootstrap.py", "managed-macos.py", "managed-linux.py", "agent.py", "offline_buffer.py"),
             "windows": ("install.cmd", "setup.ps1", "windows-common.ps1", "windows-worker.ps1", "windows-trust.ps1", "tray.ps1",
                         "runtime-check.py", "windows_status.py", "install.py", "install-windows.ps1",
                          "managed-windows.py", "agent.py", "os-observer-windows.py", "offline_buffer.py")}
# The employee runs one file and answers one elevation prompt; the installer does the rest (D-71).
KIT_EXECUTABLE = {"install.sh", "install-macos.sh"}


def field_ca() -> dict:
    path = os.getenv("FIELD_CA_FILE", "")
    if not path:
        if os.getenv("MCP_FIELD_MODE") == "1":
            raise HTTPException(503, "게이트웨이 루트 인증서가 없습니다.")
        return {}
    try:
        certificate = Path(path).read_text(encoding="utf-8")
        blocks = re.findall(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", certificate, re.S)
        if len(blocks) != 1 or certificate.strip() != blocks[0]:
            raise ValueError("single root required")
        ssl.create_default_context().load_verify_locations(cadata=certificate)
        fingerprint = hashlib.sha256(ssl.PEM_cert_to_DER_cert(certificate.strip())).hexdigest()
    except (OSError, ValueError):
        raise HTTPException(503, "게이트웨이 루트 인증서를 확인할 수 없습니다.") from None
    return {"ca_certificate": certificate, "ca_sha256": fingerprint}


async def pc_kit() -> dict | None:
    """개인별 1회용 enrollment 키트. MCP 서버가 없어도 단말 등록은 가능하다."""
    public = os.getenv("IDP_ISSUER", "").rstrip("/")
    if not (Path(os.getenv("ENDPOINT_KIT_DIR", "/endpoint-kit")) / "bootstrap.py").is_file() or not public:
        return None
    rows = await db.fetch_all(
        "SELECT id FROM mcp_servers WHERE status IN ('READY','DRIFT') AND COALESCE(lifecycle,'OPERATING')='OPERATING' ORDER BY id")
    servers = ",".join(row["id"] for row in rows)
    return {"url": "/api/pc-kit", "servers": servers, "platforms": sorted(KIT_FILES)}


@app.post("/api/pc-kit")
async def download_managed_kit(platform: Literal["linux", "windows", "macos"] = "linux",
                               delivery: Literal["zip", "command"] = "zip",
                               authorization: str | None = Header(default=None),
                               packaging: Literal["zip", "oneclick"] = "zip"):
    from .endpoint_plane import enrollment_token
    download_prefix = "Bearer kit-download."
    if authorization and authorization.startswith(download_prefix):
        if platform != "macos" or delivery != "zip":
            raise HTTPException(403, "다운로드 범위가 다릅니다.")
        ticket = authorization[len(download_prefix):]
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", ticket):
            raise HTTPException(401, "다운로드 자격이 올바르지 않습니다.")
        grant = await db.fetch_one(
            """UPDATE endpoint_enrollment_tokens SET consumed_at=now()
               WHERE token_hash=%s AND consumed_at IS NULL AND expires_at>now()
                 AND EXISTS (SELECT 1 FROM principals p WHERE p.token=owner_token AND p.status='active')
               RETURNING owner_token""", (hashlib.sha256(("kit-download:" + ticket).encode()).hexdigest(),))
        if not grant:
            raise HTTPException(401, "다운로드 자격이 만료·사용됐습니다.")
        owner = await db.fetch_one("SELECT user_id,token FROM principals WHERE token=%s AND status='active'", (grant["owner_token"],))
        if not owner:
            raise HTTPException(403, "사용할 수 없는 계정입니다.")
        user = {"user_id": owner["user_id"], "principal": owner["token"]}
    else:
        user = await current_identity(authorization)
    source = Path(os.getenv("ENDPOINT_KIT_DIR", "/endpoint-kit"))
    if packaging == "oneclick" and (platform != "windows" or not (source / "windows-oneclick.ps1.in").is_file()):
        raise HTTPException(503, "설치 파일이 배포되지 않았습니다.")
    names = KIT_FILES[platform]
    if any(not (source / name).is_file() for name in names):
        raise HTTPException(503, "관리형 설치 키트가 배포되지 않았습니다.")
    runtime = Path(os.getenv("WINDOWS_PYTHON_DIR", "/opt/windows-python"))
    if platform == "windows" and any(not (runtime / name).is_file() for name in ("python.zip", "windows-python.json")):
        raise HTTPException(503, "Windows 실행 파일이 배포되지 않았습니다.")
    public = os.getenv("IDP_ISSUER", "").rstrip("/")
    if not public:
        raise HTTPException(503, "Gateway 공개 주소가 없습니다.")
    if os.getenv("MCP_FIELD_MODE") == "1" and urlsplit(public).scheme != "https":
        raise HTTPException(503, "게이트웨이 HTTPS 공개 주소가 필요합니다.")
    if public.startswith("http://") and urlsplit(public).hostname not in {"127.0.0.1", "localhost", "::1"} and not os.getenv("ENDPOINT_TAILSCALE_NODE_ID"):
        raise HTTPException(503, "Gateway Tailscale 노드 ID를 운영자가 먼저 고정해야 합니다.")
    import json
    ca = field_ca()
    if delivery == "command":
        if platform != "macos":
            raise HTTPException(400, "지원하지 않는 설치 방식입니다.")
        from .kit_commands import macos_bootstrap
        ticket = secrets.token_urlsafe(32)
        try:
            script = macos_bootstrap(public, ticket, ca.get("ca_certificate", ""))
        except ValueError as exc:
            raise HTTPException(503, str(exc)) from None
        await db.execute(
            "INSERT INTO endpoint_enrollment_tokens(token_hash,owner_token,expires_at) VALUES (%s,%s,%s)",
            (hashlib.sha256(("kit-download:" + ticket).encode()).hexdigest(), user["principal"],
             datetime.now(UTC) + timedelta(minutes=5)))
        return Response(script, media_type="application/octet-stream",
                        headers={"Content-Disposition": 'attachment; filename="mcp-connect-macos.command"', "Cache-Control": "no-store"})
    if packaging == "oneclick" and (not ca or urlsplit(public).scheme != "https"):
        raise HTTPException(503, "게이트웨이 HTTPS 인증서가 필요합니다.")
    bundle = {"gateway_url": public, "tailscale_node_id": os.getenv("ENDPOINT_TAILSCALE_NODE_ID", ""), **ca,
              "owner": user["user_id"], **await enrollment_token(user["principal"])}
    if platform == 'linux' and os.getenv('LOCAL_MANIFEST_PUBKEY'):
        bundle['manifest_pubkey']=os.environ['LOCAL_MANIFEST_PUBKEY'].replace('\\n','\n')
        bundle['local_engine']=json.loads(os.getenv('LOCAL_ENGINE_SETTINGS') or '{}')
        # 엔진·판본은 PC마다 다르므로 실행기가 그 PC에서 측정한다. 기기는 허용 저장소만 정한다.
        bundle['local_engine'].setdefault('mirrors',[m.strip() for m in os.getenv('LOCAL_IMAGE_MIRRORS','').split(',') if m.strip()])
        bundle['local_engine'].setdefault('accepted_risk','탈출 시 호스트 root')
    output = io.BytesIO()
    payload = {name: (source / name).read_bytes() for name in names}
    if ca:
        payload.update({"root.crt": ca["ca_certificate"].encode(), "root.sha256": (ca["ca_sha256"] + "\n").encode(),
                        "mcpgw_pc.py": (STATIC_DIR / "kit" / "mcpgw_pc.py").read_bytes()})
    if platform == "windows":
        payload.update({name: (runtime / name).read_bytes() for name in ("python.zip", "windows-python.json")})
        manifest = json.dumps({"schema": 1, "gateway_url": public,
                               "tailscale_node_id": os.getenv("ENDPOINT_TAILSCALE_NODE_ID", ""),
                               "files": {name: hashlib.sha256(value).hexdigest() for name, value in payload.items()}},
                              sort_keys=True, separators=(",", ":")).encode()
        payload["windows-kit-manifest.json"] = manifest
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("enrollment.json", json.dumps(bundle))
        for name, value in payload.items():
            entry = zipfile.ZipInfo(name)
            # unzip applies the stored mode: the entry point has to come out runnable.
            entry.external_attr = (0o755 if name in KIT_EXECUTABLE else 0o644) << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, value)
    if packaging == "oneclick":
        from .windows_oneclick import launcher
        return Response(launcher(output.getvalue(), (source / "windows-oneclick.ps1.in").read_text(encoding="utf-8")),
                        media_type="application/octet-stream",
                        headers={"Content-Disposition": 'attachment; filename="mcp-managed-setup-windows.cmd"',
                                 "Cache-Control": "no-store"})
    return Response(output.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="mcp-managed-kit-{platform}.zip"',
                             "Cache-Control": "no-store",
                             **({"X-Windows-Kit-Manifest-SHA256": hashlib.sha256(manifest).hexdigest()}
                                if platform == "windows" else {})})


@app.post("/auth/logout")
async def logout(authorization: str | None = Header(default=None)):
    _, claims = authenticate(authorization)
    from . import disposal
    disposal.remember_token(claims["jti"], datetime.fromtimestamp(claims["exp"], UTC))
    await db.execute("INSERT INTO agent_revoked_tokens(jti,expires_at) VALUES (%s,%s) ON CONFLICT DO NOTHING", (claims["jti"], datetime.fromtimestamp(claims["exp"], UTC)))
    await oidc.end_session(claims)
    # Rows are only ever added here, so purging here bounds the table by the number
    # of logouts inside one token lifetime. A revoked token past its own expiry is
    # already rejected by the signature check.
    await db.execute("DELETE FROM agent_revoked_tokens WHERE expires_at < now()")
    response = JSONResponse({"status": "logged_out"})
    response.delete_cookie(GIT_COOKIE, path="/git")
    return response


@app.post("/auth/session/activity")
async def session_activity(authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    await oidc.touch_session(user["claims"])
    return {"status": "active"}


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


async def ensure_gitea_team(client: httpx.AsyncClient) -> int:
    found = await client.get(f"/api/v1/orgs/{GITEA_ORG}")
    if found.status_code == 404:
        created = await client.post("/api/v1/orgs", json={
            "username": GITEA_ORG, "full_name": "승인된 MCP", "visibility": "limited",
            "repo_admin_change_team_access": False})
        if created.status_code != 201:
            raise HTTPException(502, f"내부 Git 조직을 만들지 못했습니다 (Gitea {created.status_code}).")
    elif not found.is_success:
        raise HTTPException(502, f"내부 Git 조직 확인 실패 (Gitea {found.status_code}).")
    teams = await client.get(f"/api/v1/orgs/{GITEA_ORG}/teams", params={"limit": 50})
    if not teams.is_success:
        raise HTTPException(502, f"내부 Git 조직 팀 확인 실패 (Gitea {teams.status_code}).")
    members = next((team for team in teams.json() if team["name"] == "Members"), None)
    if members is None:
        created = await client.post(f"/api/v1/orgs/{GITEA_ORG}/teams", json={
            "name": "Members", "description": "솔루션 조직원 읽기 권한",
            "permission": "read", "units": ["repo.code"], "includes_all_repositories": True})
        if created.status_code != 201:
            raise HTTPException(502, f"내부 Git 조직 팀을 만들지 못했습니다 (Gitea {created.status_code}).")
        members = created.json()
    return members["id"]


async def ensure_gitea_user(user: dict) -> str:
    """솔루션 계정을 Gitea 조직의 전체 저장소 읽기 팀에 동기화한다."""
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
        if found.status_code == 404 or found.json().get("is_admin") != admin:
            changed = await client.patch(f"/api/v1/admin/users/{quote(login)}", json={
                "login_name": login, "source_id": 0, "admin": admin})
            if not changed.is_success:
                raise HTTPException(502, f"내부 Git 권한을 맞추지 못했습니다 (Gitea {changed.status_code}).")
        team_id = await ensure_gitea_team(client)
        joined = await client.put(f"/api/v1/teams/{team_id}/members/{quote(login)}")
        if not joined.is_success:
            raise HTTPException(502, f"내부 Git 조직 가입 실패 (Gitea {joined.status_code}).")
    _gitea_ready.add(key)
    return login


async def reconcile_gitea_accounts() -> None:
    rows = await db.fetch_all("""SELECT email, display_name, role, status FROM principals
                                 WHERE email IS NOT NULL AND email NOT LIKE '%@bob.local'""")
    for row in rows:
        login = gitea_login(row["email"])
        if row["status"] == "deleted":
            async with gitea_admin_client() as client:
                removed = await client.delete(f"/api/v1/orgs/{GITEA_ORG}/members/{quote(login)}")
                if removed.status_code not in (204, 404):
                    raise HTTPException(502, f"내부 Git 조직 탈퇴 실패 (Gitea {removed.status_code}).")
        else:
            await ensure_gitea_user({"email": row["email"], "name": row["display_name"], "roles": [row["role"]]})


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


class AccountInvitations(StrictModel):
    usernames: list[str] = Field(min_length=1, max_length=50)
    department: str = Field(min_length=2, max_length=80)


@app.post("/api/account-invitations", status_code=201)
async def invite_accounts(request: AccountInvitations, http_request: Request,
                          authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "조직 초대는 관리자만 만들 수 있습니다.")
    names = [name.strip().lower() for name in request.usernames]
    if len(set(names)) != len(names) or any(
        not re.fullmatch(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*", name)
        or not 3 <= len(name) <= 32 or name.endswith(GITEA_ALIAS_SUFFIX) for name in names
    ):
        raise HTTPException(422, "중복 없이 유효한 일반 사용자 아이디 1~50개를 지정하세요.")
    issued = []
    expires = datetime.now(UTC) + timedelta(hours=48)
    async with db.transaction() as connection:
        for name in sorted(names):
            await connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("invite|" + name,))
            if await (await connection.execute("SELECT 1 FROM principals WHERE lower(email)=%s", (name,))).fetchone():
                raise HTTPException(409, f"이미 등록된 아이디입니다: {name}")
            await connection.execute("UPDATE account_invitations SET revoked_at=now() WHERE username=%s AND consumed_at IS NULL AND revoked_at IS NULL", (name,))
            secret = secrets.token_urlsafe(32)
            await connection.execute(
                "INSERT INTO account_invitations(id,username,department,token_sha256,issued_by,expires_at) VALUES (%s,%s,%s,%s,%s,%s)",
                (uuid4(), name, request.department.strip(), hashlib.sha256(secret.encode()).hexdigest(), user["principal"], expires))
            issued.append({"username": name, "url": f"{str(http_request.base_url).rstrip('/')}/signup#invite={secret}&username={quote(name)}", "expires_at": expires})
    return {"invitations": issued, "message": "초대 링크를 만들었습니다."}


@app.get("/api/account-invitations")
async def list_invitations(authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "조직 초대는 관리자만 볼 수 있습니다.")
    return {"invitations": await db.fetch_all("SELECT id,username,department,issued_by,issued_at,expires_at,consumed_at,revoked_at FROM account_invitations ORDER BY issued_at DESC LIMIT 100")}


@app.delete("/api/account-invitations/{invitation_id}")
async def revoke_invitation(invitation_id: UUID, authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "조직 초대 회수는 관리자만 할 수 있습니다.")
    row = await db.fetch_one("UPDATE account_invitations SET revoked_at=now() WHERE id=%s AND consumed_at IS NULL RETURNING id", (invitation_id,))
    if not row:
        raise HTTPException(409, "이미 사용했거나 없는 초대입니다.")
    return {"status": "revoked"}


@app.get("/api/accounts")
async def list_accounts(authorization: str | None = Header(default=None)):
    """신원 관리대장. 관리자만 본다. 비밀번호 해시는 응답에 넣지 않는다."""
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "신원 관리대장은 관리자만 볼 수 있습니다.")
    field_filter = " AND email NOT LIKE '%@bob.local'" if os.getenv("MCP_FIELD_MODE") == "1" else ""
    return {"accounts": await db.fetch_all(
        """SELECT token, user_id, email, display_name, role, department, employee_no, job_title,
                  status, status_changed_by, status_changed_at,
                  (password_hash IS NOT NULL) AS has_password
           FROM principals WHERE status <> 'deleted'""" + field_filter + " ORDER BY role, email")}


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
            """INSERT INTO principals(token,user_id,email,display_name,role,password_hash,managed_required)
               VALUES (%s,%s,%s,%s,'employee',%s,true)
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
    if os.getenv("MCP_FIELD_MODE") == "1":
        await ensure_gitea_user({"email": row["username"], "name": row["display_name"], "roles": ["employee"]})
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
    from . import local_jobs
    target = await db.fetch_one('SELECT token FROM principals WHERE user_id=%s',(user_id,))
    if target and request.status!='active':
        await local_jobs.quiesce(user_token=target['token'])
    row = await db.fetch_one(
        """UPDATE principals SET status=%s, status_changed_by=%s, status_changed_at=now()
           WHERE user_id=%s AND status <> 'deleted'
           RETURNING token, user_id, email, display_name, role, status, status_changed_by, status_changed_at""",
        (request.status, user["principal"], user_id))
    if not row:
        raise HTTPException(404, "관리대장에 없는 계정입니다.")
    if request.status != "active":
        await upstream.release_pool(None, row["token"], "principal")
        await idp.revoke_principal_tokens(row["user_id"])
        await db.execute("DELETE FROM console_sessions WHERE user_id=%s", (row["user_id"],))
        bindings = await db.fetch_all("SELECT id FROM oidc_bindings WHERE principal=%s", (row["token"],))
        for binding in bindings:
            await oidc.end_binding_sessions(binding["id"])
        # Last: the account status already refuses every token, so a failure here must not
        # leave the revocations above undone.
        from . import mcp_sessions
        await mcp_sessions.terminate(reason="principal-disabled", principal=row["token"])
    label = {"active": "사용", "disabled": "중지", "locked": "잠금"}[request.status]
    if request.status=='active':
        await local_jobs.resume(user_token=row['token'])
    return {"account": row,
            "message": f"{row['display_name'] or row['email']} 계정을 {label} 상태로 변경했습니다."}


@app.delete("/api/accounts/{user_id}")
async def delete_account(user_id: str, authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "계정 삭제는 관리자만 할 수 있습니다.")
    if user_id in (user["user_id"], "root"):
        raise HTTPException(409, "본인 또는 root 계정은 삭제할 수 없습니다.")
    from . import local_jobs
    target=await db.fetch_one('SELECT token FROM principals WHERE user_id=%s',(user_id,))
    if target:
        await local_jobs.quiesce(user_token=target['token'])
    row = await db.fetch_one(
        """UPDATE principals SET status='deleted', status_changed_by=%s, status_changed_at=now()
           WHERE user_id=%s AND status <> 'deleted' RETURNING email, token""",
        (user["principal"], user_id))
    if row:
        await upstream.release_pool(None, row["token"], "principal")
        await idp.revoke_principal_tokens(user_id)
        await db.execute("DELETE FROM console_sessions WHERE user_id=%s", (user_id,))
        bindings = await db.fetch_all("SELECT id FROM oidc_bindings WHERE principal=%s", (row["token"],))
        for binding in bindings:
            await oidc.end_binding_sessions(binding["id"])
        from . import mcp_sessions
        await mcp_sessions.terminate(reason="principal-deleted", principal=row["token"])
    if not row:
        row = await db.fetch_one("SELECT email FROM principals WHERE user_id=%s AND status='deleted'", (user_id,))
        if not row:
            raise HTTPException(404, "관리대장에 없는 계정입니다.")
    if os.getenv("MCP_FIELD_MODE") == "1":
        login = gitea_login(row["email"])
        try:
            async with gitea_admin_client() as client:
                removed = await client.delete(f"/api/v1/orgs/{GITEA_ORG}/members/{quote(login)}")
                if removed.status_code not in (204, 404):
                    raise HTTPException(502, f"계정은 삭제됐지만 내부 Git 조직 탈퇴에 실패했습니다 (Gitea {removed.status_code}).")
        except httpx.HTTPError as exc:
            raise HTTPException(502, "계정은 삭제됐지만 내부 Git에 연결하지 못했습니다. 삭제를 다시 시도하세요.") from exc
        _gitea_ready.difference_update({f"{login}|True", f"{login}|False"})
    return {"message": f"{row['email']} 계정을 삭제했습니다."}


@app.get("/health")
async def health():
    await db.fetch_one("SELECT 1")
    return {"status": "ok", "service": "agent-service", "build": build_info()}


@app.get("/api/system/metrics")
async def system_metrics(authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "관리자만 볼 수 있는 화면입니다.")
    return await system_metrics_sampler.sample()


@app.get("/api/readiness")
async def ready():
    gateway_ok = False
    gateway = {}
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(GATEWAY_URL + "/api/health")
            gateway = response.json()
            gateway_ok = response.status_code == 200 and gateway.get("status") == "ok"
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
    gateway_build, console_build = gateway.get("build") or {}, build_info()
    consistent = (gateway_build.get("code_sha256") == console_build["code_sha256"]
                  and gateway_build.get("revision") == console_build["revision"])
    return {"status": "ready" if gateway_ok and consistent else "not_ready", "gateway": gateway_ok,
            "build": {"console": build_info(), "gateway": gateway.get("build"), "consistent": consistent},
            "policy": gateway.get("policy"),
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
    "partner": ("activity", "consent", "intake"),
    "employee": ("activity", "consent", "intake"),
    "admin": ("overview", "activity", "audit", "approvals", "coverage", "servers", "people", "consent", "intake", "sbom-impact",
              "termination", "policy"),
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
    await review.lapse_expired_acceptances()
    query = """SELECT r.id, r.submitted_by, r.display_name, r.repository_url, r.repository_path, r.requested_transport, r.purpose,
                      r.status, r.risk_level, r.review_note, r.reviewed_by, r.reviewed_at, r.created_at, r.updated_at,
                      r.commit_sha, r.source_ref, r.evidence, r.validated_at, r.exit_terms, r.internal_repo_url,
                      r.registered_server_id, r.intake_kind, r.endpoint_url, r.provenance, r.risk_input, r.requested_tools,
                      (r.submitted_by = %s OR p.user_id = %s) AS own, rt.runtime, s.endpoint AS registered_endpoint
               FROM mcp_intake_requests r LEFT JOIN principals p ON p.token = r.submitted_by
               LEFT JOIN mcp_servers s ON s.id = r.registered_server_id
               LEFT JOIN LATERAL (SELECT jsonb_build_object('id', id, 'status', status, 'endpoint', endpoint,
                                         'error', error, 'generation', generation) AS runtime
                                  FROM mcp_runtimes WHERE intake_id = r.id ORDER BY generation DESC LIMIT 1) rt ON true"""
    me = (user["principal"], user.get("user_id"))
    if "admin" in user["roles"]:
        rows = await db.fetch_all(query + " ORDER BY r.created_at DESC LIMIT 100", me)
        for row in rows:
            row["runtime_recipe"] = bool(row["intake_kind"] == "repository" and runtime_recipe(row["repository_url"]))
        return await with_risk(rows, counted=True)
    return await with_risk(await db.fetch_all(query + " WHERE r.submitted_by=%s ORDER BY r.created_at DESC LIMIT 100",
                                              (*me, user["principal"])))


async def with_risk(rows: list[dict], counted: bool = False) -> list[dict]:
    """Each request carries its tier and, for administrators, how many different people already
    recorded their approval of this same input."""
    firsts: dict[str, set[tuple[str, str]]] = {}
    if counted and rows:
        for event in await db.fetch_all(
                """SELECT target_id, actor, scope->>'input_sha256' AS digest FROM approval_events
                    WHERE kind='intake-cosign' AND target_kind='intake' AND target_id = ANY(%s::text[])""",
                ([str(row["id"]) for row in rows],)):
            firsts.setdefault(event["target_id"], set()).add((event["actor"], event["digest"]))
    for row in rows:
        stated = risk_tier.assess(row.get("risk_input"))
        suggested = (row.get("evidence") or {}).get("approval_proposal") or {}
        if stated["status"] != "ok" and suggested.get("blockers") == [] and suggested.get("tools"):
            # 근거 입력도 제안도 없으면 등급을 매기지 않고 보류로 둔다. 산정하지 않은 값을 결과처럼 적지 않는다.
            stated = suggested.get("risk") or stated
        rule = risk_tier.APPROVAL.get(stated["tier"])
        pending = (row.get("evidence") or {}).get("one_click_pending")
        row["risk"] = {"status": stated["status"], "tier": stated["tier"], "score": stated["score"],
                       "missing": stated["missing"], "required": rule and rule["approvers"], "reason": rule and rule["reason"],
                       "approvals": len(pending["approvers"]) if pending else len({actor for actor, digest in firsts.get(str(row["id"]), ())
                                         if digest == stated.get("input_sha256")})}
    return rows


@app.get("/api/mcp-requests")
async def list_mcp_requests(authorization: str | None = Header(default=None)):
    """도입 신청 목록. 관리자는 전체, 그 외에는 자기 신청만 본다."""
    user = await current_identity(authorization)
    return {"requests": await intake_rows(user)}


@app.get("/api/mcp-catalog/search")
async def search_catalog(q: str = "", authorization: str | None = Header(default=None)):
    """신청 전에 기존 요청의 신청자·상태·승인된 내부 저장소를 조회한다."""
    await current_identity(authorization)
    term = q.strip()
    like = f"%{term}%"
    request_query = """SELECT r.display_name, r.repository_url, r.repository_path, r.endpoint_url, r.intake_kind, r.requested_transport, r.status, r.risk_level,
                              r.commit_sha, r.source_ref, r.validated_at, r.reviewed_at, r.created_at,
                              r.internal_repo_url, COALESCE(p.display_name, r.submitted_by) AS submitted_by_name
                       FROM mcp_intake_requests r LEFT JOIN principals p ON p.token=r.submitted_by"""
    server_query = """SELECT id, display_name, transport, source_url, source_ref, supplier,
                             status, status_reason
                      FROM mcp_servers"""
    if term:
        requests = await db.fetch_all(
            request_query + " WHERE r.repository_url ILIKE %s OR r.display_name ILIKE %s OR r.endpoint_url ILIKE %s"
            " ORDER BY r.created_at DESC LIMIT 50", (like, like, like))
        servers = await db.fetch_all(
            server_query + " WHERE source_url ILIKE %s OR display_name ILIKE %s OR id ILIKE %s"
            " ORDER BY id LIMIT 50", (like, like, like))
    else:
        requests = await db.fetch_all(request_query + " ORDER BY r.created_at DESC LIMIT 50")
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


async def internal_archive_digest(client: httpx.AsyncClient, path: str, commit: str) -> dict:
    """Digest of the commit as the internal repository would hand it to an employee (D-90)."""
    spool = tempfile.SpooledTemporaryFile(max_size=32 << 20)
    try:
        async with client.stream("GET", f"{path}/archive/{commit}.tar.gz") as response:
            if not response.is_success:
                raise HTTPException(502, f"내부 저장소 보관본을 받지 못했습니다 (Gitea {response.status_code}).")
            total = 0
            async for block in response.aiter_bytes():
                total += len(block)
                if total > provenance.MAX_ARCHIVE_BYTES:
                    raise ProvenanceMismatch("내부 저장소 보관본이 크기 상한을 넘었습니다.")
                spool.write(block)
        spool.seek(0)
        return await asyncio.to_thread(provenance.archive_digest, spool)
    except (tarfile.TarError, EOFError, ValueError) as exc:
        raise ProvenanceMismatch(f"내부 저장소 보관본을 읽지 못했습니다: {exc}") from exc
    finally:
        spool.close()


async def publish_internal_repo(row: dict) -> tuple[str, dict]:
    """검증한 공개 GitHub 저장소를 이 기기의 Gitea `mcp` 조직으로 가져온다(D-48).

    조직은 limited — 로그인한 사용자만 본다. 직원은 읽기·클론·이슈, 관리자는 Gitea 관리자다.
    풀 리퀘스트는 끈다: 이 저장소는 검증한 커밋의 사본이고, 고친 코드는 도입 신청을 다시 거친다.
    직원에게 보이기 전에, 이 사본의 파일 해시가 검증 때 기록한 것과 같은지 대조한다(D-90).
    """
    org = GITEA_ORG
    name = internal_repo_name(row["repository_url"])
    try:
        async with gitea_admin_client() as client:
            client.timeout = httpx.Timeout(120)
            await ensure_gitea_team(client)
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
            recorded = ((row.get("provenance") or {}).get("artifact") or {}).get("sha256")
            actual = await internal_archive_digest(client, path, row["commit_sha"])
            if actual["sha256"] != recorded:
                raise ProvenanceMismatch(f"기록한 해시 {str(recorded)[:12]} · 사본 해시 {actual['sha256'][:12]}")
            checked = {"match": True, "source": "internal-repo-archive", "sha256": actual["sha256"],
                       "files": actual["files"], "bytes": actual["bytes"]}
            published = await client.patch(path, json={
                "private": False, "has_issues": True, "has_pull_requests": False, "has_wiki": False,
                "website": row["repository_url"],
                "description": f"{row.get('display_name') or name} · 검증 커밋 {row['commit_sha'][:12]}"})
            if not published.is_success:
                raise HTTPException(502, f"직원 읽기 권한 게시 실패 (Gitea {published.status_code}).")
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"내부 저장소에 연결하지 못했습니다: {type(exc).__name__}") from exc
    public = os.getenv("GITEA_PUBLIC_URL", "http://localhost:3000").rstrip("/")
    return f"{public}/{org}/{name}", checked


@app.post("/api/mcp-requests")
async def create_mcp_request(request: McpIntake, authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    try:
        repository_url = github_repository_url(request.repository_url) if request.repository_url else ""
        repository_path = github_repository_path(request.repository_url) if request.repository_url else ""
        endpoint = core.registration_endpoint(request.endpoint_url) if request.intake_kind == "remote-endpoint" else None
        if request.intake_kind == "repository" and not repository_url:
            raise ValueError("소스 도입에는 구현 저장소 주소가 필요합니다.")
        if request.intake_kind == "remote-endpoint" and request.requested_transport != "streamable-http":
            raise ValueError("현재 원격 서비스 검토는 Streamable HTTP를 지원합니다. 다른 전송은 아직 검증되지 않았습니다.")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    # 거부(REJECTED)는 사람의 판단이고 실패(FAILED)는 검증이 끝나지 못한 오류다.
    # 둘을 같이 막으면, 스캐너 장애 한 번이 그 저장소를 영구히 신청 불가로 만든다.
    # 실제로 워커의 semgrep이 깨져 있던 동안 들어온 요청이 전부 그렇게 됐다.
    # 실패한 시도의 행과 사유는 그대로 남으므로 증적이 사라지지는 않는다.
    # A source approval made before impact input existed does not block a new request: that is how it is
    # approved again with the input it lacks (DEV-71). A registration taken back out (DISABLED) frees the
    # target too: the new request goes through the full review again, and without this the source could
    # never be approved a second time, e.g. to correct a tool's read/write class (D-199).
    existing = await db.fetch_one(
        "SELECT id, status FROM mcp_intake_requests r"
        " WHERE intake_kind=%s AND COALESCE(endpoint_url,repository_url)=%s AND repository_path=%s"
        " AND status NOT IN ('REJECTED', 'FAILED')"
        " AND (status <> 'APPROVED' OR (intake_kind='repository' AND jsonb_typeof(evidence->'risk_assessment')='object'))"
        " AND NOT EXISTS (SELECT 1 FROM mcp_servers s WHERE s.id=r.registered_server_id AND s.status='DISABLED')",
        (request.intake_kind, endpoint or repository_url, "" if endpoint else repository_path),
    )
    if existing:
        raise HTTPException(409, "같은 대상의 신청이 이미 진행 중입니다.")
    applicant_input = request.risk_input.model_dump() if request.risk_input else {"data_class": request.data_class}
    if endpoint:
        found = await gateway_proxy("/api/registry/intake-discover", authorization, "POST", {"endpoint": endpoint}, timeout=45)
        if not request.requested_tools or not set(request.requested_tools) <= {t["name"] for t in found["tools"]}:
            raise HTTPException(422, "필요한 도구를 하나 이상 선택하세요. 도구 목록을 다시 불러오세요.")
    # Submitting is the applicant's own consent to use this service for this purpose; it is recorded as
    # such, apart from the operator approval that may follow (D-92).
    async with db.transaction() as connection:
        row = await (await connection.execute(
            """INSERT INTO mcp_intake_requests(
                     id, submitted_by, display_name, repository_url, requested_transport,
                     purpose, exit_terms, status, intake_kind, endpoint_url, risk_input, requested_tools, repository_path
                 ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                 RETURNING id, display_name, repository_url, repository_path, requested_transport, purpose,
                           status, risk_level, exit_terms, created_at, intake_kind, endpoint_url""",
            (uuid4(), user["principal"], request.display_name.strip(), repository_url,
             request.requested_transport, request.purpose.strip(), Jsonb({}),
             "HOLD" if endpoint else "VALIDATION_QUEUED", request.intake_kind, endpoint,
             Jsonb(applicant_input), Jsonb(sorted(set(request.requested_tools))),
             "" if endpoint else repository_path))).fetchone()
        if row:
            await review.record_event("user-consent", "recorded", "intake", row["id"], user["principal"],
                                      applicant=user["principal"], reason=request.purpose.strip(),
                                      scope={"kind": request.intake_kind, "target": endpoint or "/".join(filter(None, (repository_url, repository_path))),
                                             "transport": request.requested_transport}, connection=connection)
    return {"request": row, "message": "신청했습니다."}


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
           WHERE id=%s AND status IN ('HOLD','VALIDATION_QUEUED','VALIDATING','VALIDATED','REMOTE_REVIEWED')
           RETURNING id, status, exit_terms""",
        (Jsonb(terms), request_id),
    )
    if not row:
        raise HTTPException(409, "승인 전 도입 요청만 검증 기록을 바꿀 수 있습니다.")
    return {"request": row, "message": "확인 내용을 기록했습니다."}


@app.post("/api/mcp-requests/{request_id}/queue-validation")
async def queue_validation(request_id: UUID, authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "검증 대기열은 관리자만 변경할 수 있습니다.")
    kind = await db.fetch_one("SELECT intake_kind FROM mcp_intake_requests WHERE id=%s", (request_id,))
    if kind and kind["intake_kind"] != "repository":
        raise HTTPException(409, "원격 서비스의 구현 코드를 검증한 것으로 표시할 수 없습니다. 도구 계약 검토를 사용하세요.")
    row = await db.fetch_one(
        """UPDATE mcp_intake_requests
           SET status='VALIDATION_QUEUED', reviewed_by=%s, reviewed_at=now(), updated_at=now(),
               validation_lease_expires_at=NULL, validation_attempts=0,
               commit_sha=NULL, source_ref=NULL, evidence='{}', provenance='{}', validated_at=NULL,
               risk_level='UNASSESSED', review_note=NULL
           WHERE id=%s AND status IN ('HOLD','FAILED','VALIDATED')
           RETURNING id, status, reviewed_by, reviewed_at""",
        (user["principal"], request_id),
    )
    if not row:
        raise HTTPException(409, "승인 전(보류·검증 실패·검증 완료) 요청만 다시 검증할 수 있습니다.")
    return {"request": row, "message": "검증을 시작했습니다."}


async def intake_report_row(request_id: UUID, authorization: str | None) -> dict:
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "상세 보안 보고서는 관리자만 볼 수 있습니다.")
    row = await db.fetch_one("SELECT * FROM mcp_intake_requests WHERE id=%s", (request_id,))
    if not row:
        raise HTTPException(404, "도입 요청을 찾지 못했습니다.")
    return row


RUNTIME_RECIPES = Path(os.getenv("RUNTIME_RECIPES", "/runtime-recipes"))


def runtime_recipe(repository_url: str | None) -> dict | None:
    """The fixed recipe the runtime worker builds this repository with, and its digest (as the worker
    computes it). Recipes are files reviewed in this repository; a request cannot supply one."""
    import tomllib
    if not repository_url or not RUNTIME_RECIPES.is_dir():
        return None
    for path in sorted(RUNTIME_RECIPES.glob("*.toml")):
        try:
            recipe = tomllib.loads(path.read_text(encoding="utf-8"))["recipe"]
            if recipe.get("repository") != repository_url:
                continue
            dockerfile = path.with_name(recipe["dockerfile"])
            return {"id": recipe["id"], "sha256": hashlib.sha256(path.read_bytes() + b"\0" + dockerfile.read_bytes()).hexdigest()}
        except (OSError, KeyError, ValueError):
            continue
    return None


@app.post("/api/mcp-requests/{request_id}/runtime")
async def start_runtime(request_id: UUID, authorization: str | None = Header(default=None)):
    """Queues one build-and-run of the approved commit (DEV-38). The runtime worker does the rest."""
    from psycopg.errors import UniqueViolation
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "실행은 관리자만 할 수 있습니다.")
    row = await db.fetch_one("SELECT * FROM mcp_intake_requests WHERE id=%s", (request_id,))
    if not row or row["intake_kind"] != "repository" or row["status"] != "APPROVED" or not row["commit_sha"]:
        raise HTTPException(409, "승인된 소스 신청만 실행할 수 있습니다.")
    if not row.get("internal_repo_url"):
        raise HTTPException(409, "내부 저장소 사본이 없습니다.")
    server = await db.fetch_one("SELECT status, lifecycle FROM mcp_servers WHERE id=%s", (row.get("registered_server_id"),))
    if server and (server["status"] == "DISABLED" or server["lifecycle"] in ("TERMINATING", "RETIRED")):
        raise HTTPException(409, "등록을 해제했거나 종료 중인 신청입니다. 새 도입 신청이 필요합니다.")
    recipe = runtime_recipe(row["repository_url"])
    if not recipe:
        raise HTTPException(409, "이 저장소의 실행 레시피가 없습니다.")
    try:
        created = await db.fetch_one(
            """INSERT INTO mcp_runtimes(id, intake_id, generation, recipe_id, recipe_sha256, source_commit, status, requested_by)
               SELECT %s, %s, COALESCE(MAX(generation), 0) + 1, %s, %s, %s, 'QUEUED', %s
               FROM mcp_runtimes WHERE intake_id=%s RETURNING id, generation, status""",
            (uuid4(), request_id, recipe["id"], recipe["sha256"], row["commit_sha"], user["principal"], request_id))
    except UniqueViolation as exc:
        raise HTTPException(409, "이미 실행 중이거나 대기 중입니다.") from exc
    await review.record_event("runtime-start", "recorded", "intake", request_id, user["principal"],
                              scope={"runtime": str(created["id"]), "generation": created["generation"],
                                     "recipe": recipe, "commit": row["commit_sha"]})
    return {"runtime": created, "message": "실행을 예약했습니다."}


@app.post("/api/mcp-requests/{request_id}/runtime/stop")
async def stop_runtime(request_id: UUID, authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "실행 중지는 관리자만 할 수 있습니다.")
    stopped = await db.fetch_one(
        """UPDATE mcp_runtimes SET status='STOPPING', error='관리자가 실행을 중지했습니다.', updated_at=now()
           WHERE intake_id=%s AND status IN ('QUEUED','BUILDING','STARTING','VERIFYING','ACTIVE')
           RETURNING id, generation""", (request_id,))
    if not stopped:
        raise HTTPException(409, "중지할 실행이 없습니다.")
    await review.record_event("runtime-stop", "recorded", "intake", request_id, user["principal"],
                              scope={"runtime": str(stopped["id"]), "generation": stopped["generation"]})
    return {"message": "실행을 중지합니다."}


async def runtime_rollback_options(request_id: UUID) -> list[dict]:
    rows = await db.fetch_all(
        """SELECT e.scope, e.created_at FROM approval_events e
             WHERE e.kind='runtime-active' AND e.target_kind='intake' AND e.target_id=%s
               AND e.scope->'contract' IS NOT NULL ORDER BY e.id DESC""", (str(request_id),))
    server = await db.fetch_one(
        """SELECT s.id,s.status,s.lifecycle FROM mcp_intake_requests i
             LEFT JOIN mcp_servers s ON s.id=i.registered_server_id WHERE i.id=%s""", (request_id,))
    if not server or server.get("status") in ("DISABLED", "BLOCKED_SUPPLY_CHAIN") \
            or server.get("lifecycle") in ("TERMINATING", "TERMINATED", "RETIRED"):
        return []
    stopped = await db.fetch_one(
        """SELECT 1 FROM ops_suspensions WHERE server_id=%s AND resumed_at IS NULL
           UNION ALL SELECT 1 FROM usage_relationships WHERE server_id=%s AND status IN ('TERMINATING','TERMINATED') LIMIT 1""",
        (server["id"], server["id"]))
    if stopped:
        return []
    active = await db.fetch_one("SELECT MAX(generation) AS generation FROM mcp_runtimes WHERE intake_id=%s AND status='ACTIVE'",
                                (request_id,))
    out = []
    for row in rows:
        scope = row["scope"] or {}
        contract = scope.get("contract") or {}
        generation = scope.get("generation")
        if (not generation or (active or {}).get("generation") is None or generation >= active["generation"]
                or not contract.get("sha256") or not contract.get("tools")):
            continue
        revoked = await db.fetch_one(
            """SELECT 1 FROM approval_events WHERE target_kind='intake' AND target_id=%s
                 AND kind IN ('runtime-revoked','runtime-terminated','runtime-supply-chain-stop')
                 AND (scope->>'generation')=%s LIMIT 1""", (str(request_id), str(generation)))
        if revoked:
            continue
        runtime = await db.fetch_one(
            """SELECT image_id,source_commit,status FROM mcp_runtimes WHERE intake_id=%s AND generation=%s""",
            (request_id, generation))
        if runtime and runtime.get("image_id") and runtime["status"] == "STOPPED":
            out.append({"generation": generation, "approved_at": contract.get("approved_at") or row["created_at"],
                        "approved_by": contract.get("approved_by"), "contract_sha256": contract["sha256"],
                        "source_commit": runtime["source_commit"]})
    return out


@app.post("/api/mcp-requests/{request_id}/runtime/rollback")
async def rollback_runtime(request_id: UUID, request: RuntimeRollback,
                           authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "되돌리기는 관리자만 할 수 있습니다.")
    note = " ".join(request.note.split())
    if "\n" in request.note or "\r" in request.note:
        raise HTTPException(422, "사유는 한 줄로 입력하세요.")
    try:
        return await _request_rollback(request_id, request, user, note)
    except HTTPException as refusal:
        if refusal.status_code == 409:
            # The refusal rolled its own transaction back; the ledger entry is written in a new one, append-only.
            async with db.transaction() as connection:
                await review.record_event(
                    "runtime-rollback-request-refused", "refused", "intake", request_id, user["principal"],
                    reason=str(refusal.detail), scope={"to_generation": request.generation, "note": note},
                    connection=connection)
        raise


async def _request_rollback(request_id: UUID, request: RuntimeRollback, user: dict, note: str) -> dict:
    async with db.transaction() as connection:
        intake = await (await connection.execute(
            "SELECT registered_server_id FROM mcp_intake_requests WHERE id=%s FOR UPDATE", (request_id,))).fetchone()
        if not intake or not intake["registered_server_id"]:
            raise HTTPException(409, "등록 서버를 확인할 수 없습니다.")
        server = await (await connection.execute(
            "SELECT id,status,lifecycle FROM mcp_servers WHERE id=%s FOR UPDATE", (intake["registered_server_id"],))).fetchone()
        if (not server or server["status"] in ("DISABLED", "BLOCKED_SUPPLY_CHAIN")
                or server.get("lifecycle") in ("TERMINATING", "TERMINATED", "RETIRED")):
            raise HTTPException(409, "철회·종료·공급망 중지 대상은 되돌릴 수 없습니다.")
        stopped = await (await connection.execute(
            """SELECT 1 FROM ops_suspensions WHERE server_id=%s AND resumed_at IS NULL
               UNION ALL SELECT 1 FROM usage_relationships WHERE server_id=%s
                 AND status IN ('TERMINATING','TERMINATED') LIMIT 1""",
            (server["id"], server["id"]))).fetchone()
        if stopped:
            raise HTTPException(409, "중지 또는 종료된 서버는 되돌릴 수 없습니다.")
        target_event = await (await connection.execute(
            """SELECT scope,created_at FROM approval_events WHERE kind='runtime-active' AND target_kind='intake'
                 AND target_id=%s AND (scope->>'generation')=%s AND scope->'contract' IS NOT NULL
               ORDER BY id DESC LIMIT 1""", (str(request_id), str(request.generation)))).fetchone()
        if not target_event:
            raise HTTPException(409, "이전에 승인한 실행 판본만 선택할 수 있습니다.")
        scope = target_event["scope"] or {}
        contract = scope.get("contract") or {}
        if not contract.get("sha256") or not contract.get("tools"):
            raise HTTPException(409, "승인 계약 이력을 확인할 수 없습니다.")
        revoked = await (await connection.execute(
            """SELECT 1 FROM approval_events WHERE target_kind='intake' AND target_id=%s
                 AND kind IN ('runtime-revoked','runtime-terminated','runtime-supply-chain-stop')
                 AND (scope->>'generation')=%s LIMIT 1""", (str(request_id), str(request.generation)))).fetchone()
        if revoked:
            raise HTTPException(409, "철회·종료·공급망 중지된 판본은 되돌릴 수 없습니다.")
        target = await (await connection.execute(
            "SELECT image_id,status FROM mcp_runtimes WHERE intake_id=%s AND generation=%s FOR SHARE",
            (request_id, request.generation))).fetchone()
        if not target or not target.get("image_id") or target["status"] != "STOPPED":
            raise HTTPException(409, "이전 판본의 실행 이미지를 찾을 수 없습니다.")
        current = await (await connection.execute(
            "SELECT generation FROM mcp_runtimes WHERE intake_id=%s AND status='ACTIVE' FOR UPDATE",
            (request_id,))).fetchone()
        if not current or request.generation >= current["generation"]:
            raise HTTPException(409, "현재 실행보다 이전 승인 판본을 선택하세요.")
        tool_names = {row["name"] for row in await (await connection.execute(
            "SELECT name FROM mcp_tools WHERE server_id=%s", (contract["server_id"],))).fetchall()}
        if tool_names != set(contract["tools"]):
            raise HTTPException(409, "현재 도구 구성과 승인 판본의 계약 구성이 다릅니다.")
        current = await (await connection.execute(
            """UPDATE mcp_runtimes SET status='STOPPING',error='관리자가 승인 판본 되돌리기를 요청했습니다.',
                      rollback_target_generation=%s,rollback_contract=%s,updated_at=now()
                 WHERE intake_id=%s AND status='ACTIVE' RETURNING id,generation""",
            (request.generation, Jsonb(contract), request_id))).fetchone()
        if not current or current["generation"] == request.generation:
            raise HTTPException(409, "되돌릴 실행이 없거나 이미 선택한 판본입니다.")
        await review.record_event(
            "runtime-rollback", "recorded", "intake", request_id, user["principal"], reason=note,
            scope={"from_generation": current["generation"], "to_generation": request.generation,
                   "contract_sha256": contract["sha256"]}, connection=connection)
    return {"message": "실행 중지와 판본 전환을 요청했습니다."}


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
    artifacts = {"sbom": "sbom.cdx.json", "trivy": "trivy.json", "semgrep": "semgrep.json", "gitleaks": "gitleaks.json",
                 "exit-terms": "exit-terms.json"}
    available = []
    for kind, suffix in artifacts.items():
        name = f"intake-{request_id}-{suffix}"
        if name in (row.get("evidence") or {}).get("reports", []):
            available.append({"kind": kind, "filename": name,
                              "url": f"/api/mcp-requests/{request_id}/artifacts/{kind}"})
    return {"request": row, "reports": reports, "artifacts": available,
            "risk": {**risk_tier.assess(row.get("risk_input")), "package": risk_tier.package(row.get("risk_input"), row)},
            "exit_terms_discovery": (row.get("evidence") or {}).get("exit_terms_discovery"),
            "gate": await review.intake_gate(row), "events": await review.events_for("intake", request_id),
            "runtimes": await db.fetch_all(
                """SELECT id, generation, status, recipe_id, recipe_sha256, source_commit, source_archive_sha256, image_id,
                          endpoint, error, evidence - 'packages' AS evidence, requested_by, attempts, created_at, updated_at
                     FROM mcp_runtimes WHERE intake_id=%s ORDER BY generation DESC""", (request_id,)),
            "rollback_options": await runtime_rollback_options(request_id),
            "risk_acceptances": await db.fetch_all(
                """SELECT id, commit_sha, critical_count, finding_ids, reason, accepted_by, accepted_at, expires_at, revoked_at
                     FROM accepted_risks WHERE intake_id=%s ORDER BY id DESC""", (request_id,))}


@app.get("/api/mcp-requests/{request_id}/artifacts/{kind}")
async def intake_artifact(request_id: UUID, kind: str,
                          authorization: str | None = Header(default=None)):
    row = await intake_report_row(request_id, authorization)
    suffix = {"sbom": "sbom.cdx.json", "trivy": "trivy.json", "semgrep": "semgrep.json", "gitleaks": "gitleaks.json",
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


class SbomImpactRequest(StrictModel):
    package: str = Field(min_length=1, max_length=200)
    version_range: str = Field(min_length=1, max_length=120)


class SbomImpactStop(SbomImpactRequest):
    reason: str = Field(min_length=4, max_length=500)


@app.post("/api/supply-chain/impact")
async def supply_chain_impact(request: SbomImpactRequest, user: dict = Depends(admin_caller)):
    try:
        return await sbom_impact.impact(request.package, request.version_range)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/supply-chain/impact/stop")
async def supply_chain_impact_stop(request: SbomImpactStop, user: dict = Depends(admin_caller)):
    try:
        return await sbom_impact.stop_affected(
            request.package, request.version_range, user["principal"], request.reason)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


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


@app.put("/api/mcp-requests/{request_id}/risk-input")
async def set_risk_input(request_id: UUID, stated: ImpactInput, authorization: str | None = Header(default=None)):
    """A request filed without its impact input, or with a wrong one, is completed before approval.
    The change is a recorded event, and earlier first approvals stop counting because they name the old input."""
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "영향평가 입력은 관리자만 고칠 수 있습니다.")
    values = stated.model_dump()
    assessed = risk_tier.assess(values)
    row = await review.transition(
        """UPDATE mcp_intake_requests SET risk_input=%s, updated_at=now()
           WHERE id=%s AND status IN ('HOLD','VALIDATION_QUEUED','VALIDATING','VALIDATED','REMOTE_REVIEWED')
           RETURNING id, status, risk_input""", (Jsonb(values), request_id),
        kind="risk-input", outcome="recorded", target_kind="intake", target_id=request_id, actor=user["principal"],
        scope={"tier": assessed["tier"], "score": assessed["score"], "input_sha256": assessed["input_sha256"]})
    if not row:
        raise HTTPException(409, "승인 전 도입 요청만 영향평가 입력을 바꿀 수 있습니다.")
    return {"request": row, "risk": assessed, "message": f"위험 등급 {risk_tier.TIER_LABELS[assessed['tier']]}으로 기록했습니다."}


class IntakeApproval(StrictModel):
    risk_acceptance: str = Field(default="", max_length=1000)
    license: str = Field(default="", max_length=60)
    legal_entity: str = Field(default="", max_length=200)
    supplier_contact: str = Field(default="", max_length=300)
    security_contact: str = Field(default="", max_length=300)
    support_end: str = Field(default="", max_length=10)
    vulnerability_policy_url: str = Field(default="", max_length=500)
    subprocessors: Literal["미확인", "있음", "없음"] = "미확인"
    sbom_submitted: bool | None = None  # 묻지 않았으면 비워 둔다. False는 "제출하지 않았다"는 확인이다.
    vex_submitted: bool | None = None
    contract_basis_ref: str = Field(default="", max_length=500)
    exit_strategy: str = Field(default="", max_length=1000)


class ProvenanceMismatch(Exception):
    """The copy employees would use is not the artifact that was scanned."""


async def hold_intake(request_id: UUID, row: dict, user: dict, messages: list[str], kind: str = "intake-hold") -> None:
    """A request whose evidence does not hold up goes back to hold with the reasons, never forward."""
    note = "보류: " + " / ".join(messages)[:400]
    await review.transition(
        """UPDATE mcp_intake_requests SET status='HOLD', review_note=%s, updated_at=now()
           WHERE id=%s AND status IN ('VALIDATED', 'REMOTE_REVIEWED') RETURNING id""", (note, request_id),
        kind=kind, outcome="held", target_kind="intake", target_id=request_id, actor=user["principal"],
        applicant=row["submitted_by"], reason=note, scope={"was": row["status"]})


async def risk_tier_gate(request_id: UUID, row: dict, user: dict, reason: str) -> dict:
    """The approval method the request's tier calls for. A request without complete input is held; the
    first of two required approvers is recorded and answered with `pending`; anything else is approvable."""
    assessed = risk_tier.assess(row.get("risk_input"))
    if assessed["status"] != "ok":
        await hold_intake(request_id, row, user, assessed["messages"])
        raise HTTPException(409, "승인할 수 없습니다: " + " / ".join(assessed["messages"]))
    others: list[str] = []
    for event in await db.fetch_all(
            """SELECT DISTINCT actor FROM approval_events
                WHERE kind='intake-cosign' AND target_kind='intake' AND target_id=%s AND scope->>'input_sha256'=%s""",
            (str(request_id), assessed["input_sha256"])):
        earlier = event["actor"]
        if not await review.same_person(earlier, user["principal"]) and not [
                seen for seen in others if await review.same_person(earlier, seen)]:
            others.append(earlier)
    approvers = 1 + len(others)
    solo_mode, solo = review.solo_mode_enabled(), review.solo_operator(user)
    verdict, message = risk_tier.decide(assessed["tier"], approvers, reason)
    if verdict == "refuse":
        raise HTTPException(409, "승인할 수 없습니다: " + message)
    if verdict == "cosign":
        done = await db.fetch_one(
            """SELECT 1 AS found FROM approval_events WHERE kind='intake-cosign' AND target_kind='intake' AND target_id=%s
                  AND actor=%s AND scope->>'input_sha256'=%s""", (str(request_id), user["principal"], assessed["input_sha256"]))
        if not done:
            await review.record_event("intake-cosign", "recorded", "intake", request_id, user["principal"],
                                      applicant=row["submitted_by"], reason=(reason or "").strip() or None,
                                      scope={"tier": assessed["tier"], "input_sha256": assessed["input_sha256"],
                                             "approvers": 1 + len(others), "solo_mode": solo_mode, "solo_operator": solo})
        return {"pending": True, "message": message}
    return {"pending": False, "record": {
        "tier": assessed["tier"], "score": assessed["score"], "floors": assessed["floors"],
        "input_sha256": assessed["input_sha256"], "version": assessed["version"],
        "approvers": [user["principal"], *others], "written_reason": len((reason or "").strip()) >= risk_tier.MIN_REASON,
        "solo_mode": solo_mode, "solo_operator": solo}}


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
    await review.lapse_expired_acceptances()
    remote = await db.fetch_one(
        """SELECT r.*, p.user_id AS submitter_user_id FROM mcp_intake_requests r
           LEFT JOIN principals p ON p.token = r.submitted_by WHERE r.id=%s""", (request_id,))
    if remote:
        try:
            await review.require_independent("intake-approve", "intake", request_id, user["principal"], remote["submitted_by"],
                                             {"name": remote["display_name"]}, actor_user=user.get("user_id"),
                                             applicant_user=remote.get("submitter_user_id"))
        except review.NotIndependent as exc:
            raise HTTPException(403, str(exc)) from exc
    approval_values = approval if approval is not None else IntakeApproval()
    assurance = {key: (getattr(approval_values, key, "") or "").strip() for key in supplier_assurance.REQUIRED_FIELDS}
    assurance.update({key: value for key in supplier_assurance.OPTIONAL_FIELDS
                      if (value := getattr(approval_values, key)) is not None})
    assurance_errors = supplier_assurance.validate(assurance, required=False)
    if assurance_errors:
        if remote:
            await hold_intake(request_id, remote, user, assurance_errors)
        raise HTTPException(409, "승인할 수 없습니다: " + " / ".join(assurance_errors))
    risk_record = None
    if remote and remote["status"] in {"VALIDATED", "REMOTE_REVIEWED"}:
        gated = await risk_tier_gate(request_id, remote, user, approval_values.risk_acceptance)
        if gated["pending"]:
            return {"request": {"id": remote["id"], "status": remote["status"]}, "pending": True, "message": gated["message"]}
        risk_record = gated["record"]
    if remote:
        remote = {**remote, "supplier_assurance": assurance}
    if remote and remote.get("intake_kind") == "remote-endpoint":
        reviewed = (remote.get("evidence") or {}).get("remote_contract") or {}
        if remote["status"] != "REMOTE_REVIEWED" or not reviewed.get("reviewed_by"):
            raise HTTPException(409, "실제 도구 계약과 접근 범위를 검토한 뒤 승인하세요.")
        risk = approval.risk_acceptance.strip() if approval else ""
        if not manual_terms_verified(remote.get("exit_terms") or {}) and len(risk) < 10:
            raise HTTPException(409, "제공자 종료 조건 증거 또는 10자 이상의 위험 수용 사유가 필요합니다.")
        if datetime.fromisoformat(reviewed["valid_until"]) <= datetime.now(UTC):
            raise HTTPException(409, "검토한 사용 기한이 지났습니다. 다시 검토하세요.")
        gate = await review.intake_gate(remote)
        if gate["blockers"]:
            await hold_intake(request_id, remote, user, [item["message"] for item in gate["blockers"]])
            raise HTTPException(409, "출처 정보를 확인하지 못해 보류했습니다: " + " / ".join(item["message"] for item in gate["blockers"]))
        found = await gateway_proxy("/api/registry/discover", authorization, "POST",
                                    {"endpoint": remote["endpoint_url"]}, timeout=45)
        if (found["catalog_hash"] != reviewed["registration"]["catalog_hash"]
                or found["version"] != reviewed["version"]
                or found["server_name"] != reviewed["advertised_name"]
                or found["protocol_version"] != reviewed["protocol_version"]):
            raise HTTPException(409, "검토 후 공급자 계약이 바뀌었습니다. 다시 검토하세요.")
        evidence = {**remote["evidence"], "supplier_assurance": assurance, "risk_assessment": risk_record,
                    "supplier_assurance_unconfirmed": supplier_assurance.unconfirmed(assurance), "remote_approval": {
            "actor": user["principal"], "at": datetime.now(UTC).isoformat(),
            "review_digest": core.canonical_hash(reviewed), "risk_acceptance": risk,
            "code_scan_performed": False}}
        row = await review.transition("""UPDATE mcp_intake_requests SET status='APPROVED', evidence=%s,
                reviewed_by=%s, reviewed_at=now(), updated_at=now()
                WHERE id=%s AND status='REMOTE_REVIEWED' AND evidence=%s
                RETURNING id,status,reviewed_by,reviewed_at""",
                (Jsonb(evidence), user["principal"], request_id, Jsonb(remote["evidence"])),
                kind="intake-approve", outcome="approved", target_kind="intake", target_id=request_id,
                actor=user["principal"], applicant=remote["submitted_by"], reason=risk or reviewed.get("review_note"),
                scope={"risk_tier": risk_record["tier"], "approvers": risk_record["approvers"],
                       "solo_mode": bool(risk_record.get("solo_mode")), "solo_operator": bool(risk_record.get("solo_operator")),
                       "supplier_assurance_unconfirmed": supplier_assurance.unconfirmed(assurance),
                       "endpoint": remote["endpoint_url"], "tools": reviewed["registration"]["tools"],
                       "residency": reviewed["registration"].get("residency") or {},
                       "data_class": reviewed["registration"]["data_class"], "valid_until": reviewed["valid_until"],
                       "allowed_principals": reviewed["allowed_principals"], "contract_sha256": reviewed["registration"]["catalog_hash"]})
        if not row:
            raise HTTPException(409, "요청 상태가 변경되어 승인하지 않았습니다.")
        return {"request": row, "message": "승인했습니다."}
    pending = remote
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
    # D-90: where the code came from, what it hashed to, whether the scan is whole and recent. A licence
    # the scanner could not read may be attested by the approver; it is recorded as theirs.
    record = dict(pending.get("provenance") or {})
    declared = approval.license.strip() if approval else ""
    if declared and record and not (record.get("license") or {}).get("spdx"):
        record["license"] = {"spdx": declared, "source": "operator", "by": user["principal"]}
    try:
        keys = (artifact_provenance.trust_keys(os.getenv("MCP_PROVENANCE_TRUST_KEYS_FILE", ""))
                if (record.get("verification") or {}).get("attestation") else {})
        proof = artifact_provenance.verify_source_attestation(
            record, str((record.get("artifact") or {}).get("sha256") or ""), keys)
    except (OSError, ValueError, TypeError):
        proof = {"status": artifact_provenance.UNAVAILABLE, "reason": "신뢰 키 설정을 읽을 수 없습니다."}
    if reason := artifact_provenance.blocking_reason(proof):
        await hold_intake(request_id, {**pending, "provenance": record}, user, [reason], kind="provenance-mismatch")
        raise HTTPException(409, f"출처 증명 검증에서 보류했습니다: {reason}")
    record["verification"] = {**(record.get("verification") or {}), "provenance_status": proof["status"],
                              "provenance_reason": proof["reason"], "provenance_keyid": proof.get("keyid")}
    pending = {**pending, "provenance": record, "supplier_assurance": assurance}
    gate = await review.intake_gate(pending)
    if gate["blockers"]:
        await hold_intake(request_id, pending, user, [item["message"] for item in gate["blockers"]])
        raise HTTPException(409, "승인할 수 없어 보류했습니다: " + " / ".join(item["message"] for item in gate["blockers"]))
    try:
        internal_repo_url, checked = await publish_internal_repo(pending)
    except ProvenanceMismatch as exc:
        await hold_intake(request_id, pending, user, [str(exc)], kind="provenance-mismatch")
        raise HTTPException(409, f"배포 파일이 검증한 것과 달라 보류했습니다: {exc}") from exc
    record["verification"] = {**(record.get("verification") or {}), **checked,
                              "by": user["principal"], "at": datetime.now(UTC).isoformat(timespec="seconds")}
    critical = gate["critical"] or {}
    evidence = {**(pending.get("evidence") or {}), "supplier_assurance": assurance, "risk_assessment": risk_record,
                "supplier_assurance_unconfirmed": supplier_assurance.unconfirmed(assurance)}
    row = await review.transition(
        """UPDATE mcp_intake_requests
           SET status='APPROVED', internal_repo_url=%s, evidence=%s, reviewed_by=%s, reviewed_at=now(), updated_at=now(),
               exit_terms=%s, provenance=%s
           WHERE id=%s AND status='VALIDATED'
           RETURNING id, status, internal_repo_url, reviewed_by, reviewed_at, source_ref, exit_terms""",
        (internal_repo_url, Jsonb(evidence), user["principal"], Jsonb(terms), Jsonb(record), request_id),
        kind="intake-approve", outcome="approved", target_kind="intake", target_id=request_id,
        actor=user["principal"], applicant=pending["submitted_by"], reason=risk or None,
        scope={"risk_tier": risk_record["tier"], "approvers": risk_record["approvers"],
                       "solo_mode": bool(risk_record.get("solo_mode")), "solo_operator": bool(risk_record.get("solo_operator")),
               "supplier_assurance_unconfirmed": supplier_assurance.unconfirmed(assurance),
               "source": pending["repository_url"], "commit": pending["commit_sha"],
               "license": (record.get("license") or {}).get("spdx"),
               "artifact_sha256": (record.get("artifact") or {}).get("sha256"), "verified_sha256": checked["sha256"],
               "critical_accepted": critical.get("count", 0) if critical.get("covered") else 0,
               "vuln_db_updated_at": gate["vuln_db"] and gate["vuln_db"]["updated_at"]})
    if not row:
        raise HTTPException(409, "격리 검증을 통과한 요청만 승인할 수 있습니다.")
    return {"request": row, "message": "승인하고 사내 저장소에 게시했습니다."}


class RiskAcceptance(StrictModel):
    reason: str = Field(min_length=10, max_length=1000)
    days: int = Field(ge=1, le=review.RISK_ACCEPTANCE_MAX_DAYS)


@app.post("/api/mcp-requests/{request_id}/accept-risk")
async def accept_intake_risk(request_id: UUID, request: RiskAcceptance, authorization: str | None = Header(default=None)):
    """치명적 발견을 기한을 두고 수용한다. 기한이 지나면 요청은 다시 보류된다."""
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "위험 수용은 관리자만 기록할 수 있습니다.")
    try:
        accepted = await review.accept_risk(request_id, user["principal"], request.reason, request.days)
    except review.NotIndependent as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"acceptance": accepted, "message": f"{accepted['expires_at'].date()}까지 위험 수용을 기록했습니다."}


class IntakeRegistration(ResidencyFields):
    server_id: str = Field(pattern=r"^[a-z][a-z0-9-]{1,30}$")
    endpoint: str = Field(min_length=8, max_length=500)
    catalog_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    tools: dict[str, Literal["r", "w", "x"]] = Field(min_length=1, max_length=300)
    data_class: Literal["public", "nonimportant", "important"]
    valid_days: int = Field(ge=1, le=365)
    poisoning_ack: bool = False
    tool_reviews: dict[str, ToolReview] = Field(min_length=1, max_length=300)
    # DEV-73: signed manifest for a run on employees' PCs. Excluded from model_dump so a reviewed
    # remote registration still compares equal to what was approved.
    local: dict | None = Field(default=None, exclude=True)


class RemoteContractReview(IntakeRegistration):
    allowed_principals: list[str] = Field(min_length=1, max_length=100)
    review_note: str = Field(min_length=10, max_length=1000)
    parameter_constraints: dict[str, dict] = Field(default_factory=dict, max_length=300)


@app.post("/api/mcp-requests/{request_id}/review-contract")
async def review_remote_contract(request_id: UUID, proposal: RemoteContractReview,
                                 authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "도구 계약 검토는 관리자만 할 수 있습니다.")
    row = await db.fetch_one(
        """SELECT r.*, p.user_id AS submitter_user_id FROM mcp_intake_requests r
           LEFT JOIN principals p ON p.token = r.submitted_by WHERE r.id=%s""", (request_id,))
    if not row or row["intake_kind"] != "remote-endpoint" or row["status"] not in {"HOLD", "REMOTE_REVIEWED"}:
        raise HTTPException(409, "승인 전 원격 신청만 계약을 검토할 수 있습니다.")
    try:
        await review.require_independent("contract-review", "intake", request_id, user["principal"], row["submitted_by"],
                                         {"endpoint": row["endpoint_url"]}, actor_user=user.get("user_id"),
                                         applicant_user=row.get("submitter_user_id"))
    except review.NotIndependent as exc:
        raise HTTPException(403, str(exc)) from exc
    if proposal.endpoint != row["endpoint_url"]:
        raise HTTPException(409, "신청한 엔드포인트와 검토 대상이 다릅니다.")
    # The Console asks for login ids; the ledger and the Gateway work in principal tokens.
    principals = await db.fetch_all(
        "SELECT token, user_id FROM principals WHERE status='active' AND (token=ANY(%s::text[]) OR user_id=ANY(%s::text[]))",
        (proposal.allowed_principals, proposal.allowed_principals))
    named = {p["token"] for p in principals} | {p["user_id"] for p in principals}
    missing = sorted(set(proposal.allowed_principals) - named)
    if missing:
        raise HTTPException(422, f"활성 계정이 아닌 사용자: {', '.join(missing)}")
    proposal = proposal.model_copy(update={"allowed_principals": sorted({p["token"] for p in principals})})
    found = await gateway_proxy("/api/registry/discover", authorization, "POST",
                                {"endpoint": proposal.endpoint}, timeout=45)
    advertised = {tool["name"]: tool for tool in found["tools"]}
    if proposal.catalog_hash != found["catalog_hash"] or not set(proposal.tools) <= set(advertised):
        raise HTTPException(409, "실제 공급자 계약과 검토 내용이 다릅니다.")
    if any(advertised[name]["warnings"] for name in proposal.tools) and not proposal.poisoning_ack:
        raise HTTPException(409, "선택한 도구의 설명 경고를 읽고 검토 확인을 남기세요.")
    from jsonschema import Draft202012Validator, SchemaError
    if not proposal.parameter_constraints:
        # Left blank, the scope comes from the advertised contract and the reviewed destinations.
        proposal = proposal.model_copy(update={"parameter_constraints": review.derived_constraints(
            advertised, {name: item.model_dump() for name, item in proposal.tool_reviews.items()})})
    if set(proposal.parameter_constraints) != set(proposal.tools):
        raise HTTPException(422, "선택한 모든 도구의 인자 범위를 JSON Schema로 검토하세요.")
    try:
        for constraint in proposal.parameter_constraints.values():
            Draft202012Validator.check_schema(constraint)
            if constraint.get("type") != "object" or constraint.get("additionalProperties") is not False:
                raise ValueError("명시적 object 형식과 additionalProperties=false가 필요합니다")
    except (SchemaError, ValueError) as exc:
        raise HTTPException(422, "인자 범위 검토 형식이 올바르지 않습니다.") from exc
    from datetime import timedelta
    contract = {"registration": proposal.model_dump(exclude={"allowed_principals", "review_note", "parameter_constraints"}),
                "parameter_constraints": proposal.parameter_constraints,
                "allowed_principals": sorted(set(proposal.allowed_principals)), "review_note": proposal.review_note,
                "reviewed_by": user["principal"], "reviewed_at": datetime.now(UTC).isoformat(),
                "valid_until": (datetime.now(UTC) + timedelta(days=proposal.valid_days)).isoformat(),
                "advertised_name": found["server_name"], "version": found["version"],
                "protocol_version": found["protocol_version"],
                "tools": {name: advertised[name] for name in proposal.tools}, "code_scan_performed": False}
    evidence = {**row["evidence"], "remote_contract": contract}
    # A hosted service has no artifact to hash: the record says so and names the endpoint (D-90).
    source = {"kind": "provider-hosted", "source_url": row["endpoint_url"], "version": found["version"], "version_immutable": False,
              "license": {"spdx": None, "applicable": False},
              "artifact": {"applicable": False, "reason": provenance.NOT_APPLICABLE, "endpoint": row["endpoint_url"]},
              "contract_sha256": found["catalog_hash"], "recorded_at": datetime.now(UTC).isoformat(timespec="seconds")}
    changed = await review.transition("""UPDATE mcp_intake_requests SET status='REMOTE_REVIEWED', evidence=%s, provenance=%s,
              updated_at=now() WHERE id=%s AND status IN ('HOLD','REMOTE_REVIEWED') AND evidence=%s
              RETURNING id,status,evidence""",
              (Jsonb(evidence), Jsonb(source), request_id, Jsonb(row["evidence"])),
              kind="contract-review", outcome="recorded", target_kind="intake", target_id=request_id,
              actor=user["principal"], applicant=row["submitted_by"], reason=proposal.review_note,
              scope={"endpoint": row["endpoint_url"], "tools": proposal.tools, "data_class": proposal.data_class,
                      "residency": proposal.residency,
                     "valid_until": contract["valid_until"], "allowed_principals": contract["allowed_principals"],
                     "tool_reviews": {name: {"asset": item.asset, "destinations": item.destinations}
                                      for name, item in proposal.tool_reviews.items()}})
    if not changed:
        raise HTTPException(409, "검토 도중 요청 상태가 변경되었습니다.")
    return {"request": changed, "message": "검토를 기록했습니다."}


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
    if row["intake_kind"] == "remote-endpoint":
        reviewed = (row.get("evidence") or {}).get("remote_contract") or {}
        if reviewed.get("registration") != request.model_dump():
            raise HTTPException(409, "승인된 endpoint·도구·등급·기한과 다릅니다. 새 도입 신청이 필요합니다.")
    body = {**request.model_dump(), "display_name": row["display_name"],
            "source_url": row["endpoint_url"] if row["intake_kind"] == "remote-endpoint" else row["repository_url"],
            "commit_sha": row["commit_sha"] or "",
            "supplier": urlsplit(row["endpoint_url"] or row["repository_url"]).hostname or "",
            "purpose": row["purpose"], "owner_department": row.get("department") or "",
            "intake_id": str(row["id"]), "exit_terms": exit_term_flags(row),
            "supplier_assurance": (row.get("evidence") or {}).get("supplier_assurance") or {}}
    if request.local is not None:
        body["local"] = request.local
    result = await gateway_proxy("/api/registry/servers", authorization, "POST", body, timeout=120)
    await db.execute("UPDATE mcp_intake_requests SET registered_server_id=%s, updated_at=now() WHERE id=%s",
                     (request.server_id, request_id))
    return {**result, "message": f"게이트웨이에 등록했습니다 · /mcp/{request.server_id}/ · {result['valid_until'][:10]}까지"}


async def caller(authorization: str | None = Header(default=None)) -> dict:
    return await current_identity(authorization)


async def admin_caller(user: dict = Depends(caller)) -> dict:
    if "admin" not in user["roles"]:
        raise HTTPException(403, "관리자만 승인할 수 있습니다.")
    return user


class IntakeDiscovery(StrictModel):
    endpoint: str = Field(min_length=8, max_length=500)


@app.post("/api/mcp-requests/discover")
async def discover_intake(request: IntakeDiscovery, user: dict = Depends(caller),
                          authorization: str | None = Header(default=None)):
    return await gateway_proxy("/api/registry/intake-discover", authorization, "POST", request.model_dump(), timeout=45)


class ApprovalPreview(StrictModel):
    pass


class OneClickApproval(StrictModel):
    proposal_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    tools: list[str] = Field(min_length=1, max_length=300)
    valid_days: int = Field(default=90, ge=1, le=365)
    critical_reason: str = Field(default="", max_length=1000)
    risk_reason: str = Field(default="", max_length=1000)
    supplier_assurance: dict = Field(default_factory=dict)
    residency: dict = Field(default_factory=dict)
    # 관리자가 제안된 읽기/쓰기 분류를 낮춘 도구만. 주석이 없는 공개 MCP는 읽기 도구도 쓰기로 제안된다.
    actions: dict[str, Literal["r", "w", "x"]] = Field(default_factory=dict, max_length=300)


async def approval_row(request_id: UUID, user: dict) -> dict:
    row = await db.fetch_one(
        """SELECT r.*, p.user_id AS submitter_user_id, p.display_name AS submitter_name FROM mcp_intake_requests r
           LEFT JOIN principals p ON p.token=r.submitted_by WHERE r.id=%s""", (request_id,))
    if not row or row["status"] not in {"HOLD", "VALIDATED", "REMOTE_REVIEWED", "APPROVED"}:
        raise HTTPException(409, "검증이 끝난 신청만 검토할 수 있습니다. 검사 상태를 확인하세요.")
    try:
        await review.require_independent("intake-one-click", "intake", request_id, user["principal"], row["submitted_by"],
                                         actor_user=user.get("user_id"), applicant_user=row.get("submitter_user_id"))
    except review.NotIndependent as exc:
        raise HTTPException(403, str(exc)) from exc
    return row


async def collect_proposal_provenance(row: dict, record: dict) -> tuple[dict, str | None]:
    """OCI discovery is optional; only a discovered envelope is sent through the fail-closed verifier."""
    record = dict(record or {})
    artifact = record.get("artifact") or {}
    digest = artifact.get("sha256")
    if row.get("intake_kind") == "repository" and isinstance(digest, str):
        envelope = await asyncio.to_thread(
            artifact_provenance.collect_intake_referrer,
            artifact_provenance.allowed_registry_origins(), row.get("repository_url") or "", f"sha256:{digest}")
        if envelope is not None:
            record["verification"] = {**(record.get("verification") or {}), "attestation": envelope,
                                       "attestation_source": "oci-referrer"}
    verification = record.get("verification") or {}
    if verification.get("attestation"):
        try:
            keys = artifact_provenance.trust_keys(os.getenv("MCP_PROVENANCE_TRUST_KEYS_FILE", ""))
        except (OSError, ValueError, TypeError):
            keys = None
        if keys is None:
            proof = {"status": artifact_provenance.UNAVAILABLE, "reason": "신뢰 키 설정을 읽을 수 없습니다."}
        else:
            proof = artifact_provenance.verify_source_attestation(record, str(digest or ""), keys)
    else:
        proof = artifact_provenance.verify_source_attestation(record, str(digest or ""), {})
    verification = {**verification, "provenance_status": proof["status"], "provenance_reason": proof["reason"],
                    "provenance_keyid": proof.get("keyid")}
    record["verification"] = verification
    return record, artifact_provenance.blocking_reason(proof)


class LocalRunSpec(StrictModel):
    image: str = Field(min_length=3, max_length=300)
    command: list[str] = Field(default_factory=list, max_length=32)
    mounts: list[dict[str, str]] = Field(default_factory=list, max_length=8)
    env: dict[str, str] = Field(default_factory=dict, max_length=32)
    reason_kind: Literal["local_file", "local_tool", "device"]
    reason_text: str = Field(min_length=10, max_length=500)


async def pinned_image(image: str) -> str:
    """관리자는 `mcp/filesystem` 같은 이름만 넣는다. 실행·서명은 그 순간의 digest로 고정한다(Docker Hub)."""
    image = image.strip().lower()
    if "@sha256:" in image:
        return image
    name, tag = (image.rsplit(":", 1) if ":" in image.split("/")[-1] else (image, "latest"))
    repo = name.removeprefix("docker.io/")
    repo = repo if "/" in repo else "library/" + repo
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            token = (await client.get("https://auth.docker.io/token", params={
                "service": "registry.docker.io", "scope": f"repository:{repo}:pull"})).json()["token"]
            head = await client.head(f"https://registry-1.docker.io/v2/{repo}/manifests/{tag}", headers={
                "Authorization": f"Bearer {token}",
                "Accept": ", ".join(("application/vnd.oci.image.index.v1+json",
                                     "application/vnd.docker.distribution.manifest.list.v2+json",
                                     "application/vnd.oci.image.manifest.v1+json",
                                     "application/vnd.docker.distribution.manifest.v2+json"))})
        digest = head.headers.get("docker-content-digest", "")
    except (httpx.HTTPError, KeyError, ValueError):
        digest = ""
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise HTTPException(422, "이미지 digest를 확인하지 못했습니다. 이름@sha256:… 형식으로 입력하세요.")
    return f"{name}@{digest}"


async def signed_local_run(spec: dict, server_id: str) -> dict:
    """승인 화면을 열 때마다 새 서명 세대로 서명한다. 같은 세대의 다른 매니페스트는 게이트웨이가 거부한다."""
    pem = os.getenv("LOCAL_MANIFEST_PRIVATE_KEY", "").replace("\\n", "\n").strip()
    if not pem:
        raise HTTPException(409, "로컬 실행 서명 키가 구성되지 않았습니다.")
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    previous = await db.fetch_one("SELECT signature_generation FROM local_approvals WHERE server_id=%s", (server_id,))
    manifest = {"server_id": server_id, "image": spec["image"], "command": spec["command"], "mounts": spec["mounts"],
                "env": spec["env"], "reason": {"kind": spec["reason_kind"], "text": spec["reason_text"]},
                "approval": {"generation": (previous["signature_generation"] + 1) if previous else 1,
                             "expires_at": (datetime.now(UTC) + timedelta(days=365)).isoformat()}}
    errors = local_jobs.manifest_errors(manifest, server_id)
    if errors:
        raise HTTPException(422, " / ".join(errors))
    signature = load_pem_private_key(pem.encode(), None).sign(local_jobs.canonical(manifest))
    return {"manifest": manifest, "signature": base64.b64encode(signature).decode()}


def discovery(endpoint: str, local: dict | None, request_id) -> dict:
    return {"endpoint": endpoint, "local": local, "intake_id": str(request_id)} if local else {"endpoint": endpoint}


LOCAL_DISCOVER_SECONDS = 240  # 직원 PC가 이미지를 처음 받아 도구 목록을 돌려주는 시간


@app.post("/api/mcp-requests/{request_id}/local-run")
async def set_local_run(request_id: UUID, request: LocalRunSpec, user: dict = Depends(admin_caller)):
    """저장소형 stdio 서버를 신청자 PC의 격리 컨테이너로 실행하도록 지정한다(DEV-73). 서명은 승인 화면에서."""
    row = await approval_row(request_id, user)
    if row["intake_kind"] != "repository":
        raise HTTPException(409, "저장소 신청만 PC 격리 실행으로 지정할 수 있습니다.")
    spec = {**request.model_dump(), "image": await pinned_image(request.image)}
    errors = local_jobs.manifest_errors({"server_id": "x", "image": spec["image"], "command": spec["command"],
                                         "mounts": spec["mounts"], "env": spec["env"],
                                         "reason": {"kind": spec["reason_kind"], "text": spec["reason_text"]}}, "x")
    mirrors = [m.strip() for m in os.getenv("LOCAL_IMAGE_MIRRORS", "").split(",") if m.strip()]
    if not local_jobs.mirror_image(spec["image"], mirrors):
        errors.append("허용한 이미지 저장소가 아닙니다: " + (", ".join(mirrors) or "—"))
    if errors:
        raise HTTPException(422, " / ".join(errors))
    evidence = row.get("evidence") or {}
    changed = await db.fetch_one(
        "UPDATE mcp_intake_requests SET evidence=%s, updated_at=now() WHERE id=%s AND evidence=%s RETURNING id",
        (Jsonb({**{k: v for k, v in evidence.items() if k != "approval_proposal"}, "local_run": spec}),
         request_id, Jsonb(evidence)))
    if not changed:
        raise HTTPException(409, "신청이 변경되었습니다. 다시 열어 확인하세요.")
    return {"local_run": spec, "message": f"PC 격리 실행 · {spec['image'].split('@')[0]}"}


@app.post("/api/mcp-requests/{request_id}/approval-preview")
async def preview_intake_approval(request_id: UUID, request: ApprovalPreview, user: dict = Depends(admin_caller),
                                  authorization: str | None = Header(default=None)):
    row = await approval_row(request_id, user)
    evidence = row.get("evidence") or {}
    pending = evidence.get("one_click_pending")
    if pending:
        proposal = evidence["approval_proposal"]
        gate = await review.intake_gate({**row, "provenance": proposal["provenance"]})
        found = await gateway_proxy("/api/registry/discover", authorization, "POST",
                                    discovery(proposal["endpoint"], proposal.get("local"), request_id),
                                    timeout=LOCAL_DISCOVER_SECONDS if proposal.get("local") else 45)
        state = await gateway_proxy("/api/registry", authorization)
        if (proposal["basis"] == intake_proposal.basis(row) and proposal["scan_sha256"] == intake_proposal.scan_basis(gate)
                and proposal["expires_at"] > datetime.now(UTC).isoformat()
                and proposal["jurisdiction_pack_enabled"] == residency.enabled(state.get("organization") or {})
                and all(found.get(k) == proposal["catalog"].get(k) for k in ("catalog_hash", "server_name", "version", "protocol_version"))):
            return {"proposal": proposal, "proposal_sha256": intake_proposal.digest(proposal), "pending": pending,
                    "request": row, "gate": gate}
    endpoint = row.get("endpoint_url") or ""
    sid = intake_proposal.server_id(row)
    if row["intake_kind"] == "repository":
        runtime = await db.fetch_one(
            "SELECT endpoint FROM mcp_runtimes WHERE intake_id=%s AND status='ACTIVE' AND source_commit=%s",
            (request_id, row.get("commit_sha")))
        endpoint = runtime["endpoint"] if runtime else ""
    local = None
    if not endpoint and evidence.get("local_run"):
        local = await signed_local_run(evidence["local_run"], sid)
        endpoint = local_jobs.PREFIX + sid
    found = None
    blockers = []
    if endpoint:
        found = await gateway_proxy("/api/registry/discover", authorization, "POST", discovery(endpoint, local, request_id),
                                    timeout=LOCAL_DISCOVER_SECONDS if local else 45)
    else:
        blockers.append({"code": "execution-missing", "message": "실행 계약이 없습니다. 관리 실행을 확인하세요."})
    record = intake_proposal.source_record(row, found) if found else row.get("provenance") or {}
    record, provenance_blocker = await collect_proposal_provenance(row, record)
    if provenance_blocker:
        blockers.append({"code": "provenance-mismatch", "message": provenance_blocker})
    gate = await review.intake_gate({**row, "provenance": record})
    blockers += [b for b in gate["blockers"] if b["code"] != "critical"]
    if row["intake_kind"] == "repository" and (not row.get("validated_at") or not row.get("commit_sha")):
        blockers.append({"code": "validation-missing", "message": "저장소 검증이 끝나지 않았습니다. 검사를 다시 실행하세요."})
    requested = set(row.get("requested_tools") or [])
    tools = [t for t in (found or {}).get("tools", []) if not requested or t["name"] in requested]
    if requested - {t["name"] for t in tools}:
        blockers.append({"code": "tool-missing", "message": "신청한 도구가 사라졌습니다. 새로 신청하세요."})
    if not tools:
        blockers.append({"code": "tools-missing", "message": "도구가 없습니다. 실행 계약을 확인하세요."})
    registry_state = await gateway_proxy("/api/registry", authorization)
    proposed_risk = intake_proposal.risk_input(row, tools)
    scopes = intake_proposal.tool_reviews(row, tools)
    proposal = {"server_id": sid, "endpoint": endpoint, "catalog": found, "provenance": record, "basis": intake_proposal.basis(row),
                "local": local, "local_execution": {k: found.get(k) for k in ("observer_device", "observer_uid", "isolation_scope",
                                                                             "user_mapping", "image_signature")} if local and found else None,
                "scan_sha256": intake_proposal.scan_basis(gate),
                "commit_sha": row.get("commit_sha"), "purpose": row["purpose"], "data_class": proposed_risk["data_class"],
                "risk_input": proposed_risk, "risk": risk_tier.assess(proposed_risk), "tool_reviews": scopes,
                "tools": {t["name"]: intake_proposal.action(t) for t in tools},
                "parameter_constraints": review.derived_constraints({t["name"]: t for t in tools}, scopes),
                "supplier_assurance": {k: v for k, v in intake_proposal.supplier(row).items()
                                       if k in supplier_assurance.ASSURANCE_FIELDS},
                "supplier_metadata": intake_proposal.supplier(row),
                "jurisdiction_pack_enabled": residency.enabled(registry_state.get("organization") or {}),
                "expires_at": (datetime.now(UTC) + timedelta(minutes=15)).isoformat(), "blockers": blockers}
    # Persist precisely the display, without approving it. A concurrent review cannot silently replace it.
    changed = await db.fetch_one(
        """UPDATE mcp_intake_requests SET evidence=%s WHERE id=%s AND evidence=%s AND status=%s RETURNING id""",
        (Jsonb({**{k: v for k, v in evidence.items() if k not in {"one_click_pending", "one_click_scope"}},
                "approval_proposal": proposal}), request_id, Jsonb(evidence), row["status"]))
    if not changed:
        raise HTTPException(409, "신청이 변경되었습니다. 다시 열어 확인하세요.")
    return {"proposal": proposal, "proposal_sha256": intake_proposal.digest(proposal), "request": row, "gate": gate,
            "local_run_preset": intake_proposal.local_run_preset(row),
            "local_run_status": intake_proposal.local_run_status(row)}


@app.post("/api/mcp-requests/{request_id}/approve-and-register")
async def approve_and_register(request_id: UUID, request: OneClickApproval, user: dict = Depends(admin_caller),
                                authorization: str | None = Header(default=None)):
    # Serialize clicks across service processes. The status/evidence CAS also detects legacy-API edits.
    async with INTAKE_APPROVAL_LOCK, db.transaction() as lock:
        await lock.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (f"intake-one-click:{request_id}",))
        row = await approval_row(request_id, user)
        evidence = row.get("evidence") or {}
        proposal = evidence.get("approval_proposal") or {}
        if not proposal or intake_proposal.digest(proposal) != request.proposal_sha256:
            raise HTTPException(409, "검토 화면이 바뀌었습니다. 다시 열어 확인하세요.")
        pending = evidence.get("one_click_pending")
        if datetime.fromisoformat(proposal["expires_at"]) <= datetime.now(UTC):
            raise HTTPException(409, "검토 기한이 지났습니다. 다시 열어 확인하세요.")
        if proposal["blockers"] or proposal["basis"] != intake_proposal.basis(row):
            raise HTTPException(409, "검증을 통과하지 못했습니다. 검사 결과를 확인하세요.")
        selected = sorted(set(request.tools))
        if not selected or not set(selected) <= set(proposal["tools"]):
            raise HTTPException(422, "신청 범위 안에서 도구를 하나 이상 선택하세요.")
        actions = {name: action for name, action in request.actions.items() if action != proposal["tools"].get(name)}
        # 위험 등급은 제안 분류로 산정했다. 올리면 등급이 낮게 남으므로 낮추기만 받는다.
        if not set(actions) <= set(selected) or any("rwx".index(a) > "rwx".index(proposal["tools"][n]) for n, a in actions.items()):
            raise HTTPException(422, "도구 분류는 선택한 도구에서 제안값 이하로만 바꿀 수 있습니다.")
        assurance = {**proposal["supplier_assurance"], **request.supplier_assurance}
        if set(assurance) - set(supplier_assurance.ASSURANCE_FIELDS):
            raise HTTPException(422, "공급자 정보 항목을 확인하세요.")
        errors = supplier_assurance.validate(assurance, required=False)
        try:
            location = residency.normalize(request.residency)
            residency.require_location(location, proposal["data_class"], {"jurisdiction_pack_enabled": proposal["jurisdiction_pack_enabled"]})
        except ValueError as exc:
            errors.append(str(exc))
        if errors:
            raise HTTPException(422, " / ".join(errors))
        scope = {"proposal_sha256": request.proposal_sha256, "tools": selected, **({"actions": actions} if actions else {}),
                 "valid_days": request.valid_days,
                 "supplier_assurance": assurance, "residency": location,
                 "valid_until": pending["scope"]["valid_until"] if pending else (
                     datetime.now(UTC) + timedelta(days=request.valid_days)).isoformat()}
        if pending and pending["scope"] != scope:
            raise HTTPException(409, "1차 승인 범위와 다릅니다. 같은 범위를 확인하세요.")
        state = await gateway_proxy("/api/registry", authorization)
        if proposal["jurisdiction_pack_enabled"] != residency.enabled(state.get("organization") or {}):
            raise HTTPException(409, "관할 규칙이 바뀌었습니다. 다시 열어 확인하세요.")
        found = await gateway_proxy("/api/registry/discover", authorization, "POST",
                                    discovery(proposal["endpoint"], proposal.get("local"), request_id),
                                    timeout=LOCAL_DISCOVER_SECONDS if proposal.get("local") else 45)
        if any(found.get(k) != proposal["catalog"].get(k) for k in ("catalog_hash", "server_name", "version", "protocol_version")):
            raise HTTPException(409, "검토 후 계약이 바뀌었습니다. 다시 열어 확인하세요.")
        current = {**row, "provenance": proposal["provenance"]}
        try:
            keys = (artifact_provenance.trust_keys(os.getenv("MCP_PROVENANCE_TRUST_KEYS_FILE", ""))
                    if (proposal["provenance"].get("verification") or {}).get("attestation") else {})
        except (OSError, ValueError, TypeError) as exc:
            raise HTTPException(409, "출처 증명 신뢰 키를 확인할 수 없습니다.") from exc
        proof = artifact_provenance.verify_source_attestation(
            proposal["provenance"], str(((proposal["provenance"].get("artifact") or {}).get("sha256") or "")), keys)
        if blocker := artifact_provenance.blocking_reason(proof):
            raise HTTPException(409, f"출처 증명 재검증에서 보류했습니다: {blocker}")
        gate = await review.intake_gate(current)
        if (intake_proposal.scan_basis(gate) != proposal["scan_sha256"]
                or any(b["code"] != "critical" for b in gate["blockers"])):
            raise HTTPException(409, "검사 결과가 유효하지 않습니다. 다시 검사하세요.")
        critical = (gate.get("critical") or {}).get("count", 0)
        reason = request.critical_reason.strip() or (pending or {}).get("critical_reason", "")
        if critical and len(reason) < review.RISK_ACCEPTANCE_MIN_REASON:
            raise HTTPException(422, "치명적 발견이 있습니다. 수용 사유를 10자 이상 입력하세요.")
        assessed = proposal["risk"]
        solo_mode, solo = review.solo_mode_enabled(), review.solo_operator(user)  # D-188: recorded per approval, never counted
        approvers = []
        if pending:
            for actor in pending["approvers"]:
                if not await review.same_person(actor, row["submitted_by"]) and not any(
                        [await review.same_person(actor, seen) for seen in approvers]):
                    approvers.append(actor)
        if not any([await review.same_person(user["principal"], seen) for seen in approvers]):
            approvers.append(user["principal"])
        if assessed.get("tier") not in risk_tier.APPROVAL:
            raise HTTPException(409, "위험 등급을 산정하지 못했습니다. 다시 열어 확인하세요.")
        # D-189: the same rule the separate approval route applies. Very high asks every click for a written reason.
        risk_reason = request.risk_reason.strip()
        verdict, message = risk_tier.decide(assessed["tier"], len(approvers), risk_reason)
        if verdict == "refuse":
            raise HTTPException(422, message)
        risk_reasons = ({**((pending or {}).get("risk_reasons") or {}), user["principal"]: risk_reason}
                        if risk_tier.APPROVAL[assessed["tier"]]["reason"] == "required" else {})
        if verdict == "cosign":
            pending = {"scope": scope, "approvers": approvers, "critical_reason": reason, "risk_reasons": risk_reasons}
            changed = await review.transition(
                "UPDATE mcp_intake_requests SET evidence=%s WHERE id=%s AND evidence=%s AND status=%s RETURNING id,status",
                (Jsonb({**evidence, "one_click_pending": pending}), request_id, Jsonb(evidence), row["status"]),
                kind="intake-one-click", outcome="recorded", target_kind="intake", target_id=request_id,
                actor=user["principal"], applicant=row["submitted_by"],
                scope={**pending, "solo_mode": solo_mode, "solo_operator": solo})
            if not changed:
                raise HTTPException(409, "신청이 변경되었습니다. 다시 열어 확인하세요.")
            return {"pending": True, "message": "다른 관리자의 승인을 기다리고 있습니다."}
        if critical and not (gate.get("critical") or {}).get("covered"):
            await review.accept_risk(request_id, user["principal"], reason, min(request.valid_days, review.RISK_ACCEPTANCE_MAX_DAYS))
        tools = {name: actions.get(name, proposal["tools"][name]) for name in selected}
        reviews = {name: proposal["tool_reviews"][name] for name in selected}
        registration = IntakeRegistration(server_id=proposal["server_id"], endpoint=proposal["endpoint"],
            catalog_hash=found["catalog_hash"], tools=tools, data_class=proposal["data_class"], valid_days=request.valid_days,
            poisoning_ack=True, tool_reviews=reviews, residency=location, local=proposal.get("local"))
        risk_record = {**assessed, "approvers": approvers, "written_reason": len(risk_reason) >= risk_tier.MIN_REASON,
                       "reasons": risk_reasons, "solo_mode": solo_mode, "solo_operator": solo}
        updated = {**evidence, "supplier_assurance": assurance, "risk_assessment": risk_record, "one_click_scope": scope,
                   "supplier_assurance_unconfirmed": supplier_assurance.unconfirmed(assurance),
                   "one_click_pending": {"scope": scope, "approvers": approvers, "critical_reason": reason,
                                         "risk_reasons": risk_reasons}}
        record = dict(proposal["provenance"])
        internal_url = row.get("internal_repo_url")
        if row["intake_kind"] == "remote-endpoint":
            contract = {"registration": registration.model_dump(), "allowed_principals": [row["submitted_by"]],
                        "parameter_constraints": {n: proposal["parameter_constraints"][n] for n in selected},
                        "reviewed_by": user["principal"], "reviewed_at": datetime.now(UTC).isoformat(),
                        "valid_until": scope["valid_until"],
                        "advertised_name": found["server_name"], "version": found["version"],
                        "protocol_version": found["protocol_version"], "tools": {t["name"]: t for t in found["tools"] if t["name"] in tools},
                        "code_scan_performed": False}
            updated.update(remote_contract=contract, remote_approval={"actor": user["principal"],
                "review_digest": core.canonical_hash(contract), "at": datetime.now(UTC).isoformat(), "code_scan_performed": False})
        else:
            try:
                internal_url, checked = await publish_internal_repo(current)
            except ProvenanceMismatch as exc:
                raise HTTPException(409, "배포 파일 대조에 실패했습니다. 다시 검사하세요.") from exc
            # The preview's evidence stays on the record; this click's re-verification outranks the preview's result.
            record["verification"] = {**(record.get("verification") or {}), "provenance_status": proof["status"],
                                      "provenance_reason": proof["reason"], "provenance_keyid": proof.get("keyid"),
                                      **checked, "by": user["principal"], "at": datetime.now(UTC).isoformat()}
        changed = await review.transition(
            """UPDATE mcp_intake_requests SET status='APPROVED', evidence=%s, provenance=%s, risk_input=%s,
                      internal_repo_url=%s, reviewed_by=%s, reviewed_at=now(), updated_at=now()
                 WHERE id=%s AND evidence=%s AND status IN ('HOLD','VALIDATED','REMOTE_REVIEWED','APPROVED') RETURNING id,status""",
            (Jsonb(updated), Jsonb(record), Jsonb(proposal["risk_input"]), internal_url, user["principal"], request_id, Jsonb(evidence)),
            kind="intake-one-click", outcome="approved", target_kind="intake", target_id=request_id,
            actor=user["principal"], applicant=row["submitted_by"], reason=reason or None,
            scope={**scope, "catalog_hash": found["catalog_hash"], "approvers": approvers, "tool_reviews": reviews,
                   "solo_mode": solo_mode, "solo_operator": solo,
                   "supplier_assurance_unconfirmed": supplier_assurance.unconfirmed(assurance)})
        if not changed:
            raise HTTPException(409, "신청이 변경되었습니다. 다시 열어 확인하세요.")
        if row["intake_kind"] == "remote-endpoint":
            await review.record_event("contract-review", "recorded", "intake", request_id, user["principal"],
                applicant=row["submitted_by"], scope={"catalog_hash": found["catalog_hash"], "tools": tools,
                    "parameter_constraints": contract["parameter_constraints"], "allowed_principals": contract["allowed_principals"]})
        return await register_mcp_request(request_id, registration, authorization)


@app.post("/api/mcp-requests/{request_id}/reject")
async def reject_mcp_request(request_id: UUID, request: IntakeRejection, authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "요청 거부는 관리자만 할 수 있습니다.")
    row = await review.transition(
        """UPDATE mcp_intake_requests
           SET status='REJECTED', review_note=%s, reviewed_by=%s, reviewed_at=now(), updated_at=now()
           WHERE id=%s AND status IN ('HOLD','VALIDATION_QUEUED','VALIDATED','REMOTE_REVIEWED','FAILED')
           RETURNING id, status, review_note, reviewed_by, reviewed_at, submitted_by""",
        (request.note.strip(), user["principal"], request_id),
        kind="intake-reject", outcome="rejected", target_kind="intake", target_id=request_id,
        actor=user["principal"], reason=request.note.strip(),
    )
    if not row:
        raise HTTPException(409, "승인 전(보류·검증 대기·검증 완료·검증 실패) 요청만 거부할 수 있습니다.")
    return {"request": row}


@app.get("/api/risk-catalog")
async def risk_catalog(authorization: str | None = Header(default=None)):
    """AI-Infra-Guard 위험 범주와 이 조직 통제의 매핑표.

    로그인한 사람이면 누구나 본다. 발견 내역이 아니라 분류 기준이고, 직원이
    "내가 신청한 서버가 어떤 기준으로 검사되는가"를 알 수 없으면 도입 요청서의
    '도입 목적'은 형식이 된다.
    """
    await current_identity(authorization)
    return await gateway_proxy("/api/risk-catalog", authorization)


@app.get("/api/consents")
async def my_consents(authorization: str | None = Header(default=None)):
    """POL-08: only the person's own consents; nobody decides them on another's behalf."""
    user = await current_identity(authorization)
    return {"consents": await consent.mine(user["principal"])}


class ConsentDecision(StrictModel):
    decision: Literal["grant", "deny", "revoke"]


class ServerConsentDecision(ConsentDecision):
    consent_ids: list[int] = Field(min_length=1)


@app.post("/api/consents/server/{server_id}")
async def decide_server_consent(server_id: str, request: ServerConsentDecision,
                                authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    try:
        rows = await consent.decide_server(server_id, request.consent_ids, user["principal"], request.decision)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"consents": rows}


@app.post("/api/consents/{consent_id}")
async def decide_consent(consent_id: int, request: ConsentDecision, authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    row = await consent.decide(consent_id, user["principal"], request.decision)
    if not row:
        raise HTTPException(409, "이미 처리됐거나 본인의 동의 요청이 아닙니다.")
    return row


@app.get("/approvals")
async def approvals(authorization: str | None = Header(default=None)):
    user = await current_identity(authorization)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "합성 관리자 계정이 필요합니다.")
    pending, history = await asyncio.gather(db.fetch_all(
        """SELECT a.id, a.requested_by, a.created_at, a.expires_at,
                  (a.requested_by = %s OR p.user_id = %s) AS own,
                  a.request_payload->>'server_id' AS server_id, a.request_payload->>'tool' AS tool,
                  a.request_payload->'arguments' AS arguments, a.request_payload->'client' AS client,
                  p.display_name, p.department, d.summary, d.policy_id, d.reason, d.data_class, d.action,
                  a.explanation, d.residency_targets
             FROM approvals a
             LEFT JOIN principals p ON p.token = a.requested_by
             LEFT JOIN LATERAL (SELECT summary, policy_id, reason, data_class, action,
                                      policy_input#>'{pac,facts,residency,targets}' AS residency_targets FROM decisions
                                 WHERE approval_id = a.id ORDER BY id LIMIT 1) d ON true
            WHERE a.status='PENDING' AND a.expires_at>now() ORDER BY a.created_at DESC LIMIT 30""",
        (user["principal"], user.get("user_id"))),
        # Decided (or lapsed) requests: what the queue turned into.
        db.fetch_all(
        """SELECT a.id, a.requested_by, a.created_at, a.reviewed_at, a.reviewed_by,
                  CASE WHEN a.revoked_at IS NOT NULL THEN 'REVOKED' WHEN a.status='PENDING' THEN 'EXPIRED' ELSE a.status END AS status,
                  a.request_payload->>'server_id' AS server_id, a.request_payload->>'tool' AS tool,
                  p.display_name, p.department, a.explanation,
                  (a.reviewed_by = %s) AS can_revoke
             FROM approvals a LEFT JOIN principals p ON p.token = a.requested_by
            WHERE a.status <> 'PENDING' OR a.expires_at <= now()
            ORDER BY COALESCE(a.reviewed_at, a.expires_at) DESC LIMIT 50""", (user["principal"],)))
    for row in pending:
        if row.get("explanation"):
            row["arguments"] = row["explanation"]["arguments"]
            row["summary"] = row["explanation"]["summary"]
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
GATEWAY_PROXY_PREFIXES = ("overview", "latency", "activity", "registry", "health", "termination/", "approvals/",
                          "catalog/", "enforcement", "monitor/", "audit/", "policy/", "endpoint/",
                          "supply-chain/", "risk-catalog", "lab/", "dispatch-intents", "suspensions", "user-suspensions/")
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
        client = connections.shared("gateway", lambda: httpx.AsyncClient(timeout=120))
        response = await client.request(
            request.method, f"{GATEWAY_URL}/api/{path}", params=dict(request.query_params),
            content=body or None, headers={"Authorization": authorization or "",
                                           "Content-Type": request.headers.get("content-type", "application/json")})
    except httpx.HTTPError as exc:
        raise HTTPException(503, "게이트웨이에 연결할 수 없습니다. 잠시 후 다시 시도하세요.") from exc
    forwarded = {name: response.headers[name] for name in ("X-Account-Status", "X-Registry-SHA256") if name in response.headers}
    return Response(response.content, status_code=response.status_code,
                    media_type=response.headers.get("content-type", "application/json"),
                    headers=forwarded or None)
