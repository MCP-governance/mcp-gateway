# One image for nine of the ten MCP servers (Playwright uses Microsoft's image).
# Every server is installed here at a pinned version so the containers need no
# internet at runtime, and each Python server gets its own venv: they pin
# different `mcp` SDK versions and one shared venv silently downgrades one of them.
# All of them are written against the 1.x SDK; left unpinned, pip picks mcp 2.x
# (FastMCP renamed, request_ctx removed) and mcp-proxy / postgres-mcp fail to import.
FROM docker.gitea.com/gitea-mcp-server:1.7.0 AS gitea_mcp
FROM node:22-bookworm-slim AS node

# postgres-mcp 0.3.0 requires pglast==7.2.0 (PEP 440 equivalent to 7.2).
# PyPI no longer serves that release. Build its exact upstream source, preserving
# the server's dependency contract rather than substituting a newer parser.
# pglast v7.2: GPL-3.0-or-later; libpg_query is its pinned upstream submodule.
# Compiler and source checkout stay in this build stage.
FROM python:3.12-slim-bookworm AS pglast_builder
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential git ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && git init /src/pglast \
 && git -C /src/pglast remote add origin https://github.com/lelit/pglast.git \
 && git -C /src/pglast fetch --depth 1 origin eed764e2160222e40499061b02870328e4a3ed33 \
 && git -C /src/pglast checkout --detach FETCH_HEAD \
 && test "$(git -C /src/pglast rev-parse HEAD)" = eed764e2160222e40499061b02870328e4a3ed33 \
 && git -C /src/pglast submodule update --init --depth 1 \
 && test "$(git -C /src/pglast/libpg_query rev-parse HEAD)" = 27b2af9474003da843fb93bba59fe4297841291b \
 && python -m pip install --no-cache-dir setuptools==80.9.0 wheel==0.45.1 \
 && python -m pip wheel --use-pep517 --no-build-isolation --no-deps --wheel-dir /wheelhouse /src/pglast

FROM python:3.12-slim-bookworm
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ripgrep ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*

COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
COPY --from=pglast_builder /wheelhouse /opt/pglast-wheels
COPY --from=pglast_builder /src/pglast/README.rst /usr/local/share/doc/pglast/README.rst
COPY --from=pglast_builder /src/pglast/libpg_query/LICENSE /usr/local/share/doc/pglast/libpg_query-LICENSE
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

# --ignore-scripts: desktop-commander's postinstall reports the installation to
# its vendor. A lab image must not phone home while it is being built.
RUN npm install -g --ignore-scripts --no-fund --no-audit --prefix /opt/node \
      @modelcontextprotocol/server-filesystem@2026.8.31 \
      @modelcontextprotocol/server-memory@2026.8.31 \
      @wonderwhy-er/desktop-commander@0.2.51 \
 && npm cache clean --force

RUN set -eux; \
    for spec in proxy:mcp-proxy==0.12.0 git:mcp-server-git==2026.8.18 fetch:mcp-server-fetch==2026.8.18 \
                postgres:postgres-mcp==0.3.0 redis:redis-mcp-server==0.5.1 email:mcp-email-server==1.9.1; do \
      name="${spec%%:*}"; pkg="${spec#*:}"; \
      python -m venv "/opt/venvs/$name"; \
      "/opt/venvs/$name/bin/pip" install --no-cache-dir --find-links=/opt/pglast-wheels "$pkg" "mcp>=1.17,<2"; \
      "/opt/venvs/$name/bin/pip" check; \
    done; \
    /opt/venvs/postgres/bin/python -c 'from importlib.metadata import version; from pglast import parse_sql; assert version("pglast") == "7.2"; assert parse_sql("SELECT 1")'

# mcp-server-fetch uses readabilipy, which runs `npm install` *at request time* the
# first time it sees node without its JavaScript dependencies. Inside the internal
# network that npm call hangs until the tool call times out - and anywhere else it
# is an unreviewed package download triggered by a tool call. Install them now.
RUN cd /opt/venvs/fetch/lib/python3.12/site-packages/readabilipy/javascript \
 && npm install --omit=dev --ignore-scripts --no-fund --no-audit \
 && npm cache clean --force

COPY --from=gitea_mcp /app/gitea-mcp /usr/local/bin/gitea-mcp
COPY run-server.sh /usr/local/bin/run-server
RUN chmod 0755 /usr/local/bin/run-server \
 && useradd --uid 10001 --create-home --shell /usr/sbin/nologin mcp \
 && mkdir -p /home/mcp/.claude-server-commander \
 && printf '{"telemetryEnabled": false, "allowedDirectories": ["/workspace"], "defaultShell": "/bin/bash"}\n' \
      > /home/mcp/.claude-server-commander/config.json \
 && chown -R mcp:mcp /home/mcp

ENV PATH="/opt/node/bin:/opt/venvs/proxy/bin:${PATH}" \
    NODE_ENV=production \
    PYTHONUNBUFFERED=1
USER mcp
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/run-server"]
