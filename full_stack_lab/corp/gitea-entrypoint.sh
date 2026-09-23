#!/bin/sh
# Start Gitea (rootless image) and create the organisation's admin account once.
# The admin is the company, not the MCP provider: it is what lets the organisation
# list and revoke the Gitea MCP server's token and so collect C2/C4 evidence itself.
set -eu
/usr/local/bin/docker-entrypoint.sh "$@" &
server=$!
until wget -qO- http://127.0.0.1:3000/api/healthz >/dev/null 2>&1; do
  kill -0 "$server" 2>/dev/null || exit 1
  sleep 1
done
if [ ! -f /var/lib/gitea/.admin-ready ]; then
  gitea admin user create --config /etc/gitea/app.ini --admin \
    --username "${GITEA_ADMIN_USER:-corpadmin}" --password "${GITEA_ADMIN_PASSWORD:?}" \
    --email admin@bob.local --must-change-password=false >/dev/null 2>&1 || true
  touch /var/lib/gitea/.admin-ready
fi
wait "$server"
