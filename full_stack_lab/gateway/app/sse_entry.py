import os

from .mcp_facade import build_mcp

# compose에서는 서비스 이름으로 붙으므로 0.0.0.0이 맞다. 한 호스트에서 직접 띄울
# 때는 그 기본값이 이 장비의 모든 인터페이스에 legacy SSE ingress를 여는 것이 된다.
if __name__ == "__main__":
    build_mcp().run(
        "sse",
        host=os.getenv("SSE_BIND_ADDR", "0.0.0.0"),
        port=int(os.getenv("SSE_PORT", "8081")),
    )
