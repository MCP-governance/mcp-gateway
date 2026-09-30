#!/usr/bin/env python3
"""Opt-in live vendor MCP probes. No mock, no LLM, no response bodies in reports.

Run probe/call in the existing Gateway image on an egress-capable test network.
OAuth credentials stay in the isolated Codex profile, mounted read-only.
This client is intentionally outside Gateway; it does not prove Gateway enforcement.
"""
import argparse
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SERVERS = {
    "github": "https://api.githubcopilot.com/mcp/readonly",
    "supabase": "https://mcp.supabase.com/mcp?read_only=true&features=docs",
    "sentry": "https://mcp.sentry.dev/mcp",
    "notion": "https://mcp.notion.com/mcp",
    "figma": "https://mcp.figma.com/mcp",
    "zapier": "https://mcp.zapier.com/api/v1/connect",
    "context7": "https://mcp.context7.com/mcp",
}
SMOKE = {
    "github": ("get_file_contents", {"owner": "github", "repo": "github-mcp-server", "path": "LICENSE"}),
    "supabase": ("search_docs", {"graphql_query": '{searchDocs(query:"MCP read only",limit:1){nodes{title href}}}'}),
    "sentry": ("find_organizations", {}),
    "notion": ("notion-search", {"query": "mcpgw-boundary-synthetic-no-match-20260930", "page_size": 1}),
    "figma": ("whoami", {}),
    "zapier": ("discover_zapier_actions", {"app": "GitHub"}),
    "context7": ("query-docs", {"libraryId": "/websites/fastapi_tiangolo", "query": "FastAPI ASGI application startup"}),
}


def setup(profile):
    root = Path(profile)
    for name in ("codex", "claude"):
        (root / name).mkdir(parents=True, exist_ok=True, mode=0o700)
    codex = 'mcp_oauth_credentials_store_mode = "file"\nmcp_oauth_callback_port = 29431\n'
    codex += "".join(f'\n[mcp_servers.{name}]\nurl = {json.dumps(url)}\n'
                     'startup_timeout_sec = 30\ntool_timeout_sec = 45\n' for name, url in SERVERS.items())
    files = {root / "codex/config.toml": codex,
             root / "claude/.claude.json": json.dumps({"mcpServers": {
                 name: {"type": "http", "url": url} for name, url in SERVERS.items()}}, indent=2)}
    for path, content in files.items():
        if path.exists():
            raise SystemExit(f"existing profile preserved: {path}")
        path.write_text(content + "\n", encoding="utf-8")
        path.chmod(0o600)
    print("Installed seven official remote MCP definitions; OAuth is a separate step.")


def headers(name, credentials):
    # Only use a vendor token for its exact recorded resource; never forward Gateway SSO.
    if credentials and Path(credentials).exists():
        for row in json.loads(Path(credentials).read_text(encoding="utf-8")).values():
            if row.get("server_name") == name and row.get("server_url") == SERVERS[name]:
                expiry = row.get("expires_at") or 0
                # Native Codex stores Unix milliseconds; accept seconds from older exports.
                expiry = expiry / 1000 if expiry > 100_000_000_000 else expiry
                if expiry and expiry <= time.time():
                    raise ValueError("expired vendor token; refresh through the native client")
                return {"Authorization": "Bearer " + row["access_token"]}
    if name == "github" and os.getenv("GITHUB_MCP_TOKEN"):
        return {"Authorization": "Bearer " + os.environ["GITHUB_MCP_TOKEN"]}
    return {}


def native(args):
    """Actual vendor servers are the positive controls; change policies only in a disposable container."""
    if os.getenv("MCPGW_DISPOSABLE") != "1" or os.geteuid() != 0:
        raise SystemExit("native needs a disposable workstation container, root, MCPGW_DISPOSABLE=1")
    import importlib.util
    spec = importlib.util.spec_from_file_location("pc_kit", Path(__file__).parent.parent / "field/pc/mcpgw_pc.py")
    kit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kit)
    paths = [Path("/etc/claude-code") / n for n in ("managed-mcp.json", "managed-settings.json")]
    paths += [Path("/etc/codex") / n for n in ("requirements.toml", "managed_config.toml")]
    previous = {p: p.read_bytes() if p.exists() else None for p in paths}
    try:
        for path in paths:
            path.unlink(missing_ok=True)
        with tempfile.TemporaryDirectory(prefix="real-mcp-native-") as directory:
            root = Path(directory)
            setup(root)
            os.environ.update(HOME=str(root), CODEX_HOME=str(root / "codex"), CLAUDE_CONFIG_DIR=str(root / "claude"))
            if args.credentials:
                shutil.copyfile(args.credentials, root / "codex/.credentials.json")
                (root / "codex/.credentials.json").chmod(0o600)
            codex = (root / "codex/config.toml").read_text()
            codex = codex.replace('[mcp_servers.github]\n', '[mcp_servers.github]\nbearer_token_env_var = "GITHUB_MCP_TOKEN"\n')
            (root / "codex/config.toml").write_text(codex)
            claude = json.loads((root / "claude/.claude.json").read_text())
            for name, server in claude["mcpServers"].items():
                server["headersHelper"] = (f'{sys.executable} {Path(__file__).resolve()} headers --server {name} '
                                           f'--credentials {args.credentials}')
            (root / "claude/.claude.json").write_text(json.dumps(claude))

            def status(phase):
                started = time.time()
                reply = kit.codex_rpc(args.codex, "mcpServerStatus/list", {"detail": "toolsAndAuthOnly"}, timeout=90)
                if reply is None:
                    raise AssertionError("native Codex probe failed")
                counts = {row["name"]: len(row.get("tools", {})) for row in reply.get("data", [])}
                listed = subprocess.run(["claude", "mcp", "list"], capture_output=True, text=True, timeout=90)
                if listed.returncode != 0:
                    raise AssertionError("native Claude probe failed")
                connected = [name for name in SERVERS if any(line.startswith(name + ":") and "Connected" in line
                                                             for line in listed.stdout.splitlines())]
                print(json.dumps({"phase": phase, "started_at": started, "finished_at": time.time(),
                                  "codex_tools": counts, "claude_connected": connected,
                                  "model_invoked": False}), flush=True)
                return counts, connected

            counts, connected = status("unmanaged")
            assert all(counts.get(name, 0) for name in SERVERS), "positive control: Codex did not load all seven real servers"
            assert set(connected) == set(SERVERS), "positive control: Claude did not connect to all seven real servers"
            # A real Gateway profile, generated by the same field kit IT deploys. Its entries are distinct from the seven direct vendor URLs.
            subprocess.run([sys.executable, str(Path(__file__).parent.parent / "field/pc/mcpgw_pc.py"), "managed",
                            "--url", args.gateway_url, "--servers", args.gateway_servers, "--out", str(root / "managed"),
                            "--python", sys.executable, "--kit", str(Path(__file__).parent.parent / "field/pc/mcpgw_pc.py")],
                           capture_output=True, check=True)
            for name in ("managed-mcp.json", "managed-settings.json"):
                Path("/etc/claude-code", name).write_bytes((root / "managed" / name).read_bytes())
            Path("/etc/codex/requirements.toml").write_bytes((root / "managed/requirements.toml").read_bytes())
            counts, connected = status("managed-gateway-only")
            assert not any(counts.get(name, 0) for name in SERVERS) and not connected, "direct vendor MCP escaped native policy"
            print(json.dumps({"native_policy_check": "PASS", "servers": list(SERVERS),
                              "external_effect_oracle": "requires independent packet capture; listing is not sufficient"}), flush=True)
    finally:
        for path, data in previous.items():
            path.unlink(missing_ok=True) if data is None else path.write_bytes(data)


async def probe(args, name):
    import httpx2
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client

    result = {"server": name, "endpoint_origin": SERVERS[name].split("/", 3)[2],
              "evidence_mode": "live-vendor-mcp", "model_invoked": False,
              "gateway_traversed": False, "mcp_call_passed": False}
    try:
        async with httpx2.AsyncClient(timeout=45, trust_env=False, follow_redirects=False,
                                     headers=headers(name, args.credentials)) as http:
            async with Client(streamable_http_client(SERVERS[name], http_client=http),
                              read_timeout_seconds=45) as client:
                tools = (await client.list_tools()).tools
                contract = [{"name": t.name, "description": t.description, "input_schema": t.input_schema}
                            for t in sorted(tools, key=lambda t: t.name)]
                result.update(status="CONNECTED", server_version=client.server_info.version,
                              tools_count=len(tools), tools=[t.name for t in tools],
                              contract_sha256=hashlib.sha256(json.dumps(contract, sort_keys=True).encode()).hexdigest())
                if args.contracts:
                    folder = Path(args.contracts)
                    folder.mkdir(parents=True, exist_ok=True)
                    (folder / f"{name}.json").write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
                if args.command in {"call", "smoke"}:
                    tool, arguments = SMOKE[name] if args.command == "smoke" else (args.tool, json.loads(args.arguments))
                    if tool not in {t.name for t in tools}:
                        raise ValueError("selected tool is not advertised")
                    call = await client.call_tool(tool, arguments)
                    # Responses may contain private account data. Keep only an integrity digest and size.
                    data = json.dumps([c.model_dump(mode="json") for c in call.content], sort_keys=True).encode()
                    result.update(tool=tool, is_error=call.is_error, response_bytes=len(data),
                                  response_sha256=hashlib.sha256(data).hexdigest(), mcp_call_passed=not call.is_error)
    except Exception as error:
        # Exception strings can include bearer headers, callback state, URLs or private response bodies.
        result.update(status="INCOMPLETE", error_type=type(error).__name__)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result.get("status") == "CONNECTED" and (args.command not in {"call", "smoke"} or result["mcp_call_passed"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("setup", "probe", "call", "smoke", "headers", "native"))
    parser.add_argument("--profile", default=str(Path.home() / ".mcpgw-real-mcp"))
    parser.add_argument("--credentials", help="isolated Codex .credentials.json (never commit)")
    parser.add_argument("--github-credential-stdin", action="store_true", help="read GitHub test token from stdin, never argv")
    parser.add_argument("--server", choices=tuple(SERVERS))
    parser.add_argument("--contracts", help="private/gitignored tool contract output directory")
    parser.add_argument("--tool")
    parser.add_argument("--arguments", default="{}", help="public/test inputs only; no credentials")
    parser.add_argument("--codex", default="codex", help="native Codex executable for disposable probe")
    parser.add_argument("--gateway-url", default="http://100.83.175.111:443", help="approved test Gateway URL")
    parser.add_argument("--gateway-servers", default="ms-learn", help="approved test Gateway server IDs")
    args = parser.parse_args()
    if args.github_credential_stdin:
        os.environ["GITHUB_MCP_TOKEN"] = sys.stdin.read().strip()
    if args.command == "setup":
        setup(args.profile)
        return
    if args.command == "headers":
        print(json.dumps(headers(args.server, args.credentials)))
        return
    if args.command == "native":
        native(args)
        return
    if args.command == "call" and (not args.server or not args.tool):
        parser.error("call needs --server and --tool")

    async def run():
        return await asyncio.gather(*(probe(args, name) for name in ([args.server] if args.server else SERVERS)))

    raise SystemExit(0 if all(asyncio.run(run())) else 1)


if __name__ == "__main__":
    main()
