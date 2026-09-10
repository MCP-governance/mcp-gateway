from app.policy_core import PATH_CLASSES, classify_path, sha256, sign_assertion, verify_assertion


call = {
    "request_id": "req-1",
    "session_id": "session-1",
    "user_id": "admin-1",
    "agent_id": "lab-agent",
    "tool_call_id": "call-1",
    "server_id": "file-mcp",
    "tool_name": "read_file",
    "arguments": {"path": "/data/sensitive/secret.txt"},
}

assert classify_path("/data/public/notice.txt") == "public"
assert classify_path("/not-allowed") is None
assert sha256(PATH_CLASSES) == sha256(PATH_CLASSES)
signature = sign_assertion(call, "admin", "test-secret")
assert verify_assertion(call, "admin", signature, "test-secret")
assert not verify_assertion(call, "customer", signature, "test-secret")
print("gateway policy self-check: PASS")
