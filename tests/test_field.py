"""Field deployment: the appliance overlay and the employee-PC kit (field/pc/mcpgw_pc.py).

The kit tests never touch this machine's real Claude Code or Codex configuration: homes are
temporary directories and the `claude` CLI is replaced by a recorder.
"""
import ast
import importlib.util
import json
import os
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

from examples.demo_server import create_demo_app
from mcp_gateway.app import create_app
from mcp_gateway.config import load_config

ROOT = Path(__file__).resolve().parent.parent
KIT_PATH = ROOT / "field" / "pc" / "mcpgw_pc.py"


@pytest.fixture
def kit(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("mcpgw_pc_under_test", KIT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("MCPGW_HOME", str(tmp_path / "kit home"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    calls = []

    def fake_run(command):
        calls.append(command[1:])
        exists = command[1:3] == ["mcp", "get"] and command[3] in module.fake_claude_servers
        return subprocess.CompletedProcess(command, 0 if command[1:3] != ["mcp", "get"] or exists else 1, "", "")

    module.fake_claude_servers = set()
    module.claude_calls = calls
    monkeypatch.setattr(module, "run", fake_run)
    monkeypatch.setattr(module.shutil, "which", lambda name: "claude" if name == "claude" else None)
    return module


def setup(kit, tmp_path, monkeypatch, *extra, key="mcpp_test_secret_value"):
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(key + "\n"))
    kit.main(["setup", "--url", "https://mcp-gw.internal/", "--servers", "demo,files", "--key-stdin", *extra])


# -- appliance -------------------------------------------------------------------

def test_field_proxy_config_turns_on_keys_record_and_console(monkeypatch):
    monkeypatch.setenv("MCP_PROXY_ADMIN_TOKEN", "field-console-token-0123")
    settings = load_config(ROOT / "field" / "proxy.field.toml")
    assert settings.auth.providers == ("keys",)
    assert settings.store.path and settings.store.record_arguments is False
    assert settings.admin.token == "field-console-token-0123"
    assert settings.servers["demo"].url == "http://demo:9000/mcp"


def test_caddyfile_terminates_tls_streams_and_fences_the_console():
    text = (ROOT / "field" / "Caddyfile").read_text(encoding="utf-8")
    assert "tls internal" in text and "admin off" in text
    assert "reverse_proxy proxy:8080" in text and "flush_interval -1" in text
    fence = text[text.index("@admin_elsewhere {"):text.index("respond @admin_elsewhere 404")]
    assert "path /console /console/* /admin/*" in fence and "not remote_ip {$ADMIN_CIDR}" in fence


@pytest.mark.skipif(not shutil.which("docker"), reason="docker CLI not installed")
def test_field_overlay_publishes_only_caddy_on_the_lan_address(tmp_path):
    env = {**os.environ, "APPLIANCE_HOST": "mcp-gw.internal", "APPLIANCE_BIND": "192.0.2.10",
           "ADMIN_CIDR": "192.0.2.20/32", "MCP_PROXY_ADMIN_TOKEN": "field-console-token-0123"}
    command = ["docker", "compose", "-p", "mcpgw-field-test", "--project-directory", str(ROOT),
               "-f", str(ROOT / "compose.yaml"), "-f", str(ROOT / "compose.field.yaml"), "config", "--format", "json"]
    rendered = json.loads(subprocess.run(command, env=env, capture_output=True, encoding="utf-8", check=True).stdout)
    services = rendered["services"]
    assert [(p["host_ip"], p["published"], p["target"]) for p in services["caddy"]["ports"]] == [("192.0.2.10", "443", 443)]
    assert {p["host_ip"] for p in services["proxy"]["ports"]} == {"127.0.0.1"}
    assert "ports" not in services["demo"]
    mounts = {m["target"]: m["source"] for m in services["proxy"]["volumes"]}
    assert Path(mounts["/app/proxy.toml"]).name == "proxy.field.toml"
    # Without a LAN address the overlay refuses to render instead of opening every interface.
    missing = {k: v for k, v in env.items() if k != "APPLIANCE_BIND"}
    assert subprocess.run(command, env=missing, capture_output=True).returncode != 0


# -- employee-PC kit ------------------------------------------------------------

@pytest.mark.parametrize("url", ["http://mcp-gw.internal", "https://user:pw@mcp-gw.internal",
                                 "https://mcp-gw.internal/?k=1", "ftp://mcp-gw.internal"])
def test_kit_refuses_plaintext_and_credentials_in_the_address(kit, url):
    with pytest.raises(SystemExit):
        kit.gateway_url(url)


def test_kit_allows_plain_http_only_on_a_loopback_tunnel(kit):
    assert kit.gateway_url("https://mcp-gw.internal/") == "https://mcp-gw.internal"
    assert kit.gateway_url("http://127.0.0.1:8080") == "http://127.0.0.1:8080"
    assert kit.gateway_url("http://localhost:8080/") == "http://localhost:8080"


def test_setup_writes_helpers_not_keys_and_keeps_the_users_codex_config(kit, tmp_path, monkeypatch):
    codex = tmp_path / "codex" / "config.toml"
    codex.parent.mkdir()
    codex.write_text('model = "gpt-5"\n\n[profiles.fast]\nmodel = "gpt-5-mini"\n', encoding="utf-8")
    setup(kit, tmp_path, monkeypatch)
    first = codex.read_text(encoding="utf-8")
    parsed = tomllib.loads(first)
    assert parsed["model"] == "gpt-5" and parsed["profiles"]["fast"]["model"] == "gpt-5-mini"
    demo = parsed["mcp_servers"]["demo"]
    assert demo["url"] == "https://mcp-gw.internal/mcp/demo/"
    assert demo["http_headers_helper"].endswith(" header") and "--home" in demo["http_headers_helper"]
    assert "mcpp_test_secret_value" not in first
    adds = [c for c in kit.claude_calls if c[:2] == ["mcp", "add-json"]]
    assert [c[4] for c in adds] == ["demo", "files"]
    entry = json.loads(adds[0][5])
    assert entry["type"] == "http" and entry["url"] == "https://mcp-gw.internal/mcp/demo/"
    assert entry["headersHelper"] == demo["http_headers_helper"]
    assert "mcpp_" not in adds[0][5]
    # Running setup again replaces the block instead of adding a second one.
    kit.fake_claude_servers.update({"demo", "files"})
    setup(kit, tmp_path, monkeypatch)
    assert codex.read_text(encoding="utf-8") == first
    home = Path(os.environ["MCPGW_HOME"])
    assert (home / "key").read_text(encoding="utf-8").strip() == "mcpp_test_secret_value"
    if os.name != "nt":
        assert (home / "key").stat().st_mode & 0o077 == 0


def test_setup_does_not_overwrite_a_server_the_user_made(kit, tmp_path, monkeypatch):
    kit.fake_claude_servers.add("files")
    with pytest.raises(SystemExit, match="이미 'files'"):
        setup(kit, tmp_path, monkeypatch)
    # Checked before anything is written: no half-configured PC to trip over on the next run.
    assert not [c for c in kit.claude_calls if c[:2] == ["mcp", "add-json"]]
    assert not Path(os.environ["MCPGW_HOME"]).exists()
    codex = tmp_path / "codex" / "config.toml"
    codex.parent.mkdir(exist_ok=True)
    codex.write_text('[mcp_servers.files]\nurl = "https://elsewhere/mcp"\n', encoding="utf-8")
    kit.fake_claude_servers.clear()
    with pytest.raises(SystemExit, match=r"mcp_servers\.files"):
        setup(kit, tmp_path, monkeypatch)


def test_helper_prints_the_header_the_harnesses_expect(kit, tmp_path, monkeypatch, capsys):
    setup(kit, tmp_path, monkeypatch, "--harness", "codex")
    capsys.readouterr()
    home = os.environ["MCPGW_HOME"]
    monkeypatch.delenv("MCPGW_HOME")  # Codex runs the helper with a cleared environment
    kit.main(["--home", home, "header"])
    assert json.loads(capsys.readouterr().out) == {"Authorization": "Bearer mcpp_test_secret_value"}


def test_uninstall_removes_only_what_setup_wrote(kit, tmp_path, monkeypatch):
    codex = tmp_path / "codex" / "config.toml"
    codex.parent.mkdir()
    codex.write_text('model = "gpt-5"\n', encoding="utf-8")
    setup(kit, tmp_path, monkeypatch)
    kit.main(["uninstall"])
    assert codex.read_text(encoding="utf-8") == 'model = "gpt-5"\n'
    assert [c[:4] for c in kit.claude_calls if c[1:2] == ["remove"]] == [
        ["mcp", "remove", "--scope", "user"]] * 2
    assert not any(Path(os.environ["MCPGW_HOME"]).iterdir())


def test_managed_files_carry_no_secret_and_pin_the_urls(kit, tmp_path):
    out = tmp_path / "managed"
    kit.main(["managed", "--url", "https://mcp-gw.internal", "--servers", "demo", "--out", str(out)])
    claude = json.loads((out / "managed-mcp.json").read_text(encoding="utf-8"))
    assert claude["mcpServers"]["demo"]["headers"] == {"Authorization": "Bearer ${MCPGW_PROXY_KEY}"}
    codex = tomllib.loads((out / "requirements.toml").read_text(encoding="utf-8"))
    assert codex["mcp_servers"]["demo"]["identity"] == {"url": "https://mcp-gw.internal/mcp/demo/"}


def test_doctor_against_a_live_proxy_with_key_auth(kit, tmp_path, monkeypatch, live_server, capsys):
    """The kit's own check, end to end over loopback (the SSH-tunnel case), with a real key."""
    config = tmp_path / "proxy.toml"
    with live_server(create_demo_app()) as origin:
        config.write_text(f'[auth]\nproviders = ["keys"]\n[store]\npath = "{(tmp_path / "p.db").as_posix()}"\n'
                          f'[servers.demo]\nurl = "{origin}/mcp"\n', encoding="utf-8")
        app = create_app(load_config(config))
        with live_server(app) as gateway:
            _, secret = app.state.runtime.store.create_key("ysg", ["demo"])
            monkeypatch.setattr("sys.stdin", __import__("io").StringIO(secret + "\n"))
            kit.main(["setup", "--url", gateway, "--servers", "demo", "--harness", "codex", "--key-stdin"])
            # The Codex install check fails here (no codex on PATH in the test); the network ones must pass.
            with pytest.raises(SystemExit):
                kit.main(["doctor"])
            lines = capsys.readouterr().out.splitlines()
            assert any(line.startswith("OK   MCP demo initialize: HTTP 200") for line in lines), lines
            assert any(line.startswith("OK   헬퍼 명령") for line in lines), lines
            monkeypatch.setattr("sys.stdin", __import__("io").StringIO("mcpp_revoked\n"))
            kit.main(["key", "--stdin"])
            with pytest.raises(SystemExit):
                kit.main(["doctor"])
            assert any("MCP demo initialize: HTTP 401" in line for line in capsys.readouterr().out.splitlines())


def test_kit_runs_on_the_oldest_supported_python_syntax():
    # Employees' PCs may have Python 3.9: no match statements or 3.10+ only syntax in the kit.
    ast.parse(KIT_PATH.read_text(encoding="utf-8"), feature_version=(3, 9))
