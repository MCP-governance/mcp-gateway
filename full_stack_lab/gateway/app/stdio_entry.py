"""stdio ingress: the identity is GATEWAY_STDIO_PRINCIPAL, bound by whoever spawns it."""
import anyio
from mcp.server.stdio import stdio_server

from .mcp_facade import build_mcp


async def main() -> None:
    server = build_mcp()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    anyio.run(main)
