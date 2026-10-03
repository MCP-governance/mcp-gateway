# 도입 요청 격리 검증 워커. Gateway 이미지와 분리한 이유는 스캐너 도구 체인과
# git이 정책 집행 프로세스와 같은 파일시스템에 있을 이유가 없기 때문이다.
FROM zricethezav/gitleaks:v8.30.1 AS secrets
FROM python:3.12-slim
COPY --from=secrets /usr/bin/gitleaks /usr/local/bin/gitleaks

ARG TRIVY_VERSION=0.74.0
ARG SYFT_VERSION=1.51.1

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TRIVY_CACHE_DIR=/trivy-cache

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates curl \
    && curl -sSfL "https://github.com/aquasecurity/trivy/releases/download/v${TRIVY_VERSION}/trivy_${TRIVY_VERSION}_Linux-64bit.tar.gz" \
       | tar -xz -C /usr/local/bin trivy \
    && curl -sSfL "https://github.com/anchore/syft/releases/download/v${SYFT_VERSION}/syft_${SYFT_VERSION}_linux_amd64.tar.gz" \
       | tar -xz -C /usr/local/bin syft \
    && apt-get purge -y curl && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "psycopg[binary]==3.3.5" "semgrep==1.172.0"

# 빌드 시점에 네 도구가 전부 실행되는지 확인한다. 의존성 하나가 다른 도구를 죽이면
# 이미지 빌드가 실패해야지, 도입 검증이 통째로 실패하는 것으로 드러나면 안 된다.
RUN set -eu; \
    semgrep --version >/dev/null; \
    syft version >/dev/null; \
    trivy --version >/dev/null; \
    gitleaks version >/dev/null; \
    python -c "import psycopg"; \
    echo "scanner toolchain OK"

RUN useradd --uid 10002 --create-home worker \
    && mkdir -p /work /reports /trivy-cache \
    && chown -R worker:worker /work /reports /trivy-cache

COPY --chown=worker:worker intake_worker.py /app/intake_worker.py
COPY --chown=worker:worker exit_terms.py /app/exit_terms.py
COPY gitleaks.toml /rules/gitleaks.toml
USER worker
WORKDIR /app
CMD ["python", "intake_worker.py"]
