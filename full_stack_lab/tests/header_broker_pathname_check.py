"""Pathname socket policy regression; kernel and harness effects are separate checks."""
import ast
import unittest
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[2]


def render(mode="enforce"):
    source = (ROOT / "endpoint-agent/enforce-linux.py").read_text(encoding="utf-8")
    nodes = [n for n in ast.parse(source).body
             if isinstance(n, ast.FunctionDef) and n.name in {"profile", "bound_profile"}
             or isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "TOOLS" for t in n.targets)]
    namespace = {"Path": Path, "BASE": PurePosixPath("/usr/local/lib/mcpgw-enforcement")}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "enforce-linux.py", "exec"), namespace)
    return namespace["profile"]("mcpgw-unit", PurePosixPath("/fixed/login-shell"), "/home/unit",
        {"codex": PurePosixPath("/opt/approved/codex"), "claude": PurePosixPath("/opt/approved/claude")},
        True, True, {"codex": [PurePosixPath("/opt/approved/codex-code-mode-host")]}, mode)


class PathnamePolicy(unittest.TestCase):
    def test_pathname_is_mediated_by_file_rules(self):
        text = render()
        self.assertNotIn('addr="/run/', text)
        self.assertEqual(text.count("  /run/mcpgw-unit.sock rw,"), 3)
        self.assertEqual(text.count("  deny /run/mcpgw-unit.sock rw,"), 5)

    def test_no_abstract_socket_connect_or_coarse_unix_allow(self):
        text = render()
        self.assertIn("unix (create, getattr, getopt, setopt, shutdown) type=stream addr=none,", text)
        self.assertNotIn("unix (connect", text)
        self.assertNotIn("peer=(label=unconfined)", text)
        self.assertNotIn("network unix", text)
        credential = text.split("profile mcpgw-unit-bound-credential {", 1)[1]
        self.assertIn("/run/mcpgw-unit.sock rw,", credential)
        self.assertIn("/usr/bin/python3", credential)

    def test_shell_children_cannot_regain_credential(self):
        text = render()
        for key in ("codex", "claude"):
            harness = text.split("profile mcpgw-unit-bound-" + key + " {", 1)[1].split("\n}\n", 1)[0]
            tool = text.split("profile mcpgw-unit-bound-" + key + "-tool {", 1)[1].split("\n}\n", 1)[0]
            self.assertIn("} px -> mcpgw-unit-bound-" + key + "-tool,", harness)
            self.assertIn("header-helper px -> mcpgw-unit-bound-credential,", harness)
            self.assertIn("deny /run/mcpgw-unit.sock rw,", tool)
            self.assertIn("header-helper x,", tool)
            self.assertNotIn("header-helper px", tool)
        self.assertNotIn("change_profile", text)

    def test_warning_stage_is_preserved(self):
        self.assertNotIn("-bound-", render("warn"))
        self.assertIn("header-helper px -> mcpgw-unit-credential,", render("warn"))


if __name__ == "__main__":
    unittest.main()
