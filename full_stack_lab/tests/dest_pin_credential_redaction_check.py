"""Offline boundary tests. No sockets, database, native scanner or MCP server is started.

The stdlib-only runner executes selected production AST nodes to avoid importing the
Gateway's DB/tracing/SDK bootstrap. Native Gitleaks and SDK/TLS integration are separate checks.
"""
from __future__ import annotations

import ast
import asyncio
from contextlib import asynccontextmanager, redirect_stdout
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import socket
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import unquote, urlsplit

import httpx

LAB = Path(__file__).resolve().parent.parent
APP = LAB / "gateway" / "app"
_outcome_spec = importlib.util.spec_from_file_location("outcomes_under_test", APP / "outcomes.py")
_outcome_module = importlib.util.module_from_spec(_outcome_spec)
_outcome_spec.loader.exec_module(_outcome_module)
ROOT = LAB.parent


def selected(path, names, namespace=None):
    namespace = {"__name__": "boundary_under_test", **(namespace or {})}
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes = [node for node in tree.body if getattr(node, "name", None) in names
             or isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in node.targets)]
    found = {getattr(n, "name", None) for n in nodes}
    found.update(t.id for n in nodes if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name))
    if not set(names) <= found:
        raise AssertionError(f"missing production definitions: {set(names) - found}")
    exec(compile(ast.fix_missing_locations(ast.Module(
        body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *nodes],
        type_ignores=[])), str(path), "exec"), namespace)
    return SimpleNamespace(**namespace)


spec = importlib.util.spec_from_file_location("destination_under_test", APP / "destination.py")
destination = importlib.util.module_from_spec(spec)
spec.loader.exec_module(destination)
patterns = selected(APP / "classify.py", ["SECRET_PATTERNS"]).SECRET_PATTERNS


def redactor():
    return selected(APP / "secret_scan.py", ["ERROR_REDACTED", "_CREDENTIAL_CONTEXT", "redact_error"],
                    {"re": re, "unquote": unquote, "SECRET_PATTERNS": patterns,
                     "labels": AsyncMock(return_value=[])})


def dns(*addresses):
    return [(socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))
            for address in addresses]


class DestinationPin(unittest.IsolatedAsyncioTestCase):
    async def test_oidc_metadata_clients_get_a_fresh_pinned_transport(self):
        class OAuthClient:
            def __init__(self, *args, **kwargs):
                self.kwargs = kwargs

        module = selected(APP / "oidc.py", ["http_transport", "PinnedOAuthClient", "PinnedOAuthApp"],
                          {"settings": lambda: {"issuer": "https://issuer.example"}, "urlsplit": urlsplit,
                           "os": SimpleNamespace(getenv=lambda name, default: default),
                           "pin_transport": destination.pin_transport, "AsyncOAuth2Client": OAuthClient,
                           "StarletteOAuth2App": type("OAuthApp", (), {}),
                           "httpx": SimpleNamespace(AsyncHTTPTransport=lambda **kw: SimpleNamespace(
                               _pool=SimpleNamespace(_network_backend=object())))})
        first, second = module.PinnedOAuthClient(), module.PinnedOAuthClient()
        self.assertIs(module.PinnedOAuthApp.client_cls, module.PinnedOAuthClient)
        self.assertFalse(first.kwargs["follow_redirects"])
        self.assertFalse(first.kwargs["trust_env"])
        self.assertIsNot(first.kwargs["transport"], second.kwargs["transport"])
        self.assertIsInstance(first.kwargs["transport"]._pool._network_backend, destination.PinnedBackend)
        self.assertEqual(first.kwargs["transport"]._pool._network_backend.internal, frozenset())

    async def test_every_address_must_be_safe_before_connect(self):
        for address in ["127.0.0.1", "169.254.169.254", "::ffff:10.0.0.1", "::1", "10.0.0.1",
                        "224.0.0.1", "240.0.0.1", "100.64.0.1", "fe80::1", "::", "not-an-ip"]:
            for rows in [dns(address), dns("8.8.8.8", address), dns(address, "8.8.8.8")]:
                with self.subTest(address=address, rows=len(rows)):
                    network = SimpleNamespace(connect_tcp=AsyncMock())
                    backend = destination.PinnedBackend(network)
                    with patch.object(asyncio.get_running_loop(), "getaddrinfo", AsyncMock(return_value=rows)):
                        with self.assertRaises(destination.DestinationBlocked) as caught:
                            await backend.connect_tcp("vendor.example", 443, timeout=1)
                    self.assertEqual(caught.exception.policy_id, "MCP-EGRESS-001")
                    network.connect_tcp.assert_not_awaited()

    async def test_public_then_loopback_rebind_never_reaches_connector(self):
        network = SimpleNamespace(connect_tcp=AsyncMock(return_value="stream"))
        backend = destination.PinnedBackend(network, target=("vendor.example", 443))
        resolver = AsyncMock(side_effect=[dns("8.8.8.8"), dns("127.0.0.1")])
        with patch.object(asyncio.get_running_loop(), "getaddrinfo", resolver):
            self.assertEqual(await backend.connect_tcp("vendor.example", 443, timeout=1), "stream")
            self.assertEqual(resolver.await_count, 1)
            self.assertEqual(network.connect_tcp.call_args.kwargs["host"], "8.8.8.8")
            with self.assertRaises(destination.DestinationBlocked):
                await backend.connect_tcp("vendor.example", 443, timeout=1)
        self.assertEqual(network.connect_tcp.await_count, 1)

    async def test_internal_approval_is_exact_and_dns_still_pinned(self):
        network = SimpleNamespace(connect_tcp=AsyncMock(return_value="internal"))
        backend = destination.PinnedBackend(network, internal=[("mcp-filesystem", 8000)],
                                             target=("mcp-filesystem", 8000))
        with patch.object(asyncio.get_running_loop(), "getaddrinfo", AsyncMock(return_value=dns("172.20.0.4"))):
            self.assertEqual(await backend.connect_tcp("mcp-filesystem", 8000), "internal")
            with self.assertRaises(destination.DestinationBlocked):
                await backend.connect_tcp("mcp-filesystem", 8080)
        self.assertEqual(network.connect_tcp.call_args.kwargs["host"], "172.20.0.4")

    async def test_resolution_failure_empty_and_timeout_are_closed(self):
        for reply in [socket.gaierror("synthetic"), asyncio.TimeoutError(), []]:
            resolver = AsyncMock(side_effect=reply) if isinstance(reply, Exception) else AsyncMock(return_value=reply)
            network = SimpleNamespace(connect_tcp=AsyncMock())
            with patch.object(asyncio.get_running_loop(), "getaddrinfo", resolver):
                with self.assertRaises(destination.DestinationBlocked):
                    await destination.PinnedBackend(network).connect_tcp("vendor.example", 443, timeout=1)
            network.connect_tcp.assert_not_awaited()

    async def test_registered_network_location_not_contract_deployment_defines_internal(self):
        registry = SimpleNamespace(servers=Mock(return_value={"a": {"endpoint": "http://mcp-a:8000/mcp",
                                                                   "deployment": "provider"}}))
        db = SimpleNamespace(fetch_one=AsyncMock(return_value=None))
        module = selected(APP / "upstream.py", ["_internal_endpoint"],
                          {"registry": registry, "db": db, "urlsplit": urlsplit, "re": re})
        self.assertTrue(await module._internal_endpoint("http://mcp-a:8000/mcp"))
        db.fetch_one.assert_not_awaited()
        registry.servers.return_value["a"]["deployment"] = "internal"
        self.assertTrue(await module._internal_endpoint("http://mcp-a:8000/mcp"))
        self.assertFalse(await module._internal_endpoint("http://unapproved:8000/mcp"))
        db.fetch_one.return_value = {"id": "approved-executor"}
        self.assertTrue(await module._internal_endpoint("http://executor:8000/mcp"))
        self.assertIn("status='ACTIVE'", db.fetch_one.call_args.args[0])
        for host in ("github.example", "127.0.0.1", "2130706433", "0x7f000001"):
            endpoint = f"https://{host}/mcp"
            registry.servers.return_value["a"] = {"endpoint": endpoint, "deployment": "internal"}
            self.assertFalse(await module._internal_endpoint(endpoint))

    async def test_actual_provider_email_gitea_connect_privately_but_github_cannot(self):
        catalog = (LAB / "registry/catalog.toml").read_text(encoding="utf-8")
        servers = {}
        for name in ("email", "gitea"):
            section = catalog.split(f"[servers.{name}]", 1)[1].split("\n[", 1)[0]
            servers[name] = dict(re.findall(r'^(endpoint|deployment) = "([^"]+)"$', section, re.M))
            self.assertEqual(servers[name]["deployment"], "provider")
            self.assertEqual(servers[name]["endpoint"], f"http://mcp-{name}:8000/mcp")
        servers["github"] = {"endpoint": "https://api.githubcopilot.com/mcp/", "deployment": "provider"}
        module = selected(APP / "upstream.py", ["_internal_endpoint"],
                          {"registry": SimpleNamespace(servers=lambda: servers), "re": re, "urlsplit": urlsplit,
                           "db": SimpleNamespace(fetch_one=AsyncMock(side_effect=AssertionError("unexpected runtime lookup")))})
        for name, spec in servers.items():
            url = urlsplit(spec["endpoint"])
            target = (url.hostname, url.port or 443)
            internal = await module._internal_endpoint(spec["endpoint"])
            connector = AsyncMock(return_value="stream")
            backend = destination.PinnedBackend(SimpleNamespace(connect_tcp=connector),
                                                 internal=[target] if internal else [], target=target)
            with patch.object(asyncio.get_running_loop(), "getaddrinfo", AsyncMock(return_value=dns("172.20.0.4"))):
                if name == "github":
                    self.assertFalse(internal)
                    with self.assertRaises(destination.DestinationBlocked) as caught:
                        await backend.connect_tcp(*target)
                    self.assertEqual(caught.exception.policy_id, "MCP-EGRESS-001")
                    connector.assert_not_awaited()
                else:
                    self.assertTrue(internal)
                    self.assertEqual(await backend.connect_tcp(*target), "stream")
                    self.assertEqual(connector.call_args.kwargs["host"], "172.20.0.4")

    async def test_keycloak_discovery_and_dynamic_backchannel_origins_are_pinned(self):
        compose = (LAB / "compose.keycloak.yaml").read_text(encoding="utf-8")
        discovery = re.search(r"^      OIDC_DISCOVERY_URL: (.+)$", compose, re.M).group(1)
        self.assertIn('KC_HOSTNAME_BACKCHANNEL_DYNAMIC: "true"', compose)
        self.assertEqual(discovery, "http://keycloak:8080/realms/mcpgw/.well-known/openid-configuration")
        transports = []

        def transport(**kwargs):
            connector = AsyncMock(return_value="stream")
            result = SimpleNamespace(_pool=SimpleNamespace(_network_backend=SimpleNamespace(connect_tcp=connector)))
            transports.append((result, connector))
            return result

        module = selected(APP / "oidc.py", ["http_transport"],
                          {"settings": lambda: {"issuer": "http://127.0.0.1:18090/realms/mcpgw"}, "os": os,
                           "urlsplit": urlsplit, "pin_transport": destination.pin_transport,
                           "httpx": SimpleNamespace(AsyncHTTPTransport=transport)})
        urls = [discovery, *["http://keycloak:8080/realms/mcpgw/protocol/openid-connect/" + path
                            for path in ("certs", "token", "token/introspect", "revoke", "userinfo")]]
        with patch.dict(os.environ, {"OIDC_DISCOVERY_URL": discovery}):
            for value in urls:
                backend = module.http_transport()._pool._network_backend
                self.assertEqual(backend.internal, frozenset({("127.0.0.1", 18090), ("keycloak", 8080)}))
                url = urlsplit(value)
                with patch.object(asyncio.get_running_loop(), "getaddrinfo", AsyncMock(return_value=dns("172.20.0.8"))):
                    self.assertEqual(await backend.connect_tcp(url.hostname, url.port), "stream")
                self.assertEqual(transports[-1][1].call_args.kwargs["host"], "172.20.0.8")
            for target in (("unapproved-backchannel", 8080), ("keycloak", 9999), ("issuer.example", 443)):
                backend = module.http_transport()._pool._network_backend
                with patch.object(asyncio.get_running_loop(), "getaddrinfo", AsyncMock(return_value=dns("172.20.0.8"))):
                    with self.assertRaises(destination.DestinationBlocked):
                        await backend.connect_tcp(*target)
                transports[-1][1].assert_not_awaited()

    async def test_egress_failure_has_correct_decision_even_in_cause(self):
        module = selected(APP / "core.py", ["_upstream_failure"],
                          {"DestinationBlocked": destination.DestinationBlocked, "httpx": httpx,
                           "output_contract": selected(APP / "output_contract.py", ["WireRejected", "OutputSchemaTooComplex"]),
                           "_root_cause": lambda exc: "safe error",
                           "local_verdict": lambda policy, decision, reason, **kw:
                           {"policy_id": policy, "decision": decision, **kw}})
        error = RuntimeError("transport failed")
        error.__cause__ = destination.DestinationBlocked("blocked")
        result = module._upstream_failure(error, {})
        self.assertEqual((result["decision"], result["policy_id"]), ("Block", "MCP-EGRESS-001"))
        self.assertFalse(result["upstream_executed"])
        self.assertFalse(result["upstream_attempted"])


class CredentialRedaction(unittest.IsolatedAsyncioTestCase):
    async def test_unexpected_mcp_handler_errors_do_not_echo_exception_text(self):
        module = selected(APP / "mcp_facade.py", ["build_mcp"],
                          {"Server": lambda *a, **kw: SimpleNamespace(**kw),
                           "_caller": AsyncMock(side_effect=RuntimeError("Authorization: Bearer synthetic-secret"))})
        server = module.build_mcp()
        for handler in [server.on_call_tool, server.on_list_tools]:
            with self.assertRaises(ValueError) as caught:
                await handler(None, None)
            self.assertNotIn("synthetic-secret", str(caught.exception))

    async def test_http_and_validation_error_details_keep_shape_only_when_safe(self):
        module = selected(APP / "main.py", ["_error_detail"], {"secret_scan": redactor(), "json": json})
        self.assertEqual(await module._error_detail({"input": "ghp_" + "aB3d" * 9}), "[REDACTED]")
        self.assertEqual(await module._error_detail("Authorization: Bearer short"), "[REDACTED]")
        self.assertEqual(await module._error_detail({"message": "ordinary"}), {"message": "ordinary"})

    async def test_issuer_tokens_and_credential_contexts_are_withheld(self):
        tokens = ["ghp_" + "aB3d" * 9, "sk-" + "aB3d" * 10,
                  "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0." + "aB3d" * 10]
        module = redactor()
        for token in tokens:
            for message in [str(ValueError("request failed " + token)), "x" * 490 + token, "Bearer " + token]:
                self.assertEqual(await module.redact_error(message), "[REDACTED]")
        for value in ["Authorization: Bearer tiny", "{'Authorization': 'Basic short'}",
                      "https://vendor.example/?access_token=tiny", "https://vendor.example/?api_key=abc",
                      "https://vendor.example/?api%5Fkey=abc", "client_secret=short", "refresh_token=short"]:
            self.assertEqual(await module.redact_error(value), "[REDACTED]")

    async def test_same_native_scanner_failure_and_unknown_secret(self):
        module = redactor()
        scanner = module.redact_error.__globals__["labels"]
        scanner.return_value = ["gitleaks:vendor-specific"]
        self.assertEqual(await module.redact_error("unknown vendor diagnostic"), "[REDACTED]")
        scanner.assert_awaited_once_with("unknown vendor diagnostic")
        scanner.side_effect = RuntimeError("synthetic scanner outage")
        self.assertEqual(await module.redact_error("ordinary diagnostic"), "[REDACTED]")
        scanner.side_effect, scanner.return_value = None, []
        self.assertEqual(await module.redact_error("ordinary diagnostic"), "ordinary diagnostic")
        self.assertIsNone(await module.redact_error(None))

    async def test_audit_and_returned_payload_share_redacted_error_before_hash(self):
        scanned = redactor()
        connection = SimpleNamespace(execute=AsyncMock())

        @asynccontextmanager
        async def transaction():
            yield connection

        fingerprint = Mock(return_value="safe fingerprint")
        env = {"secret_scan": scanned, "db": SimpleNamespace(transaction=transaction), "Jsonb": lambda v: v,
               "outcome_axes": _outcome_module.outcome_axes,
               "datetime": datetime, "UTC": timezone.utc, "hashlib": hashlib, "GENESIS": "0" * 64,
               "CHAIN_VERSION": 1, "GATEWAY_ENVIRONMENT": "test", "_audit_fingerprint": fingerprint,
               "response_disposition": lambda e: "not_executed", "_audit_payload": lambda v: v,
               "_release_call": AsyncMock(), "time": SimpleNamespace(perf_counter=lambda: 1)}
        module = selected(APP / "core.py", ["_record_decision", "_storable", "_decision_payload", "AUTO_SUSPEND_POLICIES"], env)
        rendered = selected(APP / "mcp_facade.py", ["_render"],
                            {"types": SimpleNamespace(TextContent=lambda **kw: SimpleNamespace(**kw),
                                                      CallToolResult=lambda **kw: SimpleNamespace(**kw)),
                             "DECISION_LABEL": {"Block": "차단"}, "response_disposition": lambda e: "not_executed"})
        for token in ["ghp_" + "aB3d" * 9, "sk-" + "aB3d" * 10,
                      "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0." + "aB3d" * 10]:
            connection.execute.reset_mock()
            connection.execute.side_effect = [
                SimpleNamespace(fetchone=AsyncMock(return_value={"head_sha256": "0" * 64})),
                SimpleNamespace(fetchone=AsyncMock(return_value={"id": 7})), None]
            event = {"request_id": "synthetic", "trace_id": "trace", "user_token": "tester", "role": "staff",
                     "tool_name": "read", "data_class": "public", "action": "r", "decision": "Block",
                     "policy_id": "MCP-UPSTREAM-001", "reason": "failed", "upstream_executed": False,
                     "error": str(ValueError("upstream failed " + token))}
            result = await module._decision_payload(event, SimpleNamespace(view=lambda: {}, started=0))
            self.assertEqual(result["error"], "[REDACTED]")
            self.assertEqual(fingerprint.call_args.args[0]["error"], "[REDACTED]")
            self.assertEqual(connection.execute.call_args_list[1].args[1][15], "[REDACTED]")
            self.assertNotIn(token, repr(connection.execute.call_args_list))
            self.assertNotIn(token, rendered._render(result).content[0].text)


class KitCredentials(unittest.TestCase):
    def test_field_settings_files_and_entire_cli_argument_lists_contain_no_token(self):
        spec = importlib.util.spec_from_file_location("field_kit_under_test", LAB / "field/pc/mcpgw_pc.py")
        kit = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(kit)
        tokens = ["ghp_" + "aB3d" * 9, "sk-" + "aB3d" * 10, "fake-refresh-secret"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.dict(os.environ, {"MCPGW_HOME": str(root / "home"), "CODEX_HOME": str(root / "codex"),
                                         "HOME": str(root), "USERPROFILE": str(root)}):
                settings = {"url": "https://gateway.example", "servers": ["git"], "harnesses": ["claude", "codex"]}
                kit.write_private(kit.home() / "token.json", json.dumps(dict(zip(["access_token", "refresh_token", "other"], tokens))))
                with patch.object(kit, "access_token", side_effect=AssertionError("renderer read a token")), \
                     patch.object(kit, "run", Mock(return_value=SimpleNamespace(returncode=0))) as run, \
                     patch.object(kit, "claude_path", return_value="claude"), redirect_stdout(io.StringIO()):
                    kit.setup_claude(settings, False)
                    kit.setup_codex(settings, False)
                    kit.main(["managed", "--url", settings["url"], "--servers", "git", "--out", str(root / "managed"),
                              "--python", sys.executable, "--kit", str(root / "kit.py")])
                files = [p.read_text(encoding="utf-8") for p in (root / "managed").iterdir()]
                files.append(kit.codex_config().read_text(encoding="utf-8"))
                serialized = repr([files, run.call_args_list, kit.helper_command()])
                for token in tokens:
                    self.assertNotIn(token, serialized)
                self.assertIn("headersHelper", serialized)
                self.assertIn("http_headers_helper", serialized)


class ManagedKitCredentials(unittest.IsolatedAsyncioTestCase):
    async def test_endpoint_managed_policy_and_os_file_writers_use_only_helpers(self):
        package = ModuleType("policy_under_test")
        package.pac = SimpleNamespace(servers_for=lambda owner: ["git"], harness_guidance=lambda owner, servers: "")
        module = selected(APP / "endpoint_plane.py", ["managed_policy", "managed_platform", "json_document", "installed_hash"],
                          {"__package__": "policy_under_test", "os": os, "urlsplit": urlsplit,
                           "ipaddress": __import__("ipaddress"), "hashlib": hashlib,
                           "HEARTBEAT_INTERVAL": 60, "HEARTBEAT_SECONDS": 180,
                           "db": SimpleNamespace(fetch_all=AsyncMock(return_value=[{"id": "git"}]),
                                                 fetch_one=AsyncMock(return_value={"token": "tester"}))})
        token = "sk-" + "aB3d" * 10
        for platform in ["linux", "windows"]:
            detail = {"access_token": token, "device_key": token}
            if platform == "windows":
                detail.update(local_sid="S-1-5-21-1-2-3-4",
                              helper_command='"C:\\Python\\python.exe" -I -S "C:\\Kit\\managed-windows.py" header')
            device = {"device_epoch": "epoch", "local_username": "tester", "local_uid": 1000,
                      "owner_token": "tester", "device_key": token, "detail": detail}
            with patch.dict(sys.modules, {"policy_under_test": package}), \
                 patch.dict(os.environ, {"IDP_ISSUER": "https://gateway.example", "ENDPOINT_GATEWAY_IPS": "100.64.0.2"}):
                policy = await module.managed_policy(device)
            self.assertNotIn(token, json.dumps(policy))
            self.assertIn("headersHelper", policy["files"]["managed-mcp.json"])
            self.assertTrue(any("http_headers_helper" in text for text in policy["files"].values()))
            with tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary)
                if platform == "linux":
                    targets = {name: folder / name for name in policy["files"]}
                    writer = selected(ROOT / "endpoint-agent/managed-linux.py", ["apply_policy"],
                                      {"FILES": targets, "protected": lambda p: True,
                                       "private_write": lambda p, text: p.write_text(text, encoding="utf-8")})
                    writer.apply_policy(policy)
                else:
                    targets = {name: folder / name for name in policy["files"] if name != "codex-config.toml"}
                    writer = selected(ROOT / "endpoint-agent/managed-windows.py", ["apply_policy"],
                                      {"FILES": targets, "CODEX_BLOCK": "codex-config.toml", "lock_down": lambda p: None,
                                       "codex_config": lambda c: folder / "config.toml",
                                       "checked_codex_text": lambda p: p.read_text(encoding="utf-8") if p.exists() else "",
                                       "STATE": folder / "state",
                                       "with_codex_block": lambda current, block: current + block,
                                       "write_file": lambda p, text: p.write_text(text, encoding="utf-8")})
                    writer.apply_policy({}, policy)
                self.assertTrue(list(folder.iterdir()))
                for path in folder.iterdir():
                    self.assertNotIn(token, path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
