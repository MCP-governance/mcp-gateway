from __future__ import annotations

import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from psycopg.types.json import Jsonb

from . import core, db, decommission, dispatch, disposal, endpoint_plane, local_jobs, ops_response, privacy, secret_scan, upstream, user_suspend
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
from .agent_contract import CONSOLE_SCOPE, ResidencyFields, ToolReview, authenticate, authenticated_user
from .release import build_info, policy_info
from . import activity, audit, incidents, registry, residency, retention, review, risk_tier, siem, supplier_assurance, tool_sunset

AGENT_SERVICE_URL = os.getenv("AGENT_SERVICE_URL", "http://agent-service:8000")
# "오늘" is the operator's day. The DB session runs in UTC, so date_trunc('day', now())
# reset the Console's counters at 09:00 KST.
TODAY = "(date_trunc('day', now() AT TIME ZONE 'Asia/Seoul') AT TIME ZONE 'Asia/Seoul')"

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


async def _error_detail(detail):
    text = detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False, default=str)
    safe = await secret_scan.redact_error(text)
    return detail if safe == text else secret_scan.ERROR_REDACTED


class RequireBearer:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            authorization = dict(scope.get("headers") or []).get(b"authorization", b"").decode("latin-1")
            try:
                scope = dict(scope, authenticated_mcp_user=await authenticated_user(authorization or None, require_mcp=True))
            except HTTPException as exc:
                detail = await _error_detail(exc.detail)
                if (exc.headers or {}).get("X-Endpoint-Policy") == "ENDPOINT-MANAGED-001":
                    _, claims = authenticate(authorization)
                    await db.execute(
                        """INSERT INTO endpoint_managed_events(endpoint_id,owner_token,kind,detail)
                           SELECT %s,p.token,'mcp-auth-denied',%s FROM principals p WHERE p.user_id=%s""",
                        (claims.get("device_id"), Jsonb({"reason": detail, "path": scope.get("path", "")[:160]}), claims["sub"]))
                challenge = f'Bearer resource_metadata="{RESOURCE_METADATA_URL}"'
                if authorization:
                    challenge += ', error="invalid_token"'
                headers = dict(exc.headers or {})
                if exc.status_code == 401:
                    headers["WWW-Authenticate"] = challenge
                body = {"detail": detail}
                if headers.get("X-Endpoint-Policy"):
                    body["policy_id"] = headers["X-Endpoint-Policy"]
                await JSONResponse(body, status_code=exc.status_code, headers=headers)(scope, receive, send)
                return
            # The SDK routes on the first Mcp-Session-Id (Starlette Headers.get) while dict() keeps
            # the last, so with two the session ServerPath checks is not the one the SDK serves.
            session_ids = [value for key, value in scope.get("headers") or [] if key == b"mcp-session-id"]
            if len(session_ids) > 1:
                await JSONResponse({"detail": "Mcp-Session-Id 헤더는 하나만 보낼 수 있습니다."},
                                   status_code=400)(scope, receive, send)
                return
            session_id = session_ids[0].decode("latin-1") if session_ids else ""
        status = None

        async def response(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                issued = dict(message.get("headers") or []).get(b"mcp-session-id", b"").decode("latin-1")
                if issued and scope["type"] == "http":
                    user = scope["authenticated_mcp_user"]
                    claims = user.get("claims") or {}
                    if claims.get("jti"):
                        await upstream.register_downstream(issued, user["principal"], claims["jti"],
                                                           claims.get("device_id"), scope.get("mcp_server"))
            await send(message)

        try:
            await self.app(scope, receive, response)
        finally:
            if scope["type"] == "http" and scope.get("method") == "DELETE" and status in {200, 202, 204}:
                user = scope["authenticated_mcp_user"]
                jti = (user.get("claims") or {}).get("jti")
                if session_id and jti:
                    await upstream.close_downstream(user["principal"], (session_id, jti))


class ServerPath:
    """`/mcp/<server>/` is the same MCP app scoped to one registered server (D-30):
    the harness's managed config lists one URL per server, so the employee sees the
    servers under their own names. The name comes from the URL only; an unknown one
    is 404 instead of silently falling back to the aggregate endpoint."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            root = scope.get("root_path", "")
            path = scope["path"][len(root):] if scope["path"].startswith(root) else scope["path"]
            name = path.strip("/").split("/", 1)[0]
            if name:
                if name not in registry.servers():
                    # Authentication precedes this middleware. Record the actual
                    # connection refusal, never a fabricated tool invocation.
                    user = scope["authenticated_mcp_user"]
                    headers = dict(scope.get("headers") or [])
                    info = {}
                    method = scope.get("method", "unknown")
                    if method == "POST":
                        body = bytearray()
                        try:
                            async with asyncio.timeout(2):
                                while True:
                                    message = await receive()
                                    if message["type"] != "http.request":
                                        break
                                    body.extend(message.get("body", b""))
                                    if len(body) > 8192 or not message.get("more_body"):
                                        break
                            if len(body) <= 8192:
                                request = json.loads(body)
                                if isinstance(request, dict):
                                    method = str(request.get("method") or method)[:80]
                                    params = request.get("params") or {}
                                    if method == "initialize" and isinstance(params, dict):
                                        candidate = params.get("clientInfo")
                                        if isinstance(candidate, dict):
                                            info = {key: str(candidate.get(key) or "")[:60] for key in ("name", "version")}
                        except (ValueError, TimeoutError, RecursionError):
                            pass  # a body we cannot read still leaves the refusal on record
                    claims = user.get("claims") or {}
                    agent = headers.get(b"user-agent", b"").decode("latin-1")[:120]
                    decision_id = await core.record_connection_denial(user, name, method, {
                        "harness": {**info, "user_agent": agent}, "agent": info.get("name") or agent,
                        "workstation": claims.get("client_id"), "oauth_client": claims.get("client_id"),
                        "token_jti": claims.get("jti"), "endpoint": name[:120],
                    })
                    await JSONResponse({"detail": await _error_detail(f"등록되지 않은 MCP 서버: {name[:40]}"),
                                        "decision": "Block", "policy_id": "MCP-REGISTRY-001",
                                        "decision_id": decision_id}, status_code=404)(scope, receive, send)
                    return
                scope["mcp_server"] = name
                scope = dict(scope, path=root + "/", raw_path=(root + "/").encode(), mcp_server=name)
            # After the registry check, so a removed server keeps its MCP-REGISTRY-001 record.
            # RequireBearer already refused a second Mcp-Session-Id.
            session_id = next((value.decode("latin-1") for key, value in scope.get("headers") or []
                               if key == b"mcp-session-id"), "")
            user = scope["authenticated_mcp_user"]
            claims = user.get("claims") or {}
            if session_id and not await upstream.active_downstream(session_id, user["principal"],
                                                                   claims.get("device_id"), name or None):
                # MCP transport: a session the server no longer serves is answered 404 and the
                # client starts a new one with initialize. A session the gateway never bound
                # (e.g. opened before this binding existed) is that case alone, not a refusal.
                refusal = await upstream.downstream_refusal(session_id)
                body = {"detail": "MCP 세션이 종료됐습니다. 새 세션을 시작하세요."}
                if refusal:
                    decision_id = None
                    if scope.get("method") != "DELETE":  # closing an ended session is not an access attempt
                        agent = dict(scope.get("headers") or []).get(b"user-agent", b"").decode("latin-1")[:120]
                        decision_id = await core.record_connection_denial(
                            user, name or None, scope.get("method", "unknown"), {
                                "harness": {"user_agent": agent}, "agent": agent,
                                "workstation": claims.get("client_id"), "oauth_client": claims.get("client_id"),
                                "token_jti": claims.get("jti"), "endpoint": name[:120],
                            }, **refusal)
                    body.update(decision="Block", policy_id=refusal["policy_id"], decision_id=decision_id)
                await JSONResponse(body, status_code=404)(scope, receive, send)
                return
        await self.app(scope, receive, send)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RejectRequest(StrictModel):
    note: str = Field(min_length=1, max_length=500)
    evidence_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class ApprovalEvidence(StrictModel):
    evidence_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reason: Literal["scope_confirmed"] = "scope_confirmed"


class IntentResolve(StrictModel):
    outcome: Literal["executed", "not_executed"]
    note: str = Field(default="", max_length=500)


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


async def admin_caller(authorization: str | None = Header(default=None)) -> dict:
    """An administrative API asks for the role *and* for an interactive sign-in.

    The same person also holds an `mcp` token, which `bob-sso` leaves in a file on their
    PC for the harnesses to read. Accepting it here would make every local process on an
    administrator's machine able to approve calls and change enforcement in their name.
    """
    user = await authenticated_user(authorization, require_scope=CONSOLE_SCOPE)
    if "admin" not in user["roles"]:
        raise HTTPException(403, "합성 관리자 계정이 필요합니다.")
    return user


@asynccontextmanager
async def lifespan(_: FastAPI):
    await bootstrap()
    watcher = asyncio.create_task(catalog_watch())
    pool_watcher = asyncio.create_task(upstream.maintain_pool())
    operations = asyncio.create_task(ops_response.watch(OPA_URL))
    tombstones = asyncio.create_task(disposal.watch())
    try:
        async with gateway_mcp.session_manager.run():
            yield
    finally:
        watcher.cancel()
        pool_watcher.cancel()
        operations.cancel()
        tombstones.cancel()
        await asyncio.gather(watcher, pool_watcher, operations, tombstones, return_exceptions=True)
        await upstream.close_pool()
        await db.close()


app = FastAPI(title="MCP Governance Security Gateway", version="1.1.0", lifespan=lifespan)


@app.exception_handler(StarletteHTTPException)
async def public_http_error(request, exc):
    return JSONResponse({"detail": await _error_detail(exc.detail)}, status_code=exc.status_code, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def public_validation_error(request, exc):
    # Validation errors echo rejected inputs, which may themselves be credentials.
    return JSONResponse({"detail": await _error_detail(jsonable_encoder(exc.errors()))}, status_code=422)


class OpsResume(StrictModel):
    note: str = Field(min_length=4, max_length=500)


@app.get("/api/ops/status")
async def ops_status(_: dict = Depends(admin_caller)) -> dict:
    return {"siem": await siem.status(),
            "suspensions": await db.fetch_all("SELECT * FROM ops_suspensions ORDER BY id DESC LIMIT 100"),
            "image_scans": await db.fetch_all("SELECT * FROM runtime_image_scans ORDER BY id DESC LIMIT 100"),
            "alert_self_tests": await db.fetch_all("SELECT * FROM alert_self_tests ORDER BY id DESC LIMIT 20"),
            "alerts": await db.fetch_all("SELECT * FROM ops_alerts WHERE NOT synthetic ORDER BY id DESC LIMIT 100"),
            "disposal": await db.fetch_one("SELECT * FROM worker_heartbeats WHERE worker='disposal'")}


@app.post("/api/ops/servers/{server_id}/resume")
async def ops_resume(server_id: str, request: OpsResume, user: dict = Depends(admin_caller)) -> dict:
    try:
        return await ops_response.resume(server_id, user["principal"], request.note)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


class SuspendRequest(StrictModel):
    user_token: str = Field(min_length=1, max_length=200)
    server_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=4, max_length=500)


@app.get("/api/suspensions")
async def suspensions(_: dict = Depends(admin_caller)) -> dict:
    return {"suspensions": await user_suspend.listing()}


@app.post("/api/suspensions")
async def suspend_use(request: SuspendRequest, user: dict = Depends(admin_caller)) -> dict:
    try:
        return await user_suspend.suspend(request.user_token, request.server_id, user["principal"], request.reason)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/suspensions/{suspension_id}/resume")
async def resume_use(suspension_id: int, request: OpsResume, user: dict = Depends(admin_caller)) -> dict:
    try:
        return await user_suspend.resume(suspension_id, user["principal"], request.note)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


class UserSuspendAllRequest(StrictModel):
    user_token: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=4, max_length=500)


class UserResumeAllRequest(StrictModel):
    user_token: str = Field(min_length=1, max_length=200)
    note: str = Field(min_length=4, max_length=500)


@app.post("/api/user-suspensions/stop-all")
async def suspend_all_use(request: UserSuspendAllRequest, user: dict = Depends(admin_caller)) -> dict:
    try:
        return await user_suspend.suspend_all(request.user_token, user["principal"], request.reason)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/user-suspensions/resume-all")
async def resume_all_use(request: UserResumeAllRequest, user: dict = Depends(admin_caller)) -> dict:
    return await user_suspend.resume_all(request.user_token, user["principal"], request.note)


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
    policy = await policy_info(OPA_URL)
    opa_ok, jaeger_ok, analyzer_ok, anonymizer_ok = await asyncio.gather(
        _probe(OPA_URL.rsplit("/v1/", 1)[0] + "/health?bundles=true"),
        _probe(JAEGER_QUERY_URL) if JAEGER_QUERY_URL else _absent(),
        _probe(privacy.ANALYZER + "/health"),
        _probe(privacy.ANONYMIZER + "/health"),
    )
    try:
        rows = await db.fetch_all("SELECT id, status FROM mcp_servers ORDER BY id")
        db_ok = True
    except Exception:
        rows, db_ok = [], False
    servers = {row["id"]: row["status"] for row in rows if row["id"] in registry.servers()}
    # Presidio is required: without it outbound calls are refused (P-DATA-INSPECTION-001)
    # and executed results are withheld (MCP-OUTPUT-001), so "ok" would be untrue.
    components = {"gateway": True, "postgresql": db_ok, "opa": opa_ok, "jaeger": jaeger_ok,
                  "presidio_analyzer": analyzer_ok, "presidio_anonymizer": anonymizer_ok}
    required = [value for value in components.values() if value is not None]
    return {"status": "ok" if all(required) and policy["matches"] else "degraded", "components": components,
            "build": build_info(), "policy": policy,
            # Upstream state is reported, not required: one server in DRIFT must not
            # make the control point "unhealthy" - that is the Gateway doing its job.
            "mcp_servers": {"ready": sum(1 for v in servers.values() if v == "READY"),
                            "total": len(servers), "status": servers}}


@app.get("/api/state")
async def state(user: dict = Depends(admin_caller)) -> dict:
    servers, tools, decisions, approvals, reports, principals, policy = await asyncio.gather(
        db.fetch_all("SELECT * FROM mcp_servers ORDER BY id"),
        db.fetch_all("""SELECT server_id, name, action, enabled,
                               (approved_schema_hash = observed_schema_hash
                                AND (approved_output_schema_hash IS NULL
                                     OR approved_output_schema_hash=observed_output_schema_hash)) AS schema_ok
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
                                AND approved_description_hash = observed_description_hash
                                AND (approved_output_schema_hash IS NULL
                                     OR approved_output_schema_hash=observed_output_schema_hash)
                                AND COALESCE((SELECT c.exact_match OR (c.restricted_tools IS NOT NULL AND NOT t.name=ANY(c.restricted_tools))
                                     FROM catalog_snapshots c WHERE c.server_id=t.server_id ORDER BY c.id DESC LIMIT 1),false)) AS contract_ok
                          FROM mcp_tools t ORDER BY server_id, name"""),
        db.fetch_all("SELECT * FROM usage_relationships ORDER BY id"),
    )
    catalog_servers = registry.servers()
    doc = registry.runtime()
    console = doc["servers"]
    sunset = await tool_sunset.snapshot()
    return {"catalog_version": registry.catalog_version(), "tool_sunset": sunset,
            "classification": registry.catalog().get("classification", {}),
            "organization": registry.catalog().get("organization", {}),
            "servers": [{**row, "residency": residency.location(catalog_servers[row["id"]], registry.catalog().get("organization", {}))}
                        for row in servers if row["id"] in catalog_servers],
            "tools": tools, "usage_relationships": relationships,
            # D-49: which servers came from a Console registration, and until when they may be used.
            "registrations": {sid: {key: spec.get(key) for key in ("valid_until", "intake_id", "registered_by", "registered_at",
                                                                    "data_class", "tools", "tool_reviews", "provenance",
                                                                    "allowed_principals", "supplier_assurance", "supplier_assurance_unconfirmed", "residency", "residency_review", "risk_assessment")}
                                  | {"risk_review": risk_tier.legacy_review(spec, doc.get("risk_tier_grace_started_at"))}
                              for sid, spec in console.items() if sid not in registry.reviewed_servers()}}


@app.get("/api/registry/export")
async def registry_export(format: Literal["json", "csv"] = Query("json"), user: dict = Depends(admin_caller)) -> Response:
    """Download the approved intake registry from the same runtime ledger shown in Console."""
    runtime_doc = registry.runtime()
    content, digest = (supplier_assurance.export_csv(runtime_doc) if format == "csv"
                       else supplier_assurance.export_json(runtime_doc))
    media_type = "text/csv; charset=utf-8" if format == "csv" else "application/json"
    return Response(content, media_type=media_type,
                    headers={"X-Registry-SHA256": digest,
                             "Content-Disposition": f'attachment; filename="mint-registry.{format}"'})


@app.get("/api/overview")
async def overview(user: dict = Depends(admin_caller)) -> dict:
    """Everything the first Console screen shows, in one round trip."""
    today, per_server, stations, alerts, approvals, intake_actions, cases, series, flows, execution = await asyncio.gather(
        db.fetch_all(f"""SELECT decision, count(*) AS n FROM decisions d
                          WHERE created_at > {TODAY} AND {decommission.REAL_CALL} GROUP BY decision"""),
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
                               (SELECT max(d.created_at) FROM decisions d WHERE d.client->>'workstation' = a.endpoint_id
                                   AND COALESCE(d.client->>'event_kind','tools/call')='tools/call') AS last_call,
                               (SELECT d.client->'harness'->>'name' FROM decisions d
                                 WHERE d.client->>'workstation' = a.endpoint_id AND d.client->'harness'->>'name' IS NOT NULL
                                   AND COALESCE(d.client->>'event_kind','tools/call')='tools/call'
                                 ORDER BY d.id DESC LIMIT 1) AS harness,
                               (SELECT count(*) FROM decisions d WHERE d.client->>'workstation' = a.endpoint_id
                                   AND d.created_at > now() - interval '24 hours'
                                   AND COALESCE(d.client->>'event_kind','tools/call')='tools/call') AS calls
                          FROM endpoint_agents a LEFT JOIN principals p ON p.token = a.owner_token
                         WHERE a.status='active' ORDER BY a.endpoint_id"""),
        db.fetch_all(f"""SELECT decision, policy_id, count(*) AS n FROM decisions d
                          WHERE created_at > now() - interval '24 hours' AND decision IN ('Block','Alert')
                            AND {decommission.REAL_CALL}
                            AND COALESCE(d.client->>'event_kind','tools/call')='tools/call'
                         GROUP BY decision, policy_id ORDER BY n DESC LIMIT 8"""),
        db.fetch_one("SELECT count(*) AS n FROM approvals WHERE status='PENDING' AND expires_at > now()"),
        db.fetch_one("""SELECT count(*) AS n FROM mcp_intake_requests
                          WHERE status IN ('HOLD','VALIDATED','REMOTE_REVIEWED','FAILED')
                             OR (status='APPROVED' AND registered_server_id IS NULL)"""),
        decommission.summary(),
        # Charts: calls per hour by decision, and who called what (harness -> server -> decision).
        db.fetch_all(f"""SELECT date_trunc('hour', created_at) AS hour, decision, count(*) AS n FROM decisions d
                          WHERE created_at > now() - interval '24 hours' AND {decommission.REAL_CALL}
                            AND COALESCE(d.client->>'event_kind','tools/call')='tools/call'
                         GROUP BY 1, 2 ORDER BY 1"""),
        db.fetch_all(f"""SELECT COALESCE(NULLIF(d.client->'harness'->>'name', ''), NULLIF(d.client->>'agent', ''), 'unknown') AS harness,
                               d.server_id AS server, d.decision, count(*) AS n
                          FROM decisions d WHERE created_at > now() - interval '24 hours' AND {decommission.REAL_CALL}
                            AND COALESCE(d.client->>'event_kind','tools/call')='tools/call'
                         GROUP BY 1, 2, 3"""),
        db.fetch_one(f"""SELECT count(*) FILTER (WHERE COALESCE(client->>'event_kind','tools/call')='mcp-connection') AS connections,
                               count(*) FILTER (WHERE COALESCE(client->>'event_kind','tools/call')='tools/call') AS tool_calls,
        count(*) FILTER (WHERE COALESCE(client->>'event_kind','tools/call')='tools/call'
                         AND decision='Block') AS blocked,
                               count(*) FILTER (WHERE upstream_executed) AS executed,
                               count(*) FILTER (WHERE upstream_attempted AND NOT upstream_executed) AS unknown,
                               count(*) FILTER (WHERE NOT upstream_attempted AND NOT upstream_executed) AS not_sent,
                               count(*) FILTER (WHERE result_preview->>'disposition'='masked') AS masked,
                               count(*) FILTER (WHERE upstream_executed AND (result_preview->>'disposition'='withheld'
                                                OR policy_id='MCP-OUTPUT-001')) AS withheld
                          FROM decisions d WHERE created_at > {TODAY} AND {decommission.REAL_CALL}"""),
    )
    # decision -> sent? -> executed? -> what came back, for today's tool calls (D-63 Sankey).
    pipeline = await db.fetch_all(f"""SELECT decision, upstream_attempted AS attempted, upstream_executed AS executed,
                                             COALESCE(result_preview->>'disposition',
                                                      CASE WHEN upstream_executed AND policy_id='MCP-OUTPUT-001' THEN 'withheld'
                                                           WHEN upstream_executed THEN 'returned'
                                                           WHEN upstream_attempted THEN 'unknown' ELSE 'not_executed' END) AS response,
                                             count(*) AS n
                                        FROM decisions d WHERE created_at > {TODAY} AND {decommission.REAL_CALL}
                                         AND COALESCE(client->>'event_kind','tools/call')='tools/call'
                                       GROUP BY 1, 2, 3, 4""")
    counts = {row["decision"]: int(row["n"]) for row in today}
    return {
        "today": {"total": sum(counts.values()), **{k: counts.get(k, 0) for k in ("Allow", "Alert", "Restrict", "Approval", "Block")}},
        "today_since": datetime.now(ZoneInfo("Asia/Seoul")).replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),
        "servers": per_server, "workstations": stations, "top_policies": alerts,
        "pending_approvals": int(approvals["n"] or 0),
        "intake_actions": int(intake_actions["n"] or 0), "termination": cases,
        "series": series, "flows": flows, "execution": execution, "pipeline": pipeline,
        "enforcement": await enforcement_mode(), "catalog_version": registry.catalog_version(),
    }


# Stage keys written by core._Laps, in path order. Upstream stages are the MCP server's
# share of a call; the rest is the gateway's own processing.
LATENCY_STAGES = ("identity", "reserve", "schema", "inspect_in", "context", "policy",
                  "dispatch", "connect", "list", "recheck", "intent", "call", "close", "inspect_out")
UPSTREAM_STAGES = ("connect", "list", "call", "close")


@app.get("/api/latency")
async def latency(hours: int = Query(24, ge=1, le=168), user: dict = Depends(admin_caller)) -> dict:
    """Where a tools/call spends its time, from the per-stage timings kept with each decision."""
    upstream_ms = " + ".join(f"COALESCE((d.timings->>'{stage}')::float8, 0)" for stage in UPSTREAM_STAGES)
    window = f"""FROM decisions d WHERE d.created_at > now() - make_interval(hours => %s)
                   AND d.timings IS NOT NULL AND d.action <> 'connect' AND {decommission.REAL_CALL}"""
    summary, stages, servers, series = await asyncio.gather(
        db.fetch_one(f"""WITH t AS (SELECT (d.timings->>'total')::float8 AS total, {upstream_ms} AS upstream,
                                          d.timings ? 'call' AS dispatched {window})
                         SELECT count(*) AS calls, count(*) FILTER (WHERE dispatched) AS dispatched,
                                percentile_cont(0.5) WITHIN GROUP (ORDER BY total - upstream) AS gateway_p50,
                                percentile_cont(0.95) WITHIN GROUP (ORDER BY total - upstream) AS gateway_p95,
                                percentile_cont(0.99) WITHIN GROUP (ORDER BY total - upstream) AS gateway_p99,
                                percentile_cont(0.5) WITHIN GROUP (ORDER BY total) AS total_p50,
                                percentile_cont(0.95) WITHIN GROUP (ORDER BY total) AS total_p95,
                                percentile_cont(0.5) WITHIN GROUP (ORDER BY upstream) FILTER (WHERE dispatched) AS upstream_p50,
                                percentile_cont(0.95) WITHIN GROUP (ORDER BY upstream) FILTER (WHERE dispatched) AS upstream_p95
                           FROM t""", (hours,)),
        db.fetch_all(f"""SELECT s.key AS stage, count(*) AS n,
                                percentile_cont(0.5) WITHIN GROUP (ORDER BY s.value::float8) AS p50,
                                percentile_cont(0.95) WITHIN GROUP (ORDER BY s.value::float8) AS p95
                           {window.replace("FROM decisions d", "FROM decisions d, jsonb_each_text(d.timings) s")}
                            AND s.key <> 'total' GROUP BY s.key""", (hours,)),
        db.fetch_all(f"""SELECT d.server_id, count(*) AS n,
                                percentile_cont(0.5) WITHIN GROUP (ORDER BY {upstream_ms}) AS p50,
                                percentile_cont(0.95) WITHIN GROUP (ORDER BY {upstream_ms}) AS p95,
                                count(*) FILTER (WHERE d.policy_id = 'MCP-UPSTREAM-001') AS failed
                           {window} AND d.timings ? 'connect' GROUP BY d.server_id ORDER BY n DESC LIMIT 12""", (hours,)),
        db.fetch_all(f"""WITH t AS (SELECT date_trunc('hour', d.created_at) AS hour,
                                          (d.timings->>'total')::float8 - ({upstream_ms}) AS gateway {window})
                         SELECT hour, count(*) AS n,
                                percentile_cont(0.5) WITHIN GROUP (ORDER BY gateway) AS p50,
                                percentile_cont(0.95) WITHIN GROUP (ORDER BY gateway) AS p95
                           FROM t GROUP BY hour ORDER BY hour""", (hours,)),
    )
    order = {stage: index for index, stage in enumerate(LATENCY_STAGES)}

    def ms(value):
        return None if value is None else round(float(value), 2)
    return {
        "window_hours": hours,
        "calls": int(summary["calls"] or 0), "dispatched": int(summary["dispatched"] or 0),
        "gateway": {key: ms(summary[f"gateway_{key}"]) for key in ("p50", "p95", "p99")},
        "total": {key: ms(summary[f"total_{key}"]) for key in ("p50", "p95")},
        "upstream": {key: ms(summary[f"upstream_{key}"]) for key in ("p50", "p95")},
        "stages": [{"stage": row["stage"], "n": int(row["n"]), "p50": ms(row["p50"]), "p95": ms(row["p95"]),
                    "upstream": row["stage"] in UPSTREAM_STAGES}
                   for row in sorted(stages, key=lambda r: order.get(r["stage"], len(order)))
                   if row["stage"] in order],
        "servers": [{"server_id": row["server_id"], "n": int(row["n"]), "p50": ms(row["p50"]), "p95": ms(row["p95"]),
                     "failed": int(row["failed"])} for row in servers],
        "series": [{"hour": row["hour"].isoformat(), "n": int(row["n"]), "p50": ms(row["p50"]), "p95": ms(row["p95"])}
                   for row in series],
    }


@app.get("/api/activity")
async def activity_feed(after: int = 0, limit: int = 100, decision: str | None = None,
                        server: str | None = None, person: str | None = None,
                        event_kind: Literal["tools/call", "mcp-connection"] | None = None,
                        execution: Literal["executed", "not-sent", "unknown", "withheld", "connection-denied"] | None = None,
                        endpoint: str | None = None, policy: str | None = None,
                        since: datetime | None = None, until: datetime | None = None,
                        page: int = 1, q: str | None = None,
                        user: dict = Depends(caller)) -> dict:
    """Decisions as readable sentences. Admins see everyone; others see themselves."""
    own = None if "admin" in user["roles"] else user["principal"]
    return await activity.recent(after, limit, own, decision, server, person, event_kind, execution,
                                 endpoint, policy, since, until, page, q)


@app.get("/api/activity/analysis")
async def activity_analysis(decision: str | None = None, server: str | None = None,
                            person: str | None = None,
                            event_kind: Literal["tools/call", "mcp-connection"] | None = None,
                            execution: Literal["executed", "not-sent", "unknown", "withheld", "connection-denied"] | None = None,
                            endpoint: str | None = None, policy: str | None = None,
                            since: datetime | None = None, until: datetime | None = None,
                            q: str | None = None, user: dict = Depends(caller)) -> dict:
    own = None if "admin" in user["roles"] else user["principal"]
    return await activity.analysis(own, decision, server, person, event_kind, execution,
                                   endpoint, policy, since, until, q)


@app.get("/.well-known/oauth-protected-resource")
async def protected_resource_metadata() -> dict:
    """RFC 9728. The Gateway's MCP endpoint is a protected resource; employees get
    tokens from the organisation's IdP, never from an upstream MCP server."""
    return {"resource": os.getenv("GATEWAY_PUBLIC_MCP_URL", "http://gateway:8080/mcp/"),
            "authorization_servers": [os.getenv("IDP_ISSUER", "http://agent-service:8000")],
            "bearer_methods_supported": ["header"],
            "resource_name": "MCP Gateway"}


@app.get("/api/policy/matrix")
async def policy_matrix(user: dict = Depends(caller)) -> dict:
    scopes = core.pac.capabilities()
    return {"model": "pac15-capabilities", "pack_version": "pac15-v1",
            "bundle_id": scopes["bundle_id"], "capabilities": scopes["capabilities"],
            "runtime_envelopes": [{"server_id": k, "principals": v.get("allowed_principals", []),
                                   "tools": v.get("tools", {}), "valid_until": v.get("valid_until")}
                                  for k,v in registry.servers().items() if v.get("intake_id")]}


@app.get("/api/policy/ledger")
async def policy_ledger_view(user: dict = Depends(caller)) -> dict:
    """The policy list as the running OPA holds it, ordered by priority."""
    ledger, policy_set, authorization, active = await asyncio.gather(
        core.policy_ledger(refresh=True),
        core.opa_document("policy_set"),
        core.opa_document("authorization"),
        db.fetch_one("SELECT * FROM policy_versions WHERE status='ACTIVE' ORDER BY activated_at DESC LIMIT 1"),
    )
    entries = [{"policy_id": pid, **entry} for pid, entry in sorted(ledger.items(), key=lambda item: item[1].get("priority", 9999))]
    return {
        "policy_set": policy_set or {},
        "authorization": authorization or {},
        "deployed_rego": active,
        "environment": core.GATEWAY_ENVIRONMENT,
        "policies": entries,
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
        raise HTTPException(401, "아이디와 비밀번호를 확인하세요.")
    return response.json()


@app.post("/api/approvals/{approval_id}/approve")
async def approve(approval_id: str, request: ApprovalEvidence | None = None, user: dict = Depends(admin_caller)) -> dict:
    try:
        return await approve_request(approval_id, user["principal"],
            request.reason if request else None, request.evidence_sha256 if request else None)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/approvals/{approval_id}/reject")
async def reject(approval_id: str, request: RejectRequest, user: dict = Depends(admin_caller)) -> dict:
    try:
        return await reject_request(approval_id, user["principal"], request.note, request.evidence_sha256)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/api/approvals/{approval_id}/evidence")
async def approval_evidence(approval_id: UUID, user: dict = Depends(admin_caller)) -> dict:
    try:
        return await core.approval_evidence(str(approval_id), user["principal"])
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/approvals/{approval_id}/revoke")
async def approval_revoke(approval_id: UUID, request: ApprovalEvidence, user: dict = Depends(admin_caller)) -> dict:
    try:
        return await core.revoke_approval(str(approval_id), user["principal"], request.evidence_sha256)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/api/dispatch-intents")
async def dispatch_intents(user: dict = Depends(admin_caller)) -> dict:
    """Calls that were sent and never answered. The gateway does not retry them."""
    return {"rows": await dispatch.uncertain()}


@app.post("/api/dispatch-intents/{request_id}/resolve")
async def dispatch_intent_resolve(request_id: UUID, request: IntentResolve, user: dict = Depends(admin_caller)) -> dict:
    try:
        return await dispatch.resolve(str(request_id), request.outcome, user["principal"], request.note)
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


@app.post("/api/registry/{server_id}/check")
async def registry_check(server_id: str, user: dict = Depends(admin_caller)) -> dict:
    """지금 MCP 세션을 열 수 있는지만 본다 (D-40). 계약·상태·감사는 건드리지 않는다."""
    try:
        return await core.check_server(server_id)
    except LookupError as exc:
        raise HTTPException(404, "카탈로그에 없는 서버입니다.") from exc


# ── 승인한 서버를 Console에서 Gateway에 등록 (D-49) ──────────────────────────────
class LocalRun(StrictModel):
    """DEV-73: the manifest and the signature an approver produced offline."""
    manifest: dict
    signature: str = Field(min_length=40, max_length=200)


class RegistryDiscover(StrictModel):
    endpoint: str = Field(min_length=8, max_length=500)
    local: LocalRun | None = None
    intake_id: str = Field(default="", max_length=64)  # a local run is observed on this applicant's managed PC




class RegistryRegister(ResidencyFields):
    server_id: str = Field(pattern=r"^[a-z][a-z0-9-]{1,30}$")
    display_name: str = Field(min_length=2, max_length=80)
    endpoint: str = Field(min_length=8, max_length=500)
    catalog_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    tools: dict[str, Literal["r", "w", "x"]] = Field(min_length=1, max_length=300)
    data_class: Literal["public", "nonimportant", "important"]
    valid_days: int = Field(ge=1, le=365)
    source_url: str = Field(default="", max_length=300)
    commit_sha: str = Field(default="", pattern=r"^([0-9a-f]{40})?$")
    supplier: str = Field(default="", max_length=120)
    supplier_assurance: dict[str, str | bool] = Field(default_factory=dict)
    purpose: str = Field(default="", max_length=1000)
    owner_department: str = Field(default="", max_length=120)
    intake_id: str = Field(default="", max_length=64)
    exit_terms: dict[str, bool] = Field(default_factory=dict)
    poisoning_ack: bool = False  # D-52: the admin read the flagged tool text and approves it anyway
    tool_reviews: dict[str, ToolReview] = Field(min_length=1, max_length=300)  # D-91: a person scoped every approved tool
    local: LocalRun | None = None


@app.post("/api/registry/discover")
async def registry_discover(request: RegistryDiscover, user: dict = Depends(admin_caller)) -> dict:
    """등록 전 검토용: 엔드포인트가 지금 광고하는 도구와 그 계약 해시. 아무것도 기록하지 않는다."""
    try:
        return await core.discover_for_registration(request.endpoint, request.local and request.local.model_dump(),
                                                    request.intake_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"MCP 서버에 연결하지 못했습니다: {core._root_cause(exc)}") from exc


@app.post("/api/registry/intake-discover")
async def registry_intake_discover(request: RegistryDiscover, user: dict = Depends(caller)) -> dict:
    try:
        endpoint = core.registration_endpoint(request.endpoint)
        if not endpoint.startswith("https://"):
            raise ValueError("신청 도구 목록은 HTTPS 원격 서비스에서만 조회할 수 있습니다.")
        return await core.discover_for_registration(endpoint, principal=user["principal"])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, "도구 목록을 불러오지 못했습니다. 주소와 제공자 연결을 확인하세요.") from exc


@app.post("/api/registry/servers", status_code=201)
async def registry_register(request: RegistryRegister, user: dict = Depends(admin_caller)) -> dict:
    try:
        return await core.register_server(request.model_dump(), user["principal"])
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"MCP 서버에 연결하지 못했습니다: {core._root_cause(exc)}") from exc


class ToolReviews(StrictModel):
    reviews: dict[str, ToolReview] = Field(min_length=1, max_length=300)


class ResidencyReview(StrictModel):
    processing_countries: list[str] = Field(min_length=1, max_length=249)
    storage_countries: list[str] = Field(min_length=1, max_length=249)
    processor: str = Field(min_length=1, max_length=500)
    evidence_ref: str = Field(min_length=1, max_length=500)
    transfer_basis: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def validate_location(self):
        normalized = residency.normalize(self.model_dump())
        if not normalized["processor"] or not normalized["evidence_ref"]:
            raise ValueError("처리 주체와 위치 근거가 필요합니다.")
        self.__dict__.update(normalized)
        return self


@app.post("/api/registry/servers/{server_id}/tool-reviews")
async def registry_tool_reviews(server_id: str, request: ToolReviews, user: dict = Depends(admin_caller)) -> dict:
    try:
        return await core.review_tool_scopes(server_id, request.model_dump()["reviews"], user["principal"])
    except LookupError as exc:
        raise HTTPException(404, "도입 승인으로 Console에서 등록한 서버가 아닙니다.") from exc
    except review.NotIndependent as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/registry/servers/{server_id}/residency")
async def registry_residency_review(server_id: str, request: ResidencyReview,
                                    user: dict = Depends(admin_caller)) -> dict:
    try:
        return await core.review_server_residency(server_id, request.model_dump(), user["principal"])
    except LookupError as exc:
        raise HTTPException(404, "도입 승인으로 Console에서 등록한 서버가 아닙니다.") from exc
    except review.NotIndependent as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.delete("/api/registry/servers/{server_id}")
async def registry_deregister(server_id: str, user: dict = Depends(admin_caller)) -> dict:
    try:
        return await core.deregister_server(server_id, user["principal"])
    except LookupError as exc:
        raise HTTPException(404, "Console에서 등록한 서버가 아닙니다.") from exc


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


class RetentionRequest(StrictModel):
    days: int = Field(ge=1)
    jurisdictions: list[str] = Field(default_factory=list, max_length=len(retention.FLOORS))


@app.get("/api/audit/retention")
async def audit_retention(user: dict = Depends(admin_caller)) -> dict:
    return await retention.setting()


@app.put("/api/audit/retention")
async def audit_retention_update(request: RetentionRequest, user: dict = Depends(admin_caller)) -> dict:
    """A period shorter than the strictest selected jurisdiction is refused (D-141)."""
    try:
        return await retention.set_setting(request.days, request.jurisdictions, user["principal"])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


class AuditAnnotation(StrictModel):
    first_id: int = Field(ge=1)
    last_id: int = Field(ge=1)
    reason: str = Field(min_length=10, max_length=1000)


@app.post("/api/audit/annotations", status_code=201)
async def audit_annotate(request: AuditAnnotation, user: dict = Depends(admin_caller)) -> dict:
    """Marks a range of decisions as invalid. The ledger rows are not changed."""
    try:
        return await review.annotate(request.first_id, request.last_id, request.reason, user["principal"])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/audit/annotations")
async def audit_annotation_list(user: dict = Depends(admin_caller)) -> dict:
    return {"annotations": await review.annotations()}


def audit_filters(before: int = Query(0, ge=0), decision: str | None = Query(None, max_length=20),
                  server: str | None = Query(None, max_length=150), principal: str | None = Query(None, max_length=150),
                  policy: str | None = Query(None, max_length=150), event_kind: str | None = Query(None, max_length=30),
                  execution: str | None = Query(None, max_length=30), since: datetime | None = None,
                  until: datetime | None = None, trace_id: str | None = Query(None, max_length=128)) -> dict:
    return dict(before=before, decision=decision, server=server, principal=principal, policy=policy,
                event_kind=event_kind, execution=execution, since=since, until=until, trace_id=trace_id)


@app.get("/api/audit/events")
async def audit_events(limit: int = Query(100, ge=1, le=500), filters: dict = Depends(audit_filters),
                       user: dict = Depends(admin_caller)) -> dict:
    return await audit.events(limit=limit, **filters)


@app.get("/api/audit/export")
async def audit_export(limit: int = Query(500, ge=1, le=5000), filters: dict = Depends(audit_filters),
                       user: dict = Depends(admin_caller)) -> dict:
    return await audit.export(limit=limit, **filters)


@app.get("/api/audit/siem")
async def audit_siem(user: dict = Depends(admin_caller)) -> dict:
    return await siem.status()


@app.get("/api/audit/events/{event_id}")
async def audit_event(event_id: int, user: dict = Depends(admin_caller)) -> dict:
    return await audit.detail(event_id)


class IncidentCreate(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    started_at: datetime
    detected_at: datetime
    assessed_at: datetime | None = None
    scope_since: datetime
    scope_until: datetime
    server_id: str | None = Field(default=None, max_length=150)
    tool_name: str | None = Field(default=None, max_length=150)
    principal: str | None = Field(default=None, max_length=150)
    jurisdictions: list[str] = Field(min_length=1, max_length=20)
    incident_type: Literal["vulnerability", "severe-incident"] | None = None
    fix_available_at: datetime | None = None
    handled_at: datetime | None = None


class IncidentReport(StrictModel):
    jurisdiction: str = Field(min_length=1, max_length=50)
    stage: str = Field(min_length=1, max_length=50)
    note: str = Field(default="", max_length=1000)
    submitted_at: datetime | None = None


class IncidentSupplement(StrictModel):
    scope_since: datetime
    scope_until: datetime
    handled_at: datetime | None = None
    fix_available_at: datetime | None = None


@app.get("/api/audit/incidents")
async def audit_incidents(user: dict = Depends(admin_caller)) -> dict:
    return await incidents.list_cases()


@app.post("/api/audit/incidents", status_code=201)
async def audit_incident_create(request: IncidentCreate, user: dict = Depends(admin_caller)) -> dict:
    return await incidents.create(request.model_dump(), user["principal"])


@app.get("/api/audit/incidents/{incident_id}")
async def audit_incident_detail(incident_id: UUID, user: dict = Depends(admin_caller)) -> dict:
    return await incidents.detail(incident_id)


@app.post("/api/audit/incidents/{incident_id}/reports")
async def audit_incident_report(incident_id: UUID, request: IncidentReport, user: dict = Depends(admin_caller)) -> dict:
    return await incidents.report(incident_id, request.jurisdiction, request.stage, user["principal"], request.note, request.submitted_at)


@app.post("/api/audit/incidents/{incident_id}/supplements")
async def audit_incident_supplement(incident_id: UUID, request: IncidentSupplement,
                                    user: dict = Depends(admin_caller)) -> dict:
    return await incidents.supplement(incident_id, request.model_dump(), user["principal"])


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
                  "resource-rejection", "session-termination", "operator-statement"]
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
        raise HTTPException(409, str(exc))
    try:
        result["catalog"] = await core.refresh_catalog(server_id)
    except Exception as exc:
        result["catalog"] = {"status": "ERROR", "reason": core._root_cause(exc)}
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
    scopes: list[Literal["inventory", "netscan", "enforcement"]] = Field(default=["inventory"], max_length=3)
    enrollment_key: str | None = Field(default=None, min_length=32, max_length=128)


class EndpointEnroll(StrictModel):
    endpoint_id: str = Field(min_length=3, max_length=120)
    hostname: str = Field(min_length=1, max_length=200)
    platform: str = Field(min_length=1, max_length=80)
    agent_version: str = Field(min_length=1, max_length=40)
    owner_token: str | None = Field(default=None, max_length=120)
    detail: dict = Field(default_factory=dict)


class Provenance(StrictModel):
    """What the collector says it saw and did to the record before sending it."""
    raw_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    projection_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    transformations: list[Annotated[str, Field(pattern=r"^[a-z0-9_]{1,40}$")]] = Field(default_factory=list, max_length=8)
    collector: str | None = Field(default=None, pattern=r"^[a-z0-9_-]{1,40}$")


class EndpointEntry(StrictModel):
    config_path: str = Field(min_length=1, max_length=400)
    server_label: str = Field(min_length=1, max_length=200)
    transport: str = Field(min_length=1, max_length=40)
    endpoint_ref: str = Field(default="", max_length=600)
    provenance: Provenance | None = None


class EndpointReport(StrictModel):
    endpoint_id: str = Field(min_length=3, max_length=120)
    entries: list[EndpointEntry] = Field(default_factory=list, max_length=500)
    complete: bool = False
    origin: Literal["automatic", "manual"] = "manual"


class ObservationReport(StrictModel):
    endpoint_id: str = Field(min_length=3, max_length=120)
    channel: Literal["inventory", "process", "network", "os"]
    state: Literal["success", "partial", "failed", "disabled", "unauthorized", "unsupported", "unknown"]
    accepted_count: int = Field(default=0, ge=0, le=500)
    error_code: str = Field(default="", pattern=r"^[a-z_]{0,48}$")
    buffer_event_uid: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    dropped_count: int = Field(default=0, ge=0, le=2_000_000_000)
    buffer_reason: Literal["capacity", "retention", "mixed"] | None = None


class EndpointOSEvent(StrictModel):
    event_id: str = Field(min_length=10, max_length=300)
    observed_at: datetime
    kind: Literal["execution-denied", "network-denied"]
    details: dict[str, str | int] = Field(max_length=12)
    denial_class: Literal["harness_startup", "blocked_attempt", "listener_reply", "unknown"] | None = None
    provenance: Provenance | None = None


class EndpointOSReport(StrictModel):
    endpoint_id: str = Field(min_length=3, max_length=120)
    events: list[EndpointOSEvent] = Field(max_length=100)


class HostAccount(StrictModel):
    name: str = Field(min_length=1, max_length=64)
    uid: int = Field(ge=0)
    privileged_groups: list[str] = Field(default_factory=list, max_length=8)


class HostReport(StrictModel):
    """Other login accounts on the managed device: each is a path the kernel profile does not confine."""
    kernel: str = Field(max_length=120)
    wsl: bool
    other_accounts: list[HostAccount] = Field(default_factory=list, max_length=64)


class NetworkQuality(StrictModel):
    """Endpoint-to-Gateway probe summary. RTT is the TCP connect time; failures count every probe."""
    measured_at: datetime
    rtt_p50_ms: float | None = Field(default=None, ge=0, le=60000, allow_inf_nan=False)
    rtt_p95_ms: float | None = Field(default=None, ge=0, le=60000, allow_inf_nan=False)
    jitter_ms: float | None = Field(default=None, ge=0, le=60000, allow_inf_nan=False)
    failure_pct: float = Field(ge=0, le=100, allow_inf_nan=False)
    probes: int = Field(ge=1, le=32)

    @model_validator(mode="after")
    def plausible(self):
        if (self.rtt_p50_ms is None) != (self.rtt_p95_ms is None) or (
                self.rtt_p50_ms is not None and self.rtt_p50_ms > self.rtt_p95_ms):
            raise ValueError("지연 분위수가 맞지 않습니다.")
        if self.measured_at.tzinfo is None:
            raise ValueError("측정 시각에 시간대가 필요합니다.")
        age = datetime.now(UTC) - self.measured_at
        if age > timedelta(minutes=10) or age < -timedelta(minutes=1):
            raise ValueError("측정 시각이 허용 범위를 벗어났습니다.")
        return self


class UserCommandSetting(StrictModel):
    # Fixed labels only: a profile file's name is the employee's choice and may carry a secret.
    file: Literal["~", ".claude", ".claude/settings.json", ".claude/settings.local.json",
                  ".codex", ".codex/config.toml", ".codex/*.config.toml",
                  "env:CODEX_HOME", "env:CLAUDE_CONFIG_DIR", "env"]
    keys: list[Literal["apiKeyHelper", "otelHeadersHelper", "awsCredentialExport", "awsAuthRefresh", "notify"]] = Field(max_length=4)


class ManagedHeartbeat(StrictModel):
    policy_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    configuration_hashes: dict[str, str] = Field(max_length=4)
    checks: dict[str, bool] = Field(max_length=5)
    user_command_settings: list[UserCommandSetting] = Field(default_factory=list, max_length=128)
    host: HostReport | None = None
    network_quality: dict | None = Field(default=None, max_length=12)


class ManagedActivation(StrictModel):
    policy_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    note: str = Field(min_length=20, max_length=1000)


class ListenerFinding(StrictModel):
    provenance: Provenance | None = None
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
    complete: bool = False
    sources: list[Literal["local-socket", "network", "stdio-process"]] | None = Field(default=None, min_length=1, max_length=3)
    origin: Literal["automatic", "manual"] = "manual"

    @model_validator(mode="after")
    def source_scope(self):
        if self.sources is not None:
            if len(self.sources) != len(set(self.sources)):
                raise ValueError("중복된 관측 범위입니다.")
            if any(item.source not in self.sources for item in self.findings):
                raise ValueError("관측 범위 밖의 결과입니다.")
        return self


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


@app.get("/api/endpoint/managed-policy")
async def endpoint_managed_policy(device: dict = Depends(endpoint_device("enforcement"))) -> dict:
    try:
        policy = await endpoint_plane.managed_policy(device)
    except (PermissionError, ValueError) as exc:
        raise HTTPException(403, str(exc)) from exc
    return policy


@app.post("/api/endpoint/heartbeat")
async def endpoint_heartbeat(request: ManagedHeartbeat,
                             device: dict = Depends(endpoint_device("enforcement"))) -> dict:
    # A bad measurement is dropped and reported back; it never costs the device its heartbeat.
    quality, verdict = None, "absent"
    if request.network_quality is not None:
        try:
            quality, verdict = NetworkQuality.model_validate(request.network_quality).model_dump(), "stored"
        except ValueError:
            verdict = "rejected"
    try:
        command_settings = ({"user_command_settings": [item.model_dump() for item in request.user_command_settings]}
                            if request.user_command_settings else {})
        report = await endpoint_plane.heartbeat(device, request.policy_hash, request.configuration_hashes, request.checks,
                                                request.host.model_dump() if request.host else None, quality,
                                                **command_settings)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    return {**report, "network_quality": verdict}


class LocalJobResult(BaseModel):
    result: dict | None = None
    error: str | None = Field(default=None, max_length=500)
    stopped: bool = False
    isolation: dict | None = None


@app.get("/api/endpoint/local-jobs")
async def endpoint_local_job(wait: float = 25, device: dict = Depends(endpoint_device("enforcement"))) -> dict:
    """승인된 로컬 MCP 실행 요청을 그 장치에만 내준다. 장치는 바깥으로만 연결한다."""
    return {"job": await local_jobs.claim(device, max(0.0, min(wait, 25.0)))}


@app.post("/api/endpoint/local-jobs/{job_id}")
async def endpoint_local_job_result(job_id: uuid.UUID, request: LocalJobResult,
                                    device: dict = Depends(endpoint_device("enforcement"))) -> dict:
    try:
        accepted = await local_jobs.complete(device, str(job_id), request.result, request.error,
                                             stopped=request.stopped, isolation=request.isolation)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not accepted:
        raise HTTPException(409, "이 장치가 받은 진행 중 요청이 아닙니다.")
    return {"accepted": True}


@app.get("/api/endpoint/local-jobs/recovery")
async def endpoint_local_recovery(device: dict = Depends(endpoint_device("enforcement"))) -> dict:
    return {'jobs':await local_jobs.recoverable(device)}


@app.get("/api/endpoint/local-jobs/{job_id}/control")
async def endpoint_local_control(job_id: UUID, device: dict = Depends(endpoint_device("enforcement"))) -> dict:
    try:
        return await local_jobs.validate_job(device, str(job_id))
    except (PermissionError, ConnectionError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/endpoint/local-jobs/{job_id}/start")
async def endpoint_local_start(job_id: UUID, device: dict = Depends(endpoint_device("enforcement"))) -> dict:
    try:
        return await local_jobs.validate_job(device, str(job_id), start=True)
    except (PermissionError, ConnectionError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/endpoint/devices/{endpoint_id}/activate")
async def endpoint_managed_activate(endpoint_id: str, request: ManagedActivation,
                                    user: dict = Depends(admin_caller)) -> dict:
    try:
        return await endpoint_plane.activate_managed(endpoint_id, user["principal"], request.policy_hash, request.note)
    except (ValueError, PermissionError) as exc:
        raise HTTPException(409, str(exc)) from exc


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
            request.endpoint_id, [entry.model_dump() for entry in request.entries],
            complete=request.complete, origin=request.origin)
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
            request.endpoint_id, [item.model_dump() for item in request.findings],
            complete=request.complete, sources=request.sources, origin=request.origin)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@app.post("/api/endpoint/observation-status")
async def endpoint_observation_status(request: ObservationReport,
                                      device: dict = Depends(endpoint_device("inventory"))) -> dict:
    if request.endpoint_id != device["endpoint_id"]:
        raise HTTPException(403, "장치 자격과 다른 엔드포인트의 보고는 받지 않습니다.")
    required = {"process": "netscan", "network": "netscan", "os": "enforcement"}.get(request.channel)
    if request.state in {"success", "partial"} and required and required not in device["scopes"]:
        raise HTTPException(403, "이 관측 채널의 보고 권한이 없습니다.")
    if bool(request.dropped_count) != bool(request.buffer_event_uid and request.buffer_reason):
        raise HTTPException(422, "버퍼 미적재·만료 건수 보고의 식별자·사유·건수가 필요합니다.")
    return await endpoint_plane.observation_status(
        request.endpoint_id, request.channel, request.state, request.accepted_count, request.error_code,
        buffer_event_uid=request.buffer_event_uid, dropped_count=request.dropped_count,
        buffer_reason=request.buffer_reason)


@app.get("/api/endpoint/inventory")
async def endpoint_inventory(classification: str | None = None,
                             user: dict = Depends(admin_caller)) -> dict:
    try:
        endpoint_plane._classes(classification)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    window = endpoint_plane.PAGE_MAX
    entries = await endpoint_plane.inventory_page(classification, window)
    listeners = await endpoint_plane.listeners_page(classification, window)
    events = await endpoint_plane.os_events_page(limit=window)
    managed = await db.fetch_all("SELECT * FROM endpoint_managed_events ORDER BY id DESC LIMIT 200")
    managed_total = await db.fetch_one("SELECT count(*) AS n FROM endpoint_managed_events")
    return {
        "coverage": await endpoint_plane.coverage(),
        "agents": await endpoint_plane.agents(),
        "devices": await endpoint_plane.devices(),
        "entries": entries["rows"],
        "listeners": listeners["rows"],
        "scan_policy": await endpoint_plane.scan_policy(),
        "os_events": events["rows"],
        "managed_events": managed,
        "pages": {name: {key: page[key] for key in ("total", "limit", "next_cursor")}
                  for name, page in (("entries", entries), ("listeners", listeners), ("os_events", events))}
                 | {"managed_events": {"total": int(managed_total["n"] or 0), "limit": 200, "next_cursor": None}},
    }


CursorQuery = Annotated[str | None, Query(pattern=r"^\d{1,18}$")]
LimitQuery = Annotated[int, Query(ge=1, le=200)]
ClassQuery = Annotated[str | None, Query(pattern=r"^(registered|shadow|retired-residue)(,(registered|shadow|retired-residue))*$")]


@app.get("/api/endpoint/inventory/entries")
async def endpoint_inventory_entries(classification: ClassQuery = None, cursor: CursorQuery = None,
                                     limit: LimitQuery = 100, user: dict = Depends(admin_caller)) -> dict:
    return await endpoint_plane.inventory_page(classification, limit, cursor)


@app.get("/api/endpoint/inventory/listeners")
async def endpoint_inventory_listeners(classification: ClassQuery = None, cursor: CursorQuery = None,
                                       limit: LimitQuery = 100, user: dict = Depends(admin_caller)) -> dict:
    return await endpoint_plane.listeners_page(classification, limit, cursor)


@app.get("/api/endpoint/inventory/os-events")
async def endpoint_inventory_os_events(kind: Literal["execution-denied", "network-denied"] | None = None,
                                       denial_class: Literal["harness_startup", "blocked_attempt", "listener_reply", "unknown"] | None = None,
                                       cursor: CursorQuery = None, limit: LimitQuery = 100,
                                       user: dict = Depends(admin_caller)) -> dict:
    return await endpoint_plane.os_events_page(kind, denial_class, limit, cursor)


@app.get("/api/endpoint/observations")
async def endpoint_observations(cursor: Annotated[str | None, Query(pattern=r"^[A-Za-z0-9._:-]{1,120}$")] = None,
                                limit: LimitQuery = 100, user: dict = Depends(admin_caller)) -> dict:
    return await endpoint_plane.observations_page(limit, cursor)


@app.get("/api/endpoint/records/{kind}/{record_id}")
async def endpoint_record(kind: Literal["config", "listener", "os-event"], record_id: Annotated[int, Path(ge=1, le=2**62)],
                          user: dict = Depends(admin_caller)) -> dict:
    found = await endpoint_plane.record_detail(kind, record_id)
    if not found:
        raise HTTPException(404, "기록을 찾을 수 없습니다.")
    return found


@app.get("/api/endpoint/correlation")
async def endpoint_correlation(decision_id: Annotated[int | None, Query(ge=1, le=2**62)] = None,
                               kind: Literal["config", "listener", "os-event"] | None = None,
                               record_id: Annotated[int | None, Query(ge=1, le=2**62)] = None,
                               window_seconds: Annotated[int, Query(ge=10, le=3600)] = 300,
                               user: dict = Depends(admin_caller)) -> dict:
    if (decision_id is None) == (kind is None or record_id is None):
        raise HTTPException(422, "판정 번호 또는 기록 종류와 번호 중 하나만 지정하세요.")
    found = await endpoint_plane.correlate(decision_id=decision_id, kind=kind, record_id=record_id,
                                           window_seconds=window_seconds)
    if not found:
        raise HTTPException(404, "기록을 찾을 수 없습니다.")
    return found


@app.get("/api/endpoint/network-quality")
async def endpoint_network_quality(user: dict = Depends(admin_caller)) -> dict:
    return await endpoint_plane.network_quality()


@app.post("/api/endpoint/os-events")
async def endpoint_os_report(request: EndpointOSReport,
                             device: dict = Depends(endpoint_device("enforcement"))) -> dict:
    if request.endpoint_id != device["endpoint_id"]:
        raise HTTPException(403, "장치 자격과 다른 엔드포인트의 보고는 받지 않습니다.")
    if any(len(str(v)) > 300 for e in request.events for v in e.details.values()):
        raise HTTPException(422, "OS 관측 필드는 300자를 넘을 수 없습니다.")
    return await endpoint_plane.ingest_os_events(request.endpoint_id, [e.model_dump() for e in request.events])


@app.get("/api/risk-catalog")
async def risk_catalog(user: dict = Depends(caller)) -> dict:
    """AI-Infra-Guard의 위험 범주와 이 조직의 통제를 연결한 표.

    발견 목록을 읽을거리가 아니라 통제로 잇는 것은 이 매핑뿐이다. 인증 없이 여는
    이유는 조직 자산이 아니라 참조 분류표이기 때문이다(13절의 열린 읽기 목록).
    """
    rows = await db.fetch_all("SELECT * FROM aig_risk_catalog ORDER BY ordinal")
    return {"categories": [dict(row) for row in rows]}


app.mount("/mcp", RequireBearer(ServerPath(mcp_http)))


@app.get("/", include_in_schema=False)
async def console() -> RedirectResponse:
    """The browser console lives with the Agent service; this port remains the API boundary."""
    return RedirectResponse(os.getenv("CONSOLE_PUBLIC_URL", "http://localhost:8000").rstrip("/") + "/workspace")
