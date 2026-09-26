"""Agent Service forwards authenticated AI and MCP transports."""
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from services.gateway import NoCookieJar, clean_headers, read_body
from services.shared import authenticate, emit


def create_app():
    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(timeout=httpx.Timeout(30, read=120), follow_redirects=False,
                                     trust_env=False, cookies=NoCookieJar()) as client:
            app.state.client = client
            yield

    app = FastAPI(title="Agent Service", lifespan=lifespan)

    async def forward(request: Request, target: str, headers: dict):
        body = await read_body(request)
        try:
            outgoing = app.state.client.build_request(request.method, target, headers=headers,
                                                      content=body if body else None,
                                                      params=list(request.query_params.multi_items()))
            response = await app.state.client.send(outgoing, stream=True)
        except httpx.HTTPError as exc:
            raise HTTPException(502, "Agent upstream unavailable") from exc

        async def stream():
            try:
                async for chunk in response.aiter_raw():
                    yield chunk
            finally:
                await response.aclose()

        return StreamingResponse(stream(), status_code=response.status_code, headers=clean_headers(response.headers))

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.api_route("/mcp/demo", methods=["GET", "POST", "DELETE"])
    async def mcp(request: Request):
        claims = await authenticate(request)
        emit("agent-service", "request", {"transport": "mcp", "subject": claims.get("sub", "")})
        # The gateway verifies the user's transport credential again. It strips it before MCP upstream.
        headers = clean_headers(request.headers, upstream=True)
        headers["authorization"] = request.headers.get("authorization", "")
        return await forward(request, os.getenv("GATEWAY_URL", "http://mcp-gateway:8000") + "/mcp/demo", headers)

    @app.post("/v1/chat/completions")
    async def chat(request: Request):
        claims = await authenticate(request)
        key = os.getenv("LITELLM_MASTER_KEY", "")
        if not key:
            raise HTTPException(503, "LiteLLM service credential is not configured")
        headers = clean_headers(request.headers, upstream=True)
        headers["authorization"] = "Bearer " + key
        emit("agent-service", "request", {"transport": "chat", "subject": claims.get("sub", "")})
        return await forward(request, os.getenv("LITELLM_URL", "http://litellm:4000") + "/v1/chat/completions", headers)

    return app


app = create_app()
