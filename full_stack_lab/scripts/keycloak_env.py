#!/usr/bin/env python3
"""Generate local OIDC secrets without printing or overwriting operator settings."""
import os
import secrets
from pathlib import Path

path = Path(__file__).resolve().parent.parent / ".env"
text = path.read_text() if path.exists() else ""
keys = {line.split("=", 1)[0] for line in text.splitlines() if "=" in line}
values = {"OIDC_CLIENT_SECRET": secrets.token_urlsafe(48), "OIDC_SESSION_SECRET": secrets.token_urlsafe(48),
          "KEYCLOAK_ADMIN_PASSWORD": secrets.token_urlsafe(32), "AUTH_PROVIDER": "local"}
with path.open("a") as output:
    if text and not text.endswith("\n"):
        output.write("\n")
    for key, value in values.items():
        if key not in keys:
            output.write(f"{key}={value}\n")
os.chmod(path, 0o600)
print("OIDC secrets saved privately to .env; existing settings preserved. Bind identities before enabling OIDC.")
