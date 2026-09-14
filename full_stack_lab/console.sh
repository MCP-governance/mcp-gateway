#!/usr/bin/env bash
set -euo pipefail

export MCP_CONSOLE_ENTRY=console.sh
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/demo.sh" "$@"
