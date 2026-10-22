#!/usr/bin/env bash
# 내 PC 연결 — 이 파일 하나를 실행하고 권한 확인에 응하면 끝난다.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOOTSTRAP="$HERE/bootstrap.py"
PYTHON="$(command -v python3 || true)"
if [[ $(uname -s) == Darwin ]]; then
  exec /bin/bash "$HERE/install-macos.sh" "$@"
fi
[[ -n $PYTHON ]] || { echo "Python 3.10 이상 설치가 필요합니다." >&2; exit 2; }

if [[ ${EUID} -ne 0 ]]; then
  command -v sudo >/dev/null || { echo "관리자 권한이 필요합니다. root로 실행하세요." >&2; exit 2; }
  # The one elevation: sudo keeps SUDO_USER, which is the employee this device is connected for.
  exec sudo -p "관리자 권한 확인 - %u 비밀번호: " "$PYTHON" -I -B "$BOOTSTRAP" "$@"
fi
# -B: the kit sits in the employee's own folder, and root-owned __pycache__ there is something they
# cannot delete afterwards.
exec "$PYTHON" -I -B "$BOOTSTRAP" "$@"
