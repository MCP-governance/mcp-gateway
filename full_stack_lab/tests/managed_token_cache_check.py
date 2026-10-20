"""Keep the Linux helper credential alive across its normal observation cycle."""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENT = ROOT / "endpoint-agent" / "managed-linux.py"


class ManagedTokenCache(unittest.TestCase):
    def test_cache_covers_observers_and_active_poll_sleep(self):
        tree = ast.parse(AGENT.read_text(encoding="utf-8"))
        cache_seconds = next(
            node.value for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "TOKEN_CACHE_SECONDS"
                    for target in node.targets)
        )
        self.assertIsInstance(cache_seconds, ast.Constant)
        self.assertGreaterEqual(cache_seconds.value, 2 * 40 + 60)
        self.assertLess(cache_seconds.value, 300)

        update = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "update"
            and any(isinstance(arg, ast.keyword) and arg.arg == "token" for arg in node.keywords)
        )
        until = next(arg.value for arg in update.keywords if arg.arg == "until")
        self.assertTrue(
            isinstance(until, ast.BinOp)
            and isinstance(until.right, ast.Name)
            and until.right.id == "TOKEN_CACHE_SECONDS"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
