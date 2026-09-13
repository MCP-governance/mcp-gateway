from __future__ import annotations

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from .core import execute_call


def build_mcp() -> MCPServer:
    mcp = MCPServer(
        "mcp-governance-security-gateway",
        version="1.0.0",
        instructions="합성 사용자·데이터만 사용하는 정책 강제 실습용 Gateway입니다.",
    )

    @mcp.tool(description="등록된 합성 문서를 정책 확인 후 읽습니다.")
    async def read_document(user_token: str, document_id: str) -> dict:
        return await execute_call({
            "tool_name": "read_document", "user_token": user_token, "document_id": document_id
        })

    @mcp.tool(description="등록된 합성 문서를 정책 확인 후 변경합니다.")
    async def write_document(user_token: str, document_id: str, content: str) -> dict:
        return await execute_call({
            "tool_name": "write_document", "user_token": user_token,
            "document_id": document_id, "content": content,
        })

    @mcp.tool(description="외부 전송·고위험 실행(x)을 승인 또는 제한 정책으로 통제합니다.")
    async def send_external(
        user_token: str, document_id: str, destination: str, content: str
    ) -> dict:
        return await execute_call({
            "tool_name": "send_external", "user_token": user_token,
            "document_id": document_id, "destination": destination, "content": content,
        })

    @mcp.tool(description="허용된 stdio MCP 프로세스로 공개 시간정보를 조회합니다.")
    async def get_current_time(user_token: str, timezone: str = "Asia/Seoul") -> dict:
        return await execute_call({
            "tool_name": "get_current_time", "user_token": user_token, "timezone": timezone
        })

    @mcp.tool(description="GitHub 공식 MCP의 읽기 도구입니다. 인증 전에는 의도적으로 차단됩니다.")
    async def github_get_file(user_token: str, owner: str, repo: str, path: str) -> dict:
        return await execute_call({
            "tool_name": "github_get_file", "user_token": user_token,
            "owner": owner, "repo": repo, "path": path,
        })

    return mcp


def transport_security() -> TransportSecuritySettings:
    return TransportSecuritySettings(
        allowed_hosts=["gateway:*", "gateway-sse:*", "localhost:*", "127.0.0.1:*"],
        allowed_origins=["http://localhost:*", "http://127.0.0.1:*"],
    )
