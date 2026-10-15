#!/usr/bin/env python3
"""Probe pinned GhidraMCP on PJ1 using a synthetic, never-executed ELF."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import struct
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


TASK = Path("/home/pj1/mcpgw-ghidra-20261014")
SCRATCH = Path("/dev/shm/mcpgw-ghidra-20261014")
GHIDRA = SCRATCH / "runtime/ghidra"
JDK = SCRATCH / "runtime/jdk"
EXTENSION = TASK / "artifacts/GhidraMCP.jar"
PYTHON = TASK / "venv/bin/python"


def write_synthetic_elf(path: Path) -> str:
    # ELF64 ET_EXEC with mov eax,42; ret. Ghidra imports it; no process executes it.
    code = bytes.fromhex("b82a000000c3")
    offset = 64 + 56
    base = 0x400000
    entry = base + offset
    ident = b"\x7fELF" + bytes((2, 1, 1, 0, 0)) + bytes(7)
    header = struct.pack("<16sHHIQQQIHHHHHH", ident, 2, 62, 1, entry, 64, 0, 0, 64, 56, 1, 0, 0, 0)
    phdr = struct.pack("<IIQQQQQQ", 1, 5, 0, base, base, offset + len(code), offset + len(code), 0x1000)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + phdr + code)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_process_tree(pid: int) -> list[dict]:
    pending = [pid]
    found: list[dict] = []
    while pending:
        current = pending.pop()
        base = Path(f"/proc/{current}")
        if not base.exists():
            continue
        try:
            status = (base / "status").read_text(errors="replace")
            uid_line = next((line for line in status.splitlines() if line.startswith("Uid:")), "")
            comm = (base / "comm").read_text(errors="replace").strip()
            profile = (base / "attr/current").read_text(errors="replace").strip()
            cmdline = (base / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").strip()
            children = (base / "task" / str(current) / "children").read_text().split()
        except (OSError, StopIteration):
            continue
        # This command has no credential inputs; still redact credential-looking flags defensively.
        words = cmdline.split()
        safe_words: list[str] = []
        redact_next = False
        for word in words:
            if redact_next:
                safe_words.append("[redacted]")
                redact_next = False
            elif any(term in word.lower() for term in ("token", "password", "secret", "api-key", "credential")):
                safe_words.append("[redacted-flag]")
                redact_next = "=" not in word
            else:
                safe_words.append(word)
        found.append({"pid": current, "comm": comm, "uid_line": uid_line, "profile": profile, "cmdline": safe_words})
        pending.extend(int(child) for child in children if child.isdecimal())
    return found


def listeners_for(pids: set[int]) -> list[str]:
    try:
        result = subprocess.run(["ss", "-ltnpH"], check=False, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [line for line in result.stdout.splitlines() if any(f"pid={pid}," in line for pid in pids)]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--hold-seconds", type=int, default=90)
    args = parser.parse_args()
    if os.getuid() != 1000:
        raise SystemExit("probe requires pj1 UID 1000")
    if args.hold_seconds < 0 or args.hold_seconds > 120:
        raise SystemExit("hold must be between 0 and 120 seconds")

    run_dir = TASK / "artifacts/run"
    binary = run_dir / "synthetic_return_42.elf"
    evidence_path = TASK / "logs/mcp-probe.json"
    binary_sha = write_synthetic_elf(binary)
    env = os.environ.copy()
    env["GHIDRA_INSTALL_DIR"] = str(GHIDRA)
    env["JAVA_HOME"] = str(JDK)
    env["PATH"] = str(JDK / "bin") + os.pathsep + env.get("PATH", "")
    env["TMPDIR"] = str(SCRATCH / "tmp")
    env["JAVA_TOOL_OPTIONS"] = "-Xmx512m -Dfile.encoding=UTF-8 -Duser.home=" + str(TASK / "artifacts/java-home")
    Path(env["JAVA_TOOL_OPTIONS"].split("-Duser.home=", 1)[1]).mkdir(parents=True, exist_ok=True)
    Path(env["TMPDIR"]).mkdir(parents=True, exist_ok=True)

    command = [
        str(PYTHON), "-m", "ghidra_mcp", "--headless", "--binary", str(binary),
        "--ghidra-install-dir", str(GHIDRA), "--extension-jar", str(EXTENSION),
    ]
    proc = subprocess.Popen(
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", bufsize=1, env=env,
    )
    responses: queue.Queue[str | None] = queue.Queue()
    stderr: list[str] = []
    messages: list[dict] = []

    def collect_stdout() -> None:
        assert proc.stdout
        for line in proc.stdout:
            responses.put(line)
        responses.put(None)

    def collect_stderr() -> None:
        assert proc.stderr
        for line in proc.stderr:
            stderr.append(line.rstrip())

    out_thread = threading.Thread(target=collect_stdout, daemon=True)
    err_thread = threading.Thread(target=collect_stderr, daemon=True)
    out_thread.start()
    err_thread.start()
    assert proc.stdin

    def persist(stage: str) -> None:
        processes = read_process_tree(proc.pid)
        tree_pids = {entry["pid"] for entry in processes}
        evidence.update({
            "stage": stage,
            "process_tree": processes,
            "owned_listeners": listeners_for(tree_pids),
            "stderr": list(stderr),
            "messages": list(messages),
        })
        tmp = evidence_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(evidence_path)

    evidence: dict = {
        "time_kst_started": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
        "device_user_uid": os.getuid(),
        "device_apparmor_profile": Path("/proc/self/attr/current").read_text(errors="replace").strip(),
        "ghidra": "12.1.4",
        "ghidra_source_commit": "8b6bbb857accdfa20dc5b2f5dea471178c2e9fbc",
        "ghidramcp": "2.0.0",
        "ghidramcp_source_commit": "1e980252087b2479a21b9ca6d82d5829538651a7",
        "jdk": "Temurin 21.0.12.1+1",
        "python": "3.12.3",
        "mcp_sdk": "1.30.0",
        "pyghidra": "3.1.0",
        "jpype1": "1.5.2",
        "ghidra_runtime_root": str(GHIDRA),
        "java_home": str(JDK),
        "extension_jar_sha256": hashlib.sha256(EXTENSION.read_bytes()).hexdigest(),
        "command": command,
        "binary_path": str(binary),
        "binary_sha256": binary_sha,
        "stdio_pid": proc.pid,
        "stdio_uid": os.getuid(),
        "messages": messages,
    }

    def request(method: str, params: dict, request_id: int, timeout: int = 300) -> dict:
        message = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        proc.stdin.write(json.dumps(message) + "\n")
        proc.stdin.flush()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                line = responses.get(timeout=1)
            except queue.Empty:
                if proc.poll() is not None:
                    break
                continue
            if line is None:
                break
            response = json.loads(line)
            messages.append(response)
            if response.get("id") == request_id:
                return response
        raise RuntimeError(f"No response for {method}; exit={proc.poll()}; stderr={' | '.join(stderr[-40:])}")

    try:
        evidence["initialize"] = request("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "pj1-synthetic-ghidra-probe", "version": "1.0"},
        }, 1)
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()
        evidence["tools_list"] = request("tools/list", {}, 2)
        evidence["read_call"] = request("tools/call", {"name": "get_program_info", "arguments": {}}, 3)
        time.sleep(1)
        persist("mcp_connected_read_call_success_hold_started")
        print(json.dumps({
            "probe_ready": True,
            "pid": proc.pid,
            "uid": os.getuid(),
            "profile": evidence["device_apparmor_profile"],
            "tool_count": len(evidence["tools_list"].get("result", {}).get("tools", [])),
            "read_call_isError": evidence["read_call"].get("result", {}).get("isError"),
            "listeners": evidence.get("owned_listeners", []),
            "evidence_path": str(evidence_path),
            "hold_seconds": args.hold_seconds,
        }, ensure_ascii=False), flush=True)
        time.sleep(args.hold_seconds)
        evidence["hold_completed"] = True
    except Exception as exc:
        evidence["error"] = f"{type(exc).__name__}: {exc}"
        persist("probe_failed")
    finally:
        try:
            proc.stdin.close()
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        except OSError:
            proc.kill()
        time.sleep(0.5)
        out_thread.join(timeout=2)
        err_thread.join(timeout=2)
        evidence["process_exit_code"] = proc.returncode
        evidence["stderr"] = list(stderr)
        evidence["messages"] = list(messages)
        evidence["time_kst_finished"] = datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
        tmp = evidence_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(evidence_path)

    return 1 if "error" in evidence else 0


if __name__ == "__main__":
    raise SystemExit(main())
