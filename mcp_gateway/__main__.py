"""Run the proxy locally or in a container."""
import argparse
import os

import uvicorn

from .app import create_app
from .config import load_config


def main() -> None:
    parser = argparse.ArgumentParser(description="MCP Streamable HTTP reverse proxy")
    parser.add_argument("--config", default=os.environ.get("MCP_PROXY_CONFIG", "proxy.toml"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    arguments = parser.parse_args()
    try:
        settings = load_config(arguments.config)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"configuration error: {type(error).__name__}; check the config file and credential environment\n")
    uvicorn.run(create_app(settings), host=arguments.host, port=arguments.port, access_log=False)


if __name__ == "__main__":
    main()
