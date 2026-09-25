"""Render the IT-managed harness configuration from the MCP registry (D-30).

Every approved server becomes one entry per harness, pointing at the Gateway's
`/mcp/<server>/` with the SSO token - what IT would push to PCs with MDM. Run at
image build, so a server added to registry/catalog.toml reaches every harness on the
next build and the four formats cannot drift apart.

    python3 render.py <catalog.toml> <out-root>
"""
import json
import sys
import tomllib
from pathlib import Path

GATEWAY = "http://gateway:8080/mcp"
MODEL = "bob-assistant"

catalog, root = Path(sys.argv[1]), Path(sys.argv[2])
servers = sorted(tomllib.loads(catalog.read_text(encoding="utf-8"))["servers"])


def url(server: str) -> str:
    return f"{GATEWAY}/{server}/"


def write(relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def merge(relative: str, extra: dict) -> None:
    """Template (static, reviewed) + the server list (generated)."""
    template = json.loads((Path(__file__).parent / relative).read_text(encoding="utf-8"))
    write(relative, json.dumps({**template, **extra}, ensure_ascii=False, indent=2) + "\n")


# Claude Code: managed-mcp.json takes exclusive control of MCP servers; the token comes
# from headersHelper, re-run by Claude Code before it expires.
write("claude-code/managed-mcp.json", json.dumps({"mcpServers": {
    s: {"type": "http", "url": url(s), "headersHelper": "/usr/local/bin/bob-sso header"} for s in servers
}}, indent=2) + "\n")
template = json.loads((Path(__file__).parent / "claude-code/managed-settings.json").read_text(encoding="utf-8"))
template["permissions"]["allow"] = [f"mcp__{s}" for s in servers]
write("claude-code/managed-settings.json", json.dumps(template, ensure_ascii=False, indent=2) + "\n")

# Codex CLI: TOML, token from the environment variable bob-ask fills per run. Company
# tools are pre-approved in the harness (approve) - the decision is the Gateway's, as
# with Claude Code's permissions.allow and Gemini CLI's trust.
codex = (Path(__file__).parent / "codex/config.toml").read_text(encoding="utf-8")
codex += "".join(f'\n[mcp_servers.{s}]\nurl = "{url(s)}"\nbearer_token_env_var = "BOB_SSO_TOKEN"\n'
                 f'default_tools_approval_mode = "approve"\n'
                 f"startup_timeout_sec = 30\ntool_timeout_sec = 300\n" for s in servers)
write("codex/config.toml", codex)

# Gemini CLI (system settings, highest precedence): trust = no confirmation prompt;
# the Gateway is where the decision happens.
merge("gemini-cli/settings.json", {
    "mcpServers": {s: {"httpUrl": url(s), "headers": {"Authorization": "Bearer $BOB_SSO_TOKEN"},
                       "trust": True, "timeout": 300000} for s in servers},
    "mcp": {"allowed": servers},
})

# OpenCode: no Linux-managed location; OPENCODE_CONFIG points every user at this file.
merge("opencode/opencode.json", {
    "mcp": {s: {"type": "remote", "url": url(s), "oauth": False, "timeout": 300000,
                "headers": {"Authorization": "Bearer {env:BOB_SSO_TOKEN}"}} for s in servers},
})

write("bob/servers", "\n".join(servers) + "\n")
print(f"managed harness config: {len(servers)} servers -> {root}")
