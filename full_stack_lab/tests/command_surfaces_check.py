"""Harness command surfaces (D-147): every managed path closes user hooks, statusLine and
fileSuggestion on Claude Code and user/plugin hooks on Codex, while the Gateway header
helper stays. Stdlib only; endpoint_plane runs from its AST so no DB or SDK is loaded."""
import ast
import asyncio
import hashlib
import ipaddress
import json
import os
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit

LAB = Path(__file__).resolve().parents[1]


def check(test, claude: dict, requirements: dict, helpers: list[str]):
    test.assertIs(claude["allowManagedHooksOnly"], True)
    # Ineffective forms (D-147): null is not a valid value for these string keys.
    for key in ("statusLine", "apiKeyHelper", "otelHeadersHelper", "awsCredentialExport", "awsAuthRefresh"):
        test.assertNotIn(key, claude)
    test.assertIs(requirements["allow_managed_hooks_only"], True)
    test.assertTrue(helpers and all(helpers))


def check_connector_surfaces(test, claude: dict, servers: list[str], deny=("WebFetch", "WebSearch")):
    """Account-side surfaces PJ1 showed open on a managed account (10-23): synced plugins and WebSearch.
    On endpoints the web tools are built-in features: allowed until an administrator blocks them (D-298)."""
    test.assertIs(claude["syncClaudeAiPlugins"], False)
    test.assertIs(claude["syncClaudeAiSkills"], False)
    test.assertIs(claude["allowManagedPermissionRulesOnly"], True)
    test.assertEqual(claude["permissions"]["deny"], list(deny))
    # With user rules ignored, the Gateway servers must be allowed by the managed file or `-p` runs could not call them.
    test.assertEqual(claude["permissions"]["allow"], [f"mcp__{s}" for s in servers])


class ManagedCommandSurfaces(unittest.TestCase):
    def test_workstation_render(self):
        with tempfile.TemporaryDirectory() as raw:
            out = Path(raw)
            subprocess.run([sys.executable, str(LAB / "workstation/managed/render.py"), str(LAB / "registry/catalog.toml"),
                            str(out), "--gateway-url", "https://gateway.example/mcp"], check=True, capture_output=True)
            mcp = json.loads((out / "claude-code/managed-mcp.json").read_text(encoding="utf-8"))["mcpServers"]
            check(self, json.loads((out / "claude-code/managed-settings.json").read_text(encoding="utf-8")),
                  tomllib.loads((out / "codex/requirements.toml").read_text(encoding="utf-8")),
                  [s.get("headersHelper") for s in mcp.values()])
            self.assertNotIn("notify", tomllib.loads((out / "codex/config.toml").read_text(encoding="utf-8")))

    def test_field_kit_managed(self):
        with tempfile.TemporaryDirectory() as raw:
            out = Path(raw)
            subprocess.run([sys.executable, str(LAB / "field/pc/mcpgw_pc.py"), "managed", "--url", "https://mcp-gw.internal",
                            "--servers", "git", "--out", str(out), "--python", "/usr/bin/python3",
                            "--kit", "/opt/mcpgw/mcpgw_pc.py"], check=True, capture_output=True,
                           env={**os.environ, "HOME": raw, "PYTHONIOENCODING": "utf-8"})
            mcp = json.loads((out / "managed-mcp.json").read_text(encoding="utf-8"))["mcpServers"]
            check(self, json.loads((out / "managed-settings.json").read_text(encoding="utf-8")),
                  tomllib.loads((out / "requirements.toml").read_text(encoding="utf-8")),
                  [s.get("headersHelper") for s in mcp.values()])
            check_connector_surfaces(self, json.loads((out / "managed-settings.json").read_text(encoding="utf-8")), ["git"])

    def test_endpoint_managed_policy(self):
        path = LAB / "gateway/app/endpoint_plane.py"
        names = {"managed_policy", "managed_platform", "json_document", "installed_hash"}
        nodes = [n for n in ast.parse(path.read_text(encoding="utf-8")).body if getattr(n, "name", None) in names]
        self.assertEqual({n.name for n in nodes}, names)
        package = ModuleType("policy_under_test")
        package.pac = SimpleNamespace(servers_for=lambda owner: ["git"], harness_guidance=lambda owner, servers: "")
        package.registry = SimpleNamespace(server=lambda server: {})
        namespace = {"__name__": "endpoint_under_test", "__package__": "policy_under_test", "os": os,
                     "urlsplit": urlsplit, "ipaddress": ipaddress, "hashlib": hashlib,
                     "HEARTBEAT_INTERVAL": 60, "HEARTBEAT_SECONDS": 180,
                     "db": SimpleNamespace(fetch_all=AsyncMock(return_value=[{"id": "git"}]),
                                           fetch_one=AsyncMock(return_value={"token": "tester"}))}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
        connectors = {"__name__": "connectors_under_test"}
        source = (LAB / "gateway/app/connectors.py").read_text(encoding="utf-8")
        wanted = {"FEATURES", "CONNECTOR_SWITCHES", "controls_from"}
        exec(compile(ast.Module(body=[n for n in ast.parse(source).body if getattr(n, "name", None) in wanted
                                      or any(getattr(t, "id", None) in wanted for t in getattr(n, "targets", []))],
                                type_ignores=[]), "connectors.py", "exec"), connectors)
        open_controls = connectors["controls_from"](set(), [])
        closed = connectors["controls_from"]({"claude:feature:WebFetch", "claude:feature:WebSearch", "claude:connectors:all",
                                             "codex:feature:web_search", "codex:feature:browser_use", "codex:feature:computer_use",
                                             "codex:feature:apps"}, [])
        for platform, controls in (("linux", open_controls), ("windows", open_controls), ("linux", closed), ("windows", closed)):
            package.connectors = SimpleNamespace(managed_controls=AsyncMock(return_value=controls))
            detail = {"local_sid": "S-1-5-21-1-2-3-4", "helper_command": "helper header"} if platform == "windows" else {}
            device = {"device_epoch": "epoch", "local_username": "tester", "local_uid": 1000, "owner_token": "tester",
                      "detail": detail}
            with patch.dict(sys.modules, {"policy_under_test": package}), \
                 patch.dict(os.environ, {"IDP_ISSUER": "https://gateway.example", "ENDPOINT_GATEWAY_IPS": "100.64.0.2"}):
                files = asyncio.run(namespace["managed_policy"](device))["files"]
            mcp = json.loads(files["managed-mcp.json"])["mcpServers"]
            check(self, json.loads(files["managed-settings.json"]), tomllib.loads(files["requirements.toml"]),
                  [s.get("headersHelper") for s in mcp.values()])
            claude, requirements = json.loads(files["managed-settings.json"]), tomllib.loads(files["requirements.toml"])
            blocked = controls is closed
            check_connector_surfaces(self, claude, ["git"], ("WebFetch", "WebSearch") if blocked else ())
            # claude.ai connectors: on by default beside the managed set, off with the switch.
            self.assertIs(claude["allowAllClaudeAiMcps"], not blocked)
            self.assertIs(claude["disableClaudeAiConnectors"], blocked)
            self.assertIn({"serverUrl": "https://gateway.example/mcp/git/"}, claude["allowedMcpServers"])
            self.assertEqual({"serverUrl": "https://*/*"} in claude["allowedMcpServers"], not blocked)
            self.assertIs(requirements["features"]["plugins"], False)  # plugins are reviewed, never built in
            self.assertEqual(requirements.get("allowed_web_search_modes"), ["disabled"] if blocked else None)
            self.assertEqual(requirements["features"].get("apps"), False if blocked else None)
            self.assertEqual(requirements.get("allow_browser_and_computer_use"), False if blocked else None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
