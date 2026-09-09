# Tiny MCP policy-gateway demo

One MCP JSON-RPC server with a read-only ruleset: `read_document` passes and `delete_document` is blocked.

```bash
docker compose run --build --rm demo
```

Expected result: `PASS: read_document allowed; delete_document blocked`.
