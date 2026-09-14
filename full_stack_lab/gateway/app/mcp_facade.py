from __future__ import annotations

import os

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.transport_security import TransportSecuritySettings

from .agent_contract import authenticated_user
from .core import execute_call
from .method_scope import MethodScope

# stdio has no request headers, so the identity of a stdio ingress is bound once, at
# process start, by whoever is allowed to spawn it. Unset means no identity, which
# fails closed rather than falling back to a default principal.
STDIO_PRINCIPAL = os.getenv("GATEWAY_STDIO_PRINCIPAL", "")


async def principal(ctx: Context) -> str:
    """Resolve the caller from the transport, never from tool arguments.

    HTTP and SSE carry a signed synthetic JWT; the header is client-supplied input, so
    it is verified (signature, issuer, audience, expiry, revocation) before it becomes
    an identity. stdio carries no headers and uses the principal bound at spawn time.
    """
    headers = ctx.headers
    if headers is None:
        if not STDIO_PRINCIPAL:
            raise ValueError("stdio ingress에 신원이 바인딩되지 않았습니다. GATEWAY_STDIO_PRINCIPAL을 설정하세요.")
        return STDIO_PRINCIPAL
    user = await authenticated_user(headers.get("authorization"))
    return user["principal"]


def build_mcp() -> MCPServer:
    mcp = MCPServer(
        "mcp-governance-security-gateway",
        version="1.1.0",
        instructions="합성 사용자·데이터만 사용하는 정책 강제 실습용 Gateway입니다. 신원은 transport 인증에서만 옵니다.",
        middleware=[MethodScope()],
    )

    @mcp.tool(description="등록된 합성 문서를 정책 확인 후 읽습니다.")
    async def read_document(document_id: str, ctx: Context) -> dict:
        return await execute_call({
            "tool_name": "read_document", "user_token": await principal(ctx),
            "document_id": document_id,
        })

    @mcp.tool(description="등록된 합성 문서를 정책 확인 후 변경합니다.")
    async def write_document(document_id: str, content: str, ctx: Context) -> dict:
        return await execute_call({
            "tool_name": "write_document", "user_token": await principal(ctx),
            "document_id": document_id, "content": content,
        })

    @mcp.tool(description="외부 전송·고위험 실행(x)을 승인 또는 제한 정책으로 통제합니다.")
    async def send_external(
        document_id: str, destination: str, content: str, ctx: Context
    ) -> dict:
        return await execute_call({
            "tool_name": "send_external", "user_token": await principal(ctx),
            "document_id": document_id, "destination": destination, "content": content,
        })

    @mcp.tool(description="허용된 stdio MCP 프로세스로 공개 시간정보를 조회합니다.")
    async def get_current_time(ctx: Context, timezone: str = "Asia/Seoul") -> dict:
        return await execute_call({
            "tool_name": "get_current_time", "user_token": await principal(ctx),
            "timezone": timezone,
        })

    @mcp.tool(description="GitHub 공식 MCP의 읽기 도구입니다. 인증 전에는 의도적으로 차단됩니다.")
    async def github_get_file(owner: str, repo: str, path: str, ctx: Context) -> dict:
        return await execute_call({
            "tool_name": "github_get_file", "user_token": await principal(ctx),
            "owner": owner, "repo": repo, "path": path,
        })

    return mcp


def transport_security() -> TransportSecuritySettings:
    return TransportSecuritySettings(
        allowed_hosts=["gateway:*", "gateway-sse:*", "localhost:*", "127.0.0.1:*"],
        allowed_origins=["http://localhost:*", "http://127.0.0.1:*"],
    )
