FROM node:24-alpine AS ui
WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci
COPY ui/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m venv /opt/time-mcp \
    && /opt/time-mcp/bin/pip install --no-cache-dir mcp-server-time==2026.8.18 \
    && useradd --uid 10001 --create-home appuser \
    && mkdir -p /app/ui /runtime /reports \
    && chown -R appuser:appuser /app /runtime /reports
COPY --chown=appuser:appuser app ./app
COPY --from=ui --chown=appuser:appuser /ui/dist ./ui
USER appuser
EXPOSE 8080 8081
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
