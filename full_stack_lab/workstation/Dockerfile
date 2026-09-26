# An employee PC with the AI harnesses people actually use, installed from their
# official packages and left unmodified (D-30). What the company adds is what an IT
# department adds: managed configuration that points every sanctioned MCP server at
# the Gateway and the LLM at the company LLM gateway, an SSO credential helper, and
# the endpoint agent. The PC sits on the internal `office` network, so the Gateway
# and LiteLLM are the only MCP / model endpoints it can reach.
FROM node:22-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
      bubblewrap ca-certificates curl git jq procps iproute2 python3 \
 && rm -rf /var/lib/apt/lists/*
# Versions are pinned: a harness update changes the MCP client under test.
RUN npm install -g --no-fund --no-audit --omit=dev \
      @anthropic-ai/claude-code@2.1.282 \
      @openai/codex@0.157.0 \
      @google/gemini-cli@0.61.0 \
      opencode-ai@1.18.32 \
      @modelcontextprotocol/inspector@2.8.0 \
 && npm cache clean --force
# IT-managed configuration, rendered from the MCP registry (one Gateway URL per server).
COPY workstation/managed /opt/office/managed
COPY registry/catalog.toml /opt/office/catalog.toml
RUN python3 /opt/office/managed/render.py /opt/office/catalog.toml /opt/office/rendered \
 && install -d /etc/claude-code /etc/codex /etc/gemini-cli /etc/opencode /etc/bob \
 && cp /opt/office/rendered/claude-code/* /etc/claude-code/ \
 && cp /opt/office/rendered/codex/config.toml /etc/codex/managed_config.toml \
 && cp /opt/office/rendered/gemini-cli/settings.json /etc/gemini-cli/settings.json \
 && cp /opt/office/rendered/opencode/opencode.json /etc/opencode/opencode.json \
 && cp /opt/office/rendered/bob/servers /opt/office/managed/bob/harness-prompt.md /etc/bob/ \
 && cp /opt/office/managed/profile.sh /etc/profile.d/bob-harness.sh
COPY --chmod=0755 workstation/bin/ /usr/local/bin/
COPY workstation/scenarios /opt/office/scenarios
COPY workstation/shadow /opt/office/shadow
COPY workstation/provision_keys.py /opt/office/
COPY --from=endpoint agent.py /opt/office/endpoint_agent.py
COPY --chmod=0755 workstation/entrypoint.sh /usr/local/bin/workstation-entrypoint
RUN useradd --uid 10020 --create-home --shell /bin/bash agent
USER agent
WORKDIR /home/agent
ENV PYTHONUNBUFFERED=1 \
    OPENCODE_CONFIG=/etc/opencode/opencode.json \
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 DISABLE_AUTOUPDATER=1 DISABLE_TELEMETRY=1 DISABLE_ERROR_REPORTING=1 \
    OPENCODE_DISABLE_AUTOUPDATE=1 OPENCODE_DISABLE_LSP_DOWNLOAD=1
ENTRYPOINT ["/usr/local/bin/workstation-entrypoint"]
