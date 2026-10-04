#!/usr/bin/env bash
# 내 PC 연결 — 이 파일 하나를 실행하고 권한 확인에 응하면 끝난다.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ${EUID} -ne 0 ]]; then
  command -v sudo >/dev/null || { echo "관리자 권한이 필요합니다. root로 실행하세요." >&2; exit 2; }
  # The one elevation: sudo keeps SUDO_USER, which is the employee this device is connected for.
  exec sudo -p "관리자 권한 확인 - %u 비밀번호: " /usr/bin/env python3 "$HERE/bootstrap.py" "$@"
fi
exec python3 "$HERE/bootstrap.py" "$@"
