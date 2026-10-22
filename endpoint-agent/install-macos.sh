#!/bin/bash
# One elevation covers the official runtime and the endpoint installation.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ $(uname -s) != Darwin ]]; then
  echo "macOS 설치 파일입니다." >&2
  exit 2
fi
if [[ ${EUID} -ne 0 ]]; then
  exec /usr/bin/sudo -p "관리자 권한 확인 - %u 비밀번호: " /bin/bash "$HERE/install-macos.sh" "$@"
fi
PYTHON=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14
if [[ ! -x $PYTHON ]]; then
  umask 077
  runtime_work=$(mktemp -d /private/tmp/mcpgw-python.XXXXXXXX)
  trap 'rm -rf -- "$runtime_work"' EXIT
  /usr/bin/curl --disable --silent --show-error --fail --proto '=https' --max-time 300 \
    https://www.python.org/ftp/python/3.14.9/python-3.14.9-macos11.pkg --output "$runtime_work/python.pkg"
  /usr/sbin/pkgutil --check-signature "$runtime_work/python.pkg" > "$runtime_work/signature"
  /usr/bin/grep -F 'Developer ID Installer: Python Software Foundation (BMM5U3QVKW)' "$runtime_work/signature" >/dev/null
  /usr/sbin/spctl --assess --type install "$runtime_work/python.pkg"
  /usr/sbin/installer -pkg "$runtime_work/python.pkg" -target / >/dev/null
  rm -rf -- "$runtime_work"
  trap - EXIT
fi
# Public program/config directories must be traversable by the managed account. Device state
# uses explicit 0700 directories and mkstemp(0600) files independently of this process umask.
umask 022
"$PYTHON" -I -B "$HERE/managed-macos.py" "$@"
