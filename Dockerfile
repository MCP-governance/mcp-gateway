FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.11.24 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock ./
COPY mcp_gateway ./mcp_gateway
COPY proxy.toml ./proxy.toml
RUN uv sync --frozen --no-dev

FROM base AS demo
RUN uv sync --frozen --group dev
COPY examples ./examples
USER 10001:10001
CMD ["/app/.venv/bin/python", "examples/demo_server.py", "--host", "0.0.0.0", "--port", "9000"]

FROM base AS proxy
# The record lives on a volume; the directory exists so a new volume inherits its owner.
RUN mkdir -p /app/proxy-data && chown 10001:10001 /app/proxy-data
USER 10001:10001
EXPOSE 8080
CMD ["/app/.venv/bin/mcp-gateway", "--host", "0.0.0.0", "--port", "8080"]
