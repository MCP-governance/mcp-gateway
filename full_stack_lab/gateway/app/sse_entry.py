"""Legacy SSE ingress (MCP 2024-11-05 transport) on the same policy path.

Bound on 0.0.0.0 inside Compose where services dial it by name; a native run on a
host must set SSE_BIND_ADDR, or it would open this ingress on every interface.
"""
import os

import uvicorn
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Mount, Route

from .mcp_facade import build_mcp

server = build_mcp()
transport = SseServerTransport("/messages/")


async def handle_sse(request):
    async with transport.connect_sse(request.scope, request.receive, request._send) as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())
    return Response()


app = Starlette(routes=[Route("/sse", endpoint=handle_sse, methods=["GET"]),
                        Mount("/messages/", app=transport.handle_post_message)])

if __name__ == "__main__":
    uvicorn.run(app, host=os.getenv("SSE_BIND_ADDR", "0.0.0.0"), port=int(os.getenv("SSE_PORT", "8081")))
