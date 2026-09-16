# 도입 요청 격리 검증 워커. Gateway 이미지와 분리한 이유는 스캐너 도구 체인과
# git이 정책 집행 프로세스와 같은 파일시스템에 있을 이유가 없기 때문이다.
FROM python:3.12-slim

ARG TRIVY_VERSION=0.74.0
ARG SYFT_VERSION=1.51.1
# AI-Infra-Guard는 전체 플랫폼이 아니라 mcp-scan CLI만, 커밋 고정으로 설치한다.
ARG AIG_REF=036c39bd03b39ce4a811f7f125bc3b8f47e39b7c

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

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && git clone --filter=blob:none https://github.com/Tencent/AI-Infra-Guard.git /opt/ai-infra-guard \
    && git -C /opt/ai-infra-guard checkout "$AIG_REF" \
    && pip install --no-cache-dir /opt/ai-infra-guard/mcp-scan \
    && rm -rf /opt/ai-infra-guard/.git \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --uid 10002 --create-home worker \
    && mkdir -p /work /reports /trivy-cache \
    && chown -R worker:worker /work /reports /trivy-cache

COPY --chown=worker:worker intake_worker.py /app/intake_worker.py
USER worker
WORKDIR /app
CMD ["python", "intake_worker.py"]
