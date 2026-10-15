"""Run real LiteLLM/model/Microsoft Learn checks; print summaries, never payloads.

The source-controlled script is an integration client, not an MCP server. Run it
only in the isolated lab. Its successful SDK tool loop does not verify managed
PJ1 admission or the enterprise Gateway's employee/device identity boundary.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import ssl
import stat
from urllib.parse import urlsplit

MODEL = "interop-qwen3-small"
SERVER = "microsoft_learn"
READ_TOOLS = {"microsoft_docs_search", "microsoft_docs_fetch", "microsoft_code_sample_search"}
API_PATHS = {"chat": "/v1/chat/completions", "responses": "/v1/responses", "messages": "/v1/messages"}


def read_file(path: Path, limit: int, private: bool) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
            raise ValueError("file_type_or_size")
        if private and (os.name != "posix" or info.st_mode & 0o077 or info.st_uid != os.geteuid()):
            raise ValueError("private_file_permissions")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            raw = stream.read(limit + 1)
        if not raw or len(raw) > limit:
            raise ValueError("file_size")
        return raw
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def read_token(path: Path) -> str:
    token = read_file(path, 16384, True).decode("utf-8").strip()
    if not token.startswith("sk-") or any(c.isspace() for c in token):
        raise ValueError("key_format")
    return token


def private_write(path: Path, raw: bytes):
    # Refuse overwrite: repeated provisioning must not erase another lab key.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)


def context_for(path: Path | None) -> ssl.SSLContext:
    context = ssl.create_default_context()
    if path is not None:
        raw = read_file(path, 1024 * 1024, False)
        if b"PRIVATE KEY" in raw:
            raise ValueError("ca_must_be_public")
        context.load_verify_locations(cadata=raw.decode("ascii"))
    return context


def validate_origin(value: str, allow_internal_http: bool) -> str:
    url = urlsplit(value)
    if not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ("", "/"):
        raise ValueError("origin_required")
    _ = url.port
    if url.scheme != "https":
        if not (allow_internal_http and url.scheme == "http" and url.hostname in {"litellm", "127.0.0.1", "localhost"}):
            raise ValueError("https_required")
    return value.rstrip("/")


def key_payload(model: str) -> dict:
    # v1.105.0 _types.py:1268-1325 and GenerateKeyRequest:1376.
    # llm_api includes MCP inference routes, not MCP/key management CRUD routes.
    return {"key_alias": "isolated-interop-probe", "duration": "30m", "models": [model],
            "user_id": "isolated-interop-probe", "key_type": "llm_api", "max_parallel_requests": 1,
            "rpm_limit": 30, "object_permission": {"mcp_servers": [SERVER],
            "mcp_tool_permissions": {SERVER: sorted(READ_TOOLS)}}}


def expiry(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("expiry_timezone")
    return parsed.astimezone(dt.timezone.utc)


async def provision(args, http):
    if args.key_file.exists() or args.key_file.with_suffix(args.key_file.suffix + ".metadata.json").exists():
        raise ValueError("refuse_existing_key")
    master = read_token(args.master_key_file)
    response = await http.post(args.base_url + "/key/generate",
                               headers={"Authorization": "Bearer " + master}, json=key_payload(args.model))
    if response.status_code != 200:
        return {"check": "provision_limited_key", "status": "failed", "http_status": response.status_code}
    body = response.json()
    token, expires = body.get("key"), body.get("expires")
    now = dt.datetime.now(dt.timezone.utc)
    if (not isinstance(token, str) or not token.startswith("sk-") or any(c.isspace() for c in token)
            or not isinstance(expires, str) or not now < expiry(expires) <= now + dt.timedelta(minutes=31)):
        raise ValueError("generated_key_or_expiry_invalid")
    metadata = {"expires_at": expires, "created_at": now.isoformat(), "model": args.model,
                "mcp_servers": [SERVER], "mcp_tools": sorted(READ_TOOLS), "duration_requested": "30m",
                "scope_source": "key/generate request and returned expiration; subsequent actual MCP checks required"}
    private_write(args.key_file, (token + "\n").encode())
    private_write(args.key_file.with_suffix(args.key_file.suffix + ".metadata.json"), json.dumps(metadata).encode())
    return {"check": "provision_limited_key", "status": "passed", "expires_at": expires,
            "model_count": 1, "mcp_server_count": 1, "mcp_tool_count": len(READ_TOOLS)}


def request_body(route: str, model: str, stream=False) -> dict:
    if route == "responses":
        return {"model": model, "input": "Reply READY.", "max_output_tokens": 128, "stream": stream}
    return {"model": model, "messages": [{"role": "user", "content": "Reply READY."}],
            "max_tokens": 128, "stream": stream}


def text_length(route: str, body: dict) -> int:
    if not isinstance(body, dict) or body.get("error"):
        return 0
    if route == "chat":
        return sum(len((c.get("message") or {}).get("content") or "") for c in body.get("choices") or [])
    if route == "messages":
        return sum(len(p.get("text") or "") for p in body.get("content") or [] if p.get("type") == "text")
    return sum(len(p.get("text") or "") for item in body.get("output") or [] if item.get("type") == "message"
               for p in item.get("content") or [] if p.get("type") == "output_text")


async def model_checks(args, http, key: str) -> list[dict]:
    rows = []
    for route, path in API_PATHS.items():
        headers = {"Authorization": "Bearer " + key}
        if route == "messages":
            headers["anthropic-version"] = "2023-06-01"
        row = {"check": route + "_normal", "status": "failed"}
        try:
            async with asyncio.timeout(args.timeout):
                response = await http.post(args.base_url + path, headers=headers, json=request_body(route, args.model))
            row["http_status"] = response.status_code
            if response.status_code == 200:
                body = response.json()
                row.update({"response_id": body.get("id"), "text_length": text_length(route, body)})
                if row["text_length"] > 0 and (route != "responses" or body.get("status") == "completed"):
                    row["status"] = "passed"
        except Exception as exc:
            row["error_type"] = type(exc).__name__
        rows.append(row)
        rows.append(await stream_check(args, http, key, route))
    for name, token, model, accepted in [("invalid_key", "sk-isolated-invalid-key", args.model, {401, 403}),
                                        ("unknown_model", key, "isolated-unconfigured-model", {400, 401, 403, 404})]:
        row = {"check": name, "status": "failed"}
        try:
            response = await http.post(args.base_url + API_PATHS["chat"], headers={"Authorization": "Bearer " + token},
                                       json=request_body("chat", model))
            row.update({"http_status": response.status_code, "status": "passed" if response.status_code in accepted else "failed"})
        except Exception as exc:
            row["error_type"] = type(exc).__name__
        rows.append(row)
    return rows


async def stream_check(args, http, key, route):
    row = {"check": route + "_stream", "status": "failed", "event_count": 0, "text_length": 0,
           "completed": False, "stream_error": False}
    headers = {"Authorization": "Bearer " + key}
    if route == "messages":
        headers["anthropic-version"] = "2023-06-01"
    try:
        async with asyncio.timeout(args.timeout):
            async with http.stream("POST", args.base_url + API_PATHS[route], headers=headers,
                                   json=request_body(route, args.model, True)) as response:
                row["http_status"] = response.status_code
                if response.status_code != 200:
                    return row
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        row["completed"] = True
                        continue
                    body = json.loads(data)
                    row["event_count"] += 1
                    if body.get("error") or body.get("type") in {"error", "response.failed", "response.incomplete"}:
                        row["stream_error"] = True
                    if route == "chat":
                        for choice in body.get("choices") or []:
                            row["text_length"] += len((choice.get("delta") or {}).get("content") or "")
                            if choice.get("finish_reason") is not None:
                                row["completed"] = True
                    elif route == "responses":
                        if body.get("type") == "response.output_text.delta":
                            row["text_length"] += len(body.get("delta") or "")
                        if body.get("type") == "response.completed":
                            row["completed"] = (body.get("response") or {}).get("status") == "completed"
                    else:
                        if body.get("type") == "content_block_delta":
                            row["text_length"] += len((body.get("delta") or {}).get("text") or "")
                        if body.get("type") == "message_stop":
                            row["completed"] = True
        if row["text_length"] > 0 and row["completed"] and not row["stream_error"]:
            row["status"] = "passed"
    except Exception as exc:
        row["error_type"] = type(exc).__name__
    return row


def selected_tools(tools) -> dict:
    selected = {}
    for tool in tools:
        suffix = tool.name.removeprefix(SERVER + "-")
        if suffix not in READ_TOOLS or not tool.name.startswith(SERVER + "-"):
            raise ValueError("ungranted_tool_visible")
        selected[tool.name] = tool
    if not selected or not any(name.endswith("microsoft_docs_search") for name in selected):
        raise ValueError("expected_tools_missing")
    return selected


async def mcp_checks(args, key, verify):
    import httpx2
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client
    rows = []
    headers = {"x-litellm-api-key": "Bearer " + key, "x-mcp-servers": SERVER}
    try:
        async with asyncio.timeout(args.timeout * 4):
            async with httpx2.AsyncClient(timeout=args.timeout, verify=verify, trust_env=False,
                                         follow_redirects=False, headers=headers) as http:
                async with Client(streamable_http_client(args.base_url + "/mcp", http_client=http),
                                  read_timeout_seconds=args.timeout) as client:
                    listed = await client.list_tools()
                    allowed = selected_tools(listed.tools)
                    rows.append({"check": "native_mcp_initialize_list", "status": "passed", "tool_count": len(allowed),
                                 "protocol_version": str(client.protocol_version)})
                    rows.append(await model_tool_loop(args, http, key, client, allowed))
        for selector, expect_empty in [("__ungranted_unknown__", True), (SERVER + ",__ungranted_unknown__", False)]:
            row = {"check": "unknown_scope_only" if expect_empty else "mixed_scope_no_expansion", "status": "failed"}
            try:
                async with asyncio.timeout(args.timeout):
                    async with httpx2.AsyncClient(timeout=args.timeout, verify=verify, trust_env=False, follow_redirects=False,
                            headers={"x-litellm-api-key": "Bearer " + key, "x-mcp-servers": selector}) as http:
                        async with Client(streamable_http_client(args.base_url + "/mcp", http_client=http),
                                          read_timeout_seconds=args.timeout) as client:
                            listed = await client.list_tools()
                            row["tool_count"] = len(listed.tools)
                            if expect_empty:
                                row["status"] = "passed" if not listed.tools else "failed"
                            else:
                                selected_tools(listed.tools)
                                row["status"] = "passed"
            except Exception as exc:
                # MCP-specific errors are not proof of permission denial. Keep them
                # unconfirmed until the HTTP/policy outcome is independently known.
                row["error_type"] = type(exc).__name__
                row["status"] = "unconfirmed"
            rows.append(row)
    except Exception as exc:
        rows.append({"check": "native_mcp_initialize_list", "status": "failed", "error_type": type(exc).__name__})
    return rows


async def model_tool_loop(args, http, key, client, allowed):
    import jsonschema
    row = {"check": "real_model_official_sdk_read_loop", "status": "failed", "model_selected_tool_verified": False}
    messages = [{"role": "user", "content": "Use the documentation search tool to look up Azure Key Vault managed identity. Do not answer without using the tool."}]
    functions = [{"type": "function", "function": {"name": t.name, "description": t.description or "",
                  "parameters": t.input_schema}} for t in allowed.values() if t.name.endswith("microsoft_docs_search")]
    response = await http.post(args.base_url + API_PATHS["chat"], headers={"Authorization": "Bearer " + key},
                               json={"model": args.model, "messages": messages, "tools": functions, "max_tokens": 256})
    row["http_status"] = response.status_code
    if response.status_code != 200:
        return row
    body = response.json()
    row["response_id"] = body.get("id")
    choices = body.get("choices") or []
    message = choices[0].get("message") if choices else None
    calls = message.get("tool_calls") if isinstance(message, dict) else None
    if not isinstance(calls, list) or len(calls) != 1:
        row["tool_call_count"] = len(calls) if isinstance(calls, list) else 0
        return row
    call = calls[0]
    name = (call.get("function") or {}).get("name")
    if name not in allowed or not name.endswith("microsoft_docs_search"):
        raise ValueError("model_selected_ungranted_tool")
    arguments = json.loads(call["function"]["arguments"])
    jsonschema.validate(arguments, allowed[name].input_schema)
    result = await client.call_tool(name, arguments)
    row.update({"tool_call_id": call.get("id"), "tool_name": name,
                "arguments_sha256": hashlib.sha256(json.dumps(arguments, sort_keys=True).encode()).hexdigest(),
                "mcp_is_error": bool(result.is_error), "content_item_count": len(result.content or [])})
    text = "\n".join(item.text for item in result.content or [] if getattr(item, "type", None) == "text")
    row["tool_result_length"] = len(text)
    if result.is_error or not text:
        return row
    row["model_selected_tool_verified"] = True
    # The result comes from the real read-only server. Bound follow-up context,
    # report truncation, and never print raw provider text or tool arguments.
    messages += [message, {"role": "tool", "tool_call_id": call["id"], "content": text[:6000]}]
    follow = await http.post(args.base_url + API_PATHS["chat"], headers={"Authorization": "Bearer " + key},
                             json={"model": args.model, "messages": messages, "max_tokens": 128})
    row.update({"followup_http_status": follow.status_code, "followup_context_truncated": len(text) > 6000})
    if follow.status_code == 200:
        length = text_length("chat", follow.json())
        row["final_text_length"] = length
        if length > 0:
            row["status"] = "passed"
    return row


async def run(args):
    import httpx2
    verify = context_for(args.ca_file)
    async with httpx2.AsyncClient(timeout=args.timeout, verify=verify, trust_env=False, follow_redirects=False) as http:
        if args.provision:
            return {"scope": "isolated_lab_provisioning", "results": [await provision(args, http)]}
        key = read_token(args.key_file)
        meta_path = args.key_file.with_suffix(args.key_file.suffix + ".metadata.json")
        metadata = json.loads(read_file(meta_path, 65536, True))
        if expiry(metadata["expires_at"]) <= dt.datetime.now(dt.timezone.utc):
            raise ValueError("virtual_key_expired")
        if metadata.get("model") != args.model or metadata.get("mcp_servers") != [SERVER]:
            raise ValueError("key_metadata_scope_mismatch")
        rows = await model_checks(args, http, key)
        rows += await mcp_checks(args, key, verify)
        return {"scope": "isolated_actual_litellm_model_and_official_public_mcp",
                "configured_version": "1.105.0", "installed_version_verified_by_this_client": False,
                "virtual_key_expires_at": metadata["expires_at"], "private_ca_configured": args.ca_file is not None,
                "enterprise_gateway_identity_verified": False, "managed_pj1_harness_verified": False,
                "native_litellm_mcp_autoexecute_verified": False, "results": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--ca-file", type=Path)
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--allow-internal-http", action="store_true")
    parser.add_argument("--provision", action="store_true")
    parser.add_argument("--master-key-file", type=Path)
    args = parser.parse_args()
    try:
        if not 1 <= args.timeout <= 120 or (args.provision and args.master_key_file is None):
            raise ValueError("invalid_arguments")
        args.base_url = validate_origin(args.base_url, args.allow_internal_http)
        result = asyncio.run(run(args))
        okay = bool(result["results"]) and all(row["status"] == "passed" for row in result["results"])
        result["status"] = "passed" if okay else "failed_or_unconfirmed"
    except Exception as exc:
        result, okay = {"status": "failed", "error_type": type(exc).__name__}, False
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if okay else 1


if __name__ == "__main__":
    raise SystemExit(main())
