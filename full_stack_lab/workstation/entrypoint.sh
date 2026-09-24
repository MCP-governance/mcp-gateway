#!/bin/sh
# Workstation start: place the MCP client configuration(s), start the endpoint
# agent in the background, then run the AI assistant in the foreground.
set -eu
mkdir -p "$HOME/.config/bob-assistant" "$HOME/inbox" "$HOME/outbox" "$HOME/transcripts"
# The managed config: one MCP server, the Gateway. This is what IT deploys.
cp /opt/office/configs/managed.mcp.json "$HOME/.config/bob-assistant/mcp.json"
if [ "${SHADOW_MCP_CONFIG:-0}" = "1" ]; then
  # What this person added on their own: a direct connection to a registered server
  # (bypassing the Gateway) and a personal local filesystem server.
  mkdir -p "$HOME/.cursor"
  cp /opt/office/configs/shadow.mcp.json "$HOME/.cursor/mcp.json"
fi
if [ -n "${ENDPOINT_DEVICE_KEY:-}" ]; then
  ENDPOINT_ID="${WORKSTATION_ID}" ENDPOINT_CONFIG_PATHS="$HOME" ENDPOINT_GATEWAY_URL="${GATEWAY_URL:-http://gateway:8080}" \
    python /opt/office/endpoint_agent.py 2>&1 | sed -u 's/^/[endpoint] /' &
fi
exec python /opt/office/office_agent.py serve
