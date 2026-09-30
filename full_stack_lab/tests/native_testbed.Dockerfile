FROM node:22-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN npm install -g @anthropic-ai/claude-code@2.1.282 @openai/codex@0.158.0 && npm cache clean --force
RUN python3 -m venv /opt/mcp-test \
    && /opt/mcp-test/bin/pip install --no-cache-dir mcp==2.2.0 httpx==0.28.1 httpx2==2.12.0
ENV PATH="/opt/mcp-test/bin:${PATH}"
RUN install -d /etc/claude-code /etc/codex
COPY tests /validation/tests
COPY field/pc /validation/field/pc
ENTRYPOINT ["tail","-f","/dev/null"]
