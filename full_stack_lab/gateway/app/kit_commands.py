"""File-mediated macOS bootstrap: the terminal command contains no download credential."""
import re
from urllib.parse import urlsplit

MACOS_COMMAND = '/bin/bash "$HOME/Downloads/mcp-connect-macos.command"'


def macos_bootstrap(public, ticket, certificate, isolated=False):
    parsed = urlsplit(public)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.path not in ('', '/')
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or any(c in public for c in '\r\n"\\') or not re.fullmatch(r'[A-Za-z0-9_-]{43}', ticket)):
        raise ValueError('HTTPS 게이트웨이 주소와 다운로드 자격을 확인하세요')
    if not certificate or '\nMCPGW_CA\n' in certificate:
        raise ValueError('게이트웨이 루트 인증서가 필요합니다')
    # The whole block is parsed before unlinking $0. No token in argv, history or environment.
    return f'''#!/bin/bash
set +x
(
set -euo pipefail
umask 077
work=$(mktemp -d "${{TMPDIR:-/tmp}}/mcpgw-connect.XXXXXXXX")
trap 'rm -rf -- "$work"' EXIT
trap 'exit 130' INT TERM HUP
chmod 600 "$0"
rm -f -- "$0"
cat > "$work/root.crt" <<'MCPGW_CA'
{certificate.rstrip()}
MCPGW_CA
cat > "$work/request.conf" <<'MCPGW_REQUEST'
url = "{public.rstrip('/')}/api/pc-kit?platform=macos{'&isolated=true' if isolated else ''}"
request = "POST"
header = "Authorization: Bearer kit-download.{ticket}"
MCPGW_REQUEST
/usr/bin/curl --disable --silent --show-error --fail --proto '=https' --max-time 120 --cacert "$work/root.crt" --config "$work/request.conf" --output "$work/kit.zip"
rm -f -- "$work/request.conf"
/usr/bin/unzip -q "$work/kit.zip" -d "$work/kit"
rm -f -- "$work/kit.zip"
/bin/bash "$work/kit/install.sh"
)
'''
