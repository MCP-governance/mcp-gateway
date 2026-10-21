"""Capture local checks with timestamps and raw output, without product services."""
import ast
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent


def main():
    commands = [
        [sys.executable, "-B", "-X", "utf8", "full_stack_lab/tests/run_local_suite.py", "--out",
         "research/llm-wiki/analysis/dev81-direct-helper/local-suite.json"],
        [sys.executable, "-B", "-X", "utf8", "-m", "unittest", "discover", "-s", "full_stack_lab/tests", "-p",
         "header_broker_pathname_check.py", "-v"],
        [sys.executable, "-B", "-X", "utf8", "-m", "unittest", "discover", "-s", "full_stack_lab/tests", "-p",
         "header_broker_label_check.py", "-v"],
        [sys.executable, "-B", "-X", "utf8", "-m", "pyflakes", "endpoint-agent/enforce-linux.py",
         "full_stack_lab/tests/header_broker_pathname_check.py", str(HERE / "check_parser.py"),
         str(HERE / "collect_sources.py"), str(Path(__file__).resolve())],
    ]
    records = []
    for command in commands:
        started = datetime.now(timezone.utc).isoformat()
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=1200)
        records.append({"command": command, "started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(),
                        "exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
        print(json.dumps({"command": command, "exit_code": result.returncode}, ensure_ascii=False), flush=True)
    suite = HERE / "local-suite.json"
    suite.write_text(suite.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    inventory = []
    for path in sorted((ROOT / "full_stack_lab/tests").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        # Candidate inventory only: a literal name is not itself proof of extraction.
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value in ("profile", "bound_profile"):
                inventory.append({"file": path.relative_to(ROOT).as_posix(), "line": node.lineno, "symbol": node.value})
    sources = ["endpoint-agent/enforce-linux.py", "full_stack_lab/tests/header_broker_pathname_check.py",
               "full_stack_lab/tests/header_broker_label_check.py"]
    report = {"generated_utc": datetime.now(timezone.utc).isoformat(), "python": sys.version,
              "checks": records, "literal_inventory": inventory,
              "sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources},
              "merge_allowed": False,
              "reason": "Existing assertion requires main decision; direct-exec harness path remains unavailable in pinned Codex source"}
    (HERE / "checks.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return int(any(r["exit_code"] != 0 for r in records))


if __name__ == "__main__":
    raise SystemExit(main())
