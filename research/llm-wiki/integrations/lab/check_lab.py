"""Static boundary checks for the isolated lab; no containers or MCP calls."""
import json
from pathlib import Path

import yaml


def main():
    root = Path(__file__).resolve().parent
    compose = yaml.safe_load((root / "compose.yaml").read_text(encoding="utf-8"))
    config = yaml.safe_load((root / "litellm.yaml").read_text(encoding="utf-8"))
    provenance = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
    services = compose["services"]
    assert {"postgres", "ollama", "litellm", "caddy"} <= set(services)
    assert all("ports" not in services[name] for name in ("postgres", "ollama", "litellm"))
    ports = services["caddy"]["ports"]
    assert len(ports) == 2 and all(port.startswith("${INTEROP_BIND:?") for port in ports)
    assert compose["networks"]["model"]["internal"]
    assert services["ollama"]["networks"] == ["model"]
    assert all("@sha256:" in service["image"] for service in services.values())
    assert all("file" in secret and "${INTEROP_SECRET_DIR:?" in secret["file"]
               for secret in compose["secrets"].values())
    assert config["general_settings"]["require_key_mcp_access_defined"] is True
    assert config["mcp_servers"]["microsoft_learn"]["url"] == "https://learn.microsoft.com/api/mcp"
    assert config["mcp_servers"]["microsoft_learn"]["transport"] == "http"
    assert config["router_settings"]["num_retries"] == 0
    assert provenance["deployment_verified"] is False
    print("lab YAML/static boundary checks PASS; no container/model/MCP execution")


if __name__ == "__main__":
    main()
