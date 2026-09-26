"""Authenticated MCP transport with pre-execution policy and evidence checks."""
import json
import os
from contextlib import asynccontextmanager
from http.cookiejar import CookieJar
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from services.shared import authenticate, emit, internal_headers

MAX_BODY = 1024 * 1024
MAX_DISCOVERY = 4 * 1024 * 1024
HOP_HEADERS = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
               "te", "trailer", "transfer-encoding", "upgrade", "host", "content-length"}
SECRET_HEADERS = {"authorization", "x-litellm-api-key", "x-service-token", "cookie"}


class NoCookieJar(CookieJar):
    """MCP and service sessions use explicit transport headers, never ambient cookies."""

    def extract_cookies(self, response, request):
        pass

    def add_cookie_header(self, request):
        pass


def clean_headers(headers, *, upstream=False):
    excluded = set(HOP_HEADERS)
    excluded.update(part.strip().lower() for part in headers.get("connection", "").split(","))
    if upstream:
        excluded.update(SECRET_HEADERS)
    return {key: value for key, value in headers.items() if key.lower() not in excluded}


async def read_body(request: Request) -> bytes:
    parts, size = [], 0
    async for part in request.stream():
        size += len(part)
        if size > MAX_BODY:
            raise HTTPException(413, "MCP request exceeds 1 MiB")
        parts.append(part)
    return b"".join(parts)


def rpc_payload(body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "Expected a JSON-RPC object")
    if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
        raise HTTPException(400, "Expected one JSON-RPC 2.0 object")
    return payload


def decode_rpc(body: bytes, content_type: str) -> dict:
    if "text/event-stream" in content_type:
        # MCP POST SSE may contain comments and multiple events; find the result envelope.
        for event in body.decode("utf-8").replace("\r\n", "\n").split("\n\n"):
            data = "\n".join(line[5:].lstrip() for line in event.splitlines() if line.startswith("data:"))
            if data:
                value = json.loads(data)
                if isinstance(value, dict) and ("result" in value or "error" in value):
                    return value
        raise ValueError("No MCP result in SSE response")
    value = json.loads(body)
    if not isinstance(value, dict):
        raise ValueError("Invalid MCP result")
    return value


async def bounded_response(response: httpx.Response) -> bytes:
    parts, size = [], 0
    try:
        async for part in response.aiter_bytes():
            size += len(part)
            if size > MAX_DISCOVERY:
                raise HTTPException(502, "Tool discovery exceeds 4 MiB")
            parts.append(part)
        return b"".join(parts)
    finally:
        await response.aclose()


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(timeout=httpx.Timeout(30, read=120), follow_redirects=False,
                                     trust_env=False, cookies=NoCookieJar()) as client:
            app.state.client = client
            yield

    app = FastAPI(title="MCP Gateway", lifespan=lifespan)

    async def register_tools(body: bytes, content_type: str) -> list[dict]:
        try:
            tools = decode_rpc(body, content_type)["result"]["tools"]
            if not isinstance(tools, list) or any(not isinstance(t, dict) or not isinstance(t.get("name"), str) for t in tools):
                raise ValueError("Invalid tools")
            for tool in tools:
                result = await app.state.client.post(
                    os.getenv("DECISION_API_URL", "http://evidence-decision-api:8000") + "/tools/register",
                    json={"server": "demo", "tool": tool["name"], "definition": tool},
                    headers=internal_headers())
                result.raise_for_status()
            return tools
        except HTTPException:
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(503, "Tool registration unavailable") from exc

    async def guard_call(payload: dict, headers: dict, claims: dict):
        params = payload.get("params")
        if not isinstance(params, dict) or not isinstance(params.get("name"), str):
            raise HTTPException(400, "Missing tool name")
        tool_name = params["name"]
        try:
            discovery_headers = dict(headers)
            discovery_headers.update({"content-type": "application/json", "accept": "application/json, text/event-stream"})
            req = app.state.client.build_request("POST", os.getenv("MCP_UPSTREAM", "http://mcp-server:8000/mcp"),
                                                headers=discovery_headers,
                                                json={"jsonrpc": "2.0", "id": "gateway-discovery", "method": "tools/list", "params": {}})
            discovered = await app.state.client.send(req, stream=True)
            if discovered.status_code != 200:
                await discovered.aclose()
                raise HTTPException(503, "Tool discovery unavailable")
            tools = await register_tools(await bounded_response(discovered), discovered.headers.get("content-type", ""))
            if tool_name not in {tool["name"] for tool in tools}:
                raise HTTPException(403, "Tool is not advertised by this server")
            decision = await app.state.client.get(
                os.getenv("DECISION_API_URL", "http://evidence-decision-api:8000") + "/tools/demo/" + quote(tool_name, safe=""),
                headers=internal_headers())
            decision.raise_for_status()
            approved = decision.json().get("approved") is True
            if not approved:
                raise HTTPException(403, "Tool requires administrator approval")
            roles = claims.get("realm_access", {}).get("roles", claims.get("roles", []))
            opa = await app.state.client.post(os.getenv("OPA_URL", "http://opa:8181") + "/v1/data/mcp/allow",
                                             json={"input": {"subject": claims.get("sub"), "roles": roles,
                                                            "tool": tool_name, "approved": approved}})
            opa.raise_for_status()
            if opa.json().get("result") is not True:
                raise HTTPException(403, "Policy denied tool execution")
            arguments = params.get("arguments", {})
            if not isinstance(arguments, dict):
                raise HTTPException(400, "Tool arguments must be an object")
            analyzer = await app.state.client.post(os.getenv("PRESIDIO_URL", "http://presidio-analyzer:3000") + "/analyze",
                                                  json={"text": json.dumps(arguments, ensure_ascii=False), "language": "en"})
            analyzer.raise_for_status()
            findings = analyzer.json()
            if not isinstance(findings, list):
                raise HTTPException(503, "Invalid sensitivity analysis result")
            emit("mcp-gateway", "presidio", {"server": "demo", "tool": tool_name, "finding_count": len(findings)})
            if findings:
                raise HTTPException(403, "Sensitive tool arguments blocked")
        except HTTPException:
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(503, "Pre-execution checks unavailable") from exc

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.api_route("/mcp/demo", methods=["GET", "POST", "DELETE"])
    async def proxy(request: Request):
        claims = await authenticate(request)
        body = await read_body(request)
        headers = clean_headers(request.headers, upstream=True)
        payload = rpc_payload(body) if request.method == "POST" else {}
        if payload.get("method") == "tools/call":
            params = payload.get("params")
            tool = params.get("name", "") if isinstance(params, dict) else ""
            try:
                await guard_call(payload, headers, claims)
            except HTTPException:
                emit("mcp-gateway", "decision", {"status": "blocked", "server": "demo", "tool": tool, "approved": False})
                raise
            emit("mcp-gateway", "decision", {"status": "allowed", "server": "demo", "tool": tool, "approved": True})
        emit("mcp-gateway", "request", {"server": "demo", "method": payload.get("method", request.method), "subject": claims.get("sub", "")})
        try:
            upstream = app.state.client.build_request(request.method, os.getenv("MCP_UPSTREAM", "http://mcp-server:8000/mcp"),
                                                     headers=headers, content=body if body else None,
                                                     params=list(request.query_params.multi_items()))
            response = await app.state.client.send(upstream, stream=True)
        except httpx.HTTPError as exc:
            emit("mcp-gateway", "request", {"status": "error", "server": "demo", "method": payload.get("method", request.method)})
            raise HTTPException(502, "MCP upstream unavailable") from exc
        response_headers = clean_headers(response.headers)
        if payload.get("method") == "tools/list" and response.status_code == 200:
            response_body = await bounded_response(response)
            # HTTPX decodes compression while buffering discovery; remove its wire encoding.
            response_headers.pop("content-encoding", None)
            await register_tools(response_body, response.headers.get("content-type", ""))
            return Response(response_body, status_code=response.status_code, headers=response_headers)

        async def stream():
            try:
                async for chunk in response.aiter_raw():
                    yield chunk
            finally:
                await response.aclose()

        return StreamingResponse(stream(), status_code=response.status_code, headers=response_headers)

    from services.scanner import router as scan_router
    app.include_router(scan_router)
    return app


app = create_app()
