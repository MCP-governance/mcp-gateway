#!/bin/sh
# Start one MCP server as a Streamable HTTP endpoint on :8000/mcp.
#
# stdio-only servers go behind mcp-proxy in stateless mode, so the Gateway talks to
# every upstream the same way. The flags live here, in the repository, instead of in
# compose commands: a changed flag changes the server's tool descriptions and
# therefore its approved contract hash, and that change should show up in review.
set -eu
id="${1:?usage: run-server <server-id>}"
proxy() { exec mcp-proxy --host 0.0.0.0 --port 8000 --stateless --pass-environment -- "$@"; }

case "$id" in
  filesystem)
    proxy /opt/node/bin/mcp-server-filesystem /shared ;;
  memory)
    MEMORY_FILE_PATH="${MEMORY_FILE_PATH:-/data/memory.jsonl}" proxy /opt/node/bin/mcp-server-memory ;;
  desktop)
    cd /workspace
    proxy /opt/node/bin/desktop-commander ;;
  git)
    proxy /opt/venvs/git/bin/mcp-server-git ;;
  fetch)
    proxy /opt/venvs/fetch/bin/mcp-server-fetch --ignore-robots-txt \
      --user-agent "BobCorpAssistant/2.0 (+http://intranet.bob.local)" ;;
  postgres)
    proxy /opt/venvs/postgres/bin/postgres-mcp --access-mode=unrestricted ;;
  redis)
    proxy /opt/venvs/redis/bin/redis-mcp-server --url "${REDIS_URL:?}" ;;
  email)
    exec /opt/venvs/email/bin/mcp-email-server streamable-http --host 0.0.0.0 --port 8000 ;;
  gitea)
    # The access token is the provider's server-held credential (paper 3.2). It is
    # read from a file written by corp-seed, never from the Gateway, and it is not
    # printed. Revoking it in Gitea is the only thing that stops this server's
    # access to the repositories - blocking the Gateway route does not.
    GITEA_ACCESS_TOKEN="$(cat "${GITEA_TOKEN_FILE:-/run/corp-secrets/gitea-mcp.token}")"
    export GITEA_ACCESS_TOKEN
    exec gitea-mcp -t http -p 8000 -H "${GITEA_HOST:?}" ;;
  *)
    echo "unknown MCP server id: $id" >&2
    exit 2 ;;
esac
