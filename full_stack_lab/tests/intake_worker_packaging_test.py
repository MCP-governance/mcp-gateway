"""Check local worker imports against image COPY inputs without Docker or services."""
from __future__ import annotations

import ast
from importlib.machinery import PathFinder
from pathlib import Path, PurePosixPath
import shlex
import shutil
import tempfile
import unittest


LAB = Path(__file__).resolve().parent.parent
SOURCE = LAB / "supply_chain"


class IntakeWorkerPackagingTest(unittest.TestCase):
    def test_local_import_closure_is_packaged(self):
        local = {path.stem: path for path in SOURCE.glob("*.py")}
        pending, required = ["intake_worker"], set()
        while pending:
            name = pending.pop()
            if name in required:
                continue
            required.add(name)
            tree = ast.parse(local[name].read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module]
                pending.extend(name for name in names if name in local and name not in required)

        # Only COPY inputs may satisfy imports: the checkout on sys.path hid this omission.
        with tempfile.TemporaryDirectory(prefix="intake-packaging-", dir=LAB) as folder:
            app = Path(folder)
            for line in (SOURCE / "intake-worker.Dockerfile").read_text(encoding="utf-8").splitlines():
                if not line.lstrip().upper().startswith("COPY "):
                    continue
                parts = shlex.split(line, comments=True)
                if any(p.startswith("--from=") for p in parts):
                    continue
                sources = [part for part in parts[1:-1] if not part.startswith("--")]
                destination = PurePosixPath(parts[-1])
                for source in sources:
                    if source.endswith(".py") and destination.parent == PurePosixPath("/app"):
                        shutil.copyfile(SOURCE / source, app / destination.name)
            for name in sorted(required):
                with self.subTest(module=name):
                    self.assertIsNotNone(PathFinder.find_spec(name, [str(app)]),
                                         f"Local worker dependency missing from /app: {name}")


if __name__ == "__main__":
    unittest.main()
