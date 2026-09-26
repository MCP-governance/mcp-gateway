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

RUN pip install --no-cache-dir "psycopg[binary]==3.3.5" "semgrep==1.172.0" \
    "opentelemetry-api==1.44.0" "opentelemetry-sdk==1.44.0" \
    "opentelemetry-exporter-otlp-proto-http==1.44.0"

# mcp-scan과 semgrep은 같은 site-packages에 들어갈 수 없다.
#
# semgrep 1.172.0은 `semgrep mcp` 서브커맨드 때문에 cli.py가 import 시점에
# `from mcp.server.fastmcp import FastMCP`를 한다. 즉 mcp<2를 요구한다.
# aig-mcp-scan은 mcp 2.x를 요구한다. 한 환경에 둘 다 넣으면 나중에 설치한 쪽이
# 이기고, semgrep은 `--version`조차 ModuleNotFoundError로 죽는다. 그러면 SAST가
# 빠진 채로 검증이 실패해 도입 요청이 전부 FAILED가 된다.
#
# 이 저장소는 library_lab에서 이미 같은 결론을 냈다: 패키지 충돌은 숨기지 않고
# 환경을 나눈다. mcp-scan만 별도 venv에 두고 CLI만 PATH로 노출한다.
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && git clone --filter=blob:none https://github.com/Tencent/AI-Infra-Guard.git /opt/ai-infra-guard \
    && git -C /opt/ai-infra-guard checkout "$AIG_REF" \
    && python -m venv /opt/mcp-scan-venv \
    && /opt/mcp-scan-venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/mcp-scan-venv/bin/pip install --no-cache-dir /opt/ai-infra-guard/mcp-scan \
    && ln -s /opt/mcp-scan-venv/bin/aig-mcp-scan /usr/local/bin/aig-mcp-scan \
    && rm -rf /opt/ai-infra-guard/.git \
    && rm -rf /var/lib/apt/lists/*

# 빌드 시점에 네 도구가 전부 실행되는지 확인한다. 이 줄이 없어서 위의 충돌이
# 런타임까지 조용히 살아 있었다. 의존성 하나가 다른 도구를 죽이면 이미지 빌드가
# 실패해야지, 도입 검증이 통째로 실패하는 것으로 드러나면 안 된다.
RUN set -eu; \
    semgrep --version >/dev/null; \
    syft version >/dev/null; \
    trivy --version >/dev/null; \
    aig-mcp-scan --help >/dev/null; \
    python -c "import psycopg, opentelemetry.trace"; \
    echo "scanner toolchain OK"

RUN useradd --uid 10002 --create-home worker \
    && mkdir -p /work /reports /trivy-cache \
    && chown -R worker:worker /work /reports /trivy-cache

COPY --chown=worker:worker intake_worker.py /app/intake_worker.py
USER worker
WORKDIR /app
CMD ["python", "intake_worker.py"]
