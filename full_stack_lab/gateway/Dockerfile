FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home appuser \
    && mkdir -p /runtime /reports /registry-runtime \
    && chown -R appuser:appuser /app /runtime /reports /registry-runtime
COPY --chown=appuser:appuser app ./app
ARG MCP_BUILD_REVISION=unknown
ENV MCP_BUILD_REVISION=$MCP_BUILD_REVISION
LABEL org.opencontainers.image.revision=$MCP_BUILD_REVISION
USER appuser
EXPOSE 8080 8081
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
