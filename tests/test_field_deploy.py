"""Field-deploy (실기기 배치) tests: prepare.py rendering, the realm's CLI device-flow
client, the Caddyfile's path design (no admin console exposure), and that the
override Compose file still resolves with `docker compose config` (no engine
needed -- this machine cannot run the Docker engine, see AGENTS.md/common spec)."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

import prepare

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# prepare.py rendering: loopback (default) vs field (실기기) mode

def _base_env_values():
    return prepare.load_env(ROOT / ".env.example")


def test_prepare_render_loopback_mode_matches_existing_defaults():
    values = _base_env_values()
    issuer = prepare.render(ROOT, values, field_host="")
    assert issuer == "http://127.0.0.1:18081/realms/mcp"
    realm = json.loads((ROOT / "outputs/deploy/realm.json").read_text(encoding="utf-8"))
    gateway_client = next(c for c in realm["clients"] if c["clientId"] == "mcp-gateway")
    assert gateway_client["redirectUris"] == ["http://127.0.0.1:18083/*"]
    assert gateway_client["webOrigins"] == ["http://127.0.0.1:18083"]
    config_js = (ROOT / "outputs/dashboard/config.js").read_text(encoding="utf-8")
    assert issuer in config_js


def test_prepare_render_field_mode_uses_appliance_host():
    values = _base_env_values()
    issuer = prepare.render(ROOT, values, field_host="mcp-gw.internal")
    assert issuer == "https://mcp-gw.internal/realms/mcp"
    realm = json.loads((ROOT / "outputs/deploy/realm.json").read_text(encoding="utf-8"))
    gateway_client = next(c for c in realm["clients"] if c["clientId"] == "mcp-gateway")
    assert gateway_client["redirectUris"] == ["https://mcp-gw.internal/*"]
    assert gateway_client["webOrigins"] == ["https://mcp-gw.internal"]
    config_js = (ROOT / "outputs/dashboard/config.js").read_text(encoding="utf-8")
    assert "https://mcp-gw.internal/realms/mcp" in config_js
    assert "127.0.0.1" not in config_js


def test_prepare_render_never_writes_password_into_dashboard_config():
    values = _base_env_values()
    prepare.render(ROOT, values, field_host="mcp-gw.internal")
    config_js = (ROOT / "outputs/dashboard/config.js").read_text(encoding="utf-8")
    assert values["USER_PASSWORD"] not in config_js
    assert values["ADMIN_PASSWORD"] not in config_js


def test_prepare_field_flag_requires_appliance_host(tmp_path, monkeypatch):
    fake_root = tmp_path
    (fake_root / "deploy").mkdir(parents=True)
    (fake_root / "deploy/realm.template.json").write_text(
        (ROOT / "deploy/realm.template.json").read_text(encoding="utf-8"), encoding="utf-8")
    (fake_root / ".env").write_text("USER_PASSWORD=x\nADMIN_PASSWORD=y\n", encoding="utf-8")
    monkeypatch.setattr(prepare, "ROOT", fake_root)
    monkeypatch.chdir(fake_root)
    import sys
    monkeypatch.setattr(sys, "argv", ["prepare.py", "--field"])
    with pytest.raises(SystemExit):
        prepare.main()


def test_outputs_directory_is_gitignored():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "outputs/" in gitignore


# ---------------------------------------------------------------------------
# realm template: mcp-cli device-flow client for the employee PC kit

def test_realm_template_has_device_grant_cli_client():
    realm = json.loads((ROOT / "deploy/realm.template.json").read_text(encoding="utf-8"))
    cli_client = next((c for c in realm["clients"] if c["clientId"] == "mcp-cli"), None)
    assert cli_client is not None, "mcp-cli client missing from deploy/realm.template.json"
    assert cli_client["attributes"]["oauth2.device.authorization.grant.enabled"] == "true"
    assert cli_client["publicClient"] is True
    mappers = {m["name"]: m for m in cli_client.get("protocolMappers", [])}
    assert mappers["gateway-audience"]["config"]["included.client.audience"] == "mcp-gateway"


def test_realm_template_credentials_are_placeholders_only():
    # prepare.py always overwrites these from .env; the template must never carry
    # a real secret since it is a tracked file (issue this branch fixes).
    text = (ROOT / "deploy/realm.template.json").read_text(encoding="utf-8")
    assert "change-me" in text  # documented placeholder convention used across this repo


# ---------------------------------------------------------------------------
# Caddyfile: appliance TLS front door hides the Keycloak admin console

def _handles() -> dict:
    lines = (ROOT / "deploy/Caddyfile").read_text(encoding="utf-8").splitlines()
    text = "\n".join(line for line in lines if not line.lstrip().startswith("#"))
    return {path.strip(): body for path, body in re.findall(r"handle\s+([^\{\s][^\{]*)\{((?:[^{}]|\{[^{}]*\})*)\}", text)}


def test_caddyfile_never_exposes_keycloak_admin_console_or_master_realm():
    handles = _handles()
    # Only the mcp realm's user-facing paths and theme resources reach Keycloak.
    assert sorted(path for path, body in handles.items() if "reverse_proxy keycloak" in body) == \
        ["/realms/mcp/*", "/resources/*"]
    # A top-level `respond` runs after `handle` blocks, so the refusals must be handles themselves.
    assert "respond 404" in handles["/admin*"]
    assert "respond 404" in handles["/realms/*"]


def test_caddyfile_routes_agent_service_paths():
    text = (ROOT / "deploy/Caddyfile").read_text(encoding="utf-8")
    assert "/mcp/*" in text
    assert "/v1/chat/completions" in text
    assert "reverse_proxy agent-service:8000" in text


def test_caddyfile_uses_appliance_host_placeholder():
    text = (ROOT / "deploy/Caddyfile").read_text(encoding="utf-8")
    assert "{$APPLIANCE_HOST}" in text
    assert "tls internal" in text


# ---------------------------------------------------------------------------
# Compose: base (loopback) and the field override both resolve without a running
# Docker engine ("docker compose config" only parses/merges YAML).

def _docker_available() -> bool:
    return shutil.which("docker") is not None


@pytest.mark.skipif(not _docker_available(), reason="docker CLI not on PATH")
def test_compose_field_override_config_resolves(tmp_path):
    env_path = tmp_path / ".env"
    base_env = (ROOT / ".env.example").read_text(encoding="utf-8")
    env_path.write_text(base_env + "\nAPPLIANCE_HOST=mcp-gw.internal\nAPPLIANCE_BIND=192.0.2.10\n",
                         encoding="utf-8")
    result = subprocess.run(
        ["docker", "compose", "--env-file", str(env_path),
         "-f", str(ROOT / "compose.yaml"), "-f", str(ROOT / "compose.field.yaml"),
         "config", "--quiet"],
        cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace", timeout=60)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(not _docker_available(), reason="docker CLI not on PATH")
def test_compose_field_override_publishes_only_caddy_on_appliance_bind(tmp_path):
    env_path = tmp_path / ".env"
    base_env = (ROOT / ".env.example").read_text(encoding="utf-8")
    env_path.write_text(base_env + "\nAPPLIANCE_HOST=mcp-gw.internal\nAPPLIANCE_BIND=192.0.2.10\n",
                         encoding="utf-8")
    result = subprocess.run(
        ["docker", "compose", "--env-file", str(env_path),
         "-f", str(ROOT / "compose.yaml"), "-f", str(ROOT / "compose.field.yaml"), "config"],
        cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace", timeout=60)
    assert result.returncode == 0, result.stderr
    merged = yaml.safe_load(result.stdout)
    for name, service in merged["services"].items():
        for port in service.get("ports", []):
            host_ip = port.get("host_ip") if isinstance(port, dict) else None
            if name == "caddy":
                assert host_ip == "192.0.2.10"
            else:
                assert host_ip == "127.0.0.1"
