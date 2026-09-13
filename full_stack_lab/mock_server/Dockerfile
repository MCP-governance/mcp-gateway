FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home appuser \
    && mkdir -p /runtime \
    && chown -R appuser:appuser /app /runtime
COPY --chown=appuser:appuser server.py .
USER appuser
EXPOSE 9000
CMD ["python", "server.py"]
