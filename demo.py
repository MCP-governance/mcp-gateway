#!/usr/bin/env python3
import json
import subprocess
import sys


server = subprocess.Popen([sys.executable, "server.py"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)


def call(method, params=None):
    call.number += 1
    server.stdin.write(json.dumps({"jsonrpc": "2.0", "id": call.number, "method": method, "params": params or {}}) + "\n")
    server.stdin.flush()
    return json.loads(server.stdout.readline())["result"]


call.number = 0
assert call("initialize", {"protocolVersion": "2025-03-26"})["capabilities"]["tools"] == {}
assert {tool["name"] for tool in call("tools/list")["tools"]} == {"read_document", "delete_document"}
assert call("tools/call", {"name": "read_document", "arguments": {"id": "demo-1"}})["content"][0]["text"] == "ALLOWED: document demo-1"
assert call("tools/call", {"name": "delete_document", "arguments": {"id": "demo-1"}})["isError"] is True
server.terminate()
print("PASS: read_document allowed; delete_document blocked")
