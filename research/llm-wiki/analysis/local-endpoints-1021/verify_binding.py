"""Reproduce local D-183 checks without installing policy or contacting a device."""
import ast
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
SOURCES = ("endpoint-agent/broker_binding.py", "endpoint-agent/managed-linux.py",
           "endpoint-agent/enforce-linux.py", "full_stack_lab/gateway/app/agent_service.py",
           "full_stack_lab/tests/header_broker_label_check.py")


def main():
    records = []
    for pattern in ("header_broker_label_check.py", "managed_token_cache_check.py",
                    "managed_helper_unavailable_check.py", "user_command_settings_check.py",
                    "managed_enforcement_check.py", "loopback_owner_replies_test.py", "launcher_pin_check.py"):
        command = [sys.executable, "-B", "-X", "utf8", "-m", "unittest", "discover", "-s", "full_stack_lab/tests", "-p", pattern, "-v"]
        started = datetime.now(timezone.utc).isoformat()
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        records.append({"command": command, "started_utc": started,
                        "finished_utc": datetime.now(timezone.utc).isoformat(), "exit_code": result.returncode,
                        "stdout": result.stdout, "stderr": result.stderr})
    command = [sys.executable, "-B", "-X", "utf8", "-m", "pyflakes", *SOURCES]
    started = datetime.now(timezone.utc).isoformat()
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    records.append({"command": command, "started_utc": started, "exit_code": result.returncode,
                    "stdout": result.stdout, "stderr": result.stderr})
    for relative in SOURCES:
        compile((ROOT / relative).read_text(encoding="utf-8"), relative, "exec")
    # Render the actual strict renderer using Linux paths, even on the Windows host.
    source = ROOT / "full_stack_lab/tests/header_broker_label_check.py"
    spec = importlib.util.spec_from_file_location("binding_checks", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rendered = module.ENFORCER.profile("mcpgw-unit", PurePosixPath("/fixed/login-shell"), "/home/unit",
        {"codex": PurePosixPath("/opt/approved/codex"), "claude": PurePosixPath("/opt/approved/claude")},
        True, True, {"codex": [PurePosixPath("/opt/approved/codex-code-mode-host")]}, "enforce")
    (HERE / "binding-profile.apparmor").write_text(rendered, encoding="utf-8", newline="\n")
    parser = shutil.which("apparmor_parser")
    if parser:
        command = [parser, "-Q", "-T", str(HERE / "binding-profile.apparmor")]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
        records.append({"command": command, "started_utc": datetime.now(timezone.utc).isoformat(),
                        "exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
    # Save the function-extraction inventory requested by the owner.
    inventory = []
    for base in (ROOT / "full_stack_lab/tests", ROOT / "endpoint-agent"):
        for path in base.rglob("*.py"):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if any('"' + name + '"' in line for name in ("checks", "profile", "serve", "bound_profile")):
                    inventory.append({"path": path.relative_to(ROOT).as_posix(), "line": number})
    symbols = []
    for relative in SOURCES:
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in {
                    "enforcing_profiles", "kernel_ready", "peer_label", "authorize_peer", "checks", "install",
                    "serve", "Header", "handle", "profile", "bound_profile"}:
                symbols.append({"path": relative, "symbol": node.name, "line": node.lineno, "end_line": node.end_lineno})
    report = {"generated_utc": datetime.now(timezone.utc).isoformat(), "environment": sys.version,
              "scope": "local static and substituted unit checks; no kernel, device, harness or MCP execution",
              "checks": records, "compile": {"status": "pass", "files": list(SOURCES)},
              "apparmor_parser": {"available": bool(parser), "status": "executed" if parser else "incomplete"},
              "extraction_inventory": inventory,
              "code_symbols": symbols,
              "sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCES}}
    (HERE / "binding-checks.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                             encoding="utf-8", newline="\n")
    for record in records:
        print(json.dumps({"command": record["command"], "exit_code": record["exit_code"]}, ensure_ascii=False))
    print("compile: pass; apparmor_parser: " + ("executed" if parser else "incomplete"))
    return int(any(r["exit_code"] for r in records) or not parser)


if __name__ == "__main__":
    raise SystemExit(main())
