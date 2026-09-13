from .mcp_facade import build_mcp, transport_security

if __name__ == "__main__":
    build_mcp().run("sse", host="0.0.0.0", port=8081, transport_security=transport_security())
