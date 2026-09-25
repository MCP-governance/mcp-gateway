#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$HERE/install.py" "$@"

if ! command -v systemctl >/dev/null || ! systemctl --user show-environment >/dev/null 2>&1; then
  echo "사용자 systemd가 없어 자동 시작은 등록하지 않았습니다. 수동 실행:"
  echo "  python3 ~/.local/share/mcp-gateway-endpoint/agent.py --config ~/.config/mcp-gateway-endpoint/config.json --once"
  exit 0
fi

unit_dir="$HOME/.config/systemd/user"
mkdir -p "$unit_dir"
unit="$unit_dir/mcp-gateway-endpoint.service"
python3 - "$unit" "$(command -v python3)" \
  "$HOME/.local/share/mcp-gateway-endpoint/agent.py" \
  "$HOME/.config/mcp-gateway-endpoint/config.json" <<'PY'
import shlex
import sys
from pathlib import Path

unit, python, agent, config = map(Path, sys.argv[1:])
command = " ".join(shlex.quote(str(part)) for part in (python, agent, "--config", config))
unit.write_text("[Unit]\nDescription=MCP Gateway endpoint observer\n\n"
                "[Service]\nType=simple\nExecStart=" + command + "\n"
                "Restart=always\nRestartSec=30\nNoNewPrivileges=true\nUMask=0077\n\n"
                "[Install]\nWantedBy=default.target\n", encoding="utf-8")
PY
systemctl --user daemon-reload
systemctl --user enable --now mcp-gateway-endpoint.service
echo "사용자 서비스 등록 완료: systemctl --user status mcp-gateway-endpoint"
