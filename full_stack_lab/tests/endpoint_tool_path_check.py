"""Which route a reported MCP call took (D-301): Codex writes a server id's "-" as "_" in its tool names.

pj3 10-31: approved Hugging Face calls from Codex arrived as huggingface_co_b272ed53 and were filed as a local MCP,
which raised an unregistered-MCP alert for an approved server.
"""
import ast
import pathlib
import sys
import types

SOURCE = pathlib.Path(__file__).resolve().parent.parent / "gateway" / "app" / "endpoint_plane.py"
tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
wanted = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in ("canonical_server", "tool_path")]
registry = types.SimpleNamespace(servers=lambda: {"huggingface-co-b272ed53": {}, "context7": {}})
package = types.ModuleType("app")
package.registry = registry
sys.modules["app"], sys.modules["app.registry"] = package, registry
namespace = {"__package__": "app"}
exec(compile(ast.Module(body=wanted, type_ignores=[]), str(SOURCE), "exec"), namespace)
canonical, path = namespace["canonical_server"], namespace["tool_path"]

assert canonical("huggingface_co_b272ed53") == "huggingface-co-b272ed53"
assert canonical("huggingface-co-b272ed53") == "huggingface-co-b272ed53"
assert path(canonical("huggingface_co_b272ed53")) == "gateway"
assert canonical("ghidra") == "ghidra" and path("ghidra") == "local"
assert path("claude_ai_Gmail") == "connector" and path("codex_apps") == "connector"
print("PASS endpoint tool path: Codex server names map to registry ids")
