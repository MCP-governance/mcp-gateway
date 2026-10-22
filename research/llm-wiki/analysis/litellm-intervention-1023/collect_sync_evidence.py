"""Reproduce authorized local checks; never start a stack or connect to a device."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).with_name("sync-evidence.json")
PY = [sys.executable, "-B", "-X", "utf8"]
CODE = ["full_stack_lab/gateway/app/" + name for name in (
    "litellm_sync.py", "litellm_sync_tables.sql", "core.py", "main.py", "ops_response.py", "decommission.py", "agent_service.py",
    "agent_static/console.js")]
CODE += ["full_stack_lab/tests/litellm_sync_check.py", "full_stack_lab/tests/ai_gateway_addon_check.py",
         "full_stack_lab/compose.yaml", "addons/litellm/sync-bindings.example.json",
         "research/llm-wiki/analysis/litellm-intervention-1023/collect_sync_evidence.py",
         "research/llm-wiki/analysis/litellm-intervention-1023/sync-requirements.json",
         "research/llm-wiki/analysis/litellm-intervention-1023/sync-implementation.md", "docs/ai/LITELLM_SYNC.md"]


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, encoding="utf-8").strip()


def main():
    result = {"task": "AIG-01-LITELLM-SYNC", "baseline_commit": "e30be961a9a00d7982dd8565e4412c7289e85f4d",
              "head": git("rev-parse", "HEAD"), "branch": git("branch", "--show-current"),
              "scope": "local_static_and_management_http_double_only", "deployment": False, "device_connections": False,
              "real_litellm": False, "real_postgresql": False, "job_timeout_seconds": 3600,
              "inbox_ids": [8322, 8330, 8336, 8366, 8370, 8371], "inbox_last_event_id": 8377,
              "inbox_observed_at": "2026-10-23T07:09:11+09:00",
              "overlap": "No initial dirty files or detected overlap with W5-KIT-MACOS/unassigned work. Earlier jobs and quota notices are evidence, not new authorization. Assigned P1 scope only.",
              "remote_head_check": "failed_network_restricted", "source_bytes_sha256_available": False,
              "quota": {"remaining_percent_at_dispatch": 31.0, "latest_observed_remaining_percent": 84,
                        "observed_at_epoch": 1792706950.1842968, "current_remaining_percent": None,
                        "known_reset": "2026-10-30T02:08:54+09:00", "reset_at_epoch": 1793293734,
                        "prior_reset": "2026-10-23T07:08:54+09:00"}, "files": [], "checks": []}
    if result["head"] != result["baseline_commit"] or result["branch"] != "10/23-litellm-sync":
        raise SystemExit("HEAD/branch changed; reconcile before collecting evidence")
    for name in CODE:
        raw = (ROOT / name).read_bytes()
        item = {"path": name, "sha256": hashlib.sha256(raw).hexdigest()}
        if name.endswith(".py"):
            tree = ast.parse(raw.decode("utf-8"), filename=name)
            item["symbols"] = [{"name": node.name, "line": node.lineno, "end_line": node.end_lineno}
                               for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        result["files"].append(item)
    python_files = [p for p in CODE if p.endswith(".py")]
    commands = [
        ("litellm-sync-unit", PY + ["full_stack_lab/tests/litellm_sync_check.py"]),
        ("existing-addon", PY + ["full_stack_lab/tests/ai_gateway_addon_check.py"]),
        ("ops-response", PY + ["full_stack_lab/tests/ops_response_check.py"]),
        ("sbom-impact", PY + ["full_stack_lab/tests/sbom_impact_check.py"]),
        ("intake-oneclick-ast", PY + ["full_stack_lab/tests/intake_one_click_ast_check.py"]),
        ("pyflakes", PY + ["-m", "pyflakes", *python_files]),
        ("python-syntax", PY + ["-c", "import ast;from pathlib import Path;paths=" + repr(python_files)
                                + ";[ast.parse(Path(p).read_text(encoding='utf-8'),filename=p) for p in paths];print('AST PASS',len(paths))"]),
        ("console-syntax", ["node", "--check", "full_stack_lab/gateway/app/agent_static/console.js"]),
        ("console-state", ["node", "--test", "full_stack_lab/tests/console-state.test.mjs"]),
        ("intake-ui", ["node", "--test", "full_stack_lab/tests/intake_one_click_ui_check.mjs"]),
        ("open-endpoints", PY + ["full_stack_lab/tests/open_endpoints.py"]),
        ("git-whitespace", ["git", "diff", "--check"]),
        ("existing-test-unchanged", ["git", "diff", "--exit-code", "--", "full_stack_lab/tests/ai_gateway_addon_check.py"]),
        ("wiki-build", PY + ["research/llm-wiki/tools/build_wiki.py"]),
        ("wiki-check", PY + ["research/llm-wiki/tools/check_wiki.py", "--ci-ignored-local-sources"]),
        ("trace-ids", PY + ["research/llm-wiki/tools/check_trace.py", "--no-fetch"]),
    ]
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name, command in commands:
        started = datetime.now(timezone.utc).isoformat()
        process = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=60,
                                 env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        output = (process.stdout + process.stderr).decode("utf-8", errors="replace")
        result["checks"].append({"name": name, "command": command, "started_at": started,
                                 "returncode": process.returncode, "status": "passed" if process.returncode == 0 else "failed",
                                 "output": output})
        print(name + ": " + ("PASS" if process.returncode == 0 else "FAIL"))
    result["not_run"] = ["Real PostgreSQL contention/rollback/process crash", "Solution field up deployment",
                         "LiteLLM 1.105 management API and independent call effect", "PJ1 actual harness", "Browser rendering",
                         "Immutable upstream commit source-byte verification"]
    result["working_tree"] = git("status", "--short").splitlines()
    result["recorded_at"] = datetime.now(timezone.utc).isoformat()
    result["all_checks_passed"] = all(c["returncode"] == 0 for c in result["checks"])
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("Evidence: " + str(OUT.relative_to(ROOT)))
    return 0 if result["all_checks_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
