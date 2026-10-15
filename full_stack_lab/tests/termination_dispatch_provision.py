"""Provision the disposable Gitea of the termination/dispatch lab: an org with the three
repositories the registry classifies, and the provider's access token for mcp-bot, written
once to the file the Gitea MCP server reads. Synthetic accounts only; runs in the lab network."""
import os
import sys

import httpx

base = os.environ["GITEA_ADMIN_URL"].rstrip("/") + "/api/v1"
auth = (os.environ["GITEA_ADMIN_USER"], os.environ["GITEA_ADMIN_PASSWORD"])
with httpx.Client(base_url=base, auth=auth, timeout=20) as client:
    def call(method, path, expect, **kwargs):
        response = client.request(method, path, **kwargs)
        if response.status_code not in expect:
            sys.exit(f"{method} {path} -> {response.status_code}")
        return response

    call("POST", "/orgs", {201, 422}, json={"username": "bob", "visibility": "private"})
    owners = next(t for t in call("GET", "/orgs/bob/teams", {200}).json() if t["name"] == "Owners")
    call("PUT", f"/teams/{owners['id']}/members/mcp-bot", {204})
    for name in ("payment-service", "infra-secrets", "handbook"):
        call("POST", "/orgs/bob/repos", {201, 409}, json={"name": name, "private": True, "auto_init": True})
    token = call("POST", "/users/mcp-bot/tokens", {201}, headers={"Sudo": "mcp-bot"},
                 json={"name": "gitea-mcp-server", "scopes": ["all"]}).json()["sha1"]
    with open("/secrets/gitea-mcp.token", "w", encoding="utf-8") as handle:
        handle.write(token)
    os.chmod("/secrets/gitea-mcp.token", 0o644)
print("provisioned")
