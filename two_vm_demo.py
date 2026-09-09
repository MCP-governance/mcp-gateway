#!/usr/bin/env python3
"""Minimal two-VM MCP gateway demo using only the Python standard library."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PROTOCOL = "2026-07-28"
SERVER_ID = "demo-mcp"
UPSTREAM_TOKEN = os.environ.get("MCP_DEMO_UPSTREAM_TOKEN", "demo-upstream-only")
TOOLS = {
    "safe_echo": {
        "name": "safe_echo",
        "description": "Return non-sensitive demo text.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string", "maxLength": 200}},
            "required": ["text"],
            "additionalProperties": False,
        },
    },
    "send_external": {
        "name": "send_external",
        "description": "Send data to an external destination. Demo-only high-risk sink.",
        "inputSchema": {
            "type": "object",
            "properties": {"destination": {"type": "string"}, "data": {"type": "string"}},
            "required": ["destination", "data"],
            "additionalProperties": False,
        },
    },
}


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_jsonl(path: str, event: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as stream:
        stream.write(canonical(event) + "\n")


def send_json(handler: BaseHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    raw = json.dumps(payload, ensure_ascii=False).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def rpc_error(request_id: object, policy_id: str, reason: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32001, "message": "MCP tool call denied", "data": {
            "decision": "DENY", "policy_id": policy_id, "reason": reason
        }},
    }


def read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0"))
    if not 0 < length <= 65536:
        raise ValueError("invalid request size")
    value = json.loads(handler.rfile.read(length))
    if not isinstance(value, dict):
        raise ValueError("request must be a JSON object")
    return value


class MCPServer(BaseHTTPRequestHandler):
    effects_path = "/tmp/mcp-demo/effects.jsonl"

    def log_message(self, *_args: object) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/health":
            send_json(self, {"ok": True, "role": "upstream-mcp-server", "server_id": SERVER_ID})
            return
        if self.path == "/effects":
            path = Path(self.effects_path)
            events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line] if path.exists() else []
            send_json(self, {"count": len(events), "events": events})
            return
        send_json(self, {"error": "not found"}, 404)

    def do_POST(self) -> None:
        if self.path != "/mcp":
            send_json(self, {"error": "not found"}, 404)
            return
        if self.headers.get("X-Gateway-Token") != UPSTREAM_TOKEN:
            send_json(self, {"error": "gateway authentication required"}, 401)
            return
        try:
            request = read_json(self)
        except (ValueError, json.JSONDecodeError) as exc:
            send_json(self, {"error": str(exc)}, 400)
            return
        request_id = request.get("id")
        method = request.get("method")
        if method == "tools/list":
            send_json(self, {"jsonrpc": "2.0", "id": request_id, "result": {"tools": list(TOOLS.values())}})
            return
        if method != "tools/call":
            send_json(self, rpc_error(request_id, "P-PROTO-001", "unsupported method"))
            return
        params = request.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        if name == "safe_echo":
            append_jsonl(self.effects_path, {"event": "upstream_effect", "effect": "safe_echo", "at": now()})
            result = {"content": [{"type": "text", "text": str(args.get("text", ""))}]}
        elif name == "send_external":
            append_jsonl(self.effects_path, {
                "event": "upstream_effect", "effect": "external_send",
                "destination": args.get("destination"),
                "data_sha256": hashlib.sha256(str(args.get("data", "")).encode()).hexdigest(),
                "at": now(),
            })
            result = {"content": [{"type": "text", "text": "simulated external send"}]}
        else:
            send_json(self, rpc_error(request_id, "MCP-ACCESS-001", "unknown tool"))
            return
        send_json(self, {"jsonrpc": "2.0", "id": request_id, "result": result})


class Gateway(BaseHTTPRequestHandler):
    upstream = "http://127.0.0.1:9001/mcp"
    audit_path = "/tmp/mcp-demo/gateway.jsonl"

    def log_message(self, *_args: object) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/health":
            send_json(self, {"ok": True, "role": "mcp-security-gateway", "upstream": self.upstream})
            return
        if self.path == "/audit":
            path = Path(self.audit_path)
            events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line] if path.exists() else []
            send_json(self, {"count": len(events), "events": events})
            return
        send_json(self, {"error": "not found"}, 404)

    def do_POST(self) -> None:
        if self.path != "/mcp":
            send_json(self, {"error": "not found"}, 404)
            return
        trace_id = uuid.uuid4().hex
        try:
            request = read_json(self)
        except (ValueError, json.JSONDecodeError) as exc:
            append_jsonl(self.audit_path, {"trace_id": trace_id, "decision": "DENY", "policy_id": "P-PROTO-001", "reason": str(exc), "at": now()})
            send_json(self, rpc_error(None, "P-PROTO-001", str(exc)))
            return

        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}
        name = params.get("name") if isinstance(params, dict) else None
        event = {"trace_id": trace_id, "request_id": request_id, "method": method, "tool": name, "agent_id": self.headers.get("X-Agent-Id", "demo-agent"), "at": now()}
        deny = None
        if self.headers.get("MCP-Protocol-Version") != PROTOCOL:
            deny = ("P-PROTO-001", "unsupported MCP protocol version")
        elif self.headers.get("Mcp-Method") != method:
            deny = ("P-PROTO-001", "Mcp-Method does not match JSON-RPC method")
        elif method == "tools/call" and self.headers.get("Mcp-Name") != name:
            deny = ("P-PROTO-001", "Mcp-Name does not match tool name")
        elif method == "tools/call" and name not in TOOLS:
            deny = ("MCP-ACCESS-001", "unregistered MCP tool")
        elif method == "tools/call" and name != "safe_echo":
            deny = ("P-EXFIL-001", "external sink requires explicit approval")
        elif method not in {"tools/list", "tools/call"}:
            deny = ("P-PROTO-001", "unsupported MCP method")

        if deny:
            policy_id, reason = deny
            event.update({"decision": "DENY", "policy_id": policy_id, "reason": reason, "upstream_called": False})
            append_jsonl(self.audit_path, event)
            send_json(self, rpc_error(request_id, policy_id, reason))
            return

        try:
            raw = json.dumps(request, ensure_ascii=False).encode()
            upstream_request = Request(self.upstream, data=raw, method="POST", headers={
                "Content-Type": "application/json", "MCP-Protocol-Version": PROTOCOL, "X-Gateway-Token": UPSTREAM_TOKEN,
            })
            with urlopen(upstream_request, timeout=5) as result:
                upstream_result = json.loads(result.read())
        except (HTTPError, URLError, TimeoutError) as exc:
            event.update({"decision": "DENY", "policy_id": "P-UPSTREAM-001", "reason": str(exc), "upstream_called": False})
            append_jsonl(self.audit_path, event)
            send_json(self, rpc_error(request_id, "P-UPSTREAM-001", "upstream unavailable"), 502)
            return
        event.update({"decision": "ALLOW", "policy_id": "P-ALLOW-001", "reason": "approved tool and protocol", "upstream_called": True})
        append_jsonl(self.audit_path, event)
        send_json(self, upstream_result)


def post(url: str, payload: dict, headers: dict[str, str]) -> dict:
    request = Request(url, data=json.dumps(payload).encode(), method="POST", headers={"Content-Type": "application/json", **headers})
    with urlopen(request, timeout=5) as result:
        return json.loads(result.read())


def run_client(gateway: str) -> None:
    cases = [
        ("allowed safe_echo", "safe_echo", {"text": "demo message"}, "safe_echo"),
        ("blocked external sink", "send_external", {"destination": "partner.example", "data": "synthetic PII"}, "send_external"),
        ("blocked unregistered tool", "not_registered", {}, "not_registered"),
    ]
    for label, tool, arguments, header_name in cases:
        payload = {"jsonrpc": "2.0", "id": uuid.uuid4().hex, "method": "tools/call", "params": {"name": tool, "arguments": arguments}}
        print(json.dumps({"case": label, "result": post(gateway, payload, {"MCP-Protocol-Version": PROTOCOL, "Mcp-Method": "tools/call", "Mcp-Name": header_name})}, ensure_ascii=False))
    mismatch = {"jsonrpc": "2.0", "id": "header-mismatch", "method": "tools/call", "params": {"name": "safe_echo", "arguments": {"text": "x"}}}
    print(json.dumps({"case": "blocked header/body mismatch", "result": post(gateway, mismatch, {"MCP-Protocol-Version": PROTOCOL, "Mcp-Method": "tools/call", "Mcp-Name": "send_external"})}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    server = sub.add_parser("server")
    server.add_argument("--host", default="0.0.0.0")
    server.add_argument("--port", type=int, default=9001)
    server.add_argument("--effects", default="/tmp/mcp-demo/effects.jsonl")
    gateway = sub.add_parser("gateway")
    gateway.add_argument("--host", default="0.0.0.0")
    gateway.add_argument("--port", type=int, default=8080)
    gateway.add_argument("--upstream", default="http://192.168.85.130:9001/mcp")
    gateway.add_argument("--audit", default="/tmp/mcp-demo/gateway.jsonl")
    client = sub.add_parser("client")
    client.add_argument("--gateway", default="http://127.0.0.1:8080/mcp")
    sub.add_parser("self-test")
    args = parser.parse_args()
    if args.command == "self-test":
        assert "safe_echo" in TOOLS and "send_external" in TOOLS
        print("self-test: PASS")
    elif args.command == "server":
        MCPServer.effects_path = args.effects
        ThreadingHTTPServer((args.host, args.port), MCPServer).serve_forever()
    elif args.command == "gateway":
        Gateway.upstream, Gateway.audit_path = args.upstream, args.audit
        ThreadingHTTPServer((args.host, args.port), Gateway).serve_forever()
    else:
        run_client(args.gateway)


if __name__ == "__main__":
    main()
