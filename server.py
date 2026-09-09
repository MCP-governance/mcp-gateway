#!/usr/bin/env python3
import json
import sys

ALLOWED_TOOLS = {"read_document"}  # One demo ruleset: read-only tools pass.

TOOLS = [
    {"name": "read_document", "description": "Read a demo document.", "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
    {"name": "delete_document", "description": "Delete a demo document.", "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
]


def reply(request_id, result):
    print(json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}), flush=True)


def handle(request):
    method, params = request.get("method"), request.get("params", {})
    if method == "initialize":
        return {"protocolVersion": params.get("protocolVersion", "2025-03-26"), "capabilities": {"tools": {}}, "serverInfo": {"name": "tiny-policy-gateway", "version": "0.1.0"}}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        name = params.get("name")
        if name not in ALLOWED_TOOLS:
            return {"content": [{"type": "text", "text": f"BLOCKED by read-only ruleset: {name}"}], "isError": True}
        return {"content": [{"type": "text", "text": f"ALLOWED: document {params.get('arguments', {}).get('id', 'demo')}"}]}
    return {"content": [{"type": "text", "text": f"Unknown method: {method}"}], "isError": True}


for line in sys.stdin:
    request = json.loads(line)
    if "id" in request:
        reply(request["id"], handle(request))
