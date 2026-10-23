#!/usr/bin/env bash
# 내 PC 연결 — 이 파일 하나를 실행하고 권한 확인에 응하면 끝난다.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOOTSTRAP="$HERE/bootstrap.py"
PYTHON="$(command -v python3 || true)"
if [[ $(uname -s) == Darwin ]]; then
  exec /bin/bash "$HERE/install-macos.sh" "$@"
fi
[[ -n $PYTHON ]] || { echo "Python 3.8 이상 설치가 필요합니다." >&2; exit 2; }
# Before any Python of the kit runs: on Ubuntu 16.04·18.04 (Python 3.5·3.6) it would stop on a syntax
# error. Claude Code and Codex need Ubuntu 20.04 or later anyway.
if ! "$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 8))' 2>/dev/null; then
  OS_NAME="$( (. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME") || uname -sr)"
  echo "이 PC(${OS_NAME}, $("$PYTHON" -V 2>&1))는 지원하지 않습니다. Ubuntu 20.04 이상(Python 3.8 이상)에서 설치하세요." >&2
  exit 2
fi

if [[ ${EUID} -ne 0 ]]; then
  command -v sudo >/dev/null || { echo "관리자 권한이 필요합니다. root로 실행하세요." >&2; exit 2; }
  # The one elevation: sudo keeps SUDO_USER, which is the employee this device is connected for.
  exec sudo -p "관리자 권한 확인 - %u 비밀번호: " "$PYTHON" -I -B "$BOOTSTRAP" "$@"
fi
# -B: the kit sits in the employee's own folder, and root-owned __pycache__ there is something they
# cannot delete afterwards.
exec "$PYTHON" -I -B "$BOOTSTRAP" "$@"
