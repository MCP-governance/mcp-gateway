#!/bin/sh
# An employee PC: the harnesses are installed and managed by IT (/etc/*), the person
# works through `bob-ask` / `workday` (or `docker compose exec ws-… claude`), and the
# endpoint agent reports what MCP configuration is on this machine.
set -eu
mkdir -p "$HOME/transcripts" "$HOME/work" "$HOME/.gemini"
# The person trusted their work folder once (Gemini CLI keeps MCP servers off in
# untrusted folders).
[ -f "$HOME/.gemini/trustedFolders.json" ] || printf '{"%s/work": "TRUST_FOLDER"}\n' "$HOME" > "$HOME/.gemini/trustedFolders.json"
if [ "${SHADOW_MCP_CONFIG:-0}" = "1" ]; then
  # What this person added on their own, next to the managed config: a direct
  # connection to a registered server (bypassing the Gateway) and a personal local
  # filesystem server. The endpoint agent reports both as shadow MCP.
  mkdir -p "$HOME/.config/opencode"
  cp /opt/office/shadow/opencode.json "$HOME/.config/opencode/opencode.json"
fi
if [ -n "${ENDPOINT_DEVICE_KEY:-}" ]; then
  export ENDPOINT_ID="${WORKSTATION_ID}" ENDPOINT_GATEWAY_URL="${GATEWAY_URL:-http://gateway:8080}"
  export ENDPOINT_CONFIG_PATHS="$HOME:/etc/claude-code:/etc/codex:/etc/gemini-cli:/etc/opencode"
  exec python3 /opt/office/endpoint_agent.py
fi
exec sleep infinity
