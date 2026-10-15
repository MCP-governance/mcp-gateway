"""Probe separate real LLM and MCP routes without changing their trust boundaries.

This is an integration client, not an MCP server. A successful model response and
tools/list are prerequisite evidence; they do not prove model-selected tool use.
Run on the designated managed PJ1 account after provisioning; --validate-only
does not read credentials or open network connections.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import ssl
import stat
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

REVIEWED_VERSIONS = {"1.102.1", "1.105.0"}
ROUTES = {"chat": "/v1/chat/completions", "responses": "/v1/responses", "messages": "/v1/messages"}
FIELDS = {"schema_version", "mode", "litellm_version", "llm_base_url", "mcp_url", "model",
          "llm_key_file", "mcp_token_file", "routes", "timeout_seconds"}
OPTIONAL_FIELDS = {"ca_file"}
MAX_CA_BYTES = 1024 * 1024


def validate_manifest(data: dict) -> dict:
    if (not isinstance(data, dict) or not FIELDS <= set(data) or set(data) - FIELDS - OPTIONAL_FIELDS
            or data.get("schema_version") != 1):
        raise ValueError("manifest_schema")
    # Aggregation with a shared service token loses the transport-authenticated
    # employee; it must not become an implicit fallback for an unsupported mode.
    if data["mode"] != "parallel_harness":
        raise ValueError("delegated_mcp_identity_not_supported")
    if data["litellm_version"] not in REVIEWED_VERSIONS:
        raise ValueError("unreviewed_litellm_version")
    for key in ("llm_base_url", "mcp_url"):
        url = urlsplit(data[key])
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("https_endpoint_required")
        if key == "llm_base_url" and url.path not in ("", "/"):
            raise ValueError("llm_base_url_must_be_origin")
    if not isinstance(data["model"], str) or not data["model"].strip() or any(c in data["model"] for c in "\r\n"):
        raise ValueError("model_required")
    if not isinstance(data["routes"], list) or not data["routes"] or any(r not in ROUTES for r in data["routes"]):
        raise ValueError("unsupported_api_route")
    if len(set(data["routes"])) != len(data["routes"]):
        raise ValueError("duplicate_api_route")
    if type(data["timeout_seconds"]) is not int or not 1 <= data["timeout_seconds"] <= 60:
        raise ValueError("timeout_range")
    paths = [PurePosixPath(data[key]) for key in ("llm_key_file", "mcp_token_file")]
    if any(not path.is_absolute() for path in paths) or paths[0] == paths[1]:
        raise ValueError("distinct_absolute_credential_files_required")
    if "ca_file" in data and (not isinstance(data["ca_file"], str)
                             or not PurePosixPath(data["ca_file"]).is_absolute()):
        raise ValueError("absolute_ca_file_required")
    return data


def tls_context(ca_file: str | None = None) -> ssl.SSLContext:
    context = ssl.create_default_context()
    if ca_file is None:
        return context
    # Read exactly the inspected regular file, rather than validate a path then
    # let OpenSSL reopen a possibly replaced or symlinked path.
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(ca_file, flags)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_CA_BYTES:
            raise ValueError("ca_bundle_size_or_type")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            raw = stream.read(MAX_CA_BYTES + 1)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if not raw or len(raw) > MAX_CA_BYTES or b"PRIVATE KEY" in raw:
        raise ValueError("ca_bundle_format")
    try:
        context.load_verify_locations(cadata=raw.decode("ascii"))
    except (UnicodeError, ssl.SSLError) as exc:
        raise ValueError("ca_bundle_format") from exc
    # Defaults continue to require a valid chain and the exact requested host.
    return context


def read_secret(path: str) -> str:
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("posix_credential_permissions_required")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.geteuid():
            raise ValueError("credential_permissions")
        token = stream.read(16385).strip()
    if not token or len(token) > 16384 or any(c.isspace() for c in token):
        raise ValueError("credential_format")
    return token


def body_for(route: str, model: str) -> dict:
    common = {"model": model}
    if route == "responses":
        return {**common, "input": "Reply READY.", "max_output_tokens": 32}
    return {**common, "messages": [{"role": "user", "content": "Reply READY."}], "max_tokens": 32}


def has_text(route: str, body: dict) -> bool:
    if not isinstance(body, dict) or body.get("error"):
        return False
    if route == "chat":
        return any(isinstance(choice, dict) and isinstance(choice.get("message"), dict)
                   and isinstance(choice["message"].get("content"), str)
                   and bool(choice["message"]["content"].strip()) for choice in body.get("choices", []))
    if route == "messages":
        return any(isinstance(part, dict) and part.get("type") == "text"
                   and isinstance(part.get("text"), str) and bool(part["text"].strip())
                   for part in body.get("content", []))
    return any(isinstance(item, dict) and item.get("type") == "message"
               and any(isinstance(part, dict) and part.get("type") == "output_text"
                       and isinstance(part.get("text"), str) and bool(part["text"].strip())
                       for part in item.get("content", [])) for item in body.get("output", []))


async def probe(data: dict) -> dict:
    import httpx2
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client

    llm_key, mcp_token = read_secret(data["llm_key_file"]), read_secret(data["mcp_token_file"])
    if llm_key == mcp_token:
        raise ValueError("credential_domains_must_be_distinct")
    if any(urlsplit(data[key]).hostname.endswith(".invalid") for key in ("llm_base_url", "mcp_url")):
        raise ValueError("example_endpoint_not_provisioned")
    timeout = data["timeout_seconds"]
    verify = tls_context(data.get("ca_file"))
    results = []
    async with httpx2.AsyncClient(timeout=timeout, trust_env=False, follow_redirects=False, verify=verify) as http:
        for route in data["routes"]:
            result = {"route": route, "status": "failed"}
            try:
                async with asyncio.timeout(timeout):
                    headers = {"Authorization": "Bearer " + llm_key}
                    if route == "messages":
                        headers["anthropic-version"] = "2023-06-01"
                    response = await http.post(data["llm_base_url"].rstrip("/") + ROUTES[route],
                                               headers=headers,
                                               json=body_for(route, data["model"]))
                result["http_status"] = response.status_code
                if response.status_code == 200 and has_text(route, response.json()):
                    result["status"] = "passed"
            except Exception as exc:
                # Provider errors can echo a key, prompt, hostname or response body.
                result["error_type"] = type(exc).__name__
            results.append(result)
    mcp_result = {"route": "mcp_initialize_and_tools_list", "status": "failed"}
    try:
        async with asyncio.timeout(timeout):
            async with httpx2.AsyncClient(timeout=timeout, trust_env=False, follow_redirects=False,
                                         verify=verify,
                                         headers={"Authorization": "Bearer " + mcp_token}) as http:
                async with Client(streamable_http_client(data["mcp_url"], http_client=http),
                                  read_timeout_seconds=timeout) as client:
                    tools = await client.list_tools()
                    mcp_result.update({"protocol_version": str(client.protocol_version), "tool_count": len(tools.tools)})
                    if tools.tools:
                        mcp_result["status"] = "passed"
    except Exception as exc:
        mcp_result["error_type"] = type(exc).__name__
    results.append(mcp_result)
    return {"status": "passed" if all(r["status"] == "passed" for r in results) else "failed",
            "evidence_level": "separate_real_model_response_and_mcp_discovery",
            "configured_litellm_version": data["litellm_version"], "runtime_version_verified": False,
            "custom_ca_configured": bool(data.get("ca_file")), "proxy_configuration_supported": False,
            "model_selected_tool_call_verified": False, "independent_business_effect_verified": False,
            "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--validate-only", action="store_true")
    action.add_argument("--run", action="store_true")
    args = parser.parse_args()
    try:
        data = validate_manifest(json.loads(args.manifest.read_text(encoding="utf-8")))
        result = ({"status": "passed", "evidence_level": "configuration_validation_only",
                   "network_contacted": False, "model_selected_tool_call_verified": False}
                  if args.validate_only else asyncio.run(probe(data)))
    except Exception as exc:
        result = {"status": "failed", "error_type": type(exc).__name__}
        if isinstance(exc, ValueError) and str(exc) in {
            "manifest_schema", "delegated_mcp_identity_not_supported", "unreviewed_litellm_version",
            "https_endpoint_required", "llm_base_url_must_be_origin", "model_required", "unsupported_api_route",
            "duplicate_api_route", "timeout_range", "distinct_absolute_credential_files_required",
            "posix_credential_permissions_required", "credential_permissions", "credential_format",
            "credential_domains_must_be_distinct", "example_endpoint_not_provisioned",
            "absolute_ca_file_required", "ca_bundle_size_or_type", "ca_bundle_format"}:
            result["error_code"] = str(exc)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
