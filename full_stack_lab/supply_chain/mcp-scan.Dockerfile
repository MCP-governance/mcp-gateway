FROM python:3.12-slim

ARG AIG_REF=036c39bd03b39ce4a811f7f125bc3b8f47e39b7c
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential git \
    && git clone --filter=blob:none https://github.com/Tencent/AI-Infra-Guard.git /opt/ai-infra-guard \
    && git -C /opt/ai-infra-guard checkout "$AIG_REF" \
    && pip install --no-cache-dir /opt/ai-infra-guard/mcp-scan \
    && apt-get purge -y --auto-remove build-essential git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/ai-infra-guard/mcp-scan
ENTRYPOINT ["aig-mcp-scan"]
