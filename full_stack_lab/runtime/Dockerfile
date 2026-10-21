# The runtime worker: the only container that talks to the container engine (DEV-38). It carries the
# recipes it may build; a job in the database can only name one of them.
FROM docker:29.0-cli@sha256:858bb1e05af16840f5a55143c3e5e14073891fbc92f2c1f6f38dd9c5f2cca03c AS cli
FROM aquasec/trivy:0.74.0 AS scanner
FROM python:3.12-slim
COPY --from=cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=scanner /usr/local/bin/trivy /usr/local/bin/trivy
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "psycopg[binary]==3.3.5" "cryptography==50.0.1"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY gateway/app/provenance.py /app/provenance.py
COPY gateway/app/artifact_provenance.py /app/artifact_provenance.py
COPY gateway/app/server_egress.py /app/server_egress.py
COPY runtime/worker.py /app/worker.py
COPY runtime/image_scan.py /app/image_scan.py
COPY supply_chain/trivy_scan.py /app/trivy_scan.py
COPY runtime/recipes /app/recipes
RUN python -c "import worker; print(sorted(r['id'] for r in worker.load_recipes().values()))" && docker --version
CMD ["python", "/app/worker.py"]
