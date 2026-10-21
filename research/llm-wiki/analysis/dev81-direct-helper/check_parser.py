"""Offline parser evidence only: -Q never loads policy into the kernel."""
import importlib.util
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent


def main():
    spec = importlib.util.spec_from_file_location("pathname_checks", ROOT / "full_stack_lab/tests/header_broker_pathname_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    records = []
    with tempfile.TemporaryDirectory(prefix="dev81-parser-") as directory:
        for stage in ("warn", "enforce"):
            text = module.render(stage)
            path = Path(directory) / (stage + ".apparmor")
            path.write_text(text, encoding="utf-8")
            command = ["apparmor_parser", "-Q", "-T", str(path)]
            started = datetime.now(timezone.utc).isoformat()
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            records.append({"stage": stage, "command": command, "started_utc": started,
                            "exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
        # The original committed specimen is the negative control; never overwrite it.
        path = ROOT / "research/llm-wiki/analysis/local-endpoints-1021/binding-profile.apparmor"
        command = ["apparmor_parser", "-Q", "-T", str(path)]
        started = datetime.now(timezone.utc).isoformat()
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        records.append({"stage": "historical-invalid-control", "command": command, "started_utc": started,
                        "exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
    version = subprocess.run(["apparmor_parser", "--version"], capture_output=True, text=True, check=True).stdout
    ok = all(r["exit_code"] == 0 for r in records[:2]) and records[2]["exit_code"] != 0 and "invalid value for addr" in records[2]["stderr"]
    report = {"generated_utc": datetime.now(timezone.utc).isoformat(), "parser_version": version,
              "scope": "offline compiler only; no kernel load, account change, credential or MCP call",
              "checks": records, "passed": ok}
    (HERE / "parser-results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(not ok)


if __name__ == "__main__":
    raise SystemExit(main())
