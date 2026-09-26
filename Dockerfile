FROM ghcr.io/astral-sh/uv:0.11.24 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY services ./services
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER 65532:65532
CMD ["uvicorn", "services.gateway:app", "--host", "0.0.0.0", "--port", "8000"]
