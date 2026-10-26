#!/bin/sh
set -eu
generation="$(readlink /run/console-tls/current)"
caddy run --config /etc/caddy/Caddyfile --adapter caddyfile &
server=$!
trap 'kill -TERM "$server" 2>/dev/null || true' TERM INT
(
  while sleep 60; do
    current="$(readlink /run/console-tls/current)"
    if [ "$generation" != "$current" ]; then
      # Caddy 2.11.4 reloads from its source on USR1 without the admin API.
      kill -USR1 "$server"
      generation="$current"
    fi
  done
) &
watcher=$!
trap 'kill "$watcher" 2>/dev/null || true' EXIT
wait "$server"
