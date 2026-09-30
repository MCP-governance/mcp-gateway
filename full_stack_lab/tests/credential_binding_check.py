"""Offline trust-boundary checks; live vendor calls are a separate required layer."""
import json
import os
from pathlib import Path
import tempfile
import time

from app.upstream import CredentialUnavailable, credential_headers

with tempfile.TemporaryDirectory() as root:
    path = Path(root) / 'credentials.json'
    os.environ['MCP_UPSTREAM_CREDENTIALS_FILE'] = str(path)
    endpoint = 'https://mcp.vendor.example/mcp'
    row = {'endpoint': endpoint, 'allowed_principals': ['tester'], 'expires_at': time.time()+60,
           'access_token': 'test-only-no-provider-secret'}

    def write(record):
        path.write_text(json.dumps({'credentials': [record]}))
        path.chmod(0o600)

    write(row)
    assert credential_headers(endpoint, 'tester')['Authorization'].startswith('Bearer ')
    assert credential_headers(endpoint + '?different-resource', 'tester') == {}
    for change, principal in (({}, 'other'), ({'expires_at': 1}, 'tester'),
                              ({'expires_at': None}, 'tester'), ({'expires_at': float('nan')}, 'tester'),
                              ({'allowed_principals': 'tester'}, 'tester'),
                              ({'access_token': 'x\r\nInjected: y'}, 'tester')):
        write({**row, **change})
        try:
            credential_headers(endpoint, principal)
            raise AssertionError('Invalid credential binding was accepted')
        except CredentialUnavailable:
            pass
    write(row)
    path.chmod(0o644)
    try:
        credential_headers(endpoint, 'tester')
        raise AssertionError('Readable credential file was accepted')
    except CredentialUnavailable:
        pass
print('credential binding: exact resource, principal, expiry, format and permissions PASS')
